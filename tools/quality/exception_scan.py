"""Reproducible inventory of broad and silent exception handlers.

Usage::

    python tools/quality/exception_scan.py                 # summary for the default roots
    python tools/quality/exception_scan.py --json out.json # full per-handler records
    python tools/quality/exception_scan.py --list-silent core

Definitions (AST based, comments and strings are ignored):

* **broad** -- ``except:`` (bare), ``except Exception``, ``except BaseException``,
  or a tuple containing one of those.
* **silent** -- a broad *or narrow* handler whose body neither re-raises, logs,
  reports, records nor returns a value derived from the exception.  In practice:
  the body consists only of ``pass``, ``continue``, ``break``, ``...``, a
  docstring, or ``return``/assignment of a constant (``None``, ``False``, ``0``,
  ``""``, ``[]``, ``{}``) -- with no call at all.  Any call (``logger.x``,
  ``print``, ``QMessageBox``, ``self._fail(...)``) or ``raise`` makes a handler
  not silent: the scanner cannot judge whether that call is adequate, so it
  only reports what is certainly swallowed.

The number of broad handlers alone is not a quality metric: a broad handler at
a UI boundary that logs and shows a message is correct.  The metric that must
go to zero in core/database paths is *unexplained silent suppression*.  A silent
handler is "explained" when the line of the ``except`` or the first line of its
body carries a ``# silent-ok: <reason>`` marker, for a deliberately ignored,
expected condition (for example, best-effort cleanup of a temporary file).
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOTS = ("core", "dialogs", "tabs", "ui", "config", "main_window.py", "app.py", "run.py")
BROAD_NAMES = {"Exception", "BaseException"}
CONSTANT_TYPES = (ast.Constant,)
MARKER = "silent-ok:"


def _is_broad(handler: ast.ExceptHandler) -> bool:
    node = handler.type
    if node is None:
        return True
    candidates = node.elts if isinstance(node, ast.Tuple) else [node]
    return any(isinstance(c, ast.Name) and c.id in BROAD_NAMES for c in candidates) or any(
        isinstance(c, ast.Attribute) and c.attr in BROAD_NAMES for c in candidates
    )


def _is_trivial_value(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, CONSTANT_TYPES):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and not node.elts:
        return True
    if isinstance(node, ast.Dict) and not node.keys:
        return True
    return False


def _is_silent(handler: ast.ExceptHandler) -> bool:
    for stmt in handler.body:
        if isinstance(stmt, (ast.Pass, ast.Continue, ast.Break)):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # docstring or bare ``...``
        if isinstance(stmt, ast.Return) and _is_trivial_value(stmt.value):
            continue
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and _is_trivial_value(stmt.value):
            continue
        return False
    return True


def _explained(lines: list[str], handler: ast.ExceptHandler) -> bool:
    candidates = [handler.lineno]
    if handler.body:
        candidates.append(handler.body[0].lineno)
    return any(MARKER in lines[n - 1] for n in candidates if 0 < n <= len(lines))


def scan_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:  # report, never hide
        return [{"file": str(path), "line": exc.lineno or 0, "kind": "syntax-error"}]
    lines = text.splitlines()
    records = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            broad = _is_broad(node)
            silent = _is_silent(node)
            records.append({
                "file": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
                "line": node.lineno,
                "bare": node.type is None,
                "broad": broad,
                "silent": silent,
                "explained": silent and _explained(lines, node),
            })
    return records


def iter_files(roots: list[str]):
    for root in roots:
        p = (ROOT / root) if not Path(root).is_absolute() else Path(root)
        if p.is_file() and p.suffix == ".py":
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*.py")):
                if "__pycache__" not in f.parts:
                    yield f


def summarize(records: list[dict]) -> dict:
    def area(rec):
        return rec["file"].split("/", 1)[0] if "/" in rec["file"] else rec["file"]
    out = {
        "handlers": len(records),
        "broad": sum(r.get("broad", False) for r in records),
        "bare": sum(r.get("bare", False) for r in records),
        "silent": sum(r.get("silent", False) for r in records),
        "silent_broad": sum(r.get("silent", False) and r.get("broad", False) for r in records),
        "silent_unexplained": sum(r.get("silent", False) and not r.get("explained") for r in records),
        "by_area": {},
    }
    areas = Counter(area(r) for r in records)
    for name in sorted(areas):
        rs = [r for r in records if area(r) == name]
        out["by_area"][name] = {
            "handlers": len(rs),
            "broad": sum(r.get("broad", False) for r in rs),
            "silent": sum(r.get("silent", False) for r in rs),
            "silent_unexplained": sum(r.get("silent", False) and not r.get("explained") for r in rs),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_ROOTS))
    parser.add_argument("--json", type=Path, help="write per-handler records and the summary")
    parser.add_argument("--list-silent", action="store_true", help="print unexplained silent handlers")
    parser.add_argument("--check", type=Path, metavar="CEILING_JSON",
                        help="fail (exit 1) if unexplained silent handlers exceed the ceiling")
    args = parser.parse_args(argv)
    records = [r for f in iter_files(args.roots) for r in scan_file(f)]
    summary = summarize(records)
    if any(r.get("kind") == "syntax-error" for r in records):
        print("exception scan: unparsable file(s): " + ", ".join(
            f"{r['file']}:{r['line']}" for r in records if r.get("kind") == "syntax-error"))
        return 2
    print(json.dumps({k: v for k, v in summary.items() if k != "by_area"}, sort_keys=True))
    for name, values in summary["by_area"].items():
        print(f"  {name}: {values}")
    if args.list_silent:
        for r in records:
            if r.get("silent") and not r.get("explained"):
                print(f"{r['file']}:{r['line']}{' broad' if r['broad'] else ''}")
    if args.json:
        args.json.write_text(json.dumps({"summary": summary, "records": records}, indent=1), encoding="utf-8")
    if args.check:
        violations = check_ceiling(summary, json.loads(args.check.read_text(encoding="utf-8")))
        for line in violations:
            print("exception ceiling exceeded: " + line)
        return 1 if violations else 0
    return 0


def check_ceiling(summary: dict, ceiling: dict) -> list[str]:
    """Compare unexplained silent handlers per area with a ratchet ceiling.

    ``ceiling`` maps ``"total"`` and area names to the maximum allowed count of
    unexplained silent handlers. Areas absent from the ceiling are capped at 0,
    so a new top-level package starts clean. Ceilings may only be lowered.
    """
    areas = ceiling.get("silent_unexplained", {})
    problems = []
    total_cap = areas.get("total")
    if total_cap is not None and summary["silent_unexplained"] > total_cap:
        problems.append(f"total {summary['silent_unexplained']} > {total_cap}")
    for name, values in summary["by_area"].items():
        cap = areas.get(name, 0)
        if values["silent_unexplained"] > cap:
            problems.append(f"{name} {values['silent_unexplained']} > {cap}")
    return problems


if __name__ == "__main__":
    sys.exit(main())
