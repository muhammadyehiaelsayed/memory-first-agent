# Module: src/memagent/analytics/report.py
# Derived from: 00_main_functionality.feature :: "Log exactly one analytics record for every turn"
# Spec sources: milestone-4-llms-logging-analytics.md
# Executable binding: tests/bdd/test_bdd_analytics.py
Feature: Analytics aggregation and reporting over the turn log (src/memagent/analytics/report.py)
  The analytics command reads the JSONL turn records and aggregates them into a
  hit-rate, topic/category/question-type/language distributions, average latency
  per route, and a recent-turns table. The hit-rate denominator counts only turns
  that actually reached a memory lookup, and every user-derived string passes
  through rich markup escaping so a logged query can never style the report.

  # covers: memagent.analytics.report._is_lookup
  Scenario: Only turns that consulted memory count as lookups
    Given a memory-hit turn, a snippets-only degraded turn, a redis-down degraded turn, and a blocked turn
    When each turn is tested for a memory lookup
    Then the memory-hit and snippets-only turns count as lookups while the redis-down and blocked turns do not

  # source: milestone-4-llms-logging-analytics.md :: hit-rate over a known set of records
  # covers: memagent.analytics.report.aggregate
  Scenario: Hit-rate is computed over lookup turns, with unclassified and error counts
    Given four turns: two memory hits, one web miss that was unclassified and carried an error, and one blocked turn
    When the turns are aggregated
    Then total turns is four, the hit-rate is two-thirds, and the unclassified and error counts are each one

  # covers: memagent.analytics.report._counter_table
  Scenario: A distribution table lists each key with its turn count, most frequent first
    Given category counts of three technology turns and one science turn
    When the category distribution table is built
    Then the table has one row per category and renders technology ahead of science with their counts

  # source: milestone-4-llms-logging-analytics.md :: rich markup in a query is escaped
  # covers: memagent.analytics.report.render_report
  Scenario: The full report renders every section and escapes rich markup in user text
    Given an aggregate over a memory-hit turn whose query is "[red]boom[/red]"
    When the report is rendered to a console
    Then all report sections appear and the query text is rendered literally rather than as styling
