"""
Windows Job Object helper.

Implements "kill all child processes when this process exits" by:
1) Creating a Job Object
2) Setting JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
3) Assigning the current process to the job

When the process terminates (including via os._exit), the job handle is closed
by the OS and all processes in the job are terminated.
"""

from __future__ import annotations

import os
import threading


_JOB_HANDLE = None
_CHILD_JOB_HANDLE = None
_CHILD_JOB_LOCK = threading.Lock()


def _create_kill_on_close_job() -> int | None:
    if os.name != "nt":
        return None

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        CreateJobObjectW = kernel32.CreateJobObjectW
        CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        CreateJobObjectW.restype = wintypes.HANDLE

        SetInformationJobObject = kernel32.SetInformationJobObject
        SetInformationJobObject.argtypes = [wintypes.HANDLE, wintypes.INT, wintypes.LPVOID, wintypes.DWORD]
        SetInformationJobObject.restype = wintypes.BOOL

        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JobObjectExtendedLimitInformation = 9

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job_handle = CreateJobObjectW(None, None)
        if not job_handle:
            return None

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        ok = SetInformationJobObject(
            job_handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            CloseHandle(job_handle)
            return None

        return job_handle
    except Exception:
        return None


def enable_kill_on_close_job() -> bool:
    if os.name != "nt":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        AssignProcessToJobObject = kernel32.AssignProcessToJobObject
        AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        AssignProcessToJobObject.restype = wintypes.BOOL

        GetCurrentProcess = kernel32.GetCurrentProcess
        GetCurrentProcess.argtypes = []
        GetCurrentProcess.restype = wintypes.HANDLE

        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL

        job_handle = _create_kill_on_close_job()
        if not job_handle:
            return False

        ok = AssignProcessToJobObject(job_handle, GetCurrentProcess())
        if not ok:
            # Common reason: already running inside a Job that disallows nesting.
            CloseHandle(job_handle)
            return False

        # Keep handle alive for process lifetime.
        global _JOB_HANDLE
        _JOB_HANDLE = job_handle
        return True
    except Exception:
        return False


def current_process_in_managed_job() -> bool:
    return _JOB_HANDLE is not None


def get_or_create_child_job() -> int | None:
    if os.name != "nt":
        return None

    global _CHILD_JOB_HANDLE
    if _CHILD_JOB_HANDLE is not None:
        return _CHILD_JOB_HANDLE

    with _CHILD_JOB_LOCK:
        if _CHILD_JOB_HANDLE is not None:
            return _CHILD_JOB_HANDLE
        _CHILD_JOB_HANDLE = _create_kill_on_close_job()
        return _CHILD_JOB_HANDLE


def assign_process_to_job(job_handle: int, process_handle: int) -> bool:
    if os.name != "nt":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        AssignProcessToJobObject = kernel32.AssignProcessToJobObject
        AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        AssignProcessToJobObject.restype = wintypes.BOOL

        ok = AssignProcessToJobObject(job_handle, wintypes.HANDLE(process_handle))
        return bool(ok)
    except Exception:
        return False


def open_process_handle(pid: int) -> int | None:
    if os.name != "nt":
        return None

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        OpenProcess = kernel32.OpenProcess
        OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        OpenProcess.restype = wintypes.HANDLE

        PROCESS_SET_QUOTA = 0x0100
        PROCESS_TERMINATE = 0x0001
        PROCESS_QUERY_INFORMATION = 0x0400
        access = PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_QUERY_INFORMATION

        handle = OpenProcess(access, False, pid)
        return int(handle) if handle else None
    except Exception:
        return None


def close_handle(handle: int) -> None:
    if os.name != "nt":
        return

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL
        CloseHandle(wintypes.HANDLE(handle))
    except Exception:
        pass


def get_current_job_state() -> tuple[bool, bool]:
    """
    Return (in_job, breakaway_allowed) for the current process.
    """
    if os.name != "nt":
        return False, False

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        IsProcessInJob = kernel32.IsProcessInJob
        IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        IsProcessInJob.restype = wintypes.BOOL

        GetCurrentProcess = kernel32.GetCurrentProcess
        GetCurrentProcess.argtypes = []
        GetCurrentProcess.restype = wintypes.HANDLE

        QueryInformationJobObject = kernel32.QueryInformationJobObject
        QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.INT,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        QueryInformationJobObject.restype = wintypes.BOOL

        in_job = wintypes.BOOL()
        ok = IsProcessInJob(GetCurrentProcess(), None, ctypes.byref(in_job))
        if not ok or not in_job:
            return False, False

        JobObjectExtendedLimitInformation = 9
        JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
        JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        ok = QueryInformationJobObject(
            None,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
            None,
        )
        if not ok:
            return True, False

        flags = int(info.BasicLimitInformation.LimitFlags)
        breakaway_ok = bool(flags & (JOB_OBJECT_LIMIT_BREAKAWAY_OK | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK))
        return True, breakaway_ok
    except Exception:
        return False, False
