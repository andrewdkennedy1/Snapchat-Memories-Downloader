from __future__ import annotations

import threading
from pathlib import Path

import flet as ft

from snapchat_memories_downloader.default_paths import suggest_output_dir_for_html
from snapchat_memories_downloader.deps import ensure_ffmpeg
from snapchat_memories_downloader.gui_layout import build_config_section, build_logs_section, build_setup_section
from snapchat_memories_downloader.gui_pump import UiEventPump
from snapchat_memories_downloader.gui_report import report_log_lines, show_report_dialog
from snapchat_memories_downloader.gui_theme import SC_BLACK, SC_GREY, SC_WHITE, SC_YELLOW, icon
from snapchat_memories_downloader.orchestrator import download_all_memories
from snapchat_memories_downloader.parser import parse_html_file
from snapchat_memories_downloader.process_lifecycle import enable_kill_children_on_exit, shutdown_now
from snapchat_memories_downloader.shell_open import open_path


class SnapchatGui:
    def __init__(self, page: ft.Page):
        enable_kill_children_on_exit()
        self.page = page
        self.stop_event = threading.Event()
        self.pump: UiEventPump | None = None
        self._last_report_file: Path | None = None
        self._output_dir_user_selected = False
        self._suppress_output_change_event = False
        self._setup_page()
        self._build_ui()
        self.pump = UiEventPump(
            run_in_ui=self._run_in_ui,
            safe_update=self._safe_update,
            log_list=self.log_list,
            progress_bar=self.progress_bar,
            status_text=self.status_text,
            speed_text=self.speed_text,
            log_color=SC_WHITE,
        )
        self._sync_option_states()
        self._start_ffmpeg_preflight()
        self._start_default_html_count_if_present()

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
        if hasattr(self.page, "on_disconnect"):
            self.page.on_disconnect = lambda _: self._force_shutdown()

    def _handle_window_event(self, e) -> None:
        data = str(getattr(e, "data", "") or "").lower()
        if "close" in data:
            self._force_shutdown()
            return
        # Ignore non-close window events (resize, focus, etc.).

    def _force_shutdown(self) -> None:
        try:
            self.stop_event.set()
            if self.pump:
                self.pump.stop()
        except Exception:
            pass
        shutdown_now(0)

    def _build_ui(self) -> None:
        header = self._build_header()
        setup_section = build_setup_section(self)
        config_section = build_config_section(self)
        action_section = self._build_action_section()
        logs_section = build_logs_section(self)

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

    def _start_default_html_count_if_present(self) -> None:
        html_value = (self.html_input.value or "").strip()
        if not html_value:
            return
        path = Path(html_value).expanduser()
        if not path.exists():
            return
        self.html_summary_text.value = "Parsing HTML..."
        self._safe_update()
        threading.Thread(target=self._update_html_count, args=(str(path),), daemon=True).start()

    def _start_ffmpeg_preflight(self) -> None:
        threading.Thread(target=self._run_ffmpeg_preflight, daemon=True).start()

    def _run_ffmpeg_preflight(self) -> None:
        def ui_log(message: str) -> None:
            self._run_in_ui(lambda: self._append_log_line(message))

        ui_log("FFmpeg: checking...")
        ok = ensure_ffmpeg(interactive=False, log=ui_log)
        ui_log("FFmpeg: ready" if ok else "FFmpeg: not available (video merges/join disabled)")

    def _build_header(self) -> ft.Control:
        app_icon = icon("PHOTO_CAMERA", "CAMERA_ALT") or icon("CAMERA", "IMAGE") or icon("IMAGE", "CIRCLE")
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

        self.open_output_btn = ft.OutlinedButton(
            text="Open output folder",
            icon=icon("FOLDER_OPEN", "FOLDER") or icon("FOLDER", "CIRCLE"),
            on_click=lambda _: self._open_output_folder(),
        )
        self.open_report_btn = ft.OutlinedButton(
            text="Open report",
            icon=icon("DESCRIPTION", "ARTICLE") or icon("ARTICLE", "CIRCLE"),
            on_click=lambda _: self._open_report_file(),
            disabled=True,
        )

        self.progress_bar = ft.ProgressBar(value=0, color=SC_YELLOW, visible=False)
        self.status_text = ft.Text("Ready", size=13, color=SC_WHITE, visible=False)
        self.speed_text = ft.Text("", size=13, color=SC_YELLOW, visible=False)

        body = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(content=self.start_btn, expand=True),
                        self.open_output_btn,
                        self.open_report_btn,
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.progress_bar,
                ft.Row([self.status_text, ft.Container(expand=True), self.speed_text]),
            ],
            spacing=10,
        )

        return self._section(
            "3. Run",
            icon("PLAY_ARROW", "ROCKET_LAUNCH") or icon("ROCKET_LAUNCH", "CIRCLE"),
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
            if not self._output_dir_user_selected:
                try:
                    suggested = suggest_output_dir_for_html(Path(self.html_input.value))
                    self._set_output_dir_value(suggested)
                except Exception:
                    pass
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
            self._output_dir_user_selected = True
            self.output_input.value = e.path
            self._safe_update()

    def _on_output_change(self, _) -> None:
        if self._suppress_output_change_event:
            return
        self._output_dir_user_selected = True

    def _set_output_dir_value(self, value: Path) -> None:
        self._suppress_output_change_event = True
        try:
            self.output_input.value = str(value)
        finally:
            self._suppress_output_change_event = False

    def _open_output_folder(self) -> None:
        try:
            open_path(Path(self.output_input.value))
        except Exception as exc:
            self._append_log_line(f"Error opening output folder: {exc}")

    def _open_report_file(self) -> None:
        if not self._last_report_file:
            return
        try:
            open_path(self._last_report_file)
        except Exception as exc:
            self._append_log_line(f"Error opening report file: {exc}")

    def _clear_logs(self) -> None:
        if self.pump:
            self.pump.clear_logs()

    def _append_log_line(self, text: str, *, update: bool = True) -> None:
        if self.pump:
            self.pump.append_log_line(text, update=update)

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

    def _validate_inputs(self) -> tuple[bool, str]:
        html_raw = (self.html_input.value or "").strip()
        if not html_raw:
            return False, "Please select memories_history.html"
        html_path = Path(html_raw).expanduser()
        if not html_path.exists():
            return False, f"HTML file not found: {html_path}"
        if html_path.suffix.lower() != ".html":
            return False, "HTML file must end with .html"
        out_raw = (self.output_input.value or "").strip()
        if out_raw == "":
            return False, "Output directory is required"
        out_dir = Path(out_raw).expanduser()
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
        if self.pump:
            self.pump.reset()
        self._last_report_file = None
        self.open_report_btn.disabled = True
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
        self._set_running(True)
        if self.pump:
            self.pump.start()

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
            "progress_callback": self.pump.progress_callback if self.pump else None,
            "show_report": True,
        }

        threading.Thread(target=self._run_downloader, args=(params,), daemon=True).start()

    def _run_downloader(self, params: dict) -> None:
        try:
            download_all_memories(**params)
            self._run_in_ui(lambda: self._append_log_line("Done!"))
        except Exception as exc:
            self._run_in_ui(lambda: self._append_log_line(f"CRITICAL ERROR: {exc}"))
        finally:
            if self.pump:
                self.pump.stop()
            self._run_in_ui(self._finalize_run)

    def _finalize_run(self) -> None:
        self._set_running(False)
        report_event = self.pump.take_report_event() if self.pump else None
        if not report_event:
            self._safe_update()
            return

        report = report_event.get("report")
        report_file_raw = report_event.get("report_file")
        output_dir_raw = report_event.get("output_dir")

        report_file = Path(report_file_raw) if report_file_raw else None
        output_dir = Path(output_dir_raw) if output_dir_raw else None

        if report_file:
            self._last_report_file = report_file
            self.open_report_btn.disabled = False

        if isinstance(report, dict):
            for line in report_log_lines(report, report_file):
                self._append_log_line(line, update=False)
            show_report_dialog(
                page=self.page,
                report=report,
                report_file=report_file,
                output_dir=output_dir,
                accent_color=SC_YELLOW,
                open_path=open_path,
                on_error=lambda msg: self._append_log_line(msg),
                safe_update=self._safe_update,
            )

        self._safe_update()


def main(page: ft.Page) -> None:
    SnapchatGui(page)


if __name__ == "__main__":
    ft.app(target=main)
