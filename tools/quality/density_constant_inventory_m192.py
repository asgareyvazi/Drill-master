"""M192: inventory of the pcf <-> ppg conversion constants (7.48 against 7.48052) across the product code.

Read-only. The two constants differ by 0.007 % (7.48052 / 7.48 - 1 = 6.95e-5): 75 pcf is 10.0267 ppg with 7.48
and 10.0260 ppg with 7.48052. Choosing one is an open owner decision (M196). No global change is made here; this
inventory makes every use visible and lets a test notice a silent change of either constant anywhere.

Usage: python tools/quality/density_constant_inventory_m192.py [--write OUT.json] [--check OUT.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ("core", "tabs", "dialogs", "ui", "main_window.py")
CONTRACT = "density-constant-inventory-m192-v1"
# 7.48 not followed by another digit (so 7.481 / 7.4805 are not counted as 7.48), and the two longer forms.
PATTERNS = {"7.48": re.compile(r"(?<![\d.])7\.48(?!\d)"), "7.4805": re.compile(r"(?<![\d.])7\.4805(?!\d)"),
            "7.48052": re.compile(r"(?<![\d.])7\.48052(?!\d)")}


def _files():
    for scope in SCOPES:
        path = ROOT / scope
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)


def inventory() -> dict:
    sites = []
    for path in _files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name, pattern in PATTERNS.items():
                for _match in pattern.finditer(line):
                    sites.append({"file": str(path.relative_to(ROOT)), "line": number, "constant": name,
                                  "text": line.strip()[:160]})
    totals = {name: sum(1 for s in sites if s["constant"] == name) for name in PATTERNS}
    by_file = {}
    for site in sites:
        by_file.setdefault(site["file"], {}).setdefault(site["constant"], 0)
        by_file[site["file"]][site["constant"]] += 1
    return {"contract": CONTRACT, "scopes": list(SCOPES), "totals": totals, "by_file": dict(sorted(by_file.items())),
            "relative_difference": 7.48052 / 7.48 - 1.0, "sites": sites}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write")
    parser.add_argument("--check")
    args = parser.parse_args(argv)
    data = inventory()
    if args.write:
        Path(args.write).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"totals": data["totals"], "files": len(data["by_file"])}))
    if args.check:
        stored = json.loads(Path(args.check).read_text(encoding="utf-8"))
        if stored["by_file"] != data["by_file"]:
            print("the density-constant inventory changed; review and re-write it", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
