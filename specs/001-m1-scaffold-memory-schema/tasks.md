# Tasks: Milestone 1 — Repo Scaffold, Toolchain & Memory Index Schema

**Input**: Design documents from `/specs/001-m1-scaffold-memory-schema/`

**Prerequisites**: plan.md, spec.md (4 user stories), research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the source milestone spec explicitly names `tests/unit/test_smoke.py` as an M1 deliverable (Constitution: tests are NOT optional where a spec names them). No other test files may be created here (M2/M4/M5/M6 own them).

**Organization**: Tasks grouped by user story (US1–US4 from spec.md). Every file path is relative to the deliverable repo root **`~/Desktop/epam/memory-first-agent/`** (Clarifications 2026-07-05); `T-M1-XX` references map back to the milestone file's §8 breakdown.

> Analysis remediation 2026-07-05 (`/speckit-analyze` I1): the `.env.example` generator moved
> from the US2 phase into Phase 2 Foundational — US1's `make setup` recipe copies
> `.env.example → .env`, so the file must exist before the US1 checkpoint. US2's phase now
> validates the configuration behavior it consumes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 (evaluator installs & boots, P1), US2 (single-source config, P2), US3 (index contracts, P3), US4 (delivery guardrails, P4)

## Phase 1: Setup (project initialization)

- [X] T001 Create the deliverable repo root `memory-first-agent/` inside `~/Desktop/epam/`, run `git init`, and write `.gitignore` covering at least `.env .venv/ __pycache__/ *.pyc logs/ .pytest_cache/ .ruff_cache/ .coverage dist/ build/ *.egg-info/` (contracts/delivery-harness.md; part of FR-M1-13)
- [X] T002 Write `pyproject.toml` (project `memagent` 0.1.0, `requires-python = ">=3.12,<3.14"`, the exact 14 runtime pins, dev group of 5, `[project.scripts] memagent = "memagent.cli:app"`, hatchling targeting `src/memagent`, pytest `asyncio_mode="auto"` + `integration`/`e2e` markers, ruff py312/line-length 100) and `.python-version` containing `3.12` — verbatim per milestone §6.1/§6.2 (T-M1-01; FR-M1-01/03/04)
- [X] T003 Run `uv sync`, verify resolution, commit `uv.lock`; confirm `uv sync --locked` exits 0 and the 5 forbidden packages (`tavily-python`, `python-ulid`, `fakeredis`, `anthropic`, `markdownify`) are absent from `pyproject.toml` (T-M1-02; FR-M1-02)
- [X] T004 Create the full `src/memagent/` tree with importable stubs per plan.md structure: `__init__.py`, `__main__.py`, and empty-but-importable `state.py graph.py routers.py interfaces.py resources.py app.py`, `nodes/__init__.py`, `memory/{__init__,store,chunking,urls}.py`, `web/{__init__,search,fetch,to_markdown}.py`, `llm/{__init__,clients,prompts}.py`, `security/{__init__,patterns,guardrails,sanitizer}.py`, `analytics/{__init__,turnlog,classify,report}.py`, `utils/{__init__,reliability,errors,timing}.py` — stubs contain only what imports cleanly, no placeholder logic (T-M1-05 part; FR-M1-05)

**Checkpoint**: `uv run python -c "import memagent"` exits 0.

## Phase 2: Foundational (blocking prerequisites for ALL user stories)

- [X] T005 Write `src/memagent/config.py` — pydantic-settings `Settings` with **all 32 fields and exact defaults** from data-model.md Entity 1 (`env_file=".env"`, `case_sensitive=False`, `extra="ignore"`); keys optional (`openai_api_key=""`, `openai_base_url=None`, `tavily_api_key=""`) so keyless paths run; no fail-fast key check (that is M4's job) (T-M1-03; FR-M1-07/18)
- [X] T006 Write `scripts/gen_env_example.py` — iterate `Settings.model_fields` in declaration order with the fixed per-field template (`ENV_NAME=<placeholder>` + inline comment); secret-shaped placeholders `OPENAI_API_KEY=sk-...`, `OPENAI_BASE_URL=` (blank, never `None`), `TAVILY_API_KEY=` (blank); all other fields emit exact defaults; run it and commit the generated `.env.example` (32 keys, matching milestone §6.4 verbatim) — foundational because US1's `make setup` copies this file (T-M1-04; FR-M1-08) — depends on T005

**Checkpoint**: `uv run python -c "from memagent.config import Settings; Settings()"` exits 0 with `OPENAI_API_KEY` unset; `.env.example` committed.

## Phase 3: User Story 1 — Evaluator installs and boots the project (P1) 🎯 MVP

**Goal**: `make setup && make redis-up && memagent wipe-memory` works end-to-end; RedisInsight shows the empty `web_memory` index; four subcommands present.

**Independent Test**: quickstart.md §1–§2 on a clean machine, zero keys.

- [X] T007 [P] [US1] Write `src/memagent/memory/schema.py` — `build_schema()` (11 fields verbatim from contracts/schema-module.md; `prefix="chunk"` + `key_separator=":"`, NEVER `prefix="chunk:"`; vector FLAT/cosine/float32/`settings.embedding_dim`), `get_index()`, `ensure_index()` (create-if-missing, never drops), `wipe_index()` (`create(overwrite=True, drop=True)`, fallback `delete(drop=True)`+`create()`) (T-M1-06 part; FR-M1-14)
- [X] T008 [US1] Write `src/memagent/cli.py` — Typer app with exactly four subcommands per contracts/cli.md: `wipe-memory` functional (async Redis client from `Settings.redis_url` → `get_index` → `wipe_index` → echo confirmation; non-zero readable one-line error when Redis is down), `ask`/`chat`/`analytics` as "wired in Mx" stubs with no side effects (T-M1-05/07; FR-M1-06/15) — depends on T004, T005, T007
- [X] T009 [P] [US1] Write `docker-compose.yml` — no `version:` key; `redis` service image `redis:8.2`, `--appendonly yes`, port 6379, named volume, healthcheck `redis-cli ping` (2s/3s/10 retries); `redisinsight` service on `5540:5540` with `depends_on: service_healthy` — verbatim milestone §6.7 (T-M1-08; FR-M1-10)
- [X] T010 [P] [US1] Write `Makefile` — `.PHONY` targets `setup redis-up redis-down run ask analytics wipe test test-integration lint demo`, tab-indented recipes verbatim from milestone §6.8, `docker compose` v2 spelling only (T-M1-09; FR-M1-09) — depends on T004 (recipes call `memagent`)
- [X] T011 [US1] Checkpoint run: `make setup && make redis-up && uv run memagent wipe-memory` all exit 0 (`make setup` copies the T006 `.env.example` → `.env`); `http://localhost:5540` shows empty `web_memory`; `docker exec memagent-redis redis-cli FT.INFO web_memory` shows prefix `chunk:` (single colon — the double-colon trap check); `memagent --help` lists exactly the four subcommands; stubs exit 0 with no side effects (quickstart §1–§2; FR-M1-15 + demoable outcome) — depends on T006–T010

**Checkpoint**: US1 fully functional on its own — this is the milestone's demoable outcome (PLAN §13 M1 row).

## Phase 4: User Story 2 — Developer configures everything from one place (P2)

**Goal**: configuration behavior proven — defaults, overrides, keyless paths, and byte-identical regeneration of the Foundational-phase `.env.example`.

**Independent Test**: quickstart.md §3.

- [X] T012 [US2] Validate configuration behavior per quickstart §3: defaults spot-check (`similarity_threshold==0.7`, `embedding_dim==1536`, `memory_index_name=="web_memory"`, `memory_ttl_seconds==604800`), `SIMILARITY_THRESHOLD=0.85` override, keyless construction, unknown-env-var ignored, and `python scripts/gen_env_example.py && git diff --exit-code .env.example` (regeneration is a no-op) (FR-M1-07/08/18 acceptance) — depends on T005, T006

**Checkpoint**: docs cannot drift from code; every configuration edge case from the spec holds.

## Phase 5: User Story 3 — Memory index foundation defined once and wipeable (P3)

**Goal**: dimension contract enforced; redisvl signatures verified; wipe idempotent and failure-readable.

**Independent Test**: quickstart.md §4.

- [X] T013 [US3] Add `assert_index_dims(embedder_dim, settings)` to `src/memagent/memory/schema.py` — raises `ValueError` naming both dims, `EMBEDDING_MODEL`/`EMBEDDING_DIM`, and `memagent wipe-memory` when dims mismatch; defined here, wired in M2's `build_resources()` (T-M1-06 part; FR-M1-16) — depends on T007 (same file)
- [X] T014 [P] [US3] Write and run `scripts/verify_redisvl.py` — print presence/absence of `SearchIndex.load(..., ttl=)`, `array_to_buffer`, `VectorQuery`; print the EXPIRE-pipeline fallback instruction if `load(ttl=)` is absent; record the output by **creating or appending** `docs/ai_prompts/milestone-1.md` (T016 later formalizes the file — appending here is fine and matches Constitution P-VII's append-as-you-go rule) (T-M1-13; FR-M1-17) — depends on T003
- [X] T015 [US3] Validate index lifecycle per quickstart §4: `wipe-memory` twice in a row both exit 0 and `redis-cli FT._LIST` shows `web_memory` exactly once; `docker compose stop redis` → `wipe-memory` exits non-zero with a readable one-line error (no traceback wall) → `start redis`; `assert_index_dims(1536,...)` silent and `assert_index_dims(3072,...)` raises mentioning `wipe-memory` (FR-M1-16/19 acceptance) — depends on T008, T013

**Checkpoint**: the index contract every later milestone loads is locked and proven.

## Phase 6: User Story 4 — Delivery guardrails exist from day one (P4)

**Goal**: zero-secret CI green on the public GitHub repo; AI-usage disclosure scaffolded with the milestone-1 entry; repo hygiene files present.

**Independent Test**: quickstart.md §5.

- [X] T016 [P] [US4] Write `AI_USAGE.md` with the eight §6.9 headings verbatim (`# AI Usage` + `## 1. Tools used` … `## 8. Judgement notes`) and create-or-formalize `docs/ai_prompts/milestone-1.md` seeded with this milestone's prompt log so far (T014 may already have appended the redisvl verification record) (T-M1-11; FR-M1-12)
- [X] T017 [P] [US4] Write `LICENSE` (MIT — Clarifications 2026-07-05), `README.md` skeleton carrying the §10.4 quickstart verbatim (zero-keys note; one key + Docker; clone → install uv → `make setup` → `make redis-up` → `make run`) with placeholder sections stubbed for M6, and `DECISIONS.md` scaffold seeded with the standing anti-churn rulings (T-M1-12; FR-M1-13)
- [X] T018 [P] [US4] Write `tests/unit/test_smoke.py` — asserts exactly: `import memagent` works; `Settings()` defaults (`similarity_threshold==0.7`, `embedding_dim==1536`, `memory_index_name=="web_memory"`); `build_schema(Settings())` has 11 fields; MUST NOT grow into routing/similarity/chunker tests (M2-owned) (T-M1-10 part; CI green prerequisite — pytest exits 5 on empty collection) — depends on T005, T007
- [X] T019 [US4] Write `.github/workflows/ci.yml` — single `test` job on `[push, pull_request]`: `actions/checkout@v4` → `astral-sh/setup-uv@v6` → `actions/setup-python@v5` with `python-version-file: .python-version` → `uv sync` → `uv run ruff check .` → `uv run pytest -m "not integration and not e2e" --cov=memagent --cov-report=term`; no `secrets.*` anywhere; coverage report, no gate (T-M1-10 part; FR-M1-11) — depends on T018
- [X] T020 [US4] Publish and prove: `git add -A && git commit`, `gh repo create memory-first-agent --public --source=. --push`, then `gh run watch` until the single job is green with zero repository secrets (SC-005; Clarifications Q3) — depends on ALL previous tasks

**Checkpoint**: live green CI on the public repo — SC-005 verified, not deferred.

## Phase 7: Polish & Definition of Done sweep

- [X] T021 Run the full milestone §9 DoD checklist from the repo root (every verify command: locked sync, import, help surface, config defaults + keyless, env-example diff, 11-field schema + FLAT/cosine/float32/1536, dimension contract, smoke green, `ruff check .` clean, hygiene greps, Makefile `.PHONY`/no-hyphenated-compose greps, `docker compose config`, idempotent wipe + `FT._LIST`, redisvl verification recorded) and fix anything red — depends on T001–T020
- [X] T022 Append the complete milestone-1 prompt log to `docs/ai_prompts/milestone-1.md` (dated, labelled part of the complete instruction record), reference it from `AI_USAGE.md` §5, commit and push — never retroactive (Constitution P-VII; T-M1-14) — depends on T021

## Dependencies

```
Phase 1 (T001→T002→T003; T004 after T002)
  → Phase 2 (T005 → T006)
    → US1: T007[P], T009[P], T010[P] → T008 → T011
    → US2: T012                       (needs T005, T006)
    → US3: T013 (after T007), T014[P] (after T003) → T015 (after T008, T013)
    → US4: T016[P], T017[P], T018[P] (after T005, T007) → T019 → T020 (after ALL)
      → Polish: T021 → T022
```

Story completion order: US1 → US2 → US3 → US4 (US2 can start any time after Phase 2; US4's
T016/T017 any time after T001 — only T018–T020 have real dependencies).

## Parallel Execution Examples

- **After T006 (Foundational complete)**: T007 (schema.py) ∥ T009 (docker-compose.yml) ∥ T010 (Makefile) ∥ T016 (AI_USAGE.md) ∥ T017 (LICENSE/README/DECISIONS) — five different files, no shared state.
- **After T007**: T013 (same file as T007 — sequential) but T014 (verify_redisvl.py) ∥ T018 (test_smoke.py) run alongside.
- **Not parallel**: T008 waits on T004+T005+T007; T011 waits on T006–T010; T019 waits on T018; T020 waits on everything.

## Implementation Strategy

**MVP first**: Phases 1–3 (T001–T011) alone deliver the milestone's demoable outcome — a
bootable foundation with a working `wipe-memory` and visible index. Stop there and you already
have PLAN §13's M1 demo.

**Incremental delivery**: US2 (config proof), US3 (index contracts), US4 (publish + CI) each
land as an independently verifiable increment; quickstart.md gives the per-story validation
commands. The milestone closes only after T022 (prompt-log append) — the Constitution makes
that a DoD item, not an afterthought.

**Scope guard**: do not create any test file other than `tests/unit/test_smoke.py`, any env
var not in `Settings`, a coverage gate, or anything on the anti-churn list (spec §2
"Deferred by design").
