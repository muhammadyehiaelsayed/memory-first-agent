"""The five pure routing functions (verbatim PLAN section 3.3).

Pure functions of state — no I/O, deterministic. These bodies NEVER change; later
milestones only remap graph path-map keys (M3: "web_search" -> real node; M5 wires
route_after_guard). The hit/miss decision lives here, in code — never in a model
(Constitution P-I). Comparison is exactly `>= threshold` (inclusive); the epsilon
variant (threshold - 1e-6) is adopted ONLY if the boundary test proves flaky.
"""


def route_after_guard(s):
    return "log_turn" if s["guard_verdict"] == "block" else "embed_query"


def route_after_embed(s):
    return "memory_search" if s.get("query_vector") else "answer_failure"


def route_after_memory(s):
    sim = s.get("top_similarity")
    return "answer_from_memory" if sim is not None and sim >= s["threshold"] else "web_search"


def route_after_search(s):
    return "fetch_pages" if s["search_results"] else "answer_failure"


def route_after_fetch(s):
    return "ingest_content" if s["fetched_docs"] else "answer_from_web"
