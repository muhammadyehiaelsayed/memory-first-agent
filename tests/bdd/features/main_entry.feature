# Module: src/memagent/__main__.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-1-scaffold-and-memory-schema.md
# Executable binding: tests/bdd/test_bdd_contracts.py
# covers-module: memagent.__main__
Feature: The package is runnable as a module entry point (src/memagent/__main__.py)
  A user reaches the agent that answers the root scenario through its command line,
  and "python -m memagent" is the module entry point that launches it: importing
  __main__ calls the Typer app at module load. Running it with --help must launch the
  CLI cleanly and surface the four subcommands, so the entry point is exercised end to
  end via a subprocess rather than a side-effecting import.

  Scenario: Running the package as a module launches the CLI and prints help
    Given the memagent package invoked as "python -m memagent --help"
    When the module entry point runs
    Then it exits with status zero
    And the help output lists the four subcommands
