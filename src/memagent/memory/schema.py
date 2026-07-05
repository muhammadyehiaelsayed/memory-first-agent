"""The web_memory vector index schema — defined once, loaded by every later milestone.

Redis COSINE returns *distance*; the similarity conversion (1 - distance) is an M2
concern and lives in memory/store.py only. The metric is fixed here as cosine so
that conversion will hold exactly (OpenAI embeddings are L2-normalized).

Key layout written by the store (M2): chunk:{url_hash}:{i} for chunks,
chunk:{url_hash}:summary for the per-page summary doc (indexed — participates in
KNN routing), plus the NON-indexed meta hash doc:{url_hash}. Only the chunk:
prefix is scanned by the index.

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
                "prefix": "chunk",  # + key_separator ":" -> Redis PREFIX "chunk:"
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


async def wipe_index(index: AsyncSearchIndex) -> None:
    """Drop the index AND its keys, then recreate empty (wipe-memory / dims-change recovery)."""
    await index.create(overwrite=True, drop=True)


def assert_index_dims(embedder_dim: int, settings: Settings) -> None:
    if embedder_dim != settings.embedding_dim:
        raise ValueError(
            f"Embedder produces {embedder_dim}-dim vectors but the index is built for "
            f"{settings.embedding_dim} dims. Change EMBEDDING_MODEL/EMBEDDING_DIM together and "
            f"run `memagent wipe-memory` to rebuild the index."
        )
