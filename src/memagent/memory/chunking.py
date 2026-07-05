"""Markdown-aware chunking (PLAN section 4.4): 1600 chars / 200 overlap, floor 100, cap 25."""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from memagent.config import Settings

_MIN_CHUNK_CHARS = 100

_MARKDOWN_SEPARATORS = ["\n# ", "\n## ", "\n### ", "\n#### ", "\n\n", "\n", ". ", " ", ""]


def chunk_markdown(text: str, settings: Settings | None = None) -> list[str]:
    settings = settings or Settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size_chars,
        chunk_overlap=settings.chunk_overlap_chars,
        separators=_MARKDOWN_SEPARATORS,
    )
    chunks = [c.strip() for c in splitter.split_text(text)]
    chunks = [c for c in chunks if len(c) >= _MIN_CHUNK_CHARS]
    return chunks[: settings.max_chunks_per_page]
