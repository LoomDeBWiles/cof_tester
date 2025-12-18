"""Command-line interface for diagnostics and automation.

This module provides CLI commands for:
- Discovering sensors on the local network
- Streaming data from a sensor
- Logging data to files
- Running the sensor simulator
"""

import argparse
import csv
import ipaddress
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from gsdv.models import CalibrationInfo
from gsdv.protocols.http_calibration import (
    HttpCalibrationClient,
    HttpCalibrationError,
    get_calibration_with_fallback,
)
from gsdv.protocols.rdt_udp import RdtClient
from gsdv.protocols.tcp_cmd import TcpCommandClient


def cmd_discover(args: argparse.Namespace) -> int:
    """Discover sensors on the local network."""
    subnet = args.subnet
    timeout = args.timeout

    print(f"Scanning {subnet} for ATI NETrs sensors...")
    print()

    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as e:
        print(f"Error: Invalid subnet: {e}", file=sys.stderr)
        return 1

    found = []
    for ip in network.hosts():
        ip_str = str(ip)
        try:
            client = HttpCalibrationClient(ip_str, timeout=timeout)
            cal = client.get_calibration()
            found.append((ip_str, cal))
            print(f"  Found: {ip_str}")
            if cal.serial_number:
                print(f"    Serial: {cal.serial_number}")
            if cal.firmware_version:
                print(f"    Firmware: {cal.firmware_version}")
            print(f"    CPF: {cal.counts_per_force}, CPT: {cal.counts_per_torque}")
            print()
        except (HttpCalibrationError, OSError):
            pass

    if not found:
        print("No sensors found.")
        return 0

    print(f"Found {len(found)} sensor(s).")
    return 0


def cmd_stream(args: argparse.Namespace) -> int:
    """Stream data from a sensor and display to console."""
    ip = args.ip
    seconds = args.seconds
    udp_port = args.udp_port
    http_port = args.http_port

    # Get calibration
    print(f"Connecting to {ip}...")
    try:
        cal = get_calibration_with_fallback(ip, http_port=http_port)
    except Exception as e:
        print(f"Error: Failed to get calibration: {e}", file=sys.stderr)
        return 1

    print(f"Calibration: CPF={cal.counts_per_force}, CPT={cal.counts_per_torque}")
    if cal.serial_number:
        print(f"Serial: {cal.serial_number}")
    print()

    # Stream data
    print("Streaming data (press Ctrl+C to stop):")
    print()
    print(f"{'Seq':>8}  {'Fx':>10}  {'Fy':>10}  {'Fz':>10}  {'Tx':>10}  {'Ty':>10}  {'Tz':>10}")
    print("-" * 80)

    start_time = time.monotonic()
    sample_count = 0

    with RdtClient(ip, port=udp_port) as client:
        client.start_streaming()

        try:
            for sample in client.receive_samples(timeout=0.5):
                force_N, torque_Nm = cal.convert_counts_to_si(sample.counts)

                print(
                    f"{sample.rdt_sequence:>8}  "
                    f"{force_N[0]:>10.3f}  {force_N[1]:>10.3f}  {force_N[2]:>10.3f}  "
                    f"{torque_Nm[0]:>10.6f}  {torque_Nm[1]:>10.6f}  {torque_Nm[2]:>10.6f}"
                )

                sample_count += 1

                if seconds is not None and (time.monotonic() - start_time) >= seconds:
                    break

        except KeyboardInterrupt:
            print()

    elapsed = time.monotonic() - start_time
    stats = client.statistics
    sample_rate = sample_count / elapsed if elapsed > 0 else 0

    print()
    print(f"Samples: {sample_count}")
    print(f"Duration: {elapsed:.2f}s")
    print(f"Sample rate: {sample_rate:.1f} Hz")
    print(f"Packets lost: {stats.packets_lost}")

    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """Log data to a file."""
    ip = args.ip
    output_dir = Path(args.out)
    seconds = args.seconds
    format_type = args.format
    prefix = args.prefix or ""
    udp_port = args.udp_port
    http_port = args.http_port

    # Validate output directory
    if not output_dir.exists():
        print(f"Error: Output directory does not exist: {output_dir}", file=sys.stderr)
        return 1
    if not output_dir.is_dir():
        print(f"Error: Not a directory: {output_dir}", file=sys.stderr)
        return 1

    # Get calibration
    print(f"Connecting to {ip}...")
    try:
        cal = get_calibration_with_fallback(ip, http_port=http_port)
    except Exception as e:
        print(f"Error: Failed to get calibration: {e}", file=sys.stderr)
        return 1

    print(f"Calibration: CPF={cal.counts_per_force}, CPT={cal.counts_per_torque}")

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if format_type == "tsv":
        ext = "tsv"
        delimiter = "\t"
    else:
        ext = "csv"
        delimiter = ","

    filename = f"{prefix}{timestamp}.{ext}" if prefix else f"{timestamp}.{ext}"
    output_path = output_dir / filename

    print(f"Logging to: {output_path}")
    print()

    # Open file and start streaming
    start_time = time.monotonic()
    sample_count = 0

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        # Add BOM for Excel compatibility
        if format_type == "excel_compatible":
            f.write("\ufeff")

        writer = csv.writer(f, delimiter=delimiter)

        # Write metadata header
        f.write(f"# Sensor: {ip}\n")
        f.write(f"# Serial: {cal.serial_number or 'N/A'}\n")
        f.write(f"# Firmware: {cal.firmware_version or 'N/A'}\n")
        f.write(f"# CPF: {cal.counts_per_force}\n")
        f.write(f"# CPT: {cal.counts_per_torque}\n")
        f.write(f"# Start: {datetime.now().isoformat()}\n")

        # Write header row
        writer.writerow([
            "timestamp_utc",
            "t_monotonic_ns",
            "rdt_sequence",
            "ft_sequence",
            "status",
            "Fx [N]",
            "Fy [N]",
            "Fz [N]",
            "Tx [N-m]",
            "Ty [N-m]",
            "Tz [N-m]",
        ])

        with RdtClient(ip, port=udp_port) as client:
            client.start_streaming()

            try:
                for sample in client.receive_samples(timeout=0.5):
                    force_N, torque_Nm = cal.convert_counts_to_si(sample.counts)

                    writer.writerow([
                        datetime.utcnow().isoformat(),
                        sample.t_monotonic_ns,
                        sample.rdt_sequence,
                        sample.ft_sequence,
                        sample.status,
                        f"{force_N[0]:.6f}",
                        f"{force_N[1]:.6f}",
                        f"{force_N[2]:.6f}",
                        f"{torque_Nm[0]:.9f}",
                        f"{torque_Nm[1]:.9f}",
                        f"{torque_Nm[2]:.9f}",
                    ])

                    sample_count += 1

                    # Progress update every 1000 samples
                    if sample_count % 1000 == 0:
                        elapsed = time.monotonic() - start_time
                        rate = sample_count / elapsed if elapsed > 0 else 0
                        print(f"\rSamples: {sample_count}, Rate: {rate:.1f} Hz", end="", flush=True)

                    if seconds is not None and (time.monotonic() - start_time) >= seconds:
                        break

            except KeyboardInterrupt:
                print()

    elapsed = time.monotonic() - start_time
    stats = client.statistics
    sample_rate = sample_count / elapsed if elapsed > 0 else 0
    file_size = output_path.stat().st_size

    print()
    print(f"Logging complete.")
    print(f"  Samples: {sample_count}")
    print(f"  Duration: {elapsed:.2f}s")
    print(f"  Sample rate: {sample_rate:.1f} Hz")
    print(f"  Packets lost: {stats.packets_lost}")
    print(f"  File size: {file_size / 1024:.1f} KB")

    return 0


def cmd_simulate_sensor(args: argparse.Namespace) -> int:
    """Run the sensor simulator."""
    from gsdv.diagnostics.sensor_simulator import SimulatorConfig, main as simulator_main

    # Re-invoke the simulator main with the same arguments
    # This is a workaround to use the existing argument parsing in sensor_simulator.py
    simulator_main()
    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GSDV - Gamma Sensor Data Viewer CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # discover command
    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover sensors on the local network",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    discover_parser.add_argument(
        "--subnet",
        default="192.168.1.0/24",
        help="Subnet to scan",
    )
    discover_parser.add_argument(
        "--timeout",
        type=float,
        default=0.5,
        help="Timeout per host in seconds",
    )
    discover_parser.set_defaults(func=cmd_discover)

    # stream command
    stream_parser = subparsers.add_parser(
        "stream",
        help="Stream data from a sensor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    stream_parser.add_argument(
        "--ip",
        required=True,
        help="Sensor IP address",
    )
    stream_parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Duration to stream in seconds (default: unlimited)",
    )
    stream_parser.add_argument(
        "--udp-port",
        type=int,
        default=49152,
        help="UDP RDT port",
    )
    stream_parser.add_argument(
        "--http-port",
        type=int,
        default=80,
        help="HTTP calibration port",
    )
    stream_parser.set_defaults(func=cmd_stream)

    # log command
    log_parser = subparsers.add_parser(
        "log",
        help="Log data to a file",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    log_parser.add_argument(
        "--ip",
        required=True,
        help="Sensor IP address",
    )
    log_parser.add_argument(
        "--out",
        required=True,
        help="Output directory",
    )
    log_parser.add_argument(
        "--format",
        choices=["csv", "tsv", "excel_compatible"],
        default="csv",
        help="Output format",
    )
    log_parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Duration to log in seconds (default: unlimited)",
    )
    log_parser.add_argument(
        "--prefix",
        default="",
        help="Filename prefix",
    )
    log_parser.add_argument(
        "--udp-port",
        type=int,
        default=49152,
        help="UDP RDT port",
    )
    log_parser.add_argument(
        "--http-port",
        type=int,
        default=80,
        help="HTTP calibration port",
    )
    log_parser.set_defaults(func=cmd_log)

    # simulate-sensor command
    sim_parser = subparsers.add_parser(
        "simulate-sensor",
        help="Run the sensor simulator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sim_parser.add_argument("--udp-port", type=int, default=49152, help="UDP RDT port")
    sim_parser.add_argument("--tcp-port", type=int, default=49151, help="TCP command port")
    sim_parser.add_argument("--http-port", type=int, default=8080, help="HTTP calibration port")
    sim_parser.add_argument("--rate", type=int, default=1000, help="Sample rate in Hz")
    sim_parser.add_argument("--seed", type=int, default=None, help="Random seed for deterministic output")
    sim_parser.set_defaults(func=cmd_simulate_sensor)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
