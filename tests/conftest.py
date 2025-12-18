"""Pytest configuration for GSDV tests."""

import sys


def pytest_configure(config):
    """Disable pytest-qt if Qt is not available."""
    try:
        from PySide6 import QtGui  # noqa: F401
    except ImportError:
        # Qt not available, disable pytest-qt
        config.pluginmanager.set_blocked("pytest-qt")


# Disable Qt plugin loading at import time if EGL is missing
collect_ignore = []
try:
    from PySide6 import QtGui  # noqa: F401
except ImportError:
    collect_ignore.append("test_integration_simulator.py")
