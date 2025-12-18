
import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from gsdv.diagnostics.cli import cmd_log
from gsdv.models import CalibrationInfo

@pytest.fixture
def mock_dependencies():
    with patch("gsdv.diagnostics.cli.get_calibration_with_fallback") as mock_cal, \
         patch("gsdv.diagnostics.cli.RdtClient") as mock_rdt, \
         patch("gsdv.diagnostics.cli.csv.writer") as mock_csv:
        
        # Setup mock calibration
        mock_cal.return_value = CalibrationInfo(
            serial_number="12345",
            firmware_version="1.0",
            counts_per_force=1000.0,
            counts_per_torque=1000.0
        )
        
        # Setup mock RdtClient to return context manager
        mock_client_instance = MagicMock()
        mock_rdt.return_value.__enter__.return_value = mock_client_instance
        
        # Mock receive_samples to return empty list or one sample then stop
        # We can just make it return empty list to stop loop immediately
        mock_client_instance.receive_samples.return_value = []
        
        # Mock statistics
        mock_client_instance.statistics.packets_lost = 0
        
        yield mock_cal, mock_rdt, mock_csv

def test_cmd_log_sanitizes_prefix(tmp_path, mock_dependencies):
    """Verify that path traversal characters in prefix are sanitized."""
    output_dir = tmp_path / "logs"
    output_dir.mkdir()
    
    # Arguments mimicking the CLI
    args = argparse.Namespace(
        ip="127.0.0.1",
        out=str(output_dir),
        format="csv",
        seconds=None,
        prefix="../traversal/",
        udp_port=49152,
        http_port=80
    )
    
    # Run cmd_log
    ret = cmd_log(args)
    assert ret == 0
    
    # Check created files
    files = list(output_dir.iterdir())
    assert len(files) == 1
    created_file = files[0]
    
    # The prefix should be sanitized. 
    # "../traversal/" -> "traversal" (slashes and dots removed/stripped)
    # The filename format is {prefix}{timestamp}.{ext}
    # sanitize_prefix strips leading/trailing dots and removes slashes.
    # So ".." -> stripped. "/" -> removed.
    # Let's check what sanitize_prefix("../traversal/") returns.
    # It should probably be "traversal_" + timestamp.
    
    print(f"Created file: {created_file.name}")
    
    assert "traversal" in created_file.name
    assert ".." not in created_file.name
    assert "/" not in created_file.name
    
    # Ensure no file was created outside output_dir (not easy to check globally, 
    # but we can check the intended parent if we want, though verify file in dir is enough)
    assert (tmp_path / "traversal").exists() is False

def test_cmd_log_absolute_path_prefix(tmp_path, mock_dependencies):
    """Verify that absolute path in prefix is sanitized."""
    output_dir = tmp_path / "logs"
    output_dir.mkdir()
    
    # Arguments mimicking the CLI
    args = argparse.Namespace(
        ip="127.0.0.1",
        out=str(output_dir),
        format="csv",
        seconds=None,
        prefix="/etc/passwd",
        udp_port=49152,
        http_port=80
    )
    
    # Run cmd_log
    ret = cmd_log(args)
    assert ret == 0
    
    # Check created files
    files = list(output_dir.iterdir())
    assert len(files) == 1
    created_file = files[0]
    
    print(f"Created file: {created_file.name}")
    
    assert "etcpasswd" in created_file.name
    assert created_file.parent == output_dir
