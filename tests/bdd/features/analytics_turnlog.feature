# Module: src/memagent/analytics/turnlog.py
# Derived from: 00_main_functionality.feature :: "Log exactly one analytics record for every turn"
# Spec sources: milestone-4-llms-logging-analytics.md
# Executable binding: tests/bdd/test_bdd_analytics.py
Feature: Turn record schema and JSONL writer (src/memagent/analytics/turnlog.py)
  logs/turns.jsonl is the single source of truth for analytics: exactly one
  appended JSON line per turn, no Redis mirror. TurnLogger owns the append (and
  creates the parent directory), while build_turn_record maps the reduced agent
  state onto the fixed turn-record schema — the concrete shape behind the root
  "one analytics record per turn" invariant.

  # source: milestone-4-llms-logging-analytics.md :: exactly one record per turn is appended
  # covers: memagent.analytics.turnlog.TurnLogger.__init__, memagent.analytics.turnlog.TurnLogger.log
  Scenario: The writer appends exactly one JSON line per record and creates missing directories
    Given a turn logger pointed at a not-yet-existing logs directory
    When three turn records are written
    Then the log file holds exactly three JSON lines and every line parses as JSON

  # source: milestone-4-llms-logging-analytics.md :: memory-hit record has no web block
  # covers: memagent.analytics.turnlog.build_turn_record
  Scenario: A memory-hit record carries every schema field and no web block
    Given a memory-hit turn state
    When the turn record is built
    Then the record has the full turn-record schema, a null web block, and the default 0.70 threshold

  # covers: memagent.analytics.turnlog.build_turn_record
  Scenario: A web-route record reports provider, results, fetched pages, and only persisted chunks
    Given a web-search turn state with five results, three fetched pages, and twelve persisted chunk ids
    When the turn record is built
    Then the web block reports provider "tavily", five results, three fetched pages, and twelve ingested chunks
