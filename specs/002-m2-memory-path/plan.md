# Implementation Plan: Milestone 2 — Memory Path (Embeddings, Store, Threshold Routing, Graph Skeleton)

**Branch**: `002-m2-memory-path` | **Date**: 2026-07-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-m2-memory-path/spec.md`

**Source documents**: `specs/milestone-2-memory-path.md` §3/4/6/10 (technical HOW —
authoritative for this plan), `PLAN.md` (project-authoritative), constitution v1.0.0.
Builds on Milestone 1 (closed 2026-07-05, 22/22 tasks, CI green).

## Summary

Build the memory-first read path in `epam/memory-first-agent/`: canonical typed state
(`state.py` + the two turn-bookkeeping channels), DI Protocols, frozen `AgentResources`,
all five pure routers, the one-site distance→similarity conversion inside
`RedisMemoryStore.knn`, chunker + URL canonicalization, thin OpenAI clients
(`max_retries=0`, GitHub Models `base_url` support), fixed prompts API, a compiled
LangGraph graph running the hit path end-to-end (temporary no-op `log_turn`, temporary
miss→`answer_failure` edge), the `Agent` facade, a seed script, and the wired
`memagent ask` with `[MEMORY HIT sim=0.XX]` banners. Proven by three M2-owned unit test
files (routing boundary, similarity conversion, chunker invariants) plus the live seeded
demo on the **GitHub Models free tier** (Clarifications 2026-07-05).

## Technical Context

**Language/Version**: Python 3.12 (locked in M1; `uv` toolchain)

**Primary Dependencies** (all already pinned in M1's pyproject): `langgraph>=1.2,<2`
(StateGraph), `langchain-text-splitters` (chunker), `redisvl>=0.22,<0.24` (0.23.0
installed; `VectorQuery`/`load(ttl=)`/`array_to_buffer` verified present at M1),
`redis>=6.2,<7`, `openai>=2` (AsyncOpenAI), `pydantic>=2.11`, `typer`, `rich`

**Storage**: M1's `web_memory` index (FLAT/cosine/float32/1536, HASH, prefix `chunk:`);
keys `chunk:{url_hash}:{i}` + optional `chunk:{url_hash}:summary` (indexed) +
non-indexed `doc:{url_hash}` meta; per-key `EXPIRE` TTL 604800 (0 disables)

**Testing**: M2 owns exactly `tests/unit/test_routing.py`, `test_similarity.py`,
`test_chunker.py` (keyless, no Docker). Node/graph/facade scenarios are typed @unit in the
source §7 but are **authored in M6** with its conftest fakes (Ruling A); within M2 they are
verified by the live demo.

**Target Platform**: local macOS dev + ubuntu CI (unchanged from M1)

**Project Type**: single CLI project — extends the existing `src/memagent/` package

**Performance Goals**: seeded hit answers in a single graph pass (embed → KNN → one LLM
call); KNN is exact top-5 at demo scale

**Constraints**: live calls run on GitHub Models free tier (`OPENAI_BASE_URL` + fine-grained
PAT with `models: read`; daily rate limits acceptable for dev); unit tests keyless;
`AsyncOpenAI(max_retries=0, timeout=45.0)` — no retry logic anywhere (tenacity is M5's);
threshold comparison stays `>= threshold` (epsilon variant only if the boundary test flakes)

**Scale/Scope**: 26 FRs, ~15 new/edited source files, 3 unit-test files, 1 seed script,
2 live verification calls

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| P-I Memory-first routing is code | The hit/miss decision is `route_after_memory` — a pure function unit-tested at the boundary table; the LLM is only called *after* routing decides. NOT a ReAct step. | PASS |
| P-II One conversion site | `distance_to_similarity()` lives in `memory/store.py`, called inside `knn` only; the `memory_search` node reads, never re-derives. Boundary + not-1−d/2 tests included. | PASS |
| P-III Single owner per concern | All numbers from `Settings`; types once in `state.py` (Route closed 5-set); `AsyncOpenAI(max_retries=0)` keeps retry ownership free for M5's tenacity; one call-site per client (Ruling D seam). | PASS |
| P-IV JSONL single source of truth | `log_turn` remains a NO-OP stub (M4 owns the real TurnLogger); no logging side-channel introduced. | PASS |
| P-V Sanitize before store | M2 stores only operator-seeded content (`flags=[]`); `store()` already persists `sanitizer_flags`/`content_sha256`; retrieved content is wrapped as `<untrusted_context>` data with the API fixed for M5's hardening (Ruling E). | PASS |
| P-VI Scope discipline | No 0.50 salvage, no embed-failure→web (fails cleanly), `knn` contractually unfiltered, `history=[]` (no session memory), miss branch temporarily → `answer_failure` exactly as Ruling B prescribes. | PASS |
| P-VII AI_USAGE per milestone | FR-026: dated M2 prompt log appended + linked from AI_USAGE.md — in the DoD. | PASS |
| P-VIII Zero-key testability | The three M2 unit files run with zero keys/Docker; CI stays green; the live demo uses the free tier, not paid keys. | PASS |
| P-IX Evidence-based decisions | FR-025 records live pass/fail for catalogue ids + `temperature=0`; redisvl signatures already runtime-verified at M1. | PASS |
| Technology constraints | Exact stack match; no new dependencies (all pins landed in M1). | PASS |
| Workflow gates | M1 DoD green before M2 starts (verified); test ownership per Ruling A; all seams (B/D/E/F + conversion site + prompts API) stated in contracts. | PASS |

**Post-Phase-1 re-check (2026-07-05)**: design artifacts introduce no violations — the
conversion site stays single, the store never filters, stubs match Ruling B's table, and the
two added state channels are documented single-writer bookkeeping (research.md D2). PASS.

## Project Structure

### Documentation (this feature)

```text
specs/002-m2-memory-path/
├── spec.md              # Feature spec (+ Clarifications 2026-07-05: GitHub Models free dev)
├── plan.md              # This file
├── research.md          # Phase 0 — 11 consolidated decisions
├── data-model.md        # Phase 1 — AgentState, records, Route, TurnResult, key patterns
├── quickstart.md        # Phase 1 — validation guide (unit tests + live seeded demo)
├── contracts/
│   ├── state-and-routing.md   # state.py, Route, StepError, routers, boundary semantics
│   ├── memory-store.md        # knn/store/is_fresh, vector-alignment, upsert, TTL
│   ├── llm-and-prompts.md     # clients (thin, seams to M4/M5), prompts fixed API
│   └── graph-and-facade.md    # build_graph wiring, Agent.answer, TurnResult, ask CLI, seed script
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root: `epam/memory-first-agent/`)

```text
src/memagent/
├── state.py            # NEW  — AgentState + records + Route + StepError (canonical)
├── interfaces.py       # NEW  — Embedder/CompletionResult/ChatLLM/WebSearcher/MemoryStore
│                       #        (+ minimal PageFetcher/TurnLogger placeholder Protocols)
├── resources.py        # NEW  — frozen AgentResources (from __future__ import annotations)
├── routers.py          # NEW  — all 5 pure routers (verbatim)
├── graph.py            # NEW  — hit-path wiring + log_turn no-op + temp miss→failure
├── app.py              # NEW  — build_resources() + Agent.answer() → TurnResult
├── cli.py              # EDIT — ask wired to Agent.answer with banners
├── nodes/
│   ├── embed.py        # NEW  — embed_query
│   ├── memory.py       # NEW  — memory_search
│   ├── answer.py       # NEW  — answer_from_memory, answer_failure
│   └── log.py          # NEW  — log_turn no-op stub (M4 replaces)
├── memory/
│   ├── store.py        # NEW  — RedisMemoryStore + distance_to_similarity + is_fresh
│   ├── chunking.py     # NEW  — chunk_markdown (1600/200, floor 100, cap 25)
│   └── urls.py         # NEW  — canonicalize, url_hash
├── llm/
│   ├── clients.py      # NEW  — OpenAIEmbedder(settings), OpenAIChatLLM(settings, model)
│   └── prompts.py      # NEW  — build_system_prompt(), wrap_context(sources, origin) [API FINAL]
└── analytics/
    └── classify.py     # NEW  — QueryClassification schema ONLY (M4 adds classifier fn)
scripts/seed_memory.py  # NEW
tests/unit/test_routing.py     # NEW (M2-owned)
tests/unit/test_similarity.py  # NEW (M2-owned)
tests/unit/test_chunker.py     # NEW (M2-owned)
```

**Structure Decision**: per-node filenames follow the source §6.1 minimal-assumption layout
(spec-noted as changeable); everything else is the fixed §10.2 tree. M1 stubs are replaced
in place — no call-site changes (constitution workflow gate).

## Complexity Tracking

> No Constitution Check violations — table intentionally empty.
