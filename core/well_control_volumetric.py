"""M373: volumetric method worksheet and gas-migration rate - TRAINING AID (P11).

TRAINING AID - NOT FOR OPERATIONAL WELL CONTROL. The textbook volumetric method (IWCF / IADC well-control manuals;
Grace, *Advanced Blowout and Well Control*): with the well shut in, circulation impossible and gas migrating, let the
casing pressure rise by a safety margin plus a working range, then bleed mud at a constant casing pressure until the
lost hydrostatic equals the working range, and repeat. Oilfield units (psi, ft, bbl):

* mud gradient            G = rho / 144            [psi/ft, rho in lb/ft^3 - exact, no gallon conversion]
* hydrostatic per barrel  H = G / C                [psi/bbl, C = annular capacity at the bubble, bbl/ft]
* volume per cycle        dV = Pw / H = Pw C / G   [bbl]
* cycle k (k = 1..n)      let the casing rise to P_k = SICP + Ps + k Pw, then bleed dV holding P_k;
                          cumulative bled volume k dV
* migration rate          v = (dP / dt) / G        [ft/h, from an observed shut-in pressure rise]

Nothing is assumed: SICP, mud density, the annular capacity at the bubble, the safety margin, the working range and
the number of cycles to tabulate are declared. A declared casing-pressure limit (e.g. MAASP) marks the first cycle
that would exceed it and the schedule STOPS there - a TRAINING AID never tabulates past a declared limit. The
migration rate is NOT ASSESSED unless both the observed rise and its duration are given; a zero rise is a value.
Single bubble, constant annular capacity, no gas expansion law, no temperature or z-factor, no lubricate-and-bleed
phase (NOT IMPLEMENTED), no choke or kill-line friction.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

METHOD_ID = "m373.volumetric_method"
METHOD_VERSION = "M373 volumetric method worksheet v1"
CALCULATOR = "Volumetric method (TRAINING AID)"
LABEL = ("TRAINING AID - NOT FOR OPERATIONAL WELL CONTROL (P11): volumetric-method bleed schedule, single bubble, constant "
         "annular capacity, no gas law, no lubricate-and-bleed")
COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"
WITHIN, EXCEEDS, NO_LIMIT = "WITHIN DECLARED LIMIT", "EXCEEDS DECLARED LIMIT - STOP", "NO LIMIT DECLARED"
PSI_PER_FT_PER_PCF = 1.0 / 144.0     # 1 lb/ft^3 over 1 ft of height on 144 in^2
MAX_CYCLES = 50

FIELDS: Tuple[Tuple[str, str, bool], ...] = (
    ("sicp_psi", "psi", True), ("mud_density_pcf", "pcf", True), ("annular_capacity_bbl_ft", "bbl/ft", True),
    ("safety_margin_psi", "psi", True), ("working_range_psi", "psi", True), ("cycles", "", True),
    ("casing_limit_psi", "psi", False), ("pressure_rise_psi", "psi", False), ("rise_duration_h", "h", False),
)
UNITS = {key: unit for key, unit, _required in FIELDS}


class VolumetricError(ValueError):
    """Inputs that cannot be evaluated (the message says why)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _number(inputs: Mapping[str, Any], key: str) -> Optional[float]:
    value = inputs.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise VolumetricError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VolumetricError(f"{key} {value!r} is not a number") from exc
    if not math.isfinite(number):
        raise VolumetricError(f"{key} must be finite")
    return number


def freeze(inputs: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    unknown = set(inputs) - set(UNITS)
    if unknown:
        raise VolumetricError(f"unknown input(s): {', '.join(sorted(unknown))}")
    return {key: _number(inputs, key) for key in UNITS}


def inputs_sha256(values: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(values), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _migration(v: Mapping[str, Optional[float]], gradient: float) -> Dict[str, Any]:
    gaps = [k for k in ("pressure_rise_psi", "rise_duration_h") if v[k] is None]
    if gaps:
        return {"status": NOT_ASSESSED, "value": None, "reason": f"not given: {', '.join(gaps)}"}
    if v["pressure_rise_psi"] < 0 or v["rise_duration_h"] <= 0:
        raise VolumetricError("the observed pressure rise cannot be negative and its duration must be > 0")
    rate = v["pressure_rise_psi"] / v["rise_duration_h"]
    return {"status": COMPUTED, "value": rate / gradient, "pressure_rate_psi_h": rate,
            "reason": "(dP/dt) / mud gradient"}


def evaluate(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    v = freeze(inputs)
    base = {"label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v)}
    missing = [key for key, _unit, required in FIELDS if required and v[key] is None]
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", **base}
    if v["sicp_psi"] < 0 or v["safety_margin_psi"] < 0:
        raise VolumetricError("SICP and the safety margin cannot be negative")
    if v["mud_density_pcf"] <= 0 or v["annular_capacity_bbl_ft"] <= 0 or v["working_range_psi"] <= 0:
        raise VolumetricError("mud density, annular capacity and working range must be > 0")
    cycles = v["cycles"]
    if cycles != int(cycles) or not 1 <= cycles <= MAX_CYCLES:
        raise VolumetricError(f"cycles must be a whole number from 1 to {MAX_CYCLES}")
    limit = v["casing_limit_psi"]
    if limit is not None and limit <= 0:
        raise VolumetricError("the casing-pressure limit must be > 0 when declared")
    gradient = v["mud_density_pcf"] * PSI_PER_FT_PER_PCF
    per_bbl = gradient / v["annular_capacity_bbl_ft"]
    volume = v["working_range_psi"] / per_bbl
    schedule: List[Dict[str, Any]] = []
    stopped = None
    for k in range(1, int(cycles) + 1):
        hold = v["sicp_psi"] + v["safety_margin_psi"] + k * v["working_range_psi"]
        state = NO_LIMIT if limit is None else (WITHIN if hold <= limit else EXCEEDS)
        schedule.append({"cycle": k, "hold_casing_psi": hold, "bleed_bbl": volume, "cumulative_bbl": k * volume,
                         "state": state})
        if state == EXCEEDS:
            stopped = k
            break
    return {"status": COMPUTED, **base, "gradient_psi_ft": gradient, "hydrostatic_psi_per_bbl": per_bbl,
            "volume_per_cycle_bbl": volume, "schedule": schedule, "stopped_at_cycle": stopped,
            "migration": _migration(v, gradient)}


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    lines = [LABEL, f"Mud gradient {result['gradient_psi_ft']:.4f} psi/ft; {result['hydrostatic_psi_per_bbl']:.2f} "
                    f"psi per bbl at the bubble; bleed {result['volume_per_cycle_bbl']:.2f} bbl per cycle."]
    for row in result["schedule"]:
        lines.append(f"Cycle {row['cycle']}: let casing rise to {row['hold_casing_psi']:.0f} psi, bleed "
                     f"{row['bleed_bbl']:.2f} bbl holding it (cumulative {row['cumulative_bbl']:.2f} bbl) - "
                     f"{row['state']}")
    if result["stopped_at_cycle"]:
        lines.append(f"STOP: cycle {result['stopped_at_cycle']} would exceed the declared casing limit "
                     f"{result['inputs']['casing_limit_psi']:g} psi - escalate; this aid tabulates no further.")
    mig = result["migration"]
    lines.append(f"Gas migration {mig['value']:.0f} ft/h ({mig['reason']})." if mig["status"] == COMPUTED
                 else f"Gas migration: NOT ASSESSED - {mig['reason']}.")
    return lines


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    v = result["inputs"]
    inputs: Dict[str, Any] = {key: {"value": v[key], "unit": UNITS[key], "label": key,
                                    "source": "DECLARED" if v[key] is not None else "NOT_ENTERED"} for key in UNITS}
    inputs["inputs_sha256"] = {"value": result["inputs_sha256"], "unit": "", "label": "inputs SHA-256"}
    results: Dict[str, Any] = {"status": {"value": result["status"], "label": result.get("reason") or LABEL}}
    if result["status"] == COMPUTED:
        results["volume_per_cycle_bbl"] = {"value": result["volume_per_cycle_bbl"], "unit": "bbl",
                                           "label": "Pw x C / G"}
        results["hydrostatic_psi_per_bbl"] = {"value": result["hydrostatic_psi_per_bbl"], "unit": "psi/bbl",
                                              "label": "G / C"}
        for row in result["schedule"]:
            results[f"cycle{row['cycle']}_hold_psi"] = {"value": row["hold_casing_psi"], "unit": "psi",
                                                        "label": row["state"]}
        results["stopped_at_cycle"] = {"value": result["stopped_at_cycle"], "unit": "",
                                       "label": "first cycle above the declared limit"}
        mig = result["migration"]
        results["migration_ft_h"] = {"value": mig["value"], "unit": "ft/h", "label": mig["reason"]}
    return inputs, results


def unit_of(key: str) -> str:
    for suffix, unit in (("_psi_per_bbl", "psi/bbl"), ("_bbl", "bbl"), ("_psi", "psi"), ("_ft_h", "ft/h")):
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
                        name=f"Volumetric method from SICP {v['sicp_psi']:g} psi (TRAINING AID)",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; inputs SHA-256 {result['inputs_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    if inputs_sha256(freeze(values)) != (inputs.get("inputs_sha256") or {}).get("value"):
        raise IntegrityError("the stored volumetric-method inputs fail their SHA-256 check")
    return case_payload(evaluate(values))[1]
