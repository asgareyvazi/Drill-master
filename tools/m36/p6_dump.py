#!/usr/bin/env python3
"""M36 / P6 - reading list for one batch.

usage: python tools/m36/p6_dump.py p6-batch-002 [limit]

Prints, per record: identity, rule/kind/priority/class, the question the register asks, the trigger
line, the current source window, the enclosing definition with its signature and docstring, whether
the enclosing symbol is referenced elsewhere in the repository, and the recorded evidence fields.
Nothing is decided here.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"


def _refs(symbol: str) -> list[str]:
    if not symbol:
        return []
    hits = subprocess.run(["grep", "-rn", "--include=*.py", "-w", symbol, "."],
                          cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    out = []
    for line in hits:
        if re.match(rf"\s*(def|class)\s+{re.escape(symbol)}\b", line.split(":", 2)[-1]):
            continue
        out.append(line)
    return out


def _enclosing(rel: str, line: int):
    src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if best is None or node.lineno >= best.lineno:
                    best = node
    body = src.splitlines()
    if best is None:
        return None, body
    end = best.body[0].lineno - 1 if best.body else best.lineno
    signature = " ".join(x.strip() for x in body[best.lineno - 1:end])
    doc = ast.get_docstring(best) or ""
    return (best.name, best.lineno, signature, doc), body


def main() -> int:
    batch = sys.argv[1] if len(sys.argv) > 1 else "p6-batch-002"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    selected = [r for r in register["records"] if r.get("p6_batch") == batch][:limit]
    if not selected:
        print(f"no records for {batch}")
        return 1
    cache: dict[str, list[str]] = {}
    for record in selected:
        rel, line = record["file"], record["line"]
        info, body = _enclosing(rel, line)
        symbol = (record.get("symbol") or "").split(".")[-1]
        if symbol and symbol not in cache:
            cache[symbol] = _refs(symbol)
        print("=" * 100)
        print(f"{record['id']}  {rel}:{line}  [{record['rule']} / {record['kind']} / "
              f"{record['priority']} / class {record['p6_class']}]")
        print(f"symbol: {record.get('symbol')}   refs_elsewhere: {len(cache.get(symbol, []))}")
        for ref in cache.get(symbol, [])[:3]:
            print(f"    ref: {ref[:130]}")
        print(f"Q: {record.get('question')}")
        print(f"MISSING: {record.get('missing_fact')}")
        print(f"TRIGGER: {record.get('trigger')!r}   current_line: {record.get('current_source_line')!r}")
        quote = record.get("contract_quote")
        if quote:
            text = quote if isinstance(quote, str) else json.dumps(quote, ensure_ascii=False)
            print(f"CONTRACT QUOTED IN REGISTER: {text[:220]}")
        if info:
            name, lineno, signature, doc = info
            print(f"ENCLOSING: {name} (line {lineno})  {signature[:200]}")
            if doc:
                print(f"DOC: {' '.join(doc.split())[:200]}")
        lo, hi = max(1, line - 6), min(len(body), line + 4)
        for n in range(lo, hi + 1):
            print(("  >>" if n == line else "    ") + f"{n:6d} {body[n - 1][:145]}")
    print("=" * 100)
    print(f"{batch}: {len(selected)} record(s) dumped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
