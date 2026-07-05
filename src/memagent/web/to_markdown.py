"""trafilatura HTML->markdown (M3): precision-first extract with gated output.

include_links=False drops inline links; raw-content shortcuts stay off upstream —
the fetch+markdown step is graded in-house work (PLAN section 5.1/5.3).
"""

import trafilatura

MIN_MARKDOWN_CHARS = 200      # reject cookie-wall / JS-shell pages
MAX_MARKDOWN_CHARS = 20_000   # cap token cost on huge articles


def to_markdown(html: str) -> str | None:
    md = trafilatura.extract(
        html, output_format="markdown", include_tables=True,
        include_links=False, favor_precision=True,
    )
    if not md:
        md = trafilatura.extract(
            html, output_format="markdown", include_tables=True,
            include_links=False, favor_recall=True,
        )
    if not md or len(md) < MIN_MARKDOWN_CHARS:
        return None
    return md[:MAX_MARKDOWN_CHARS]
