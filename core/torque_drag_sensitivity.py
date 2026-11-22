"""M318 (M281): friction-factor sensitivity ("broomstick") on one pinned torque-and-drag run (SCREENING).

The run is the exact input set of a successful W13 torque-and-drag run (pinned survey stations, string
components, mud density, WOB, hole ID). The sweep re-runs the existing Johancsik soft-string engine
(``TorqueDragEngine.calculate``) once for every **declared** friction factor. The engine and its formulas are
unchanged.

Rules:
* There is no default friction factor and no default list. Every factor is declared by the user, must lie in
  [0, 1], and duplicates are removed. A factor the engine refuses is listed with the reason. It is never skipped
  silently, and a 0 is never substituted.
* Observed values (pickup / slack-off / rotating hookload in klbf, rotating surface torque in ft·lbf) are entered by
  the user as observations. The sweep only says where an observation lies relative to the modelled curve:
  BELOW_RANGE, ABOVE_RANGE, AT ff, or BETWEEN ff_a AND ff_b. It does not interpolate an "apparent friction
  factor", because that would be a new derived number with no validated method. A non-monotonic curve is
  NOT_CHECKED.
* The result is SCREENING and is never a calibrated friction factor.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional

CONTRACT = "td-friction-sensitivity-v1"
METHOD_ID = "m318.td_friction_sensitivity"
METHOD_VERSION = "M318 v1 (TorqueDragEngine.calculate per declared friction factor)"
LABEL = "SCREENING — FRICTION-FACTOR SENSITIVITY — NOT A CALIBRATED FRICTION FACTOR"
MAX_FACTORS = 12
CURVES = {"pickup": ("hookload_pickup", "klbf"), "slackoff": ("hookload_slackoff", "klbf"),
          "rotating": ("hookload_rotating", "klbf"), "torque": ("surface_torque_rotating_ft_lbf", "ft·lbf")}
BELOW, ABOVE, AT, BETWEEN, NOT_CHECKED = "BELOW_RANGE", "ABOVE_RANGE", "AT", "BETWEEN", "NOT_CHECKED"


class SensitivityError(ValueError):
    """The sweep cannot start (no run, no declared factor, a factor outside [0, 1], too many factors)."""


def parse_factors(text: str) -> List[float]:
    """Declared factors separated by spaces or semicolons. Commas are refused, as in D86: "0,25" is never 0.25."""
    if text is None or not str(text).strip():
        raise SensitivityError("Declare at least one friction factor (there is no default).")
    if "," in str(text):
        raise SensitivityError("Separate friction factors with spaces or ';' — commas are refused (0,25 is ambiguous).")
    values = []
    for token in str(text).replace(";", " ").split():
        try:
            value = float(token)
        except ValueError as exc:
            raise SensitivityError(f"{token!r} is not a number.") from exc
        values.append(value)
    return normalize_factors(values)


def normalize_factors(values: Iterable[Any]) -> List[float]:
    factors = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise SensitivityError(f"Friction factor {value!r} is not a finite number.")
        if not 0.0 <= float(value) <= 1.0:
            raise SensitivityError(f"Friction factor {value:g} is outside [0, 1].")
        factors.append(float(value))
    factors = sorted(set(factors))
    if not factors:
        raise SensitivityError("Declare at least one friction factor (there is no default).")
    if len(factors) > MAX_FACTORS:
        raise SensitivityError(f"At most {MAX_FACTORS} friction factors per sweep ({len(factors)} declared).")
    return factors


def sweep(run: Optional[Mapping[str, Any]], factors: Iterable[Any]) -> Dict[str, Any]:
    from core.engineering.engines.torque_drag import TorqueDragEngine

    if not run or not run.get("survey") or not run.get("components"):
        raise SensitivityError("Run torque and drag on a pinned survey first; the sweep re-uses that run's inputs.")
    if not (run.get("survey_source") or {}).get("revision_id"):
        # M323 (A-6): a sweep on an unpinned survey could never be traced or replayed; it is refused, not stored
        raise SensitivityError("The run is not tied to a pinned survey revision; pin the survey and re-run T&D.")
    declared = normalize_factors(factors)
    rows: List[Dict[str, Any]] = []
    for ff in declared:
        result = TorqueDragEngine.calculate(run["survey"], run["components"], mud_density_ppg=run["mud_density_ppg"],
                                            friction_factor=ff, wob_klbf=run.get("wob_klbf"),
                                            wellbore_id_in=run.get("wellbore_id_in"))
        if not result.success:
            rows.append({"friction_factor": ff, "status": "FAILED", "reason": result.error,
                         **{name: None for name in CURVES}, "buckling": None})
            continue
        v = result.values
        rows.append({"friction_factor": ff, "status": "OK", "reason": "",
                     **{name: v.get(key) for name, (key, _unit) in CURVES.items()},
                     "buckling": bool(v.get("buckling", {}).get("any"))})
    return {"contract": CONTRACT, "method": METHOD_ID, "method_version": METHOD_VERSION, "label": LABEL,
            "engine_method": TorqueDragEngine.METHOD, "factors": declared, "rows": rows,
            "survey_source": dict(run.get("survey_source") or {}), "mud_density_ppg": run["mud_density_ppg"],
            # M328: the exact engine inputs of the sweep, frozen for replay (never re-read from W13 widgets)
            "run_snapshot": {"survey": [dict(st) for st in run["survey"]],
                             "components": [dict(c) for c in run["components"]],
                             "mud_density_ppg": run["mud_density_ppg"], "wob_klbf": run.get("wob_klbf"),
                             "wellbore_id_in": run.get("wellbore_id_in"),
                             "survey_source": dict(run.get("survey_source") or {}),
                             "components_sha256": components_sha256(run["components"])},
            "wob_klbf": run.get("wob_klbf"), "wellbore_id_in": run.get("wellbore_id_in"),
            "failed": [r["friction_factor"] for r in rows if r["status"] != "OK"]}


def components_sha256(components: Iterable[Mapping[str, Any]]) -> str:
    """SHA-256 of the engine components (canonical JSON), stored with the run snapshot and checked on replay."""
    import hashlib
    import json

    payload = json.dumps([dict(c) for c in components], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def locate(result: Mapping[str, Any], curve: str, observed: Optional[float]) -> Dict[str, Any]:
    """Where an observation lies on one modelled curve. Never interpolates a friction factor."""
    if curve not in CURVES:
        raise SensitivityError(f"Unknown curve {curve!r}.")
    unit = CURVES[curve][1]
    if observed is None or isinstance(observed, bool) or not math.isfinite(float(observed)):
        return {"curve": curve, "status": NOT_CHECKED, "reason": "no observation entered", "unit": unit}
    points = [(r["friction_factor"], r[curve]) for r in result["rows"] if r["status"] == "OK" and r[curve] is not None]
    if len(points) < 2:
        return {"curve": curve, "status": NOT_CHECKED, "reason": "fewer than two successful friction factors",
                "unit": unit}
    values = [value for _ff, value in points]
    rising = all(b >= a for a, b in zip(values, values[1:]))
    falling = all(b <= a for a, b in zip(values, values[1:]))
    if not (rising or falling) or values[0] == values[-1]:
        return {"curve": curve, "status": NOT_CHECKED, "unit": unit,
                "reason": "the modelled curve is not monotonic over the declared factors"}
    for ff, value in points:
        if abs(value - observed) <= 1e-9 * max(1.0, abs(value)):
            return {"curve": curve, "status": AT, "friction_factors": [ff], "unit": unit,
                    "reason": f"observed {observed:g} {unit} equals the model at FF {ff:g}"}
    low, high = min(values), max(values)
    if observed < low or observed > high:
        status = BELOW if observed < low else ABOVE
        return {"curve": curve, "status": status, "unit": unit,
                "reason": f"observed {observed:g} {unit} is outside the modelled {low:g}–{high:g} {unit} for FF "
                          f"{points[0][0]:g}–{points[-1][0]:g}"}
    for (ff_a, a), (ff_b, b) in zip(points, points[1:]):
        if min(a, b) <= observed <= max(a, b):
            return {"curve": curve, "status": BETWEEN, "friction_factors": [ff_a, ff_b], "unit": unit,
                    "reason": f"observed {observed:g} {unit} lies between FF {ff_a:g} ({a:g}) and FF {ff_b:g} ({b:g})"}
    return {"curve": curve, "status": NOT_CHECKED, "reason": "not located", "unit": unit}  # unreachable by monotonicity


def table_lines(result: Mapping[str, Any]) -> List[str]:
    def show(value, digits):
        return "—" if value is None else f"{value:.{digits}f}"

    lines = [f"{result['label']}.", "FF | PU klbf | SO klbf | ROT klbf | TQ ft·lbf | buckling"]
    for r in result["rows"]:
        if r["status"] != "OK":
            lines.append(f"{r['friction_factor']:g} | FAILED: {r['reason']}")
            continue
        lines.append(f"{r['friction_factor']:g} | {show(r['pickup'], 1)} | {show(r['slackoff'], 1)} | "
                     f"{show(r['rotating'], 1)} | {show(r['torque'], 0)} | {'flag' if r['buckling'] else 'no flag'}")
    return lines


def save_case(db, result: Mapping[str, Any], observations: Mapping[str, Optional[float]], *, well_id: Optional[int],
              user_id: Optional[int] = None) -> Dict[str, Any]:
    from core import calculation_cases as cc

    ok_rows = [r for r in result["rows"] if r["status"] == "OK"]
    if not ok_rows:
        raise ValueError("No friction factor ran successfully; there is nothing to store.")
    if not result.get("run_snapshot"):
        raise ValueError("The sweep carries no run snapshot; it cannot be stored reproducibly.")
    inputs, results = case_payload(result, observations)
    return cc.save_case(db, calculator="T&D friction sensitivity", name=f"FF sweep {result['factors']}",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; engine {result['engine_method']}")


def case_payload(result: Mapping[str, Any], observations: Mapping[str, Optional[float]]):
    """(inputs, results) of a sweep case: one builder for save and M328 replay."""
    pin = result["survey_source"]
    inputs = {"friction_factors": {"value": result["factors"], "unit": "", "label": "declared friction factors",
                                   "source": "DECLARED"},
              "mud_density_ppg": {"value": result["mud_density_ppg"], "unit": "ppg", "label": "mud density"},
              "wob_klbf": {"value": result["wob_klbf"], "unit": "klbf", "label": "WOB"},
              "wellbore_id_in": {"value": result["wellbore_id_in"], "unit": "in", "label": "hole ID"},
              "survey_revision_id": {"value": pin.get("revision_id"), "unit": "",
                                     "label": f"survey revision {pin.get('revision')}",
                                     "source": "PINNED" if pin.get("revision_id") else "NOT_PINNED"},
              "survey_stations_sha256": {"value": pin.get("stations_sha256"), "unit": "",
                                         "label": "pinned survey SHA-256"},
              "engine_method": {"value": result["engine_method"], "unit": "", "label": "T&D engine method"},
              "run_snapshot": {"value": result.get("run_snapshot"), "unit": "",
                               "label": "frozen survey stations, string and run inputs (M328 replay)",
                               "source": "SNAPSHOT"}}
    for curve in CURVES:
        value = observations.get(curve)
        inputs[f"observed_{curve}"] = {"value": value, "unit": CURVES[curve][1], "label": f"observed {curve}",
                                       "source": "OBSERVED" if value is not None else "NOT_ENTERED"}
    results: Dict[str, Any] = {}
    for r in result["rows"]:
        for curve in CURVES:
            results[f"ff_{r['friction_factor']:g}_{curve}"] = {"value": r[curve], "label": f"{curve} at FF "
                                                                                        f"{r['friction_factor']:g}"}
        if r["status"] != "OK":
            results[f"ff_{r['friction_factor']:g}_status"] = {"value": "FAILED", "label": r["reason"]}
    for curve in CURVES:
        where = locate(result, curve, observations.get(curve))
        results[f"located_{curve}"] = {"value": where["status"], "label": where["reason"]}
    return inputs, results
