# Milestone 9 — Executable BDD scenarios for every function (appended 2026-07-06)

A post-v1.2 AI-assisted pass. The user asked for full BDD coverage: every Python file and
every function under its own Gherkin scenario, derived from the main functionality, mined
from the planning specs' existing scenarios, executable and passing — with zero changes to
source code. Tooling: Claude Code (Fable 5 orchestrator + Opus 4.8 authoring subagents +
Fable 5 verification subagents), dynamic workflows. Result: seven phase-scoped commits (BDD
M1–M6 scope + traceability gate/docs), each independently full-suite green, tagged `v1.3` and
merged `--no-ff` to main as part of the final-polish merge.

## 1. Instructions (user-issued, verbatim)

1. "i want to have full bdd senarios for each funtionalty in this agent make sure that each
   python file and each funtion inside has it is own BDD senario drived from the main senario
   which is defined in main funtianlity you can scan all md files to extract this senarios
   make sure you use workflows and the orcastrator shold be on fable modeles and the sub
   agents can use opus 4.8 make sure all BDD at the end is working and make sure you don't
   change the code of files i need at the end that each pthon method shloud be under BDD
   senarios"
2. "before you commit i want to double check again uisng workflows all agents use fable 5
   make sure that all funtionalty works and BDD works as well"
3. AskUserQuestion → **"Full land + tag v1.3"**

## 2. What was built (new files only; zero source changes)

- `tests/bdd/features/` — 45 Gherkin feature files: `00_main_functionality.feature` (the
  root feature: one scenario per `Route` literal — `memory_hit`, `memory_miss_web_search`,
  `degraded_web`, `blocked`, `failed` — plus the one-JSONL-record-per-turn invariant),
  one feature file per Python module (43), and `99_traceability.feature`. 210 scenarios;
  every module feature declares its parent root scenario in a `# Derived from:` header, and
  105 scenarios adapt Gherkin from `specs/milestone-*.md` with `# source:` credits.
- `tests/bdd/test_bdd_*.py` — 18 pytest-bdd binding files (215 pytest items, all passing;
  keyless fakes/respx per the unit-suite conventions; redis-backed scenarios use the
  existing skip-if-unreachable contract).
- `tests/bdd/test_bdd_traceability.py` — the coverage gate: re-derives all 142 module-level
  functions/methods from `src/` + `scripts/` by AST on every run and fails unless each has
  a `# covers: <qualname>` declaration, bidirectionally (typos and stale entries fail too);
  zero-function modules with top-level behavior need `# covers-module:`.
- `docs/BDD.md` — generated index: run instructions, layout, per-feature table, and the
  full function→scenario traceability matrix.
- Only pre-existing files touched: `pyproject.toml` + `uv.lock` (added `pytest-bdd>=8.1.0`
  as a dev dependency so the scenarios execute as plain pytest items in CI).

## 3. Authoring workflow (`wf_c467c8ac-951`, 32 agents)

Orchestrator (Fable 5) scaffolded the root feature + traceability gate first (the gate was
smoke-tested to fail listing exactly the 142 pending functions), then fanned out 16 Opus 4.8
author agents (one per module batch, each required to run its own binding to green before
returning) pipelined into 16 independent Opus 4.8 adversarial verifiers hunting vacuous
steps, behavior-vs-code mismatches, and illegal edits. All 16 batches passed audit on the
first pass; a repair stage existed but was never needed. Honest findings preserved in the
feature files: the milestone-5 spec's mermaid example differs from LangGraph's real output
(scenarios assert the real strings), and `interfaces.py` Protocol contracts are exercised
via a conforming in-memory stand-in while live Redis behavior is owned by the store feature.

## 4. Pre-commit verification workflow (`wf_41004307-98e`, 13 Fable 5 agents)

Per instruction 2 — a different model family than the authors, so genuinely fresh eyes:

- **Functionality**: full suite 362 passed / 0 failed / 0 skipped (redis-backed tests ran);
  ruff check + format clean; `eval_lifecycle --mock` PASS (3/3 miss→hit); graph render
  byte-idempotent; CLI smoke; a live-key e2e through the real CLI (wipe → miss with 51
  chunks ingested → hit at sim 0.755 → analytics → L1 guard blocked an injection probe with
  zero LLM calls).
- **BDD is not vacuous**: gate self-test (deleting a covers line and adding a ghost entry
  each fail the gate naming the exact function; byte-identical restore) plus mutation
  testing — six real regressions injected into `src/` one at a time (exclusive threshold,
  inverted similarity, sanitizer skipping HIGH severity, broken URL canonicalization,
  zeroed `chunks_ingested`, dead search fallback): **6/6 caught** by the BDD scenarios with
  on-point assertions, every mutant restored via `git checkout` and re-greened.
- One environment note from the live run: the GitHub Models dev alias transiently returned a
  near-orthogonal embedding on one turn (hit landed on the retry at 0.755); stored vectors
  and the threshold math were verified correct — provider flakiness, not code.

## 5. Judgement notes

- Comment-based `# covers:` declarations were chosen over Gherkin tags: pytest-bdd maps tags
  to pytest markers, and dotted qualnames make invalid marker names.
- The traceability gate is itself a BDD scenario, and it was mutation-tested like everything
  else — the coverage claim is enforced, not asserted.
