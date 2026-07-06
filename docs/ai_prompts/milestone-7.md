# Milestone 7 — Test-coverage hardening (appended 2026-07-06)

A post-v1.0 AI-assisted pass, not one of the six planned milestones. After v1.0 shipped, the
user asked for an end-to-end audit of the whole project; it surfaced test-coverage gaps (never
functional bugs), which were then closed. Tooling: Claude Code (Opus 4.8) orchestrating dynamic
subagent workflows. Result: tag `v1.1` (main `8472b11`), 114 → 144 tests, coverage 76% → 84%.

## 1. Instructions (user-issued, verbatim)

1. "use workflows to test all project all milestones end to end make sure that every thing
   works if you find any thing let me know first before you fix it"
2. (after the audit report) AskUserQuestion → **"All 18 + drop dead constant"** (full hardening)
3. AskUserQuestion → **"Full land + tag v1.1"** (commit → push → CI green → merge → tag)

## 2. Audit (report-first, no fixes until approved)

A dynamic workflow (`wu8s2ktp9`, 25 agents) audited each shipped milestone M1–M6 spec-vs-code:
6 read-only per-milestone auditors, then an independent skeptical verifier per finding
(default REFUTED unless a concrete reproduction was proven). Ground truth was established first
by the orchestrator running the full CI recipe locally against a live `redis:8.2` (114 tests
green, both `--mock` evals exit 0, render idempotent).

**Result: the product code was correct end-to-end — zero functional bugs.** The audit found
**18 confirmed test-coverage gaps** (12 MEDIUM + 6 LOW): load-bearing behaviors implemented
correctly but asserted by no test (or by a vacuous/tautological one), so a regression would
have shipped green. One finding was adversarially REFUTED (a `.gitignore` `logs/` "drift" that
the M1 spec's own acceptance criteria deliberately accept via a substring grep).

Highest-value gaps: the `filter_urls` SSRF/private-IP guard had zero coverage; the default
keyless `DdgsSearcher` field mapping was only ever monkeypatched away; two `@unit` scenarios
the specs explicitly mandated (`.env.example` anti-drift, `aggregate()` hit-rate) were never
written; two existing tests were vacuous (an 87-char "short doc" below the chunk floor asserted
`0 <= 1`; the redis-skip test rebuilt the socket probe inline and never invoked the fixture).

## 3. Fixes (all 18) + the dead constant

8 new unit test files (`test_url_filter`, `test_search_provider`, `test_ingest`, `test_report`,
`test_clients`, `test_m1_contracts`, `test_answer_context`, `test_timing`); edits fixing the
vacuous short-doc test + adding the overlap-invariant test, the redirect final-URL test, the
`is_fresh` 24h boundary test, and a rewrite of the tautological redis-skip test (conftest.py
extracted `probe_redis_or_skip` so the skip path is genuinely exercised). Removed the dead
`_LLM_FAST_FAIL_STATUS` constant (never read; LLM retry/fast-fail is governed solely by
`_LLM_RETRYABLE`) — no runtime behavior change.

## 4. Verification

Every new test was **mutation-verified 14/14**: the exact regression each gap named was
injected into the source, the guarding test was confirmed to FAIL, then reverted — proving no
new test is itself vacuous. 144 tests pass (138 unit + 6 integration/e2e vs live `redis:8.2`);
coverage 76% → 84% (report.py 0→96%, schema.py 43→96%, web/fetch.py filter_urls →99%,
timing.py →100%); ruff clean; both eval harnesses exit 0. Landed on branch `m7-test-hardening`,
branch CI green, merged `--no-ff` to main (`8472b11`), tagged `v1.1`, main CI green.
