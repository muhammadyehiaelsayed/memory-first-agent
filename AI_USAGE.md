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
| Module stubs (`state.py`, `web/`, `llm/`, …) | AI-generated | docstring-only; filled in M2–M5 |

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

`docs/ai_prompts/milestone-1.md` — the chronological instruction record for Milestone 1,
labelled as part of the complete instruction record. One file per milestone is appended as
that milestone is built.

## 6. What was reviewed, tested, and corrected by hand

- Live failure test caught that `redis.asyncio` raises `redis.exceptions.ConnectionError`
  (not the builtin) — the CLI's readable-error contract failed on first run and was corrected,
  then re-verified (one-line error, exit 1, clean recovery).
- `FT.INFO` observation: redisvl registers the FT.CREATE prefix as `chunk` (bare, without the
  separator); keys are still `chunk:<id>` and the `doc:*` meta prefix stays un-indexed — the
  double-colon trap the plan warned about is confirmed avoided.
- Field-count truth-check: `Settings` has 32 fields (design docs briefly claimed 33; corrected).
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
