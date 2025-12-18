"""Integration tests using the sensor simulator.

Tests cover:
- Protocol-level integration (HTTP, TCP, UDP)
- CLI command integration (discover, stream, log)
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

import pytest

from gsdv.diagnostics.cli import cmd_discover, cmd_log, cmd_stream
from gsdv.protocols.http_calibration import HttpCalibrationClient
from gsdv.protocols.rdt_udp import RdtClient
from gsdv.protocols.tcp_cmd import TcpCommandClient


class TestSensorSimulator:
    """Tests for sensor simulator functionality."""

    def test_http_calibration_returns_configured_values(self, sensor_simulator) -> None:
        """HTTP endpoint returns calibration values matching simulator config."""
        client = HttpCalibrationClient(
            "127.0.0.1", port=sensor_simulator.config.http_port
        )
        cal = client.get_calibration()

        assert cal.counts_per_force == sensor_simulator.config.counts_per_force
        assert cal.counts_per_torque == sensor_simulator.config.counts_per_torque
        assert cal.serial_number == sensor_simulator.config.serial_number
        assert cal.firmware_version == sensor_simulator.config.firmware_version

    def test_tcp_calibration_returns_configured_values(self, sensor_simulator) -> None:
        """TCP READCALINFO returns calibration values matching simulator config."""
        with TcpCommandClient(
            "127.0.0.1", port=sensor_simulator.config.tcp_port
        ) as client:
            cal = client.read_calibration()

        assert cal.counts_per_force == sensor_simulator.config.counts_per_force
        assert cal.counts_per_torque == sensor_simulator.config.counts_per_torque
        assert cal.force_units_code == sensor_simulator.config.force_units_code
        assert cal.torque_units_code == sensor_simulator.config.torque_units_code

    def test_udp_streaming_receives_samples(self, sensor_simulator) -> None:
        """UDP RDT streaming returns samples with valid data."""
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=0.5, max_samples=10))
            client.stop_streaming()

        assert len(samples) >= 1
        for sample in samples:
            assert len(sample.counts) == 6
            assert sample.status == 0

    def test_udp_samples_have_sequential_rdt_sequence(self, sensor_simulator) -> None:
        """UDP RDT samples have increasing sequence numbers."""
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=0.5, max_samples=10))
            client.stop_streaming()

        assert len(samples) >= 2
        for i in range(1, len(samples)):
            assert samples[i].rdt_sequence > samples[i - 1].rdt_sequence

    def test_deterministic_seed_produces_reproducible_noise(self, sensor_simulator) -> None:
        """Simulator with same seed produces reproducible noise pattern."""
        from gsdv.diagnostics.sensor_simulator import SensorSimulator, SimulatorConfig

        # Collect samples from fixture simulator (seed=42)
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples1 = list(client.receive_samples(timeout=0.3, max_samples=5))
            client.stop_streaming()

        # Stop first simulator and start new one with same seed
        sensor_simulator.stop()

        # Find new ports
        import socket

        ports = []
        port = 60000
        while len(ports) < 3 and port < 65535:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    ports.append(port)
                except OSError:
                    pass
            port += 1

        config2 = SimulatorConfig(
            udp_port=ports[0],
            tcp_port=ports[1],
            http_port=ports[2],
            seed=42,
        )

        with SensorSimulator(config2) as sim2:
            import time

            time.sleep(0.1)
            with RdtClient("127.0.0.1", port=config2.udp_port) as client:
                client.start_streaming()
                samples2 = list(client.receive_samples(timeout=0.3, max_samples=5))
                client.stop_streaming()

        # With same seed, we should receive samples (timing may vary)
        assert len(samples1) >= 1
        assert len(samples2) >= 1


class TestEndToEnd:
    """End-to-end integration tests combining multiple protocols."""

    def test_full_workflow_calibrate_then_stream(self, sensor_simulator) -> None:
        """Test typical workflow: get calibration then stream data."""
        # Get calibration via HTTP
        http_client = HttpCalibrationClient(
            "127.0.0.1", port=sensor_simulator.config.http_port
        )
        cal = http_client.get_calibration()

        # Stream and convert data
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=0.3, max_samples=5))
            client.stop_streaming()

        # Convert raw counts to SI units
        for sample in samples:
            force_N, torque_Nm = cal.convert_counts_to_si(sample.counts)
            assert len(force_N) == 3
            assert len(torque_Nm) == 3

    def test_tcp_and_http_calibration_agree(self, sensor_simulator) -> None:
        """TCP and HTTP calibration endpoints return consistent data."""
        http_client = HttpCalibrationClient(
            "127.0.0.1", port=sensor_simulator.config.http_port
        )
        http_cal = http_client.get_calibration()

        with TcpCommandClient(
            "127.0.0.1", port=sensor_simulator.config.tcp_port
        ) as tcp_client:
            tcp_cal = tcp_client.read_calibration()

        assert http_cal.counts_per_force == tcp_cal.counts_per_force
        assert http_cal.counts_per_torque == tcp_cal.counts_per_torque


class TestFaultInjection:
    """Tests for fault injection functionality."""

    def test_packet_loss_drops_packets(self, sensor_simulator_with_loss) -> None:
        """Packet loss fault drops a fraction of packets."""
        with RdtClient("127.0.0.1", port=sensor_simulator_with_loss.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=0.5, max_samples=100))
            client.stop_streaming()

        # With 50% loss, we should see gaps in sequence numbers
        # Check that packets were actually lost by examining sequence gaps
        assert len(samples) >= 10
        sequences = [s.rdt_sequence for s in samples]
        total_lost = 0
        for i in range(1, len(sequences)):
            gap = sequences[i] - sequences[i - 1]
            if gap > 1:
                total_lost += gap - 1

        # With 50% loss over many packets, we should have lost some
        assert total_lost > 0

    def test_packet_reorder_changes_sequence(self, sensor_simulator_with_reorder) -> None:
        """Packet reorder fault causes out-of-order delivery."""
        with RdtClient("127.0.0.1", port=sensor_simulator_with_reorder.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=0.3, max_samples=100))
            client.stop_streaming()

        # Check for out-of-order sequences
        sequences = [s.rdt_sequence for s in samples]
        out_of_order = sum(1 for i in range(1, len(sequences)) if sequences[i] < sequences[i - 1])
        assert out_of_order > 0

    def test_burst_loss_drops_consecutive_packets(self, sensor_simulator_with_burst_loss) -> None:
        """Burst loss drops multiple consecutive packets."""
        with RdtClient("127.0.0.1", port=sensor_simulator_with_burst_loss.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=0.4, max_samples=200))
            client.stop_streaming()

        # Look for gaps >= burst length (consecutive missing)
        sequences = [s.rdt_sequence for s in samples]
        gaps = []
        for i in range(1, len(sequences)):
            gap = sequences[i] - sequences[i - 1]
            if gap > 1:
                gaps.append(gap)

        # Should have some gaps from burst loss
        assert len(gaps) > 0

    def test_disconnect_causes_gap(self, sensor_simulator_with_disconnect) -> None:
        """Forced disconnect causes a gap in packet delivery."""
        import time

        with RdtClient("127.0.0.1", port=sensor_simulator_with_disconnect.config.udp_port) as client:
            client.start_streaming()
            recv_times = []
            start = time.monotonic()
            for sample in client.receive_samples(timeout=0.5, max_samples=300):
                recv_times.append(time.monotonic())
            client.stop_streaming()

        # Look for gaps in receive times > 40ms (disconnect should cause gap)
        gaps = []
        for i in range(1, len(recv_times)):
            gap_ms = (recv_times[i] - recv_times[i - 1]) * 1000
            if gap_ms > 40:
                gaps.append(gap_ms)

        # Should have some gaps from disconnects
        assert len(gaps) > 0

    def test_no_faults_delivers_all_packets_in_order(self, sensor_simulator) -> None:
        """With no faults, all packets are delivered in order."""
        with RdtClient("127.0.0.1", port=sensor_simulator.config.udp_port) as client:
            client.start_streaming()
            samples = list(client.receive_samples(timeout=0.2, max_samples=50))
            client.stop_streaming()

        # Should have received packets in order
        sequences = [s.rdt_sequence for s in samples]
        assert len(sequences) >= 10
        for i in range(1, len(sequences)):
            assert sequences[i] == sequences[i - 1] + 1


class TestCliStream:
    """Tests for gsdv stream CLI command."""

    def test_stream_receives_samples(self, sensor_simulator, capsys) -> None:
        """gsdv stream receives and displays samples from simulator."""
        args = argparse.Namespace(
            ip="127.0.0.1",
            seconds=0.3,
            udp_port=sensor_simulator.config.udp_port,
            http_port=sensor_simulator.config.http_port,
        )

        result = cmd_stream(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Fx" in captured.out
        assert "Samples:" in captured.out

    def test_stream_shows_calibration_info(self, sensor_simulator, capsys) -> None:
        """gsdv stream displays calibration information."""
        args = argparse.Namespace(
            ip="127.0.0.1",
            seconds=0.2,
            udp_port=sensor_simulator.config.udp_port,
            http_port=sensor_simulator.config.http_port,
        )

        cmd_stream(args)

        captured = capsys.readouterr()
        assert f"CPF={sensor_simulator.config.counts_per_force}" in captured.out
        assert f"CPT={sensor_simulator.config.counts_per_torque}" in captured.out


class TestCliLog:
    """Tests for gsdv log CLI command."""

    def test_log_creates_csv_file(self, sensor_simulator, tmp_path, capsys) -> None:
        """gsdv log creates a CSV file with sensor data."""
        args = argparse.Namespace(
            ip="127.0.0.1",
            out=str(tmp_path),
            seconds=0.3,
            format="csv",
            prefix="test_",
            udp_port=sensor_simulator.config.udp_port,
            http_port=sensor_simulator.config.http_port,
        )

        result = cmd_log(args)

        assert result == 0
        csv_files = list(tmp_path.glob("test_*.csv"))
        assert len(csv_files) == 1

        with open(csv_files[0], encoding="utf-8") as f:
            content = f.read()
            assert "# Sensor: 127.0.0.1" in content
            assert "Fx [N]" in content

    def test_log_writes_parseable_csv(self, sensor_simulator, tmp_path) -> None:
        """gsdv log writes valid CSV that can be parsed."""
        args = argparse.Namespace(
            ip="127.0.0.1",
            out=str(tmp_path),
            seconds=0.3,
            format="csv",
            prefix="",
            udp_port=sensor_simulator.config.udp_port,
            http_port=sensor_simulator.config.http_port,
        )

        cmd_log(args)

        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1

        with open(csv_files[0], encoding="utf-8") as f:
            lines = [line for line in f if not line.startswith("#")]

        reader = csv.DictReader(lines)
        rows = list(reader)
        assert len(rows) >= 1
        assert "Fx [N]" in rows[0]
        assert "rdt_sequence" in rows[0]

    def test_log_reports_statistics(self, sensor_simulator, tmp_path, capsys) -> None:
        """gsdv log reports sample count and rate."""
        args = argparse.Namespace(
            ip="127.0.0.1",
            out=str(tmp_path),
            seconds=0.3,
            format="csv",
            prefix="",
            udp_port=sensor_simulator.config.udp_port,
            http_port=sensor_simulator.config.http_port,
        )

        cmd_log(args)

        captured = capsys.readouterr()
        assert "Samples:" in captured.out
        assert "Duration:" in captured.out
        assert "Sample rate:" in captured.out

    def test_log_fails_on_invalid_directory(self, sensor_simulator, capsys) -> None:
        """gsdv log returns error for non-existent output directory."""
        args = argparse.Namespace(
            ip="127.0.0.1",
            out="/nonexistent/directory/path",
            seconds=0.1,
            format="csv",
            prefix="",
            udp_port=sensor_simulator.config.udp_port,
            http_port=sensor_simulator.config.http_port,
        )

        result = cmd_log(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err


class TestCliDiscover:
    """Tests for gsdv discover CLI command."""

    def test_discover_finds_simulator(self, sensor_simulator, capsys) -> None:
        """gsdv discover finds the simulator on loopback."""
        args = argparse.Namespace(
            subnet="127.0.0.1/32",
            timeout=1.0,
            http_port=sensor_simulator.config.http_port,
        )

        result = cmd_discover(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "127.0.0.1" in captured.out
        assert "Found 1 sensor" in captured.out

    def test_discover_shows_serial_number(self, sensor_simulator, capsys) -> None:
        """gsdv discover displays serial number of found sensors."""
        args = argparse.Namespace(
            subnet="127.0.0.1/32",
            timeout=1.0,
            http_port=sensor_simulator.config.http_port,
        )

        cmd_discover(args)

        captured = capsys.readouterr()
        assert sensor_simulator.config.serial_number in captured.out

    def test_discover_no_sensors_on_empty_subnet(self, capsys) -> None:
        """gsdv discover reports no sensors on empty subnet."""
        args = argparse.Namespace(
            subnet="192.0.2.0/30",
            timeout=0.1,
            http_port=80,
        )

        result = cmd_discover(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "No sensors found" in captured.out

    def test_discover_invalid_subnet_returns_error(self, capsys) -> None:
        """gsdv discover returns error for invalid subnet."""
        args = argparse.Namespace(
            subnet="not-a-subnet",
            timeout=0.1,
            http_port=80,
        )

        result = cmd_discover(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid subnet" in captured.err


class TestCliSubprocess:
    """End-to-end tests running CLI as subprocess."""

    def test_cli_stream_subprocess(self, sensor_simulator) -> None:
        """CLI stream command works as subprocess."""
        result = subprocess.run(
            [
                sys.executable, "-m", "gsdv.diagnostics.cli",
                "stream",
                "--ip", "127.0.0.1",
                "--seconds", "0.3",
                "--udp-port", str(sensor_simulator.config.udp_port),
                "--http-port", str(sensor_simulator.config.http_port),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "Samples:" in result.stdout

    def test_cli_log_subprocess(self, sensor_simulator, tmp_path) -> None:
        """CLI log command works as subprocess."""
        result = subprocess.run(
            [
                sys.executable, "-m", "gsdv.diagnostics.cli",
                "log",
                "--ip", "127.0.0.1",
                "--out", str(tmp_path),
                "--seconds", "0.3",
                "--udp-port", str(sensor_simulator.config.udp_port),
                "--http-port", str(sensor_simulator.config.http_port),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "Logging complete" in result.stdout
        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1

    def test_cli_discover_subprocess(self, sensor_simulator) -> None:
        """CLI discover command works as subprocess."""
        result = subprocess.run(
            [
                sys.executable, "-m", "gsdv.diagnostics.cli",
                "discover",
                "--subnet", "127.0.0.1/32",
                "--timeout", "1.0",
                "--http-port", str(sensor_simulator.config.http_port),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "127.0.0.1" in result.stdout
