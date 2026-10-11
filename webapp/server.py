#!/usr/bin/env python3
"""
Web GUI backend for the outreach pipeline (steps 1 & 2).

Step 1 - Fetch prospects from NPPES/CMS, one state at a time, with a live
         done/remaining tracker.
Step 2 - Select rows from the CSV and fetch their emails through Apollo,
         showing three tables: fetched / not fetched / not available.

Run:
    export APOLLO_API_KEY=...            # required for step 2
    export NPPES_TAXONOMY="Family Medicine"   # optional, see /api/taxonomy-hints
    python -m webapp.server
    # open http://127.0.0.1:5000
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, Response, jsonify, request, send_from_directory

from core import apollo_enrich, config, state_status
from core.logging_setup import get_logger
from jobs.fetch_prospects import fetch_one_state

log = get_logger("webapp")

app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"))

# Track in-flight fetches so the UI can poll and we never run the same state
# twice concurrently.
_fetch_lock = threading.Lock()
_running_states: set[str] = set()

# On startup, clear any state left "running" by a previous killed/crashed run --
# there's no thread for it anymore, so leaving it stuck would make it
# un-selectable in the UI.
_stale = state_status.reset_stale_running()
if _stale:
    log.info("Reset %d stale running state(s) on startup: %s", len(_stale), ", ".join(_stale))

# Bring prospects.csv up to the current column set before anything appends.
from core.repository import ProspectRepository
ProspectRepository()

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


@app.before_request
def _local_only():
    """When a public tunnel forwards to this app (for Apollo phone webhooks),
    expose only the secret webhook path -- never the console or its API,
    which would let anyone spend Apollo credits."""
    host = request.host.rsplit(":", 1)[0].lower()
    if host in _LOCAL_HOSTS:
        return None
    if request.path == f"/api/apollo-webhook/{config.APOLLO_WEBHOOK_SECRET}":
        return None
    return Response("Not found", status=404)


@app.route("/api/apollo-webhook/<secret>", methods=["POST"])
def api_apollo_webhook(secret: str):
    """Apollo posts revealed phone numbers here, some time after bulk_match."""
    if secret != config.APOLLO_WEBHOOK_SECRET:
        return Response("Not found", status=404)
    payload = request.get_json(silent=True)
    log.info("Apollo webhook body: %s", str(payload)[:2000])
    n = apollo_enrich.queue_phone_webhook(payload or {})
    return jsonify({"ok": True, "people": n})


# Comprehensive taxonomy_description values the user can pick in the UI.
# NPPES matches these EXACTLY (case + spelling), so the UI offers them as a
# picklist. Blank means "all taxonomies". See core/taxonomy_list.py.
from core.taxonomy_list import TAXONOMY_DESCRIPTIONS as TAXONOMY_HINTS


# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Config / metadata
# ---------------------------------------------------------------------------
@app.route("/api/config")
def api_config():
    return jsonify(
        {
            "apollo_key_set": bool(config.APOLLO_API_KEY),
            "nppes_taxonomy": config.NPPES_TAXONOMY,
            "nppes_max_per_state": config.NPPES_MAX_PER_STATE,
            "cms_enrich_enabled": config.CMS_ENRICH_ENABLED,
            "apollo_bulk_size": config.APOLLO_BULK_SIZE,
            "prospect_categories": list(config.PROSPECT_CATEGORIES),
            "phone_ready": bool(config.APOLLO_PHONE_WEBHOOK_BASE),
        }
    )


@app.route("/api/taxonomy-hints")
def api_taxonomy_hints():
    """Values the user can enter in the taxonomy box (like NPPES_TAXONOMY="")."""
    return jsonify({"hints": TAXONOMY_HINTS, "current": config.NPPES_TAXONOMY})


@app.route("/api/taxonomy", methods=["POST"])
def api_set_taxonomy():
    """Set the taxonomy filter used for subsequent fetches (in-process)."""
    data = request.get_json(silent=True) or {}
    # Trim whitespace -- a trailing space is a common cause of 0 matches.
    value = str(data.get("taxonomy", "")).strip()
    config.NPPES_TAXONOMY = value
    log.info("NPPES_TAXONOMY set to %r", value)
    return jsonify({"ok": True, "nppes_taxonomy": config.NPPES_TAXONOMY})


@app.route("/api/probe")
def api_probe():
    """Cheap check that a state+taxonomy combo will actually return rows.
    Used by the UI to warn before a full fetch. Query params: state, taxonomy."""
    from core.nppes_source import probe

    state = request.args.get("state", "").strip().upper()
    if state not in config.ALL_STATES:
        return jsonify({"ok": False, "error": f"Unknown state: {state!r}"}), 400
    taxonomy = request.args.get("taxonomy", None)
    result = probe(state, taxonomy)
    result["ok"] = True
    return jsonify(result)


# ---------------------------------------------------------------------------
# Step 1 - states
# ---------------------------------------------------------------------------
@app.route("/api/states")
def api_states():
    s = state_status.summary()
    with _fetch_lock:
        for st in s["states"]:
            if st["code"] in _running_states:
                st["status"] = "running"
    s["running"] = sorted(_running_states)
    return jsonify(s)


def _run_fetch(state: str, taxonomy: str | None = None,
               categories: list[str] | None = None) -> None:
    try:
        fetch_one_state(state, taxonomy=taxonomy, categories=categories)
    finally:
        with _fetch_lock:
            _running_states.discard(state)


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    """Kick off a background fetch for one or more states."""
    data = request.get_json(silent=True) or {}
    states = data.get("states")
    if isinstance(states, str):
        states = [states]
    if not states:
        one = data.get("state")
        states = [one] if one else []

    states = [str(s).strip().upper() for s in states if str(s).strip()]
    invalid = [s for s in states if s not in config.ALL_STATES]
    if invalid:
        return jsonify({"ok": False, "error": f"Unknown states: {invalid}"}), 400

    categories = [str(c) for c in (data.get("categories") or [])]
    unknown = [c for c in categories if c not in config.PROSPECT_CATEGORIES]
    if unknown:
        return jsonify({"ok": False, "error": f"Unknown categories: {unknown}"}), 400

    # The UI sends the taxonomy box value with every fetch, so it is the single
    # source of truth. If the key is absent (e.g. CLI/other callers), fall back
    # to the current global. Also keep the global in sync for /api/config etc.
    if categories:
        taxonomy = None
    elif "taxonomy" in data:
        taxonomy = str(data.get("taxonomy") or "").strip()
        config.NPPES_TAXONOMY = taxonomy
    else:
        taxonomy = config.NPPES_TAXONOMY

    started, skipped = [], []
    with _fetch_lock:
        for st in states:
            if st in _running_states:
                skipped.append(st)
                continue
            _running_states.add(st)
            started.append(st)
            state_status.mark(st, "running")

    for st in started:
        threading.Thread(target=_run_fetch, args=(st, taxonomy, categories), daemon=True).start()

    return jsonify({"ok": True, "started": started, "already_running": skipped,
                    "taxonomy": taxonomy, "categories": categories})


# ---------------------------------------------------------------------------
# Step 2 - rows + Apollo enrichment
# ---------------------------------------------------------------------------
@app.route("/api/rows")
def api_rows():
    rows = apollo_enrich.list_rows(
        search=request.args.get("search", ""),
        bucket=request.args.get("bucket", ""),
        state=request.args.get("state", ""),
        only_missing=request.args.get("only_missing", "") in ("1", "true", "yes"),
        category=request.args.get("category", ""),
    )
    limit = int(request.args.get("limit", "500"))
    return jsonify(
        {
            "rows": rows[:limit],
            "returned": min(len(rows), limit),
            "total_matching": len(rows),
            "summary": apollo_enrich.summary(),
        }
    )


@app.route("/api/rows/summary")
def api_rows_summary():
    return jsonify(apollo_enrich.summary())


@app.route("/api/categories")
def api_categories():
    return jsonify({"categories": apollo_enrich.summary_by_category(),
                    "summary": apollo_enrich.summary()})


@app.route("/api/export")
def api_export():
    """Download found emails as CSV, optionally for one category."""
    import csv
    import io

    rows = apollo_enrich.list_rows(bucket="fetched", category=request.args.get("category", ""))
    cols = ["name", "contact_name", "contact_title", "email", "contact_phone", "category",
            "taxonomy", "city", "state", "phone", "npi"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    slug = (request.args.get("category") or "all").lower().replace(" ", "-").replace("/", "-")
    return Response(buf.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="emails-{slug}.csv"'})


@app.route("/api/enrich", methods=["POST"])
def api_enrich():
    data = request.get_json(silent=True) or {}
    indices = data.get("indices", [])
    if not isinstance(indices, list):
        return jsonify({"ok": False, "error": "indices must be a list"}), 400
    try:
        want_phone = bool(data.get("want_phone")) and bool(config.APOLLO_PHONE_WEBHOOK_BASE)
        result = apollo_enrich.enrich_selected_rows(indices, want_phone=want_phone)
    except Exception as exc:  # noqa: BLE001
        log.exception("Enrichment failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
    result["ok"] = True
    result["apollo_key_set"] = bool(config.APOLLO_API_KEY)
    result["summary"] = apollo_enrich.summary()
    return jsonify(result)


def main() -> None:
    import os

    host = os.getenv("WEBAPP_HOST", "127.0.0.1")
    port = int(os.getenv("WEBAPP_PORT", "5000"))
    log.info("Starting web GUI on http://%s:%s", host, port)
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
