"""Render the compiled graph's mermaid diagram (keyless) and splice it into the docs.

Node factories only close over `resources`; compilation touches no client or key, so we build
AgentResources with None clients and `Settings(_env_file=None)` (pinned defaults, no .env) — the
render stays keyless AND redis-less (do NOT route it through build_test_resources, D2). Prints
the mermaid to stdout (DoD grep) and splices it between stable markers in README.md and
docs/architecture.md. Idempotent: re-running reproduces byte-identical between-marker content.
"""

from pathlib import Path

from memagent.config import Settings
from memagent.graph import build_graph
from memagent.resources import AgentResources

BEGIN = "<!-- BEGIN graph -->"
END = "<!-- END graph -->"


def render_mermaid() -> str:
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
    return build_graph(resources).get_graph().draw_mermaid()


def splice(path: Path, mermaid: str, *, title: str) -> None:
    """Replace the content between BEGIN/END markers with the mermaid block (create if absent)."""
    block = f"{BEGIN}\n\n```mermaid\n{mermaid.rstrip()}\n```\n\n{END}"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n{block}\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        pre, post = text[: text.index(BEGIN)], text[text.index(END) + len(END) :]
        text = pre + block + post
    else:  # no markers yet -> append an Architecture section
        text = f"{text.rstrip()}\n\n## Architecture\n\n{block}\n"
    path.write_text(text, encoding="utf-8")


def main() -> None:
    mermaid = render_mermaid()
    print(mermaid)  # stdout for the DoD grep + M5 behaviour
    splice(Path("README.md"), mermaid, title="Memory-First Web Agent")
    splice(Path("docs/architecture.md"), mermaid, title="Architecture")


if __name__ == "__main__":
    main()
