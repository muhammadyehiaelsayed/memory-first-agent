# Pre-tag re-verification — 2026-07-06 (Milestone 6, FR-023)

Every time-sensitive fact from PLAN §14 re-verified immediately before the `v1.0` tag. Facts
verifiable without a paid key were checked live in the project venv (below); the one
real-key-dependent fact is recorded "pending real-key capture" (Clarification Q1 — it does not
block `v1.0`). No drift found: no corrections were needed to `config.py`, `.env.example`,
`pyproject.toml`, or `MODEL_CHOICES.md`.

## Dependency pins (live `importlib.metadata.version`, all within `pyproject.toml` ranges)

| Package | Installed | Pin | Status |
|---|---|---|---|
| langgraph | 1.2.7 | `>=1.2,<2` | ✅ |
| redis (client) | 6.4.0 | `>=6.2,<7` | ✅ |
| redisvl | 0.23.0 | `>=0.22,<0.24` | ✅ |
| httpx | 0.28.1 | `>=0.28` | ✅ |
| trafilatura | 2.1.0 | `>=2.1,<3` | ✅ |
| ddgs | 9.14.4 | `>=9,<10` | ✅ |
| openai | 2.44.0 | `>=2` | ✅ |
| tenacity | 9.1.4 | `~=9.1` | ✅ |
| structlog | 26.1.0 | `~=26.1` | ✅ |
| pydantic | 2.13.4 | `>=2.11` | ✅ |
| pytest / pytest-asyncio / respx / pytest-cov / coverage | 8.4.2 / 1.4.0 / 0.23.1 / 7.1.0 / 7.15.0 | `~=8.4` / `>=1,<2` / `~=0.23` / — / — | ✅ |

`uv sync --frozen` audits cleanly against the committed `uv.lock` (CI install step).

## Library-surface signatures (live probe)

- `redisvl.query.VectorQuery.__init__` still accepts `vector_field_name` + `num_results` (+ `dtype`) — ✅ used by `memory/store.py`.
- `redisvl.redis.utils.array_to_buffer` present and callable — ✅.
- `redisvl` idempotency is `ensure_index` (exists-guard + `create(overwrite=False)`); `wipe_index` = `create(overwrite=True, drop=True)` + `doc:*` purge — ✅ (integration test asserts both).
- `langgraph 1.2.7` `get_graph().draw_mermaid()` renders `__start__ --> guard_input` + all 10 nodes, byte-identical across runs — ✅ (`scripts/render_graph.py`, idempotent).
- `openai 2.44.0` structured output via the stable `chat.completions.parse` / `.create` — ✅ (`llm/clients.py`).
- `redis:8.2` (docker-compose + CI service) ships FT.* vector search in core — ✅.

## Model ids + prices (OpenAI public pricing, re-checked 2026-07-05, unchanged)

| Role | Model id | Price (in / out per 1M) |
|---|---|---|
| Conversation | `gpt-5.4-mini` | $0.75 / $4.50 |
| Analytics + page summaries | `gpt-5.4-nano` | $0.20 / $1.25 |
| Embeddings | `text-embedding-3-small` (1536d) | $0.02 in |
| Flagship (documented runner-up) | `gpt-5.4` | $2.50 / $15.00 |

## ⏳ Pending real-key capture (Clarification Q1 — does NOT block v1.0)

- **`temperature=0` support on the pinned `gpt-5.4-mini`**: unverified against the pinned id.
  The GitHub Models catalog serves **no `gpt-5.4*` ids** (37 probed), so the one-off probe
  (`chat.completions.create(model="gpt-5.4-mini", temperature=0, max_tokens=8)` expecting HTTP
  200) requires a real `OPENAI_API_KEY`. Documented as pending in `MODEL_CHOICES.md`; the same
  applies to the production-key demo transcript and the real-key `eval_lifecycle` run.
