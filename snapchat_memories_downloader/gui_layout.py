from __future__ import annotations

import flet as ft

from snapchat_memories_downloader.gui_theme import SC_BLACK, SC_YELLOW, icon


def build_setup_section(gui) -> ft.Control:
    gui.html_input = ft.TextField(
        label="Snapchat HTML File (memories_history.html)",
        value="",
        expand=True,
        border_color=SC_YELLOW,
        hint_text="Select memories_history.html",
    )
    gui.output_input = ft.TextField(
        label="Output Directory",
        value="memories",
        expand=True,
        border_color=SC_YELLOW,
        hint_text="Choose where to save files",
        on_change=gui._on_output_change,
    )

    html_row = ft.Row(
        [
            gui.html_input,
            ft.IconButton(
                icon=icon("FILE_OPEN", "UPLOAD_FILE")
                or icon("UPLOAD_FILE", "INSERT_DRIVE_FILE")
                or icon("INSERT_DRIVE_FILE", "CIRCLE"),
                on_click=gui._pick_html,
                icon_color=SC_YELLOW,
                tooltip="Choose memories_history.html",
            ),
        ]
    )
    gui.html_summary_text = ft.Text("", size=12, color=SC_YELLOW)
    out_row = ft.Row(
        [
            gui.output_input,
            ft.IconButton(
                icon=icon("FOLDER_OPEN", "FOLDER") or icon("FOLDER", "CIRCLE"),
                on_click=gui._pick_dir,
                icon_color=SC_YELLOW,
                tooltip="Choose output folder",
            ),
        ]
    )

    return gui._section(
        "1. Setup",
        icon("SETTINGS", "TUNE") or icon("TUNE", "CIRCLE"),
        ft.Column([html_row, gui.html_summary_text, out_row], spacing=12),
    )


def build_config_section(gui) -> ft.Control:
    gui.mode_dropdown = ft.Dropdown(
        label="Run Mode",
        options=[
            ft.dropdown.Option("download", "Download All"),
            ft.dropdown.Option("resume", "Resume Incomplete"),
            ft.dropdown.Option("retry-failed", "Retry Failed"),
            ft.dropdown.Option("test", "Test (3 items)"),
        ],
        value="download",
        expand=True,
        on_change=lambda _: gui._sync_option_states(),
    )
    gui.media_dropdown = ft.Dropdown(
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

    gui.concurrent_cb = ft.Checkbox(
        label="Concurrent download",
        value=True,
        on_change=lambda _: gui._sync_option_states(),
    )
    gui.duplicates_cb = ft.Checkbox(label="Remove duplicates during download", value=True)
    gui.timestamp_cb = ft.Checkbox(label="Timestamp-based filenames", value=True)
    gui.join_multi_cb = ft.Checkbox(label="Join multi-snaps (videos)", value=True)

    gui.auto_jobs_text = ft.Text("Auto jobs: --", size=12, color=SC_YELLOW)
    gui.auto_jobs_hint = ft.Text(
        "Adjusts automatically based on system load.",
        size=11,
        color=SC_YELLOW,
    )
    gui.merge_mode_text = ft.Text(
        "Overlay merging runs after downloads complete (2-step process).",
        size=12,
        color=SC_YELLOW,
    )

    options = ft.Row(
        [
            ft.Column([gui.merge_mode_text, gui.concurrent_cb], expand=True, spacing=6),
            ft.Column([gui.duplicates_cb, gui.timestamp_cb, gui.join_multi_cb], expand=True, spacing=6),
            ft.Column([gui.auto_jobs_text, gui.auto_jobs_hint], width=220, spacing=6),
        ],
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )

    body = ft.Column(
        [
            ft.Row([gui.mode_dropdown, gui.media_dropdown], spacing=12),
            options,
        ],
        spacing=12,
    )

    return gui._section(
        "2. Configuration",
        icon("TUNE", "SETTINGS") or icon("SETTINGS", "CIRCLE"),
        body,
    )


def build_logs_section(gui) -> ft.Control:
    gui.log_list = ft.ListView(expand=True, spacing=2, auto_scroll=True)
    gui.clear_btn = ft.OutlinedButton(
        text="Clear logs",
        on_click=lambda _: gui._clear_logs(),
        icon=icon("DELETE_OUTLINE", "DELETE") or icon("DELETE", "CIRCLE"),
    )

    body = ft.Column(
        [
            ft.Row([ft.Container(expand=True), gui.clear_btn]),
            ft.Container(
                content=gui.log_list,
                height=100,
                padding=12,
                bgcolor=SC_BLACK,
                border_radius=10,
            ),
        ],
        spacing=10,
        expand=True,
    )

    return gui._section(
        "Logs",
        icon("TERMINAL", "CODE") or icon("CODE", "CIRCLE"),
        body,
    )
