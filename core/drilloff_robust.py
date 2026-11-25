"""M475: drill-off founder point by a robust (least absolute deviations) two-segment line - a separate method.

SCREENING. M372 (``core.mse_drilloff``, interval slope rule) and M423 (``core.drilloff_fitted``, least squares) are
unchanged and keep their method IDs, versions and replay. M423 documents that least squares is not robust: one gross
ROP outlier next to the knee can pull the breakpoint onto itself. This method fits the same continuous hinge

    ROP = a + b WOB + c max(WOB - W*, 0)

by least absolute deviations (LAD, L1): for a fixed W* it minimises sum |r_i| exactly. A basic optimal solution of
the L1 problem interpolates at least p = 3 observations (the linear-programming vertex property; Bloomfield &
Steiger 1983, *Least Absolute Deviations*), so every triple of steps is solved exactly and the smallest sum is kept
(the first triple in index order on a tie: LAD optima need not be unique, stated). W* is searched over
[W_(2), W_(n-1)] (at least two steps on each side) on a ``GRID``-point grid per interval between tested WOB values,
then refined by golden section around the best grid point; the better of the two is kept.

Outliers: robust scale s = 1.4826 x median |r_i| over the steps that are not on the fitted vertex (the three
interpolated steps have r = 0 by construction and would bias the median); a step with |r_i| > 3 s is flagged, never
removed. If s = 0 (more than half the remaining steps lie exactly on the fit) any non-zero residual is flagged.

Decision (same declared rule as M423, not tuned): FOUNDER IDENTIFIED when b > 0 and the upper slope b + c <
``slope_ratio`` x b (declared 0 < ratio < 1); otherwise NO FOUNDER IN TESTED RANGE.

WOB basis (E6b): the user must declare whether the typed WOB values are ``surface`` or ``downhole`` measurements.
The method never converts one into the other and never derives downhole WOB (no hook-load, friction or drag model);
a surface basis is reported as "surface WOB - not downhole WOB". The declared basis is part of the frozen inputs and
their SHA-256. This is not a validated downhole drill-off method (no field validation, no data set with rights).

Inputs (declared, nothing defaulted): steps of WOB (klbf), RPM (rpm) and ROP (ft/h), the RPM tolerance (rpm), the
slope ratio and the WOB basis. NOT ASSESSED with fewer than ``MIN_STEPS`` complete steps, more than ``MAX_STEPS``
(bounded exact search), RPM varying by more than the tolerance (not a drill-off test) or a missing WOB basis;
duplicate WOB values are refused. LAD resists outliers in ROP; it is not robust to a wrong WOB value (leverage),
which is stated.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

METHOD_ID = "m475.drilloff_robust"
METHOD_VERSION = "M475 drill-off founder, least-absolute-deviations two-segment line v1"
CALCULATOR = "Drill-off test (robust LAD two-segment line)"
LABEL = ("SCREENING - drill-off founder by a least-absolute-deviations continuous two-segment fit of ROP on WOB at "
         "constant RPM with a declared WOB basis; a statistical breakpoint estimate, not a drilling optimiser and not "
         "a validated downhole method")
COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"
FOUNDER, NO_FOUNDER = "FOUNDER IDENTIFIED", "NO FOUNDER IN TESTED RANGE"
WOB_BASES = ("surface", "downhole")
MIN_STEPS = 6
MAX_STEPS = 30
GRID = 20
GOLDEN_TOL = 1e-10
OUTLIER_SIGMA = 3.0
MAD_TO_SIGMA = 1.4826            # 1 / Phi^-1(0.75), normal consistency of the median absolute deviation
TIE_REL = 1e-12

FIELDS: Tuple[Tuple[str, str, bool], ...] = (("rpm_tolerance_rpm", "rpm", True), ("slope_ratio", "", True))
TEXT_FIELDS: Tuple[Tuple[str, str, bool], ...] = (("wob_basis", "", True),)
STEP_FIELDS: Tuple[Tuple[str, str], ...] = (("wob_klbf", "klbf"), ("rpm", "rpm"), ("rop_ft_hr", "ft/h"))
UNITS = {key: unit for key, unit, _required in FIELDS + TEXT_FIELDS}


class FitError(ValueError):
    """Inputs that cannot be evaluated (the message says why)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _number(value: Any, key: str) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise FitError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FitError(f"{key} {value!r} is not a number") from exc
    if not math.isfinite(number):
        raise FitError(f"{key} must be finite")
    return number


def freeze(inputs: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    unknown = set(inputs) - set(UNITS)
    if unknown:
        raise FitError(f"unknown input(s): {', '.join(sorted(unknown))}")
    frozen: Dict[str, Any] = {key: _number(inputs.get(key), key) for key, _unit, _required in FIELDS}
    basis = inputs.get("wob_basis")
    basis = basis.strip() if isinstance(basis, str) and basis.strip() else None
    if basis is not None and basis not in WOB_BASES:
        raise FitError(f"WOB basis {basis!r} is not one of {', '.join(WOB_BASES)}")
    frozen["wob_basis"] = basis
    rows = []
    for index, step in enumerate(steps, start=1):
        extra = set(step) - {key for key, _unit in STEP_FIELDS}
        if extra:
            raise FitError(f"step {index}: unknown field(s) {', '.join(sorted(extra))}")
        row = {key: _number(step.get(key), f"step {index} {key}") for key, _unit in STEP_FIELDS}
        if all(value is None for value in row.values()):
            continue
        if any(value is not None and value < 0 for value in row.values()):
            raise FitError(f"step {index}: WOB, RPM and ROP cannot be negative")
        rows.append(row)
    frozen["steps"] = rows
    return frozen


def inputs_sha256(frozen: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(frozen), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---- exact L1 fit ---------------------------------------------------------------------------------------------------
def lad_hinge(xs: Sequence[float], ys: Sequence[float], breakpoint: float
              ) -> Optional[Tuple[List[float], float, Tuple[int, int, int]]]:
    """Exact LAD fit of the hinge at a fixed breakpoint: (coefficients, sum |r|, interpolated step indices)."""
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    design = np.column_stack([np.ones_like(x), x, np.maximum(x - breakpoint, 0.0)])
    triples = np.array(list(itertools.combinations(range(len(x)), 3)), dtype=int)
    systems = design[triples]                                   # (T, 3, 3)
    scale = max(1.0, float(np.abs(design).max()))
    det = np.linalg.det(systems)
    ok = np.abs(det) > 1e-9 * scale ** 2
    if not ok.any():
        return None
    triples, systems = triples[ok], systems[ok]
    coef = np.linalg.solve(systems, y[triples][..., None])[..., 0]          # (T, 3)
    sad = np.abs(y[None, :] - coef @ design.T).sum(axis=1)
    best = float(sad.min())
    index = int(np.flatnonzero(sad <= best + TIE_REL * max(1.0, best))[0])  # first triple among equal optima
    return [float(c) for c in coef[index]], float(sad[index]), tuple(int(i) for i in triples[index])


def best_breakpoint(xs: Sequence[float], ys: Sequence[float]
                    ) -> Optional[Tuple[float, List[float], float, Tuple[int, int, int]]]:
    """Grid per interval in [x_(2), x_(n-1)], golden-section refinement, keep the smaller sum |r|."""
    lo_index, hi_index = 1, len(xs) - 2

    def sad_at(b: float) -> float:
        fit = lad_hinge(xs, ys, b)
        return math.inf if fit is None else fit[1]

    candidates = []
    for k in range(lo_index, hi_index):
        a, b = xs[k], xs[k + 1]
        candidates.extend(a + (b - a) * i / GRID for i in range(GRID))
    candidates.append(xs[hi_index])
    sad0, b0 = min((sad_at(b), b) for b in candidates)
    if not math.isfinite(sad0):
        return None
    step = (xs[hi_index] - xs[lo_index]) / max(1, (hi_index - lo_index) * GRID)
    left, right = max(xs[lo_index], b0 - step), min(xs[hi_index], b0 + step)
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = right - ratio * (right - left), left + ratio * (right - left)
    fc, fd = sad_at(c), sad_at(d)
    while right - left > GOLDEN_TOL * max(1.0, abs(right)):
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right - ratio * (right - left)
            fc = sad_at(c)
        else:
            left, c, fc = c, d, fd
            d = left + ratio * (right - left)
            fd = sad_at(d)
    best = None
    for b in (b0, 0.5 * (left + right)):
        fit = lad_hinge(xs, ys, b)
        if fit is not None and (best is None or fit[1] < best[2]):
            best = (b, fit[0], fit[1], fit[2])
    return best


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])


def evaluate(inputs: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    v = freeze(inputs, steps)
    base = {"label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v), "method_version": METHOD_VERSION}
    missing = [key for key, _unit, required in FIELDS + TEXT_FIELDS if required and v[key] is None]
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", **base}
    if not 0 < v["slope_ratio"] < 1:
        raise FitError("the slope ratio must be between 0 and 1")
    if v["rpm_tolerance_rpm"] < 0:
        raise FitError("the RPM tolerance cannot be negative")
    usable = [s for s in v["steps"] if None not in (s["wob_klbf"], s["rpm"], s["rop_ft_hr"])]
    if len(usable) < MIN_STEPS:
        return {"status": NOT_ASSESSED, **base, "reason": f"{len(usable)} complete step(s); the robust fit needs at "
                                                          f"least {MIN_STEPS}"}
    if len(usable) > MAX_STEPS:
        return {"status": NOT_ASSESSED, **base, "reason": f"{len(usable)} complete steps; the exact L1 search is "
                                                          f"bounded at {MAX_STEPS} steps"}
    wobs = [s["wob_klbf"] for s in usable]
    if len(set(wobs)) != len(wobs):
        raise FitError("two steps share the same WOB: a step test needs distinct WOB values")
    rpms = [s["rpm"] for s in usable]
    if max(rpms) - min(rpms) > v["rpm_tolerance_rpm"]:
        return {"status": NOT_ASSESSED, **base, "reason": f"RPM varies {min(rpms):g}-{max(rpms):g} rpm, more than the "
                                                          f"declared tolerance {v['rpm_tolerance_rpm']:g} rpm: not a "
                                                          f"drill-off test"}
    ordered = sorted(usable, key=lambda s: s["wob_klbf"])
    xs = [s["wob_klbf"] for s in ordered]
    ys = [s["rop_ft_hr"] for s in ordered]
    best = best_breakpoint(xs, ys)
    if best is None:
        return {"status": NOT_ASSESSED, **base, "reason": "the two-segment L1 fit is singular for these steps"}
    breakpoint, (a, b, c), sad, vertex = best
    residuals = [y - (a + b * x + c * max(x - breakpoint, 0.0)) for x, y in zip(xs, ys)]
    off_vertex = [abs(r) for i, r in enumerate(residuals) if i not in vertex]
    scale = MAD_TO_SIGMA * _median(off_vertex)
    tiny = 1e-9 * max(1.0, max(abs(y) for y in ys))
    flagged = [xs[i] for i, r in enumerate(residuals)
               if abs(r) > tiny and (abs(r) > OUTLIER_SIGMA * scale if scale > tiny else True)]
    upper = b + c
    if b > 0 and upper < v["slope_ratio"] * b:
        status, reason = FOUNDER, (f"fitted upper slope {upper:.4g} < {v['slope_ratio']:g} x lower slope {b:.4g} "
                                   f"ft/h/klbf")
    elif b <= 0:
        status, reason = NO_FOUNDER, f"fitted lower slope {b:.4g} ft/h/klbf is not positive: no linear-response region"
    else:
        status, reason = NO_FOUNDER, (f"fitted upper slope {upper:.4g} stays at or above {v['slope_ratio']:g} x lower "
                                      f"slope {b:.4g} ft/h/klbf")
    return {"status": COMPUTED, **base, "founder_status": status, "reason": reason, "wob_basis": v["wob_basis"],
            "breakpoint_wob_klbf": breakpoint if status == FOUNDER else None,
            "fitted_breakpoint_wob_klbf": breakpoint, "slope_below": b, "slope_above": upper, "intercept": a,
            "sum_abs_residuals": sad, "robust_scale": scale, "residuals": residuals,
            "vertex_wob_klbf": [xs[i] for i in vertex], "flagged_wob_klbf": flagged, "steps_used": len(xs)}


def basis_text(basis: Optional[str]) -> str:
    if basis == "downhole":
        return "WOB basis: downhole, as declared by the user (not derived or checked by this method)"
    return "WOB basis: surface - not downhole WOB (no downhole correction is applied)"


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    lines = [LABEL, f"Method {METHOD_ID} {METHOD_VERSION}; {result['steps_used']} steps.",
             basis_text(result["wob_basis"]) + "."]
    lines.append(f"L1 fit: ROP = {result['intercept']:.4g} + {result['slope_below']:.4g} WOB below "
                 f"{result['fitted_breakpoint_wob_klbf']:.4g} klbf, slope {result['slope_above']:.4g} ft/h/klbf above.")
    lines.append(f"Sum |residual| {result['sum_abs_residuals']:.4g} ft/h; robust scale {result['robust_scale']:.4g} "
                 f"ft/h; fit passes through the steps at WOB "
                 + ", ".join(f"{w:g}" for w in result["vertex_wob_klbf"]) + " klbf.")
    if result["founder_status"] == FOUNDER:
        lines.append(f"Founder at fitted WOB {result['breakpoint_wob_klbf']:.4g} klbf - {result['reason']}.")
    else:
        lines.append(f"Founder: {result['founder_status']} - {result['reason']}.")
    if result["flagged_wob_klbf"]:
        lines.append("Residual > 3 x robust scale at WOB " + ", ".join(f"{w:g}" for w in result["flagged_wob_klbf"])
                     + " klbf (flagged, not removed).")
    return lines


RESULT_FIELDS = (("founder_status", ""), ("wob_basis", ""), ("breakpoint_wob_klbf", "klbf"),
                 ("fitted_breakpoint_wob_klbf", "klbf"), ("slope_below", "ft/h/klbf"), ("slope_above", "ft/h/klbf"),
                 ("intercept", "ft/h"), ("sum_abs_residuals", "ft/h"), ("robust_scale", "ft/h"))


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    v = result["inputs"]
    inputs: Dict[str, Any] = {key: {"value": v[key], "unit": UNITS[key], "label": key,
                                    "source": "DECLARED" if v[key] is not None else "NOT_ENTERED"} for key in UNITS}
    inputs["steps"] = {"value": v["steps"], "unit": "klbf / rpm / ft/h", "label": "test steps as entered"}
    inputs["inputs_sha256"] = {"value": result["inputs_sha256"], "unit": "", "label": "inputs SHA-256"}
    results: Dict[str, Any] = {"status": {"value": result["status"], "label": result.get("reason") or LABEL}}
    if result["status"] == COMPUTED:
        for key, unit in RESULT_FIELDS:
            results[key] = {"value": result.get(key), "unit": unit, "label": key}
        results["flagged_wob_klbf"] = {"value": ", ".join(f"{w:g}" for w in result["flagged_wob_klbf"]),
                                       "unit": "klbf", "label": "flagged steps (not removed)"}
    return inputs, results


def unit_of(key: str) -> str:
    return dict(RESULT_FIELDS).get(key, "")


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != COMPUTED:
        raise ValueError(f"Nothing to store: not computed ({result.get('reason')}).")
    inputs, results = case_payload(result)
    return cc.save_case(db, calculator=CALCULATOR,
                        name=f"Drill-off robust L1 line, {result['steps_used']} steps, {result['wob_basis']} WOB, "
                             f"{result['founder_status']}",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id,
                        note=f"{LABEL}; {basis_text(result['wob_basis'])}; inputs SHA-256 {result['inputs_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    steps = (inputs.get("steps") or {}).get("value") or []
    if not isinstance(steps, list) or inputs_sha256(freeze(values, steps)) != (inputs.get("inputs_sha256") or
                                                                                {}).get("value"):
        raise IntegrityError("the stored robust drill-off inputs fail their SHA-256 check")
    return case_payload(evaluate(values, steps))[1]
