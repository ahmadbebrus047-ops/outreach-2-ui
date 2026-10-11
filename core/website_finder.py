"""Find a prospect's practice/employer website domain from public search.

NPPES rows carry no company or domain, and Apollo cannot match a person from
a bare name. This module runs one public web search per prospect (reusing the
search engines in core/scraper.py) and returns the most plausible practice or
hospital domain, skipping directories and social sites.

A wrong guess is cheap: Apollo only charges when it returns an email, so a
mismatched domain simply comes back as no match.
"""
from __future__ import annotations

import re
import time

import requests

from core.logging_setup import get_logger
from core.models import Prospect
from core.scraper import BingSearch, DuckDuckGoSearch, _domain

log = get_logger("website_finder")

# Aggregators, directories, social and reference sites -- never a practice domain.
_SKIP_DOMAINS = {
    "healthgrades.com", "vitals.com", "webmd.com", "zocdoc.com", "doximity.com",
    "npiprofile.com", "npidb.org", "npino.com", "hipaaspace.com", "npiregistry.cms.hhs.gov",
    "nppes.cms.hhs.gov", "opennpi.com", "npilookup.org", "carelistings.com",
    "sharecare.com", "usnews.com", "health.usnews.com", "castleconnolly.com",
    "md.com", "ratemds.com", "wellness.com", "caredash.com", "medicare.gov",
    "findatopdoc.com", "doctor.com", "kareo.com", "practicefusion.com",
    "medicarelist.com", "providerdata.com", "hospitalcareers.com", "buzzfile.com",
    "yelp.com", "yellowpages.com", "bbb.org", "mapquest.com", "manta.com",
    "facebook.com", "linkedin.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "wikipedia.org", "google.com", "bing.com", "duckduckgo.com",
    "bizapedia.com", "opencorporates.com", "dnb.com", "zoominfo.com", "apollo.io",
    "rocketreach.co", "signalhire.com", "indeed.com", "glassdoor.com",
    "ziprecruiter.com", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "researchgate.net", "amazon.com", "tdlr.texas.gov", "tmb.state.tx.us",
}
_SKIP_SUFFIXES = (".gov",)

# Generic words that don't identify an organization.
_STOP = {
    "llc", "pllc", "inc", "pa", "ltd", "corp", "co", "the", "and", "of", "group",
    "medical", "clinic", "center", "health", "healthcare", "family", "practice",
    "care", "services", "associates", "md", "do",
}


def _skipped(domain: str) -> bool:
    if not domain or domain.endswith(_SKIP_SUFFIXES):
        return True
    return any(domain == d or domain.endswith("." + d) for d in _SKIP_DOMAINS)


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2 and t not in _STOP]


def _query(p: Prospect) -> str:
    if p.entity_type == "individual":
        return f'"{p.name}" {p.credential} {p.taxonomy} {p.city} {p.state}'.strip()
    return f'"{p.name}" {p.city} {p.state}'.strip()


class WebsiteFinder:
    def __init__(self, timeout: int = 15, pause: float = 1.5, max_results: int = 10):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.engines = [DuckDuckGoSearch(self.session, timeout), BingSearch(self.session, timeout)]
        self.pause = pause
        self.max_results = max_results

    def find(self, p: Prospect) -> str:
        """Return a bare domain like 'example.com', or '' if nothing plausible."""
        results = []
        for engine in self.engines:
            results = engine.search(_query(p), self.max_results)
            if results:
                break
        time.sleep(self.pause)

        if p.entity_type == "individual":
            # The person's surname must appear in the result for it to count.
            parts = p.name.split()
            must = [parts[-1].lower()] if parts else []
        else:
            must = []
        org_tokens = _tokens(p.name) if p.entity_type != "individual" else []

        best, best_score = "", 0
        for r in results:
            domain = _domain(r.url)
            if _skipped(domain):
                continue
            hay = f"{r.title} {r.snippet} {r.url}".lower()
            if must and not all(m in hay for m in must):
                continue
            score = 1
            compact = domain.replace("-", "")
            score += sum(3 for t in org_tokens if t in compact)
            score += sum(1 for t in org_tokens if t in hay)
            if (p.city or "").lower() in hay:
                score += 1
            if score > best_score:
                best, best_score = domain, score

        log.info("%s -> %s", p.name, best or "(none)")
        return best
