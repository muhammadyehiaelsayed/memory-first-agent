"""memory_search node: raw KNN lookup. NO threshold logic here (routers own that).

Catches ONLY MemoryUnavailableError (redis exhausted its retries) → treats it as a miss,
sets skip_store + degradation="redis_down" so answer_from_web records degraded_web (D8).
Everything else (incl. redis ResponseError, a programming bug) propagates.
"""

from memagent.resources import AgentResources
from memagent.utils.errors import MemoryUnavailableError


def make_memory_search(resources: AgentResources):
    async def memory_search(state: dict) -> dict:
        try:
            hits = await resources.memory.knn(
                state["query_vector"], resources.settings.memory_top_k
            )
        except MemoryUnavailableError as exc:
            return {
                "memory_hits": [],
                "top_similarity": None,
                "skip_store": True,
                "degradation": "redis_down",
                "errors": [
                    {
                        "node": "memory_search",
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:200],
                    }
                ],
            }
        return {
            "memory_hits": hits,
            "top_similarity": hits[0]["similarity"] if hits else None,
        }

    return memory_search
