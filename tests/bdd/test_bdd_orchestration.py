"""Executable binding for the orchestration batch feature files.

Binds three features that make the memory-first pipeline hang together:
- features/routers.feature      — the five pure sync routers (state -> next-node key)
- features/graph.feature        — build_graph, inspected via its compiled mermaid diagram
- features/app.feature          — configure_logging / configure_tracing / new_turn_state /
                                  build_resources / Agent.__init__ (all keyless) and
                                  Agent.answer (live).

Keyless techniques:
- The routers are pure functions of a plain dict: they are called directly, no I/O.
- build_graph compiles from resources holding None clients (compilation touches no client),
  so its structure is observable without any live backend (mirrors scripts/render_graph.py).
- configure_logging is asserted by inspecting the resulting structlog config (its logger
  factory targets stderr, not stdout, so operational logs never pollute the piped answer).
- configure_tracing is driven against an injected env dict (its test seam), so the real
  os.environ is never mutated and no LangSmith upload can start from the keyless suite.
- build_resources runs with OPENAI/TAVILY keys faked by the conftest `settings` fixture; the
  OpenAI/httpx/redis clients construct without any network round-trip.
- Agent.answer runs the REAL graph over REAL Redis (redis is up; skip-not-fail if it is not)
  with FakeLLM/FakeEmbedder, and respx intercepts the Tavily + page HTTP so the miss path is
  exercised end to end without a network or a key. Steps are sync; coroutines run via
  asyncio.run(...) (one turn == one loop, so the redis client is never reused across loops).
"""

import asyncio
import os
import pathlib
import sys

import httpx
import structlog
from pytest_bdd import given, parsers, scenarios, then, when

import redis.asyncio as aioredis

from memagent.app import (
    Agent,
    build_resources,
    configure_logging,
    configure_tracing,
    new_turn_state,
)
from memagent.config import Settings
from memagent.graph import build_graph
from memagent.memory.schema import get_index, wipe_index
from memagent.memory.store import RedisMemoryStore, make_redis_client
from memagent.resources import AgentResources
from memagent.routers import (
    route_after_embed,
    route_after_fetch,
    route_after_guard,
    route_after_memory,
    route_after_search,
)
from memagent.web.fetch import HttpxPageFetcher
from memagent.web.search import FallbackProvider

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # repo root on path
from tests.conftest import build_test_resources, probe_redis_or_skip  # noqa: E402

scenarios("features/routers.feature")
scenarios("features/graph.feature")
scenarios("features/app.feature")

QUESTION = "How does Redis vector search work?"
URL = "https://example.test/redis-vector-search"
# A full HTML doc whose body repeats the question 40x so the stored chunk embeds ~1.0 to it.
PAGE_HTML = "<html><body><article><p>" + (QUESTION + " ") * 40 + "</p></article></body></html>"


def _keyless_resources() -> AgentResources:
    """Resources with None clients — enough to compile the graph, touches no backend."""
    return AgentResources(
        settings=Settings(_env_file=None),
        memory=None,
        embedder=None,
        chat_llm=None,
        analytics_llm=None,
        searcher=None,
        fetcher=None,
        turn_logger=None,
    )


# =========================================================================== #
# routers.feature — the five pure routers                                     #
# =========================================================================== #
@given(parsers.parse('a guard verdict of "{verdict}"'), target_fixture="router_state")
def _guard_state(verdict):
    return {"guard_verdict": verdict}


@given("a state carrying a 1536-float query vector", target_fixture="router_state")
def _embed_state():
    return {"query_vector": [0.1] * 1536}


@given(
    parsers.parse("a top similarity of {sim:g} and a threshold of {thr:g}"),
    target_fixture="router_state",
)
def _memory_state(sim, thr):
    return {"top_similarity": sim, "threshold": thr}


@given("search results containing at least one entry", target_fixture="router_state")
def _search_state():
    return {"search_results": [{"url": "https://a.test/1"}]}


@given("fetched documents containing at least one page", target_fixture="router_state")
def _fetch_state():
    return {"fetched_docs": [{"url": "https://a.test/1"}]}


@when("the post-guard router decides where to go", target_fixture="decision")
def _decide_guard(router_state):
    return route_after_guard(router_state)


@when("the post-embed router decides where to go", target_fixture="decision")
def _decide_embed(router_state):
    return route_after_embed(router_state)


@when("the post-memory router decides where to go", target_fixture="decision")
def _decide_memory(router_state):
    return route_after_memory(router_state)


@when("the post-search router decides where to go", target_fixture="decision")
def _decide_search(router_state):
    return route_after_search(router_state)


@when("the post-fetch router decides where to go", target_fixture="decision")
def _decide_fetch(router_state):
    return route_after_fetch(router_state)


@then(parsers.parse('it routes to "{target}"'))
def _routes_to(decision, target):
    assert decision == target, f"expected {target!r}, got {decision!r}"


@then(parsers.parse('a guard verdict of "{verdict}" routes to "{target}"'))
def _guard_alt(verdict, target):
    assert route_after_guard({"guard_verdict": verdict}) == target


@then('a state whose query vector is None routes to "answer_failure"')
def _embed_none():
    assert route_after_embed({"query_vector": None}) == "answer_failure"


@then('a state with no query vector at all routes to "answer_failure"')
def _embed_absent():
    assert route_after_embed({}) == "answer_failure"


@then('a top similarity of 0.6999 at the same threshold routes to "web_search"')
def _memory_below():
    assert route_after_memory({"top_similarity": 0.6999, "threshold": 0.70}) == "web_search"


@then('an absent top similarity routes to "web_search"')
def _memory_absent():
    assert route_after_memory({"top_similarity": None, "threshold": 0.70}) == "web_search"


@then('an empty search-results list routes to "answer_failure"')
def _search_empty():
    assert route_after_search({"search_results": []}) == "answer_failure"


@then('an empty fetched-docs list routes to "answer_from_web"')
def _fetch_empty():
    assert route_after_fetch({"fetched_docs": []}) == "answer_from_web"


# =========================================================================== #
# graph.feature — build_graph, inspected via the compiled mermaid diagram     #
# =========================================================================== #
@given("the graph is compiled from keyless resources", target_fixture="compiled_graph")
def _compiled_graph():
    return build_graph(_keyless_resources())


@when("its structure is rendered as a mermaid diagram", target_fixture="mermaid")
def _render_mermaid(compiled_graph):
    return compiled_graph.get_graph().draw_mermaid()


@when("its structure is inspected", target_fixture="mermaid")
def _inspect(compiled_graph):
    return compiled_graph.get_graph().draw_mermaid()


@then('the entry edge goes from start into "guard_input"')
def _entry_guard(mermaid):
    assert "__start__ --> guard_input" in mermaid


@then('the guard can route directly to "log_turn"')
def _guard_to_log(mermaid):
    assert "guard_input -.-> log_turn" in mermaid


@then('the guard can also route onward to "embed_query"')
def _guard_to_embed(mermaid):
    assert "guard_input -.-> embed_query" in mermaid


@then("it contains the memory-first nodes guard_input, embed_query, memory_search and log_turn")
def _has_nodes(compiled_graph):
    nodes = set(compiled_graph.get_graph().nodes)
    assert {"guard_input", "embed_query", "memory_search", "log_turn"} <= nodes


@then('memory_search can branch to either "answer_from_memory" or "web_search"')
def _memory_branch(mermaid):
    assert "memory_search -.-> answer_from_memory" in mermaid
    assert "memory_search -.-> web_search" in mermaid


@then('answer_from_memory, answer_from_web and answer_failure all lead to "log_turn"')
def _answers_to_log(mermaid):
    assert "answer_from_memory --> log_turn" in mermaid
    assert "answer_from_web --> log_turn" in mermaid
    assert "answer_failure --> log_turn" in mermaid


@then("log_turn is the final node before the graph ends")
def _log_to_end(mermaid):
    assert "log_turn --> __end__" in mermaid


# =========================================================================== #
# app.feature — configure_logging                                             #
# =========================================================================== #
@given("logging is configured from the keyless settings")
def _configure_logging(settings):
    configure_logging(settings)


@when("the active structured-logging configuration is inspected", target_fixture="log_cfg")
def _inspect_log_cfg():
    return structlog.get_config()


@then("its logger factory writes to stderr rather than stdout")
def _factory_stderr(log_cfg):
    factory = log_cfg["logger_factory"]
    assert isinstance(factory, structlog.PrintLoggerFactory)
    assert factory._file is sys.stderr
    assert factory._file is not sys.stdout


@then("the log stream is rendered for the console")
def _console_render(log_cfg):
    assert any(isinstance(p, structlog.dev.ConsoleRenderer) for p in log_cfg["processors"])


# =========================================================================== #
# app.feature — configure_tracing                                             #
# =========================================================================== #
@given("tracing is configured from settings that never opted in", target_fixture="tracing_ctx")
def _tracing_default():
    env: dict[str, str] = {}  # the injection seam: no real os.environ mutation, no leak
    enabled = configure_tracing(Settings(_env_file=None, openai_api_key="sk-test"), env=env)
    return {"enabled": enabled, "env": env}


@given(
    "tracing is configured with the flag set but no API key",
    target_fixture="tracing_ctx",
)
def _tracing_no_key():
    env: dict[str, str] = {}
    # the AND gate's documented boundary: flag set, key blank -> tracing must stay off
    half = Settings(_env_file=None, openai_api_key="sk-test", langsmith_tracing=True)
    return {"enabled": configure_tracing(half, env=env), "env": env}


@given(
    "tracing is configured with LangSmith enabled and an API key",
    target_fixture="tracing_ctx",
)
def _tracing_opted_in():
    env: dict[str, str] = {}
    opted_in = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        langsmith_tracing=True,
        langsmith_api_key="ls-test",
        langsmith_project="proj-x",
    )
    return {"enabled": configure_tracing(opted_in, env=env), "env": env}


@then("tracing reports disabled and exports no LANGSMITH variables")
def _tracing_stays_off(tracing_ctx):
    assert tracing_ctx["enabled"] is False
    assert tracing_ctx["env"] == {}


@then("tracing reports enabled and exports the four LANGSMITH variables")
def _tracing_exports(tracing_ctx):
    assert tracing_ctx["enabled"] is True
    assert tracing_ctx["env"] == {
        "LANGSMITH_TRACING": "true",
        "LANGSMITH_API_KEY": "ls-test",
        "LANGSMITH_ENDPOINT": "https://api.smith.langchain.com",
        "LANGSMITH_PROJECT": "proj-x",
    }


@given(
    "resources are built from settings that opt in to LangSmith tracing",
    target_fixture="traced_env",
)
def _resources_opted_in(monkeypatch):
    # register an undo for every var the production path writes into the REAL os.environ
    for var in (
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_ENDPOINT",
        "LANGSMITH_PROJECT",
    ):
        monkeypatch.setenv(var, "pre")
        monkeypatch.delenv(var)
    opted_in = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        langsmith_tracing=True,
        langsmith_api_key="ls-test",
    )
    build_resources(opted_in)  # the wiring under test: it must export for real, not to a seam
    return dict(os.environ)


@then("the process environment carries the LangSmith opt-in for the graph run")
def _env_carries_opt_in(traced_env):
    assert traced_env["LANGSMITH_TRACING"] == "true"
    assert traced_env["LANGSMITH_API_KEY"] == "ls-test"
    assert traced_env["LANGSMITH_ENDPOINT"] == "https://api.smith.langchain.com"


# =========================================================================== #
# app.feature — new_turn_state                                                #
# =========================================================================== #
@given(
    parsers.parse('a fresh turn state built for the question "{q}"'),
    target_fixture="turn_state",
)
def _fresh_turn_state(settings, q):
    long_history = [{"role": "user", "content": str(i)} for i in range(50)]
    state = new_turn_state(settings, "session-1", q, long_history)
    return {"state": state, "settings": settings, "query": q}


@then('the guard verdict starts as "allow" and the sanitized query mirrors the question')
def _state_guard_allow(turn_state):
    assert turn_state["state"]["guard_verdict"] == "allow"
    assert turn_state["state"]["sanitized_query"] == turn_state["query"]
    assert turn_state["state"]["query"] == turn_state["query"]


@then("the threshold is taken from the configured similarity threshold")
def _state_threshold(turn_state):
    assert turn_state["state"]["threshold"] == turn_state["settings"].similarity_threshold


@then('the route defaults to "failed" until a node proves otherwise')
def _state_route_default(turn_state):
    assert turn_state["state"]["route"] == "failed"


@then("the turn carries a non-empty turn id and the conversation history is capped")
def _state_turn_id_and_history(turn_state):
    state, settings = turn_state["state"], turn_state["settings"]
    assert isinstance(state["turn_id"], str) and state["turn_id"]
    assert len(state["history"]) == settings.history_max_turns * 2


# =========================================================================== #
# app.feature — build_resources                                               #
# =========================================================================== #
@given("resources are built from the keyless settings", target_fixture="built_resources")
def _built_resources(settings):
    return build_resources(settings)


@then("the memory store is a Redis-backed store and the embedder matches the configured dimension")
def _resources_memory_embedder(built_resources, settings):
    assert isinstance(built_resources.memory, RedisMemoryStore)
    assert built_resources.embedder.dim == settings.embedding_dim


@then(
    "the searcher is the Tavily-first fallback provider and the fetcher is the httpx page fetcher"
)
def _resources_search_fetch(built_resources):
    assert isinstance(built_resources.searcher, FallbackProvider)
    assert isinstance(built_resources.fetcher, HttpxPageFetcher)


@then("the same settings object is threaded through the resources")
def _resources_settings_identity(built_resources, settings):
    assert built_resources.settings is settings
    # tidy up the lazily-constructed redis client (never connected)
    try:
        asyncio.run(built_resources.memory._redis.aclose())
    except Exception:  # noqa: BLE001 — best-effort cleanup only
        pass


# =========================================================================== #
# app.feature — Agent.__init__                                                #
# =========================================================================== #
@given("an agent constructed from keyless resources", target_fixture="two_agents")
def _two_agents():
    res = _keyless_resources()
    return {"res": res, "a1": Agent(res), "a2": Agent(res)}


@then("it holds a compiled, invokable graph and the resources it was given")
def _agent_graph_and_resources(two_agents):
    a1 = two_agents["a1"]
    assert a1.graph is not None and hasattr(a1.graph, "ainvoke")
    assert a1.resources is two_agents["res"]


@then("it has a non-empty session id distinct from a second agent's")
def _agent_session_id(two_agents):
    a1, a2 = two_agents["a1"], two_agents["a2"]
    assert isinstance(a1.session_id, str) and a1.session_id
    assert a1.session_id != a2.session_id


# =========================================================================== #
# app.feature — Agent.ensure_ready (live index provisioning, idempotent)      #
# =========================================================================== #
@when("the agent is made ready twice against a dropped index", target_fixture="ready_probe")
def _agent_made_ready_twice(live):
    async def go():
        admin = aioredis.from_url(live["settings"].redis_url)
        try:
            index = get_index(live["settings"], admin)
            if await index.exists():
                await index.delete(drop=True)  # fresh Redis: no index at all
            agent = live["agent"]
            await agent.ensure_ready()  # must create the index
            first_ready = agent._ready
            exists_after = await index.exists()
            await agent.ensure_ready()  # idempotent: a no-op the second time
            return {"first": first_ready, "exists": exists_after, "ready": agent._ready}
        finally:
            await admin.aclose()
            await live["resources"].memory._redis.aclose()

    return asyncio.run(go())


@then("the memory index exists and readiness is a no-op the second time")
def _agent_ready_idempotent(ready_probe):
    assert ready_probe["exists"] is True
    assert ready_probe["first"] is True and ready_probe["ready"] is True


# =========================================================================== #
# app.feature — Agent.answer (live, single-turn miss path)                    #
# =========================================================================== #
@given("a live agent over an empty memory index", target_fixture="live")
def _live_agent(settings):
    probe_redis_or_skip(settings)  # skip-not-fail if Redis is unreachable (it is up here)
    client = make_redis_client(settings)
    resources = build_test_resources(settings, client)
    return {
        "settings": settings,
        "client": client,
        "resources": resources,
        "agent": Agent(resources),
        "query": QUESTION,
    }


@given("the web returns a page relevant to the question")
def _web_page_ok(respx_mock, live):
    live["tavily"] = respx_mock.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"url": URL, "title": "Redis Vector Search", "content": QUESTION}]},
        )
    )
    respx_mock.get(URL).mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE_HTML)
    )


@when("the agent answers the question")
def _agent_answers(live):
    async def go():
        admin = aioredis.from_url(live["settings"].redis_url)
        try:
            await wipe_index(get_index(live["settings"], admin))  # empty index before the turn
            return await live["agent"].answer(live["query"])
        finally:
            await admin.aclose()
            await live["resources"].memory._redis.aclose()

    live["result"] = asyncio.run(go())


@then('the returned turn result is routed "memory_miss_web_search"')
def _answer_route(live):
    assert live["result"].route == "memory_miss_web_search", live["result"].route


@then("the result carries a non-empty answer and cites the web source URL")
def _answer_content(live):
    result = live["result"]
    assert result.answer
    assert any(s["origin"] == "web" for s in result.sources), result.sources
    assert URL in [s["url"] for s in result.sources]


@then("the reported similarity is None because memory was empty")
def _answer_similarity_none(live):
    assert live["result"].similarity is None
