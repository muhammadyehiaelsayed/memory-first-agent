"""M4-owned: TurnLogger + build_turn_record + real log_turn node (FR-M4-09..12).

Uses tmp_path JSONL files and small inline fakes (the M6 conftest does not exist yet).
"""

import asyncio
import json
import threading
import time
import uuid

from memagent.analytics.classify import QueryClassification
from memagent.analytics.turnlog import TurnLogger, build_turn_record
from memagent.config import Settings
from memagent.nodes.log import make_log_turn

RECORD_KEYS = {
    "turn_id",
    "ts",
    "session_id",
    "query",
    "query_sha256",
    "route",
    "degradation",
    "similarity_top",
    "similarity_threshold",
    "web",
    "sources",
    "latency_ms",
    "tokens",
    "cost_usd",
    "guardrail",
    "errors",
    "analytics",
}

VALID_CLF = QueryClassification(
    topic="redis vector search",
    category="technology",
    question_type="how_to",
    language="en",
    confidence=0.9,
)
NANO_USAGE = {"input_tokens": 198, "output_tokens": 36, "model": "gpt-5.4-nano"}


def make_state(route: str, **overrides) -> dict:
    state = {
        "turn_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "query": "How does Redis vector search work?",
        "route": route,
        "degradation": None,
        "top_similarity": 0.74 if route == "memory_hit" else 0.41,
        "search_results": [],
        "fetched_docs": [],
        "chunks": [],
        "sources": [],
        "errors": [],
        "latency_ms": {},
        "tokens": {},
        "guard_verdict": "allow",
        "guardrail_events": [],
        "analytics": None,
        "search_provider": None,
    }
    state.update(overrides)
    return state


class FakeAnalyticsLLM:
    async def parse(self, system, user, schema):
        return VALID_CLF, dict(NANO_USAGE)


class Resources:
    """Inline stand-in for AgentResources — only what log_turn touches."""

    def __init__(self, turn_logger):
        self.settings = Settings()
        self.analytics_llm = FakeAnalyticsLLM()
        self.turn_logger = turn_logger


class RaisingLogger:
    def log(self, record: dict) -> None:
        raise OSError("disk full")


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_exactly_one_line_per_log_call(tmp_path):
    logger = TurnLogger(str(tmp_path / "logs" / "turns.jsonl"))
    settings = Settings()
    for _ in range(3):
        logger.log(build_turn_record(make_state("memory_hit"), settings))
    lines = read_lines(tmp_path / "logs" / "turns.jsonl")
    assert len(lines) == 3


def test_record_shape_for_every_route():
    settings = Settings()
    for route in ("memory_hit", "memory_miss_web_search", "degraded_web", "blocked", "failed"):
        record = build_turn_record(make_state(route), settings)
        assert set(record) == RECORD_KEYS
        assert record["route"] == route
        uuid.UUID(record["turn_id"])  # valid uuid4 string
        sha = record["query_sha256"]
        assert len(sha) == 16 and int(sha, 16) >= 0  # 16 hex chars
        assert json.loads(json.dumps(record)) == record  # JSON-serializable as-is


def test_memory_hit_has_no_web_block_and_default_threshold():
    record = build_turn_record(make_state("memory_hit"), Settings())
    assert record["web"] is None
    assert record["similarity_threshold"] == 0.7


def test_web_route_builds_web_block():
    state = make_state(
        "memory_miss_web_search",
        search_provider="tavily",
        search_results=[{"url": "u", "title": "t", "snippet": "s", "rank": 0}] * 5,
        fetched_docs=[{"url": "u", "title": "t", "markdown": "m", "summary": None, "ok": True}] * 3
        + [{"url": "u2", "title": "t", "markdown": "", "summary": None, "ok": False}],
        chunks=[{"chunk_id": "c", "text": "x", "url": "u", "title": "t", "chunk_index": 0}] * 14,
        stored_chunk_ids=[f"chunk:h:{i}" for i in range(12)],  # 12 PERSISTED of 14 produced
    )
    web = build_turn_record(state, Settings())["web"]
    assert web == {
        "provider": "tavily",
        "results_returned": 5,
        "pages_fetched": 3,
        "chunks_ingested": 12,  # persisted count (stored_chunk_ids), not the 14 produced
    }


def test_failed_web_turn_still_emits_web_block_and_hit_stays_null():
    # A8: a web turn that ends route="failed" (e.g. answer-LLM failure after ingest already
    # persisted chunks) must NOT lose its web block just because the final route is "failed".
    # timed("web_search") stamps latency_ms["web_search"] whenever the web pipeline ran, so
    # gate on that evidence rather than the route.
    failed = make_state(
        "failed",
        search_provider="tavily",
        search_results=[{"url": "u", "title": "t", "snippet": "s", "rank": 0}] * 4,
        fetched_docs=[{"url": "u", "title": "t", "markdown": "m", "summary": None, "ok": True}] * 2,
        stored_chunk_ids=[f"chunk:h:{i}" for i in range(9)],  # 9 chunks DID persist before failure
        latency_ms={"web_search": 210, "fetch": 480, "ingest": 90},
    )
    web = build_turn_record(failed, Settings())["web"]
    assert web == {
        "provider": "tavily",
        "results_returned": 4,
        "pages_fetched": 2,
        "chunks_ingested": 9,  # persisted chunks survive into the record despite route="failed"
    }
    # a pure memory-hit turn never enters web_search, so the signal is absent -> web stays null
    assert build_turn_record(make_state("memory_hit"), Settings())["web"] is None


def test_blocked_turn_is_still_logged(tmp_path):
    logger = TurnLogger(str(tmp_path / "turns.jsonl"))
    log_turn = make_log_turn(Resources(logger))
    state = make_state("blocked", guard_verdict="block", turn_started_at=time.perf_counter())
    asyncio.run(log_turn(state))
    lines = read_lines(tmp_path / "turns.jsonl")
    assert len(lines) == 1 and lines[0]["route"] == "blocked"
    assert lines[0]["guardrail"]["verdict"] == "block"


def test_log_turn_never_raises_when_logger_fails(capsys):
    log_turn = make_log_turn(Resources(RaisingLogger()))
    state = make_state("memory_hit", turn_started_at=time.perf_counter())
    updates = asyncio.run(log_turn(state))  # must not raise
    assert isinstance(updates, dict)


def test_summary_llm_tokens_are_aggregated_into_the_record():
    # ingest_content records per-page summary usage under hash-keyed summary:{h} entries;
    # build_turn_record must fold them into one summary_llm bucket so web turns don't undercount.
    state = make_state(
        "memory_miss_web_search",
        tokens={
            "answer_llm": {"model": "gpt-5.4-mini", "input_tokens": 2311, "output_tokens": 402},
            "summary:h1": {"model": "gpt-5.4-nano", "input_tokens": 500, "output_tokens": 90},
            "summary:h2": {"model": "gpt-5.4-nano", "input_tokens": 300, "output_tokens": 60},
        },
    )
    record = build_turn_record(state, Settings())
    assert record["tokens"]["summary_llm"] == {
        "model": "gpt-5.4-nano",
        "input": 800,  # 500 + 300 summed across both pages
        "output": 150,  # 90 + 60
    }
    # answer tokens still recorded and summary stays distinct from analytics_llm
    assert record["tokens"]["answer_llm"]["input"] == 2311
    assert "analytics_llm" not in record["tokens"]


def test_no_summary_bucket_when_no_summary_tokens():
    record = build_turn_record(make_state("memory_hit"), Settings())
    assert "summary_llm" not in record["tokens"]


def test_log_turn_offloads_the_blocking_write_off_the_event_loop(tmp_path):
    main_thread = threading.get_ident()
    seen = {}

    class ThreadCapturingLogger:
        def log(self, record: dict) -> None:
            seen["thread"] = threading.get_ident()

    log_turn = make_log_turn(Resources(ThreadCapturingLogger()))
    state = make_state("memory_hit", turn_started_at=time.perf_counter())
    asyncio.run(log_turn(state))
    # asyncio.to_thread runs the sync append on a worker thread, never the event-loop thread
    assert seen["thread"] != main_thread


def test_real_log_turn_writes_full_record(tmp_path):
    logger = TurnLogger(str(tmp_path / "turns.jsonl"))
    log_turn = make_log_turn(Resources(logger))
    state = make_state(
        "memory_miss_web_search",
        tokens={
            "answer_llm": {"model": "gpt-5.4-mini", "input_tokens": 2311, "output_tokens": 402}
        },
        latency_ms={"embed": 42, "answer_llm": 1420},
        turn_started_at=time.perf_counter(),
        search_provider="ddgs",
    )
    updates = asyncio.run(log_turn(state))
    record = read_lines(tmp_path / "turns.jsonl")[0]
    assert isinstance(record["latency_ms"]["total"], int)
    assert "classify" in record["latency_ms"]
    assert record["latency_ms"]["embed"] == 42  # reduced dicts merged, not clobbered
    assert record["tokens"]["answer_llm"] == {"model": "gpt-5.4-mini", "input": 2311, "output": 402}
    assert record["tokens"]["analytics_llm"] == {
        "model": "gpt-5.4-nano",
        "input": 198,
        "output": 36,
    }
    assert record["analytics"]["topic"] == "redis vector search"
    # the node's own updates feed the graph reducers too
    assert updates["analytics"] is VALID_CLF
    assert updates["tokens"]["analytics_llm"] == NANO_USAGE
