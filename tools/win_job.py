"""Windows Job Object supervision for the validation Worker.

The Worker is started suspended, put into a job and only then resumed, so it and
every process it starts are in the job from their first instruction. The job
holds a hard limit on the committed memory of all its processes
(JOB_OBJECT_LIMIT_JOB_MEMORY) and kills them all when it is terminated or its
last handle is closed (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE). Standard library +
ctypes only; import on Windows only.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import subprocess

JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
JOB_OBJECT_ASSOCIATE_COMPLETION_PORT_INFORMATION = 7
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_MSG_ACTIVE_PROCESS_ZERO = 4
JOB_OBJECT_MSG_JOB_MEMORY_LIMIT = 10
CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
MESSAGES = {JOB_OBJECT_MSG_JOB_MEMORY_LIMIT: 'memoryLimit', JOB_OBJECT_MSG_ACTIVE_PROCESS_ZERO: 'empty'}


class _BasicLimit(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount',
                                                     'OtherOperationCount', 'ReadTransferCount',
                                                     'WriteTransferCount', 'OtherTransferCount')]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _BasicLimit), ('IoInfo', _IoCounters),
                ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [('TotalUserTime', ctypes.c_int64), ('TotalKernelTime', ctypes.c_int64),
                ('ThisPeriodTotalUserTime', ctypes.c_int64), ('ThisPeriodTotalKernelTime', ctypes.c_int64),
                ('TotalPageFaultCount', wintypes.DWORD), ('TotalProcesses', wintypes.DWORD),
                ('ActiveProcesses', wintypes.DWORD), ('TotalTerminatedProcesses', wintypes.DWORD)]


class _CompletionPort(ctypes.Structure):
    _fields_ = [('CompletionKey', ctypes.c_void_p), ('CompletionPort', wintypes.HANDLE)]


_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_ntdll = ctypes.WinDLL('ntdll')
for _name, _args, _result in (
        ('CreateJobObjectW', (ctypes.c_void_p, wintypes.LPCWSTR), wintypes.HANDLE),
        ('SetInformationJobObject', (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD), wintypes.BOOL),
        ('QueryInformationJobObject', (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                       ctypes.POINTER(wintypes.DWORD)), wintypes.BOOL),
        ('AssignProcessToJobObject', (wintypes.HANDLE, wintypes.HANDLE), wintypes.BOOL),
        ('TerminateJobObject', (wintypes.HANDLE, wintypes.UINT), wintypes.BOOL),
        ('CreateIoCompletionPort', (wintypes.HANDLE, wintypes.HANDLE, ctypes.c_size_t, wintypes.DWORD), wintypes.HANDLE),
        ('GetQueuedCompletionStatus', (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_size_t),
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD), wintypes.BOOL),
        ('TerminateProcess', (wintypes.HANDLE, wintypes.UINT), wintypes.BOOL),
        ('CloseHandle', (wintypes.HANDLE,), wintypes.BOOL)):
    _function = getattr(_kernel32, _name)
    _function.argtypes, _function.restype = _args, _result
_ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
_ntdll.NtResumeProcess.restype = ctypes.c_long


def _check(ok, what):
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error(), what)


class Job:
    """One Job Object with a hard memory limit; every process started through it stays inside."""

    def __init__(self, memory_limit_bytes: int):
        self._job = _kernel32.CreateJobObjectW(None, None)
        _check(self._job, 'CreateJobObjectW')
        self._port = None
        try:
            self._port = _kernel32.CreateIoCompletionPort(INVALID_HANDLE_VALUE, None, 0, 1)
            _check(self._port, 'CreateIoCompletionPort')
            association = _CompletionPort(None, self._port)
            _check(_kernel32.SetInformationJobObject(self._job, JOB_OBJECT_ASSOCIATE_COMPLETION_PORT_INFORMATION,
                                                     ctypes.byref(association), ctypes.sizeof(association)),
                   'associate the completion port')
            limit = _ExtendedLimit()
            # DIE_ON_UNHANDLED_EXCEPTION: a crash ends the process instead of waiting on an error dialog.
            limit.BasicLimitInformation.LimitFlags = (JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                                                      | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION)
            limit.JobMemoryLimit = memory_limit_bytes
            _check(_kernel32.SetInformationJobObject(self._job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                                     ctypes.byref(limit), ctypes.sizeof(limit)), 'set the job limits')
        except BaseException:
            self.close()
            raise

    def start(self, command, *, cwd, env, stdout, stderr) -> subprocess.Popen:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP)
        handle = int(process._handle)
        try:
            _check(_kernel32.AssignProcessToJobObject(self._job, handle), 'AssignProcessToJobObject')
            status = _ntdll.NtResumeProcess(handle)
            if status < 0:
                raise OSError(f'NtResumeProcess failed with NTSTATUS {status & 0xFFFFFFFF:#010x}')
        except BaseException:
            _kernel32.TerminateProcess(handle, 1)
            process.wait()
            raise
        return process

    def poll_messages(self) -> set[str]:
        """Job notifications since the last call: 'memoryLimit' and/or 'empty'."""
        seen = set()
        message, key, overlapped = wintypes.DWORD(), ctypes.c_size_t(), ctypes.c_void_p()
        while _kernel32.GetQueuedCompletionStatus(self._port, ctypes.byref(message), ctypes.byref(key),
                                                  ctypes.byref(overlapped), 0):
            if message.value in MESSAGES:
                seen.add(MESSAGES[message.value])
        return seen

    def _query(self, structure, information_class):
        _check(_kernel32.QueryInformationJobObject(self._job, information_class, ctypes.byref(structure),
                                                   ctypes.sizeof(structure), None), 'QueryInformationJobObject')
        return structure

    def peak_memory(self) -> int:
        """Peak committed memory of all processes in the job, in bytes."""
        return self._query(_ExtendedLimit(), JOB_OBJECT_EXTENDED_LIMIT_INFORMATION).PeakJobMemoryUsed

    def active_processes(self) -> int:
        return self._query(_Accounting(), JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION).ActiveProcesses

    def terminate(self) -> None:
        _check(_kernel32.TerminateJobObject(self._job, 1), 'TerminateJobObject')

    def close(self) -> None:
        """Close the job; KILL_ON_JOB_CLOSE ends anything still inside."""
        for name in ('_port', '_job'):
            handle = getattr(self, name, None)
            if handle:
                _kernel32.CloseHandle(handle)
                setattr(self, name, None)
