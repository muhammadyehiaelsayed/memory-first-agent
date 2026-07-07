"""Executable binding for the web-path graph nodes (batch: nodes_web_path).

Covers make_web_search / make_fetch_pages / make_ingest_content by calling each
node factory's async closure directly with a hand-built state dict and local
fakes, then asserting the returned state delta (the nodes are async state->state
functions, so every When wraps the coroutine in asyncio.run). Fully keyless: the
three nodes here touch no Redis, no network, and no API keys — searcher, fetcher,
memory, embedder and analytics LLM are all local in-memory fakes.
"""

import asyncio

from pytest_bdd import given, parsers, scenarios, then, when

from memagent.config import Settings
from memagent.interfaces import CompletionResult
from memagent.memory.urls import url_hash
from memagent.nodes.fetch import make_fetch_pages
from memagent.nodes.ingest import make_ingest_content
from memagent.nodes.search import make_web_search
from memagent.resources import AgentResources
from memagent.security.sanitizer import sanitize
from memagent.state import FetchedDoc, SearchResult

scenarios("features/nodes_search.feature")
scenarios("features/nodes_fetch.feature")
scenarios("features/nodes_ingest.feature")

# Keyless defaults (no .env): mirrors tests/unit/test_ingest.py's Settings(_env_file=None).
SETTINGS = Settings(_env_file=None)

LONG_MARKDOWN = "word " * 2000  # 10000 chars, well over summary_input_chars (6000)


def _run(coro):
    return asyncio.run(coro)


# ---- local fakes ------------------------------------------------------------
class FakeSearcher:
    """Records (query, k) it was called with; exposes provider_used like FallbackProvider."""

    def __init__(self, results=None, exc=None, provider="tavily"):
        self._results = results or []
        self._exc = exc
        self.provider_used = provider
        self.calls: list[tuple[str, int]] = []

    async def search(self, query, k):
        self.calls.append((query, k))
        if self._exc is not None:
            raise self._exc
        return self._results


class FakeFetcher:
    """Records the exact URL list the node handed it (post filter + top-N)."""

    def __init__(self, exc=None):
        self._exc = exc
        self.received: list[str] | None = None

    async def fetch(self, urls):
        self.received = list(urls)
        if self._exc is not None:
            raise self._exc
        return [FetchedDoc(url=u, title="T", markdown="body", summary=None, ok=True) for u in urls]


class FakeEmbedder:
    dim = 1536

    async def embed(self, texts):
        return [[0.0] * self.dim for _ in texts]


class FakeMemory:
    """Captures is_fresh / store calls so persistence behaviour is observable."""

    def __init__(self, fresh=False, store_exc=None, stored_ids=None):
        self._fresh = fresh
        self._store_exc = store_exc
        self._stored_ids = ["cid:0", "cid:1", "cid:2"] if stored_ids is None else stored_ids
        self.is_fresh_calls = 0
        self.store_calls: list[dict] = []

    async def is_fresh(self, h):
        self.is_fresh_calls += 1
        return self._fresh

    async def store(self, *, page, chunks, vectors, source_query, flags):
        self.store_calls.append(
            {
                "page": page,
                "chunks": chunks,
                "vectors": vectors,
                "source_query": source_query,
                "flags": flags,
            }
        )
        if self._store_exc is not None:
            raise self._store_exc
        return list(self._stored_ids)


class CapturingSummaryLLM:
    """analytics_llm stand-in: captures the summary input; can be made to fail."""

    def __init__(self, text="A grounded summary.", exc=None):
        self._text = text
        self._exc = exc
        self.captured: str | None = None
        self.complete_calls = 0

    async def complete(self, system, messages):
        self.complete_calls += 1
        self.captured = messages[0]["content"]
        if self._exc is not None:
            raise self._exc
        return CompletionResult(
            text=self._text,
            usage={"input_tokens": 1, "output_tokens": 1, "model": "fake"},
        )


def _resources(**over):
    base = dict(
        settings=SETTINGS,
        memory=None,
        embedder=FakeEmbedder(),
        chat_llm=None,
        analytics_llm=None,
        searcher=None,
        fetcher=None,
        turn_logger=None,
    )
    base.update(over)
    return AgentResources(**base)


def _page(url="https://redis.io/persistence", markdown=None):
    return {
        "url": url,
        "title": "Redis Persistence",
        "markdown": markdown or ("Redis persistence explained in detail. " * 20),
        "summary": None,
        "ok": True,
    }


# ============================ web_search node ================================
@given(
    parsers.parse('a searcher that returns three results and reports provider "{prov}"'),
    target_fixture="ctx",
)
def _searcher_ok(prov):
    results = [
        SearchResult(url=f"https://ex{i}.com/a", title=f"t{i}", snippet="s", rank=i)
        for i in range(3)
    ]
    return {"searcher": FakeSearcher(results=results, provider=prov), "expected_results": results}


@given("a searcher that raises a transport error", target_fixture="ctx")
def _searcher_fail():
    return {"searcher": FakeSearcher(exc=RuntimeError("tavily down"), provider=None)}


@given(parsers.parse('a memory-miss turn whose sanitized query is "{query}"'))
def _miss_query(ctx, query):
    ctx["state"] = {"sanitized_query": query, "query": query}


@when("the web search node runs")
def _run_web_search(ctx):
    node = make_web_search(_resources(searcher=ctx["searcher"]))
    ctx["update"] = _run(node(ctx["state"]))


@then("the returned state carries the three search results")
def _three_results(ctx):
    assert ctx["update"]["search_results"] == ctx["expected_results"]
    assert len(ctx["update"]["search_results"]) == 3


@then("the searcher was asked for exactly SEARCH_MAX_RESULTS results for that query")
def _searcher_called(ctx):
    assert SETTINGS.search_max_results == 8
    assert ctx["searcher"].calls == [(ctx["state"]["sanitized_query"], SETTINGS.search_max_results)]


@then(parsers.parse('the state records the search provider as "{prov}"'))
def _provider_recorded(ctx, prov):
    assert ctx["update"]["search_provider"] == prov


@then("the returned state carries no search results")
def _no_results(ctx):
    assert ctx["update"]["search_results"] == []


@then("a web_search error is recorded on the turn")
def _websearch_error(ctx):
    errors = ctx["update"]["errors"]
    assert any(e["node"] == "web_search" for e in errors)
    assert errors[0]["error_type"] == "RuntimeError"


@then("the state records no search provider")
def _no_provider(ctx):
    assert ctx["update"]["search_provider"] is None


# ============================ fetch_pages node ===============================
@given("search results for six public domains plus one loopback address", target_fixture="ctx")
def _fetch_urls():
    public = [f"https://pub{i}.com/page" for i in range(6)]
    loopback = "http://127.0.0.1/admin"
    urls = public + [loopback]
    state = {
        "search_results": [
            SearchResult(url=u, title="t", snippet="s", rank=i) for i, u in enumerate(urls)
        ]
    }
    return {"state": state, "public": public, "loopback": loopback, "fetcher": FakeFetcher()}


@given("FETCH_TOP_N is 5")
def _fetch_top_n(ctx):
    assert SETTINGS.fetch_top_n == 5


@given("search results with one fetchable URL", target_fixture="ctx")
def _fetch_one_url():
    state = {
        "search_results": [SearchResult(url="https://pub.com/a", title="t", snippet="s", rank=0)]
    }
    return {"state": state}


@given("a fetcher that raises on every call")
def _fetcher_raises(ctx):
    ctx["fetcher"] = FakeFetcher(exc=RuntimeError("network gone"))


@when("the fetch pages node runs")
def _run_fetch(ctx):
    node = make_fetch_pages(_resources(fetcher=ctx["fetcher"]))
    ctx["update"] = _run(node(ctx["state"]))


@then("the loopback address is never handed to the fetcher")
def _no_loopback(ctx):
    assert ctx["loopback"] not in ctx["fetcher"].received


@then("exactly five URLs are handed to the fetcher")
def _five_fetched(ctx):
    assert ctx["fetcher"].received == ctx["public"][:5]


@then("a fetched document is returned for each fetched URL")
def _docs_returned(ctx):
    docs = ctx["update"]["fetched_docs"]
    assert [d["url"] for d in docs] == ctx["public"][:5]


@then("the returned state carries no fetched documents")
def _no_docs(ctx):
    assert ctx["update"]["fetched_docs"] == []


@then("a fetch_pages error is recorded on the turn")
def _fetch_error(ctx):
    errors = ctx["update"]["errors"]
    assert any(e["node"] == "fetch_pages" for e in errors)
    assert errors[0]["error_type"] == "RuntimeError"


# ============================ ingest_content node ============================
@given("a fetched page and an empty memory that accepts stores", target_fixture="ctx")
def _ingest_normal():
    doc = _page()
    return {
        "memory": FakeMemory(fresh=False, stored_ids=["cid:0", "cid:1", "cid:2"]),
        "llm": CapturingSummaryLLM(text="A grounded summary."),
        "doc": doc,
        "state": {"query": "how does redis persist data", "fetched_docs": [doc]},
    }


@given("a fetched page far larger than the summary input cap", target_fixture="ctx")
def _ingest_long():
    doc = _page(markdown=LONG_MARKDOWN)
    return {
        "memory": FakeMemory(fresh=False),
        "llm": CapturingSummaryLLM(),
        "doc": doc,
        "state": {"query": "big page", "fetched_docs": [doc]},
    }


@given("a fetched page and a summariser that fails", target_fixture="ctx")
def _ingest_summary_fail():
    doc = _page()
    return {
        "memory": FakeMemory(fresh=False),
        "llm": CapturingSummaryLLM(exc=RuntimeError("summary boom")),
        "doc": doc,
        "state": {"query": "q", "fetched_docs": [doc]},
    }


@given("a fetched page and a memory whose store fails", target_fixture="ctx")
def _ingest_store_fail():
    doc = _page()
    return {
        "memory": FakeMemory(fresh=False, store_exc=RuntimeError("store boom")),
        "llm": CapturingSummaryLLM(),
        "doc": doc,
        "state": {"query": "q", "fetched_docs": [doc]},
    }


@given("a fetched page on a turn that must not persist", target_fixture="ctx")
def _ingest_skip():
    doc = _page()
    return {
        "memory": FakeMemory(fresh=False),
        "llm": CapturingSummaryLLM(text="A summary."),
        "doc": doc,
        "state": {"query": "q", "fetched_docs": [doc], "skip_store": True},
    }


@given("a fetched page already ingested within the freshness window", target_fixture="ctx")
def _ingest_fresh():
    doc = _page()
    return {
        "memory": FakeMemory(fresh=True),
        "llm": CapturingSummaryLLM(),
        "doc": doc,
        "state": {"query": "q", "fetched_docs": [doc]},
    }


@given("a fetched page whose chunker raises", target_fixture="ctx")
def _ingest_chunk_fail(monkeypatch):
    import memagent.nodes.ingest as ingest_mod

    def boom(*args, **kwargs):
        raise RuntimeError("chunk boom")

    # chunk_markdown() runs inside the per-doc guard, so a chunker blow-up degrades the page.
    monkeypatch.setattr(ingest_mod, "chunk_markdown", boom)
    doc = _page()
    return {
        "memory": FakeMemory(fresh=False),
        "llm": CapturingSummaryLLM(),
        "doc": doc,
        "state": {"query": "q", "fetched_docs": [doc]},
    }


@when("the ingest content node runs")
def _run_ingest(ctx):
    node = make_ingest_content(_resources(memory=ctx["memory"], analytics_llm=ctx["llm"]))
    ctx["update"] = _run(node(ctx["state"]))


@then("the page content is stored as chunks for future reuse")
def _stored(ctx):
    assert ctx["memory"].store_calls, "store was never called"
    assert ctx["update"]["stored_chunk_ids"] == ["cid:0", "cid:1", "cid:2"]
    assert ctx["update"]["chunks"]


@then("the stored chunk ids are keyed by the canonical URL hash")
def _chunk_ids_hashed(ctx):
    h = url_hash(ctx["doc"]["url"])
    chunks = ctx["update"]["chunks"]
    assert chunks
    assert all(c["chunk_id"].startswith(f"{h}:") for c in chunks)


@then("the enriched page carries its summary and sanitizer flags")
def _enriched(ctx):
    out_doc = ctx["update"]["fetched_docs"][0]
    assert out_doc["summary"] == "A grounded summary."
    assert out_doc["sanitizer_flags"] == []


@then("the summary embedding is stored ahead of the chunk embeddings")
def _summary_vector_first(ctx):
    call = ctx["memory"].store_calls[0]
    # vectors == [summary] + chunk_texts -> exactly one more vector than chunks
    assert len(call["vectors"]) == len(call["chunks"]) + 1
    assert call["source_query"] == "how does redis persist data"
    assert call["flags"] == []


@then("the summariser receives only the first 6000 characters of the sanitized page")
def _summary_capped(ctx):
    clean = sanitize(LONG_MARKDOWN)[0]
    assert ctx["llm"].captured == clean[: SETTINGS.summary_input_chars]
    assert len(ctx["llm"].captured) == SETTINGS.summary_input_chars == 6000


@then("the chunks are still produced from the sanitized markdown")
def _chunks_still(ctx):
    assert ctx["update"]["chunks"]


@then("the page summary is left empty")
def _summary_none(ctx):
    assert ctx["update"]["fetched_docs"][0]["summary"] is None


@then("a summary failure is recorded on the turn")
def _summary_error(ctx):
    assert any(
        e["node"] == "ingest_content" and "summary failed" in e["detail"]
        for e in ctx["update"]["errors"]
    )


@then("nothing is persisted")
def _nothing_persisted(ctx):
    assert ctx["update"]["stored_chunk_ids"] == []


@then("a store failure is recorded on the turn")
def _store_error(ctx):
    assert any(
        e["node"] == "ingest_content" and "store failed" in e["detail"]
        for e in ctx["update"]["errors"]
    )


@then("the memory store is never called")
def _store_not_called(ctx):
    assert ctx["memory"].store_calls == []
    assert ctx["update"]["stored_chunk_ids"] == []


@then("the in-hand chunks are still available for answering")
def _chunks_available(ctx):
    assert ctx["update"]["chunks"]


@then("the freshness gate was consulted for the page")
def _fresh_checked(ctx):
    assert ctx["memory"].is_fresh_calls == 1


@then("no summary is requested and nothing is re-stored")
def _fresh_skip(ctx):
    assert ctx["llm"].complete_calls == 0
    assert ctx["memory"].store_calls == []
    assert ctx["update"]["stored_chunk_ids"] == []


@then("the page is still chunked for the in-hand answer")
def _fresh_chunks(ctx):
    assert ctx["update"]["chunks"]


@then("the turn still returns with the page skipped and an ingest failure recorded")
def _ingest_degraded(ctx):
    update = ctx["update"]
    assert update["fetched_docs"]  # turn returned normally, no exception propagated
    assert update["chunks"] == []  # nothing chunked for the failed doc
    assert update["stored_chunk_ids"] == []
    assert any(
        e["node"] == "ingest_content" and "ingest failed" in e["detail"] for e in update["errors"]
    )
