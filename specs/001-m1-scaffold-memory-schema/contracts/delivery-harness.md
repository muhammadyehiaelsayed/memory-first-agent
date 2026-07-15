# Contract: Delivery harness (M1 shape — M6 finalizes content, never the shape)

Repo root: `epam/memory-first-agent/` (Clarifications 2026-07-05). Verbatim blocks live in
the milestone file §6; this contract states what MUST hold and how it is checked.

## `pyproject.toml` (FR-001/002/004)

- `requires-python = ">=3.12,<3.14"`; project name `memagent`, version `0.1.0`.
- **Exactly 14 runtime dependencies**: `langgraph>=1.2,<2`, `langchain-text-splitters`,
  `redis>=6.2,<7`, `redisvl>=0.22,<0.24`, `httpx>=0.28`, `tenacity~=9.1`,
  `trafilatura>=2.1,<3`, `ddgs>=9,<10`, `openai>=2`, `pydantic>=2.11`, `pydantic-settings`,
  `typer>=0.16`, `rich>=14`, `structlog~=26.1`.
- **Forbidden** (checked by acceptance): `tavily-python`, `python-ulid`, `fakeredis`,
  `anthropic`, `markdownify`.
- Dev group: `pytest~=8.4`, `pytest-asyncio>=1,<2`, `respx~=0.23`, `ruff`, `pytest-cov`.
- Build backend `hatchling` targeting `src/memagent`; pytest `asyncio_mode="auto"`, markers
  `integration` + `e2e`; ruff `target-version="py312"`, `line-length=100`.
- `uv.lock` committed; `uv sync --locked` exits 0.

## `Makefile` (FR-009)

- Targets (all `.PHONY`): `setup redis-up run ask analytics wipe test test-integration lint
  demo` (+ `redis-down` extra). Tab-indented recipes.
- `setup` = `uv sync` + copy `.env.example → .env` if missing; `redis-up` =
  `docker compose up -d --wait`; `test` = `uv run pytest -m "not integration and not e2e"`;
  `lint` = `uv run ruff check .`; `ask` takes `Q=`.
- **Zero occurrences of the hyphenated `docker-compose`** anywhere in recipes.

## `docker-compose.yml` (FR-010)

- No top-level `version:` key. Service `redis`: image **`redis:8.2`**, command
  `--appendonly yes`, port 6379, named volume, healthcheck `redis-cli ping` (2s/3s/10).
  Service `redisinsight`: image `redis/redisinsight:latest`, port `5540:5540`,
  `depends_on: redis: condition: service_healthy`.
- Check: `docker compose config` valid; `docker compose up -d --wait` returns only when
  Redis answers PING.

## `.env.example` + generator (FR-008)

- Produced by `scripts/gen_env_example.py`: iterates `Settings.model_fields` in declaration
  order with a fixed per-field template `ENV_NAME=<placeholder># comment`.
- Secret-shaped placeholders: `OPENAI_API_KEY=sk-...`, `OPENAI_BASE_URL=` (blank, never
  `None`), `TAVILY_API_KEY=` (blank). Every other field emits its exact Settings default.
- **Byte-identical** to the committed file: `python scripts/gen_env_example.py && git diff
  --exit-code .env.example` passes.

## `.github/workflows/ci.yml` (FR-011)

- Single job `test` on `ubuntu-latest`, triggers `[push, pull_request]`.
- Steps exactly: `actions/checkout@v4` → `astral-sh/setup-uv@v6` →
  `actions/setup-python@v5` with `python-version-file: .python-version` → `uv sync` →
  `uv run ruff check .` → `uv run pytest -m "not integration and not e2e" --cov=memagent
  --cov-report=term`.
- No `secrets.*` reference anywhere; coverage is a report — **no threshold/gate**.
- Live green run on the public GitHub repo closes M1 (SC-005, Clarifications Q3).

## Docs & meta (FR-012/013)

- `AI_USAGE.md` headings, verbatim: `# AI Usage` + `## 1. Tools used`,
  `## 2. Workflow narrative`, `## 3. Per-component provenance table`,
  `## 4. Curated highlights (3-6 representative prompts)`,
  `## 5. Complete prompt log (see docs/ai_prompts/)`,
  `## 6. What was reviewed, tested, and corrected by hand`,
  `## 7. What was deliberately NOT AI-generated`, `## 8. Judgement notes`.
- `docs/ai_prompts/milestone-1.md` exists, non-empty, labelled part of the complete
  instruction record (append-as-you-go — Constitution P-VII).
- `LICENSE` = MIT. `.gitignore` ⊇ `.env .venv/ __pycache__/ *.pyc logs/ .pytest_cache/
  .ruff_cache/ .coverage dist/ build/ *.egg-info/`.
- `README.md` skeleton contains the §10.4 quickstart verbatim (zero-keys note; one key +
  Docker; clone → install uv → `make setup` → `make redis-up` → `make run`) with stubbed
  placeholder sections filled in M6.
- `DECISIONS.md` scaffold seeded with the anti-churn list (M6 finalizes).

## `tests/unit/test_smoke.py` (M1-owned; FR-011's green unit run)

Asserts exactly: `import memagent` works; `Settings()` defaults
(`similarity_threshold == 0.7`, `embedding_dim == 1536`,
`memory_index_name == "web_memory"`); `build_schema(Settings())` has 11 fields. MUST NOT
grow into routing/similarity/chunker tests (M2-owned files).
