# Module: src/memagent/web/to_markdown.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-3-web-pipeline.md
# Executable binding: tests/bdd/test_bdd_web_fetch.py
Feature: HTML to markdown extraction gating (src/memagent/web/to_markdown.py)
  Every page fetched on a memory miss is converted to markdown before it is
  ingested and used to ground the answer. This module wraps trafilatura with a
  precision-first extract, a recall retry, a minimum-length floor and a maximum
  cap, so the root "memory_miss_web_search" flow ingests clean, bounded content
  only and skips cookie-wall or JS-shell pages.

  # source: milestone-3-web-pipeline.md :: Precision pass produces markdown with tables and no inline links
  # covers: memagent.web.to_markdown.to_markdown
  Scenario: The precision pass uses the configured trafilatura keyword arguments
    Given a trafilatura extractor that records its keyword arguments and returns usable markdown
    When the HTML is converted to markdown
    Then the precision-first keyword arguments are used exactly once
    And the extracted markdown is returned

  # source: milestone-3-web-pipeline.md :: Empty precision pass retries once with recall
  # covers: memagent.web.to_markdown.to_markdown
  Scenario: An empty precision pass retries once with recall
    Given a trafilatura extractor that is empty on precision but non-empty on recall
    When the HTML is converted to markdown
    Then a second call is made with favor_recall enabled
    And the recall markdown is returned

  # source: milestone-3-web-pipeline.md :: The 200-character floor gates unusable pages
  # covers: memagent.web.to_markdown.to_markdown
  Scenario: Extractions below the floor are rejected as unusable
    Given a trafilatura extractor returning fewer than the minimum characters
    When the HTML is converted to markdown
    Then no markdown is returned

  # source: milestone-3-web-pipeline.md :: Markdown is capped at 20000 characters per page
  # covers: memagent.web.to_markdown.to_markdown
  Scenario: Over-long extractions are capped at the maximum character budget
    Given a trafilatura extractor returning far more than the maximum characters
    When the HTML is converted to markdown
    Then the returned markdown is truncated to the configured maximum length

  # source: milestone-3-web-pipeline.md :: Both passes empty returns none
  # covers: memagent.web.to_markdown.to_markdown
  Scenario: Two empty passes yield no markdown
    Given a trafilatura extractor that is empty on both precision and recall
    When the HTML is converted to markdown
    Then no markdown is returned
