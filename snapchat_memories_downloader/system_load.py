from __future__ import annotations

import os
import time
from pathlib import Path


def _read_cpu_times_windows() -> tuple[int, int] | None:
    try:
        import ctypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ) == 0:
            return None

        def to_int(ft: FILETIME) -> int:
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

        idle_time = to_int(idle)
        kernel_time = to_int(kernel)
        user_time = to_int(user)
        total_time = kernel_time + user_time
        return idle_time, total_time
    except Exception:
        return None


def _read_cpu_times_proc() -> tuple[int, int] | None:
    stat_path = Path("/proc/stat")
    if not stat_path.exists():
        return None
    try:
        with stat_path.open("r", encoding="utf-8") as handle:
            line = handle.readline()
        parts = line.strip().split()
        if not parts or parts[0] != "cpu":
            return None
        values = [int(v) for v in parts[1:]]
        if len(values) < 4:
            return None
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return idle, total
    except Exception:
        return None


def _read_cpu_times() -> tuple[int, int] | None:
    if os.name == "nt":
        return _read_cpu_times_windows()
    return _read_cpu_times_proc()


class CpuUsageSampler:
    def __init__(self) -> None:
        self._last_idle: int | None = None
        self._last_total: int | None = None
        self._last_value: float | None = None

    def usage_percent(self) -> float | None:
        sample = _read_cpu_times()
        if sample is None:
            return self._last_value
        idle, total = sample
        if self._last_idle is None or self._last_total is None:
            self._last_idle = idle
            self._last_total = total
            return self._last_value
        idle_delta = idle - self._last_idle
        total_delta = total - self._last_total
        self._last_idle = idle
        self._last_total = total
        if total_delta <= 0:
            return self._last_value
        usage = 100.0 * (1.0 - (idle_delta / total_delta))
        usage = max(0.0, min(100.0, usage))
        self._last_value = usage
        return usage


def auto_job_target(
    usage_percent: float | None,
    *,
    min_jobs: int = 1,
    max_jobs: int = 20,
) -> int:
    cores = os.cpu_count() or 4
    if usage_percent is None:
        return max(min_jobs, min(max_jobs, cores))
    headroom = max(0.0, 100.0 - usage_percent)
    target = int(round((headroom / 100.0) * cores))
    if target < min_jobs:
        target = min_jobs
    if target > max_jobs:
        target = max_jobs
    return target


def throttle_sleep(seconds: float) -> None:
    time.sleep(seconds)
