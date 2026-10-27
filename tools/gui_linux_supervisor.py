"""Linux GUI process guardian: contain detached workers and preserve session ownership."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def children_of(pid):
    """Collect descendants from /proc, deepest first; disappearing processes are normal."""
    parents = {}
    for entry in os.scandir('/proc'):
        if not entry.name.isdigit():
            continue
        try:
            data = Path(entry.path, 'stat').read_bytes().rsplit(b')', 1)[1].split()
            parents[int(entry.name)] = int(data[1])
        except (OSError, ValueError, IndexError):
            continue
    found = set()
    ordered = []
    frontier = {pid}
    while frontier:
        frontier = {child for child, parent in parents.items() if parent in frontier and child not in found}
        found.update(frontier)
        ordered.extend(frontier)
    return list(reversed(ordered))


def signal_owned(pid, owner):
    """A pidfd pins process identity; recheck ancestry before signalling it."""
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return False
    try:
        if pid not in children_of(owner):
            return False
        try:
            signal.pidfd_send_signal(fd, signal.SIGKILL)
            return True
        except ProcessLookupError:
            return False
    finally:
        os.close(fd)


def inner(status_path, lock_fd, command):
    gui = subprocess.Popen(command, pass_fds=(lock_fd,) if lock_fd >= 0 else ())
    code = gui.wait()
    Path(status_path).write_text(json.dumps({'exitCode': code}))
    return 0


def main(status_path, lock_fd, command):
    # Require identity-safe process signalling before starting the GUI.
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Linux pidfd support is required for safe GUI process cleanup')
    probe = os.pidfd_open(os.getpid())
    try:
        signal.pidfd_send_signal(probe, 0)
    finally:
        os.close(probe)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'cannot establish GUI child subreaper')
    stopping = False
    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    inner_status = status_path + '.inner'
    child = subprocess.Popen([sys.executable, __file__, '--inner', inner_status, str(lock_fd), *command],
                             pass_fds=(lock_fd,) if lock_fd >= 0 else ())
    while child.poll() is None and not stopping:
        time.sleep(.05)
    killed = set()
    # Retain the lock and continue until every child has actually exited. A process
    # stuck in kernel I/O can take longer than a timeout to honor SIGKILL.
    while True:
        child.poll()  # only Popen reaps its own child, preserving its exit status
        live = children_of(os.getpid())
        if not live:
            break
        for pid in live:
            if signal_owned(pid, os.getpid()):
                killed.add(pid)
            if pid != child.pid:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
        time.sleep(.02)
    code = child.wait()
    if Path(inner_status).is_file():
        code = json.loads(Path(inner_status).read_text())['exitCode']
    Path(status_path).write_text(json.dumps({'exitCode': code, 'strayProcessesKilled': bool(killed)}))
    return 0


if __name__ == '__main__':
    if sys.argv[1] == '--inner':
        sys.exit(inner(sys.argv[2], int(sys.argv[3]), sys.argv[4:]))
    sys.exit(main(sys.argv[1], int(sys.argv[2]), sys.argv[3:]))
