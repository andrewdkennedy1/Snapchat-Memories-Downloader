from __future__ import annotations

import queue
import threading
import time
import zipfile
from pathlib import Path

from .deps import requests
from .downloader import download_and_extract
from .duplicates import DuplicateIndex
from .exif_utils import add_exif_metadata
from .files import (
    generate_filename,
    get_file_extension,
    parse_date_to_timestamp,
    set_file_timestamp,
)
from .metadata_store import initialize_metadata, metadata_lock, save_metadata
from .multisnap import join_multi_snaps
from .overlay import merge_image_overlay, merge_video_overlay
from .parser import parse_html_file
from .report import generate_report, save_report, print_report_summary, show_report_popup


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


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def download_item(
    idx: int,
    metadata: dict,
    memories: list,
    output_path: Path,
    metadata_list: list,
    stop_event: threading.Event | None,
    merge_overlays: bool,
    defer_video_overlays: bool,
    overlays_only: bool,
    use_timestamp_filenames: bool,
    remove_duplicates: bool,
    duplicate_index: DuplicateIndex | None,
    deferred_overlays: list,
    deferred_lock: threading.Lock,
    stats: dict,
    stats_lock: threading.Lock,
    progress_callback: callable = None,
) -> None:
    if stop_event and stop_event.is_set():
        return
    memory = memories[idx]
    file_num = f"{metadata['number']:02d}"
    extension = get_file_extension(metadata.get("media_type", "Image"))

    def log(msg: str):
        print(msg)
        if progress_callback:
            progress_callback({"type": "log", "message": msg})

    log(f"\n# {metadata['number']}")
    log(f"  Date: {metadata['date']}")
    log(f"  Type: {metadata['media_type']}")
    log(f"  Location: {metadata['latitude']}, {metadata['longitude']}")

    if metadata.get("status") == "success" and metadata.get("files"):
        log("  Already downloaded, skipping...")
        return

    if stop_event and stop_event.is_set():
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
            duplicate_index,
        )

        if stop_event and stop_event.is_set():
            return

        if len(files_saved) == 0:
            log("  Skipped: No overlay detected (overlays-only mode)")
            with metadata_lock:
                metadata["status"] = "skipped"
                metadata["skip_reason"] = "no_overlay"
                save_metadata(metadata_list, output_path)
            return

        if len(files_saved) > 1:
            log(f"  ZIP extracted: {len(files_saved)} files")
            for file_info in files_saved:
                log(f"    - {file_info['path']} ({file_info['size']:,} bytes)")
        else:
            downloaded_file = files_saved[0]
            log(
                f"  Downloaded: {downloaded_file['path']} ({downloaded_file['size']:,} bytes)"
            )

        timestamp = parse_date_to_timestamp(metadata["date"])
        if timestamp:
            for file_info in files_saved:
                file_path = output_path / file_info["path"]
                set_file_timestamp(file_path, timestamp)
            log(f"  Timestamp set to: {metadata['date']}")

        with metadata_lock:
            metadata["status"] = "success"
            metadata["files"] = files_saved

            if any(f.get("deferred") for f in files_saved):
                with deferred_lock:
                    deferred_overlays.append((file_num, metadata, files_saved))

            # Update total bytes
            total_bytes = sum(f.get("size", 0) for f in files_saved)
            with stats_lock:
                stats["total_bytes"] += total_bytes

            save_metadata(metadata_list, output_path)

    except (OSError, requests.RequestException, zipfile.BadZipFile) as e:
        log(f"  ERROR: {str(e)}")
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
    jobs_supplier: callable | None = None,
    limit: int | None = None,
    stop_event: threading.Event | None = None,
    progress_callback: callable = None,
    show_report: bool = True,
) -> None:
    start_time = time.time()
    
    memories = parse_html_file(html_path)
    if limit is not None and limit >= 0:
        memories = memories[:limit]
    if not memories:
        print("No memories found in HTML file!")
        return

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    duplicate_index = DuplicateIndex(output_path) if remove_duplicates else None
    if duplicate_index:
        duplicate_index.build()

    metadata_list = initialize_metadata(memories, output_path)

    if resume:
        items_to_download = [
            (i, m)
            for i, m in enumerate(metadata_list)
            if m.get("status") in ["pending", "in_progress", "failed"]
        ]
        mode_label = "Resuming"
    elif retry_failed:
        items_to_download = [(i, m) for i, m in enumerate(metadata_list) if m.get("status") == "failed"]
        mode_label = "Retrying failed"
    else:
        items_to_download = list(enumerate(metadata_list))
        mode_label = "Downloading"

    if videos_only:
        items_to_download = [(i, m) for i, m in items_to_download if m.get("media_type") == "Video"]
        media_label = "videos only"
    elif pictures_only:
        items_to_download = [(i, m) for i, m in items_to_download if m.get("media_type") == "Image"]
        media_label = "pictures only"
    else:
        media_label = "all media"

    if resume or retry_failed:
        print(f"\n{mode_label} ({media_label}): {len(items_to_download)} items to download")
    else:
        print(f"\n{mode_label} ({media_label}) {len(items_to_download)} memories to {output_dir}/")

    if not items_to_download:
        print("All selected memories already downloaded.")
        return

    print("=" * 60)

    total_items = len(items_to_download)
    deferred_overlays: list[tuple[str, dict, list]] = []
    deferred_lock = threading.Lock()

    stats = {"total_bytes": 0, "start_time": time.time()}
    stats_lock = threading.Lock()
    completed_counter = {"count": 0}
    counter_lock = threading.Lock()

    def print_progress(completed: int):
        elapsed = time.time() - stats["start_time"]
        with stats_lock:
            total_b = stats["total_bytes"]
        speed = total_b / elapsed if elapsed > 0 else 0
        speed_fmt = format_speed(speed)
        size_fmt = format_size(total_b)
        eta_seconds = None
        if completed > 0:
            remaining = max(total_items - completed, 0)
            avg_per_item = elapsed / completed
            eta_seconds = avg_per_item * remaining
        eta_fmt = format_eta(eta_seconds)
        msg = f"[{completed}/{total_items}] Speed: {speed_fmt} ETA: {eta_fmt} (Total: {size_fmt})"
        print(msg)
        if progress_callback:
            progress_callback({
                "type": "progress",
                "completed": completed,
                "total": total_items,
                "speed": speed_fmt,
                "eta": eta_fmt,
                "total_size": size_fmt,
                "message": msg
            })

    print_progress(0)

    if concurrent and total_items > 1:
        job_limit_default = max(1, min(int(jobs), 20))

        def read_job_limit() -> int:
            value = job_limit_default
            if jobs_supplier:
                try:
                    value = int(jobs_supplier())
                except (TypeError, ValueError):
                    value = job_limit_default
            if value < 1:
                value = 1
            if value > 20:
                value = 20
            return value

        max_workers = 20 if jobs_supplier else job_limit_default
        allowed_workers = {"value": read_job_limit()}
        allowed_lock = threading.Lock()
        allowed_cv = threading.Condition(allowed_lock)
        monitor_stop = threading.Event()

        def monitor_jobs() -> None:
            last_value = None
            while not monitor_stop.is_set():
                current = read_job_limit()
                if current != last_value:
                    with allowed_cv:
                        allowed_workers["value"] = current
                        allowed_cv.notify_all()
                    last_value = current
                time.sleep(0.3)

        if jobs_supplier:
            threading.Thread(target=monitor_jobs, daemon=True).start()

        print(f"Downloading concurrently using up to {max_workers} workers...")
        work_queue: queue.Queue[tuple[int, dict] | None] = queue.Queue()

        def worker(worker_id: int) -> None:
            while True:
                if stop_event and stop_event.is_set():
                    pass
                with allowed_cv:
                    while worker_id > allowed_workers["value"]:
                        if stop_event and stop_event.is_set():
                            break
                        allowed_cv.wait(timeout=0.5)
                try:
                    item = work_queue.get(timeout=0.2)
                except queue.Empty:
                    if stop_event and stop_event.is_set():
                        continue
                    else:
                        continue
                if item is None:
                    work_queue.task_done()
                    break
                idx, metadata = item
                try:
                    download_item(
                        idx,
                        metadata,
                        memories,
                        output_path,
                        metadata_list,
                        stop_event,
                        merge_overlays,
                        defer_video_overlays,
                        overlays_only,
                        use_timestamp_filenames,
                        remove_duplicates,
                        duplicate_index,
                        deferred_overlays,
                        deferred_lock,
                        stats,
                        stats_lock,
                        progress_callback,
                    )
                except Exception as e:
                    print(f"\nERROR: Worker crashed: {e}")
                finally:
                    with counter_lock:
                        completed_counter["count"] += 1
                        completed = completed_counter["count"]
                    print_progress(completed)
                    work_queue.task_done()

        threads = []
        for worker_id in range(1, max_workers + 1):
            t = threading.Thread(target=worker, args=(worker_id,), daemon=True)
            t.start()
            threads.append(t)

        for item in items_to_download:
            if stop_event and stop_event.is_set():
                break
            work_queue.put(item)

        for _ in threads:
            work_queue.put(None)

        work_queue.join()
        monitor_stop.set()
        with allowed_cv:
            allowed_cv.notify_all()
        for t in threads:
            t.join(timeout=0.5)
    else:
        for count, (idx, metadata) in enumerate(items_to_download, start=1):
            if stop_event and stop_event.is_set():
                break
            download_item(
                idx,
                metadata,
                memories,
                output_path,
                metadata_list,
                stop_event,
                merge_overlays,
                defer_video_overlays,
                overlays_only,
                use_timestamp_filenames,
                remove_duplicates,
                duplicate_index,
                deferred_overlays,
                deferred_lock,
                stats,
                stats_lock,
                progress_callback,
            )
            print_progress(count)

    if stop_event and stop_event.is_set():
        return

    if deferred_overlays:
        print("\n" + "=" * 60)
        print(f"Processing {len(deferred_overlays)} deferred overlay merge(s)...")
        print("=" * 60)

        for i, (file_num, metadata, files_saved) in enumerate(deferred_overlays, start=1):
            if stop_event and stop_event.is_set():
                return
            print(f"\n({i}/{len(deferred_overlays)}) Processing deferred merge #{metadata['number']}")

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

                    is_video = extension.lower() in [".mp4", ".mov", ".avi"]
                    if is_video:
                        print("  Merging video overlay (this may take a while)...")
                        success = merge_video_overlay(main_file, overlay_file, merged_file)
                    else:
                        print("  Merging image overlay...")
                        with open(main_file, "rb") as f:
                            main_data = f.read()
                        with open(overlay_file, "rb") as f:
                            overlay_data = f.read()
                        merged_data = merge_image_overlay(main_data, overlay_data)
                        merged_data = add_exif_metadata(
                            merged_data,
                            metadata["date"],
                            metadata["latitude"],
                            metadata["longitude"],
                        )
                        with open(merged_file, "wb") as f:
                            f.write(merged_data)
                        success = merged_file.exists() and merged_file.stat().st_size > 0

                    if success:
                        with metadata_lock:
                            metadata["files"] = [
                                {"path": output_filename, "size": merged_file.stat().st_size, "type": "merged"}
                            ]

                        timestamp = parse_date_to_timestamp(metadata["date"])
                        if timestamp:
                            set_file_timestamp(merged_file, timestamp)

                        if main_file.exists():
                            if duplicate_index:
                                duplicate_index.unregister_file(main_file)
                            main_file.unlink()
                            print(f"  Deleted: {main_file.name}")
                        if overlay_file.exists():
                            if duplicate_index:
                                duplicate_index.unregister_file(overlay_file)
                            overlay_file.unlink()
                            print(f"  Deleted: {overlay_file.name}")

                        print(f"  Success: {output_filename} ({merged_file.stat().st_size:,} bytes)")
                    else:
                        print("  ERROR: Overlay merge failed, keeping separate files")

                except Exception as e:
                    print(f"  ERROR: {str(e)}")
                    print("  Keeping separate -main/-overlay files")

        with metadata_lock:
            save_metadata(metadata_list, output_path)
        print("\n" + "=" * 60)
        print("Deferred overlay processing complete!")

    metadata_file = output_path / "metadata.json"
    with metadata_lock:
        save_metadata(metadata_list, output_path)

    if stop_event and stop_event.is_set():
        return

    print("\n" + "=" * 60)
    print("Download complete!")
    print(f"Files saved to: {output_path.absolute()}")
    print(f"Metadata saved to: {metadata_file.absolute()}")

    if join_multi_snaps_enabled:
        join_multi_snaps(output_path)

    end_time = time.time()
    
    # Generate comprehensive report
    report = generate_report(metadata_list, output_path, start_time, end_time)
    report_file = save_report(report, output_path)
    
    # Show report summary in console
    print_report_summary(report)

    if progress_callback:
        try:
            progress_callback(
                {
                    "type": "report",
                    "report": report,
                    "report_file": str(report_file),
                    "output_dir": str(output_path.absolute()),
                }
            )
        except Exception:
            pass
    
    # Show GUI popup if requested and not stopped
    if show_report and progress_callback is None and not (stop_event and stop_event.is_set()):
        show_report_popup(report, report_file)
    
    # Legacy command suggestions
    if report["totals"]["failed"] > 0:
        print("\nTo retry failed downloads, run:")
        print("  python app.py --retry-failed")
    if report["totals"]["pending"] > 0:
        print("\nTo resume incomplete downloads, run:")
        print("  python app.py --resume")
