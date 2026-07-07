"""Executable binding for the web_fetch batch feature files.

Covers src/memagent/web/fetch.py (URL filter + HttpxPageFetcher) and
src/memagent/web/to_markdown.py (trafilatura gating). Every fetch scenario drives
the REAL httpx path with respx interception; every markdown scenario drives the
REAL to_markdown() with trafilatura.extract monkeypatched (pinning OUR gating, not
trafilatura's extraction quality). Steps are sync (pytest-bdd generates sync tests)
and wrap coroutines in asyncio.run. The shared `settings` fixture (conftest) supplies
WAIT_CAP_SCALE=0 so the production fetch-retry path retries instantly.
"""

import asyncio

import httpx
import respx
from pytest_bdd import given, scenarios, then, when

import memagent.web.to_markdown as tm
from memagent.utils.errors import PageFetchError
from memagent.web.fetch import (
    HttpxPageFetcher,
    _extract_title,
    _is_private_host,
    _is_safe_fetch_target,
    _registrable_domain,
    filter_urls,
)

scenarios("features/web_fetch.feature")
scenarios("features/web_to_markdown.feature")

HTML_HEADERS = {"content-type": "text/html"}
PRECISION_KWARGS = {
    "output_format": "markdown",
    "include_tables": True,
    "include_links": False,
    "favor_precision": True,
}


def _page(title: str) -> bytes:
    """A body substantial enough that trafilatura yields non-empty markdown (>= 200 chars)."""
    body = (
        "Redis vector search uses cosine similarity over embeddings stored in a FLAT index. "
        "This paragraph is deliberately long enough that the markdown extractor produces a "
        "non-empty document instead of discarding the page as boilerplate or too short."
    )
    return (
        f"<html><head><title>{title}</title></head>"
        f"<body><article><h1>{title}</h1><p>{body}</p></article></body></html>"
    ).encode()


# ---------------------------------------------------------------------------
# _registrable_domain
# ---------------------------------------------------------------------------
@given("hosts with sub-domains, mixed case and a bare single label", target_fixture="rd_hosts")
def _rd_hosts():
    return ["www.sub.Example.COM", "example.com.", "localhost"]


@when("the registrable domain is computed for each host", target_fixture="rd_results")
def _rd_compute(rd_hosts):
    return [_registrable_domain(h) for h in rd_hosts]


@then("a multi-label host keeps only its last two labels")
def _rd_multi(rd_results):
    assert rd_results[0] == "example.com"


@then("the result is lower-cased with any trailing dot removed")
def _rd_normalized(rd_results):
    assert rd_results[0] == "example.com"  # mixed-case input lower-cased
    assert rd_results[1] == "example.com"  # trailing dot stripped


@then("a single-label host is returned unchanged")
def _rd_single(rd_results):
    assert rd_results[2] == "localhost"


@given(
    "two hosts belonging to different organisations under the co.uk public suffix",
    target_fixture="rd_hosts",
)
def _rd_compound_hosts():
    # Compound ccTLD: without the three-label rule both would collapse to "co.uk" and the
    # per-domain diversity cap would treat these unrelated organisations as one site.
    return ["bbc.co.uk", "www.guardian.co.uk"]


@then("each host keeps three labels and the two organisations stay distinct")
def _rd_compound(rd_results):
    assert rd_results == ["bbc.co.uk", "guardian.co.uk"]
    assert rd_results[0] != rd_results[1]


# ---------------------------------------------------------------------------
# _is_private_host
# ---------------------------------------------------------------------------
@given(
    "a mix of localhost, private, loopback, link-local and public hosts",
    target_fixture="ph_hosts",
)
def _ph_hosts():
    return {
        "localhost": True,
        "127.0.0.1": True,
        "10.0.0.5": True,
        "192.168.1.1": True,
        "169.254.169.254": True,
        "::1": True,
        "8.8.8.8": False,
        "example.com": False,
    }


@when("each host is tested against the private-host guard", target_fixture="ph_results")
def _ph_test(ph_hosts, monkeypatch):
    # No real DNS: the one hostname in the set ("example.com") "resolves" to a public
    # address so the resolving guard leaves it unflagged offline.
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    return {host: _is_private_host(host) for host in ph_hosts}


@given(
    "a hostname whose DNS record resolves to a private address",
    target_fixture="rebind_host",
)
def _rebind_host(monkeypatch):
    # No real DNS: the hostname "resolves" to a loopback address, exercising the
    # hostname->private-IP SSRF vector without touching the network.
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    return "internal.attacker.example"


@when(
    "the resolving hostname is tested against the private-host guard",
    target_fixture="rebind_verdict",
)
def _rebind_test(rebind_host):
    return _is_private_host(rebind_host)


@then("the resolving hostname is flagged private")
def _rebind_flagged(rebind_verdict):
    assert rebind_verdict is True


@then("localhost and the private, loopback and link-local IP literals are flagged private")
def _ph_private(ph_hosts, ph_results):
    private = [h for h, expected in ph_hosts.items() if expected]
    assert private  # guard against a vacuous pass
    for host in private:
        assert ph_results[host] is True, host


@then("a public IP and an unresolved hostname are not flagged")
def _ph_public(ph_results):
    assert ph_results["8.8.8.8"] is False
    assert ph_results["example.com"] is False  # resolves (mocked) to a public IP


# ---------------------------------------------------------------------------
# filter_urls (shared When)
# ---------------------------------------------------------------------------
@given(
    "a list of candidate URLs mixing https, http, ftp, file, data and a private IP",
    target_fixture="fu_urls",
)
def _fu_schemes():
    return [
        "https://example.com/a",
        "http://good.org/b",
        "ftp://example.com/c",
        "file:///etc/passwd",
        "data:text/html,<h1>x</h1>",
        "http://127.0.0.1/x",
    ]


@given(
    "three URLs on one domain, a youtube.com URL and one URL on another domain",
    target_fixture="fu_urls",
)
def _fu_diversity():
    return [
        "https://ex.com/1",
        "https://ex.com/2",
        "https://ex.com/3",
        "https://youtube.com/watch?v=abc",
        "https://other.com/z",
    ]


@when("the URLs are filtered for the fetch stage", target_fixture="fu_kept")
def _fu_filter(fu_urls, settings):
    return filter_urls(fu_urls, settings)


@then("only the http and https public URLs survive")
def _fu_survive(fu_kept):
    assert fu_kept == ["https://example.com/a", "http://good.org/b"]


@then("the ftp, file, data and private-host URLs are dropped")
def _fu_dropped(fu_kept):
    for dropped in (
        "ftp://example.com/c",
        "file:///etc/passwd",
        "data:text/html,<h1>x</h1>",
        "http://127.0.0.1/x",
    ):
        assert dropped not in fu_kept


@then("the youtube.com URL is dropped")
def _fu_denylist(fu_kept):
    assert not any("youtube.com" in url for url in fu_kept)


@then("at most two URLs from the repeated domain survive in their original order")
def _fu_cap(fu_kept):
    assert [url for url in fu_kept if url.startswith("https://ex.com/")] == [
        "https://ex.com/1",
        "https://ex.com/2",
    ]


@then("the other-domain URL survives")
def _fu_other(fu_kept):
    assert "https://other.com/z" in fu_kept


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------
@given("HTML whose title carries an entity and collapsible whitespace", target_fixture="et_ctx")
def _et_ctx():
    return {
        "with_title": "<html><head><title>Redis &amp;   Vector\n Search</title></head></html>",
        "no_title": "<html><head></head><body>no title element here</body></html>",
        "long_title": "<html><head><title>" + ("A" * 400) + "</title></head></html>",
        "fallback": "https://fallback.example/page",
    }


@when("the title is extracted with a fallback identifier", target_fixture="et_results")
def _et_extract(et_ctx):
    fb = et_ctx["fallback"]
    return {
        "with": _extract_title(et_ctx["with_title"], fb),
        "none": _extract_title(et_ctx["no_title"], fb),
        "long": _extract_title(et_ctx["long_title"], fb),
    }


@then("the entity is unescaped and the whitespace collapsed")
def _et_unescaped(et_results):
    assert et_results["with"] == "Redis & Vector Search"


@then("a titleless document falls back to the provided identifier")
def _et_fallback(et_results):
    assert et_results["none"] == "https://fallback.example/page"


@then("an over-long title is truncated to 300 characters")
def _et_truncated(et_results):
    assert len(et_results["long"]) == 300


# ---------------------------------------------------------------------------
# HttpxPageFetcher.__init__
# ---------------------------------------------------------------------------
@given("the default web settings")
def _default_web_settings():
    return None  # the conftest `settings` fixture supplies the values


@when("a page fetcher is constructed", target_fixture="init_probe")
def _construct(settings):
    fetcher = HttpxPageFetcher(settings)
    probe = {
        "client_type": type(fetcher._client),
        "follow_redirects": fetcher._client.follow_redirects,
        "user_agent": fetcher._client.headers.get("user-agent"),
        "sem_value": fetcher._semaphore._value,
        "concurrency": settings.fetch_concurrency,
    }
    asyncio.run(fetcher._client.aclose())
    return probe


@then(
    "its httpx client does not auto-follow redirects and sends the memagent "
    "User-Agent carrying a URL"
)
def _init_client(init_probe):
    assert init_probe["client_type"] is httpx.AsyncClient
    assert init_probe["follow_redirects"] is False  # followed manually so each hop is re-checked
    ua = init_probe["user_agent"]
    assert ua and "memagent" in ua and "http" in ua


@then("the concurrency semaphore is sized to FETCH_CONCURRENCY")
def _init_semaphore(init_probe):
    assert init_probe["sem_value"] == init_probe["concurrency"] == 5


# ---------------------------------------------------------------------------
# _is_safe_fetch_target (SSRF guard re-run on every redirect hop)
# ---------------------------------------------------------------------------
@given(
    "a public https URL, a loopback URL, a link-local metadata URL and a file URL",
    target_fixture="ssrf_targets",
)
def _ssrf_targets():
    return {
        "public": "https://example.com/page",
        "loopback": "http://127.0.0.1/admin",
        "metadata": "http://169.254.169.254/latest/meta-data/",
        "file": "file:///etc/passwd",
    }


@when("each URL is tested against the SSRF fetch-target guard", target_fixture="ssrf_verdicts")
def _ssrf_check(ssrf_targets):
    return {name: _is_safe_fetch_target(url) for name, url in ssrf_targets.items()}


@then("only the public https URL is judged safe to fetch")
def _ssrf_public_safe(ssrf_verdicts):
    assert ssrf_verdicts["public"] is True


@then("the loopback, metadata and file URLs are rejected")
def _ssrf_private_rejected(ssrf_verdicts):
    assert ssrf_verdicts["loopback"] is False
    assert ssrf_verdicts["metadata"] is False
    assert ssrf_verdicts["file"] is False


@given("a URL that 302-redirects to a link-local metadata address", target_fixture="fetch_plan")
def _plan_ssrf_redirect():
    def register(router):
        return router.get("https://lure.example/").mock(
            return_value=httpx.Response(
                302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
            )
        )

    return {"register": register, "target": "https://lure.example/"}


# ---------------------------------------------------------------------------
# HttpxPageFetcher._fetch_one (shared When "the page is fetched")
# ---------------------------------------------------------------------------
@given("a URL that 301-redirects to a final page", target_fixture="fetch_plan")
def _plan_redirect():
    def register(router):
        router.get("https://start.example/").mock(
            return_value=httpx.Response(301, headers={"location": "https://final.example/page"})
        )
        return router.get("https://final.example/page").mock(
            return_value=httpx.Response(200, headers=HTML_HEADERS, content=_page("Final"))
        )

    return {"register": register, "target": "https://start.example/"}


@given("a URL that times out once and then returns HTML", target_fixture="fetch_plan")
def _plan_retry():
    def register(router):
        return router.get("https://slow.example/").mock(
            side_effect=[
                httpx.ReadTimeout("slow"),
                httpx.Response(200, headers=HTML_HEADERS, content=_page("Slow")),
            ]
        )

    return {"register": register, "target": "https://slow.example/"}


@given("a response body larger than FETCH_MAX_BYTES", target_fixture="fetch_plan")
def _plan_oversize(settings):
    big = b"x" * (settings.fetch_max_bytes + 10)

    def register(router):
        return router.get("https://big.example/").mock(
            return_value=httpx.Response(200, headers=HTML_HEADERS, content=big)
        )

    return {"register": register, "target": "https://big.example/"}


@given("a response whose content type is application/pdf", target_fixture="fetch_plan")
def _plan_pdf():
    def register(router):
        return router.get("https://doc.example/").mock(
            return_value=httpx.Response(
                200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4"
            )
        )

    return {"register": register, "target": "https://doc.example/"}


@given("a URL that returns 404", target_fixture="fetch_plan")
def _plan_404():
    def register(router):
        return router.get("https://missing.example/").mock(return_value=httpx.Response(404))

    return {"register": register, "target": "https://missing.example/"}


@when("the page is fetched", target_fixture="fetch_one_result")
def _when_fetch_one(fetch_plan, settings):
    result: dict = {}
    with respx.mock(assert_all_called=False) as router:
        route = fetch_plan["register"](router)
        fetcher = HttpxPageFetcher(settings)

        async def _run():
            try:
                result["doc"] = await fetcher._fetch_one(fetch_plan["target"])
                result["error"] = None
            except Exception as exc:  # noqa: BLE001 — captured for the Then assertions
                result["doc"] = None
                result["error"] = exc
            await fetcher._client.aclose()

        asyncio.run(_run())
        result["call_count"] = route.call_count
    return result


@then("the FetchedDoc records the final resolved URL")
def _then_final_url(fetch_one_result):
    doc = fetch_one_result["doc"]
    assert doc is not None and doc["url"] == "https://final.example/page"


@then("the transport is called twice")
def _then_called_twice(fetch_one_result):
    assert fetch_one_result["call_count"] == 2


@then("a usable FetchedDoc is produced")
def _then_usable_doc(fetch_one_result):
    doc = fetch_one_result["doc"]
    assert doc is not None and doc["ok"] is True and doc["markdown"]


@then("the page is skipped and yields no document")
def _then_skipped(fetch_one_result):
    assert fetch_one_result["doc"] is None
    assert fetch_one_result["error"] is None  # skipped, not raised


@then("a PageFetchError is raised")
def _then_pagefetcherror(fetch_one_result):
    assert isinstance(fetch_one_result["error"], PageFetchError)


@then("the transport is called exactly once")
def _then_called_once(fetch_one_result):
    assert fetch_one_result["call_count"] == 1


# ---------------------------------------------------------------------------
# HttpxPageFetcher._fetch_guarded
# ---------------------------------------------------------------------------
@given("one URL that returns 404 and one healthy URL", target_fixture="guarded_plan")
def _plan_guarded():
    def register(router):
        router.get("https://bad.example/").mock(return_value=httpx.Response(404))
        router.get("https://ok.example/").mock(
            return_value=httpx.Response(200, headers=HTML_HEADERS, content=_page("OK"))
        )

    return {"register": register, "bad": "https://bad.example/", "good": "https://ok.example/"}


@when("each is fetched through the guarded per-URL path", target_fixture="guarded_result")
def _when_guarded(guarded_plan, settings):
    with respx.mock(assert_all_called=False) as router:
        guarded_plan["register"](router)
        fetcher = HttpxPageFetcher(settings)

        async def _run():
            bad = await fetcher._fetch_guarded(guarded_plan["bad"])
            good = await fetcher._fetch_guarded(guarded_plan["good"])
            await fetcher._client.aclose()
            return {"bad": bad, "good": good}

        return asyncio.run(_run())


@then("the failing URL yields None instead of raising")
def _then_guarded_bad(guarded_result):
    assert guarded_result["bad"] is None


@then("the healthy URL yields a FetchedDoc")
def _then_guarded_good(guarded_result):
    doc = guarded_result["good"]
    assert doc is not None and doc["ok"] is True


# ---------------------------------------------------------------------------
# HttpxPageFetcher.fetch
# ---------------------------------------------------------------------------
@given("three fetchable URLs where the middle one returns 404", target_fixture="fetch_many_plan")
def _plan_three():
    def register(router):
        router.get("https://one.example/").mock(
            return_value=httpx.Response(200, headers=HTML_HEADERS, content=_page("One"))
        )
        router.get("https://mid.example/").mock(return_value=httpx.Response(404))
        router.get("https://three.example/").mock(
            return_value=httpx.Response(200, headers=HTML_HEADERS, content=_page("Three"))
        )

    return {
        "register": register,
        "urls": [
            "https://one.example/",
            "https://mid.example/",
            "https://three.example/",
        ],
    }


@when("the fetcher fetches all three", target_fixture="fetch_many_result")
def _when_fetch_three(fetch_many_plan, settings):
    with respx.mock(assert_all_called=False) as router:
        fetch_many_plan["register"](router)
        fetcher = HttpxPageFetcher(settings)

        async def _run():
            docs = await fetcher.fetch(fetch_many_plan["urls"])
            await fetcher._client.aclose()
            return docs

        return asyncio.run(_run())


@then("two FetchedDocs are returned for the healthy URLs")
def _then_two_docs(fetch_many_result):
    assert len(fetch_many_result) == 2
    assert {doc["title"] for doc in fetch_many_result} == {"One", "Three"}


@then("the failed URL contributes no document")
def _then_no_failed(fetch_many_result):
    assert all("mid.example" not in doc["url"] for doc in fetch_many_result)


@given("two URLs that both return 404", target_fixture="fetch_all_fail_plan")
def _plan_all_fail():
    def register(router):
        router.get("https://a1.example/").mock(return_value=httpx.Response(404))
        router.get("https://a2.example/").mock(return_value=httpx.Response(404))

    return {"register": register, "urls": ["https://a1.example/", "https://a2.example/"]}


@when("the fetcher fetches them", target_fixture="fetch_all_fail_result")
def _when_fetch_all_fail(fetch_all_fail_plan, settings):
    with respx.mock(assert_all_called=False) as router:
        fetch_all_fail_plan["register"](router)
        fetcher = HttpxPageFetcher(settings)

        async def _run():
            docs = await fetcher.fetch(fetch_all_fail_plan["urls"])
            await fetcher._client.aclose()
            return docs

        return asyncio.run(_run())


@then("no FetchedDocs are returned")
def _then_empty(fetch_all_fail_result):
    assert fetch_all_fail_result == []


# ---------------------------------------------------------------------------
# to_markdown gating (trafilatura.extract monkeypatched)
# ---------------------------------------------------------------------------
@given(
    "a trafilatura extractor that records its keyword arguments and returns usable markdown",
    target_fixture="tm_ctx",
)
def _tm_record(monkeypatch):
    calls: list[dict] = []

    def fake_extract(html, **kwargs):
        calls.append(kwargs)
        return "x" * 500

    monkeypatch.setattr(tm.trafilatura, "extract", fake_extract)
    return {"calls": calls}


@given(
    "a trafilatura extractor that is empty on precision but non-empty on recall",
    target_fixture="tm_ctx",
)
def _tm_recall(monkeypatch):
    calls: list[dict] = []

    def fake_extract(html, **kwargs):
        calls.append(kwargs)
        return None if kwargs.get("favor_precision") else "y" * 500

    monkeypatch.setattr(tm.trafilatura, "extract", fake_extract)
    return {"calls": calls}


@given(
    "a trafilatura extractor returning fewer than the minimum characters",
    target_fixture="tm_ctx",
)
def _tm_floor(monkeypatch):
    monkeypatch.setattr(tm.trafilatura, "extract", lambda html, **kw: "z" * 199)
    return {}


@given(
    "a trafilatura extractor returning far more than the maximum characters",
    target_fixture="tm_ctx",
)
def _tm_cap(monkeypatch):
    monkeypatch.setattr(tm.trafilatura, "extract", lambda html, **kw: "z" * 25_000)
    return {}


@given(
    "a trafilatura extractor that is empty on both precision and recall",
    target_fixture="tm_ctx",
)
def _tm_empty(monkeypatch):
    monkeypatch.setattr(tm.trafilatura, "extract", lambda html, **kw: None)
    return {}


@when("the HTML is converted to markdown", target_fixture="tm_result")
def _tm_convert(tm_ctx, settings):
    return tm.to_markdown("<html><body>content</body></html>", settings)


@then("the precision-first keyword arguments are used exactly once")
def _tm_kwargs(tm_ctx):
    assert tm_ctx["calls"] == [PRECISION_KWARGS]


@then("the extracted markdown is returned")
def _tm_extracted(tm_result):
    assert tm_result == "x" * 500


@then("a second call is made with favor_recall enabled")
def _tm_recall_call(tm_ctx):
    assert len(tm_ctx["calls"]) == 2
    assert tm_ctx["calls"][1]["favor_recall"] is True
    assert "favor_precision" not in tm_ctx["calls"][1]


@then("the recall markdown is returned")
def _tm_recall_result(tm_result):
    assert tm_result == "y" * 500


@then("no markdown is returned")
def _tm_none(tm_result):
    assert tm_result is None


@then("the returned markdown is truncated to the configured maximum length")
def _tm_truncated(tm_result, settings):
    assert tm_result is not None
    assert len(tm_result) == settings.max_markdown_chars
