# Module: scripts/gen_env_example.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-1-scaffold-and-memory-schema.md (§6.4 .env.example generator, FR-M1-08)
# Executable binding: tests/bdd/test_bdd_scripts_tooling.py
Feature: The .env.example generator keeps documented settings in lock-step with Settings (scripts/gen_env_example.py)
  Every tunable in the agent — including the 0.70 inclusive similarity threshold that
  decides the memory_hit branch and the turn-log path — lives once in Settings. This
  script is the single anti-drift mechanism: it renders .env.example straight from
  Settings.model_fields so the documented environment can never diverge from the code
  that reads it.

  # covers: scripts.gen_env_example.render
  # source: milestone-1-scaffold-and-memory-schema.md :: "regenerating .env.example is a no-op when in sync"
  Scenario: The rendered template reproduces the committed .env.example byte-for-byte
    Given the committed .env.example file
    When the env template is rendered from Settings
    Then the rendered text is byte-identical to the committed file

  # covers: scripts.gen_env_example.render
  # source: milestone-1-scaffold-and-memory-schema.md :: "every Settings field appears in .env.example"
  Scenario: Every Settings field is emitted, with secret-shaped fields blanked
    When the env template is rendered from Settings
    Then every Settings field name appears uppercased as a KEY= line
    And the secret-shaped fields emit safe placeholders instead of their raw defaults

  # covers: scripts.gen_env_example.main
  Scenario: Running the generator writes the template to the .env.example path
    Given the generator output is redirected to a temporary directory
    When the generator entry point runs
    Then the redirected .env.example matches the rendered template
    And the run reports how many settings it wrote
