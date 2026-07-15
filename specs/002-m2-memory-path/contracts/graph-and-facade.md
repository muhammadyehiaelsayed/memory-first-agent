# Contract: graph, facade, CLI, seed script (M2)

## `graph.build_graph(resources) -> CompiledGraph` (Rulings B + F)

Wiring (exact):

```
entry: embed_query                          # guard_input activates in M5 (Ruling F)
embed_query --route_after_embed--> {memory_search | answer_failure}
memory_search --route_after_memory--> {answer_from_memory | "web_search"→answer_failure}
                                            # TEMPORARY path-map; M3 remaps the
                                            # "web_search" KEY to the real node
answer_from_memory -> log_turn
answer_failure    -> log_turn
log_turn -> END                             # log_turn = no-op stub returning {} (M4 replaces)
```

- One compiled async `StateGraph(AgentState)`; `compiled.get_graph().draw_mermaid()`
  returns a non-empty string (M6 renders it into the README).
- Node functions receive/return partial `AgentState` dicts; injected via closures over
  `resources` (no module singletons).

## Node behaviors

| Node | Does | Never |
|---|---|---|
| `embed_query` | embeds `sanitized_query` → `query_vector` (len 1536); on error: `query_vector=None` + StepError appended | retries (M5), raises through |
| `memory_search` | `memory.knn(query_vector, settings.memory_top_k)` → `memory_hits`, `top_similarity` (max or None) | threshold-compares, re-derives similarity |
| `answer_from_memory` | `chat_llm.complete(build_system_prompt(), …wrap_context(hits,"memory")…)` → `route="memory_hit"`, `answer` (ends with "Sources:"), `sources` deduped by URL, all `origin="memory"` | using non-hit context |
| `answer_failure` | fixed deterministic apology, `route="failed"` | LLM calls, raising (even on malformed state) |
| `log_turn` (stub) | returns `{}` | anything else |

## `app.py`

- `build_resources(settings: Settings | None = None) -> AgentResources` — `Settings()`
  fallback; real embedder/chat/analytics/store + no-op searcher/fetcher/turn_logger
  stubs; calls M1's `assert_index_dims(embedder.dim, settings)`. Note: requires a
  non-empty key even for graph inspection (`OPENAI_API_KEY=dummy` works — clients build
  `AsyncOpenAI` eagerly).
- `Agent.answer(q) -> TurnResult` — initial state: `turn_id=str(uuid4())`, `session_id`,
  `query=q`, `history=[]`, `threshold=settings.similarity_threshold`,
  `guard_verdict="allow"`, `sanitized_query=q`, `skip_store=False`,
  `turn_started_at=time.perf_counter()`, `search_provider=None`, empty lists/None for
  the rest; `await compiled.ainvoke(state)`; returns
  `TurnResult(route, answer, sources, top_similarity)`.

## `cli.py ask` (replaces the M1 echo stub — call sites unchanged)

- Hit: print `[MEMORY HIT sim={similarity:.2f}]` then the answer, then sources as
  `(memory) {title} <{url}>`.
- Miss (temporary M2 path): print `[MEMORY MISS]` then the deterministic response.
  **M3 owns** upgrading this banner to `[MEMORY MISS → searching the web]` + web sources.
- Exit 0 on answered turns (hit or deterministic miss/failure).

## `scripts/seed_memory.py`

`--url <URL>` + text arg or `--file <path>`: canonicalize URL → `chunk_markdown(text)` →
wrap strings into `Chunk` records (`chunk_id`, `text`, `url`, `title`, `chunk_index`) →
embed chunk texts → `store(page(summary=None), chunks, vectors, source_query="seed",
flags=[])`. Post-condition: asking an equivalent question routes `memory_hit`
(FR-M2-23), demoable as `[MEMORY HIT sim=0.9x]` for the exact seeded text.
