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

Three later AI-assisted passes hardened the delivery beyond the six planned milestones — M7
(test-coverage hardening → `v1.1`), M8 (delivery-readiness review + fixes → `v1.2`), and M9
(executable BDD scenarios for every function → `v1.3`). M7/M8 were driven by adversarial
subagent workflows that audited the shipped repo and reported findings to the user *before*
any change; M9 authored the BDD layer via a 32-agent workflow with a 13-agent pre-commit
verification pass — all logged the same append-only way (§5).

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
| `security/patterns.py`, `security/guardrails.py`, `nodes/guard.py` | AI-generated, human-reviewed | L1 severity-tagged registry + input screen + guard entry node; patterns tightened after the impl-verification workflow caught benign false positives (M5, see §6) |
| `security/sanitizer.py` (real body), `llm/prompts.py` (L2 finalised) | AI-generated, human-reviewed | L3 neutralise-not-delete sharing the L1 registry; hardened system prompt + provenance-headed `wrap_context`; bodies swapped at the frozen call-sites (Rulings C/E) (M5) |
| `utils/reliability.py`, `utils/errors.py`, client/`web`/`store` retry wraps | AI-generated, human-reviewed | single-owner tenacity policies (analytics client deliberately unwrapped, D3), 4 typed errors, redis native `Retry`; live-verified library surfaces (M5) |
| `nodes/{memory,answer}.py` degradation, `graph.py` guard rewire, `cli.py` banners, `app.py` `TurnResult.degradation` | AI-generated, human-reviewed | the degradation matrix wired end-to-end; `ask` table orders `failed` before `redis_down` (recheck fix B) (M5) |
| `tests/unit/{test_guardrails,test_sanitizer,test_search_retry,test_fetch_retry,test_reliability}.py`, `docs/threat_model.md`, `scripts/render_graph.py` | AI-generated | five M5-owned test files (tests-first) + threat model T1–T4 + keyless graph render (M5) |
| `tests/conftest.py`, `tests/integration/`, `tests/e2e/`, `scripts/eval_lifecycle.py`, `scripts/eval_grounding.py`, CI, README/docs | AI-generated, human-reviewed | integration + e2e + eval harnesses + CI green + docs; repo-probe / plan-recheck / impl-verify workflows caught defects before coding (M6, v1.0) |
| `tests/unit/{test_url_filter,test_search_provider,test_ingest,test_report,test_clients,test_m1_contracts,test_answer_context,test_timing}.py` + test edits | AI-generated, human-reviewed | 18 audited test-coverage gaps closed, mutation-verified 14/14; dead `_LLM_FAST_FAIL_STATUS` removed (M7, v1.1) |
| L3 sanitizer HIGH-only scope, `doc:{h}` meta TTL, constants→`Settings`, `scripts/seed_memory.py` fix, stale-docstring polish | AI-generated, human-reviewed | delivery-readiness review (36-agent workflow); 23 findings fixed, 3 behavior changes mutation-verified (M8, v1.2) |
| `tests/bdd/` (45 features, 18 bindings, `test_bdd_traceability.py` gate), `docs/BDD.md`, `pytest-bdd>=8.1.0` dep | AI-generated, human-reviewed | 210 scenarios covering all 142 functions, mutation-verified 6/6; zero source changes (M9, v1.3) |

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

`docs/ai_prompts/` is **the complete instruction record** — one file per milestone, appended
as that milestone is built (never retroactively, per Constitution Principle VII), the
chronological log of every instruction:

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
- `docs/ai_prompts/milestone-5.md` — Milestone 5 (guardrails L1/L2/L3 + reliability retries
  + degradation matrix; the four clarifications, three planning-artifact verification
  workflows, the live manual-test session, and the impl-verification workflow that caught
  four false-positive/substring bugs in the shipped code — all fixed and regression-guarded)
- `docs/ai_prompts/milestone-6.md` — Milestone 6 (integration + e2e tests, eval harnesses,
  CI green, docs, v1.0; the full Spec Kit chain, the repo-probe + plan-recheck + tasks-audit
  workflows that caught the `Agent(resources)` and full-HTML-fixture defects before coding, and
  the implementation + verification of the miss→hit core proof)
- `docs/ai_prompts/milestone-7.md` — Milestone 7 (post-v1.0 test-coverage hardening → v1.1; a
  25-agent audit workflow found 18 test-coverage gaps behind a fully-green suite, all closed and
  mutation-verified 14/14, plus removal of a dead constant)
- `docs/ai_prompts/milestone-8.md` — Milestone 8 (delivery-readiness review + fixes → v1.2; a
  live manual e2e run and a 36-agent reviewer-lens file review found 23 findings, all fixed
  incl. three mutation-verified behavior changes)
- `docs/ai_prompts/milestone-9.md` — Milestone 9 (executable BDD scenarios → v1.3; 45 feature
  files / 210 scenarios covering all 142 functions, enforced by an AST-based traceability
  gate, authored by a 32-agent workflow and proven non-vacuous by a 13-agent verification
  pass with 6/6 source mutants caught; zero source changes; landed as seven phase-scoped
  commits, each independently full-suite green, tagged v1.3)
- `docs/ai_prompts/milestone-10.md` — Milestone 10 (full-repo review + fixes; a 67-agent
  adversarially-verified review found 0 critical / 1 high / 5 medium, of which the high
  (fresh-Redis quickstart crash) and the two security mediums (SSRF-via-redirect, Tavily
  malformed-200 skipping the ddgs fallback) were fixed and mutation-verified; 371 tests,
  traceability gate at 146 functions)
- `docs/ai_prompts/milestone-11.md` — Milestone 11 (fix all remaining confirmed findings; a
  file-disjoint editor workflow addressed the rest — concurrent ingest, off-loop trafilatura,
  pipelined store writes, DNS-resolving SSRF guard, compound-ccTLD diversity, blocked-history
  fix, token/cost aggregation, a non-vacuous mock grounding eval, a strengthened traceability
  gate, dep pin + CI secret/dep scans, and doc-truth fixes; four findings deliberately not
  changed with rationale; 399 tests)

## 6. What was reviewed, tested, and corrected by hand

- Live failure test caught that `redis.asyncio` raises `redis.exceptions.ConnectionError`
  (not the builtin) — the CLI's readable-error contract failed on first run and was corrected,
  then re-verified (one-line error, exit 1, clean recovery).
- `FT.INFO` observation: redisvl registers the FT.CREATE prefix as `chunk` (bare, without the
  separator); keys are still `chunk:<id>` and the `doc:*` meta prefix stays un-indexed — the
  double-colon trap the plan warned about is confirmed avoided.
- Field-count truth-check: `Settings` had 32 fields at M1 (design docs briefly claimed 33;
  corrected) — now 37 after M8 moved tuning constants into `Settings`.
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
- M5's `/speckit-plan recheck` ran an adversarial workflow over the planning artifacts (17
  findings → 8 confirmed → 6 fixes) and a tasks audit (6 doc-accuracy fixes) BEFORE any code
  — catching a wrong CLI exit-code ordering and an under-specified provenance chain while
  they were still cheap to fix.
- M5's impl-verification workflow (run after the 100-test suite was green, the same
  "prove it, don't assume it" discipline as the M3/M4 manual sessions) caught four real
  bugs the tests missed: the shared injection registry, applied to fetched web content in
  L3, corrupted benign technical prose ("PostgreSQL can act as a message queue") and
  falsely flagged it; the same `role_hijack`/`instruction_override` looseness over-BLOCKED
  benign queries at L1; and a `"sources:" in answer.lower()` check matched inside
  "resources:", silently dropping the citation footer. All four fixed (tighter,
  context-anchored patterns; a line-anchored Sources header check) and regression-guarded;
  two other reported findings were correctly refuted (an inherent regex recall gap, and a
  CommonMark-correct image strip). See milestone-5.md §7.
- A second M5 manual session (2026-07-06) inspected the ACTUAL Redis-stored chunks after a
  real ingestion and caught two dual-use false positives the workflow's synthetic fixtures
  missed: `role_hijack` neutralised "switch to developer mode" (a real product feature) and
  bare "jailbreak" on a benign Chromium security doc, corrupting the stored text and flagging
  the page. Both fixed (dropped `developer mode` and standalone `jailbreak` from the pattern;
  real attacks still caught via the framing-gated `jailbroken`/`dan`/`do-anything-now`
  tokens) and regression-guarded; re-ingestion then stored 0 marked/flagged chunks. See
  milestone-5.md §8. Lesson: a shared L1-query/L3-content registry must be tuned against real
  fetched prose, and verified by inspecting stored chunks — not just the answer text.
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
