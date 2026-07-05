"""Seed the memory with one document so a memory hit is demoable (FR-M2-23).

Usage:
    uv run python scripts/seed_memory.py --url https://redis.io/docs/vectors --file docs/seed.md
    uv run python scripts/seed_memory.py --url https://example.com --text "..." --title "Example"
"""

import argparse
import asyncio
from pathlib import Path

import redis.asyncio as aioredis

from memagent.config import Settings
from memagent.llm.clients import OpenAIEmbedder
from memagent.memory.chunking import chunk_markdown
from memagent.memory.store import RedisMemoryStore
from memagent.memory.urls import canonicalize
from memagent.state import Chunk, FetchedDoc


async def seed(url: str, text: str, title: str) -> int:
    settings = Settings()
    canonical = canonicalize(url)
    texts = chunk_markdown(text, settings)
    if not texts:
        raise SystemExit("error: the document produced zero chunks (>=100 chars each needed)")
    chunks = [
        Chunk(chunk_id=f"{i}", text=t, url=canonical, title=title, chunk_index=i)
        for i, t in enumerate(texts)
    ]
    embedder = OpenAIEmbedder(settings)
    vectors = await embedder.embed(texts)  # no summary -> vectors align 1:1 (research D6)
    page = FetchedDoc(url=canonical, title=title, markdown=text, summary=None, ok=True)
    client = aioredis.from_url(settings.redis_url)
    try:
        store = RedisMemoryStore(settings, client)
        stored = await store.store(page, chunks, vectors, source_query="seed", flags=[])
    finally:
        await client.aclose()
    return len(stored)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="source URL stored as metadata")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="markdown/text file to seed")
    group.add_argument("--text", help="inline text to seed")
    parser.add_argument("--title", default=None, help="document title (default: derived)")
    args = parser.parse_args()

    text = args.file.read_text(encoding="utf-8") if args.file else args.text
    title = args.title
    if title is None:
        first = text.strip().splitlines()[0] if text.strip() else args.url
        title = first.lstrip("# ").strip() or args.url

    n = asyncio.run(seed(args.url, text, title))
    print(f"Seeded {n} chunk(s) for {canonicalize(args.url)} (title: {title!r})")


if __name__ == "__main__":
    main()
