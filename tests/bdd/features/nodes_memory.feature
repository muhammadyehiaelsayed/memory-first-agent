# Module: src/memagent/nodes/memory.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-2-memory-path.md
# Executable binding: tests/bdd/test_bdd_nodes_memory_path.py
Feature: Search Redis vector memory first (src/memagent/nodes/memory.py)
  The memory_search node performs the raw KNN lookup that feeds the deterministic
  hit/miss branch behind the root "Answer from memory" scenario. It holds NO
  threshold logic (that lives in the routers): it returns the raw top-k with
  similarity attached and surfaces the highest similarity as top_similarity.
  A Redis outage is caught and degraded to a miss labelled redis_down rather
  than crashing the turn.

  # source: milestone-2-memory-path.md :: "memory_search does not filter by threshold"
  # covers: memagent.nodes.memory.make_memory_search
  Scenario: The raw top-k is returned unfiltered with the highest similarity surfaced
    Given a memory store that returns five hits with similarities 0.9, 0.8, 0.5, 0.4, 0.2
    When the memory_search node runs
    Then all five hits are kept in state
    And top_similarity equals 0.9
    And knn was called exactly once with k equal to MEMORY_TOP_K

  # source: milestone-2-memory-path.md :: "an empty index yields no hits and a None top_similarity"
  # covers: memagent.nodes.memory.make_memory_search
  Scenario: An empty memory index is a normal miss, not an error
    Given a memory store with an empty index
    When the memory_search node runs
    Then no memory hits are returned
    And top_similarity is None

  # covers: memagent.nodes.memory.make_memory_search
  Scenario: A Redis outage degrades to a miss labelled redis_down
    Given a memory store whose Redis backend is unreachable
    When the memory_search node runs
    Then no memory hits are returned
    And the turn is marked to skip storing with degradation "redis_down"
    And a step error is recorded for the "memory_search" node
