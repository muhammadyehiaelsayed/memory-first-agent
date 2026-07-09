"""Agent facade: build_resources() + Agent.answer() -> TurnResult + logging/tracing setup."""

import logging
import os
import sys
import time
from collections.abc import MutableMapping
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
    """Operational logs -> STDERR only (stdout stays pipe-clean, FR-M4-21).

    On an interactive terminal the operational chatter — httpx request lines, per-node
    structlog breadcrumbs, and tenacity retry WARNINGs (e.g. rate-limit backoff) — is
    silenced so it never clutters the live spinner; the graded per-turn record in
    logs/turns.jsonl is written regardless, so real observability is untouched, and a
    failed turn still surfaces its apology on stdout. Piped / CI runs (stderr is not a
    TTY) keep the full ``settings.log_level`` for debugging, and an explicit
    ``LOG_LEVEL`` always wins.
    """
    settings_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    if os.getenv("LOG_LEVEL"):
        level = settings_level  # user asked for a specific level — honour it everywhere
    elif sys.stderr.isatty():
        level = logging.CRITICAL  # interactive: only the spinner + result, no log noise
    else:
        level = settings_level  # piped / CI: keep full logs on stderr
    logging.basicConfig(stream=sys.stderr, level=level)
    logging.getLogger().setLevel(level)  # applies even if basicConfig already ran
    logging.getLogger("httpx").setLevel(level)
    logging.getLogger("httpcore").setLevel(level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def configure_tracing(settings: Settings, env: MutableMapping[str, str] | None = None) -> bool:
    """Opt-in LangSmith tracing — off by default, so the default posture stays zero-egress.

    When LANGSMITH_TRACING=true AND an API key is set, export the standard LANGSMITH_*
    variables so langgraph's built-in instrumentation uploads one trace per turn: the
    compiled "memagent" graph run with a child span per node, plus the conversation LLM
    calls (build_openai_clients wraps the shared transport). The export step exists
    because Settings reads .env itself without touching os.environ, while the langsmith
    SDK only sees real environment variables. Traces complement — never replace —
    logs/turns.jsonl, which stays the offline, keyless source of truth for analytics.
    ``env`` is an injection seam for tests; returns True when tracing was enabled.
    """
    target = os.environ if env is None else env
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        return False
    target["LANGSMITH_TRACING"] = "true"
    target["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    target["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    target["LANGSMITH_PROJECT"] = settings.langsmith_project
    return True


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
    configure_tracing(settings)  # before the clients so the wrapped transport is traceable
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
        self._ready = False

    async def ensure_ready(self) -> None:
        """Provision the vector index once before the first turn (idempotent).

        Covers the fresh-Redis quickstart (`make redis-up -> make run`): without it the first
        memory_search would hit a missing index and crash. answer() calls this lazily; the
        REPL (which drives the graph directly) calls it before its loop.
        """
        if self._ready:
            return
        await self.resources.memory.ensure_ready()
        self._ready = True

    async def answer(self, query: str) -> TurnResult:
        await self.ensure_ready()
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
