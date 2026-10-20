"""Every `from <repo module> import name` must still resolve (M43 Phase 4).

Replacing `from PySide6.QtX import *` with explicit imports removes names a
module used to re-export implicitly. This static check (no Qt import needed)
parses every tracked Python file and verifies that each name imported from a
repository module is defined or imported at that module's top level. Target
modules that still contain a wildcard import cannot be resolved statically and
are skipped; they become checked automatically once their wildcard is replaced.
"""

from __future__ import annotations

import ast
import subprocess
import warnings
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse(path: str) -> ast.Module:
    with warnings.catch_warnings():  # invalid escapes in unrelated tool scripts
        warnings.simplefilter("ignore", (SyntaxWarning, DeprecationWarning))
        return ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)


def _tracked_python() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def _module_file(module: str, tracked: frozenset[str]) -> str | None:
    base = module.replace(".", "/")
    for candidate in (f"{base}.py", f"{base}/__init__.py"):
        if candidate in tracked:
            return candidate
    return None


def _is_package(module: str, tracked: frozenset[str]) -> bool:
    prefix = module.replace(".", "/") + "/"
    return any(p.startswith(prefix) for p in tracked)


def _top_level_statements(body):
    """Module-level statements, descending into if/try/with blocks (conditional definitions)."""
    for node in body:
        yield node
        if isinstance(node, (ast.If, ast.Try, ast.With)):
            for field in ("body", "orelse", "finalbody"):
                yield from _top_level_statements(getattr(node, field, []) or [])
            for handler in getattr(node, "handlers", []) or []:
                yield from _top_level_statements(handler.body)


def _target_names(node) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(e) for e in node.elts)) if node.elts else set()
    return set()


@lru_cache(maxsize=None)
def _exports(path: str) -> tuple[frozenset[str], bool]:
    """(names bound at top level, has a wildcard import)."""
    tree = _parse(path)
    names: set[str] = set()
    wildcard = False
    for node in _top_level_statements(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names |= _target_names(target)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names |= _target_names(node.target)
        elif isinstance(node, ast.Import):
            names |= {(a.asname or a.name.split(".")[0]) for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    wildcard = True
                else:
                    names.add(alias.asname or alias.name)
    return frozenset(names), wildcard


def test_names_imported_from_repository_modules_exist():
    tracked = frozenset(_tracked_python())
    missing = []
    for path in sorted(tracked):
        try:
            tree = _parse(path)
        except SyntaxError:  # compileall in the release gate reports these
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            target = _module_file(node.module, tracked)
            if target is None:
                continue
            exported, wildcard = _exports(target)
            if wildcard:
                continue
            for alias in node.names:
                name = alias.name
                if name == "*" or name in exported:
                    continue
                if _is_package(node.module, tracked) and _module_file(f"{node.module}.{name}", tracked):
                    continue  # `from package import submodule`
                missing.append(f"{path}:{node.lineno} imports {name!r} from {node.module}")
    assert missing == [], "names no longer provided by their module:\n" + "\n".join(missing)


def test_core_wildcards_replaced_with_the_names_actually_used():
    exported, wildcard = _exports("core/wellbore_schematic_engine.py")
    assert not wildcard, "core/wellbore_schematic_engine.py must no longer use wildcard imports"
    assert {"QColor", "QPen", "Qt", "SchematicAutoBuilder"} <= exported
    assert "QWidget" not in exported  # it was never used there and is no longer re-exported
    exported, wildcard = _exports("core/common_widgets.py")
    assert not wildcard and {"safe_replace_chart", "Signal", "QWidget"} <= exported
