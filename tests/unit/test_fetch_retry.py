"""M5-owned: page-fetch retry policy (FR-M5-22), respx-driven, WAIT_CAP_SCALE=0.

Per-URL, non-fatal: timeouts/502/503/504 retry (2 attempts); other 4xx, non-HTML, and
oversize bodies are skipped without retry; one failing URL never stops the others.
"""

import asyncio

import httpx
import respx

from memagent.config import Settings
from memagent.utils.errors import PageFetchError
from memagent.web.fetch import HttpxPageFetcher

SETTINGS = Settings(_env_file=None, wait_cap_scale=0.0)
HTML = {"content-type": "text/html"}


def _page(title: str) -> bytes:
    # Substantial body so trafilatura extracts real content (thin pages return None → skip).
    body = (
        "Redis vector search uses cosine similarity over embeddings stored in a FLAT index. "
        "This paragraph is deliberately long enough that the markdown extractor produces a "
        "non-empty document instead of discarding the page as boilerplate or too short."
    )
    return f"<html><head><title>{title}</title></head><body><article><h1>{title}</h1><p>{body}</p></article></body></html>".encode()


def _run(coro):
    return asyncio.run(coro)


@respx.mock
def test_read_timeout_then_success_two_calls():
    route = respx.get("https://a.com/").mock(
        side_effect=[
            httpx.ReadTimeout("slow"),
            httpx.Response(200, headers=HTML, content=_page("A")),
        ]
    )
    fetcher = HttpxPageFetcher(SETTINGS)
    doc = _run(fetcher._fetch_one("https://a.com/"))
    assert route.call_count == 2
    assert doc and doc["ok"]


@respx.mock
def test_404_not_retried_raises_pagefetch():
    route = respx.get("https://b.com/").mock(return_value=httpx.Response(404))
    fetcher = HttpxPageFetcher(SETTINGS)
    raised = False
    try:
        _run(fetcher._fetch_one("https://b.com/"))
    except PageFetchError:
        raised = True
    assert raised
    assert route.call_count == 1


@respx.mock
def test_oversize_body_skipped():
    big = b"x" * (SETTINGS.fetch_max_bytes + 10)
    respx.get("https://c.com/").mock(return_value=httpx.Response(200, headers=HTML, content=big))
    fetcher = HttpxPageFetcher(SETTINGS)
    assert _run(fetcher._fetch_one("https://c.com/")) is None  # aborted, no retry


@respx.mock
def test_non_html_content_type_skipped():
    respx.get("https://d.com/").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF"
        )
    )
    fetcher = HttpxPageFetcher(SETTINGS)
    assert _run(fetcher._fetch_one("https://d.com/")) is None


@respx.mock
def test_redirect_stores_final_resolved_url():
    # FR-M3-13: with follow_redirects=True the stored identity is the POST-redirect URL, so
    # freshness/dedup key off where the content actually lives (not the original request URL).
    respx.get("https://start.com/").mock(
        return_value=httpx.Response(301, headers={"location": "https://final.com/page"})
    )
    respx.get("https://final.com/page").mock(
        return_value=httpx.Response(200, headers=HTML, content=_page("Final"))
    )
    fetcher = HttpxPageFetcher(SETTINGS)
    doc = _run(fetcher._fetch_one("https://start.com/"))
    assert doc and doc["url"] == "https://final.com/page"


@respx.mock
def test_one_failed_url_does_not_stop_the_others():
    respx.get("https://a.com/").mock(
        return_value=httpx.Response(200, headers=HTML, content=_page("A"))
    )
    respx.get("https://bad.com/").mock(return_value=httpx.Response(404))
    respx.get("https://c.com/").mock(
        return_value=httpx.Response(200, headers=HTML, content=_page("C"))
    )
    fetcher = HttpxPageFetcher(SETTINGS)
    docs = _run(fetcher.fetch(["https://a.com/", "https://bad.com/", "https://c.com/"]))
    assert len(docs) == 2
    assert {d["title"] for d in docs} == {"A", "C"}
