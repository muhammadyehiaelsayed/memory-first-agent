# Phase 0 Research: Milestone 1 — Repo Scaffold, Toolchain & Memory Index Schema

**Date**: 2026-07-05 · **Plan**: [plan.md](plan.md)

No `NEEDS CLARIFICATION` markers remained after `/speckit-clarify` (session 2026-07-05).
This file consolidates (a) the three clarification decisions and (b) the already-verified
technology research inherited from `PLAN.md` §14 / `DECISIONS.md` (each verified against
official sources on the date shown). One open verification is deliberately deferred to
runtime by design: FR-017's `scripts/verify_redisvl.py` (a task, not plan-time research).

## Decisions

### D1. Repository layout — deliverable is `epam/memory-first-agent/`
- **Decision**: create `memory-first-agent/` inside `epam/` as its own git repository; the
  `epam/` folder remains the planning workspace (spec-kit config, milestone specs, PLAN.md).
- **Rationale**: matches PLAN §10.2's canonical tree root exactly; keeps the evaluator's
  deliverable free of planning-workspace noise; disclosure content (AI_USAGE, prompt logs,
  MODEL_CHOICES.md, DECISIONS.md) is *copied into* the deliverable where the plan places it.
- **Alternatives considered**: `epam/` itself as the repo (ships planning noise, root name
  mismatch); a separate sibling folder (breaks spec-kit path resolution rooted at `epam/`).
- **Source**: spec Clarifications, Q1 → A.

### D2. License — MIT
- **Decision**: `LICENSE` = MIT.
- **Rationale**: conventional default for take-home/demo repos; permissive, universally
  recognized, zero evaluator friction; the milestone file's §6.11 spec-note already proposed
  MIT as the default.
- **Alternatives considered**: Apache-2.0 (more formal, patent grant — unneeded here);
  no-license/proprietary (hostile to an evaluator who must run the code).
- **Source**: spec Clarifications, Q2 → A.

### D3. GitHub remote — public repo + green CI inside M1's DoD
- **Decision**: `git init` → first commit → create a **public** GitHub repository → push;
  a live green CI run closes the milestone (SC-005 verified live, not deferred).
- **Rationale**: CI failures surface while the repo is tiny; every later milestone inherits a
  working push-and-verify loop; matches "every milestone ends submittable".
- **Alternatives considered**: local-only until later (SC-005 unverifiable); private repo
  (works identically for CI; user chose public — flip anytime with
  `gh repo edit --visibility private` if EPAM asks for confidentiality).
- **Source**: spec Clarifications, Q3 → C.

### D4. Redis runtime — `redis:8.2` image (query engine in core)
- **Decision**: `redis:8.2` with AOF + healthcheck; RedisInsight sidecar on :5540.
- **Rationale**: Redis 8 ships FT.* vector search in core; redis-stack is EOL Dec 2025 —
  using it would look stale. `--wait` + healthcheck gives a deterministic `make redis-up`.
- **Alternatives considered**: `redis/redis-stack-server:latest` (EOL; documented last-resort
  fallback only); external/hosted Redis (breaks the zero-key local demo).
- **Source**: PLAN §4.1/§14 (verified 2026-07-04); DECISIONS.md "Redis image".

### D5. Vector index client — `redisvl>=0.22,<0.24`, schema via `IndexSchema.from_dict`
- **Decision**: declare the 11-field schema with redisvl; `prefix="chunk"` +
  `key_separator=":"` (never `prefix="chunk:"` — the double-colon trap); wipe via
  `create(overwrite=True, drop=True)` with the `delete(drop=True)` + `create()` fallback.
- **Rationale**: removes ~50–100 lines of hand-written FT.CREATE/byte-packing; 0.23.0 is
  current stable (PyPI, 2026-07-04). Exact signatures (`load(ttl=)`, `array_to_buffer`,
  `VectorQuery`) are runtime-verified by `scripts/verify_redisvl.py` (FR-017) because they
  are needed by M2, and M1 is the cheapest place to catch drift.
- **Alternatives considered**: raw redis-py FT.* (verbose, error-prone); langchain-redis
  (wraps redisvl, adds weight).
- **Source**: PLAN §10.1/§14; DECISIONS.md "Vector store client".

### D6. Index geometry — FLAT / cosine / float32 / 1536, fixed in M1
- **Decision**: geometry is fixed here and guarded by `assert_index_dims` (defined M1, wired
  into `build_resources()` in M2).
- **Rationale**: exact KNN keeps the 0.70 routing deterministic and provable; changing dims
  later means an index rebuild + threshold re-tune, so the contract is fixed before any node
  logic exists. HNSW is the documented >100k-vector growth path.
- **Alternatives considered**: HNSW now (approximate — could flip a boundary case);
  3072-dim `text-embedding-3-large` (6.5× cost, rebuild — documented env upgrade only).
- **Source**: PLAN §0/§4.2/§4.3; DECISIONS.md "Index type".

### D7. Toolchain — uv + hatchling + src layout + Typer
- **Decision**: uv with a committed `uv.lock` (pip fallback documented in README); build
  backend `hatchling` targeting `src/memagent`; Typer CLI via `[project.scripts]`.
- **Rationale**: fast, reproducible installs for the evaluator; hatchling is the minimal
  src-layout backend (spec-note default — PLAN doesn't name one); Typer's 4-subcommand
  surface pairs with pydantic/rich already in the stack.
- **Alternatives considered**: Poetry (slower, no gain); setuptools (more boilerplate);
  argparse/click (more wiring for the same four commands).
- **Source**: PLAN §10.1; DECISIONS.md "uv / Typer"; milestone §6.1 spec-note.

### D8. Configuration — pydantic-settings with lowercase fields, `extra="ignore"`
- **Decision**: one `Settings(BaseSettings)` with every §10.3 env var as a lowercase field
  matched case-insensitively; keys optional (empty-string defaults) so keyless paths run;
  `.env.example` generated by `scripts/gen_env_example.py` with a fixed per-field template
  (placeholder + inline comment), byte-identical to the committed file.
- **Rationale**: single source of every number (Constitution P-III); generation makes doc
  drift structurally impossible (FR-008's `git diff --exit-code`); the fail-fast key check
  deliberately lands in M4's client construction, not here, or `make test`/`wipe` would break.
- **Alternatives considered**: hand-maintained `.env.example` (drifts); `python-dotenv` + os
  environ (loses typing/defaults); failing fast on missing key at import (breaks keyless CI).
- **Source**: milestone §6.3/§6.4 (incl. the naive-generator warning); PLAN §10.3.

### D9. CI shape — single zero-secret job, pinned major-tag actions
- **Decision**: `actions/checkout@v4`, `astral-sh/setup-uv@v6`, `actions/setup-python@v5`
  with `python-version-file: .python-version`; `uv sync` → `ruff check` → pytest unit run
  with `--cov=memagent --cov-report=term` (report, never a gate).
- **Rationale**: tested == shipped (Python from the same pin file); zero secrets keeps forks
  and the evaluator's clone green; M6 extends this same job with the redis:8.2 service and
  mock evals rather than replacing it.
- **Alternatives considered**: SHA-pinned actions (more secure, noisier updates — major tags
  chosen per PLAN hygiene ruling); coverage gate (explicitly anti-churn).
- **Source**: milestone §6.10; PLAN §10.1/§12.

### D10. Compose file — no top-level `version:` key
- **Decision**: modern compose v2 file; AOF via `--appendonly yes`; healthcheck
  `redis-cli ping` (2s interval) so `up -d --wait` blocks until ready.
- **Rationale**: `version:` is obsolete under compose v2; `--wait` + healthcheck makes
  `make redis-up` deterministic for SC-001.
- **Alternatives considered**: hyphenated `docker-compose` v1 spelling (EOL — forbidden by
  FR-009's acceptance check).
- **Source**: milestone §6.7; PLAN hygiene rulings.

## Best-practice notes applied

- **Stub discipline**: package-skeleton stubs contain only what imports cleanly — no logic,
  no TODO-implementation bodies that could mislead (Constitution: replacing a stub must not
  change call sites).
- **Smoke-test boundary**: `tests/unit/test_smoke.py` asserts import + `Settings()` defaults +
  11-field schema and MUST NOT grow into routing/similarity/chunker tests (M2-owned files).
- **Idempotent wipe**: `wipe-memory` succeeds whether or not the index exists (FR-019) —
  first-run UX and the dims-change recovery path are the same code.
