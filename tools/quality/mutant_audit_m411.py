#!/usr/bin/env python3
"""M411: audit of a mutation catalogue — for every mutant, the mutated symbol, the injected defect and the FIRST test
that kills it.

Uses the same scratch-copy engine as ``tools/quality/mutation_m46.py``. Each mutant is applied in a scratch copy of
the working tree and its listed tests are run with ``-x -rf``, which stops at the first failure. The first ``FAILED``
node id is recorded as the killing test. The mutated symbol is the innermost ``def`` / ``class`` that encloses the
first line of the mutated snippet (or ``<module>``). The audit re-executes every mutant, so it is also an independent
re-run of the catalogue. Its counts are reported as such, and a SURVIVED mutant is reported, never hidden.

Usage::

    python tools/quality/mutant_audit_m411.py --catalogue mutation_m361_m400 [--out FILE.md] [--json FILE]
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mutation_m46 as engine  # noqa: E402

REPO = HERE.parents[1]


def enclosing_symbol(source: str, snippet: str) -> str:
    offset = source.index(snippet)
    line = source.count("\n", 0, offset) + 1
    best, best_span = "<module>", None
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= line <= end and (best_span is None or end - node.lineno < best_span):
                best, best_span = node.name, end - node.lineno
    return f"{best} (l.{line})"


def first_failure(copy: Path, tests: list, timeout: int = 900) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "pytest", "-x", "-q", "-rf", "-p", "no:cacheprovider", "-p", "no:randomly",
           "--tb=no", *tests]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        proc = subprocess.run(cmd, cwd=copy, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    # "-rf" lines read "FAILED <nodeid> - <message>"; a parametrised node id may itself contain spaces
    failed = [ln.split(" ", 1)[1].split(" - ", 1)[0] for ln in proc.stdout.splitlines()
              if ln.startswith(("FAILED ", "ERROR "))]
    return proc.returncode, failed[0] if failed else ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalogue", required=True, help="module name in tools/quality defining MUTANTS")
    parser.add_argument("--out")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    mutants = importlib.import_module(args.catalogue).MUTANTS
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO,
                                capture_output=True, text=True).stdout.strip())
    rows, started = [], time.time()
    with tempfile.TemporaryDirectory(prefix="mutant_audit_") as tmp:
        copy = Path(tmp) / "repo"
        engine._copy_worktree(copy)
        for m in mutants:
            target = copy / m.path
            original = target.read_text(encoding="utf-8")
            if original.count(m.old) != 1:
                rows.append({"id": m.id, "path": m.path, "symbol": "-", "defect": m.note, "status": "INVALID",
                             "killing_test": ""})
                continue
            symbol = enclosing_symbol(original, m.old)
            target.write_text(original.replace(m.old, m.new), encoding="utf-8")
            try:
                code, killer = first_failure(copy, m.tests)
            finally:
                target.write_text(original, encoding="utf-8")
            status = "KILLED" if code != 0 else "SURVIVED"
            rows.append({"id": m.id, "path": m.path, "symbol": symbol, "defect": m.note, "status": status,
                         "killing_test": killer if status == "KILLED" else "", "exit": code,
                         "equivalent": m.equivalent})
            print(f"{m.id:32s} {status:8s} {killer}", flush=True)
    killed = sum(r["status"] == "KILLED" for r in rows)
    summary = (f"{args.catalogue}: {len(rows)} mutants, {killed} killed, "
               f"{sum(r['status'] == 'SURVIVED' for r in rows)} survived, "
               f"{sum(r['status'] == 'INVALID' for r in rows)} invalid; SHA {sha}{' (DIRTY TREE)' if dirty else ''}; "
               f"{time.time() - started:.0f} s")
    print(summary)
    if args.out:
        lines = [f"# M411 mutant audit — `{args.catalogue}`", "", summary, "",
                 "| # | Mutant | File | Mutated symbol | Injected defect | Result | First killing test |",
                 "|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            lines.append(f"| {i} | `{r['id']}` | `{r['path']}` | `{r['symbol']}` | {r['defect']} | {r['status']} | "
                         f"`{r['killing_test']}` |")
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    return 0 if killed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
