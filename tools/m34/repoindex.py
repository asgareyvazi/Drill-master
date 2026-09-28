"""Repo-wide definition and call-site index used as per-item evidence.

Answers the questions a single line cannot: "where is this name defined?", "what does the
callee's signature promise?", "who calls this function and do they guard its sentinel?".
"""
from __future__ import annotations

import ast
import functools
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import ROOT, iter_source_files, read_source  # noqa: E402


@functools.lru_cache(maxsize=1)
def _walk_all():
    definitions: dict[str, list[dict]] = {}
    calls: dict[str, list[dict]] = {}
    assignments: dict[str, list[dict]] = {}      # attribute name -> assignment sites
    properties: dict[str, list[dict]] = {}
    class_fields: dict[str, list[dict]] = {}     # annotated class attribute -> declaration

    for rel in iter_source_files():
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse(read_source(rel))
        except (SyntaxError, ValueError):
            continue
        parents: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions.setdefault(node.name, []).append({
                    "file": rel, "line": node.lineno,
                    "returns": ast.unparse(node.returns) if node.returns else None,
                    "doc": ast.get_docstring(node) or "",
                    "args": [a.arg for a in node.args.args],
                    "n_returns": sum(1 for n in ast.walk(node) if isinstance(n, ast.Return)),
                    "source": ast.unparse(node)[:1200],
                })
                if any(isinstance(d, ast.Name) and d.id == "property" for d in node.decorator_list):
                    properties.setdefault(node.name, []).append({"file": rel, "line": node.lineno})
            elif isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else None)
                if name:
                    calls.setdefault(name, []).append({"file": rel, "line": node.lineno})
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                class_fields.setdefault(node.target.id, []).append({
                    "file": rel, "line": node.lineno,
                    "annotation": ast.unparse(node.annotation),
                    "class": _class_of(parents, node),
                })
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                for t in targets:
                    if isinstance(t, ast.Attribute):
                        assignments.setdefault(t.attr, []).append({
                            "file": rel, "line": node.lineno,
                            "value": ast.unparse(value)[:160] if value else None,
                            "in_init": _in_init(parents, node),
                        })
    return definitions, calls, assignments, properties, class_fields


def _class_of(parents, node) -> str | None:
    cur = node
    while cur is not None and id(cur) in parents:
        cur = parents[id(cur)]
        if isinstance(cur, ast.ClassDef):
            return cur.name
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return None
    return None


def _in_init(parents, node) -> bool:
    cur = node
    while cur is not None and id(cur) in parents:
        cur = parents[id(cur)]
        if isinstance(cur, ast.FunctionDef):
            return cur.name == "__init__"
    return False


def definitions_of(name: str) -> list[dict]:
    return _walk_all()[0].get(name, [])


def callers_of(name: str) -> list[dict]:
    return _walk_all()[1].get(name, [])


def assignments_of(attribute: str) -> list[dict]:
    return _walk_all()[2].get(attribute, [])


def is_property(name: str) -> list[dict]:
    return _walk_all()[3].get(name, [])


def class_field(attribute: str) -> list[dict]:
    """Annotations declared on a class attribute (dataclass field, ORM column, enum)."""
    return _walk_all()[4].get(attribute, [])


def class_field_of(class_name: str, attribute: str) -> list[dict]:
    """The declaration of ``attribute`` on exactly ``class_name`` (not a same-named field elsewhere)."""
    return [f for f in _walk_all()[4].get(attribute, []) if f["class"] == class_name]


def class_field_any(attribute: str) -> list[dict]:
    return _walk_all()[4].get(attribute, [])


def call_site_is_guarded(rel: str, line: int) -> dict:
    """Classify one call site: guarded / ignored / used-in-arithmetic / persisted."""
    try:
        lines = read_source(rel).splitlines()
    except OSError:
        return {"kind": "unknown"}
    window = "\n".join(lines[max(0, line - 2):min(len(lines), line + 6)])
    if f"if {window}" in window or " is not None" in window or "if not " in window \
            or "getattr(" in window or " or " in window:
        return {"kind": "guarded", "text": window.strip()[:120]}
    if line <= len(lines):
        stmt = lines[line - 1].strip()
        if stmt.startswith(("return", "self.", "print", "logger", "log.")) or "=" in stmt:
            return {"kind": "captured-or-ignored", "text": stmt[:120]}
    return {"kind": "ignored", "text": window.strip()[:120]}
