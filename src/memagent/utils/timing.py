"""timed() node wrapper -> state.latency_ms (M4).

The SINGLE stage-latency owner (Constitution P-III): nodes do not self-measure. The
wrapper merges into any latency_ms the wrapped node returned rather than replacing it,
so a node-returned entry can never be silently clobbered. log_turn is NOT wrapped — it
measures its own classify/total internally because the TurnRecord is written inside the
node, before any wrapper or reducer runs.
"""

import time


def timed(stage: str, fn):
    async def wrapped(state: dict) -> dict:
        t0 = time.perf_counter()
        out = await fn(state) or {}
        dt = int((time.perf_counter() - t0) * 1000)
        return {**out, "latency_ms": {**out.get("latency_ms", {}), stage: dt}}

    return wrapped
