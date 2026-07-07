"""Tavily via raw httpx + ddgs fallback.

TavilySearcher holds a reusable httpx.AsyncClient (never the vendor SDK package, which would
be invisible to respx) with explicit connect/read timeouts, and applies the tenacity
tavily_retry policy at its single POST call-site: 429/5xx are retried then surfaced as
SearchUnavailableError; 4xx re-raise the original so FallbackProvider falls through to the
keyless ddgs provider. Retries live only here — one owner (Constitution P-III).
"""

import asyncio

import httpx
import structlog
from ddgs import DDGS

from memagent.config import Settings
from memagent.state import SearchResult
from memagent.utils.errors import SearchUnavailableError
from memagent.utils.reliability import tavily_retry

TAVILY_ENDPOINT = "https://api.tavily.com/search"

logger = structlog.get_logger(__name__)


class TavilySearcher:
    """Raw httpx POST; snippet maps from the response 'content' field (specs/003 D1)."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.read_timeout_s, connect=settings.connect_timeout_s),
            headers={
                "Authorization": f"Bearer {settings.tavily_api_key}",
                "Content-Type": "application/json",
            },
        )
        # M5: retry the single POST call-site (Ruling D); 400/401/403 re-raise for the fallback.
        self._post = tavily_retry(settings)(self._post)

    async def _post(self, query: str, k: int) -> httpx.Response:
        response = await self._client.post(
            TAVILY_ENDPOINT,
            json={"query": query, "max_results": k, "include_raw_content": False},
        )
        response.raise_for_status()
        return response

    async def search(self, query: str, k: int) -> list[SearchResult]:
        response = await self._post(query, k)
        try:
            results = response.json().get("results", [])
        except (ValueError, AttributeError) as exc:
            # A 200 with a malformed/non-object body (upstream proxy HTML, truncation, schema
            # drift) is a Tavily failure, not a hard stop: surface the typed error so
            # FallbackProvider degrades to the keyless ddgs provider (availability first).
            raise SearchUnavailableError(f"tavily returned an unparseable body: {exc}") from exc
        return [
            SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("content", ""),
                rank=i,
            )
            for i, r in enumerate(results[:k])
        ]


class DdgsSearcher:
    """Keyless DuckDuckGo; ddgs is synchronous so it runs via asyncio.to_thread."""

    async def search(self, query: str, k: int) -> list[SearchResult]:
        rows = await asyncio.to_thread(lambda: list(DDGS().text(query, max_results=k)))
        return [
            SearchResult(
                url=r.get("href", ""),
                title=r.get("title", ""),
                snippet=r.get("body", ""),
                rank=i,
            )
            for i, r in enumerate(rows[:k])
        ]


class FallbackProvider:
    """Implements WebSearcher: Tavily first (iff key present), ddgs on any failure.

    provider_used is turn bookkeeping read by the web_search node (specs/003 D6) —
    the WebSearcher Protocol signature stays untouched.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._tavily = TavilySearcher(settings)
        self._ddgs = DdgsSearcher()
        self.provider_used: str | None = None

    async def search(self, query: str, k: int) -> list[SearchResult]:
        if self._settings.tavily_api_key:
            try:
                results = await self._tavily.search(query, k)
                self.provider_used = "tavily"
                logger.info("web_search", provider_used="tavily", results=len(results))
                return results
            except (httpx.HTTPStatusError, httpx.TransportError, SearchUnavailableError) as exc:
                # 400/401/403 (re-raised original) OR exhaustion (SearchUnavailableError)
                # both fall through to the keyless ddgs provider — availability first.
                logger.warning("tavily_failed", error=type(exc).__name__)
        try:
            results = await self._ddgs.search(query, k)
            self.provider_used = "ddgs"
            logger.info("web_search", provider_used="ddgs", results=len(results))
            return results
        except Exception as exc:  # noqa: BLE001 — ddgs is the last resort; typed error, never a traceback
            logger.warning("ddgs_failed", error=type(exc).__name__)
            self.provider_used = None
            raise SearchUnavailableError(str(exc)) from exc
