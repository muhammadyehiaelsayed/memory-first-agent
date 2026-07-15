# Milestone 2 — Memory path (embeddings, store, KNN, threshold routing, graph skeleton)

| Estimated effort | Depends on | Enables | PLAN.md sections covered |
|---|---|---|---|
| 4–5 h | M1 (repo scaffold, `config.py`/`Settings`, `memory/schema.py` + index create/wipe, Typer stubs, docker-compose `redis:8.2`) | M3 (web path plugs into the miss branch), M4 (two-LLM finalisation + `log_turn`), M5 (guard node, degradation, tenacity wrapping) | 2, 2.1, 3 (all), 4.2, 4.3, 4.4, 6 (embeddings + GitHub Models free-dev), 12 (unit tests), 13 (M2 row), 14 (GitHub Models + `temperature=0` rows) |

---

## 1. Goal & context

This milestone builds the **memory-first read path**: everything needed to embed a query, look it up in Redis vector memory, decide with a deterministic threshold whether that is a hit, and answer from memory when it is. It also lays the **structural spine** the remaining milestones bolt onto — the canonical typed state, the dependency-injection Protocols, the frozen resources container, all five pure router functions, and a compiled LangGraph graph that runs end-to-end for the hit path.

Why it exists: the assignment's core, graded behaviour is "embed the query, vector-search Redis first; if similarity ≥ 0.7 answer from memory only, with the stored metadata." M2 delivers exactly that read half and proves it with a seeded document. The write half (web search → fetch → ingest) arrives in M3 and plugs into the miss branch this milestone deliberately leaves as a temporary stub.

Assignment requirements advanced:
- "Embed query, vector search Redis first" → `embed_query` + `memory_search` nodes over redisvl KNN.
- "similarity ≥ 0.7 → answer from memory only, with stored metadata" → `route_after_memory` (inclusive `>=`) + `answer_from_memory` citing stored `url`/`title`.
- "Grounded answer with source URLs" → `sources: list[SourceRef]` + a "Sources:" section from the basic system prompt.
- The #1 correctness trap ("similarity = 1 − vector_distance") is isolated to a single, unit-tested conversion site.

Demoable outcome (PLAN §13, M2 row): after running `scripts/seed_memory.py`, `memagent ask "<seeded question>"` prints `[MEMORY HIT sim=0.87]` plus the stored metadata (source URL/title); an unseeded question takes the temporary miss branch to a deterministic response.

---

## 2. Scope

### In scope
- `state.py` — the **verbatim** PLAN §3.1 `AgentState` plus `MemoryHit`, `SearchResult`, `FetchedDoc`, `Chunk`, `SourceRef` TypedDicts, the `Route` enum (PLAN §2.1), and the `StepError` record type.
- `interfaces.py` — the **verbatim** PLAN §3.4 Protocols: `Embedder`, `ChatLLM` (with `CompletionResult`), `WebSearcher`, `MemoryStore`. `MemoryStore.knn()` returns the **raw unfiltered top-k** with similarity attached; threshold filtering never lives here.
- `resources.py` — the frozen `AgentResources` dataclass (PLAN §3.4).
- `routers.py` — **all five** pure router functions (PLAN §3.3), even the three that only activate later (Ruling B).
- `llm/clients.py` — `Embedder` implementation (`AsyncOpenAI` embeddings, `max_retries=0`, `timeout=45.0`, thin wrapper seam per Ruling D) + a basic `ChatLLM` wrapper whose `complete()` is production-grade enough for the answer path.
- `llm/prompts.py` — `build_system_prompt()` and `wrap_context()` with **minimal** `<untrusted_context>` wrapping; this module's API is fixed here and finalised in M5 (Ruling E).
- `memory/store.py` — redisvl `AsyncSearchIndex`: `knn` top-5 attaching `similarity = 1 − distance` at the **one** conversion site; `store` with per-key `EXPIRE` TTL; upsert cleanup via `doc:{hash}.num_chunks`; a freshness-check helper.
- `memory/chunking.py` — `RecursiveCharacterTextSplitter`, 1600/200, min 100, max 25/page, markdown separators.
- `memory/urls.py` — canonical URL (strip `utm_*` + fragment, lowercase scheme/host); `url_hash = sha256(canonical)[:16]`.
- Nodes: `embed_query`, `memory_search`, `answer_from_memory`, `answer_failure`.
- `graph.py` — partial wiring: one compiled async `StateGraph`, entry `embed_query`, a **temporary no-op `log_turn` stub**, and a **temporary miss → `answer_failure`** edge (Ruling B).
- `app.py` — the `Agent` facade: `build_resources()` + `async answer(q) -> TurnResult`, passing **empty** history.
- CLI: wire `memagent ask "…"` (an echo stub in M1) to `Agent.answer`, printing the hit/miss banner + stored metadata.
- `scripts/seed_memory.py` — embed + store a supplied text/URL so a hit is demoable.
- Unit tests (M2-owned, Ruling A): `tests/unit/test_routing.py`, `tests/unit/test_similarity.py`, `tests/unit/test_chunker.py`.
- M2 verification duty (PLAN §14): one live GitHub Models call confirming the free-dev catalog ids, and one live call confirming `temperature=0` on `gpt-5.4-mini` (Part 7 checklist).
- AI-assistance disclosure: append this milestone's prompts to `docs/ai_prompts/`.

### Out of scope (owned by other milestones)
- `web/search.py`, `web/fetch.py`, `web/to_markdown.py`, and nodes `web_search`, `fetch_pages`, `ingest_content`, `answer_from_web` — **M3**. M2 only leaves the miss-branch seam.
- Per-page nano summaries and `doc_type="summary"` ingestion — **M3** (though the `store()` signature and index schema already accommodate them).
- Real `log_turn`, `TurnLogger`/JSONL, `classify.py`, the `analytics` CLI, per-stage latency `timed()` wrapper, token plumbing into the turn log, `chat` REPL history — **M4**. M2 ships only a no-op `log_turn` stub.
- `guard_input` node, `route_after_guard` activation, L1 input screen, L2 prompt hardening (provenance headers, tag-breakout escape, cite-only rules), L3 sanitizer internals — **M5**. In M2 the graph entry is `embed_query` and `guard_verdict` defaults to `"allow"` (Ruling F).
- `utils/reliability.py` tenacity policies, typed errors, the degradation matrix, and Redis-down graceful handling — **M5**. Until then clients rely on the SDK timeout only (Ruling D). `test_search_retry`, `test_fetch_retry`, `test_sanitizer`, `test_guardrails` are M5-owned.
- `tests/conftest.py` fixtures (`FakeLLM`, `FakeEmbedder`, zero-wait settings, `redis_url` skip fixture, `clean_index`), `tests/integration/test_redis_store.py`, `tests/e2e/test_lifecycle.py`, `scripts/eval_lifecycle.py`, `scripts/eval_grounding.py` — **M6**. These *exercise* M2 code but are authored in M6.
- `memory/schema.py` (index definition, create-if-missing, `wipe-memory`) — **M1**. M2 consumes it.

### Deferred by design (anti-churn — do not add here or anywhere)
- **0.50 "weak-memory salvage" route** and the **embed-failure → web** route (PLAN §2.1). Embeddings and the LLM share one provider — an embed failure fails the turn cleanly (`route="failed"`), it does not fall through to the web.
- **Filtering inside the store.** `knn()` is contractually raw top-k; a store that filtered by threshold broke every degraded path in review (PLAN §3.4). Threshold logic lives only in routers/nodes.
- **Deep session memory / conversation memory.** M2 passes empty history; REPL history (last 6 turns) is M4. Do not conflate REPL history with the Redis knowledge memory that is the assignment's point.
- **Redis turn-log mirror, canary tokens, output URL-defang allowlist, coverage gates, token streaming, `GUARD_LLM_CHECK`** — rejected repeatedly (PLAN §13, DECISIONS anti-churn). None are M2 concerns; do not "helpfully" add them.

---

## 3. Prerequisites & interfaces consumed

Must already exist from **M1**:

- `memagent.config.Settings` (pydantic-settings) — the single source of every number/env name. M2 reads: `openai_api_key`, `openai_base_url`, `conversation_model` (`gpt-5.4-mini`), `analytics_model` (`gpt-5.4-nano`), `embedding_model` (`text-embedding-3-small`), `embedding_dim` (`1536`), `redis_url`, `memory_index_name` (`web_memory`), `similarity_threshold` (`0.7`), `memory_top_k` (`5`), `memory_ttl_seconds` (`604800`), `freshness_window_seconds` (`86400`), `chunk_size_chars` (`1600`), `chunk_overlap_chars` (`200`), `max_chunks_per_page` (`25`), `llm_timeout_s` (`45`). (`.env.example` in PLAN §10.3 is the canonical list.)
- `memagent.memory.schema` — the redisvl `IndexSchema` for index `web_memory`, prefix `chunk:`, plus create-if-missing and drop-and-recreate (`wipe-memory`). Startup asserts `embedder.dim == index dims`. M2's `store.py` opens an `AsyncSearchIndex` against this schema. If the redisvl `load(ttl=)` / `array_to_buffer` / `VectorQuery` signatures differ from expectation at M1, the documented fallback is an explicit `EXPIRE` pipeline (PLAN §14).
- A running `redis:8.2` container (docker-compose from M1) for the live demo and M6 integration/e2e tests. Unit tests need no Redis.
- Typer app in `cli.py` with an `ask` subcommand stub (echoes) — M2 replaces its body.
- `.python-version`, `pyproject.toml` with the runtime pins (PLAN §10.1), `uv.lock`.

Cross-milestone seams that touch M2 (state these so files interlock):
- **Ruling A (test-file ownership):** each test file has exactly one owning milestone. M2 owns `tests/unit/test_routing.py`, `test_similarity.py`, `test_chunker.py`; `tests/conftest.py` fixtures (`FakeLLM`, `FakeEmbedder`, `clean_index`, zero-wait settings, `redis_url` skip), `tests/integration/test_redis_store.py`, and `tests/e2e/test_lifecycle.py` are **M6-owned** (see §2). Node/graph/facade behaviour is exercised by M6's tests using those fakes; M2's own automated proof is the three unit files plus the manual demo.
- **Ruling D (LLM client seam):** the wrapper seam — exactly one call-site per client — must exist from M2 so M5's tenacity wrapping is a drop-in. M2 ships `Embedder` fully and `ChatLLM.complete()` fully; `ChatLLM.parse()`, usage plumbing, `temperature=0` validation against the pinned id, and `max_tokens` (2048/256) are finalised in M4.
- **Ruling E (prompt seam):** `llm/prompts.py`'s API (`build_system_prompt`, `wrap_context`) is **fixed in M2**; the full L2 hardening lands in M5 without changing that API.
- **Ruling F (guard seam):** no `guard_input` node in M2; graph entry is `embed_query`; `guard_verdict` defaults to `"allow"`.
- **Ruling B (graph-evolution seam):** M2 wires a temporary no-op `log_turn` and temporarily routes the miss branch to `answer_failure`.

---

## 4. Interfaces provided

Contracts this milestone exposes to later milestones. Signatures are the fixed public surface; see §6 for full bodies.

- **`memagent.state`** — `AgentState`, `Route`, `MemoryHit`, `SearchResult`, `FetchedDoc`, `Chunk`, `SourceRef`, `StepError`. Every later node reads/writes these fields; single-writer discipline (only `errors`/`latency_ms`/`tokens` are reduced). `AgentState` also carries the single-writer channels `turn_started_at` (stamped by `Agent.answer`/REPL) and `search_provider` (written by M3's `web_search`), added for the M4 turn log (§6.2 spec note).
- **`memagent.interfaces`** — `Embedder`, `CompletionResult`, `ChatLLM`, `WebSearcher`, `MemoryStore` Protocols. M3 implements `WebSearcher`/`PageFetcher`; M4 finalises `ChatLLM.parse()`; test fakes (M6) satisfy `Embedder`/`ChatLLM`.
- **`memagent.resources.AgentResources`** — frozen container passed to `build_graph(resources)`. M2 populates `settings`, `memory`, `embedder`, `chat_llm`, `analytics_llm` with real objects and `searcher`, `fetcher`, `turn_logger` with **stubs** (see spec note in §6.3) that M3/M4 replace.
- **`memagent.routers`** — `route_after_guard`, `route_after_embed`, `route_after_memory`, `route_after_search`, `route_after_fetch`. All five are pure and unit-tested now; the graph only wires `route_after_embed` and `route_after_memory` in M2. M3 wires `route_after_search`/`route_after_fetch`; M5 wires `route_after_guard`.
- **`memagent.memory.store.RedisMemoryStore`** — implements `MemoryStore`; `store()` already accepts summary docs so M3 need not change the signature. Module-level pure helper `distance_to_similarity(distance) -> float`. A freshness helper (`is_fresh(url_hash) -> bool`) shipped now, consumed by M3's `ingest_content`.
- **`memagent.memory.chunking.chunk_markdown(text) -> list[str]`** — used by `seed_memory.py` now and `ingest_content` in M3.
- **`memagent.memory.urls`** — `canonicalize(url) -> str`, `url_hash(url) -> str`.
- **`memagent.llm.prompts`** — `build_system_prompt() -> str`, `wrap_context(sources, origin) -> str`. **Both signatures are the FINAL public API fixed here (Ruling E)** — including `wrap_context`'s `origin` argument (`"memory"`/`"web"`), so M5's L2 hardening is a pure body swap. `answer_from_memory` (M2) calls `wrap_context(memory_hits, origin="memory")`; M3's `answer_from_web` calls `wrap_context(sources, origin="web")`.
- **`memagent.graph.build_graph(resources) -> CompiledGraph`** — one compiled async `StateGraph`. `draw_mermaid()` works on it (M6 renders it into the README).
- **`memagent.app`** — `build_resources(settings: Settings | None = None) -> AgentResources` (falls back to `Settings()` when `settings is None`, so `build_resources()` works for graph-inspection commands), `Agent` with `async answer(q) -> TurnResult`. `TurnResult` is a `NamedTuple(route: str, answer: str | None, sources: list[SourceRef], similarity: float | None)`. Used by the CLI (`ask` now, `chat` in M4) and M6 e2e tests.

**Temporary stubs delivered by M2 (and their replacement milestone):**

| Stub | Behaviour in M2 | Replaced by |
|---|---|---|
| `log_turn` node | no-op (returns `{}`) | M4 real `TurnLogger`/JSONL node |
| miss-branch edge | `route_after_memory`'s `"web_search"` return value is mapped to the `answer_failure` node via the graph path-map | M3 (maps to real `web_search` → `fetch_pages` → …) |
| `AgentResources.searcher` | no-op `WebSearcher` returning `[]` | M3 real Tavily/ddgs searcher |
| `AgentResources.fetcher` | no-op / unused placeholder | M3 real `PageFetcher` |
| `AgentResources.turn_logger` | no-op logger | M4 real `TurnLogger` |
| `ChatLLM.parse()` | basic structured-output call, not yet validated | M4 finalisation |

---

## 5. Functional requirements

Each is one testable statement with an explicit acceptance criterion.

- **FR-M2-01** — `state.py` defines the §3.1 `AgentState` (plus the two turn-bookkeeping channels `turn_started_at`/`search_provider` of §6.2) and the `MemoryHit`/`SearchResult`/`FetchedDoc`/`Chunk`/`SourceRef` TypedDicts and `StepError`. *Accept:* `from memagent.state import AgentState, Route, MemoryHit, SearchResult, FetchedDoc, Chunk, SourceRef, StepError` imports without error, and `typing.get_type_hints(AgentState)` resolves (all referenced names importable).
- **FR-M2-02** — `Route` is the closed 5-value `Literal` `memory_hit | memory_miss_web_search | degraded_web | blocked | failed` (a `typing.Literal` alias, not an `Enum`). *Accept:* `set(typing.get_args(Route)) == {"memory_hit", "memory_miss_web_search", "degraded_web", "blocked", "failed"}`; that no other value type-checks is a mypy-level (static-typing) property, not a runtime assertion.
- **FR-M2-03** — `interfaces.py` defines the verbatim §3.4 `Embedder`, `ChatLLM` (+`CompletionResult`), `WebSearcher`, `MemoryStore` Protocols, with `MemoryStore.knn()` documented and typed as raw unfiltered top-k. *Accept:* Protocols importable; `knn(vector, k)` return-annotated `list[MemoryHit]`; no threshold parameter exists on `knn`.
- **FR-M2-04** — `resources.py` defines `AgentResources` as a `@dataclass(frozen=True)` with the eight §3.4 fields. *Accept:* assigning to any field after construction raises `dataclasses.FrozenInstanceError`.
- **FR-M2-05** — `routers.py` implements all five pure functions verbatim (§3.3). *Accept:* each is importable and side-effect-free (no I/O); called twice with the same input returns the same output.
- **FR-M2-06** — `route_after_memory` returns `"answer_from_memory"` iff `top_similarity is not None and top_similarity >= threshold`, else `"web_search"`. *Accept:* the boundary table in §7 (0.70@0.70 → hit, 0.6999 → miss, `None` → miss, 1.0 → hit, 0.0 → miss) holds.
- **FR-M2-07** — the distance→similarity conversion is `similarity = 1.0 − vector_distance` (not `1 − d/2`) and lives in exactly one place, `distance_to_similarity()` in `memory/store.py`, called inside `knn`. *Accept:* `distance_to_similarity(0.30) == 0.70` (within the documented epsilon); `grep -rn "1\.0 - distance" src/ --include=*.py | grep -v '#'` shows the subtraction (the `return 1.0 - distance` line in `distance_to_similarity`) in exactly one module (`memory/store.py`), excluding the verbatim `MemoryHit` comment.
- **FR-M2-08** — `OpenAIEmbedder` implements `Embedder` using `AsyncOpenAI(max_retries=0, timeout=45.0)` (optional `base_url` from `OPENAI_BASE_URL`), `dim == embedding_dim` (1536), `embed(texts)` returns one 1536-float vector per input in order. *Accept:* `embedder.dim == 1536`; `len(await embedder.embed(["a","b"])) == 2` and each vector has length 1536.
- **FR-M2-09** — `OpenAIChatLLM` implements `ChatLLM.complete(system, messages)` returning `CompletionResult(text, usage)` where `usage` carries `model`, `input_tokens`, `output_tokens`. *Accept:* `complete()` returns a non-empty `text` and a `usage` dict with those keys. (`parse()` exists but is finalised in M4.)
- **FR-M2-10** — `RedisMemoryStore.knn(vector, k)` returns up to `k` (`MEMORY_TOP_K=5`) `MemoryHit`s ordered by descending similarity, each with `similarity` attached and no threshold filtering; an empty index returns `[]`. *Accept:* against a seeded index the nearest chunk is first; against an empty index the result is `[]` (not an error).
- **FR-M2-11** — `RedisMemoryStore.store(page, chunks, vectors, source_query, flags)` writes keys `chunk:{url_hash}:{i}` (chunks) and, when a summary is provided (`page["summary"]` not `None`; `vectors[0]` embeds it, `vectors[1:]` align to chunks — §6.7), `chunk:{url_hash}:summary`, plus non-indexed meta `doc:{url_hash}` (`num_chunks`, `fetched_at`, `url`); each `chunk:` key gets `EXPIRE MEMORY_TTL_SECONDS` when that value `> 0` (0 disables). *Accept:* after `store`, `TTL chunk:{hash}:0` is > 0 and ≤ 604800 by default; with `MEMORY_TTL_SECONDS=0` no TTL is set.
- **FR-M2-12** — upsert cleanup: before writing a page already present, `store` deletes all `chunk:{hash}:*` using the old `doc:{hash}.num_chunks` count. *Accept:* re-storing the same URL with fewer chunks leaves no stale `chunk:{hash}:{i}` keys beyond the new `num_chunks` (plus optional `:summary`).
- **FR-M2-13** — `is_fresh(url_hash)` returns `True` when `doc:{hash}.fetched_at` is younger than `FRESHNESS_WINDOW_SECONDS` (86400), else `False` (missing doc → `False`). Helper shipped now, consumed by M3. *Accept:* a doc fetched 1 h ago → `True`; 48 h ago → `False`; absent → `False`.
- **FR-M2-14** — `chunk_markdown(text)` uses `RecursiveCharacterTextSplitter` with markdown separators, `chunk_size=1600`, `chunk_overlap=200`, drops chunks shorter than 100 chars, caps at 25 chunks/page, and never returns an empty-string chunk. *Accept:* the invariants in §7's chunker feature hold, including unicode and short-doc cases.
- **FR-M2-15** — `canonicalize(url)` lowercases scheme+host, strips the fragment and all `utm_*` query parameters; `url_hash(url) = sha256(canonicalize(url).encode())[:16]` (hex). *Accept:* `HTTP://Example.com/a?utm_source=x#frag` and `http://example.com/a` produce the same canonical string and the same 16-char hash.
- **FR-M2-16** — `embed_query` node embeds `sanitized_query` (which equals `query` in M2) and sets `query_vector`; on any embedding error it sets `query_vector = None` and records a `StepError`, so `route_after_embed` sends the turn to `answer_failure`. *Accept:* success → `query_vector` length 1536; forced embed error → `query_vector is None` and route resolves to `answer_failure`.
- **FR-M2-17** — `memory_search` node calls `memory.knn(query_vector, MEMORY_TOP_K)`, stores `memory_hits`, and sets `top_similarity` to the highest returned similarity (or `None` when no hits). It performs no threshold comparison. *Accept:* seeded near-duplicate → `top_similarity` set and ≥ 0.70; empty index → `memory_hits == []` and `top_similarity is None`.
- **FR-M2-18** — `answer_from_memory` node calls `chat_llm.complete()` over the `memory_hits` wrapped by `wrap_context(memory_hits, origin="memory")`, sets `route="memory_hit"`, `answer`, and `sources` (deduped by URL, `origin="memory"`), and the answer ends with a "Sources:" section. *Accept:* with hits present, `route == "memory_hit"`, every `sources[i].origin == "memory"`, and the rendered answer contains "Sources:".
- **FR-M2-19** — `answer_failure` node sets `route="failed"`, writes a deterministic apology into `answer`, makes **no** LLM call, and never raises. *Accept:* returns the fixed apology string; the injected `chat_llm` records zero calls; passing malformed state does not raise.
- **FR-M2-20** — `llm/prompts.py` exposes `build_system_prompt() -> str` and `wrap_context(sources, origin) -> str`; the system prompt states that `<untrusted_context>` content is data-not-instructions and that the answer must end with "Sources:"; `wrap_context` wraps each source under a `source_url` header inside `<untrusted_context>` and records the `origin`. Both signatures — including `wrap_context`'s `origin` arg — are the FINAL fixed public API (Ruling E); M5 hardens only the bodies. *Accept:* `build_system_prompt()` mentions "untrusted_context" and "Sources:"; `wrap_context([hit], "memory")` contains `<untrusted_context>` and the hit's URL.
- **FR-M2-21** — `graph.build_graph(resources)` compiles one async `StateGraph` with entry `embed_query`, nodes `embed_query`/`memory_search`/`answer_from_memory`/`answer_failure`/`log_turn`(no-op), the miss branch temporarily mapped to `answer_failure`, and every §2.1 answer path terminating at `log_turn → END`. *Accept:* `build_graph(resources)` returns a compiled graph; `compiled.get_graph().draw_mermaid()` returns a non-empty string; `await compiled.ainvoke(initial_state)` completes for both hit and miss inputs.
- **FR-M2-22** — `app.Agent.answer(q)` builds the initial state (`turn_id=uuid4()`, `session_id`, `query=q`, `history=[]`, `threshold=settings.similarity_threshold`, `guard_verdict="allow"`, `sanitized_query=q`, `skip_store=False`, `turn_started_at=time.perf_counter()`, `search_provider=None`), invokes the graph, and returns `TurnResult(route, answer, sources, similarity)` from the final state. *Accept:* against a seeded hit, `answer()` returns `route="memory_hit"` and `similarity >= 0.70`; history passed to the graph is empty.
- **FR-M2-23** — `scripts/seed_memory.py` accepts a text (or file) and a URL, canonicalises the URL, chunks the text, embeds the chunks, and stores them via `RedisMemoryStore`, so a subsequent KNN of the same text is a hit. *Accept:* after seeding, `Agent.answer("<seeded question>")` is `memory_hit`.
- **FR-M2-24** — `memagent ask "…"` calls `Agent.answer`, prints a hit banner `[MEMORY HIT sim=0.XX]` (or a `[MEMORY MISS]` banner on the temporary miss path) followed by the answer and the stored source metadata (URL + title). *Accept:* seeded question → banner shows `sim>=0.70` and lists the seeded URL; unseeded question → `[MEMORY MISS]` banner + deterministic response.
- **FR-M2-25** (verification duty, PLAN §14) — one live GitHub Models call confirms the free-dev catalog ids resolve (`openai/gpt-5.4-mini`, `openai/gpt-5.4-nano`, a `text-embedding-3-small`-equivalent id) via `OPENAI_BASE_URL` + a GitHub PAT; one live call confirms `temperature=0` is accepted by `gpt-5.4-mini`. *Accept:* both results recorded in `docs/ai_prompts/` / commit notes (id strings + pass/fail), with any id corrections landing in `.env.example`/`Settings` defaults.
- **FR-M2-26** — AI-assistance disclosure for M2 is appended (not retroactive) to `docs/ai_prompts/` and referenced from `AI_USAGE.md`. *Accept:* a dated M2 prompt-log file exists and `AI_USAGE.md` links it.

---

## 6. Technical specification

Self-contained: a competent developer new to this repo builds M2 from this section without opening PLAN.md. All numbers, ids, and pins are copied verbatim from PLAN.md.

### 6.1 File layout added/edited in M2

```
src/memagent/
├── state.py            # NEW — canonical types (this milestone)
├── interfaces.py       # NEW — Protocols
├── resources.py        # NEW — frozen AgentResources
├── routers.py          # NEW — 5 pure routers
├── graph.py            # NEW — partial wiring (hit path + stubs)
├── app.py              # NEW — Agent facade + build_resources()
├── cli.py              # EDIT — wire `ask` to Agent.answer
├── nodes/
│   ├── embed.py        # NEW — embed_query
│   ├── memory.py       # NEW — memory_search
│   ├── answer.py       # NEW — answer_from_memory, answer_failure
│   └── log.py          # NEW — log_turn no-op stub
├── memory/
│   ├── store.py        # NEW — RedisMemoryStore + distance_to_similarity + is_fresh
│   ├── chunking.py     # NEW — chunk_markdown
│   └── urls.py         # NEW — canonicalize, url_hash
│   # schema.py already exists from M1
├── llm/
│   ├── clients.py      # NEW — OpenAIEmbedder, OpenAIChatLLM
│   └── prompts.py      # NEW — build_system_prompt, wrap_context (API fixed here)
├── analytics/
│   └── classify.py     # NEW — QueryClassification schema only (M4 adds the classifier fn); see §6.2 note
scripts/seed_memory.py  # NEW
tests/unit/test_routing.py     # NEW (M2-owned)
tests/unit/test_similarity.py  # NEW (M2-owned)
tests/unit/test_chunker.py     # NEW (M2-owned)
```

> **Spec note:** PLAN §3.2 groups the 10 nodes "one file per §3.2 group"; the exact per-node filenames above are a minimal-assumption default (change freely). The only fixed requirement is that the node functions are importable and injected into `build_graph`.

### 6.2 `state.py` — verbatim §3.1 (with the two undefined names resolved)

```python
class MemoryHit(TypedDict):
    doc_id: str; text: str; url: str; title: str
    similarity: float          # 1 - vector_distance, computed in memory_search only
    stored_at: str             # ISO-8601 (converted from epoch at the store boundary)
    sanitizer_flags: list[str] # provenance: what the ingest sanitizer touched
    doc_type: str              # "chunk" | "summary"

class SearchResult(TypedDict):  url: str; title: str; snippet: str; rank: int
class FetchedDoc(TypedDict):    url: str; title: str; markdown: str; summary: str | None; ok: bool
class Chunk(TypedDict):         chunk_id: str; text: str; url: str; title: str; chunk_index: int
class SourceRef(TypedDict):     url: str; title: str; origin: Literal["memory", "web"]

class AgentState(TypedDict):
    turn_id: str; session_id: str; query: str
    history: list[dict]; threshold: float
    guard_verdict: Literal["allow", "flag", "block"]   # "flag" = proceed but skip_store
    guardrail_events: Annotated[list[str], operator.add]
    sanitized_query: str
    query_vector: list[float] | None
    memory_hits: list[MemoryHit]; top_similarity: float | None
    search_results: list[SearchResult]; fetched_docs: list[FetchedDoc]
    chunks: list[Chunk]; stored_chunk_ids: list[str]; skip_store: bool
    route: Route; degradation: str | None              # "redis_down" | "snippets_only" | None
    answer: str | None; sources: list[SourceRef]
    errors: Annotated[list[StepError], operator.add]
    latency_ms: Annotated[dict[str, int], lambda a, b: {**a, **b}]
    analytics: QueryClassification | None
    tokens: Annotated[dict, lambda a, b: {**a, **b}]   # per-model usage for the turn log
    # --- turn-bookkeeping channels (M2-added beyond PLAN §3.1; see spec note below) ---
    turn_started_at: float | None       # perf_counter() stamp at turn start; feeds latency_ms.total (M4 log_turn)
    search_provider: str | None         # "tavily" | "ddgs" | None; written by M3 web_search, feeds TurnRecord.web.provider (M4)
```

> **Spec note (two channels added to PLAN §3.1's `AgentState`):** LangGraph only propagates keys **declared in the state schema** — a key stamped by the facade/REPL or written by a node but absent from `AgentState` is dropped before `log_turn` reads it. PLAN §8.2's `TurnRecord` requires `latency_ms.total` (computed in `log_turn` from `turn_started_at`, M4 §6.5/§6.8) and `web.provider` (from `search_provider`, M4 §6.3). Neither channel exists in PLAN §3.1, so M2 — the `state.py` owner — declares both here. `turn_started_at` is stamped by `Agent.answer`/the REPL at turn start (single write); `search_provider` is written once by M3's `web_search` node from the `FallbackProvider`'s chosen provider. Both are single-writer (no reducer). Without these two channels `latency_ms.total` is never populated (FR-M4-12) and `web.provider` is always `None` (breaking PLAN §8.2).

> **Spec note (similarity conversion site):** the verbatim `MemoryHit.similarity` comment (`# 1 - vector_distance, computed in memory_search only`) is PLAN §3.1's historical wording. The **authoritative single conversion site** in this milestone is `RedisMemoryStore.knn` (§6.7, FR-M2-07/FR-M2-10), which computes `similarity = distance_to_similarity(vector_distance)` and attaches it before returning — consistent with PLAN §4.3's "memory_search/store boundary". The `memory_search` *node* does **not** re-derive similarity; it only reads `top_similarity` from the hits `knn` returns.

`Route` (verbatim §2.1):

```python
Route = Literal["memory_hit", "memory_miss_web_search", "degraded_web", "blocked", "failed"]
```

> **Spec note (StepError):** PLAN.md references `StepError` in the state but never defines its fields. `state.py` is the canonical-types home, so define it here. Minimal-assumption default (change freely):
> ```python
> class StepError(TypedDict):
>     node: str; error_type: str; detail: str
> ```

> **Spec note (QueryClassification resolution):** `AgentState.analytics` is typed `QueryClassification | None`. LangGraph calls `typing.get_type_hints(AgentState)` to discover the `Annotated` reducers, which evaluates *every* annotation, so `QueryClassification` must be importable at runtime even in M2 (where `analytics` is never written — `log_turn` is a no-op). PLAN §8.3 / IMPLEMENTATION_GUIDE M4 place the classifier schema in `analytics/classify.py`, which M4 owns. Minimal-assumption default that keeps `AgentState` verbatim and importable without stealing M4's logic: M2 ships **only the schema** (the pydantic `QueryClassification` model + the `Category` and `QuestionType` enums, verbatim §8.3 — **no `_missing_` yet**) in `analytics/classify.py`; M4 finalises the *same* enums in place by adding the `_missing_` classmethods (out-of-enum → `other`, FR-M4-15) and adds the classifier *function*, structured-output call, retry, and null-handling into the same file (and owns `test_classifier_parsing.py`). This M2-ships-schema / M4-hardens split is a named seam (M4 §6.4). `state.py` imports the schema: `from memagent.analytics.classify import QueryClassification`. (Alternative if you prefer zero new files in M2: house `QueryClassification` in `state.py` itself and have M4 import it from there — either is fine; pick once.)

Verbatim §8.3 schema shipped for the import to resolve:

```python
class QuestionType(str, Enum): factual; how_to; comparison; opinion; troubleshooting; other
class Category(str, Enum):
    technology; science; health; finance_business; travel_geography
    entertainment_sports; history_politics; lifestyle; other

class QueryClassification(BaseModel):
    topic: str            # free-form, 1-4 lowercase words ("redis vector search")
    category: Category    # closed enum
    question_type: QuestionType
    language: str         # ISO 639-1
    confidence: float     # 0..1
```

### 6.3 `interfaces.py` — verbatim §3.4 Protocols

```python
class Embedder(Protocol):
    dim: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class CompletionResult(NamedTuple):
    text: str
    usage: dict          # {"input_tokens": int, "output_tokens": int, "model": str}

class ChatLLM(Protocol):
    async def complete(self, system: str, messages: list[dict]) -> CompletionResult: ...
    async def parse(self, system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel, dict]: ...

class WebSearcher(Protocol):
    async def search(self, query: str, k: int) -> list[SearchResult]: ...

class MemoryStore(Protocol):
    async def knn(self, vector: list[float], k: int) -> list[MemoryHit]:  # RAW top-k, NO filtering
        ...
    async def store(self, page: FetchedDoc, chunks: list[Chunk], vectors: list[list[float]],
                    source_query: str, flags: list[str]) -> list[str]: ...
```

`resources.py` — frozen container (verbatim §3.4):

```python
@dataclass(frozen=True)
class AgentResources:
    settings: Settings; memory: MemoryStore; embedder: Embedder
    chat_llm: ChatLLM; analytics_llm: ChatLLM
    searcher: WebSearcher; fetcher: PageFetcher; turn_logger: TurnLogger
```

> **Spec note (`PageFetcher`/`TurnLogger` forward refs):** these types belong to M3/M4. Use `from __future__ import annotations` in `resources.py` so the dataclass field annotations stay as unevaluated strings (a `@dataclass` reads field names from `__annotations__` but does not resolve the string types), and do **not** call `get_type_hints` on `AgentResources`. To construct the frozen container in M2, supply no-op stub objects for `searcher` (returns `[]`), `fetcher` (unused placeholder), and `turn_logger` (no-op). M3/M4 swap in the real implementations. If a linter objects to undefined names, define minimal placeholder `Protocol`s `PageFetcher`/`TurnLogger` in `interfaces.py` now (M3/M4 flesh them out).

### 6.4 `routers.py` — verbatim §3.3, all five

```python
def route_after_guard(s):  return "log_turn" if s["guard_verdict"] == "block" else "embed_query"
def route_after_embed(s):  return "memory_search" if s.get("query_vector") else "answer_failure"
def route_after_memory(s):
    sim = s.get("top_similarity")
    return "answer_from_memory" if sim is not None and sim >= s["threshold"] else "web_search"
def route_after_search(s): return "fetch_pages" if s["search_results"] else "answer_failure"
def route_after_fetch(s):  return "ingest_content" if s["fetched_docs"] else "answer_from_web"
```

All five are delivered and unit-tested now (Ruling B). In M2's graph only `route_after_embed` and `route_after_memory` are wired.

### 6.5 Threshold + conversion (§4.3 — the #1 correctness trap)

Redis `COSINE` returns **distance** `d = 1 − cosine_similarity`. OpenAI embeddings are L2-normalised, so:

```
similarity = 1.0 − vector_distance          # exact; NOT 1 − d/2
hit  ⇔  similarity >= SIMILARITY_THRESHOLD  # inclusive, default 0.70 ⇔ distance <= 0.30
```

Implement once:

```python
def distance_to_similarity(distance: float) -> float:
    return 1.0 - distance
```

> **Spec note (float32 epsilon):** float32 storage can return a true 0.70 as `0.699999988`. Decision for this repo (documented once, per PLAN §4.3/Part 6): keep the router comparison exactly `sim >= threshold`; **if and only if** the boundary test flakes, switch to `sim >= threshold - 1e-6`. `test_similarity.py` records this decision in a comment and asserts the chosen behaviour at the 0.70 boundary.

**Calibration warning (surface in README, not code):** 0.70 is calibrated for `text-embedding-3-small`; changing `EMBEDDING_MODEL` changes what 0.70 means and requires re-tuning `SIMILARITY_THRESHOLD` plus a `wipe-memory` rebuild.

### 6.6 Index schema (consumed from M1's `schema.py`; reproduced for self-containedness — §4.2)

Index `web_memory`, HASH storage, indexed prefix `chunk:`. Keys: `chunk:{url_hash}:{i}` (chunks), `chunk:{url_hash}:summary` (per-page summary doc — **indexed, participates in KNN**). Non-indexed companion `doc:{url_hash}` (`num_chunks`, `fetched_at`, `url`).

| Field | Type | Notes |
|---|---|---|
| `chunk_text` | text | sanitised markdown — raw is never stored |
| `url` | tag | canonical URL (utm/fragment-stripped) |
| `url_hash` | tag | `sha256(canonical_url)[:16]` |
| `title` | text | |
| `doc_type` | tag | `chunk` \| `summary` |
| `source_query` | text | query that triggered ingestion |
| `chunk_index` | numeric | |
| `fetched_at` | numeric, sortable | epoch seconds (→ ISO at the `MemoryHit` boundary) |
| `sanitizer_flags` | tag (csv) | provenance for the T3 defence |
| `content_sha256` | text | audit/tamper check |
| `embedding` | vector | **FLAT**, `cosine`, `float32`, dims = `EMBEDDING_DIM` (1536) |

### 6.7 `memory/store.py` — `RedisMemoryStore`

- Opens a redisvl `AsyncSearchIndex` from M1's schema against `REDIS_URL`.
- `knn(vector, k=MEMORY_TOP_K=5)`: run a redisvl `VectorQuery` for the top-k nearest by `embedding`, returning the indexed fields + `vector_distance`. For each result set `similarity = distance_to_similarity(vector_distance)` (the one conversion site), convert `fetched_at` epoch → ISO-8601 for `stored_at`, split `sanitizer_flags` csv → list, and build a `MemoryHit`. Return the list **unfiltered**, sorted by descending similarity. Empty index → `[]`.
- `store(page, chunks, vectors, source_query, flags)`: compute `url_hash` from `page["url"]`; if `doc:{hash}` exists, read its `num_chunks` and delete all `chunk:{hash}:*` first (deterministic upsert without SCAN); write each chunk hash `chunk:{hash}:{i}` (with `chunk_text`, `url`, `url_hash`, `title`, `doc_type`, `source_query`, `chunk_index`, `fetched_at`, `sanitizer_flags`, `content_sha256`, `embedding`), write `chunk:{hash}:summary` when a summary is present (M3 supplies it via `page["summary"]`), write `doc:{hash}` meta (`num_chunks`, `fetched_at`, `url`), and set `EXPIRE MEMORY_TTL_SECONDS` (604800) on each `chunk:` key when the value is `> 0` (`0` disables). Return the list of stored chunk ids.
  - **Vector/summary alignment (contract with the caller, pins PLAN FACT #3):** the summary doc must be stored *with an embedding* so it participates in KNN. Convention: **when `page["summary"]` is not `None`, `vectors[0]` is the summary embedding and `vectors[1:]` align 1:1 to `chunks`** (so `len(vectors) == len(chunks) + 1`) — `chunk:{hash}:summary` is written with `chunk_text=page["summary"]`, `doc_type="summary"`, `embedding=vectors[0]`, and each `chunk:{hash}:{i}` gets `embedding=vectors[i+1]`. **When `page["summary"]` is `None`, no summary doc is written and `vectors` aligns 1:1 to `chunks`** (`len(vectors) == len(chunks)`). This is exactly what M3's `ingest_content` produces by batch-embedding `([summary] if summary else []) + chunk_texts` (M3 §6.10). In M2, `seed_memory` has no summary, so it passes `page["summary"]=None` and `len(vectors) == len(chunks)`.
- `is_fresh(url_hash) -> bool`: read `doc:{hash}.fetched_at`; return `now - fetched_at < FRESHNESS_WINDOW_SECONDS` (86400); missing → `False`.

> **Spec note (redisvl TTL/upsert signatures):** if the M1 re-verification finds `load(..., ttl=)` or `array_to_buffer` signatures differ, use the documented fallback — an explicit `EXPIRE` pipeline after `load()` (PLAN §14). The observable behaviour (per-key TTL, deterministic cleanup) is what FR-M2-10/11 assert; the mechanism may vary.

> **Spec note (Redis-down handling):** the graceful degradation path (`MemoryUnavailableError` → treat as miss, `skip_store=True`, `degradation="redis_down"`, `route="degraded_web"`) is M5's degradation matrix. In M2, `memory_search` implements the happy path plus the empty-index miss; if Redis is unreachable the node may surface the error (the M2 demo assumes Redis is up). Do not build the degradation matrix here.

### 6.8 `memory/chunking.py`

`chunk_markdown(text) -> list[str]` using `RecursiveCharacterTextSplitter` from `langchain-text-splitters` with markdown separators (headings/paragraphs first), `chunk_size=CHUNK_SIZE_CHARS=1600`, `chunk_overlap=CHUNK_OVERLAP_CHARS=200`. Post-filter: drop any chunk `< 100` chars, drop empty/whitespace-only chunks, and cap the result at `MAX_CHUNKS_PER_PAGE=25`.

### 6.9 `memory/urls.py`

```
canonicalize(url):  lowercase scheme + host; drop fragment (#...); drop every utm_* query param;
                    keep remaining query params; return the rebuilt URL
url_hash(url):      hashlib.sha256(canonicalize(url).encode()).hexdigest()[:16]
```

> **Spec note (case-normalisation):** PLAN §4.2 defines canonicalisation only as "utm/fragment-stripped". This spec additionally lowercases the **scheme and host** (path and query case preserved) — scheme and host are case-insensitive per RFC 3986, so this is a safe minimal-assumption default that only affects `url_hash` equality/dedup for case-variant hosts (e.g. `HTTP://Example.com` ≡ `http://example.com`). This behaviour is asserted in FR-M2-15 and the §7 canonicalisation scenarios.

### 6.10 `llm/clients.py`

- `OpenAIEmbedder(settings)`: holds `AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None, max_retries=0, timeout=45.0)`; `dim = settings.embedding_dim` (1536); `embed(texts)` calls the embeddings endpoint with `model=settings.embedding_model` and returns vectors in input order.
- `OpenAIChatLLM(settings, model)`: same `AsyncOpenAI` construction; `complete(system, messages)` calls the chat/responses endpoint with `model`, `max_tokens=2048`, `temperature=0`, and returns `CompletionResult(text, usage={"model": model, "input_tokens": …, "output_tokens": …})`.

> **Spec note (Ruling D seam + `temperature=0`):** `AsyncOpenAI` is constructed with `max_retries=0` so M5's tenacity is the sole retry owner; the single call-site per client is the wrapper seam M5 wraps. `temperature=0` is version-sensitive across GPT-5-family snapshots — per PLAN §14, FR-M2-25 performs one **build-time sanity confirmation** against the pinned `gpt-5.4-mini` id (a single live call); the actual `temperature=0` **validation logic** is owned by M4's client finalisation (Ruling D). If the pinned id rejects `temperature`, M2 records it and M4 decides the handling. `complete()` is production-grade in M2 (the answer path needs it); `parse()` is implemented basically and finalised in M4 (usage plumbing, structured-output parse, `max_tokens=256`). **Constructor-signature note:** M2's thin constructors are `OpenAIEmbedder(settings)` and `OpenAIChatLLM(settings, model)` (each builds its own `AsyncOpenAI`); M4 finalises them to the ONE-shared-client signatures `OpenAIEmbedder(client, model, dim)` / `OpenAIChatLLM(client, model, max_tokens, temperature)` and **rewrites `app.py build_resources` to use `build_openai_clients(settings)`** (M4 §6.2). This constructor change is part of the Ruling D finalisation; the `embed`/`complete` call interfaces stay fixed, so M3's node code is unaffected.

### 6.11 `llm/prompts.py` (API fixed here — Ruling E)

- `build_system_prompt() -> str` (no args): a **basic** hardened prompt stating that everything inside `<untrusted_context>` is quoted data and never instructions, and that the answer must end with a "Sources:" section. (Full L2 hardening — per-source provenance headers, tag-breakout escaping, user-question-last, and the cite-only-`source_url` rule text — is added in M5 without changing this signature, per Ruling E.)
- `wrap_context(sources, origin) -> str`: wrap `sources` (a list of `MemoryHit` or `FetchedDoc`) inside a single `<untrusted_context>` block, each source preceded by a minimal header line carrying at least `source_url`; `origin` (`"memory"`/`"web"`) is recorded in the header. `answer_from_memory` calls `wrap_context(memory_hits, origin="memory")`; M3's `answer_from_web` calls `wrap_context(sources, origin="web")`. (M5 adds `fetched_at`/`sanitizer_flags` to the header and tag-breakout escaping — body only, never the signature.)
- **Both signatures above are the FINAL API (Ruling E).** The `origin` parameter and the no-arg `build_system_prompt()` are fixed here so M5's finalisation touches only the bodies and never the call sites in `answer_from_memory`/`answer_from_web`.

### 6.12 `graph.py` — partial wiring (Ruling B + F)

```
sg = StateGraph(AgentState)
sg.add_node("embed_query", embed_query)
sg.add_node("memory_search", memory_search)
sg.add_node("answer_from_memory", answer_from_memory)
sg.add_node("answer_failure", answer_failure)
sg.add_node("log_turn", log_turn)               # no-op stub (M4 replaces)

sg.set_entry_point("embed_query")               # guard_input activates in M5 (Ruling F)
sg.add_conditional_edges("embed_query", route_after_embed,
                         {"memory_search": "memory_search",
                          "answer_failure": "answer_failure"})
sg.add_conditional_edges("memory_search", route_after_memory,
                         {"answer_from_memory": "answer_from_memory",
                          "web_search": "answer_failure"})   # TEMPORARY miss→failure (M3 remaps)
sg.add_edge("answer_from_memory", "log_turn")
sg.add_edge("answer_failure", "log_turn")
sg.add_edge("log_turn", END)
compiled = sg.compile()
```

The router functions stay verbatim; only the **path-map** for `route_after_memory` changes in M3 (the `"web_search"` key remaps to the real `web_search` node). This is the whole miss-branch seam.

### 6.13 `app.py`

- `build_resources(settings: Settings | None = None) -> AgentResources`: if `settings is None`, fall back to `Settings()` (so `build_resources()` with no argument works for graph-inspection/`draw_mermaid` commands — note these still require a non-empty `OPENAI_API_KEY` because the clients build `AsyncOpenAI`, e.g. `OPENAI_API_KEY=dummy`); construct `OpenAIEmbedder(settings)`, `OpenAIChatLLM(settings, settings.conversation_model)` as `chat_llm`, `OpenAIChatLLM(settings, settings.analytics_model)` as `analytics_llm`, `RedisMemoryStore`, and the no-op `searcher`/`fetcher`/`turn_logger` stubs; assert `embedder.dim == embedding_dim`.
- `Agent.answer(q) -> TurnResult`: build the initial `AgentState` (`turn_id=str(uuid4())`, `session_id`, `query=q`, `history=[]`, `threshold=settings.similarity_threshold`, `guard_verdict="allow"`, `sanitized_query=q`, `skip_store=False`, `turn_started_at=time.perf_counter()` (feeds `latency_ms.total` in M4's `log_turn`), `search_provider=None`, empty lists/None for the rest), `await compiled.ainvoke(state)`, then return `TurnResult(route=final["route"], answer=final.get("answer"), sources=final.get("sources", []), similarity=final.get("top_similarity"))`.

### 6.14 `cli.py` — `ask`

Replace the M1 echo body: run `asyncio.run(Agent(...).answer(query))`; if `route == "memory_hit"` print `[MEMORY HIT sim={similarity:.2f}]`, else print `[MEMORY MISS]`; then print the answer and, for a hit, the source list (`(memory) {title} <{url}>`). *(The bare `[MEMORY MISS]` here is temporary — M2's miss path routes to `answer_failure`. **M3 owns updating this `ask` banner** to the canonical `[MEMORY MISS → searching the web]` and printing web sources on a miss once the real web path lands — M3 §6.13a.)*

### 6.15 `scripts/seed_memory.py`

CLI that takes `--url` and text (arg or `--file`): canonicalise the URL, call `chunk_markdown(text)` (which returns `list[str]`), wrap each string in a `Chunk` record (`chunk_id`, `text`, `url`, `title`, `chunk_index`) since `store` takes `list[Chunk]`, embed the chunk texts (no summary → pass `page["summary"]=None`, so `vectors` align 1:1 to chunks per §6.7), and `store(...)` them with `source_query="seed"` and `flags=[]`, so the exact seeded text is a `memory_hit` on ask.

### 6.16 Environment variables relevant to M2 (defaults verbatim, PLAN §10.3)

```bash
OPENAI_API_KEY=sk-...                  # required
OPENAI_BASE_URL=                       # optional — GitHub Models free-dev endpoint (+ GitHub PAT as key)
CONVERSATION_MODEL=gpt-5.4-mini
ANALYTICS_MODEL=gpt-5.4-nano
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
REDIS_URL=redis://localhost:6379/0
MEMORY_INDEX_NAME=web_memory
SIMILARITY_THRESHOLD=0.7               # inclusive; hit ⇔ (1 - distance) >= this
MEMORY_TOP_K=5
MEMORY_TTL_SECONDS=604800              # 7d; 0 disables
FRESHNESS_WINDOW_SECONDS=86400
CHUNK_SIZE_CHARS=1600
CHUNK_OVERLAP_CHARS=200
MAX_CHUNKS_PER_PAGE=25
LLM_TIMEOUT_S=45
```

### 6.17 Dependency pins used in M2 (PLAN §10.1)

`langgraph>=1.2,<2`, `langchain-text-splitters`, `redis>=6.2,<7`, `redisvl>=0.22,<0.24` (0.23.0 current 2026-07-04), `openai` (>=2, verify), `pydantic>=2.11`, `pydantic-settings`, `typer>=0.16`, `rich>=14`, `structlog~=26.1`. (`tenacity~=9.1` is M5; `trafilatura`/`ddgs`/`httpx` fetch usage is M3.) Dev: `pytest~=8.4`, `pytest-asyncio` (1.x), `ruff`, `pytest-cov`.

### 6.18 Commands

```bash
uv sync                                    # install locked deps
make redis-up                              # docker compose up -d --wait (redis:8.2)
uv run memagent wipe-memory                # M1 command: (re)create the empty index
uv run python scripts/seed_memory.py --url https://redis.io/docs/vectors \
    --file docs/seed.md                    # seed one document
uv run memagent ask "How does Redis vector search work?"   # expect [MEMORY HIT sim=0.9x]
uv run pytest tests/unit/test_routing.py tests/unit/test_similarity.py tests/unit/test_chunker.py -q
uv run ruff check src tests
```

---

## 7. BDD acceptance scenarios

Gherkin, one Feature per functional area. Every Scenario is tagged `@unit` / `@integration` / `@e2e` / `@manual`. Concrete values only.

> **Ownership note (FR-M2-16…22 node/graph/facade scenarios):** the `@unit` scenarios for `embed_query`, `memory_search`, `answer_from_memory`, `answer_failure`, graph wiring, and `Agent.answer` exercise M2 code but depend on the `FakeEmbedder`/`FakeLLM`/fake `MemoryStore`/`clean_index` fixtures that **Ruling A assigns to M6's `tests/conftest.py`**. Per Ruling A, M2's own unit files are only `test_routing.py`/`test_similarity.py`/`test_chunker.py`; these node/graph/facade scenarios are therefore **authored and run in M6** (the tag denotes test *type*, not the milestone that runs it). Within M2, FR-M2-16…22 are verified by the manual demo (FR-M2-24 and the §9 demoable outcome), not by an automated M2 test.

```gherkin
# tests/unit/test_routing.py  (M2-owned)
Feature: Threshold routing (FR-M2-05, FR-M2-06)

  @unit
  Scenario Outline: route_after_memory applies the inclusive 0.70 boundary
    Given a state whose threshold is 0.70
    And top_similarity is <sim>
    When route_after_memory is called
    Then it returns "<target>"

    Examples:
      | sim    | target             |
      | 0.70   | answer_from_memory |   # inclusive hit
      | 0.6999 | web_search         |   # just below → miss
      | 1.0    | answer_from_memory |   # perfect match → hit
      | 0.0    | web_search         |   # unrelated → miss
      | None   | web_search         |   # empty index → miss

  @unit
  Scenario: route_after_embed sends a valid vector to memory search
    Given a state whose query_vector is a 1536-float list
    When route_after_embed is called
    Then it returns "memory_search"

  @unit
  Scenario: route_after_embed sends a missing vector to failure
    Given a state whose query_vector is None
    When route_after_embed is called
    Then it returns "answer_failure"

  @unit
  Scenario: route_after_guard blocks a blocked verdict
    Given a state whose guard_verdict is "block"
    When route_after_guard is called
    Then it returns "log_turn"

  @unit
  Scenario: route_after_guard allows a non-blocked verdict
    Given a state whose guard_verdict is "allow"
    When route_after_guard is called
    Then it returns "embed_query"

  @unit
  Scenario: route_after_search with results proceeds to fetch
    Given a state whose search_results has 3 entries
    When route_after_search is called
    Then it returns "fetch_pages"

  @unit
  Scenario: route_after_search with no results fails the turn
    Given a state whose search_results is an empty list
    When route_after_search is called
    Then it returns "answer_failure"

  @unit
  Scenario: route_after_fetch with fetched docs proceeds to ingest
    Given a state whose fetched_docs has 2 entries
    When route_after_fetch is called
    Then it returns "ingest_content"

  @unit
  Scenario: route_after_fetch with no fetched docs answers from snippets
    Given a state whose fetched_docs is an empty list
    When route_after_fetch is called
    Then it returns "answer_from_web"

  @unit
  Scenario: routers are pure
    Given any fixed state
    When any router is called twice
    Then both calls return the same value
    And neither invocation reads or writes Redis, the network, or the filesystem
```

```gherkin
# tests/unit/test_similarity.py  (M2-owned)
Feature: Distance-to-similarity conversion (FR-M2-06, FR-M2-07)

  @unit
  Scenario: cosine distance 0.30 converts to similarity 0.70
    Given a vector_distance of 0.30
    When distance_to_similarity is applied
    Then the similarity equals 0.70 within 1e-9

  @unit
  Scenario: the 0.30 distance routes as an inclusive hit
    Given distance_to_similarity(0.30) as top_similarity
    And a threshold of 0.70
    When route_after_memory is called
    Then it returns "answer_from_memory"

  @unit
  Scenario: float32 noise at the boundary is handled per the documented decision
    Given a top_similarity of 0.699999988 that represents a true 0.70
    And a threshold of 0.70
    When route_after_memory is called
    Then it returns "web_search"   # default per §6.5: sim >= threshold, and 0.699999988 < 0.70
    And the test documents that the "sim >= threshold - 1e-6" variant is adopted only if this boundary flakes

  @unit
  Scenario: the L2 formula is NOT used
    Given a vector_distance of 0.30
    When distance_to_similarity is applied
    Then the result does not equal 0.85 (which is 1 - 0.30/2)
```

```gherkin
# tests/unit/test_chunker.py  (M2-owned)
Feature: Markdown chunking invariants (FR-M2-14)

  @unit
  Scenario: chunk size and overlap respect the configured bounds
    Given a 10000-character markdown document
    When chunk_markdown splits it with size 1600 and overlap 200
    Then no chunk exceeds 1600 characters
    And each pair of consecutive chunks shares overlapping text of more than 0 and at most 200 characters

  @unit
  Scenario: chunks below the floor are dropped
    Given a markdown document that would yield a 40-character trailing fragment
    When chunk_markdown splits it
    Then no returned chunk is shorter than 100 characters

  @unit
  Scenario: the per-page chunk cap is enforced
    Given a 200000-character markdown document
    When chunk_markdown splits it
    Then it returns at most 25 chunks

  @unit
  Scenario: no empty chunks are ever produced
    Given a markdown document containing runs of blank lines
    When chunk_markdown splits it
    Then no returned chunk is empty or whitespace-only

  @unit
  Scenario: unicode text is chunked without corruption
    Given a markdown document containing "café", "naïve", and CJK characters "配置"
    When chunk_markdown splits it
    Then the concatenated chunks contain "café", "naïve", and "配置" intact (no mojibake, no split multibyte characters)

  @unit
  Scenario: a very short document yields at most one chunk
    Given a 120-character markdown document
    When chunk_markdown splits it
    Then it returns exactly one chunk equal to the input
```

```gherkin
# behaviour of RedisMemoryStore — verified by M6 tests/integration/test_redis_store.py
Feature: Redis vector store (FR-M2-10, FR-M2-11, FR-M2-12, FR-M2-13)

  @integration
  Scenario: KNN returns raw top-k with similarity attached
    Given an index seeded with 8 chunk documents
    When knn is called with k = 5
    Then exactly 5 MemoryHits are returned
    And each hit has a similarity equal to 1.0 minus its vector_distance
    And no threshold filtering has been applied

  @integration
  Scenario: an empty index is a normal miss, not an error
    Given a freshly created empty index
    When knn is called with any 1536-float vector and k = 5
    Then it returns an empty list

  @integration
  Scenario: stored chunks carry a positive TTL by default
    Given MEMORY_TTL_SECONDS is 604800
    When a page with 3 chunks is stored
    Then TTL of chunk:{hash}:0 is greater than 0 and at most 604800

  @integration
  Scenario: TTL is disabled when configured to zero
    Given MEMORY_TTL_SECONDS is 0
    When a page with 3 chunks is stored
    Then chunk:{hash}:0 has no expiry set

  @integration
  Scenario: re-storing with fewer chunks removes stale keys
    Given a URL previously stored with 6 chunks
    When the same URL is re-stored with 3 chunks
    Then keys chunk:{hash}:3 through chunk:{hash}:5 no longer exist
    And doc:{hash}.num_chunks equals 3

  @integration
  Scenario: freshness helper skips a recently fetched URL
    Given doc:{hash}.fetched_at is 1 hour ago
    When is_fresh(hash) is called
    Then it returns True

  @integration
  Scenario: freshness helper allows a stale URL
    Given doc:{hash}.fetched_at is 48 hours ago
    When is_fresh(hash) is called
    Then it returns False

  @integration
  Scenario: freshness helper treats a missing doc as not fresh
    Given no doc:{hash} record exists
    When is_fresh(hash) is called
    Then it returns False
```

```gherkin
Feature: URL canonicalisation and hashing (FR-M2-15)

  @unit
  Scenario Outline: tracking params, fragments, and case are normalised away
    Given the URL "<raw>"
    When canonicalize is applied
    Then the result equals "<canonical>"

    Examples:
      | raw                                             | canonical                    |
      | HTTP://Example.com/a?utm_source=x#frag          | http://example.com/a         |
      | http://example.com/a                            | http://example.com/a         |
      | https://Foo.COM/p?utm_medium=e&id=7             | https://foo.com/p?id=7       |

  @unit
  Scenario: two variant spellings hash to the same 16-char key
    Given "HTTP://Example.com/a?utm_source=x#frag" and "http://example.com/a"
    When url_hash is applied to each
    Then both produce the same 16-character hexadecimal hash
```

```gherkin
Feature: Embedding client (FR-M2-08)

  @manual
  Scenario: the embedder reports 1536 dimensions
    Given an OpenAIEmbedder built from settings with EMBEDDING_DIM 1536
    When embedder.dim is read
    Then it equals 1536

  @manual
  Scenario: embed returns one vector per input in order
    Given a live OpenAI (or GitHub Models) key
    When embed(["alpha", "beta"]) is awaited
    Then two vectors are returned, each of length 1536

  @manual
  Scenario: the SDK is constructed with retries disabled
    Given an OpenAIEmbedder
    When its AsyncOpenAI client configuration is inspected
    Then max_retries is 0 and timeout is 45.0
```

> **Ownership note (FR-M2-08 non-network assertions):** `dim == 1536`, `max_retries == 0`, and `timeout == 45.0` need no network, but per Ruling A M2's only unit files are `test_routing`/`test_similarity`/`test_chunker` — none for the clients. In M2 these assertions (the Ruling D construction seam) are confirmed as part of the FR-M2-25 live-verification step; an automated unit assertion, if added, lands with M6's client/test fixtures. Hence the `@manual` tag.

```gherkin
Feature: Chat client (FR-M2-09)

  @manual
  Scenario: complete returns text and a usage dict with the three token keys
    Given a live OpenAI (or GitHub Models) key and CONVERSATION_MODEL gpt-5.4-mini
    When complete(system, [{"role": "user", "content": "ping"}]) is awaited
    Then the CompletionResult text is a non-empty string
    And the usage dict contains exactly the keys model, input_tokens, output_tokens
```

```gherkin
Feature: Embed-query node (FR-M2-16)

  @unit
  Scenario: a successful embedding populates the query vector
    Given a FakeEmbedder that returns a 1536-float vector
    When embed_query runs over a state with query "hello"
    Then query_vector has length 1536

  @unit
  Scenario: an embedding failure clears the vector and records an error
    Given an embedder that raises on embed
    When embed_query runs
    Then query_vector is None
    And errors contains one StepError for node "embed_query"
    And route_after_embed then resolves to "answer_failure"
```

```gherkin
Feature: Memory-search node (FR-M2-17)

  @integration
  Scenario: a seeded near-duplicate produces a high top_similarity
    Given an index seeded with the chunk "Redis vector search stores vectors"
    And a query vector for the same sentence
    When memory_search runs
    Then memory_hits is non-empty
    And top_similarity is at least 0.70

  @integration
  Scenario: an empty index yields no hits and a None top_similarity
    Given a freshly created empty index
    When memory_search runs
    Then memory_hits is an empty list
    And top_similarity is None

  @unit
  Scenario: memory_search does not filter by threshold
    Given a memory store returning 5 hits with similarities 0.9, 0.8, 0.5, 0.4, 0.2
    When memory_search runs
    Then all 5 hits are kept in state
    And top_similarity equals 0.9
    And knn was called exactly once with the query vector and k = 5 (MEMORY_TOP_K)
```

```gherkin
Feature: Answer-from-memory node (FR-M2-18, FR-M2-20)

  @unit
  Scenario: a memory hit answers from the wrapped context and cites sources
    Given memory_hits with one hit for "https://redis.io/docs/vectors" titled "Redis vectors"
    And a FakeLLM that echoes a grounded answer ending with a Sources section
    When answer_from_memory runs
    Then route is "memory_hit"
    And sources contains one SourceRef with origin "memory" and that URL
    And the answer text contains "Sources:"

  @unit
  Scenario: duplicate-URL hits are deduplicated in sources
    Given memory_hits with three hits sharing the same URL
    When answer_from_memory runs
    Then sources contains exactly one SourceRef for that URL

  @unit
  Scenario: the context is wrapped as untrusted data
    Given one memory hit
    When wrap_context([hit], origin="memory") is applied
    Then the output contains "<untrusted_context>" and the hit's source_url
```

```gherkin
Feature: Answer-failure node (FR-M2-19)

  @unit
  Scenario: failure is deterministic and calls no model
    Given a state routed to answer_failure and an injected chat_llm spy
    When answer_failure runs
    Then route is "failed"
    And answer is a fixed apology string
    And the chat_llm spy recorded zero calls

  @unit
  Scenario: answer_failure never raises on malformed state
    Given a state missing optional fields
    When answer_failure runs
    Then it returns without raising
```

```gherkin
Feature: Graph wiring and Agent facade (FR-M2-21, FR-M2-22)

  @unit
  Scenario: the graph compiles and exposes a mermaid diagram
    Given AgentResources with fakes
    When build_graph(resources) is called
    Then it returns a compiled graph
    And get_graph().draw_mermaid() returns a non-empty string containing "embed_query"

  @unit
  Scenario: the hit path runs end to end through the no-op log_turn
    Given a store returning a hit with similarity 0.87 and a FakeLLM
    When Agent.answer("seeded question") is awaited
    Then the TurnResult route is "memory_hit"
    And the TurnResult similarity is 0.87

  @unit
  Scenario: the miss branch is temporarily routed to failure
    Given a store returning an empty list
    When Agent.answer("unseeded question") is awaited
    Then the graph traverses embed_query, memory_search, answer_failure, log_turn
    And the TurnResult route is "failed"

  @unit
  Scenario: Agent passes empty history to the graph
    When Agent.answer("anything") is awaited
    Then the initial state history is an empty list
    And guard_verdict is "allow"
```

```gherkin
Feature: Seed script and CLI ask (FR-M2-23, FR-M2-24)

  @manual
  Scenario: seeding then asking the same question is a memory hit
    Given a running redis:8.2 and a live embedding key
    And seed_memory has stored a document for "https://redis.io/docs/vectors"
    When "memagent ask" is run with the seeded question verbatim
    Then stdout contains "[MEMORY HIT sim=0." with a value at least 0.70
    And stdout lists the seeded URL under the sources

  @manual
  Scenario: an unseeded question shows the miss banner
    Given a running redis:8.2 with an empty index
    When "memagent ask" is run with a novel question
    Then stdout contains "[MEMORY MISS]"
    And stdout shows the deterministic temporary response

  @unit
  Scenario: the hit banner formats the similarity to two decimals
    Given a TurnResult with route "memory_hit" and similarity 0.8712
    When the ask command renders it
    Then the banner reads "[MEMORY HIT sim=0.87]"
```

```gherkin
Feature: Live catalogue verification (FR-M2-25)

  @manual
  Scenario: GitHub Models free-dev catalogue ids resolve
    Given OPENAI_BASE_URL points at GitHub Models and a GitHub PAT with models:read
    When one embedding call and one chat call are made against the openai/* catalogue ids
    Then both succeed and the exact id strings are recorded in docs/ai_prompts/

  @manual
  Scenario: gpt-5.4-mini accepts temperature=0
    Given a live OpenAI key and CONVERSATION_MODEL gpt-5.4-mini
    When one chat completion is requested with temperature=0
    Then the call succeeds (no 400)
    And the result is recorded; if it 400-rejects temperature, that is recorded instead
```

---

## 8. Task breakdown

Ordered, each ≤ ~1 h. `[P]` = parallel-safe (independent files, no ordering dependency).

- **T-M2-01** — `state.py`: `AgentState` (verbatim), the five TypedDicts, `Route`, `StepError`; resolve `QueryClassification` import per §6.2 spec note. *(FR-M2-01, FR-M2-02)*
- **T-M2-02 [P]** — `interfaces.py`: the four Protocols + `CompletionResult`; placeholder `PageFetcher`/`TurnLogger` if the linter needs them. *(FR-M2-03)*
- **T-M2-03 [P]** — `resources.py`: frozen `AgentResources` with `from __future__ import annotations`. *(FR-M2-04)*
- **T-M2-04 [P]** — `routers.py`: all five verbatim pure functions. *(FR-M2-05, FR-M2-06)*
- **T-M2-05 [P]** — `memory/urls.py`: `canonicalize`, `url_hash`. *(FR-M2-15)*
- **T-M2-06 [P]** — `memory/chunking.py`: `chunk_markdown` with the 1600/200/min-100/max-25 rules. *(FR-M2-14)*
- **T-M2-07 [P]** — `llm/prompts.py`: `build_system_prompt`, `wrap_context` (basic, API fixed). *(FR-M2-20)*
- **T-M2-08** — `llm/clients.py`: `OpenAIEmbedder` (+`dim`) and `OpenAIChatLLM.complete` (`max_retries=0`, `timeout=45.0`, `temperature=0`, `max_tokens=2048`); basic `parse`. *(FR-M2-08, FR-M2-09)* — depends on T-M2-01/02.
- **T-M2-09a** — `memory/store.py` (part 1): `distance_to_similarity` and `RedisMemoryStore.knn` — the single conversion site, raw unfiltered top-k ordered by descending similarity, empty index → `[]` — against M1's schema (redisvl `AsyncSearchIndex`). *(FR-M2-07, FR-M2-10)* — depends on T-M2-01, T-M2-05.
- **T-M2-09b** — `memory/store.py` (part 2): `RedisMemoryStore.store` (deterministic upsert cleanup via `doc:{hash}.num_chunks`, per-key `EXPIRE` TTL, summary-doc write) and `is_fresh`; EXPIRE-pipeline fallback if the redisvl signatures differ. *(FR-M2-11, FR-M2-12, FR-M2-13)* — depends on T-M2-01, T-M2-05, T-M2-09a.
- **T-M2-10 [P]** — `nodes/embed.py` (`embed_query`), `nodes/answer.py` (`answer_failure`). *(FR-M2-16, FR-M2-19)* — depends on T-M2-08.
- **T-M2-11** — `nodes/memory.py` (`memory_search`), `nodes/answer.py` (`answer_from_memory`). *(FR-M2-17, FR-M2-18)* — depends on T-M2-07, T-M2-08, T-M2-09a.
- **T-M2-12 [P]** — `nodes/log.py`: no-op `log_turn` stub. *(FR-M2-21)*
- **T-M2-13** — `graph.py`: partial wiring with entry `embed_query`, the two conditional edges, temporary miss→`answer_failure` path-map, `log_turn`→END. *(FR-M2-21)* — depends on T-M2-04, T-M2-10..12.
- **T-M2-14** — `app.py`: `build_resources` (real embedder/chat_llm/analytics_llm/store + stub searcher/fetcher/turn_logger; `dim` assertion) and `Agent.answer` + `TurnResult`. *(FR-M2-22)* — depends on T-M2-08, T-M2-09b, T-M2-13.
- **T-M2-15** — `cli.py`: wire `ask` to `Agent.answer`; hit/miss banner + source metadata. *(FR-M2-24)* — depends on T-M2-14.
- **T-M2-16** — `scripts/seed_memory.py`: `--url`/`--file` → canonicalise → chunk → embed → store. *(FR-M2-23)* — depends on T-M2-06, T-M2-09b.
- **T-M2-17 [P]** — `tests/unit/test_routing.py`: the parametrized boundary + all five routers. *(FR-M2-05, FR-M2-06)* — depends on T-M2-04.
- **T-M2-18 [P]** — `tests/unit/test_similarity.py`: `distance_to_similarity(0.30)==0.70`, hit routing, epsilon decision, not-1−d/2. *(FR-M2-06, FR-M2-07)* — depends on T-M2-09a.
- **T-M2-19 [P]** — `tests/unit/test_chunker.py`: size/overlap/floor/cap/unicode/short-doc/no-empty. *(FR-M2-14)* — depends on T-M2-06.
- **T-M2-20** — live verification: one GitHub Models call (catalogue ids) + one `gpt-5.4-mini` `temperature=0` call; record results, correct `.env.example`/`Settings` defaults if ids differ. *(FR-M2-25)* — depends on T-M2-08.
- **T-M2-21** — append the M2 AI-prompt log to `docs/ai_prompts/` and link from `AI_USAGE.md`; run `ruff` and the three unit test files green. *(FR-M2-26)*

---

## 9. Definition of Done

- [ ] `uv run python -c "import memagent.state, memagent.interfaces, memagent.resources, memagent.routers, memagent.graph, memagent.app"` succeeds (all modules import; `get_type_hints(AgentState)` resolves). *(FR-M2-01/02/03/04)*
- [ ] `uv run pytest tests/unit/test_routing.py tests/unit/test_similarity.py tests/unit/test_chunker.py -q` passes, including the 0.70-inclusive boundary and `distance_to_similarity(0.30)==0.70`. *(FR-M2-05/06/07/14)*
- [ ] `uv run ruff check src tests` is clean. *(code organisation)*
- [ ] `grep -rn "1\.0 - distance" src/ --include=*.py | grep -v '#'` shows the conversion in exactly one module (`memory/store.py`) — the `return 1.0 - distance` line in `distance_to_similarity` — with exactly one match (the verbatim `MemoryHit` comment is excluded by `grep -v '#'`). *(FR-M2-07)*
- [ ] `OPENAI_API_KEY=dummy uv run python -c "from memagent.config import Settings; from memagent.app import build_resources; from memagent.graph import build_graph; d=build_graph(build_resources(Settings())).get_graph().draw_mermaid(); assert d and all(n in d for n in ('embed_query','memory_search','answer_from_memory','answer_failure','log_turn'))"` exits 0 — a non-empty mermaid diagram naming all five nodes (graph construction and `draw_mermaid()` make no network calls). *(FR-M2-21)*
- [ ] **Demoable outcome (PLAN §13, M2 row):** with `redis:8.2` up and the index wiped, `uv run python scripts/seed_memory.py --url … --file …` then `uv run memagent ask "<seeded question>"` prints `[MEMORY HIT sim=0.XX]` (`XX >= 70`) and lists the seeded source URL/title; a novel question prints `[MEMORY MISS]`. *(FR-M2-23/24)*
- [ ] `uv run python -c "from memagent.resources import AgentResources; assert AgentResources.__dataclass_params__.frozen"` exits 0 — `AgentResources` is `frozen=True`, so any field assignment after construction raises `dataclasses.FrozenInstanceError`. *(FR-M2-04)*
- [ ] **Live verification (PLAN §14):** one GitHub Models call confirms the free-dev catalogue ids (`openai/gpt-5.4-mini`, `openai/gpt-5.4-nano`, `text-embedding-3-small`-equivalent) resolve, and one call confirms `gpt-5.4-mini` accepts `temperature=0`; both results (id strings + pass/fail) recorded, and `.env.example`/`Settings` corrected if any id differs. *(FR-M2-25)*
- [ ] **AI-assistance disclosure appended for M2 (not retroactively):** a dated M2 file exists under `docs/ai_prompts/` and `AI_USAGE.md` references it as part of the complete instruction record — verify with `ls docs/ai_prompts/` (a dated M2 file is listed) and `grep -q ai_prompts AI_USAGE.md`. *(FR-M2-26)*
- [ ] Commit on a feature branch; the seam stubs (`log_turn` no-op, miss→`answer_failure` path-map, `searcher`/`fetcher`/`turn_logger` stubs) are clearly marked with the milestone that replaces each.

---

## 10. Risks & gotchas

- **Distance ≠ similarity (PLAN §15.1, Part 6.1).** The single most likely bug. Use `1 − distance` (never `1 − d/2`); keep it in one function; test the 0.70 boundary. Float32 can render a true 0.70 as `0.699999988` — the epsilon decision (`sim >= threshold - 1e-6` only if flaky) is documented once in `test_similarity.py`.
- **First query always misses (PLAN §15.7, Part 6.2).** An empty index returns `[]` → `top_similarity = None` → miss. Handle `None` everywhere; `memory_search` must not raise on an empty index.
- **`get_type_hints(AgentState)` must resolve.** LangGraph introspects the `Annotated` reducers, evaluating *all* annotations. `StepError` and `QueryClassification` must be importable at runtime in M2 (see §6.2). A missing name surfaces as a `NameError` at graph-build time, not import time.
- **Do not let the model route (PLAN §2, Part 6.3).** Routing is code (`route_after_memory`), never model judgment, or the memory-first contract and hit/miss log become unverifiable.
- **redisvl signature drift (PLAN §14).** `load(ttl=)` / `array_to_buffer` / `VectorQuery` were flagged for M1 re-verification; if they differ, use the explicit `EXPIRE` pipeline fallback. Avoid `HybridQuery` (needs Redis 8.4+).
- **`temperature=0` is version-sensitive (PLAN §14, MODEL_CHOICES).** The flagship rejects `temperature`; `gpt-5.4-mini` is expected to accept it, but validate against the pinned id with the M2 live call before relying on deterministic output.
- **Async all-or-nothing (Part 6.5).** Every client is async (`AsyncOpenAI`, redisvl `AsyncSearchIndex`). Do not introduce a blocking call in a node.
- **Seam discipline (Ruling B/D/E/F).** Keep the router functions verbatim; evolve only the graph path-map. Keep `prompts.py` and the client wrapper signatures fixed so M3/M4/M5 are drop-ins. Do not build the degradation matrix, tenacity policies, guard node, or real `log_turn` here.
- **Anti-churn (PLAN §13, DECISIONS).** Do not add the 0.50 salvage route, embed-failure→web fallback, store-side threshold filtering, session memory, or a Redis turn-log mirror.

---

## 11. Spec Kit mapping

- **Feeds `/specify` (spec.md):** §1 (Goal & context), §2 (Scope), §5 (Functional requirements FR-M2-01…26), and §7 (BDD acceptance scenarios) — the what and the observable behaviour.
- **Feeds `/plan` (plan.md):** §3 (Prerequisites & interfaces consumed), §4 (Interfaces provided + temporary stubs), §6 (Technical specification: file layout, verbatim types/Protocols/routers, index schema, conversion, env vars, pins, commands), and §10 (Risks & gotchas) — the how and the seams.
- **Feeds `/tasks` (tasks.md):** §8 (Task breakdown T-M2-01…21 with `[P]` markers and FR links) and §9 (Definition of Done with exact verify commands) — the ordered, checkable work.
