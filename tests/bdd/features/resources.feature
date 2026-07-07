# Module: src/memagent/resources.py
# Derived from: 00_main_functionality.feature :: "Report failure when the query cannot be embedded"
# Spec sources: milestone-1-scaffold-and-memory-schema.md
# Executable binding: tests/bdd/test_bdd_contracts.py
# covers-module: memagent.resources
Feature: The dependency-injection container is a frozen resource bundle (src/memagent/resources.py)
  Every route runs against one immutable AgentResources bundle of collaborators
  (settings, memory, embedder, both LLMs, searcher, fetcher, turn logger). The root
  "failed" scenario is reproduced in tests by swapping the embedder for a failing one
  via dataclasses.replace on this frozen container, so its two contracts matter: the
  bundle cannot be mutated in place, and replacing one collaborator yields a fresh
  bundle while leaving the original untouched.

  Scenario: The dependency container is a frozen dataclass carrying all eight collaborators
    Given a resources container assembled from stand-in collaborators
    When the container is inspected
    Then it is a frozen dataclass
    And it exposes exactly the eight collaborator fields
    And reassigning a collaborator after construction is rejected

  Scenario: Swapping one dependency yields a new container and leaves the original intact
    Given a resources container assembled from stand-in collaborators
    When the embedder is swapped via dataclasses.replace
    Then the new container uses the replacement embedder
    And the original container still holds its first embedder
    And both containers remain immutable
