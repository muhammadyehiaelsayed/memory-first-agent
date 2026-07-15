# Implementation Plan: Milestone 3 — Web Pipeline (Search, Fetch, Markdown, Summarize, Ingest)

**Branch**: `003-m3-web-pipeline` | **Date**: 2026-07-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-m3-web-pipeline/spec.md`

**Source documents**: `specs/milestone-3-web-pipeline.md` §3/4/6/10 (technical HOW —
authoritative for this plan), `PLAN.md` (project-authoritative), constitution v1.0.0.
Builds on Milestone 1 (closed 2026-07-05) and Milestone 2 (closed 2026-07-05, 32/32 tasks,
CI green on main).

## Summary

Build the entire web branch in `epam/memory-first-agent/` and rewire the graph so a memory
miss flows `web_search → fetch_pages → ingest_content → answer_from_web → log_turn`:
Tavily via raw httpx with keyless ddgs fallback (`web/search.py`), SSRF-guarded bounded
streaming fetch (`web/fetch.py`), trafilatura markdown gating (`web/to_markdown.py`), the
pass-through sanitizer seam (`security/sanitizer.py`, Ruling C), four real nodes, real
searcher/fetcher wired into `AgentResources`, the M2 temporary miss→`answer_failure` edge
removed, and the `ask` CLI upgraded to the canonical `[MEMORY MISS → searching the web]`
banner with web sources. Proven by the live miss→ingest→hit demo transcript
(`docs/demo_transcript.md`) plus one optional M3-owned unit file
(`tests/unit/test_to_markdown.py`) — all other §7 scenarios are M5/M6-owned automation
(Ruling A). Live work runs on GitHub Models free tier + the provided Tavily free-tier key
(Clarifications 2026-07-05; key live-verified HTTP 200).

## Technical Context

**Language/Version**: Python 3.12 (locked in M1; `uv` toolchain)

**Primary Dependencies** (ALL already pinned in M1's pyproject and installed — zero new
pins): `httpx>=0.28` (0.28.1 — search POST + streamed fetch), `trafilatura>=2.1,<3`
(2.1.0 — all five extract kwargs runtime-verified 2026-07-05), `ddgs>=9,<10` (9.14.4 —
live keyless call verified 2026-07-05, rows carry `title/href/body`), `structlog~=26.1`
(first use: `provider_used` log line), plus consumed-from-M2: `openai>=2` (summaries +
embeddings), `langchain-text-splitters` (chunker), `redisvl` (store)

**Storage**: unchanged — M1's `web_memory` index; M3 writes through M2's
`RedisMemoryStore.store()` (N `chunk:{h}:{i}` + 1 `chunk:{h}:summary` + `doc:{h}` meta,
TTL 604800) and reads freshness via `is_fresh(h)` (present since M2, hash-keyed)

**Testing**: M3 owns exactly ONE optional unit file, `tests/unit/test_to_markdown.py`
(keyless, no Docker). Search/fetch/URL-filter scenarios are M5-owned
(`test_search_retry.py`/`test_fetch_retry.py`/`test_guardrails.py`); ingest/answer/graph
lifecycle scenarios are M6-owned (`test_lifecycle.py`, `test_redis_store.py`) — Ruling A.
M3's primary proof is the live demo transcript.

**Target Platform**: local macOS dev + ubuntu CI (unchanged)

**Project Type**: single CLI project — extends the existing `src/memagent/` package

**Performance Goals**: miss turn = 1 search call + ≤5 concurrent bounded fetches + ≤5
summary calls (nano) + 1 embed batch per page + 1 answer call; per-URL wall-clock ≤ 20 s;
answer context bounded to summary + 2 chunks per page regardless of ingest volume

**Constraints**: NO retries/backoff (tenacity is M5's — plain try/except fallback only);
sanitizer is a pass-through returning `(text, [])` (M5 fills internals; `ingest_content`
frozen after M3); `log_turn` stays no-op (M4); graph entry stays `embed_query` (M5
activates guard); live calls on GitHub Models free tier (dev aliases in `.env`) + Tavily
free tier (`TAVILY_API_KEY` in git-ignored `.env`, probe-verified); answering never
depends on persistence

**Scale/Scope**: 35 FRs, 3 web modules + 1 sanitizer stub + 3 new node files + 1 node
edit, 3 file edits (`graph.py`, `app.py`, `cli.py`) + 1 additive interface edit, 1
optional test file, demo transcript + prompt log

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| P-I Memory-first routing is code | The miss branch stays deterministic: `route_after_memory`/`route_after_search`/`route_after_fetch` are the M2-delivered pure functions; the LLM never chooses a route. NOT ReAct. | PASS |
| P-II One conversion site | M3 stores vectors but never converts distance→similarity; the conversion stays inside `RedisMemoryStore.knn` (source §10 trap note: do NOT re-implement in ingest/answer). | PASS |
| P-III Single owner per concern | All numbers from `Settings` (M1 fields: SEARCH_MAX_RESULTS, FETCH_*, FRESHNESS_WINDOW_SECONDS…); module constants only where PLAN defines no env name (MIN/MAX_MARKDOWN_CHARS, SUMMARY_INPUT_CHARS, denylist, UA — source §6.8 spec note); NO retry logic anywhere (M5's tenacity seam stays clean — fallback is plain try/except). | PASS |
| P-IV JSONL single source of truth | `log_turn` remains the M2 no-op stub; `search_provider` is written to state for M4's TurnRecord — no side-channel logging beyond the structlog line. | PASS |
| P-V Sanitize before store | The seam is invoked between markdown and chunking from day one (order is the T3 defence); stored records persist `sanitizer_flags`; `wrap_context(sources, origin="web")` wraps fetched content as untrusted data. Stub internals are M5's by design (Ruling C). | PASS |
| P-VI Scope discipline | Out-of-scope list enforced: no retries (M5), no sanitizer internals (M5), no TurnLogger/classifier (M4), no e2e/eval automation (M6), no salvage route, no robots.txt, no hosted extractors, `include_raw_content=False` stays. | PASS |
| P-VII AI_USAGE per milestone | FR-035: dated `docs/ai_prompts/milestone-3.md` + `AI_USAGE.md` update — in the DoD. | PASS |
| P-VIII Zero-key testability | The one optional M3 test file runs keyless/no-Docker; CI stays green with zero keys; live demo uses free tiers (GitHub Models + Tavily free), not the paid key. | PASS |
| P-IX Evidence-based decisions | Runtime-verified 2026-07-05 and recorded in research.md: Tavily key probe (HTTP 200, result fields `content/title/url/score` → snippet mapping), ddgs live row keys `title/href/body`, trafilatura 2.1.0 kwarg support, `is_fresh(h)` signature. | PASS |
| Technology constraints | Exact stack match; raw httpx (never `tavily-python`), trafilatura in-house, ddgs fallback; zero new dependencies. | PASS |
| Workflow gates | M2 DoD green before M3 starts (verified); test ownership per Ruling A; seams B/C/D/E/F/G all stated in contracts; stub replacement changes no call sites (searcher/fetcher slots already exist in `AgentResources`). | PASS |

**Post-Phase-1 re-check (2026-07-05)**: design artifacts introduce no violations. Two
interface deltas, both recorded (research.md D4): (a) additive — `is_fresh(h)` joins the
`MemoryStore` Protocol in `interfaces.py` (existed on the concrete store since M2,
FR-M2-13, hash-keyed, zero call-site changes); (b) placeholder replacement — the M2
`PageFetcher` placeholder (`fetch(results: list[SearchResult])`, docstring "M3 fleshes
this out") takes its designed M3 signature `fetch(urls: list[str])` (analyze I1; its only
implementer `_NoopFetcher` is deleted this milestone). The `fetched_docs` two-writer note
is documented single-owner-in-time (research.md D8). PASS.

## Project Structure

### Documentation (this feature)

```text
specs/003-m3-web-pipeline/
├── spec.md              # Feature spec (+ Clarifications 2026-07-05: Tavily key provided)
├── plan.md              # This file
├── research.md          # Phase 0 — 10 consolidated decisions incl. live verifications
├── data-model.md        # Phase 1 — records M3 writes, key patterns, state deltas
├── quickstart.md        # Phase 1 — validation guide (demo lifecycle + structural checks)
├── contracts/
│   ├── web-search.md          # TavilySearcher, DdgsSearcher, FallbackProvider, web_search node
│   ├── fetch-and-markdown.md  # filter_urls, PageFetcher, to_markdown, fetch_pages node
│   ├── ingest-and-sanitize.md # sanitize stub, ingest_content order/gates/tolerances
│   └── answer-and-graph.md    # answer_from_web, graph rewiring, ask CLI banner
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root: `epam/memory-first-agent/`)

```text
src/memagent/
├── web/
│   ├── search.py       # FILL — TavilySearcher, DdgsSearcher, FallbackProvider (M1 stub → real)
│   ├── fetch.py        # FILL — filter_urls(), HttpxPageFetcher (M1 stub → real)
│   └── to_markdown.py  # FILL — to_markdown() + MIN/MAX constants (M1 stub → real)
├── security/
│   └── sanitizer.py    # FILL — sanitize() PASS-THROUGH STUB w/ M5-replacement docstring
├── nodes/
│   ├── search.py       # NEW  — web_search node (writes search_results + search_provider)
│   ├── fetch.py        # NEW  — fetch_pages node (filter → top-N → fetch)
│   ├── ingest.py       # NEW  — ingest_content node (sanitize→summary→chunk→embed→store)
│   └── answer.py       # EDIT — add answer_from_web (answer_from_memory/failure untouched)
├── interfaces.py       # EDIT — additive: is_fresh(h) joins MemoryStore Protocol (D4)
├── graph.py            # EDIT — add 4 nodes; remap miss path; remove temp edge (Ruling B)
├── app.py              # EDIT — build_resources constructs FallbackProvider + HttpxPageFetcher
│                       #        (replacing _NoopSearcher/_NoopFetcher; call sites unchanged)
└── cli.py              # EDIT — ask: canonical miss banner + web sources on miss (§6.13a)
tests/unit/test_to_markdown.py   # NEW (OPTIONAL, M3-owned) — gating invariants only
docs/demo_transcript.md          # NEW — captured two-turn miss→hit session
docs/ai_prompts/milestone-3.md   # NEW — M3 prompt log (DoD)
```

**Structure Decision**: node files follow M2's per-concern naming (`nodes/search.py`,
`nodes/fetch.py`, `nodes/ingest.py`); `answer_from_web` joins `nodes/answer.py` where the
answer family and its shared helpers (`_dedupe_sources`, prompts usage) already live —
recorded as research.md D3. `resources.py` (the frozen dataclass) is untouched: the
searcher/fetcher slots exist since M2; only `app.py`'s construction changes.

## Complexity Tracking

> No Constitution Check violations — table intentionally empty.
