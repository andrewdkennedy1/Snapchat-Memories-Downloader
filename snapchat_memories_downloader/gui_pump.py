from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

import flet as ft


class UiEventPump:
    def __init__(
        self,
        *,
        run_in_ui: Callable[[Callable[[], None]], None],
        safe_update: Callable[[], None],
        log_list: ft.ListView,
        progress_bar: ft.ProgressBar,
        status_text: ft.Text,
        speed_text: ft.Text,
        log_color: str,
        max_log_lines: int = 2000,
    ) -> None:
        self._run_in_ui = run_in_ui
        self._safe_update = safe_update

        self._log_list = log_list
        self._progress_bar = progress_bar
        self._status_text = status_text
        self._speed_text = speed_text

        self._log_color = log_color
        self._max_log_lines = max_log_lines

        self._log_queue: queue.Queue[str] = queue.Queue(maxsize=5000)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._lock = threading.Lock()
        self._latest_progress: dict | None = None
        self._report_event: dict | None = None

    def reset(self) -> None:
        with self._lock:
            self._latest_progress = None
            self._report_event = None
        while True:
            try:
                self._log_queue.get_nowait()
            except queue.Empty:
                break

    def clear_logs(self) -> None:
        self._log_list.controls.clear()
        self._safe_update()

    def append_log_line(self, text: str, *, update: bool = True) -> None:
        self._log_list.controls.append(
            ft.Text(text, size=12, color=self._log_color, font_family="monospace")
        )
        if len(self._log_list.controls) > self._max_log_lines:
            del self._log_list.controls[: len(self._log_list.controls) - self._max_log_lines]
        if update:
            self._safe_update()

    def start(self) -> None:
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._pump_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def take_report_event(self) -> dict | None:
        with self._lock:
            evt = dict(self._report_event) if self._report_event else None
            self._report_event = None
        return evt

    def progress_callback(self, data: dict) -> None:
        data_type = data.get("type")
        if data_type == "progress":
            with self._lock:
                self._latest_progress = dict(data)
            return

        if data_type == "report":
            with self._lock:
                self._report_event = dict(data)
            return

        if data_type != "log":
            return

        msg = str(data.get("message", ""))
        if not msg:
            return
        try:
            self._log_queue.put_nowait(msg)
        except queue.Full:
            return

    def _pump_loop(self) -> None:
        last_flush = 0.0
        pending_logs: list[str] = []

        while not self._stop.is_set() or not self._log_queue.empty():
            try:
                line = self._log_queue.get(timeout=0.1)
                pending_logs.append(line)
            except queue.Empty:
                pass

            now = time.monotonic()
            should_flush = (now - last_flush) >= 0.15 or len(pending_logs) >= 100
            if not should_flush:
                continue

            with self._lock:
                progress = dict(self._latest_progress) if self._latest_progress else None

            logs_to_apply = pending_logs[:200]
            pending_logs = pending_logs[200:]
            last_flush = now

            def apply() -> None:
                for ln in logs_to_apply:
                    self.append_log_line(ln, update=False)

                if progress and progress.get("type") == "progress":
                    completed = int(progress.get("completed", 0))
                    total = int(progress.get("total", 1)) or 1
                    self._progress_bar.value = completed / total
                    self._status_text.value = f"Downloaded {completed} / {total}"
                    speed = str(progress.get("speed", ""))
                    total_size = str(progress.get("total_size", ""))
                    suffix = f" (Total: {total_size})" if total_size else ""
                    self._speed_text.value = f"{speed}{suffix}".strip()

                self._safe_update()

            self._run_in_ui(apply)

