"""trafilatura HTML->markdown (M3): precision-first extract with gated output.

include_links=False drops inline links; raw-content shortcuts stay off upstream —
the fetch+markdown step is graded in-house work (PLAN section 5.1/5.3). The min-length
floor (reject cookie-wall / JS-shell pages) and max-length cap (bound token cost on huge
articles) are Settings fields: min_markdown_chars / max_markdown_chars.
"""

import trafilatura

from memagent.config import Settings


def to_markdown(html: str, settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    md = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_links=False,
        favor_precision=True,
    )
    if not md:
        md = trafilatura.extract(
            html,
            output_format="markdown",
            include_tables=True,
            include_links=False,
            favor_recall=True,
        )
    if not md or len(md) < settings.min_markdown_chars:
        return None
    return md[: settings.max_markdown_chars]
