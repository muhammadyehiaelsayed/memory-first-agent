"""Dependency-injection Protocols (verbatim PLAN section 3.4).

MemoryStore.knn returns the RAW unfiltered top-k with similarity attached — threshold
filtering lives in routers/nodes only (a store that filters is a contract violation).
"""

from typing import NamedTuple, Protocol

from pydantic import BaseModel

from memagent.state import Chunk, FetchedDoc, MemoryHit, SearchResult


class Embedder(Protocol):
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class CompletionResult(NamedTuple):
    text: str
    usage: dict          # {"input_tokens": int, "output_tokens": int, "model": str}


class ChatLLM(Protocol):
    async def complete(self, system: str, messages: list[dict]) -> CompletionResult: ...

    async def parse(
        self, system: str, user: str, schema: type[BaseModel]
    ) -> tuple[BaseModel, dict]: ...


class WebSearcher(Protocol):
    async def search(self, query: str, k: int) -> list[SearchResult]: ...


class MemoryStore(Protocol):
    async def knn(self, vector: list[float], k: int) -> list[MemoryHit]:  # RAW top-k, NO filtering
        ...

    async def store(
        self,
        page: FetchedDoc,
        chunks: list[Chunk],
        vectors: list[list[float]],
        source_query: str,
        flags: list[str],
    ) -> list[str]: ...

    async def is_fresh(self, h: str) -> bool:  # h = url_hash(canonicalize(url)); 24h window
        ...


class PageFetcher(Protocol):
    """Bounded concurrent page fetching; the fetch_pages node filters and passes plain URLs."""

    async def fetch(self, urls: list[str]) -> list[FetchedDoc]: ...


class TurnLogger(Protocol):
    """One TurnRecord JSON line appended per turn (analytics/turnlog.py, M4)."""

    def log(self, record: dict) -> None: ...
