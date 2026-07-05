"""web_search node: provider search + provider bookkeeping (feeds TurnRecord.web in M4)."""

import time

from memagent.resources import AgentResources


def make_web_search(resources: AgentResources):
    async def web_search(state: dict) -> dict:
        started = time.perf_counter()
        try:
            results = await resources.searcher.search(
                state["sanitized_query"], resources.settings.search_max_results
            )
            update: dict = {"search_results": results}
        except Exception as exc:  # noqa: BLE001 — empty results route to answer_failure
            update = {
                "search_results": [],
                "errors": [
                    {
                        "node": "web_search",
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:200],
                    }
                ],
            }
        update["search_provider"] = getattr(resources.searcher, "provider_used", None)
        update["latency_ms"] = {"web_search": int((time.perf_counter() - started) * 1000)}
        return update

    return web_search
