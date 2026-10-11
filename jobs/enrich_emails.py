#!/usr/bin/env python3
"""Enrich prospects.csv with publicly listed professional emails.

Default remains a no-op. To use the no-API public-web scraper:

    export ENRICHER=web
    python -m jobs.enrich_emails

The scraper searches public search-result pages, visits public practice
websites, and records the source URL and heuristic confidence. Existing emails
are never overwritten.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core.enrichment import get_enricher
from core.logging_setup import get_logger
from core.models import Prospect
from core.repository import _LockedFile

log = get_logger("enrich_emails")


def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--"
    seconds = int(round(seconds))
    minutes, secs = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def _print_progress(index: int, total: int, stats: dict[str, int], started: float) -> None:
    import time

    elapsed = time.monotonic() - started
    rate = index / elapsed if elapsed > 0 else 0
    eta = (total - index) / rate if rate > 0 else None
    pct = (index / total * 100) if total else 100.0
    # Keep the display compact and overwrite it in-place.
    lines = [
        f"[{index}/{total}] {pct:5.1f}%",
        f"Found: {stats['found']}",
        f"Unverified: {stats['unverified']}",
        f"Not found: {stats['not_found']}",
        f"Rate limited: {stats['rate_limited']}",
        f"Errors: {stats['error']}",
        f"ETA: {_format_eta(eta)}",
    ]
    # ANSI cursor-up works in Terminal, VS Code, iTerm, etc.
    if index > 1:
        print(f"\033[{len(lines)}A", end="")
    print("\n".join(lines))


def main() -> None:
    import time

    enricher = get_enricher()
    log.info("Using enricher: %s", type(enricher).__name__)

    with _LockedFile(config.PROSPECTS_FILE, "r") as fh:
        rows = list(csv.DictReader(fh))

    total = len(rows)
    updated = 0
    stats = {
        "found": 0,
        "unverified": 0,
        "not_found": 0,
        "rate_limited": 0,
        "error": 0,
    }
    started = time.monotonic()

    # Reserve the display area before the first update.
    print()
    for index, row in enumerate(rows, start=1):
        if row.get("email"):
            stats["found"] += 1
            _print_progress(index, total, stats, started)
            continue

        try:
            p = Prospect(**{k: row.get(k, "") for k in Prospect.fieldnames()})
            result = enricher.find_email(p)
            status = getattr(result, "status", "error") or "error"
            if status not in stats:
                status = "error"
            stats[status] += 1

            row["email_status"] = status
            row["email_source"] = getattr(result, "source", "")
            row["email_confidence"] = str(getattr(result, "confidence", 0) or "")

            if result.email:
                row["email"] = result.email
                # Re-key so email-based identity/dedup stays consistent.
                row["dedup_key"] = Prospect(
                    **{k: row.get(k, "") for k in Prospect.fieldnames() if k != "dedup_key"}
                ).dedup_key
                updated += 1
        except Exception:
            stats["error"] += 1
            row["email_status"] = "error"
            log.exception("Unexpected enrichment error for row %d", index)

        _print_progress(index, total, stats, started)

    with _LockedFile(config.PROSPECTS_FILE, "w") as fh:
        writer = csv.DictWriter(fh, fieldnames=Prospect.fieldnames())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nEnrichment complete. {updated} emails added.")


if __name__ == "__main__":
    main()
