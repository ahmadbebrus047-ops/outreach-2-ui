"""
Campaign logic: decide who to email today and dispatch.

Rules encoded here:
  * Only prospects with a non-empty email are eligible.
  * Never contact anyone on the suppression list.
  * Reminders (to already-emailed prospects whose last send was >= N days ago,
    up to MAX_REMINDERS) take priority over new sends.
  * New prospects fill the rest of the daily quota.
  * Both flows respect the same daily limit so we never over-send.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from core import config, templates
from core.logging_setup import get_logger
from core.repository import (
    ProspectRepository,
    SentLogRepository,
    SuppressionRepository,
)

log = get_logger("campaign")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


class Campaign:
    def __init__(self, mailer):
        self.mailer = mailer
        self.prospects = ProspectRepository()
        self.sent = SentLogRepository()
        self.suppression = SuppressionRepository()

    # -- selection ----------------------------------------------------------
    def _eligible_prospects(self) -> dict[str, dict]:
        out = {}
        for row in self.prospects.all():
            email = (row.get("email") or "").strip()
            key = row.get("dedup_key", "")
            if not email or not key:
                continue
            if self.suppression.is_suppressed(key, email):
                continue
            out[key] = row
        return out

    def _due_for_reminder(self, sent_rec: dict) -> bool:
        count = int(sent_rec.get("send_count", "0"))
        if count == 0 or count > config.MAX_REMINDERS:
            return False
        last = _parse(sent_rec["last_sent_at"])
        due = datetime.now(timezone.utc) - timedelta(days=config.REMINDER_AFTER_DAYS)
        return last <= due

    def _build_queue(self) -> list[tuple[dict, bool]]:
        """Return list of (prospect_row, is_reminder), reminders first."""
        eligible = self._eligible_prospects()
        sent_by_key = {r["dedup_key"]: r for r in self.sent.all()}

        reminders, fresh = [], []
        for key, row in eligible.items():
            rec = sent_by_key.get(key)
            if rec is None:
                fresh.append((row, False))
            elif self._due_for_reminder(rec):
                reminders.append((row, True))
            # else: already contacted and not yet due -> skip

        queue = reminders + fresh
        return queue[: config.DAILY_SEND_LIMIT]

    # -- dispatch -----------------------------------------------------------
    def run(self) -> None:
        queue = self._build_queue()
        if not queue:
            log.info("Nothing to send today.")
            return

        log.info("Queued %d messages (limit %d).", len(queue), config.DAILY_SEND_LIMIT)
        for row, is_reminder in queue:
            subject, body = (
                templates.reminder_email(row) if is_reminder
                else templates.initial_email(row)
            )
            ok = self.mailer.send(row["email"], subject, body)
            if ok:
                self.sent.record_send(row["dedup_key"], row["email"])
            time.sleep(config.SEND_PAUSE_SECONDS)
        log.info("Campaign run complete.")
