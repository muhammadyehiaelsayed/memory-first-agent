"""Agent facade: build_resources() + Agent.answer() -> TurnResult."""

import time
from typing import NamedTuple
from uuid import uuid4

import redis.asyncio as aioredis

from memagent.config import Settings
from memagent.graph import build_graph
from memagent.llm.clients import OpenAIChatLLM, OpenAIEmbedder
from memagent.memory.schema import assert_index_dims
from memagent.memory.store import RedisMemoryStore
from memagent.resources import AgentResources
from memagent.state import SourceRef
from memagent.web.fetch import HttpxPageFetcher
from memagent.web.search import FallbackProvider


class TurnResult(NamedTuple):
    route: str
    answer: str | None
    sources: list[SourceRef]
    similarity: float | None


class _NoopTurnLogger:
    """Stub — replaced by M4's JSONL TurnLogger."""

    def log(self, record: dict) -> None:  # noqa: ARG002
        return None


def build_resources(settings: Settings | None = None) -> AgentResources:
    settings = settings if settings is not None else Settings()
    embedder = OpenAIEmbedder(settings)
    assert_index_dims(embedder.dim, settings)
    client = aioredis.from_url(settings.redis_url)
    return AgentResources(
        settings=settings,
        memory=RedisMemoryStore(settings, client),
        embedder=embedder,
        chat_llm=OpenAIChatLLM(settings, settings.conversation_model),
        analytics_llm=OpenAIChatLLM(settings, settings.analytics_model),
        searcher=FallbackProvider(settings),
        fetcher=HttpxPageFetcher(settings),
        turn_logger=_NoopTurnLogger(),
    )


class Agent:
    def __init__(self, resources: AgentResources | None = None):
        self.resources = resources if resources is not None else build_resources()
        self.graph = build_graph(self.resources)
        self.session_id = str(uuid4())

    async def answer(self, query: str) -> TurnResult:
        settings = self.resources.settings
        state = {
            "turn_id": str(uuid4()),
            "session_id": self.session_id,
            "query": query,
            "history": [],                      # per-turn stateless; REPL history is M4
            "threshold": settings.similarity_threshold,
            "guard_verdict": "allow",           # guard node activates in M5 (Ruling F)
            "guardrail_events": [],
            "sanitized_query": query,           # L1 sanitization lands in M5
            "query_vector": None,
            "memory_hits": [],
            "top_similarity": None,
            "search_results": [],
            "fetched_docs": [],
            "chunks": [],
            "stored_chunk_ids": [],
            "skip_store": False,
            "route": "failed",
            "degradation": None,
            "answer": None,
            "sources": [],
            "errors": [],
            "latency_ms": {},
            "analytics": None,
            "tokens": {},
            "turn_started_at": time.perf_counter(),
            "search_provider": None,
        }
        final = await self.graph.ainvoke(state)
        return TurnResult(
            route=final["route"],
            answer=final.get("answer"),
            sources=final.get("sources", []),
            similarity=final.get("top_similarity"),
        )
