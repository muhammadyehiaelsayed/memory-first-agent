# Implementation Plan: Milestone 4 — LLM Clients Finalized, Turn Log, Classifier, Analytics CLI, REPL

**Branch**: `004-m4-llms-logging-analytics` | **Date**: 2026-07-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-m4-llms-logging-analytics/spec.md`
(restating source `specs/milestone-4-llms-logging-analytics.md`; that file's §3/4/6/10
drive this plan)

## Summary

M4 stands up the observability half of the agent: the two OpenAI clients take their final
shape (shared `AsyncOpenAI`, pinned models, `max_tokens` 2048/256, `temperature=0`,
one `_call`/`_parse_call` seam per surface for M5's retries), the M2 no-op `log_turn` stub
in `nodes/log.py` becomes the real node (classify → `build_turn_record` → JSONL append,
never raises), a nano-model classifier labels every query (closed enums, `_missing_ →
other`, 8 s timeout, tenacity ×2, null-on-failure), `memagent analytics` renders ten
report sections (plus `--json`) over `logs/turns.jsonl`, and `memagent chat` becomes a
streaming REPL with the canonical hit/miss banners, pipe-clean stdout, and structlog
diagnostics on stderr. Technical approach is fixed by source §6 plus the repo probe
(research D1): two source-assumed work items are already on main (usage-returning
`complete()`, answer-node token capture), and the log node lives at `nodes/log.py` — all
edits are in-place stub replacements that change no call sites.

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.14`), `uv`-managed

**Primary Dependencies**: openai 2.44.0 (`chat.completions.parse` verified), langgraph
1.2.7 (`astream(stream_mode="updates")` verified), tenacity 9.1.4, structlog 26.1.0
(contextvars processors verified), rich 15.0.0 (`markup.escape` verified), typer,
pydantic/pydantic-settings — zero new dependencies (all pinned since M1)

**Storage**: `logs/turns.jsonl` append-only JSONL (single source of truth, no Redis
mirror); Redis 8 memory index untouched by this milestone

**Testing**: pytest; M4-owned `tests/unit/test_classifier_parsing.py` +
`tests/unit/test_turnlog.py` with inline fakes (M6 conftest fixtures do NOT exist yet);
zero keys, no network (P-VIII)

**Target Platform**: local CLI (macOS/Linux), CI on GitHub Actions with dockerized redis

**Project Type**: single Python CLI project (`src/memagent/`)

**Performance Goals**: classifier bounded at 8 s (never blocks the visible answer — it
runs after the answer prints); per-stage latency instrumentation adds only
perf_counter arithmetic per node

**Constraints**: `log_turn` NEVER raises; stdout pipe-clean (answer+sources only);
`max_retries=0` on the SDK (retries are M5's); replacing stubs must not change call
sites; anti-churn list (no token streaming, no Redis log mirror, no coverage gate)

**Scale/Scope**: ~6 source files edited, 3 placeholder files filled, 2 new test files,
1 doc port (`MODEL_CHOICES.md`), 1 sample data file, ~10-record sample log

## Constitution Check

*GATE: evaluated against Constitution v1.0.0 before Phase 0; re-checked post-design.*

| # | Gate (Principle) | Verdict | Evidence |
|---|---|---|---|
| 1 | P-I routing is code | PASS | No routing changes; banner decision reuses the router's inclusive `>=` comparison (contract repl-and-observability) |
| 2 | P-II one conversion site | PASS | M4 reads `top_similarity` only; no similarity math anywhere in the new code |
| 3 | P-III single owner | PASS | Retries: classifier's ×2 is the source-mandated, documented carve-out (research D6), SDK stays `max_retries=0`; config: all knobs already in `Settings`; types: record reads `state.py` types, classify.py hardened in place, never re-declared |
| 4 | P-IV JSONL single source of truth | PASS | One record/turn incl. blocked; closed route enum from `state.py`; no Redis mirror; analytics read records only |
| 5 | P-V sanitize before store | PASS | M4 stores nothing new to memory; classifier treats the query as tagged DATA (FR-014) — same spirit, no sanitizer changes |
| 6 | P-VI scope discipline | PASS | Only source-§2 items; anti-churn respected (updates-mode streaming only, no log mirror, no coverage gate, uuid4 ids) |
| 7 | P-VII AI_USAGE per milestone | PASS | FR-023 + planned `docs/ai_prompts/milestone-4.md` |
| 8 | P-VIII zero-key testability | PASS | Owned tests use inline fakes + tmp_path; analytics CLI needs no key/Redis; only FR-007 probe is live (manual, documented) |
| 9 | P-IX evidence-based | PASS | 8 live verifications recorded in research (SDK surfaces ×4, catalog probe, inference probes ×2, repo-state probe); prices re-verified at implement |
| 10 | Tech & architecture constraints | PASS | One StateGraph, node names unchanged (mermaid stable); JSONL log; locked model ids from `Settings`; no new deps |
| 11 | Workflow & quality gates | PASS | M1–M3 DoDs green (M3 closed 2026-07-05, main `20145bd`); M4-owned test files match the fixed ownership map; stub replacements keep call sites |

**Initial Constitution Check: PASS (11/11).**

## Project Structure

### Documentation (this feature)

```text
specs/004-m4-llms-logging-analytics/
├── plan.md              # This file
├── research.md          # Phase 0 (D1–D11, incl. repo-probe deltas + live verifications)
├── data-model.md        # Phase 1 (TurnRecord, classification, aggregate, stage map)
├── quickstart.md        # Phase 1 (8 validation scenarios)
├── contracts/
│   ├── llm-clients.md            # FR-001…008
│   ├── turn-log-and-classifier.md # FR-009…015
│   ├── analytics-report.md        # FR-016…019
│   └── repl-and-observability.md  # FR-020…022
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (deliverable repo: `~/Desktop/epam/memory-first-agent`)

```text
src/memagent/
├── llm/clients.py           # EDIT: final constructors, seam methods, build_openai_clients()
├── app.py                   # EDIT: build_resources() → build_openai_clients(); real TurnLogger;
│                            #       configure_logging(); turn_id contextvars bind in answer()
├── analytics/
│   ├── classify.py          # EDIT (harden in place): _missing_ hooks + classify() + prompts
│   ├── turnlog.py           # FILL placeholder: TurnLogger + build_turn_record
│   └── report.py            # FILL placeholder: aggregate() + render_report()
├── nodes/log.py             # REPLACE stub body: real make_log_turn (imports unchanged)
├── utils/timing.py          # FILL placeholder: timed()
├── graph.py                 # EDIT: wrap nodes with timed() per stage map (names unchanged)
├── cli.py                   # EDIT: real chat REPL + real analytics command (ask/wipe untouched
│                            #       except shared banner constant + configure_logging call)
└── interfaces.py            # EDIT: TurnLogger docstring only (signature already final)

logs/turns.sample.jsonl      # NEW: 10-record sample (data-model §5)
MODEL_CHOICES.md             # NEW at repo root: ported + re-verified + probe outcome
README.md                    # EDIT: DuckDB one-liner note
tests/unit/test_classifier_parsing.py   # NEW (M4-owned)
tests/unit/test_turnlog.py               # NEW (M4-owned)
docs/ai_prompts/milestone-4.md           # NEW (P-VII)
AI_USAGE.md                              # EDIT: M4 section
```

**Structure Decision**: single-project layout continues; every M4 module path already
exists as an M1 placeholder or M2 stub — the milestone fills/replaces in place and adds
only tests, sample data, and docs.

## Complexity Tracking

No constitution violations — table intentionally empty.

## Post-Phase-1 Constitution re-check

PASS (11/11) — design introduced no new violations. Three **repo-vs-source deltas**
surfaced by the Phase 0 probe are folded into the contracts so `/speckit-tasks` cuts
correct tasks (the M3 lesson — catch signature drift before code):

1. **`nodes/log.py`, not `nodes/log_turn.py`** — the stub file M4 must edit in place;
   creating the source spec's filename would orphan the graph import (research D1).
2. **Two source tasks are already satisfied on main** — `complete()` returning
   `CompletionResult` with usage, and answer-node `tokens.answer_llm` capture (source
   T-M4-08b). They become verify-only assertions, not implementation tasks.
3. **`analytics/turnlog.py`/`report.py`/`utils/timing.py` exist as placeholders** —
   tasks phrase these as "fill placeholder", preserving module paths and imports.

Plus one environment fact affecting task ordering: the FR-007 probe needs the real OpenAI
key (Clarify Option B); the user's new fine-grained GitHub PAT was live-probed today —
catalog 200 but inference 403 (`no_access`, missing the "Models: read" account
permission) and no `gpt-5.4*` ids served — so dev stays on the classic PAT and the probe
task blocks only on the real key, not on any code.
