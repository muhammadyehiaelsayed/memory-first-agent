# Module: scripts/render_graph.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-6-e2e-evals-delivery.md (§6.8 render_graph, FR-M6-18)
# Executable binding: tests/bdd/test_bdd_scripts_tooling.py
Feature: The architecture diagram is auto-generated from the compiled graph (scripts/render_graph.py)
  The whole memory-first pipeline — guard, embed, memory search, web search, fetch,
  ingest, answer and log — is one compiled LangGraph. This script renders that graph to
  a mermaid diagram straight from the compiled object (keyless, no Redis) and splices it
  into the docs between stable markers, so the README diagram is provably not hand-drawn
  and cannot drift from the real routing.

  # covers: scripts.render_graph.render_mermaid
  # source: milestone-6-e2e-evals-delivery.md :: FR-M6-18 (diagram lists all 10 nodes; re-render byte-identical)
  Scenario: The compiled graph renders to a deterministic mermaid diagram without any keys
    When the agent graph is rendered to mermaid
    Then the mermaid text names every one of the ten pipeline nodes
    And rendering it a second time produces byte-identical output

  # covers: scripts.render_graph.splice
  Scenario: Splicing into a document inserts one fenced mermaid block and stays idempotent
    Given a fresh markdown file that holds no diagram yet
    When the mermaid block is spliced into it twice
    Then the file holds exactly one fenced mermaid block between the stable markers
    And the second splice leaves the file byte-identical to the first

  # covers: scripts.render_graph.main
  Scenario: The docs entry point prints the diagram and writes it into both doc files
    Given the working directory is an empty temporary project
    When the render-graph entry point runs
    Then the mermaid diagram is printed to standard output
    And both README.md and docs/architecture.md contain the spliced mermaid block
