# Quickstart Validation: Milestone 2 — Memory Path

**Date**: 2026-07-05 · Contracts: [contracts/](contracts/) · Data model:
[data-model.md](data-model.md) · Run from `~/Desktop/epam/memory-first-agent/`.

## Prerequisites

- M1 closed and green (repo, `Settings`, `web_memory` index, `wipe-memory`, CI)
- Docker up: `make redis-up`
- **GitHub Models free-dev credentials** (Clarifications 2026-07-05): a fine-grained
  GitHub PAT with the `models: read` permission. Configure the session:

```bash
# in .env (dev machine only — never committed):
OPENAI_API_KEY=<fine-grained GitHub PAT>
OPENAI_BASE_URL=<GitHub Models OpenAI-compatible endpoint>   # verify + record at implement time
CONVERSATION_MODEL=<dev-mode id, e.g. openai/gpt-5.4-mini>   # session-level override only
EMBEDDING_MODEL=<dev-mode embedding id>                      # production defaults stay untouched
```

- Unit tests need none of the above (keyless, no Docker).

## 1. Unit proof — the M2-owned test files (US2 + US3)

```bash
uv run pytest tests/unit/test_routing.py tests/unit/test_similarity.py tests/unit/test_chunker.py -q
```

Expected: all pass. Must include: the 5-row boundary table (0.70 inclusive hit, 0.6999
miss, None miss, 1.0 hit, 0.0 miss); `distance_to_similarity(0.30) == 0.70` + routes as
hit; the 1−d/2 formula asserted absent; router purity (same input → same output, no I/O);
chunker bounds/floor/cap/no-empty/unicode/short-doc invariants; URL canonicalization table
+ same-hash assertion (FR-M2-15, hosted in test_chunker.py per analysis C1).

```bash
uv run ruff check src tests && make test    # whole suite still green, keyless
```

## 2. Live seeded demo — the milestone's demoable outcome (US1)

```bash
uv run memagent wipe-memory                                  # start from an empty index
uv run python scripts/seed_memory.py --url https://redis.io/docs/vectors --file docs/seed.md
uv run memagent ask "How does Redis vector search work?"
```

Expected: `[MEMORY HIT sim=0.XX]` with sim ≥ 0.70 (two decimals), an answer ending with
"Sources:", and `(memory) <title> <https://redis.io/docs/vectors>`.

```bash
uv run memagent ask "What is the capital of Mongolia?"       # unseeded topic
```

Expected: `[MEMORY MISS]` + the deterministic response (temporary M2 miss path), exit 0.

Deeper checks:

```bash
docker exec memagent-redis redis-cli TTL "chunk:$(uv run python -c \
  "from memagent.memory.urls import url_hash; print(url_hash('https://redis.io/docs/vectors'))"):0"
# expected: > 0 and <= 604800
```

## 3. Structural spine checks (US4)

```bash
uv run python -c "
from typing import get_args
from memagent.state import Route
assert set(get_args(Route)) == {'memory_hit','memory_miss_web_search','degraded_web','blocked','failed'}
print('Route closed set OK')"
uv run python -c "
import dataclasses
from memagent.resources import AgentResources
assert dataclasses.fields(AgentResources) and AgentResources.__dataclass_params__.frozen
print('frozen resources OK')"
OPENAI_API_KEY=dummy uv run python -c "
from memagent.app import build_resources
from memagent.graph import build_graph
g = build_graph(build_resources())
m = g.get_graph().draw_mermaid()
assert m and 'embed_query' in m
print('graph compiles; mermaid OK')"
```

## 4. FR-025 verification records (US4)

One live call listing/using the catalogue ids and one `temperature=0` call on the
conversation model — copy actual id strings + pass/fail into
`docs/ai_prompts/milestone-2.md`.

## Done when

Sections 1–4 all behave as stated (SC-001…SC-006), plus: M2 prompts appended to
`docs/ai_prompts/milestone-2.md` and referenced from `AI_USAGE.md` §5 — then M3 may start.
