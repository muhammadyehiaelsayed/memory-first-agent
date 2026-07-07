# Module: src/memagent/utils/errors.py
# Derived from: 00_main_functionality.feature :: "Degrade gracefully when search succeeds but every page fetch fails"
# Spec sources: milestone-5-security-reliability.md (§6.7 degradation matrix, redis-down row)
# Executable binding: tests/bdd/test_bdd_utils.py
Feature: Redis outages are recognised even when wrapped deep in a cause chain (src/memagent/utils/errors.py)
  A turn only degrades to the degraded_web route with a "redis_down" label if the store
  correctly recognises a Redis connection or timeout failure. redisvl wraps those failures
  inside a RedisSearchError with the real error nested in __cause__, so a top-level
  isinstance check misses the most common outage shape. redis_down_in_chain walks the whole
  cause chain, so the store's typed translation and the CLI startup guard both recognise a
  wrapped outage rather than crashing the turn.

  # covers: memagent.utils.errors.redis_down_in_chain
  Scenario: A wrapped redis connection error is recognised through the cause chain
    Given a wrapper error whose __cause__ is a redis ConnectionError
    When redis_down_in_chain inspects the wrapper
    Then it reports a redis outage
    And it also reports an outage for a bare redis timeout error and for an OSError
    And it does not report an outage for an unrelated error with no redis cause
