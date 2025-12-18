"""
Subprocess helpers.

On Windows, a "windowed" PyInstaller build has no console attached, so child
processes like ffmpeg may pop up their own console windows unless we suppress
them via creation flags/startup info.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Any


_tracked_pids: set[int] = set()
_tracked_pids_lock = threading.Lock()
_job_attach_warned = False


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

    with _tracked_pids_lock:
        pids = sorted(_tracked_pids)

    if not pids:
        return

    for pid in pids:
        _terminate_pid_tree(pid)


def _terminate_pid_tree(pid: int) -> None:
    if os.name == "nt":
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
        return

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            return

    time.sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
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


def _no_window_kwargs(*, extra_creationflags: int = 0) -> dict[str, Any]:
    if os.name != "nt":
        return {}
    kwargs: dict[str, Any] = {}
    has_console = _has_console_window()

    creationflags = extra_creationflags
    if not has_console:
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if create_no_window:
            creationflags |= create_no_window
    if creationflags:
        kwargs["creationflags"] = creationflags

    if not has_console:
        startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
        if startupinfo_cls is not None:
            startupinfo = startupinfo_cls()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo

    return kwargs


def run_capture(cmd: Sequence[str], *, timeout: int) -> subprocess.CompletedProcess[bytes]:
    job_handle, extra_creationflags = _prepare_windows_job()

    proc = subprocess.Popen(
        list(cmd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_no_window_kwargs(extra_creationflags=extra_creationflags),
        **({"start_new_session": True} if os.name != "nt" else {}),
    )
    track_pid(proc.pid)
    _attach_process_to_job(proc, job_handle)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return subprocess.CompletedProcess(list(cmd), proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired as exc:
            _terminate_pid_tree(proc.pid)
            try:
                proc.communicate(timeout=2)
            except Exception:
                pass
            raise exc
    finally:
        untrack_pid(proc.pid)


def _prepare_windows_job() -> tuple[int | None, int]:
    if os.name != "nt":
        return None, 0

    try:
        from . import windows_job

        if windows_job.current_process_in_managed_job():
            return None, 0

        job_handle = windows_job.get_or_create_child_job()
        if not job_handle:
            return None, 0

        in_job, breakaway_ok = windows_job.get_current_job_state()
        extra_flags = 0
        if in_job and breakaway_ok:
            extra_flags = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        return job_handle, extra_flags
    except Exception:
        return None, 0


def _attach_process_to_job(proc: subprocess.Popen[bytes], job_handle: int | None) -> None:
    if os.name != "nt" or not job_handle:
        return

    attached = False
    try:
        from .windows_job import assign_process_to_job, close_handle, open_process_handle

        proc_handle = getattr(proc, "_handle", None)
        if proc_handle:
            attached = assign_process_to_job(job_handle, proc_handle)

        if not attached:
            handle = open_process_handle(proc.pid)
            if handle:
                try:
                    attached = assign_process_to_job(job_handle, handle)
                finally:
                    close_handle(handle)
    except Exception:
        attached = False

    if not attached:
        _warn_job_attach_once()


def _warn_job_attach_once() -> None:
    global _job_attach_warned
    if _job_attach_warned:
        return
    _job_attach_warned = True
    print(
        "Warning: unable to attach child process to a kill-on-close job; "
        "ffmpeg may outlive the app if it crashes."
    )
