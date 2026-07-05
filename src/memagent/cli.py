"""Typer CLI — the four-subcommand user surface.

M1: wipe-memory is fully functional; ask/chat/analytics are stubs replaced in
M2/M4 (replacing a stub must not change its call sites).
"""

import asyncio

import redis.asyncio as aioredis
import typer
from redis import exceptions as redis_exceptions

from memagent.config import Settings
from memagent.memory.schema import get_index, wipe_index

app = typer.Typer(add_completion=False, help="Memory-first web agent")

# redis-py's ConnectionError/TimeoutError do NOT subclass the builtins.
_REDIS_DOWN = (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError, OSError)


@app.command("wipe-memory")
def wipe_memory() -> None:
    """Drop and recreate the Redis vector index (also the dims-change recovery path)."""
    try:
        asyncio.run(_wipe())
    except _REDIS_DOWN as exc:
        settings = Settings()
        typer.echo(
            f"error: cannot reach Redis at {settings.redis_url} - is it running? "
            f"(make redis-up) [{exc.__class__.__name__}]",
            err=True,
        )
        raise typer.Exit(code=1) from exc


async def _wipe() -> None:
    settings = Settings()
    client = aioredis.from_url(settings.redis_url)
    try:
        index = get_index(settings, client)
        await wipe_index(index)
        typer.echo(f"Wiped and recreated index '{settings.memory_index_name}'.")
    finally:
        await client.aclose()


@app.command()
def ask(query: str) -> None:
    """Answer a single question: memory first, web fallback (web path lands in M3)."""
    settings = Settings()
    if not settings.openai_api_key:
        typer.echo(
            "error: OPENAI_API_KEY is not set - add it to .env "
            "(a GitHub Models PAT works for free development; see README).",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        result = asyncio.run(_ask(query))
    except _REDIS_DOWN as exc:
        typer.echo(
            f"error: cannot reach Redis at {settings.redis_url} - is it running? "
            f"(make redis-up) [{exc.__class__.__name__}]",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    if result.route == "memory_hit":
        typer.echo(f"[MEMORY HIT sim={result.similarity:.2f}]")
    else:
        # Bare [MEMORY MISS] is temporary - M3 upgrades this banner to
        # "[MEMORY MISS -> searching the web]" and prints web sources.
        typer.echo("[MEMORY MISS]")
    typer.echo(result.answer or "")
    if result.route == "memory_hit" and result.sources:
        typer.echo("")
        for src in result.sources:
            typer.echo(f"({src['origin']}) {src['title']} <{src['url']}>")


async def _ask(query: str):
    from memagent.app import Agent

    return await Agent().answer(query)


@app.command()
def chat() -> None:
    """Interactive REPL (wired in M4)."""
    typer.echo("[stub] chat REPL is wired in M4.")


@app.command()
def analytics() -> None:
    """Analytics report over logs/turns.jsonl (wired in M4)."""
    typer.echo("[stub] analytics report is wired in M4.")
