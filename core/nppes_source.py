"""
Prospect source backed by the NPPES NPI Registry public API.

Why not Selenium: NPPES is the authoritative, free, ToS-friendly source for
US provider name / address / phone, queryable by state. It returns clean JSON,
so there's nothing to scrape and nothing to get blocked for. It does NOT
provide email addresses (no legitimate bulk source does) -- the `email` field
is left blank for you to populate.
"""
from __future__ import annotations

import time
from typing import Iterator

import requests

from core import config
from core.logging_setup import get_logger
from core.models import Prospect

log = get_logger("nppes_source")


def _addresses(result: dict) -> tuple[dict, dict]:
    """Return (location_address, mailing_address)."""
    loc, mail = {}, {}
    for addr in result.get("addresses", []):
        if addr.get("address_purpose") == "LOCATION":
            loc = addr
        elif addr.get("address_purpose") == "MAILING":
            mail = addr
    if not loc:
        loc = (result.get("addresses") or [{}])[0]
    return loc, mail


def _primary_taxonomy(result: dict) -> dict:
    taxes = result.get("taxonomies", []) or []
    for t in taxes:
        if t.get("primary"):
            return t
    return taxes[0] if taxes else {}


def _fmt_addr(addr: dict) -> str:
    return " ".join(
        x for x in [addr.get("address_1", ""), addr.get("address_2", "")] if x
    ).strip()


def _display_name(result: dict) -> str:
    basic = result.get("basic", {})
    if result.get("enumeration_type") == "NPI-2":  # organization
        return basic.get("organization_name", "").strip()
    parts = [basic.get("first_name", ""), basic.get("last_name", "")]
    return " ".join(p for p in parts if p).strip()


def _fetch_page(state: str, skip: int, taxonomy: str | None = None) -> list[dict]:
    tax = config.NPPES_TAXONOMY if taxonomy is None else taxonomy
    params = {
        "version": config.NPPES_API_VERSION,
        "state": state,
        "country_code": "US",
        "limit": config.NPPES_PAGE_SIZE,
        "skip": skip,
    }
    if tax:
        params["taxonomy_description"] = tax
    resp = requests.get(config.NPPES_API_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", []) or []


def _count_for(state: str, taxonomy: str | None) -> int:
    p = {
        "version": config.NPPES_API_VERSION,
        "state": state,
        "country_code": "US",
        "limit": 1,
        "skip": 0,
    }
    if taxonomy:
        p["taxonomy_description"] = taxonomy
    r = requests.get(config.NPPES_API_URL, params=p, timeout=30)
    r.raise_for_status()
    return r.json().get("result_count", 0) or 0


def probe(state: str, taxonomy: str | None = None) -> dict:
    """Cheap 1-row query used to sanity-check a state / taxonomy combo before a
    full fetch. Returns {reachable, count_with_filter, count_without_filter,
    taxonomy, suggested, warning}.

    If the given taxonomy matches 0 but a different casing does match, `suggested`
    holds the casing that works, so the UI can offer to use it. This makes the
    tool robust whether NPPES treats the description as case-sensitive or not.
    """
    tax = config.NPPES_TAXONOMY if taxonomy is None else taxonomy
    out = {
        "reachable": False,
        "count_with_filter": 0,
        "count_without_filter": 0,
        "taxonomy": tax,
        "suggested": "",
        "warning": "",
    }
    try:
        out["count_with_filter"] = _count_for(state, tax) if tax else _count_for(state, None)
        out["reachable"] = True

        if tax and out["count_with_filter"] == 0:
            # See if the state has anyone at all.
            out["count_without_filter"] = _count_for(state, None)

            # Try common casing variants to find one NPPES accepts.
            variants = [tax.title(), tax.upper(), tax.lower(),
                        tax.capitalize()]
            seen = {tax}
            for v in variants:
                if v in seen:
                    continue
                seen.add(v)
                try:
                    if _count_for(state, v) > 0:
                        out["suggested"] = v
                        break
                except requests.RequestException:
                    continue

            if out["suggested"]:
                out["warning"] = (
                    f"Taxonomy {tax!r} matched 0 in {state}, but {out['suggested']!r} "
                    f"works. Use that spelling instead."
                )
            elif out["count_without_filter"] > 0:
                out["warning"] = (
                    f"Taxonomy {tax!r} matched 0 providers in {state}, though the "
                    f"state has providers without any filter. Check spelling, pick a "
                    f"value from the dropdown, or clear the filter."
                )
        else:
            out["count_without_filter"] = out["count_with_filter"]
    except requests.RequestException as exc:
        out["warning"] = f"Could not reach NPPES: {exc}"
    return out



def _has_code(result: dict, codes: list[str]) -> bool:
    for t in result.get("taxonomies", []) or []:
        code = t.get("code", "")
        for want in codes:
            if (want.endswith("*") and code.startswith(want[:-1])) or code == want:
                return True
    return False


def fetch_state(
    state: str,
    taxonomy: str | None = None,
    codes: list[str] | None = None,
    category: str = "",
) -> Iterator[Prospect]:
    """Yield Prospect objects for a single state, paging through results.

    `taxonomy` overrides config.NPPES_TAXONOMY for this call when provided
    (None = use the global; "" = explicitly no filter). `codes`, if given,
    keeps only providers holding one of those taxonomy codes, and `category`
    is stamped on every yielded row.
    """
    tax_filter = config.NPPES_TAXONOMY if taxonomy is None else taxonomy
    fetched = 0
    skip = 0
    # NPPES caps skip at 1000; loop respects both that and our own cap.
    while fetched < config.NPPES_MAX_PER_STATE and skip <= 1000:
        try:
            results = _fetch_page(state, skip, taxonomy=tax_filter)
        except requests.RequestException as exc:
            log.warning("NPPES request failed (state=%s skip=%s): %s", state, skip, exc)
            break
        if not results:
            break

        for r in results:
            if codes and not _has_code(r, codes):
                continue
            loc, mail = _addresses(r)
            basic = r.get("basic", {})
            tax = _primary_taxonomy(r)
            entity = "organization" if r.get("enumeration_type") == "NPI-2" else "individual"
            yield Prospect(
                npi=str(r.get("number", "")),
                name=_display_name(r),
                email="",  # populated later by enrichment, never scraped
                phone=loc.get("telephone_number", ""),
                fax=loc.get("fax_number", ""),
                address=_fmt_addr(loc),
                city=loc.get("city", ""),
                state=loc.get("state", ""),
                postal_code=loc.get("postal_code", "")[:5],
                entity_type=entity,
                credential=basic.get("credential", ""),
                taxonomy=tax.get("desc", ""),
                taxonomy_code=tax.get("code", ""),
                sole_proprietor=basic.get("sole_proprietor", ""),
                mailing_address=_fmt_addr(mail),
                source="nppes",
                category=category,
            )
            fetched += 1

        skip += config.NPPES_PAGE_SIZE
        time.sleep(config.NPPES_REQUEST_PAUSE)

    log.info("Fetched %d prospects for %s", fetched, state)
