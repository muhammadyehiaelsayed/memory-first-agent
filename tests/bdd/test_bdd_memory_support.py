"""Executable binding for the memory_support batch feature files.

Covers the memory-layer support modules: the web_memory index schema
(memory/schema.py), URL canonicalisation + identity hashing (memory/urls.py),
and markdown-aware chunking (memory/chunking.py).

Redis-backed schema-lifecycle scenarios use the keyless `settings` + `redis_url`
skip-not-fail fixtures from tests/conftest.py. pytest-bdd generates SYNC tests,
so every step that touches an async schema helper opens its own redis client
inside a single `asyncio.run(...)` call (client + ops + aclose share one event
loop, avoiding the cross-loop attachment error). Every other scenario is fully
keyless and network-free.
"""

import asyncio

import redis.asyncio as aioredis
from pytest_bdd import given, parsers, scenarios, then, when
from redisvl.index import AsyncSearchIndex

from memagent.config import Settings
from memagent.memory.chunking import chunk_markdown
from memagent.memory.schema import (
    assert_index_dims,
    build_schema,
    ensure_index,
    get_index,
    wipe_index,
)
from memagent.memory.urls import canonicalize, url_hash

scenarios("features/memory_schema.feature")
scenarios("features/memory_urls.feature")
scenarios("features/memory_chunking.feature")


# ---------------------------------------------------------------------------
# memory_schema.feature — build_schema
# ---------------------------------------------------------------------------
@when("the web_memory schema is built from settings", target_fixture="schema_dict")
def build_the_schema():
    # pins the DEFAULT shipped schema (name "web_memory", prefix "chunk") — uses a fresh
    # default Settings, not the isolated test fixture that overrides those for demo safety
    return build_schema(Settings(_env_file=None)).to_dict()


@then(parsers.parse("it declares exactly {n:d} fields named {names}"))
def check_field_names(schema_dict, n, names):
    got = [f["name"] for f in schema_dict["fields"]]
    assert len(got) == n
    assert set(got) == {name.strip() for name in names.split(",")}


@then(parsers.parse('the index name is "{name}" with hash storage and a "{prefix}" prefix'))
def check_index_identity(schema_dict, name, prefix):
    index = schema_dict["index"]
    assert index["name"] == name
    assert index["storage_type"] == "hash"
    assert index["prefix"] == prefix


@then(parsers.parse("the embedding field is a flat cosine float32 vector of {dims:d} dims"))
def check_embedding_field(schema_dict, dims):
    emb = next(f for f in schema_dict["fields"] if f["name"] == "embedding")
    assert emb["type"] == "vector"
    attrs = emb["attrs"]
    assert attrs["algorithm"] == "flat"
    assert attrs["distance_metric"] == "cosine"
    assert attrs["datatype"] == "float32"
    assert attrs["dims"] == dims


# ---------------------------------------------------------------------------
# memory_schema.feature — get_index
# ---------------------------------------------------------------------------
@given("a Redis client for the configured URL", target_fixture="redis_client")
def a_redis_client(settings):
    return aioredis.from_url(settings.redis_url)


@when("an index is built from the schema and that client", target_fixture="built_index")
def build_index_over_client(redis_client):
    # default schema (named "web_memory") over the lazy client — a construction-only check,
    # so it pins the shipped name rather than the isolated test fixture's
    return get_index(Settings(_env_file=None), redis_client)


@then("the result is an AsyncSearchIndex bound to that client")
def check_index_binding(built_index, redis_client):
    assert isinstance(built_index, AsyncSearchIndex)
    assert built_index.client is redis_client


@then(parsers.parse('the index is named "{name}"'))
def check_index_name(built_index, redis_client, name):
    assert built_index.name == name
    asyncio.run(redis_client.aclose())  # never connected; close the lazy pool


# ---------------------------------------------------------------------------
# memory_schema.feature — ensure_index (live redis)
# ---------------------------------------------------------------------------
@given("a running Redis with no web_memory index")
def running_redis_no_index(redis_url, settings):
    async def _drop():
        client = aioredis.from_url(settings.redis_url)
        try:
            index = get_index(settings, client)
            if await index.exists():
                await index.delete(drop=True)
        finally:
            await client.aclose()

    asyncio.run(_drop())


@when("ensure_index is called twice in a row", target_fixture="ensure_result")
def ensure_twice(settings):
    async def _flow():
        client = aioredis.from_url(settings.redis_url)
        try:
            index = get_index(settings, client)
            first = await ensure_index(index)
            second = await ensure_index(index)
            exists = await index.exists()
            return {"first": first, "second": second, "exists": exists}
        finally:
            await client.aclose()

    return asyncio.run(_flow())


@then("the first call reports it created the index")
def first_created(ensure_result):
    assert ensure_result["first"] is True


@then("the second call reports no creation")
def second_noop(ensure_result):
    assert ensure_result["second"] is False


@then("the web_memory index exists afterwards")
def index_exists_after(ensure_result):
    assert ensure_result["exists"] is True


# ---------------------------------------------------------------------------
# memory_schema.feature — wipe_index (live redis)
# ---------------------------------------------------------------------------
@given(
    "a running Redis with the web_memory index and a stale doc: meta hash",
    target_fixture="wipe_setup",
)
def redis_with_stale_doc(redis_url, settings):
    # under the isolated meta prefix ("doc_test:") so both the write and the wipe stay off the
    # demo's "doc:*" namespace — never pollutes or purges real demo memory
    stale_key = f"{settings.memory_meta_prefix}:bddstalehash"

    async def _setup():
        client = aioredis.from_url(settings.redis_url)
        try:
            index = get_index(settings, client)
            await ensure_index(index)
            await client.hset(stale_key, mapping={"url": "https://redis.io/x", "fetched_at": "1"})
            return await client.exists(stale_key)
        finally:
            await client.aclose()

    assert asyncio.run(_setup()) == 1  # the stale meta hash is really present before the wipe
    return {"key": stale_key}


@when("wipe_index runs", target_fixture="wipe_result")
def run_wipe(settings, wipe_setup):
    async def _flow():
        client = aioredis.from_url(settings.redis_url)
        try:
            index = get_index(settings, client)
            await wipe_index(index, settings)
            after = await client.exists(wipe_setup["key"])
            exists = await index.exists()
            return {"after": after, "exists": exists}
        finally:
            await client.aclose()

    return asyncio.run(_flow())


@then("the stale doc: meta hash is gone")
def stale_gone(wipe_result):
    assert wipe_result["after"] == 0


@then("an empty web_memory index still exists")
def empty_index_exists(wipe_result):
    assert wipe_result["exists"] is True


# ---------------------------------------------------------------------------
# memory_schema.feature — assert_index_dims
# ---------------------------------------------------------------------------
@when(
    parsers.parse("assert_index_dims is called with an embedder dimension of {dim:d}"),
    target_fixture="dims_result",
)
def call_assert_dims(dim, settings):
    try:
        returned = assert_index_dims(dim, settings)
        return {"raised": False, "returned": returned, "message": None}
    except ValueError as exc:
        return {"raised": True, "returned": None, "message": str(exc)}


@then(parsers.parse("the dimension check {verdict}"))
def check_dims_verdict(dims_result, verdict):
    if verdict == "passes":
        assert dims_result["raised"] is False
        assert dims_result["returned"] is None
    else:
        assert dims_result["raised"] is True
        assert "wipe-memory" in dims_result["message"]


# ---------------------------------------------------------------------------
# memory_urls.feature — canonicalize + url_hash
# ---------------------------------------------------------------------------
@when(parsers.parse('the URL "{raw}" is canonicalised'), target_fixture="canonical_result")
def do_canonicalize(raw):
    return canonicalize(raw)


@then(parsers.parse('the canonical URL is "{canonical}"'))
def check_canonical(canonical_result, canonical):
    assert canonical_result == canonical


@when(
    parsers.parse('the identity hashes of "{first}" and "{second}" are computed'),
    target_fixture="hash_pair",
)
def do_hashes(first, second):
    return (url_hash(first), url_hash(second))


@then("the two hashes are equal")
def hashes_equal(hash_pair):
    assert hash_pair[0] == hash_pair[1]


@then("the hash is 16 lowercase hexadecimal characters")
def hash_shape(hash_pair):
    digest = hash_pair[0]
    assert len(digest) == 16
    assert all(ch in "0123456789abcdef" for ch in digest)


# ---------------------------------------------------------------------------
# memory_chunking.feature — chunk_markdown
# ---------------------------------------------------------------------------
@given("a long markdown document of many space-separated tokens", target_fixture="doc_text")
def long_document():
    return "token000 " + " ".join(f"token{i:03d}" for i in range(1, 900))


@given(parsers.parse('the markdown text "{text}"'), target_fixture="doc_text")
def literal_text(text):
    return text


@given(
    "a single paragraph that exceeds the 100-character floor but is shorter than one chunk",
    target_fixture="doc_text",
)
def short_whole_paragraph():
    return (
        "A single meaningful paragraph about Redis vector search internals, kept whole "
        "because it exceeds the hundred character floor."
    )


@given("a very large markdown document", target_fixture="doc_text")
def huge_document():
    return "\n\n".join("Section content " * 40 for _ in range(200))


@when("it is chunked with default settings", target_fixture="chunks")
def chunk_the_document(doc_text, settings):
    return chunk_markdown(doc_text, settings)


@then("every chunk is within the configured chunk size")
def within_size(chunks, settings):
    assert chunks
    assert all(len(c) <= settings.chunk_size_chars for c in chunks)


@then("there are at least two chunks")
def at_least_two(chunks):
    assert len(chunks) >= 2


@then("the tail of the first chunk reappears at the head of the second")
def overlap_present(chunks):
    assert chunks[0][-60:] in chunks[1]


@then("no chunks are returned")
def no_chunks(chunks):
    assert chunks == []


@then("exactly one chunk is returned equal to the input paragraph")
def one_chunk_equal(chunks, doc_text):
    assert chunks == [doc_text]


@then("no more than the configured maximum number of chunks is returned")
def capped_chunks(chunks, settings):
    assert 0 < len(chunks) <= settings.max_chunks_per_page
