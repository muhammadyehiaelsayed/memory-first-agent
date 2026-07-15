# Contract — Canonical Test Fixtures (`tests/conftest.py`)

FR-001..005. `conftest.py` does **not** exist yet — M6 creates it (D1). The 12 existing unit
tests keep their local fakes (Ruling A); conftest adds the canonical fixtures + shared fakes +
`build_test_resources()` (D2). Names/signatures follow source §6.2.

## Fixtures

```python
# ---- zero-wait settings (FR-001) ----
@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")   # never used by fakes
    monkeypatch.setenv("WAIT_CAP_SCALE", "0")          # instant retries via PROD path
    monkeypatch.setenv("TURN_LOG_PATH", str(tmp_path / "turns.jsonl"))
    return Settings()                                  # env resolves UPPERCASE field names (data-model §1: config.py:15-66)

# ---- deterministic FakeEmbedder (FR-003) ----
class FakeEmbedder:                                    # dim=1536; sha256 bag-of-words -> unit vector
    def __init__(self, dim: int = 1536): self.dim = dim
    async def embed(self, texts): return [self._vec(t) for t in texts]
    # _vec: tokenize [a-z0-9]+, +/-1 into v[h % dim] by hash bit, L2-normalize; empty -> e0

@pytest.fixture
def fake_embedder(settings): return FakeEmbedder(dim=settings.embedding_dim)   # 1536

# ---- FakeLLM (FR-002) ----
class FakeLLM:                                         # implements ChatLLM
    def __init__(self, answer="Answer grounded in the provided context.", schema_factory=None): ...
    async def complete(self, system, messages) -> CompletionResult:
        return CompletionResult(self.answer, {"input_tokens":100,"output_tokens":20,"model":"fake"})
    async def parse(self, system, user, schema):
        obj = self.schema_factory(schema) if self.schema_factory else schema()   # bare schema() only builds schemas with valid defaults; QueryClassification AND GroundingVerdict have all-required fields -> those tests MUST pass a schema_factory (recheck F)
        return obj, {"input_tokens":50,"output_tokens":10,"model":"fake"}

@pytest.fixture
def fake_llm(): return FakeLLM()

# ---- redis_url: skip if unreachable (FR-004) ----
@pytest.fixture
def redis_url(settings):
    p = urlparse(settings.redis_url); host, port = p.hostname or "localhost", p.port or 6379
    try:
        with socket.create_connection((host, port), timeout=1.0): pass
    except OSError:
        pytest.skip(f"Redis not reachable at {host}:{port}")
    return settings.redis_url

# ---- clean_index: drop + recreate empty (FR-005) ----
@pytest.fixture
async def clean_index(redis_url, settings):
    import redis.asyncio as aioredis
    from memagent.memory.schema import get_index, wipe_index      # M1 helpers (NOT build_index)
    client = aioredis.from_url(settings.redis_url)
    index = get_index(settings, client)                           # needs a client (data-model §1: schema.py:58)
    await wipe_index(index)                                       # create(overwrite=True,drop=True) + doc:* purge
    yield index
    await client.aclose()
```

## `build_test_resources()` + `resources`/`agent` fixtures (D2)

```python
def build_test_resources(settings, redis_client):
    from memagent.memory.store import RedisMemoryStore
    from memagent.web.search import <FallbackProvider/TavilySearcher>   # REAL (respx-intercepted by caller)
    from memagent.web.fetch import HttpxPageFetcher
    from memagent.analytics.turnlog import TurnLogger
    return AgentResources(
        settings=settings,
        memory=RedisMemoryStore(settings, redis_client),
        embedder=FakeEmbedder(settings.embedding_dim),
        chat_llm=FakeLLM(),
        analytics_llm=FakeLLM(schema_factory=lambda s: QueryClassification(  # summary=complete(); classify=parse() -> VALID instance (recheck F)
            topic="redis vector search", category="technology",              # QueryClassification: 5 REQUIRED fields, no defaults
            question_type="factual", language="en", confidence=0.9)),         # enums coerce via str+_missing_ (no enum import needed)
        searcher=<real searcher>,               # httpx path forced via TAVILY_API_KEY (D3)
        fetcher=HttpxPageFetcher(settings),
        turn_logger=TurnLogger(settings.turn_log_path),
    )

@pytest.fixture
def resources(settings, clean_index): return build_test_resources(settings, clean_index_redis_client)
@pytest.fixture
def agent(resources): from memagent.app import Agent; return Agent(resources)   # Agent takes AgentResources and builds the graph ITSELF (recheck A; app.py:99-101)
```

> The `resources` fixture must obtain the **same** redis client the `clean_index` fixture
> created (share it, or construct one from `settings.redis_url`); the store and the wiped index
> point at one Redis. `render_graph.py` is NOT built via this helper (it stays keyless — D2).
>
> **Scripts importing this helper/fakes** (`eval_lifecycle.py`, `capture_demo.py`) run as files
> (`python scripts/…py`), so the repo root is NOT on `sys.path` and `tests/` is not an installed
> package (pyproject packages only `src/memagent`; no `__init__.py`; no pytest `pythonpath`). Each
> such script MUST prepend the repo root before importing (recheck H):
> `import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))`
> then `from tests.conftest import build_test_resources`. `conftest.py` stays the single owner (D2).

## Contract tests (in `conftest`-consumers; the fixtures themselves are exercised by §integration/e2e)

- **FR-001**: a 4-attempt `llm_retry(settings)`-wrapped coro that always raises `RateLimitError`
  runs under `settings` with `wait_cap_scale == 0` → 4 attempts, total sleep < 0.05 s.
- **FR-002**: `await fake_llm.complete("s", [])` twice → identical `.text`; each `.usage` has int
  `input_tokens`/`output_tokens` + `model` str. For `parse`, pass a schema_factory (bare `schema()`
  raises `ValidationError` — `QueryClassification` has 5 required fields, no defaults — recheck F):
  `qc = FakeLLM(schema_factory=lambda s: QueryClassification(topic="t", category="technology",
  question_type="factual", language="en", confidence=0.9))`; `await qc.parse("s","u",
  QueryClassification)` → `(valid QueryClassification, usage dict)`.
- **FR-003**: `embed(["redis vector search"])` twice → bit-identical, len 1536, L2-norm within
  1e-6 of 1.0; `cosine(embed(q), embed(q*3)) >= 0.70`; disjoint text `< 0.70`.
- **FR-004**: with Redis down, `pytest -m "not integration and not e2e"` passes; a test using
  `redis_url` reports `skipped` (never `error`).
- **FR-005**: after `clean_index`, `await store.knn(any_vector, 5) == []`.

Frozen: fixture **names** (`settings`, `fake_embedder`, `fake_llm`, `redis_url`, `clean_index`),
`WAIT_CAP_SCALE=0`, `dim=1536`, unit-norm vectors, token-overlap→high-cosine, `pytest.skip` on
unreachable Redis, and the M1 helper names `get_index`/`wipe_index`.
