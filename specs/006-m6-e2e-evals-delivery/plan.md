# Implementation Plan: Milestone 6 — Integration/E2E Tests, Eval Harnesses, CI Green, Docs, v1.0

**Branch**: `006-m6-e2e-evals-delivery` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-m6-e2e-evals-delivery/spec.md`

## Summary

M6 is the **terminal** milestone: it adds **no product behaviour** — it proves M1–M5, packages
it, and ships `v1.0`. The plan-phase repo probe (research R0, seven parallel readers over main
`6a582e4`, 103 tests green) confirmed the shipped interface surface, **resolved** the two
signatures the source spec flagged "unsure" (`PageFetcher.fetch(urls)`, sync
`TurnLogger.log(record)`), and found the deltas that shape the work: `conftest.py` **does not
exist** (M6 creates it; the 12 unit tests keep their local fakes — D1), `tests/integration`/`e2e`
and the CI redis service **don't exist** (M6 adds them — D10/D15), idempotent create is
`ensure_index` not raw `create` (D4), `stored_at` is derived from an epoch the store stamps
itself (D5), the record fields are `similarity_top`/role-keyed `tokens` (D7), the Tavily/fetch
clients are retry-wrapped so respx routes must be 200-only and non-redirecting (D3), and
`temperature=0` on `gpt-5.4-mini` genuinely needs a real key (D14, Clarification Q1). Two
clarifications are locked: `v1.0` tags on the **keyless** path with real-key artifacts marked
"pending real-key capture", and the e2e/eval mock uses **respx** (real HTTP counter). Approach
fixed in `research.md` (R0 + D1–D15 + live verifications), typed in `data-model.md`, contracted
in four `contracts/*.md`, validated by `quickstart.md` (8 gates + DoD); an adversarial recheck
(research R1) then applied 9 code-verified fixes — 2 HIGH: the `Agent(resources)` constructor (the
shipped Agent builds the graph itself) and the full-HTML e2e fetch fixture (a bare `<article>` is
dropped by trafilatura).

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.14`), `uv` + committed `uv.lock` (pip fallback documented).

**Primary Dependencies**: **no new ones**. Test/CI surface uses `pytest~=8.4`,
`pytest-asyncio>=1,<2`, `respx~=0.23`, `pytest-cov`, `ruff`, `coverage` — all pinned since M1/M5
and live-verified (respx 0.23.1, pytest 8.4.2, pytest-asyncio 1.4.0, coverage 7.15.0, langgraph
1.2.7, redisvl 0.23.0, httpx 0.28.1, openai 2.44.0). No product deps added.

**Storage**: Redis 8 (`redis:8.2`) via redisvl — **no schema change**; M6 asserts the existing
FLAT cosine `web_memory` index round-trip. Unit runs are dockerless (skip fixture).

**Testing**: pytest; **three** M6-owned artifacts — `tests/conftest.py`,
`tests/integration/test_redis_store.py`, `tests/e2e/test_lifecycle.py` — plus three scripts
(`eval_lifecycle.py`, `eval_grounding.py`, `capture_demo.py`) and the FR-019 extension of the
existing `render_graph.py`. Unit + both `--mock` evals are keyless; integration/e2e +
`eval_lifecycle --mock` need `redis:8.2`; `WAIT_CAP_SCALE=0` drives retries through the prod path.

**Target Platform**: local CLI + CI (ubuntu-latest); dockerized `redis:8.2` for integration/e2e
and the live demo.

**Project Type**: single project (`src/memagent/`, Typer CLI); M6 touches `tests/`, `scripts/`,
`.github/workflows/`, `docs/`, `README.md`, `AI_USAGE.md`, and applies the one-time D11 `ruff
format .` cosmetic pass that reformats 16 `src/memagent/` files (whitespace only — no
logic/behaviour change; tests stay green). No `src/memagent/` **logic/behaviour** change beyond a
possible logged bug-fix corrective (recheck E).

**Performance Goals**: not latency-bound; the M6 budget is correctness + reproducibility — the
core proof (miss→hit, unchanged web `call_count`) and a green, keyless, single-job CI.

**Constraints**: zero real keys in CI (fakes + respx + `redis:8.2`); coverage is a report, never a
gate; respx routes 200-only + non-redirecting (D3); e2e page query-dominated + >200 chars (D8);
one `TurnRecord` per turn; `v1.0` on the keyless-green commit with real-key artifacts pending
(Clarification Q1). M6 must not rewrite the 12 upstream-owned unit tests (Ruling A).

**Scale/Scope**: 1 conftest + 2 test files + 3 scripts + 1 script-extension + 1 `ci.yml` finalize
+ README/AI_USAGE/DECISIONS/verification docs + a one-time `ruff format` pass + the `v1.0` tag.

## Constitution Check

*GATE: must pass before Phase 0 and re-checked after Phase 1 design.*

| Principle | Gate | Verdict |
|---|---|---|
| I. Memory-first routing is code | M6 adds no routing; the e2e *asserts* the deterministic `route_after_memory` (`>=` inclusive) miss→hit; no LLM/ReAct routing introduced | ✅ PASS |
| II. One conversion site | M6 tests `distance_to_similarity = 1 - d` at the single site (store.py:60) incl. the 0.70 boundary (D6); adds no second conversion | ✅ PASS |
| III. Single owner per concern | reuses the shipped retry owner (`WAIT_CAP_SCALE=0` prod path); no new retry logic; `build_test_resources` is the single test-wiring owner; render stays keyless (D2) | ✅ PASS |
| IV. JSONL single source of truth | e2e reads `turns.jsonl` and asserts exactly one record per turn (2 total); no Redis mirror; asserts the M4 record shape unchanged | ✅ PASS |
| V. Sanitize before store | unchanged; the e2e exercises the real ingest→sanitize→store path; `sanitizer_flags`/`content_sha256` persistence is asserted via the round-trip | ✅ PASS |
| VI. Scope discipline | anti-churn cuts restated in spec Assumptions and NOT added (coverage gate, log mirror, canary/defang, gray-zone guard, 0.50 salvage, embed→web); D11 `ruff format` is cosmetic finalization, not new scope | ✅ PASS |
| VII. AI_USAGE per milestone | FR-022 + DoD: `docs/ai_prompts/milestone-6.md` appended as M6 lands, `AI_USAGE.md` carries "the complete instruction record"; the M6 log is written during, not after | ✅ PASS |
| VIII. Zero-key testability & evaluator-first | unit + both `--mock` evals keyless; CI zero-secret with a `redis:8.2` service; render_graph keyless (D2); the 5-command + zero-key paths are FR-025; `v1.0` on the keyless-green commit | ✅ PASS |
| IX. Evidence-based, honest | every consumed signature probe-verified 2026-07-06; source-spec deltas documented not silently followed (D1–D15); FR-023 dated re-verification; real-key items honestly marked "pending real-key capture" (Clarification Q1) | ✅ PASS |

**Initial gate: PASS** (no violations; Complexity Tracking empty).

### Post-Design re-check (after Phase 1)

Design holds all nine. Source-spec statements corrected against repo reality — recorded so
`/speckit-tasks` and review treat them as intentional, not drift:

1. **conftest "ordering seam"** (source §3) — no upstream test references a central fixture;
   `conftest.py` is absent. M6 **creates** it and leaves the 12 unit files' local fakes untouched
   (D1). Preserves Ruling A (no upstream rewrite) and VIII (keyless).
2. **`render_graph.py` via `build_test_resources()`** (source §6.8) — would make graph-render need
   Redis. M6 keeps render's existing all-`None` keyless build and only adds the marker splice (D2).
   Preserves VIII.
3. **FR-006 "create twice is idempotent"** — redisvl `create(overwrite=False)` raises on an
   existing index; the shipped idempotent primitive is `ensure_index` (exists-guard). Test asserts
   `ensure_index` ×2 (D4). No principle affected (IX by verifying).
4. **FR-008 epoch injection** — `store()` stamps `fetched_at` itself; `stored_at` is derived at the
   knn boundary. Test monkeypatches the store clock for a deterministic epoch (D5). II/IX intact.
5. **FR-012 field names** — record fields are `similarity_top` (← state `top_similarity`) and a
   role-keyed `tokens` block (`{}` unless fakes return usage). Asserted with the real names + fakes
   returning usage (D7). IV intact.
6. **`ruff format` gating** (FR-017) — the repo currently gates `ruff check` only; the reformat was
   deferred to M6. M6 runs `ruff format` once as a separate cosmetic commit and gates both (D11).
   VI intact (cosmetic, not new scope); fallback documented.
7. **`temperature=0` on `gpt-5.4-mini`** — genuinely needs a real key (GitHub Models serves no
   gpt-5.4* ids). Marked "pending real-key capture"; `v1.0` tags on the keyless path (D14,
   Clarification Q1). VIII/IX intact.

**Post-design gate: PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/006-m6-e2e-evals-delivery/
├── plan.md              # this file
├── spec.md              # /speckit-specify + /speckit-clarify (2 clarifications)
├── research.md          # Phase 0 — R0 repo probe + D1–D15 + live lib verifications
├── data-model.md        # Phase 1 — consumed-signature reference, fakes, GroundingVerdict, value-flow
├── contracts/
│   ├── test-fixtures.md      # conftest fixtures + fakes + build_test_resources (FR-001..005)
│   ├── integration-e2e.md    # test_redis_store + test_lifecycle (FR-006..012)
│   ├── eval-harnesses.md     # eval_lifecycle + eval_grounding (FR-013..016)
│   └── ci-docs-release.md    # ci.yml + render_graph ext + capture_demo + README + AI_USAGE + reverify + v1.0 (FR-017..025)
├── quickstart.md        # Phase 1 — 8 gates + adapted DoD
└── tasks.md             # /speckit-tasks (NOT created here)
```

### Source Code (repository root: `memory-first-agent/`)

```text
tests/
├── conftest.py               # NEW (D1) — settings, fake_embedder, fake_llm, redis_url, clean_index,
│                             #   FakeEmbedder, FakeLLM, build_test_resources(), resources/agent fixtures
├── integration/
│   └── test_redis_store.py   # NEW (@integration) — idempotent create (ensure_index), round-trip,
│                             #   monkeypatched-clock metadata, known-vector similarity + 0.70 boundary
├── e2e/
│   └── test_lifecycle.py     # NEW (@e2e) — THE core proof: respx miss→hit, call_count, 2 turn records
└── unit/
    ├── test_m6_fixtures.py   # NEW (keyless, M6-owned) — FR-001/002/003(+004) fixture assertions (audit fix)
    └── (12 EXISTING files)   # UNTOUCHED (Ruling A); keep local fakes

scripts/
├── render_graph.py           # EXTEND (FR-019) — keep keyless build; ADD README + docs/architecture.md marker splice
├── eval_lifecycle.py         # NEW — --mock hard gate (needs redis) + real-key mode (readable no-key error)
├── eval_grounding.py         # NEW (~40–60 lines) — 5–8 cases, nano judge, --mock keyless+redisless, non-gating
└── capture_demo.py           # NEW — real-key live miss→hit -> docs/demo_transcript.md (pending w/o key)

.github/workflows/ci.yml      # FINALIZE (D10) — single job + redis:8.2 + integration/e2e + both eval mocks + coverage report
docs/
├── architecture.md           # rendered mermaid between markers
├── demo_transcript.md         # captured (real key) or "pending real-key capture" placeholder
├── verification-2026-07-06.md # dated §14 re-verification note (temperature=0 pending)
└── ai_prompts/milestone-6.md  # M6 instruction record (appended as M6 lands)
README.md                      # ten verbatim sections + mermaid markers
AI_USAGE.md                    # "the complete instruction record" + M6 rows
DECISIONS.md                   # finalized anti-churn record (verify exists; scaffolded M1)
pyproject.toml                 # (markers already declared; no change unless a pin correction)
```

**Structure Decision**: single project, existing `src/memagent/` layout **unchanged** (M6 proves,
does not build). M6 creates one conftest, two test files, three scripts, two dirs; extends one
script; finalizes CI + docs; runs one cosmetic `ruff format`; tags `v1.0`. Every edit is in
`tests/`/`scripts/`/`docs/`/CI/README — no `src/memagent/` behaviour change (except a logged
bug-fix corrective if a test reveals one).

## Complexity Tracking

No constitution violations — table intentionally empty.
