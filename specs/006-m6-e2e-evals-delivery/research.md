# Phase 0 Research — M6 Integration/E2E, Evals, CI, Docs, v1.0

**Date**: 2026-07-06 | **Feature**: 006-m6-e2e-evals-delivery
**Method**: a live parallel repo probe of `memory-first-agent` (main `6a582e4`, 103 tests
green) across six subsystems + a seventh live library-surface verification inside the
project venv (Constitution P-IX), run **before** any design was fixed. M6 is a pure-integration
milestone: its fixtures, tests, and scripts *call* the shipped M1–M5 code, so the whole
plan hinges on the exact shipped signatures — not the source spec's minimal-assumption
guesses. The probe confirmed most guesses, **resolved** the two the source spec flagged as
"unsure" (`PageFetcher.fetch`, `TurnLogger.log`), and found several deltas recorded below so
`/speckit-tasks` and `/speckit-implement` do not build against fiction.

## R0 — Repo-state probe: source-spec deltas (main `6a582e4`)

| # | Source-spec assumption | Actual shipped state | Consequence for M6 |
|---|---|---|---|
| 1 | §3 "conftest ordering seam": M2/M4/M5 tests reference `FakeLLM`/`FakeEmbedder`/`settings` fixtures that M6 finalizes | **`conftest.py` does NOT exist anywhere.** All 12 unit tests build `Settings()` inline and define **local** fakes; three (`test_classifier_parsing`, `test_guardrails`, `test_turnlog`) literally comment *"the M6 conftest does not exist yet"* | M6 **creates** conftest from scratch (D1). It does **not** rewrite the 12 unit files (Ruling A). The de-facto fake shapes to match: `FakeEmbedder(dim=1536; async embed(texts))`, `FakeChatLLM(async complete(system,messages)->CompletionResult; async parse(system,user,schema)->(obj,usage))` |
| 2 | `PageFetcher.fetch` signature "unsure" (spec note) | **Resolved**: Protocol + concrete `HttpxPageFetcher` both `async def fetch(self, urls: list[str]) -> list[FetchedDoc]` (interfaces.py:57, web/fetch.py:103) | No guess needed; e2e/evals call `fetch(urls)` |
| 3 | `TurnLogger` append method "unsure" (spec note) | **Resolved**: `def log(self, record: dict) -> None` — **synchronous**, takes a pre-built dict; `TurnLogger(path)` ctor (analytics/turnlog.py:19,22). Record built by a separate module-level `build_turn_record(state, settings)` | e2e wires a real `TurnLogger(settings.turn_log_path)`; asserts by reading the JSONL back |
| 4 | FR-012 asserts record fields `route`, `similarity_top`, `tokens` | **Confirmed names, with mapping**: record `similarity_top` ← state `top_similarity` (turnlog.py:56); record `tokens` is **keyed by role** (`answer_llm`/`analytics_llm`), each `{model,input,output}`, `{}` if unpopulated (turnlog.py:38-46); timestamp field is **`ts`** not `timestamp` | FR-012 asserts `route`/`similarity_top` and a **non-empty** `tokens`; the fakes must return real usage so nodes populate `state["tokens"]` (D7) |
| 5 | FR-008 "chunk stored with `fetched_at` epoch 1751625600" | `store()` stamps `fetched_at = int(time.time())` **itself** (no param); `stored_at` is **derived at the knn read boundary** via `_epoch_to_iso(fetched_at)` (store.py:64,114); missing → epoch 0 | Metadata test **monkeypatches the store clock** to a fixed epoch, then asserts `stored_at == _epoch_to_iso(fixed)` (D5) |
| 6 | FR-006 "creating the index twice is idempotent" | redisvl `create(overwrite=False)` **errors** on an existing index; idempotency is a two-step guard: `ensure_index()` = `if await index.exists(): return False` then `create(overwrite=False)` (schema.py:62-67). `wipe_index()` = `create(overwrite=True, drop=True)` + purge of `doc:*` meta hashes | FR-006 calls **`ensure_index(index)` twice** (2nd returns False, one index); `clean_index` uses `wipe_index` (D4) |
| 7 | §6.4 respx "search endpoint call_count" | `TavilySearcher._post` is wrapped by `tavily_retry`, `_fetch_one` by `fetch_retry` (M5). Tavily path selected by **truthy `settings.tavily_api_key`** (search.py:90). Fetch stores the **post-redirect** URL as doc identity (fetch.py:133) | respx routes must return **happy-path 200** (a retryable status would be hit N times, breaking `call_count==1`) and **not redirect** (a redirect makes the cited URL ≠ Tavily URL, breaking FR-011). A dummy `TAVILY_API_KEY` forces the httpx path (D3) |
| 8 | §6.8 `render_graph.py` uses `build_test_resources()` | `render_graph.py` **already exists** (keyless), builds `AgentResources(...all None)` + `Settings(_env_file=None)`, prints `draw_mermaid()`, is **idempotent**, and writes **no files**. Routing it through `build_test_resources()` (which builds a **real Redis store**) would make graph-render need Redis | FR-019 **extends** the existing keyless `render_graph.py` (add the between-marker file splice); it keeps its all-None resources. `build_test_resources()` (real store) is for the e2e + evals only (D2) |
| 9 | e2e turn-2 hit ≥ 0.70 with `FakeEmbedder` | `FakeEmbedder` is bag-of-words hash→unit vector; a query-dominated chunk embeds ~1.0 to the query. `to_markdown` drops pages < **200 extracted chars** (MIN_MARKDOWN_CHARS). Ingest also stores a FakeLLM-generated **summary doc** that is indexed and KNN-eligible | The fetch fixture returns HTML **repeating the query verbatim, > 200 chars**; the query-dominated chunk wins KNN (max), so `top_similarity ~1.0 ≥ 0.70`. The lower-scoring summary doc never becomes the max (D8) |
| 10 | `SourceRef` carries provenance | `SourceRef` = exactly `{url, title, origin: Literal["memory","web"]}` — **no** stored_at/flags. `MemoryHit` has **no `origin`**. `answer_from_memory`/`answer_from_web` build sources via a shared `_dedupe_sources(hits, origin)` (answer.py:21) | FR-010/011 dict-access `s["origin"]`; the memory-origin + cited-URL-equals-turn-1 assertions rely on `_dedupe_sources(hits,"memory")` + the non-redirecting fetch route (D9) |
| 11 | §6.7 CI "finalize to a single job with the full pipeline" | Current `ci.yml` is a **single job, lint + unit only**: checkout@v4, setup-uv@v6, setup-python@v5 (`python-version-file: .python-version`), `uv sync`, `ruff check .`, `pytest -m "not integration and not e2e" --cov --cov-report=term`. **No redis service, no integration/e2e/eval steps, no coverage-report step.** Markers `integration`/`e2e` already declared in pyproject but **unused** | M6 adds a `redis:8.2` service + `REDIS_URL`, the integration/e2e step, both eval `--mock` steps, and an explicit coverage report; keeps one job / zero secrets / pinned actions; uses `uv sync --frozen` (D10) |
| 12 | FR-017 "ruff (lint + **format check**)" | Current CI + `make lint` run `ruff check .` **only**; the M5 quickstart explicitly **deferred** a repo-wide `ruff format` to "an M6 option" (16 pre-existing files predate the formatter) | M6 runs a one-time `ruff format .` finalization pass (cosmetic, zero logic change, separate commit) and gates **both** `ruff check .` and `ruff format --check .` (D11); fallback documented |
| 13 | FR-023 re-verify `temperature=0` on `gpt-5.4-mini` | `MODEL_CHOICES.md` marks it **⏳ PENDING — requires a real OPENAI_API_KEY**; GitHub Models serves **no** gpt-5.4* ids (37 probed); temperature=0 returns 200 only on dev alias `gpt-4.1-mini` | Confirms Clarification Q1: this fact is **pending real-key capture**; every other §14 fact is keyless-verifiable at tag (D14) |
| 14 | MemoryStore protocol = `knn` + `store` | Protocol **also** declares `async def is_fresh(self, h: str) -> bool` (interfaces.py:50); there are **five** pure routers (adds `route_after_fetch`), not four | No M6 impact beyond awareness; `build_test_resources` uses the real `RedisMemoryStore` which implements all three |
| 15 | §6.11 the "5 commands" / `make demo` | Makefile targets confirmed: `setup redis-up redis-down run ask analytics wipe test test-integration lint demo`. `make demo` == `uv run memagent chat` (does not collapse steps); `make wipe` runs the `wipe-memory` subcommand (target name ≠ CLI name) | README documents the literal 5 commands (clone → install uv → `make setup` → `make redis-up` → `make run`); note the `wipe`/`wipe-memory` name split (D-doc) |

## Live library verifications (P-IX, run 2026-07-06 in-project venv)

| Check | Method | Result |
|---|---|---|
| respx route `.call_count` | `@respx.mock` GET route + httpx request | `call_count == 1` held; **respx 0.23.1 / httpx 0.28.1** (pins satisfied) |
| redisvl create idempotency | signature + source probe | `AsyncSearchIndex.create(overwrite=False, drop=False)`; `.exists()` present; idempotency is **exists-guard + create**, not one primitive. **redisvl 0.23.0** (pin `>=0.22,<0.24` satisfied) |
| redisvl `VectorQuery` | signature probe | `VectorQuery(vector, vector_field_name, return_fields, dtype='float32', num_results, ...)`; store uses `vector_field_name='embedding'`, `num_results=k` — valid |
| langgraph `draw_mermaid()` | ran `scripts/render_graph.py` | **langgraph 1.2.7**; emits all 10 node lines + `\t__start__ --> guard_input;` + `guard_input -.-> log_turn;`; **byte-identical across two runs** (idempotent); writes no files. NB `langgraph.__version__` raises — use `importlib.metadata` |
| pytest stack | `--version` probes | pytest 8.4.2, pytest-asyncio 1.4.0, pytest-cov 7.1.0, coverage 7.15.0; `asyncio_mode="auto"` set; `uv run coverage`/`pytest` work |
| openai parse surface | source probe | **openai 2.44.0**; clients bind the **stable** `chat.completions.parse` / `.create` (not beta, not responses) |
| Test baseline | `uv run pytest -q` (implied by 103-green main) | 103 passed on main `6a582e4` |

## Decisions

### D1 — `conftest.py` is NEW; the 12 existing unit tests are NOT rewritten
**Decision**: M6 authors `tests/conftest.py` from scratch (it does not exist — R0 #1). It
defines the canonical fixtures the source spec §6.2 names — `settings` (`WAIT_CAP_SCALE=0`,
tmp `turn_log_path`), `fake_embedder`, `fake_llm`, `redis_url` (ping-or-skip via `socket`),
`clean_index` — plus the shared fakes (`FakeEmbedder`, `FakeLLM`) and the
`build_test_resources()` helper (D2) and its `resources`/`agent` fixtures. The 12 existing
unit files keep their **local** inline fakes and inline `Settings()` construction unchanged
(Ruling A — M6 does not own or rewrite them); they already pass and do not import conftest.
**Rationale**: the "conftest ordering seam" the source spec describes does not exist in
reality — no upstream test references a central fixture, so there is nothing to reconcile and
centralizing would rewrite 12 upstream-owned files for zero gain (churn + ownership
violation). Fixture *names/signatures* still follow §6.2 so future tests share them.
**Alternatives**: centralize all fakes and edit the 12 files — rejected (rewrites upstream-owned tests).

### D2 — `build_test_resources()` (real store) vs `render_graph.py` (keyless, unchanged)
**Decision**: a new plain, importable `build_test_resources(settings, redis_client)` in
`conftest.py` assembles `AgentResources(settings, memory=RedisMemoryStore(settings, client),
embedder=FakeEmbedder(dim), chat_llm=FakeLLM(), analytics_llm=FakeLLM(), searcher=<real
TavilySearcher/FallbackProvider>, fetcher=<real HttpxPageFetcher>, turn_logger=TurnLogger(
settings.turn_log_path))`. The pytest `resources`/`agent` fixtures wrap it; **`eval_lifecycle`
imports and calls it directly** (after a repo-root `sys.path` shim — `tests/` is not an installed
package, recheck H); **`eval_grounding` does NOT use it** (redis-less; FakeLLM answerer+judge only —
D13, recheck I). **`render_graph.py` is NOT routed through it** — it keeps its
existing all-`None` keyless `AgentResources` (graph *compilation* touches no client and must
stay Redis-less), and FR-019 only *adds* the between-marker file splice.
**Rationale**: `build_test_resources` builds a real Redis store (needs a live `redis:8.2`);
graph-render must remain keyless+dockerless (R0 #8). Conflating them (source §6.8) would break
render's keyless property. **Alternatives**: one universal builder — rejected (couples
render to Redis).

### D3 — respx route discipline: 200-only, no redirect, dummy TAVILY_API_KEY
**Decision**: the e2e + `eval_lifecycle --mock` set `TAVILY_API_KEY="test-key"` (forces the
httpx/Tavily path — search.py:90) and register two respx routes: `POST
https://api.tavily.com/search` → `200 {"results":[{"url":U,"title":T,"content":S}]}` and `GET
U` → `200 text/html <article>…query-dominated…</article>` (**no redirect**). Both are
happy-path 200.
**Rationale**: `TavilySearcher._post` is wrapped by `tavily_retry` and `_fetch_one` by
`fetch_retry` (R0 #7) — a retryable-status route would be hit N times and break
`call_count==1`; a redirecting fetch route would make the stored/cited URL the redirect target
(fetch.py:133), breaking FR-011's "cited URL == turn-1 URL". Response shape must be
`{"results":[{url,title,content}]}` (search.py maps `content`→snippet). **Alternatives**: a
counting-fake searcher/fetcher (Clarification Q2 rejected it as weaker proof).

### D4 — FR-006 idempotent-create uses `ensure_index`, not raw `create`
**Decision**: the idempotency test calls `ensure_index(index)` twice — first `True` (created),
second `False` (already exists), no error, exactly one `web_memory` index. `clean_index` uses
`wipe_index(index)` (`create(overwrite=True, drop=True)` + `doc:*` purge) so each test starts
truly empty (turn 1 is a real miss — the purge also clears the M3 freshness gate).
**Rationale**: redisvl `create(overwrite=False)` **raises** on an existing index (R0 #6); the
shipped idempotency contract is `ensure_index`'s exists-guard, which is what FR-006 must assert.

### D5 — FR-008 metadata: monkeypatch the store clock for a deterministic epoch
**Decision**: `stored_at` is derived at the knn boundary from `fetched_at` (`store()` stamps
`int(time.time())` itself). The metadata test monkeypatches the store module's `time.time`
(via `monkeypatch.setattr`) to a fixed epoch, stores, `knn`, and asserts
`hit["stored_at"] == _epoch_to_iso(fixed)` (importing the same converter) **and** that
`stored_at` parses as ISO-8601, and `url`/`title` round-trip intact.
**Rationale**: `store()` takes no `fetched_at` param (R0 #5), so the exact epoch→ISO
conversion can only be pinned by controlling the clock through the production path.
**Alternatives**: assert `parses-as-ISO` + `epoch ≈ now` (looser) — kept as a fallback if
monkeypatching the module clock proves brittle.

### D6 — FR-009 distance→similarity and the exact 0.70 pair
**Decision**: confirmed single site `distance_to_similarity(d) = 1.0 - d` (store.py:60). The
test stores a hand-built unit vector and queries with: the identical vector → `similarity ==
1.0`; an orthogonal unit vector → `similarity == 0.0`; and `w = [0.7, sqrt(1-0.49), 0…]` vs
`u=[1,0,…]` → cosine 0.70 → Redis `vector_distance` 0.30 → `similarity` within `1e-6` of 0.70.
With `SIMILARITY_THRESHOLD=0.7` this is an inclusive hit.
**Rationale**: exercises the real FLAT cosine index; the `1e-6` tolerance absorbs float32
boundary noise without loosening the global threshold (Constitution II).

### D7 — FR-012 tokens/similarity_top come from the real turn, with proper fake usage
**Decision**: the e2e reads the tmp `turns.jsonl` and asserts exactly two objects with
`route == ["memory_miss_web_search","memory_hit"]`, the 2nd `similarity_top >= 0.70`, and each
with a **non-empty** `tokens` block. To make `tokens` non-empty, `FakeLLM.complete()` and
`.parse()` return a usage dict shaped `{"input_tokens":int,"output_tokens":int,"model":str}` so
the answer/classify nodes populate `state["tokens"]["answer_llm"|"analytics_llm"]`, which
`build_turn_record` remaps to `{model,input,output}` (R0 #4). `similarity_top` (record) ← state
`top_similarity`.
**Rationale**: the record's `tokens` is `{}` unless the nodes wrote usage upstream — a fake
returning empty usage would silently produce `tokens: {}` and fail FR-012 for the wrong reason.

### D8 — e2e turn-2 ≥ 0.70 depends on a query-dominated, > 200-char page
**Decision**: the fetch route serves HTML whose extractable body repeats the question verbatim
(query-dominated) and exceeds 200 chars post-trafilatura, so the stored chunk embeds ~1.0 to
the repeated query under the bag-of-words `FakeEmbedder`. The FakeLLM-generated summary doc is
also indexed but scores lower and never becomes the KNN max.
**Rationale**: the #2 milestone gotcha — a non-query-dominated or too-short page drops below
0.70 (or is dropped entirely by the 200-char floor) and fails the core proof for the wrong
reason (R0 #9).

### D9 — memory-origin source + cited-URL assertions
**Decision**: FR-011 asserts `any(s["origin"]=="memory")` and that the cited URL equals the
turn-1 fetched URL. This relies on `answer_from_memory` building `SourceRef(origin="memory")`
via `_dedupe_sources(hits,"memory")` and on D3's non-redirecting fetch route (so the stored
URL == the Tavily result URL == the cited URL). The e2e verifies both.
**Rationale**: `SourceRef.origin` is the only provenance channel (R0 #10); a redirect would
break URL identity.

### D10 — CI finalization (single job, redis:8.2, zero secrets)
**Decision**: extend the current single job to run, in order: `ruff check . && ruff format
--check .` → `pytest -m "not integration and not e2e" --cov=memagent --cov-report=term` →
`pytest -m "integration or e2e" --cov=memagent --cov-append --cov-report=term` (with a
`redis:8.2` service + `REDIS_URL=redis://localhost:6379/0`) → `python scripts/eval_lifecycle.py
--mock` → `python scripts/eval_grounding.py --mock` → `coverage report`. Keep
checkout@v4/setup-python@v5/setup-uv@v6 (pinned), `python-version-file: .python-version`, `uv
sync --frozen`; **no `secrets.*`, no `--cov-fail-under`**.
**Rationale**: FR-016/017/018 verbatim; the redis service image must equal docker-compose's
`redis:8.2` (R0 #11). The redis service healthcheck mirrors compose.

### D11 — `ruff format` gating (one-time finalization pass)
**Decision**: run `ruff format .` once as an M6 finalization step (cosmetic; **no logic
change**), committed as a **dedicated** "M6: repo-wide ruff format" commit kept separate from
logic commits, then gate **both** `ruff check .` and `ruff format --check .` in CI (FR-017).
**Rationale**: the M5 quickstart explicitly deferred the repo-wide reformat to "an M6 option";
M6 is the finalization milestone and FR-017 lists "format check". Keeping it a separate,
review-isolated commit prevents the cosmetic diff from obscuring the real M6 work.
**Fallback** (if the reformat diff proves unacceptably broad at implement time): keep
`ruff check .` only and record FR-017's "format check" as satisfied by `ruff check` in the
quickstart — decided at implement time on the actual diff size.

### D12 — Non-happy-path routes are consumed green, not re-proven e2e
**Decision**: the e2e proves only `memory_miss_web_search` → `memory_hit`. `blocked`
(M5 `test_guardrails` T1 + M2 `test_routing` + M4 `test_turnlog`), `degraded_web`/`failed`
(M5 `test_reliability` + M2 routers) are consumed green in CI and NOT re-authored.
**Rationale**: Ruling A ownership; the source §2 "Non-happy-path route coverage" note.

### D13 — Eval harness key/redis requirements and gating
**Decision**: `eval_grounding.py --mock` is **keyless AND redis-less** (FakeLLM as answerer +
judge, `GroundingVerdict` via a passing `schema_factory`), **non-gating** (prints scorecard,
exit 0). `eval_lifecycle.py --mock` needs a live `redis:8.2` (real store) + respx (D3), is a
**hard gate** (exit 1 unless every question is miss-then-hit). `capture_demo.py` is **real-key
only** (Constitution forbids GitHub Models for the recorded demo) → its transcript is pending
real-key capture (Clarification Q1). Question set (D-content): three query-dominated questions
(§6.5 default) — settled at `/tasks`.
**Rationale**: matches §6.5/§6.6 and the zero-key CI contract (Constitution VIII).

### D14 — Pre-tag re-verification: keyless now, one item pending
**Decision**: at tag, re-verify the keyless-verifiable §14 facts — dependency pins (from
`uv.lock`: langgraph 1.2.7, redisvl 0.23.0, httpx 0.28.1, respx 0.23.1, openai 2.44.0, tenacity
~9.1, trafilatura, ddgs, redis client 6.x), the `redisvl` `create`/`VectorQuery`/`array_to_buffer`
signatures, `draw_mermaid()`, and model catalog ids + prices from OpenAI's public pricing —
into a date-stamped note (`docs/verification-2026-07-06.md` or a MODEL_CHOICES/AI_USAGE
section). `temperature=0` on `gpt-5.4-mini` is recorded **"pending real-key capture"** (R0 #13,
Clarification Q1).
**Rationale**: honors Constitution IX + zero-key delivery; the one real-key fact is the open
M4 T019 probe.

### D15 — Test/dir allocation
**Decision**: M6 owns (creates) `tests/conftest.py`, `tests/unit/test_m6_fixtures.py` (keyless
fixture assertions for FR-001/002/003(+004) — audit fix, distinct from the 12 frozen upstream files),
`tests/integration/test_redis_store.py`,
`tests/e2e/test_lifecycle.py`, `scripts/eval_lifecycle.py`, `scripts/eval_grounding.py`,
`scripts/capture_demo.py`, and the FR-019 extension of `scripts/render_graph.py`. It creates the
`tests/integration/` and `tests/e2e/` directories (both absent). The `integration`/`e2e`
pytest markers are already declared in `pyproject.toml` (no config change needed). It does not
author or rewrite the 12 existing unit files.
**Rationale**: Ruling A ownership; the markers were forward-provisioned by M1 (R0 #1, #11).

## R1 — Plan recheck (`/speckit-plan recheck`, 2026-07-06)

An adversarial recheck (6 finder dimensions × general-purpose agents, **each finding independently
verified/refuted against the shipped code** — default REFUTED): 12 candidates, **11 survived**, 1
refuted. Deduped to **9 distinct fixes**, all applied to the artifacts:

| # | Sev | Finding | Fix applied |
|---|---|---|---|
| A | HIGH | Contracts wrote `Agent(build_graph(resources))`; shipped `Agent.__init__(resources)` builds the graph itself (app.py:99-101) → `AttributeError` on first `answer()`. Broke e2e + eval gate + `agent` fixture | `Agent(resources)` in `integration-e2e.md`, `test-fixtures.md`, `eval-harnesses.md` |
| B | HIGH | e2e fetch fixture was a bare `<article>` → trafilatura returns `None` → page dropped → turn 1 `degraded_web`, nothing stored, all core-proof assertions fail (empirically confirmed vs trafilatura 2.1.0; shipped `test_fetch_retry.py` uses the wrapped form) | wrapped to `<html><body><article><p>…</p></article></body></html>` in `integration-e2e.md` |
| C | LOW | `AgentResources` Ref pointed at `app.py / render_graph.py`; defined in `resources.py:22-31` | ref corrected in `data-model.md` |
| D | MED | SC-007 unconditionally required a real transcript, contradicting Q1/FR-020/SC-008 (keyless tag) | SC-007 conditioned on key availability in `spec.md` |
| E | LOW-MED | D11 `ruff format` touches 16 src + 7 unit files, contradicting "untouched" wording (Ruling A itself is fine — cosmetic ≠ rewrite) | reworded plan.md Project Type + quickstart DoD |
| F | LOW-MED | Bare `fake_llm.parse(QueryClassification)` raises `ValidationError` (5 required fields, no defaults); FR-002 needs a `schema_factory`; e2e `analytics_llm` likewise needs one to classify | `test-fixtures.md` FR-002 + `build_test_resources` `analytics_llm` given a schema_factory |
| G | LOW | `(D0)` dangling decision reference (×2) | retargeted to data-model §1 refs in `test-fixtures.md` |
| H | MED | Standalone scripts can't `from tests.conftest import …` under `python scripts/…` (tests/ not installed) → `ModuleNotFoundError` at CI gate | `sys.path.insert(0, <repo root>)` shim documented in `eval-harnesses.md`, `test-fixtures.md`, `spec.md`, `data-model.md` |
| I | LOW | "Both eval scripts import `build_test_resources`" over-generalized (grounding is redis-less) | corrected in `eval-harnesses.md` + this D2 |

**Confirmations (no change needed — verified correct against the code):** ingest summarizes via
`analytics_llm.complete()` (FakeLLM implements it); answer nodes write `state["tokens"]["answer_llm"]`
and classify writes `["analytics_llm"]` in the exact `{model,input,output}` shape (D7 holds — the
record's `tokens` is non-empty from `answer_llm` even if classify degrades); `answer_from_memory`
builds `origin="memory"` with the stored (non-redirected) URL (D9); a dummy `TAVILY_API_KEY` forces
the httpx path and a 200 route does not trip `tavily_retry` (D3); `render_graph.py` correctly stays
keyless (D2); redisvl idempotency via `ensure_index` (D4). **Refuted (1):** the claim that D11
violates Ruling A/D1 — a whitespace-only reformat is not a "rewrite" (tests keep their local fakes
and pass), so Ruling A stands; only the absolute "untouched" *wording* needed fix E.
