"""Executable binding for the memory-first path node features.

Covers nodes/embed.py, nodes/memory.py, nodes/answer.py. Graph nodes are async
state->state factories: we build a frozen AgentResources with local fakes for the
one dependency each scenario exercises, call the node directly with a hand-built
state dict via asyncio.run(...), and assert on the returned state delta. No graph
compilation, no Redis, no network (this batch is redis_ok=false).
"""

import asyncio
import re

from pytest_bdd import given, parsers, scenarios, then, when

from memagent.interfaces import CompletionResult
from memagent.nodes.answer import (
    FAILURE_APOLOGY,
    LOW_CONFIDENCE_DISCLAIMER,
    _dedupe_sources,
    make_answer_failure,
    make_answer_from_memory,
    make_answer_from_web,
)
from memagent.nodes.embed import make_embed_query
from memagent.nodes.memory import make_memory_search
from memagent.resources import AgentResources
from memagent.utils.errors import MemoryUnavailableError

scenarios("features/nodes_embed.feature")
scenarios("features/nodes_memory.feature")
scenarios("features/nodes_answer.feature")


# ---- helpers ----------------------------------------------------------------
def _resources(settings, *, memory=None, embedder=None, chat_llm=None):
    """Frozen AgentResources with only the fields a node needs; rest are None."""
    return AgentResources(
        settings=settings,
        memory=memory,
        embedder=embedder,
        chat_llm=chat_llm,
        analytics_llm=None,
        searcher=None,
        fetcher=None,
        turn_logger=None,
    )


class _BoomEmbedder:
    dim = 1536

    async def embed(self, texts):
        raise RuntimeError("embedding backend unreachable")


class _FakeStore:
    """Records knn calls; returns canned hits or raises the configured error."""

    def __init__(self, hits=None, raise_exc=None):
        self._hits = hits or []
        self._raise = raise_exc
        self.calls: list[tuple] = []

    async def knn(self, vector, k):
        self.calls.append((vector, k))
        if self._raise is not None:
            raise self._raise
        return self._hits

    async def store(self, *a, **k):
        return []

    async def is_fresh(self, h):
        return False


class _CapturingChat:
    """Captures the last user prompt so the bounded-context rule is observable."""

    def __init__(self):
        self.system = None
        self.prompt = None

    async def complete(self, system, messages):
        self.system = system
        self.prompt = messages[-1]["content"]
        return CompletionResult(
            text="Answer grounded in the provided context.",
            usage={"input_tokens": 1, "output_tokens": 1, "model": "fake"},
        )


def _mem_hit(url, sim, title="Redis vectors"):
    return {
        "doc_id": f"{url}#0",
        "text": "Redis stores L2-normalized vectors and searches them by cosine distance.",
        "url": url,
        "title": title,
        "similarity": sim,
        "stored_at": "2026-01-01T00:00:00+00:00",
        "sanitizer_flags": [],
        "doc_type": "chunk",
    }


# ---- shared parametrized Then steps -----------------------------------------
@then(parsers.parse('the turn is routed "{route}"'))
def _routed(context, route):
    assert context["out"]["route"] == route


@then(parsers.parse('a step error is recorded for the "{node}" node'))
def _step_error(context, node):
    errors = context["out"].get("errors", [])
    assert errors, "expected at least one StepError in the state delta"
    assert any(e["node"] == node for e in errors), f"no StepError for node {node!r}: {errors}"
    err = next(e for e in errors if e["node"] == node)
    assert err["error_type"] and err["detail"]  # populated, not blank


@then("no memory hits are returned")
def _no_hits(context):
    assert context["out"]["memory_hits"] == []


# ============================================================================
# nodes_embed.feature
# ============================================================================
@given("a sanitized query and a working embedding service", target_fixture="context")
def _ctx_embed_ok(settings, fake_embedder):
    return {
        "settings": settings,
        "embedder": fake_embedder,
        "state": {"sanitized_query": "how does redis vector search work"},
    }


@given("a sanitized query but the embedding service is unavailable", target_fixture="context")
def _ctx_embed_fail(settings):
    return {
        "settings": settings,
        "embedder": _BoomEmbedder(),
        "state": {"sanitized_query": "how does redis vector search work"},
    }


@when("the embed_query node runs")
def _run_embed(context):
    res = _resources(context["settings"], embedder=context["embedder"])
    context["out"] = asyncio.run(make_embed_query(res)(context["state"]))


@then("the query vector has 1536 dimensions")
def _vec_dims(context):
    vec = context["out"]["query_vector"]
    assert vec is not None
    assert len(vec) == 1536


@then("no step error is recorded")
def _no_step_error(context):
    assert not context["out"].get("errors")


@then("the query vector is cleared to None")
def _vec_none(context):
    assert context["out"]["query_vector"] is None


# ============================================================================
# nodes_memory.feature
# ============================================================================
@given(
    "a memory store that returns five hits with similarities 0.9, 0.8, 0.5, 0.4, 0.2",
    target_fixture="context",
)
def _ctx_mem_five(settings):
    hits = [_mem_hit(f"https://ex/{i}", sim) for i, sim in enumerate([0.9, 0.8, 0.5, 0.4, 0.2])]
    return {
        "settings": settings,
        "store": _FakeStore(hits=hits),
        "state": {"query_vector": [0.1] * 1536},
    }


@given("a memory store with an empty index", target_fixture="context")
def _ctx_mem_empty(settings):
    return {
        "settings": settings,
        "store": _FakeStore(hits=[]),
        "state": {"query_vector": [0.1] * 1536},
    }


@given("a memory store whose Redis backend is unreachable", target_fixture="context")
def _ctx_mem_down(settings):
    return {
        "settings": settings,
        "store": _FakeStore(raise_exc=MemoryUnavailableError("redis exhausted its retries")),
        "state": {"query_vector": [0.1] * 1536},
    }


@when("the memory_search node runs")
def _run_memory(context):
    res = _resources(context["settings"], memory=context["store"])
    context["out"] = asyncio.run(make_memory_search(res)(context["state"]))


@then("all five hits are kept in state")
def _five_hits(context):
    assert len(context["out"]["memory_hits"]) == 5


@then("top_similarity equals 0.9")
def _top_sim_high(context):
    assert context["out"]["top_similarity"] == 0.9


@then("knn was called exactly once with k equal to MEMORY_TOP_K")
def _knn_once(context):
    calls = context["store"].calls
    assert len(calls) == 1
    vector, k = calls[0]
    assert k == context["settings"].memory_top_k == 5
    assert vector == context["state"]["query_vector"]


@then("top_similarity is None")
def _top_sim_none(context):
    assert context["out"]["top_similarity"] is None


@then(parsers.parse('the turn is marked to skip storing with degradation "{label}"'))
def _skip_store(context, label):
    assert context["out"]["skip_store"] is True
    assert context["out"]["degradation"] == label


# ============================================================================
# nodes_answer.feature
# ============================================================================
@given(
    "three retrieved hits that share one source URL plus one blank-URL hit",
    target_fixture="context",
)
def _ctx_dedupe():
    url = "https://redis.io/docs/vectors"
    hits = [
        {"url": url, "title": "Redis vectors"},
        {"url": url, "title": "Redis vectors (dup)"},
        {"url": "", "title": "blank url, must be skipped"},
        {"url": url, "title": "Redis vectors (dup2)"},
    ]
    return {"hits": hits, "url": url}


@when('the sources are deduplicated with origin "memory"')
def _run_dedupe(context):
    context["sources"] = _dedupe_sources(context["hits"], "memory")


@then('exactly one source reference remains, tagged origin "memory"')
def _one_source(context):
    srcs = context["sources"]
    assert len(srcs) == 1
    assert srcs[0]["url"] == context["url"]
    assert srcs[0]["origin"] == "memory"


@then("the blank-URL hit is dropped")
def _blank_dropped(context):
    assert all(s["url"] for s in context["sources"])


@given("memory holds a hit for a stored page with a URL and title", target_fixture="context")
def _ctx_answer_memory(settings, fake_llm):
    url = "https://redis.io/docs/vectors"
    return {
        "settings": settings,
        "chat": fake_llm,
        "url": url,
        "state": {
            "query": "how does redis store vectors",
            "memory_hits": [_mem_hit(url, 0.87)],
        },
    }


@when("the answer_from_memory node runs")
def _run_answer_memory(context):
    res = _resources(context["settings"], chat_llm=context["chat"])
    context["out"] = asyncio.run(make_answer_from_memory(res)(context["state"]))


@then('the answer cites the stored URL with origin "memory"')
def _cites_memory(context):
    srcs = context["out"]["sources"]
    assert len(srcs) == 1
    assert srcs[0]["origin"] == "memory"
    assert srcs[0]["url"] == context["url"]


@then('the rendered answer ends with a "Sources:" section')
def _ends_sources(context):
    answer = context["out"]["answer"]
    assert re.search(r"(?im)^\s*sources\s*:", answer)
    assert context["url"] in answer


@given("a fetched web page with a summary and four chunks", target_fixture="context")
def _ctx_answer_web(settings):
    url = "https://redis.io/vs"
    chunks = [
        {
            "chunk_id": f"{url}:{i}",
            "text": f"CHUNKBODY{i}",
            "url": url,
            "title": "Redis",
            "chunk_index": i,
        }
        for i in range(4)
    ]
    chat = _CapturingChat()
    return {
        "settings": settings,
        "chat": chat,
        "url": url,
        "state": {
            "query": "how does redis vector search work",
            "fetched_docs": [{"url": url, "title": "Redis", "summary": "the summary", "ok": True}],
            "chunks": chunks,
            "search_results": [],
        },
    }


@given("a web search that returned snippets but no fetchable pages", target_fixture="context")
def _ctx_answer_snippets(settings, fake_llm):
    return {
        "settings": settings,
        "chat": fake_llm,
        "state": {
            "query": "how does redis vector search work",
            "fetched_docs": [],
            "chunks": [],
            "search_results": [
                {"url": "https://ex/1", "title": "T1", "snippet": "snippet one", "rank": 1},
                {"url": "https://ex/2", "title": "T2", "snippet": "snippet two", "rank": 2},
            ],
        },
    }


@when("the answer_from_web node runs")
def _run_answer_web(context):
    res = _resources(context["settings"], chat_llm=context["chat"])
    context["out"] = asyncio.run(make_answer_from_web(res)(context["state"]))


@then("only the first two chunks of the page appear in the answer context")
def _bounded_context(context):
    prompt = context["chat"].prompt
    assert prompt is not None, "the node must call chat_llm.complete with a built prompt"
    assert "CHUNKBODY0" in prompt and "CHUNKBODY1" in prompt  # first per_page=2 included
    assert "CHUNKBODY2" not in prompt and "CHUNKBODY3" not in prompt  # the rest excluded
    assert context["settings"].web_context_chunks_per_page == 2


@then('the web sources are cited with origin "web"')
def _cites_web(context):
    srcs = context["out"]["sources"]
    assert srcs
    assert all(s["origin"] == "web" for s in srcs)


@then(parsers.parse('the degradation is recorded as "{label}"'))
def _degradation_is(context, label):
    assert context["out"]["degradation"] == label


@then("the answer carries a low-confidence disclaimer")
def _has_disclaimer(context):
    assert LOW_CONFIDENCE_DISCLAIMER in context["out"]["answer"]


@given("a chat model spy that must not be called", target_fixture="context")
def _ctx_failure(settings, fake_llm):
    return {"settings": settings, "chat": fake_llm, "state": {}}


@when("the answer_failure node runs on a minimal state")
def _run_failure(context):
    res = _resources(context["settings"], chat_llm=context["chat"])
    # Must tolerate a malformed/empty state and never raise.
    context["out"] = asyncio.run(make_answer_failure(res)(context["state"]))


@then("the answer is the deterministic failure apology")
def _is_apology(context):
    assert context["out"]["answer"] == FAILURE_APOLOGY
    assert context["out"]["sources"] == []


@then("no chat completion was ever requested")
def _no_completion(context):
    assert context["chat"].complete_calls == 0
