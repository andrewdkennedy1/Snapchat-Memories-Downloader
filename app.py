#!/usr/bin/env python3
"""
Snapchat Memories Downloader
Downloads all memories from Snapchat export HTML file with metadata preservation.

This file is the Flet GUI entrypoint.
"""

from __future__ import annotations

import sys
import traceback
from snapchat_memories_downloader.tk_dialogs import show_error

try:
    import flet as ft
    _HAS_FLET = True
except ImportError:
    _HAS_FLET = False

def main():
    if not _HAS_FLET:
        show_error(
            "Missing Dependencies",
            "Flet is not installed. Please install it with: pip install flet"
        )
        sys.exit(1)

    try:
        from snapchat_memories_downloader.process_lifecycle import enable_kill_children_on_exit
        from snapchat_memories_downloader.gui import main as flet_main
        
        enable_kill_children_on_exit()
        ft.app(target=flet_main)
    except Exception as e:
        error_msg = f"Failed to launch GUI:\n{str(e)}\n\n{traceback.format_exc()}"
        print(error_msg)
        show_error("Launch Error", error_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
