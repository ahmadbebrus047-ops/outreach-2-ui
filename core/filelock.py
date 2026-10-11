"""
Cross-platform advisory file locking.

The project was originally written for Unix (fcntl). Windows has no fcntl, so
this module provides lock_exclusive / lock_shared / unlock that work on both:

  * POSIX (macOS, Linux): fcntl.flock
  * Windows:              msvcrt.locking

Locks are best-effort/advisory and only meant to keep the cron + web jobs from
corrupting the CSVs when they run at the same time. If locking is unavailable
for any reason, the code degrades to "no lock" rather than crashing.
"""
from __future__ import annotations

import os

_PLATFORM = "posix" if os.name == "posix" else ("nt" if os.name == "nt" else "other")

if _PLATFORM == "posix":
    import fcntl

    def lock_exclusive(fh) -> None:
        fcntl.flock(fh, fcntl.LOCK_EX)

    def lock_shared(fh) -> None:
        fcntl.flock(fh, fcntl.LOCK_SH)

    def unlock(fh) -> None:
        fcntl.flock(fh, fcntl.LOCK_UN)

elif _PLATFORM == "nt":
    import msvcrt

    # msvcrt locks a byte range; we lock a single byte from the start, which is
    # enough to serialize writers. Shared/exclusive both map to the same lock
    # here (Windows msvcrt has no shared mode), which is safe if conservative.
    _LOCK_BYTES = 1

    def _lock(fh) -> None:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, _LOCK_BYTES)
        except OSError:
            # Empty file or already-locked edge cases: don't crash the job.
            pass

    def lock_exclusive(fh) -> None:
        _lock(fh)

    def lock_shared(fh) -> None:
        _lock(fh)

    def unlock(fh) -> None:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, _LOCK_BYTES)
        except OSError:
            pass

else:  # unknown platform: no-op locks

    def lock_exclusive(fh) -> None:  # noqa: D401
        pass

    def lock_shared(fh) -> None:
        pass

    def unlock(fh) -> None:
        pass
