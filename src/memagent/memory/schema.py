"""The web_memory vector index schema — defined once, loaded by every later milestone.

Redis COSINE returns *distance*; the similarity conversion (1 - distance) is an M2
concern and lives in memory/store.py only. The metric is fixed here as cosine so
that conversion will hold exactly (OpenAI embeddings are L2-normalized).

Key layout written by the store (M2): {chunk_prefix}:{url_hash}:{i} for chunks,
{chunk_prefix}:{url_hash}:summary for the per-page summary doc (indexed — participates
in KNN routing), plus the NON-indexed meta hash {meta_prefix}:{url_hash}. Only the
chunk prefix is scanned by the index. Both prefixes come from Settings (default "chunk"
/ "doc") so a test/eval can carve out a disjoint namespace on the same Redis.

prefix trap: redisvl builds the Redis PREFIX as prefix + key_separator, so
prefix="chunk" + key_separator=":" -> PREFIX "chunk:". Setting prefix="chunk:"
would yield keys "chunk::<id>".
"""

from redisvl.index import AsyncSearchIndex
from redisvl.schema import IndexSchema

from memagent.config import Settings


def build_schema(settings: Settings) -> IndexSchema:
    return IndexSchema.from_dict(
        {
            "index": {
                "name": settings.memory_index_name,  # "web_memory"
                # + key_separator ":" -> Redis PREFIX "<prefix>:" (default "chunk:")
                "prefix": settings.memory_chunk_prefix,
                "key_separator": ":",
                "storage_type": "hash",
            },
            "fields": [
                {"name": "chunk_text", "type": "text"},  # sanitized markdown
                {"name": "url", "type": "tag"},  # canonical URL
                {"name": "url_hash", "type": "tag"},  # sha256(canonical)[:16]
                {"name": "title", "type": "text"},
                {"name": "doc_type", "type": "tag"},  # "chunk" | "summary"
                {"name": "source_query", "type": "text"},
                {"name": "chunk_index", "type": "numeric"},
                {"name": "fetched_at", "type": "numeric", "attrs": {"sortable": True}},
                {"name": "sanitizer_flags", "type": "tag", "attrs": {"separator": ","}},
                {"name": "content_sha256", "type": "text"},
                {
                    "name": "embedding",
                    "type": "vector",
                    "attrs": {
                        "algorithm": "flat",
                        "dims": settings.embedding_dim,  # 1536
                        "distance_metric": "cosine",
                        "datatype": "float32",
                    },
                },
            ],
        }
    )


def get_index(settings: Settings, client) -> AsyncSearchIndex:
    return AsyncSearchIndex(build_schema(settings), redis_client=client)


async def ensure_index(index: AsyncSearchIndex) -> bool:
    """Create the index if missing; never drop data. Returns True if it created it."""
    if await index.exists():
        return False
    await index.create(overwrite=False)
    return True


async def wipe_index(index: AsyncSearchIndex, settings: Settings) -> None:
    """Drop the index AND its keys, then recreate empty (wipe-memory / dims-change recovery).

    Also deletes the NON-indexed {meta_prefix}:{url_hash} meta hashes: they carry the freshness
    bookkeeping (fetched_at) and the upsert generation count (num_chunks). Leaving them
    behind would make M3's freshness gate skip re-ingesting any URL seen < 24h before
    the wipe — memory would silently stay empty for those URLs (found live, 2026-07-05).

    ``settings`` is REQUIRED (not defaulted) so the meta-prefix scan always matches the same
    namespace as the index being dropped: a caller operating on an isolated test namespace can
    never accidentally purge the demo's "doc:*" keys via a stale default.
    """
    await index.create(overwrite=True, drop=True)
    client = index.client
    if client is None:
        return
    match = f"{settings.memory_meta_prefix}:*"
    stale = [key async for key in client.scan_iter(match=match, count=500)]
    if stale:
        await client.delete(*stale)


def assert_index_dims(embedder_dim: int, settings: Settings) -> None:
    if embedder_dim != settings.embedding_dim:
        raise ValueError(
            f"Embedder produces {embedder_dim}-dim vectors but the index is built for "
            f"{settings.embedding_dim} dims. Change EMBEDDING_MODEL/EMBEDDING_DIM together and "
            f"run `memagent wipe-memory` to rebuild the index."
        )
