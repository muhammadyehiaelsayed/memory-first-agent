"""timed() stage-latency wrapper (FR-M4-22), untested before M7.

The single stage-latency owner merges a {stage: ms} entry into whatever latency_ms the wrapped
node returned — never clobbering a node-supplied entry — and tolerates a node returning None.
"""

import asyncio

from memagent.utils.timing import timed


def _run(coro):
    return asyncio.run(coro)


def test_timed_adds_integer_stage_latency():
    async def node(state):
        return {"foo": 1}

    out = _run(timed("embed", node)({}))
    assert out["foo"] == 1
    assert isinstance(out["latency_ms"]["embed"], int)


def test_timed_merges_without_clobbering_node_latency():
    async def node(state):
        return {"latency_ms": {"inner": 5}}

    out = _run(timed("embed", node)({}))
    assert out["latency_ms"]["inner"] == 5  # node-returned entry preserved
    assert isinstance(out["latency_ms"]["embed"], int)  # wrapper stage added alongside


def test_timed_tolerates_node_returning_none():
    async def node(state):
        return None

    out = _run(timed("embed", node)({}))
    assert set(out["latency_ms"]) == {"embed"}  # no crash; just the stage entry
