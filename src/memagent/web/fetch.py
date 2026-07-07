"""Bounded concurrent page fetcher.

filter_urls is the mini-SSRF guard + diversity filter. HttpxPageFetcher wraps each per-URL
fetch in the tenacity page-fetch policy (fetch_retry: 2 attempts; retries timeouts and
502/503/504). The wait_for page deadline stays OUTSIDE the retry so it bounds both attempts,
and any timeout / size cap / non-retryable status degrades to a skipped page, never a fatal
error.
"""

import asyncio
import html as html_lib
import ipaddress
import re
import socket
from urllib.parse import urlsplit

import httpx
import structlog

from memagent.config import Settings
from memagent.state import FetchedDoc
from memagent.utils.reliability import fetch_retry
from memagent.web.to_markdown import to_markdown

ALLOWED_SCHEMES = {"http", "https"}
ACCEPTED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
JS_ONLY_DENYLIST = {
    "youtube.com",
    "youtu.be",
    "x.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
}
USER_AGENT = "memagent/1.0 (+https://github.com/muhammadyehiaelsayed/memory-first-agent)"
MAX_REDIRECTS = 5

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

logger = structlog.get_logger(__name__)


# Compound public suffixes whose registrable domain is the last THREE labels (bbc.co.uk,
# not co.uk). A tiny bundled list — deliberately NOT the full PSL and dependency-free
# (tldextract's default PSL bootstrap fetches over the network, which breaks the repo's
# keyless/offline design). Enough to stop the diversity cap collapsing distinct *.co.uk /
# *.com.au orgs into one bucket.
_COMPOUND_SUFFIXES = frozenset(
    {
        "co.uk",
        "ac.uk",
        "org.uk",
        "gov.uk",
        "com.au",
        "co.jp",
        "com.br",
        "co.nz",
        "co.in",
        "co.za",
        "com.mx",
    }
)


def _registrable_domain(host: str) -> str:
    parts = host.lower().rstrip(".").split(".")
    if len(parts) < 2:
        return host.lower()
    last_two = ".".join(parts[-2:])
    if len(parts) >= 3 and last_two in _COMPOUND_SUFFIXES:
        return ".".join(parts[-3:])
    return last_two


def _is_private_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True

    def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
        )

    try:
        return _blocked(ipaddress.ip_address(host))
    except ValueError:
        pass
    # Hostname (not an IP literal): resolve it and block if ANY resolved address is
    # private/loopback/link-local/reserved/unspecified — this closes the direct
    # hostname->private-IP SSRF vector. Fail-open on resolution error (return False) so a
    # transient DNS failure does not drop an otherwise-public URL. DNS-rebinding TOCTOU (the
    # record changing between this check and the connect) remains an accepted, out-of-scope
    # residual for this mini-guard.
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if _blocked(ip):
            return True
    return False


def _is_safe_fetch_target(url: str) -> bool:
    """Scheme + private-host SSRF check for a single URL.

    filter_urls vets only the initial search-result URLs; this is re-run on every redirect
    hop (the fetcher no longer auto-follows) so a public page cannot 302 the fetcher into
    http://169.254.169.254/... or a loopback/internal service.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme.lower() in ALLOWED_SCHEMES and bool(host) and not _is_private_host(host)


def filter_urls(urls: list[str], settings: Settings) -> list[str]:
    kept: list[str] = []
    per_domain: dict[str, int] = {}
    for url in urls:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme.lower() not in ALLOWED_SCHEMES or not host:
            continue
        if _is_private_host(host):
            continue
        domain = _registrable_domain(host)
        if domain in JS_ONLY_DENYLIST:
            continue
        if per_domain.get(domain, 0) >= settings.max_urls_per_domain:
            continue
        per_domain[domain] = per_domain.get(domain, 0) + 1
        kept.append(url)
    return kept


def _extract_title(html: str, fallback: str) -> str:
    match = _TITLE_RE.search(html)
    if not match:
        return fallback
    title = html_lib.unescape(" ".join(match.group(1).split())).strip()
    return title[:300] or fallback


class HttpxPageFetcher:
    """Implements the PageFetcher Protocol: streamed, capped, deadline-bounded."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            follow_redirects=False,  # followed manually so each hop is re-checked for SSRF
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_s,
                read=settings.read_timeout_s,
                write=settings.read_timeout_s,
                pool=settings.connect_timeout_s,
            ),
            headers={"User-Agent": USER_AGENT},
        )
        self._semaphore = asyncio.Semaphore(settings.fetch_concurrency)
        # M5: retry the per-URL transport (Ruling D); the wait_for deadline in
        # _fetch_guarded stays OUTSIDE, so it bounds BOTH attempts.
        self._fetch_one = fetch_retry(settings)(self._fetch_one)

    async def fetch(self, urls: list[str]) -> list[FetchedDoc]:
        results = await asyncio.gather(*(self._fetch_guarded(u) for u in urls))
        return [doc for doc in results if doc is not None]

    async def _fetch_guarded(self, url: str) -> FetchedDoc | None:
        try:
            async with self._semaphore:
                return await asyncio.wait_for(self._fetch_one(url), self._settings.page_deadline_s)
        except Exception as exc:  # noqa: BLE001 — per-URL failures are skipped; others continue
            logger.warning("fetch_skipped", url=url, error=type(exc).__name__)
            return None

    async def _fetch_one(self, url: str) -> FetchedDoc | None:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            async with self._client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    target = str(response.url.join(location)) if location else ""
                    if not target or not _is_safe_fetch_target(target):
                        logger.warning("redirect_blocked", frm=current, to=target or "(none)")
                        return None
                    current = target
                    continue
                response.raise_for_status()
                ctype = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype not in ACCEPTED_CONTENT_TYPES:
                    return None
                body = bytearray()
                async for part in response.aiter_bytes():
                    body.extend(part)
                    if len(body) > self._settings.fetch_max_bytes:
                        # Oversize: skip the page entirely — never truncate-and-keep.
                        return None
                html = body.decode(response.encoding or "utf-8", errors="replace")
                # trafilatura.extract is CPU-bound (lxml parse, doubled on the recall
                # fallback) and blocks the event loop; offload it so concurrent page
                # extractions actually run in parallel (mirrors DdgsSearcher.to_thread).
                markdown = await asyncio.to_thread(to_markdown, html, self._settings)
                if markdown is None:
                    return None
                final_url = str(response.url)  # post-redirect URL is the stored identity
                return FetchedDoc(
                    url=final_url,
                    title=_extract_title(html, fallback=final_url),
                    markdown=markdown,
                    summary=None,
                    ok=True,
                )
        logger.warning("too_many_redirects", url=url)
        return None
