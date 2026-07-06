"""ingest_content resilience branches, untested before M7 (specs/003 I2, FR-M3-22/26/27).

Persistence NEVER gates answering: the summary input is capped at 6000 chars, a summary-LLM
failure is swallowed (chunks still flow), and a store failure is swallowed (chunks still flow).
Driven on a normal miss (not fresh, not skip_store) with in-memory fakes — no Redis, no network.
"""

import asyncio

from memagent.config import Settings
from memagent.interfaces import CompletionResult
from memagent.nodes.ingest import SUMMARY_INPUT_CHARS, make_ingest_content
from memagent.resources import AgentResources
from memagent.security.sanitizer import sanitize

S = Settings(_env_file=None)
LONG_MARKDOWN = "word " * 2000  # 10000 chars, well over SUMMARY_INPUT_CHARS (6000)


def _run(coro):
    return asyncio.run(coro)


class FakeEmbedder:
    dim = 1536

    async def embed(self, texts):
        return [[0.0] * self.dim for _ in texts]


class FakeMemory:
    def __init__(self, store_exc=None):
        self._store_exc = store_exc

    async def is_fresh(self, h):
        return False  # force the full ingest path

    async def store(self, **kw):
        if self._store_exc:
            raise self._store_exc
        return ["chunk:x:0"]


class CapturingSummaryLLM:
    def __init__(self, exc=None):
        self.exc = exc
        self.captured = None

    async def complete(self, system, messages):
        self.captured = messages[0]["content"]
        if self.exc:
            raise self.exc
        return CompletionResult(
            text="a summary", usage={"input_tokens": 1, "output_tokens": 1, "model": "fake"}
        )


def _resources(analytics_llm, memory):
    return AgentResources(
        settings=S,
        memory=memory,
        embedder=FakeEmbedder(),
        chat_llm=None,
        analytics_llm=analytics_llm,
        searcher=None,
        fetcher=None,
        turn_logger=None,
    )


def _state():
    doc = {
        "url": "https://redis.io/x",
        "title": "Redis",
        "markdown": LONG_MARKDOWN,
        "summary": None,
        "ok": True,
    }
    return {"query": "how does redis work", "fetched_docs": [doc]}


def test_summary_input_is_capped_at_6000_chars():
    llm = CapturingSummaryLLM()
    _run(make_ingest_content(_resources(llm, FakeMemory()))(_state()))
    clean = sanitize(LONG_MARKDOWN)[0]
    assert llm.captured == clean[:SUMMARY_INPUT_CHARS]  # exact prefix, never the full 10k page
    assert len(llm.captured) == 6000


def test_summary_failure_is_tolerated_and_chunks_still_flow():
    llm = CapturingSummaryLLM(exc=RuntimeError("summary boom"))
    out = _run(make_ingest_content(_resources(llm, FakeMemory()))(_state()))
    assert out["chunks"]  # chunking ran despite the summary failure
    assert out["fetched_docs"][0]["summary"] is None
    assert any(
        e["node"] == "ingest_content" and "summary failed" in e["detail"] for e in out["errors"]
    )


def test_store_failure_is_tolerated_and_chunks_still_flow():
    memory = FakeMemory(store_exc=RuntimeError("store boom"))
    out = _run(make_ingest_content(_resources(CapturingSummaryLLM(), memory))(_state()))
    assert out["chunks"]  # the in-hand answer keeps its context
    assert out["stored_chunk_ids"] == []  # nothing persisted
    assert any(
        e["node"] == "ingest_content" and "store failed" in e["detail"] for e in out["errors"]
    )
