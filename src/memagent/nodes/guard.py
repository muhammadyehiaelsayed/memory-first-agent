"""guard_input node (M5): L1 screen at the graph entry (Ruling F).

Writes guard_verdict / sanitized_query / guardrail_events; on block also writes the canned
refusal into `answer` (no answer node runs on the block path — guard -> log_turn -> END, so
this is the ONLY place the user-facing refusal can be set, PLAN §7.1) and `route="blocked"`;
on flag also `skip_store=True`. Fails OPEN: if screen_input raises, allow the query and
record "fail_open" (availability over strictness for a single-user tool). Never re-raises.
"""

import structlog

from memagent.resources import AgentResources
from memagent.security.guardrails import screen_input

BLOCKED_REFUSAL = "I can't help with that request."

logger = structlog.get_logger(__name__)


def make_guard_input(resources: AgentResources):
    async def guard_input(state: dict) -> dict:
        try:
            result = screen_input(state["query"], resources.settings)
        except Exception as exc:  # noqa: BLE001 — fail OPEN: a broken guard must not deny all service
            logger.warning("guard_fail_open", error=type(exc).__name__, detail=str(exc)[:200])
            return {
                "guard_verdict": "allow",
                "sanitized_query": state["query"],
                "guardrail_events": ["fail_open"],
            }
        update: dict = {
            "guard_verdict": result.verdict,
            "sanitized_query": result.sanitized_query,
            "guardrail_events": result.events,
        }
        if result.verdict == "block":
            update["route"] = "blocked"
            update["answer"] = BLOCKED_REFUSAL
            update["sources"] = []
        elif result.verdict == "flag":
            update["skip_store"] = True
        return update

    return guard_input
