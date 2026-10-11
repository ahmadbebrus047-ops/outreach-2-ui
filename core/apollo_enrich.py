"""
Selective Apollo enrichment for the UI.

The UI shows the prospects CSV, lets the user select specific rows, and calls
`enrich_selected_rows(...)`. That function:

  1. loads the CSV,
  2. builds Prospect objects for the selected row indices,
  3. calls Apollo in bulk (10 per request) to fetch emails,
  4. writes the emails + status back into the CSV (never overwriting an
     existing email),
  5. returns a three-bucket breakdown for the UI:
        - "fetched"        : an email was returned (status found/unverified)
        - "not_available"  : Apollo ran but had no email (status not_found)
        - "not_fetched"    : row not attempted yet, or an error occurred

The whole CSV read/modify/write is done under the same exclusive file lock the
rest of the project uses, so it is safe alongside the fetch job.
"""
from __future__ import annotations

import csv
import json
import threading
from typing import Iterable

from core import config
from core.enrichment import ApolloEnricher
from core.logging_setup import get_logger
from core.models import Prospect
from core.repository import _LockedFile
from core.website_finder import WebsiteFinder

log = get_logger("apollo_enrich")

# email_status values that mean "we have an email"
_HAS_EMAIL = {"found", "unverified"}


def _load_rows() -> list[dict]:
    if not config.PROSPECTS_FILE.exists():
        return []
    with _LockedFile(config.PROSPECTS_FILE, "r") as fh:
        return list(csv.DictReader(fh))


def _write_rows(rows: list[dict]) -> None:
    with _LockedFile(config.PROSPECTS_FILE, "w") as fh:
        # extrasaction: rows appended before the `website` column existed can
        # carry an unnamed trailing field; drop it rather than crash.
        writer = csv.DictWriter(fh, fieldnames=Prospect.fieldnames(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _prospect_from_row(row: dict) -> Prospect:
    return Prospect(**{k: row.get(k, "") for k in Prospect.fieldnames()})


def _bucket_for_row(row: dict) -> str:
    """Classify a row into one of the three UI buckets by its current state."""
    if row.get("email"):
        return "fetched"
    status = (row.get("email_status") or "").lower()
    if status in _HAS_EMAIL:
        return "fetched"
    if status == "not_found":
        return "not_available"
    return "not_fetched"  # "", "error", or never attempted


def category_of(row: dict) -> str:
    """The PROSPECT_CATEGORIES key for a row, or '' if it's outside them.

    Rows fetched by category carry it; older rows are mapped by their primary
    taxonomy code.
    """
    if row.get("category") in config.PROSPECT_CATEGORIES:
        return row["category"]
    code = row.get("taxonomy_code") or ""
    for name, spec in config.PROSPECT_CATEGORIES.items():
        for want in spec["codes"]:
            if (want.endswith("*") and code.startswith(want[:-1])) or code == want:
                return name
    return ""


def row_view(row: dict, index: int) -> dict:
    """A compact, UI-friendly projection of a CSV row."""
    return {
        "index": index,
        "npi": row.get("npi", ""),
        "name": row.get("name", ""),
        "entity_type": row.get("entity_type", ""),
        "category": category_of(row),
        "taxonomy": row.get("taxonomy", ""),
        "city": row.get("city", ""),
        "state": row.get("state", ""),
        "phone": row.get("phone", ""),
        "email": row.get("email", ""),
        "email_status": row.get("email_status", ""),
        "email_source": row.get("email_source", ""),
        "medicare_enrolled": row.get("medicare_enrolled", ""),
        "website": row.get("website", ""),
        "contact_name": row.get("contact_name", ""),
        "contact_title": row.get("contact_title", ""),
        "contact_phone": row.get("contact_phone", ""),
        "phone_status": row.get("phone_status", ""),
        "bucket": _bucket_for_row(row),
    }


def list_rows(
    search: str = "",
    bucket: str = "",
    state: str = "",
    only_missing: bool = False,
    category: str = "",
) -> list[dict]:
    """Return all rows as UI views, with optional filters."""
    merge_phone_inbox(wait=False)
    rows = _load_rows()
    out = []
    for i, row in enumerate(rows):
        view = row_view(row, i)
        if not view["category"]:
            continue  # outside the target categories
        if bucket and view["bucket"] != bucket:
            continue
        if category and view["category"] != category:
            continue
        if state and view["state"].upper() != state.upper():
            continue
        if only_missing and view["bucket"] == "fetched":
            continue
        if search:
            hay = " ".join(
                str(view.get(k, "")) for k in ("name", "npi", "city", "taxonomy")
            ).lower()
            if search.lower() not in hay:
                continue
        out.append(view)
    return out


def summary() -> dict:
    """Bucket counts across the target categories only."""
    counts = {"fetched": 0, "not_available": 0, "not_fetched": 0, "total": 0}
    for row in _load_rows():
        if category_of(row):
            counts[_bucket_for_row(row)] += 1
            counts["total"] += 1
    return counts


def summary_by_category() -> list[dict]:
    """Per-category bucket counts, in PROSPECT_CATEGORIES order (always all of them)."""
    cats = {
        name: {"category": name, "total": 0, "fetched": 0, "not_available": 0, "not_fetched": 0}
        for name in config.PROSPECT_CATEGORIES
    }
    for row in _load_rows():
        cat = category_of(row)
        if cat:
            cats[cat]["total"] += 1
            cats[cat][_bucket_for_row(row)] += 1
    return list(cats.values())


def _phones_by_person(payload) -> dict[str, list[str]]:
    """Pull {apollo person id: [numbers]} out of a webhook body.

    Apollo's exact webhook shape isn't pinned down in its docs, so walk the JSON
    and take any object carrying both an `id` and a `phone_numbers` list.
    """
    found: dict[str, list[str]] = {}

    def walk(node):
        if isinstance(node, dict):
            pid = node.get("id") or node.get("person_id")
            nums = node.get("phone_numbers")
            if pid and isinstance(nums, list):
                have = found.setdefault(str(pid), [])
                for n in nums:
                    v = (n.get("sanitized_number") or n.get("raw_number") or n.get("number")
                         if isinstance(n, dict) else n)
                    if v and str(v) not in have:
                        have.append(str(v))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return found


# Serializes this module's read-modify-write of prospects.csv. An enrich batch
# holds rows in memory for minutes, so a phone webhook arriving mid-batch is
# queued in PHONE_INBOX and merged in rather than written (and then clobbered).
_csv_lock = threading.Lock()
PHONE_INBOX = config.DATA_DIR / "phone_inbox.jsonl"


def queue_phone_webhook(payload) -> int:
    """Record a webhook delivery, then merge it if no batch is running.
    Returns how many people with phones the payload carried."""
    phones = _phones_by_person(payload)
    log.info("Phone webhook received: %d people with phones", len(phones))
    if phones:
        with open(PHONE_INBOX, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(phones) + "\n")
        merge_phone_inbox(wait=False)
    return len(phones)


def _drain_inbox_into(rows: list[dict]) -> int:
    """Apply queued phones to `rows` in place and empty the inbox."""
    if not PHONE_INBOX.exists():
        return 0
    # Move the inbox aside first so a delivery landing mid-drain starts a new
    # inbox instead of being deleted unread.
    taken = PHONE_INBOX.with_suffix(".processing")
    PHONE_INBOX.replace(taken)
    phones: dict[str, list[str]] = {}
    for line in taken.read_text(encoding="utf-8").splitlines():
        if line.strip():
            for pid, nums in json.loads(line).items():
                have = phones.setdefault(pid, [])
                have.extend(n for n in nums if n not in have)
    updated = 0
    for row in rows:
        nums = phones.get(row.get("apollo_id") or "")
        if nums is not None:
            row["contact_phone"] = "; ".join(nums)
            row["phone_status"] = "found" if nums else "not_found"
            updated += 1
    taken.unlink()
    return updated


def merge_phone_inbox(wait: bool = True) -> int:
    """Merge queued phones into the CSV. With wait=False, skip if a batch holds the lock."""
    if not PHONE_INBOX.exists():
        return 0
    if not _csv_lock.acquire(blocking=wait):
        return 0
    try:
        rows = _load_rows()
        updated = _drain_inbox_into(rows)
        if updated:
            _write_rows(rows)
        return updated
    finally:
        _csv_lock.release()


def enrich_selected_rows(indices: Iterable[int], want_phone: bool = False) -> dict:
    with _csv_lock:
        return _enrich_selected_rows(indices, want_phone)


def _enrich_selected_rows(indices: Iterable[int], want_phone: bool) -> dict:
    """Enrich the given row indices via Apollo and persist results.

    Returns:
        {
          "fetched":       [row_view, ...],   # got an email this run
          "not_available": [row_view, ...],   # Apollo had no email
          "not_fetched":   [row_view, ...],   # errored / skipped this run
          "credits_estimate": int,            # ~1 per email fetched
          "attempted": int,
        }
    """
    rows = _load_rows()
    n = len(rows)
    indices = sorted({int(i) for i in indices if 0 <= int(i) < n})

    result = {
        "fetched": [],
        "not_available": [],
        "not_fetched": [],
        "credits_estimate": 0,
        "attempted": 0,
    }
    if not indices:
        return result

    if not config.APOLLO_API_KEY:
        # No key configured: report every selected row as not-fetched so the UI
        # can tell the user to set APOLLO_API_KEY.
        for i in indices:
            view = row_view(rows[i], i)
            view["bucket"] = "not_fetched"
            view["note"] = "APOLLO_API_KEY not set"
            result["not_fetched"].append(view)
        result["attempted"] = len(indices)
        return result

    # Only enrich rows that don't already have an email.
    to_enrich = [i for i in indices if not rows[i].get("email")]
    already = [i for i in indices if rows[i].get("email")]

    for i in already:
        result["fetched"].append(row_view(rows[i], i))

    # Apollo can't match a bare name, so look up a practice domain first for
    # rows that don't have one yet. Saved to the CSV so it's never re-searched.
    need_site = [i for i in to_enrich if not rows[i].get("website")] if config.WEBSITE_LOOKUP else []
    if need_site:
        finder = WebsiteFinder()
        for i in need_site:
            rows[i]["website"] = finder.find(_prospect_from_row(rows[i]))

    if to_enrich:
        enricher = ApolloEnricher()
        prospects = [_prospect_from_row(rows[i]) for i in to_enrich]
        email_results = enricher.find_emails_bulk(prospects, want_phone=want_phone)

        for i, res in zip(to_enrich, email_results):
            row = rows[i]
            if res.apollo_id:
                row["apollo_id"] = res.apollo_id
            if res.phone_requested:
                row["phone_status"] = "pending"
                row["contact_name"] = row.get("contact_name") or res.contact_name
                row["contact_title"] = row.get("contact_title") or res.contact_title
            row["email_status"] = res.status
            row["email_source"] = res.source or "apollo"
            row["email_confidence"] = str(res.confidence or "")
            if res.email:
                row["email"] = res.email
                row["contact_name"] = res.contact_name
                row["contact_title"] = res.contact_title
                # Re-key so email-based identity/dedup stays consistent.
                row["dedup_key"] = Prospect(
                    **{
                        k: row.get(k, "")
                        for k in Prospect.fieldnames()
                        if k != "dedup_key"
                    }
                ).dedup_key

            view = row_view(row, i)
            if res.email:
                result["fetched"].append(view)
                result["credits_estimate"] += 1
            elif res.status == "not_found":
                result["not_available"].append(view)
            else:  # error
                view["note"] = res.source or "Apollo error"
                result["not_fetched"].append(view)

    result["attempted"] = len(indices)
    _drain_inbox_into(rows)  # phones that arrived while this batch ran
    _write_rows(rows)
    log.info(
        "Apollo enrich: %d attempted, %d fetched, %d unavailable, %d not-fetched",
        result["attempted"],
        len(result["fetched"]),
        len(result["not_available"]),
        len(result["not_fetched"]),
    )
    return result
