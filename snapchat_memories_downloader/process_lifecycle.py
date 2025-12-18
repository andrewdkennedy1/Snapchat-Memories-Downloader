"""
Process lifecycle helpers.

Goal: when running as a GUI exe on Windows, closing the app should not leave
child processes (e.g. ffmpeg) running in the background.

We primarily rely on a Windows Job Object with the KILL_ON_JOB_CLOSE limit.
When the main process exits, Windows terminates all processes in the job.

If the job setup is unavailable (e.g. restricted environment), we fall back to
best-effort termination of tracked child PIDs.
"""

from __future__ import annotations

import os
from typing import NoReturn


_windows_job_enabled = False


def enable_kill_children_on_exit() -> None:
    global _windows_job_enabled
    if _windows_job_enabled:
        return
    if os.name != "nt":
        _windows_job_enabled = True
        return

    try:
        from .windows_job import enable_kill_on_close_job

        _windows_job_enabled = enable_kill_on_close_job()
    except Exception:
        _windows_job_enabled = False


def shutdown_now(exit_code: int = 0) -> NoReturn:
    """
    Hard-exit the process after best-effort child cleanup.

    Note: this uses os._exit() intentionally so the process exits even if
    non-daemon threads are running or the GUI framework keeps an event loop.
    """

    try:
        # If the Windows Job Object was enabled and this process was added to it,
        # closing this process will also kill children. We still do a best-effort
        # kill for environments where job assignment failed.
        from .subprocess_utils import terminate_tracked_children

        terminate_tracked_children()
    finally:
        os._exit(exit_code)

