"""Binding for features/99_traceability.feature — the BDD coverage gate.

Re-derives the function inventory from src/ + scripts/ by AST on every run and
checks it against the ``# covers:`` / ``# covers-module:`` comment declarations
in tests/bdd/features/*.feature, in both directions. Nested closures (a def
inside a def) are implementation details of their parent function and are
covered by the parent's scenario, so they are not inventoried.
"""

import ast
import re
from pathlib import Path

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
    for feature in sorted(FEATURES.glob("*.feature")):
        for line in feature.read_text(encoding="utf-8").splitlines():
            if m := _COVERS.match(line):
                covers.update(n.strip() for n in m.group("names").split(",") if n.strip())
            elif m := _COVERS_MODULE.match(line):
                covered_modules.add(m.group("name"))
    return {"covers": covers, "covered_modules": covered_modules}


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


@then("every zero-function module with real behavior declares module coverage")
def every_behavior_module_covered(inventory, declared):
    missing = sorted(inventory["behavior_modules"] - declared["covered_modules"])
    assert not missing, (
        "zero-function module(s) with top-level behavior lack '# covers-module:':\n  "
        + "\n  ".join(missing)
    )
