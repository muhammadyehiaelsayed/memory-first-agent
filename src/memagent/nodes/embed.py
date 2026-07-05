"""embed_query node: embed the sanitized query; on failure, route to answer_failure."""

from memagent.resources import AgentResources


def make_embed_query(resources: AgentResources):
    async def embed_query(state: dict) -> dict:
        try:
            vectors = await resources.embedder.embed([state["sanitized_query"]])
            return {"query_vector": vectors[0]}
        except Exception as exc:  # noqa: BLE001 — node owns degradation; retries are M5's
            return {
                "query_vector": None,
                "errors": [
                    {
                        "node": "embed_query",
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:200],
                    }
                ],
            }

    return embed_query
