"""Typer CLI — the four-subcommand user surface (all real as of M4).

stdout carries ONLY banners, answers, and sources (pipe-clean, FR-M4-21); operational
structlog lines go to stderr with turn_id bound. The miss banner below is THE canonical
string — ask and chat share the same constant, byte-identical.
"""

import asyncio
import json
from pathlib import Path

import redis.asyncio as aioredis
import typer
from redis import exceptions as redis_exceptions
from redisvl.exceptions import RedisSearchError
from rich.console import Console

from memagent.analytics.report import aggregate, render_report
from memagent.config import Settings
from memagent.memory.schema import get_index, wipe_index

app = typer.Typer(add_completion=False, help="Memory-first web agent")

# redis-py's ConnectionError/TimeoutError do NOT subclass the builtins.
_REDIS_DOWN = (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError, OSError)

# The ONE canonical miss banner (arrow included) — reused verbatim by ask AND chat.
MISS_BANNER = "[MEMORY MISS → searching the web]"
ANSWER_NODES = {"answer_from_memory", "answer_from_web", "answer_failure"}


def _hit_banner(sim: float) -> str:
    return f"[MEMORY HIT sim={sim:.2f}]"


def _print_sources(sources: list[dict]) -> None:
    if sources:
        typer.echo("")
        for src in sources:
            typer.echo(f"({src['origin']}) {src['title']} <{src['url']}>")


def _redis_down_in_chain(exc: BaseException) -> bool:
    """redisvl wraps connection failures in RedisSearchError — walk the cause chain.

    Found in the M3 manual test: `ask` with Redis down surfaced a RedisSearchError
    traceback wall instead of the readable one-line error the CLI promises.
    """
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, _REDIS_DOWN):
            return True
        cause = cause.__cause__
    return False


def _exit_redis_down(settings: Settings, exc: BaseException) -> None:
    typer.echo(
        f"error: cannot reach Redis at {settings.redis_url} - is it running? "
        f"(make redis-up) [{exc.__class__.__name__}]",
        err=True,
    )
    raise typer.Exit(code=1) from exc


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
        result = asyncio.run(_ask(query, settings))
    except _REDIS_DOWN as exc:
        _exit_redis_down(settings, exc)
    except RedisSearchError as exc:
        if not _redis_down_in_chain(exc):
            raise
        _exit_redis_down(settings, exc)
    if result.route == "memory_hit":
        typer.echo(_hit_banner(result.similarity))
    else:
        typer.echo(MISS_BANNER)
    typer.echo(result.answer or "")
    _print_sources(result.sources)


async def _ask(query: str, settings: Settings):
    from memagent.app import Agent, configure_logging

    configure_logging(settings)
    return await Agent().answer(query)


@app.command()
def chat() -> None:
    """Interactive REPL: streaming turns with hit/miss banners, history capped at 6."""
    settings = Settings()
    if not settings.openai_api_key:
        typer.echo(
            "error: OPENAI_API_KEY is not set - add it to .env "
            "(a GitHub Models PAT works for free development; see README).",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        asyncio.run(_chat(settings))
    except _REDIS_DOWN as exc:
        _exit_redis_down(settings, exc)
    except RedisSearchError as exc:
        if not _redis_down_in_chain(exc):
            raise
        _exit_redis_down(settings, exc)


async def _chat(settings: Settings) -> None:
    import structlog

    from memagent.app import Agent, configure_logging, new_turn_state

    configure_logging(settings)
    agent = Agent()
    history: list[dict] = []
    typer.echo("memagent chat — type a question; exit/quit or Ctrl-D to leave.")
    while True:
        try:
            query = (await asyncio.to_thread(input, "you> ")).strip()
        except EOFError:
            typer.echo("")
            return
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            return
        state = new_turn_state(settings, agent.session_id, query, history)
        # The REPL bypasses Agent.answer(), so it binds its own turn_id (FR-M4-21).
        structlog.contextvars.bind_contextvars(turn_id=state["turn_id"])
        answer = None
        try:
            async for chunk in agent.graph.astream(state, stream_mode="updates"):
                for node, update in chunk.items():
                    update = update or {}
                    if node == "guard_input" and update.get("route") == "blocked":
                        # dormant until M5 activates guard_input (Ruling F)
                        if update.get("answer"):
                            answer = update["answer"]
                            typer.echo(answer)
                    if node == "memory_search":
                        sim = update.get("top_similarity")
                        if sim is not None and sim >= state["threshold"]:
                            typer.echo(_hit_banner(sim))
                        else:
                            typer.echo(MISS_BANNER)
                    if node in ANSWER_NODES and update.get("answer"):
                        answer = update["answer"]
                        typer.echo(answer)  # on screen BEFORE log_turn/classify runs
                        _print_sources(update.get("sources", []))
        finally:
            structlog.contextvars.clear_contextvars()
        if answer:
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": answer})
            history[:] = history[-settings.history_max_turns * 2 :]


@app.command()
def analytics(
    json_output: bool = typer.Option(False, "--json", help="Print aggregates as JSON to stdout."),
) -> None:
    """Analytics report over logs/turns.jsonl (hit-rate, topics, question types)."""
    # Pure file read: needs neither OPENAI_API_KEY nor Redis.
    settings = Settings()
    path = Path(settings.turn_log_path)
    records: list[dict] = []
    if not path.exists():
        # Guidance goes to stderr so `--json` stdout stays machine-parseable.
        typer.echo(
            "no turns logged yet — run `memagent ask` or `memagent chat` first "
            "(see logs/turns.sample.jsonl for the record format).",
            err=True,
        )
        if not json_output:
            raise typer.Exit(code=0)
    else:
        corrupt = 0
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    corrupt += 1  # a crash mid-write must not take the report down
        if corrupt:
            typer.echo(f"warning: skipped {corrupt} corrupt line(s) in {path}", err=True)
    agg = aggregate(records)
    if json_output:
        typer.echo(json.dumps(agg))
        return
    render_report(agg, Console())
