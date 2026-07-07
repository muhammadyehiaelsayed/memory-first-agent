"""Executable binding for features/memory_store.feature.

Self-contained, keyless. Pure helpers (distance_to_similarity, _epoch_to_iso,
make_redis_client, _as_memory_error) are exercised with no I/O. The store
behaviours (knn / store / is_fresh / __init__ / _io) drive the REAL
RedisMemoryStore against the live redis:8.2 on this machine; the whole
client lifecycle (connect -> wipe -> act -> aclose) runs inside a single
``asyncio.run`` per scenario because sync pytest-bdd steps cannot consume the
async ``clean_index`` fixture and an aioredis client is bound to one loop.

The keyless ``settings`` / ``fake_embedder`` fixtures and the sync
skip-if-down ``redis_url`` fixture come from tests/conftest.py.
"""

import asyncio
import math

import redis.asyncio as aioredis
from pytest_bdd import given, parsers, scenarios, then, when
from redis import exceptions as redis_exceptions
from redisvl.exceptions import RedisSearchError

import memagent.memory.store as store_mod
from memagent.memory.schema import get_index, wipe_index
from memagent.memory.store import (
    RedisMemoryStore,
    _as_memory_error,
    _epoch_to_iso,
    distance_to_similarity,
    make_redis_client,
)
from memagent.memory.urls import url_hash
from memagent.utils.errors import MemoryUnavailableError

scenarios("features/memory_store.feature")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _page(url: str, title: str) -> dict:
    return {"url": url, "title": title, "markdown": "m", "summary": None, "ok": True}


def _chunk(text: str, url: str, title: str, i: int = 0) -> dict:
    return {"chunk_id": f"{url}:{i}", "text": text, "url": url, "title": title, "chunk_index": i}


# ========================================================================== #
# Scenario: distance -> similarity conversion (pure)
# ========================================================================== #
@given(parsers.parse("a cosine vector distance of {distance:g}"), target_fixture="ctx")
def _given_distance(distance):
    return {"distance": distance}


@when("the distance is converted to a similarity")
def _convert_distance(ctx):
    ctx["similarity"] = distance_to_similarity(ctx["distance"])


@then(parsers.parse("the similarity is {expected:g}, exactly one minus the distance"))
def _similarity_is(ctx, expected):
    assert abs(ctx["similarity"] - expected) < 1e-9
    assert abs(ctx["similarity"] - (1.0 - ctx["distance"])) < 1e-12


@then(parsers.parse("the discredited half-distance formula that would yield {wrong:g} is not used"))
def _not_half_formula(ctx, wrong):
    assert ctx["similarity"] != wrong


@then("distance 0.0 converts to similarity 1.0 and distance 1.0 converts to similarity 0.0")
def _extremes():
    assert distance_to_similarity(0.0) == 1.0
    assert distance_to_similarity(1.0) == 0.0


# ========================================================================== #
# Scenario: epoch -> ISO
# ========================================================================== #
@given(parsers.parse("an epoch timestamp of {epoch:g} seconds"), target_fixture="ctx")
def _given_epoch(epoch):
    return {"epoch": epoch}


@when("the timestamp is converted to a stored-at string")
def _convert_epoch(ctx):
    ctx["iso"] = _epoch_to_iso(ctx["epoch"])


@then(parsers.parse('the string is the ISO-8601 UTC instant "{expected}"'))
def _iso_equals(ctx, expected):
    assert ctx["iso"] == expected


@then("the string parses back as a valid ISO-8601 datetime")
def _iso_parses(ctx):
    from datetime import datetime

    parsed = datetime.fromisoformat(ctx["iso"])
    assert parsed.utcoffset() is not None  # carries a UTC offset


# ========================================================================== #
# Scenario: make_redis_client
# ========================================================================== #
@given("the application settings", target_fixture="ctx")
def _given_settings(settings):
    return {"settings": settings}


@when("a Redis client is built for the store")
def _build_client(ctx):
    ctx["client"] = make_redis_client(ctx["settings"])


@then("the client retries only connection and timeout errors, three retries deep")
def _client_retry_policy(ctx):
    kwargs = ctx["client"].connection_pool.connection_kwargs
    retry_on = {e.__name__ for e in kwargs["retry_on_error"]}
    assert retry_on == {"ConnectionError", "TimeoutError"}
    assert kwargs["retry"].get_retries() == 3


@then("its socket read and connect timeouts are capped at two seconds")
def _client_socket_timeouts(ctx):
    kwargs = ctx["client"].connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == 2.0
    assert kwargs["socket_connect_timeout"] == 2.0


# ========================================================================== #
# Scenario: _as_memory_error
# ========================================================================== #
@given(
    "a redisvl RedisSearchError wrapping a Redis connection failure in its cause chain",
    target_fixture="ctx",
)
def _given_wrapped_error():
    wrapped = RedisSearchError("index query failed")
    wrapped.__cause__ = redis_exceptions.ConnectionError("connection refused")
    return {"wrapped": wrapped}


@when("the exception is examined for a memory outage")
def _examine_error(ctx):
    ctx["translated"] = _as_memory_error(ctx["wrapped"])


@then("it is translated into a typed MemoryUnavailableError")
def _translated_typed(ctx):
    assert isinstance(ctx["translated"], MemoryUnavailableError)


@then("a bare Redis connection failure is also recognised as a memory outage")
def _bare_conn_recognised():
    assert isinstance(
        _as_memory_error(redis_exceptions.ConnectionError("down")), MemoryUnavailableError
    )


@then("a plain Redis ResponseError, which signals a programming bug, is not translated")
def _response_error_not_translated():
    assert _as_memory_error(redis_exceptions.ResponseError("bad arg")) is None


# ========================================================================== #
# Scenario: RedisMemoryStore.__init__
# ========================================================================== #
@given("the application settings and a Redis client", target_fixture="ctx")
def _given_settings_and_client(settings):
    return {"settings": settings, "client": make_redis_client(settings)}


@when("a RedisMemoryStore is constructed over them")
def _construct_store(ctx):
    ctx["store"] = RedisMemoryStore(ctx["settings"], ctx["client"])


@then('it opens the shared "web_memory" vector index against that client')
def _index_opened(ctx):
    index = ctx["store"]._index
    assert index.schema.index.name == ctx["settings"].memory_index_name == "web_memory"
    assert index.client is ctx["client"]


@then("it retains the settings it was given")
def _settings_retained(ctx):
    assert ctx["store"]._settings is ctx["settings"]


# ========================================================================== #
# Scenario: RedisMemoryStore._io
# ========================================================================== #
@given("a constructed RedisMemoryStore", target_fixture="ctx")
def _given_constructed_store(settings):
    return {"store": RedisMemoryStore(settings, make_redis_client(settings))}


@when("a guarded I/O operation raises a Redis connection failure")
def _io_raises_conn(ctx):
    store = ctx["store"]

    async def _flow():
        async def _ok():
            return "the-value"

        async def _boom():
            raise redis_exceptions.ConnectionError("connection reset")

        async def _bug():
            raise redis_exceptions.ResponseError("wrong number of arguments")

        outcome = {}
        try:
            await store._io(_boom())
        except MemoryUnavailableError as exc:
            outcome["translated"] = exc
        outcome["ok_value"] = await store._io(_ok())
        try:
            await store._io(_bug())
        except redis_exceptions.ResponseError as exc:
            outcome["response_error"] = exc
        return outcome

    ctx["io"] = asyncio.run(_flow())


@then("the store surfaces it as a typed MemoryUnavailableError")
def _io_translated(ctx):
    assert isinstance(ctx["io"]["translated"], MemoryUnavailableError)


@then("a successful guarded operation returns its value unchanged")
def _io_ok_value(ctx):
    assert ctx["io"]["ok_value"] == "the-value"


@then("a Redis ResponseError from a guarded operation is left to surface untranslated")
def _io_response_error(ctx):
    assert isinstance(ctx["io"]["response_error"], redis_exceptions.ResponseError)


# ========================================================================== #
# Scenario: knn round-trip + inclusive 0.70 boundary (LIVE redis)
# ========================================================================== #
@given(
    "an empty web_memory index holding a single chunk anchored at a known unit embedding",
    target_fixture="ctx",
)
def _given_anchor(settings, redis_url):
    return {"settings": settings, "redis_url": redis_url}


@when("the anchor content is looked up by nearest-neighbour search")
def _knn_lookup(ctx):
    settings = ctx["settings"]
    dim = settings.embedding_dim

    async def _flow():
        client = aioredis.from_url(settings.redis_url)
        try:
            await wipe_index(get_index(settings, client))
            store = RedisMemoryStore(settings, client)
            e0 = [0.0] * dim
            e0[0] = 1.0
            e1 = [0.0] * dim
            e1[1] = 1.0
            w = [0.0] * dim
            w[0], w[1] = 0.7, math.sqrt(1 - 0.49)  # unit vector at cosine 0.70 to e0
            page = _page("https://redis.io/anchor", "Anchor")
            await store.store(
                page=page,
                chunks=[_chunk("anchor body", page["url"], page["title"])],
                vectors=[e0],
                source_query="seed",
                flags=[],
            )
            identical = await store.knn(e0, k=5)
            orthogonal = await store.knn(e1, k=5)
            cos07 = await store.knn(w, k=5)
            # re-wipe to a truly empty index -> a miss must be [] not an error
            await wipe_index(get_index(settings, client))
            empty = await store.knn(e0, k=5)
            return identical, orthogonal, cos07, empty
        finally:
            await client.aclose()

    ident, orth, cos07, empty = asyncio.run(_flow())
    ctx.update(identical=ident, orthogonal=orth, cos07=cos07, empty=empty)


@then("the top hit carries similarity 1.0 with its text, url and title intact")
def _knn_top_hit(ctx):
    top = ctx["identical"][0]
    assert abs(top["similarity"] - 1.0) <= 1e-6
    assert top["text"] == "anchor body"
    assert top["url"] == "https://redis.io/anchor"
    assert top["title"] == "Anchor"


@then(
    "a query at cosine 0.70 to the anchor scores exactly 0.70, "
    "an inclusive hit at the 0.70 threshold"
)
def _knn_boundary(ctx):
    sim = ctx["cos07"][0]["similarity"]
    assert abs(sim - 0.70) <= 1e-6
    assert sim >= ctx["settings"].similarity_threshold - 1e-6


@then("an orthogonal query scores 0.0")
def _knn_orthogonal(ctx):
    assert abs(ctx["orthogonal"][0]["similarity"] - 0.0) <= 1e-6


@then("a nearest-neighbour lookup against a truly empty index returns an empty list")
def _knn_empty(ctx):
    assert ctx["empty"] == []


# ========================================================================== #
# Scenario: store round-trip + upsert pruning (LIVE redis)
# ========================================================================== #
@given("an empty web_memory index", target_fixture="ctx")
def _given_empty_index(settings, fake_embedder, redis_url):
    return {"settings": settings, "embedder": fake_embedder}


@when("a page with six chunks is ingested into the store")
def _ingest_six(ctx):
    settings = ctx["settings"]
    embedder = ctx["embedder"]
    url = "https://redis.io/upsert"
    texts = [f"redis chunk body number {i} explaining vector search" for i in range(6)]

    async def _flow():
        client = aioredis.from_url(settings.redis_url)
        try:
            await wipe_index(get_index(settings, client))
            store = RedisMemoryStore(settings, client)
            page = _page(url, "Upsert")
            chunks6 = [_chunk(t, url, "Upsert", i) for i, t in enumerate(texts)]
            vecs6 = await embedder.embed(texts)
            ids6 = await store.store(
                page=page, chunks=chunks6, vectors=vecs6, source_query="seed", flags=[]
            )
            h = url_hash(url)
            ttl0 = await client.ttl(f"chunk:{h}:0")
            # round-trip the first chunk back out by KNN of its own embedding
            hits = await store.knn((await embedder.embed([texts[0]]))[0], k=5)
            top = hits[0]
            # re-store the same URL with only three chunks
            texts3 = texts[:3]
            chunks3 = [_chunk(t, url, "Upsert", i) for i, t in enumerate(texts3)]
            vecs3 = await embedder.embed(texts3)
            ids3 = await store.store(
                page=page, chunks=chunks3, vectors=vecs3, source_query="seed", flags=[]
            )
            exists_stale = await client.exists(f"chunk:{h}:3", f"chunk:{h}:5")
            exists_kept = await client.exists(f"chunk:{h}:2")
            num = await client.hget(f"doc:{h}", "num_chunks")
            return {
                "ids6": ids6,
                "ttl0": ttl0,
                "top": top,
                "ids3": ids3,
                "exists_stale": exists_stale,
                "exists_kept": exists_kept,
                "num": int(num),
            }
        finally:
            await client.aclose()

    ctx["res"] = asyncio.run(_flow())


@then("each chunk key carries a bounded positive TTL no greater than 604800 seconds")
def _store_ttl(ctx):
    res = ctx["res"]
    assert len(res["ids6"]) == 6
    assert 0 < res["ttl0"] <= ctx["settings"].memory_ttl_seconds == 604800


@then("the page content and metadata round-trip back out through nearest-neighbour search")
def _store_round_trip(ctx):
    top = ctx["res"]["top"]
    assert top["url"] == "https://redis.io/upsert"
    assert top["title"] == "Upsert"
    assert top["text"].startswith("redis chunk body number 0")


@then(
    "re-storing the same URL with three chunks removes the stale chunk keys "
    "and sets the meta count to three"
)
def _store_upsert_prune(ctx):
    res = ctx["res"]
    assert len(res["ids3"]) == 3
    assert res["exists_stale"] == 0  # neither chunk:{h}:3 nor chunk:{h}:5 remains
    assert res["exists_kept"] == 1  # chunk:{h}:2 is still a live chunk
    assert res["num"] == 3


# ========================================================================== #
# Scenario: is_fresh boundary (LIVE redis + monkeypatched clock)
# ========================================================================== #
@given("a page stored at a pinned instant", target_fixture="ctx")
def _given_pinned_page(settings, fake_embedder, redis_url):
    return {"settings": settings, "embedder": fake_embedder}


@when("the freshness of its URL is checked as time advances across the 24h window")
def _check_freshness(ctx):
    settings = ctx["settings"]
    embedder = ctx["embedder"]
    t0 = 1751625600.0
    clock = [t0]
    original = store_mod.time.time
    store_mod.time.time = lambda: clock[0]

    async def _flow():
        client = aioredis.from_url(settings.redis_url)
        try:
            await wipe_index(get_index(settings, client))
            store = RedisMemoryStore(settings, client)
            url = "https://redis.io/fresh"
            page = _page(url, "Fresh")
            await store.store(
                page=page,
                chunks=[_chunk("freshness body", url, "Fresh")],
                vectors=await embedder.embed(["freshness body"]),
                source_query="seed",
                flags=[],
            )
            h = url_hash(url)
            window = settings.freshness_window_seconds
            clock[0] = t0 + window - 1
            inside = await store.is_fresh(h)
            clock[0] = t0 + window
            at_boundary = await store.is_fresh(h)
            clock[0] = t0 + window + 100
            past = await store.is_fresh(h)
            unknown = await store.is_fresh("deadbeefdeadbeef")
            return inside, at_boundary, past, unknown
        finally:
            await client.aclose()

    try:
        inside, at_boundary, past, unknown = asyncio.run(_flow())
    finally:
        store_mod.time.time = original
    ctx.update(inside=inside, at_boundary=at_boundary, past=past, unknown=unknown)


@then("the URL is fresh one second inside the window")
def _fresh_inside(ctx):
    assert ctx["inside"] is True


@then("the URL is not fresh exactly at the window boundary")
def _fresh_at_boundary(ctx):
    assert ctx["at_boundary"] is False


@then("the URL is not fresh well past the window")
def _fresh_past(ctx):
    assert ctx["past"] is False


@then("an unknown URL is never reported fresh")
def _fresh_unknown(ctx):
    assert ctx["unknown"] is False
