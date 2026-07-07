# Module: src/memagent/memory/store.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-1-scaffold-and-memory-schema.md, milestone-2-memory-path.md
# Executable binding: tests/bdd/test_bdd_memory_store.py
Feature: Redis vector memory store (src/memagent/memory/store.py)
  The store is the memory-first read/write engine behind the root memory_hit
  scenario. It owns the ONE distance->similarity conversion site
  (similarity = 1 - cosine distance) whose inclusive >= 0.70 result is what
  routes a turn to "memory_hit", and it round-trips ingested web content back
  out of Redis by nearest-neighbour search so a later similar question can be
  answered from memory. It also isolates Redis-outage translation and the 24h
  freshness gate that keeps ingestion from re-fetching a URL seen recently.

  # source: milestone-2-memory-path.md :: cosine distance 0.30 converts to similarity 0.70
  # covers: memagent.memory.store.distance_to_similarity
  Scenario: A cosine distance becomes a similarity by one minus the distance
    Given a cosine vector distance of 0.30
    When the distance is converted to a similarity
    Then the similarity is 0.70, exactly one minus the distance
    And the discredited half-distance formula that would yield 0.85 is not used
    And distance 0.0 converts to similarity 1.0 and distance 1.0 converts to similarity 0.0

  # covers: memagent.memory.store._epoch_to_iso
  Scenario: A stored epoch timestamp is exposed as an ISO-8601 UTC instant
    Given an epoch timestamp of 1751625600.0 seconds
    When the timestamp is converted to a stored-at string
    Then the string is the ISO-8601 UTC instant "2025-07-04T10:40:00+00:00"
    And the string parses back as a valid ISO-8601 datetime

  # covers: memagent.memory.store.make_redis_client
  Scenario: The Redis client is built with bounded native retries
    Given the application settings
    When a Redis client is built for the store
    Then the client retries only connection and timeout errors, three retries deep
    And its socket read and connect timeouts are capped at two seconds

  # covers: memagent.memory.store._as_memory_error
  Scenario: A wrapped Redis outage is recognised as a typed memory error
    Given a redisvl RedisSearchError wrapping a Redis connection failure in its cause chain
    When the exception is examined for a memory outage
    Then it is translated into a typed MemoryUnavailableError
    And a bare Redis connection failure is also recognised as a memory outage
    And a plain Redis ResponseError, which signals a programming bug, is not translated

  # covers: memagent.memory.store.RedisMemoryStore.__init__
  Scenario: Constructing the store opens the shared web_memory index
    Given the application settings and a Redis client
    When a RedisMemoryStore is constructed over them
    Then it opens the shared "web_memory" vector index against that client
    And it retains the settings it was given

  # covers: memagent.memory.store.RedisMemoryStore._io
  Scenario: A Redis outage during an I/O op is translated while bugs surface loudly
    Given a constructed RedisMemoryStore
    When a guarded I/O operation raises a Redis connection failure
    Then the store surfaces it as a typed MemoryUnavailableError
    And a successful guarded operation returns its value unchanged
    And a Redis ResponseError from a guarded operation is left to surface untranslated

  # covers: memagent.memory.store.RedisMemoryStore.ensure_ready
  Scenario: A fresh Redis with no index is provisioned on first use instead of crashing
    Given a Redis instance from which the web_memory index has been dropped
    When the store is asked to ensure the index is ready and is then queried
    Then the index did not exist beforehand but exists afterwards
    And the nearest-neighbour query returns an empty list rather than raising

  # source: milestone-2-memory-path.md :: KNN returns raw top-k with similarity attached
  # covers: memagent.memory.store.RedisMemoryStore.knn
  Scenario: A stored chunk is found again with its similarity attached at the 0.70 hit boundary
    Given an empty web_memory index holding a single chunk anchored at a known unit embedding
    When the anchor content is looked up by nearest-neighbour search
    Then the top hit carries similarity 1.0 with its text, url and title intact
    And a query at cosine 0.70 to the anchor scores exactly 0.70, an inclusive hit at the 0.70 threshold
    And an orthogonal query scores 0.0
    And a nearest-neighbour lookup against a truly empty index returns an empty list

  # source: milestone-2-memory-path.md :: re-storing with fewer chunks removes stale keys
  # covers: memagent.memory.store.RedisMemoryStore.store
  Scenario: Ingested page content round-trips and re-ingestion prunes stale chunks
    Given an empty web_memory index
    When a page with six chunks is ingested into the store
    Then each chunk key carries a bounded positive TTL no greater than 604800 seconds
    And the page content and metadata round-trip back out through nearest-neighbour search
    And re-storing the same URL with three chunks removes the stale chunk keys and sets the meta count to three

  # source: milestone-2-memory-path.md :: freshness helper treats a missing doc as not fresh
  # covers: memagent.memory.store.RedisMemoryStore.is_fresh
  Scenario: The freshness gate is inclusive-inside and exclusive at the 24h boundary
    Given a page stored at a pinned instant
    When the freshness of its URL is checked as time advances across the 24h window
    Then the URL is fresh one second inside the window
    And the URL is not fresh exactly at the window boundary
    And the URL is not fresh well past the window
    And an unknown URL is never reported fresh
