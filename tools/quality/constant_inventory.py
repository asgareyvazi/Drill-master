"""M113: inventory of unit-conversion constants in the product code (read-only; changes no value).

For each physical quantity the literal variants found in ``core``, ``tabs`` and ``dialogs`` are counted per
file (comments excluded).  Several variants of the same quantity are reported as an INCONSISTENCY with the
relative difference; whether one value becomes authoritative is an owner decision (M112 pack "7.48 vs
7.48052").  A change would be a new method version — stored records keep the version they were computed
with and are never relabelled.

``--write`` stores ``docs/engineering/constant_inventory.json``; ``--check`` exits 1 when it is stale.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import tokenize
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "engineering" / "constant_inventory.json"
INVENTORY_VERSION = "M113 constant inventory v1"
DIRS = ("core", "tabs", "dialogs")

#: quantity -> (unit statement, {variant literal: exact value it stands for})
QUANTITIES: Dict[str, Dict[str, Any]] = {
    "pcf per ppg (gal per ft³)": {"exact": 7.480519480519481, "variants": ["7.48052", "7.4805", "7.48"]},
    "ft³ per bbl": {"exact": 5.614583333333333, "variants": ["5.6146", "5.615", "0.1781"],
                    "note": "0.1781 = bbl per ft³ (1/5.6146)"},
    "gal per bbl": {"exact": 42.0, "variants": ["42.0"], "note": "only 42.0 literals are counted (bare 42 is ambiguous)"},
    "psi/ft per ppg": {"exact": 0.051948, "variants": ["0.052"]},
    "psi/ft per pcf": {"exact": 1 / 144, "variants": ["0.006944", "144.0"], "note": "144.0 = in² per ft²"},
    "ft per m": {"exact": 1 / 0.3048, "variants": ["3.28084", "0.3048"], "note": "0.3048 = m per ft"},
    "bbl/ft capacity constant (in²)": {"exact": 1029.4, "variants": ["1029.4"]},
    "mm per in": {"exact": 25.4, "variants": ["25.4"]},
    "m per 100 ft (DLS °/100 ft ↔ °/30 m)": {"exact": 30.48, "variants": ["30.48"]},
    "°F per °C": {"exact": 1.8, "variants": ["1.8"], "note": "1.8 also appears in non-temperature uses; see files"},
    "psi per bar / kPa": {"exact": 14.503773773, "variants": ["14.5038", "6.894"], "note": "6.894 = kPa per psi"},
    "lb per kg": {"exact": 2.2046226218, "variants": ["2.20462"]},
    "fresh water density": {"exact": 8.3454, "variants": ["8.33", "62.4"],
                            "note": "8.33 ppg ≈ 62.31 pcf vs 62.4 pcf ≈ 8.342 ppg"},
}


#: conventions found by name in the source text (labels and field names; both units in use is not a defect
#: by itself — every value must carry its unit, and nothing may compare across them without conversion)
CONVENTIONS: Dict[str, Dict[str, str]] = {
    "cost per length": {"per metre": r"cost_per_(?:m|meter|metre)\b", "per foot": r"cost_per_(?:ft|foot)\b"},
    "dog-leg severity unit": {"°/30 m": r"(?:deg|°) ?/ ?30 ?m", "°/100 ft": r"(?:deg|°) ?/ ?100 ?ft"},
    "temperature unit": {"°C": r"°C|degC", "°F": r"°F|degF"},
}


def _code_tokens(text: str) -> List[str]:
    """NUMBER tokens of the source (comments and strings excluded)."""
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.NUMBER:
                out.append(tok.string)
    except (tokenize.TokenError, IndentationError):  # silent-ok: unparsable file contributes no tokens
        return out
    return out


def _canon(literal: str) -> str:
    s = literal.replace("_", "").lower()
    if re.fullmatch(r"\d+\.\d*0+", s):
        s = s.rstrip("0")
    return s


def scan(root: Path = ROOT) -> Dict[str, Any]:
    files = [p for d in DIRS for p in sorted((root / d).rglob("*.py"))]
    tokens = {p.relative_to(root).as_posix(): [_canon(t) for t in _code_tokens(p.read_text(encoding="utf-8"))]
              for p in files}
    result: Dict[str, Any] = {}
    for quantity, spec in QUANTITIES.items():
        variants = {}
        for literal in spec["variants"]:
            want = _canon(literal)
            per_file = {f: toks.count(want) for f, toks in tokens.items() if toks.count(want)}
            variants[literal] = {"value": float(literal), "uses": sum(per_file.values()), "files": per_file}
        used = [v for v, info in variants.items() if info["uses"]]
        entry = {"exact": spec["exact"], "variants": variants, "note": spec.get("note", "")}
        same_meaning = [v for v in used if abs(float(v) - spec["exact"]) / spec["exact"] < 0.05]
        if len(same_meaning) > 1:
            values = [float(v) for v in same_meaning]
            entry["inconsistency"] = {"variants": same_meaning,
                                      "max_relative_difference": round((max(values) - min(values)) / min(values), 8)}
        result[quantity] = entry
    texts = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in files}
    conventions = {}
    for name, variants in CONVENTIONS.items():
        conventions[name] = {}
        for label, pattern in variants.items():
            per_file = {f: len(re.findall(pattern, t)) for f, t in texts.items() if re.search(pattern, t)}
            conventions[name][label] = {"uses": sum(per_file.values()), "files": per_file}
    return {"version": INVENTORY_VERSION, "quantities": result, "conventions": conventions,
            "inconsistent": sorted(q for q, e in result.items() if "inconsistency" in e)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    result = scan()
    text = json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if args.write:
        OUT.write_text(text, encoding="utf-8")
    for q, e in result["quantities"].items():
        uses = ", ".join(f"{v}×{i['uses']}" for v, i in e["variants"].items())
        flag = "  INCONSISTENT" if "inconsistency" in e else ""
        print(f"{q}: {uses}{flag}")
    if args.check and (not OUT.exists() or OUT.read_text(encoding="utf-8") != text):
        print("constant_inventory.json is stale (run --write)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
