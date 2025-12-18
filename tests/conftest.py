"""Pytest configuration for GSDV tests."""


def _qt_is_available() -> bool:
    """Check if Qt is fully available (Python bindings and native libraries)."""
    try:
        from PySide6 import QtWidgets  # noqa: F401

        return True
    except (ImportError, OSError):
        return False


def pytest_configure(config):
    """Disable pytest-qt if Qt is not available."""
    if not _qt_is_available():
        config.pluginmanager.set_blocked("pytest-qt")


# Disable Qt test modules if Qt is not available
collect_ignore = []
if not _qt_is_available():
    collect_ignore.append("test_integration_simulator.py")
    collect_ignore.append("test_main_window.py")
    collect_ignore.append("test_ui_accessibility.py")
