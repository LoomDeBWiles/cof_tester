"""Network protocol implementations for ATI NETrs sensor communication.

This package provides protocol implementations for communicating with
ATI NETrs force/torque sensors:

- UDP RDT (Real-time Data Transfer) streaming protocol
- TCP command interface for calibration and configuration
- HTTP calibration retrieval

Example:
    >>> from gsdv.protocols import RdtClient, HttpCalibrationClient
    >>> cal_client = HttpCalibrationClient("192.168.1.1")
    >>> cal = cal_client.get_calibration()
    >>> rdt_client = RdtClient("192.168.1.1")
    >>> rdt_client.start_streaming()
"""

from gsdv.models import CalibrationInfo, SampleRecord
from gsdv.protocols.http_calibration import (
    HTTP_PORT,
    HTTP_TIMEOUT,
    CALIBRATION_ENDPOINT,
    HttpCalibrationClient,
    HttpCalibrationError,
    get_calibration_with_fallback,
    parse_calibration_xml,
)
from gsdv.protocols.rdt_udp import (
    RDT_HEADER,
    RDT_PORT,
    RDT_REQUEST_SIZE,
    RDT_RESPONSE_SIZE,
    RdtClient,
    RdtCommand,
    RdtStatistics,
    build_rdt_request,
    parse_rdt_response,
)
from gsdv.protocols.tcp_cmd import (
    CALINFO_RESPONSE_SIZE,
    TCP_PORT,
    TCP_RESPONSE_HEADER,
    TRANSFORM_REQUEST_SIZE,
    TcpCommand,
    TcpCommandClient,
    ToolTransform,
    TransformAngleUnits,
    TransformDistUnits,
    build_bias_request,
    build_calinfo_request,
    build_transform_request,
    parse_calinfo_response,
)

__all__ = [
    # Models
    "CalibrationInfo",
    "SampleRecord",
    # UDP RDT
    "RDT_HEADER",
    "RDT_PORT",
    "RDT_REQUEST_SIZE",
    "RDT_RESPONSE_SIZE",
    "RdtClient",
    "RdtCommand",
    "RdtStatistics",
    "build_rdt_request",
    "parse_rdt_response",
    # TCP Command
    "CALINFO_RESPONSE_SIZE",
    "TCP_PORT",
    "TCP_RESPONSE_HEADER",
    "TRANSFORM_REQUEST_SIZE",
    "TcpCommand",
    "TcpCommandClient",
    "ToolTransform",
    "TransformAngleUnits",
    "TransformDistUnits",
    "build_bias_request",
    "build_calinfo_request",
    "build_transform_request",
    "parse_calinfo_response",
    # HTTP Calibration
    "CALIBRATION_ENDPOINT",
    "HTTP_PORT",
    "HTTP_TIMEOUT",
    "HttpCalibrationClient",
    "HttpCalibrationError",
    "get_calibration_with_fallback",
    "parse_calibration_xml",
]
