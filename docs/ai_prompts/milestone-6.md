# Milestone 6 — Complete instruction record (appended 2026-07-06)

Chronological log of every instruction that drove Milestone 6 (integration/e2e tests, eval
harnesses, CI green, docs, v1.0), per the disclosure rule in `AI_USAGE.md` (Constitution
P-VII: appended as the milestone lands, never retroactively). Tooling: Claude Code (Opus 4.8)
orchestrating dynamic workflows of subagents for the verification passes + GitHub Spec Kit at
the planning workspace; source spec `specs/milestone-6-e2e-evals-delivery.md`.

## 1. Spec Kit phase prompts (user-issued, verbatim)

1. `/speckit-specify for Milestone 6, feeding it specs/milestone-6-e2e-evals-delivery.md`
   → `specs/006-m6-e2e-evals-delivery/spec.md` (25 FRs FR-001…025 restating FR-M6-01…24 incl.
   the source's FR-M6-11b → FR-012; 4 user stories P1–P4; 16/16 quality checklist).
2. `/speckit-clarify` → 2 questions asked and answered (both Option A; §2 below).
3. `/speckit-plan` → plan.md (Constitution Check 9/9 PASS pre- and post-design), research.md
   (R0 repo probe + D1–D15 + live library verifications), data-model.md, 4 contracts,
   quickstart.md. The plan phase ran a **7-agent parallel probe of the shipped M1–M5 code
   BEFORE cutting the design** (the M3/M4/M5 lesson) — M6 is pure integration, so every
   fixture/test/script calls real shipped signatures.
4. `/speckit-plan recheck what has been planned` (ultracode) → an adversarial recheck workflow
   (6 finder dimensions × independent verifiers): 12 candidates, 11 confirmed → 9 distinct
   fixes applied (§4a).
5. `/speckit-tasks` → tasks.md, 18 tasks in 7 phases (Setup → Foundational conftest → US1 core
   proof → US2 evals+CI → US3 auto-docs → US4 delivery → Polish); then a 2-auditor tasks-audit
   workflow found 3 defects, all fixed (§4b).
6. `/speckit-analyze` → cross-artifact consistency gate: 3 LOW findings; user said "fix all
   findings" → all 3 remediated (§4c).
7. `/speckit-implement` → executed all 18 tasks against the real repo, testing each phase live
   (§5), and validated the whole pipeline locally.

## 2. Clarifications (both Option A)

- **Q1 — real-key deliverables & the `v1.0` tag gate**: tag `v1.0` on the **keyless path** (CI
  green + both `--mock` evals + every fact re-verifiable without a paid key). The three
  real-key artifacts (captured demo transcript, real-key `eval_lifecycle`, the `temperature=0`
  probe on the pinned `gpt-5.4-mini` — the open M4 T019 item) are marked **"pending real-key
  capture"** and do NOT block the tag (honors zero-key delivery, Constitution VIII).
- **Q2 — core-proof HTTP mocking**: **respx** intercepting the real search/fetch httpx client
  (LOCKED) — `call_count` is a literal HTTP route counter and the real Tavily+trafilatura
  pipeline is exercised e2e; a dummy `TAVILY_API_KEY` forces the interceptable httpx path.

## 3. Plan-phase repo probe (R0) — source-spec deltas found before coding (main `6a582e4`)

The probe **resolved** the two signatures the source spec flagged "unsure" — `PageFetcher.fetch(urls)`
and the **synchronous** `TurnLogger.log(record)` — and found: `conftest.py` did not exist (M6
creates it; the 12 unit tests keep local fakes); `tests/integration`/`e2e` and the CI redis
service did not exist; the record fields are `similarity_top` (← state `top_similarity`) and a
role-keyed `tokens` block; `stored_at` is derived at the knn boundary from an epoch `store()`
stamps itself; idempotent create is `ensure_index` (exists-guard), not raw `create`; the
Tavily/fetch clients are retry-wrapped (respx routes must be 200-only + non-redirecting); and
`temperature=0` on `gpt-5.4-mini` genuinely needs a real key (GitHub Models serves no gpt-5.4*
ids). Live-verified: respx 0.23.1, redisvl 0.23.0, langgraph 1.2.7 (`draw_mermaid` idempotent,
10 nodes), openai 2.44.0 (`chat.completions.parse`), pytest 8.4.2.

## 4. Verification workflows (adversarial, before and after cutting tasks)

### 4a. Plan recheck — 9 code-verified fixes (2 HIGH)
- **A (HIGH)** contracts wrote `Agent(build_graph(resources))`; the shipped `Agent(resources)`
  builds the graph itself → `AttributeError`. Fixed in all 3 contracts.
- **B (HIGH)** the e2e fetch fixture was a bare `<article>` → trafilatura returns `None` → page
  dropped → core proof fails. Fixed to a full HTML document (empirically confirmed vs trafilatura
  2.1.0; the shipped `test_fetch_retry.py` already uses the wrapped form).
- **C/D/E/F/G/H/I** (LOW–MED): `AgentResources` ref; SC-007 vs the keyless-tag clarification;
  the `ruff format` "untouched" wording; the `schema_factory` requirement for
  `QueryClassification`/`GroundingVerdict`; a dangling `(D0)`; the `sys.path` shim standalone
  scripts need to import `tests.conftest`; the "both evals import build_test_resources"
  over-generalization. 1 finding correctly refuted.

### 4b. Tasks audit — 3 fixes
A coverage gap (the FR-001/002/003 acceptance assertions had no authoring task — the happy-path
e2e never fires the retry or the disjoint-cosine case → added a keyless `tests/unit/test_m6_fixtures.py`),
a parallel-write hazard (T015/T016 both write the verification note → made T016 sequential), and
a `[P]` mislabel on T012.

### 4c. Analyze — 3 LOW fixes
The `topic=…` ellipsis in a task example; the FR-004/005 coverage-line imprecision; a note that
`DECISIONS.md` finalization is a DoD item without a discrete FR.

## 5. Implementation session (task order, tested live at each phase)

Branch `m6-e2e-evals-delivery` from green `main` `6a582e4` (103 tests). Foundational
`tests/conftest.py` (settings/fakes/redis-skip/clean-index/`build_test_resources`) + the audit's
`tests/unit/test_m6_fixtures.py` → **109 unit tests green keyless**. US1: `tests/integration/test_redis_store.py`
(4 checks incl. the exact 0.70 boundary) + `tests/e2e/test_lifecycle.py` (**the core proof: turn 1
`memory_miss_web_search` call_count 1 → identical turn 2 `memory_hit` sim 1.0, call_count still 1,
memory-origin source, URL match, 2 turn records with populated tokens**) → **5 integration/e2e
green**. US2: `scripts/eval_lifecycle.py --mock` (all 3 questions miss-then-hit, exit 0; no-key →
readable error, exit 2) + `scripts/eval_grounding.py --mock` (keyless, redis-less, 6-case scorecard,
exit 0) + the one-time `ruff format .` pass (29 files, cosmetic) + finalized `.github/workflows/ci.yml`
(single job, `redis:8.2` service, ruff→unit→integration/e2e→both eval mocks→coverage report, zero
secrets, no cov gate — every step validated locally incl. `uv sync --frozen` and the coverage chain
= 76%). US3: extended `scripts/render_graph.py` (idempotent 10-node mermaid into README +
`docs/architecture.md`) + `scripts/capture_demo.py`. US4: finalized README (ten verbatim sections +
the auto-generated graph), this record + `AI_USAGE.md` + `DECISIONS.md`, and the dated
re-verification note.

## 6. Real-key items (pending, Clarification Q1)

`docs/demo_transcript.md` retains the **real** M3-captured miss→hit transcript (GitHub Models dev
tier); the production-key re-capture via `capture_demo.py`, the real-key `eval_lifecycle` run, and
the `temperature=0` probe on `gpt-5.4-mini` are recorded "pending real-key capture" — they do not
block `v1.0`, and the identical behaviour is enforced keylessly in CI.
