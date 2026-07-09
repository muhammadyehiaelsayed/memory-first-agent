"""log_turn — the real node (M4, Ruling B): classify -> build record -> append JSONL.

log_turn NEVER raises (PLAN section 3.2): it is the last node on every path, and an
exception here would lose the turn's graded artifact AND crash a turn whose answer the
user already saw. It measures its OWN classify latency and computes latency_ms.total
here, because the LangGraph reducer and any outer timed() wrapper run only AFTER this
node returns — i.e. after the record has already been written.
"""

import asyncio
import time

import structlog

from memagent.analytics.classify import classify
from memagent.analytics.turnlog import build_turn_record

logger = structlog.get_logger(__name__)


def make_log_turn(resources):
    async def log_turn(state: dict) -> dict:
        updates: dict = {}
        try:
            t0 = time.perf_counter()
            clf, usage = await classify(
                resources.analytics_llm, state["query"], resources.settings.classify_timeout_s
            )
            classify_ms = int((time.perf_counter() - t0) * 1000)
            updates["analytics"] = clf
            if usage:
                updates["tokens"] = {"analytics_llm": usage}
            latency = {"classify": classify_ms}
            started = state.get("turn_started_at")
            if started is not None:
                latency["total"] = int((time.perf_counter() - started) * 1000)
            updates["latency_ms"] = latency
            # Build the record from MERGED-reduced dicts, never a shallow overwrite: the
            # answer node already put answer_llm into state's tokens/latency_ms channels,
            # and {**state, **updates} would clobber those whole dicts (FR-M4-22).
            merged = {
                **state,
                **updates,
                "tokens": {**state.get("tokens", {}), **updates.get("tokens", {})},
                "latency_ms": {**state.get("latency_ms", {}), **latency},
            }
            record = build_turn_record(merged, resources.settings)
            # Cost flows back into state so a LangSmith trace (opt-in) shows the turn's
            # USD cost on this node's outputs and on the root run — same figure as JSONL.
            updates["cost_usd"] = record["cost_usd"]
            # TurnLogger.log does a synchronous file append; offload it so the blocking write
            # never stalls the event loop (matters once the graph is driven concurrently).
            await asyncio.to_thread(resources.turn_logger.log, record)
        except Exception as exc:  # noqa: BLE001 — never raises (FR-M4-11)
            logger.error("log_turn_failed", error=type(exc).__name__, detail=str(exc))
        return updates

    return log_turn
