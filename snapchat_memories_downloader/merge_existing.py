from __future__ import annotations

import os
import queue
import threading
from collections.abc import Callable
from pathlib import Path

from . import deps
from .overlay import merge_image_overlay, merge_video_overlay


def merge_existing_files(
    folder_path: str,
    *,
    jobs: int = 1,
    jobs_supplier: Callable[[], int] | None = None,
    log: Callable[[str], None] | None = None,
    progress_callback: Callable[[dict], None] | None = None,
    stop_event=None,
) -> dict:
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        message = f"Error: {folder_path} is not a valid directory!"
        _log(message, log)
        return {"merged": 0, "skipped": 0, "errors": 1}

    _log(f"Scanning {folder_path} for -main/-overlay pairs...", log)
    _log("=" * 60, log)

    main_files = list(folder.glob("*-main.*"))
    if not main_files:
        _log("No -main files found in the specified folder!", log)
        return {"merged": 0, "skipped": 0, "errors": 0}

    _log(f"Found {len(main_files)} -main files", log)

    merged_count = 0
    skipped_count = 0
    error_count = 0
    counter_lock = threading.Lock()
    total = len(main_files)
    _report_progress(0, total, progress_callback)

    def merge_one(main_file: Path, idx: int) -> None:
        nonlocal merged_count, skipped_count, error_count
        if stop_event and stop_event.is_set():
            return
        filename = main_file.name
        if "-main" not in filename:
            return

        base_name = filename.replace("-main", "")
        extension = main_file.suffix

        overlay_file = list(folder.glob(f"{base_name.replace(extension, '')}-overlay.*"))
        if not overlay_file:
            _log(f"\n[SKIP] {filename}", log)
            _log("  No matching overlay file found", log)
            with counter_lock:
                skipped_count += 1
            _report_progress(idx, total, progress_callback)
            return

        overlay_file = overlay_file[0]
        output_file = folder / base_name

        _log(f"\n[{idx}/{len(main_files)}] Merging: {filename}", log)
        _log(f"  Main: {main_file.name} ({main_file.stat().st_size:,} bytes)", log)
        _log(f"  Overlay: {overlay_file.name} ({overlay_file.stat().st_size:,} bytes)", log)

        try:
            is_video = extension.lower() in [".mp4", ".mov", ".avi"]
            is_image = extension.lower() in [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
                ".bmp",
                ".tiff",
                ".tif",
            ]

            if is_video:
                if not deps.ffmpeg_available:
                    _log("  ERROR: FFmpeg not available for video merging", log)
                    with counter_lock:
                        error_count += 1
                    _report_progress(idx, total, progress_callback)
                    return

                _log("  Merging videos (this may take a while)...", log)
                success = merge_video_overlay(main_file, overlay_file, output_file)
                if success:
                    _log(f"  Success: {base_name} ({output_file.stat().st_size:,} bytes)", log)
                    main_stat = main_file.stat()
                    os.utime(output_file, (main_stat.st_atime, main_stat.st_mtime))
                    with counter_lock:
                        merged_count += 1
                else:
                    _log("  ERROR: Video merge failed", log)
                    with counter_lock:
                        error_count += 1

            elif is_image:
                if deps.Image is None:
                    _log("  ERROR: Pillow not available for image merging", log)
                    with counter_lock:
                        error_count += 1
                    _report_progress(idx, total, progress_callback)
                    return

                with open(main_file, "rb") as f:
                    main_data = f.read()
                with open(overlay_file, "rb") as f:
                    overlay_data = f.read()

                merged_data = merge_image_overlay(main_data, overlay_data)
                with open(output_file, "wb") as f:
                    f.write(merged_data)

                _log(f"  Success: {base_name} ({len(merged_data):,} bytes)", log)
                main_stat = main_file.stat()
                os.utime(output_file, (main_stat.st_atime, main_stat.st_mtime))
                with counter_lock:
                    merged_count += 1
            else:
                _log(f"  ERROR: Unknown file type {extension}", log)
                with counter_lock:
                    error_count += 1

        except Exception as e:
            _log(f"  ERROR: {str(e)}", log)
            with counter_lock:
                error_count += 1
        finally:
            _report_progress(idx, total, progress_callback)

    normalized_jobs = max(1, min(int(jobs or 1), 20))
    if normalized_jobs > 1:
        max_workers = 20 if jobs_supplier else normalized_jobs
        allowed_workers = {"value": normalized_jobs}
        allowed_lock = threading.Lock()
        allowed_cv = threading.Condition(allowed_lock)
        monitor_stop = threading.Event()

        def read_job_limit() -> int:
            value = normalized_jobs
            if jobs_supplier:
                try:
                    value = int(jobs_supplier())
                except (TypeError, ValueError):
                    value = normalized_jobs
            if value < 1:
                value = 1
            if value > 20:
                value = 20
            return value

        def monitor_jobs() -> None:
            last_value = None
            while not monitor_stop.is_set():
                current = read_job_limit()
                if current != last_value:
                    with allowed_cv:
                        allowed_workers["value"] = current
                        allowed_cv.notify_all()
                    last_value = current
                monitor_stop.wait(0.3)

        if jobs_supplier:
            threading.Thread(target=monitor_jobs, daemon=True).start()

        work_queue: queue.Queue[tuple[int, Path] | None] = queue.Queue()

        def worker(worker_id: int) -> None:
            while True:
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
                idx, main_file = item
                merge_one(main_file, idx)
                work_queue.task_done()

        threads = []
        for worker_id in range(1, max_workers + 1):
            t = threading.Thread(target=worker, args=(worker_id,), daemon=True)
            t.start()
            threads.append(t)

        for idx, main_file in enumerate(main_files, start=1):
            if stop_event and stop_event.is_set():
                _log("Merge cancelled by user.", log)
                break
            work_queue.put((idx, main_file))

        for _ in threads:
            work_queue.put(None)

        work_queue.join()
        monitor_stop.set()
        with allowed_cv:
            allowed_cv.notify_all()
        for t in threads:
            t.join(timeout=0.5)
    else:
        for idx, main_file in enumerate(main_files, start=1):
            if stop_event and stop_event.is_set():
                _log("Merge cancelled by user.", log)
                break
            merge_one(main_file, idx)

    _log("\n" + "=" * 60, log)
    _log("Merge complete!", log)
    _log(f"Summary: {merged_count} merged, {skipped_count} skipped, {error_count} errors", log)
    _log("\nNote: Original -main and -overlay files were NOT deleted", log)
    return {"merged": merged_count, "skipped": skipped_count, "errors": error_count}


def _log(message: str, logger: Callable[[str], None] | None) -> None:
    print(message)
    if logger:
        logger(message)


def _report_progress(completed: int, total: int, progress_callback: Callable[[dict], None] | None) -> None:
    if not progress_callback:
        return
    progress_callback(
        {
            "type": "progress",
            "phase": "merge",
            "completed": completed,
            "total": total,
            "message": f"Merging overlays ({completed}/{total})",
        }
    )
