# Module: scripts/eval_grounding.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-6-e2e-evals-delivery.md (§6.6, FR-M6-14, FR-M6-15)
# Executable binding: tests/bdd/test_bdd_scripts_evals.py
Feature: Grounding eval harness demonstrates cited, abstaining answers (scripts/eval_grounding.py)
  The root memory_miss_web_search scenario ends with "the answer cites its
  source URLs". This harness is the honest DEMONSTRATION of that property: it
  runs a small fixed set of grounded and abstain cases, has an answerer produce
  a context-bound answer, and scores it with an LLM-as-judge on grounding,
  citation-validity and abstention. The --mock path uses FakeLLM for both roles
  so it runs keyless and Redis-less in CI, printing a scorecard that labels
  itself a demonstration rather than a benchmark.

  # source: milestone-6-e2e-evals-delivery.md :: A grounded case expects a valid citation
  # covers: scripts.eval_grounding._score
  Scenario: Scoring drives every fixed case through the answerer and the judge
    Given a fake answerer and a fake grounding judge
    When the fixed grounding cases are scored
    Then one verdict row is produced per fixed case
    And the answerer and judge were each invoked once per case
    And every row carries a grounding verdict

  # source: milestone-6-e2e-evals-delivery.md :: Output honestly labels itself a demonstration
  # covers: scripts.eval_grounding._render
  Scenario: The scorecard prints per-case rows, an aggregate, and an honest disclaimer
    Given a set of scored grounding verdicts
    When the scorecard is rendered
    Then a row is printed for each scored case
    And an aggregate over all three dimensions is printed
    And the output states it is a demonstration, not a benchmark

  # source: milestone-6-e2e-evals-delivery.md :: --mock scores all three dimensions keylessly
  # covers: scripts.eval_grounding._run_mock
  Scenario: The keyless mock run scores every case and succeeds
    Given no API key and no Redis are available
    When the grounding mock run executes
    Then it prints an aggregate scorecard
    And it returns exit code 0

  # covers: scripts.eval_grounding._run_real
  Scenario: The real run drives the OpenAI-backed answerer and judge
    Given the OpenAI client builder is stubbed with fakes
    When the grounding real run executes
    Then it prints an aggregate scorecard
    And it returns exit code 0

  # covers: scripts.eval_grounding.main
  Scenario: The grounding entrypoint runs keylessly under the mock flag and exits zero
    Given no API key and no Redis are available
    When the grounding entrypoint runs with the mock flag
    Then it prints an aggregate scorecard
    And it returns exit code 0

  # source: milestone-6-e2e-evals-delivery.md :: real-key mode fails readably without a key
  # covers: scripts.eval_grounding.main
  Scenario: The grounding entrypoint without a key or the mock flag fails readably
    Given no OpenAI API key is configured
    When the grounding entrypoint runs without arguments
    Then it exits with code 2
    And it explains that a real OpenAI key is required
