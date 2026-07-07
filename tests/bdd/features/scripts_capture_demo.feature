# Module: scripts/capture_demo.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-6-e2e-evals-delivery.md (§6.9, FR-M6-19)
# Executable binding: tests/bdd/test_bdd_scripts_evals.py
Feature: Capture a live miss-then-hit demo transcript (scripts/capture_demo.py)
  The root memory_hit scenario is what the recorded demo proves to a human: the
  same question is asked twice, misses the first time and hits stored memory the
  second. This script drives the real Agent facade over two identical turns and
  renders each turn's route banner, sources and answer into
  docs/demo_transcript.md. Absent a real OpenAI key the transcript stays a
  committed "pending real-key capture" placeholder, so main() must refuse
  cleanly rather than crash or write a half-baked file.

  # covers: scripts.capture_demo._banner
  Scenario: The transcript banner names each turn's routing decision
    Given turn results for a memory hit, a web miss and a degraded turn
    When each result is rendered as a transcript banner
    Then the memory-hit banner shows the similarity score
    And the web-miss banner announces the web search
    And any other route is shown verbatim in brackets

  # source: milestone-6-e2e-evals-delivery.md :: capture_demo records a miss then a hit
  # covers: scripts.capture_demo._capture
  Scenario: Capturing a live session renders both turns as a miss-then-hit transcript
    Given a stubbed Agent that misses then hits on the demo question
    When the demo session is captured to markdown
    Then the transcript records two turns
    And turn one is a memory miss with a web source
    And turn two is a memory hit whose banner shows the similarity

  # covers: scripts.capture_demo.main
  Scenario: Without a real OpenAI key the demo stays a pending placeholder
    Given no OpenAI API key is configured
    When the capture-demo entrypoint runs
    Then it exits with code 2
    And it explains that a real OpenAI key is required
