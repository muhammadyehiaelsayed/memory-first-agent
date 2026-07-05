"""Frozen resources container passed to build_graph (verbatim PLAN section 3.4).

Forward-referenced types stay unevaluated strings (from __future__ import annotations);
never call typing.get_type_hints on AgentResources.
"""

from __future__ import annotations

from dataclasses import dataclass

from memagent.config import Settings
from memagent.interfaces import (
    ChatLLM,
    Embedder,
    MemoryStore,
    PageFetcher,
    TurnLogger,
    WebSearcher,
)


@dataclass(frozen=True)
class AgentResources:
    settings: Settings
    memory: MemoryStore
    embedder: Embedder
    chat_llm: ChatLLM
    analytics_llm: ChatLLM
    searcher: WebSearcher
    fetcher: PageFetcher
    turn_logger: TurnLogger
