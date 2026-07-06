"""Print the compiled graph's mermaid diagram (keyless) — for the DoD grep + README.

Node factories only close over `resources`; compilation touches no client or key, so we
can build AgentResources with None clients and `Settings(_env_file=None)` (pinned defaults,
no .env). Verifies the M5 entry rewire: `__start__ --> guard_input` and the block edge
`guard_input -.-> log_turn`.
"""

from memagent.config import Settings
from memagent.graph import build_graph
from memagent.resources import AgentResources


def main() -> None:
    settings = Settings(_env_file=None)
    resources = AgentResources(
        settings=settings,
        memory=None,
        embedder=None,
        chat_llm=None,
        analytics_llm=None,
        searcher=None,
        fetcher=None,
        turn_logger=None,
    )
    print(build_graph(resources).get_graph().draw_mermaid())


if __name__ == "__main__":
    main()
