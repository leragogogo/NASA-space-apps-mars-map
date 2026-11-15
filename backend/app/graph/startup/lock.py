"""A lock file next to graph.npz, so that only one process (for example one of several server workers) builds."""
from __future__ import annotations

import os
import socket
import time
from contextlib import contextmanager
from pathlib import Path

DEFAULT_TIMEOUT_S = 1800.0  # longest wait for another process's build
STALE_AFTER_S = 1800.0  # a build takes about a minute; a lock older than this belongs to a crashed process


def _owner_is_dead(lock: Path) -> bool:
    """True when the lock was written by a process on this machine that no longer exists (for example one killed
    for running out of memory), so nobody has to wait for the age limit. Locks of other machines are not judged."""
    try:
        pid, host, _ = lock.read_text().split()
        if host != socket.gethostname():
            return False
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return True
    except (OSError, ValueError):
        return False  # unreadable, or a process we may not signal: assume it is alive
    return False


@contextmanager
def graph_lock(graph_path: Path, timeout_s: float = DEFAULT_TIMEOUT_S, poll_s: float = 0.5,
               stale_after_s: float = STALE_AFTER_S):
    """Hold `<graph>.lock` while building. Others wait until it is released.

    Waiting longer than `timeout_s` in total raises TimeoutError. A lock whose owner process is gone (same machine)
    is taken over at once; any lock older than `stale_after_s` is taken over too. These are separate on purpose:
    a short wait must never steal the lock of a builder that is still working.
    """
    graph_path = Path(graph_path)
    lock = graph_path.with_name(graph_path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
            except FileNotFoundError:
                continue  # released between the two calls: try again at once
            if age > stale_after_s or _owner_is_dead(lock):
                lock.unlink(missing_ok=True)  # stale: its owner is gone
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"gave up waiting for {lock} after {timeout_s:.0f} s")
            time.sleep(poll_s)
            continue
        with os.fdopen(fd, "w") as f:
            f.write(f"{os.getpid()} {socket.gethostname()} {time.time():.0f}\n")
        break
    try:
        yield lock
    finally:
        lock.unlink(missing_ok=True)
