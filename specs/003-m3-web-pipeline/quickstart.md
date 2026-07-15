# Quickstart Validation: Milestone 3 — Web Pipeline

**Date**: 2026-07-05 · Contracts: [contracts/](contracts/) · Data model:
[data-model.md](data-model.md) · Run from `~/Desktop/epam/memory-first-agent/`.

## Prerequisites

- M1 + M2 closed and green (repo, index, memory path, `[MEMORY HIT sim=0.XX]` demo).
- Docker up: `make redis-up`.
- `.env` (git-ignored, never committed) carries the M2 GitHub Models free-dev block
  (`OPENAI_API_KEY`=PAT, `OPENAI_BASE_URL`, dev model aliases) **plus** the M3 addition
  (Clarifications 2026-07-05, already stored and probe-verified):

```bash
TAVILY_API_KEY=tvly-dev-...   # free tier; blank would exercise the ddgs fallback instead
```

- The optional unit test needs none of the above (keyless, no Docker).

## 1. Import + structural spine

```bash
uv run python -c "import memagent.web.search, memagent.web.fetch, memagent.web.to_markdown, memagent.security.sanitizer"
! grep -rn "tavily-python\|import tavily\|markdownify" src/
OPENAI_API_KEY=dummy uv run python -c "
from memagent.app import build_resources
from memagent.graph import build_graph
m = build_graph(build_resources()).get_graph().draw_mermaid()
assert 'web_search' in m and 'fetch_pages' in m and 'ingest_content' in m and 'answer_from_web' in m
print(m)"
```

Expected: all three exit 0 (grep inverted — no forbidden imports). Then EYEBALL the
printed mermaid (the DoD mandates inspection — a negative substring assert can pass
vacuously against LangGraph's labeled-edge syntax): the miss path must read
`memory_search → web_search → fetch_pages → (ingest_content →) answer_from_web →
log_turn`, and `answer_failure` must be reachable ONLY from `embed_query`/`web_search`
failure routes — no edge from `memory_search` to `answer_failure` may remain.

## 2. Unit proof — the one optional M3-owned file

```bash
uv run pytest tests/unit/test_to_markdown.py -q     # gating: kwargs, recall retry, 199/200 floor, 20k cap
uv run ruff check src/memagent/web src/memagent/nodes src/memagent/security/sanitizer.py
make test                                            # whole suite still green, keyless
```

## 3. Live miss→ingest→hit lifecycle — the milestone's demoable outcome (US1)

```bash
uv run memagent wipe-memory
uv run memagent ask "What did the James Webb telescope find about exoplanet atmospheres in 2026?"
```

Expected turn 1: `[MEMORY MISS → searching the web]`, an answer ending with "Sources:",
and `(web) {title} <{url}>` source lines (Tavily as provider; structlog line shows
`provider_used="tavily"`).

```bash
uv run memagent ask "What did the James Webb telescope find about exoplanet atmospheres in 2026?"
```

Expected turn 2 (identical wording — verbatim re-ask): `[MEMORY HIT sim=0.9x]` with
`(memory)` sources and **no web call** (similarity ≥ 0.70).

Deeper storage checks after turn 1:

```bash
docker exec memagent-redis redis-cli --scan --pattern 'chunk:*' | head    # chunk:{h}:0..N + chunk:{h}:summary
docker exec memagent-redis redis-cli --scan --pattern 'doc:*'             # doc:{h} meta per page
# freshness gate: re-ask within 24 h re-ingests nothing (fetched_at fresh)
```

Capture both turns verbatim into `docs/demo_transcript.md` (FR-034).

## 4. Degraded + failure paths (behavioral spot-checks)

```bash
# snippets-only degraded path: force zero fetchable pages is environment-dependent —
# verified behaviorally in M6's e2e; spot-check here only if it occurs naturally.
# both-providers-fail → answer_failure: run with a bogus key AND no network to observe
# the deterministic failure response (optional).
```

## Done when

Sections 1–3 behave as stated (SC-001…SC-007), `docs/demo_transcript.md` exists, M3
prompts are appended to `docs/ai_prompts/milestone-3.md` and referenced from
`AI_USAGE.md` §5 — then M4 may start.
