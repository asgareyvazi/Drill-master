"""M371: casing axial-load components and wear-reduced pipe-body ratings - beyond the API TR 5C3 pipe-body subset.

SCREENING. Textbook closed forms (Lubinski; Bourgoyne et al., *Applied Drilling Engineering*, ch. 7), steel pipe
body only, tension positive, oilfield units (in, psi, lbf, degF):

* steel area           A_s = pi/4 (OD^2 - ID^2)
* bending in a dogleg  kappa = DLS * pi / 180 / 1200  [rad/in, DLS in deg/100 ft]
                       sigma_b = E * OD / 2 * kappa,  F_b = sigma_b * A_s  (outer-fibre equivalent load)
* temperature change   dF_T = -E * alpha * dT * A_s   (both ends fixed; heating reduces tension)
* ballooning           dF_B = 2 nu (A_i dP_i - A_o dP_o),  A_i = pi/4 ID^2, A_o = pi/4 OD^2  (both ends fixed)
* fibre stress         sigma_max = (F_base + dF_T + dF_B) / A_s + sigma_b;  utilisation = sigma_max / Yp
* wear                 t_worn = t (1 - wear% / 100); burst and collapse from ``CasingEngine`` on the worn wall
                       (the engine's 0.875 wall tolerance is still applied: conservative, stated).

Nothing is assumed: Young's modulus, the expansion coefficient and Poisson's ratio are declared inputs (no steel
defaults), and a component whose inputs are not all given is NOT ASSESSED (never 0). The total and the fibre stress
are NOT ASSESSED unless the base axial load is given; the components are still reported. Not a triaxial design
envelope, no connection ratings, no temperature-derated yield (pass a derated yield), no buckling of the casing.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

METHOD_ID = "m371.casing_axial_loads"
METHOD_VERSION = "M371 casing axial-load components and wear v1"
CALCULATOR = "Casing axial loads and wear"
LABEL = ("SCREENING - casing axial-load components (bending, temperature, ballooning) and wear-reduced pipe-body "
         "ratings; pipe body only, not a triaxial design, not a connection rating")
COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"

#: every input, its unit and whether it is required for anything to be computed
FIELDS: Tuple[Tuple[str, str, bool], ...] = (
    ("od_in", "in", True), ("id_in", "in", True), ("yield_psi", "psi", True),
    ("base_axial_load_lbf", "lbf", False),
    ("youngs_modulus_psi", "psi", False), ("dls_deg_per_100ft", "deg/100ft", False),
    ("expansion_per_degf", "1/degF", False), ("delta_temperature_degf", "degF", False),
    ("poisson_ratio", "", False), ("delta_internal_psi", "psi", False), ("delta_external_psi", "psi", False),
    ("wear_percent", "%", False),
)
UNITS = {key: unit for key, unit, _required in FIELDS}


class AxialLoadError(ValueError):
    """Inputs that cannot be evaluated (the message says why)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _number(inputs: Mapping[str, Any], key: str) -> Optional[float]:
    value = inputs.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise AxialLoadError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AxialLoadError(f"{key} {value!r} is not a number") from exc
    if not math.isfinite(number):
        raise AxialLoadError(f"{key} must be finite")
    return number


def freeze(inputs: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """The declared inputs as numbers (None = not given); unknown keys are refused."""
    unknown = set(inputs) - set(UNITS)
    if unknown:
        raise AxialLoadError(f"unknown input(s): {', '.join(sorted(unknown))}")
    return {key: _number(inputs, key) for key in UNITS}


def inputs_sha256(values: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(values), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _component(status: str, value=None, reason: str = "", **extra) -> Dict[str, Any]:
    return {"status": status, "value": value, "reason": reason, **extra}


def evaluate(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    from core.engineering.engines.casing import CasingEngine

    v = freeze(inputs)
    missing = [key for key, _unit, required in FIELDS if required and v[key] is None]
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", "label": LABEL, "inputs": v,
                "inputs_sha256": inputs_sha256(v), "components": {}}
    od, idd, yp = v["od_in"], v["id_in"], v["yield_psi"]
    if not (od > 0 and 0 < idd < od and yp > 0):
        raise AxialLoadError("OD > ID > 0 and yield > 0 are required")
    area = math.pi / 4.0 * (od ** 2 - idd ** 2)
    a_in, a_out = math.pi / 4.0 * idd ** 2, math.pi / 4.0 * od ** 2
    comps: Dict[str, Dict[str, Any]] = {}

    def need(*keys):
        return [k for k in keys if v[k] is None]

    gaps = need("youngs_modulus_psi", "dls_deg_per_100ft")
    if gaps:
        comps["bending"] = _component(NOT_ASSESSED, reason=f"not given: {', '.join(gaps)}")
    else:
        if v["youngs_modulus_psi"] <= 0 or v["dls_deg_per_100ft"] < 0:
            raise AxialLoadError("Young's modulus must be > 0 and DLS >= 0")
        kappa = math.radians(v["dls_deg_per_100ft"]) / 1200.0
        sigma_b = v["youngs_modulus_psi"] * od / 2.0 * kappa
        comps["bending"] = _component(COMPUTED, sigma_b * area, "outer-fibre equivalent load sigma_b x A_s",
                                      stress_psi=sigma_b)
    gaps = need("youngs_modulus_psi", "expansion_per_degf", "delta_temperature_degf")
    if gaps:
        comps["temperature"] = _component(NOT_ASSESSED, reason=f"not given: {', '.join(gaps)}")
    else:
        if v["youngs_modulus_psi"] <= 0 or v["expansion_per_degf"] <= 0:
            raise AxialLoadError("Young's modulus and the expansion coefficient must be > 0")
        comps["temperature"] = _component(
            COMPUTED, -v["youngs_modulus_psi"] * v["expansion_per_degf"] * v["delta_temperature_degf"] * area,
            "both ends fixed; heating reduces tension")
    gaps = need("poisson_ratio", "delta_internal_psi", "delta_external_psi")
    if gaps:
        comps["ballooning"] = _component(NOT_ASSESSED, reason=f"not given: {', '.join(gaps)} (a pressure change "
                                                              "that did not happen must be entered as 0)")
    else:
        if not 0 < v["poisson_ratio"] < 0.5:
            raise AxialLoadError("Poisson's ratio must be between 0 and 0.5")
        comps["ballooning"] = _component(
            COMPUTED, 2.0 * v["poisson_ratio"] * (a_in * v["delta_internal_psi"] - a_out * v["delta_external_psi"]),
            "both ends fixed; internal pressure increase raises tension")
    result: Dict[str, Any] = {"status": COMPUTED, "label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v),
                              "steel_area_in2": area, "components": comps}
    axial_parts = [comps[k] for k in ("temperature", "ballooning")]
    if v["base_axial_load_lbf"] is None:
        result.update(total_axial_lbf=None, max_fibre_stress_psi=None, utilisation=None,
                      total_status=NOT_ASSESSED, total_reason="the base axial load is not given")
    elif any(c["status"] != COMPUTED for c in axial_parts + [comps["bending"]]):
        missing_parts = [k for k in ("bending", "temperature", "ballooning") if comps[k]["status"] != COMPUTED]
        result.update(total_axial_lbf=None, max_fibre_stress_psi=None, utilisation=None,
                      total_status=NOT_ASSESSED,
                      total_reason=f"component(s) not assessed: {', '.join(missing_parts)} - a partial sum is "
                                   "not a total")
    else:
        total = v["base_axial_load_lbf"] + sum(c["value"] for c in axial_parts)
        sigma = total / area + comps["bending"]["stress_psi"]
        result.update(total_axial_lbf=total, max_fibre_stress_psi=sigma, utilisation=sigma / yp,
                      total_status=COMPUTED, total_reason="base + temperature + ballooning; bending at the outer "
                                                          "fibre on the tension side")
    if v["wear_percent"] is None:
        result["wear"] = _component(NOT_ASSESSED, reason="no wear declared: the ratings below are for the "
                                                         "nominal wall only")
        wall = (od - idd) / 2.0
    else:
        if not 0 <= v["wear_percent"] < 100:
            raise AxialLoadError("wear must be at least 0 % and below 100 %")
        wall = (od - idd) / 2.0 * (1.0 - v["wear_percent"] / 100.0)
        result["wear"] = _component(COMPUTED, wall, "remaining wall, in (engine 0.875 wall tolerance still applied)")
    burst = CasingEngine.burst(od, wall, yp)
    collapse = CasingEngine.collapse(od, wall, yp)
    result["burst_psi"] = burst.value if burst.success else None
    result["collapse_psi"] = collapse.value if collapse.success else None
    result["collapse_regime"] = collapse.values.get("regime") if collapse.success else None
    result["rating_wall_in"] = wall
    return result


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    lines = [LABEL, f"Steel area {result['steel_area_in2']:.3f} in²."]
    for name, comp in result["components"].items():
        if comp["status"] == COMPUTED:
            extra = f" (bending stress {comp['stress_psi']:.0f} psi)" if name == "bending" else ""
            lines.append(f"{name.capitalize()}: {comp['value']:+.0f} lbf{extra} - {comp['reason']}")
        else:
            lines.append(f"{name.capitalize()}: NOT ASSESSED - {comp['reason']}")
    if result["total_status"] == COMPUTED:
        lines.append(f"Total axial {result['total_axial_lbf']:.0f} lbf; max fibre stress "
                     f"{result['max_fibre_stress_psi']:.0f} psi = {100 * result['utilisation']:.1f} % of yield.")
    else:
        lines.append(f"Total: NOT ASSESSED - {result['total_reason']}")
    wear = result["wear"]
    lines.append(f"Wall for ratings {result['rating_wall_in']:.4f} in"
                 + (f" after {result['inputs']['wear_percent']:g} % wear" if wear["status"] == COMPUTED
                    else " (nominal; no wear declared)")
                 + f": burst {result['burst_psi']} psi, collapse {result['collapse_psi']} psi "
                   f"({result['collapse_regime']}).")
    return lines


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    v = result["inputs"]
    inputs: Dict[str, Any] = {key: {"value": v[key], "unit": UNITS[key], "label": key,
                                    "source": "DECLARED" if v[key] is not None else "NOT_ENTERED"} for key in UNITS}
    inputs["inputs_sha256"] = {"value": result["inputs_sha256"], "unit": "", "label": "inputs SHA-256"}
    results: Dict[str, Any] = {"status": {"value": result["status"], "label": result.get("reason") or LABEL}}
    if result["status"] == COMPUTED:
        for name, comp in result["components"].items():
            results[f"{name}_lbf"] = {"value": comp["value"], "unit": "lbf", "label": comp["reason"]}
            results[f"{name}_status"] = {"value": comp["status"], "label": comp["reason"]}
        for key, unit in (("total_axial_lbf", "lbf"), ("max_fibre_stress_psi", "psi"), ("utilisation", ""),
                          ("burst_psi", "psi"), ("collapse_psi", "psi"), ("rating_wall_in", "in")):
            results[key] = {"value": result[key], "unit": unit, "label": key}
        results["total_status"] = {"value": result["total_status"], "label": result["total_reason"]}
    return inputs, results


def unit_of(key: str) -> str:
    for suffix, unit in (("_lbf", "lbf"), ("_psi", "psi"), ("_in", "in")):
        if key.endswith(suffix):
            return unit
    return ""


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != COMPUTED:
        raise ValueError(f"Nothing to store: not computed ({result.get('reason')}).")
    inputs, results = case_payload(result)
    v = result["inputs"]
    return cc.save_case(db, calculator=CALCULATOR, name=f"Casing {v['od_in']:g} in x {v['id_in']:g} in axial loads",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; inputs SHA-256 {result['inputs_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    if inputs_sha256(freeze(values)) != (inputs.get("inputs_sha256") or {}).get("value"):
        raise IntegrityError("the stored casing inputs fail their SHA-256 check")
    return case_payload(evaluate(values))[1]
