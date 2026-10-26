"""Windows file operations for the validation host's run directories.

Windows symbolic links need administrator rights or Developer Mode, so a run's
host/ folder links the read-only game snapshot with hard links (files; a copy
when no link can be made, e.g. across volumes) and directory junctions
(folders). A hard link shares the snapshot file's read-only attribute, so the
cleanup deletes such links without clearing it. Standard library + ctypes only;
import on Windows only.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import stat

import _winapi

FILE_ATTRIBUTE_READONLY = 0x1
DELETE = 0x00010000
FILE_SHARE_ALL = 0x1 | 0x2 | 0x4
OPEN_EXISTING = 3
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_DISPOSITION_INFO_EX = 21
# FILE_DISPOSITION_FLAG_DELETE | POSIX_SEMANTICS | IGNORE_READONLY_ATTRIBUTE (Windows 10 1809+, NTFS)
DISPOSITION_FLAGS = 0x1 | 0x2 | 0x10
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.SetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
_kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL


def link_file(src: Path, dst: Path) -> str:
    """Hard-link src to dst; copy it when the volume cannot link. Returns 'hardlink' or 'copy'."""
    try:
        os.link(src, dst)
        return 'hardlink'
    except FileExistsError:
        raise
    except OSError:
        shutil.copyfile(src, dst)
        return 'copy'


def link_dir(src: Path, dst: Path) -> None:
    """Create dst as a directory junction to src (no privilege needed, works across local volumes)."""
    _winapi.CreateJunction(os.path.abspath(src), os.path.abspath(dst))


def remove_tree(path: Path) -> None:
    """Delete a run directory: junctions and links are removed without entering them, and
    read-only hard links are deleted without clearing the attribute they share with the snapshot."""
    path = Path(path)
    with os.scandir(path) as entries:
        for entry in entries:
            full = Path(entry.path)
            if entry.is_junction():
                os.rmdir(full)
            elif entry.is_symlink():
                os.unlink(full)  # also removes a directory symlink on Windows
            elif entry.is_dir(follow_symlinks=False):
                remove_tree(full)
            else:
                # DirEntry.stat() reports st_nlink as 0 on Windows; os.stat reads the real count.
                _remove_file(full, os.stat(full, follow_symlinks=False))
    os.rmdir(path)


def _remove_file(path: Path, info: os.stat_result) -> None:
    if not info.st_file_attributes & FILE_ATTRIBUTE_READONLY:
        os.unlink(path)
    elif info.st_nlink == 1:
        # The only name of a file of our own (copies are made writable by copyfile; this is a fallback).
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        os.unlink(path)
    else:
        _delete_ignoring_read_only(path)


def _delete_ignoring_read_only(path: Path) -> None:
    handle = _kernel32.CreateFileW(str(path), DELETE, FILE_SHARE_ALL, None, OPEN_EXISTING,
                                   FILE_FLAG_OPEN_REPARSE_POINT, None)
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error(), f'cannot open {path} for deletion')
    try:
        flags = wintypes.DWORD(DISPOSITION_FLAGS)
        if not _kernel32.SetFileInformationByHandle(handle, FILE_DISPOSITION_INFO_EX, ctypes.byref(flags),
                                                    ctypes.sizeof(flags)):
            raise ctypes.WinError(ctypes.get_last_error(), f'cannot delete the read-only link {path}')
    finally:
        _kernel32.CloseHandle(handle)
