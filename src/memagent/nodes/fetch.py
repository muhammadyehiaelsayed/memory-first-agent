"""fetch_pages node: filter URLs -> take top-N -> bounded concurrent fetch."""

from memagent.resources import AgentResources
from memagent.web.fetch import filter_urls


def make_fetch_pages(resources: AgentResources):
    async def fetch_pages(state: dict) -> dict:
        try:
            urls = filter_urls(
                [r["url"] for r in state["search_results"]], resources.settings
            )
            docs = await resources.fetcher.fetch(urls[: resources.settings.fetch_top_n])
            update: dict = {"fetched_docs": docs}
        except Exception as exc:  # noqa: BLE001 — empty docs degrade to the snippets-only answer
            update = {
                "fetched_docs": [],
                "errors": [
                    {
                        "node": "fetch_pages",
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:200],
                    }
                ],
            }
        return update

    return fetch_pages
