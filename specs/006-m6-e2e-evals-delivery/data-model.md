# Data Model — M6 Integration/E2E, Evals, CI, Docs, v1.0

**Date**: 2026-07-06 | **Feature**: 006-m6-e2e-evals-delivery

M6 introduces **no new state fields, no new `TurnRecord` fields, and no Redis schema change** —
it *proves* the existing ones. What is new: test-only fakes/fixtures, one shared resource
helper, and one small pydantic verdict schema for the grounding eval. Everything below is
probe-verified against `memory-first-agent` main `6a582e4` (refs are `file:line`).

## 1. Consumed interfaces (probe-locked — the load-bearing reference)

The fixtures/tests/scripts call these exact signatures. **Do not guess — these are shipped.**

| Interface | Exact shipped signature / shape | Ref |
|---|---|---|
| `Settings` (relevant fields) | `similarity_threshold=0.7`, `memory_index_name="web_memory"`, `embedding_dim=1536`, `memory_top_k=5`, `memory_ttl_seconds=604800`, `wait_cap_scale=1.0`, `redis_url="redis://localhost:6379/0"`, `turn_log_path="logs/turns.jsonl"`, `conversation_model="gpt-5.4-mini"`, `analytics_model="gpt-5.4-nano"`, `embedding_model="text-embedding-3-small"`, `openai_api_key=""`, `tavily_api_key=""`. `SettingsConfigDict(env_file=".env", case_sensitive=False)` → env names are the UPPERCASE field name (no `Field(alias=)`); `Settings(_env_file=None)` pins defaults | config.py:15-66 |
| `get_index(settings, client) -> AsyncSearchIndex` | pure constructor (no I/O): `AsyncSearchIndex(build_schema(settings), redis_client=client)` — **needs a redis client** | schema.py:58 |
| `ensure_index(index) -> bool` | `if await index.exists(): return False` then `await index.create(overwrite=False)` — **the idempotent create** | schema.py:62 |
| `wipe_index(index) -> None` | `await index.create(overwrite=True, drop=True)` **plus** purge of `doc:*` meta hashes | schema.py:70 |
| `Route` | `Literal["memory_hit","memory_miss_web_search","degraded_web","blocked","failed"]` | state.py:13 |
| `MemoryHit` (TypedDict) | `doc_id, text, url, title, similarity: float (=1-distance), stored_at: str (ISO), sanitizer_flags: list[str], doc_type: str` — **no `origin`** | state.py:16-24 |
| `SourceRef` (TypedDict) | exactly `{url: str, title: str, origin: Literal["memory","web"]}` | state.py:50-53 |
| `FetchedDoc` (TypedDict) | `{url, title, markdown, summary: str\|None, ok: bool}` | state.py:34-39 |
| `Chunk` (TypedDict) | `{chunk_id, text, url, title, chunk_index}` | state.py:42-47 |
| `Embedder` (Protocol) | `dim: int`; `async def embed(self, texts: list[str]) -> list[list[float]]` | interfaces.py:14 |
| `CompletionResult` (NamedTuple) | `(text: str, usage: dict)` where usage `{input_tokens:int, output_tokens:int, model:str}` | interfaces.py:20 |
| `ChatLLM` (Protocol) | `async def complete(self, system, messages: list[dict]) -> CompletionResult`; `async def parse(self, system, user, schema: type[BaseModel]) -> tuple[BaseModel, dict]` | interfaces.py:25-30 |
| `WebSearcher` (Protocol) | `async def search(self, query: str, k: int) -> list[SearchResult]` | interfaces.py:33 |
| `MemoryStore` (Protocol) | `async def knn(self, vector, k) -> list[MemoryHit]` (RAW top-k); `async def store(self, page: FetchedDoc, chunks, vectors, source_query, flags) -> list[str]`; `async def is_fresh(self, h: str) -> bool` | interfaces.py:37-51 |
| `PageFetcher` (Protocol) | `async def fetch(self, urls: list[str]) -> list[FetchedDoc]` (concrete `HttpxPageFetcher` matches) | interfaces.py:54, fetch.py:103 |
| `TurnLogger` | `TurnLogger(path)`; `def log(self, record: dict) -> None` — **synchronous** append | turnlog.py:19,22 |
| `AgentResources` (frozen dataclass) | `settings, memory, embedder, chat_llm, analytics_llm, searcher, fetcher, turn_logger` (8 fields) | resources.py:22-31 |
| `build_graph(resources)` | builds `StateGraph(AgentState)`, entry `guard_input`, returns `sg.compile()` | graph.py:35-50 |
| `Agent.answer(query) -> TurnResult` | `TurnResult(route=final["route"], answer=final.get("answer"), sources=final.get("sources",[]), similarity=final.get("top_similarity"), degradation=final.get("degradation"))` | app.py:104-117 |
| `TurnResult` (NamedTuple) | `(route: str, answer: str\|None, sources: list[SourceRef], similarity: float\|None, degradation: str\|None = None)` | app.py:23-28 |
| `distance_to_similarity(d)` | `return 1.0 - d` — **single conversion site** | store.py:60 |
| `_epoch_to_iso(epoch)` | `datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()` — `stored_at` derived here at knn boundary | store.py:64,114 |
| `make_redis_client(settings)` | `aioredis.from_url(url, retry=Retry(ExponentialBackoff(cap=1.0), 3), retry_on_error=[ConnectionError,TimeoutError], socket_timeout=2.0, socket_connect_timeout=2.0)` | store.py:29-41 |
| Tavily HTTP | `POST https://api.tavily.com/search`, `json={"query","max_results","include_raw_content":False}`, resp `{"results":[{"url","title","content"}]}`; path gated by truthy `tavily_api_key` | search.py:21,44,90 |
| `render_graph.py` | keyless (all-`None` resources, `Settings(_env_file=None)`); prints `draw_mermaid()`; emits `\t__start__ --> guard_input;` + all 10 nodes; idempotent | render_graph.py:1-30 |

## 2. New M6 types (test-only + one eval schema)

### `tests/conftest.py` fakes (match the de-facto inline shapes — R0 #1)

```python
class FakeEmbedder:                    # dim=1536; bag-of-words sha256 -> L2-normalized unit vector
    dim: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...   # token overlap -> high cosine

class FakeLLM:                         # implements ChatLLM
    async def complete(self, system, messages) -> CompletionResult      # canned text + usage {input_tokens,output_tokens,model}
    async def parse(self, system, user, schema) -> tuple[BaseModel, dict]  # schema_factory(schema) or schema(); + usage dict
                                                                            # NB QueryClassification & GroundingVerdict have all-required fields -> MUST pass a schema_factory (recheck F)
```

Load-bearing: `dim == 1536`, unit-norm output, **bit-stable** for identical input, query-dominated
text scores cosine `>= 0.70`; `usage` dicts are **populated** (so `state["tokens"]` fills — D7).

### `scripts/eval_grounding.py` — `GroundingVerdict` (pydantic, M6-local)

```python
class GroundingVerdict(BaseModel):
    grounded: bool             # every claim supported by the supplied context
    citations_valid: bool      # all cited URLs are source_url present in context
    abstained_correctly: bool  # for abstain cases, the answerer refused
```

Judged by the **nano** model via `analytics_llm.parse(...)`; in `--mock`, `FakeLLM.parse`'s
`schema_factory` returns a passing verdict. No new state/record type.

## 3. Canonical fixtures (names/signatures frozen — §6.2)

| Fixture | Returns / does | Consumed by |
|---|---|---|
| `settings` | `Settings()` with env `WAIT_CAP_SCALE=0`, `TURN_LOG_PATH=<tmp>/turns.jsonl`, dummy `OPENAI_API_KEY` | all |
| `fake_embedder` | `FakeEmbedder(dim=settings.embedding_dim)` | unit + e2e |
| `fake_llm` | `FakeLLM()` | unit + e2e |
| `redis_url` | `socket.create_connection((host,port),1.0)`; on `OSError` → `pytest.skip(...)`; else returns `settings.redis_url` | integration + e2e |
| `clean_index` | (deps `redis_url`) `get_index(settings, aioredis.from_url(url))` → `await wipe_index(index)`; `yield index`; `await client.aclose()` | integration + e2e |
| `resources` / `agent` | wrap `build_test_resources(settings, redis_client)` (D2) → `AgentResources` / `Agent` | e2e |

`build_test_resources(settings, redis_client)` (plain fn in conftest; file-invoked scripts import it
after `sys.path.insert(0, <repo root>)` since `tests/` is not an installed package — recheck H): fakes for
LLM/embedder, **real** `RedisMemoryStore(settings, redis_client)`, **real** search/fetch
clients (respx-intercepted by the caller), **real** `TurnLogger(settings.turn_log_path)`.

## 4. Value-flow the e2e proves (no new fields — existing state/record)

| Turn | Action | Asserted state/record → source field | Ref |
|---|---|---|---|
| 1 | `agent.answer(Q)` on empty index | `route == "memory_miss_web_search"`; `top_similarity` is `None`→miss; `any(s["origin"]=="web")`; tavily respx `route.call_count == 1` | routers.py:19, answer.py:133 |
| 1→ingest | fetched page sanitized→summary(FakeLLM)→chunked→embed(Fake)→`store()` | chunk hash written with `fetched_at=int(time.time())`, `content_sha256`, `sanitizer_flags` | store.py:155-171 |
| 2 | identical `agent.answer(Q)` | `route == "memory_hit"`; `similarity >= 0.70` (query-dominated chunk, D8); `any(s["origin"]=="memory")` + cited URL == turn-1 URL (D9); tavily `call_count` **still 1** | routers.py:19 |
| both | each turn → one `TurnLogger.log(build_turn_record(state))` line | `turns.jsonl` has exactly 2 objects; routes `["memory_miss_web_search","memory_hit"]`; 2nd `similarity_top>=0.70`; each `tokens != {}` | turnlog.py:48-68 |

### `TurnRecord` fields M6 asserts (M4 shape — exact names)

| Record field | Value / source | Note |
|---|---|---|
| `route` | `state["route"]` | required key |
| `similarity_top` | `state.get("top_similarity")` | **record name ≠ state name** |
| `tokens` | `{role: {model, input, output}}` for `answer_llm`/`analytics_llm` in `state["tokens"]`; `{}` if none | non-empty requires fakes to return usage (D7) |
| `degradation` | `state.get("degradation")` | `None` on the happy path |
| (`ts`, `query`, `query_sha256`, `web`, `sources`, `latency_ms`, `guardrail`, `errors`, `analytics`) | present; not asserted by M6 FRs | timestamp field is `ts` |

## 5. Documentation-artifact contracts

| Artifact | Contract |
|---|---|
| README + `docs/architecture.md` mermaid | `render_graph.py` splices `draw_mermaid()` between stable markers `<!-- BEGIN graph -->` / `<!-- END graph -->`; re-run byte-identical; contains all 10 node names + `__start__ --> guard_input` |
| `docs/demo_transcript.md` | captured live (real key); MISS with web sources then HIT `sim>=0.70`; **pending real-key capture** placeholder until a key is provided (Clarification Q1) |
| `.github/workflows/ci.yml` | one job; `redis:8.2` service; steps ruff(check+format) → unit → integration/e2e → `eval_lifecycle --mock` → `eval_grounding --mock` → coverage report; no `secrets.*`; no `--cov-fail-under`; actions pinned; `python-version-file` |
| `docs/verification-2026-07-06.md` | dated re-verification note; each §14 fact + status; `temperature=0` on `gpt-5.4-mini` marked "pending real-key capture" |
| `v1.0` tag | on the green, keyless-verified commit |

**No Redis schema, state, or record field is added or changed** — M6 asserts the M1–M5 shapes.
