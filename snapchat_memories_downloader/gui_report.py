from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import flet as ft


def report_log_lines(report: dict, report_file: Path | None) -> list[str]:
    totals = report.get("totals", {}) if isinstance(report, dict) else {}
    processing = report.get("file_processing", {}) if isinstance(report, dict) else {}

    lines = [
        "\n" + "=" * 30 + " REPORT " + "=" * 30,
        f"Duration: {report.get('duration_seconds', '?')} seconds",
        f"Output: {report.get('output_directory', '')}",
        f"Memories: {totals.get('successful', 0)}/{totals.get('memories_processed', 0)} successful",
    ]

    if totals.get("failed", 0):
        lines.append(f"Failed: {totals.get('failed')}")
    if totals.get("skipped", 0):
        lines.append(f"Skipped: {totals.get('skipped')}")

    lines.append(
        f"Files: {totals.get('total_files', 0)} (merged: {processing.get('merged_overlays', 0)}, "
        f"unmerged pairs: {processing.get('unmerged_pairs', 0)})"
    )

    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.append("Errors:")
        lines.extend([f"  {err}" for err in errors])

    if report_file:
        lines.append(f"Report file: {report_file}")
    lines.append("=" * 68)
    return lines


def show_report_dialog(
    *,
    page: ft.Page,
    report: dict,
    report_file: Path | None,
    output_dir: Path | None,
    accent_color: str,
    open_path: Callable[[Path], None],
    on_error: Callable[[str], None],
    safe_update: Callable[[], None],
) -> None:
    totals = report.get("totals", {}) if isinstance(report, dict) else {}
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []

    output_path = output_dir or Path(str(report.get("output_directory", "")))

    def close_dialog(_) -> None:
        if page.dialog:
            page.dialog.open = False
        safe_update()

    def open_output_folder(_) -> None:
        try:
            open_path(output_path)
        except Exception as exc:
            on_error(f"Error opening output folder: {exc}")

    def open_report_json(_) -> None:
        if not report_file:
            return
        try:
            open_path(report_file)
        except Exception as exc:
            on_error(f"Error opening report file: {exc}")

    summary_lines = [
        f"Successful: {totals.get('successful', 0)} / {totals.get('memories_processed', 0)}",
        f"Failed: {totals.get('failed', 0)}",
        f"Skipped: {totals.get('skipped', 0)}",
        f"Output: {output_path}",
    ]
    if report_file:
        summary_lines.append(f"Report JSON: {report_file.name}")

    content_controls: list[ft.Control] = [
        ft.Text("\n".join(summary_lines), selectable=True),
    ]
    if errors:
        content_controls.append(ft.Container(height=8))
        content_controls.append(ft.Text("Errors:", weight=ft.FontWeight.BOLD, color=accent_color))
        content_controls.append(ft.Text("\n".join(str(e) for e in errors), selectable=True))

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Download report"),
        content=ft.Column(content_controls, tight=True, scroll=ft.ScrollMode.AUTO),
        actions=[
            ft.TextButton("Open output folder", on_click=open_output_folder),
            ft.TextButton(
                "Open report JSON",
                on_click=open_report_json,
                disabled=report_file is None,
            ),
            ft.TextButton("Close", on_click=close_dialog),
        ],
    )

    page.dialog = dialog
    dialog.open = True
    safe_update()

