#!/usr/bin/env python3
"""
Job 1: fetch prospects from NPPES (+ CMS enrollment join) and append (deduped)
to the flat file. Records per-state status so the UI can track progress.

Idempotent -- re-running only ever adds genuinely new rows.

Usage:
    python -m jobs.fetch_prospects                 # all TARGET_STATES
    python -m jobs.fetch_prospects --all           # all 50 states + DC + terr.
    python -m jobs.fetch_prospects TX CA NY        # only these states
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, state_status
from core.cms_source import annotate_with_enrollment, build_enrollment_index
from core.logging_setup import get_logger
from core.nppes_source import fetch_state
from core.repository import ProspectRepository

log = get_logger("fetch_prospects")


def fetch_one_state(
    state: str,
    repo: ProspectRepository | None = None,
    taxonomy: str | None = None,
    categories: list[str] | None = None,
) -> dict:
    """Fetch a single state end-to-end. Returns a small result dict.

    This is the function the UI backend calls. It updates the state-status
    tracker as it goes. `categories` (keys of config.PROSPECT_CATEGORIES) are
    fetched one after another; without them, `taxonomy` (None = use config
    global; "" = no filter) is used as a single free-text search.
    """
    state = state.strip().upper()
    repo = repo or ProspectRepository()

    if state not in config.ALL_STATES:
        raise ValueError(f"Unknown state code: {state!r}")

    state_status.mark(state, "running")
    try:
        # 1) Primary source: NPPES (name, address, phone, specialty, ...).
        prospects = []
        if categories:
            for cat in categories:
                spec = config.PROSPECT_CATEGORIES[cat]
                log.info("Fetching %s for category %r", state, cat)
                prospects.extend(fetch_state(state, taxonomy=spec["query"],
                                             codes=spec["codes"], category=cat))
        else:
            log.info("Fetching %s with taxonomy=%r", state,
                     config.NPPES_TAXONOMY if taxonomy is None else taxonomy)
            prospects = list(fetch_state(state, taxonomy=taxonomy))

        # 2) Second source: CMS Medicare enrollment, joined by NPI.
        if config.CMS_ENRICH_ENABLED:
            enroll_index = build_enrollment_index(state)
            prospects = list(annotate_with_enrollment(prospects, enroll_index))

        # 3) Append with dedup.
        added = repo.upsert_many(prospects)
        log.info("State %s: %d new prospects appended.", state, added)
        entry = state_status.mark(state, "done", count=added)
        return {"state": state, "added": added, "fetched": len(prospects), **entry}
    except Exception as exc:  # noqa: BLE001 - report to UI, keep others running
        log.exception("State %s failed", state)
        state_status.mark(state, "error", error=str(exc))
        return {"state": state, "added": 0, "error": str(exc)}


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]

    if "--all" in argv:
        states = list(config.ALL_STATES)
    else:
        positional = [a for a in argv if not a.startswith("-")]
        states = positional or [s.strip().upper() for s in config.TARGET_STATES if s.strip()]

    repo = ProspectRepository()
    total_new = 0
    for state in states:
        result = fetch_one_state(state, repo)
        total_new += result.get("added", 0)
    log.info("Done. %d new prospects total.", total_new)


if __name__ == "__main__":
    main()
