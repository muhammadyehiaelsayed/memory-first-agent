"""Binding for features/99_traceability.feature — the BDD coverage gate.

Re-derives the function inventory from src/ + scripts/ by AST on every run and
checks it against the ``# covers:`` / ``# covers-module:`` comment declarations
in tests/bdd/features/*.feature, in both directions. Nested closures (a def
inside a def) are implementation details of their parent function and are
covered by the parent's scenario, so they are not inventoried.
"""

import ast
import re
import sys
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then

scenarios("features/99_traceability.feature")

REPO = Path(__file__).resolve().parents[2]
FEATURES = Path(__file__).resolve().parent / "features"

_COVERS = re.compile(r"^\s*#\s*covers:\s*(?P<names>.+?)\s*$")
_COVERS_MODULE = re.compile(r"^\s*#\s*covers-module:\s*(?P<name>[\w.]+)\s*$")


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(REPO).with_suffix("").parts)
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _functions_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mod = _module_name(path)
    found: list[str] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append(f"{prefix}.{child.name}")  # no recursion: closures excluded
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}.{child.name}")

    visit(tree, mod)
    return found


def _has_top_level_behavior(path: Path) -> bool:
    """True when a zero-function module still does something at import time:
    any top-level statement beyond imports and the module docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # drop the docstring
    return any(not isinstance(node, (ast.Import, ast.ImportFrom)) for node in body)


def _scenario_follows(lines: list[str], index: int) -> bool:
    """True when a ``Scenario:``/``Scenario Outline:`` sits directly beneath the
    declaration at ``index`` — before the next blank-separated block.

    Sibling comment lines (e.g. a ``# source:`` note or a stacked ``# covers:``)
    are skipped, but a blank line ends the block: a declaration left behind by a
    moved/deleted scenario, or pasted into a Feature narrative, is separated from
    the next scenario by a blank line and therefore does NOT count. This ties
    each credited declaration to a real scenario block."""
    for line in lines[index + 1 :]:
        stripped = line.strip()
        if not stripped:
            return False  # blank line ends the block before any scenario appeared
        if stripped.startswith("#"):
            continue  # sibling comment (source note / stacked covers)
        return stripped.startswith(("Scenario:", "Scenario Outline:"))
    return False


@given("the inventory of all Python functions in src and scripts", target_fixture="inventory")
def inventory():
    files = sorted(list((REPO / "src").rglob("*.py")) + list((REPO / "scripts").glob("*.py")))
    functions: set[str] = set()
    behavior_modules: set[str] = set()
    for f in files:
        funcs = _functions_of(f)
        functions.update(funcs)
        if not funcs and _has_top_level_behavior(f):
            behavior_modules.add(_module_name(f))
    return {"functions": functions, "behavior_modules": behavior_modules}


@given("all coverage declarations across the feature files", target_fixture="declared")
def declared():
    covers: set[str] = set()
    covered_modules: set[str] = set()
    orphans: list[str] = []
    for feature in sorted(FEATURES.glob("*.feature")):
        lines = feature.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if m := _COVERS.match(line):
                names = [n.strip() for n in m.group("names").split(",") if n.strip()]
                if _scenario_follows(lines, i):
                    covers.update(names)  # declaration sits above a real scenario
                else:
                    orphans.append(f"{feature.name}:{i + 1}: {line.strip()}")
            elif m := _COVERS_MODULE.match(line):
                covered_modules.add(m.group("name"))
    return {"covers": covers, "covered_modules": covered_modules, "orphans": orphans}


@then("every function in the inventory is declared covered")
def every_function_covered(inventory, declared):
    missing = sorted(inventory["functions"] - declared["covers"])
    assert not missing, (
        f"{len(missing)} function(s) have no '# covers:' declaration in any feature file:\n  "
        + "\n  ".join(missing)
    )


@then("every coverage declaration points at a real function")
def every_declaration_real(inventory, declared):
    stale = sorted(declared["covers"] - inventory["functions"])
    assert not stale, (
        f"{len(stale)} '# covers:' declaration(s) do not match any function "
        f"(typo or stale entry):\n  " + "\n  ".join(stale)
    )
    ghost = sorted(declared["covered_modules"] - inventory["behavior_modules"])
    assert not ghost, (
        "covers-module declaration(s) for modules that have functions or no behavior:\n  "
        + "\n  ".join(ghost)
    )


@then("every coverage declaration sits directly above a real scenario")
def every_declaration_has_a_scenario(declared):
    orphans = declared["orphans"]
    assert not orphans, (
        f"{len(orphans)} '# covers:' declaration(s) are not immediately followed by a "
        "Scenario (orphaned comment — its scenario was moved/deleted or the comment was "
        "pasted into narrative), so they credit no behavioral coverage:\n  " + "\n  ".join(orphans)
    )


@then("every zero-function module with real behavior declares module coverage")
def every_behavior_module_covered(inventory, declared):
    missing = sorted(inventory["behavior_modules"] - declared["covered_modules"])
    assert not missing, (
        "zero-function module(s) with top-level behavior lack '# covers-module:':\n  "
        + "\n  ".join(missing)
    )


# --- Unit tests for the stricter scenario-adjacency rule (findings #21/#42) -----
# These exercise the gate's own logic directly so a regression that re-credits an
# orphaned '# covers:' comment (no Scenario beneath it) is caught.


def test_scenario_follows_credits_declaration_directly_above_scenario():
    lines = [
        "  # source: note",
        "  # covers: pkg.mod.func",
        "  Scenario: does the thing",
        "    Given a thing",
    ]
    assert _scenario_follows(lines, 1)


def test_scenario_follows_allows_scenario_outline_and_stacked_covers():
    lines = [
        "  # covers: pkg.mod.a",
        "  # covers: pkg.mod.b",
        "  Scenario Outline: variants",
    ]
    assert _scenario_follows(lines, 0)  # stacked covers skips the sibling comment
    assert _scenario_follows(lines, 1)


def test_scenario_follows_rejects_orphan_before_blank():
    # a covers left behind by a deleted scenario: a blank line separates it from
    # the next scenario block.
    lines = [
        "  # covers: pkg.mod.orphan",
        "",
        "  # covers: pkg.mod.survivor",
        "  Scenario: the surviving one",
    ]
    assert not _scenario_follows(lines, 0)
    assert _scenario_follows(lines, 2)


def test_scenario_follows_rejects_covers_pasted_in_narrative():
    lines = [
        "Feature: something",
        "  # covers: pkg.mod.func",
        "  narrative prose continues here, not a scenario",
        "",
        "  Scenario: real",
    ]
    assert not _scenario_follows(lines, 1)


def test_declared_drops_orphan_but_keeps_real(tmp_path, monkeypatch):
    (tmp_path / "sample.feature").write_text(
        "Feature: sample\n"
        "\n"
        "  # covers: pkg.mod.real\n"
        "  Scenario: real one\n"
        "    Given x\n"
        "\n"
        "  # covers: pkg.mod.orphan\n"
        "\n"
        "  Scenario: unrelated, with its own declaration missing\n"
        "    Given y\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "FEATURES", tmp_path)
    result = declared()
    assert "pkg.mod.real" in result["covers"]
    assert "pkg.mod.orphan" not in result["covers"]
    assert any("pkg.mod.orphan" in o for o in result["orphans"])


def test_every_declaration_has_a_scenario_flags_orphans():
    with pytest.raises(AssertionError, match="orphan"):
        every_declaration_has_a_scenario({"orphans": ["sample.feature:7: # covers: x"]})
    every_declaration_has_a_scenario({"orphans": []})  # clean case does not raise
