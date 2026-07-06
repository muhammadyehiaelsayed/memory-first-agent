"""Canonical typed state — the single home of every state/record type (Constitution P-III).

Single-writer fields unless a reducer is declared. LangGraph propagates ONLY keys declared
in AgentState; ``typing.get_type_hints(AgentState)`` must resolve at runtime, which is why
QueryClassification is imported from analytics.classify (schema-only in M2).
"""

import operator
from typing import Annotated, Literal, TypedDict

from memagent.analytics.classify import QueryClassification

Route = Literal["memory_hit", "memory_miss_web_search", "degraded_web", "blocked", "failed"]


class MemoryHit(TypedDict):
    doc_id: str
    text: str
    url: str
    title: str
    similarity: float  # 1 - vector_distance, attached in RedisMemoryStore.knn only
    stored_at: str  # ISO-8601 (converted from epoch at the store boundary)
    sanitizer_flags: list[str]  # provenance: what the ingest sanitizer touched
    doc_type: str  # "chunk" | "summary"


class SearchResult(TypedDict):
    url: str
    title: str
    snippet: str
    rank: int


class FetchedDoc(TypedDict):
    url: str
    title: str
    markdown: str
    summary: str | None
    ok: bool


class Chunk(TypedDict):
    chunk_id: str
    text: str
    url: str
    title: str
    chunk_index: int


class SourceRef(TypedDict):
    url: str
    title: str
    origin: Literal["memory", "web"]


class StepError(TypedDict):
    node: str
    error_type: str
    detail: str


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


class AgentState(TypedDict):
    turn_id: str
    session_id: str
    query: str
    history: list[dict]
    threshold: float
    guard_verdict: Literal["allow", "flag", "block"]  # "flag" = proceed but skip_store
    guardrail_events: Annotated[list[str], operator.add]
    sanitized_query: str
    query_vector: list[float] | None
    memory_hits: list[MemoryHit]
    top_similarity: float | None
    search_results: list[SearchResult]
    fetched_docs: list[FetchedDoc]
    chunks: list[Chunk]
    stored_chunk_ids: list[str]
    skip_store: bool
    route: Route
    degradation: str | None  # "redis_down" | "snippets_only" | None
    answer: str | None
    sources: list[SourceRef]
    errors: Annotated[list[StepError], operator.add]
    latency_ms: Annotated[dict[str, int], _merge_dicts]
    analytics: QueryClassification | None
    tokens: Annotated[dict, _merge_dicts]  # per-model usage for the turn log
    # --- turn-bookkeeping channels (single-writer; specs/002 research D2) ---
    turn_started_at: float | None  # perf_counter() at turn start; feeds latency_ms.total (M4)
    search_provider: str | None  # "tavily" | "ddgs" | None; written by M3's web_search
