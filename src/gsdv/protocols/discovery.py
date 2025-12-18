"""Subnet discovery for ATI NETrs sensors.

This module implements automatic sensor discovery by probing IP addresses
on local subnets for the /netftapi2.xml calibration endpoint.

Key features:
- Enumerates local network interfaces to find subnet ranges
- Concurrent probing with bounded total scan time (<10s for /24)
- Non-blocking async interface for UI integration
"""

import ipaddress
import socket
import struct
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from gsdv.protocols.http_calibration import CALIBRATION_ENDPOINT, HTTP_PORT


@dataclass(frozen=True, slots=True)
class DiscoveredSensor:
    """Information about a discovered sensor.

    Attributes:
        ip: IP address of the sensor.
        serial_number: Serial number if available from calibration response.
        firmware_version: Firmware version if available.
    """

    ip: str
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None


# Discovery configuration
PROBE_TIMEOUT = 0.15  # seconds per host - tuned for <10s on /24
MAX_CONCURRENT_PROBES = 100  # concurrent connections
MAX_SCAN_TIME = 10.0  # hard limit for entire scan


def get_local_subnets() -> list[ipaddress.IPv4Network]:
    """Get IPv4 subnets for all local network interfaces.

    Returns:
        List of IPv4Network objects representing local subnets.
        Excludes loopback (127.0.0.0/8) and link-local (169.254.0.0/16).
    """
    subnets: list[ipaddress.IPv4Network] = []

    if sys.platform == "win32":
        subnets.extend(_get_subnets_windows())
    else:
        subnets.extend(_get_subnets_unix())

    return subnets


def _get_subnets_unix() -> Iterator[ipaddress.IPv4Network]:
    """Get subnets on Unix-like systems using /proc/net/route or ifconfig."""
    # Try /proc/net/route first (Linux)
    try:
        with open("/proc/net/route") as f:
            lines = f.readlines()[1:]  # Skip header
            for line in lines:
                parts = line.strip().split()
                if len(parts) < 8:
                    continue
                iface = parts[0]
                dest = int(parts[1], 16)
                mask = int(parts[7], 16)

                # Skip default route and loopback
                if dest == 0 or iface == "lo":
                    continue

                # Convert to network address
                try:
                    # dest and mask are in little-endian on x86
                    dest_bytes = struct.pack("<I", dest)
                    mask_bytes = struct.pack("<I", mask)
                    dest_ip = socket.inet_ntoa(dest_bytes)
                    mask_ip = socket.inet_ntoa(mask_bytes)

                    # Calculate prefix length from mask
                    mask_int = int.from_bytes(mask_bytes, "big")
                    prefix_len = bin(mask_int).count("1")

                    network = ipaddress.IPv4Network(f"{dest_ip}/{prefix_len}", strict=False)

                    # Skip link-local
                    if network.is_link_local or network.is_loopback:
                        continue

                    yield network
                except (ValueError, OSError):
                    continue
        return
    except FileNotFoundError:
        pass

    # Fallback: use socket to get local IPs and assume /24
    yield from _get_subnets_from_hostnames()


def _get_subnets_windows() -> Iterator[ipaddress.IPv4Network]:
    """Get subnets on Windows using socket hostname resolution."""
    yield from _get_subnets_from_hostnames()


def _get_subnets_from_hostnames() -> Iterator[ipaddress.IPv4Network]:
    """Get subnets by resolving local hostname and assuming /24 networks."""
    try:
        hostname = socket.gethostname()
        addrs = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM)
        seen: set[str] = set()
        for _, _, _, _, sockaddr in addrs:
            ip = sockaddr[0]
            if ip in seen:
                continue
            seen.add(ip)

            try:
                addr = ipaddress.IPv4Address(ip)
                if addr.is_loopback or addr.is_link_local:
                    continue
                # Assume /24 network for discovered addresses
                network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
                yield network
            except ValueError:
                continue
    except OSError:
        pass


def _probe_host(ip: str, port: int = HTTP_PORT, timeout: float = PROBE_TIMEOUT) -> Optional[DiscoveredSensor]:
    """Probe a single host for sensor presence.

    Args:
        ip: IP address to probe.
        port: HTTP port (default 80).
        timeout: Connection timeout in seconds.

    Returns:
        DiscoveredSensor if sensor found, None otherwise.
    """
    request = f"GET {CALIBRATION_ENDPOINT} HTTP/1.1\r\nHost: {ip}\r\nConnection: close\r\n\r\n"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((ip, port))
            sock.sendall(request.encode("ascii"))

            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                # Early termination if we have enough data
                if len(response) > 2048:
                    break
    except (OSError, socket.timeout):
        return None

    try:
        response_str = response.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return None

    # Check for successful HTTP response
    if "200" not in response_str[:50]:
        return None

    # Check for netftapi2 XML content
    if "<netftapi2>" not in response_str and "<cfgcpf>" not in response_str:
        return None

    # Extract serial number and firmware if present
    serial = _extract_xml_field(response_str, "setserial")
    firmware = _extract_xml_field(response_str, "setfwver")

    return DiscoveredSensor(ip=ip, serial_number=serial, firmware_version=firmware)


def _extract_xml_field(xml: str, tag: str) -> Optional[str]:
    """Extract a simple XML field value."""
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start = xml.find(start_tag)
    if start == -1:
        return None
    start += len(start_tag)
    end = xml.find(end_tag, start)
    if end == -1:
        return None
    return xml[start:end].strip() or None


def scan_subnet(
    network: ipaddress.IPv4Network,
    port: int = HTTP_PORT,
    timeout_per_host: float = PROBE_TIMEOUT,
    max_workers: int = MAX_CONCURRENT_PROBES,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[DiscoveredSensor]:
    """Scan a subnet for sensors.

    Args:
        network: IPv4 network to scan.
        port: HTTP port to probe (default 80).
        timeout_per_host: Timeout per host in seconds.
        max_workers: Maximum concurrent probes.
        progress_callback: Optional callback(completed, total) for progress updates.

    Returns:
        List of discovered sensors.
    """
    hosts = list(network.hosts())
    total = len(hosts)
    discovered: list[DiscoveredSensor] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_probe_host, str(ip), port, timeout_per_host): ip for ip in hosts}
        completed = 0

        for future in as_completed(futures):
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

            result = future.result()
            if result is not None:
                discovered.append(result)

    return discovered


def discover_sensors(
    port: int = HTTP_PORT,
    timeout_per_host: float = PROBE_TIMEOUT,
    max_workers: int = MAX_CONCURRENT_PROBES,
    subnets: Optional[list[ipaddress.IPv4Network]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[DiscoveredSensor]:
    """Discover sensors on all local subnets.

    This is the main entry point for sensor discovery. It enumerates
    local network interfaces, scans their subnets, and returns all
    discovered sensors.

    Args:
        port: HTTP port to probe (default 80).
        timeout_per_host: Timeout per host in seconds.
        max_workers: Maximum concurrent probes.
        subnets: Optional list of subnets to scan (auto-detected if None).
        progress_callback: Optional callback(completed, total) for progress updates.

    Returns:
        List of discovered sensors across all subnets.
    """
    if subnets is None:
        subnets = get_local_subnets()

    if not subnets:
        return []

    # Calculate total hosts across all subnets for progress
    all_hosts: list[str] = []
    for network in subnets:
        all_hosts.extend(str(ip) for ip in network.hosts())

    total = len(all_hosts)
    discovered: list[DiscoveredSensor] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_probe_host, ip, port, timeout_per_host): ip for ip in all_hosts}
        completed = 0

        for future in as_completed(futures):
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

            result = future.result()
            if result is not None:
                discovered.append(result)

    return discovered
