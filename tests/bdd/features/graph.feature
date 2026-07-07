# Module: src/memagent/graph.py
# Derived from: 00_main_functionality.feature :: "Block malicious input at the guard before any model call"
# Spec sources: milestone-5-security-reliability.md, code-derived
# Executable binding: tests/bdd/test_bdd_orchestration.py
Feature: The compiled StateGraph wires the memory-first pipeline (src/memagent/graph.py)
  build_graph assembles the one compiled async StateGraph that every turn flows
  through. Its entry point is the L1 guard (so a malicious input can short-circuit
  straight to logging without any model call), and its conditional edges encode
  the memory-first order: guard -> embed -> memory_search, then the deterministic
  branch to answer_from_memory (hit) or web_search (miss) -> fetch -> ingest ->
  answer_from_web, with every terminal node draining into log_turn. Compilation is
  keyless: the node factories only close over resources, so the graph structure is
  observable without any live client.

  # source: milestone-5-security-reliability.md :: Graph entry is guard_input (FR-M5-07)
  # covers: memagent.graph.build_graph
  Scenario: The graph screens input at the entry and can short-circuit a block to logging
    Given the graph is compiled from keyless resources
    When its structure is rendered as a mermaid diagram
    Then the entry edge goes from start into "guard_input"
    And the guard can route directly to "log_turn"
    And the guard can also route onward to "embed_query"

  # covers: memagent.graph.build_graph
  Scenario: The graph searches memory before the web and drains every path into logging
    Given the graph is compiled from keyless resources
    When its structure is inspected
    Then it contains the memory-first nodes guard_input, embed_query, memory_search and log_turn
    And memory_search can branch to either "answer_from_memory" or "web_search"
    And answer_from_memory, answer_from_web and answer_failure all lead to "log_turn"
    And log_turn is the final node before the graph ends
