from __future__ import annotations

import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .deps import requests
from .downloader import download_and_extract
from .files import (
    generate_filename,
    get_file_extension,
    parse_date_to_timestamp,
    set_file_timestamp,
)
from .metadata_store import initialize_metadata, metadata_lock, save_metadata
from .multisnap import join_multi_snaps
from .overlay import merge_video_overlay
from .parser import parse_html_file


def format_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.2f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.2f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"


def format_size(bytes_total: int) -> str:
    if bytes_total < 1024:
        return f"{bytes_total} B"
    elif bytes_total < 1024 * 1024:
        return f"{bytes_total / 1024:.2f} KB"
    else:
        return f"{bytes_total / (1024 * 1024):.2f} MB"


def download_item(
    idx: int,
    metadata: dict,
    memories: list,
    output_path: Path,
    metadata_list: list,
    merge_overlays: bool,
    defer_video_overlays: bool,
    overlays_only: bool,
    use_timestamp_filenames: bool,
    remove_duplicates: bool,
    deferred_videos: list,
    deferred_lock: threading.Lock,
    stats: dict,
    stats_lock: threading.Lock,
) -> None:
    memory = memories[idx]
    file_num = f"{metadata['number']:02d}"
    extension = get_file_extension(metadata.get("media_type", "Image"))

    print(f"\n# {metadata['number']}")
    print(f"  Date: {metadata['date']}")
    print(f"  Type: {metadata['media_type']}")
    print(f"  Location: {metadata['latitude']}, {metadata['longitude']}")

    if metadata.get("status") == "success" and metadata.get("files"):
        print("  Already downloaded, skipping...")
        return

    with metadata_lock:
        metadata["status"] = "in_progress"
        save_metadata(metadata_list, output_path)

    try:
        files_saved = download_and_extract(
            memory["url"],
            output_path,
            file_num,
            extension,
            merge_overlays,
            defer_video_overlays,
            metadata["date"],
            metadata["latitude"],
            metadata["longitude"],
            overlays_only,
            use_timestamp_filenames,
            remove_duplicates,
        )

        if len(files_saved) == 0:
            print("  Skipped: No overlay detected (overlays-only mode)")
            with metadata_lock:
                metadata["status"] = "skipped"
                metadata["skip_reason"] = "no_overlay"
                save_metadata(metadata_list, output_path)
            return

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

        with metadata_lock:
            metadata["status"] = "success"
            metadata["files"] = files_saved

            if any(f.get("deferred") for f in files_saved):
                with deferred_lock:
                    deferred_videos.append((file_num, metadata, files_saved))

            # Update total bytes
            total_bytes = sum(f.get("size", 0) for f in files_saved)
            with stats_lock:
                stats["total_bytes"] += total_bytes

            save_metadata(metadata_list, output_path)

    except (OSError, requests.RequestException, zipfile.BadZipFile) as e:
        print(f"  ERROR: {str(e)}")
        with metadata_lock:
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            save_metadata(metadata_list, output_path)


def download_all_memories(
    html_path: str,
    output_dir: str = "memories",
    resume: bool = False,
    retry_failed: bool = False,
    merge_overlays: bool = False,
    defer_video_overlays: bool = False,
    videos_only: bool = False,
    pictures_only: bool = False,
    overlays_only: bool = False,
    use_timestamp_filenames: bool = False,
    remove_duplicates: bool = False,
    join_multi_snaps_enabled: bool = False,
    concurrent: bool = False,
    jobs: int = 5,
) -> None:
    memories = parse_html_file(html_path)
    if not memories:
        print("No memories found in HTML file!")
        return

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    metadata_list = initialize_metadata(memories, output_path)

    if videos_only:
        items_to_download = [(i, m) for i, m in enumerate(metadata_list) if m.get("media_type") == "Video"]
        print(f"\nProcessing videos only: {len(items_to_download)} videos to download")
    elif pictures_only:
        items_to_download = [(i, m) for i, m in enumerate(metadata_list) if m.get("media_type") == "Image"]
        print(f"\nProcessing pictures only: {len(items_to_download)} pictures to download")
    elif resume:
        items_to_download = [
            (i, m)
            for i, m in enumerate(metadata_list)
            if m.get("status") in ["pending", "in_progress", "failed"]
        ]
        print(f"\nResuming: {len(items_to_download)} items to download")
    elif retry_failed:
        items_to_download = [(i, m) for i, m in enumerate(metadata_list) if m.get("status") == "failed"]
        print(f"\nRetrying: {len(items_to_download)} failed items")
    else:
        items_to_download = list(enumerate(metadata_list))
        print(f"\nDownloading {len(items_to_download)} memories to {output_dir}/")

    if not items_to_download:
        print("All selected memories already downloaded.")
        return

    print("=" * 60)

    total_items = len(items_to_download)
    deferred_videos: list[tuple[str, dict, list]] = []
    deferred_lock = threading.Lock()

    stats = {"total_bytes": 0, "start_time": time.time()}
    stats_lock = threading.Lock()

    def print_progress(completed: int):
        elapsed = time.time() - stats["start_time"]
        with stats_lock:
            total_b = stats["total_bytes"]
        speed = total_b / elapsed if elapsed > 0 else 0
        speed_fmt = format_speed(speed)
        size_fmt = format_size(total_b)
        print(f"[{completed}/{total_items}] Speed: {speed_fmt} (Total: {size_fmt})")

    print_progress(0)

    if concurrent and total_items > 1:
        print(f"Downloading concurrently using {jobs} jobs...")
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = [
                executor.submit(
                    download_item,
                    idx,
                    metadata,
                    memories,
                    output_path,
                    metadata_list,
                    merge_overlays,
                    defer_video_overlays,
                    overlays_only,
                    use_timestamp_filenames,
                    remove_duplicates,
                    deferred_videos,
                    deferred_lock,
                    stats,
                    stats_lock,
                )
                for idx, metadata in items_to_download
            ]

            completed = 0
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"\nERROR: Worker crashed: {e}")
                completed += 1
                print_progress(completed)
    else:
        for count, (idx, metadata) in enumerate(items_to_download, start=1):
            download_item(
                idx,
                metadata,
                memories,
                output_path,
                metadata_list,
                merge_overlays,
                defer_video_overlays,
                overlays_only,
                use_timestamp_filenames,
                remove_duplicates,
                deferred_videos,
                deferred_lock,
                stats,
                stats_lock,
            )
            print_progress(count)

    if deferred_videos:
        print("\n" + "=" * 60)
        print(f"Processing {len(deferred_videos)} deferred video overlay(s)...")
        print("=" * 60)

        for i, (file_num, metadata, files_saved) in enumerate(deferred_videos, start=1):
            print(f"\n({i}/{len(deferred_videos)}) Processing deferred video #{metadata['number']}")

            main_file = None
            overlay_file = None
            for file_info in files_saved:
                file_path = output_path / file_info["path"]
                if file_info["type"] == "main":
                    main_file = file_path
                elif file_info["type"] == "overlay":
                    overlay_file = file_path

            if main_file and overlay_file:
                try:
                    extension = main_file.suffix
                    output_filename = generate_filename(
                        metadata["date"], extension, use_timestamp_filenames, file_num
                    )
                    merged_file = output_path / output_filename

                    print("  Merging video overlay (this may take a while)...")
                    success = merge_video_overlay(main_file, overlay_file, merged_file)

                    if success:
                        with metadata_lock:
                            metadata["files"] = [
                                {"path": output_filename, "size": merged_file.stat().st_size, "type": "merged"}
                            ]

                        timestamp = parse_date_to_timestamp(metadata["date"])
                        if timestamp:
                            set_file_timestamp(merged_file, timestamp)

                        if main_file.exists():
                            main_file.unlink()
                            print(f"  Deleted: {main_file.name}")
                        if overlay_file.exists():
                            overlay_file.unlink()
                            print(f"  Deleted: {overlay_file.name}")

                        print(f"  Success: {output_filename} ({merged_file.stat().st_size:,} bytes)")
                    else:
                        print("  ERROR: Video merge failed, keeping separate files")

                except Exception as e:
                    print(f"  ERROR: {str(e)}")
                    print("  Keeping separate -main/-overlay files")

        with metadata_lock:
            save_metadata(metadata_list, output_path)
        print("\n" + "=" * 60)
        print("Deferred video processing complete!")

    metadata_file = output_path / "metadata.json"
    with metadata_lock:
        save_metadata(metadata_list, output_path)

    print("\n" + "=" * 60)
    print("Download complete!")
    print(f"Files saved to: {output_path.absolute()}")
    print(f"Metadata saved to: {metadata_file.absolute()}")

    if join_multi_snaps_enabled:
        join_multi_snaps(output_path)

    successful = sum(1 for m in metadata_list if m.get("status") == "success")
    failed = sum(1 for m in metadata_list if m.get("status") == "failed")
    pending = sum(1 for m in metadata_list if m.get("status") == "pending")
    total_files = sum(
        len(m.get("files", [])) for m in metadata_list if m.get("status") == "success"
    )
    print(f"\nSummary: {successful} successful, {failed} failed, {pending} pending, {total_files} total files")

    if failed > 0:
        print("\nTo retry failed downloads, run:")
        print("  python app.py --retry-failed")
    if pending > 0:
        print("\nTo resume incomplete downloads, run:")
        print("  python app.py --resume")
