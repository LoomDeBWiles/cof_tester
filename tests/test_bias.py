"""Tests for bias (tare/zero) service."""

import socket
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from gsdv.errors import BiasError
from gsdv.protocols.bias import (
    BiasService,
    SoftZeroOffset,
    capture_soft_zero,
    send_device_bias,
)


class TestSoftZeroOffset:
    """Tests for SoftZeroOffset dataclass."""

    def test_apply_subtracts_offset_from_counts(self) -> None:
        offset = SoftZeroOffset(counts=(100, 200, 300, 10, 20, 30))
        sample = (150, 250, 350, 60, 70, 80)
        result = offset.apply(sample)
        assert result == (50, 50, 50, 50, 50, 50)

    def test_apply_handles_negative_results(self) -> None:
        offset = SoftZeroOffset(counts=(100, 200, 300, 10, 20, 30))
        sample = (50, 100, 150, 5, 10, 15)
        result = offset.apply(sample)
        assert result == (-50, -100, -150, -5, -10, -15)

    def test_apply_with_zero_offset(self) -> None:
        offset = SoftZeroOffset(counts=(0, 0, 0, 0, 0, 0))
        sample = (100, 200, 300, 10, 20, 30)
        result = offset.apply(sample)
        assert result == sample

    def test_apply_array_subtracts_offset(self) -> None:
        offset = SoftZeroOffset(counts=(100, 200, 300, 10, 20, 30))
        sample = np.array([150, 250, 350, 60, 70, 80], dtype=np.int32)
        result = offset.apply_array(sample)
        expected = np.array([50, 50, 50, 50, 50, 50], dtype=np.int32)
        np.testing.assert_array_equal(result, expected)

    def test_apply_array_handles_negative_results(self) -> None:
        offset = SoftZeroOffset(counts=(100, 200, 300, 10, 20, 30))
        sample = np.array([50, 100, 150, 5, 10, 15], dtype=np.int32)
        result = offset.apply_array(sample)
        expected = np.array([-50, -100, -150, -5, -10, -15], dtype=np.int32)
        np.testing.assert_array_equal(result, expected)


class TestCaptureSoftZero:
    """Tests for capture_soft_zero function."""

    def test_captures_counts_as_offset(self) -> None:
        counts = (100, 200, 300, 10, 20, 30)
        offset = capture_soft_zero(counts)
        assert offset.counts == counts

    def test_returns_soft_zero_offset_instance(self) -> None:
        counts = (0, 0, 0, 0, 0, 0)
        offset = capture_soft_zero(counts)
        assert isinstance(offset, SoftZeroOffset)


class TestSendDeviceBias:
    """Tests for send_device_bias function."""

    @patch("gsdv.protocols.bias.RdtClient")
    def test_sends_udp_bias_command(self, mock_rdt_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_rdt_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_rdt_class.return_value.__exit__ = MagicMock(return_value=False)

        send_device_bias("192.168.1.100")

        mock_rdt_class.assert_called_once_with("192.168.1.100", port=49152)
        mock_client.send_bias.assert_called_once()

    @patch("gsdv.protocols.bias.RdtClient")
    def test_uses_custom_udp_port(self, mock_rdt_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_rdt_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_rdt_class.return_value.__exit__ = MagicMock(return_value=False)

        send_device_bias("192.168.1.100", udp_port=50000)

        mock_rdt_class.assert_called_once_with("192.168.1.100", port=50000)

    @patch("gsdv.protocols.bias.TcpCommandClient")
    @patch("gsdv.protocols.bias.RdtClient")
    def test_falls_back_to_tcp_on_udp_failure(
        self, mock_rdt_class: MagicMock, mock_tcp_class: MagicMock
    ) -> None:
        # UDP fails
        mock_rdt_class.return_value.__enter__ = MagicMock(
            side_effect=OSError("UDP failed")
        )
        mock_rdt_class.return_value.__exit__ = MagicMock(return_value=False)

        # TCP succeeds
        mock_tcp_client = MagicMock()
        mock_tcp_class.return_value.__enter__ = MagicMock(return_value=mock_tcp_client)
        mock_tcp_class.return_value.__exit__ = MagicMock(return_value=False)

        send_device_bias("192.168.1.100")

        mock_tcp_class.assert_called_once_with(
            "192.168.1.100", port=49151, timeout=2.0
        )
        mock_tcp_client.send_bias.assert_called_once()

    @patch("gsdv.protocols.bias.TcpCommandClient")
    @patch("gsdv.protocols.bias.RdtClient")
    def test_raises_bias_error_when_both_fail(
        self, mock_rdt_class: MagicMock, mock_tcp_class: MagicMock
    ) -> None:
        # UDP fails
        mock_rdt_class.return_value.__enter__ = MagicMock(
            side_effect=OSError("UDP failed")
        )
        mock_rdt_class.return_value.__exit__ = MagicMock(return_value=False)

        # TCP fails
        mock_tcp_class.return_value.__enter__ = MagicMock(
            side_effect=ConnectionError("TCP failed")
        )
        mock_tcp_class.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(BiasError) as exc_info:
            send_device_bias("192.168.1.100")

        assert "192.168.1.100" in str(exc_info.value)
        assert "device tare" in str(exc_info.value)
        assert "UDP" in str(exc_info.value)
        assert "TCP" in str(exc_info.value)

    @patch("gsdv.protocols.bias.TcpCommandClient")
    @patch("gsdv.protocols.bias.RdtClient")
    def test_uses_custom_tcp_port_and_timeout(
        self, mock_rdt_class: MagicMock, mock_tcp_class: MagicMock
    ) -> None:
        # UDP fails
        mock_rdt_class.return_value.__enter__ = MagicMock(
            side_effect=socket.error("UDP failed")
        )
        mock_rdt_class.return_value.__exit__ = MagicMock(return_value=False)

        # TCP succeeds
        mock_tcp_client = MagicMock()
        mock_tcp_class.return_value.__enter__ = MagicMock(return_value=mock_tcp_client)
        mock_tcp_class.return_value.__exit__ = MagicMock(return_value=False)

        send_device_bias("192.168.1.100", tcp_port=50001, timeout=5.0)

        mock_tcp_class.assert_called_once_with(
            "192.168.1.100", port=50001, timeout=5.0
        )


class TestBiasService:
    """Tests for BiasService class."""

    def test_init_sets_ip_and_ports(self) -> None:
        service = BiasService("192.168.1.100", udp_port=50000, tcp_port=50001)
        assert service.ip == "192.168.1.100"

    def test_has_soft_zero_initially_false(self) -> None:
        service = BiasService("192.168.1.100")
        assert service.has_soft_zero is False

    def test_soft_zero_offset_initially_none(self) -> None:
        service = BiasService("192.168.1.100")
        assert service.soft_zero_offset is None

    @patch("gsdv.protocols.bias.send_device_bias")
    def test_apply_device_bias_calls_send_device_bias(
        self, mock_send: MagicMock
    ) -> None:
        service = BiasService("192.168.1.100", udp_port=50000, tcp_port=50001, timeout=3.0)
        service.apply_device_bias()

        mock_send.assert_called_once_with(
            "192.168.1.100", udp_port=50000, tcp_port=50001, timeout=3.0
        )

    @patch("gsdv.protocols.bias.send_device_bias")
    def test_apply_device_bias_clears_soft_zero(self, mock_send: MagicMock) -> None:
        service = BiasService("192.168.1.100")
        service.apply_soft_zero((100, 200, 300, 10, 20, 30))
        assert service.has_soft_zero is True

        service.apply_device_bias()

        assert service.has_soft_zero is False
        assert service.soft_zero_offset is None

    def test_apply_soft_zero_stores_offset(self) -> None:
        service = BiasService("192.168.1.100")
        counts = (100, 200, 300, 10, 20, 30)
        service.apply_soft_zero(counts)

        assert service.has_soft_zero is True
        assert service.soft_zero_offset is not None
        assert service.soft_zero_offset.counts == counts

    def test_clear_soft_zero_removes_offset(self) -> None:
        service = BiasService("192.168.1.100")
        service.apply_soft_zero((100, 200, 300, 10, 20, 30))
        service.clear_soft_zero()

        assert service.has_soft_zero is False
        assert service.soft_zero_offset is None

    def test_adjust_sample_with_no_offset_returns_original(self) -> None:
        service = BiasService("192.168.1.100")
        counts = (100, 200, 300, 10, 20, 30)
        result = service.adjust_sample(counts)
        assert result == counts

    def test_adjust_sample_with_offset_applies_it(self) -> None:
        service = BiasService("192.168.1.100")
        service.apply_soft_zero((50, 100, 150, 5, 10, 15))
        result = service.adjust_sample((100, 200, 300, 10, 20, 30))
        assert result == (50, 100, 150, 5, 10, 15)

    def test_adjust_sample_array_with_no_offset_returns_original(self) -> None:
        service = BiasService("192.168.1.100")
        counts = np.array([100, 200, 300, 10, 20, 30], dtype=np.int32)
        result = service.adjust_sample_array(counts)
        np.testing.assert_array_equal(result, counts)

    def test_adjust_sample_array_with_offset_applies_it(self) -> None:
        service = BiasService("192.168.1.100")
        service.apply_soft_zero((50, 100, 150, 5, 10, 15))
        counts = np.array([100, 200, 300, 10, 20, 30], dtype=np.int32)
        result = service.adjust_sample_array(counts)
        expected = np.array([50, 100, 150, 5, 10, 15], dtype=np.int32)
        np.testing.assert_array_equal(result, expected)


class TestBiasServiceApplyBias:
    """Tests for BiasService.apply_bias method."""

    @patch("gsdv.protocols.bias.send_device_bias")
    def test_device_mode_calls_device_bias(self, mock_send: MagicMock) -> None:
        service = BiasService("192.168.1.100")
        service.apply_bias("device")
        mock_send.assert_called_once()

    def test_soft_mode_applies_soft_zero(self) -> None:
        service = BiasService("192.168.1.100")
        counts = (100, 200, 300, 10, 20, 30)
        service.apply_bias("soft", current_counts=counts)

        assert service.has_soft_zero is True
        assert service.soft_zero_offset is not None
        assert service.soft_zero_offset.counts == counts

    def test_soft_mode_requires_current_counts(self) -> None:
        service = BiasService("192.168.1.100")
        with pytest.raises(ValueError, match="current_counts required"):
            service.apply_bias("soft")

    @patch("gsdv.protocols.bias.send_device_bias")
    def test_device_mode_fallback_on_failure(self, mock_send: MagicMock) -> None:
        mock_send.side_effect = BiasError("192.168.1.100", "device tare", "failed")

        service = BiasService("192.168.1.100")
        counts = (100, 200, 300, 10, 20, 30)
        service.apply_bias("device", current_counts=counts, fallback_on_failure=True)

        assert service.has_soft_zero is True
        assert service.soft_zero_offset is not None
        assert service.soft_zero_offset.counts == counts

    @patch("gsdv.protocols.bias.send_device_bias")
    def test_device_mode_no_fallback_without_counts(self, mock_send: MagicMock) -> None:
        mock_send.side_effect = BiasError("192.168.1.100", "device tare", "failed")

        service = BiasService("192.168.1.100")
        with pytest.raises(BiasError):
            service.apply_bias("device", fallback_on_failure=True)

    @patch("gsdv.protocols.bias.send_device_bias")
    def test_device_mode_raises_when_fallback_disabled(
        self, mock_send: MagicMock
    ) -> None:
        mock_send.side_effect = BiasError("192.168.1.100", "device tare", "failed")

        service = BiasService("192.168.1.100")
        counts = (100, 200, 300, 10, 20, 30)
        with pytest.raises(BiasError):
            service.apply_bias("device", current_counts=counts, fallback_on_failure=False)

    def test_unknown_mode_raises_value_error(self) -> None:
        service = BiasService("192.168.1.100")
        with pytest.raises(ValueError, match="Unknown bias mode"):
            service.apply_bias("invalid_mode")
