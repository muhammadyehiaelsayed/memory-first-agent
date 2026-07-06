# Memory-First Web Agent

A GenAI agent that answers from **Redis vector memory first** (similarity ≥ 0.7, checked in
code — not by the model), falls back to **web search** on a miss, ingests what it finds for
future reuse, and returns **grounded answers with source URLs**.

> **Zero keys needed:** `make test` (fully offline) and `python scripts/eval_lifecycle.py --mock`
> (needs a local `redis:8.2` — run `make redis-up` first). CI runs these among its lint / test / eval steps.
> **One key** (`OPENAI_API_KEY`) **+ Docker** for the live demo; `TAVILY_API_KEY` optional (keyless DuckDuckGo fallback).
>
> Quickstart: clone -> install uv -> `make setup` (uv sync + .env) -> `make redis-up` -> `make run`.

## Quickstart

Five commands from clone to a live miss→hit (needs `OPENAI_API_KEY` + Docker):

```bash
git clone <repo> && cd memory-first-agent
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv
make setup       # uv sync + create .env from .env.example (add OPENAI_API_KEY)
make redis-up    # docker compose up -d --wait (redis:8.2 + RedisInsight at http://localhost:5540)
make run         # chat REPL — ask a question twice: MISS then HIT
```

Other targets: `make ask Q="..."`, `make analytics`, `make wipe` (runs the `wipe-memory`
CLI subcommand — the Make target name differs from the CLI command name), `make test`,
`make test-integration`, `make lint`, `make demo`.

**Zero-key path** (matches CI, no API keys / no internet): `make test` (also needs no Redis) and
`python scripts/eval_lifecycle.py --mock` (needs a local `redis:8.2` — `make redis-up`).

**No uv?** `pip install -e ".[dev]"` inside a Python 3.12 venv works as a fallback
(uv + the committed `uv.lock` is the reproducible path).

## Why this is deliberately not a ReAct / tool-calling agent

The memory-first hit/miss decision is a **deterministic threshold branch in code** — a pure
router over graph state (`similarity >= SIMILARITY_THRESHOLD`), never an LLM judgment or a
tool-choice step. That is what keeps "memory-first" *verifiable* and the hit/miss turn log
*reliable*: the route is a property of the code, not of a model's mood. Parallelism lives
*inside* the `fetch_pages` node (`asyncio.gather` + a bounded semaphore), not as graph
fan-out, so the graph stays a single, auditable, per-turn-stateless `StateGraph`.

## Architecture

Auto-generated from the compiled LangGraph graph by `scripts/render_graph.py` (keyless;
re-running reproduces byte-identical output). Ten nodes; the L1 guard is the entry point.

<!-- BEGIN graph -->

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	guard_input(guard_input)
	embed_query(embed_query)
	memory_search(memory_search)
	answer_from_memory(answer_from_memory)
	web_search(web_search)
	fetch_pages(fetch_pages)
	ingest_content(ingest_content)
	answer_from_web(answer_from_web)
	answer_failure(answer_failure)
	log_turn(log_turn)
	__end__([<p>__end__</p>]):::last
	__start__ --> guard_input;
	answer_failure --> log_turn;
	answer_from_memory --> log_turn;
	answer_from_web --> log_turn;
	embed_query -.-> answer_failure;
	embed_query -.-> memory_search;
	fetch_pages -.-> answer_from_web;
	fetch_pages -.-> ingest_content;
	guard_input -.-> embed_query;
	guard_input -.-> log_turn;
	ingest_content --> answer_from_web;
	memory_search -.-> answer_from_memory;
	memory_search -.-> web_search;
	web_search -.-> answer_failure;
	web_search -.-> fetch_pages;
	log_turn --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

<!-- END graph -->

## Turn log & analytics

Every turn appends one JSON record to `logs/turns.jsonl` (route, similarity, sources,
latencies, token usage, query classification). `memagent analytics` renders hit-rate and
topic/question-type tables over it (`--json` for machines); `logs/turns.sample.jsonl`
ships so the report works on a fresh clone.

The turn log is directly DuckDB-queryable:

```
duckdb -c "SELECT route, count(*) FROM read_json_auto('logs/turns.jsonl') GROUP BY route"
```

JSONL stays the single source of truth — there is no Redis mirror of turn records.

## Security & reliability

Full threat model in [`docs/threat_model.md`](docs/threat_model.md). Four threats, defended by
three guardrail layers (L1 input screen, L2 instruction/data separation, L3
sanitize-before-store) plus an output defence:

| ID | Threat | Mitigation |
|---|---|---|
| T1 | Direct injection in the user query | L1 input screen + L2 prompt hardening |
| T2 | Indirect injection inside fetched pages | L2 data/instruction separation + L3 sanitizer |
| T3 | **Memory poisoning** — injected content stored in Redis, replayed as trusted context on future hits | **L3 sanitize-before-store + persisted `sanitizer_flags` provenance** (the highest-value defense: anything surviving ingestion becomes "trusted memory" forever) |
| T4 | Exfil/unsafe output (attacker URLs, tracker images) | prompt rule "cite only provenance URLs" + markdown-image strip on output |

Reliability: every upstream dependency has a single-owner retry policy
(`utils/reliability.py`, tenacity) with typed failures; every failure mode has a designed
degradation outcome (web-only on Redis down, snippets-only when all fetches fail, a clean
`failed` apology when search/LLM/embeddings are down), and the turn is always logged exactly
once — never a traceback. No jailbreak-proof claims: the layers are "basic but real".

## Calibration & limitations

Stated honestly, each with its named production upgrade:

- **0.70 similarity threshold.** `SIMILARITY_THRESHOLD=0.7` is calibrated for
  `text-embedding-3-small`; the boundary is inclusive (`similarity = 1 − vector_distance`,
  the single conversion site). Changing `EMBEDDING_MODEL` changes what 0.70 *means* — re-tune
  `SIMILARITY_THRESHOLD` and run `make wipe` to rebuild the index for the new geometry.
- **TTL is a coarse staleness policy, not a limitation.** `MEMORY_TTL_SECONDS=604800` (7 days)
  bounds how long a stored page is reused. The production upgrade is ETag / Last-Modified
  conditional revalidation (re-fetch only when the source changed) rather than a blunt clock.
- **robots.txt is not consulted.** A known limitation for a single-user take-home; the
  production fix is a robots.txt fetch + cache honored before each page GET.
- **Why fetch + markdown stay in-house.** Fetching and markdown extraction are the two steps
  the assignment explicitly grades, so they are not outsourced to a one-shot Jina/Firecrawl
  call: local `trafilatura` wins on extraction quality and needs no second API key.
- Out of scope (deliberate): ML injection classifiers, DLP/PII redaction, URL reputation,
  auth/rate limiting — see `docs/threat_model.md`.

## Paraphrase behaviour (worked example)

Memory-first matching is embedding-similarity, so recall depends on how the re-ask is phrased:

- **Verbatim re-ask → HIT.** "How does Redis vector search work?" asked twice → turn 2 is a
  `memory_hit` (`sim ≈ 1.0 ≥ 0.70`), answered from memory with no web call.
- **Paraphrase → depends.** "Explain how vectors are searched in Redis" embeds *near* the
  original but may fall just below 0.70 and miss — then it searches the web and ingests, so the
  *next* phrasing in that neighbourhood hits.
- **Why it improves over time.** Each page is stored with a per-page *summary* doc embedded at
  "question altitude" alongside its chunks, which raises hit rates for paraphrases that share
  intent but not wording. Lowering `SIMILARITY_THRESHOLD` trades precision for recall.

## Design decisions

See [`DECISIONS.md`](DECISIONS.md) for the standing locked-decision / anti-churn record, and
[`MODEL_CHOICES.md`](MODEL_CHOICES.md) for the two-LLM choice / cost / quality story.

## Demo transcript

A captured miss→ingest→hit session lives in
[`docs/demo_transcript.md`](docs/demo_transcript.md) (re-capture on a production key via
`python scripts/capture_demo.py`). The same behaviour is proven keylessly in CI by
`tests/e2e/test_lifecycle.py` and `scripts/eval_lifecycle.py --mock`.

## AI assistance

Built with AI assistance under a complete-disclosure rule — see [`AI_USAGE.md`](AI_USAGE.md)
(the complete instruction record) and the per-milestone prompt logs in `docs/ai_prompts/`.

## License

MIT — see `LICENSE`.
