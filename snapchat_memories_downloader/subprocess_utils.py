"""
Subprocess helpers.

On Windows, a "windowed" PyInstaller build has no console attached, so child
processes like ffmpeg may pop up their own console windows unless we suppress
them via creation flags/startup info.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from typing import Any


def _has_console_window() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes  # only available/meaningful on Windows

        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:
        return False


def _no_window_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    if _has_console_window():
        return {}

    kwargs: dict[str, Any] = {}

    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if create_no_window:
        kwargs["creationflags"] = create_no_window

    startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_cls is not None:
        startupinfo = startupinfo_cls()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo

    return kwargs


def run_capture(cmd: Sequence[str], *, timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(cmd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        **_no_window_kwargs(),
    )
