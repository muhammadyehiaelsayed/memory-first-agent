"""Canonical M6 test fixtures — settings, fakes, redis skip/clean, and build_test_resources.

Owned by M6 (Ruling A / spec 006 §6.2). The upstream unit tests use their own local
fakes and do NOT import this file; these fixtures serve the integration/e2e tests and the
standalone eval/render scripts (which import `build_test_resources` after a repo-root
sys.path shim — tests/ is not an installed package).

Load-bearing invariants: fixture NAMES (`settings`, `fake_embedder`, `fake_llm`, `redis_url`,
`clean_index`), `WAIT_CAP_SCALE=0`, `dim=1536`, unit-norm vectors, token-overlap -> high cosine,
`pytest.skip` on unreachable Redis, and `Agent(resources)` (the Agent builds the graph itself).
"""

import hashlib
import math
import re
import socket
from urllib.parse import urlparse

import pytest

from memagent.analytics.classify import QueryClassification
from memagent.config import Settings
from memagent.interfaces import CompletionResult


# ---- zero-wait settings (FR-001) --------------------------------------------
@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")  # never used by the fakes
    monkeypatch.setenv(
        "TAVILY_API_KEY", "test-key"
    )  # forces the interceptable Tavily-httpx path (respx)
    monkeypatch.setenv(
        "WAIT_CAP_SCALE", "0"
    )  # instant retries through the PROD path (no monkeypatched sleeps)
    monkeypatch.setenv("TURN_LOG_PATH", str(tmp_path / "turns.jsonl"))
    return Settings()


# ---- deterministic FakeEmbedder (FR-003) ------------------------------------
class FakeEmbedder:
    """Bag-of-words sha256 -> L2-normalized unit vector.

    Deterministic and hash-based (PLAN: "det. hash->unit vector"): texts sharing tokens are
    close in cosine space, so a query-dominated page (the query repeated) embeds ~1.0 to the
    repeated query — this is what makes the e2e turn-2 memory hit reproducible.
    """

    def __init__(self, dim: int = 1536):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        tokens = re.findall(r"[a-z0-9]+", text.lower()) or ["__empty__"]
        for tok in tokens:
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v))
        if norm == 0.0:
            v[0] = 1.0
            return v
        return [x / norm for x in v]


@pytest.fixture
def fake_embedder(settings):
    return FakeEmbedder(dim=settings.embedding_dim)


# ---- FakeLLM (FR-002) -------------------------------------------------------
class FakeLLM:
    """Canned ChatLLM. `complete()` echoes `answer` + a populated usage dict; `parse()` builds
    a valid instance of the requested schema via `schema_factory`.

    NB bare `schema()` only works for schemas with valid defaults; QueryClassification and the
    grounding eval's GroundingVerdict have all-required fields, so those callers MUST pass a
    `schema_factory` (recheck F).
    """

    def __init__(
        self,
        answer: str = "Answer grounded in the provided context.",
        schema_factory=None,
    ):
        self.answer = answer
        self.schema_factory = schema_factory
        self.complete_calls = 0
        self.parse_calls = 0

    async def complete(self, system: str, messages: list[dict]) -> CompletionResult:
        self.complete_calls += 1
        return CompletionResult(
            text=self.answer,
            usage={"input_tokens": 100, "output_tokens": 20, "model": "fake"},
        )

    async def parse(self, system: str, user: str, schema):
        self.parse_calls += 1
        obj = self.schema_factory(schema) if self.schema_factory else schema()
        return obj, {"input_tokens": 50, "output_tokens": 10, "model": "fake"}


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_llm_qc():
    """A FakeLLM whose parse() yields a valid QueryClassification (schema_factory tests, FR-002)."""
    return _analytics_fake()


# ---- redis_url: skip integration/e2e if Redis is unreachable (FR-004) -------
def probe_redis_or_skip(settings) -> str:
    """Return settings.redis_url iff Redis is reachable; else pytest.skip (never error).

    Extracted from the redis_url fixture so FR-004's skip-not-error contract is unit-testable
    (test_m6_fixtures.py exercises THIS function), rather than asserted only by an inline
    socket-probe tautology that never touched the fixture code.
    """
    parsed = urlparse(settings.redis_url)
    host, port = parsed.hostname or "localhost", parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError:
        pytest.skip(f"Redis not reachable at {host}:{port} — skipping integration/e2e")
    return settings.redis_url


@pytest.fixture
def redis_url(settings):
    return probe_redis_or_skip(settings)


# ---- clean_index: drop + recreate the empty web_memory index (FR-005) -------
@pytest.fixture
async def clean_index(redis_url, settings):
    import redis.asyncio as aioredis

    from memagent.memory.schema import get_index, wipe_index  # M1 helpers (NOT build_index)

    client = aioredis.from_url(settings.redis_url)
    index = get_index(settings, client)
    await wipe_index(index)  # create(overwrite=True, drop=True) + doc:* purge -> truly empty
    yield index
    await client.aclose()


# ---- build_test_resources() + resources/agent fixtures (D2) -----------------
def _analytics_fake() -> FakeLLM:
    """analytics_llm: summary via complete(); classify via parse() -> a VALID QueryClassification
    (5 required fields, no defaults -> a schema_factory is mandatory, recheck F)."""
    return FakeLLM(
        schema_factory=lambda schema: QueryClassification(
            topic="redis",
            category="technology",
            question_type="factual",
            language="en",
            confidence=0.9,
        )
    )


def build_test_resources(settings, redis_client):
    """Assemble AgentResources: FAKE llm/embedder, REAL store/search/fetch/turn-logger.

    A plain importable function (D2) so the eval/render scripts can call it directly (after a
    repo-root sys.path shim). respx (configured by the caller) intercepts the real
    search/fetch httpx clients, so the "search endpoint call_count" is a real HTTP counter.
    NOT used by render_graph.py (that stays keyless — graph compilation touches no client).
    """
    from memagent.analytics.turnlog import TurnLogger
    from memagent.memory.store import RedisMemoryStore
    from memagent.resources import AgentResources
    from memagent.web.fetch import HttpxPageFetcher
    from memagent.web.search import FallbackProvider

    return AgentResources(
        settings=settings,
        memory=RedisMemoryStore(settings, redis_client),
        embedder=FakeEmbedder(settings.embedding_dim),
        chat_llm=FakeLLM(),
        analytics_llm=_analytics_fake(),
        searcher=FallbackProvider(settings),  # httpx/Tavily path forced by TAVILY_API_KEY (D3)
        fetcher=HttpxPageFetcher(settings),
        turn_logger=TurnLogger(settings.turn_log_path),
    )


@pytest.fixture
async def resources(settings, clean_index):
    from memagent.memory.store import make_redis_client

    client = make_redis_client(settings)  # same Redis URL as clean_index -> the just-wiped index
    try:
        yield build_test_resources(settings, client)
    finally:
        await client.aclose()


@pytest.fixture
def agent(resources):
    from memagent.app import Agent

    return Agent(resources)  # recheck A: Agent takes AgentResources and builds the graph itself
