# Tasks: Milestone 6 — Integration/E2E Tests, Eval Harnesses, CI Green, Docs, v1.0

**Input**: Design documents from `specs/006-m6-e2e-evals-delivery/`
**Prerequisites**: plan.md, spec.md, research.md (R0 + D1–D15 + **R1 recheck**), data-model.md,
contracts/{test-fixtures,integration-e2e,eval-harnesses,ci-docs-release}.md, quickstart.md.
**Repo root for all paths**: `memory-first-agent/` (branch off green `main` `6a582e4`).

**Tests**: M6's fixtures, integration test, e2e test, and eval harnesses ARE the deliverables
(the milestone *proves* M1–M5) — so these are implementation tasks, not optional TDD scaffolding.

**Recheck (R1) fixes baked into the tasks below** — do NOT reintroduce the originals:
- **A** `Agent(resources)` (NOT `Agent(build_graph(...))`) — the shipped Agent builds the graph itself (app.py:99-101). [T004, T006, T007]
- **B** e2e/eval fetch fixture is a **full HTML doc** `<html><body><article><p>…</p></article></body></html>` — a bare `<article>` is dropped by trafilatura. [T006, T007]
- **E** the D11 `ruff format .` pass is a **separate cosmetic commit** (16 src + 7 unit files, whitespace only) — run it before the CI format-check gate. [T009]
- **F** `FakeLLM.parse` needs a **schema_factory** for `QueryClassification`/`GroundingVerdict` (all-required fields; bare `schema()` raises `ValidationError`). [T002, T004, T008]
- **H** standalone scripts prepend the repo root to `sys.path` before `from tests.conftest import …` (tests/ is not installed). [T007, T008, T012]

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[US#]**: user-story tasks only (Setup/Foundational/Polish carry no story label)

---

## Phase 1: Setup

**Purpose**: prepare the M6 workspace; add no product code.

- [X] T001 Create feature branch `m6-e2e-evals-delivery` from green `main`; create empty dirs `tests/integration/` and `tests/e2e/`; confirm `[tool.pytest.ini_options]` in `pyproject.toml` already declares the `integration` and `e2e` markers (R0 #11 — no change needed) and `asyncio_mode = "auto"`; confirm no new dependencies are required (pytest/pytest-asyncio/respx/pytest-cov/ruff already pinned).

**Checkpoint**: branch + empty test dirs ready.

---

## Phase 2: Foundational (Blocking Prerequisites) — `tests/conftest.py`

**Purpose**: the canonical fixtures + fakes + shared resource helper that BOTH US1 (integration/e2e) and US2 (evals) build on. `conftest.py` does not exist yet (R0 #1, D1) — create it; do NOT rewrite the 12 existing unit files.

**⚠️ CRITICAL**: no user story can begin until Phase 2 is complete. T002→T003→T004 are sequential (same file).

- [X] T002 Create `tests/conftest.py` with the fakes/fixtures per `contracts/test-fixtures.md`: `settings` fixture (env `WAIT_CAP_SCALE=0`, `TURN_LOG_PATH=<tmp>/turns.jsonl`, dummy `OPENAI_API_KEY`), `FakeEmbedder` (dim 1536, sha256 bag-of-words → L2-unit vector, bit-stable, token-overlap→high cosine) + `fake_embedder` fixture, `FakeLLM` (`complete()`→canned text + `{input_tokens,output_tokens,model}` usage; `parse()`→`schema_factory(schema) or schema()` + usage; **recheck F**: bare `schema()` cannot build `QueryClassification`) + `fake_llm` fixture. Then run `uv run pytest -m "not integration and not e2e" -q` and confirm all 103 existing unit tests still pass (they use local fakes, don't import conftest — no collision). Then author `tests/unit/test_m6_fixtures.py` (NEW keyless M6-owned unit file — distinct from the 12 frozen upstream files, preserving Ruling A) with the `contracts/test-fixtures.md` "Contract tests" assertions for FR-001/002/003 (audit fix — the happy-path e2e never fires the retry or the disjoint-cosine case): (1) a 4-attempt `llm_retry(settings)`-wrapped coro that always raises `RateLimitError` completes all 4 attempts with total sleep < 0.05 s under `WAIT_CAP_SCALE=0` (production path, no monkeypatch); (2) `fake_llm.complete()` twice → identical `.text` + int token usage, and `parse()` with a `schema_factory` → a valid `QueryClassification` + usage; (3) `fake_embedder` embeds bit-identically, len 1536, unit-norm, query-dominated cosine ≥ 0.70, disjoint text < 0.70. *(FR-001, FR-002, FR-003)*
- [X] T003 Add to `tests/conftest.py`: `redis_url` fixture (`socket.create_connection` ping → `pytest.skip` on `OSError`) and `clean_index` fixture (deps `redis_url`; `get_index(settings, aioredis.from_url(url))` → `await wipe_index(index)` → `yield index` → `await client.aclose()` — M1 helpers, **not** `build_index`). With Docker stopped, confirm `uv run pytest -m "not integration and not e2e"` passes and integration/e2e collect as `skipped` (never `error`); add a keyless FR-004 assertion to `tests/unit/test_m6_fixtures.py` that a test requesting `redis_url` against an unreachable host/port reports `skipped`, not `error`. FR-005 (empty index → `knn` returns `[]`) is exercised by the integration test (T005) + the e2e turn-1 miss (T006). *(FR-004, FR-005)* (depends T002)
- [X] T004 Add to `tests/conftest.py`: `build_test_resources(settings, redis_client)` (plain importable fn per `contracts/test-fixtures.md`) assembling `AgentResources` — `memory=RedisMemoryStore(settings, redis_client)`, `embedder=FakeEmbedder`, `chat_llm=FakeLLM()`, **`analytics_llm=FakeLLM(schema_factory=lambda s: QueryClassification(topic="redis", category="technology", question_type="factual", language="en", confidence=0.9))`** (**recheck F** — so summary via `complete()` and classify via `parse()` both work), real `searcher`/`fetcher`, real `TurnLogger(settings.turn_log_path)` — plus the `resources` and `agent` pytest fixtures where **`agent` = `Agent(resources)`** (**recheck A** — Agent builds the graph itself; do NOT pass `build_graph(...)`). *(supports US1 + US2)* (depends T003)

**Checkpoint**: conftest complete; fixtures importable; existing suite green.

---

## Phase 3: User Story 1 — The memory-first lifecycle is proven end-to-end (Priority: P1) 🎯 MVP

**Goal**: prove the assignment's core contract — real-Redis round-trip + turn-1 miss → identical turn-2 hit (search `call_count` unchanged) + one turn record per turn.

**Independent Test**: with live `redis:8.2`, `uv run pytest -m "integration or e2e" -v` passes; the e2e shows `memory_miss_web_search` (call_count 1) then `memory_hit` (sim≥0.70, call_count still 1) with exactly two turn records.

- [X] T005 [P] [US1] Write `tests/integration/test_redis_store.py` (`@pytest.mark.integration`, uses `clean_index` + `fake_embedder`) with the four checks in `contracts/integration-e2e.md`: (1) idempotent create — `await ensure_index(index)` **twice** → True then False, one index (**recheck D4** — not raw `create(overwrite=False)` twice); (2) `store()`→`knn()` round-trip (text/url/title intact); (3) metadata — **monkeypatch the store clock** (`monkeypatch.setattr` on `store`'s `time.time` → fixed epoch 1751625600), assert `hit["stored_at"] == _epoch_to_iso(1751625600)` and parses as ISO-8601 (**recheck D5**); (4) known-vector similarity — identical→1.0, orthogonal→0.0, cosine-0.70 pair `w=[0.7,sqrt(0.51),0…]`→within 1e-6 of 0.70 (**D6**). *(FR-006, FR-007, FR-008, FR-009)* (depends T004)
- [X] T006 [P] [US1] Write `tests/e2e/test_lifecycle.py` (`@pytest.mark.e2e`) per `contracts/integration-e2e.md`: set `TAVILY_API_KEY="test-key"` (forces httpx path — D3); `agent = Agent(resources)` (**recheck A**); respx routes — `POST https://api.tavily.com/search`→`200 {"results":[{url,title,content}]}` and `GET <url>`→`200 text/html` with a **full-HTML query-dominated page** `"<html><body><article><p>"+(QUESTION+" ")*40+"</p></article></body></html>"` (**recheck B** — bare `<article>` is dropped; no redirect — D3/D9). Assert **turn 1**: `route=="memory_miss_web_search"`, a `origin=="web"` source, tavily `route.call_count==1` (FR-010); **turn 2** (identical): `route=="memory_hit"`, `similarity>=0.70`, a `origin=="memory"` source whose URL == turn-1 URL, tavily `call_count` **still 1** (FR-011); read `settings.turn_log_path` → exactly 2 objects, routes `["memory_miss_web_search","memory_hit"]`, 2nd `similarity_top>=0.70`, each `tokens` non-empty (**D7**) (FR-012). *(FR-010, FR-011, FR-012)* (depends T004)

**Checkpoint**: 🎯 MVP — the core proof passes; `make test-integration` green.

---

## Phase 4: User Story 2 — The build verifies itself with zero keys (Priority: P2)

**Goal**: the lifecycle hard gate + grounding demonstration + a single green keyless CI job.

**Independent Test**: `python scripts/eval_lifecycle.py --mock` exits 0 (needs redis); `python scripts/eval_grounding.py --mock` exits 0 keyless; `ci.yml` inspection passes FR-017/018 checks.

- [X] T007 [P] [US2] Write `scripts/eval_lifecycle.py` per `contracts/eval-harnesses.md`: prepend repo root to `sys.path` then `from tests.conftest import build_test_resources` (**recheck H**); `--mock` = real store + respx + fakes over 3 query-dominated questions asked twice each (each a **full-HTML** page — **recheck B**), `agent = Agent(build_test_resources(settings, client))` (**recheck A**), reset/wipe the index between questions so each turn-1 is a real miss; PASS iff every question is `memory_miss_web_search` then `memory_hit`(sim≥0.70) → exit 0, else name the failing question → exit 1 (hard gate); no `--mock` + no `OPENAI_API_KEY` → readable "OPENAI_API_KEY required" to stderr, non-zero, no traceback. *(FR-013, FR-014)* (depends T004)
- [X] T008 [P] [US2] Write `scripts/eval_grounding.py` (~120 lines; the "~40–60" estimate was optimistic) per `contracts/eval-harnesses.md`: repo-root `sys.path` shim then import `FakeLLM` (**recheck H**); define `GroundingVerdict(grounded, citations_valid, abstained_correctly)`; 5–8 fixed `(question, context, expect∈{grounded,abstain})` cases; nano judge via `analytics_llm.parse(..., GroundingVerdict)`; `--mock` = `FakeLLM` as answerer + judge with a `schema_factory` returning a **passing** `GroundingVerdict` (**recheck F**), keyless AND redis-less (no store/index — **recheck I**), print a per-case row + 3-dimension aggregate + "demonstration, not a benchmark", exit 0 (non-gating). *(FR-015, FR-016)* (depends T004 for `FakeLLM`; independent of T007)
- [X] T009 [US2] Run `uv run ruff format .` once and commit as a **dedicated** "M6: repo-wide ruff format" commit (**recheck E / D11** — cosmetic, whitespace only; expected to touch 16 `src/memagent/` files + 7 `tests/unit/` files; logic unchanged, all tests stay green). Confirm `uv run ruff format --check .` is then clean. *(prerequisite for T010's format gate)* (fallback: if the diff is unacceptable, keep `ruff check .` only and record FR-017 "format check" as satisfied by `ruff check` — decide on the actual diff)
- [X] T010 [US2] Finalize `.github/workflows/ci.yml` per `contracts/ci-docs-release.md`: single `build` job; `redis:8.2` service (matching docker-compose) + healthcheck + `REDIS_URL`; steps in order `ruff check . && ruff format --check .` → `pytest -m "not integration and not e2e" --cov=memagent --cov-report=term` → `pytest -m "integration or e2e" --cov=memagent --cov-append` → `python scripts/eval_lifecycle.py --mock` → `python scripts/eval_grounding.py --mock` → `coverage report`; `uv sync --frozen`; pinned `actions/*@v4/@v5/@v6`; `python-version-file: .python-version`; **no `secrets.*`, no `--cov-fail-under`**. Push and confirm the job is green. *(FR-017, FR-018)* (depends T005, T006, T007, T008, T009)

**Checkpoint**: CI is one green keyless job; both evals behave per contract.

---

## Phase 5: User Story 3 — Documentation is auto-generated and verifiable (Priority: P3)

**Goal**: a provably-generated 10-node mermaid diagram + a captured miss→hit transcript.

**Independent Test**: run `render_graph.py` twice → between-marker mermaid byte-identical, all 10 nodes; `capture_demo.py` (real key) → transcript shows MISS(web)→HIT(sim≥0.70).

- [X] T011 [P] [US3] Extend `scripts/render_graph.py` per `contracts/ci-docs-release.md`: keep its existing **keyless** all-`None` `AgentResources` build (do NOT route through `build_test_resources` — D2); add `replace_between(path, "<!-- BEGIN graph -->", "<!-- END graph -->", "```mermaid\n{mermaid}```")` splicing into `README.md` and `docs/architecture.md` (creating markers if absent); keep printing to stdout. Run twice; confirm the between-marker content is byte-identical and names all 10 nodes (`guard_input … log_turn`) + `__start__ --> guard_input`. *(FR-019)* (depends T001)
- [X] T012 [P] [US3] Write `scripts/capture_demo.py` per `contracts/ci-docs-release.md`: repo-root `sys.path` shim (**recheck H**); real-key live miss→hit over the same question twice via the real wiring (mini `temperature=0`), writing `docs/demo_transcript.md` (MISS with web sources → HIT sim≥0.70). Absent a real key, commit a `docs/demo_transcript.md` **"pending real-key capture"** placeholder (Clarification Q1 — does not block the tag). *(FR-020)* (depends T004)

**Checkpoint**: README + architecture diagram auto-generated; demo transcript captured or placeholdered.

---

## Phase 6: User Story 4 — The repo is delivered: complete docs, re-verified facts, v1.0 (Priority: P4)

**Goal**: complete README + AI_USAGE + DECISIONS, a dated re-verification note, and the `v1.0` tag on the keyless-green commit.

**Independent Test**: grep README for the ten phrases; `AI_USAGE.md` contains "the complete instruction record"; `docs/verification-2026-07-06.md` lists each §14 fact; `git tag` lists `v1.0`.

- [X] T013 [P] [US4] Finalize `README.md` with all ten verbatim sections per `contracts/ci-docs-release.md` (§10.4 quickstart incl. "Zero keys needed"; T1–T4 threat-model table; 0.70 calibration; coarse-TTL + ETag; robots.txt limitation; why fetch+markdown in-house; DuckDB `read_json_auto`; pip fallback; worked paraphrase; "not a ReAct/tool-calling agent") + the `<!-- BEGIN/END graph -->` mermaid markers (populated by T011). Note the `make wipe` → `wipe-memory` CLI name split (R0 #15). *(FR-021)* (depends T011 for the mermaid block)
- [X] T014 [P] [US4] Finalize `AI_USAGE.md` (all 8 sections; contains the literal "the complete instruction record"; points to `docs/ai_prompts/`) and append `docs/ai_prompts/milestone-6.md` — the full M6 instruction record **as the milestone lands** (Constitution VII, never retroactively); finalize repo-root `DECISIONS.md` (verify it exists — scaffolded M1) with the complete anti-churn record. *(FR-022)*
- [X] T015 [P] [US4] Re-verify the runtime/service §14 facts → `docs/verification-2026-07-06.md`: OpenAI model ids + prices (public pricing), Tavily request shape, ddgs API, `redis:8.2` module availability, the `chat.completions.parse` method; correct any drift in `config.py`/`.env.example`/`MODEL_CHOICES.md`. Record **`temperature=0` on `gpt-5.4-mini` as "pending real-key capture"** (GitHub Models serves no gpt-5.4* ids — R0 #13, Clarification Q1). *(FR-023)*
- [X] T016 [US4] Re-verify the library-pin §14 facts into the same note (**depends T015** — both write `docs/verification-2026-07-06.md`, so NOT parallel — audit fix): dependency pins from `uv.lock` (langgraph 1.2.7, redisvl 0.23.0, httpx 0.28.1, respx 0.23.1, openai 2.44.0, tenacity ~9.1, trafilatura, ddgs, redis client), redisvl `create`/`VectorQuery`/`array_to_buffer` signatures, and `draw_mermaid()`; correct any drift in `pyproject.toml`. *(FR-023)*
- [X] T017 [US4] Confirm CI green on HEAD + run the 5-command live path (clone → install uv → `make setup` → `make redis-up` → `make run` → MISS then HIT) and the zero-key path (`make test` dockerless + `python scripts/eval_lifecycle.py --mock` against the CI redis); then `git tag v1.0` on that green, keyless-verified commit (real-key artifacts — demo transcript, real-key lifecycle, temperature probe — remain "pending real-key capture" and do NOT block the tag — Clarification Q1). *(FR-024, FR-025)* (depends T010, T011, T012, T013, T014, T015, T016)

**Checkpoint**: repo is submittable; `v1.0` tagged.

---

## Phase 7: Polish & Cross-Cutting

- [X] T018 Run the full `quickstart.md` DoD sweep (all 8 gates): unit keyless/dockerless + integration/e2e on redis:8.2 green; both eval mocks; CI single green job; render idempotent (10 nodes); README ten-phrase grep; AI_USAGE + `docs/ai_prompts/milestone-6.md`; dated verification note; `v1.0` present. Confirm the full suite (103 prior + new integration/e2e) is green and `ruff check`/`ruff format --check` clean.

---

## Dependencies & Execution Order

### Phase order
- **Setup (T001)** → **Foundational (T002→T003→T004, sequential same-file)** → **US1/US2/US3 (parallelizable after T004)** → **US4 (T017 depends on all)** → **Polish (T018)**.

### Cross-story notes
- **US1 (T005, T006)**: depend only on T004; independently testable (`pytest -m "integration or e2e"`). **MVP.**
- **US2**: T007/T008 depend on T004 (independent of US1). T010 (CI) runs the whole suite, so it depends on US1's tests (T005/T006) + the eval scripts (T007/T008) + the format pass (T009). The eval *scripts themselves* are independently testable without US1.
- **US3 (T011)** depends only on T001 (render is keyless); **T012** depends on T004.
- **US4**: T013 depends on T011 (mermaid block); T017 (tag) depends on everything.

### Parallel opportunities
- After T004: **T005, T006, T007, T008, T011, T012** touch different files → parallelizable.
- After the above: **T013, T014** are parallelizable docs tasks; **T015 → T016** are sequential (both write `docs/verification-2026-07-06.md`).
- Sequential barriers: T002→T003→T004 (same file); T009 before T010 (format gate); T010 after all suite+scripts; T017 after everything.

### Parallel example (post-Foundational)
```
Task: "T005 integration test_redis_store.py"
Task: "T006 e2e test_lifecycle.py"
Task: "T007 scripts/eval_lifecycle.py"
Task: "T008 scripts/eval_grounding.py"
Task: "T011 extend scripts/render_graph.py"
Task: "T012 scripts/capture_demo.py"
```

## Implementation Strategy

- **MVP = US1** (T001→T004→T005→T006): the core memory-first proof. STOP and validate `make test-integration` before proceeding.
- **Incremental**: add US2 (CI gate) → US3 (auto-docs) → US4 (delivery + `v1.0`), each independently testable.
- **AI_USAGE (T014) is appended AS M6 lands**, not at the end (Constitution VII; the biggest scoring risk per source §10.6).
- **Anti-churn** (Constitution VI): do NOT add a coverage gate, redis turn-log mirror, canary/defang, gray-zone guard, or the 0.50 salvage route.

## Notes
- `[P]` = different files, no incomplete-task dependency. `[US#]` maps to spec.md user stories.
- Every FR-001…025 is covered (FR-001/002/003(+004) acceptance assertions authored in `tests/unit/test_m6_fixtures.py` by T002/T003): FR-001/002/003→T002, FR-004→T003, FR-005→T003 (fixture)+T005/T006 (empty-index assertion), FR-006/007/008/009→T005, FR-010/011/012→T006, FR-013/014→T007, FR-015/016→T008, FR-017/018→T010, FR-019→T011, FR-020→T012, FR-021→T013, FR-022→T014, FR-023→T015+T016, FR-024/025→T017.
- Commit after each task (T009 is its own dedicated commit).
