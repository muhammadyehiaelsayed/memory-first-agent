"""One compiled async StateGraph (Rulings B + F).

M2 wires the hit path. TEMPORARY seams (comment-marked):
- entry is embed_query (guard_input activates in M5 — Ruling F)
- route_after_memory's "web_search" key maps to answer_failure (M3 remaps to the real
  web_search node — this path-map line is the whole miss-branch seam)
- log_turn is a no-op stub (M4 replaces)
"""

from langgraph.graph import END, StateGraph

from memagent.nodes.answer import make_answer_failure, make_answer_from_memory
from memagent.nodes.embed import make_embed_query
from memagent.nodes.log import make_log_turn
from memagent.nodes.memory import make_memory_search
from memagent.resources import AgentResources
from memagent.routers import route_after_embed, route_after_memory
from memagent.state import AgentState


def build_graph(resources: AgentResources):
    sg = StateGraph(AgentState)
    sg.add_node("embed_query", make_embed_query(resources))
    sg.add_node("memory_search", make_memory_search(resources))
    sg.add_node("answer_from_memory", make_answer_from_memory(resources))
    sg.add_node("answer_failure", make_answer_failure(resources))
    sg.add_node("log_turn", make_log_turn(resources))  # no-op stub (M4 replaces)

    sg.set_entry_point("embed_query")  # guard_input activates in M5 (Ruling F)
    sg.add_conditional_edges(
        "embed_query",
        route_after_embed,
        {"memory_search": "memory_search", "answer_failure": "answer_failure"},
    )
    sg.add_conditional_edges(
        "memory_search",
        route_after_memory,
        {
            "answer_from_memory": "answer_from_memory",
            "web_search": "answer_failure",  # TEMPORARY miss->failure (M3 remaps this key)
        },
    )
    sg.add_edge("answer_from_memory", "log_turn")
    sg.add_edge("answer_failure", "log_turn")
    sg.add_edge("log_turn", END)
    return sg.compile()
