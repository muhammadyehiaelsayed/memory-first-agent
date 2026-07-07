# Module: scripts/eval_lifecycle.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-6-e2e-evals-delivery.md (§6.5, FR-M6-12, FR-M6-13, FR-M6-24)
# Executable binding: tests/bdd/test_bdd_scripts_evals.py
Feature: Lifecycle eval harness is the memory-first hard gate (scripts/eval_lifecycle.py)
  The root memory_miss_web_search scenario says a fresh question is answered from
  the web and ingested for future reuse. This harness turns that promise into a
  pass/fail gate: each fixed question is asked twice and must route
  memory_miss_web_search then memory_hit (similarity >= 0.70). The --mock path
  drives the real graph against live redis:8.2 with FakeLLM/FakeEmbedder and
  respx-mocked search/fetch, exits 0 only when every question is miss-then-hit,
  and names any failure. Real-key mode needs OPENAI_API_KEY; absent it, the
  script must fail with a readable message and no traceback.

  # covers: scripts.eval_lifecycle._page_html
  Scenario: The mocked page repeats its question so it embeds as a later memory hit
    Given a lifecycle question
    When the mock page HTML is generated for it
    Then the HTML is a full document with a block-level article
    And the question text is repeated many times so it dominates the extracted content

  # source: milestone-6-e2e-evals-delivery.md :: --mock passes when every question is miss-then-hit
  # covers: scripts.eval_lifecycle._run_mock
  Scenario: The mock gate proves every fixed question misses then hits against real Redis
    Given a live redis:8.2 is reachable
    When the lifecycle mock gate runs against real Redis with mocked search and fetch
    Then the gate reports every question passed
    And it returns exit code 0

  # source: milestone-6-e2e-evals-delivery.md :: real-key mode runs the live lifecycle pre-submission
  # covers: scripts.eval_lifecycle._run_real
  Scenario: The real-key run verifies miss-then-hit through the live Agent facade
    Given the Agent facade is stubbed to miss then hit on each question
    When the lifecycle real run executes
    Then each question is reported as miss then hit
    And it returns exit code 0

  # source: milestone-6-e2e-evals-delivery.md :: The zero-key eval gate passes against the CI Redis
  # covers: scripts.eval_lifecycle.main
  Scenario: The lifecycle entrypoint runs the hard gate keylessly and exits zero
    Given a live redis:8.2 is reachable
    When the lifecycle script is executed as a subprocess with the mock flag
    Then the subprocess exits with status 0
    And the subprocess output reports all questions passed

  # source: milestone-6-e2e-evals-delivery.md :: real-key mode fails readably without a key
  # covers: scripts.eval_lifecycle.main
  Scenario: The lifecycle entrypoint without a key or the mock flag fails readably
    Given no OpenAI API key is configured
    When the lifecycle entrypoint runs without arguments
    Then it exits with code 2
    And it explains that a real OpenAI key is required
