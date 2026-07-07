# Module: src/memagent/state.py
# Derived from: 00_main_functionality.feature :: "Log exactly one analytics record for every turn"
# Spec sources: milestone-1-scaffold-and-memory-schema.md, code-derived (state.py channel reducers)
# Executable binding: tests/bdd/test_bdd_contracts.py
Feature: Per-turn state channels merge node contributions for the turn log (src/memagent/state.py)
  The root logging invariant records one analytics line per turn, and that record's
  latency_ms and tokens maps are accumulated across nodes through the AgentState
  reducer declared here. _merge_dicts is the reducer wired onto both Annotated
  channels, so this scenario pins the exact merge semantics the turn record depends
  on: contributions from different nodes combine, and a single-writer key overrides
  the earlier value without mutating the inputs.

  # covers: memagent.state._merge_dicts
  Scenario: Per-node latency and token contributions accumulate into one turn map
    Given a turn that has recorded latency for the embed node
    And a later node records latency for the answer model
    When the two latency contributions are merged by the state reducer
    Then the merged map contains both nodes' timings
    And a later write to the same node key overrides the earlier value
    And merging leaves the original contribution maps unmodified
