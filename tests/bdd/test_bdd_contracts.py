"""Executable bindings for the contracts batch feature files.

Covers the DI seams and scaffold contracts: config.Settings defaults/overrides, the
state.py channel reducer, the frozen AgentResources container, the interfaces.py
Protocols, the package version, and the ``python -m memagent`` entry point.

Keyless by construction: Settings are built with ``_env_file=None``; the Embedder /
ChatLLM contracts are exercised through the conftest fakes; WebSearcher and PageFetcher
are exercised through their REAL implementations with respx intercepting httpx; the
MemoryStore contract is exercised through an in-memory conforming stand-in (the real
RedisMemoryStore needs Redis, which this batch may not use); the TurnLogger contract
uses the real TurnLogger writing to a tmp file. Every ``then`` asserts a real observable
outcome and each interfaces scenario also anchors on the real Protocol declaration.
"""

import asyncio
import dataclasses
import inspect
import json
import os
import subprocess
import sys

import httpx
import pytest
import respx
from pytest_bdd import given, parsers, scenarios, then, when

import memagent.interfaces as interfaces
from memagent.analytics.classify import QueryClassification
from memagent.analytics.turnlog import TurnLogger
from memagent.config import Settings
from memagent.resources import AgentResources
from memagent.state import _merge_dicts
from memagent.web.fetch import HttpxPageFetcher
from memagent.web.search import TAVILY_ENDPOINT, TavilySearcher

scenarios("features/config.feature")
scenarios("features/state.feature")
scenarios("features/resources.feature")
scenarios("features/interfaces.feature")
scenarios("features/package.feature")
scenarios("features/main_entry.feature")


# --------------------------------------------------------------------------- #
# shared helpers                                                              #
# --------------------------------------------------------------------------- #
_RESOURCE_FIELDS = {
    "settings",
    "memory",
    "embedder",
    "chat_llm",
    "analytics_llm",
    "searcher",
    "fetcher",
    "turn_logger",
}

# Distinct, identity-comparable stand-ins so dataclasses.replace assertions are real.
_ORIGINAL_EMBEDDER = ("stub-embedder", "original")
_REPLACEMENT_EMBEDDER = ("stub-embedder", "replacement")


def _make_hit(similarity: float, doc_id: str) -> dict:
    """A MemoryHit-shaped dict (state.MemoryHit is a TypedDict -> a plain dict at runtime)."""
    return {
        "doc_id": doc_id,
        "text": f"chunk {doc_id}",
        "url": f"https://mem.test/{doc_id}",
        "title": doc_id,
        "similarity": similarity,
        "stored_at": "2026-07-03T10:41:22+00:00",
        "sanitizer_flags": [],
        "doc_type": "chunk",
    }


def _make_chunk(index: int) -> dict:
    return {
        "chunk_id": f"chunk:h:{index}",
        "text": f"body {index}",
        "url": "https://page.test/a",
        "title": "A page",
        "chunk_index": index,
    }


class InMemoryStore:
    """A conforming MemoryStore stand-in that honours the interfaces.py contract:

    knn returns the RAW top-k with similarity attached and applies NO threshold filter
    (threshold filtering is a router/node concern); store returns one id per chunk;
    is_fresh reports membership in the recently-seen set.
    """

    def __init__(self, hits: list[dict] | None = None, fresh: set[str] | None = None):
        self._hits = hits or []
        self._fresh = fresh or set()
        self.stored_ids: list[str] = []
        self.ensure_calls = 0

    async def ensure_ready(self) -> None:
        self.ensure_calls += 1

    async def knn(self, vector: list[float], k: int) -> list[dict]:
        ordered = sorted(self._hits, key=lambda h: h["similarity"], reverse=True)
        return ordered[:k]  # RAW top-k, unfiltered

    async def store(self, page, chunks, vectors, source_query, flags) -> list[str]:
        ids = [c["chunk_id"] for c in chunks]
        self.stored_ids.extend(ids)
        return ids

    async def is_fresh(self, h: str) -> bool:
        return h in self._fresh


def _page_html(title: str) -> bytes:
    body = (
        "Redis vector search uses cosine similarity over embeddings stored in a FLAT index. "
        "This paragraph is deliberately long enough that the markdown extractor produces a "
        "non-empty document instead of discarding the page as boilerplate or too short."
    )
    return (
        f"<html><head><title>{title}</title></head>"
        f"<body><article><h1>{title}</h1><p>{body}</p></article></body></html>"
    ).encode()


# --------------------------------------------------------------------------- #
# config.feature                                                              #
# --------------------------------------------------------------------------- #
@given("no similarity or key overrides are set in the environment")
def _clean_env(monkeypatch):
    for key in (
        "SIMILARITY_THRESHOLD",
        "EMBEDDING_DIM",
        "MEMORY_INDEX_NAME",
        "MEMORY_TTL_SECONDS",
        "CHUNK_SIZE_CHARS",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@given(parsers.parse('the environment sets {name} to "{value}"'))
def _set_env(monkeypatch, name, value):
    monkeypatch.setenv(name, value)


@given("OPENAI_API_KEY is not set in the environment")
def _unset_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@given('an unrecognised environment variable SOME_UNKNOWN_VAR is set to "x"')
def _set_unknown(monkeypatch):
    monkeypatch.setenv("SOME_UNKNOWN_VAR", "x")


@when("Settings are constructed from the environment", target_fixture="built_settings")
def _build_settings():
    return Settings(_env_file=None)


@then("the similarity threshold defaults to 0.70")
def _thr_default(built_settings):
    assert built_settings.similarity_threshold == 0.70


@then("the embedding dimension defaults to 1536")
def _dim_default(built_settings):
    assert built_settings.embedding_dim == 1536


@then('the memory index is named "web_memory"')
def _index_default(built_settings):
    assert built_settings.memory_index_name == "web_memory"


@then("the memory TTL defaults to 604800 seconds")
def _ttl_default(built_settings):
    assert built_settings.memory_ttl_seconds == 604800


@then("the chunk size defaults to 1600 characters")
def _chunk_default(built_settings):
    assert built_settings.chunk_size_chars == 1600


@then("the similarity threshold is exactly 0.85")
def _thr_override(built_settings):
    assert built_settings.similarity_threshold == 0.85


@then("construction succeeds without raising")
def _construction_ok(built_settings):
    assert isinstance(built_settings, Settings)


@then("the OpenAI API key is the empty string")
def _key_empty(built_settings):
    assert built_settings.openai_api_key == ""


@then('the settings object has no attribute named "some_unknown_var"')
def _no_unknown_attr(built_settings):
    assert not hasattr(built_settings, "some_unknown_var")


# --------------------------------------------------------------------------- #
# state.feature                                                               #
# --------------------------------------------------------------------------- #
@given("a turn that has recorded latency for the embed node", target_fixture="left_map")
def _left_map():
    return {"embed": 42}


@given("a later node records latency for the answer model", target_fixture="right_map")
def _right_map():
    return {"answer_llm": 1420}


@when("the two latency contributions are merged by the state reducer", target_fixture="merged_map")
def _merge(left_map, right_map):
    return _merge_dicts(left_map, right_map)


@then("the merged map contains both nodes' timings")
def _merged_union(merged_map):
    assert merged_map == {"embed": 42, "answer_llm": 1420}


@then("a later write to the same node key overrides the earlier value")
def _merge_override():
    assert _merge_dicts({"embed": 1}, {"embed": 2}) == {"embed": 2}


@then("merging leaves the original contribution maps unmodified")
def _merge_no_mutation(left_map, right_map):
    assert left_map == {"embed": 42}
    assert right_map == {"answer_llm": 1420}


# --------------------------------------------------------------------------- #
# resources.feature                                                           #
# --------------------------------------------------------------------------- #
@given("a resources container assembled from stand-in collaborators", target_fixture="res")
def _res():
    return AgentResources(
        settings=Settings(_env_file=None),
        memory=("stub", "memory"),
        embedder=_ORIGINAL_EMBEDDER,
        chat_llm=("stub", "chat_llm"),
        analytics_llm=("stub", "analytics_llm"),
        searcher=("stub", "searcher"),
        fetcher=("stub", "fetcher"),
        turn_logger=("stub", "turn_logger"),
    )


@when("the container is inspected")
def _inspect_container(res):
    # Assertions happen in the then steps; nothing to compute here.
    assert res is not None


@when("the embedder is swapped via dataclasses.replace", target_fixture="swapped")
def _swap_embedder(res):
    new = dataclasses.replace(res, embedder=_REPLACEMENT_EMBEDDER)
    return {"original": res, "new": new}


@then("it is a frozen dataclass")
def _is_frozen(res):
    assert dataclasses.is_dataclass(res)
    assert type(res).__dataclass_params__.frozen is True


@then("it exposes exactly the eight collaborator fields")
def _eight_fields(res):
    assert {f.name for f in dataclasses.fields(res)} == _RESOURCE_FIELDS


@then("reassigning a collaborator after construction is rejected")
def _reassign_rejected(res):
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.embedder = _REPLACEMENT_EMBEDDER


@then("the new container uses the replacement embedder")
def _new_uses_replacement(swapped):
    assert swapped["new"].embedder is _REPLACEMENT_EMBEDDER


@then("the original container still holds its first embedder")
def _original_intact(swapped):
    assert swapped["original"].embedder is _ORIGINAL_EMBEDDER


@then("both containers remain immutable")
def _both_immutable(swapped):
    for container in (swapped["original"], swapped["new"]):
        with pytest.raises(dataclasses.FrozenInstanceError):
            container.embedder = ("stub", "mutated")


# --------------------------------------------------------------------------- #
# interfaces.feature                                                          #
# --------------------------------------------------------------------------- #
@then(parsers.parse("the {proto} contract declares {method} as an async method"))
def _protocol_declares_async(proto, method):
    fn = getattr(getattr(interfaces, proto), method)
    assert inspect.iscoroutinefunction(fn), f"{proto}.{method} should be an async coroutine"


# --- Embedder.embed ---
@given("a conforming embedder", target_fixture="embedder")
def _embedder(fake_embedder):
    return fake_embedder


@when("it embeds a batch that repeats one text", target_fixture="embed_out")
def _do_embed(embedder):
    texts = ["redis vector search", "redis vector search", "graph databases"]
    vectors = asyncio.run(embedder.embed(texts))
    return {"texts": texts, "vectors": vectors, "dim": embedder.dim}


@then("it returns one vector per input text")
def _embed_count(embed_out):
    assert len(embed_out["vectors"]) == len(embed_out["texts"])


@then("every vector has the configured embedding width")
def _embed_width(embed_out):
    assert all(len(v) == embed_out["dim"] for v in embed_out["vectors"])


@then("identical input texts produce identical vectors")
def _embed_deterministic(embed_out):
    vectors = embed_out["vectors"]
    assert vectors[0] == vectors[1]  # same text -> same vector
    assert vectors[0] != vectors[2]  # different text -> different vector


# --- ChatLLM.complete ---
@given("a conforming chat model", target_fixture="chat_model")
def _chat_model(fake_llm):
    return fake_llm


@when("it completes a system-plus-user conversation", target_fixture="complete_out")
def _do_complete(chat_model):
    return asyncio.run(chat_model.complete("SYSTEM", [{"role": "user", "content": "hi"}]))


@then("the result carries the generated answer text")
def _complete_text(complete_out):
    assert isinstance(complete_out, interfaces.CompletionResult)
    assert isinstance(complete_out.text, str) and complete_out.text


@then("the result carries a usage record with input, output and model")
def _complete_usage(complete_out):
    assert {"input_tokens", "output_tokens", "model"} <= set(complete_out.usage)


# --- ChatLLM.parse ---
@given("a conforming classifier chat model", target_fixture="classifier_model")
def _classifier_model(fake_llm_qc):
    return fake_llm_qc


@when("it parses a query into a QueryClassification schema", target_fixture="parse_out")
def _do_parse(classifier_model):
    obj, usage = asyncio.run(classifier_model.parse("SYSTEM", "classify me", QueryClassification))
    return {"obj": obj, "usage": usage}


@then("it returns the populated schema instance and a usage record")
def _parse_shape(parse_out):
    assert isinstance(parse_out["usage"], dict) and parse_out["usage"]


@then("the parsed instance is a QueryClassification")
def _parse_type(parse_out):
    assert isinstance(parse_out["obj"], QueryClassification)


# --- WebSearcher.search (real TavilySearcher + respx) ---
@given("a Tavily-backed web searcher", target_fixture="tavily_settings")
def _tavily_settings():
    return Settings(_env_file=None, wait_cap_scale=0.0, tavily_api_key="test-key")


@when("it searches for a query capped at three results", target_fixture="search_out")
def _do_search(tavily_settings):
    payload = {
        "results": [
            {"url": "https://r1.test", "title": "R1", "content": "snippet one"},
            {"url": "https://r2.test", "title": "R2", "content": "snippet two"},
            {"url": "https://r3.test", "title": "R3", "content": "snippet three"},
        ]
    }
    with respx.mock:
        respx.post(TAVILY_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        results = asyncio.run(TavilySearcher(tavily_settings).search("redis vectors", 3))
    return {"results": results}


@then("it returns three ranked SearchResult records")
def _search_count(search_out):
    results = search_out["results"]
    assert len(results) == 3
    assert all({"url", "title", "snippet", "rank"} <= set(r) for r in results)


@then("each result preserves its zero-based rank order")
def _search_ranks(search_out):
    assert [r["rank"] for r in search_out["results"]] == [0, 1, 2]


@then("the snippet is mapped from the provider content field")
def _search_snippet(search_out):
    assert [r["snippet"] for r in search_out["results"]] == [
        "snippet one",
        "snippet two",
        "snippet three",
    ]


# --- MemoryStore.ensure_ready ---
@given("a conforming in-memory store", target_fixture="ensure_store")
def _ensure_store():
    return InMemoryStore()


@when("its index provisioning is ensured", target_fixture="ensure_out")
def _do_ensure(ensure_store):
    asyncio.run(ensure_store.ensure_ready())
    return ensure_store


@then("the provisioning completes without error")
def _ensure_ok(ensure_out):
    assert ensure_out.ensure_calls == 1


# --- MemoryStore.knn ---
@given(
    "an in-memory store holding hits both above and below the similarity threshold",
    target_fixture="knn_store",
)
def _knn_store():
    return InMemoryStore(hits=[_make_hit(0.92, "a"), _make_hit(0.55, "b"), _make_hit(0.30, "c")])


@when("the store is queried for its nearest neighbours", target_fixture="knn_out")
def _do_knn(knn_store):
    return asyncio.run(knn_store.knn([0.0, 0.0, 0.0], k=5))


@then("it returns the raw top-k ordered by descending similarity")
def _knn_ordered(knn_out):
    assert [h["similarity"] for h in knn_out] == [0.92, 0.55, 0.30]


@then("hits below the 0.70 threshold are still returned unfiltered")
def _knn_unfiltered(knn_out):
    below = [h["similarity"] for h in knn_out if h["similarity"] < 0.70]
    assert below == [0.55, 0.30]  # nothing was dropped by the store


@then("every returned hit carries its similarity score")
def _knn_similarity_attached(knn_out):
    assert all("similarity" in h for h in knn_out)


# --- MemoryStore.store ---
@given("an in-memory store and a page split into three chunks", target_fixture="store_in")
def _store_in():
    page = {
        "url": "https://page.test/a",
        "title": "A page",
        "markdown": "m",
        "summary": None,
        "ok": True,
    }
    chunks = [_make_chunk(i) for i in range(3)]
    vectors = [[0.0, 0.0, 0.0] for _ in chunks]
    return {"store": InMemoryStore(), "page": page, "chunks": chunks, "vectors": vectors}


@when("the chunks and their vectors are stored", target_fixture="store_out")
def _do_store(store_in):
    return asyncio.run(
        store_in["store"].store(
            store_in["page"], store_in["chunks"], store_in["vectors"], "redis", ["flag"]
        )
    )


@then("one chunk identifier is returned per chunk")
def _store_ids(store_in, store_out):
    assert len(store_out) == len(store_in["chunks"])


# --- MemoryStore.is_fresh ---
@given("an in-memory store that has recently seen one URL hash", target_fixture="fresh_store")
def _fresh_store():
    return InMemoryStore(fresh={"abc123"})


@when("freshness is checked for a seen and an unseen hash", target_fixture="fresh_out")
def _do_is_fresh(fresh_store):
    seen = asyncio.run(fresh_store.is_fresh("abc123"))
    unseen = asyncio.run(fresh_store.is_fresh("zzz999"))
    return {"seen": seen, "unseen": unseen}


@then("the seen hash is reported fresh and the unseen hash is not")
def _fresh_result(fresh_out):
    assert fresh_out["seen"] is True
    assert fresh_out["unseen"] is False


# --- PageFetcher.fetch (real HttpxPageFetcher + respx) ---
@given("an httpx page fetcher and two stubbed HTML pages", target_fixture="fetch_settings")
def _fetch_settings():
    return Settings(_env_file=None, wait_cap_scale=0.0)


@when("it fetches both URLs", target_fixture="fetch_out")
def _do_fetch(fetch_settings):
    html_headers = {"content-type": "text/html"}
    with respx.mock:
        respx.get("https://alpha.test/").mock(
            return_value=httpx.Response(200, headers=html_headers, content=_page_html("Alpha"))
        )
        respx.get("https://beta.test/").mock(
            return_value=httpx.Response(200, headers=html_headers, content=_page_html("Beta"))
        )
        fetcher = HttpxPageFetcher(fetch_settings)
        docs = asyncio.run(fetcher.fetch(["https://alpha.test/", "https://beta.test/"]))
    return docs


@then("it returns one cleaned document per fetchable page")
def _fetch_count(fetch_out):
    assert len(fetch_out) == 2


@then("each document is marked ok with extracted markdown and a title")
def _fetch_docs_shape(fetch_out):
    assert all(d["ok"] for d in fetch_out)
    assert all(d["markdown"] for d in fetch_out)
    assert {d["title"] for d in fetch_out} == {"Alpha", "Beta"}


# --- TurnLogger.log (real TurnLogger) ---
@given("a turn logger writing to a temporary log file", target_fixture="log_ctx")
def _log_ctx(tmp_path):
    path = tmp_path / "turns.jsonl"
    return {"logger": TurnLogger(str(path)), "path": path}


@when("two turn records are logged")
def _do_log(log_ctx):
    log_ctx["logger"].log({"turn_id": "t1", "route": "memory_hit"})
    log_ctx["logger"].log({"turn_id": "t2", "route": "blocked"})


@then("exactly two JSON lines are appended")
def _log_two_lines(log_ctx):
    lines = [ln for ln in log_ctx["path"].read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


@then("each line round-trips to the record that was logged")
def _log_roundtrip(log_ctx):
    lines = [ln for ln in log_ctx["path"].read_text(encoding="utf-8").splitlines() if ln.strip()]
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first == {"turn_id": "t1", "route": "memory_hit"}
    assert second == {"turn_id": "t2", "route": "blocked"}


@then("the TurnLogger contract declares log as a synchronous method")
def _turnlogger_sync():
    fn = interfaces.TurnLogger.log
    assert not inspect.iscoroutinefunction(fn)
    assert "record" in inspect.signature(fn).parameters


# --------------------------------------------------------------------------- #
# package.feature                                                             #
# --------------------------------------------------------------------------- #
@given("the installed memagent package", target_fixture="pkg")
def _pkg():
    import memagent

    return memagent


@when("its version marker is read", target_fixture="pkg_version")
def _pkg_version(pkg):
    return pkg.__version__


@then('it is the semantic version "0.1.0"')
def _version_value(pkg_version):
    assert pkg_version == "0.1.0"


@then("the version has three dotted numeric components")
def _version_shape(pkg_version):
    parts = pkg_version.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


# --------------------------------------------------------------------------- #
# main_entry.feature                                                          #
# --------------------------------------------------------------------------- #
@given(
    parsers.parse('the memagent package invoked as "{command}"'),
    target_fixture="entry_command",
)
def _entry_command(command):
    assert command == "python -m memagent --help"
    return [sys.executable, "-m", "memagent", "--help"]


@when("the module entry point runs", target_fixture="entry_proc")
def _run_entry(entry_command):
    env = {**os.environ, "COLUMNS": "200", "NO_COLOR": "1"}
    return subprocess.run(entry_command, capture_output=True, text=True, env=env)


@then("it exits with status zero")
def _entry_exit(entry_proc):
    assert entry_proc.returncode == 0, entry_proc.stderr


@then("the help output lists the four subcommands")
def _entry_help(entry_proc):
    output = entry_proc.stdout + entry_proc.stderr
    for command in ("wipe-memory", "ask", "chat", "analytics"):
        assert command in output, f"{command!r} missing from --help output"
