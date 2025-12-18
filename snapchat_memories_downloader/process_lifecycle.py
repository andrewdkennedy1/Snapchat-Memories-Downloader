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

import atexit
import os
import signal
import sys
import threading
from typing import NoReturn


_windows_job_enabled = False
_shutdown_handlers_registered = False
_shutdown_lock = threading.Lock()


def enable_kill_children_on_exit() -> None:
    global _windows_job_enabled
    if not _windows_job_enabled:
        if os.name != "nt":
            _windows_job_enabled = True
        else:
            try:
                from .windows_job import enable_kill_on_close_job

                _windows_job_enabled = enable_kill_on_close_job()
            except Exception:
                _windows_job_enabled = False

    _register_shutdown_handlers()


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


def _register_shutdown_handlers() -> None:
    global _shutdown_handlers_registered
    if _shutdown_handlers_registered:
        return

    with _shutdown_lock:
        if _shutdown_handlers_registered:
            return
        _shutdown_handlers_registered = True

    def _cleanup() -> None:
        try:
            from .subprocess_utils import terminate_tracked_children

            terminate_tracked_children()
        except Exception:
            pass

    atexit.register(_cleanup)

    previous_hook = sys.excepthook

    def _excepthook(exc_type, exc, tb) -> None:
        _cleanup()
        previous_hook(exc_type, exc, tb)

    sys.excepthook = _excepthook

    def _install_signal_handler(sig: int) -> None:
        try:
            previous = signal.getsignal(sig)
        except Exception:
            return

        def _handler(signum, frame) -> None:
            _cleanup()
            if callable(previous):
                previous(signum, frame)
                return
            raise SystemExit(0)

        try:
            signal.signal(sig, _handler)
        except Exception:
            pass

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            _install_signal_handler(getattr(signal, name))
