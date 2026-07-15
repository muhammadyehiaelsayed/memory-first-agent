# Milestone 1 - Repo scaffold, toolchain, Redis index schema

| Estimated effort | Depends on | Enables | PLAN.md sections covered |
|---|---|---|---|
| 3-4 h | Nothing (first milestone); external prerequisites only (Docker, uv/pip, Python 3.12) | M2 (memory path), M3 (web path), M4 (LLM/logging/analytics), M5 (security/reliability), M6 (tests/CI/docs) | 0 (headline decisions), 4.1 (Redis runtime), 4.2 (index schema), 10.1-10.4 (toolchain, tree, .env, README), 11 (AI_USAGE headings), 12 (CI shape), 13 (M1 row), 14 (redis:8.2 + redisvl verification rows) |

---

## 1. Goal & context

This milestone lays the foundation the whole project stands on: a runnable, installable, lint-clean Python repository with the Redis vector index defined and wipeable end-to-end. Nothing here answers a question yet - no LLM calls, no web fetches, no graph execution - but by the end a competent developer can clone the repo, install it in five commands, start Redis, and watch `memagent wipe-memory` create the `web_memory` index that every later milestone loads and queries.

Why this milestone exists first: the memory-first contract the assignment grades (embed the query, vector-search Redis, route on `similarity >= 0.70`) is only provable if the index schema, the dimension contract, and the single `Settings` source of truth exist before any node logic is written. Getting the schema and configuration wrong later means an index rebuild and a re-tune of the threshold, so it is fixed here, once.

Assignment requirements advanced by M1:
- **"Deliver a repo only"** - repo tree, README quickstart, `docker-compose.yml`, CI that runs on every push with zero keys.
- **"Embed the query, vector-search Redis first"** - the `web_memory` FLAT cosine index that this requirement depends on is created and wipeable here (population comes in M2/M3).
- **"Document AI assistance (all instructions)"** - `AI_USAGE.md` with its eight headings and the `docs/ai_prompts/` chronological log are scaffolded, and the per-milestone append rule starts with this milestone.

Demoable outcome (PLAN section 13, M1 row): `make setup && make redis-up && memagent wipe-memory` succeeds, and RedisInsight at `http://localhost:5540` shows the empty `web_memory` index.

---

## 2. Scope

### In scope
- `pyproject.toml` with the verbatim section-10.1 dependency pins (14 runtime + 5 dev) and `requires-python = ">=3.12,<3.14"`; committed `uv.lock`.
- `.python-version` pinned to `3.12`.
- The full `src/memagent/` package tree from section 10.2, created with importable module stubs so `import memagent` and the console entry point both work.
- Typer CLI (`src/memagent/cli.py`) with four subcommands wired through `[project.scripts]`: `chat`, `ask`, `analytics`, `wipe-memory`. Three are stubs; **`wipe-memory` is fully functional end-to-end**.
- `config.py` - a `pydantic-settings` `Settings` class holding **every** env var from section 10.3 with its exact default. This is THE source of every number in the project.
- `.env.example` **generated from `Settings`** (via `scripts/gen_env_example.py`) so docs cannot drift from code.
- `Makefile` with targets `setup redis-up run ask analytics wipe test test-integration lint demo` - all `.PHONY`, all using `docker compose` (v2 spelling).
- `docker-compose.yml`: `redis:8.2` with AOF persistence + healthcheck, plus a RedisInsight sidecar on `:5540`.
- CI skeleton (`.github/workflows/ci.yml`): a single job running ruff then unit tests, pinned GitHub Actions, Python read from `.python-version`, zero real keys, coverage report (no gate).
- `AI_USAGE.md` with the eight section-11 headings; `docs/ai_prompts/` directory with the milestone-1 prompt log.
- `LICENSE`, `.gitignore`, and a `README.md` skeleton carrying the section-10.4 quickstart.
- `DECISIONS.md` scaffold at the repo root (PLAN section 10.2 lists it as a delivered file, and M2/M3/M5/M6 cite its "standing anti-churn rulings"): seed it with the anti-churn list (0.50 salvage route, canary/output-defang, Redis turn-log mirror, coverage gate, `GUARD_LLM_CHECK`, token streaming, deep session memory). **M1 scaffolds it; M6 finalizes it.**
- `memory/schema.py`: the full section-4.2 index schema (all 11 fields incl. `doc_type`, `sanitizer_flags`, `content_sha256`; FLAT cosine float32, 1536 dims; HASH storage; prefix `chunk:`, index name `web_memory`), plus index create/ensure/wipe functions wired so `memagent wipe-memory` works.
- The startup dimension-assertion helper (`embedder.dim == index dims`), defined here and documented as a contract (invoked in M2 once an embedder exists).
- The section-14 M1 verification duty: a throwaway script confirming the `redisvl >=0.22,<0.24` signatures actually used later (`load(..., ttl=)`, `array_to_buffer`, `VectorQuery`), with the EXPIRE-pipeline fallback noted.
- One M1-owned smoke test (`tests/unit/test_smoke.py`) so CI has a green unit run.

### Out of scope (belongs to other milestones)
- **Embeddings client, `ChatLLM` wrapper** - M2 (finalized M4). `llm/clients.py` is a stub here.
- **Chunker (`memory/chunking.py`), store upsert/KNN + similarity conversion (`memory/store.py`), URL canonicalisation (`memory/urls.py`)** - M2.
- **`embed_query` / `memory_search` / `answer_from_memory` nodes, routers, graph wiring, `app.py` facade** - M2.
- **Web search / fetch / trafilatura markdown, `web_search`/`fetch_pages`/`ingest_content`/`answer_from_web` nodes, per-page summaries** - M3.
- **`TurnLogger` JSONL, classifier, `analytics` report, rich REPL banners, `MODEL_CHOICES.md` re-verification** - M4.
- **Security L1/L2/L3 real implementations (`security/*`), `reliability.py` policies, typed errors, degradation** - M5.
- **`tests/conftest.py` fakes, `tests/integration/test_redis_store.py`, `tests/e2e/test_lifecycle.py`, `scripts/eval_lifecycle.py`, `scripts/eval_grounding.py`, `render_graph.py`, `capture_demo.py`, `seed_memory.py`** - M6 (seed script M2).
- **Unit tests `test_routing`/`test_similarity`/`test_chunker`** - M2; `test_classifier_parsing`/`test_turnlog` - M4; `test_sanitizer`/`test_guardrails`/`test_search_retry`/`test_fetch_retry` - M5.

### Deferred by design (anti-churn - do not "helpfully" add during scaffolding)
These are adjacent to M1 because they would touch `config.py` (new env vars) or CI (a coverage gate). All were evaluated twice and rejected; do not add them:
- The `0.50` weak-memory salvage route (no env var, no route).
- Canary token and output URL-defang allowlist (no config, no CI check).
- Redis turn-log mirror (JSONL stays the single source of truth).
- Token streaming and deep session memory.
- CI coverage **gate** (a coverage *report* is emitted; no threshold that fails the build).
- `GUARD_LLM_CHECK` gray-zone classifier env var.

---

## 3. Prerequisites & interfaces consumed

This is the first milestone, so **no interfaces are consumed from prior milestones**. External prerequisites only:

| Prerequisite | Why | Version / note |
|---|---|---|
| Python 3.12 | `requires-python = ">=3.12,<3.14"` | pinned in `.python-version` |
| uv | dependency install + lockfile + `uv run` | pip fallback documented in README |
| Docker + `docker compose` (v2) | runs `redis:8.2` and RedisInsight | v1 `docker-compose` is EOL - never use the hyphenated form |
| `redis:8.2` image | ships the FT.* query engine (vector search) in core | verify FT.* present at M1 (see section 10); fallback `redis/redis-stack-server:latest` (EOL, last resort) |
| `redisvl >=0.22,<0.24` | declares the index schema + create/drop | **must be re-verified at M1** (section 14 duty); `0.23.0` current on PyPI 2026-07-04 |

Seam note (rulings D/E/F/G): later milestones consume M1's `Settings` and `memory/schema.py`. M1 must therefore keep `Settings` as the sole home of every number, keep `OPENAI_API_KEY` **optional** (so keyless test/wipe paths run), and leave clean stub files where M2-M5 attach real logic.

---

## 4. Interfaces provided

Contracts this milestone exposes to later milestones. Temporary stubs are flagged with the milestone that replaces them.

### 4.1 `memagent.config.Settings`
The single source of every tunable number and env name. Later milestones read fields off `Settings` and never hard-code numbers. **Fixed in M1, extended by no one** (new numbers get a field here, never a literal in a node).

### 4.2 `memagent.memory.schema` (real logic in M1)
```python
def build_schema(settings: Settings) -> IndexSchema        # redisvl IndexSchema for web_memory
def get_index(settings: Settings, client) -> AsyncSearchIndex
async def ensure_index(index: AsyncSearchIndex) -> bool     # create if missing, no drop; True if created
async def wipe_index(index: AsyncSearchIndex) -> None       # drop index + data, recreate empty
def assert_index_dims(embedder_dim: int, settings: Settings) -> None  # dimension contract (section 4.4)
```
M2's `memory/store.py` consumes `build_schema`/`get_index`; M2's `build_resources()` calls `assert_index_dims` once at startup.

### 4.3 `memagent.cli` (Typer app)
`app` is the console entry point (`[project.scripts] memagent = "memagent.cli:app"`).
| Command | M1 status | Replaced by |
|---|---|---|
| `wipe-memory` | **functional** (drops + recreates `web_memory`) | not a stub - stays as is |
| `ask "…"` | stub - echoes the query and prints a "not wired yet" notice | M2 (real answer via the graph) |
| `chat` | stub - prints a placeholder banner | M4 (real rich REPL streaming graph updates) |
| `analytics` | stub - prints a placeholder | M4 (real rich report over `turns.jsonl`) |

### 4.4 Dimension contract
`assert_index_dims(embedder_dim, settings)` raises `ValueError` with an actionable message when `embedder_dim != settings.embedding_dim`. Defined in M1; **not called at M1 startup** (no embedder exists yet). M2 wires it into `build_resources()`. Rationale: `EMBEDDING_DIM=1536` is baked into the FLAT index; changing the embedding model changes the dims and requires `wipe-memory`.

### 4.5 The delivery harness
`pyproject.toml` (+ `uv.lock`), `Makefile`, `docker-compose.yml`, `.env.example`, `.github/workflows/ci.yml`, `.gitignore`, `README.md`, `AI_USAGE.md`, `DECISIONS.md`, `docs/ai_prompts/`. M6 finalizes CI (adds the redis:8.2 service + integration/e2e + `--mock` evals), the README (architecture diagram, transcript, limitations), `AI_USAGE.md`, and `DECISIONS.md`. The **shape** is fixed here.

### 4.6 Package skeleton (importable stubs)
The full `src/memagent/` tree exists and imports cleanly. Stub modules (`state.py`, `graph.py`, `routers.py`, `interfaces.py`, `resources.py`, `app.py`, `nodes/`, `memory/store.py`, `memory/chunking.py`, `memory/urls.py`, `web/*`, `llm/*`, `security/*`, `analytics/*`, `utils/*`) contain only what is needed to import without error. They are filled by M2-M5 per the milestone map in section 2.

---

## 5. Functional requirements

Each is one testable statement with an explicit acceptance criterion.

- **FR-M1-01** `pyproject.toml` declares `requires-python = ">=3.12,<3.14"` and lists all 14 runtime dependencies with the exact section-10.1 pins.
  *Accept:* parsing `[project].dependencies` yields exactly the 14 pinned specifiers in section 6.1; `requires-python` equals `>=3.12,<3.14`.
- **FR-M1-02** `uv.lock` is committed and resolves the declared dependencies.
  *Accept:* `git ls-files uv.lock` prints the path; `uv sync --locked` (or `uv lock --check`) exits 0.
- **FR-M1-03** `.python-version` pins `3.12`.
  *Accept:* file contents are `3.12` (optionally with a patch, e.g. `3.12.x`).
- **FR-M1-04** `[project.scripts]` maps `memagent` to `memagent.cli:app`.
  *Accept:* after `uv sync`, `uv run memagent --help` exits 0.
- **FR-M1-05** The `src/memagent/` tree matches section 10.2 and the package imports cleanly.
  *Accept:* `uv run python -c "import memagent"` exits 0; every directory in the tree exists with an `__init__.py` where it is a package.
- **FR-M1-06** The CLI exposes exactly four subcommands - `chat`, `ask`, `analytics`, `wipe-memory` - with `chat`/`ask`/`analytics` as stubs and `wipe-memory` functional.
  *Accept:* `memagent --help` lists the four; `memagent ask "hello"` exits 0 and echoes; `memagent wipe-memory` performs a real index wipe (FR-M1-15).
- **FR-M1-07** `config.py` `Settings` holds every env var from section 10.3, each with its exact default value, loaded from environment or `.env`.
  *Accept:* `Settings()` with no `.env` yields the defaults in section 6.2 (spot-checked: `similarity_threshold == 0.7`, `embedding_dim == 1536`, `memory_index_name == "web_memory"`, `memory_ttl_seconds == 604800`, `chunk_size_chars == 1600`).
- **FR-M1-08** `.env.example` is generated from `Settings` and lists every setting with its default.
  *Accept:* regenerating via `scripts/gen_env_example.py` produces no `git diff`; every `Settings` field name appears in `.env.example`.
- **FR-M1-09** The `Makefile` provides `setup redis-up run ask analytics wipe test test-integration lint demo`, all `.PHONY`, using `docker compose` (v2).
  *Accept:* all ten targets are named after `.PHONY:`; no occurrence of the hyphenated `docker-compose` in recipes.
- **FR-M1-10** `docker-compose.yml` defines `redis:8.2` with AOF + a healthcheck, plus a RedisInsight sidecar published on `5540`.
  *Accept:* `docker compose config` is valid; the redis service image is `redis:8.2` with `--appendonly yes` and a `redis-cli ping` healthcheck; a RedisInsight service publishes `5540:5540`.
- **FR-M1-11** CI is a single job that runs ruff then unit tests, uses pinned actions, reads Python from `.python-version`, and needs zero real keys.
  *Accept:* `ci.yml` has one job; actions are pinned to a major tag (`@vN`); Python comes via `python-version-file: .python-version`; no secret is referenced; coverage is reported not gated.
- **FR-M1-12** `AI_USAGE.md` contains the eight section-11 headings and `docs/ai_prompts/` exists with a milestone-1 entry.
  *Accept:* the eight headings (section 6.9) are present as markdown headers; `docs/ai_prompts/milestone-1.md` exists and is non-empty.
- **FR-M1-13** `LICENSE`, `.gitignore`, and a `README.md` skeleton with the section-10.4 quickstart exist.
  *Accept:* `.gitignore` ignores `.env`, `.venv/`, `__pycache__/`, `logs/`; `README.md` contains the verbatim zero-keys note and the five-command quickstart.
- **FR-M1-14** `memory/schema.py` defines the full section-4.2 index: name `web_memory`, prefix `chunk:`, HASH storage, all 11 fields, `embedding` = FLAT/cosine/float32/1536.
  *Accept:* `build_schema(Settings())` yields a schema with the 11 fields and types in section 6.5; the vector field is FLAT, cosine, float32, 1536 dims.
- **FR-M1-15** Index create/wipe are wired so `memagent wipe-memory` drops and recreates the index end-to-end against a running Redis.
  *Accept:* with `redis:8.2` up, `memagent wipe-memory` exits 0 and `FT._LIST` (or RedisInsight) shows `web_memory`.
- **FR-M1-16** A startup dimension-assertion helper enforces `embedder.dim == index dims`, defined in M1 as a documented contract.
  *Accept:* `assert_index_dims(1536, Settings())` returns without raising; `assert_index_dims(3072, Settings())` raises `ValueError` mentioning `wipe-memory`.
- **FR-M1-17** A throwaway script verifies the `redisvl` signatures used later (`load(..., ttl=)`, `array_to_buffer`, `VectorQuery`), with the EXPIRE-pipeline fallback documented.
  *Accept:* `scripts/verify_redisvl.py` runs and prints which signatures are present; if `load(ttl=)` is absent, the EXPIRE-pipeline fallback is noted in the script output and README.
- **FR-M1-18** `OPENAI_API_KEY` is optional in `Settings` so keyless test, lint, and `wipe-memory` paths run; the readable fail-fast key check lands in **M4's `build_openai_clients`** (where the OpenAI clients are finalised) — M2's thin client construction until then relies on the SDK's own error.
  *Accept:* `Settings()` with `OPENAI_API_KEY` unset succeeds and yields `openai_api_key == ""`; no import path requires the key.
- **FR-M1-19** `memagent wipe-memory` is idempotent - it succeeds whether or not the index already exists.
  *Accept:* running `memagent wipe-memory` twice in a row both exit 0; the index exists afterwards with zero documents.

---

## 6. Technical specification

Everything a developer needs to build M1 without opening PLAN.md. File paths are relative to the repo root `memory-first-agent/`.

### 6.1 `pyproject.toml`
```toml
[project]
name = "memagent"
version = "0.1.0"
description = "Memory-first web agent: answers from Redis vector memory first, falls back to the web."
requires-python = ">=3.12,<3.14"
dependencies = [
    "langgraph>=1.2,<2",
    "langchain-text-splitters",
    "redis>=6.2,<7",
    "redisvl>=0.22,<0.24",
    "httpx>=0.28",
    "tenacity~=9.1",
    "trafilatura>=2.1,<3",
    "ddgs>=9,<10",
    "openai>=2",
    "pydantic>=2.11",
    "pydantic-settings",
    "typer>=0.16",
    "rich>=14",
    "structlog~=26.1",
]

[project.scripts]
memagent = "memagent.cli:app"

[dependency-groups]
dev = [
    "pytest~=8.4",
    "pytest-asyncio>=1,<2",
    "respx~=0.23",
    "ruff",
    "pytest-cov",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/memagent"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: requires a running redis:8.2 (skipped when unreachable)",
    "e2e: full-lifecycle test against real redis",
]

[tool.ruff]
target-version = "py312"
line-length = 100
```
> **Spec note:** PLAN.md pins `langchain-text-splitters`, `pydantic-settings`, `openai` (">=2"), `ruff`, and `pytest-cov` without exact bounds; left unpinned here to match. The build backend (`hatchling`) is not named in PLAN.md; chosen as the minimal src-layout backend (change freely). `pytest-asyncio` "1.x" is expressed as `>=1,<2`.

Deliberately **absent** (do not add): `tavily-python`, `python-ulid`, `fakeredis`, `anthropic`, `markdownify`.

### 6.2 `.python-version`
```
3.12
```

### 6.3 `src/memagent/config.py`
`pydantic-settings` `BaseSettings`; field names lowercase, matched case-insensitively to the UPPERCASE env vars. Every value below is copied verbatim from section 10.3.
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )

    # --- keys (all optional so keyless test/lint/wipe run) ---
    openai_api_key: str = ""            # the ONE required key at runtime (LLMs + embeddings)
    openai_base_url: str | None = None  # optional -> GitHub Models free dev mode
    tavily_api_key: str = ""            # optional -> keyless ddgs fallback

    # --- models ---
    conversation_model: str = "gpt-5.4-mini"
    analytics_model: str = "gpt-5.4-nano"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # --- redis / memory ---
    redis_url: str = "redis://localhost:6379/0"
    memory_index_name: str = "web_memory"
    similarity_threshold: float = 0.7   # inclusive: hit <=> (1 - distance) >= this
    memory_top_k: int = 5
    memory_ttl_seconds: int = 604800    # 7 days; 0 disables
    freshness_window_seconds: int = 86400

    # --- web ---
    search_max_results: int = 8
    fetch_top_n: int = 5
    fetch_concurrency: int = 5
    connect_timeout_s: int = 5
    read_timeout_s: int = 10
    page_deadline_s: int = 20
    fetch_max_bytes: int = 2500000

    # --- llm timing / retries ---
    llm_timeout_s: int = 45
    llm_max_attempts: int = 4
    classify_timeout_s: int = 8

    # --- chunking / context ---
    chunk_size_chars: int = 1600
    chunk_overlap_chars: int = 200
    max_chunks_per_page: int = 25
    web_context_chunks_per_page: int = 2
    history_max_turns: int = 6

    # --- reliability / guard / logging ---
    wait_cap_scale: float = 1.0         # tests set 0 -> instant retries via prod path
    guard_max_query_chars: int = 2000
    log_level: str = "INFO"
    turn_log_path: str = "logs/turns.jsonl"
```
> **Spec note:** PLAN.md's fail-fast rule ("startup fails fast if `OPENAI_API_KEY` is missing") is deliberately **not** enforced in `Settings` at M1 - doing so would break `make test`, `make lint`, and the `wipe-memory` demo, all of which are keyless. The readable `SystemExit` fail-fast lands in **M4's `build_openai_clients`** (client finalisation, M4 §6.2); M2's thin per-client construction until then relies on the OpenAI SDK's own error if the key is empty. Marked as FR-M1-18.

### 6.4 `.env.example` and its generator
`.env.example` is produced by `scripts/gen_env_example.py`, which holds a **fixed per-field line template** - each line is `ENV_NAME=<placeholder value>` followed by its inline comment - and iterates `Settings.model_fields` (in declaration order) so every field is covered and the ordering cannot drift. The emitted placeholder values are deliberately NOT the raw Python defaults for the three secret-shaped fields: `OPENAI_API_KEY` emits the illustrative `sk-...` placeholder, and `OPENAI_BASE_URL`/`TAVILY_API_KEY` emit blank (their Python defaults are `None`/`""`); every non-secret field emits its exact `Settings` default. The generator's output is **byte-identical** to the committed file, so regenerating it produces no `git diff` (FR-M1-08). The committed contents match section 10.3 verbatim:
```bash
OPENAI_API_KEY=sk-...                  # the ONE required key (LLMs + embeddings)
OPENAI_BASE_URL=                       # optional - GitHub Models endpoint + GitHub PAT for free dev
TAVILY_API_KEY=                        # optional - blank = keyless DuckDuckGo fallback
CONVERSATION_MODEL=gpt-5.4-mini        # verified 2026-07-04; gpt-5.4 flagship = zero-code-change fallback
ANALYTICS_MODEL=gpt-5.4-nano
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
REDIS_URL=redis://localhost:6379/0
MEMORY_INDEX_NAME=web_memory
SIMILARITY_THRESHOLD=0.7               # inclusive; hit <=> 1 - distance >= this
MEMORY_TOP_K=5
MEMORY_TTL_SECONDS=604800              # 7d; 0 disables
FRESHNESS_WINDOW_SECONDS=86400
SEARCH_MAX_RESULTS=8
FETCH_TOP_N=5
FETCH_CONCURRENCY=5
CONNECT_TIMEOUT_S=5
READ_TIMEOUT_S=10
PAGE_DEADLINE_S=20
FETCH_MAX_BYTES=2500000
LLM_TIMEOUT_S=45
LLM_MAX_ATTEMPTS=4
CLASSIFY_TIMEOUT_S=8
CHUNK_SIZE_CHARS=1600
CHUNK_OVERLAP_CHARS=200
MAX_CHUNKS_PER_PAGE=25
WEB_CONTEXT_CHUNKS_PER_PAGE=2
HISTORY_MAX_TURNS=6
WAIT_CAP_SCALE=1.0                     # tests set 0 -> instant retries through prod code path
GUARD_MAX_QUERY_CHARS=2000
LOG_LEVEL=INFO
TURN_LOG_PATH=logs/turns.jsonl
```
> **Spec note:** the generator's fixed per-field template - placeholder value plus inline comment - is the single anti-drift mechanism, and its output MUST be byte-identical to the committed `.env.example` (otherwise FR-M1-08's `git diff --exit-code .env.example` fails). Because of that template, a naive "iterate `model_fields`, write `KEY=default`" generator would NOT reproduce this file - it would emit `OPENAI_BASE_URL=None` and drop the comments. The template blanks `OPENAI_BASE_URL` and `TAVILY_API_KEY` (never `None`) and keeps `OPENAI_API_KEY=sk-...` as a visibly non-functional placeholder (not a real key), matching section 10.3 exactly. The generator, the shown block, and the "no git diff" acceptance therefore all agree.

### 6.5 `src/memagent/memory/schema.py`
The full section-4.2 index. Redis COSINE returns *distance*; `similarity = 1 - distance` (M2 concern), but the metric is fixed here as `cosine`.
```python
from redisvl.schema import IndexSchema
from redisvl.index import AsyncSearchIndex
from memagent.config import Settings

def build_schema(settings: Settings) -> IndexSchema:
    return IndexSchema.from_dict({
        "index": {
            "name": settings.memory_index_name,   # "web_memory"
            "prefix": "chunk",                     # key_separator ":" -> Redis PREFIX "chunk:"
            "key_separator": ":",
            "storage_type": "hash",
        },
        "fields": [
            {"name": "chunk_text",      "type": "text"},                       # sanitized markdown
            {"name": "url",             "type": "tag"},                        # canonical URL
            {"name": "url_hash",        "type": "tag"},                        # sha256(canonical)[:16]
            {"name": "title",           "type": "text"},
            {"name": "doc_type",        "type": "tag"},                        # "chunk" | "summary"
            {"name": "source_query",    "type": "text"},
            {"name": "chunk_index",     "type": "numeric"},
            {"name": "fetched_at",      "type": "numeric", "attrs": {"sortable": True}},  # epoch s
            {"name": "sanitizer_flags", "type": "tag",     "attrs": {"separator": ","}},  # csv provenance
            {"name": "content_sha256",  "type": "text"},
            {"name": "embedding",       "type": "vector",  "attrs": {
                "algorithm": "flat",
                "dims": settings.embedding_dim,   # 1536
                "distance_metric": "cosine",
                "datatype": "float32",
            }},
        ],
    })

def get_index(settings: Settings, client) -> AsyncSearchIndex:
    return AsyncSearchIndex(build_schema(settings), redis_client=client)

async def ensure_index(index: AsyncSearchIndex) -> bool:
    """Create the index if missing; never drop data. Returns True if it created it."""
    if await index.exists():
        return False
    await index.create(overwrite=False)
    return True

async def wipe_index(index: AsyncSearchIndex) -> None:
    """Drop the index AND its keys, then recreate it empty (wipe-memory / dims-change recovery)."""
    await index.create(overwrite=True, drop=True)

def assert_index_dims(embedder_dim: int, settings: Settings) -> None:
    if embedder_dim != settings.embedding_dim:
        raise ValueError(
            f"Embedder produces {embedder_dim}-dim vectors but the index is built for "
            f"{settings.embedding_dim} dims. Change EMBEDDING_MODEL/EMBEDDING_DIM together and "
            f"run `memagent wipe-memory` to rebuild the index."
        )
```
Keys the store (M2) will write: `chunk:{url_hash}:{i}` (chunks), `chunk:{url_hash}:summary` (per-page summary - indexed, participates in KNN), and the **non-indexed** meta hash `doc:{url_hash}` (`num_chunks`, `fetched_at`, `url`). Only the `chunk:` prefix is scanned by the index.

> **Spec note - the prefix double-colon trap:** redisvl builds the Redis `PREFIX` as `prefix + key_separator`. Set `prefix="chunk"` with `key_separator=":"` to get PREFIX `chunk:` and keys `chunk:<id>`. Setting `prefix="chunk:"` would yield `chunk::<id>`. This is the single most likely schema mistake; verify with `FT.INFO web_memory` after `wipe-memory`.

> **Spec note - `create()`/`delete()` signature:** `create(overwrite=True, drop=True)` is the single-call wipe under redisvl 0.23.0. If M1 verification (FR-M1-17) shows a different signature, fall back to `await index.delete(drop=True)` then `await index.create(overwrite=False)`.

### 6.6 `src/memagent/cli.py` (Typer app; `wipe-memory` functional, rest stubbed)
```python
import asyncio
import typer
import redis.asyncio as aioredis
from memagent.config import Settings
from memagent.memory.schema import get_index, wipe_index

app = typer.Typer(add_completion=False, help="Memory-first web agent")

@app.command("wipe-memory")
def wipe_memory() -> None:
    """Drop and recreate the Redis vector index (also the dims-change recovery path)."""
    asyncio.run(_wipe())

async def _wipe() -> None:
    settings = Settings()
    client = aioredis.from_url(settings.redis_url)
    try:
        index = get_index(settings, client)
        await wipe_index(index)
        typer.echo(f"Wiped and recreated index '{settings.memory_index_name}'.")
    finally:
        await client.aclose()

@app.command()
def ask(query: str) -> None:
    """Answer a single question (wired in M2)."""
    typer.echo(f"[stub] ask received: {query!r} - answering is wired in M2.")

@app.command()
def chat() -> None:
    """Interactive REPL (wired in M4)."""
    typer.echo("[stub] chat REPL is wired in M4.")

@app.command()
def analytics() -> None:
    """Analytics report over logs/turns.jsonl (wired in M4)."""
    typer.echo("[stub] analytics report is wired in M4.")
```
> **Spec note:** PLAN.md does not specify M1 behavior for the three stub commands; they print a one-line "wired in Mx" notice and exit 0 (change freely). `wipe-memory`'s clean-error behavior when Redis is unreachable is a plain non-zero exit with a readable message in M1; the typed `MemoryUnavailableError` wrapper arrives in M5.

### 6.7 `docker-compose.yml`
```yaml
services:
  redis:
    image: redis:8.2
    container_name: memagent-redis
    command: ["redis-server", "--appendonly", "yes"]
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 3s
      retries: 10
  redisinsight:
    image: redis/redisinsight:latest
    container_name: memagent-redisinsight
    ports:
      - "5540:5540"
    depends_on:
      redis:
        condition: service_healthy
volumes:
  redis-data:
```
No top-level `version:` key (obsolete under compose v2). AOF via `--appendonly yes`; the healthcheck makes `docker compose up -d --wait` block until Redis answers `PING`.

### 6.8 `Makefile`
```makefile
.PHONY: setup redis-up redis-down run ask analytics wipe test test-integration lint demo

setup:
	uv sync
	test -f .env || cp .env.example .env

redis-up:
	docker compose up -d --wait

redis-down:
	docker compose down

run:
	uv run memagent chat

ask:
	uv run memagent ask "$(Q)"

analytics:
	uv run memagent analytics

wipe:
	uv run memagent wipe-memory

test:
	uv run pytest -m "not integration and not e2e"

test-integration:
	uv run pytest -m "integration or e2e"

lint:
	uv run ruff check .

demo:
	uv run memagent chat
```
Recipes are tab-indented. `redis-down` is an extra beyond the required ten (the IMPLEMENTATION_GUIDE M1 step lists it).
> **Spec note:** PLAN.md does not define the `ask` and `demo` recipe bodies. `ask` takes the query via `Q=` (e.g. `make ask Q="what is redis"`); `demo` runs the chat REPL in M1 and is repointed at `scripts/capture_demo.py` in M6 (change freely).

### 6.9 `AI_USAGE.md` (the eight section-11 headings)
```
# AI Usage
## 1. Tools used
## 2. Workflow narrative
## 3. Per-component provenance table
## 4. Curated highlights (3-6 representative prompts)
## 5. Complete prompt log (see docs/ai_prompts/)
## 6. What was reviewed, tested, and corrected by hand
## 7. What was deliberately NOT AI-generated
## 8. Judgement notes
```
`docs/ai_prompts/milestone-1.md` holds this milestone's chronological prompts, labelled as part of the complete instruction record. **Per ruling 12, the per-milestone append is part of this milestone's Definition of Done and every later one - never write it retroactively.**

### 6.10 `.github/workflows/ci.yml`
```yaml
name: ci
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
      - name: Install dependencies
        run: uv sync
      - name: Lint
        run: uv run ruff check .
      - name: Unit tests (coverage report, no gate)
        run: uv run pytest -m "not integration and not e2e" --cov=memagent --cov-report=term
```
Single job; actions pinned to major tags; Python from `.python-version`; no secrets. M6 expands this into the full pipeline (redis:8.2 service container -> integration/e2e -> `eval_lifecycle --mock` + `eval_grounding --mock`).

### 6.11 `.gitignore`, `LICENSE`, `README.md`
`.gitignore` ignores at least: `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `logs/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `dist/`, `build/`, `*.egg-info/`.
`README.md` skeleton carries the section-10.4 quickstart verbatim:
> **Zero keys needed:** `make test` and `python scripts/eval_lifecycle.py --mock` (CI runs exactly these).
> **One key** (`OPENAI_API_KEY`) **+ Docker** for the live demo; `TAVILY_API_KEY` optional (keyless DuckDuckGo fallback).
>
> Quickstart: clone -> install uv -> `make setup` (uv sync + .env) -> `make redis-up` -> `make run`.

Placeholder sections (architecture diagram, design decisions, security & reliability, limitations, demo transcript) are stubbed and filled in M6.
`DECISIONS.md` is scaffolded at the repo root here (PLAN section 10.2 lists it; M2/M3/M5/M6 cite its "standing anti-churn rulings") — seed it with the anti-churn list (0.50 salvage route, canary/output-defang allowlist, Redis turn-log mirror, coverage gate, `GUARD_LLM_CHECK` gray-zone classifier, token streaming, deep session memory) and any key decisions locked so far; **M6 finalizes it**.
> **Spec note:** PLAN.md does not name a licence; default `LICENSE` = MIT (change freely).

### 6.12 `scripts/verify_redisvl.py` (M1 verification duty, section 14)
A throwaway script that imports redisvl and prints whether the signatures used later are present: `SearchIndex.load(..., ttl=...)`, `redisvl.utils.vectorize`/`array_to_buffer`, and `redisvl.query.VectorQuery`. If `load(ttl=)` is absent, the script prints the EXPIRE-pipeline fallback instruction (store then `EXPIRE` per key). Output is captured into `docs/ai_prompts/milestone-1.md` or a short note in the README's "verified at M1" list.

### 6.13 `tests/unit/test_smoke.py` (M1-owned)
A single smoke test so CI's unit run is green before M2 adds real tests. It asserts: `import memagent` works, `Settings()` loads defaults (`similarity_threshold == 0.7`, `embedding_dim == 1536`, `memory_index_name == "web_memory"`), and `build_schema(Settings())` returns a schema with 11 fields. **Must not grow into routing/similarity/chunker tests** - those are M2's owned files.

### 6.14 Exact commands
```bash
uv init                       # once, if starting empty
uv sync                       # install locked deps, create .venv
uv run python scripts/gen_env_example.py   # (re)generate .env.example
uv run python scripts/verify_redisvl.py    # M1 signature verification
make setup                    # uv sync + copy .env.example -> .env
make redis-up                 # docker compose up -d --wait (redis:8.2 + RedisInsight)
uv run memagent wipe-memory   # create/recreate the web_memory index
uv run pytest -m "not integration and not e2e"   # unit run (smoke)
uv run ruff check .           # lint
```

---

## 7. BDD acceptance scenarios

```gherkin
Feature: Dependency pins and Python version
  # covers FR-M1-01, FR-M1-02, FR-M1-03

  @unit
  Scenario: requires-python is bounded to 3.12
    Given the parsed pyproject.toml
    When I read project.requires-python
    Then it equals ">=3.12,<3.14"
    And the file .python-version contains "3.12"

  @unit
  Scenario: exactly the 14 runtime pins are declared
    Given the parsed pyproject.toml
    When I read project.dependencies
    Then it contains "langgraph>=1.2,<2"
    And it contains "redis>=6.2,<7"
    And it contains "redisvl>=0.22,<0.24"
    And it contains "tenacity~=9.1"
    And it contains "trafilatura>=2.1,<3"
    And it contains "ddgs>=9,<10"
    And it contains "structlog~=26.1"
    And there are exactly 14 runtime dependencies

  @unit
  Scenario: forbidden dependencies are absent
    Given the parsed pyproject.toml
    Then no dependency name is "tavily-python"
    And no dependency name is "python-ulid"
    And no dependency name is "fakeredis"
    And no dependency name is "anthropic"
    And no dependency name is "markdownify"

  @manual
  Scenario: the lockfile is committed and resolves
    Given a clean checkout
    When I run "uv sync --locked"
    Then it exits 0
    And "git ls-files uv.lock" prints "uv.lock"

Feature: CLI command surface
  # covers FR-M1-04, FR-M1-05, FR-M1-06; smoke portion in tests/unit/test_smoke.py

  @unit
  Scenario: the package imports cleanly
    When I run "python -c 'import memagent'"
    Then it exits 0

  @unit
  Scenario: help lists the four subcommands
    When I run "memagent --help"
    Then it exits 0
    And the output lists "chat"
    And the output lists "ask"
    And the output lists "analytics"
    And the output lists "wipe-memory"

  @unit
  Scenario: ask is a stub that echoes and exits cleanly
    When I run "memagent ask \"how does redis vector search work\""
    Then it exits 0
    And the output contains "how does redis vector search work"

  @unit
  Scenario Outline: stub commands exit 0 without side effects
    When I run "memagent <command>"
    Then it exits 0
    And no network call is made
    Examples:
      | command   |
      | chat      |
      | analytics |

Feature: Configuration settings are the single source of truth
  # covers FR-M1-07, FR-M1-18; smoke portion in tests/unit/test_smoke.py

  @unit
  Scenario: defaults load with no .env present
    Given no .env file
    When I construct Settings()
    Then similarity_threshold is exactly 0.7
    And embedding_dim is 1536
    And memory_index_name is "web_memory"
    And memory_ttl_seconds is 604800
    And chunk_size_chars is 1600
    And chunk_overlap_chars is 200
    And history_max_turns is 6
    And wait_cap_scale is 1.0

  @unit
  Scenario Outline: every setting exposes its documented default
    Given no .env file
    When I construct Settings()
    Then the field <field> equals <default>
    Examples:
      | field                       | default                    |
      | conversation_model          | "gpt-5.4-mini"             |
      | analytics_model             | "gpt-5.4-nano"             |
      | embedding_model             | "text-embedding-3-small"   |
      | redis_url                   | "redis://localhost:6379/0" |
      | memory_top_k                | 5                          |
      | freshness_window_seconds    | 86400                      |
      | search_max_results          | 8                          |
      | fetch_top_n                 | 5                          |
      | fetch_concurrency           | 5                          |
      | fetch_max_bytes             | 2500000                    |
      | llm_timeout_s               | 45                         |
      | llm_max_attempts            | 4                          |
      | classify_timeout_s          | 8                          |
      | max_chunks_per_page         | 25                         |
      | web_context_chunks_per_page | 2                          |
      | guard_max_query_chars       | 2000                       |
      | turn_log_path               | "logs/turns.jsonl"         |

  @unit
  Scenario: an environment variable overrides its default
    Given the environment sets SIMILARITY_THRESHOLD to "0.85"
    When I construct Settings()
    Then similarity_threshold is exactly 0.85

  @unit
  Scenario: missing OPENAI_API_KEY does not raise at import or construction
    Given OPENAI_API_KEY is unset
    When I construct Settings()
    Then it succeeds
    And openai_api_key is ""
    And running "python -c 'import memagent'" with OPENAI_API_KEY unset exits 0

  @unit
  Scenario: unknown environment variables are ignored
    Given the environment sets SOME_UNKNOWN_VAR to "x"
    When I construct Settings()
    Then it succeeds and has no attribute "some_unknown_var"

Feature: .env.example stays in sync with Settings
  # covers FR-M1-08

  @unit
  Scenario: every Settings field appears in .env.example
    Given the committed .env.example
    And the field names of Settings
    Then each field name (uppercased) appears as a KEY in .env.example

  @unit
  Scenario: regenerating .env.example is a no-op when in sync
    When I run "python scripts/gen_env_example.py"
    Then the git diff of .env.example is empty

Feature: Redis index schema definition
  # covers FR-M1-14; smoke portion in tests/unit/test_smoke.py

  @unit
  Scenario: the schema declares eleven fields
    When I build the schema from Settings()
    Then it has exactly 11 fields
    And the field names are: chunk_text, url, url_hash, title, doc_type, source_query, chunk_index, fetched_at, sanitizer_flags, content_sha256, embedding

  @unit
  Scenario: index identity and storage
    When I build the schema from Settings()
    Then the index name is "web_memory"
    And the storage type is "hash"
    And the resulting Redis key prefix is "chunk:"

  @unit
  Scenario: the embedding field is FLAT cosine float32 1536
    When I build the schema from Settings()
    Then the "embedding" field type is "vector"
    And its algorithm is "flat"
    And its distance_metric is "cosine"
    And its datatype is "float32"
    And its dims is 1536

  @unit
  Scenario Outline: metadata field types match section 4.2
    When I build the schema from Settings()
    Then the field <name> has type <type>
    Examples:
      | name            | type    |
      | chunk_text      | text    |
      | url             | tag     |
      | url_hash        | tag     |
      | title           | text    |
      | doc_type        | tag     |
      | source_query    | text    |
      | chunk_index     | numeric |
      | fetched_at      | numeric |
      | sanitizer_flags | tag     |
      | content_sha256  | text    |

  @unit
  Scenario: fetched_at is a sortable numeric and sanitizer_flags is a csv tag
    When I build the schema from Settings()
    Then the "fetched_at" field is sortable
    And the "sanitizer_flags" tag separator is ","

Feature: wipe-memory works end to end
  # automated in M6 tests/integration/test_redis_store.py; M1 proves it via the live demo.
  # The three @integration scenarios below are OWNED BY M6 (test-file ownership ruling); in M1
  # they are satisfied ONLY by the live demo (FR-M1-15) - they are not an M1 automated-test obligation.

  @integration
  Scenario: wipe-memory creates the index when it is absent
    Given a running redis:8.2 with no web_memory index
    When I run "memagent wipe-memory"
    Then it exits 0
    And FT._LIST includes "web_memory"
    And the index has 0 documents

  @integration
  Scenario: wipe-memory is idempotent when the index already exists
    Given a running redis:8.2 with the web_memory index present
    When I run "memagent wipe-memory"
    And I run "memagent wipe-memory" again
    Then both runs exit 0
    And FT._LIST includes "web_memory" exactly once

  @integration
  Scenario: wipe-memory drops existing data
    Given a running redis:8.2 with the web_memory index
    And a HASH key "chunk:abc123:0" exists under the chunk: prefix
    When I run "memagent wipe-memory"
    Then the key "chunk:abc123:0" no longer exists
    And the index has 0 documents

  @manual
  Scenario: wipe-memory reports a clean error when Redis is unreachable
    Given no Redis is listening on the configured REDIS_URL
    When I run "memagent wipe-memory"
    Then it exits non-zero
    And the output is a single line
    And the output contains no "Traceback (most recent call last)"

Feature: Startup dimension assertion contract
  # covers FR-M1-16; smoke portion in tests/unit/test_smoke.py

  @unit
  Scenario: matching dimensions pass
    When I call assert_index_dims(1536, Settings())
    Then it returns without raising

  @unit
  Scenario: a dimension mismatch raises an actionable error
    When I call assert_index_dims(3072, Settings())
    Then a ValueError is raised
    And the message mentions "wipe-memory"

Feature: docker-compose brings up Redis and RedisInsight
  # covers FR-M1-10, FR-M1-15 (demo); Makefile portion covers FR-M1-09

  @unit
  Scenario: docker-compose.yml declares the required redis service (pure YAML, no Docker)
    Given the parsed docker-compose.yml
    Then the "redis" service image is "redis:8.2"
    And its command includes "--appendonly yes"
    And it defines a healthcheck whose test runs "redis-cli ping"
    And some service publishes "5540:5540"

  @manual
  Scenario: make redis-up starts a healthy redis:8.2
    When I run "make redis-up"
    Then a container "memagent-redis" is running image "redis:8.2"
    And "docker compose ps" reports it healthy
    And "redis-cli FT._LIST" exits 0

  @manual
  Scenario: RedisInsight shows the index after a wipe
    Given "make redis-up" has completed
    When I run "memagent wipe-memory"
    And I open http://localhost:5540 and connect to memagent-redis
    Then the "web_memory" index is listed with 0 documents

  @unit
  Scenario: all required Makefile targets are declared .PHONY
    Given the Makefile
    Then the .PHONY line lists setup, redis-up, run, ask, analytics, wipe, test, test-integration, lint, demo
    And no recipe invokes the hyphenated "docker-compose"

Feature: CI skeleton runs lint and unit tests with zero keys
  # covers FR-M1-11

  @manual
  Scenario: the single CI job lints then runs unit tests
    Given a push to the repository
    When CI runs the "test" job
    Then it runs "ruff check ." before pytest
    And pytest runs with -m "not integration and not e2e"
    And a coverage report is printed with no failing gate
    And the run references no repository secret

  @manual
  Scenario: CI pins its actions and reads Python from the version file
    Given ci.yml
    Then actions/checkout is pinned to a major tag
    And actions/setup-python uses python-version-file ".python-version"
    And astral-sh/setup-uv is pinned to a major tag

Feature: redisvl signature verification (M1 duty)
  # covers FR-M1-17

  @manual
  Scenario: verification confirms the signatures used later
    When I run "python scripts/verify_redisvl.py"
    Then it reports whether SearchIndex.load accepts a ttl= keyword
    And it reports whether array_to_buffer is importable
    And it reports whether VectorQuery is importable

  @manual
  Scenario: the EXPIRE-pipeline fallback is documented when load(ttl=) is absent
    Given "python scripts/verify_redisvl.py" reports no ttl= keyword on load
    Then the script prints the EXPIRE-pipeline fallback instruction
    And the fallback is noted in the README "verified at M1" list

Feature: AI-assistance documentation is scaffolded
  # covers FR-M1-12, and ruling 12 (per-milestone append)

  @unit
  Scenario: AI_USAGE.md carries the eight headings
    Given AI_USAGE.md
    Then it contains a heading "Tools used"
    And it contains a heading "Workflow narrative"
    And it contains a heading "Per-component provenance table"
    And it contains a heading "Curated highlights"
    And it contains a heading "Complete prompt log"
    And it contains a heading "What was reviewed, tested, and corrected by hand"
    And it contains a heading "What was deliberately NOT AI-generated"
    And it contains a heading "Judgement notes"

  @manual
  Scenario: the milestone-1 prompt log is appended, not reconstructed
    Given docs/ai_prompts/milestone-1.md
    Then it is non-empty
    And it was committed as part of the M1 work (not retroactively)

Feature: Repository hygiene files
  # covers FR-M1-13

  @unit
  Scenario: .gitignore ignores the required paths
    Given the committed .gitignore
    Then it contains the exact line ".env"
    And it contains ".venv/"
    And it contains "__pycache__/"
    And it contains "logs/"

  @unit
  Scenario: README carries the verbatim zero-keys note and quickstart
    Given the committed README.md
    Then it contains the zero-keys note "`make test` and `python scripts/eval_lifecycle.py --mock`"
    And it contains the quickstart "clone -> install uv -> `make setup` (uv sync + .env) -> `make redis-up` -> `make run`"
```

---

## 8. Task breakdown

Ordered; each roughly <= 1 hour. `[P]` marks tasks that can run in parallel with their siblings once their dependencies are met. Each names the FR(s) it satisfies.

- **T-M1-01** `uv init`; write `pyproject.toml` with the 14 runtime pins, dev group, `[project.scripts]`, pytest/ruff config, and `requires-python`; create `.python-version`. *(FR-M1-01, FR-M1-03, FR-M1-04)*
- **T-M1-02** `uv sync`; verify resolution; commit `uv.lock`. Depends on T-M1-01. *(FR-M1-02)*
- **T-M1-03 [P]** Write `config.py` `Settings` with every section-10.3 field and default; keep keys optional. *(FR-M1-07, FR-M1-18)*
- **T-M1-04** Write `scripts/gen_env_example.py`; generate and commit `.env.example`. Depends on T-M1-03. *(FR-M1-08)*
- **T-M1-05 [P]** Create the full `src/memagent/` tree with importable stub modules, `__init__.py`, `__main__.py`, and `cli.py` with the four subcommands (three stubs). Depends on T-M1-01. *(FR-M1-05, FR-M1-06)*
- **T-M1-06 [P]** Write `memory/schema.py`: `build_schema`, `get_index`, `ensure_index`, `wipe_index`, `assert_index_dims` (all 11 fields; FLAT cosine float32 1536). Depends on T-M1-03. *(FR-M1-14, FR-M1-16)*
- **T-M1-07** Wire `cli.py wipe-memory` to `get_index` + `wipe_index` over an async Redis client from `Settings.redis_url`. Depends on T-M1-05, T-M1-06. *(FR-M1-15, FR-M1-19)*
- **T-M1-08 [P]** Write `docker-compose.yml` (redis:8.2 + AOF + healthcheck + RedisInsight :5540). *(FR-M1-10)*
- **T-M1-09 [P]** Write the `Makefile` with all ten `.PHONY` targets using `docker compose`. Depends on T-M1-05 (commands reference `memagent`). *(FR-M1-09)*
- **T-M1-10 [P]** Write `.github/workflows/ci.yml` (single job, pinned actions, python from file, coverage report) and `tests/unit/test_smoke.py`. Depends on T-M1-03, T-M1-06. *(FR-M1-11)*
- **T-M1-11 [P]** Write `AI_USAGE.md` (8 headings) and create `docs/ai_prompts/`. *(FR-M1-12)*
- **T-M1-12 [P]** Write `LICENSE` (MIT), `.gitignore`, the `README.md` skeleton with the section-10.4 quickstart, and the `DECISIONS.md` scaffold seeded with the standing anti-churn rulings (finalized in M6). *(FR-M1-13)*
- **T-M1-13 [P]** Write and run `scripts/verify_redisvl.py`; record the outcome; note the EXPIRE fallback if needed. Depends on T-M1-02. *(FR-M1-17)*
- **T-M1-14** Run the demo (`make setup && make redis-up && memagent wipe-memory`), confirm RedisInsight shows `web_memory`, run `pytest`/`ruff`, then append this milestone's prompts to `docs/ai_prompts/milestone-1.md`. Depends on all above. *(Definition of Done + ruling 12)*

---

## 9. Definition of Done

Each item has an exact verify command or observable outcome.

- [ ] `uv sync` succeeds and `uv.lock` is committed - `uv sync --locked` exits 0; `git ls-files uv.lock` prints `uv.lock`. *(FR-M1-01, FR-M1-02)*
- [ ] `.python-version` is `3.12` - `cat .python-version`. *(FR-M1-03)*
- [ ] Package imports - `uv run python -c "import memagent"` exits 0. *(FR-M1-05)*
- [ ] CLI surface - `uv run memagent --help` lists `chat`, `ask`, `analytics`, `wipe-memory`. *(FR-M1-04, FR-M1-06)*
- [ ] Config defaults - `uv run python -c "from memagent.config import Settings; s=Settings(); assert s.similarity_threshold==0.7 and s.embedding_dim==1536 and s.memory_index_name=='web_memory' and s.memory_ttl_seconds==604800"` exits 0. *(FR-M1-07)*
- [ ] Keyless construction - the same command runs with `OPENAI_API_KEY` unset. *(FR-M1-18)*
- [ ] `.env.example` in sync - `uv run python scripts/gen_env_example.py` leaves `git diff --exit-code .env.example` clean. *(FR-M1-08)*
- [ ] Schema shape - `uv run python -c "from memagent.config import Settings; from memagent.memory.schema import build_schema; assert len(build_schema(Settings()).fields)==11"` exits 0; the `embedding` field is FLAT/cosine/float32/1536. *(FR-M1-14)*
- [ ] Dimension contract - `assert_index_dims(3072, Settings())` raises `ValueError` mentioning `wipe-memory`. *(FR-M1-16)*
- [ ] Unit run green - `uv run pytest -m "not integration and not e2e"` passes (smoke test). *(CI wiring)*
- [ ] Lint clean - `uv run ruff check .` reports no errors. *(FR-M1-11)*
- [ ] Repo hygiene files - `.gitignore` ignores `.env`, `.venv/`, `__pycache__/`, `logs/` (`grep -qxF '.env' .gitignore` and greps for `.venv/`, `__pycache__/`, `logs/` all exit 0); `README.md` contains the verbatim zero-keys note and five-command quickstart; `DECISIONS.md` exists at the repo root with the standing anti-churn rulings (`test -s DECISIONS.md`). *(FR-M1-13)*
- [ ] Makefile - all ten targets under `.PHONY:`; no `docker-compose` (hyphenated) in recipes - `grep -q '^.PHONY:.*demo' Makefile && ! grep -q 'docker-compose' Makefile` exits 0. *(FR-M1-09)*
- [ ] Compose valid - `docker compose config` exits 0; redis service is `redis:8.2` with AOF + healthcheck; RedisInsight publishes `5540`. *(FR-M1-10)*
- [ ] CI green - the push shows a passing single job that ran ruff + unit tests with no secrets, Python from `.python-version`, pinned actions. *(FR-M1-11)*
- [ ] redisvl verified - `uv run python scripts/verify_redisvl.py` output recorded; EXPIRE fallback noted if `load(ttl=)` is absent. *(FR-M1-17)*
- [ ] **Demoable outcome (PLAN section 13)** - `make setup && make redis-up && uv run memagent wipe-memory` exits 0, and RedisInsight at `http://localhost:5540` shows the empty `web_memory` index. *(FR-M1-15, FR-M1-19)*
- [ ] **Idempotent wipe** - with `redis:8.2` up, `uv run memagent wipe-memory` run twice in a row both exit 0, and `redis-cli FT._LIST` shows `web_memory` exactly once (with zero documents). *(FR-M1-19)*
- [ ] **AI usage (ruling 12)** - `AI_USAGE.md` has the eight headings; `docs/ai_prompts/milestone-1.md` is appended with this milestone's prompts (committed now, not retroactively) - `[ "$(grep -c '^## ' AI_USAGE.md)" -eq 8 ]` and `test -s docs/ai_prompts/milestone-1.md` both exit 0. *(FR-M1-12)*

---

## 10. Risks & gotchas

- **redisvl prefix double-colon trap** (section 6.5) - `prefix="chunk"` + `key_separator=":"` yields PREFIX `chunk:`. `prefix="chunk:"` yields `chunk::`. Verify with `FT.INFO web_memory` after the first wipe. Highest-probability schema mistake.
- **redisvl signature drift across 0.22-0.24** (PLAN section 14) - `create()`/`delete()`/`load(ttl=)`/`array_to_buffer`/`VectorQuery` signatures may differ from the code in section 6.5. This is exactly why FR-M1-17 runs a verification script at M1; use `delete(drop=True)`+`create()` or the EXPIRE-pipeline fallback if needed.
- **`redis:8.2` must ship FT.***  (PLAN section 14) - confirm with `redis-cli FT._LIST` after `make redis-up`. If it unexpectedly lacks the query engine, fall back to `redis/redis-stack-server:latest` (EOL - last resort, note it in README).
- **Empty unit-test collection fails CI** - `pytest` exits 5 when it collects no tests. M1 must ship `tests/unit/test_smoke.py` so the unit run is green before M2 adds real tests.
- **`OPENAI_API_KEY` must be optional in `Settings`** - making it required at import breaks keyless `make test`, `make lint`, and the `wipe-memory` demo. The fail-fast key check belongs at client construction (M2), not here (FR-M1-18).
- **`docker compose` v2 spelling** - the hyphenated `docker-compose` (v1) is EOL; every recipe uses the space form.
- **Makefile tabs** - recipe lines must be tab-indented, not spaces, or `make` errors.
- **`EMBEDDING_DIM` is baked into the FLAT index** - changing `EMBEDDING_MODEL`/`EMBEDDING_DIM` requires `wipe-memory`; the dimension assertion (FR-M1-16) exists to catch mismatches loudly in M2.
- **Distance vs similarity** (PLAN section 4.3) - not implemented until M2, but the schema fixes the metric to `cosine` so `similarity = 1 - distance` will hold. Do not change the metric here.
- **AI_USAGE written retroactively** (PLAN section 15) - the biggest scoring risk on that requirement; the per-milestone append is a DoD item starting now.

---

## 11. Spec Kit mapping

- **/specify -> spec.md**: sections 1 (goal & context), 2 (scope, incl. out-of-scope and deferred-by-design), 5 (functional requirements FR-M1-01..19), and 7 (BDD acceptance scenarios).
- **/plan -> plan.md**: sections 3 (prerequisites & interfaces consumed), 4 (interfaces provided + stub-replacement map), 6 (full technical specification: pyproject, config, schema, compose, Makefile, CI, exact commands), and 10 (risks & gotchas).
- **/tasks -> tasks.md**: section 8 (T-M1-01..14 with `[P]` markers and FR links), with section 9 (Definition of Done) as the acceptance gates each task rolls up to.
