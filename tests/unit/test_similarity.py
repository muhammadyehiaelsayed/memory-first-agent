"""M2-owned: the ONE distance->similarity conversion site (FR-M2-06/07).

Float32 epsilon decision (recorded once, per PLAN section 4.3 / specs/002 research D8):
the router comparison stays exactly `sim >= threshold`. A float32-noise value like
0.699999988 therefore routes as a MISS under the default. If and only if the boundary
test below ever proves flaky against real Redis, switch route_after_memory to
`sim >= threshold - 1e-6` and update this comment.
"""

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
    # Behavioural, not source-text: the discredited half-distance formula (1 - d/2) would map
    # distance 0.4 -> 0.8; the correct cosine identity (1 - d) maps it to 0.6.
    assert distance_to_similarity(0.4) == 0.6
    assert distance_to_similarity(0.4) != 0.8


def test_conversion_extremes():
    assert distance_to_similarity(0.0) == 1.0
    assert distance_to_similarity(1.0) == 0.0
