# Tasks: Milestone 2 — Memory Path (Embeddings, Store, Threshold Routing, Graph Skeleton)

**Input**: Design documents from `/specs/002-m2-memory-path/`

**Prerequisites**: plan.md, spec.md (4 user stories), research.md, data-model.md, contracts/ (4), quickstart.md

**Tests**: Included — the source milestone spec explicitly names the three M2-owned unit files (`test_routing.py`, `test_similarity.py`, `test_chunker.py`; Constitution: tests are NOT optional where a spec names them). No other test files may be created (node/graph/facade @unit scenarios are **authored in M6** with its conftest fakes — Ruling A; M2 proves them via the live demo).

**Organization**: grouped by user story. File paths relative to the deliverable repo root **`~/Desktop/epam/memory-first-agent/`**; `T-M2-XX` references map to the milestone file's §8.

> Ordering notes baked in from the start: (a) `analytics/classify.py` (schema-only) precedes
> `state.py` because `AgentState.analytics` must resolve at runtime (research D3); (b) the
> GitHub Models `.env` configuration (user-provided PAT) precedes the live demo checkpoint;
> (c) `memory/store.py` is split knn-first so US2's similarity test can run before the
> write path lands; (d) analysis remediation 2026-07-05: T020 also authors the
> `docs/seed.md` demo fixture (I1), and `test_chunker.py` hosts the FR-M2-15 URL
> pure-helper scenarios (C1 — no fourth test file; Ruling A file list intact).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1 (seeded hit demo, P1) · US2 (threshold contract, P2) · US3 (memory foundations proof, P3) · US4 (spine + verification + disclosure, P4)

## Phase 1: Setup

- [X] T001 In `~/Desktop/epam/memory-first-agent/`, create and switch to feature branch `m2-memory-path` (`git checkout -b m2-memory-path`) — M2's DoD requires committing on a feature branch
- [X] T002 Baseline check: `make test && uv run ruff check .` green and `make redis-up` healthy before any M2 change (M1 regression guard)

## Phase 2: Foundational (blocking prerequisites for ALL user stories)

- [X] T003 Write `src/memagent/analytics/classify.py` — schema ONLY (research D3): `QuestionType` (factual, how_to, comparison, opinion, troubleshooting, other) and `Category` (technology, science, health, finance_business, travel_geography, entertainment_sports, history_politics, lifestyle, other) str-Enums **without** `_missing_` hooks, plus pydantic `QueryClassification` (topic, category, question_type, language, confidence) — M4 hardens this file in place (T-M2-01 part; FR-M2-01)
- [X] T004 Write `src/memagent/state.py` — verbatim `AgentState` per data-model.md Entity 1 (incl. reducers: `guardrail_events`/`errors` via `operator.add`, `latency_ms`/`tokens` via dict-merge; the two M2-added channels `turn_started_at`/`search_provider`), `MemoryHit`/`SearchResult`/`FetchedDoc`/`Chunk`/`SourceRef` TypedDicts, `StepError{node,error_type,detail}`, `Route` Literal (closed 5-set); imports `QueryClassification` from analytics.classify; `typing.get_type_hints(AgentState)` must resolve (T-M2-01; FR-M2-01/02) — depends on T003
- [X] T005 [P] Write `src/memagent/interfaces.py` — verbatim Protocols per contracts/state-and-routing.md: `Embedder` (dim + embed), `CompletionResult` NamedTuple, `ChatLLM` (complete + parse), `WebSearcher`, `MemoryStore` (`knn` raw top-k, NO threshold param; `store(page, chunks, vectors, source_query, flags)`), plus minimal placeholder `PageFetcher`/`TurnLogger` Protocols (T-M2-02; FR-M2-03)
- [X] T006 [P] Write `src/memagent/resources.py` — `from __future__ import annotations`; `@dataclass(frozen=True) AgentResources(settings, memory, embedder, chat_llm, analytics_llm, searcher, fetcher, turn_logger)`; never call `get_type_hints` on it (T-M2-03; FR-M2-04)
- [X] T007 [P] Write `src/memagent/routers.py` — all five pure functions verbatim from contracts/state-and-routing.md (`route_after_guard/embed/memory/search/fetch`); `route_after_memory` uses `sim is not None and sim >= s["threshold"]` — comparison stays `>=` (epsilon only on proven flake, research D8) (T-M2-04; FR-M2-05/06)
- [X] T008 [P] Write `src/memagent/memory/urls.py` — `canonicalize` (lowercase scheme+host, drop fragment, drop `utm_*` params, keep others, preserve path/query case) and `url_hash = sha256(canonical)[:16]` (T-M2-05; FR-M2-15)
- [X] T009 [P] Write `src/memagent/memory/chunking.py` — `chunk_markdown(text)` via `RecursiveCharacterTextSplitter` (markdown separators, `chunk_size=1600`, `chunk_overlap=200`), post-filter: drop <100 chars + empty/whitespace, cap 25 (T-M2-06; FR-M2-14)
- [X] T010 [P] Write `src/memagent/llm/prompts.py` — `build_system_prompt() -> str` (no args; untrusted_context-is-data + mandatory "Sources:" ending) and `wrap_context(sources, origin) -> str` (single `<untrusted_context>` block, per-source `source_url` header, origin recorded) — **both signatures FINAL** (Ruling E; T-M2-07; FR-M2-20)

**Checkpoint**: `uv run python -c "import memagent.state, memagent.interfaces, memagent.resources, memagent.routers"` exits 0 (get_type_hints resolves).

## Phase 3: User Story 1 — Seeded question answered from memory with visible proof (P1) 🎯 MVP

**Goal**: wipe → seed → `memagent ask` prints `[MEMORY HIT sim=0.XX]` + answer + "Sources:" + seeded URL/title; unseeded ask prints `[MEMORY MISS]` + deterministic response.

**Independent Test**: quickstart.md §2 (live, GitHub Models free tier).

- [X] T011 [US1] Write `src/memagent/llm/clients.py` — `OpenAIEmbedder(settings)` (own `AsyncOpenAI(api_key, base_url=settings.openai_base_url or None, max_retries=0, timeout=45.0)`; `dim=settings.embedding_dim`; ordered vectors) and `OpenAIChatLLM(settings, model)` (`complete()` → `CompletionResult(text, usage{model,input_tokens,output_tokens})`, `max_tokens=2048`, `temperature=0`; basic `parse()`) — thin constructors per research D7, ONE call-site per client (T-M2-08; FR-M2-08/09) — depends on T004, T005
- [X] T012 [US1] Write `src/memagent/memory/store.py` part 1 — `distance_to_similarity(d) = 1.0 - d` (module-level, THE one conversion site) + `RedisMemoryStore.knn(vector, k)` via redisvl `VectorQuery` (raw unfiltered top-k, descending similarity, epoch→ISO `stored_at`, csv→list flags, empty index → `[]`) against M1's schema (T-M2-09a; FR-M2-07/10) — depends on T004, T008
- [X] T013 [US1] Extend `src/memagent/memory/store.py` part 2 — `store()` (upsert cleanup via old `doc:{hash}.num_chunks`, write `chunk:{hash}:{i}` with all 11 fields, `chunk:{hash}:summary` iff `page["summary"] is not None` with `vectors[0]` = summary embedding (research D6), `doc:{hash}` meta, per-key `EXPIRE settings.memory_ttl_seconds` when >0) and `is_fresh(url_hash)` (T-M2-09b; FR-M2-11/12/13) — depends on T012
- [X] T014 [US1] Write `src/memagent/nodes/embed.py` (`embed_query`: embeds `sanitized_query` → `query_vector`; on error → `query_vector=None` + StepError) and the `answer_failure` half of `src/memagent/nodes/answer.py` (fixed apology, `route="failed"`, NO LLM call, never raises) — no [P]: T015 writes the same `nodes/answer.py` (analysis A1) (T-M2-10; FR-M2-16/19) — depends on T011
- [X] T015 [US1] Write `src/memagent/nodes/memory.py` (`memory_search`: `memory.knn(query_vector, settings.memory_top_k)` → `memory_hits` + `top_similarity` max-or-None, NO threshold logic) and the `answer_from_memory` half of `nodes/answer.py` (`chat_llm.complete` over `wrap_context(memory_hits, "memory")` → `route="memory_hit"`, answer ends "Sources:", `sources` deduped by URL with `origin="memory"`) (T-M2-11; FR-M2-17/18) — depends on T010, T011, T012 (same file as T014's answer_failure — sequential with T014)
- [X] T016 [P] [US1] Write `src/memagent/nodes/log.py` — `log_turn` no-op stub returning `{}`, comment-marked "replaced by M4" (T-M2-12; FR-M2-21)
- [X] T017 [US1] Write `src/memagent/graph.py` — `build_graph(resources)`: `StateGraph(AgentState)`, entry `embed_query` (Ruling F), conditional edges via `route_after_embed` and `route_after_memory` with the TEMPORARY path-map `{"web_search": "answer_failure"}` comment-marked "M3 remaps", `answer_from_memory`/`answer_failure` → `log_turn` → END, compiled once (T-M2-13; FR-M2-21) — depends on T007, T014, T015, T016
- [X] T018 [US1] Write `src/memagent/app.py` — `build_resources(settings=None)` (Settings() fallback; real embedder/chat_llm/analytics_llm/RedisMemoryStore + no-op searcher/fetcher/turn_logger stubs marked with replacing milestones; calls M1's `assert_index_dims(embedder.dim, settings)`) and `Agent.answer(q)` → initial state per contracts/graph-and-facade.md (uuid4, history=[], threshold, guard_verdict="allow", sanitized_query=q, skip_store=False, turn_started_at=perf_counter(), search_provider=None) → `TurnResult(route, answer, sources, similarity)` (T-M2-14; FR-M2-22) — depends on T011, T013, T017
- [X] T019 [US1] Edit `src/memagent/cli.py` — replace `ask`'s M1 echo body: run `Agent.answer(query)`; hit → `[MEMORY HIT sim={similarity:.2f}]` + answer + `(memory) {title} <{url}>` lines; miss → `[MEMORY MISS]` + deterministic response (M3 owns the banner upgrade); exit 0 (T-M2-15; FR-M2-24) — depends on T018
- [X] T020 [US1] Write `scripts/seed_memory.py` — `--url` + text/`--file`: canonicalize → `chunk_markdown` → wrap into `Chunk` records → embed chunk texts → `store(page(summary=None), chunks, vectors, "seed", [])` (vectors 1:1 per research D6) — AND author the demo fixture `docs/seed.md` (a short factual text about Redis vector search, ≥2 chunks worth, committed to the repo) so T022's seed command has its input (analysis I1) (T-M2-16; FR-M2-23) — depends on T009, T013
- [X] T021 [US1] ⚠ NEEDS USER: configure GitHub Models free-dev credentials in `.env` (never committed): `OPENAI_API_KEY=<fine-grained PAT with models:read>`, `OPENAI_BASE_URL=<GitHub Models endpoint>`, session-level dev model ids (e.g. `CONVERSATION_MODEL=openai/gpt-5.4-mini`, matching embedding id); verify endpoint + record actual id strings (research D1; Clarifications 2026-07-05) — production `Settings` defaults untouched
- [X] T022 [US1] Checkpoint run (quickstart §2): `uv run memagent wipe-memory` → `seed_memory.py --url https://redis.io/docs/vectors --file docs/seed.md` → `memagent ask "How does Redis vector search work?"` prints `[MEMORY HIT sim=0.XX]` (≥0.70, two decimals) + "Sources:" + seeded URL/title; `memagent ask "What is the capital of Mongolia?"` prints `[MEMORY MISS]` + deterministic response; TTL spot-check on `chunk:{hash}:0` is >0 and ≤604800 — depends on T013–T021

**Checkpoint**: the PLAN §13 M2 demoable outcome works live. 🎯

## Phase 4: User Story 2 — The 0.70 threshold contract is provable (P2)

**Goal**: boundary + conversion proven by M2-owned automated tests, keyless.

**Independent Test**: quickstart.md §1 (routing + similarity files).

- [X] T023 [P] [US2] Write `tests/unit/test_routing.py` — parametrized boundary table (0.70@0.70 → answer_from_memory INCLUSIVE, 0.6999 → web_search, None → web_search, 1.0 → hit, 0.0 → miss); all five routers' return values per contracts; purity (same input twice → same output, no I/O) (T-M2-17; FR-M2-05/06) — depends on T007
- [X] T024 [P] [US2] Write `tests/unit/test_similarity.py` — `distance_to_similarity(0.30) == 0.70` (exact or documented epsilon) and routes as hit via `route_after_memory`; float32-noise comment recording the D8 decision (comparison stays `>=`; 0.699999988 < 0.70 → miss under the default); assert the 1−d/2 formula is NOT used (no `/ 2` in the conversion path) (T-M2-18; FR-M2-06/07) — depends on T012
- [X] T025 [US2] Checkpoint: `uv run pytest tests/unit/test_routing.py tests/unit/test_similarity.py -q` green + single-conversion-site grep: `grep -rn "1\.0 - distance" src/ --include=*.py | grep -v '#'` → exactly one match in `memory/store.py` — depends on T023, T024

## Phase 5: User Story 3 — Memory foundations behave correctly (P3)

**Goal**: chunker + URL pure-helper invariants automated; store TTL/upsert/freshness proven against live Redis.

**Independent Test**: quickstart.md §1 (chunker file) + §2 deeper checks.

- [X] T026 [P] [US3] Write `tests/unit/test_chunker.py` — header comment: "memory-layer pure-helper tests (chunking + urls)". Chunker: size ≤1600/overlap 200 bounds, <100-char floor dropped, 25-chunk cap, never-empty, unicode preservation, short-doc → ≤1 chunk. URLs (analysis C1, FR-M2-15 scenarios): canonicalize table (`HTTP://Example.com/a?utm_source=x#frag` → `http://example.com/a`; `https://Foo.COM/p?utm_medium=e&id=7` → `https://foo.com/p?id=7`) and both variant spellings hash to the same 16-char hex key (T-M2-19; FR-M2-14/15) — depends on T008, T009
- [X] T027 [US3] Live store validation against redis:8.2 (source §7 store scenarios): re-seed same URL with fewer chunks → no stale `chunk:{hash}:{i}` keys beyond new `num_chunks` (`redis-cli KEYS "chunk:{hash}:*"`); `MEMORY_TTL_SECONDS=0` run → `TTL` returns -1 (no expiry); `is_fresh`: just-seeded hash → True, absent hash → False; `knn` on wiped index → `[]` (script or REPL snippet; record outputs) — depends on T013, T022

## Phase 6: User Story 4 — Structural spine + verification + disclosure (P4)

**Goal**: spine contracts machine-checked; FR-025 recorded; disclosure appended.

**Independent Test**: quickstart.md §3–§4.

- [X] T028 [P] [US4] Spine checks (quickstart §3): Route closed-set assertion via `get_args`; `AgentResources.__dataclass_params__.frozen` True; `OPENAI_API_KEY=dummy` graph build + `draw_mermaid()` non-empty naming all five nodes (FR-M2-01/02/04/21 acceptance) — depends on T017, T018
- [X] T029 [US4] FR-025 live verification (T-M2-20): one GitHub Models call confirming the three catalogue ids resolve + one `temperature=0` call on the dev conversation model; record id strings + pass/fail in `docs/ai_prompts/milestone-2.md`; correct `.env.example`/`Settings` defaults ONLY if a production id (not a dev-mode alias) proves wrong (FR-M2-25) — depends on T011, T021
- [X] T030 [US4] Create `docs/ai_prompts/milestone-2.md` (dated M2 prompt log: speckit flow, clarify answer, corrections, verification records) and reference it from `AI_USAGE.md` §5; update the §3 provenance table with M2 components (T-M2-21 part; FR-M2-26)

## Phase 7: Polish & Definition of Done sweep

- [X] T031 Run the full milestone §9 DoD list: module-import one-liner, three unit files green, `uv run ruff check src tests` clean, conversion-site grep, dummy-key mermaid check, demoable outcome re-run, frozen-resources check, verification recorded, disclosure greps (`ls docs/ai_prompts/` + `grep -q ai_prompts AI_USAGE.md`); fix anything red — depends on T001–T030
- [X] T032 Commit on `m2-memory-path` (seam stubs comment-marked with replacing milestones), push, verify CI green on the branch, merge to `main`, push, verify CI green again — depends on T031

## Dependencies

```
Phase 1 (T001 → T002)
  → Phase 2: T003 → T004; then T005[P] T006[P] T007[P] T008[P] T009[P] T010[P]
    → US1: T011 (T004,T005) → T012 (T004,T008) → T013
           T014[P] (T011) → T015 (T010,T011,T012; same file as T014)
           T016[P] → T017 (T007,T014,T015,T016) → T018 (T011,T013,T017)
           → T019 → T020 (T009,T013) → T021 (user) → T022 (all US1)
    → US2: T023[P] (T007), T024[P] (T012) → T025
    → US3: T026[P] (T009), T027 (T013, T022)
    → US4: T028[P] (T017,T018), T029 (T011,T021), T030
      → Polish: T031 → T032
```

Story order: US1 → US2 → US3 → US4, but US2's T023 and US3's T026 can start as soon as
their Phase-2 dependency lands (they don't wait for US1).

## Parallel Execution Examples

- **After T004**: T005 ∥ T006 ∥ T007 ∥ T008 ∥ T009 ∥ T010 — six files, no shared state.
- **After T007/T009/T012**: T023 (test_routing) ∥ T026 (test_chunker) ∥ T024 (test_similarity) alongside US1 node work.
- **Not parallel**: T014 → T015 share `nodes/answer.py`; T012 → T013 share `memory/store.py`; T022 gates on the user-provided PAT (T021).

## Implementation Strategy

**MVP first**: Phases 1–3 (T001–T022) deliver the PLAN §13 M2 demoable outcome. US2/US3
tests can interleave earlier where dependencies allow — recommended, since T023/T024/T026
catch boundary/chunker defects before the live demo debugging starts.

**User-gated step**: T021 needs your fine-grained GitHub PAT (`models: read`). Everything
before it is keyless; T022/T027/T029 are the only tasks that touch the network.

**Scope guard**: no retry loops (`max_retries=0` only — tenacity is M5), no Redis-down
degradation matrix, no store-side filtering, no session memory, no salvage route, no
test files beyond the three M2-owned ones, routers verbatim forever.
