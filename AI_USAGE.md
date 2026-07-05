# AI Usage

This project is built with AI assistance under a strict disclosure rule: the complete
instruction record is appended per milestone in `docs/ai_prompts/` — never written
retroactively. This file is the index and narrative; the appendix holds every prompt.

## 1. Tools used

- **Claude Code** (Anthropic CLI) with the Claude Fable 5 model as the primary assistant,
  orchestrating Opus 4.8 subagents for multi-agent design/review workflows during planning.
- **GitHub Spec Kit** (spec-driven development): `/speckit-constitution`, `/speckit-specify`,
  `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-analyze`,
  `/speckit-implement` drive each milestone from spec to code.

## 2. Workflow narrative

Plan-first: an 8-specialist + adversarial-review AI workflow produced the project plan
(PLAN.md in the planning workspace), which was split into six milestone specifications with
BDD scenarios. Each milestone then runs through Spec Kit (specify → clarify → plan → tasks →
analyze → implement) with a human decision at every clarification gate. Code is generated
milestone by milestone against reviewed specs; every milestone ends with a Definition of
Done sweep and this file's per-milestone append.

## 3. Per-component provenance table

| Component | Provenance | Notes |
|---|---|---|
| `pyproject.toml`, `.python-version`, `uv.lock` | AI-generated, human-reviewed | pins copied verbatim from the reviewed plan |
| `src/memagent/config.py` (Settings) | AI-generated, human-reviewed | field set fixed by plan §10.3 |
| `scripts/gen_env_example.py` + `.env.example` | AI-generated | byte-identical regeneration verified |
| `src/memagent/memory/schema.py` | AI-generated, human-reviewed | 11-field index; verified live against redis:8.2 |
| `src/memagent/cli.py` | AI-generated, hand-corrected | redis-down error handling fixed after live failure test (see §6) |
| `Makefile`, `docker-compose.yml`, `.github/workflows/ci.yml` | AI-generated | shapes fixed by plan |
| `scripts/verify_redisvl.py` | AI-generated | M1 verification duty; output recorded in the appendix |
| `tests/unit/test_smoke.py` | AI-generated | scope deliberately bounded to smoke checks |
| `state.py`, `interfaces.py`, `resources.py`, `routers.py` | AI-generated, human-reviewed | canonical types + the 5 pure routers (M2) |
| `memory/store.py`, `chunking.py`, `urls.py` | AI-generated, human-reviewed | single conversion site; 25 unit tests green first run (M2) |
| `llm/clients.py`, `llm/prompts.py`, `nodes/`, `graph.py`, `app.py` | AI-generated, human-reviewed | thin clients (max_retries=0), hit-path graph, facade (M2) |
| `scripts/seed_memory.py`, `docs/seed.md` | AI-generated | demo fixture + seeder (M2) |
| `web/search.py`, `web/fetch.py`, `web/to_markdown.py` | AI-generated, human-reviewed | raw-httpx Tavily + ddgs fallback, SSRF-guarded bounded fetch, markdown gating; field mappings live-verified (M3) |
| `security/sanitizer.py` | AI-generated | pass-through seam; M5 swaps internals without touching call sites (M3) |
| `nodes/search.py`, `nodes/fetch.py`, `nodes/ingest.py`, `answer_from_web` | AI-generated, human-reviewed | the real miss branch; ingest order is the T3 defence (M3) |
| `graph.py` rewire, `app.py` real resources, `cli.py` miss banner | AI-generated | M2 temporary edge removed; canonical `[MEMORY MISS → searching the web]` (M3) |
| `memory/schema.py` `wipe_index` doc-meta fix | AI-generated, hand-caught | live Redis inspection found stale `doc:*` metas would defeat the freshness gate after a wipe (see §6, M3) |
| `tests/unit/test_to_markdown.py`, `docs/demo_transcript.md` | AI-generated | the one M3-owned test file (Ruling A) + captured live lifecycle (M3) |
| `llm/clients.py` finalized + `build_openai_clients` | AI-generated, human-reviewed | ONE shared AsyncOpenAI, `_call`/`_parse_call` retry seams, pinned params; scripted FR assertions (M4) |
| `analytics/classify.py` hardening, `analytics/turnlog.py`, `nodes/log.py` real node | AI-generated, human-reviewed | `_missing_→other`, null-tolerant 8s/×2 classifier; one TurnRecord JSONL line per turn incl. blocked; never raises (M4) |
| `analytics/report.py`, `logs/turns.sample.jsonl`, `cli.py` analytics | AI-generated | aggregate + rich tables, `--json`, markup-escape on user strings; 10-record sample (M4) |
| `cli.py` chat REPL, `app.py` `configure_logging`/`new_turn_state`, `utils/timing.py`, `graph.py` timed() wiring | AI-generated, human-reviewed | streaming banners, 6-turn history cap, stderr-only structlog with turn_id, single-owner stage latency (M4) |
| `tests/unit/test_classifier_parsing.py`, `tests/unit/test_turnlog.py`, `MODEL_CHOICES.md` port | AI-generated | the two M4-owned test files (tests-first); prices re-verified 2026-07-05 on the official page (M4) |
| Remaining stubs (`security/guardrails`, `utils/reliability.py`, `utils/errors.py`) | AI-generated | docstring-only; filled in M5 |

## 4. Curated highlights (3-6 representative prompts)

1. "Build a Memory-First Web Agent in Python … answers from Redis vector memory first
   (similarity ≥ 0.7), falls back to web search on a miss …" — the original assignment
   framing that seeded the plan.
2. "Review what you did and if there are better alternatives in terms of technology … justify
   the 2 LLM models, why not others that might be same or better and cheaper." — triggered the
   adversarial market re-review that changed the conversation model choice.
3. "Based on the plan I want it divided into MD files based on the 6 milestones … add BDD
   scenarios and make sure it is good to start … using spec-driven development using spec kit."
4. "/speckit-clarify" answers: deliverable lives in `epam/memory-first-agent/` as its own
   repo (A); LICENSE = MIT (A); public GitHub repo + green CI inside M1's DoD (C).
5. "/speckit-implement" — executed the 22-task M1 plan that produced this repository.

## 5. Complete prompt log (see docs/ai_prompts/)

One file per milestone, appended as that milestone is built — the chronological
instruction record:

- `docs/ai_prompts/milestone-1.md` — Milestone 1 (scaffold, toolchain, index schema)
- `docs/ai_prompts/milestone-2.md` — Milestone 2 (memory path, threshold routing, live
  GitHub Models verification records)
- `docs/ai_prompts/milestone-3.md` — Milestone 3 (web pipeline; Tavily/ddgs/trafilatura
  verification records, analyze findings I1/I2/U1, the wipe-memory freshness-gate fix,
  and the first live miss→ingest→hit transcript)
- `docs/ai_prompts/milestone-4.md` — Milestone 4 (turn log, classifier, analytics CLI,
  REPL, finalized clients; PAT/pricing/probe verification records, analyze findings, the
  ISO-language and latency-single-owner fixes, and the pending pinned-model temperature
  probe status)

## 6. What was reviewed, tested, and corrected by hand

- Live failure test caught that `redis.asyncio` raises `redis.exceptions.ConnectionError`
  (not the builtin) — the CLI's readable-error contract failed on first run and was corrected,
  then re-verified (one-line error, exit 1, clean recovery).
- `FT.INFO` observation: redisvl registers the FT.CREATE prefix as `chunk` (bare, without the
  separator); keys are still `chunk:<id>` and the `doc:*` meta prefix stays un-indexed — the
  double-colon trap the plan warned about is confirmed avoided.
- Field-count truth-check: `Settings` has 32 fields (design docs briefly claimed 33; corrected).
- M3 live inspection caught that `wipe-memory` left the non-indexed `doc:*` freshness
  metas behind — harmless before M3, but it would have made the freshness gate silently
  skip re-ingestion after a wipe. Fixed in `wipe_index` and re-verified (0 keys post-wipe).
- M3's `/speckit-analyze` caught a Protocol-signature conflict (placeholder `PageFetcher`
  vs the designed URL-list `fetch`) before any code was written — fixed in the task list.
- M4's plan-phase repo probe found two source-spec work items already shipped (usage-returning
  `complete()`, answer-node token capture) and the log stub under a different filename —
  preventing duplicate/conflicting tasks; M4's `/speckit-analyze` then caught that three M3
  nodes self-measured latency (the planned `timed()` wrapper would have clobbered/drifted the
  keys) and that the `logs/` directory ignore made the tracked sample log impossible.
- M4's first live classified turn returned `language: "English"` instead of the ISO code —
  fixed with a schema field description and re-verified live (`"en"`).
- M4's manual test session (run under a real GitHub Models rate-limit window) caught that
  `answer_from_memory` — unlike its web sibling — didn't catch LLM failures: a live 429 on
  the hit path crashed the chat REPL AND lost the turn's log record. Also caught: a corrupt
  JSONL line crashed `memagent analytics`, and `--json` emitted prose on a missing log.
  All three fixed and re-verified (see milestone-4.md §7a).
- Every Definition of Done command was executed for real (see milestone log), not assumed.

## 7. What was deliberately NOT AI-generated

- The decision framework itself: milestone gates, clarification answers (repo layout, license,
  repo visibility), and every KEEP/CHANGE ruling in `DECISIONS.md` were human decisions.
- Model and cost selection judgments, the threat-model priorities, and the anti-churn scope
  cuts were decided in reviewed planning sessions, not free-generated.

## 8. Judgement notes

- AI was fastest at verbatim-faithful scaffolding (pins, schema, Makefile) — zero corrections
  needed where the plan was explicit.
- The one real M1 bug (exception hierarchy) is exactly the class of error live verification
  exists to catch; "generate then prove by running" remains the working rule.
