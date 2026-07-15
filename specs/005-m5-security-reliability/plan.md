# Implementation Plan: Milestone 5 — Guardrails (L1/L2/L3) and Reliability

**Branch**: `005-m5-security-reliability` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-m5-security-reliability/spec.md`

## Summary

Turn the working happy-path agent into a defended, resilient one by filling the seams M2–M4
left open — with **no new dependencies and no call-site changes**. Three security layers
(L1 input screen, L2 hardened prompt bodies, L3 real sanitizer sharing L1's pattern
registry) plus a single-owner tenacity retry policy per dependency, four typed errors, and
a fully wired degradation matrix. The plan-phase repo probe (research R0) found several
source-spec "M5 adds X" items already shipped (broad node catches, `sanitizer_flags` +
`content_sha256` persistence, fetch skip-rules, the embed-failure route), shrinking the
node work to targeted deltas and shifting three FRs to test-only. Approach fixed in
`research.md` (D1–D15), typed in `data-model.md`, contracted in four `contracts/*.md`,
validated by `quickstart.md`.

## Technical Context

**Language/Version**: Python 3.12 (`>=3.12,<3.14`), `uv` + committed `uv.lock`.

**Primary Dependencies**: no new ones (Constitution locks 14 runtime deps). M5 uses
`tenacity~=9.1` (retry owner), `redis 6.4` native `Retry`, raw `httpx>=0.28`,
`structlog~=26.1`; stdlib `re`/`unicodedata` for L1/L3; dev `respx~=0.23`, `pytest`.
Live-verified surfaces in research (openai 2.44.0 exceptions, tenacity/redis/respx APIs).

**Storage**: Redis 8 (`redis:8.2`) via redisvl; **no schema change** — `sanitizer_flags`
and `content_sha256` fields already exist and are already persisted by `memory/store.py`.

**Testing**: pytest; five M5-owned unit files (four constitution-listed + new
`test_reliability.py`, D13); zero real keys, no live network; `WAIT_CAP_SCALE=0` drives
retries through the production path.

**Target Platform**: local CLI (macOS/Linux); dockerized Redis for the live demo.

**Project Type**: single project (`src/memagent/`, Typer CLI).

**Performance Goals**: not latency-bound; the reliability budget is correctness — bounded
attempts (LLM 4 / search 3 / fetch 2 / redis 3) with jittered, cap-scaled backoff.

**Constraints**: fail-open guard (availability > strictness); never retry auth errors;
sanitize strictly between markdown and chunking (T3); every turn logged exactly once incl.
blocked/degraded/failed; `AsyncOpenAI(max_retries=0)` mandatory; pipe-clean stdout.

**Scale/Scope**: ~6 new/edited source files + 5 test files + 1 render script; single-user
tool, per-turn stateless graph.

## Constitution Check

*GATE: must pass before Phase 0 and re-checked after Phase 1 design.*

| Principle | Gate | Verdict |
|---|---|---|
| I. Memory-first routing is code | M5 adds no routing logic; `route_after_guard`/`route_after_memory` stay pure, threshold untouched | ✅ PASS |
| II. One conversion site | `distance_to_similarity` untouched; M5 doesn't compare against the threshold (risk #8) | ✅ PASS |
| III. Single owner per concern | tenacity retry lives ONLY in `reliability.py`, applied only in client wrappers; **analytics client deliberately not wrapped** so classify keeps its own M4 policy (D3); redis uses native `Retry` (not a 2nd tenacity layer); `timed()` remains the single latency owner (new `guard` stage); base64/marker/banners are code constants (D15) | ✅ PASS |
| IV. JSONL single source of truth | blocked/degraded/failed all produce exactly one TurnRecord; no Redis mirror | ✅ PASS |
| V. Sanitize before store | L3 real body swaps in at the frozen `ingest_content` call-site (sanitize between markdown and chunking); flags + sha256 persisted and re-attached on hit (already wired); neutralize-not-delete | ✅ PASS |
| VI. Scope discipline | anti-churn cuts restated in the spec Assumptions and NOT added (canary, defang allowlist, GUARD_LLM_CHECK, 2-hit drop, salvage route, embed→web route, log mirror); only spec FRs planned | ✅ PASS |
| VII. AI_USAGE per milestone | `docs/ai_prompts/milestone-5.md` + AI_USAGE rows in the task list (FR-030), never retroactive | ✅ PASS |
| VIII. Zero-key testability | all five test files keyless + no network; `render_graph.py` builds resources with `Settings(_env_file=None)` and `None` clients; `WAIT_CAP_SCALE=0` prod-path retries | ✅ PASS |
| IX. Evidence-based, honest | every library surface live-verified 2026-07-05 in-venv (research); source-spec deltas documented not silently followed; DoD greps corrected to the real mermaid literals (D2) | ✅ PASS |

**Initial gate: PASS** (no violations; Complexity Tracking empty).

### Post-Design re-check (after Phase 1)

Design holds all nine. Three source-spec statements were corrected against repo reality —
recorded here so `/speckit-tasks` and review treat them as intentional, not drift:

1. **Graph-render command & mermaid literals** — the source DoD greps `START --> guard_input`
   / `guard_input -->|block| log_turn` and names `scripts/render_graph.py`. Live langgraph
   1.2.7 emits `__start__ --> guard_input;` and unlabeled dotted `guard_input -.-> log_turn;`,
   and that script does not exist. Plan adds the keyless script and asserts the real
   literals (D2). No principle affected (IX satisfied by verifying).
2. **"M5 adds try/except to the nodes"** — only `memory_search` lacks a catch; the other
   five nodes already catch (M2–M4). Plan narrows node work to `memory_search` (typed,
   narrow) + `answer_from_web` route/degradation mapping + T4 strip, and lets typed errors
   flow through the existing broad catches (research #2). Preserves III (no duplicate
   error handling).
3. **`content_sha256` / `sanitizer_flags` persistence "added by M5"** — already persisted
   by `store.py` (research #3); FR-M5-14/T-M5-08 become test-only. No code change, so V
   stays satisfied by the existing wiring.

Two additive edits worth stating so they are not misread as scope creep or a Principle-V
conflict:
- `TurnResult` gains `degradation: str | None = None` (NamedTuple default — existing
  unpackers unaffected) so `ask` can render the memory-offline banner (D11). Not a
  state/record/schema field; does not touch M2-owned types.
- `nodes/ingest.py` gets one additive line — enriching each output doc with
  `"sanitizer_flags": flags` (D10) — so web-fetched-page provenance reaches
  `wrap_context`. This does **not** violate Principle V's "frozen `ingest_content`
  call-site": V freezes the `sanitize()` invocation between markdown and chunking (the T3
  ordering), which is untouched; the doc-enrichment is an output-shaping additive write,
  owned and tested via `contracts/prompts-l2.md`. Without it, a freshly-fetched
  neutralized page would render `sanitizer_flags: []` in its L2 header (FR-009 gap on the
  web path).

**Post-design gate: PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/005-m5-security-reliability/
├── plan.md              # this file
├── spec.md              # /speckit-specify + /speckit-clarify (4 clarifications)
├── research.md          # Phase 0 — R0 repo probe + D1–D15 + live lib verifications
├── data-model.md        # Phase 1 — new types, value-flow rules, degradation table
├── contracts/
│   ├── security-guardrails.md   # patterns, L1 guard, L3 sanitizer, T4 strip
│   ├── prompts-l2.md            # build_system_prompt + wrap_context bodies
│   ├── reliability.md           # errors, retry policies, client wraps, redis retry, degradation
│   └── graph-and-cli.md         # guard wiring, CLI banners/exit codes, render script
├── quickstart.md        # Phase 1 — 7 gates + adapted DoD
└── tasks.md             # /speckit-tasks (NOT created here)
```

### Source Code (repository root: `memory-first-agent/`)

```text
src/memagent/
├── security/
│   ├── patterns.py        # FILL — Severity, Pattern, PATTERN_REGISTRY, max_severity
│   ├── guardrails.py      # FILL — GuardResult, screen_input
│   └── sanitizer.py       # REPLACE BODY — real L3 + strip_markdown_images (sig frozen)
├── utils/
│   ├── errors.py          # FILL — 4 typed errors + redis_down_in_chain (moved from cli)
│   ├── reliability.py     # FILL — llm_retry / tavily_retry / fetch_retry factories
│   └── timing.py          # (unchanged; tolerates the new "guard" stage)
├── nodes/
│   ├── guard.py           # NEW — make_guard_input, BLOCKED_REFUSAL
│   ├── memory.py          # EDIT — catch MemoryUnavailableError → redis_down degrade
│   ├── ingest.py          # EDIT (additive) — enrich each output doc with "sanitizer_flags": flags (D10); sanitize() call-site FROZEN
│   └── answer.py          # EDIT — answer_from_web route/degradation map (D9) + copy doc sanitizer_flags into source dicts (D10); T4 strip both nodes
├── llm/
│   ├── prompts.py         # FINALIZE BODIES — L2 hardening (signatures frozen)
│   └── clients.py         # EDIT — optional retrying wrap on seams; analytics client unwrapped
├── web/
│   ├── search.py          # EDIT — tavily_retry on POST; explicit httpx timeout; fallback raises typed
│   └── fetch.py           # EDIT — fetch_retry on _fetch_one (deadline stays outside)
├── memory/
│   └── store.py           # EDIT — make_redis_client(native Retry); typed translation in knn/store/is_fresh
├── graph.py               # EDIT — add guard_input node, move entry point, wire route_after_guard
├── app.py                 # EDIT — make_redis_client; TurnResult.degradation
└── cli.py                 # EDIT — BLOCKED/MEMORY_OFFLINE banners, exit codes; import redis_down_in_chain

scripts/
└── render_graph.py        # NEW — keyless mermaid dump for the DoD grep + README

tests/unit/                # five M5-owned files (Ruling A + D13)
├── test_guardrails.py     # L1, wiring, L2, T1 block, httpx guard, T4 output
├── test_sanitizer.py      # L3 strip/flag/neutralize/benign/poisoned-page
├── test_search_retry.py   # respx: 429×2→200, 401→fallback, 503 exhaustion
├── test_fetch_retry.py    # respx: timeout-retry, 404/oversize/non-HTML skip, non-fatal
└── test_reliability.py    # NEW — OpenAI policy, WAIT_CAP_SCALE=0, redis Retry, degradation matrix
```

**Structure Decision**: single project, existing `src/memagent/` layout. M5 fills five
placeholder modules, replaces one stub body, adds one node + one script, and edits eight
wiring files — every edit at a pre-existing seam, no call-site moved (Rulings A–G).

## Complexity Tracking

No constitution violations — table intentionally empty.
