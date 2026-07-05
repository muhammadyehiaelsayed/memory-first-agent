# Milestone 1 — Prompt Log (part of the complete instruction record)

> Chronological record of the instructions that produced Milestone 1. Appended as the
> milestone was built (2026-07-05) — never retroactively. Planning-phase prompts (the
> assignment framing, plan design, milestone-spec authoring) are summarized in
> `AI_USAGE.md` §4 and recorded in the planning workspace; from M1 onward every
> milestone's instructions are logged here verbatim.

## 2026-07-05 — Spec Kit flow for Milestone 1

1. **Constitution**: "run /speckit-constitution using the constitution block from
   specs/README.md and also consider that you look into all md files in whole project
   folder start from root folder epam" → constitution v1.0.0 ratified (9 principles).
2. **Specify**: "/speckit-specify for Milestone 1, feeding it
   specs/milestone-1-scaffold-and-memory-schema.md" → feature
   `001-m1-scaffold-memory-schema`, 19 FRs, 4 user stories, 16/16 quality checklist.
3. **Clarify**: "/speckit-clarify" — three questions asked, user answers:
   - Q1 repo layout → **A**: deliverable is `epam/memory-first-agent/`, its own git repo.
   - Q2 license → **A**: MIT.
   - Q3 CI verifiability → **C**: public GitHub repo + live green CI inside M1's DoD.
4. **Plan**: "/speckit-plan" → plan.md (11/11 constitution gates PASS), research.md
   (10 decisions), data-model.md, 3 contracts, quickstart.md.
5. **Tasks**: "/speckit-tasks" → 22 tasks across 7 phases (US1–US4).
6. **Analyze**: "/speckit-analyze" → 5 findings (1 HIGH ordering issue: `.env.example`
   needed before US1's `make setup`); user: "yes apply the fixes" → tasks renumbered,
   generator moved to the foundational phase.
7. **Implement**: "/speckit-implement" → T001–T022 executed; this repository.

## Verification records (T014, FR-M1-17)

`scripts/verify_redisvl.py` output against the locked environment (redisvl **0.23.0**):

```
redisvl version: 0.23.0
  [OK] SearchIndex.load(..., ttl=...)
       (found in redisvl.redis.utils)
  [OK] array_to_buffer
  [OK] query.VectorQuery
```

All three M2-required signatures present — the EXPIRE-pipeline fallback is NOT needed.

Additional live observations recorded for M2:
- `FT.INFO web_memory` reports prefix `chunk` (redisvl passes the bare prefix to
  FT.CREATE); generated keys are `chunk:<id>` — no double-colon issue; `doc:*` meta keys
  remain outside the index as designed.
- redis-down behavior: `redis.asyncio` raises `redis.exceptions.ConnectionError` (not the
  builtin `ConnectionError`) — the CLI catches the redis-py exceptions explicitly.

## Corrections during implementation

- `cli.py` exception handling hand-corrected after the live redis-down test printed a
  traceback wall instead of the contracted one-line error (fixed; re-verified: readable
  line + exit 1 + clean recovery).
- Design docs' "33 Settings fields" corrected to the true count of **32**.
