"""Typer CLI — the four-subcommand user surface (all real as of M4).

stdout carries ONLY banners, answers, and sources (pipe-clean, FR-M4-21); operational
structlog lines go to stderr with turn_id bound. The miss banner below is THE canonical
string — ask and chat share the same constant, byte-identical.
"""

import asyncio
import contextlib
import json
import sys
import threading
from pathlib import Path

import typer
from redisvl.exceptions import RedisSearchError
from rich.console import Console

from memagent.analytics.report import aggregate, render_report
from memagent.config import Settings
from memagent.memory.schema import get_index, wipe_index
from memagent.memory.store import make_redis_client
from memagent.routers import route_after_memory
from memagent.utils.errors import REDIS_DOWN_ERRORS, redis_down_in_chain

app = typer.Typer(add_completion=False, help="Memory-first web agent")

# Canonical banners (arrows included) — reused verbatim by ask AND chat.
MISS_BANNER = "[MEMORY MISS → searching the web]"
BLOCKED_BANNER = "[BLOCKED by input guard]"
MEMORY_OFFLINE_BANNER = "[MEMORY OFFLINE → searching the web (not cached)]"

# The live spinner + colored step labels go to STDERR so stdout stays pipe-clean
# (FR-M4-21) and piped output is byte-identical; animation runs only on a real TTY.
# Banners/answers/sources go to stdout via _emit — styled on a terminal, plain
# (identical to typer.echo) when captured or piped. Colour is gated on the stream's
# own isatty() (NOT rich's is_terminal, which honours FORCE_COLOR) so the pipe-clean
# contract holds even when FORCE_COLOR is set in the environment.
_out = Console()
_err = Console(stderr=True)


def _emit(text: str, color: str | None = None, *, markdown: bool = False) -> None:
    """Print to stdout: styled/rendered on a real TTY, byte-identical plain text otherwise.

    The non-TTY path is checked FIRST so piped/redirected/captured output is always the
    exact plain text (pipe-clean contract, FR-M4-21) regardless of color/markdown.
    """
    if not sys.stdout.isatty():
        typer.echo(text)
    elif markdown:
        from rich.markdown import Markdown

        _out.print(Markdown(text))
    elif color:
        _out.print(text, style=color, markup=False, highlight=False, soft_wrap=True)
    else:
        typer.echo(text)


def status_label(node: str, update: dict, merged: dict) -> tuple[str, str] | None:
    """Map a just-finished node + the decision it took to a friendly (label, colour)
    for the live spinner, or None when there is nothing to narrate.

    Pure and side-effect-free (``_advance_status`` renders it). ``astream`` fires only
    AFTER a node completes, so each label names the work now in flight and folds in the
    decision that node just made — the friendly "which step / what did it decide" the
    user asked for, in one line. The locked step names ("Found in memory (sim …)",
    "searching the web", "Reading N pages") stay verbatim inside the friendly text so the
    spinner reads the same as the banner that follows.
    """
    if node in {"guard_input", "embed_query"}:
        if update.get("route") == "blocked":
            return "🛑 Blocked by the input guard", "red"
        return "🧠 Checking memory", "cyan"
    if node == "memory_search":
        if update.get("degradation") == "redis_down":
            return "📴 Memory offline — searching the web", "yellow"
        if route_after_memory(merged) == "answer_from_memory":
            sim = update.get("top_similarity") or 0.0
            return f"✅ Found in memory (sim {sim:.2f}) — writing your answer", "green"
        return "🌐 Not in memory — searching the web", "yellow"
    if node == "web_search":
        n = len(merged.get("search_results") or [])
        return f"📄 Reading {n} page{'' if n == 1 else 's'}", "cyan"
    if node in {"fetch_pages", "ingest_content"}:
        return "✍️ Writing your answer", "cyan"
    return None  # answer_from_* / log_turn: the spinner is about to stop, nothing to say


def _advance_status(status, node: str, update: dict, merged: dict) -> None:
    """Render the friendly label for the step now in flight onto the live spinner.

    A no-op when there is no spinner (piped/captured run) or nothing to narrate.
    """
    res = status_label(node, update, merged)
    if status is not None and res is not None:
        label, color = res
        status.update(f"[{color}]{label}…[/]")


def chat_help_text() -> str:
    """The greeting + command list + stop hint shown in the chat REPL (rich markup).

    Returned as ONE string so the welcome panel (at start) and the `/help` command render
    byte-identically. It names every command and BOTH ways to stop — `exit`/`quit`/Ctrl-D
    to leave, Ctrl-C to cancel an in-flight answer — so the user is never stuck wondering
    how to get out or what else they can do.
    """
    return (
        "[dim]Hi! Ask me anything — I check what I already know first,\n"
        "then search the web when it's something new.[/]\n\n"
        "[bold]Commands[/]\n"
        "  [bold cyan]/help[/]    show this message again\n"
        "  [bold cyan]/clear[/]   clear the screen & forget this chat\n"
        "  [bold cyan]exit[/]     leave  ·  also: [bold cyan]quit[/], or [bold cyan]Ctrl-D[/]\n\n"
        "[dim]While I'm answering, press [/][bold cyan]Ctrl-C[/][dim] to stop and ask again.[/]"
    )


async def _stream_turn(agent, state: dict) -> tuple[dict, dict | None, bool]:
    """Drive one graph turn under a live stderr spinner (TTY only).

    Returns (merged_final_state, memory_search_update|None, guard_blocked). The
    memory-search update and block flag let the caller pick the banner from the same
    signals the router uses, independent of the reconstructed route.
    """
    merged = dict(state)
    mem_update: dict | None = None
    blocked = False
    spinner = (
        _err.status("[cyan]🧠 Checking memory…[/]", spinner="dots")
        if sys.stderr.isatty()
        else contextlib.nullcontext()
    )
    with spinner as status:
        async for chunk in agent.graph.astream(state, stream_mode="updates"):
            for node, update in chunk.items():
                update = update or {}
                merged.update(update)
                _advance_status(status, node, update, merged)
                if node == "memory_search":
                    mem_update = update
                if node == "guard_input" and update.get("route") == "blocked":
                    blocked = True
    return merged, mem_update, blocked


def _hit_banner(sim: float) -> str:
    return f"[MEMORY HIT sim={sim:.2f}]"


def _print_sources(sources: list[dict]) -> None:
    if sources:
        typer.echo("")
        for src in sources:
            _emit(f"({src['origin']}) {src['title']} <{src['url']}>", "cyan")


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
    except REDIS_DOWN_ERRORS as exc:
        settings = Settings()
        typer.echo(
            f"error: cannot reach Redis at {settings.redis_url} - is it running? "
            f"(make redis-up) [{exc.__class__.__name__}]",
            err=True,
        )
        raise typer.Exit(code=1) from exc


async def _wipe() -> None:
    settings = Settings()
    client = make_redis_client(settings)
    try:
        index = get_index(settings, client)
        await wipe_index(index)
        typer.echo(f"Wiped and recreated index '{settings.memory_index_name}'.")
    finally:
        await client.aclose()


@app.command()
def ask(query: str) -> None:
    """Answer a single question: Redis memory first, web search + fetch fallback on a miss."""
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
    except REDIS_DOWN_ERRORS as exc:
        _exit_redis_down(settings, exc)
    except RedisSearchError as exc:
        if not redis_down_in_chain(exc):
            raise
        _exit_redis_down(settings, exc)
    # Top-down, first match wins. `failed` is checked BEFORE `redis_down` so a lingering
    # degradation label never suppresses the failed exit-1 contract (FR-M5-27).
    if sys.stdout.isatty():
        typer.echo("")  # a blank line between the spinner region and the result
    if result.route == "blocked":
        _emit(BLOCKED_BANNER, "bold red")
        _emit(result.answer or "", markdown=True)
        return  # no sources, exit 0 — the guard worked as designed (not a failure)
    if result.route == "failed":
        _emit(result.answer or "", "bold red")  # clean error, no banner
        raise typer.Exit(code=1)
    if result.route == "memory_hit":
        _emit(_hit_banner(result.similarity), "bold green")
    elif result.degradation == "redis_down":
        _emit(MEMORY_OFFLINE_BANNER, "bold yellow")
    else:
        _emit(MISS_BANNER, "bold yellow")
    _emit(result.answer or "", markdown=True)
    _print_sources(result.sources)


async def _ask(query: str, settings: Settings):
    import structlog

    from memagent.app import Agent, TurnResult, configure_logging, new_turn_state

    configure_logging(settings)
    agent = Agent()
    await agent.ensure_ready()
    state = new_turn_state(settings, agent.session_id, query)
    structlog.contextvars.bind_contextvars(turn_id=state["turn_id"])
    try:
        merged, _mem, _blocked = await _stream_turn(agent, state)
    finally:
        structlog.contextvars.clear_contextvars()
    return TurnResult(
        route=merged.get("route", "failed"),
        answer=merged.get("answer"),
        sources=merged.get("sources", []),
        similarity=merged.get("top_similarity"),
        degradation=merged.get("degradation"),
    )


@app.command()
def chat() -> None:
    """Interactive REPL: live status, hit/miss banners, /help, /clear and exit commands.

    History is capped at 6 turns; Ctrl-C stops the current answer.
    """
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
    except KeyboardInterrupt:  # a race-timed Ctrl-C during teardown never shows a traceback
        if sys.stderr.isatty():
            _err.print("")
        raise typer.Exit(code=130) from None
    except REDIS_DOWN_ERRORS as exc:
        _exit_redis_down(settings, exc)
    except RedisSearchError as exc:
        if not redis_down_in_chain(exc):
            raise
        _exit_redis_down(settings, exc)


async def _chat(settings: Settings) -> None:
    import structlog

    from memagent.app import Agent, configure_logging, new_turn_state
    from memagent.nodes.answer import FAILURE_APOLOGY

    configure_logging(settings)
    agent = Agent()
    await agent.ensure_ready()  # REPL drives the graph directly, so provision the index here
    history: list[dict] = []
    tty = sys.stdout.isatty()
    err_tty = sys.stderr.isatty()

    def show_help() -> None:
        """Render the welcome/help panel to stderr (TTY only) — never touches stdout."""
        if not err_tty:
            return
        from rich import box
        from rich.panel import Panel
        from rich.text import Text

        _err.print(
            Panel(
                Text.from_markup(chat_help_text()),
                box=box.ROUNDED,
                border_style="cyan",
                title="memagent 🧠 · memory-first chat",
                title_align="left",
                padding=(1, 2),
            )
        )

    async def read_line() -> str:
        """Read one input line on a DAEMON thread, awaitably.

        A real Ctrl-C under asyncio's Runner cancels the awaiting task (raising
        CancelledError here), NOT the blocking read in the worker thread. Using a daemon
        reader means that abandoned read can never hang process exit — so leaving the chat
        stays instant even if the interpreter tears down while a read is still parked.
        """
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()

        def reader() -> None:
            try:
                text = input("")
            except Exception as exc:  # noqa: BLE001 — forward EOF/etc. to the awaiter
                loop.call_soon_threadsafe(fut.set_exception, exc)
            else:
                loop.call_soon_threadsafe(fut.set_result, text)

        threading.Thread(target=reader, daemon=True).start()
        return await fut

    def stop_current_task() -> None:
        """Balance the Runner's task.cancel() from a Ctrl-C so the loop can keep going."""
        task = asyncio.current_task()
        if task is not None:
            task.uncancel()

    show_help()
    while True:
        # The prompt is written to STDERR (never input()'s arg, which would leak it to
        # stdout) so a piped `chat` stays byte-identical; a blank line separates turns.
        if err_tty:
            _err.print("\n[bold cyan]you> [/]", end="")
        try:
            query = (await read_line()).strip()
        except EOFError:  # Ctrl-D — leave cleanly, no stdout write
            if err_tty:
                _err.print("[dim]👋 bye[/]")
            return
        except (KeyboardInterrupt, asyncio.CancelledError):  # Ctrl-C at the idle prompt: leave
            stop_current_task()
            if err_tty:
                _err.print("[dim]👋 bye[/]")
            return
        if not query:
            continue
        low = query.lower()
        if low in {"exit", "quit"}:
            if err_tty:
                _err.print("[dim]👋 bye[/]")
            return
        if low in {"/help", "help", "?"}:  # whole-input match: "help me with X" is a question
            show_help()
            continue
        if low == "/clear":
            history[:] = []  # forget this chat's context; long-term Redis memory is untouched
            if err_tty:
                _err.clear()
                _err.print(
                    "[dim]🧹 Cleared this chat — long-term memory is kept. /help for commands.[/]"
                )
            continue
        if low.startswith("/"):
            if err_tty:
                _err.print(f"[dim]Unknown command '{query}' — type /help to see what I can do.[/]")
            continue
        state = new_turn_state(settings, agent.session_id, query, history)
        # The REPL bypasses Agent.answer(), so it binds its own turn_id (FR-M4-21).
        structlog.contextvars.bind_contextvars(turn_id=state["turn_id"])
        try:
            merged, mem_update, blocked = await _stream_turn(agent, state)
        except (KeyboardInterrupt, asyncio.CancelledError):
            # Ctrl-C mid-answer cancels ONLY this turn (a real SIGINT arrives as
            # CancelledError under asyncio.Runner); the turn is discarded, nothing stored.
            stop_current_task()
            if err_tty:
                _err.print("[dim]⏹ Stopped — ask me something else.[/]")
            continue
        finally:
            structlog.contextvars.clear_contextvars()
        # The spinner is stopped now, so these stdout lines never interleave with it.
        answer = merged.get("answer")
        failed = answer is not None and answer == FAILURE_APOLOGY
        if tty:
            typer.echo("")  # breathing room between the input line and the result
        if blocked:
            _emit(BLOCKED_BANNER, "bold red")  # keep the L1-blocked payload out of history
            if answer:
                _emit(answer, markdown=True)
        elif failed:
            # The turn failed (e.g. the model was busy/rate-limited). Show ONE clean error,
            # never a misleading HIT banner followed by an apology.
            _emit(answer, "bold red")
        else:
            if mem_update is not None:
                if mem_update.get("degradation") == "redis_down":
                    _emit(MEMORY_OFFLINE_BANNER, "bold yellow")  # Redis down mid-turn → web-only
                # Defer to the router (single hit/miss owner) so the banner tracks it.
                elif route_after_memory(merged) == "answer_from_memory":
                    _emit(_hit_banner(mem_update.get("top_similarity")), "bold green")
                else:
                    _emit(MISS_BANNER, "bold yellow")
            if answer:
                _emit(answer, markdown=True)
                _print_sources(merged.get("sources", []))
        # A blocked or failed turn is not a real exchange — never replay its canned text as
        # trusted user/assistant context on later turns.
        if answer and not blocked and not failed:
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
