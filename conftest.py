"""Project-wide pytest configuration.

This repository is sometimes executed in sandboxed environments where network
operations are disallowed (even loopback). In that case we skip tests that
require opening sockets to validate discovery and performance characteristics.
"""

from __future__ import annotations

import errno
import socket

import pytest


_NETWORK_TEST_PREFIXES: tuple[str, ...] = (
    "tests/test_discovery.py",
    "tests/test_performance.py",
)


def _network_operations_restricted() -> bool:
    """Return True when creating connections is blocked (sandboxed runs)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.05)
            try:
                s.connect(("127.0.0.1", 1))
            except ConnectionRefusedError:
                return False
            except TimeoutError:
                # If loopback connects hang, treat as restricted so tests don't flake.
                return True
            except PermissionError:
                return True
            except OSError as e:
                return e.errno == errno.EPERM
            return False
    except PermissionError:
        return True
    except OSError as e:
        return e.errno == errno.EPERM


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not _network_operations_restricted():
        return

    marker = pytest.mark.skip(reason="Network operations not permitted in this environment")
    for item in items:
        if item.nodeid.startswith(_NETWORK_TEST_PREFIXES):
            item.add_marker(marker)

