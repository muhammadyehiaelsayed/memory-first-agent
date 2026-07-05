"""One compiled async StateGraph (Rulings B + F).

M2 wired the hit path; M3 wired the real miss branch (web_search -> fetch_pages ->
ingest_content -> answer_from_web); M4 wired the real log_turn (TurnRecord JSONL) and
per-stage timed() instrumentation. REMAINING TEMPORARY seam (comment-marked):
- entry is embed_query (guard_input activates in M5 — Ruling F)
"""

from langgraph.graph import END, StateGraph

from memagent.nodes.answer import (
    make_answer_failure,
    make_answer_from_memory,
    make_answer_from_web,
)
from memagent.nodes.embed import make_embed_query
from memagent.nodes.fetch import make_fetch_pages
from memagent.nodes.ingest import make_ingest_content
from memagent.nodes.log import make_log_turn
from memagent.nodes.memory import make_memory_search
from memagent.nodes.search import make_web_search
from memagent.resources import AgentResources
from memagent.routers import (
    route_after_embed,
    route_after_fetch,
    route_after_memory,
    route_after_search,
)
from memagent.state import AgentState
from memagent.utils.timing import timed


def build_graph(resources: AgentResources):
    sg = StateGraph(AgentState)
    # timed() is the single stage-latency owner (PLAN section 8.2 stage names);
    # log_turn stays unwrapped — it measures classify/total itself, pre-write.
    sg.add_node("embed_query", timed("embed", make_embed_query(resources)))
    sg.add_node("memory_search", timed("vector_search", make_memory_search(resources)))
    sg.add_node("answer_from_memory", timed("answer_llm", make_answer_from_memory(resources)))
    sg.add_node("web_search", timed("web_search", make_web_search(resources)))
    sg.add_node("fetch_pages", timed("fetch", make_fetch_pages(resources)))
    sg.add_node("ingest_content", timed("ingest", make_ingest_content(resources)))
    sg.add_node("answer_from_web", timed("answer_llm", make_answer_from_web(resources)))
    sg.add_node("answer_failure", timed("answer_failure", make_answer_failure(resources)))
    sg.add_node("log_turn", make_log_turn(resources))

    sg.set_entry_point("embed_query")  # guard_input activates in M5 (Ruling F)
    sg.add_conditional_edges(
        "embed_query",
        route_after_embed,
        {"memory_search": "memory_search", "answer_failure": "answer_failure"},
    )
    sg.add_conditional_edges(
        "memory_search",
        route_after_memory,
        {"answer_from_memory": "answer_from_memory", "web_search": "web_search"},
    )
    sg.add_conditional_edges(
        "web_search",
        route_after_search,
        {"fetch_pages": "fetch_pages", "answer_failure": "answer_failure"},
    )
    sg.add_conditional_edges(
        "fetch_pages",
        route_after_fetch,
        {"ingest_content": "ingest_content", "answer_from_web": "answer_from_web"},
    )
    sg.add_edge("ingest_content", "answer_from_web")
    sg.add_edge("answer_from_memory", "log_turn")
    sg.add_edge("answer_from_web", "log_turn")
    sg.add_edge("answer_failure", "log_turn")
    sg.add_edge("log_turn", END)
    return sg.compile()
