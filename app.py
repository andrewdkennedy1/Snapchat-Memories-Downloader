#!/usr/bin/env python3
"""
Snapchat Memories Downloader
Downloads all memories from Snapchat export HTML file with metadata preservation.

This file is the CLI/Gooey/Flet entrypoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

try:
    from gooey import Gooey, GooeyParser  # type: ignore
    _HAS_GOOEY = True
except Exception:
    Gooey = None
    GooeyParser = None
    _HAS_GOOEY = False

try:
    import flet as ft
    _HAS_FLET = True
except ImportError:
    _HAS_FLET = False

from snapchat_memories_downloader.deps import requests, ensure_ffmpeg
from snapchat_memories_downloader.default_paths import find_memories_history_html
from snapchat_memories_downloader.downloader import download_and_extract
from snapchat_memories_downloader.files import (
    get_file_extension,
    parse_date_to_timestamp,
    set_file_timestamp,
)
from snapchat_memories_downloader.merge_existing import merge_existing_files
from snapchat_memories_downloader.orchestrator import download_all_memories, format_speed, format_size
from snapchat_memories_downloader.parser import parse_html_file


def _build_gooey_decorator():
    if not _HAS_GOOEY:
        return lambda fn: fn
    return Gooey(
        program_name="Snapchat Memories Downloader",
        default_size=(900, 620),
        navigation="Tabbed",
        theme="dark",
        advanced=True,
    )


@_build_gooey_decorator()
def main():
    # If Flet is installed and no args provided, launch Flet GUI
    if _HAS_FLET and len(sys.argv) == 1:
        from snapchat_memories_downloader.process_lifecycle import enable_kill_children_on_exit
        from snapchat_memories_downloader.gui import main as flet_main
        enable_kill_children_on_exit()
        ft.app(target=flet_main)
        return

    # Preflight check for FFmpeg (Windows only, auto-downloads if missing)
    ensure_ffmpeg()

    parser: argparse.ArgumentParser
    if _HAS_GOOEY:
        parser = GooeyParser(description="Snapchat Memories Downloader")
    else:
        parser = argparse.ArgumentParser(description="Snapchat Memories Downloader")

    def add_arg(group, *args, **kwargs):
        if not _HAS_GOOEY:
            kwargs.pop("widget", None)
            kwargs.pop("gooey_options", None)
        return group.add_argument(*args, **kwargs)

    def legacy_help(help_text: str) -> Any:
        return argparse.SUPPRESS if _HAS_GOOEY else help_text

    setup_group = parser.add_argument_group("Setup")
    add_arg(
        setup_group,
        "html_file",
        nargs="?",
        default="",
        widget="FileChooser",
    )
    add_arg(setup_group, "-o", "--output", type=str, default="memories", widget="DirChooser")

    download_group = parser.add_argument_group("Download Options")
    add_arg(download_group, "--mode", choices=["download", "resume", "retry-failed", "test"], default="download")
    add_arg(download_group, "--media", choices=["all", "videos", "pictures", "overlays"], default="all")
    # CLI-friendly aliases (kept for README/backwards compatibility; hidden in Gooey UI)
    add_arg(download_group, "--resume", action="store_true", help=legacy_help("Resume interrupted download"))
    add_arg(download_group, "--retry-failed", action="store_true", help=legacy_help("Retry only failed items"))
    add_arg(download_group, "--test", action="store_true", help=legacy_help("Download first 3 items only"))
    add_arg(download_group, "--videos-only", action="store_true", help=legacy_help("Download only videos"))
    add_arg(download_group, "--pictures-only", action="store_true", help=legacy_help("Download only pictures"))
    add_arg(download_group, "--overlays-only", action="store_true", help=legacy_help("Download only overlays (ZIPs with overlays)"))
    
    # Advanced 
    advanced_group = parser.add_argument_group("Advanced")
    add_arg(advanced_group, "--merge-overlays", action="store_true", default=True)
    add_arg(advanced_group, "--defer-video-overlays", action="store_true")
    add_arg(advanced_group, "--concurrent", action="store_true", default=True)
    add_arg(advanced_group, "--jobs", type=int, default=5)
    add_arg(advanced_group, "--remove-duplicates", action="store_true", default=True)
    add_arg(advanced_group, "--timestamp-filenames", action="store_true", default=True)
    add_arg(advanced_group, "--join-multi-snaps", action="store_true", default=True)

    tools_group = parser.add_argument_group("Tools")
    add_arg(tools_group, "--merge-existing", type=str, widget="DirChooser")
    add_arg(tools_group, "--no-report", action="store_true", help="Disable popup report window")

    args = parser.parse_args()

    if args.merge_existing:
        merge_existing_files(args.merge_existing)
        sys.exit(0)

    if not args.html_file:
        guessed = find_memories_history_html()
        if guessed:
            args.html_file = str(guessed)

    if not args.html_file:
        print("Error: Please provide the path to memories_history.html")
        print("Tip: You can drag/drop the file onto the executable, or run with:")
        print("  SnapchatMemoriesDownloader.exe <path-to-memories_history.html>")
        sys.exit(1)

    html_path = Path(args.html_file)
    if html_path.is_dir():
        html_path = html_path / "memories_history.html"
    args.html_file = str(html_path)

    # Core logic
    mode = args.mode
    if args.resume:
        mode = "resume"
    elif args.retry_failed:
        mode = "retry-failed"
    elif args.test:
        mode = "test"

    media = args.media
    if args.videos_only:
        media = "videos"
    elif args.pictures_only:
        media = "pictures"
    elif args.overlays_only:
        media = "overlays"
    
    resume_mode = (mode == "resume")
    retry_failed_mode = (mode == "retry-failed")
    test_mode = (mode == "test")

    videos_only_mode = (media == "videos")
    pictures_only_mode = (media == "pictures")
    overlays_only_mode = (media == "overlays")

    if test_mode:
        print("TEST MODE: Downloading first 3 memories\n")
        memories = parse_html_file(args.html_file)[:3]
        if not memories:
            print("No memories found!")
            sys.exit(0)
        
        output_path = Path(args.output)
        output_path.mkdir(exist_ok=True)
        
        import time
        stats = {"total_bytes": 0, "start_time": time.time()}
        
        for idx, memory in enumerate(memories, start=1):
            file_num = f"{idx:02d}"
            # Simplified download for test mode
            download_and_extract(
                memory["url"], output_path, file_num, 
                get_file_extension(memory.get("media_type", "Image")),
                args.merge_overlays, args.defer_video_overlays,
                memory["date"], memory.get("latitude"), memory.get("longitude"),
                overlays_only_mode, args.timestamp_filenames, args.remove_duplicates
            )
            print(f"Downloaded {idx}/3")
        print("\nTest complete!")
        return

    download_all_memories(
        args.html_file,
        output_dir=args.output,
        resume=resume_mode,
        retry_failed=retry_failed_mode,
        merge_overlays=args.merge_overlays,
        defer_video_overlays=args.defer_video_overlays,
        videos_only=videos_only_mode,
        pictures_only=pictures_only_mode,
        overlays_only=overlays_only_mode,
        use_timestamp_filenames=args.timestamp_filenames,
        remove_duplicates=args.remove_duplicates,
        join_multi_snaps_enabled=args.join_multi_snaps,
        concurrent=args.concurrent,
        jobs=args.jobs,
        show_report=not args.no_report,
    )


if __name__ == "__main__":
    main()
