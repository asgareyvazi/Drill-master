"""M34 analysis infrastructure: source indexing, fingerprints and per-line facts.

This module is the M34 successor of the (lost) M33 session tooling. It lives INSIDE the
repository on purpose: M33's evidence survived but its generators did not, which is precisely
why M33 could not be reproduced. Anything that produced evidence must be shippable.

Identity contract (unchanged from M33 so that M33 fingerprints still verify):
    fingerprint = sha256("path|kind|symbol|normalized expression|ordinal")
A line number is never an identity; a fingerprint always carries context.
"""
from __future__ import annotations

import ast
import functools
import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

SKIP_DIRS = {".git", "build", "dist", ".venv", "__pycache__", ".pytest_cache", "node_modules",
             ".mypy_cache", ".ruff_cache", ".tox", ".nox", "docs", "out", "target", "coverage"}


# ---------------------------------------------------------------- file access
@functools.lru_cache(maxsize=512)
def file_lines(rel: str) -> tuple[str, ...]:
    path = ROOT / rel
    try:
        return tuple(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return ()


def file_sha(rel: str) -> str:
    try:
        return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    except OSError:
        return ""


def read_source(rel: str) -> str:
    return "\n".join(file_lines(rel))


# ---------------------------------------------------------------- normalization
def norm(text: str) -> str:
    """Whitespace-collapsed single-line form (M33-compatible)."""
    return re.sub(r"\s+", " ", text or "").strip()


def fingerprint(rel: str, kind: str, symbol: str | None, expr: str, ordinal: int = 0) -> str:
    payload = "|".join([rel, kind, symbol or "", norm(expr), str(ordinal)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- AST index
@functools.lru_cache(maxsize=256)
def ast_index(rel: str):
    """Return (tree, parents, functions, lines).

    ``functions`` is a list of (start_line, end_line, qualname, node) discovered with
    ``ast.walk`` over the whole module (a hand-rolled generic_visit silently misses nested
    defs — that bug cost M33 hours; do not reintroduce it).
    """
    src = read_source(rel)
    lines = file_lines(rel)
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return None, {}, [], lines
    parents: dict[int, ast.AST] = {}
    functions: list[tuple[int, int, str, ast.AST]] = []

    def walk(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{child.name}"
                functions.append((child.lineno, getattr(child, "end_lineno", child.lineno),
                                  qual, child))
                walk(child, qual + ".")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            else:
                walk(child, prefix)

    walk(tree)
    return tree, parents, functions, lines


def enclosing_function(rel: str, line: int):
    _, _, functions, _ = ast_index(rel)
    best = None
    for start, end, qual, node in functions:
        if start <= line <= end and (best is None or start >= best[0]):
            best = (start, end, qual, node)
    return best


def function_source(rel: str, line: int) -> tuple[str, str | None]:
    hit = enclosing_function(rel, line)
    if not hit:
        return "", None
    start, end, qual, _ = hit
    return "\n".join(file_lines(rel)[start - 1:end]), qual


def function_docstring(rel: str, line: int) -> str:
    hit = enclosing_function(rel, line)
    if not hit:
        return ""
    try:
        return ast.get_docstring(hit[3]) or ""
    except Exception:
        return ""


def inline_statement(rel: str, line: int) -> str:
    """The physical line, joined with its continuation lines when it is a bracket opener."""
    lines = file_lines(rel)
    if not (1 <= line <= len(lines)):
        return ""
    text, i = lines[line - 1], line
    while (i < len(lines) and text.count("(") > text.count(")") + text.count(")") * 0
           and i < line + 6):
        if text.count("(") <= text.count(")") and text.count("[") <= text.count("]"):
            break
        text += " " + lines[i].strip()
        i += 1
    return text


def enclosing_statement(rel: str, line: int):
    """Smallest AST statement containing the line, plus its parents chain."""
    tree, parents, _, _ = ast_index(rel)
    if tree is None:
        return None, parents
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and getattr(node, "lineno", None) and \
                node.lineno <= line <= getattr(node, "end_lineno", node.lineno):
            if best is None or ((getattr(node, "end_lineno", node.lineno) - node.lineno) <
                                (getattr(best, "end_lineno", best.lineno) - best.lineno)):
                best = node
    return best, parents


def enclosing_except(rel: str, line: int):
    tree, _, _, _ = ast_index(rel)
    if tree is None:
        return None
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and \
                node.lineno <= line <= getattr(node, "end_lineno", node.lineno):
            if best is None or node.lineno >= best.lineno:
                best = node
    return best


def iter_source_files():
    """Source files only (never evidence JSON, never the docs tree)."""
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel.startswith("tools/m34/"):
            continue                      # the analyser must not analyse its own patterns
        if path.suffix == ".py" or rel.startswith(".github/") or rel == "pyproject.toml":
            yield rel
