"""M6-owned integration tests: real redis:8.2 round-trip + exact similarity (FR-006..009).

Marked @integration -> skipped (never errored) when Redis is unreachable (redis_url fixture).
"""

import math
from datetime import datetime

import pytest

from memagent.memory.schema import ensure_index, get_index
from memagent.memory.store import RedisMemoryStore, _epoch_to_iso

pytestmark = pytest.mark.integration


def _page(url: str = "https://redis.io/x", title: str = "Redis") -> dict:
    return {"url": url, "title": title, "markdown": "m", "summary": None, "ok": True}


def _chunk(text: str, url: str, title: str) -> dict:
    return {"chunk_id": f"{url}:0", "text": text, "url": url, "title": title, "chunk_index": 0}


# ---- FR-006: creating the index when it already exists is idempotent (D4) ----
async def test_ensure_index_is_idempotent(redis_url, settings):
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_url)
    try:
        index = get_index(settings, client)
        if await index.exists():
            await index.delete(drop=True)  # start from no-index so we exercise both branches
        assert await ensure_index(index) is True  # created
        assert await ensure_index(index) is False  # already exists -> no-op, no raise
        assert await index.exists()  # exactly one web_memory index
    finally:
        await client.aclose()


# ---- FR-007: a stored chunk round-trips by KNN with text/url/title intact ----
async def test_store_knn_round_trip(clean_index, fake_embedder, settings):
    store = RedisMemoryStore(settings, clean_index.client)
    text = "Redis stores vectors next to data"
    page = _page()
    chunk = _chunk(text, page["url"], page["title"])
    vecs = await fake_embedder.embed([text])
    await store.store(page=page, chunks=[chunk], vectors=vecs, source_query="q", flags=[])

    hits = await store.knn((await fake_embedder.embed([text]))[0], k=5)
    assert hits
    top = hits[0]
    assert top["text"] == text
    assert top["url"] == page["url"]
    assert top["title"] == page["title"]


# ---- FR-008: url/title/fetched_at survive; stored_at is the ISO of the epoch (D5) ----
async def test_metadata_survives_with_iso_stored_at(
    clean_index, fake_embedder, settings, monkeypatch
):
    import memagent.memory.store as store_mod

    monkeypatch.setattr(store_mod.time, "time", lambda: 1751625600.0)  # pin the store clock
    store = RedisMemoryStore(settings, clean_index.client)
    text = "vector search explained"
    page = _page(url="https://redis.io/meta", title="Meta")
    chunk = _chunk(text, page["url"], page["title"])
    await store.store(
        page=page,
        chunks=[chunk],
        vectors=await fake_embedder.embed([text]),
        source_query="q",
        flags=[],
    )

    top = (await store.knn((await fake_embedder.embed([text]))[0], k=5))[0]
    assert top["url"] == page["url"]
    assert top["title"] == page["title"]
    assert top["stored_at"] == _epoch_to_iso(1751625600.0)  # exact epoch->ISO conversion
    datetime.fromisoformat(top["stored_at"])  # parses as valid ISO-8601


# ---- FR-009: similarity == 1 - vector_distance, incl. the exact 0.70 boundary (D6) ----
async def test_distance_to_similarity_exact(clean_index, settings):
    store = RedisMemoryStore(settings, clean_index.client)
    dim = settings.embedding_dim
    e0 = [0.0] * dim
    e0[0] = 1.0
    e1 = [0.0] * dim
    e1[1] = 1.0
    w = [0.0] * dim
    w[0], w[1] = 0.7, math.sqrt(1 - 0.49)  # unit vector with cos(e0, w) == 0.70

    page = _page(url="https://redis.io/vec", title="Vec")
    chunk = _chunk("anchor", page["url"], page["title"])
    await store.store(page=page, chunks=[chunk], vectors=[e0], source_query="q", flags=[])

    identical = await store.knn(e0, k=5)
    orthogonal = await store.knn(e1, k=5)
    cos07 = await store.knn(w, k=5)
    assert abs(identical[0]["similarity"] - 1.0) <= 1e-6
    assert abs(orthogonal[0]["similarity"] - 0.0) <= 1e-6
    assert abs(cos07[0]["similarity"] - 0.70) <= 1e-6
    assert cos07[0]["similarity"] >= settings.similarity_threshold - 1e-6  # inclusive hit at 0.70


# ---- FR-M3-24: the 24h freshness gate boundary (is_fresh) is exclusive (`<`) ----
async def test_is_fresh_boundary(clean_index, fake_embedder, settings, monkeypatch):
    import memagent.memory.store as store_mod
    from memagent.memory.urls import url_hash

    t0 = 1751625600.0
    monkeypatch.setattr(store_mod.time, "time", lambda: t0)  # pin the store clock at write time
    store = RedisMemoryStore(settings, clean_index.client)
    page = _page(url="https://redis.io/fresh", title="Fresh")
    chunk = _chunk("freshness body", page["url"], page["title"])
    await store.store(
        page=page,
        chunks=[chunk],
        vectors=await fake_embedder.embed(["freshness body"]),
        source_query="q",
        flags=[],
    )
    h = url_hash(page["url"])  # store writes doc:{url_hash(page["url"])}
    window = settings.freshness_window_seconds

    monkeypatch.setattr(store_mod.time, "time", lambda: t0 + window - 1)
    assert await store.is_fresh(h) is True  # 1s inside the 24h window
    monkeypatch.setattr(store_mod.time, "time", lambda: t0 + window)
    assert await store.is_fresh(h) is False  # exactly at the window: exclusive boundary
    monkeypatch.setattr(store_mod.time, "time", lambda: t0 + window + 100)
    assert await store.is_fresh(h) is False  # well past the window
    assert await store.is_fresh("deadbeefdeadbeef") is False  # unknown url -> not fresh


# ---- M8: the doc:{h} meta hash expires in step with its chunks (was written without a TTL) ----
async def test_meta_hash_has_ttl(clean_index, fake_embedder, settings):
    from memagent.memory.urls import url_hash

    store = RedisMemoryStore(settings, clean_index.client)
    page = _page(url="https://redis.io/ttl-meta", title="TTL")
    chunk = _chunk("body text", page["url"], page["title"])
    await store.store(
        page=page,
        chunks=[chunk],
        vectors=await fake_embedder.embed(["body text"]),
        source_query="q",
        flags=[],
    )
    ttl = await clean_index.client.ttl(f"doc:{url_hash(page['url'])}")
    assert 0 < ttl <= settings.memory_ttl_seconds  # bounded expiry, not -1 (unbounded)
