"""Domain model for a prospect and helpers for building a stable identity."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


def _norm(s: Optional[str]) -> str:
    """Lowercase, collapse whitespace, strip punctuation for matching."""
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


@dataclass
class Prospect:
    npi: str = ""              # NPPES unique id (great natural key)
    name: str = ""            # clinic / provider name
    email: str = ""           # populated by enrichment; blank rows skipped on send
    phone: str = ""
    fax: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    # --- richer NPPES fields ---
    entity_type: str = ""      # "individual" or "organization"
    credential: str = ""       # e.g. "MD", "DO"
    taxonomy: str = ""         # specialty description, e.g. "Family Medicine"
    taxonomy_code: str = ""
    sole_proprietor: str = ""  # "YES"/"NO" (individuals only)
    mailing_address: str = ""
    # --- CMS Medicare enrollment join ---
    medicare_enrolled: str = ""    # "YES"/"NO"/"" (unknown)
    provider_type_desc: str = ""   # CMS provider-type description
    # --- enrichment bookkeeping ---
    email_status: str = ""     # "", "found", "not_found", "unverified"
    email_source: str = ""     # public URL where the email was found
    email_confidence: str = "" # 0-100 heuristic confidence
    source: str = "nppes"
    dedup_key: str = field(default="")
    # Kept last so older CSVs (without this column) still line up on append.
    website: str = ""          # practice/employer domain, found before Apollo
    category: str = ""         # PROSPECT_CATEGORIES key this row was fetched under
    contact_name: str = ""     # person the email belongs to (org rows: e.g. practice manager)
    contact_title: str = ""
    apollo_id: str = ""        # Apollo person id, to match webhook phone deliveries
    contact_phone: str = ""    # phone revealed by Apollo (arrives later via webhook)
    phone_status: str = ""     # "", "pending", "found", "not_found"

    def __post_init__(self) -> None:
        if not self.dedup_key:
            self.dedup_key = self.compute_dedup_key()

    def compute_dedup_key(self) -> str:
        """
        Identity is: verified email if present, else NPI, else a hash of
        normalized (name + address). This makes dedup robust whether or not
        an email exists yet.
        """
        if self.email:
            # Emails must keep '@' and '.', so normalize by case/space only.
            return "email:" + self.email.strip().lower()
        if self.npi:
            return "npi:" + self.npi.strip()
        basis = _norm(self.name) + "|" + _norm(self.address) + "|" + _norm(self.city)
        return "hash:" + hashlib.sha1(basis.encode()).hexdigest()

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def fieldnames(cls) -> list[str]:
        return list(asdict(cls()).keys())
