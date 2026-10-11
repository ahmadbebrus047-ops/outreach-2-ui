"""Email enrichment providers and the public-web scraper enricher."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Protocol

import requests

from core.logging_setup import get_logger
from core.models import Prospect

log = get_logger("enrichment")


@dataclass
class EmailResult:
    email: str = ""
    status: str = "not_found"   # found | unverified | not_found
    source: str = ""
    confidence: int = 0
    contact_name: str = ""
    contact_title: str = ""
    apollo_id: str = ""
    phone_requested: bool = False   # phone will arrive later via webhook


class EmailEnricher(Protocol):
    def find_email(self, prospect: Prospect) -> EmailResult: ...


class NullEnricher:
    def find_email(self, prospect: Prospect) -> EmailResult:
        return EmailResult(status="not_found")


class PublicWebEnricher:
    """No-API public-web search + website email extraction."""

    def __init__(self):
        from core.scraper import PublicWebEmailEnricher
        self.scraper = PublicWebEmailEnricher(
            request_pause=float(os.getenv("SEARCH_PAUSE_SECONDS", "1.5")),
            page_pause=float(os.getenv("PAGE_PAUSE_SECONDS", "0.75")),
            timeout=int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "15")),
            max_search_results=int(os.getenv("SEARCH_RESULTS_PER_QUERY", "8")),
            max_sites_per_prospect=int(os.getenv("MAX_SITES_PER_PROSPECT", "5")),
        )

    def find_email(self, prospect: Prospect) -> EmailResult:
        return self.scraper.find_email(prospect)


class HunterEnricher:
    """Optional licensed-provider implementation retained for existing users."""

    BASE = "https://api.hunter.io/v2"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("HUNTER_API_KEY", "")

    def find_email_for_domain(self, domain: str, first: str = "", last: str = "") -> EmailResult:
        if not self.api_key or not domain:
            return EmailResult(status="not_found")
        try:
            endpoint = "email-finder" if first and last else "domain-search"
            params = {"domain": domain, "api_key": self.api_key}
            if first and last:
                params.update({"first_name": first, "last_name": last})
            else:
                params["limit"] = 1
            r = requests.get(f"{self.BASE}/{endpoint}", params=params, timeout=30)
            r.raise_for_status()
            data = r.json().get("data", {})
        except (requests.RequestException, ValueError) as exc:
            log.warning("Hunter lookup failed for %s: %s", domain, exc)
            return EmailResult(status="not_found")
        email, confidence = data.get("email", ""), data.get("score", 0)
        if not email and data.get("emails"):
            top = data["emails"][0]
            email, confidence = top.get("value", ""), top.get("confidence", 0)
        if not email:
            return EmailResult(status="not_found")
        return EmailResult(email=email, status="found" if confidence >= 80 else "unverified", confidence=confidence)

    def find_email(self, prospect: Prospect) -> EmailResult:
        return EmailResult(status="not_found")


class ApolloSearchError(Exception):
    def __init__(self, msg: str, rate_limited: bool = False):
        super().__init__(msg)
        self.rate_limited = rate_limited


class ApolloEnricher:
    """Apollo.io email enrichment (2026 API).

    Correctly uses:
      * the `x-api-key` HEADER for auth (Apollo removed body-based api_key),
      * the `/api/v1/people/match` and `/api/v1/people/bulk_match` endpoints,
      * bulk matching (up to 10 people/request) to save time and credits.

    A found email costs 1 Apollo credit; a no-match costs 0 credits.
    """

    from core import config as _cfg  # local alias

    MATCH_URL = "https://api.apollo.io/api/v1/people/match"
    BULK_MATCH_URL = "https://api.apollo.io/api/v1/people/bulk_match"
    BULK_SIZE = 10

    def __init__(self, api_key: Optional[str] = None, reveal_personal: bool | None = None):
        self.api_key = api_key or self._cfg.APOLLO_API_KEY
        self._last_search = 0.0
        if reveal_personal is None:
            reveal_personal = os.getenv("APOLLO_REVEAL_PERSONAL", "0") == "1"
        self.reveal_personal = reveal_personal

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _split_name(prospect: Prospect) -> tuple[str, str]:
        if prospect.entity_type == "individual" and prospect.name:
            parts = prospect.name.split()
            if len(parts) >= 2:
                return parts[0], parts[-1]
        return "", ""

    @classmethod
    def _detail_for(cls, prospect: Prospect) -> dict:
        """Build one Apollo `details[]` object from a Prospect."""
        first, last = cls._split_name(prospect)
        detail: dict = {}
        if first and last:
            detail["first_name"] = first
            detail["last_name"] = last
        if prospect.name and prospect.entity_type == "organization":
            detail["organization_name"] = prospect.name
        elif prospect.name and not (first and last):
            # Fall back to using the org/name field as organization context.
            detail["organization_name"] = prospect.name
        # A domain is what lets Apollo pin down which person this is.
        if prospect.website:
            detail["domain"] = prospect.website
        return detail

    @staticmethod
    def _result_from_person(person: Optional[dict]) -> EmailResult:
        person = person or {}
        email = person.get("email", "") or ""
        common = dict(
            source="apollo",
            contact_name=person.get("name") or "",
            contact_title=person.get("title") or "",
            apollo_id=person.get("id") or "",
        )
        if not email:
            return EmailResult(status="not_found", **common)
        raw_status = (person.get("email_status") or "").lower()
        good = raw_status in ("verified", "likely to engage")
        return EmailResult(
            email=email,
            status="found" if good else "unverified",
            confidence=90 if good else 50,
            **common,
        )

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "x-api-key": self.api_key,
        }

    # -- single -------------------------------------------------------------

    def find_email(self, prospect: Prospect) -> EmailResult:
        if not self.api_key:
            return EmailResult(status="not_found", source="apollo")
        detail = self._detail_for(prospect)
        if not detail:
            return EmailResult(status="not_found", source="apollo")
        payload = dict(detail)
        payload["reveal_personal_emails"] = self.reveal_personal
        payload["reveal_phone_number"] = False  # email only: never spend phone credits
        try:
            r = requests.post(
                self.MATCH_URL, json=payload, headers=self._headers(), timeout=30
            )
            r.raise_for_status()
            person = r.json().get("person") or {}
        except (requests.RequestException, ValueError) as exc:
            log.warning("Apollo lookup failed for %s: %s", prospect.name, exc)
            return EmailResult(status="error", source="apollo")
        return self._result_from_person(person)

    # -- people search (free) -----------------------------------------------

    @staticmethod
    def _same_person(person: dict, first: str, last: str) -> bool:
        """Search hides most of the surname (e.g. 'Ab***a'); check what's shown."""
        if (person.get("first_name") or "").lower() != first.lower():
            return False
        shown = (person.get("last_name_obfuscated") or person.get("last_name") or "").lower()
        if "*" not in shown:
            return shown == last.lower()
        head, _, tail = shown.partition("*")
        tail = tail.strip("*")
        return last.lower().startswith(head) and last.lower().endswith(tail)

    def _people_search(self, payload: dict, who: str) -> list[dict]:
        """POST to People Search, paced under Apollo's per-minute limit.

        Raises ApolloSearchError on any failure, so the caller can leave the row
        retryable instead of recording a false "no email".
        """
        wait = self._cfg.APOLLO_SEARCH_PAUSE - (time.monotonic() - self._last_search)
        if wait > 0:
            time.sleep(wait)
        self._last_search = time.monotonic()
        try:
            r = requests.post(
                self._cfg.APOLLO_SEARCH_URL, json=payload, headers=self._headers(), timeout=30
            )
        except requests.RequestException as exc:
            raise ApolloSearchError(str(exc)) from exc
        if r.status_code == 429:
            log.warning("Apollo search rate limit hit at %s", who)
            raise ApolloSearchError("rate limited", rate_limited=True)
        if r.status_code != 200:
            log.warning("Apollo search failed for %s: HTTP %s %s", who, r.status_code, r.text[:200])
            raise ApolloSearchError(f"HTTP {r.status_code}")
        try:
            return r.json().get("people") or []
        except ValueError as exc:
            raise ApolloSearchError("bad JSON") from exc

    def _search_person(self, prospect: Prospect) -> Optional[dict]:
        """Resolve an individual to an Apollo person via People Search.

        Returns the matching person dict (with `id` and `has_email`), or None.
        Search costs no credits; only a later bulk_match that returns an email does.
        Searches statewide: Apollo's city often differs from the NPPES address.
        """
        first, last = self._split_name(prospect)
        if not (first and last):
            return None
        payload: dict = {"q_keywords": f"{first} {last}", "per_page": 10}
        state = self._cfg.STATE_NAMES.get(prospect.state.upper(), prospect.state)
        if state:
            payload["person_locations"] = [state]
        people = self._people_search(payload, prospect.name)
        for person in people:
            if self._same_person(person, first, last) and self._is_healthcare(person):
                return person
        return None

    # Common names match people in other fields (a bank, a consultancy), so
    # only accept someone whose title or employer is clearly medical.
    _HEALTH_WORDS = (
        "medic", "health", "physician", "doctor", "clinic", "hospital", "care",
        "nurs", "surg", "pediatric", "cardio", "internal", "family", "radiolog",
        "oncolog", "psychiat", "therap", "dental", "dentist", "pharm", "patholog",
        "anesthe", "ortho", "neuro", "dermat", "obstet", "gyne", "urolog",
        "emergency", "pulmon", "gastro", "endocrin", "nephro", "rheumat",
        "allerg", "ophthalm", "optom", "hospitalist", "resident", "fellow",
        "m.d", "md", "d.o.", "practitioner", "rehab", "infectious", "geriatric",
        "dietitian", "dietician", "nutrition", "rdn", "fnp", "aprn", "np",
    )
    _HEALTH_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in _HEALTH_WORDS) + r")")

    @classmethod
    def _is_healthcare(cls, person: dict) -> bool:
        # Judge by the person's own title: a "Security Architect" at a health
        # company is not a doctor. Fall back to the employer only if untitled.
        hay = " ".join([person.get("title") or "", person.get("headline") or ""]).strip()
        if not hay:
            hay = (person.get("organization") or {}).get("name") or ""
        # Word-start match, so "resident" doesn't hit "Vice President".
        return bool(cls._HEALTH_RE.search(hay.lower()))

    # Who to reach at a group practice, best first. For a billing pitch the
    # practice/office manager is the buyer; the medical director is a fallback.
    _ORG_TITLES = [
        "practice manager", "office manager", "practice administrator",
        "billing manager", "revenue cycle manager", "administrator",
        "operations manager", "owner", "ceo", "medical director",
    ]
    _ORG_GENERIC = {
        "llc", "pllc", "pa", "inc", "ltd", "lp", "llp", "corp", "co", "the", "and", "of",
        "pc", "sc", "group", "medical", "clinic", "center", "centers", "health",
        "healthcare", "associates", "services", "care", "practice", "family",
    }

    @classmethod
    def _org_tokens(cls, name: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9]+", name.lower())
                if len(t) > 1 and t not in cls._ORG_GENERIC}

    @classmethod
    def _title_rank(cls, title: str) -> int:
        t = (title or "").lower()
        for rank, want in enumerate(cls._ORG_TITLES):
            if re.search(r"\b" + re.escape(want) + r"\b", t):
                return rank
        return len(cls._ORG_TITLES)

    def _search_org_contact(self, prospect: Prospect) -> Optional[dict]:
        """Find the best decision-maker at an organization via People Search (free)."""
        if not prospect.name:
            return None
        payload: dict = {
            "q_organization_name": prospect.name,
            "person_titles": self._ORG_TITLES,
            "per_page": 25,
        }
        state = self._cfg.STATE_NAMES.get(prospect.state.upper(), prospect.state)
        if state:
            payload["person_locations"] = [state]
        people = self._people_search(payload, prospect.name)

        want = self._org_tokens(prospect.name)
        best, best_rank = None, len(self._ORG_TITLES)
        for person in people:
            if not person.get("has_email"):
                continue
            org = (person.get("organization") or {}).get("name") or ""
            have = self._org_tokens(org)
            # Every distinctive word of the NPPES name must be in Apollo's org name
            # (or vice versa), so "Smith Family Clinic" doesn't match "Smith Dental".
            if not want or not have or not (want <= have or have <= want):
                continue
            rank = self._title_rank(person.get("title") or "")
            if rank < best_rank:
                best, best_rank = person, rank
        return best

    # -- bulk (up to 10 per call) -------------------------------------------

    @staticmethod
    def _has_phone(person: dict) -> bool:
        # Search reports "Yes", "Maybe: ...", or a falsy value.
        v = person.get("has_direct_phone")
        return bool(v) and str(v).lower() not in ("no", "false")

    def find_emails_bulk(self, prospects: list[Prospect], want_phone: bool = False) -> list[EmailResult]:
        """Enrich a batch of prospects. Returns results aligned to input order.

        Individuals are first resolved with People Search (free). Only people
        Apollo says have an email (or, with `want_phone`, a phone) are sent to
        bulk_match, so no-match rows never reach the paid endpoint. Splits
        into chunks of BULK_SIZE (10).
        """
        want_phone = want_phone and bool(self._cfg.APOLLO_PHONE_WEBHOOK_BASE)
        if not self.api_key:
            return [EmailResult(status="not_found", source="apollo") for _ in prospects]

        results: list[Optional[EmailResult]] = [None] * len(prospects)
        pending: list[tuple[int, dict]] = []   # (index, bulk_match detail)
        rate_limited = False
        for idx, p in enumerate(prospects):
            detail = self._detail_for(p)
            if self._cfg.APOLLO_SEARCH_ENABLED:
                if rate_limited:
                    # Leave the rest retryable rather than burning more requests.
                    results[idx] = EmailResult(status="error", source="apollo: rate limited")
                    continue
                try:
                    person = (self._search_person(p) if p.entity_type == "individual"
                              else self._search_org_contact(p))
                except ApolloSearchError as exc:
                    rate_limited = exc.rate_limited
                    results[idx] = EmailResult(
                        status="error",
                        source="apollo: rate limited" if exc.rate_limited else "apollo: search failed",
                    )
                    continue
                worth_it = person is not None and (
                    person.get("has_email") or (want_phone and self._has_phone(person)))
                if not worth_it:
                    results[idx] = EmailResult(status="not_found", source="apollo")
                    continue
                detail = {"id": person["id"]}
            if not detail:
                results[idx] = EmailResult(status="not_found", source="apollo")
                continue
            pending.append((idx, detail))

        for start in range(0, len(pending), self.BULK_SIZE):
            batch = pending[start : start + self.BULK_SIZE]
            matched = self._bulk_match([d for _, d in batch], want_phone)
            for (idx, _), res in zip(batch, matched):
                results[idx] = res

        return results  # type: ignore[return-value]

    def _bulk_match(self, details: list[dict], want_phone: bool = False) -> list[EmailResult]:
        results: list[EmailResult] = []
        for start in range(0, len(details), self.BULK_SIZE):
            chunk = details[start : start + self.BULK_SIZE]
            payload = {
                "details": chunk,
                "reveal_personal_emails": self.reveal_personal,
                # Phone reveals cost extra credits and Apollo only delivers them
                # later to a public webhook, so request them only when asked.
                "reveal_phone_number": want_phone,
            }
            if want_phone:
                payload["webhook_url"] = (
                    f"{self._cfg.APOLLO_PHONE_WEBHOOK_BASE}/api/apollo-webhook/"
                    f"{self._cfg.APOLLO_WEBHOOK_SECRET}"
                )
            try:
                r = requests.post(
                    self.BULK_MATCH_URL,
                    json=payload,
                    headers=self._headers(),
                    timeout=60,
                )
                r.raise_for_status()
                matches = r.json().get("matches") or []
            except (requests.RequestException, ValueError) as exc:
                log.warning("Apollo bulk lookup failed: %s", exc)
                results.extend(
                    EmailResult(status="error", source="apollo") for _ in chunk
                )
                continue

            # Apollo returns `matches` aligned to `details` order; pad if short.
            for i in range(len(chunk)):
                person = matches[i] if i < len(matches) else None
                res = self._result_from_person(person)
                res.phone_requested = want_phone and bool(res.apollo_id)
                results.append(res)

        return results


ENRICHERS = {
    "null": NullEnricher,
    "web": PublicWebEnricher,
    "public_web": PublicWebEnricher,
    "scraper": PublicWebEnricher,
    "hunter": HunterEnricher,
    "apollo": ApolloEnricher,
}


def get_enricher() -> EmailEnricher:
    name = os.getenv("ENRICHER", "null").lower()
    return ENRICHERS.get(name, NullEnricher)()
