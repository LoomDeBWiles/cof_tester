"""Tests for ChannelSelector widget (FR-13: Channel Toggles).

FR-13 Requirements:
- MUST provide per-channel enable/disable controls
- Six toggle buttons for Fx, Fy, Fz, Tx, Ty, Tz
- Visually distinct enabled state
- Toggling hides/shows traces
- State persists
"""

import pytest

# Skip entire module if Qt is not available
pytest.importorskip("PySide6")

try:
    import PySide6.QtGui
except ImportError:
    pytest.skip("PySide6 not usable", allow_module_level=True)

from gsdv.ui import ChannelSelector


@pytest.fixture
def channel_selector(qtbot):
    """Create a ChannelSelector widget for testing."""
    widget = ChannelSelector()
    qtbot.addWidget(widget)
    return widget


class TestChannelSelectorInitialization:
    """Tests for ChannelSelector initialization."""

    def test_has_six_checkboxes(self, channel_selector):
        """Widget has six checkboxes for all channels."""
        assert len(channel_selector._checkboxes) == 6
        expected_channels = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")
        for channel in expected_channels:
            assert channel in channel_selector._checkboxes

    def test_all_channels_enabled_by_default(self, channel_selector):
        """All channels are enabled by default."""
        for checkbox in channel_selector._checkboxes.values():
            assert checkbox.isChecked()

    def test_checkbox_labels_match_channel_names(self, channel_selector):
        """Checkbox labels match channel names."""
        for channel, checkbox in channel_selector._checkboxes.items():
            assert checkbox.text() == channel


class TestChannelSelectorToggling:
    """Tests for channel toggle functionality."""

    def test_toggling_emits_signal(self, channel_selector, qtbot):
        """Toggling a channel emits channel_toggled signal."""
        signals_received = []
        channel_selector.channel_toggled.connect(
            lambda ch, enabled: signals_received.append((ch, enabled))
        )

        # Toggle Fx off
        channel_selector._checkboxes["Fx"].setChecked(False)
        assert len(signals_received) == 1
        assert signals_received[0] == ("Fx", False)

        # Toggle Fx back on
        channel_selector._checkboxes["Fx"].setChecked(True)
        assert len(signals_received) == 2
        assert signals_received[1] == ("Fx", True)

    def test_enabled_channels_reflects_state(self, channel_selector):
        """enabled_channels() returns only checked channels."""
        # Initially all enabled
        assert len(channel_selector.enabled_channels()) == 6

        # Disable two channels
        channel_selector._checkboxes["Fx"].setChecked(False)
        channel_selector._checkboxes["Tz"].setChecked(False)
        enabled = channel_selector.enabled_channels()
        assert len(enabled) == 4
        assert "Fx" not in enabled
        assert "Tz" not in enabled
        assert "Fy" in enabled
        assert "Fz" in enabled
        assert "Tx" in enabled
        assert "Ty" in enabled

    def test_set_channel_enabled(self, channel_selector):
        """set_channel_enabled() programmatically controls checkboxes."""
        channel_selector.set_channel_enabled("Fx", False)
        assert not channel_selector._checkboxes["Fx"].isChecked()

        channel_selector.set_channel_enabled("Fx", True)
        assert channel_selector._checkboxes["Fx"].isChecked()

    def test_set_channel_enabled_invalid_channel(self, channel_selector):
        """set_channel_enabled() ignores invalid channel names."""
        # Should not raise, just silently ignore
        channel_selector.set_channel_enabled("InvalidChannel", False)


class TestChannelSelectorIntegration:
    """Tests for integration with plot widget."""

    def test_toggle_signal_can_control_plot_visibility(self, channel_selector, qtbot):
        """Verify signal can be connected to plot's set_channel_visible."""
        from gsdv.plot.plot_widget import MultiChannelPlot

        plot = MultiChannelPlot()
        qtbot.addWidget(plot)

        # Connect the signal
        channel_selector.channel_toggled.connect(plot.set_channel_visible)

        # Toggle channel off
        channel_selector._checkboxes["Fx"].setChecked(False)
        assert not plot._lines["Fx"].isVisible()

        # Toggle channel on
        channel_selector._checkboxes["Fx"].setChecked(True)
        assert plot._lines["Fx"].isVisible()

    def test_all_six_channels_can_be_toggled_independently(self, channel_selector, qtbot):
        """All six channels can be toggled independently."""
        from gsdv.plot.plot_widget import MultiChannelPlot

        plot = MultiChannelPlot()
        qtbot.addWidget(plot)
        channel_selector.channel_toggled.connect(plot.set_channel_visible)

        # Initially all visible
        for channel in ChannelSelector.CHANNELS:
            assert plot._lines[channel].isVisible()

        # Toggle each off one by one
        for channel in ChannelSelector.CHANNELS:
            channel_selector._checkboxes[channel].setChecked(False)
            assert not plot._lines[channel].isVisible()
            # Others should still be visible (if not already disabled)
            for other_channel in ChannelSelector.CHANNELS:
                if other_channel != channel and channel_selector._checkboxes[other_channel].isChecked():
                    assert plot._lines[other_channel].isVisible()

        # Toggle all back on
        for channel in ChannelSelector.CHANNELS:
            channel_selector._checkboxes[channel].setChecked(True)
            assert plot._lines[channel].isVisible()
