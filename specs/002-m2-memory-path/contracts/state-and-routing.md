# Contract: state, types, and routing (M2 — canonical, later milestones import)

Consumers: every node (M2–M5), graph, facade, M6 tests. Stability: **fixed here**; M4
only *reads* the two bookkeeping channels; nobody edits `state.py` after M2.

## `memagent.state`

Exports: `AgentState`, `Route`, `MemoryHit`, `SearchResult`, `FetchedDoc`, `Chunk`,
`SourceRef`, `StepError` (fields per [data-model.md](../data-model.md)).

- `Route = Literal["memory_hit", "memory_miss_web_search", "degraded_web", "blocked", "failed"]`
  — a Literal alias, NOT an Enum. `set(get_args(Route))` equals exactly that 5-set.
- Reducers: `guardrail_events`/`errors` append (`operator.add`); `latency_ms`/`tokens`
  dict-merge (`lambda a, b: {**a, **b}`). Everything else single-writer.
- `typing.get_type_hints(AgentState)` MUST resolve — hence `QueryClassification` is
  importable from `analytics/classify.py` in M2 (schema-only).

## `memagent.interfaces` (verbatim Protocols)

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

Plus minimal placeholder Protocols `PageFetcher` / `TurnLogger` (fleshed out by M3/M4).
`knn` has **no threshold parameter** — a store that filters is a contract violation.

## `memagent.resources.AgentResources`

`@dataclass(frozen=True)`: `settings, memory, embedder, chat_llm, analytics_llm,
searcher, fetcher, turn_logger`. Uses `from __future__ import annotations`; never call
`get_type_hints` on it. M2 fills searcher/fetcher/turn_logger with no-op stubs
(Ruling B table).

## `memagent.routers` — five pure functions (verbatim §3.3)

```python
def route_after_guard(s):  return "log_turn" if s["guard_verdict"] == "block" else "embed_query"
def route_after_embed(s):  return "memory_search" if s.get("query_vector") else "answer_failure"
def route_after_memory(s):
    sim = s.get("top_similarity")
    return "answer_from_memory" if sim is not None and sim >= s["threshold"] else "web_search"
def route_after_search(s): return "fetch_pages" if s["search_results"] else "answer_failure"
def route_after_fetch(s):  return "ingest_content" if s["fetched_docs"] else "answer_from_web"
```

- Boundary semantics (FR-M2-06): 0.70@0.70 → hit (INCLUSIVE), 0.6999 → miss, None → miss,
  1.0 → hit, 0.0 → miss. Comparison stays `>= threshold` (epsilon only on proven flake —
  research D8, decision recorded in `test_similarity.py`).
- All five delivered and unit-tested in M2 (`test_routing.py`); the graph wires only
  `route_after_embed` + `route_after_memory` now. Routers NEVER change; M3/M5 only remap
  path-map keys (research D11).
