"""
Per-state fetch tracking so the UI can show which states are done and which
are left. Backed by a small JSON file (data/state_status.json).

Shape:
{
  "TX": {"status": "done", "count": 1000, "fetched_at": "2026-09-15T08:50:55Z"},
  "CA": {"status": "error", "count": 0,  "fetched_at": "...", "error": "..."},
  ...
}
Only states that have been attempted appear. Everything else is "pending".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core import config
from core import filelock


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r") as fh:
        filelock.lock_shared(fh)
        try:
            data = fh.read().strip()
        finally:
            filelock.unlock(fh)
    if not data:
        return {}
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        filelock.lock_exclusive(fh)
        try:
            json.dump(data, fh, indent=2)
        finally:
            filelock.unlock(fh)


def load(path: Path = config.STATE_STATUS_FILE) -> dict:
    return _read(path)


def mark(
    state: str,
    status: str,
    count: int = 0,
    error: str = "",
    path: Path = config.STATE_STATUS_FILE,
) -> dict:
    """Record the outcome of a state fetch. `status` in
    {"running", "done", "error"}."""
    state = state.strip().upper()
    data = _read(path)
    entry = data.get(state, {})
    entry.update(
        {
            "status": status,
            "count": count if count else entry.get("count", 0),
            "fetched_at": _utcnow(),
        }
    )
    if error:
        entry["error"] = error
    elif "error" in entry and status != "error":
        entry.pop("error", None)
    data[state] = entry
    _write(path, data)
    return entry


def reset_stale_running(path: Path = config.STATE_STATUS_FILE) -> list[str]:
    """Clear any state stuck in "running" from a previous crashed/killed run.

    Called on server startup. If a state was mid-fetch when the process died,
    its status was never reset, which would leave it un-selectable. There's no
    thread running it anymore, so we reset it: to "done" if it actually managed
    to store rows, otherwise back to "pending".

    Returns the list of state codes that were reset.
    """
    data = _read(path)
    reset: list[str] = []
    changed = False
    for code, entry in data.items():
        if entry.get("status") == "running":
            entry["status"] = "done" if entry.get("count", 0) else "pending"
            entry["fetched_at"] = _utcnow()
            entry.pop("error", None)
            reset.append(code)
            changed = True
    if changed:
        _write(path, data)
    return reset


def summary(path: Path = config.STATE_STATUS_FILE) -> dict:
    """Return a UI-friendly view of every known state and its status."""
    data = _read(path)
    out = []
    for code in config.ALL_STATES:
        entry = data.get(code, {})
        out.append(
            {
                "code": code,
                "name": config.STATE_NAMES.get(code, code),
                "status": entry.get("status", "pending"),
                "count": entry.get("count", 0),
                "fetched_at": entry.get("fetched_at", ""),
                "error": entry.get("error", ""),
            }
        )
    done = [s for s in out if s["status"] == "done"]
    return {
        "states": out,
        "total_states": len(out),
        "done_states": len(done),
        "pending_states": len([s for s in out if s["status"] == "pending"]),
        "total_prospects": sum(s["count"] for s in out),
    }
