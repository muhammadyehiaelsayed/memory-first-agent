"""JSONL TurnLogger + build_turn_record (M4, verbatim PLAN section 8.2 schema).

logs/turns.jsonl is the turn log's SINGLE source of truth (Constitution P-IV): exactly one
appended JSON line per turn, no Redis mirror, analytics read these records only.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from memagent.config import Settings

# route values whose turns touched the web pipeline -> record a web block
_WEB_ROUTES = ("memory_miss_web_search", "degraded_web")


class TurnLogger:
    def __init__(self, path: str):
        self._path = Path(path)

    def log(self, record: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_turn_record(state: dict, settings: Settings) -> dict:
    query = state["query"]
    web = None
    if state.get("route") in _WEB_ROUTES:
        web = {
            "provider": state.get("search_provider"),
            "results_returned": len(state.get("search_results", [])),
            "pages_fetched": sum(1 for d in state.get("fetched_docs", []) if d.get("ok")),
            "chunks_ingested": len(state.get("chunks", [])),
        }
    tokens = {}
    for role in ("answer_llm", "analytics_llm"):
        usage = state.get("tokens", {}).get(role)
        if usage:
            tokens[role] = {
                "model": usage["model"],
                "input": usage["input_tokens"],
                "output": usage["output_tokens"],
            }
    analytics = state.get("analytics")
    return {
        "turn_id": state["turn_id"],
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "session_id": state["session_id"],
        "query": query,
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest()[:16],
        "route": state["route"],
        "degradation": state.get("degradation"),
        "similarity_top": state.get("top_similarity"),
        "similarity_threshold": state.get("threshold", settings.similarity_threshold),
        "web": web,
        "sources": list(state.get("sources", [])),
        "latency_ms": dict(state.get("latency_ms", {})),
        "tokens": tokens,
        "guardrail": {
            "verdict": state.get("guard_verdict", "allow"),
            "events": list(state.get("guardrail_events", [])),
        },
        "errors": [dict(e) for e in state.get("errors", [])],
        "analytics": analytics.model_dump() if analytics is not None else None,
    }
