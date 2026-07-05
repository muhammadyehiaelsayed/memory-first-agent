"""M2-owned: memory-layer pure-helper tests (chunking + urls) — FR-M2-14/15.

Hosts the URL canonicalisation scenarios per specs/002 analysis C1 (no fourth
test file; Ruling A file list intact).
"""

import pytest

from memagent.config import Settings
from memagent.memory.chunking import chunk_markdown
from memagent.memory.urls import canonicalize, url_hash

SETTINGS = Settings()


def test_chunk_size_and_overlap_bounds():
    text = "\n\n".join(f"Paragraph {i}: " + ("lorem ipsum dolor sit amet " * 12) for i in range(30))
    chunks = chunk_markdown(text, SETTINGS)
    assert chunks
    assert all(len(c) <= SETTINGS.chunk_size_chars for c in chunks)


def test_chunks_below_floor_are_dropped():
    chunks = chunk_markdown("short.", SETTINGS)
    assert chunks == []
    assert all(len(c) >= 100 for c in chunk_markdown("x" * 5000, SETTINGS))


def test_chunk_cap_is_enforced():
    huge = "\n\n".join("Section content " * 40 for _ in range(200))
    assert len(chunk_markdown(huge, SETTINGS)) <= SETTINGS.max_chunks_per_page == 25


def test_no_empty_chunks():
    text = ("word " * 100 + "\n\n\n\n") * 10
    assert all(c.strip() for c in chunk_markdown(text, SETTINGS))


def test_unicode_survives():
    text = ("Redis معلومات عن البحث الشعاعي 向量搜索 émbeddings çöğüş " * 8 + "\n\n") * 5
    chunks = chunk_markdown(text, SETTINGS)
    assert chunks
    assert any("向量搜索" in c for c in chunks)
    assert any("معلومات" in c for c in chunks)


def test_short_document_yields_at_most_one_chunk():
    text = "A single meaningful paragraph about Redis vector search internals, long enough to keep."
    assert len(chunk_markdown(text, SETTINGS)) <= 1


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("HTTP://Example.com/a?utm_source=x#frag", "http://example.com/a"),
        ("http://example.com/a", "http://example.com/a"),
        ("https://Foo.COM/p?utm_medium=e&id=7", "https://foo.com/p?id=7"),
    ],
)
def test_canonicalize_table(raw, canonical):
    assert canonicalize(raw) == canonical


def test_variant_spellings_hash_identically():
    a = url_hash("HTTP://Example.com/a?utm_source=x#frag")
    b = url_hash("http://example.com/a")
    assert a == b
    assert len(a) == 16
    assert all(ch in "0123456789abcdef" for ch in a)
