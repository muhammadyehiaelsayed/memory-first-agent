"""Typer CLI — the four-subcommand user surface.

M1: wipe-memory is fully functional; ask/chat/analytics are stubs replaced in
M2/M4 (replacing a stub must not change its call sites).
"""

import asyncio

import redis.asyncio as aioredis
import typer

from memagent.config import Settings
from memagent.memory.schema import get_index, wipe_index

app = typer.Typer(add_completion=False, help="Memory-first web agent")


@app.command("wipe-memory")
def wipe_memory() -> None:
    """Drop and recreate the Redis vector index (also the dims-change recovery path)."""
    try:
        asyncio.run(_wipe())
    except (ConnectionError, OSError) as exc:
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
    """Answer a single question (wired in M2)."""
    typer.echo(f"[stub] ask received: {query!r} - answering is wired in M2.")


@app.command()
def chat() -> None:
    """Interactive REPL (wired in M4)."""
    typer.echo("[stub] chat REPL is wired in M4.")


@app.command()
def analytics() -> None:
    """Analytics report over logs/turns.jsonl (wired in M4)."""
    typer.echo("[stub] analytics report is wired in M4.")
