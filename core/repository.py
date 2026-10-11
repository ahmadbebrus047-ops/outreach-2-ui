"""
Flat-file (CSV) persistence layer.

Design: a thin Repository per file. Callers never touch CSV directly, so the
dedup/append/suppression invariants live in exactly one place. Swapping CSV
for SQLite later means changing only this module.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from core import config
from core import filelock
from core.models import Prospect


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class _LockedFile:
    """Context manager giving an exclusive OS-level lock (cron-safe)."""

    def __init__(self, path: Path, mode: str):
        self.path = path
        self.mode = mode
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, self.mode, newline="")
        filelock.lock_exclusive(self.fh)
        return self.fh

    def __exit__(self, *exc):
        filelock.unlock(self.fh)
        self.fh.close()


class ProspectRepository:
    """Append-only, deduplicated store of prospects."""

    def __init__(self, path: Path = config.PROSPECTS_FILE):
        self.path = path
        if not self.path.exists():
            with _LockedFile(self.path, "w") as fh:
                csv.DictWriter(fh, fieldnames=Prospect.fieldnames()).writeheader()
        else:
            self._migrate_header()

    def _migrate_header(self) -> None:
        """Rewrite the CSV under the current columns if new fields were added,
        so appended rows don't land in columns the header doesn't name."""
        fields = Prospect.fieldnames()
        with _LockedFile(self.path, "r") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames == fields:
                return
            rows = list(reader)
        with _LockedFile(self.path, "w") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def _existing_keys(self) -> set[str]:
        keys: set[str] = set()
        with _LockedFile(self.path, "r") as fh:
            for row in csv.DictReader(fh):
                if row.get("dedup_key"):
                    keys.add(row["dedup_key"])
        return keys

    def all(self) -> Iterator[dict]:
        with _LockedFile(self.path, "r") as fh:
            yield from csv.DictReader(fh)

    def upsert_many(self, prospects: Iterable[Prospect]) -> int:
        """Append only prospects whose dedup_key isn't already present.
        Returns the count of newly written rows."""
        known = self._existing_keys()
        suppressed = SuppressionRepository().all_keys()
        new_rows = []
        seen_this_batch: set[str] = set()
        for p in prospects:
            key = p.dedup_key
            if key in known or key in seen_this_batch or key in suppressed:
                continue
            seen_this_batch.add(key)
            new_rows.append(p.to_row())

        if not new_rows:
            return 0

        with _LockedFile(self.path, "a") as fh:
            writer = csv.DictWriter(fh, fieldnames=Prospect.fieldnames())
            writer.writerows(new_rows)
        return len(new_rows)


class SentLogRepository:
    """Records every send so we never repeat and can schedule reminders."""

    FIELDS = ["dedup_key", "email", "first_sent_at", "last_sent_at", "send_count"]

    def __init__(self, path: Path = config.SENT_LOG_FILE):
        self.path = path
        if not self.path.exists():
            with _LockedFile(self.path, "w") as fh:
                csv.DictWriter(fh, fieldnames=self.FIELDS).writeheader()

    def _load(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        with _LockedFile(self.path, "r") as fh:
            for row in csv.DictReader(fh):
                out[row["dedup_key"]] = row
        return out

    def _rewrite(self, records: dict[str, dict]) -> None:
        with _LockedFile(self.path, "w") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.FIELDS)
            writer.writeheader()
            writer.writerows(records.values())

    def get(self, dedup_key: str) -> dict | None:
        return self._load().get(dedup_key)

    def record_send(self, dedup_key: str, email: str) -> None:
        records = self._load()
        now = _utcnow()
        if dedup_key in records:
            rec = records[dedup_key]
            rec["last_sent_at"] = now
            rec["send_count"] = str(int(rec.get("send_count", "0")) + 1)
        else:
            records[dedup_key] = {
                "dedup_key": dedup_key,
                "email": email,
                "first_sent_at": now,
                "last_sent_at": now,
                "send_count": "1",
            }
        self._rewrite(records)

    def all(self) -> list[dict]:
        return list(self._load().values())


class SuppressionRepository:
    """Opt-outs and hard bounces. Checked before every send and every upsert."""

    FIELDS = ["dedup_key", "email", "reason", "added_at"]

    def __init__(self, path: Path = config.SUPPRESSION_FILE):
        self.path = path
        if not self.path.exists():
            with _LockedFile(self.path, "w") as fh:
                csv.DictWriter(fh, fieldnames=self.FIELDS).writeheader()

    def all_keys(self) -> set[str]:
        keys: set[str] = set()
        with _LockedFile(self.path, "r") as fh:
            for row in csv.DictReader(fh):
                if row.get("dedup_key"):
                    keys.add(row["dedup_key"])
                if row.get("email"):
                    keys.add("email:" + row["email"].lower())
        return keys

    def is_suppressed(self, dedup_key: str, email: str = "") -> bool:
        keys = self.all_keys()
        return dedup_key in keys or ("email:" + email.lower()) in keys

    def add(self, dedup_key: str, email: str, reason: str) -> None:
        with _LockedFile(self.path, "a") as fh:
            csv.DictWriter(fh, fieldnames=self.FIELDS).writerow(
                {"dedup_key": dedup_key, "email": email,
                 "reason": reason, "added_at": _utcnow()}
            )
