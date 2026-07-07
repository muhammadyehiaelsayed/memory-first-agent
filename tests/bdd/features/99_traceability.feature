# ============================================================================
# META FEATURE — enforces the BDD coverage contract itself.
#
# The contract: every module-level function and class method in src/ and
# scripts/ appears in at least one "# covers:" declaration in some feature
# file here, every declaration resolves to a real function (no typos, no
# stale entries), and every zero-function module with real top-level
# behavior declares "# covers-module:".
#
# Executable binding: tests/bdd/test_bdd_traceability.py
# ============================================================================
Feature: BDD traceability — every Python function sits under a scenario
  The BDD suite is only trustworthy if its coverage claim is machine-checked.
  This feature re-derives the full function inventory from the source tree on
  every run and compares it against the coverage declarations embedded in the
  feature files, in both directions.

  Scenario: Every function in src and scripts is covered by at least one scenario
    Given the inventory of all Python functions in src and scripts
    And all coverage declarations across the feature files
    Then every function in the inventory is declared covered
    And every coverage declaration points at a real function
    And every zero-function module with real behavior declares module coverage
