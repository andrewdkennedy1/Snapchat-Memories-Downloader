#!/usr/bin/env python3
"""
Snapchat Memories Downloader
Downloads all memories from Snapchat export HTML file with metadata preservation.

This file is the CLI/Gooey entrypoint. The implementation is split into modules
under `snapchat_memories_downloader/` by concern (parsing, downloading, EXIF,
overlay merging, metadata persistence, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

try:
    from gooey import Gooey, GooeyParser  # type: ignore

    _HAS_GOOEY = True
except Exception:
    Gooey = None  # type: ignore[assignment]
    GooeyParser = None  # type: ignore[assignment]
    _HAS_GOOEY = False

from snapchat_memories_downloader.deps import requests
from snapchat_memories_downloader.downloader import download_and_extract
from snapchat_memories_downloader.files import (
    get_file_extension,
    parse_date_to_timestamp,
    set_file_timestamp,
)
from snapchat_memories_downloader.merge_existing import merge_existing_files
from snapchat_memories_downloader.orchestrator import download_all_memories
from snapchat_memories_downloader.parser import parse_html_file


def _build_gooey_decorator():
    if not _HAS_GOOEY:
        return lambda fn: fn

    base_kwargs = dict(
        program_name="Snapchat Memories Downloader",
        default_size=(980, 720),
        navigation="Sidebar",
        header_show_title=True,
        header_show_subtitle=False,
        progress_regex=r"^\[(\d+)/(\d+)\]",
        progress_expr="x / y * 100",
        hide_progress_msg=False,
        clear_before_run=True,
    )

    attempts = [
        {**base_kwargs, "theme": "dark", "advanced": True, "required_cols": 1, "optional_cols": 3},
        {**base_kwargs, "theme": "dark", "advanced": True},
        {**base_kwargs, "theme": "dark"},
        {**base_kwargs, "advanced": True},
        base_kwargs,
    ]

    for kwargs in attempts:
        try:
            return Gooey(**kwargs)  # type: ignore[misc]
        except TypeError:
            continue

    return Gooey(**base_kwargs)  # type: ignore[misc]


@_build_gooey_decorator()
def main():
    parser: argparse.ArgumentParser
    if _HAS_GOOEY:
        parser = GooeyParser(
            description="Download your Snapchat Memories export to files on your computer (keeps dates and location when possible)."
        )
    else:
        parser = argparse.ArgumentParser(
            description="Download your Snapchat Memories export to files on your computer (keeps dates and location when possible)."
        )

    def add_arg(group, *args, **kwargs):
        if not _HAS_GOOEY:
            kwargs.pop("widget", None)
            kwargs.pop("gooey_options", None)
        return group.add_argument(*args, **kwargs)

    basics_group = parser.add_argument_group("Basics")
    add_arg(
        basics_group,
        "html_file",
        nargs="?",
        default="html/memories_history.html",
        help="Select your Snapchat export 'memories_history.html' (or the folder that contains it).",
        widget="FileChooser",
        gooey_options={"wildcard": "HTML (*.html)|*.html|All files (*.*)|*.*"},
    )
    add_arg(
        basics_group,
        "-o",
        "--output",
        type=str,
        default="memories",
        metavar="DIR",
        help="Where to save downloaded files.",
        widget="DirChooser",
    )

    run_group = parser.add_argument_group(
        "Filters & Run", "Resume, retry, and media selection"
    )
    add_arg(run_group, "--resume", action="store_true", help="Resume interrupted")
    add_arg(run_group, "--retry-failed", action="store_true", help="Retry failed")
    add_arg(run_group, "--test", action="store_true", help="Test (3 items)")
    add_arg(run_group, "--videos-only", action="store_true", help="Videos only")
    add_arg(run_group, "--pictures-only", action="store_true", help="Pictures only")
    add_arg(run_group, "--overlays-only", action="store_true", help="Overlays only")

    processing_group = parser.add_argument_group(
        "Processing", "Overlay and joining options"
    )
    add_arg(
        processing_group,
        "--merge-overlays",
        action="store_true",
        help="Merge overlays",
    )
    add_arg(
        processing_group,
        "--defer-video-overlays",
        action="store_true",
        help="Defer video merge",
    )
    add_arg(
        processing_group,
        "--join-multi-snaps",
        action="store_true",
        help="Join multi-snaps",
    )

    advanced_group = parser.add_argument_group(
        "Settings", "Filenames, cleanup, and speed"
    )
    add_arg(
        advanced_group,
        "--timestamp-filenames",
        action="store_true",
        help="Timestamp names",
    )
    add_arg(
        advanced_group,
        "--remove-duplicates",
        action="store_true",
        help="Skip duplicates",
    )
    add_arg(
        advanced_group,
        "--concurrent",
        action="store_true",
        help="Multi-threaded",
    )
    add_arg(
        advanced_group,
        "--jobs",
        type=int,
        default=5,
        help="Worker count",
    )

    tools_group = parser.add_argument_group("Tools")
    add_arg(
        tools_group,
        "--merge-existing",
        type=str,
        metavar="FOLDER",
        help="Merge existing -main/-overlay file pairs in a folder (no downloading)",
        widget="DirChooser",
    )

    args = parser.parse_args()

    if args.merge_existing:
        merge_existing_files(args.merge_existing)
        sys.exit(0)

    html_path = args.html_file
    if os.path.isdir(html_path):
        html_path = os.path.join(html_path, "memories_history.html")
        print(f"Looking for memories_history.html in directory: {html_path}")

    html_file = html_path
    if not os.path.exists(html_file):
        print(f"Error: {html_file} not found!")
        print("Usage: python app.py [path/to/file_or_folder] [options]")
        print("Run 'python app.py --help' for more information.")
        sys.exit(1)

    output_dir = args.output
    resume_mode = args.resume
    retry_failed_mode = args.retry_failed
    test_mode = args.test
    merge_overlays_mode = args.merge_overlays
    defer_video_overlays_mode = args.defer_video_overlays
    videos_only_mode = args.videos_only
    pictures_only_mode = args.pictures_only
    overlays_only_mode = args.overlays_only
    timestamp_filenames_mode = args.timestamp_filenames
    remove_duplicates_mode = args.remove_duplicates
    join_multi_snaps_mode = args.join_multi_snaps
    concurrent_mode = args.concurrent
    jobs_count = args.jobs

    selected_modes = sum([bool(resume_mode), bool(retry_failed_mode), bool(test_mode)])
    if selected_modes > 1:
        print("Error: Choose only one of --resume, --retry-failed, or --test.")
        sys.exit(2)

    if videos_only_mode and pictures_only_mode:
        print("Error: Choose only one of --videos-only or --pictures-only.")
        sys.exit(2)

    if defer_video_overlays_mode and not merge_overlays_mode:
        print("Note: --defer-video-overlays implies --merge-overlays, enabling it.")
        merge_overlays_mode = True

    if jobs_count < 1:
        jobs_count = 1

    if test_mode:
        print("TEST MODE: Downloading only first 3 memories\n")
        memories = parse_html_file(html_file)[:3]
        if not memories:
            print("No memories found in HTML file!")
            sys.exit(0)

        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        metadata_list: list[dict] = []

        total_test = len(memories)
        import time
        from snapchat_memories_downloader.orchestrator import format_speed, format_size
        
        test_stats = {"total_bytes": 0, "start_time": time.time()}

        def print_test_progress(completed: int):
            elapsed = time.time() - test_stats["start_time"]
            total_b = test_stats["total_bytes"]
            speed = total_b / elapsed if elapsed > 0 else 0
            speed_fmt = format_speed(speed)
            size_fmt = format_size(total_b)
            print(f"[{completed}/{total_test}] Speed: {speed_fmt} (Total: {size_fmt})")

        print_test_progress(0)

        for idx, memory in enumerate(memories, start=1):
            file_num = f"{idx:02d}"
            extension = get_file_extension(memory.get("media_type", "Image"))

            metadata = {
                "number": idx,
                "date": memory.get("date", "Unknown"),
                "media_type": memory.get("media_type", "Unknown"),
                "latitude": memory.get("latitude", "Unknown"),
                "longitude": memory.get("longitude", "Unknown"),
                "url": memory.get("url", ""),
            }

            print(f"  Date: {metadata['date']}")
            print(f"  Type: {metadata['media_type']}")
            print(f"  Location: {metadata['latitude']}, {metadata['longitude']}")

            files_saved: list[dict] = []
            try:
                files_saved = download_and_extract(
                    memory["url"],
                    output_path,
                    file_num,
                    extension,
                    merge_overlays_mode,
                    defer_video_overlays_mode,
                    metadata["date"],
                    metadata["latitude"],
                    metadata["longitude"],
                    False,  # overlays_only not used in test mode
                    timestamp_filenames_mode,
                    remove_duplicates_mode,
                )

                if len(files_saved) > 1:
                    print(f"  ZIP extracted: {len(files_saved)} files")
                    for file_info in files_saved:
                        print(f"    - {file_info['path']} ({file_info['size']:,} bytes)")
                else:
                    downloaded_file = files_saved[0]
                    print(
                        f"  Downloaded: {downloaded_file['path']} ({downloaded_file['size']:,} bytes)"
                    )

                timestamp = parse_date_to_timestamp(metadata["date"])
                if timestamp:
                    for file_info in files_saved:
                        file_path = output_path / file_info["path"]
                        set_file_timestamp(file_path, timestamp)
                    print(f"  Timestamp set to: {metadata['date']}")
                print()

                metadata["status"] = "success"
                metadata["files"] = files_saved
            except (OSError, requests.RequestException, zipfile.BadZipFile) as e:
                print(f"  ERROR: {str(e)}\n")
                metadata["status"] = "failed"
                metadata["error"] = str(e)

            test_stats["total_bytes"] += sum(f.get("size", 0) for f in files_saved)
            metadata_list.append(metadata)
            print_test_progress(idx)

        metadata_file = output_path / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata_list, f, indent=2, ensure_ascii=False)

    else:
        download_all_memories(
            html_file,
            output_dir=output_dir,
            resume=resume_mode,
            retry_failed=retry_failed_mode,
            merge_overlays=merge_overlays_mode,
            defer_video_overlays=defer_video_overlays_mode,
            videos_only=videos_only_mode,
            pictures_only=pictures_only_mode,
            overlays_only=overlays_only_mode,
            use_timestamp_filenames=timestamp_filenames_mode,
            remove_duplicates=remove_duplicates_mode,
            join_multi_snaps_enabled=join_multi_snaps_mode,
            concurrent=concurrent_mode,
            jobs=jobs_count,
        )


if __name__ == "__main__":
    main()
