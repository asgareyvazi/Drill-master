"""M372: drill-off / WOB step test - founder point and per-step MSE (Teale) with drilling efficiency.

SCREENING. The Dupriest & Koederitz workflow (SPE 92194, 2005): at a constant rotary speed, step the weight on bit
up and record the stabilised ROP and torque at each step. While the bit is efficient ROP rises roughly linearly with
WOB; the *founder point* is the step after which the ROP response falls off. MSE (Teale 1965) is computed per step
through the canonical ``MSEEngine``; drilling efficiency is CCS / MSE when a confined compressive strength is declared.

Founder rule (stated, not tuned): steps are sorted by WOB; the slope of each interval is dROP/dWOB (ft/h per klbf);
the reference slope is the first interval's. The founder is the lower step of the first later interval whose slope
is below ``founder_slope_fraction`` x reference. If no interval falls below it the founder is NOT in the tested range
(the highest WOB was still on the linear trend) - a different finding from "not assessed".

Nothing is assumed:
* the bit diameter, the slope fraction and the RPM tolerance are declared inputs (no defaults in the service);
* a step needs WOB, RPM and ROP for the founder and also torque for MSE; a step lacking torque is NOT ASSESSED for
  MSE only. Zero torque is a value (MSE = axial term), an empty cell is not;
* the founder is NOT ASSESSED with fewer than three complete steps, when the RPM varies by more than the declared
  tolerance (the test is not a drill-off test), or when ROP does not rise over the first interval;
* drilling efficiency is NOT ASSESSED without a declared CCS (no rock-strength correlation is applied).
Surface WOB and torque, no downhole correction, no bit-efficiency factor. Not a drilling optimiser.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

METHOD_ID = "m372.mse_drilloff"
METHOD_VERSION = "M372 drill-off founder and step MSE v1"
CALCULATOR = "Drill-off test (founder and MSE)"
LABEL = ("SCREENING - drill-off test founder point (constant RPM, linear-response rule) and per-step Teale MSE from "
         "surface WOB and torque; not a drilling optimiser")
COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"
FOUNDER, NO_FOUNDER = "FOUNDER IDENTIFIED", "NO FOUNDER IN TESTED RANGE"

#: scalar inputs: key, unit, required
FIELDS: Tuple[Tuple[str, str, bool], ...] = (
    ("bit_diameter_in", "in", True), ("founder_slope_fraction", "", True), ("rpm_tolerance_rpm", "rpm", True),
    ("ccs_psi", "psi", False),
)
UNITS = {key: unit for key, unit, _required in FIELDS}
STEP_FIELDS: Tuple[Tuple[str, str], ...] = (("wob_klbf", "klbf"), ("rpm", "rpm"), ("torque_ft_lbf", "ft·lbf"),
                                            ("rop_ft_hr", "ft/h"))
MIN_STEPS = 3


class DrillOffError(ValueError):
    """Inputs that cannot be evaluated (the message says why)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _number(value: Any, key: str) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise DrillOffError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DrillOffError(f"{key} {value!r} is not a number") from exc
    if not math.isfinite(number):
        raise DrillOffError(f"{key} must be finite")
    return number


def freeze(inputs: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Declared inputs as numbers (None = not given); unknown keys are refused; steps keep their entered order."""
    unknown = set(inputs) - set(UNITS)
    if unknown:
        raise DrillOffError(f"unknown input(s): {', '.join(sorted(unknown))}")
    frozen: Dict[str, Any] = {key: _number(inputs.get(key), key) for key in UNITS}
    rows = []
    for index, step in enumerate(steps, start=1):
        extra = set(step) - {key for key, _unit in STEP_FIELDS}
        if extra:
            raise DrillOffError(f"step {index}: unknown field(s) {', '.join(sorted(extra))}")
        row = {key: _number(step.get(key), f"step {index} {key}") for key, _unit in STEP_FIELDS}
        if all(value is None for value in row.values()):
            continue                                                  # an empty table row is not a step
        if any(value is not None and value < 0 for value in row.values()):
            raise DrillOffError(f"step {index}: WOB, RPM, torque and ROP cannot be negative")
        rows.append(row)
    frozen["steps"] = rows
    return frozen


def inputs_sha256(frozen: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(frozen), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _step_mse(step: Mapping[str, Optional[float]], diameter: float, ccs: Optional[float]) -> Dict[str, Any]:
    from core.engineering.engines.mse import MSEEngine

    gaps = [key for key, _unit in STEP_FIELDS if step[key] is None]
    if gaps:
        return {"status": NOT_ASSESSED, "mse_psi": None, "efficiency": None,
                "reason": f"not given: {', '.join(gaps)}"}
    res = MSEEngine.calculate(wob_lbf=step["wob_klbf"] * 1000.0, rpm=step["rpm"], torque_ft_lbf=step["torque_ft_lbf"],
                              rop_ft_hr=step["rop_ft_hr"], bit_diameter_in=diameter)
    if not res.success:
        return {"status": NOT_ASSESSED, "mse_psi": None, "efficiency": None, "reason": res.error or "MSE refused"}
    mse = float(res.value)
    out = {"status": COMPUTED, "mse_psi": mse, "axial_term_psi": res.values["axial_term_psi"],
           "rotary_term_psi": res.values["rotary_term_psi"], "efficiency": None,
           "reason": "Teale MSE (MSEEngine, 120π)"}
    if ccs is None:
        out["efficiency_reason"] = "no CCS declared"
    else:
        out["efficiency"] = ccs / mse
        out["efficiency_reason"] = "CCS / MSE"
    return out


def _founder(steps: List[Dict[str, Any]], fraction: float, tolerance: float) -> Dict[str, Any]:
    usable = [s for s in steps if None not in (s["wob_klbf"], s["rpm"], s["rop_ft_hr"])]
    if len(usable) < MIN_STEPS:
        return {"status": NOT_ASSESSED, "reason": f"{len(usable)} step(s) with WOB, RPM and ROP; at least "
                                                  f"{MIN_STEPS} are needed"}
    rpms = [s["rpm"] for s in usable]
    if max(rpms) - min(rpms) > tolerance:
        return {"status": NOT_ASSESSED, "reason": f"RPM varies {min(rpms):g}-{max(rpms):g} rpm, more than the "
                                                  f"declared tolerance {tolerance:g} rpm: not a drill-off test"}
    slopes = [(b["rop_ft_hr"] - a["rop_ft_hr"]) / (b["wob_klbf"] - a["wob_klbf"])
              for a, b in zip(usable, usable[1:])]
    reference = slopes[0]
    if reference <= 0:
        return {"status": NOT_ASSESSED, "slopes": slopes,
                "reason": "ROP does not rise over the first WOB interval: no linear-response region to refer to"}
    for index, slope in enumerate(slopes[1:], start=1):
        if slope < fraction * reference:
            step = usable[index]
            return {"status": FOUNDER, "wob_klbf": step["wob_klbf"], "rop_ft_hr": step["rop_ft_hr"],
                    "slopes": slopes, "reference_slope": reference,
                    "reason": f"interval {index + 1} slope {slope:.3g} ft/h/klbf < {fraction:g} x reference "
                              f"{reference:.3g}"}
    return {"status": NO_FOUNDER, "wob_klbf": None, "rop_ft_hr": None, "slopes": slopes,
            "reference_slope": reference,
            "reason": f"every interval stays at or above {fraction:g} x the reference slope; the highest tested WOB "
                      f"{usable[-1]['wob_klbf']:g} klbf is still on the linear trend"}


def evaluate(inputs: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    v = freeze(inputs, steps)
    missing = [key for key, _unit, required in FIELDS if required and v[key] is None]
    base = {"label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v)}
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", **base}
    if not v["steps"]:
        return {"status": NOT_ASSESSED, "reason": "no test steps entered", **base}
    if v["bit_diameter_in"] <= 0:
        raise DrillOffError("the bit diameter must be > 0")
    if not 0 < v["founder_slope_fraction"] < 1:
        raise DrillOffError("the founder slope fraction must be between 0 and 1")
    if v["rpm_tolerance_rpm"] < 0:
        raise DrillOffError("the RPM tolerance cannot be negative")
    if v["ccs_psi"] is not None and v["ccs_psi"] <= 0:
        raise DrillOffError("CCS must be > 0 when declared")
    wobs = [s["wob_klbf"] for s in v["steps"] if s["wob_klbf"] is not None]
    if len(set(wobs)) != len(wobs):
        raise DrillOffError("two steps share the same WOB: a step test needs distinct WOB values")
    ordered = sorted(v["steps"], key=lambda s: (s["wob_klbf"] is None, s["wob_klbf"] or 0.0))
    rows = []
    for step in ordered:
        rows.append({**step, **_step_mse(step, v["bit_diameter_in"], v["ccs_psi"])})
    founder = _founder(ordered, v["founder_slope_fraction"], v["rpm_tolerance_rpm"])
    assessed = [r for r in rows if r["status"] == COMPUTED]
    lowest = min(assessed, key=lambda r: r["mse_psi"]) if assessed else None
    return {"status": COMPUTED, **base, "steps": rows, "founder": founder,
            "lowest_mse_wob_klbf": lowest["wob_klbf"] if lowest else None,
            "lowest_mse_psi": lowest["mse_psi"] if lowest else None}


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    lines = [LABEL]
    for row in result["steps"]:
        head = (f"WOB {row['wob_klbf']} klbf, RPM {row['rpm']}, torque {row['torque_ft_lbf']} ft·lbf, "
                f"ROP {row['rop_ft_hr']} ft/h: ")
        if row["status"] == COMPUTED:
            eff = (f"; efficiency {100 * row['efficiency']:.1f} %" if row["efficiency"] is not None
                   else f"; efficiency NOT ASSESSED ({row['efficiency_reason']})")
            lines.append(head + f"MSE {row['mse_psi']:.0f} psi{eff}")
        else:
            lines.append(head + f"MSE NOT ASSESSED ({row['reason']})")
    founder = result["founder"]
    if founder["status"] == FOUNDER:
        lines.append(f"Founder at WOB {founder['wob_klbf']:g} klbf (ROP {founder['rop_ft_hr']:g} ft/h) - "
                     f"{founder['reason']}.")
    else:
        lines.append(f"Founder: {founder['status']} - {founder['reason']}.")
    if result["lowest_mse_psi"] is not None:
        lines.append(f"Lowest MSE {result['lowest_mse_psi']:.0f} psi at WOB {result['lowest_mse_wob_klbf']:g} klbf.")
    return lines


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    v = result["inputs"]
    inputs: Dict[str, Any] = {key: {"value": v[key], "unit": UNITS[key], "label": key,
                                    "source": "DECLARED" if v[key] is not None else "NOT_ENTERED"} for key in UNITS}
    inputs["steps"] = {"value": v["steps"], "unit": "klbf / rpm / ft·lbf / ft/h", "label": "test steps as entered"}
    inputs["inputs_sha256"] = {"value": result["inputs_sha256"], "unit": "", "label": "inputs SHA-256"}
    results: Dict[str, Any] = {"status": {"value": result["status"], "label": result.get("reason") or LABEL}}
    if result["status"] == COMPUTED:
        founder = result["founder"]
        results["founder_status"] = {"value": founder["status"], "label": founder["reason"]}
        results["founder_wob_klbf"] = {"value": founder.get("wob_klbf"), "unit": "klbf", "label": "founder WOB"}
        results["founder_rop_ft_hr"] = {"value": founder.get("rop_ft_hr"), "unit": "ft/h", "label": "founder ROP"}
        for index, row in enumerate(result["steps"], start=1):
            results[f"step{index}_wob_klbf"] = {"value": row["wob_klbf"], "unit": "klbf", "label": f"step {index}"}
            results[f"step{index}_mse_psi"] = {"value": row["mse_psi"], "unit": "psi", "label": row["reason"]}
            results[f"step{index}_efficiency"] = {"value": row["efficiency"], "unit": "",
                                                  "label": row.get("efficiency_reason", row["reason"])}
        results["lowest_mse_psi"] = {"value": result["lowest_mse_psi"], "unit": "psi", "label": "lowest step MSE"}
    return inputs, results


def unit_of(key: str) -> str:
    for suffix, unit in (("_klbf", "klbf"), ("_psi", "psi"), ("_ft_hr", "ft/h")):
        if key.endswith(suffix):
            return unit
    return ""


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != COMPUTED:
        raise ValueError(f"Nothing to store: not computed ({result.get('reason')}).")
    inputs, results = case_payload(result)
    v = result["inputs"]
    return cc.save_case(db, calculator=CALCULATOR,
                        name=f"Drill-off test, {len(v['steps'])} steps, {v['bit_diameter_in']:g} in bit",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; inputs SHA-256 {result['inputs_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    steps = (inputs.get("steps") or {}).get("value") or []
    if not isinstance(steps, list) or inputs_sha256(freeze(values, steps)) != (inputs.get("inputs_sha256") or
                                                                                {}).get("value"):
        raise IntegrityError("the stored drill-off inputs fail their SHA-256 check")
    return case_payload(evaluate(values, steps))[1]
