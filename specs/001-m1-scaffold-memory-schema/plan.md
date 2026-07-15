# Implementation Plan: Milestone 1 — Repo Scaffold, Toolchain & Memory Index Schema

**Branch**: `001-m1-scaffold-memory-schema` | **Date**: 2026-07-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-m1-scaffold-memory-schema/spec.md`

**Source documents**: `specs/milestone-1-scaffold-and-memory-schema.md` §3/4/6/10 (technical
HOW — authoritative for this plan), `PLAN.md` (project-authoritative on any conflict),
`.specify/memory/constitution.md` v1.0.0.

## Summary

Stand up the deliverable repository `epam/memory-first-agent/` (new git repo, published public
on GitHub with a green CI run — Clarifications 2026-07-05): pinned Python 3.12 + uv toolchain,
importable `src/memagent/` package skeleton, Typer CLI with `wipe-memory` functional and three
stubs, a single-source `Settings` class generating `.env.example`, Makefile + docker-compose
(redis:8.2 + RedisInsight), zero-secret CI (ruff → smoke test, coverage report no gate), the
AI-usage disclosure scaffold with the milestone-1 prompt log, and the full 11-field
`web_memory` FLAT/cosine/float32/1536 index schema with idempotent create/wipe wired
end-to-end. Nothing answers questions yet; this fixes the contracts every later milestone
loads (Settings, schema, CLI surface, delivery harness shape).

## Technical Context

**Language/Version**: Python 3.12 (`requires-python = ">=3.12,<3.14"`, pinned via `.python-version`)

**Primary Dependencies**: All 14 runtime pins land in `pyproject.toml` now (verbatim PLAN §10.1);
M1 actively exercises `redisvl>=0.22,<0.24`, `redis>=6.2,<7`, `typer>=0.16`, `pydantic>=2.11`,
`pydantic-settings`; build backend `hatchling` (spec-note default); dev group `pytest~=8.4`,
`pytest-asyncio>=1,<2`, `respx~=0.23`, `ruff`, `pytest-cov`

**Storage**: Redis 8 (`redis:8.2` image, AOF, healthcheck) — vector index `web_memory`, HASH
storage, prefix `chunk:`, FLAT cosine float32 1536 dims; RedisInsight sidecar on :5540

**Testing**: pytest (`asyncio_mode = "auto"`, markers `integration`/`e2e`); M1 owns exactly one
smoke test (`tests/unit/test_smoke.py`) — must not grow into M2's owned test files

**Target Platform**: macOS/Linux dev machines; `ubuntu-latest` CI; Docker Desktop with
compose v2

**Project Type**: Single CLI project (src layout) — the assignment deliverable repo

**Performance Goals**: SC-001 — clean machine to running foundation in ≤5 commands / <10 min;
`docker compose up -d --wait` blocks until Redis answers PING

**Constraints**: zero-key paths for install/lint/test/wipe (FR-018); `.env.example` generation
byte-identical to committed file (FR-008); `docker compose` v2 spelling only; CI references no
secrets; all numbers live in `Settings` only (Constitution P-III)

**Scale/Scope**: 19 functional requirements, ~30 files, one working command (`wipe-memory`);
index sized for demo scale (hundreds–thousands of vectors; HNSW documented as the >100k path)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| P-I Memory-first routing is code | No routing exists in M1; nothing delegates routing to an LLM. The schema fixes the geometry that makes deterministic routing provable in M2. | PASS |
| P-II One conversion site | M1 fixes `cosine` metric + 1536 dims; **no** distance→similarity conversion appears anywhere in M1 code (reserved for M2 `memory/store.py`). | PASS |
| P-III Single owner per concern | `Settings` is the sole home of every number (FR-007); `.env.example` generated from it (FR-008); no retry code exists (tenacity arrives M5); `Route`/state types deferred to M2. | PASS |
| P-IV JSONL single source of truth | `turn_log_path` setting exists; no turn logging yet; no Redis mirror introduced. | PASS |
| P-V Sanitize before store | No ingestion in M1; the schema carries `sanitizer_flags` + `content_sha256` fields that make the M5 defense storable. | PASS |
| P-VI Scope discipline | Only FR-M1-01…19; anti-churn honored: no salvage env var, no coverage gate, no `GUARD_LLM_CHECK`, no mirror config. Stub commands print "wired in Mx" and nothing more. | PASS |
| P-VII AI_USAGE per milestone | `AI_USAGE.md` headings + `docs/ai_prompts/milestone-1.md` are FR-012 and part of this milestone's DoD. | PASS |
| P-VIII Zero-key testability | `OPENAI_API_KEY` optional (FR-018); smoke test + lint + wipe run keyless; CI has zero secrets. | PASS |
| P-IX Evidence-based decisions | redisvl signature verification script (FR-017) is an M1 duty; pins carry verification dates from PLAN §14. | PASS |
| Technology constraints | Exact match: redis:8.2, redisvl>=0.22,<0.24, uv, Typer, 14 pins, dropped deps absent (explicit acceptance check). | PASS |
| Workflow gates | First milestone (nothing consumed); test ownership respected (smoke only); seams left as importable stubs for M2–M5. | PASS |

**Post-Phase-1 re-check (2026-07-05)**: design artifacts introduce no new violations — the
data model contains no conversion logic, contracts keep `Settings` single-source, quickstart
uses only documented commands. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-m1-scaffold-memory-schema/
├── spec.md              # Feature spec (+ Clarifications session 2026-07-05)
├── plan.md              # This file
├── research.md          # Phase 0 — decisions, rationale, alternatives
├── data-model.md        # Phase 1 — Settings, index schema, CLI surface, harness
├── quickstart.md        # Phase 1 — validation guide (commands + expected outcomes)
├── contracts/
│   ├── schema-module.md # memory/schema.py function contracts
│   ├── cli.md           # memagent CLI command contract
│   └── delivery-harness.md # pyproject/Makefile/compose/CI/.env.example contracts
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

Repo root is **`epam/memory-first-agent/`** (new git repository — Clarifications 2026-07-05;
the surrounding `epam/` planning workspace is not part of the deliverable). M1 creates:

```text
memory-first-agent/
├── README.md  AI_USAGE.md  DECISIONS.md  LICENSE (MIT)  .gitignore
├── .env.example  .python-version  pyproject.toml  uv.lock  Makefile  docker-compose.yml
├── .github/workflows/ci.yml
├── docs/
│   └── ai_prompts/milestone-1.md
├── scripts/
│   ├── gen_env_example.py     # Settings → .env.example (byte-identical, FR-008)
│   └── verify_redisvl.py      # M1 verification duty (FR-017)
├── src/memagent/
│   ├── __init__.py  __main__.py
│   ├── cli.py                 # 4 subcommands; wipe-memory functional (FR-006)
│   ├── config.py              # Settings — THE source of every number (FR-007)
│   ├── state.py  graph.py  routers.py  interfaces.py  resources.py  app.py   # stubs → M2
│   ├── nodes/__init__.py      # stubs → M2/M3
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── schema.py          # REAL M1 logic (FR-014/015/016)
│   │   └── store.py  chunking.py  urls.py    # stubs → M2
│   ├── web/  __init__.py  search.py  fetch.py  to_markdown.py    # stubs → M3
│   ├── llm/  __init__.py  clients.py  prompts.py                 # stubs → M2/M4/M5
│   ├── security/  __init__.py  patterns.py  guardrails.py  sanitizer.py  # stubs → M3/M5
│   ├── analytics/  __init__.py  turnlog.py  classify.py  report.py       # stubs → M4
│   └── utils/  __init__.py  reliability.py  errors.py  timing.py         # stubs → M5
└── tests/
    └── unit/test_smoke.py     # M1-owned smoke test (FR-011 green CI)
```

**Structure Decision**: single-project src layout exactly as PLAN §10.2; stub modules exist
only to import cleanly (Constitution: replacing a stub must not change its call sites). The
planning workspace (`epam/specs/`, `.specify/`, PLAN.md) intentionally stays outside the repo.

## Complexity Tracking

> No Constitution Check violations — table intentionally empty.
