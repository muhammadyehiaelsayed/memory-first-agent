# Milestone 6 — Integration/e2e tests, eval harnesses, CI green, docs, v1.0

| Estimated effort | Depends on | Enables | PLAN.md sections covered |
|---|---|---|---|
| 4–5 h | M1, M2, M3, M4, M5 (M6 integrates the whole system — every prior milestone must be complete) | The `v1.0` tag and the submittable repo; the "evaluator runs everything in 5 commands" outcome | §10.4 (README quickstart), §11 (AI_USAGE.md), §12 (whole test plan), §13 (M6 row), §14 (final re-verify), §15 (risks) |

---

## 1. Goal & context

M6 is the final milestone. It does **not** add product behaviour — it *proves* the behaviour built in M1–M5, packages it, and ships it. Concretely, M6 delivers:

1. The **test fixtures** (`tests/conftest.py`) that every other test file already depends on: a zero-wait `Settings`, a `FakeLLM`, a deterministic `FakeEmbedder`, a `redis_url` fixture that skips when Redis is unreachable, and a `clean_index` fixture.
2. The **integration test** (`tests/integration/test_redis_store.py`) that runs the real memory store against a real `redis:8.2`.
3. The **e2e lifecycle test** (`tests/e2e/test_lifecycle.py`) — the assignment's core proof: identical question asked twice, turn 1 a web-search miss, turn 2 a memory hit that does **not** touch the web.
4. Two **eval harnesses**: `scripts/eval_lifecycle.py` (a hard pass/fail gate on the miss-then-hit contract) and `scripts/eval_grounding.py` (an honest LLM-judge demonstration of grounding / citation-validity / abstention).
5. **CI finalized** to a single green job that runs with zero real keys.
6. **Docs finalized**: an auto-generated architecture diagram (`scripts/render_graph.py`), a captured demo transcript (`scripts/capture_demo.py`), the complete README, and the complete `AI_USAGE.md`.
7. The **pre-tag re-verification** of every time-sensitive fact (PLAN §14), then the `v1.0` tag.

Assignment requirements advanced by this milestone: the "log each turn (hit/miss)" and "grounded answer with source URLs" requirements are *proved* end-to-end here; the "document AI assistance (all instructions)" requirement is *completed* here; and the "deliver a repo only, runnable" requirement is *satisfied* here (CI green + 5-command run).

The demoable outcome (PLAN §13, M6 row): **the evaluator runs everything in 5 commands.**

---

## 2. Scope

### In scope

- `tests/conftest.py` — the canonical fixtures: zero-wait `Settings` (`WAIT_CAP_SCALE=0`), `FakeLLM`, deterministic `FakeEmbedder` (hash → unit vector), `redis_url` (skips integration/e2e if Redis unreachable), `clean_index`.
- `tests/integration/test_redis_store.py` — real `redis:8.2` round-trip: index create idempotent; upsert → KNN round-trip; URL/title/`fetched_at` metadata survives; known-vector distance converts to the expected similarity (including the exact 0.70 boundary).
- `tests/e2e/test_lifecycle.py` — one test, the core proof: mocked search/fetch (respx) + `FakeLLM` + `FakeEmbedder` against real Redis; turn 1 `memory_miss_web_search` with web source URLs; identical turn 2 `memory_hit` with `similarity >= 0.70` **and** the search endpoint `call_count` unchanged from turn 1.
- `scripts/eval_lifecycle.py` — `--mock` in CI (exit 1 unless every question is miss-then-hit); real-key mode run by hand before submission.
- `scripts/eval_grounding.py` — ~40–60 lines, 5–8 fixed cases, nano model as LLM-judge scoring grounding / citation-validity / abstention; `--mock` keyless in CI; labelled honestly as a demonstration, not a benchmark.
- `.github/workflows/ci.yml` — finalize to a single job: ruff → unit → integration/e2e (`redis:8.2` service matching docker-compose) → `eval_lifecycle --mock` + `eval_grounding --mock`; coverage **report** (no gate); zero real secrets.
- `scripts/render_graph.py` — `draw_mermaid()` → README + `docs/architecture.md` (provably not hand-drawn).
- `scripts/capture_demo.py` — captures a live miss→hit session into `docs/demo_transcript.md`.
- **README finalized** — verbatim §10.4 quickstart (incl. the zero-keys line), the threat-model table verbatim, the 0.70 calibration note, the TTL-is-coarse note + ETag production upgrade, the robots.txt limitation, why fetch+markdown stay in-house, the DuckDB note, the pip fallback, the worked paraphrase example from §15.2, and the "deliberately not a ReAct/tool-calling agent" design rationale (PLAN §2).
- **`AI_USAGE.md` finalized** — the complete chronological instruction record in `docs/ai_prompts/`, explicitly labelled "the complete instruction record"; the final per-milestone append.
- **`DECISIONS.md` finalized** — the repo-root standing anti-churn rulings file (scaffolded in M1) is finalized here with the complete locked-decision/anti-churn record cited by M2/M3/M5/M6.
- **PLAN §14 re-verification** of every time-sensitive fact immediately before tagging.
- **Tag `v1.0`.**

### Out of scope (owned by other milestones)

- `tests/unit/test_routing.py`, `test_similarity.py`, `test_chunker.py` — **owned by M2**. M6 consumes their green status in CI but does not author them.
- `tests/unit/test_classifier_parsing.py`, `test_turnlog.py` — **owned by M4**.
- `tests/unit/test_sanitizer.py`, `test_guardrails.py` (incl. the 3 attack fixtures and the "search client holds an `httpx.AsyncClient`" guard assertion), `test_search_retry.py`, `test_fetch_retry.py` — **owned by M5**.
- The node/store/client/pipeline **implementations** themselves — M2 (memory path + clients + routers + graph + facade), M3 (web pipeline + ingest), M4 (turn log + classifier + analytics CLI + REPL), M5 (security + reliability). M6 must not modify them; if a test reveals a bug, the fix belongs conceptually to the owning module but is applied here as a corrective (log it in AI_USAGE).
- `MODEL_CHOICES.md` **authoring** — **owned by M4**. M6 only re-verifies its prices/ids (PLAN §14) before tagging.
- The CI *skeleton* (lint job) — **owned by M1**. M6 finalizes it into the full single job.
- `scripts/seed_memory.py` — **owned by M2**.
- **Non-happy-path route coverage (`blocked`, `degraded_web`, `failed`).** The e2e lifecycle test proves only the `memory_miss_web_search`→`memory_hit` core path (§6.4); it does **not** re-prove the other routes, which are covered upstream (ruling A test-file ownership + PLAN §12): `blocked` (guardrail-high query → `route="blocked"`, search/store never touched, still logged) by **M5** `test_guardrails.py` (the T1 attack fixture) + **M2** `test_routing.py` (`route_after_guard` block→`log_turn`) + **M4** `test_turnlog.py` (blocked `TurnRecord` shape); `degraded_web` (Redis-down / all-fetches-failed) by **M5** reliability & degradation tests; `failed` (search down / embed exhaustion) by **M2** `test_routing.py` (`route_after_embed`, `route_after_search`). M6 consumes their green status in CI and must not re-author them.

### Deferred by design (anti-churn — do NOT add here)

These sit adjacent to M6 work and must not be "helpfully" added (DECISIONS.md standing anti-churn rulings + PLAN §15.3):

- **Coverage gates.** CI emits a coverage *report* only; there is no threshold that fails the build. Do not add `--cov-fail-under`.
- **Redis mirror of turn records** (`--from-file` replay, JSON/ZSET mirror) — stretch only.
- **Output URL-defang allowlist / canary token** — stretch only.
- **`GUARD_LLM_CHECK` gray-zone LLM classifier** — stretch only.
- **FT.AGGREGATE analytics demo, HNSW benchmark note, RedisInsight screenshots** — stretch only.
- **The 0.50 weak-memory salvage route** and the **embed-failure→web route** — cut by design; the e2e/eval harnesses must assume the closed 5-route enum only.
- **Token streaming, deep session memory** — rejected.

---

## 3. Prerequisites & interfaces consumed

Everything below must already exist and be green before M6 starts. Signatures are copied from PLAN §3; where PLAN is silent a Spec note gives the minimal-assumption default.

### From M1 — `config.py`, `memory/schema.py`, tooling

- `Settings` (pydantic-settings) exposing every §10.4 env var, notably: `similarity_threshold: float = 0.7`, `memory_index_name: str = "web_memory"`, `embedding_dim: int = 1536`, `memory_top_k: int = 5`, `memory_ttl_seconds: int = 604800`, `wait_cap_scale: float = 1.0`, `redis_url: str`, `turn_log_path: str = "logs/turns.jsonl"`, `similarity_threshold`, model ids.
- `docker-compose.yml` with `redis:8.2` (AOF + healthcheck) — the CI service image must match this exactly.
- `.github/workflows/ci.yml` skeleton (lint job) and `Makefile` targets (`setup redis-up run ask analytics wipe test test-integration lint demo`, all `.PHONY`).
- `memory/schema.py`: index create-if-missing + drop/recreate helpers.
  > **Spec note:** M1 §4.2 provides `get_index(settings, client) -> AsyncSearchIndex` (which needs a redis client) and `async def wipe_index(index: AsyncSearchIndex) -> None` (drop + recreate) — there is **no** `build_index`. The `clean_index` fixture therefore constructs a `redis.asyncio` client from `settings.redis_url`, calls `get_index(settings, client)`, then `wipe_index(index)`. The fixture only needs "create the empty `web_memory` index" and "drop everything under `chunk:` + `doc:`".

### From M2 — protocols, store, routers, graph, facade

Verbatim protocols (PLAN §3.4):

```python
class Embedder(Protocol):
    dim: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class CompletionResult(NamedTuple):
    text: str
    usage: dict          # {"input_tokens": int, "output_tokens": int, "model": str}

class ChatLLM(Protocol):
    async def complete(self, system: str, messages: list[dict]) -> CompletionResult: ...
    async def parse(self, system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel, dict]: ...

class WebSearcher(Protocol):
    async def search(self, query: str, k: int) -> list[SearchResult]: ...

class MemoryStore(Protocol):
    async def knn(self, vector: list[float], k: int) -> list[MemoryHit]:  # RAW top-k, NO filtering
        ...
    async def store(self, page: FetchedDoc, chunks: list[Chunk], vectors: list[list[float]],
                    source_query: str, flags: list[str]) -> list[str]: ...

@dataclass(frozen=True)
class AgentResources:
    settings: Settings; memory: MemoryStore; embedder: Embedder
    chat_llm: ChatLLM; analytics_llm: ChatLLM
    searcher: WebSearcher; fetcher: PageFetcher; turn_logger: TurnLogger
```

- `build_graph(resources: AgentResources)` → one compiled async `StateGraph`.
- **Agent facade** (`app.py`): `async def answer(self, q: str) -> TurnResult` where `TurnResult(route, answer, sources, similarity)`. Both the CLI and the e2e/eval harnesses drive the graph through this facade.
- State types (`state.py`): `Route = Literal["memory_hit","memory_miss_web_search","degraded_web","blocked","failed"]`, `MemoryHit`, `SearchResult`, `FetchedDoc`, `Chunk`, `SourceRef`, `AgentState`.
- Pure routers (`routers.py`), notably `route_after_memory` (inclusive `>=`).
  > **Spec note:** `PageFetcher` protocol is referenced in `AgentResources` but its signature is not spelled out in PLAN.md. Chosen minimal-assumption default: `async def fetch(self, urls: list[str]) -> list[FetchedDoc]`. Change freely.

### From M3 — web pipeline

- `web/search.py` `WebSearcher` impl (Tavily via raw httpx POST to `api.tavily.com/search`, `include_raw_content=False`, ddgs fallback). **The search client holds an `httpx.AsyncClient`** — this is what makes respx interception in the e2e test valid (M5 guards it with an assertion).
- `web/fetch.py` `PageFetcher` impl (streamed httpx GET) and `web/to_markdown.py` (trafilatura).
- Nodes `web_search`, `fetch_pages`, `ingest_content`, `answer_from_web`.

### From M4 — logging, classifier, analytics, REPL

- `analytics/turnlog.py` `TurnLogger` (one `TurnRecord` JSON per turn appended to `logs/turns.jsonl`).
  > **Spec note:** `TurnLogger` method name is not fixed in PLAN.md. Chosen minimal-assumption default: `def log(self, record: dict) -> None` (synchronous append). Change freely; the e2e test only needs "one JSON line per turn at `settings.turn_log_path`".
- `analytics/classify.py` `QueryClassification` schema (topic / category / question_type / language / confidence), called inside `log_turn` via `analytics_llm.parse`.
- `analytics/report.py` (`memagent analytics`, `--json`).
- `MODEL_CHOICES.md` (authored in M4; re-verified in M6).
- `cli.py` REPL (`chat | ask | analytics | wipe-memory`).

### From M5 — security & reliability

- `security/` (L1 guard, L2 prompt hardening, L3 sanitizer) fully implemented — by M6 `guard_input` is active and `<untrusted_context>` wrapping is finalized.
- `utils/reliability.py` + `utils/errors.py` — the tenacity policy table honouring `WAIT_CAP_SCALE`. **This is why the M6 zero-wait fixture works: setting `WAIT_CAP_SCALE=0` scales every backoff wait to zero through the production retry code path — no monkeypatching.**

### Seams that touch M6 (orchestrator rulings)

- **Ruling A (test-file ownership).** M6 owns exactly the five test/eval artifacts listed in §2 In scope, plus `conftest.py`. All other test files are owned upstream; M6 must not rewrite them.
- **conftest ordering seam.** M2/M4/M5 unit tests reference `FakeLLM` / `FakeEmbedder` / the zero-wait `settings` fixture. Those milestones introduced provisional versions as needed; **M6 owns and finalizes the canonical `conftest.py`.** The fixture *names and signatures* (§4) are stable from first use, so upstream tests keep passing unchanged against the finalized fixtures.
  > **Spec note:** PLAN.md does not describe how conftest fixtures existed before M6 given M2 tests need them. Chosen minimal-assumption resolution: fixture names/signatures are frozen at first use; M6 consolidates them into the single canonical `conftest.py`. Change freely if the build order kept them in the canonical file from M2.

---

## 4. Interfaces provided

M6 is the terminal milestone — there is **no downstream milestone to consume these**; the consumers are (a) the whole test suite, (b) CI, and (c) the evaluator. M6 introduces **no temporary stubs** and replaces none; it finalizes.

The stable contracts M6 exposes:

| Interface | Contract | Consumed by |
|---|---|---|
| `settings` fixture | Returns a `Settings` with `wait_cap_scale=0`, `turn_log_path` pointed at a per-test tmp file, no real keys required. | all test files |
| `FakeLLM` | `complete()` returns a canned `CompletionResult` with populated `usage`; `parse()` returns a valid instance of the requested schema + usage dict. Deterministic. | all tests needing a `ChatLLM` |
| `FakeEmbedder` | `dim == settings.embedding_dim (1536)`; `embed(texts)` returns L2-normalized unit vectors; texts sharing tokens are close in cosine space (so the e2e turn-2 hit is reproducible). Deterministic. | all tests needing an `Embedder` |
| `redis_url` fixture | Yields the Redis URL if a live `redis:8.2` answers `PING`; otherwise `pytest.skip(...)` so unit runs stay dockerless. | integration + e2e tests |
| `clean_index` fixture | Drops and recreates the `web_memory` index (empty) before the test; depends on `redis_url`. | integration + e2e tests |
| `resources` / `agent` fixtures + `build_test_resources()` helper | Assemble `AgentResources` (fakes for LLM/embedder, real store for integration/e2e, mocked search/fetch, a real `TurnLogger` at `settings.turn_log_path`) and the `Agent` facade. The pytest `resources`/`agent` fixtures wrap a plain `build_test_resources()` helper; standalone CLI scripts (which cannot use pytest fixtures) import and call that helper directly. | e2e test (fixtures); eval/render scripts (via `build_test_resources()`) |
| `scripts/eval_lifecycle.py` | CLI: `--mock` (CI gate) / real-key (manual). Exit code contract in §6. | CI, evaluator |
| `scripts/eval_grounding.py` | CLI: `--mock` (CI demonstration). Prints a scorecard; exit 0. | CI, evaluator |
| README markers | `scripts/render_graph.py` writes the mermaid block between stable comment markers in `README.md` and `docs/architecture.md`. | render script, evaluator |

---

## 5. Functional requirements

Each is one testable statement with an explicit acceptance criterion.

- **FR-M6-01 — Zero-wait settings fixture.** `conftest.py` provides a `settings` fixture returning a `Settings` with `wait_cap_scale == 0`. *Acceptance:* a retry decorated by `utils/reliability.py` under this fixture performs its full attempt count with total sleep time ≈ 0 s (no real backoff).
- **FR-M6-02 — FakeLLM fixture.** `conftest.py` provides a `FakeLLM` implementing `ChatLLM`. `complete()` returns a `CompletionResult` whose `usage` dict has integer `input_tokens`/`output_tokens` and a `model` string; `parse()` returns a valid instance of the requested pydantic schema plus a usage dict. *Acceptance:* calling `complete()` and `parse()` requires no network and returns deterministic values across runs.
- **FR-M6-03 — Deterministic FakeEmbedder fixture.** `conftest.py` provides a `FakeEmbedder` with `dim == 1536`; `embed()` returns unit-norm vectors; identical input text always yields the identical vector; a **query-dominated** text (the query tokens dominate the token bag) scores cosine `>= 0.70` to the query. *Acceptance:* `embed(["redis vector search"])[0]` is bit-stable across runs and, for a query-dominated `p` (e.g. the query repeated), `cosine(embed(q), embed(p)) >= 0.70`. Note (see gotcha §10.2): a page containing the query plus substantial unrelated content is **not** guaranteed to clear 0.70 — the e2e proof (§6.4) relies on a query-dominated page, not merely a query-containing one.
- **FR-M6-04 — Redis skip fixture.** `conftest.py` provides a `redis_url` fixture that pings the configured Redis; if unreachable it calls `pytest.skip(...)`. *Acceptance:* with no Redis running, `pytest -m "not integration and not e2e"` passes and integration/e2e tests report `skipped`, never `error`.
- **FR-M6-05 — Clean-index fixture.** `conftest.py` provides a `clean_index` fixture (depending on `redis_url`) that drops + recreates the empty `web_memory` index before the test body. *Acceptance:* after the fixture runs, a KNN query returns `[]` (empty index).
- **FR-M6-06 — Integration: index create is idempotent.** Creating the index when it already exists does not raise and does not duplicate it. *Acceptance:* calling create twice leaves exactly one `web_memory` index.
- **FR-M6-07 — Integration: upsert → KNN round-trip.** A stored page's chunk is retrievable by KNN with its metadata intact. *Acceptance:* after `store(page, chunks, vectors, ...)`, `knn(query_vector, k=5)` returns a `MemoryHit` whose `text`, `url`, `title` match the stored chunk.
- **FR-M6-08 — Integration: URL metadata survives.** `url`, `title`, and `fetched_at` survive the round-trip, with `fetched_at` converted from epoch to ISO-8601 at the `MemoryHit` boundary. *Acceptance:* the returned `MemoryHit.stored_at` is a valid ISO-8601 string equal to the ISO form of the stored epoch `fetched_at`.
- **FR-M6-09 — Integration: distance → similarity is exact.** A vector stored and queried with a known cosine relationship yields `similarity == 1 - vector_distance`, including the exact 0.70 boundary. *Acceptance:* querying with the identical stored vector gives `similarity == 1.0`; an orthogonal vector gives `similarity == 0.0`; a pair constructed with cosine `0.70` gives `similarity` within `1e-6` of `0.70` (distance `0.30`).
- **FR-M6-10 — E2E: turn 1 is a web-search miss.** Against real Redis with mocked search/fetch + fakes, the first ask of a fresh question routes `memory_miss_web_search` and returns `sources` with `origin == "web"` URLs. *Acceptance:* `TurnResult.route == "memory_miss_web_search"` and `len([s for s in sources if s["origin"] == "web"]) >= 1` (sources are `SourceRef` TypedDicts, so members are dict-accessed); the search endpoint `call_count == 1`.
- **FR-M6-11 — E2E: identical turn 2 is a memory hit that never touches the web.** Asking the identical question a second time routes `memory_hit` with `similarity >= 0.70`, and the search endpoint `call_count` is unchanged from turn 1. *Acceptance:* `TurnResult.route == "memory_hit"`, `similarity >= 0.70`, and the search endpoint `call_count` is still `1`.
- **FR-M6-11b — E2E: each turn writes exactly one TurnRecord to the turn log.** After turns 1 and 2, `settings.turn_log_path` (the per-test tmp `turns.jsonl` pointed to by the `settings` fixture) contains exactly two JSON lines: the first with `route == "memory_miss_web_search"`, the second with `route == "memory_hit"` and `similarity_top >= 0.70`; each line carries a populated `tokens` block. This is where M6 *proves* the "log each turn (hit/miss)" requirement end-to-end. *Acceptance:* reading the tmp `turns.jsonl` yields exactly two parseable JSON objects whose `route` values are `["memory_miss_web_search", "memory_hit"]` in order, each with a non-empty `tokens` dict, and the second object's `similarity_top >= 0.70`.
- **FR-M6-12 — eval_lifecycle --mock is a hard gate.** `scripts/eval_lifecycle.py --mock` asks each fixed question twice and exits `1` unless **every** question is miss-then-hit (`memory_miss_web_search` then `memory_hit` with `similarity >= 0.70`); exits `0` when all hold. *Acceptance:* `python scripts/eval_lifecycle.py --mock; echo $?` prints `0` on a healthy build; if any question fails the miss-then-hit contract the process exits `1`.
- **FR-M6-13 — eval_lifecycle real-key mode.** The same script runs against real OpenAI + real search when `--mock` is omitted and `OPENAI_API_KEY` is set, for a manual pre-submission check. *Acceptance:* without `--mock` and without `OPENAI_API_KEY`, the script exits non-zero with a readable "OPENAI_API_KEY required" message (it does not crash with a traceback).
- **FR-M6-14 — eval_grounding scores three dimensions.** `scripts/eval_grounding.py` runs 5–8 fixed cases; for each it produces an answer over a supplied context and scores it with the nano model as judge on grounding, citation-validity, and abstention. *Acceptance:* the printed scorecard contains a per-case row and an aggregate for all three dimensions; the file is ~40–60 lines.
- **FR-M6-15 — eval_grounding --mock is keyless and non-crashing.** `scripts/eval_grounding.py --mock` uses `FakeLLM` for both answerer and judge, needs no API key and no Redis, and exits `0` after printing the scorecard. *Acceptance:* `python scripts/eval_grounding.py --mock; echo $?` prints `0` with no network access.
- **FR-M6-16 — CI single job, correct order, zero secrets.** `.github/workflows/ci.yml` is a single job running, in order: ruff (lint+format check) → unit → integration/e2e → `eval_lifecycle --mock` → `eval_grounding --mock` → coverage report. It references no repository secrets. *Acceptance (each an independent check):* (a) it is exactly one job; (b) the steps appear in the stated order; (c) the job has no `secrets.*` reference; (d) the coverage step has no `--cov-fail-under`/threshold flag.
- **FR-M6-17 — CI environment matches shipped.** The CI Redis service is pinned `redis:8.2` (matching `docker-compose.yml`), Python is taken from `.python-version`, and all `actions/*` are pinned to a version. *Acceptance (each an independent check):* (a) `services.redis.image == "redis:8.2"`; (b) the setup-python step reads `.python-version` (`python-version-file`); (c) no `actions/*@main` or otherwise-unpinned action uses.
- **FR-M6-18 — Auto-generated architecture diagram.** `scripts/render_graph.py` calls `compiled.get_graph().draw_mermaid()` and writes the result into both `README.md` (between stable markers) and `docs/architecture.md`. *Acceptance:* re-running the script reproduces byte-identical mermaid between the markers; the diagram lists all 10 nodes.
- **FR-M6-19 — Captured demo transcript.** `scripts/capture_demo.py` runs a live miss→hit session and writes `docs/demo_transcript.md`. *Acceptance:* `docs/demo_transcript.md` shows the same question twice — first a MISS with web sources, then a HIT from memory with `sim >= 0.70`.
- **FR-M6-20 — README finalized with all required verbatim sections.** README contains: the §10.4 quickstart verbatim incl. the zero-keys line; the threat-model table verbatim; the 0.70 calibration note; the TTL-is-coarse note + ETag production upgrade; the robots.txt limitation; why fetch+markdown stay in-house; the DuckDB note; the pip fallback; the worked paraphrase example from §15.2; and the "deliberately not a ReAct/tool-calling agent" design rationale (PLAN §2). *Acceptance (each of the ten enumerated items is an independent check):* each item listed above is present in the README and matches the source wording.
- **FR-M6-21 — AI_USAGE.md finalized with the complete instruction record.** `AI_USAGE.md` has all 8 sections (PLAN §11) and points to `docs/ai_prompts/`, explicitly labelled "the complete instruction record"; the M6 prompts are appended. *Acceptance:* `docs/ai_prompts/` contains a per-milestone chronological log through M6; `AI_USAGE.md` contains the literal phrase "the complete instruction record".
- **FR-M6-22 — Pre-tag re-verification.** Every PLAN §14 time-sensitive fact is re-verified immediately before tagging; any drift is corrected in config/docs. *Acceptance:* a short re-verification note (date-stamped 2026-07-04 or later) records each §14 row checked and its status.
- **FR-M6-23 — Tag v1.0.** A `v1.0` git tag is created on the commit where CI is green and all above FRs pass. *Acceptance:* `git tag` lists `v1.0`.
- **FR-M6-24 — 5-command evaluator run.** A fresh evaluator can go from clone to a live miss→hit in five commands. *Acceptance:* the documented 5-command sequence (§6) produces a working session; the zero-key path (`make test` + `eval_lifecycle --mock`) passes with no keys.

---

## 6. Technical specification

Self-contained detail — a developer builds M6 from this section without opening PLAN.md.

### 6.1 pytest configuration (in `pyproject.toml`, finalized here)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: requires a live redis:8.2 (skips if unreachable)",
    "e2e: full-graph lifecycle against real Redis with mocked HTTP + fakes",
]
```

- Unit run: `pytest -m "not integration and not e2e"` — no Redis, no network, no keys.
- Integration + e2e run: `pytest -m "integration or e2e"` — needs Redis.
- Dev deps present since M1/M5: `pytest~=8.4`, `pytest-asyncio` (1.x), `respx~=0.23`, `pytest-cov`, `ruff`.

### 6.2 `tests/conftest.py` — the canonical fixtures

```python
import hashlib, math, re, socket
import pytest
from urllib.parse import urlparse

from memagent.config import Settings
from memagent.interfaces import CompletionResult  # NamedTuple(text, usage)

# ---- zero-wait settings -------------------------------------------------
@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")   # never used by fakes
    monkeypatch.setenv("WAIT_CAP_SCALE", "0")          # instant retries, prod code path
    monkeypatch.setenv("TURN_LOG_PATH", str(tmp_path / "turns.jsonl"))
    return Settings()

# ---- deterministic FakeEmbedder (hash -> unit vector) -------------------
class FakeEmbedder:
    """Bag-of-words token hashing -> L2-normalized unit vector.

    Deterministic and hash-based (PLAN: "det. hash->unit vector"). Chosen so
    that texts sharing tokens are close in cosine space: this is what makes the
    e2e turn-2 hit reproducible (the mocked page repeats the query text, so its
    stored chunk embeds >= 0.70 to the repeated query)."""
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

# ---- FakeLLM ------------------------------------------------------------
class FakeLLM:
    """Canned ChatLLM. `answer` is echoed by complete(); parse() builds a
    valid instance of the requested schema via `schema_factory`."""
    def __init__(self, answer: str = "Answer grounded in the provided context.",
                 schema_factory=None):
        self.answer = answer
        self.schema_factory = schema_factory
        self.complete_calls = 0
        self.parse_calls = 0
    async def complete(self, system: str, messages: list[dict]) -> CompletionResult:
        self.complete_calls += 1
        return CompletionResult(text=self.answer,
                                usage={"input_tokens": 100, "output_tokens": 20, "model": "fake"})
    async def parse(self, system: str, user: str, schema):
        self.parse_calls += 1
        obj = self.schema_factory(schema) if self.schema_factory else schema()  # defaults must be valid
        return obj, {"input_tokens": 50, "output_tokens": 10, "model": "fake"}

@pytest.fixture
def fake_llm():
    return FakeLLM()

# ---- redis_url: skip integration/e2e if Redis unreachable ---------------
@pytest.fixture
def redis_url(settings):
    parsed = urlparse(settings.redis_url)
    host, port = parsed.hostname or "localhost", parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError:
        pytest.skip(f"Redis not reachable at {host}:{port} — skipping integration/e2e")
    return settings.redis_url

# ---- clean_index: drop + recreate the empty index -----------------------
@pytest.fixture
async def clean_index(redis_url, settings):
    import redis.asyncio as aioredis
    from memagent.memory.schema import get_index, wipe_index  # M1 §4.2 helpers
    client = aioredis.from_url(settings.redis_url)
    index = get_index(settings, client)   # M1: get_index(settings, client) — needs a redis client
    await wipe_index(index)   # drop + recreate empty web_memory
    yield index
    await client.aclose()
```

> **Spec note:** the exact `schema_factory` shape is an M6-local minimal-assumption default (PLAN silent); `get_index`/`wipe_index` are the **M1 §4.2 helper names** (not an invented `build_index`). What is load-bearing and fixed: fixture *names* (`settings`, `fake_embedder`, `fake_llm`, `redis_url`, `clean_index`), `WAIT_CAP_SCALE=0`, `dim=1536`, unit-norm vectors, token-overlap → high cosine, and the `pytest.skip` on unreachable Redis.

### 6.3 `tests/integration/test_redis_store.py` (`@integration`, real `redis:8.2`)

Uses `clean_index` + `fake_embedder`. Four checks (PLAN §12 integration list):

1. **Idempotent create** (FR-M6-06): call create twice → no error, one index.
2. **Round-trip** (FR-M6-07): build a `FetchedDoc` + `Chunk`s, embed with `fake_embedder`, `store(...)`, then `knn(embed(query), k=5)` → first hit's `text/url/title` equal the stored chunk.
3. **Metadata survives** (FR-M6-08): assert returned `MemoryHit.url`, `.title`, and ISO `.stored_at` equal the stored values; `stored_at` parses as ISO-8601.
4. **Known-vector similarity** (FR-M6-09): store a hand-built unit vector; query with (a) the same vector → `similarity == 1.0`, (b) an orthogonal unit vector → `similarity == 0.0`, (c) a vector at cosine 0.70 → `abs(similarity - 0.70) <= 1e-6`. Constructing the 0.70 pair: with unit vectors `u=[1,0,0,...]` and `w=[0.7, sqrt(1-0.49), 0,...]`, `cos(u,w)=0.7`, so Redis distance `=0.30` and `similarity = 1 - 0.30 = 0.70`.

### 6.4 `tests/e2e/test_lifecycle.py` (`@e2e`, the core proof)

Wiring: `AgentResources` with `fake_llm` (conversation + analytics), `fake_embedder`, a **real** `TurnLogger` writing to `settings.turn_log_path` (the per-test tmp `turns.jsonl`, so the turn log can be read back and asserted — FR-M6-11b), the **real** `MemoryStore` (against `clean_index` Redis), and the **real** `web/search.py` + `web/fetch.py` — with **respx** intercepting the HTTP endpoints so the "search endpoint call_count" is a real respx route counter. The test sets `TAVILY_API_KEY="test-key"` so the searcher takes the Tavily-httpx path (respx-intercepted) rather than the ddgs fallback.

```python
QUESTION = "How does Redis vector search work?"

# respx mocks:
#   POST https://api.tavily.com/search -> 1 result {url, title, snippet}
#   GET  <result url>                  -> 200 text/html, an <article> that
#                                          repeats QUESTION verbatim (so the
#                                          stored chunk embeds >= 0.70 to it,
#                                          and trafilatura extracts > 200 chars)
```

- **Turn 1** (FR-M6-10): `res1 = await agent.answer(QUESTION)`; assert `res1.route == "memory_miss_web_search"`; assert `any(s["origin"] == "web" for s in res1.sources)` (`SourceRef` is a TypedDict — dict access); assert `tavily_route.call_count == 1`.
- **Turn 2** (FR-M6-11): `res2 = await agent.answer(QUESTION)`; assert `res2.route == "memory_hit"`; assert `res2.similarity >= 0.70`; assert `tavily_route.call_count == 1` (**unchanged** — the memory hit must not touch the web).

The mocked HTML must yield trafilatura markdown `> 200` chars dominated by the query tokens, so the bag-of-words `FakeEmbedder` scores turn 2 `>= 0.70`. respx patches httpx only; `redis.asyncio` traffic is untouched.

> **Spec note:** PLAN says "mocked search/fetch"; respx (intercepting the real search/fetch code) is chosen over an injected counting fake because it makes the assertion a literal *endpoint* `call_count` and exercises the real web pipeline. A counting fake `WebSearcher`/`PageFetcher` is an acceptable equivalent if respx+real-client proves brittle.

### 6.5 `scripts/eval_lifecycle.py`

```
Usage: python scripts/eval_lifecycle.py [--mock]
  --mock : FakeLLM + FakeEmbedder + respx-mocked search/fetch, real Redis (CI).
           No --mock: real OpenAI + real search (manual, pre-submission).
Contract: for each fixed question, ask twice.
  PASS if turn 1 == memory_miss_web_search AND turn 2 == memory_hit with sim >= 0.70.
  Exit 0 iff every question passes; else exit 1 (print which question failed).
Without --mock and without OPENAI_API_KEY -> exit non-zero with a readable message.
```

> **Spec note:** PLAN does not fix the question set. Chosen minimal-assumption default (3 diverse, unambiguous questions, change freely): "How does Redis vector search work?", "What is cosine similarity?", "How do I set a TTL on a Redis key?". Each mocked page repeats its question verbatim so the miss-then-hit holds under the `FakeEmbedder`.

### 6.6 `scripts/eval_grounding.py` (~40–60 lines)

Honest LLM-judge **demonstration** (not a benchmark — say so in output and README). 5–8 fixed cases; each is `(question, context, expect)` where `expect ∈ {"grounded", "abstain"}`:

- **grounded** cases: context contains the answer + a `source_url`. The answerer (conversation LLM) must answer and cite that URL. Judge scores grounding=1, citation_valid=1.
- **abstain** cases: context is empty or off-topic. The answerer must refuse ("insufficient context"). Judge scores abstention=1.

The judge is the **nano** model (`analytics_llm.parse`) returning a small verdict schema:

```python
class GroundingVerdict(BaseModel):
    grounded: bool          # is every claim supported by the context?
    citations_valid: bool   # are all cited URLs present as source_url in context?
    abstained_correctly: bool  # for abstain cases, did it refuse?
```

`--mock`: `FakeLLM` is both answerer and judge; its `schema_factory` returns a passing `GroundingVerdict`; no key, no Redis; prints the scorecard (per-case + aggregate) and exits `0`.

> **Spec note:** exact case texts are M6-local (PLAN silent). `--mock` is intentionally **non-gating** (exit 0 after printing) because PLAN labels this a demonstration; only `eval_lifecycle` is a hard gate.

### 6.7 `.github/workflows/ci.yml` (single job, finalized)

```yaml
name: ci
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:8.2                 # MUST match docker-compose.yml
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s
          --health-timeout 3s --health-retries 5
    steps:
      - uses: actions/checkout@v4         # pinned
      - uses: actions/setup-python@v5     # pinned
        with:
          python-version-file: ".python-version"   # CI Python from repo
      - uses: astral-sh/setup-uv@v6       # pinned
      - run: uv sync --frozen
      - run: uv run ruff check . && uv run ruff format --check .
      - run: uv run pytest -m "not integration and not e2e" --cov=memagent --cov-report=term
      - run: uv run pytest -m "integration or e2e" --cov=memagent --cov-append --cov-report=term
        env:
          REDIS_URL: redis://localhost:6379/0
      - run: uv run python scripts/eval_lifecycle.py --mock
      - run: uv run python scripts/eval_grounding.py --mock
      - run: uv run coverage report        # REPORT ONLY — no --fail-under gate
```

Zero `secrets.*`. Everything runs on fakes; the only live dependency is the pinned `redis:8.2` service.

### 6.8 `scripts/render_graph.py`

```python
# Build resources with fakes (no live keys), compile the graph, render mermaid,
# and splice it into README.md and docs/architecture.md between stable markers.
resources = build_test_resources()          # fakes; no network
mermaid = build_graph(resources).get_graph().draw_mermaid()
for path in ("README.md", "docs/architecture.md"):
    replace_between(path, "<!-- BEGIN graph -->", "<!-- END graph -->",
                    f"```mermaid\n{mermaid}```")
```

Re-running must be idempotent (byte-identical output between markers). The rendered diagram must contain all 10 node names — `guard_input`, `embed_query`, `memory_search`, `answer_from_memory`, `web_search`, `fetch_pages`, `ingest_content`, `answer_from_web`, `answer_failure`, `log_turn` — this is what makes the README diagram "provably not hand-drawn".

### 6.9 `scripts/capture_demo.py`

Runs a real miss→hit session (needs `OPENAI_API_KEY`; run by hand before submission) via the `Agent` facade over two identical questions, capturing route banners + sources, and writes `docs/demo_transcript.md`. Deterministic answers (mini at `temperature=0`) keep the transcript reproducible.

### 6.10 README required sections (finalized here, sourced verbatim)

1. **Quickstart (verbatim, PLAN §10.4)** including the zero-keys block:
   > **Zero keys needed:** `make test` and `python scripts/eval_lifecycle.py --mock` (CI runs exactly these).
   > **One key** (`OPENAI_API_KEY`) **+ Docker** for the live demo; `TAVILY_API_KEY` optional (keyless DuckDuckGo fallback).

   Quickstart: clone → install uv → `make setup` (uv sync + .env) → `make redis-up` → `make run`.
2. **Threat-model table (verbatim, PLAN §7)** — rows T1–T4 with mitigations; T3 memory poisoning is the centerpiece. FR-M6-20 requires this reproduced verbatim in the README, so it is embedded here in full:

   | ID | Threat | Mitigation |
   |---|---|---|
   | T1 | Direct injection in the user query | L1 input screen + L2 prompt hardening |
   | T2 | Indirect injection inside fetched pages | L2 data/instruction separation + L3 sanitizer |
   | T3 | **Memory poisoning** — injected content stored in Redis, replayed as trusted context on future hits | **L3 sanitize-before-store + persisted `sanitizer_flags` provenance** (the highest-value defense: anything surviving ingestion becomes "trusted memory" forever) |
   | T4 | Exfil/unsafe output (attacker URLs, tracker images) | prompt rule "cite only provenance URLs" + markdown-image strip on output |
3. **0.70 calibration note** — 0.70 is calibrated for `text-embedding-3-small`; changing `EMBEDDING_MODEL` changes what 0.70 means → re-tune `SIMILARITY_THRESHOLD` + `wipe-memory`.
4. **TTL note + ETag upgrade** — `MEMORY_TTL_SECONDS=604800` (7d) is a *coarse* staleness policy (not a limitation); ETag/Last-Modified conditional revalidation is the named production upgrade.
5. **robots.txt limitation** — robots.txt not consulted; stated as a known limitation with the production fix.
6. **Why fetch+markdown stay in-house** — they are the two steps the assignment explicitly grades; local trafilatura wins on extraction quality and needs no second key (pre-empts "why not one Jina/Firecrawl call?").
7. **DuckDB note** — the JSONL is directly DuckDB-queryable: `duckdb -c "SELECT route, count(*) FROM read_json_auto('logs/turns.jsonl') GROUP BY route"` (JSONL stays canonical).
8. **pip fallback** — documented for evaluators without uv.
9. **Worked paraphrase example (PLAN §15.2)** — a verbatim re-ask → hit; a paraphrase → depends; summary docs (question-altitude embeddings) raise hit rates.
10. **Why this is deliberately not a ReAct/tool-calling agent (PLAN §2)** — the memory-first hit/miss decision is a deterministic threshold branch in **code** (a pure router), not model judgment, so "memory-first" stays verifiable and the hit/miss log stays reliable; parallelism lives *inside* `fetch_pages` (`asyncio.gather` + semaphore), not as graph fan-out. This graded design-rationale point is owned here (M6 README finalisation).

### 6.11 The 5 evaluator commands (demoable outcome)

Live path (needs `OPENAI_API_KEY` + Docker):

```
1. git clone <repo> && cd memory-first-agent
2. curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv
3. make setup        # uv sync + copy .env (add OPENAI_API_KEY)
4. make redis-up     # docker compose up -d --wait (redis:8.2)
5. make run          # chat REPL — ask a question twice: MISS then HIT
```

Zero-key path (no keys, matches CI): `make test` and `python scripts/eval_lifecycle.py --mock`.

> **Spec note:** PLAN §10.4 lists these five steps as the quickstart; naming them "the 5 commands" is the minimal-assumption reading of the §13 demoable outcome. Change freely (e.g. `make demo` may collapse steps 4–5).

### 6.12 Relevant env defaults (from `Settings`, unchanged here)

`SIMILARITY_THRESHOLD=0.7` (inclusive), `MEMORY_TOP_K=5`, `EMBEDDING_DIM=1536`, `MEMORY_INDEX_NAME=web_memory`, `MEMORY_TTL_SECONDS=604800`, `WAIT_CAP_SCALE=1.0` (tests set `0`), `WEB_CONTEXT_CHUNKS_PER_PAGE=2`, `TURN_LOG_PATH=logs/turns.jsonl`. Canonical dependency pins (verify at tag, PLAN §14): `langgraph>=1.2,<2`, `redis>=6.2,<7`, `redisvl>=0.22,<0.24`, `httpx>=0.28`, `trafilatura>=2.1,<3`, `ddgs>=9,<10`, `openai>=2`, `tenacity~=9.1`, `structlog~=26.1`, `pytest~=8.4`, `respx~=0.23`.

---

## 7. BDD acceptance scenarios

```gherkin
Feature: Canonical test fixtures (conftest.py)
  # tests/conftest.py — owned by M6 (ruling A)

  @unit
  Scenario: Zero-wait settings scale every backoff to zero        # FR-M6-01
    Given the settings fixture is loaded
    When a 4-attempt tenacity-wrapped call that always raises a retryable error runs under the fixture
    Then settings.wait_cap_scale is exactly 0
    And the call completes all 4 attempts with total sleep time under 0.05 seconds

  @unit
  Scenario: FakeLLM is deterministic and reports usage             # FR-M6-02
    Given the fake_llm fixture
    When complete("sys", []) is awaited twice
    Then both results have identical text
    And each result.usage has integer input_tokens and output_tokens and a "model" string

  @unit
  Scenario: FakeLLM.parse returns a valid schema instance          # FR-M6-02
    Given the fake_llm fixture with a schema_factory for QueryClassification
    When parse("sys", "hello", QueryClassification) is awaited
    Then the first element is a valid QueryClassification instance
    And the second element is a usage dict

  @unit
  Scenario: FakeEmbedder produces bit-stable 1536-dim unit vectors # FR-M6-03
    Given the fake_embedder fixture
    When "redis vector search" is embedded twice
    Then both vectors are identical
    And each vector has length 1536
    And the L2 norm of each vector is within 1e-6 of 1.0

  @unit
  Scenario: FakeEmbedder scores a query-dominated text as similar  # FR-M6-03
    Given the fake_embedder fixture
    When q = embed("how does redis vector search work")
    And  p = embed("how does redis vector search work how does redis vector search work how does redis vector search work")
    Then the cosine similarity of q and p is >= 0.70   # query-dominated -> cosine ~ 1.0 (see gotcha §10.2)

  @unit
  Scenario Outline: FakeEmbedder cosine reflects token overlap     # FR-M6-03
    Given the fake_embedder fixture
    When two texts with "<overlap>" token overlap are embedded
    Then their cosine similarity is "<relation>"
    Examples:
      | overlap    | relation      |
      | identical  | equal to 1.0  |
      | disjoint   | below 0.70    |

  @integration
  Scenario: redis_url yields when Redis answers PING               # FR-M6-04
    Given a live redis:8.2 on the configured URL
    When the redis_url fixture resolves
    Then it returns the URL and does not skip

  @unit
  Scenario: redis_url skips cleanly when Redis is down             # FR-M6-04
    Given no Redis is reachable at the configured host and port
    When a test requesting the redis_url fixture runs
    Then the test is reported as skipped, not errored

  @integration
  Scenario: clean_index leaves an empty index                      # FR-M6-05
    Given the clean_index fixture has run
    When knn(any_vector, k=5) is awaited
    Then it returns an empty list


Feature: Redis integration round-trip
  # tests/integration/test_redis_store.py — owned by M6

  @integration
  Scenario: Index creation is idempotent                           # FR-M6-06
    Given the web_memory index already exists
    When the index is created a second time
    Then no error is raised
    And exactly one web_memory index exists

  @integration
  Scenario: Stored chunk is retrievable by KNN with its text       # FR-M6-07
    Given clean_index and a page with one chunk "Redis stores vectors next to data"
    And the chunk is embedded with fake_embedder and stored
    When knn(embed("Redis stores vectors next to data"), k=5) is awaited
    Then the top hit's text equals "Redis stores vectors next to data"
    And the top hit's url and title equal the stored page's url and title

  @integration
  Scenario: URL, title and fetched_at survive the round-trip       # FR-M6-08
    Given a chunk stored with fetched_at epoch 1751625600 and url "https://redis.io/x"
    When it is retrieved via knn
    Then the returned MemoryHit.url is "https://redis.io/x"
    And MemoryHit.stored_at is the ISO-8601 form of epoch 1751625600
    And MemoryHit.stored_at parses as a valid ISO-8601 timestamp

  @integration
  Scenario Outline: Distance converts to the exact expected similarity  # FR-M6-09
    Given a unit vector "<stored>" is stored in clean_index
    When knn is queried with unit vector "<query>"
    Then the returned similarity is "<similarity>"
    Examples:
      | stored     | query                    | similarity               |
      | e0         | e0 (identical)           | exactly 1.0              |
      | e0         | e1 (orthogonal)          | exactly 0.0              |
      | e0         | cosine-0.70 vector       | within 1e-6 of 0.70      |

  @integration
  Scenario: The exact 0.70 boundary is an inclusive hit at the store boundary  # FR-M6-09
    Given a stored vector and a query vector with cosine similarity 0.70
    When the MemoryHit similarity is computed as 1 - vector_distance
    Then similarity is within 1e-6 of 0.70
    And with SIMILARITY_THRESHOLD 0.7 this routes as a memory hit (>= is inclusive)


Feature: End-to-end memory-first lifecycle
  # tests/e2e/test_lifecycle.py — owned by M6; THE assignment core proof
  # Only memory_miss_web_search -> memory_hit is proven e2e here; blocked / degraded_web /
  # failed routes are covered upstream (see §2 "Non-happy-path route coverage").

  @e2e
  Scenario: Turn 1 misses memory and searches the web              # FR-M6-10
    Given real Redis with an empty index
    And respx mocks POST api.tavily.com/search to return one result
    And respx mocks the result URL to return HTML repeating the question verbatim
    And FakeLLM and FakeEmbedder are injected
    When the agent answers "How does Redis vector search work?"
    Then the route is "memory_miss_web_search"
    And at least one source has origin "web"
    And the Tavily search endpoint call_count is 1

  @e2e
  Scenario: Identical turn 2 hits memory and never touches the web # FR-M6-11
    Given turn 1 above has completed and ingested the page
    When the agent answers the identical question a second time
    Then the route is "memory_hit"
    And the returned similarity is >= 0.70
    And the Tavily search endpoint call_count is still 1

  @e2e
  Scenario: The memory hit cites a memory-origin source            # FR-M6-11
    Given turn 2 has produced a memory_hit
    Then at least one returned source has origin "memory"
    And the cited URL equals the final URL fetched on turn 1

  @e2e
  Scenario: Each turn appends exactly one TurnRecord to the log     # FR-M6-11b
    Given turns 1 and 2 above have completed
    When settings.turn_log_path is read
    Then it contains exactly two JSON lines
    And the first line's route is "memory_miss_web_search"
    And the second line's route is "memory_hit" with similarity_top >= 0.70
    And each line carries a populated tokens block


Feature: Lifecycle eval harness (hard gate)
  # scripts/eval_lifecycle.py — owned by M6

  @integration
  Scenario: --mock passes when every question is miss-then-hit     # FR-M6-12
    Given a live redis:8.2 and no API keys
    When "python scripts/eval_lifecycle.py --mock" runs
    Then every fixed question routes memory_miss_web_search then memory_hit (sim >= 0.70)
    And the process exits 0

  @integration
  Scenario: --mock exits 1 when a question fails the contract      # FR-M6-12
    Given a question whose turn-2 page is NOT query-dominated, so its stored chunk embeds below 0.70 to the query
    When "python scripts/eval_lifecycle.py --mock" runs
    Then the failing question is named in the output
    And the process exits 1

  @manual
  Scenario: real-key mode fails readably without a key             # FR-M6-13
    Given OPENAI_API_KEY is unset and --mock is omitted
    When "python scripts/eval_lifecycle.py" runs
    Then it prints a readable "OPENAI_API_KEY required" message
    And it exits non-zero without a Python traceback

  @manual
  Scenario: real-key mode runs the live lifecycle pre-submission   # FR-M6-13
    Given a valid OPENAI_API_KEY and Docker Redis running
    When "python scripts/eval_lifecycle.py" runs
    Then each question is verified miss-then-hit against real OpenAI and real search
    And the process exits 0


Feature: Grounding eval harness (demonstration)
  # scripts/eval_grounding.py — owned by M6

  @unit
  Scenario: --mock scores all three dimensions keylessly           # FR-M6-14, FR-M6-15
    Given no API key and no Redis
    When "python scripts/eval_grounding.py --mock" runs
    Then a per-case row is printed for each of the 5-8 fixed cases
    And an aggregate for grounding, citation-validity and abstention is printed
    And the process exits 0

  @unit
  Scenario: An abstain case expects a refusal                      # FR-M6-14
    Given a fixed case whose context is empty
    When the answerer runs over that context
    Then the expected behaviour is "abstain"
    And the judge scores abstained_correctly for a refusal answer

  @unit
  Scenario: A grounded case expects a valid citation               # FR-M6-14
    Given a fixed case whose context contains the answer and a source_url
    When the answerer runs and cites that source_url
    Then the judge scores grounded and citations_valid true

  @manual
  Scenario: Output honestly labels itself a demonstration          # FR-M6-14
    When the grounding scorecard is printed
    Then it states it is a demonstration, not a benchmark


Feature: CI pipeline finalized
  # .github/workflows/ci.yml — skeleton from M1, finalized in M6

  @manual
  Scenario: Single job runs the stages in the required order       # FR-M6-16
    Given the ci.yml build job
    When ci.yml is inspected
    Then its steps run in order: ruff, unit, integration/e2e, eval_lifecycle --mock, eval_grounding --mock, coverage report

  @manual
  Scenario: CI uses zero real secrets                              # FR-M6-16
    When ci.yml is inspected
    Then it contains no "secrets." reference
    And all API-dependent steps run with fakes

  @manual
  Scenario: Coverage is reported but never gates                   # FR-M6-16
    When the coverage step runs
    Then it prints a coverage report
    And no --cov-fail-under or equivalent threshold is present

  @manual
  Scenario: CI environment matches the shipped environment         # FR-M6-17
    When ci.yml is inspected
    Then the redis service image is exactly "redis:8.2"
    And setup-python reads python-version-file ".python-version"
    And every actions/* reference is pinned to a version (none use @main)


Feature: Auto-generated documentation
  # scripts/render_graph.py, scripts/capture_demo.py — owned by M6

  @unit
  Scenario: render_graph writes the real mermaid diagram           # FR-M6-18
    Given the compiled graph built with fake resources
    When "python scripts/render_graph.py" runs
    Then README.md and docs/architecture.md contain a mermaid block between the markers
    And the block names all 10 nodes (guard_input ... log_turn)

  @unit
  Scenario: render_graph is idempotent                             # FR-M6-18
    Given render_graph has already run once
    When it runs a second time
    Then the mermaid content between the markers is byte-identical

  @manual
  Scenario: capture_demo records a miss then a hit                 # FR-M6-19
    Given a valid OPENAI_API_KEY and Docker Redis running
    When "python scripts/capture_demo.py" runs the same question twice
    Then docs/demo_transcript.md shows a MISS with web sources then a HIT with sim >= 0.70


Feature: Final documentation and release
  # README.md, AI_USAGE.md, docs/ai_prompts/, v1.0 tag

  @manual
  Scenario Outline: README contains every required verbatim section  # FR-M6-20
    When README.md is inspected
    Then it contains "<section>"
    Examples:
      | section                                             |
      | the verbatim §10.4 quickstart incl. the zero-keys line |
      | the verbatim T1-T4 threat-model table               |
      | the 0.70 calibration note                           |
      | the TTL-is-coarse note and ETag production upgrade  |
      | the robots.txt limitation and its production fix    |
      | why fetch+markdown stay in-house                    |
      | the DuckDB read_json_auto note                      |
      | the pip fallback instructions                       |
      | the worked paraphrase example from §15.2            |
      | why the design is deliberately not a ReAct/tool-calling agent (§2) |

  @manual
  Scenario: AI_USAGE.md is complete and labels the full log        # FR-M6-21
    When AI_USAGE.md is inspected
    Then all 8 sections from PLAN §11 are present
    And it points to docs/ai_prompts/ labelled "the complete instruction record"
    And docs/ai_prompts/ contains a chronological per-milestone log through M6

  @manual
  Scenario: Time-sensitive facts are re-verified before tagging    # FR-M6-22
    Given the PLAN §14 verify-before-implementation list
    When each row is re-checked immediately before tagging
    Then a date-stamped note records each item's status
    And any price/id drift has been corrected in config and MODEL_CHOICES.md

  @manual
  Scenario: v1.0 is tagged on a green commit                       # FR-M6-23
    Given CI is green and all M6 FRs pass on HEAD
    When the release is tagged
    Then "git tag" lists "v1.0"

  @manual
  Scenario: The evaluator reaches a live miss-then-hit in 5 commands  # FR-M6-24
    Given a fresh clone, OPENAI_API_KEY and Docker
    When the 5 documented commands are run in order
    Then the chat REPL answers the same question first as a MISS then as a HIT

  @unit
  Scenario: The dockerless zero-key unit path passes with no keys   # FR-M6-24
    Given no API keys are set and no Redis is running
    When "make test" runs
    Then the unit suite passes and integration/e2e report skipped

  @integration
  Scenario: The zero-key eval gate passes against the CI Redis      # FR-M6-24
    Given no API keys are set and a live redis:8.2 (the CI service)
    When "python scripts/eval_lifecycle.py --mock" runs
    Then it exits 0 with no keys
```

---

## 8. Task breakdown

Ordered; `[P]` = parallel-safe once its prerequisites exist. Each task ≤ ~1 h.

- **T-M6-01** — Write `tests/conftest.py`: `settings` (WAIT_CAP_SCALE=0, tmp turn-log), `FakeEmbedder`, `fake_embedder`, `FakeLLM`, `fake_llm`. Confirm existing M2/M4/M5 unit tests still pass against these canonical fixtures. *(FR-M6-01, 02, 03)*
- **T-M6-02** — Add `redis_url` (skip-if-unreachable) and `clean_index` fixtures. Verify unit run skips integration/e2e cleanly with Redis down. *(FR-M6-04, 05)*
- **T-M6-03** [P after 02] — Write `tests/integration/test_redis_store.py`: idempotent create, round-trip, metadata survival, known-vector similarity incl. the 0.70 boundary. Run against `make redis-up`. *(FR-M6-06, 07, 08, 09)*
- **T-M6-04** [P after 02] — Author the shared `build_test_resources()` helper and the `resources`/`agent` fixtures that wrap it (assemble `AgentResources`: fakes for LLM/embedder, real store, respx-mocked search/fetch, a real `TurnLogger` at `settings.turn_log_path`; the plain helper is importable by the eval/render scripts). Then write `tests/e2e/test_lifecycle.py`: respx-mock Tavily + page GET; assert turn 1 miss (call_count 1) and turn 2 hit (sim ≥ 0.70, call_count still 1); read back the tmp `turns.jsonl` and assert exactly two TurnRecords with routes `memory_miss_web_search` then `memory_hit`. *(FR-M6-10, 11, 11b)*
- **T-M6-05** [P after 04] — Write `scripts/eval_lifecycle.py` with `--mock` gate (exit 1 on any non-miss-then-hit) and real-key mode (readable no-key error); reuses `build_test_resources()` from T-M6-04 to run the full lifecycle. *(FR-M6-12, 13)*
- **T-M6-06** [P] — Write `scripts/eval_grounding.py` (~40–60 lines): 5–8 cases, nano judge, `--mock` keyless scorecard, honest labelling. *(FR-M6-14, 15)*
- **T-M6-07** — Finalize `.github/workflows/ci.yml`: single job, correct order, `redis:8.2` service, Python from `.python-version`, pinned actions, coverage report no gate, zero secrets. Push and confirm green. *(FR-M6-16, 17)*
- **T-M6-08** [P after 04] — Write `scripts/render_graph.py` (uses `build_test_resources()` from T-M6-04 to compile the graph); run it; verify all 10 nodes render and the output is idempotent between markers in README + `docs/architecture.md`. *(FR-M6-18)*
- **T-M6-09** — Write `scripts/capture_demo.py`; run it once with a real key + Docker Redis; commit `docs/demo_transcript.md` (miss→hit). *(FR-M6-19)*
- **T-M6-10** [P] — Finalize `README.md` with all ten required verbatim sections (§6.10). *(FR-M6-20)*
- **T-M6-11** [P] — Finalize `AI_USAGE.md` (8 sections) and append the complete M6 prompt log to `docs/ai_prompts/`, labelled "the complete instruction record". *(FR-M6-21)*
- **T-M6-12a** [P] — Re-verify the runtime/service PLAN §14 facts: OpenAI model ids + prices, `temperature=0` support on the pinned `gpt-5.4-mini` id, Tavily request shape, ddgs API, GitHub Models catalog ids, `redis:8.2` FT.* availability, and the openai structured-output method; correct any drift in `config.py` / `.env.example` / `MODEL_CHOICES.md`. *(FR-M6-22)*
- **T-M6-12b** [P] — Re-verify the library-pin PLAN §14 facts: all dependency pins, `redisvl` `load(ttl=)` / `array_to_buffer` / `VectorQuery` signatures, and the `draw_mermaid()` signature; correct any drift in `pyproject.toml`. *(FR-M6-22)*
- **T-M6-13** — Confirm CI green + the 5-command live run + the zero-key path; then `git tag v1.0`. *(FR-M6-23, 24)*

---

## 9. Definition of Done

- [ ] `pytest -m "not integration and not e2e"` passes with **no Redis, no network, no keys**. *(verify: run with Docker stopped; integration/e2e report `skipped`.)*
- [ ] `pytest -m "integration or e2e"` passes against `make redis-up` (`redis:8.2`). *(verify: `make test-integration` green.)*
- [ ] The e2e lifecycle test asserts turn 1 `memory_miss_web_search` (search call_count 1) and turn 2 `memory_hit` (sim ≥ 0.70, search call_count still 1). *(verify: `pytest tests/e2e/test_lifecycle.py -v`.)*
- [ ] `python scripts/eval_lifecycle.py --mock` exits `0` on a healthy build and `1` if any question breaks miss-then-hit. *(verify: `python scripts/eval_lifecycle.py --mock; echo $?`.)*
- [ ] `python scripts/eval_grounding.py --mock` exits `0` and prints a three-dimension scorecard, keyless. *(verify: `python scripts/eval_grounding.py --mock; echo $?`.)*
- [ ] CI is a single green job: ruff → unit → integration/e2e (`redis:8.2`) → `eval_lifecycle --mock` → `eval_grounding --mock` → coverage report; no `secrets.*`; no coverage gate. *(verify: green check on the pushed commit; inspect `ci.yml`.)*
- [ ] `scripts/render_graph.py` regenerates a mermaid diagram (all 10 nodes) into README + `docs/architecture.md`, idempotently. *(verify: run twice; `git diff` between the markers is empty on the second run.)*
- [ ] `docs/demo_transcript.md` shows the captured miss→hit session. *(verify: open the file; MISS-then-HIT visible with sim ≥ 0.70.)*
- [ ] README contains all ten required verbatim sections (§6.10). *(verify: grep each phrase — e.g. "Zero keys needed", "Memory poisoning", "read_json_auto", "not a ReAct".)*
- [ ] **AI_USAGE.md finalized + `docs/ai_prompts/` per-milestone append (this milestone).** M6 prompts appended chronologically; `AI_USAGE.md` has all 8 sections and the literal label "the complete instruction record". *(verify: open both; confirm the M6 entry exists and is not retroactive.)* — **required by every milestone's DoD.**
- [ ] **`DECISIONS.md` finalized** (scaffolded in M1) with the complete standing anti-churn / locked-decision record cited by M2/M3/M5/M6. *(verify: `test -s DECISIONS.md`; it lists the anti-churn cuts.)*
- [ ] PLAN §14 facts re-verified with a date-stamped note; any drift corrected in `config.py` / `.env.example` / `MODEL_CHOICES.md`. *(verify: the note exists and lists each §14 row.)*
- [ ] **Demoable outcome (PLAN §13, M6 row): the evaluator runs everything in 5 commands.** *(verify: fresh clone → the 5 commands (§6.11) → live MISS-then-HIT; and the zero-key `make test` + `eval_lifecycle --mock` path passes.)*
- [ ] `git tag v1.0` created on the green commit. *(verify: `git tag` lists `v1.0`.)*

---

## 10. Risks & gotchas

Milestone-specific traps, pulled from PLAN §14/§15 and the section notes.

1. **Distance ≠ similarity (PLAN §4.3, §15.1).** The integration test must assert `similarity == 1 - vector_distance` (NOT `1 - d/2`). The 0.70 boundary is **inclusive**. If a float32 "true 0.70" returns as `0.699999988`, compare with `>= threshold - 1e-6` and document the decision once — do not loosen the threshold globally.
2. **The e2e turn-2 hit depends on FakeEmbedder token overlap.** If the mocked page does not repeat the query verbatim (or trafilatura strips it below the 200-char floor / 100-char chunk floor), turn 2 can fall below 0.70 and the core proof fails for the wrong reason. Keep the mocked HTML query-dominated and > 200 chars after extraction.
3. **respx only patches httpx.** Redis (`redis.asyncio`) and the fakes are untouched — good, but it means the searcher **must** use the Tavily-httpx path (set a dummy `TAVILY_API_KEY`), else the ddgs fallback (not httpx) escapes respx and `call_count` never increments. This is the same coverage risk M5's "search client holds an `httpx.AsyncClient`" guard test protects.
4. **First query always misses (PLAN §15.7).** Empty index → `knn` returns `[]` → `top_similarity` is `None` → normal miss. The e2e turn 1 relies on this; do not treat empty results as an error.
5. **ddgs fragility at demo time (PLAN §15.4).** ddgs is scraping and only the fallback. `capture_demo.py` and `eval_lifecycle` real-key mode should prefer Tavily; if ddgs is used and throws, the turn must degrade to an explicit "web search unavailable" turn, not a traceback.
6. **AI_USAGE written retroactively is the biggest scoring risk (PLAN §15.5).** Append the M6 prompt log *as you build M6*, not at the end.
7. **Model/price drift (PLAN §14, §15.6).** Prices/ids were verified 2026-07-04; re-verify at tag. `temperature=0` support on `gpt-5.4-mini` is version-sensitive across snapshots — confirm against the pinned id. Do not tag on stale numbers.
8. **Scope creep (PLAN §15.3, DECISIONS anti-churn).** Do not add a coverage gate, a Redis turn-log mirror, canary/output-defang, a gray-zone LLM guard, or the 0.50 salvage route while "polishing" M6. They were cut twice.
9. **Evaluator without uv/Docker (PLAN §15.8).** The pip fallback must be documented and the unit suite must pass keyless and dockerless — verify by running the unit subset in a clean venv.
10. **CI service vs docker-compose drift.** The CI Redis image must stay `redis:8.2` exactly (matching docker-compose) so tested == shipped; a bump on one side only silently breaks the "same environment" guarantee.

---

## 11. Spec Kit mapping

- **Feeds `/specify` (spec.md):** §1 Goal & context, §2 Scope (all three subsections), §5 Functional requirements, and §7 BDD acceptance scenarios — these define *what* M6 must prove and deliver and the observable pass/fail conditions.
- **Feeds `/plan` (plan.md):** §3 Prerequisites & interfaces consumed, §4 Interfaces provided, §6 Technical specification (fixture code, test structures, `ci.yml`, script contracts, README section list, the 5 commands), and §10 Risks & gotchas — the *how*, the seams, and the traps.
- **Feeds `/tasks` (tasks.md):** §8 Task breakdown (T-M6-01…13 with `[P]` markers and FR references) and §9 Definition of Done (the verify commands and the demoable outcome that close each task).
