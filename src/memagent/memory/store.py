"""Redis vector memory store.

distance_to_similarity is THE one conversion site in the entire codebase
(Constitution P-II): Redis COSINE returns distance d = 1 - cosine_similarity (the
metric normalizes internally), so similarity is exactly 1 - d for any inputs.

knn returns the RAW unfiltered top-k (threshold routing lives in routers only).
Redis-down calls surface as the typed MemoryUnavailableError via the _io translation
wrapper below; the degraded-route decision itself belongs to the graph's routers.
"""

import hashlib
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
from redis import exceptions as redis_exceptions
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redisvl.exceptions import RedisSearchError
from redisvl.query import VectorQuery
from redisvl.redis.utils import array_to_buffer

from memagent.config import Settings
from memagent.memory.urls import url_hash
from memagent.state import Chunk, FetchedDoc, MemoryHit
from memagent.utils.errors import MemoryUnavailableError, redis_down_in_chain


def make_redis_client(settings: Settings):
    """Async redis client with native Retry (3 retries = 4 total tries; ~1s cap; 2s socket).

    ConnectionError/TimeoutError retry; ResponseError (a programming bug) is NOT retried and
    surfaces loudly. Used by app.build_resources and cli._wipe (one construction site).
    """
    return aioredis.from_url(
        settings.redis_url,
        retry=Retry(ExponentialBackoff(cap=1.0), 3),
        retry_on_error=[redis_exceptions.ConnectionError, redis_exceptions.TimeoutError],
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
    )


def _as_memory_error(exc: BaseException) -> MemoryUnavailableError | None:
    """Return a MemoryUnavailableError if exc is a (possibly redisvl-wrapped) redis outage."""
    if isinstance(exc, MemoryUnavailableError):
        return exc
    if isinstance(exc, RedisSearchError) and redis_down_in_chain(exc):
        return MemoryUnavailableError(str(exc))
    if redis_down_in_chain(exc):
        return MemoryUnavailableError(str(exc))
    return None


_RETURN_FIELDS = [
    "chunk_text",
    "url",
    "url_hash",
    "title",
    "doc_type",
    "source_query",
    "chunk_index",
    "fetched_at",
    "sanitizer_flags",
    "content_sha256",
]


def distance_to_similarity(distance: float) -> float:
    return 1.0 - distance


def _epoch_to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


class RedisMemoryStore:
    """Implements the MemoryStore Protocol over M1's web_memory schema."""

    def __init__(self, settings: Settings, client):
        from memagent.memory.schema import get_index  # M1-owned module

        self._settings = settings
        self._redis = client
        self._index = get_index(settings, client)
        self._index_ensured = False

    async def ensure_ready(self) -> None:
        """Idempotently create the web_memory index — called once at Agent startup.

        `make redis-up -> make run` provisions no index, so the first knn would otherwise
        raise RedisSearchError (a missing index, NOT a redis outage) and escape the
        memory_search guard, crashing the documented quickstart. ensure_index is
        exists-guarded — it never drops data and is a no-op once the index exists (checked
        once per store lifetime). A redis outage here degrades via the typed error, exactly
        like every other store call; a genuine schema/programming error still surfaces loudly.
        """
        if self._index_ensured:
            return
        from memagent.memory.schema import ensure_index

        try:
            await ensure_index(self._index)
        except Exception as exc:  # noqa: BLE001 — outage -> typed error; real bugs re-raise
            if err := _as_memory_error(exc):
                raise err from exc
            raise
        self._index_ensured = True

    async def _io(self, coro):
        """Await a redis coroutine, translating a (possibly wrapped) outage to the typed error.

        ResponseError and other programming bugs are NOT translated — they surface loudly.
        """
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001
            if err := _as_memory_error(exc):
                raise err from exc
            raise

    async def knn(self, vector: list[float], k: int) -> list[MemoryHit]:
        query = VectorQuery(
            vector=vector,
            vector_field_name="embedding",
            return_fields=_RETURN_FIELDS,
            num_results=k,
            dtype="float32",
        )
        results = await self._io(self._index.query(query))
        hits: list[MemoryHit] = []
        for r in results:
            flags = (r.get("sanitizer_flags") or "").strip()
            hits.append(
                MemoryHit(
                    doc_id=r.get("id", ""),
                    text=r.get("chunk_text", ""),
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    similarity=distance_to_similarity(float(r["vector_distance"])),
                    stored_at=_epoch_to_iso(float(r.get("fetched_at", 0))),
                    sanitizer_flags=flags.split(",") if flags else [],
                    doc_type=r.get("doc_type", "chunk"),
                )
            )
        hits.sort(key=lambda h: h["similarity"], reverse=True)
        return hits

    async def store(
        self,
        page: FetchedDoc,
        chunks: list[Chunk],
        vectors: list[list[float]],
        source_query: str,
        flags: list[str],
    ) -> list[str]:
        h = url_hash(page["url"])
        cp = self._settings.memory_chunk_prefix
        mp = self._settings.memory_meta_prefix
        meta_key = f"{mp}:{h}"
        summary = page.get("summary")

        expected = len(chunks) + (1 if summary is not None else 0)
        if len(vectors) != expected:
            raise ValueError(
                f"vector alignment violated: got {len(vectors)} vectors for {len(chunks)} "
                f"chunks (summary={'present' if summary is not None else 'absent'}); "
                f"expected {expected}"
            )

        # Deterministic upsert: remove the previous generation without SCAN.
        old = await self._io(self._redis.hgetall(meta_key))
        if old:
            old_n = int(old.get(b"num_chunks", b"0"))
            stale = [f"{cp}:{h}:{i}" for i in range(old_n)] + [f"{cp}:{h}:summary"]
            await self._io(self._redis.delete(*stale))

        fetched_at = int(time.time())
        ttl = self._settings.memory_ttl_seconds
        flags_csv = ",".join(flags)
        chunk_vectors = vectors[1:] if summary is not None else vectors
        stored_ids: list[str] = []

        # Batch every write (summary + chunks + meta) into ONE pipeline round-trip instead of
        # ~2 serial round-trips per chunk. Pipeline command methods buffer synchronously (not
        # awaited); only execute() is awaited, and _io still translates a redis outage there.
        # transaction=False keeps the same non-atomicity the prior serial hset->expire had.
        async with self._redis.pipeline(transaction=False) as pipe:

            def _queue(key: str, text: str, doc_type: str, chunk_index: int, vec: list[float]):
                pipe.hset(
                    key,
                    mapping={
                        "chunk_text": text,
                        "url": page["url"],
                        "url_hash": h,
                        "title": page["title"],
                        "doc_type": doc_type,
                        "source_query": source_query,
                        "chunk_index": chunk_index,
                        "fetched_at": fetched_at,
                        "sanitizer_flags": flags_csv,
                        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "embedding": array_to_buffer(vec, dtype="float32"),
                    },
                )
                if ttl > 0:
                    pipe.expire(key, ttl)

            if summary is not None:
                _queue(f"{cp}:{h}:summary", summary, "summary", -1, vectors[0])

            for i, (chunk, vec) in enumerate(zip(chunks, chunk_vectors)):
                key = f"{cp}:{h}:{i}"
                _queue(key, chunk["text"], "chunk", i, vec)
                stored_ids.append(key)

            pipe.hset(
                meta_key,
                mapping={"num_chunks": len(chunks), "fetched_at": fetched_at, "url": page["url"]},
            )
            if ttl > 0:  # freshness bookkeeping expires in step with the chunks it describes
                pipe.expire(meta_key, ttl)

            await self._io(pipe.execute())
        return stored_ids

    async def is_fresh(self, h: str) -> bool:
        meta_key = f"{self._settings.memory_meta_prefix}:{h}"
        fetched_at = await self._io(self._redis.hget(meta_key, "fetched_at"))
        if fetched_at is None:
            return False
        return time.time() - float(fetched_at) < self._settings.freshness_window_seconds
