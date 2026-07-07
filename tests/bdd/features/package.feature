# Module: src/memagent/__init__.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-1-scaffold-and-memory-schema.md
# Executable binding: tests/bdd/test_bdd_contracts.py
# covers-module: memagent
Feature: The memagent package advertises its version (src/memagent/__init__.py)
  The whole memory-first web agent is delivered as the importable memagent package,
  and the root scenario runs entirely inside it. Its one piece of observable
  top-level behaviour is the version marker every distribution carries, which must
  match the packaged 0.1.0 release identity.

  Scenario: The package advertises its semantic version
    Given the installed memagent package
    When its version marker is read
    Then it is the semantic version "0.1.0"
    And the version has three dotted numeric components
