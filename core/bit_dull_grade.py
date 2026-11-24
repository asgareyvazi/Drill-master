"""M427: structured IADC dull-grade record, validation and per-well trend - no wear prediction.

RECORD. The IADC dull grading system (roller-cone: IADC 1987 revision; fixed-cutter: IADC/SPE 23939, 1992) records
eight fields, written I-O-D-L-B-G-O-R:

1. Inner cutting structure (I) and 2. outer cutting structure (O): 0 (no wear) to 8 (fully worn), integers.
3. Dull characteristic (D) and 7. other dull characteristic (O): two-letter codes (``DULL_CODES``); roller-cone-only
   codes (``CONE_ONLY``) are refused on a fixed-cutter bit.
4. Location (L): roller cone N / M / G / A or cone numbers 1-3; fixed cutter C / N / T / S / G / A.
5. Bearings / seals (B): roller cone E / F / N (sealed) or 0-8 (open bearing); fixed cutter X.
6. Gauge (G): I (in gauge) or 1-16 sixteenths of an inch out of gauge.
8. Reason pulled (R): ``REASON_CODES``.

The codes are classification facts of the public IADC system; only codes recorded here are accepted (an unknown code
is refused, never mapped to a near match). The record stores what was graded; nothing is inferred from DDR rows (the
M130 bit-run aggregation states that DDR rows carry no dull grade). The trend lists saved grades of a well ordered
by depth out (then date, then save order) - arithmetic and ordering only, no interpretation.

NOT IMPLEMENTED (stated): remaining-life or wear-rate prediction. A predictor needs a validated dull-grade dataset
with formation, operating parameters and run outcomes under usable data rights, and a published method; none is in
the repository (``docs/engineering/DRILLMASTER_ENGINEERING_ROADMAP_M460.md``, N-BIT-1).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

METHOD_ID = "m427.bit_dull_grade"
METHOD_VERSION = "M427 IADC dull grade record v1"
CALCULATOR = "Bit dull grade (IADC)"
LABEL = "RECORD - IADC dull grade as graded by the user; validated against the IADC code set; no wear prediction"
VALID, INVALID, NOT_ASSESSED = "VALID", "INVALID", "NOT ASSESSED"
BIT_TYPES = ("roller-cone", "fixed-cutter")

DULL_CODES = {
    "BC": "broken cone", "BF": "bond failure", "BT": "broken teeth / cutters", "BU": "balled up bit",
    "CC": "cracked cone", "CD": "cone dragged", "CI": "cone interference", "CR": "cored", "CT": "chipped teeth / cutters",
    "DL": "cutter delamination", "ER": "erosion", "FC": "flat crested wear", "HC": "heat checking", "JD": "junk damage",
    "LC": "lost cone", "LM": "lost matrix", "LN": "lost nozzle", "LT": "lost teeth / cutters", "NO": "no dull characteristic",
    "NR": "not rerunnable", "OC": "off-centre wear", "PB": "pinched bit", "PN": "plugged nozzle / flow passage",
    "RG": "rounded gauge", "RO": "ring out", "RR": "rerunnable", "SD": "shirttail damage", "SS": "self-sharpening wear",
    "TR": "tracking", "WO": "washed out bit", "WT": "worn teeth / cutters",
}
CONE_ONLY = {"BC", "CC", "CD", "CI", "LC", "SD", "TR"}
FIXED_CUTTER_ONLY = {"BF", "DL", "LM", "NR", "RR"}
REASON_CODES = {
    "BHA": "change bottomhole assembly", "CM": "condition mud", "CP": "core point", "DMF": "downhole motor failure",
    "DP": "drill plug", "DSF": "drill string failure", "DST": "drill stem test", "DTF": "downhole tool failure",
    "FM": "formation change", "HP": "hole problems", "HR": "hours on bit", "LIH": "left in hole", "LOG": "run logs",
    "PP": "pump pressure", "PR": "penetration rate", "RIG": "rig repair", "TD": "total / casing depth", "TQ": "torque",
    "TW": "twist off", "WC": "weather conditions",
}
LOCATIONS = {"roller-cone": {"N", "M", "G", "A", "1", "2", "3"}, "fixed-cutter": {"C", "N", "T", "S", "G", "A"}}

TEXT_FIELDS = ("bit_no", "bit_type", "inner", "outer", "dull_char", "location", "bearings", "gauge", "other_char",
               "reason_pulled", "date_out")
NUMBER_FIELDS: Tuple[Tuple[str, str], ...] = (("bit_size_in", "in"), ("depth_in_m", "m"), ("depth_out_m", "m"))
REQUIRED = ("bit_no", "bit_type", "inner", "outer", "dull_char", "location", "bearings", "gauge", "other_char",
            "reason_pulled")
UNITS = {**{key: "" for key in TEXT_FIELDS}, **dict(NUMBER_FIELDS)}
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class DullGradeError(ValueError):
    """Inputs that cannot be evaluated (the message says why)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _number(value: Any, key: str) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise DullGradeError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DullGradeError(f"{key} {value!r} is not a number") from exc
    if not math.isfinite(number):
        raise DullGradeError(f"{key} must be finite")
    return number


def freeze(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    unknown = set(inputs) - set(UNITS)
    if unknown:
        raise DullGradeError(f"unknown input(s): {', '.join(sorted(unknown))}")
    frozen: Dict[str, Any] = {}
    for key in TEXT_FIELDS:
        value = inputs.get(key)
        if value is not None and not isinstance(value, str):
            value = str(value)
        value = value.strip() if isinstance(value, str) else None
        if value and key not in ("bit_no", "bit_type", "date_out"):
            value = value.upper()
        frozen[key] = value or None
    for key, _unit in NUMBER_FIELDS:
        frozen[key] = _number(inputs.get(key), key)
    return frozen


def inputs_sha256(frozen: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(frozen), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _scale(value: str, key: str, problems: List[str]) -> Optional[int]:
    if not value.isdigit() or not 0 <= int(value) <= 8:
        problems.append(f"{key} {value!r} must be an integer 0-8")
        return None
    return int(value)


def validate(v: Mapping[str, Any]) -> List[str]:
    """Every rule the record breaks (empty = valid)."""
    problems: List[str] = []
    bit_type = v["bit_type"]
    if bit_type not in BIT_TYPES:
        return [f"bit type {bit_type!r} is not one of {', '.join(BIT_TYPES)}"]
    _scale(v["inner"], "inner rows (I)", problems)
    _scale(v["outer"], "outer rows (O)", problems)
    for key, label in (("dull_char", "dull characteristic (D)"), ("other_char", "other characteristic (O)")):
        code = v[key]
        if code not in DULL_CODES:
            problems.append(f"{label} {code!r} is not an IADC dull characteristic code")
        elif bit_type == "fixed-cutter" and code in CONE_ONLY:
            problems.append(f"{label} {code} ({DULL_CODES[code]}) applies to roller-cone bits only")
        elif bit_type == "roller-cone" and code in FIXED_CUTTER_ONLY:
            problems.append(f"{label} {code} ({DULL_CODES[code]}) applies to fixed-cutter bits only")
    location = v["location"]
    allowed = LOCATIONS[bit_type]
    if bit_type == "roller-cone" and location.isdigit():
        if not set(location) <= {"1", "2", "3"} or len(set(location)) != len(location):
            problems.append(f"location {location!r}: cone numbers are 1, 2 or 3, each once")
    elif location not in allowed:
        problems.append(f"location {location!r} is not one of {', '.join(sorted(allowed))} for a {bit_type} bit")
    bearings = v["bearings"]
    if bit_type == "fixed-cutter":
        if bearings != "X":
            problems.append(f"bearings / seals {bearings!r}: a fixed-cutter bit is graded X")
    elif bearings not in {"E", "F", "N"} and not (bearings.isdigit() and 0 <= int(bearings) <= 8):
        problems.append(f"bearings / seals {bearings!r}: E, F, N (sealed) or 0-8 (open bearing)")
    gauge = v["gauge"]
    if gauge != "I" and not (gauge.isdigit() and 1 <= int(gauge) <= 16):
        problems.append(f"gauge {gauge!r}: I (in gauge) or 1-16 sixteenths of an inch out of gauge")
    if v["reason_pulled"] not in REASON_CODES:
        problems.append(f"reason pulled {v['reason_pulled']!r} is not an IADC reason-pulled code")
    for key in ("depth_in_m", "depth_out_m", "bit_size_in"):
        if v[key] is not None and v[key] < 0:
            problems.append(f"{key} cannot be negative")
    if v["bit_size_in"] is not None and v["bit_size_in"] == 0:
        problems.append("bit size 0 is not a bit size")
    if v["depth_in_m"] is not None and v["depth_out_m"] is not None and v["depth_out_m"] < v["depth_in_m"]:
        problems.append("depth out is shallower than depth in")
    if v["date_out"] is not None and not DATE.fullmatch(v["date_out"]):
        problems.append(f"date out {v['date_out']!r} must be YYYY-MM-DD")
    return problems


def evaluate(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    v = freeze(inputs)
    base = {"label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v), "method_version": METHOD_VERSION}
    missing = [key for key in REQUIRED if v[key] is None]
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", **base}
    problems = validate(v)
    grade = "-".join(v[key] for key in ("inner", "outer", "dull_char", "location", "bearings", "gauge", "other_char",
                                        "reason_pulled"))
    if problems:
        return {"status": INVALID, "reason": "; ".join(problems), "problems": problems, "grade": grade, **base}
    footage = (v["depth_out_m"] - v["depth_in_m"]) if None not in (v["depth_in_m"], v["depth_out_m"]) else None
    return {"status": VALID, **base, "grade": grade, "problems": [], "footage_m": footage,
            "dull_meaning": DULL_CODES[v["dull_char"]], "other_meaning": DULL_CODES[v["other_char"]],
            "reason_meaning": REASON_CODES[v["reason_pulled"]],
            "reason": f"IADC grade {grade} validated for a {v['bit_type']} bit"}


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") == NOT_ASSESSED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    if result.get("status") == INVALID:
        return [f"INVALID grade {result['grade']}:"] + [f"  - {p}" for p in result["problems"]] + [LABEL]
    v = result["inputs"]
    lines = [LABEL, f"Bit {v['bit_no']} ({v['bit_type']}): {result['grade']}",
             f"Dull {v['dull_char']} = {result['dull_meaning']}; other {v['other_char']} = {result['other_meaning']}; "
             f"pulled {v['reason_pulled']} = {result['reason_meaning']}."]
    lines.append(f"Footage {result['footage_m']:g} m." if result["footage_m"] is not None
                 else "Footage NOT ASSESSED (depth in or out not entered).")
    lines.append("Remaining-life prediction: NOT IMPLEMENTED (no validated dataset or method).")
    return lines


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    v = result["inputs"]
    inputs: Dict[str, Any] = {key: {"value": v[key], "unit": UNITS[key], "label": key,
                                    "source": "DECLARED" if v[key] is not None else "NOT_ENTERED"} for key in UNITS}
    inputs["inputs_sha256"] = {"value": result["inputs_sha256"], "unit": "", "label": "inputs SHA-256"}
    results: Dict[str, Any] = {"status": {"value": result["status"], "label": result.get("reason") or LABEL}}
    if result["status"] == VALID:
        results["grade"] = {"value": result["grade"], "label": "IADC I-O-D-L-B-G-O-R"}
        results["footage_m"] = {"value": result["footage_m"], "unit": "m", "label": "depth out - depth in"}
    return inputs, results


def unit_of(key: str) -> str:
    return "m" if key == "footage_m" else ""


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != VALID:
        raise ValueError(f"Nothing to store: the grade is {result.get('status')} ({result.get('reason')}).")
    if well_id is None:
        raise ValueError("Nothing to store: a dull grade belongs to a well and no well is selected.")
    inputs, results = case_payload(result)
    v = result["inputs"]
    return cc.save_case(db, calculator=CALCULATOR, name=f"Dull grade bit {v['bit_no']}: {result['grade']}",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; inputs SHA-256 {result['inputs_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    if inputs_sha256(freeze(values)) != (inputs.get("inputs_sha256") or {}).get("value"):
        raise IntegrityError("the stored dull-grade inputs fail their SHA-256 check")
    return case_payload(evaluate(values))[1]


def trend(db, well_id: int) -> List[Dict[str, Any]]:
    """Saved grades of one well, ordered by depth out, date out, then case id (ordering only, no interpretation)."""
    from core import calculation_cases as cc

    rows = []
    for full in cc.list_cases(db, calculator=CALCULATOR, well_id=well_id):
        if full.get("method") != METHOD_ID:
            continue
        values = {key: ((full.get("inputs") or {}).get(key) or {}).get("value") for key in UNITS}
        rows.append({"case_id": full["id"], "bit_no": values["bit_no"], "bit_type": values["bit_type"],
                     "depth_in_m": values["depth_in_m"], "depth_out_m": values["depth_out_m"],
                     "date_out": values["date_out"],
                     "grade": ((full.get("results") or {}).get("grade") or {}).get("value"),
                     "inner": values["inner"], "outer": values["outer"]})
    return sorted(rows, key=lambda r: (r["depth_out_m"] is None, r["depth_out_m"] or 0.0, r["date_out"] or "",
                                       r["case_id"]))
