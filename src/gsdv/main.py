"""Main entry point for the Gamma Sensor Data Viewer application."""

import sys
import time


def main() -> int:
    """Launch the GSDV application.

    If command-line arguments are provided, runs the CLI.
    Otherwise, launches the GUI.
    """
    # Check if we have CLI subcommands
    if len(sys.argv) > 1:
        from gsdv.diagnostics.cli import main as cli_main

        return cli_main()

    # Launch GUI
    from PySide6.QtWidgets import QApplication

    from gsdv.acquisition import AcquisitionEngine
    from gsdv.config.preferences import PreferencesStore
    from gsdv.protocols import get_calibration_with_fallback
    from gsdv.logging.writer import AsyncFileWriter
    from gsdv.ui.main_window import MainWindow

    app = QApplication(sys.argv)

    # Load preferences
    prefs_store = PreferencesStore()
    preferences = prefs_store.load()

    # Create main window with preferences
    window = MainWindow(preferences=preferences)

    # State for acquisition and recording
    acquisition_engine: AcquisitionEngine | None = None
    file_writer: AsyncFileWriter | None = None
    recording_start_time: float = 0.0

    def on_connect_requested(ip: str) -> None:
        """Handle connection request from UI."""
        nonlocal acquisition_engine

        window.connection_panel.set_connected(False, f"Connecting to {ip}...")

        try:
            # Get calibration first
            calibration = get_calibration_with_fallback(ip)
            window.update_calibration(calibration)

            # Sample callback for recording
            def on_sample(sample):
                if file_writer is not None and file_writer.is_running:
                    # Convert SampleRecord to tuple for the formatter
                    file_writer.write((
                        sample.t_monotonic_ns,
                        sample.rdt_sequence,
                        sample.ft_sequence,
                        sample.status,
                        sample.counts,
                    ))

            # Create and start acquisition engine with decimation
            print(f"DEBUG: decimation_factor = {preferences.decimation_factor}")
            acquisition_engine = AcquisitionEngine(
                ip=ip,
                decimation_factor=preferences.decimation_factor,
            )
            acquisition_engine.set_sample_callback(on_sample)

            # Connect the buffer to the plot
            window.plot_area.set_buffer(acquisition_engine.buffer)
            window.plot_area.set_calibration(
                calibration.counts_per_force,
                calibration.counts_per_torque,
            )

            # Start acquisition
            acquisition_engine.start()

            # Start display updates
            window.start_display_updates()

            window.connection_panel.set_connected(True, f"Connected to {ip}")

        except Exception as e:
            window.connection_panel.set_connected(False, f"Failed: {e}")
            window.show_status_message(f"Connection failed: {e}", 5000)
            if acquisition_engine is not None:
                acquisition_engine.stop()
                acquisition_engine = None

    def on_disconnect_requested() -> None:
        """Handle disconnection request from UI."""
        nonlocal acquisition_engine, file_writer

        # Stop recording first
        if file_writer is not None:
            file_writer.stop()
            file_writer = None
            window.recording_controls.set_recording(False)

        if acquisition_engine is not None:
            acquisition_engine.stop()
            acquisition_engine = None

        window.stop_display_updates()
        window.plot_area.clear()
        window.sensor_info.clear_info()
        window.connection_panel.set_connected(False, "Disconnected")
        window.update_sample_rate(0.0)
        window.update_packet_loss(0)

    def on_bias_requested() -> None:
        """Handle bias/tare request from UI."""
        if acquisition_engine is None:
            window.show_status_message("Not connected to a sensor", 3000)
            return

        try:
            from gsdv.protocols import send_device_bias
            send_device_bias(acquisition_engine.ip)
            window.show_status_message("Bias applied", 2000)
        except Exception as e:
            window.show_status_message(f"Bias failed: {e}", 5000)

    def on_record_started() -> None:
        """Handle record start request from UI."""
        nonlocal file_writer, recording_start_time

        if acquisition_engine is None:
            window.show_status_message("Not connected to a sensor", 3000)
            return

        output_path = window.recording_controls.get_output_path()
        if not output_path:
            window.show_status_message("Select an output directory first", 3000)
            return

        # Generate filename with timestamp
        from datetime import datetime
        from pathlib import Path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = preferences.filename_prefix or "sensor_data"
        filename = f"{prefix}_{timestamp}.csv"
        filepath = Path(output_path) / filename

        # Create CSV header
        header = "timestamp_ns,rdt_sequence,ft_sequence,status,Fx,Fy,Fz,Tx,Ty,Tz\n"

        # Sample formatter
        def format_sample(sample: tuple) -> str:
            t_ns, rdt_seq, ft_seq, status, counts = sample
            return f"{t_ns},{rdt_seq},{ft_seq},{status},{counts[0]},{counts[1]},{counts[2]},{counts[3]},{counts[4]},{counts[5]}"

        try:
            file_writer = AsyncFileWriter(
                path=filepath,
                formatter=format_sample,
                header=header,
            )
            file_writer.start()
            recording_start_time = time.monotonic()
            window.recording_controls.set_recording(True)
            window.show_status_message(f"Recording to {filename}", 3000)
        except Exception as e:
            window.show_status_message(f"Recording failed: {e}", 5000)
            file_writer = None

    def on_record_stopped() -> None:
        """Handle record stop request from UI."""
        nonlocal file_writer

        if file_writer is not None:
            file_writer.stop()
            stats = file_writer.stats()
            window.show_status_message(
                f"Recording stopped. Wrote {stats.samples_written} samples ({stats.bytes_written} bytes)",
                5000
            )
            file_writer = None

        window.recording_controls.set_recording(False)

    def update_stats() -> None:
        """Update status bar with acquisition statistics."""
        if acquisition_engine is not None and acquisition_engine.is_running:
            stats = acquisition_engine.stats()
            window.update_sample_rate(stats.samples_per_second)
            window.update_packet_loss(stats.packets_lost)
            window.update_buffer_status(stats.buffer_stats.fill_ratio * 100)

        # Update recording stats
        if file_writer is not None and file_writer.is_running:
            writer_stats = file_writer.stats()
            elapsed = time.monotonic() - recording_start_time
            window.recording_controls.update_recording_stats(elapsed, writer_stats.bytes_written)

    # Wire up signals
    window.connection_panel.connect_requested.connect(on_connect_requested)
    window.connection_panel.disconnect_requested.connect(on_disconnect_requested)
    window.bias_requested.connect(on_bias_requested)
    window.recording_controls.record_started.connect(on_record_started)
    window.recording_controls.record_stopped.connect(on_record_stopped)

    # Stats update timer
    from PySide6.QtCore import QTimer
    stats_timer = QTimer()
    stats_timer.timeout.connect(update_stats)
    stats_timer.start(100)  # 10 Hz stats update

    # Restore last IP if available
    if preferences.last_ip:
        window.connection_panel.set_ip(preferences.last_ip)

    # Save preferences on exit
    def save_preferences() -> None:
        """Save current preferences before exit."""
        preferences.last_ip = window.connection_panel.get_ip()
        prefs_store.save(preferences)

    def cleanup() -> None:
        """Clean up on exit."""
        nonlocal acquisition_engine, file_writer
        if file_writer is not None:
            file_writer.stop()
            file_writer = None
        if acquisition_engine is not None:
            acquisition_engine.stop()
            acquisition_engine = None

    app.aboutToQuit.connect(save_preferences)
    app.aboutToQuit.connect(cleanup)

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
