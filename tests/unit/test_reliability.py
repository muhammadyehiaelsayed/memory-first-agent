"""M5-owned: retry policy (FR-M5-17/18/19/20/23) + degradation matrix (FR-M5-24..28).

Inline fakes; the OpenAI policy runs through the production llm_retry path with
WAIT_CAP_SCALE=0 (no monkeypatched sleeps). The degradation scenarios drive the real graph
via Agent with fake resources, asserting the designed route/degradation and one record each.
"""

import asyncio
import logging
import pathlib
import time

import httpx
from openai import APIConnectionError, APIStatusError

from memagent.app import Agent
from memagent.config import Settings
from memagent.interfaces import CompletionResult
from memagent.llm.clients import build_openai_clients
from memagent.memory.store import RedisMemoryStore, make_redis_client
from memagent.resources import AgentResources
from memagent.utils.errors import (
    LLMUnavailableError,
    MemoryUnavailableError,
    SearchUnavailableError,
)
from memagent.utils.reliability import llm_retry

SETTINGS0 = Settings(_env_file=None, wait_cap_scale=0.0)
REQ = httpx.Request("POST", "https://api.openai.com/v1/x")
USAGE = {"input_tokens": 1, "output_tokens": 1, "model": "fake"}
CLF = {
    "topic": "t",
    "category": "other",
    "question_type": "other",
    "language": "en",
    "confidence": 0.5,
}


# ============================ OpenAI retry policy ============================
def test_async_openai_built_with_max_retries_zero():
    conv, analytics, embedder = build_openai_clients(Settings(_env_file=None, openai_api_key="x"))
    assert conv._client.max_retries == 0


def test_no_node_module_imports_tenacity():
    nodes_dir = pathlib.Path("src/memagent/nodes")
    offenders = [p.name for p in nodes_dir.glob("*.py") if "tenacity" in p.read_text()]
    assert offenders == [], offenders


def test_transient_errors_retry_to_four_attempts(caplog):
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] <= 3:
            raise APIConnectionError(request=REQ)
        return "ok"

    wrapped = llm_retry(SETTINGS0)(flaky)
    with caplog.at_level(logging.WARNING, logger="memagent.reliability"):
        start = time.perf_counter()
        assert asyncio.run(wrapped()) == "ok"
        elapsed = time.perf_counter() - start
    assert calls["n"] == 4  # 3 failures + 1 success under the 4-attempt policy
    assert elapsed < 1.0  # WAIT_CAP_SCALE=0 → no real sleep
    assert sum(1 for r in caplog.records if r.name == "memagent.reliability") >= 3


def test_auth_error_fast_fails_after_one_call():
    calls = {"n": 0}

    async def auth_fail():
        calls["n"] += 1
        raise APIStatusError("unauthorized", response=httpx.Response(401, request=REQ), body=None)

    wrapped = llm_retry(SETTINGS0)(auth_fail)
    raised = False
    try:
        asyncio.run(wrapped())
    except LLMUnavailableError:
        raised = True
    assert raised
    assert calls["n"] == 1  # 401 is never retried


# ============================ Redis native retry ============================
def test_make_redis_client_has_retry_three():
    client = make_redis_client(SETTINGS0)
    retry = client.connection_pool.connection_kwargs.get("retry")
    assert retry is not None
    assert retry._retries == 3  # 3 retries = 4 total tries


class FakeRedisDown:
    async def hgetall(self, key):
        raise __import__("redis").exceptions.ConnectionError("refused")

    async def hget(self, *a):
        raise __import__("redis").exceptions.ConnectionError("refused")


def test_down_redis_raises_memory_unavailable():
    store = RedisMemoryStore(SETTINGS0, FakeRedisDown())
    page = {"url": "https://x/p", "title": "P", "markdown": "m", "summary": None, "ok": True}
    chunks = [{"chunk_id": "x:0", "text": "t", "url": page["url"], "title": "P", "chunk_index": 0}]
    raised = False
    try:
        asyncio.run(
            store.store(page=page, chunks=chunks, vectors=[[0.1] * 4], source_query="q", flags=[])
        )
    except MemoryUnavailableError:
        raised = True
    assert raised


# ============================ Degradation matrix ============================
class FakeEmbedder:
    dim = 1536

    def __init__(self, fail=False):
        self.fail = fail

    async def embed(self, texts):
        if self.fail:
            raise LLMUnavailableError("embed down")
        return [[0.0] * 1536 for _ in texts]


class FakeChat:
    def __init__(self, complete_fail=False, parse_fail=False):
        self.complete_fail = complete_fail
        self.parse_fail = parse_fail

    async def complete(self, system, messages):
        if self.complete_fail:
            raise LLMUnavailableError("chat down")
        return CompletionResult(text="Grounded answer.", usage=USAGE)

    async def parse(self, system, user, schema):
        if self.parse_fail:
            raise RuntimeError("analytics down")
        return schema(**CLF), USAGE


class FakeSearcher:
    provider_used = "tavily"

    def __init__(self, fail=False, empty=False):
        self.fail = fail
        self.empty = empty

    async def search(self, query, k):
        if self.fail:
            raise SearchUnavailableError("search down")
        return (
            []
            if self.empty
            else [{"url": "https://ex.com/a", "title": "A", "snippet": "s", "rank": 0}]
        )


class FakeFetcher:
    def __init__(self, empty=False):
        self.empty = empty

    async def fetch(self, urls):
        if self.empty:
            return []
        return [
            {
                "url": u,
                "title": "A",
                "markdown": "# A\n\nRedis vector search.",
                "summary": None,
                "ok": True,
            }
            for u in urls
        ]


class FakeMemory:
    def __init__(self, hits=None, down=False, ensure_down=False):
        self.hits = hits or []
        self.down = down
        self.ensure_down = ensure_down
        self.store_calls = 0

    async def ensure_ready(self):
        if self.ensure_down:  # startup Redis outage, before the graph runs (H3)
            raise MemoryUnavailableError("redis down at startup")
        return None

    async def knn(self, vector, k):
        if self.down:
            raise MemoryUnavailableError("redis down")
        return self.hits

    async def store(self, page, chunks, vectors, source_query, flags):
        self.store_calls += 1
        return ["chunk:x:0"]

    async def is_fresh(self, h):
        return False


class FakeLogger:
    def __init__(self):
        self.records = []

    def log(self, record):
        self.records.append(record)


def resources(**kw):
    defaults = dict(
        settings=SETTINGS0,
        memory=FakeMemory(),
        embedder=FakeEmbedder(),
        chat_llm=FakeChat(),
        analytics_llm=FakeChat(),
        searcher=FakeSearcher(),
        fetcher=FakeFetcher(),
        turn_logger=FakeLogger(),
    )
    defaults.update(kw)
    return AgentResources(**defaults)


def run(res, query="How does Redis vector search work?"):
    return asyncio.run(Agent(resources=res).answer(query))


HIT = [
    {
        "doc_id": "d",
        "text": "Redis uses cosine.",
        "url": "https://ex.com/p",
        "title": "P",
        "similarity": 0.8,
        "stored_at": "2026-07-01T00:00:00+00:00",
        "sanitizer_flags": [],
        "doc_type": "chunk",
    }
]


def test_redis_down_degrades_to_web_only():
    res = resources(memory=FakeMemory(down=True))
    result = run(res)
    assert result.route == "degraded_web"
    assert result.degradation == "redis_down"
    assert res.memory.store_calls == 0
    assert len(res.turn_logger.records) == 1


def test_startup_redis_outage_degrades_to_web_not_traceback():
    # H3: ensure_ready fails PRE-graph on a startup outage; test_redis_down_degrades_to_web_only
    # only fails knn() AFTER readiness. The turn must NOT raise to the caller and MUST still run
    # web-only and write exactly one record (no persistence attempted).
    res = resources(memory=FakeMemory(down=True, ensure_down=True))
    result = run(res)  # must not raise
    assert result.route == "degraded_web"
    assert result.degradation == "redis_down"
    assert res.memory.store_calls == 0
    assert len(res.turn_logger.records) == 1


def test_all_fetches_fail_snippets_only():
    res = resources(fetcher=FakeFetcher(empty=True))
    result = run(res)
    assert result.route == "degraded_web"
    assert result.degradation == "snippets_only"


def test_search_down_is_failed():
    res = resources(searcher=FakeSearcher(fail=True))
    result = run(res)
    assert result.route == "failed"
    assert len(res.turn_logger.records) == 1


def test_zero_results_is_failed():
    res = resources(searcher=FakeSearcher(empty=True))
    assert run(res).route == "failed"


def test_chat_llm_down_is_failed():
    res = resources(chat_llm=FakeChat(complete_fail=True))
    result = run(res)
    assert result.route == "failed"
    assert len(res.turn_logger.records) == 1


def test_embeddings_down_is_failed():
    res = resources(embedder=FakeEmbedder(fail=True))
    assert run(res).route == "failed"


def test_analytics_down_leaves_route_and_nulls_analytics():
    res = resources(memory=FakeMemory(hits=HIT), analytics_llm=FakeChat(parse_fail=True))
    result = run(res)
    assert result.route == "memory_hit"
    assert res.turn_logger.records[0]["analytics"] is None


def test_combined_redis_down_and_chat_down_is_failed():  # [B] regression guard
    res = resources(memory=FakeMemory(down=True), chat_llm=FakeChat(complete_fail=True))
    result = run(res)
    assert result.route == "failed"  # failed wins over the lingering redis_down label
