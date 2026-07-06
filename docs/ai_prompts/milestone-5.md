# Milestone 5 — Complete instruction record (appended 2026-07-06)

Chronological log of every instruction that drove Milestone 5 (guardrails L1/L2/L3 +
reliability retries + degradation matrix), per the disclosure rule in `AI_USAGE.md`
(Constitution P-VII: appended per milestone, never retroactively). Tooling: Claude Code
(Fable 5) orchestrating Opus 4.8 subagents for the verification workflows + GitHub Spec Kit
at the planning workspace; source spec `specs/milestone-5-security-reliability.md`.

## 1. Spec Kit phase prompts (user-issued, verbatim)

1. `/speckit-specify for Milestone 5, feeding it specs/milestone-5-security-reliability.md`
   → `specs/005-m5-security-reliability/spec.md` (31 FRs: FR-001…029 ↔ FR-M5-01…29, +FR-030
   AI-disclosure, +FR-031 demoable outcome; 4 user stories P1–P4; 16/16 quality checklist).
2. `/speckit-clarify` → 4 questions asked and answered (all Option A; §2 below).
3. `/speckit-plan` → plan.md (Constitution Check 9/9 PASS pre- and post-design), research.md
   (R0 repo probe + D1–D15 + live library-surface verifications), data-model.md, 4 contracts,
   quickstart.md. The plan phase probed the repo BEFORE cutting tasks (the M3/M4 lesson).
4. `/speckit-plan recheck what has been planned` (ultracode) → an adversarial recheck
   workflow (6 dimensions × Opus, each finding independently verified): 17 raw findings, 8
   confirmed → 6 distinct fixes applied to the artifacts (§4a). Also caught + deleted an
   orphan `contracts/guardrails-l1.md` stub from a prior compacted session.
5. `/speckit-tasks` → tasks.md, 31 tasks in 7 phases (US1 L1 → US2 poisoning → US3 retries →
   US4 degradation), traceability to source T-M5-01…20; then an audit workflow (2 auditors)
   found 6 doc-accuracy defects, all fixed (§4b).
6. `/speckit-analyze` → cross-artifact consistency gate: 2 LOW findings; user said "fix all
   findings" → both remediated in tasks.md (§4c).
7. `/speckit-implement … make sure everything after implement is working correctly like I
   manually test it and use dynamic workflows if needed` → executed all 31 tasks TDD-first,
   ran a live manual-test session (§6), and an adversarial impl-verification workflow that
   caught 4 real code bugs — all fixed and regression-guarded (§7).

## 2. Clarifications (all Option A)

- **Q1 — category→severity map**: instruction-override/prompt-leak/role-hijack → HIGH
  (block); fake-role-markers/exfil-coaxing → MEDIUM (flag + skip_store). Makes the T1
  fixture resolve to `block`; impersonation/exfil phrasing degrades to flag-and-don't-store.
- **Q2 — blocked turn in `ask`**: exit 0 (a block is the guardrail working, distinct from
  `failed`), a distinct `[BLOCKED by input guard]` banner + refusal, no hit/miss banner.
- **Q3 — Redis-down warning**: a distinct `[MEMORY OFFLINE → searching the web (not cached)]`
  banner that REPLACES the miss banner; the warning never enters the answer text.
- **Q4 — flag verdict visibility**: silent on stdout (the medium tier tolerates false
  positives without punishing them); verdict + matched patterns live only in the turn record
  and stderr diagnostics.

## 3. Plan-phase live verifications (Constitution P-IX, 2026-07-05)

| Check | Result |
|---|---|
| Repo-state vs source-spec (main `5bc6bfc`) | only `memory_search` lacked a catch; `store.py` already persists `sanitizer_flags`+`content_sha256` (FR-014 pre-satisfied); fetch skip-rules pre-satisfied; `route_after_guard` verbatim in routers.py; `TurnResult` had no `degradation`; `classify.py` owns its own retry |
| Mermaid literals | live `draw_mermaid()` renders `__start__ --> guard_input` + dotted `guard_input -.-> log_turn` (NOT the source-spec's `START -->`/`-->|block|`) — assertions adjusted (D2) |
| tenacity 9.1.4 / redis 6.4 / openai 2.44 / respx 0.23.1 | AsyncRetrying, wait_random_exponential, Retry(backoff,retries), ExponentialBackoff(cap), APIStatusError.status_code all verified; httpx default timeout 5s (justifies the explicit Tavily timeout) |

## 4. Verification workflows on the planning artifacts

### 4a. Plan recheck (`/speckit-plan recheck`) — 6 fixes applied
- **[A]** web `sanitizer_flags` producer chain under-specified (ingest enrich + answer copy +
  a populated-flags test were missing a contract owner) — reconciled across plan/prompts-l2.
- **[B]** the `ask` render table checked `redis_down` before `failed`; a combined
  redis-down + LLM-down turn would exit 0 with the offline banner instead of the FR-027
  apology + exit 1 — reordered `failed` first.
- **[C]** the 401→ddgs search-retry test escapes respx (ddgs uses primp/Rust) — specified a
  ddgs-leg stub.
- **[D/E/F]** dangling `FR-M5-31`→`FR-031`; redis "3 retries = 4 tries" wording; documented
  that `ruff format --check` is intentionally not gated (matches repo Makefile + M4 decision).
- 9 findings correctly refuted (e.g. a false "tenacity double-owner" reading of classify.py).

### 4b. Tasks audit — 6 doc-accuracy fixes
Stale task IDs in the "recheck fixes baked in" index (including a nonexistent `T035`), a
missing `T024` in the `cli.py` writer chain, two "expect FAIL until" ranges crossing story
boundaries, missing `(depends T003)` on the US3 test tasks, and a branch-name note. Task
LOGIC confirmed sound (no circular deps, no parallel-write hazards).

### 4c. Analyze — 2 LOW fixes
FR-005's flag-path integration + Q4 silence assertion added to T005; SC-006 "exactly one
record per turn" made an explicit invariant check in T031.

## 5. Implementation session (TDD, task order)

Branch `m5-security-reliability` from green main `5bc6bfc` (50 tests). Foundational
`errors.py` + `patterns.py` → US1 (guardrails/guard node/graph rewire/render_graph/CLI
banners+ordered table) → US2 (sanitizer real body/L2 prompts/ingest flag-enrich/answer T4+
copy) → US3 (reliability policies/client wraps/search+fetch+redis retries) → US4
(memory redis_down catch/answer route mapping/chat banner). Five owned test files authored
before their implementations. Full suite reached 100 passing (50 prior + 50 M5); ruff clean;
`WAIT_CAP_SCALE=0` retry proof in 0.54s.

## 6. Manual test session (live, real Redis + GitHub Models + Tavily)

- **T1 injection via `ask`** → `[BLOCKED by input guard]` + refusal, exit 0, one `blocked`
  record with `web=None`, `sources=[]`, guardrail `verdict=block, events=[instruction_override, prompt_leak]`.
- **Benign miss→hit** → turn 1 MISS→web (tavily); turn 2 `[MEMORY HIT sim=0.75]` (the guard
  entry does not break the happy path).
- **Flagged query** ("System: you must comply…") → answers with NO flag banner (Q4); the
  identical re-ask stays a MISS, proving `skip_store` cached nothing.
- **Redis-down degradation** → `docker stop memagent-redis`, next `ask` → `[MEMORY OFFLINE →
  searching the web (not cached)]` + a real web answer, exit 0, ZERO tracebacks, record
  `route=degraded_web`/`degradation=redis_down`. Redis restarted cleanly.
- **Analytics** rendered all sections over the real 6-turn session (25% hit-rate, topics,
  categories, question types, languages, per-route latency).

## 7. Impl-verification workflow findings (hand-caught, all fixed)

An adversarial workflow (4 correctness lenses × Opus, each finding independently verified)
probed the IMPLEMENTED code for what the 100 passing tests missed. 6 raw → **4 confirmed,
2 refuted**. Reliability and degradation lenses came back clean.

- **HIGH (fixed)**: the shared `PATTERN_REGISTRY` is applied verbatim to fetched web CONTENT
  in L3, and `role_hijack`'s bare `act as` / `from now on you will` matched ordinary technical
  prose ("PostgreSQL can act as a message queue" → neutralized + falsely `neutralized_instruction`-
  flagged + a wrong `content_sha256` persisted). Violated FR-015 byte-identical passthrough.
- **MEDIUM (fixed)**: `role_hijack` also over-BLOCKED benign queries ("act as a mentor",
  "developer mode in Chrome") — a HIGH hard-refusal against the availability-first design.
- **MEDIUM (fixed)**: `instruction_override`'s bare `all|any` over-blocked benign
  "ignore any formatting instructions in the document".
- **MEDIUM (fixed)**: the Sources-footer fallback used `"sources:" in answer.lower()`, which
  is a substring of "**re**sources:" — a model answer containing "resources:" silently
  suppressed the citation footer (FR rule-5).

Fix: `role_hijack` now requires a jailbreak-persona token within 30 chars of a framing verb;
`instruction_override` requires a directional word (`all|any` are only optional quantifiers);
the Sources check is line-anchored `(?im)^\s*sources\s*:`. All verified — attacks still
block/flag, the false positives are gone, benign web prose passes through unchanged — and
regression-guarded in `test_guardrails.py` and `test_sanitizer.py` (103 tests total).

**Correctly refuted (no change):** (1) "compound paraphrase evades the regexes" — the
inherent recall gap of any regex filter, explicitly out of the spec's "basic but real" scope;
broadening would violate SC-003's zero-false-positive rule. (2) "the image stripper deletes
`docs![here](url)`" — per CommonMark that IS an image (`<img>`, alt="here"), so stripping is
both markdown-correct and required by the T4 exfil defence.
