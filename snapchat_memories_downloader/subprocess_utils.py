"""
Subprocess helpers.

On Windows, a "windowed" PyInstaller build has no console attached, so child
processes like ffmpeg may pop up their own console windows unless we suppress
them via creation flags/startup info.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Sequence
from typing import Any


_tracked_pids: set[int] = set()
_tracked_pids_lock = threading.Lock()


def track_pid(pid: int) -> None:
    with _tracked_pids_lock:
        _tracked_pids.add(pid)


def untrack_pid(pid: int) -> None:
    with _tracked_pids_lock:
        _tracked_pids.discard(pid)


def terminate_tracked_children() -> None:
    """
    Best-effort termination of tracked child processes.

    This is a fallback for cases where Windows Job Objects cannot be enabled.
    """

    if os.name != "nt":
        return

    with _tracked_pids_lock:
        pids = sorted(_tracked_pids)

    if not pids:
        return

    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                **_no_window_kwargs(),
            )
        except Exception:
            pass


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
    proc = subprocess.Popen(
        list(cmd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_no_window_kwargs(),
    )
    track_pid(proc.pid)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return subprocess.CompletedProcess(list(cmd), proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired as exc:
            try:
                proc.kill()
            except Exception:
                pass
            raise exc
    finally:
        untrack_pid(proc.pid)
