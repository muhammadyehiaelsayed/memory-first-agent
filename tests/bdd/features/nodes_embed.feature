# Module: src/memagent/nodes/embed.py
# Derived from: 00_main_functionality.feature :: "Report failure when the query cannot be embedded"
# Spec sources: milestone-2-memory-path.md
# Executable binding: tests/bdd/test_bdd_nodes_memory_path.py
Feature: Embed the query for a memory-first lookup (src/memagent/nodes/embed.py)
  The embed_query node is the gateway of the memory-first path: it turns the
  sanitized query into a vector so memory_search can look it up. It owns its own
  degradation — an embedding failure does not raise; it clears the vector and
  records a StepError so route_after_embed sends the turn to answer_failure,
  which is exactly the root "Report failure when the query cannot be embedded"
  branch.

  # source: milestone-2-memory-path.md :: "a successful embedding populates the query vector"
  # covers: memagent.nodes.embed.make_embed_query
  Scenario: A successful embedding populates the query vector
    Given a sanitized query and a working embedding service
    When the embed_query node runs
    Then the query vector has 1536 dimensions
    And no step error is recorded

  # source: milestone-2-memory-path.md :: "an embedding failure clears the vector and records an error"
  # covers: memagent.nodes.embed.make_embed_query
  Scenario: An embedding failure clears the vector and records a step error
    Given a sanitized query but the embedding service is unavailable
    When the embed_query node runs
    Then the query vector is cleared to None
    And a step error is recorded for the "embed_query" node
