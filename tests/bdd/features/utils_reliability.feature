# Module: src/memagent/utils/reliability.py
# Derived from: 00_main_functionality.feature :: "Report failure when the query cannot be embedded"
# Spec sources: milestone-5-security-reliability.md (§6.6 policy table, FR-M5-17..22)
# Executable binding: tests/bdd/test_bdd_utils.py
Feature: Single-owner retry policies translate transport failures into typed dependency errors (src/memagent/utils/reliability.py)
  The root "failed" and "degraded_web" routes depend on this module being the ONE place
  that retries a flaky dependency and, on exhaustion or fast-fail, converts a raw
  transport error into a typed LLMUnavailableError / SearchUnavailableError /
  PageFetchError that the pipeline nodes turn into a designed degradation instead of a
  crash. Every wait scales by WAIT_CAP_SCALE, so the real retry code path runs instantly
  under test rather than being monkeypatched away.

  # covers: memagent.utils.reliability._max_wait
  Scenario: Backoff wait caps collapse to zero under the test scale
    Given a retry wait cap of 20 seconds
    When the wait cap is scaled by a WAIT_CAP_SCALE of 0
    Then the effective maximum wait is 0 seconds
    And the same cap scaled by 1 stays at its full value

  # covers: memagent.utils.reliability._status
  Scenario: The HTTP status is extracted from both SDK and transport errors
    When the status helper inspects an OpenAI 401 status error, an httpx 503 status error, and a plain ValueError
    Then it reports 401 for the SDK error, 503 for the transport error, and nothing for the unrelated error

  # covers: memagent.utils.reliability._is_retryable_llm
  Scenario: Transient OpenAI errors are retryable while client errors are not
    When the LLM retry predicate classifies a timeout, a connection error, and a 400 status error
    Then the timeout and the connection error are retryable and the 400 status error is not

  # covers: memagent.utils.reliability._is_retryable_tavily
  Scenario: Search retries cover timeouts, 429, and 5xx but never 4xx auth failures
    When the search retry predicate classifies a connect timeout, a 429, a 500, and a 401
    Then the timeout, the 429, and the 500 are retryable and the 401 is not

  # covers: memagent.utils.reliability._is_retryable_fetch
  Scenario: Page fetch retries only gateway errors and timeouts
    When the fetch retry predicate classifies a read timeout, a 503, a 404, and a 429
    Then the timeout and the 503 are retryable and the 404 and 429 are not

  # source: milestone-5-security-reliability.md :: FR-M5-20 (OpenAI retry acceptance)
  # covers: memagent.utils.reliability.llm_retry
  Scenario: A transient LLM call retries to success then an auth failure fast-fails as a typed error
    Given an LLM call guarded by the llm_retry policy with instant retries
    When the call raises a transient connection error three times then returns a result
    Then the guarded call returns the result after exactly 4 attempts without real sleeping
    When a guarded LLM call fails immediately with an HTTP 401
    Then it raises LLMUnavailableError after a single attempt

  # source: milestone-5-security-reliability.md :: Auth error fails fast and falls back to ddgs / Persistent 503 exhausts and raises the typed error
  # covers: memagent.utils.reliability.tavily_retry
  Scenario: Auth failures fall through to the fallback while exhausted search retries raise the typed error
    Given a search call guarded by the tavily_retry policy with instant retries
    When a guarded search fails with an HTTP 401
    Then the original transport error propagates unchanged so the ddgs fallback can run
    When a guarded search keeps returning HTTP 503
    Then it raises SearchUnavailableError after exactly 3 attempts

  # source: milestone-5-security-reliability.md :: 404 is not retried and the URL is skipped / Read timeout retries then succeeds
  # covers: memagent.utils.reliability.fetch_retry
  Scenario: A non-retryable page fetch becomes a non-fatal PageFetchError while a timeout is retried once
    Given a page fetch guarded by the fetch_retry policy with instant retries
    When a guarded fetch fails with an HTTP 404
    Then it raises PageFetchError after a single attempt
    When a guarded fetch times out once then returns the page
    Then the guarded call returns the page after exactly 2 attempts

  # source: review remediation :: A9 (the ingest page-summary consumer of the unwrapped analytics client owns a bounded retry)
  # covers: memagent.utils.reliability.summary_retry
  Scenario: The page summary retries a transient error once then re-raises after the 2-attempt budget
    Given a summary call guarded by the summary_retry policy with instant retries
    When a guarded summary times out once then returns the summary
    Then the guarded call returns the summary after exactly 2 attempts
    When a guarded summary keeps failing with a transient connection error
    Then the original error propagates after exactly 2 attempts so ingest degrades
