"""Main entry point for the Gamma Sensor Data Viewer application."""

import sys


def main() -> int:
    """Launch the GSDV application.

    If command-line arguments are provided, runs the CLI.
    Otherwise, launches the GUI (when implemented).
    """
    # Check if we have CLI subcommands
    if len(sys.argv) > 1:
        from gsdv.diagnostics.cli import main as cli_main

        return cli_main()

    # Launch GUI (placeholder for now)
    print("GSDV - Gamma Sensor Data Viewer")
    print()
    print("GUI not yet implemented. Use CLI commands:")
    print("  gsdv discover      - Discover sensors on the network")
    print("  gsdv stream --ip   - Stream data from a sensor")
    print("  gsdv log --ip      - Log data to a file")
    print("  gsdv simulate-sensor - Run the sensor simulator")
    print()
    print("Run 'gsdv --help' for more information.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
