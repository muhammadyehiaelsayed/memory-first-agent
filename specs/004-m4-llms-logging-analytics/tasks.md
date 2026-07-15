# Tasks: Milestone 4 — LLM Clients Finalized, Turn Log, Classifier, Analytics CLI, REPL

**Input**: Design documents from `/specs/004-m4-llms-logging-analytics/`

**Prerequisites**: plan.md, spec.md (4 user stories), research.md (D1–D11), data-model.md,
contracts/ (4 files), quickstart.md

**Tests**: REQUESTED by the source spec — M4 owns exactly two unit-test files
(`test_classifier_parsing.py`, `test_turnlog.py`; Constitution test-ownership map). Report/
client behaviors are verified by scripted checks + quickstart runs, not extra test files
(P-VI scope).

**Organization**: by user story; all code paths are in the deliverable repo
`~/Desktop/epam/memory-first-agent/` (this specs dir is the planning workspace).

**Source-task traceability**: T-M4-01→T017/T018; T-M4-02→T017; T-M4-03→T018/T019;
T-M4-04→T022; T-M4-05→T021; T-M4-06→T004; T-M4-07→T005; T-M4-08a→T024/T025;
T-M4-08b→T002 (already on main — verify only); T-M4-09→T007; T-M4-10→T026;
T-M4-11→T012/T013; T-M4-12→T014/T015; T-M4-13→T027; T-M4-14→T009; T-M4-15→T010;
T-M4-16→T030.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Create branch `m4-llms-logging-analytics` from green main (`20145bd`+) in `~/Desktop/epam/memory-first-agent/`; baseline gate: `uv run ruff check . && uv run ruff format --check . && make test` (36 tests green, zero keys)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: pin the research-D1 repo facts every story builds on, BEFORE writing code
against them (the M3 lesson: verify assumed seams first).

- [X] T002 Scripted verification (no code changes) recorded for `docs/ai_prompts/milestone-4.md`: (a) `src/memagent/llm/clients.py` `complete()` already returns `CompletionResult` with 3-key usage; (b) `src/memagent/nodes/answer.py` lines ~47/~116 already return `{"tokens": {"answer_llm": result.usage}}` (source T-M4-08b satisfied — no new code); (c) stub file is `src/memagent/nodes/log.py` and `graph.py:19` imports it; (d) `src/memagent/app.py` already stamps `turn_id`/`session_id`/`turn_started_at`/`search_provider`. Run: `python -c` asserts + grep, outputs captured

**Checkpoint**: repo facts confirmed — user stories can begin

---

## Phase 3: User Story 1 — Every turn leaves exactly one graded record (Priority: P1) 🎯 MVP

**Goal**: real classifier + `TurnLogger`/`build_turn_record` + real `log_turn` node; one
JSONL record per turn on every route; recording never breaks a turn (FR-009…015, FR-022
record side).

**Independent Test**: owned unit tests green with zero keys; then quickstart §2 — two live
`ask` turns append exactly 2 parseable full-schema lines to `logs/turns.jsonl`.

### Tests for User Story 1 (write FIRST, expect FAIL until T005–T008 land)

- [X] T003 [P] [US1] Author `tests/unit/test_classifier_parsing.py` (inline fake analytics_llm; NOT M6 conftest): valid parse → `Category.technology`/`QuestionType.how_to` + non-empty usage; captured user message has query only inside `<query>` tags; `category="wombat"` payload → `Category.other`; always-raising fake → `(None, {})` no propagation; fail-once fake → success with exactly 2 parse calls; sleeping fake + tiny `timeout_s` → `(None, {})` promptly (contracts/turn-log-and-classifier.md)
- [X] T004 [P] [US1] Author `tests/unit/test_turnlog.py` (tmp_path JSONL): 3 logs → exactly 3 parseable lines; `build_turn_record` shape for all 5 routes (constructed states; data-model §1 keys, uuid4 `turn_id`, 16-hex `query_sha256`); `memory_hit` → `web is None` + threshold 0.7; `route="blocked"` state → line written; raising `TurnLogger.log` → `log_turn` returns without raising; real `log_turn` + inline fake analytics_llm → record has int `latency_ms.total`, `latency_ms.classify`, remapped `tokens.answer_llm` (`{"model","input","output"}`), `tokens.analytics_llm` present

### Implementation for User Story 1

- [X] T005 [US1] Harden `src/memagent/analytics/classify.py` IN PLACE (M2 docstring pre-authorizes): add `_missing_ → other` classmethods to both enums; add `CLASSIFY_SYSTEM`, `_classify_user()` (`<query>`-tag framing), and `async classify(analytics_llm, query, timeout_s)` = tenacity `stop_after_attempt(2)` inner + `asyncio.wait_for` outer + `(None, {})` on ANY failure; update module docstring (remove "do not add them here")
- [X] T006 [P] [US1] Fill `src/memagent/analytics/turnlog.py`: `TurnLogger(path)` (mkdir parents, append `json.dumps(record, ensure_ascii=False)+"\n"`) + `build_turn_record(state, settings)` per data-model §1 (web block only on web routes; tokens remap only `answer_llm`/`analytics_llm`; `ts` UTC ISO ms; `query_sha256[:16]`; `errors` as dicts; `analytics.model_dump()` or None)
- [X] T007 [US1] Replace stub body IN `src/memagent/nodes/log.py` with real `make_log_turn(resources)` per contracts/turn-log-and-classifier.md: own classify timing, `latency={"classify":ms,("total" from turn_started_at)}`, merge REDUCED tokens/latency dicts (never shallow `{**state,**updates}`), `build_turn_record(merged,…)` → `resources.turn_logger.log(record)`, ALL inside one try/except → `log.error("log_turn_failed",…)`; graph import/node name unchanged (depends on T005, T006)
- [X] T008 [US1] `src/memagent/app.py`: replace `_NoopTurnLogger` with `TurnLogger(settings.turn_log_path)` in `build_resources()`; delete the `_NoopTurnLogger` class; update `src/memagent/interfaces.py` `TurnLogger` Protocol docstring (placeholder → real, signature unchanged) (depends on T006)
- [X] T009 [US1] CHECKPOINT: `uv run pytest tests/unit/test_classifier_parsing.py tests/unit/test_turnlog.py -q` green; full `make test` green; live quickstart §2 (two `ask` turns → 2 lines, miss then hit shape, `web.provider`, `latency_ms.classify`+`total`, both token roles); `.gitignore` keeps `logs/turns.jsonl` untracked

**Checkpoint**: the graded log is real — MVP demoable (`ask` + inspect JSONL)

---

## Phase 4: User Story 2 — Hit-rate and topic analytics over the log (Priority: P2)

**Goal**: `aggregate()`/`render_report()` + real `memagent analytics [--json]` + shipped
sample log + README DuckDB note (FR-016…019).

**Independent Test**: quickstart §3 — ten sections over `logs/turns.sample.jsonl`;
`--json` emits one valid JSON doc; missing file → friendly guidance exit 0.

### Implementation for User Story 2

- [X] T010 [P] [US2] Fill `src/memagent/analytics/report.py`: pure `aggregate(records)` per data-model §4 (hit-rate rule research D10 — denominator = hits+misses+snippets_only-degraded, 0.0 on empty; top-10 topics; per-route mean of `latency_ms.total`; errors/unclassified counts; last-10 recent) + `render_report(agg, console)` rich tables with `rich.markup.escape()` on EVERY user-derived cell (query, topic, title, url, language)
- [X] T011 [P] [US2] Author `logs/turns.sample.jsonl` (10 full data-model-§1 records): all 5 routes ≥1, ≥1 `"analytics": null`, ≥1 non-empty `errors`, ≥1 non-`en` language, ≥1 query containing `[red]…[/red]` markup, fixed fictional timestamps; AND change `.gitignore` line 19 from `logs/` to `logs/turns.jsonl` — git cannot re-include a file under an excluded DIRECTORY, so a `!` exception would silently fail (analyze I2; verified with `git check-ignore`); then confirm the sample is tracked and the live log stays ignored
- [X] T012 [US2] Replace the `analytics` stub in `src/memagent/cli.py` per contracts/analytics-report.md: read `Settings().turn_log_path`, stream+parse lines (skip blanks), missing file → friendly guidance naming `memagent ask` + the sample file, exit 0; `--json` flag prints `json.dumps(aggregate(records))` to stdout and returns BEFORE any rich output; default path renders via `render_report`; NO OPENAI_API_KEY/Redis guard on this command (depends on T010)
- [X] T013 [P] [US2] Add the verbatim DuckDB note to `README.md` (`read_json_auto('logs/turns.jsonl')` one-liner, contracts/analytics-report.md)
- [X] T014 [US2] CHECKPOINT: quickstart §3 in full — `uv run memagent analytics` over the sample renders all ten sections; `--json | python3 -c json.load` OK with `total_turns`/`hit_rate`; markup-bearing sample query renders literally (FR-018 eyeball); `TURN_LOG_PATH=logs/nope.jsonl` run → guidance, exit 0, no traceback; route-coverage grep loop passes

**Checkpoint**: US1+US2 = the milestone's demoable analytics over real + sample turns

---

## Phase 5: User Story 3 — Finalized clients with the documented cost story (Priority: P3)

**Goal**: shared-transport clients with seams + pinned params, `build_openai_clients()`,
`app.py` rewiring, `MODEL_CHOICES.md`, live FR-007 probe (FR-001…008).

**Independent Test**: scripted client assertions pass; `MODEL_CHOICES.md` greps pass;
live `ask` still works on GitHub Models dev aliases after rewiring.

### Implementation for User Story 3

- [X] T015 [US3] Finalize `src/memagent/llm/clients.py` per contracts/llm-clients.md: constants `CONVERSATION_MAX_TOKENS=2048`/`ANALYTICS_MAX_TOKENS=256`; `OpenAIChatLLM(client, model, max_tokens, temperature=0.0)`; `complete()`/`parse()` bodies call ONLY `_call`/`_parse_call` seam methods (pass `max_tokens`, include `temperature` iff not None); `OpenAIEmbedder(client, model, dim)`; `build_openai_clients(settings)` (SystemExit one-liner on empty key; ONE shared `AsyncOpenAI(max_retries=0, timeout=float(llm_timeout_s), base_url or None)`); delete the module-level `_client()` helper
- [X] T016 [US3] Rewire `src/memagent/app.py` `build_resources()` to `build_openai_clients(settings)` for conversation/analytics/embedder (Ruling D finalisation); keep `assert_index_dims`, Redis, searcher/fetcher, turn_logger construction unchanged (depends on T015; sequential with T008 on app.py — same file)
- [X] T017 [US3] Scripted FR-001…006 verification (recorded, no committed test file): stub `_call`/`_parse_call` → usage dicts exact (2311/402 case); `build_openai_clients` products carry pinned model ids + 2048/256 + temp 0 + shared client `max_retries==0`/`timeout==45.0`; `inspect.getsource(complete/parse)` contains no `self._client.`; empty-key → readable SystemExit; `OPENAI_BASE_URL` plumbed (depends on T015, T016)
- [X] T018 [P] [US3] Port `/Users/mohamed.elsayed/Desktop/epam/MODEL_CHOICES.md` → `~/Desktop/epam/memory-first-agent/MODEL_CHOICES.md`: re-verify every price against the official OpenAI pricing page (fresh verification date), keep full why-not table + free-dev note + per-turn/$100-turn figures (spec FR-008 verbatim price set)
- [ ] T019 [US3] FR-007 live probe — ⚠️ BLOCKED on the user-provided real `sk-…` platform key (Clarify Option B): run the contracts/llm-clients.md snippet against pinned `gpt-5.4-mini` (`temperature=0`, `max_tokens=8`); record verbatim outcome + date in `MODEL_CHOICES.md` and `docs/ai_prompts/milestone-4.md`; contingencies: temp-400 → `temperature=None` for conversation client + document; max_tokens-400 → `max_completion_tokens` inside seams only + document; NEVER swap models (depends on T018 for the doc landing spot; independent of code tasks)
- [X] T020 [US3] CHECKPOINT: full `make test` + ruff green; live `uv run memagent ask` smoke on GitHub Models dev aliases (rewired clients work; stderr shows summaries/classify OK; `tokens.answer_llm` still lands in the newest JSONL record); `grep -c '\$0.75' MODEL_CHOICES.md` ≥ 1

**Checkpoint**: clients are production-shaped; cost story auditable

---

## Phase 6: User Story 4 — Interactive chat with clean observability (Priority: P4)

**Goal**: `timed()` stage latencies, structlog→stderr with `turn_id`, streaming REPL with
canonical banners and capped history (FR-020…022).

**Independent Test**: quickstart §4/§5 — miss→hit banners live in one chat session;
`ask` redirected to a file contains only answer+sources; stderr lines carry `turn_id=`.

### Implementation for User Story 4

- [X] T021 [P] [US4] Fill `src/memagent/utils/timing.py`: `timed(stage, fn)` per contracts/repl-and-observability.md (preserves fn's keys; adds `{"latency_ms": {stage: int_ms}}`)
- [X] T022 [US4] Wire `timed()` in `src/memagent/graph.py` at `add_node` time per data-model §7 stage map (`embed`, `vector_search`, `web_search`, `fetch`, `ingest`, `answer_llm`×2, `answer_failure`); `log_turn` NOT wrapped; node NAMES unchanged (mermaid stable); AND delete the now-redundant in-node latency writes + `started` bookkeeping in `src/memagent/nodes/search.py` (~line 28), `src/memagent/nodes/fetch.py` (~line 29), `src/memagent/nodes/ingest.py` (~line 107) — `timed()` is the single stage-latency owner (analyze I1; P-III); confirm no test asserts the old `fetch_pages`/`ingest_content` keys (pre-verified) (depends on T021)
- [X] T023 [US4] `src/memagent/app.py`: add `configure_logging(settings)` (structlog ConsoleRenderer + merge_contextvars + TimeStamper(iso) on `PrintLoggerFactory(file=sys.stderr)`, stdlib basicConfig→stderr w/ `settings.log_level`); `Agent.answer()` binds `structlog.contextvars.bind_contextvars(turn_id=…)` at turn start, `clear_contextvars()` in finally; extract the initial-state builder into a shared helper the REPL reuses (depends on T016 — same file, after US3's rewiring)
- [X] T024 [US4] Replace the `chat` stub in `src/memagent/cli.py` per contracts/repl-and-observability.md: `configure_logging` + key guard + Redis-down handling reused from `ask` (incl. `_redis_down_in_chain` — M3 fix applies to chat too); loop: shared state helper (fresh uuid4 turn_id, session_id, `history[-12:]`, `turn_started_at`), `agent.graph.astream(state, stream_mode="updates")`, banner on `memory_search` update (inclusive `>=` vs threshold; share ONE banner constant with `ask` — byte-identical `[MEMORY MISS → searching the web]`), print answer immediately on `answer_from_memory`/`answer_from_web`/`answer_failure` update + sources `(origin) title <url>`, dormant `guard_input`/blocked branch; bind `structlog.contextvars.bind_contextvars(turn_id=…)` at the start of EACH REPL turn and `clear_contextvars()` after (the REPL bypasses `Agent.answer()`, so the loop must bind its own — analyze U1, FR-021); history append+truncate to `history_max_turns*2`; `exit`/`quit`/EOF clean exit; also call `configure_logging` in `ask` (depends on T023; sequential with T012 on cli.py — same file)
- [X] T025 [US4] CHECKPOINT: quickstart §4 (chat: novel question → MISS banner + sourced answer BEFORE that turn's classify stderr lines; identical re-ask → HIT sim≥0.70, zero web lines — use the Redis question, calibration note) and §5 (`ask > out.txt` → 0 `turn_id=` on stdout, ≥1 on stderr); unit-style boundary check 0.70→HIT/0.6999→MISS on the banner decision; history cap check (7 turns → 12 messages)

**Checkpoint**: all four stories functional

---

## Phase 7: Polish & Milestone Close

- [X] T026 [P] Author `docs/ai_prompts/milestone-4.md` (complete M4 instruction record: spec-kit phase prompts verbatim, live verification tables incl. the PAT/catalog/probe records + T002 findings, per-component provenance) and append the M4 section + provenance rows to `AI_USAGE.md` (FR-023, P-VII)
- [X] T027 Final DoD sweep per source spec §9 + quickstart §8: `ruff check` + `format --check` + `make test` green; all four subcommands real (FR-024) — `wipe-memory` → `ask`×2 → `chat` turn → `analytics` shows real hit-rate/topic tables over this session's turns; then commit → push branch → CI green → merge to main → CI green (M1–M3 workflow); update the project memory note

---

## Dependencies & Execution Order

- **Phase 1 → 2**: T001 → T002 (facts before code)
- **US1 (P3..)**: T003/T004 [P] (tests first, fail) → T005 → {T006 [P with T005]} → T007 (needs T005+T006) → T008 (needs T006) → T009
- **US2**: T010/T011/T013 [P] → T012 (needs T010) → T014. Independent of US1 code (sample-driven), but live-turn sections of T014 read US1's output — run after T009 as ordered
- **US3**: T015 → T016 → T017; T018 [P] anytime; T019 blocked ONLY on the real key (can run any time after T018, even post-merge if the key arrives late — record accordingly) → T020
- **US4**: T021 [P] → T022; T023 after T016 (app.py); T024 after T023 + T012 (cli.py) → T025
- **File-coordination (no parallel writes)**: `app.py`: T008 → T016 → T023; `cli.py`: T012 → T024; `clients.py`: T015 only
- **Polish**: T026 [P] alongside late US4; T027 last

### Parallel opportunities

- T003 + T004 (both new test files)
- T005 + T006 (different modules) after tests are authored
- T010 + T011 + T013 (report module / sample data / README)
- T018 anytime; T021 anytime after T002
- T026 in parallel with T025

## Implementation Strategy

**MVP = Phase 1–3 (US1)**: the graded turn log alone is demoable (`ask` + JSONL
inspection) and is the assignment's core logging requirement. Then US2 (the report makes
the log legible — the milestone's demoable outcome), US3 (client finalisation +
cost story), US4 (operator UX). Stop-and-validate at every checkpoint task (T009, T014,
T020, T025). If the real key hasn't arrived by T019, proceed through T027 with T019
explicitly recorded as pending-on-key, run it the moment the key lands, and amend
`MODEL_CHOICES.md`/prompts log in a follow-up commit — the DoD item stays open until then.
