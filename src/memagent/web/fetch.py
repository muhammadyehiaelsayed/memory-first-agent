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

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

logger = structlog.get_logger(__name__)


def _registrable_domain(host: str) -> str:
    parts = host.lower().rstrip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


def _is_private_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Hostname (not an IP literal): a known, accepted limitation of this mini-guard —
        # we do not resolve DNS, so a hostname that points at a private IP is not caught here.
        return False
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    )


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
            follow_redirects=True,
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
        async with self._client.stream("GET", url) as response:
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
            markdown = to_markdown(html, self._settings)
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
