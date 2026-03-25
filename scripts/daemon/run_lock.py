#!/usr/bin/env python3
"""Global whipper run lock shared by daemon and scheduler."""
import fcntl
import threading
from pathlib import Path

LOCK_PATH = Path.home() / ".claude" / "whipper-logs" / "run.lock"
THREAD_LOCK = threading.Lock()


def acquire_run_lock(blocking: bool = True):
    if not THREAD_LOCK.acquire(blocking=blocking):
        return None

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("w")
    flags = fcntl.LOCK_EX
    if not blocking:
        flags |= fcntl.LOCK_NB
    try:
        fcntl.flock(handle.fileno(), flags)
        return handle
    except BlockingIOError:
        handle.close()
        THREAD_LOCK.release()
        return None


def release_run_lock(handle) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
        THREAD_LOCK.release()
