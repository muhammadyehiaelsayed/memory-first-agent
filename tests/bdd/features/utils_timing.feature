# Module: src/memagent/utils/timing.py
# Derived from: 00_main_functionality.feature :: "Log exactly one analytics record for every turn"
# Spec sources: code-derived from src/memagent/utils/timing.py docstring (FR-M4-22); milestone-5-security-reliability.md
# Executable binding: tests/bdd/test_bdd_utils.py
Feature: The stage-latency wrapper records per-stage timings for the turn record (src/memagent/utils/timing.py)
  Every logged turn carries a latency_ms breakdown. timed() is the single stage-latency
  owner: nodes never self-measure. It wraps an async node, measures the wall-clock
  milliseconds spent in its stage, and merges that entry into whatever latency_ms the node
  itself returned so a node-supplied timing is never silently clobbered — and it tolerates a
  node that returns None.

  # covers: memagent.utils.timing.timed
  Scenario: A stage timing is measured and merged without clobbering node-supplied timings
    Given an async node that returns its own inner latency entry
    When it is wrapped by timed for the "embed" stage and awaited
    Then the returned state keeps the node's own inner latency entry
    And the wrapper adds an integer millisecond timing for the "embed" stage
    And a node that returns None still yields only the "embed" stage timing
