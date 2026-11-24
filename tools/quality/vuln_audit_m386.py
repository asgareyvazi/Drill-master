"""M386: known-vulnerability check of every pinned runtime dependency in ``requirements-lock.txt``.

Read-only. For each ``name==version`` pin it asks the PyPI JSON API (``https://pypi.org/pypi/<name>/<version>/json``)
for the ``vulnerabilities`` list PyPI publishes from the OSV database, and reports, per package, the advisory ids,
their ``fixed_in`` versions and whether a fix exists. Nothing is installed, upgraded or changed: a finding is
evidence for an owner decision, not a pin change (PySide6 pins in particular need P2 / M378 approval).

A lookup that fails is NOT CHECKED, never "no vulnerabilities". Exit status: 0 when every pin was checked and none
has a published advisory, 1 when an advisory exists, 2 when a pin could not be checked.

Usage: python tools/quality/vuln_audit_m386.py [--lock requirements-lock.txt] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "vuln-audit-m386-v1"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)")
CLEAN, VULNERABLE, NOT_CHECKED = "NO PUBLISHED ADVISORY", "ADVISORY PUBLISHED", "NOT CHECKED"


def parse_lock(text: str) -> List[Dict[str, str]]:
    pins = []
    for line in text.splitlines():
        match = PIN.match(line.strip())
        if match:
            pins.append({"name": match.group(1), "version": match.group(2)})
    return pins


def fetch_pypi(name: str, version: str) -> Dict:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:          # noqa: S310 - fixed https host
        return json.load(response)


def audit(pins: List[Dict[str, str]], fetch: Callable[[str, str], Dict] = fetch_pypi) -> List[Dict]:
    rows = []
    for pin in pins:
        row: Dict = {"name": pin["name"], "version": pin["version"], "advisories": []}
        try:
            data = fetch(pin["name"], pin["version"])
        except (urllib.error.URLError, OSError, ValueError) as exc:
            row.update(state=NOT_CHECKED, reason=f"{type(exc).__name__}: {exc}")
            rows.append(row)
            continue
        vulns = data.get("vulnerabilities")
        if not isinstance(vulns, list):
            row.update(state=NOT_CHECKED, reason="the response has no vulnerabilities list")
            rows.append(row)
            continue
        for v in vulns:
            row["advisories"].append({"id": v.get("id"), "aliases": v.get("aliases") or [],
                                      "fixed_in": v.get("fixed_in") or [], "summary": (v.get("summary") or
                                                                                       v.get("details") or "")[:200],
                                      "withdrawn": v.get("withdrawn")})
        live = [a for a in row["advisories"] if not a["withdrawn"]]
        row.update(state=VULNERABLE if live else CLEAN,
                   reason=f"{len(live)} advisory(ies)" if live else "PyPI lists no advisory for this exact version")
        rows.append(row)
    return rows


def summary(rows: List[Dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        out[row["state"]] = out.get(row["state"], 0) + 1
    return out


def exit_code(rows: List[Dict]) -> int:
    states = {row["state"] for row in rows}
    if NOT_CHECKED in states or not rows:
        return 2
    return 1 if VULNERABLE in states else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lock", default=str(ROOT / "requirements-lock.txt"))
    parser.add_argument("--json", help="write the result here")
    args = parser.parse_args(argv)
    rows = audit(parse_lock(Path(args.lock).read_text(encoding="utf-8")))
    for row in rows:
        ids = ", ".join(f"{a['id']} (fixed in {', '.join(a['fixed_in']) or 'no fix listed'})"
                        for a in row["advisories"] if not a["withdrawn"])
        print(f"{row['name']}=={row['version']:<16} {row['state']}{': ' + ids if ids else ''}")
    print(json.dumps(summary(rows), sort_keys=True))
    if args.json:
        Path(args.json).write_text(json.dumps({"contract": CONTRACT, "lock": Path(args.lock).name, "rows": rows,
                                               "summary": summary(rows)}, indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8")
    return exit_code(rows)


if __name__ == "__main__":
    sys.exit(main())
