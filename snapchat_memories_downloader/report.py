"""Post-run report generation and display."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def generate_report(metadata_list: List[Dict], output_path: Path, start_time: float, end_time: float) -> Dict:
    """Generate comprehensive download report."""
    
    # Count statuses
    successful = sum(1 for m in metadata_list if m.get("status") == "success")
    failed = sum(1 for m in metadata_list if m.get("status") == "failed")
    pending = sum(1 for m in metadata_list if m.get("status") == "pending")
    skipped = sum(1 for m in metadata_list if m.get("status") == "skipped")
    
    # Count file types and merges
    merged_files = 0
    main_overlay_pairs = 0
    single_files = 0
    total_files = 0
    
    for m in metadata_list:
        if m.get("status") == "success":
            files = m.get("files", [])
            total_files += len(files)
            
            for file_info in files:
                file_type = file_info.get("type", "single")
                if file_type == "merged":
                    merged_files += 1
                elif file_type in ["main", "overlay"]:
                    if file_type == "main":  # Count pairs once
                        main_overlay_pairs += 1
                else:
                    single_files += 1
    
    # Calculate sizes
    total_size = 0
    for m in metadata_list:
        if m.get("status") == "success":
            for file_info in m.get("files", []):
                total_size += file_info.get("size", 0)
    
    # Collect errors
    errors = []
    for i, m in enumerate(metadata_list):
        if m.get("status") == "failed":
            error_msg = m.get("error", "Unknown error")
            errors.append(f"#{m.get('number', i+1)}: {error_msg}")
    
    duration = end_time - start_time
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": round(duration, 2),
        "output_directory": str(output_path.absolute()),
        "totals": {
            "memories_processed": len(metadata_list),
            "successful": successful,
            "failed": failed,
            "pending": pending,
            "skipped": skipped,
            "total_files": total_files,
            "total_size_bytes": total_size
        },
        "file_processing": {
            "single_files": single_files,
            "merged_overlays": merged_files,
            "unmerged_pairs": main_overlay_pairs
        },
        "errors": errors[:10],  # Limit to first 10 errors
        "error_count": len(errors)
    }
    
    return report


def save_report(report: Dict, output_path: Path) -> Path:
    """Save report to JSON file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = output_path / f"download_report_{timestamp}.json"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    return report_file


def format_size(bytes_total: int) -> str:
    """Format bytes as human readable size."""
    if bytes_total < 1024:
        return f"{bytes_total} B"
    elif bytes_total < 1024 * 1024:
        return f"{bytes_total / 1024:.1f} KB"
    elif bytes_total < 1024 * 1024 * 1024:
        return f"{bytes_total / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_total / (1024 * 1024 * 1024):.1f} GB"


def print_report_summary(report: Dict):
    """Print formatted report summary to console."""
    print("\n" + "=" * 60)
    print("DOWNLOAD REPORT")
    print("=" * 60)
    
    totals = report["totals"]
    processing = report["file_processing"]
    
    print(f"Duration: {report['duration_seconds']:.1f} seconds")
    print(f"Output: {report['output_directory']}")
    print(f"Total Size: {format_size(totals['total_size_bytes'])}")
    
    print(f"\nMemories: {totals['successful']}/{totals['memories_processed']} successful")
    if totals['failed'] > 0:
        print(f"Failed: {totals['failed']}")
    if totals['pending'] > 0:
        print(f"Pending: {totals['pending']}")
    if totals['skipped'] > 0:
        print(f"Skipped: {totals['skipped']}")
    
    print(f"\nFiles: {totals['total_files']} total")
    print(f"  Single files: {processing['single_files']}")
    print(f"  Merged overlays: {processing['merged_overlays']}")
    print(f"  Unmerged pairs: {processing['unmerged_pairs']}")
    
    if report['errors']:
        print(f"\nErrors ({report['error_count']}):")
        for error in report['errors']:
            print(f"  {error}")
        if report['error_count'] > len(report['errors']):
            print(f"  ... and {report['error_count'] - len(report['errors'])} more")
    
    print("=" * 60)


def show_report_popup(report: Dict, report_file: Path):
    """Show report in GUI popup if available."""
    try:
        import tkinter as tk
        from tkinter import messagebox, scrolledtext
        
        # Create popup window
        root = tk.Tk()
        root.withdraw()  # Hide main window
        
        # Create report window
        window = tk.Toplevel()
        window.title("Download Report")
        window.geometry("600x500")
        window.resizable(True, True)
        
        # Create scrollable text area
        text_area = scrolledtext.ScrolledText(window, wrap=tk.WORD, font=("Consolas", 10))
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Format report content
        totals = report["totals"]
        processing = report["file_processing"]
        
        content = f"""SNAPCHAT MEMORIES DOWNLOAD REPORT
Generated: {report['timestamp']}
Duration: {report['duration_seconds']:.1f} seconds
Output Directory: {report['output_directory']}
Total Size: {format_size(totals['total_size_bytes'])}

SUMMARY
Memories Processed: {totals['memories_processed']}
Successful: {totals['successful']}
Failed: {totals['failed']}
Pending: {totals['pending']}
Skipped: {totals['skipped']}

FILES
Total Files: {totals['total_files']}
Single Files: {processing['single_files']}
Merged Overlays: {processing['merged_overlays']}
Unmerged Pairs: {processing['unmerged_pairs']}
"""
        
        if report['errors']:
            content += f"\nERRORS ({report['error_count']}):\n"
            for error in report['errors']:
                content += f"{error}\n"
            if report['error_count'] > len(report['errors']):
                content += f"... and {report['error_count'] - len(report['errors'])} more\n"
        
        content += f"\nFull report saved to: {report_file}"
        
        text_area.insert(tk.END, content)
        text_area.config(state=tk.DISABLED)
        
        # Add buttons
        button_frame = tk.Frame(window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        def open_report_file():
            import subprocess
            import sys
            if sys.platform == "win32":
                subprocess.run(["notepad", str(report_file)])
            elif sys.platform == "darwin":
                subprocess.run(["open", str(report_file)])
            else:
                subprocess.run(["xdg-open", str(report_file)])
        
        tk.Button(button_frame, text="Open Report File", command=open_report_file).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Close", command=window.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Center window
        window.update_idletasks()
        x = (window.winfo_screenwidth() // 2) - (window.winfo_width() // 2)
        y = (window.winfo_screenheight() // 2) - (window.winfo_height() // 2)
        window.geometry(f"+{x}+{y}")
        
        window.mainloop()
        
    except ImportError:
        # Fallback if tkinter not available
        print(f"\nReport saved to: {report_file}")
        print("To view the full report, open the JSON file above.")
