"""M2-owned: the five pure routers + the inclusive 0.70 boundary table (FR-M2-05/06)."""

import pytest

from memagent.routers import (
    route_after_embed,
    route_after_fetch,
    route_after_guard,
    route_after_memory,
    route_after_search,
)


@pytest.mark.parametrize(
    ("top_similarity", "expected"),
    [
        (0.70, "answer_from_memory"),   # exactly at threshold -> hit (INCLUSIVE)
        (0.6999, "web_search"),         # just below -> miss
        (None, "web_search"),           # empty index -> miss, never an error
        (1.0, "answer_from_memory"),
        (0.0, "web_search"),
    ],
)
def test_route_after_memory_boundary(top_similarity, expected):
    state = {"top_similarity": top_similarity, "threshold": 0.70}
    assert route_after_memory(state) == expected


def test_route_after_embed():
    assert route_after_embed({"query_vector": [0.1] * 1536}) == "memory_search"
    assert route_after_embed({"query_vector": None}) == "answer_failure"
    assert route_after_embed({}) == "answer_failure"


def test_route_after_guard():
    assert route_after_guard({"guard_verdict": "block"}) == "log_turn"
    assert route_after_guard({"guard_verdict": "allow"}) == "embed_query"
    assert route_after_guard({"guard_verdict": "flag"}) == "embed_query"


def test_route_after_search():
    assert route_after_search({"search_results": [{"url": "u"}]}) == "fetch_pages"
    assert route_after_search({"search_results": []}) == "answer_failure"


def test_route_after_fetch():
    assert route_after_fetch({"fetched_docs": [{"url": "u"}]}) == "ingest_content"
    assert route_after_fetch({"fetched_docs": []}) == "answer_from_web"


def test_routers_are_pure():
    state = {"top_similarity": 0.9, "threshold": 0.7}
    frozen = dict(state)
    assert route_after_memory(state) == route_after_memory(state)
    assert state == frozen  # no mutation, no I/O side effects observable
