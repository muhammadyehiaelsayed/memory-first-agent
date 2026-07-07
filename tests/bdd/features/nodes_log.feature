# Module: src/memagent/nodes/log.py
# Derived from: 00_main_functionality.feature :: "Log exactly one analytics record for every turn"
# Spec sources: milestone-4-llms-logging-analytics.md
# Executable binding: tests/bdd/test_bdd_analytics.py
Feature: Per-turn analytics logging node (src/memagent/nodes/log.py)
  The log-turn node is the last node on every route. It classifies the query,
  measures its own classify latency and the turn's total wall-clock, merges the
  reduced token/latency channels, builds the turn record, and appends exactly
  one JSONL line — realising the root "one analytics record per turn" invariant.
  It must never raise, so a classification or write failure is swallowed and the
  turn the user already saw is preserved.

  # source: milestone-4-llms-logging-analytics.md :: the real log_turn node builds and writes a full record
  # covers: memagent.nodes.log.make_log_turn
  Scenario: A completed turn is classified, timed, and written as one full record
    Given a completed web-search turn carrying answer tokens and a working turn logger
    When the log-turn node runs
    Then exactly one record is appended carrying total latency, the classify stage, the merged answer tokens, and the classification

  # source: milestone-4-llms-logging-analytics.md :: a blocked turn is still logged
  # covers: memagent.nodes.log.make_log_turn
  Scenario: A blocked turn is still recorded in the turn log
    Given a completed blocked turn and a working turn logger
    When the log-turn node runs
    Then the recorded turn names the "blocked" route with a block verdict

  # source: milestone-4-llms-logging-analytics.md :: log_turn never raises when the logger fails
  # covers: memagent.nodes.log.make_log_turn
  Scenario: A failing turn logger never crashes the turn
    Given a log-turn node whose logger raises on every write
    When the log-turn node runs
    Then the node returns its classification updates without propagating the failure
