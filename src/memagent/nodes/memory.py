"""memory_search node: raw KNN lookup. NO threshold logic here (routers own that)."""

from memagent.resources import AgentResources


def make_memory_search(resources: AgentResources):
    async def memory_search(state: dict) -> dict:
        hits = await resources.memory.knn(
            state["query_vector"], resources.settings.memory_top_k
        )
        return {
            "memory_hits": hits,
            "top_similarity": hits[0]["similarity"] if hits else None,
        }

    return memory_search
