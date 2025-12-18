"""Sensor simulator for testing without hardware.

This module provides a simulated ATI NETrs sensor that implements:
- UDP RDT streaming at configurable rates
- TCP command interface (READCALINFO, WRITETRANSFORM, bias)
- HTTP calibration endpoint (/netftapi2.xml)
- Fault injection for testing error handling (loss, reorder, burst, disconnect)

The simulator can run standalone for manual testing or as a pytest fixture
for automated integration tests.
"""

import argparse
import collections
import math
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import numpy as np

from gsdv.protocols.rdt_udp import (
    RDT_HEADER,
    RDT_REQUEST_SIZE,
    RDT_RESPONSE_SIZE,
    REQUEST_FORMAT,
    RESPONSE_FORMAT,
    RdtCommand,
)
from gsdv.protocols.tcp_cmd import (
    CALINFO_REQUEST_SIZE,
    CALINFO_RESPONSE_SIZE,
    TCP_RESPONSE_HEADER,
    TcpCommand,
)


@dataclass
class FaultConfig:
    """Configuration for fault injection in the simulator.

    All probabilities are per-packet and should be in range [0.0, 1.0].
    """

    # Packet loss
    loss_probability: float = 0.0

    # Packet reordering
    reorder_probability: float = 0.0
    reorder_delay_packets: int = 2

    # Burst loss (multiple consecutive packets dropped)
    burst_loss_probability: float = 0.0
    burst_loss_length: int = 3

    # Forced disconnects (temporary stop of packet flow)
    disconnect_probability: float = 0.0
    disconnect_duration_ms: int = 100


@dataclass
class SimulatorConfig:
    """Configuration for the sensor simulator."""

    # Network ports
    udp_port: int = 49152
    tcp_port: int = 49151
    http_port: int = 8080  # Use non-privileged port by default

    # Streaming settings
    sample_rate_hz: int = 1000
    seed: Optional[int] = None

    # Calibration values
    counts_per_force: int = 1000000
    counts_per_torque: int = 1000000
    serial_number: str = "SIM-001"
    firmware_version: str = "1.0.0"
    force_units_code: int = 2  # N
    torque_units_code: int = 3  # N-m

    # Signal generation
    signal_amplitude: int = 100000
    signal_frequency_hz: float = 1.0
    noise_stddev: int = 1000

    # Fault injection
    faults: FaultConfig = field(default_factory=FaultConfig)


@dataclass
class SimulatorState:
    """Mutable state for the simulator."""

    streaming: bool = False
    streaming_client: Optional[tuple[str, int]] = None
    rdt_sequence: int = 0
    ft_sequence: int = 0
    bias_offset: np.ndarray = field(default_factory=lambda: np.zeros(6, dtype=np.int32))
    running: bool = True

    # Fault injection state
    burst_loss_remaining: int = 0
    disconnect_until: float = 0.0


class SensorSimulator:
    """Simulated ATI NETrs sensor for testing.

    Implements UDP RDT streaming, TCP commands, and HTTP calibration.

    Example:
        >>> config = SimulatorConfig(udp_port=49152, tcp_port=49151, http_port=8080)
        >>> sim = SensorSimulator(config)
        >>> sim.start()
        >>> # ... run tests ...
        >>> sim.stop()
    """

    def __init__(self, config: Optional[SimulatorConfig] = None) -> None:
        """Initialize the simulator.

        Args:
            config: Simulator configuration. Uses defaults if not provided.
        """
        self.config = config or SimulatorConfig()
        self.state = SimulatorState()
        self._rng = np.random.default_rng(self.config.seed)

        self._udp_socket: Optional[socket.socket] = None
        self._tcp_socket: Optional[socket.socket] = None
        self._http_server: Optional[HTTPServer] = None

        self._udp_thread: Optional[threading.Thread] = None
        self._tcp_thread: Optional[threading.Thread] = None
        self._http_thread: Optional[threading.Thread] = None
        self._streaming_thread: Optional[threading.Thread] = None

        self._start_time = time.monotonic()

        # Reorder buffer for out-of-order packet simulation
        self._reorder_buffer: collections.deque[bytes] = collections.deque()

    def _generate_sample(self) -> np.ndarray:
        """Generate a simulated sensor sample.

        Returns:
            Array of 6 int32 counts [Fx, Fy, Fz, Tx, Ty, Tz].
        """
        t = time.monotonic() - self._start_time
        freq = self.config.signal_frequency_hz
        amp = self.config.signal_amplitude

        # Generate sinusoidal signals with phase offsets
        base = np.array([
            amp * math.sin(2 * math.pi * freq * t),
            amp * math.sin(2 * math.pi * freq * t + math.pi / 3),
            amp * math.sin(2 * math.pi * freq * t + 2 * math.pi / 3),
            amp * math.sin(2 * math.pi * freq * t + math.pi),
            amp * math.sin(2 * math.pi * freq * t + 4 * math.pi / 3),
            amp * math.sin(2 * math.pi * freq * t + 5 * math.pi / 3),
        ], dtype=np.float64)

        # Add noise
        noise = self._rng.normal(0, self.config.noise_stddev, 6)

        # Apply bias offset and convert to int32
        counts = (base + noise - self.state.bias_offset).astype(np.int32)
        return counts

    def _build_rdt_response(self, counts: np.ndarray) -> bytes:
        """Build an RDT response packet.

        Args:
            counts: Array of 6 int32 counts.

        Returns:
            36-byte RDT response packet.
        """
        return struct.pack(
            RESPONSE_FORMAT,
            self.state.rdt_sequence,
            self.state.ft_sequence,
            0,  # status
            counts[0], counts[1], counts[2],
            counts[3], counts[4], counts[5],
        )

    def _should_drop_packet(self) -> bool:
        """Determine if the current packet should be dropped due to faults.

        Returns:
            True if the packet should be dropped, False if it should be sent.
        """
        faults = self.config.faults

        # Check if in burst loss
        if self.state.burst_loss_remaining > 0:
            self.state.burst_loss_remaining -= 1
            return True

        # Check for new burst loss
        if faults.burst_loss_probability > 0:
            if self._rng.random() < faults.burst_loss_probability:
                self.state.burst_loss_remaining = faults.burst_loss_length - 1
                return True

        # Check for single packet loss
        if faults.loss_probability > 0:
            if self._rng.random() < faults.loss_probability:
                return True

        return False

    def _send_packet(self, response: bytes) -> None:
        """Send a packet, possibly with reordering.

        Args:
            response: The packet data to send.
        """
        if self._udp_socket is None or self.state.streaming_client is None:
            return

        faults = self.config.faults

        # Check for reordering
        if faults.reorder_probability > 0 and self._rng.random() < faults.reorder_probability:
            # Buffer this packet for delayed sending
            self._reorder_buffer.append(response)
            if len(self._reorder_buffer) >= faults.reorder_delay_packets:
                # Send the oldest buffered packet instead
                response = self._reorder_buffer.popleft()
        elif self._reorder_buffer:
            # Randomly flush a buffered packet
            response = self._reorder_buffer.popleft()

        try:
            self._udp_socket.sendto(response, self.state.streaming_client)
        except OSError:
            pass

    def _streaming_loop(self) -> None:
        """Main streaming loop - sends RDT packets at configured rate."""
        interval = 1.0 / self.config.sample_rate_hz
        next_send = time.monotonic()
        faults = self.config.faults

        while self.state.running and self.state.streaming:
            now = time.monotonic()

            # Check for disconnect fault
            if self.state.disconnect_until > 0:
                if now < self.state.disconnect_until:
                    # Still disconnected, skip packet generation
                    next_send = now + interval
                    time.sleep(max(0, interval * 0.9))
                    continue
                else:
                    # Disconnect period ended
                    self.state.disconnect_until = 0.0

            if now >= next_send:
                if self.state.streaming_client and self._udp_socket:
                    counts = self._generate_sample()
                    response = self._build_rdt_response(counts)

                    # Apply fault injection
                    if not self._should_drop_packet():
                        self._send_packet(response)

                    self.state.rdt_sequence = (self.state.rdt_sequence + 1) & 0xFFFFFFFF
                    self.state.ft_sequence = (self.state.ft_sequence + 1) & 0xFFFFFFFF

                    # Check for new disconnect fault
                    if faults.disconnect_probability > 0:
                        if self._rng.random() < faults.disconnect_probability:
                            self.state.disconnect_until = now + faults.disconnect_duration_ms / 1000.0

                next_send += interval
                if next_send < now:
                    next_send = now + interval
            else:
                time.sleep(max(0, next_send - now - 0.0001))

    def _handle_udp(self) -> None:
        """Handle incoming UDP RDT requests."""
        if self._udp_socket is None:
            return

        self._udp_socket.settimeout(0.1)

        while self.state.running:
            try:
                data, addr = self._udp_socket.recvfrom(RDT_REQUEST_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            if len(data) != RDT_REQUEST_SIZE:
                continue

            header, command, sample_count = struct.unpack(REQUEST_FORMAT, data)
            if header != RDT_HEADER:
                continue

            if command == RdtCommand.START_REALTIME:
                self.state.streaming_client = addr
                self.state.streaming = True
                self.state.rdt_sequence = 0
                self.state.ft_sequence = 0
                if self._streaming_thread is None or not self._streaming_thread.is_alive():
                    self._streaming_thread = threading.Thread(target=self._streaming_loop, daemon=True)
                    self._streaming_thread.start()

            elif command == RdtCommand.STOP:
                self.state.streaming = False

            elif command == RdtCommand.SET_BIAS:
                # Store current values as bias offset
                self.state.bias_offset = self._generate_sample()

    def _handle_tcp_client(self, client_socket: socket.socket) -> None:
        """Handle a TCP client connection."""
        client_socket.settimeout(1.0)

        try:
            while self.state.running:
                try:
                    data = client_socket.recv(CALINFO_REQUEST_SIZE)
                except socket.timeout:
                    continue
                except OSError:
                    break

                if not data:
                    break

                command = data[0]

                if command == TcpCommand.READCALINFO:
                    response = struct.pack(
                        ">HBBII6H",
                        TCP_RESPONSE_HEADER,
                        self.config.force_units_code,
                        self.config.torque_units_code,
                        self.config.counts_per_force,
                        self.config.counts_per_torque,
                        1, 1, 1, 1, 1, 1,  # scale factors
                    )
                    client_socket.sendall(response)

                elif command == TcpCommand.READFT:
                    # Check for bias flag
                    if len(data) >= 20:
                        sys_commands = struct.unpack_from(">H", data, 18)[0]
                        if sys_commands & 0x0001:
                            self.state.bias_offset = self._generate_sample()

                elif command == TcpCommand.WRITETRANSFORM:
                    # Accept transform command (no response needed)
                    pass

        finally:
            client_socket.close()

    def _handle_tcp(self) -> None:
        """Accept and handle TCP connections."""
        if self._tcp_socket is None:
            return

        self._tcp_socket.settimeout(0.1)

        while self.state.running:
            try:
                client_socket, _ = self._tcp_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            # Handle client in a separate thread
            client_thread = threading.Thread(
                target=self._handle_tcp_client,
                args=(client_socket,),
                daemon=True,
            )
            client_thread.start()

    def _create_http_handler(self) -> type:
        """Create an HTTP request handler class with access to simulator config."""
        config = self.config

        class CalibrationHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass  # Suppress logging

            def do_GET(self) -> None:
                if self.path == "/netftapi2.xml":
                    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<netftapi2>
    <cfgcpf>{config.counts_per_force}</cfgcpf>
    <cfgcpt>{config.counts_per_torque}</cfgcpt>
    <cfgfu>{config.force_units_code}</cfgfu>
    <cfgtu>{config.torque_units_code}</cfgtu>
    <setserial>{config.serial_number}</setserial>
    <setfwver>{config.firmware_version}</setfwver>
</netftapi2>"""
                    self.send_response(200)
                    self.send_header("Content-Type", "application/xml")
                    self.send_header("Content-Length", str(len(xml)))
                    self.end_headers()
                    self.wfile.write(xml.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

        return CalibrationHandler

    def _handle_http(self) -> None:
        """Run the HTTP server."""
        if self._http_server is None:
            return

        self._http_server.timeout = 0.1
        while self.state.running:
            self._http_server.handle_request()

    def start(self) -> None:
        """Start the simulator."""
        self.state.running = True
        self._start_time = time.monotonic()

        # Start UDP server
        self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp_socket.bind(("", self.config.udp_port))
        self._udp_thread = threading.Thread(target=self._handle_udp, daemon=True)
        self._udp_thread.start()

        # Start TCP server
        self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp_socket.bind(("", self.config.tcp_port))
        self._tcp_socket.listen(5)
        self._tcp_thread = threading.Thread(target=self._handle_tcp, daemon=True)
        self._tcp_thread.start()

        # Start HTTP server
        handler_class = self._create_http_handler()
        self._http_server = HTTPServer(("", self.config.http_port), handler_class)
        self._http_thread = threading.Thread(target=self._handle_http, daemon=True)
        self._http_thread.start()

    def stop(self) -> None:
        """Stop the simulator."""
        self.state.running = False
        self.state.streaming = False

        # Wait for threads to finish
        if self._streaming_thread and self._streaming_thread.is_alive():
            self._streaming_thread.join(timeout=1.0)
        if self._udp_thread and self._udp_thread.is_alive():
            self._udp_thread.join(timeout=1.0)
        if self._tcp_thread and self._tcp_thread.is_alive():
            self._tcp_thread.join(timeout=1.0)
        if self._http_thread and self._http_thread.is_alive():
            self._http_thread.join(timeout=1.0)

        # Close sockets
        if self._udp_socket:
            self._udp_socket.close()
            self._udp_socket = None
        if self._tcp_socket:
            self._tcp_socket.close()
            self._tcp_socket = None
        if self._http_server:
            self._http_server.server_close()
            self._http_server = None

    def __enter__(self) -> "SensorSimulator":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.stop()


def main() -> None:
    """Run the sensor simulator as a standalone application."""
    parser = argparse.ArgumentParser(
        description="ATI NETrs sensor simulator for testing",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--udp-port", type=int, default=49152, help="UDP RDT port")
    parser.add_argument("--tcp-port", type=int, default=49151, help="TCP command port")
    parser.add_argument("--http-port", type=int, default=8080, help="HTTP calibration port")
    parser.add_argument("--rate", type=int, default=1000, help="Sample rate in Hz")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for deterministic output")
    parser.add_argument("--cpf", type=int, default=1000000, help="Counts per force")
    parser.add_argument("--cpt", type=int, default=1000000, help="Counts per torque")

    # Fault injection arguments
    parser.add_argument("--loss", type=float, default=0.0, help="Packet loss probability (0.0-1.0)")
    parser.add_argument("--reorder", type=float, default=0.0, help="Packet reorder probability (0.0-1.0)")
    parser.add_argument("--reorder-delay", type=int, default=2, help="Reorder delay in packets")
    parser.add_argument("--burst-loss", type=float, default=0.0, help="Burst loss probability (0.0-1.0)")
    parser.add_argument("--burst-length", type=int, default=3, help="Burst loss length in packets")
    parser.add_argument("--disconnect", type=float, default=0.0, help="Disconnect probability (0.0-1.0)")
    parser.add_argument("--disconnect-ms", type=int, default=100, help="Disconnect duration in milliseconds")

    args = parser.parse_args()

    fault_config = FaultConfig(
        loss_probability=args.loss,
        reorder_probability=args.reorder,
        reorder_delay_packets=args.reorder_delay,
        burst_loss_probability=args.burst_loss,
        burst_loss_length=args.burst_length,
        disconnect_probability=args.disconnect,
        disconnect_duration_ms=args.disconnect_ms,
    )

    config = SimulatorConfig(
        udp_port=args.udp_port,
        tcp_port=args.tcp_port,
        http_port=args.http_port,
        sample_rate_hz=args.rate,
        seed=args.seed,
        counts_per_force=args.cpf,
        counts_per_torque=args.cpt,
        faults=fault_config,
    )

    print("Starting sensor simulator...")
    print(f"  UDP RDT port:     {config.udp_port}")
    print(f"  TCP command port: {config.tcp_port}")
    print(f"  HTTP port:        {config.http_port}")
    print(f"  Sample rate:      {config.sample_rate_hz} Hz")
    if any([args.loss, args.reorder, args.burst_loss, args.disconnect]):
        print("  Faults enabled:")
        if args.loss > 0:
            print(f"    Loss:       {args.loss:.0%}")
        if args.reorder > 0:
            print(f"    Reorder:    {args.reorder:.0%} ({args.reorder_delay} packets)")
        if args.burst_loss > 0:
            print(f"    Burst loss: {args.burst_loss:.0%} ({args.burst_length} packets)")
        if args.disconnect > 0:
            print(f"    Disconnect: {args.disconnect:.0%} ({args.disconnect_ms}ms)")
    print()
    print("Press Ctrl+C to stop.")

    with SensorSimulator(config) as sim:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping simulator...")


if __name__ == "__main__":
    main()
