# Module: src/memagent/nodes/ingest.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-3-web-pipeline.md
# Executable binding: tests/bdd/test_bdd_nodes_web_path.py
Feature: Ingest-content node stores fetched pages for future reuse without ever gating the answer (src/memagent/nodes/ingest.py)
  This node realises the "ingest what was found" half of the memory-miss root
  scenario: for each fetched page it sanitizes the markdown, summarises the first
  slice of it, chunks it, embeds the summary plus chunks, and stores them so a later
  identical question becomes a memory hit. Persistence never gates answering — the
  freshness gate, skip_store, a summary failure and a store failure each still leave
  the in-hand chunks available for the current turn's answer.

  # source: milestone-3-web-pipeline.md :: FR-M3-23 (chunks + summary stored per page)
  # covers: memagent.nodes.ingest.make_ingest_content
  Scenario: A fetched page is sanitized, summarised, chunked and stored for future reuse
    Given a fetched page and an empty memory that accepts stores
    When the ingest content node runs
    Then the page content is stored as chunks for future reuse
    And the stored chunk ids are keyed by the canonical URL hash
    And the enriched page carries its summary and sanitizer flags
    And the summary embedding is stored ahead of the chunk embeddings

  # source: milestone-3-web-pipeline.md :: FR-M3-22 (summary from the first 6000 chars)
  # covers: memagent.nodes.ingest.make_ingest_content
  Scenario: The summary input is capped so a huge page never blows the token budget
    Given a fetched page far larger than the summary input cap
    When the ingest content node runs
    Then the summariser receives only the first 6000 characters of the sanitized page

  # source: milestone-3-web-pipeline.md :: FR-M3-26 (summary failure tolerated)
  # covers: memagent.nodes.ingest.make_ingest_content
  Scenario: A summary failure is tolerated and chunking still flows
    Given a fetched page and a summariser that fails
    When the ingest content node runs
    Then the chunks are still produced from the sanitized markdown
    And the page summary is left empty
    And a summary failure is recorded on the turn

  # source: milestone-3-web-pipeline.md :: FR-M3-27 (store failure never blocks answering)
  # covers: memagent.nodes.ingest.make_ingest_content
  Scenario: A store failure never blocks the in-hand answer
    Given a fetched page and a memory whose store fails
    When the ingest content node runs
    Then the chunks are still produced from the sanitized markdown
    And nothing is persisted
    And a store failure is recorded on the turn

  # source: milestone-3-web-pipeline.md :: FR-M3-25 (skip_store persists nothing but still chunks)
  # covers: memagent.nodes.ingest.make_ingest_content
  Scenario: A skip-store turn persists nothing yet still chunks for the answer
    Given a fetched page on a turn that must not persist
    When the ingest content node runs
    Then the memory store is never called
    And the in-hand chunks are still available for answering

  # source: milestone-3-web-pipeline.md :: FR-M3-24 (freshness gate skips re-ingest within 24h)
  # covers: memagent.nodes.ingest.make_ingest_content
  Scenario: A recently ingested URL is not re-stored within the freshness window
    Given a fetched page already ingested within the freshness window
    When the ingest content node runs
    Then the freshness gate was consulted for the page
    And no summary is requested and nothing is re-stored
    And the page is still chunked for the in-hand answer

  # source: specs/003 I2 (ingestion never gates answering — sanitize/chunk inside the guard)
  # covers: memagent.nodes.ingest.make_ingest_content
  Scenario: A page whose chunker blows up degrades to a skipped doc without crashing the turn
    Given a fetched page whose chunker raises
    When the ingest content node runs
    Then the turn still returns with the page skipped and an ingest failure recorded
