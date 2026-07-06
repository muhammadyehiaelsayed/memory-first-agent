"""Agent facade: build_resources() + Agent.answer() -> TurnResult + logging setup."""

import logging
import sys
import time
from typing import NamedTuple
from uuid import uuid4

import structlog

from memagent.analytics.turnlog import TurnLogger
from memagent.config import Settings
from memagent.graph import build_graph
from memagent.llm.clients import build_openai_clients
from memagent.memory.schema import assert_index_dims
from memagent.memory.store import RedisMemoryStore, make_redis_client
from memagent.resources import AgentResources
from memagent.state import SourceRef
from memagent.web.fetch import HttpxPageFetcher
from memagent.web.search import FallbackProvider


class TurnResult(NamedTuple):
    route: str
    answer: str | None
    sources: list[SourceRef]
    similarity: float | None
    degradation: str | None = None


def configure_logging(settings: Settings) -> None:
    """Operational logs -> STDERR only (stdout stays pipe-clean, FR-M4-21)."""
    logging.basicConfig(
        stream=sys.stderr, level=getattr(logging, settings.log_level.upper(), logging.INFO)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def new_turn_state(
    settings: Settings, session_id: str, query: str, history: list[dict] | None = None
) -> dict:
    """The ONE complete initial AgentState (FR-M2-22) — shared by Agent.answer and the REPL."""
    return {
        "turn_id": str(uuid4()),
        "session_id": session_id,
        "query": query,
        "history": (history or [])[-settings.history_max_turns * 2 :],
        "threshold": settings.similarity_threshold,
        "guard_verdict": "allow",  # guard_input overwrites this before routing
        "guardrail_events": [],
        "sanitized_query": query,  # guard_input replaces this with the L1-normalized form
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
        "turn_started_at": time.perf_counter(),  # feeds latency_ms.total (log_turn)
        "search_provider": None,
    }


def build_resources(settings: Settings | None = None) -> AgentResources:
    settings = settings if settings is not None else Settings()
    chat_llm, analytics_llm, embedder = build_openai_clients(settings)  # ONE shared transport
    assert_index_dims(embedder.dim, settings)
    client = make_redis_client(settings)  # M5: native Retry (3) + 2s socket timeouts
    return AgentResources(
        settings=settings,
        memory=RedisMemoryStore(settings, client),
        embedder=embedder,
        chat_llm=chat_llm,
        analytics_llm=analytics_llm,
        searcher=FallbackProvider(settings),
        fetcher=HttpxPageFetcher(settings),
        turn_logger=TurnLogger(settings.turn_log_path),
    )


class Agent:
    def __init__(self, resources: AgentResources | None = None):
        self.resources = resources if resources is not None else build_resources()
        self.graph = build_graph(self.resources)
        self.session_id = str(uuid4())

    async def answer(self, query: str) -> TurnResult:
        state = new_turn_state(self.resources.settings, self.session_id, query)
        structlog.contextvars.bind_contextvars(turn_id=state["turn_id"])
        try:
            final = await self.graph.ainvoke(state)
        finally:
            structlog.contextvars.clear_contextvars()
        return TurnResult(
            route=final["route"],
            answer=final.get("answer"),
            sources=final.get("sources", []),
            similarity=final.get("top_similarity"),
            degradation=final.get("degradation"),
        )
