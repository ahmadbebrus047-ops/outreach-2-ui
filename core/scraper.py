"""Public-web search and email extraction for prospect enrichment.

This module deliberately does NOT use a search/enrichment API. It submits
ordinary web requests to publicly available search-result pages, extracts
result links, and then checks publicly accessible business/practice pages for
published professional email addresses.

It is intentionally conservative:
* no CAPTCHA/anti-bot bypassing
* no login/private pages
* no guessed email addresses
* no overwriting an existing email
* short timeouts + configurable pauses
* only HTTP(S) pages are followed

Search engines are pluggable. The default order is DuckDuckGo HTML, Brave
Search HTML, then Bing HTML. Search engines can change their markup at any
time, so parsers are kept small and isolated.
"""
from __future__ import annotations

import html
import re
import os
import time
from dataclasses import dataclass
from typing import Iterable, Protocol
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from core.logging_setup import get_logger
from core.models import Prospect

log = get_logger("scraper")

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9][A-Za-z0-9._%+-]{0,63}"
    r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,63})(?![A-Za-z0-9._%+-])",
    re.I,
)
BAD_EMAIL_PREFIXES = {"noreply", "no-reply", "donotreply", "do-not-reply"}
FREE_MAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "aol.com", "proton.me", "protonmail.com", "live.com", "msn.com",
}
SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".mp4")


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass
class EmailCandidate:
    email: str
    source_url: str
    score: int
    reason: str


class SearchEngine(Protocol):
    name: str

    def search(self, query: str, limit: int = 8) -> list[SearchResult]: ...


class BaseSearchEngine:
    name = "search"

    def __init__(self, session: requests.Session, timeout: int = 15):
        self.session = session
        self.timeout = timeout
        self.last_outcome = "ok"

    @staticmethod
    def _clean_url(url: str) -> str:
        url = html.unescape(url).strip()
        parsed = urlparse(url)
        # Search engines commonly wrap results in redirect URLs.
        for key in ("uddg", "url", "u"):
            value = parse_qs(parsed.query).get(key, [""])[0]
            if value.startswith(("http://", "https://")):
                return unquote(value)
        return url

    @staticmethod
    def _valid_result(url: str) -> bool:
        try:
            p = urlparse(url)
            return p.scheme in {"http", "https"} and bool(p.netloc)
        except ValueError:
            return False


class DuckDuckGoSearch(BaseSearchEngine):
    name = "duckduckgo"
    ENDPOINT = "https://html.duckduckgo.com/html/"

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        self.last_outcome = "ok"
        try:
            response = self.session.get(
                self.ENDPOINT,
                params={"q": query},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 429:
                self.last_outcome = "rate_limited"
                retry_after = getattr(exc.response, "headers", {}).get("Retry-After", "") if exc.response else ""
                log.warning("%s search rate-limited (HTTP 429)%s; skipping this engine for this request", self.name, f"; Retry-After={retry_after}s" if retry_after else "")
            else:
                self.last_outcome = "error"
                log.warning("%s search failed: %s", self.name, exc)
            return []
        except requests.RequestException as exc:
            self.last_outcome = "error"
            log.warning("%s search failed: %s", self.name, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[SearchResult] = []
        for item in soup.select(".result"):
            anchor = item.select_one("a.result__a")
            if not anchor:
                continue
            url = self._clean_url(anchor.get("href", ""))
            if not self._valid_result(url):
                continue
            snippet = item.select_one(".result__snippet")
            results.append(SearchResult(anchor.get_text(" ", strip=True), url,
                                        snippet.get_text(" ", strip=True) if snippet else ""))
            if len(results) >= limit:
                break
        return results


class BraveSearch(BaseSearchEngine):
    name = "brave"
    ENDPOINT = "https://search.brave.com/search"

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        self.last_outcome = "ok"
        try:
            response = self.session.get(
                self.ENDPOINT,
                params={"q": query},
                headers={"Accept-Language": "en-US,en;q=0.9"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 429:
                self.last_outcome = "rate_limited"
                retry_after = getattr(exc.response, "headers", {}).get("Retry-After", "") if exc.response else ""
                log.warning("%s search rate-limited (HTTP 429)%s; skipping this engine for this request", self.name, f"; Retry-After={retry_after}s" if retry_after else "")
            else:
                self.last_outcome = "error"
                log.warning("%s search failed: %s", self.name, exc)
            return []
        except requests.RequestException as exc:
            self.last_outcome = "error"
            log.warning("%s search failed: %s", self.name, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[SearchResult] = []
        # Brave's markup has changed over time; accept several common forms.
        anchors = soup.select("a[href^='http']")
        for anchor in anchors:
            url = self._clean_url(anchor.get("href", ""))
            if not self._valid_result(url):
                continue
            host = urlparse(url).netloc.lower()
            if "brave.com" in host:
                continue
            title = anchor.get_text(" ", strip=True)
            if not title or len(title) < 3:
                continue
            parent = anchor.parent
            snippet = parent.get_text(" ", strip=True) if parent else ""
            results.append(SearchResult(title, url, snippet[:500]))
            if len(results) >= limit:
                break
        return _dedupe_results(results)[:limit]


class BingSearch(BaseSearchEngine):
    name = "bing"
    ENDPOINT = "https://www.bing.com/search"

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        self.last_outcome = "ok"
        try:
            response = self.session.get(
                self.ENDPOINT,
                params={"q": query},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 429:
                self.last_outcome = "rate_limited"
                retry_after = getattr(exc.response, "headers", {}).get("Retry-After", "") if exc.response else ""
                log.warning("%s search rate-limited (HTTP 429)%s; skipping this engine for this request", self.name, f"; Retry-After={retry_after}s" if retry_after else "")
            else:
                self.last_outcome = "error"
                log.warning("%s search failed: %s", self.name, exc)
            return []
        except requests.RequestException as exc:
            self.last_outcome = "error"
            log.warning("%s search failed: %s", self.name, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[SearchResult] = []
        for item in soup.select("li.b_algo"):
            anchor = item.select_one("h2 a")
            if not anchor:
                continue
            url = self._clean_url(anchor.get("href", ""))
            if not self._valid_result(url):
                continue
            snippet = item.select_one(".b_caption p")
            results.append(SearchResult(anchor.get_text(" ", strip=True), url,
                                        snippet.get_text(" ", strip=True) if snippet else ""))
            if len(results) >= limit:
                break
        return results


def _dedupe_results(results: Iterable[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    output: list[SearchResult] = []
    for result in results:
        key = result.url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(result)
    return output


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().split(":", 1)[0].removeprefix("www.")


def _same_or_subdomain(url: str, root_domain: str) -> bool:
    domain = _domain(url)
    return domain == root_domain or domain.endswith("." + root_domain)


def _search_queries(prospect: Prospect) -> list[str]:
    """Generate increasingly broad queries from NPPES fields."""
    name = (prospect.name or "").strip()
    city = (prospect.city or "").strip()
    state = (prospect.state or "").strip()
    taxonomy = (prospect.taxonomy or "").strip()
    queries: list[str] = []

    if name and city and state:
        queries.append(f'"{name}" "{city}" "{state}" email')
        queries.append(f'"{name}" "{city}" "{state}" contact')
    if name and taxonomy:
        queries.append(f'"{name}" "{taxonomy}" email')
    if name:
        queries.append(f'"{name}" email')
        queries.append(f'"{name}" contact')

    # Preserve order while removing duplicate queries.
    return list(dict.fromkeys(queries))


def _email_candidates(text: str, source_url: str) -> list[str]:
    text = html.unescape(text).replace("[at]", "@").replace("(at)", "@")
    text = re.sub(r"\s+at\s+", "@", text, flags=re.I)
    text = re.sub(r"\s+dot\s+", ".", text, flags=re.I)
    return [m.group(1).lower().rstrip(".,;:") for m in EMAIL_RE.finditer(text)]


def _score_email(email: str, prospect: Prospect, page_url: str) -> tuple[int, str]:
    local, domain = email.rsplit("@", 1)
    score = 0
    reasons: list[str] = []
    domain = domain.lower()

    if local.lower() not in BAD_EMAIL_PREFIXES:
        score += 10
    else:
        score -= 80

    if domain not in FREE_MAIL_DOMAINS:
        score += 35
        reasons.append("business-domain")
    else:
        score -= 20
        reasons.append("free-mail")

    name_tokens = [x for x in re.findall(r"[a-z0-9]+", (prospect.name or "").lower()) if len(x) > 2]
    local_compact = re.sub(r"[^a-z0-9]", "", local.lower())
    matched = sum(1 for token in name_tokens if token in local_compact)
    if matched:
        score += min(35, matched * 18)
        reasons.append("name-match")

    org_tokens = [x for x in re.findall(r"[a-z0-9]+", (prospect.name or "").lower()) if len(x) > 4]
    if any(token in domain.replace("-", "") for token in org_tokens):
        score += 20
        reasons.append("domain-name-match")

    if _same_or_subdomain(page_url, domain):
        score += 20
        reasons.append("page-domain-match")

    return score, ",".join(reasons)


def _find_internal_pages(soup: BeautifulSoup, base_url: str, max_pages: int = 5) -> list[str]:
    base_domain = _domain(base_url)
    preferred_words = ("contact", "about", "team", "staff", "provider", "location", "office")
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"])
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or not _same_or_subdomain(href, base_domain):
            continue
        if any(parsed.path.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
            continue
        if href.rstrip("/") in seen:
            continue
        seen.add(href.rstrip("/"))
        label = (anchor.get_text(" ", strip=True) + " " + parsed.path).lower()
        rank = 10 if any(word in label for word in preferred_words) else 0
        ranked.append((rank, href))

    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [url for _, url in ranked[:max_pages]]


class PublicWebEmailEnricher:
    """Search the public web and extract published professional emails."""

    def __init__(
        self,
        engines: list[SearchEngine] | None = None,
        request_pause: float = 1.5,
        page_pause: float = 0.75,
        timeout: int = 15,
        max_search_results: int = 8,
        max_sites_per_prospect: int = 5,
    ):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        # Search-engine HTML endpoints are not stable and may rate-limit
        # automated requests. Brave is therefore opt-in rather than part of
        # the default rotation. Set ENABLE_BRAVE_SEARCH=1 if you explicitly
        # want to use it.
        default_engines: list[SearchEngine] = [
            DuckDuckGoSearch(self.session, timeout),
            BingSearch(self.session, timeout),
        ]
        if os.getenv("ENABLE_BRAVE_SEARCH", "0") == "1":
            default_engines.insert(1, BraveSearch(self.session, timeout))
        self.engines = engines or default_engines
        self.request_pause = request_pause
        self.page_pause = page_pause
        self.timeout = timeout
        self.max_search_results = max_search_results
        self.max_sites_per_prospect = max_sites_per_prospect
        self._robots_cache: dict[str, RobotFileParser] = {}

    def _robots_allowed(self, url: str) -> bool:
        """Honor the target site's robots.txt when fetching its pages."""
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            rp = RobotFileParser()
            rp.set_url(origin + "/robots.txt")
            try:
                rp.read()
            except Exception:
                # If robots.txt cannot be retrieved, don't use it as a reason to
                # fail the entire job; the request is still bounded and public.
                rp = RobotFileParser()
                rp.parse([])
            self._robots_cache[origin] = rp
        return self._robots_cache[origin].can_fetch(self.session.headers["User-Agent"], url)

    def _fetch(self, url: str) -> str:
        if not self._robots_allowed(url):
            return ""
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return ""
            if len(response.content) > 5_000_000:
                return ""
            time.sleep(self.page_pause)
            return response.text
        except requests.RequestException as exc:
            log.debug("Could not fetch %s: %s", url, exc)
            return ""

    def find_email(self, prospect: Prospect):
        from core.enrichment import EmailResult

        if prospect.email:
            return EmailResult(email=prospect.email, status=prospect.email_status or "found")

        candidates: dict[str, EmailCandidate] = {}
        queries = _search_queries(prospect)
        all_results: list[SearchResult] = []

        search_attempts = 0
        rate_limited_attempts = 0
        error_attempts = 0

        for query in queries:
            for engine in self.engines:
                search_attempts += 1
                results = engine.search(query, self.max_search_results)
                all_results.extend(results)
                outcome = getattr(engine, "last_outcome", "ok")
                if outcome == "rate_limited":
                    rate_limited_attempts += 1
                elif outcome == "error":
                    error_attempts += 1
                if results:
                    # A successful engine is enough for this query; don't hammer
                    # every search engine unnecessarily.
                    break
            time.sleep(self.request_pause)

        all_results = _dedupe_results(all_results)
        # Search result snippets themselves can contain the public email.
        for result in all_results:
            for email in _email_candidates(result.title + " " + result.snippet, result.url):
                score, reason = _score_email(email, prospect, result.url)
                old = candidates.get(email)
                if old is None or score > old.score:
                    candidates[email] = EmailCandidate(email, result.url, score, reason)

        # Visit the most promising unique domains, not every search result.
        sites: list[str] = []
        seen_domains: set[str] = set()
        for result in all_results:
            domain = _domain(result.url)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            sites.append(result.url)
            if len(sites) >= self.max_sites_per_prospect:
                break

        for site in sites:
            body = self._fetch(site)
            if not body:
                continue
            soup = BeautifulSoup(body, "html.parser")
            text = soup.get_text(" ", strip=True)
            chunks = [text]
            for a in soup.select('a[href^="mailto:"]'):
                chunks.append(a.get("href", "")[7:].split("?", 1)[0])
            for email in _email_candidates(" ".join(chunks), site):
                score, reason = _score_email(email, prospect, site)
                old = candidates.get(email)
                if old is None or score > old.score:
                    candidates[email] = EmailCandidate(email, site, score, reason)

            for page in _find_internal_pages(soup, site):
                body = self._fetch(page)
                if not body:
                    continue
                page_soup = BeautifulSoup(body, "html.parser")
                chunks = [page_soup.get_text(" ", strip=True)]
                chunks.extend(
                    a.get("href", "")[7:].split("?", 1)[0]
                    for a in page_soup.select('a[href^="mailto:"]')
                )
                for email in _email_candidates(" ".join(chunks), page):
                    score, reason = _score_email(email, prospect, page)
                    old = candidates.get(email)
                    if old is None or score > old.score:
                        candidates[email] = EmailCandidate(email, page, score, reason)

        viable = [c for c in candidates.values() if c.score >= 45 and c.email.split("@", 1)[0] not in BAD_EMAIL_PREFIXES]
        if not viable:
            if search_attempts and rate_limited_attempts == search_attempts:
                return EmailResult(status="rate_limited")
            if search_attempts and error_attempts == search_attempts:
                return EmailResult(status="error")
            return EmailResult(status="not_found")

        viable.sort(key=lambda c: c.score, reverse=True)
        winner = viable[0]
        status = "found" if winner.score >= 75 else "unverified"
        log.info("%s -> %s (%s, %d)", prospect.name, winner.email, winner.source_url, winner.score)
        return EmailResult(
            email=winner.email,
            status=status,
            source=winner.source_url,
            confidence=min(100, winner.score),
        )
