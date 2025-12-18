
import os
import time
from pathlib import Path
from gsdv.logging.writer import AsyncFileWriter

def test_async_file_writer_header_line_terminator(tmp_path):
    """
    Test that AsyncFileWriter uses the correct line terminator for the header,
    matching the configured line_terminator (e.g., \r\n for Excel).
    """
    output_file = tmp_path / "test_output.csv"
    header = "Time,Value"
    line_terminator = "\r\n"
    
    writer = AsyncFileWriter(
        path=output_file,
        header=header,
        line_terminator=line_terminator,
        flush_interval_ms=10  # fast flush for testing
    )
    
    with writer:
        writer.write(("1.0", "100"))
        time.sleep(0.1) # wait for flush
        
    content = output_file.read_bytes()
    
    # Expected: "Time,Value\r\n1.0,100\r\n"
    # Current Buggy Behavior: "Time,Value\n1.0,100\r\n"
    
    expected_header_line = (header + line_terminator).encode('utf-8')
    assert content.startswith(expected_header_line), \
        f"Header line ending incorrect. Content: {content!r}"
        
    expected_content = (header + line_terminator + "1.0,100" + line_terminator).encode('utf-8')
    assert content == expected_content, \
        f"File content incorrect.\nExpected: {expected_content!r}\nActual:   {content!r}"

