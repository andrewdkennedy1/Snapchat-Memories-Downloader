from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path

import flet as ft

from snapchat_memories_downloader.orchestrator import download_all_memories
from snapchat_memories_downloader.parser import parse_html_file

# Snapchat-ish colors (dark UI)
SC_YELLOW = "#FFFC00"
SC_BLACK = "#000000"
SC_GREY = "#1D1D1D"
SC_WHITE = "#FFFFFF"


def _icon(name: str, fallback_name: str = "CIRCLE") -> ft.IconData:
    fallback = getattr(ft.Icons, fallback_name, None)
    return getattr(ft.Icons, name, fallback)


class SnapchatGui:
    def __init__(self, page: ft.Page):
        self.page = page
        self.stop_event = threading.Event()
        self._log_queue: queue.Queue[str] = queue.Queue(maxsize=5000)
        self._pump_stop = threading.Event()
        self._latest_progress: dict | None = None
        self._progress_lock = threading.Lock()
        self._setup_page()
        self._build_ui()
        self._sync_option_states()

    def _setup_page(self) -> None:
        self.page.title = "Snapchat Memories Downloader"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = SC_BLACK
        self.page.padding = 20
        self.page.window.width = 900
        self.page.window.height = 1080
        self.page.window.center()
        self.page.theme = ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=SC_YELLOW,
                on_primary=SC_BLACK,
                surface=SC_GREY,
                on_surface=SC_WHITE,
            )
        )
        self.page.on_window_event = self._handle_window_event

    def _handle_window_event(self, e) -> None:
        try:
            self.stop_event.set()
            self._pump_stop.set()
        except Exception:
            pass

        data = str(getattr(e, "data", "") or "").lower()
        if data == "close":
            os._exit(0)

    def _build_ui(self) -> None:
        header = self._build_header()
        setup_section = self._build_setup_section()
        config_section = self._build_config_section()
        action_section = self._build_action_section()
        logs_section = self._build_logs_section()

        content = ft.Column(
            [
                header,
                ft.Container(height=16),
                setup_section,
                config_section,
                action_section,
                logs_section,
            ],
            expand=True,
            spacing=16,
            scroll=ft.ScrollMode.ADAPTIVE,
        )

        self.page.add(content)

        self.file_picker = ft.FilePicker(on_result=self._on_file_result)
        self.dir_picker = ft.FilePicker(on_result=self._on_dir_result)
        self.page.overlay.extend([self.file_picker, self.dir_picker])

    def _build_header(self) -> ft.Control:
        app_icon = _icon("PHOTO_CAMERA", "CAMERA_ALT") or _icon("CAMERA", "IMAGE") or _icon("IMAGE", "CIRCLE")
        return ft.Row(
            [
                ft.Icon(app_icon, color=SC_YELLOW, size=38),
                ft.Text("Snapchat Memories", size=28, weight=ft.FontWeight.BOLD),
                ft.Text("Downloader", size=28, color=SC_YELLOW, weight=ft.FontWeight.BOLD),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )

    def _section(self, title: str, icon: ft.IconData, body: ft.Control) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=SC_YELLOW, size=18),
                            ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=SC_YELLOW),
                        ],
                        spacing=8,
                    ),
                    body,
                ],
                spacing=12,
            ),
            padding=16,
            bgcolor=SC_GREY,
            border_radius=12,
        )

    def _build_setup_section(self) -> ft.Control:
        self.html_input = ft.TextField(
            label="Snapchat HTML File (memories_history.html)",
            value="html/memories_history.html",
            expand=True,
            border_color=SC_YELLOW,
        )
        self.output_input = ft.TextField(
            label="Output Directory",
            value="memories",
            expand=True,
            border_color=SC_YELLOW,
        )

        html_row = ft.Row(
            [
                self.html_input,
                ft.IconButton(
                    icon=_icon("FILE_OPEN", "UPLOAD_FILE") or _icon("UPLOAD_FILE", "INSERT_DRIVE_FILE") or _icon("INSERT_DRIVE_FILE", "CIRCLE"),
                    on_click=self._pick_html,
                    icon_color=SC_YELLOW,
                    tooltip="Choose memories_history.html",
                ),
            ]
        )
        self.html_summary_text = ft.Text("", size=12, color=SC_YELLOW)
        out_row = ft.Row(
            [
                self.output_input,
                ft.IconButton(
                    icon=_icon("FOLDER_OPEN", "FOLDER") or _icon("FOLDER", "CIRCLE"),
                    on_click=self._pick_dir,
                    icon_color=SC_YELLOW,
                    tooltip="Choose output folder",
                ),
            ]
        )

        return self._section(
            "1. Setup",
            _icon("SETTINGS", "TUNE") or _icon("TUNE", "CIRCLE"),
            ft.Column([html_row, self.html_summary_text, out_row], spacing=12),
        )

    def _build_config_section(self) -> ft.Control:
        self.mode_dropdown = ft.Dropdown(
            label="Run Mode",
            options=[
                ft.dropdown.Option("download", "Download All"),
                ft.dropdown.Option("resume", "Resume Incomplete"),
                ft.dropdown.Option("retry-failed", "Retry Failed"),
                ft.dropdown.Option("test", "Test (3 items)"),
            ],
            value="download",
            expand=True,
            on_change=lambda _: self._sync_option_states(),
        )
        self.media_dropdown = ft.Dropdown(
            label="Media Filter",
            options=[
                ft.dropdown.Option("all", "All Media"),
                ft.dropdown.Option("videos", "Videos Only"),
                ft.dropdown.Option("pictures", "Pictures Only"),
                ft.dropdown.Option("overlays", "Overlays Only"),
            ],
            value="all",
            expand=True,
        )

        self.merge_cb = ft.Checkbox(label="Merge overlays (when possible)", value=True, on_change=lambda _: self._sync_option_states())
        self.defer_cb = ft.Checkbox(label="Defer video merges (batch at end)", value=False)
        self.concurrent_cb = ft.Checkbox(label="Concurrent download", value=True, on_change=lambda _: self._sync_option_states())
        self.duplicates_cb = ft.Checkbox(label="Remove duplicates during download", value=True)
        self.timestamp_cb = ft.Checkbox(label="Timestamp-based filenames", value=True)
        self.join_multi_cb = ft.Checkbox(label="Join multi-snaps (videos)", value=True)

        self.jobs_count = ft.TextField(
            label="Jobs",
            value="5",
            width=120,
            border_color=SC_YELLOW,
            hint_text="e.g. 5",
        )

        options = ft.Row(
            [
                ft.Column([self.merge_cb, self.defer_cb, self.concurrent_cb], expand=True, spacing=6),
                ft.Column([self.duplicates_cb, self.timestamp_cb, self.join_multi_cb], expand=True, spacing=6),
                ft.Column([self.jobs_count], width=140),
            ],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        body = ft.Column(
            [
                ft.Row([self.mode_dropdown, self.media_dropdown], spacing=12),
                options,
            ],
            spacing=12,
        )

        return self._section(
            "2. Configuration",
            _icon("TUNE", "SETTINGS") or _icon("SETTINGS", "CIRCLE"),
            body,
        )

    def _build_action_section(self) -> ft.Control:
        self.start_btn = ft.ElevatedButton(
            text="Start",
            on_click=self._start_download,
            style=ft.ButtonStyle(
                bgcolor=SC_YELLOW,
                color=SC_BLACK,
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
            height=46,
        )

        self.progress_bar = ft.ProgressBar(value=0, color=SC_YELLOW, visible=False)
        self.status_text = ft.Text("Ready", size=13, color=SC_WHITE, visible=False)
        self.speed_text = ft.Text("", size=13, color=SC_YELLOW, visible=False)

        body = ft.Column(
            [
                ft.Row([ft.Container(content=self.start_btn, expand=True)]),
                self.progress_bar,
                ft.Row([self.status_text, ft.Container(expand=True), self.speed_text]),
            ],
            spacing=10,
        )

        return self._section(
            "3. Run",
            _icon("PLAY_ARROW", "ROCKET_LAUNCH") or _icon("ROCKET_LAUNCH", "CIRCLE"),
            body,
        )

    def _build_logs_section(self) -> ft.Control:
        self.log_list = ft.ListView(expand=True, spacing=2, auto_scroll=True)
        self.clear_btn = ft.OutlinedButton(
            text="Clear logs",
            on_click=lambda _: self._clear_logs(),
            icon=_icon("DELETE_OUTLINE", "DELETE") or _icon("DELETE", "CIRCLE"),
        )

        body = ft.Column(
            [
                ft.Row([ft.Container(expand=True), self.clear_btn]),
                ft.Container(
                    content=self.log_list,
                    height=100,
                    padding=12,
                    bgcolor=SC_BLACK,
                    border_radius=10,
                ),
            ],
            spacing=10,
            expand=True,
        )

        return self._section(
            "Logs",
            _icon("TERMINAL", "CODE") or _icon("CODE", "CIRCLE"),
            body,
        )

    def _sync_option_states(self) -> None:
        is_test = self.mode_dropdown.value == "test"
        is_concurrent = bool(self.concurrent_cb.value) and not is_test

        self.jobs_count.disabled = not is_concurrent
        self.jobs_count.value = self.jobs_count.value or "5"

        is_merge_enabled = bool(self.merge_cb.value)
        self.defer_cb.disabled = not is_merge_enabled
        if not is_merge_enabled:
            self.defer_cb.value = False

        self._safe_update()

    def _pick_html(self, _) -> None:
        self.file_picker.pick_files(allowed_extensions=["html"])

    def _on_file_result(self, e: ft.FilePickerResultEvent) -> None:
        if e.files:
            self.html_input.value = e.files[0].path
            self.html_summary_text.value = "Parsing HTML..."
            self._safe_update()
            threading.Thread(
                target=self._update_html_count, args=(self.html_input.value,), daemon=True
            ).start()

    def _update_html_count(self, html_path: str) -> None:
        try:
            memories = parse_html_file(html_path, log=None)
            count = len(memories)
            self._run_in_ui(
                lambda: self._set_html_summary(f"Found {count} memories")
            )
        except Exception as exc:
            self._run_in_ui(
                lambda: self._set_html_summary(f"Error parsing HTML: {exc}")
            )

    def _set_html_summary(self, text: str) -> None:
        self.html_summary_text.value = text
        self._safe_update()

    def _pick_dir(self, _) -> None:
        self.dir_picker.get_directory_path()

    def _on_dir_result(self, e: ft.FilePickerResultEvent) -> None:
        if e.path:
            self.output_input.value = e.path
            self._safe_update()

    def _clear_logs(self) -> None:
        self.log_list.controls.clear()
        self._safe_update()

    def _append_log_line(self, text: str, *, update: bool = True) -> None:
        self.log_list.controls.append(ft.Text(text, size=12, color=SC_WHITE, font_family="monospace"))
        max_lines = 2000
        if len(self.log_list.controls) > max_lines:
            del self.log_list.controls[: len(self.log_list.controls) - max_lines]
        if update:
            self._safe_update()

    def _safe_update(self) -> None:
        try:
            self.page.update()
        except Exception:
            pass

    def _run_in_ui(self, fn) -> None:
        for method_name in ("call_from_thread", "invoke_later"):
            method = getattr(self.page, method_name, None)
            if callable(method):
                method(fn)
                return
        fn()

    def _progress_callback(self, data: dict) -> None:
        data_type = data.get("type")
        if data_type == "progress":
            with self._progress_lock:
                self._latest_progress = dict(data)
            return

        if data_type == "log":
            msg = str(data.get("message", ""))
            if not msg:
                return
            try:
                self._log_queue.put_nowait(msg)
            except queue.Full:
                return

    def _pump_ui_events(self) -> None:
        last_flush = 0.0
        pending_logs: list[str] = []

        while not self._pump_stop.is_set() or not self._log_queue.empty():
            try:
                line = self._log_queue.get(timeout=0.1)
                pending_logs.append(line)
            except queue.Empty:
                pass

            now = time.monotonic()
            should_flush = (now - last_flush) >= 0.15 or len(pending_logs) >= 100
            if not should_flush:
                continue

            with self._progress_lock:
                progress = self._latest_progress

            logs_to_apply = pending_logs[:200]
            pending_logs = pending_logs[200:]
            last_flush = now

            def apply() -> None:
                for ln in logs_to_apply:
                    self._append_log_line(ln, update=False)

                if progress and progress.get("type") == "progress":
                    completed = int(progress.get("completed", 0))
                    total = int(progress.get("total", 1)) or 1
                    self.progress_bar.value = completed / total
                    self.status_text.value = f"Downloaded {completed} / {total}"
                    speed = str(progress.get("speed", ""))
                    total_size = str(progress.get("total_size", ""))
                    suffix = f" (Total: {total_size})" if total_size else ""
                    self.speed_text.value = f"{speed}{suffix}".strip()

                self._safe_update()

            self._run_in_ui(apply)

    def _validate_inputs(self) -> tuple[bool, str]:
        html_path = Path(self.html_input.value).expanduser()
        if not html_path.exists():
            return False, f"HTML file not found: {html_path}"
        if html_path.suffix.lower() != ".html":
            return False, "HTML file must end with .html"
        out_dir = Path(self.output_input.value).expanduser()
        if str(out_dir).strip() == "":
            return False, "Output directory is required"
        return True, ""

    def _set_running(self, running: bool) -> None:
        self.start_btn.disabled = running
        self.start_btn.text = "Downloading..." if running else "Start"
        self.progress_bar.visible = running
        self.status_text.visible = running
        self.speed_text.visible = running
        if running:
            self.progress_bar.value = 0
            self.status_text.value = "Starting..."
            self.speed_text.value = ""
        self._safe_update()

    def _start_download(self, _) -> None:
        ok, error = self._validate_inputs()
        self._clear_logs()
        if not ok:
            self._append_log_line(f"Error: {error}")
            return

        is_test = self.mode_dropdown.value == "test"
        if is_test:
            self._append_log_line("Test mode: downloading first 3 items")

        jobs_value = self.jobs_count.value.strip() if self.jobs_count.value else ""
        if self.jobs_count.disabled:
            jobs = 1
        else:
            if not jobs_value.isdigit() or int(jobs_value) < 1:
                self._append_log_line("Error: Jobs must be a positive integer.")
                return
            jobs = int(jobs_value)

        self.stop_event.clear()
        self._pump_stop.clear()
        self._set_running(True)
        threading.Thread(target=self._pump_ui_events, daemon=True).start()

        params = {
            "html_path": self.html_input.value,
            "output_dir": self.output_input.value,
            "resume": self.mode_dropdown.value == "resume",
            "retry_failed": self.mode_dropdown.value == "retry-failed",
            "merge_overlays": bool(self.merge_cb.value),
            "defer_video_overlays": bool(self.defer_cb.value),
            "videos_only": self.media_dropdown.value == "videos",
            "pictures_only": self.media_dropdown.value == "pictures",
            "overlays_only": self.media_dropdown.value == "overlays",
            "use_timestamp_filenames": bool(self.timestamp_cb.value),
            "remove_duplicates": bool(self.duplicates_cb.value),
            "join_multi_snaps_enabled": bool(self.join_multi_cb.value),
            "concurrent": bool(self.concurrent_cb.value) and not is_test,
            "jobs": jobs,
            "limit": 3 if is_test else None,
            "stop_event": self.stop_event,
            "progress_callback": self._progress_callback,
        }

        threading.Thread(target=self._run_downloader, args=(params,), daemon=True).start()

    def _run_downloader(self, params: dict) -> None:
        try:
            download_all_memories(**params)
            self._run_in_ui(lambda: self._append_log_line("Done!"))
        except Exception as exc:
            self._run_in_ui(lambda: self._append_log_line(f"CRITICAL ERROR: {exc}"))
        finally:
            self._pump_stop.set()
            self._run_in_ui(lambda: self._set_running(False))


def main(page: ft.Page) -> None:
    SnapchatGui(page)


if __name__ == "__main__":
    ft.app(target=main)
