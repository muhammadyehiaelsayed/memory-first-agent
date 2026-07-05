"""M2-owned: the ONE distance->similarity conversion site (FR-M2-06/07).

Float32 epsilon decision (recorded once, per PLAN section 4.3 / specs/002 research D8):
the router comparison stays exactly `sim >= threshold`. A float32-noise value like
0.699999988 therefore routes as a MISS under the default. If and only if the boundary
test below ever proves flaky against real Redis, switch route_after_memory to
`sim >= threshold - 1e-6` and update this comment.
"""

import inspect

from memagent.memory import store as store_module
from memagent.memory.store import distance_to_similarity
from memagent.routers import route_after_memory


def test_distance_030_converts_to_similarity_070():
    assert abs(distance_to_similarity(0.30) - 0.70) < 1e-12


def test_distance_030_routes_as_inclusive_hit():
    sim = distance_to_similarity(0.30)
    assert route_after_memory({"top_similarity": sim, "threshold": 0.70}) == "answer_from_memory"


def test_float32_noise_boundary_documented_decision():
    noisy = 0.699999988  # a true 0.70 read back through float32 storage
    assert route_after_memory({"top_similarity": noisy, "threshold": 0.70}) == "web_search"


def test_l2_halved_formula_is_not_used():
    source = inspect.getsource(store_module.distance_to_similarity)
    assert "/ 2" not in source and "/2" not in source
    assert "1.0 - distance" in source


def test_conversion_extremes():
    assert distance_to_similarity(0.0) == 1.0
    assert distance_to_similarity(1.0) == 0.0
