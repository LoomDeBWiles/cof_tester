"""Tests for UDP RDT (Raw Data Transfer) streaming protocol."""

import socket
import struct
import threading
import time
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

from gsdv.models import SampleRecord
from gsdv.protocols.rdt_udp import (
    RDT_HEADER,
    RDT_PORT,
    RDT_REQUEST_SIZE,
    RDT_RESPONSE_SIZE,
    REQUEST_FORMAT,
    RESPONSE_FORMAT,
    RdtClient,
    RdtCommand,
    RdtStatistics,
    build_rdt_request,
    parse_rdt_response,
)


class TestRdtCommand:
    """Tests for RDT command enum values."""

    def test_stop_command_value(self) -> None:
        assert RdtCommand.STOP == 0x0000

    def test_start_realtime_command_value(self) -> None:
        assert RdtCommand.START_REALTIME == 0x0002

    def test_start_buffered_command_value(self) -> None:
        assert RdtCommand.START_BUFFERED == 0x0003

    def test_set_bias_command_value(self) -> None:
        assert RdtCommand.SET_BIAS == 0x0042


class TestProtocolConstants:
    """Tests for protocol constants."""

    def test_rdt_port(self) -> None:
        assert RDT_PORT == 49152

    def test_rdt_header(self) -> None:
        assert RDT_HEADER == 0x1234

    def test_request_size(self) -> None:
        assert RDT_REQUEST_SIZE == 8

    def test_response_size(self) -> None:
        assert RDT_RESPONSE_SIZE == 36


class TestBuildRdtRequest:
    """Tests for building RDT request packets."""

    def test_request_size_is_8_bytes(self) -> None:
        request = build_rdt_request(RdtCommand.START_REALTIME)
        assert len(request) == RDT_REQUEST_SIZE

    def test_request_header_is_correct(self) -> None:
        request = build_rdt_request(RdtCommand.STOP)
        header = struct.unpack(">H", request[:2])[0]
        assert header == RDT_HEADER

    def test_start_realtime_command_encoded(self) -> None:
        request = build_rdt_request(RdtCommand.START_REALTIME)
        command = struct.unpack(">H", request[2:4])[0]
        assert command == 0x0002

    def test_stop_command_encoded(self) -> None:
        request = build_rdt_request(RdtCommand.STOP)
        command = struct.unpack(">H", request[2:4])[0]
        assert command == 0x0000

    def test_bias_command_encoded(self) -> None:
        request = build_rdt_request(RdtCommand.SET_BIAS)
        command = struct.unpack(">H", request[2:4])[0]
        assert command == 0x0042

    def test_sample_count_default_zero(self) -> None:
        request = build_rdt_request(RdtCommand.START_REALTIME)
        sample_count = struct.unpack(">I", request[4:8])[0]
        assert sample_count == 0

    def test_sample_count_custom_value(self) -> None:
        request = build_rdt_request(RdtCommand.START_REALTIME, sample_count=1000)
        sample_count = struct.unpack(">I", request[4:8])[0]
        assert sample_count == 1000

    def test_request_format_big_endian(self) -> None:
        request = build_rdt_request(RdtCommand.START_REALTIME, sample_count=256)
        header, command, sample_count = struct.unpack(REQUEST_FORMAT, request)
        assert header == RDT_HEADER
        assert command == RdtCommand.START_REALTIME
        assert sample_count == 256


class TestParseRdtResponse:
    """Tests for parsing RDT response packets."""

    def _build_response(
        self,
        rdt_seq: int = 0,
        ft_seq: int = 0,
        status: int = 0,
        fx: int = 0,
        fy: int = 0,
        fz: int = 0,
        tx: int = 0,
        ty: int = 0,
        tz: int = 0,
    ) -> bytes:
        """Build a test response packet."""
        return struct.pack(
            RESPONSE_FORMAT,
            rdt_seq,
            ft_seq,
            status,
            fx,
            fy,
            fz,
            tx,
            ty,
            tz,
        )

    def test_parses_rdt_sequence(self) -> None:
        response = self._build_response(rdt_seq=12345)
        rdt_seq, _, _, _ = parse_rdt_response(response)
        assert rdt_seq == 12345

    def test_parses_ft_sequence(self) -> None:
        response = self._build_response(ft_seq=67890)
        _, ft_seq, _, _ = parse_rdt_response(response)
        assert ft_seq == 67890

    def test_parses_status(self) -> None:
        response = self._build_response(status=0x00FF)
        _, _, status, _ = parse_rdt_response(response)
        assert status == 0x00FF

    def test_parses_force_counts(self) -> None:
        response = self._build_response(fx=100, fy=-200, fz=300)
        _, _, _, counts = parse_rdt_response(response)
        assert counts[0] == 100
        assert counts[1] == -200
        assert counts[2] == 300

    def test_parses_torque_counts(self) -> None:
        response = self._build_response(tx=-400, ty=500, tz=-600)
        _, _, _, counts = parse_rdt_response(response)
        assert counts[3] == -400
        assert counts[4] == 500
        assert counts[5] == -600

    def test_parses_all_six_counts(self) -> None:
        response = self._build_response(fx=1, fy=2, fz=3, tx=4, ty=5, tz=6)
        _, _, _, counts = parse_rdt_response(response)
        assert counts == (1, 2, 3, 4, 5, 6)

    def test_parses_negative_counts(self) -> None:
        response = self._build_response(fx=-1000000, fy=-2000000, fz=-3000000)
        _, _, _, counts = parse_rdt_response(response)
        assert counts[0] == -1000000
        assert counts[1] == -2000000
        assert counts[2] == -3000000

    def test_rejects_short_packet(self) -> None:
        short_data = b"\x00" * 35
        with pytest.raises(ValueError, match="Invalid RDT response size"):
            parse_rdt_response(short_data)

    def test_rejects_long_packet(self) -> None:
        long_data = b"\x00" * 37
        with pytest.raises(ValueError, match="Invalid RDT response size"):
            parse_rdt_response(long_data)

    def test_rejects_empty_packet(self) -> None:
        with pytest.raises(ValueError, match="Invalid RDT response size"):
            parse_rdt_response(b"")

    def test_handles_max_sequence_number(self) -> None:
        response = self._build_response(rdt_seq=0xFFFFFFFF)
        rdt_seq, _, _, _ = parse_rdt_response(response)
        assert rdt_seq == 0xFFFFFFFF


class TestRdtStatistics:
    """Tests for RDT statistics tracking."""

    def test_default_packets_received_zero(self) -> None:
        stats = RdtStatistics()
        assert stats.packets_received == 0

    def test_default_packets_lost_zero(self) -> None:
        stats = RdtStatistics()
        assert stats.packets_lost == 0

    def test_default_last_sequence_negative_one(self) -> None:
        stats = RdtStatistics()
        assert stats.last_rdt_sequence == -1


class TestRdtClient:
    """Tests for RDT client."""

    def test_init_stores_ip(self) -> None:
        client = RdtClient("192.168.1.100")
        assert client.ip == "192.168.1.100"

    def test_init_default_port(self) -> None:
        client = RdtClient("192.168.1.100")
        assert client.port == RDT_PORT

    def test_init_custom_port(self) -> None:
        client = RdtClient("192.168.1.100", port=12345)
        assert client.port == 12345

    def test_is_streaming_initially_false(self) -> None:
        client = RdtClient("192.168.1.100")
        assert client.is_streaming is False

    def test_statistics_initially_empty(self) -> None:
        client = RdtClient("192.168.1.100")
        assert client.statistics.packets_received == 0
        assert client.statistics.packets_lost == 0

    def test_context_manager_entry(self) -> None:
        with RdtClient("192.168.1.100") as client:
            assert isinstance(client, RdtClient)


class TestRdtClientWithMockedSocket:
    """Tests for RDT client behavior with mocked socket."""

    def _build_response(
        self,
        rdt_seq: int = 0,
        ft_seq: int = 0,
        status: int = 0,
        fx: int = 0,
        fy: int = 0,
        fz: int = 0,
        tx: int = 0,
        ty: int = 0,
        tz: int = 0,
    ) -> bytes:
        """Build a test response packet."""
        return struct.pack(
            RESPONSE_FORMAT,
            rdt_seq,
            ft_seq,
            status,
            fx,
            fy,
            fz,
            tx,
            ty,
            tz,
        )

    @patch("socket.socket")
    def test_start_streaming_sends_start_command(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        client = RdtClient("192.168.1.100")
        client.start_streaming()

        mock_sock.sendto.assert_called_once()
        sent_data, addr = mock_sock.sendto.call_args[0]
        assert addr == ("192.168.1.100", RDT_PORT)
        header, command, _ = struct.unpack(REQUEST_FORMAT, sent_data)
        assert header == RDT_HEADER
        assert command == RdtCommand.START_REALTIME

    @patch("socket.socket")
    def test_start_streaming_sets_streaming_flag(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        client = RdtClient("192.168.1.100")
        client.start_streaming()

        assert client.is_streaming is True

    @patch("socket.socket")
    def test_stop_streaming_sends_stop_command(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        client = RdtClient("192.168.1.100")
        client.start_streaming()
        mock_sock.sendto.reset_mock()
        client.stop_streaming()

        mock_sock.sendto.assert_called_once()
        sent_data, addr = mock_sock.sendto.call_args[0]
        header, command, _ = struct.unpack(REQUEST_FORMAT, sent_data)
        assert command == RdtCommand.STOP

    @patch("socket.socket")
    def test_stop_streaming_clears_streaming_flag(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        client = RdtClient("192.168.1.100")
        client.start_streaming()
        client.stop_streaming()

        assert client.is_streaming is False

    @patch("socket.socket")
    def test_send_bias_sends_bias_command(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        client = RdtClient("192.168.1.100")
        client.send_bias()

        mock_sock.sendto.assert_called_once()
        sent_data, _ = mock_sock.sendto.call_args[0]
        header, command, _ = struct.unpack(REQUEST_FORMAT, sent_data)
        assert command == RdtCommand.SET_BIAS

    @patch("socket.socket")
    def test_receive_samples_returns_sample_records(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        response = self._build_response(rdt_seq=1, ft_seq=100, status=0, fx=10, fy=20, fz=30, tx=40, ty=50, tz=60)
        mock_sock.recvfrom.side_effect = [(response, ("192.168.1.100", RDT_PORT)), socket.timeout()]

        client = RdtClient("192.168.1.100")
        samples = list(client.receive_samples(timeout=0.1))

        assert len(samples) == 1
        sample = samples[0]
        assert isinstance(sample, SampleRecord)
        assert sample.rdt_sequence == 1
        assert sample.ft_sequence == 100
        assert sample.status == 0
        assert sample.counts == (10, 20, 30, 40, 50, 60)

    @patch("socket.socket")
    def test_receive_samples_respects_max_samples(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        responses = [
            (self._build_response(rdt_seq=i), ("192.168.1.100", RDT_PORT)) for i in range(10)
        ]
        mock_sock.recvfrom.side_effect = responses

        client = RdtClient("192.168.1.100")
        samples = list(client.receive_samples(max_samples=3))

        assert len(samples) == 3

    @patch("socket.socket")
    def test_receive_samples_tracks_packet_count(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        responses = [
            (self._build_response(rdt_seq=i), ("192.168.1.100", RDT_PORT)) for i in range(5)
        ]
        mock_sock.recvfrom.side_effect = responses + [socket.timeout()]

        client = RdtClient("192.168.1.100")
        list(client.receive_samples(timeout=0.1))

        assert client.statistics.packets_received == 5


class TestSequenceGapDetection:
    """Tests for sequence gap detection in RDT client."""

    def _build_response(self, rdt_seq: int) -> bytes:
        return struct.pack(RESPONSE_FORMAT, rdt_seq, 0, 0, 0, 0, 0, 0, 0, 0)

    @patch("socket.socket")
    def test_no_gap_when_sequential(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        responses = [
            (self._build_response(rdt_seq=i), ("192.168.1.100", RDT_PORT)) for i in range(5)
        ]
        mock_sock.recvfrom.side_effect = responses + [socket.timeout()]

        client = RdtClient("192.168.1.100")
        list(client.receive_samples(timeout=0.1))

        assert client.statistics.packets_lost == 0

    @patch("socket.socket")
    def test_detects_gap_of_one(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Sequence: 0, 2 (gap of 1)
        responses = [
            (self._build_response(rdt_seq=0), ("192.168.1.100", RDT_PORT)),
            (self._build_response(rdt_seq=2), ("192.168.1.100", RDT_PORT)),
        ]
        mock_sock.recvfrom.side_effect = responses + [socket.timeout()]

        client = RdtClient("192.168.1.100")
        list(client.receive_samples(timeout=0.1))

        assert client.statistics.packets_lost == 1

    @patch("socket.socket")
    def test_detects_large_gap(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Sequence: 0, 100 (gap of 99)
        responses = [
            (self._build_response(rdt_seq=0), ("192.168.1.100", RDT_PORT)),
            (self._build_response(rdt_seq=100), ("192.168.1.100", RDT_PORT)),
        ]
        mock_sock.recvfrom.side_effect = responses + [socket.timeout()]

        client = RdtClient("192.168.1.100")
        list(client.receive_samples(timeout=0.1))

        assert client.statistics.packets_lost == 99

    @patch("socket.socket")
    def test_detects_sequence_wraparound(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Sequence: 0xFFFFFFFE, 0xFFFFFFFF, 1 (gap of 1 after wrap)
        responses = [
            (self._build_response(rdt_seq=0xFFFFFFFE), ("192.168.1.100", RDT_PORT)),
            (self._build_response(rdt_seq=0xFFFFFFFF), ("192.168.1.100", RDT_PORT)),
            (self._build_response(rdt_seq=1), ("192.168.1.100", RDT_PORT)),
        ]
        mock_sock.recvfrom.side_effect = responses + [socket.timeout()]

        client = RdtClient("192.168.1.100")
        list(client.receive_samples(timeout=0.1))

        assert client.statistics.packets_lost == 1

    @patch("socket.socket")
    def test_accumulates_multiple_gaps(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # Sequence: 0, 3, 10 (gaps of 2 and 6)
        responses = [
            (self._build_response(rdt_seq=0), ("192.168.1.100", RDT_PORT)),
            (self._build_response(rdt_seq=3), ("192.168.1.100", RDT_PORT)),
            (self._build_response(rdt_seq=10), ("192.168.1.100", RDT_PORT)),
        ]
        mock_sock.recvfrom.side_effect = responses + [socket.timeout()]

        client = RdtClient("192.168.1.100")
        list(client.receive_samples(timeout=0.1))

        assert client.statistics.packets_lost == 2 + 6

    @patch("socket.socket")
    def test_first_packet_no_gap(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        # First packet starts at 1000 - no gap expected
        responses = [
            (self._build_response(rdt_seq=1000), ("192.168.1.100", RDT_PORT)),
        ]
        mock_sock.recvfrom.side_effect = responses + [socket.timeout()]

        client = RdtClient("192.168.1.100")
        list(client.receive_samples(timeout=0.1))

        assert client.statistics.packets_lost == 0


class TestRdtClientCleanup:
    """Tests for RDT client cleanup behavior."""

    @patch("socket.socket")
    def test_close_stops_streaming_if_active(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        client = RdtClient("192.168.1.100")
        client.start_streaming()
        client.close()

        # Should have sent start and stop
        assert mock_sock.sendto.call_count == 2

    @patch("socket.socket")
    def test_close_closes_socket(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        client = RdtClient("192.168.1.100")
        client.start_streaming()
        client.close()

        mock_sock.close.assert_called_once()

    @patch("socket.socket")
    def test_context_manager_closes_on_exit(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        with RdtClient("192.168.1.100") as client:
            client.start_streaming()

        mock_sock.close.assert_called_once()

    @patch("socket.socket")
    def test_start_streaming_resets_statistics(self, mock_socket_class: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        responses = [
            (struct.pack(RESPONSE_FORMAT, i, 0, 0, 0, 0, 0, 0, 0, 0), ("192.168.1.100", RDT_PORT))
            for i in [0, 5]  # Gap of 4
        ]
        mock_sock.recvfrom.side_effect = responses + [socket.timeout()]

        client = RdtClient("192.168.1.100")
        list(client.receive_samples(timeout=0.1))
        assert client.statistics.packets_lost == 4

        # Start new streaming session
        client.start_streaming()
        assert client.statistics.packets_lost == 0
        assert client.statistics.packets_received == 0
