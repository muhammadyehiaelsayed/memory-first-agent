# Memory-First Web Agent

A GenAI agent that answers from **Redis vector memory first** (similarity ≥ 0.7, checked in
code — not by the model), falls back to **web search** on a miss, ingests what it finds for
future reuse, and returns **grounded answers with source URLs**.

> **Zero keys needed:** `make test` and `python scripts/eval_lifecycle.py --mock` (CI runs exactly these).
> **One key** (`OPENAI_API_KEY`) **+ Docker** for the live demo; `TAVILY_API_KEY` optional (keyless DuckDuckGo fallback).
>
> Quickstart: clone -> install uv -> `make setup` (uv sync + .env) -> `make redis-up` -> `make run`.

## Quickstart

```bash
make setup       # uv sync + create .env from .env.example
make redis-up    # redis:8.2 + RedisInsight (http://localhost:5540)
make run         # chat REPL (wired in M4; stub until then)
uv run memagent wipe-memory   # create/reset the web_memory vector index
make test        # unit tests - zero keys, zero docker
```

No uv? `pip install -e ".[dev]"` inside a Python 3.12 venv works as a fallback
(uv + the committed `uv.lock` is the reproducible path).

## Status

Milestone 1 of 6 — repo scaffold, toolchain, and the `web_memory` Redis vector index
(FLAT/cosine/float32/1536) with a working `memagent wipe-memory`. The agent itself
(memory path, web pipeline, analytics, guardrails, evals) lands in M2–M6.

Verified at M1 (2026-07-05): `redis:8.2` ships FT.* in core; redisvl 0.23.0 provides
`load(ttl=)`, `array_to_buffer`, and `VectorQuery` (no EXPIRE fallback needed).

## Architecture

_To be filled in M6: auto-generated LangGraph mermaid diagram (`scripts/render_graph.py`),
component notes._

## Design decisions

See `DECISIONS.md` (scaffold — finalized in M6) and, from M4, `MODEL_CHOICES.md` for the
two-LLM choice/cost/quality story.

## Security & reliability

_To be filled in M5/M6: threat model T1–T4, three guardrail layers with
sanitize-before-store as the centerpiece, retry/degradation matrix._

## Limitations

_To be filled in M6 (stated honestly: robots.txt, TTL staleness policy, threshold
calibration note, and the named production upgrades)._

## Demo transcript

_To be filled in M6: captured miss→ingest→hit session (`docs/demo_transcript.md`)._

## AI assistance

Built with AI assistance under a complete-disclosure rule — see `AI_USAGE.md` and the
per-milestone prompt logs in `docs/ai_prompts/`.

## License

MIT — see `LICENSE`.
