"""
Second public data source: CMS data.cms.gov "Medicare Fee-For-Service Public
Provider Enrollment" dataset. Keyless JSON REST API, filterable by state and
provider type.

We use it as an ENRICHMENT join, not a primary list: after NPPES gives us
prospects, we look up each NPI here to learn (a) whether the provider is
actively enrolled to bill Medicare and (b) the CMS provider-type description.
Both are strong qualifiers for a medical-billing pitch.

Docs: https://data.cms.gov/api-docs
Endpoint shape: https://data.cms.gov/data-api/v1/dataset/{dataset_id}/data
"""
from __future__ import annotations

import time
from typing import Iterable

import requests

from core.logging_setup import get_logger

log = get_logger("cms_source")

# "Medicare Fee-For-Service Public Provider Enrollment" dataset id (from CMS docs).
CMS_DATASET_ID = "2457ea29-fc82-48b0-86ec-3b0755de7515"
CMS_API_BASE = f"https://data.cms.gov/data-api/v1/dataset/{CMS_DATASET_ID}/data"
_PAGE = 5000
_PAUSE = 0.3


def build_enrollment_index(state: str) -> dict[str, dict]:
    """
    Pull all enrollment rows for a state and index them by NPI.
    Returns {npi: {"provider_type_desc": str}}. Empty dict on failure so the
    caller degrades gracefully (enrollment fields just stay blank).
    """
    index: dict[str, dict] = {}
    offset = 0
    while True:
        params = {
            "filter[STATE_CD]": state,
            "size": _PAGE,
            "offset": offset,
        }
        try:
            resp = requests.get(CMS_API_BASE, params=params, timeout=60)
            resp.raise_for_status()
            rows = resp.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("CMS request failed (state=%s offset=%s): %s", state, offset, exc)
            break
        if not rows:
            break
        for row in rows:
            npi = str(row.get("NPI", "")).strip()
            if npi:
                index[npi] = {
                    "provider_type_desc": row.get("PROVIDER_TYPE_DESC", ""),
                }
        if len(rows) < _PAGE:
            break
        offset += _PAGE
        time.sleep(_PAUSE)

    log.info("CMS enrollment index for %s: %d NPIs", state, len(index))
    return index


def annotate_with_enrollment(prospects: Iterable, enroll_index: dict[str, dict]):
    """Set medicare_enrolled / provider_type_desc on each prospect in place."""
    for p in prospects:
        hit = enroll_index.get(p.npi)
        if hit:
            p.medicare_enrolled = "YES"
            p.provider_type_desc = hit.get("provider_type_desc", "")
        else:
            p.medicare_enrolled = "NO"
        yield p
