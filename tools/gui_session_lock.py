"""Cross-process ownership of the GUI session for one results directory."""
from contextlib import contextmanager
import errno
import os

if __package__:
    from . import validation_host as vh
else:
    import validation_host as vh


@contextmanager
def session_lock(results):
    """Hold an OS lock; yield its fd so a Unix GUI can retain it on host death.

    The lock file lives outside the removable session and is never unlinked:
    unlinking a lock file allows contenders to lock different inodes.
    """
    path = results / '.gui-session.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_BINARY', 0), 0o600)
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise vh.Blocked('guiSessionBusy', f'{results} already has an active GUI session') from error
            raise
        yield fd
    finally:
        # Do not explicitly unlock: an inherited Unix descriptor must retain
        # ownership until the GUI closes even if its launcher dies.
        os.close(fd)
