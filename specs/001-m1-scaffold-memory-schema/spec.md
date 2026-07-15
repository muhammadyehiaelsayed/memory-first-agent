# Feature Specification: Milestone 1 — Repo Scaffold, Toolchain & Memory Index Schema

**Feature Branch**: `001-m1-scaffold-memory-schema`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Milestone 1 — Repo scaffold, toolchain, Redis index schema for the Memory-First Web Agent. Source specification: specs/milestone-1-scaffold-and-memory-schema.md (use its §1 Goal & context, §2 Scope, §5 Functional requirements, §7 BDD acceptance scenarios per that file's §11 Spec Kit mapping; PLAN.md is authoritative on any conflict)."

> **Source of truth**: this spec restates `specs/milestone-1-scaffold-and-memory-schema.md`
> (§1/2/5/7) for the Spec Kit flow. The milestone file's §6 Technical specification feeds
> `/speckit-plan`; its §8/9 feed `/speckit-tasks`. On any conflict, `PLAN.md` wins
> (Constitution, Principle VI).

## Clarifications

### Session 2026-07-05

- Q: Where does the deliverable repository live? → A: Option A — a new `epam/memory-first-agent/`
  subfolder is created as its own git repository and is the deliverable; `epam/` remains the
  planning workspace (spec-kit config, milestone specs, PLAN.md). All repo-relative paths in
  this feature resolve against `epam/memory-first-agent/`.
- Q: Which open-source license for the `LICENSE` file? → A: Option A — MIT.
- Q: When is the GitHub remote established so "CI green on every push" (SC-005) is
  verifiable? → A: Option C — full loop in M1 with a **public** GitHub repository: `git init`,
  first commit, create the public remote, push, and a live green CI run is part of M1's
  Definition of Done.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Evaluator installs and boots the project (Priority: P1)

A reviewer with only Docker, uv (or pip), and Python 3.12 clones the repository and, in five
commands, has a working foundation: dependencies installed, the memory store running, and the
empty `web_memory` vector index created and visible in a browser UI. No paid credential is
needed for any of this.

**Why this priority**: "Deliver a repo only" is the assignment's delivery contract — if the
evaluator cannot install and boot the project friction-free, nothing built in later milestones
is reachable. Every later milestone assumes exactly this foundation.

**Independent Test**: On a clean machine with the prerequisites, run
`make setup && make redis-up && uv run memagent wipe-memory` and open
`http://localhost:5540`. Delivers a verifiable, running foundation with zero keys.

**Acceptance Scenarios**:

1. **Given** a fresh clone and no `.env` file, **When** the user runs `make setup`, **Then**
   dependencies install from the committed lockfile and `uv run memagent --help` exits 0.
2. **Given** setup is complete, **When** the user runs `make redis-up`, **Then** the memory
   store (redis:8.2 with persistence and a healthcheck) and the RedisInsight UI on port 5540
   are running.
3. **Given** the store is up, **When** the user runs `memagent wipe-memory`, **Then** the
   command exits 0 and the empty `web_memory` index is visible in RedisInsight.
4. **Given** the package is installed, **When** the user runs `memagent --help`, **Then**
   exactly four subcommands are listed: `chat`, `ask`, `analytics`, `wipe-memory`.
5. **Given** the stub subcommands (`chat`, `ask`, `analytics`), **When** any is invoked,
   **Then** it exits 0, makes no network call, and clearly states it is not wired yet.

---

### User Story 2 - Developer configures everything from one place (Priority: P2)

A developer joining the project finds every tunable number and environment variable defined in
a single configuration source with documented defaults. The example environment file is
generated from that source, so documentation can never drift from code. No credential is
required to import, lint, test, or reset memory.

**Why this priority**: the memory-first contract graded later (threshold 0.7, index dimensions
1536) is only provable if these numbers have one authoritative home before any node logic
exists. Fixing configuration later would force an index rebuild and threshold re-tune.

**Independent Test**: Construct the configuration object with no `.env` present and assert the
documented defaults; regenerate `.env.example` and confirm zero drift.

**Acceptance Scenarios**:

1. **Given** no `.env` file, **When** `Settings()` is constructed, **Then** it succeeds with
   the documented defaults (spot checks: `similarity_threshold == 0.7`,
   `embedding_dim == 1536`, `memory_index_name == "web_memory"`,
   `memory_ttl_seconds == 604800`, `chunk_size_chars == 1600`).
2. **Given** the environment sets `SIMILARITY_THRESHOLD=0.85`, **When** `Settings()` is
   constructed, **Then** `similarity_threshold` is exactly 0.85.
3. **Given** `OPENAI_API_KEY` is unset, **When** the package is imported or `Settings()` is
   constructed, **Then** no error is raised and the key field is empty (keyless paths work).
4. **Given** the committed `.env.example`, **When** the generator script is re-run, **Then**
   the file is unchanged (no git diff) and every settings field appears in it.
5. **Given** an unknown environment variable, **When** `Settings()` is constructed, **Then**
   it is ignored (no attribute leaks in).

---

### User Story 3 - Memory index foundation is defined once and wipeable (Priority: P3)

The vector index that the whole product routes on is fully defined — name, key prefix, all 11
attributes, exact vector geometry (FLAT, cosine, float32, 1536 dims) — and can be created and
reset idempotently from the CLI. A dimension-contract guard exists so a future embedding-model
change fails fast with an actionable message instead of corrupting search results.

**Why this priority**: later milestones only load and query this index; its schema is the one
thing that cannot be cheaply changed later (changing dims or metric means rebuild + re-tune).

**Independent Test**: Build the schema from default settings and assert its identity and
field inventory; run `memagent wipe-memory` twice against a running store and confirm both
runs succeed and the index exists, empty.

**Acceptance Scenarios**:

1. **Given** default settings, **When** the schema is built, **Then** it has exactly 11 fields
   (`chunk_text`, `url`, `url_hash`, `title`, `doc_type`, `source_query`, `chunk_index`,
   `fetched_at`, `sanitizer_flags`, `content_sha256`, `embedding`), index name `web_memory`,
   HASH storage, key prefix `chunk:`.
2. **Given** the schema, **When** the `embedding` field is inspected, **Then** it is a vector
   field with algorithm FLAT, distance metric cosine, datatype float32, and 1536 dimensions.
3. **Given** the index already exists, **When** `memagent wipe-memory` runs again, **Then** it
   still exits 0 and the index exists afterwards with zero documents (idempotent).
4. **Given** a mismatched embedder dimension (3072), **When** the dimension contract is
   checked against settings (1536), **Then** it raises an actionable error that mentions
   `wipe-memory`.

---

### User Story 4 - Delivery guardrails exist from day one (Priority: P4)

From the first push, continuous integration runs lint and unit tests with zero secrets, and
the AI-assistance disclosure scaffold exists with the milestone-1 prompt log already appended —
so the "document all instructions" requirement is satisfied continuously, never retroactively.

**Why this priority**: these are compliance artifacts whose value is destroyed by backfilling
(Constitution, Principle VII). They must exist before feature work starts, but they do not
block local development the way P1–P3 do.

**Independent Test**: CI runs green on a push with no repository secrets configured;
`AI_USAGE.md` has its eight headings and `docs/ai_prompts/milestone-1.md` is non-empty.

**Acceptance Scenarios**:

1. **Given** a push to the repository, **When** CI runs, **Then** a single job executes lint
   then unit tests, with pinned actions, Python read from `.python-version`, no secrets
   referenced, and a coverage report (no gate).
2. **Given** the repository root, **When** inspected, **Then** `AI_USAGE.md` contains the
   eight required headings and `docs/ai_prompts/milestone-1.md` exists and is non-empty.
3. **Given** the repository root, **When** inspected, **Then** `LICENSE`, `.gitignore`
   (ignoring `.env`, `.venv/`, `__pycache__/`, `logs/`), and a `README.md` skeleton with the
   zero-keys note and five-command quickstart exist.
4. **Given** the repository root, **When** inspected, **Then** a `DECISIONS.md` scaffold
   exists seeded with the anti-churn list (finalized in M6).

---

### Edge Cases

- `memagent wipe-memory` when the index does not exist yet: creates it (first run) — command
  is idempotent across repeated runs (FR-019).
- `memagent wipe-memory` when the memory store is unreachable: exits non-zero with a readable
  error naming the store URL; it does not hang or print a stack trace wall.
- `OPENAI_API_KEY` entirely unset: import, configuration, lint, tests, and wipe-memory all
  still work (the readable fail-fast key check deliberately lands in M4, not here).
- Unknown environment variables present: ignored, never crash configuration loading.
- Forbidden dependencies (`tavily-python`, `python-ulid`, `fakeredis`, `anthropic`,
  `markdownify`) accidentally reintroduced: caught by an explicit acceptance check on the
  dependency list.
- Stub commands invoked before their milestone (`chat`, `analytics`, `ask`): exit 0 with a
  clear "not wired yet" notice and no side effects, so early exploration never misleads.
- `.env.example` edited by hand: regeneration from settings restores it — the generated file
  is the documentation, code is the source.

## Requirements *(mandatory)*

### Functional Requirements

Traceability: FR-001…FR-019 below map 1:1 to FR-M1-01…FR-M1-19 in
`specs/milestone-1-scaffold-and-memory-schema.md` §5, which carries the full acceptance
criterion for each.

- **FR-001**: The project manifest MUST declare Python `>=3.12,<3.14` and exactly the 14
  pinned runtime dependencies from the plan (source: FR-M1-01).
- **FR-002**: A lockfile MUST be committed and resolve the declared dependencies
  reproducibly (source: FR-M1-02).
- **FR-003**: The repository MUST pin the Python version to 3.12 via `.python-version`
  (source: FR-M1-03).
- **FR-004**: Installing the project MUST expose a `memagent` console command
  (source: FR-M1-04).
- **FR-005**: The full package tree MUST exist with importable module stubs so
  `import memagent` succeeds before any feature logic exists (source: FR-M1-05).
- **FR-006**: The CLI MUST expose exactly four subcommands — `chat`, `ask`, `analytics`,
  `wipe-memory` — three as harmless stubs and `wipe-memory` fully functional
  (source: FR-M1-06).
- **FR-007**: A single configuration source MUST hold every environment variable with its
  exact documented default (source: FR-M1-07).
- **FR-008**: The example environment file MUST be generated from the configuration source so
  it can never drift (source: FR-M1-08).
- **FR-009**: The Makefile MUST provide the ten named targets, all `.PHONY`, using
  `docker compose` v2 spelling only (source: FR-M1-09).
- **FR-010**: The compose file MUST run the pinned memory store (redis:8.2) with persistence
  and a healthcheck, plus the RedisInsight UI on port 5540 (source: FR-M1-10).
- **FR-011**: CI MUST be a single zero-secret job — lint, then unit tests — with pinned
  actions, Python from `.python-version`, and a coverage report without a gate
  (source: FR-M1-11).
- **FR-012**: The AI-usage disclosure file MUST carry its eight headings and the chronological
  prompt-log directory MUST contain a non-empty milestone-1 entry (source: FR-M1-12).
- **FR-013**: `LICENSE` (MIT, per Clarifications 2026-07-05), `.gitignore`, a README
  skeleton with the zero-keys note and five-command quickstart, and a `DECISIONS.md`
  scaffold seeded with the anti-churn rulings (finalized in M6) MUST exist
  (source: FR-M1-13 + milestone §2 scope).
- **FR-014**: The memory index schema MUST define index `web_memory`, prefix `chunk:`, HASH
  storage, all 11 fields, and a FLAT/cosine/float32/1536 vector field (source: FR-M1-14).
- **FR-015**: Index create/wipe MUST be wired end-to-end so `memagent wipe-memory` drops and
  recreates the index against a running store (source: FR-M1-15).
- **FR-016**: A dimension-contract helper MUST raise an actionable error (mentioning
  `wipe-memory`) when the embedder dimension differs from the index dimension
  (source: FR-M1-16).
- **FR-017**: A verification script MUST confirm the vector-store client signatures used by
  later milestones, documenting the fallback if one is absent (source: FR-M1-17).
- **FR-018**: The paid API key MUST be optional at this stage so keyless install, lint, test,
  and reset paths all work (source: FR-M1-18).
- **FR-019**: `memagent wipe-memory` MUST be idempotent — repeated runs succeed and leave an
  existing, empty index (source: FR-M1-19).

### Key Entities

- **Settings (configuration source)**: the single authoritative home of every tunable number
  and environment name (threshold, dimensions, index name, TTL, chunk sizes, timeouts…); all
  other components read from it, none define their own numbers.
- **Memory index (`web_memory`)**: the vector index every later milestone loads and queries;
  identity (name, prefix, storage form), 11 attributes including provenance
  (`sanitizer_flags`, `content_sha256`, `doc_type`), and fixed vector geometry.
- **CLI surface (`memagent`)**: the four-subcommand user interface; in this milestone one
  real capability (memory reset) and three clearly-labeled stubs.
- **Delivery harness**: manifest + lockfile, Makefile, compose file, CI workflow, README
  skeleton, license, ignore rules, decision log scaffold, and the AI-usage disclosure
  scaffold — the shape is fixed here and finalized in M6.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer on a clean machine reaches a running, verifiable foundation (store
  up, index visible in the browser UI) in at most 5 commands and under 10 minutes.
- **SC-002**: 100% of milestone-1 capabilities (install, lint, unit tests, memory reset) work
  with zero paid credentials configured.
- **SC-003**: The memory reset command succeeds on 100% of repeated runs (idempotent), whether
  or not the index already exists.
- **SC-004**: Regenerating the example environment file from the configuration source
  produces zero drift (empty diff), and every configuration field is documented in it.
- **SC-005**: CI completes green on every push with zero repository secrets configured —
  verified by a live green run on the public GitHub repository before this milestone closes
  (per Clarifications 2026-07-05).
- **SC-006**: The AI-assistance disclosure contains a dated milestone-1 entry before any
  milestone-2 work starts (append-as-you-go, never retroactive).

## Assumptions

- External prerequisites are present: Docker with compose v2, uv (pip fallback documented),
  and Python 3.12 — these are the milestone's only dependencies (first milestone; nothing is
  consumed from prior work).
- The deliverable lives in `epam/memory-first-agent/`, created in this milestone as its own
  git repository (per Clarifications, Session 2026-07-05); the surrounding `epam/` folder is
  the planning workspace and is not part of the deliverable. CI and committed-lockfile checks
  apply to the `memory-first-agent/` repo.
- The repo is published to a **public** GitHub repository during this milestone (git init →
  first commit → push), and a live green CI run closes the milestone; GitHub CLI or web
  access to the user's GitHub account is available for repo creation.
- `specs/milestone-1-scaffold-and-memory-schema.md` §6 carries the full technical detail
  (exact pins, schema field table, Makefile recipes, CI YAML shape) and is the direct input
  to `/speckit-plan`; this spec deliberately stays at the capability level.
- The stack named here (Redis 8, uv, Typer, redisvl) is locked by the project constitution's
  Technology & Architecture Constraints — naming it in this spec is traceability, not an open
  design choice.
- No `[NEEDS CLARIFICATION]` markers: the source milestone spec defines every requirement
  with an explicit acceptance criterion, and `PLAN.md` resolves conflicts by rule.
