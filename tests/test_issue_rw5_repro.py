import pytest

try:
    from PySide6.QtWidgets import QApplication
    from gsdv.ui.main_window import MainWindow, TimeWindowSelector
except (ImportError, OSError) as exc:
    pytest.skip(
        f"PySide6 Qt widgets (libEGL) not available: {exc}",
        allow_module_level=True,
    )

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

def test_time_window_selector_snapping(qapp):
    """Test that TimeWindowSelector snaps to the closest preset."""
    selector = TimeWindowSelector()
    
    # Set a custom value that is not in presets (e.g. 13s)
    # Closest preset is 10s
    custom_value = 13.0
    selector.set_window_seconds(custom_value)
    
    # The selector should snap to 10s
    assert selector.window_seconds() == 10.0
    assert selector.window_seconds() != custom_value

def test_mainwindow_preference_mismatch(qapp):
    """Test the mismatch between UI display and actual plot value."""
    # Mock preferences object
    class MockPrefs:
        def __init__(self):
            self.time_window_seconds = 13.0
            self.theme = "dark"
            self.force_unit = "N"
            self.torque_unit = "Nm"
            self.filter_enabled = False
            self.filter_cutoff_hz = 10.0
            self.transform_dx = 0.0
            self.transform_dy = 0.0
            self.transform_dz = 0.0
            self.transform_rx = 0.0
            self.transform_ry = 0.0
            self.transform_rz = 0.0

    prefs = MockPrefs()
    window = MainWindow(preferences=prefs)
    
    # The selector should show the snapped value (10s)
    selector_value = window._time_window_selector.window_seconds()
    assert selector_value == 10.0
    
    # The plot should use the raw preference value (13s)
    # Accessing private attribute _window_seconds for verification
    plot_value = window._plot_area._window_seconds
    assert plot_value == 13.0
    
    # This confirms the bug: selector says 10s, plot uses 13s
    assert selector_value != plot_value
