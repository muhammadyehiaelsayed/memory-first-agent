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


def test_overlap_duplicates_boundary_content_between_chunks():
    # A long space-separated run forces multi-chunk splitting: overlap=200 makes the tail of a
    # chunk reappear at the head of the next; overlap=0 does not. (The size-bound test above holds
    # identically with overlap=0, so it never actually exercised the overlap invariant.)
    big = "token000 " + " ".join(f"token{i:03d}" for i in range(1, 900))
    overlapped = chunk_markdown(big, SETTINGS)
    none = chunk_markdown(big, Settings(chunk_overlap_chars=0))
    assert len(overlapped) >= 2
    assert overlapped[0][-60:] in overlapped[1]  # overlap present with the 200-char setting
    assert none[0][-60:] not in none[1]  # ... and absent when overlap is 0
    assert sum(len(c) for c in overlapped) > sum(len(c) for c in none)  # overlap duplicates text


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


def test_short_document_yields_exactly_one_chunk_equal_to_input():
    # >= the 100-char floor but < chunk_size: a valid short doc must survive as ONE chunk equal
    # to its input. (The prior 87-char input fell below the floor -> [] -> a vacuous `<= 1`.)
    text = (
        "A single meaningful paragraph about Redis vector search internals, kept whole "
        "because it exceeds the hundred character floor."
    )
    assert chunk_markdown(text, SETTINGS) == [text]


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
