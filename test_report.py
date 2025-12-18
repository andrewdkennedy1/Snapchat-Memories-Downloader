#!/usr/bin/env python3
"""Test script for report functionality."""

import time
from pathlib import Path
from snapchat_memories_downloader.report import generate_report, save_report, print_report_summary

# Mock metadata for testing
test_metadata = [
    {
        "number": 1,
        "date": "2024-01-01 12:00:00 UTC",
        "media_type": "Image",
        "status": "success",
        "files": [{"path": "01.jpg", "size": 1024000, "type": "single"}]
    },
    {
        "number": 2,
        "date": "2024-01-02 12:00:00 UTC", 
        "media_type": "Video",
        "status": "success",
        "files": [
            {"path": "02-main.mp4", "size": 2048000, "type": "main"},
            {"path": "02-overlay.png", "size": 512000, "type": "overlay"}
        ]
    },
    {
        "number": 3,
        "date": "2024-01-03 12:00:00 UTC",
        "media_type": "Image", 
        "status": "success",
        "files": [{"path": "03.jpg", "size": 800000, "type": "merged"}]
    },
    {
        "number": 4,
        "date": "2024-01-04 12:00:00 UTC",
        "media_type": "Video",
        "status": "failed",
        "error": "Download timeout after 30 seconds"
    },
    {
        "number": 5,
        "date": "2024-01-05 12:00:00 UTC",
        "media_type": "Image",
        "status": "pending"
    }
]

def main():
    output_path = Path("./test_output")
    output_path.mkdir(exist_ok=True)
    
    start_time = time.time()
    time.sleep(0.1)  # Simulate some processing time
    end_time = time.time()
    
    # Generate report
    report = generate_report(test_metadata, output_path, start_time, end_time)
    
    # Save report
    report_file = save_report(report, output_path)
    
    # Print summary
    print_report_summary(report)
    
    print(f"\nTest report saved to: {report_file}")
    print("Report functionality working correctly!")

if __name__ == "__main__":
    main()
