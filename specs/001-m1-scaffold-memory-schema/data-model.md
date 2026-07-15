# Phase 1 Data Model: Milestone 1 — Repo Scaffold, Toolchain & Memory Index Schema

**Date**: 2026-07-05 · **Plan**: [plan.md](plan.md) · Field values are verbatim from
`specs/milestone-1-scaffold-and-memory-schema.md` §6.3/§6.5 (source: PLAN §10.3/§4.2).

## Entity 1: `Settings` (`src/memagent/config.py`)

Single source of every tunable number and env name (Constitution P-III). pydantic-settings
`BaseSettings`; lowercase field names matched case-insensitively to UPPERCASE env vars;
`env_file=".env"`, `extra="ignore"` (unknown vars never crash — spec edge case).

| Field | Type | Default | Notes |
|---|---|---|---|
| openai_api_key | str | `""` | optional at M1 (FR-018); fail-fast check lands in M4 |
| openai_base_url | str \| None | `None` | optional → GitHub Models free dev mode |
| tavily_api_key | str | `""` | optional → keyless ddgs fallback |
| conversation_model | str | `"gpt-5.4-mini"` | |
| analytics_model | str | `"gpt-5.4-nano"` | |
| embedding_model | str | `"text-embedding-3-small"` | threshold calibrated to this model |
| embedding_dim | int | `1536` | baked into the index; guarded by `assert_index_dims` |
| redis_url | str | `"redis://localhost:6379/0"` | |
| memory_index_name | str | `"web_memory"` | |
| similarity_threshold | float | `0.7` | inclusive; hit ⇔ (1 − distance) ≥ this |
| memory_top_k | int | `5` | |
| memory_ttl_seconds | int | `604800` | 7 days; 0 disables |
| freshness_window_seconds | int | `86400` | |
| search_max_results | int | `8` | |
| fetch_top_n | int | `5` | |
| fetch_concurrency | int | `5` | |
| connect_timeout_s | int | `5` | |
| read_timeout_s | int | `10` | |
| page_deadline_s | int | `20` | |
| fetch_max_bytes | int | `2500000` | |
| llm_timeout_s | int | `45` | |
| llm_max_attempts | int | `4` | |
| classify_timeout_s | int | `8` | |
| chunk_size_chars | int | `1600` | |
| chunk_overlap_chars | int | `200` | |
| max_chunks_per_page | int | `25` | |
| web_context_chunks_per_page | int | `2` | |
| history_max_turns | int | `6` | |
| wait_cap_scale | float | `1.0` | tests set 0 → instant retries via prod path |
| guard_max_query_chars | int | `2000` | |
| log_level | str | `"INFO"` | |
| turn_log_path | str | `"logs/turns.jsonl"` | |

**Validation rules**: construction with no `.env` and no env vars MUST succeed (keyless);
env var overrides its field (e.g. `SIMILARITY_THRESHOLD=0.85` → `0.85`); no field is added
outside this class (new numbers get a field here, never a literal elsewhere).

**Relationships**: consumed by `memory/schema.py` (index name, dims), `cli.py`
(redis_url), `scripts/gen_env_example.py` (all fields, declaration order); M2+ read
everything else.

## Entity 2: `web_memory` index (`src/memagent/memory/schema.py`)

Redis 8 FT.* vector index, HASH storage. Identity: name `web_memory` (from Settings), prefix
`chunk` + key_separator `:` → Redis PREFIX `chunk:` (the double-colon trap: never set
`prefix="chunk:"`).

| # | Field | Type | Attrs / meaning |
|---|---|---|---|
| 1 | chunk_text | text | sanitized markdown — raw is never stored (M5 enforces) |
| 2 | url | tag | canonical URL (utm/fragment-stripped) |
| 3 | url_hash | tag | `sha256(canonical_url)[:16]` |
| 4 | title | text | |
| 5 | doc_type | tag | `chunk` \| `summary` — both participate in KNN |
| 6 | source_query | text | query that triggered ingestion |
| 7 | chunk_index | numeric | |
| 8 | fetched_at | numeric, sortable | epoch seconds |
| 9 | sanitizer_flags | tag, separator `,` | provenance for the T3 defense |
| 10 | content_sha256 | text | audit/tamper check |
| 11 | embedding | vector | **FLAT, cosine, float32, dims = `settings.embedding_dim` (1536)** |

**Key patterns** (written by M2's store; the shape is fixed here):
- `chunk:{url_hash}:{i}` — chunk docs (indexed)
- `chunk:{url_hash}:summary` — per-page summary doc (indexed, participates in KNN)
- `doc:{url_hash}` — non-indexed meta hash (`num_chunks`, `fetched_at`, `url`)

**State transitions (index lifecycle)**:

```
absent ──ensure_index()──▶ exists(empty) ──M2 store()──▶ exists(populated)
   ▲                            │  ▲                          │
   └────────── wipe_index() ────┘  └────── wipe_index() ◀─────┘
        (drop index + data, recreate empty — idempotent, FR-019)
```

**Validation rules**: exactly 11 fields; vector field FLAT/cosine/float32/1536;
`assert_index_dims(embedder_dim, settings)` raises `ValueError` mentioning `wipe-memory`
when `embedder_dim != settings.embedding_dim` (defined M1, called from M2's
`build_resources()`).

## Entity 3: CLI surface (`src/memagent/cli.py`)

| Command | M1 behavior | Replaced by |
|---|---|---|
| `wipe-memory` | **functional**: connect to `settings.redis_url`, drop + recreate `web_memory`, echo confirmation; non-zero readable error if Redis unreachable | stays as-is |
| `ask "…"` | stub: echoes the query + "wired in M2", exit 0, no side effects | M2 |
| `chat` | stub: one-line "wired in M4" banner, exit 0 | M4 |
| `analytics` | stub: one-line "wired in M4" notice, exit 0 | M4 |

Entry point: `[project.scripts] memagent = "memagent.cli:app"`.

## Entity 4: Delivery harness (repo-root artifacts)

| Artifact | Content contract (detail in [contracts/delivery-harness.md](contracts/delivery-harness.md)) |
|---|---|
| `pyproject.toml` | 14 runtime pins verbatim; dev group of 5; hatchling; pytest markers `integration`/`e2e`; ruff py312/100 |
| `uv.lock` | committed; `uv sync --locked` resolves |
| `.python-version` | `3.12` |
| `.env.example` | generated (byte-identical) from Settings; 32 keys |
| `Makefile` | 10 required `.PHONY` targets (+`redis-down`); compose v2 spelling only |
| `docker-compose.yml` | redis:8.2 (AOF, healthcheck) + redisinsight :5540; no `version:` key |
| `.github/workflows/ci.yml` | single zero-secret job: uv sync → ruff → unit tests + coverage report |
| `AI_USAGE.md` | the 8 headings; `docs/ai_prompts/milestone-1.md` non-empty |
| `DECISIONS.md` | scaffold seeded with the anti-churn list (M6 finalizes) |
| `LICENSE` | MIT (Clarifications 2026-07-05) |
| `.gitignore` | ≥ `.env .venv/ __pycache__/ *.pyc logs/ .pytest_cache/ .ruff_cache/ .coverage dist/ build/ *.egg-info/` |
| `README.md` | skeleton with §10.4 quickstart verbatim (zero-keys note + 5 commands) |
