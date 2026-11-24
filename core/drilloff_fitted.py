"""M423: drill-off founder point by a fitted two-segment (continuous hinge) line - a separate method from M372.

SCREENING. The M372 rule (``core.mse_drilloff``) compares consecutive interval slopes and can only name a tested step.
This method fits the whole test at once:

    ROP = a + b WOB + c max(WOB - W*, 0)

by ordinary least squares for every candidate breakpoint W*, and keeps the W* with the smallest residual sum of
squares (continuous piecewise-linear regression; the breakpoint is not restricted to a tested WOB). Below W* the
fitted slope is b, above it b + c. The search covers W* in [W_(2), W_(n-1)] (at least two steps on each side): a
200-point grid per interval between tested WOB values, then golden-section refinement around the best grid point.

Decision (stated, not tuned): FOUNDER IDENTIFIED when b > 0 and the upper slope b + c < ``slope_ratio`` x b (declared
0 < ratio < 1); otherwise NO FOUNDER IN TESTED RANGE. The result also states R^2, the residual standard error
s = sqrt(SSE / (n - 3)), the single straight-line SSE for comparison and every step whose residual exceeds 3 s_(i),
s_(i) = sqrt((SSE - r_i^2) / (n - 4)) the leave-one-out scale (leverage not included) - flagged, never removed (no
outlier is dropped silently). (With the pooled s a residual can never exceed 3 s for n <= 12, so it is not used.)
Least squares is not robust: a gross outlier next to the knee can pull the breakpoint onto itself (stated limitation,
covered by a test); review flagged steps and the residuals before relying on the fitted breakpoint.

Inputs (declared, nothing defaulted): steps of WOB (klbf), RPM (rpm) and ROP (ft/h); the RPM tolerance (rpm) and the
slope ratio. NOT ASSESSED with fewer than 5 complete steps (3 parameters plus at least 2 residual degrees of freedom),
duplicate WOB values, or RPM varying by more than the tolerance (not a drill-off test). Surface WOB, constant RPM, no
downhole correction. The fitted breakpoint is a statistical estimate of where the ROP response changes slope; it is
not claimed to be more physically accurate than the M372 rule - the benchmark cases compare both by construction.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

METHOD_ID = "m423.drilloff_fitted"
METHOD_VERSION = "M423 drill-off founder, continuous two-segment least squares v1"
CALCULATOR = "Drill-off test (fitted two-segment line)"
LABEL = ("SCREENING - drill-off founder by a continuous two-segment least-squares fit of ROP on WOB at constant RPM; a "
         "statistical breakpoint estimate, not a drilling optimiser")
COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"
FOUNDER, NO_FOUNDER = "FOUNDER IDENTIFIED", "NO FOUNDER IN TESTED RANGE"
MIN_STEPS = 5
GRID = 200
GOLDEN_TOL = 1e-10
OUTLIER_SIGMA = 3.0

FIELDS: Tuple[Tuple[str, str, bool], ...] = (("rpm_tolerance_rpm", "rpm", True), ("slope_ratio", "", True))
STEP_FIELDS: Tuple[Tuple[str, str], ...] = (("wob_klbf", "klbf"), ("rpm", "rpm"), ("rop_ft_hr", "ft/h"))
UNITS = {key: unit for key, unit, _required in FIELDS}


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
    frozen: Dict[str, Any] = {key: _number(inputs.get(key), key) for key in UNITS}
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


# ---- least squares ------------------------------------------------------------------------------------------------
def _solve(matrix: List[List[float]], rhs: List[float]) -> Optional[List[float]]:
    """Gaussian elimination with partial pivoting; None for a singular system."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12 * max(1.0, max(abs(x) for row in a for x in row[:n])):
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(col + 1, n):
            factor = a[r][col] / a[col][col]
            for c in range(col, n + 1):
                a[r][c] -= factor * a[col][c]
    out = [0.0] * n
    for r in range(n - 1, -1, -1):
        out[r] = (a[r][n] - sum(a[r][c] * out[c] for c in range(r + 1, n))) / a[r][r]
    return out


def fit_line(xs: Sequence[float], ys: Sequence[float]) -> Tuple[float, float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    sse = sum((y - intercept - slope * x) ** 2 for x, y in zip(xs, ys))
    return intercept, slope, sse


def fit_hinge(xs: Sequence[float], ys: Sequence[float], breakpoint: float) -> Optional[Tuple[List[float], float]]:
    rows = [[1.0, x, max(x - breakpoint, 0.0)] for x in xs]
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    aty = [sum(r[i] * y for r, y in zip(rows, ys)) for i in range(3)]
    coef = _solve(ata, aty)
    if coef is None:
        return None
    sse = sum((y - sum(c * v for c, v in zip(coef, r))) ** 2 for r, y in zip(rows, ys))
    return coef, sse


def best_breakpoint(xs: Sequence[float], ys: Sequence[float]) -> Optional[Tuple[float, List[float], float]]:
    """Global search on a grid per interval in [x_(2), x_(n-1)], then golden-section refinement."""
    lo_index, hi_index = 1, len(xs) - 2
    best: Optional[Tuple[float, List[float], float]] = None

    def sse_at(b: float) -> float:
        fit = fit_hinge(xs, ys, b)
        return math.inf if fit is None else fit[1]

    candidates = []
    for k in range(lo_index, hi_index):
        a, b = xs[k], xs[k + 1]
        candidates.extend(a + (b - a) * i / GRID for i in range(GRID))
    candidates.append(xs[hi_index])
    scored = [(sse_at(b), b) for b in candidates]
    sse0, b0 = min(scored)
    if not math.isfinite(sse0):
        return None
    step = (xs[hi_index] - xs[lo_index]) / max(1, (hi_index - lo_index) * GRID)
    left, right = max(xs[lo_index], b0 - step), min(xs[hi_index], b0 + step)
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = right - ratio * (right - left), left + ratio * (right - left)
    fc, fd = sse_at(c), sse_at(d)
    while right - left > GOLDEN_TOL * max(1.0, abs(right)):
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right - ratio * (right - left)
            fc = sse_at(c)
        else:
            left, c, fc = c, d, fd
            d = left + ratio * (right - left)
            fd = sse_at(d)
    for b in (b0, 0.5 * (left + right)):
        fit = fit_hinge(xs, ys, b)
        if fit is not None and (best is None or fit[1] < best[2]):
            best = (b, fit[0], fit[1])
    return best


def evaluate(inputs: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    v = freeze(inputs, steps)
    base = {"label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v), "method_version": METHOD_VERSION}
    missing = [key for key, _unit, required in FIELDS if required and v[key] is None]
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", **base}
    if not 0 < v["slope_ratio"] < 1:
        raise FitError("the slope ratio must be between 0 and 1")
    if v["rpm_tolerance_rpm"] < 0:
        raise FitError("the RPM tolerance cannot be negative")
    usable = [s for s in v["steps"] if None not in (s["wob_klbf"], s["rpm"], s["rop_ft_hr"])]
    if len(usable) < MIN_STEPS:
        return {"status": NOT_ASSESSED, **base, "reason": f"{len(usable)} complete step(s); the fit needs at least "
                                                          f"{MIN_STEPS} (3 parameters + 2 residual degrees of freedom)"}
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
    _a1, _b1, sse_line = fit_line(xs, ys)
    best = best_breakpoint(xs, ys)
    if best is None:
        return {"status": NOT_ASSESSED, **base, "reason": "the two-segment fit is singular for these steps"}
    breakpoint, (a, b, c), sse = best
    n = len(xs)
    mean = sum(ys) / n
    sst = sum((y - mean) ** 2 for y in ys)
    sigma = math.sqrt(sse / (n - 3))
    residuals = [y - (a + b * x + c * max(x - breakpoint, 0.0)) for x, y in zip(xs, ys)]
    # leave-one-out residual scale s_(i) = sqrt((SSE - r_i^2) / (n - 4)): a point's own residual does not inflate the
    # scale it is judged against (with the pooled s, |r_i| / s <= sqrt(n - 3) and nothing could be flagged for n <= 12).
    # Leverage is not included (stated approximation); flagged steps stay in the fit.
    flagged = []
    for i, r in enumerate(residuals):
        rest = sse - r * r
        scale = math.sqrt(rest / (n - 4)) if rest > 0 else 0.0
        if abs(r) > 1e-9 * max(1.0, max(abs(y) for y in ys)) and (scale == 0.0 or abs(r) > OUTLIER_SIGMA * scale):
            flagged.append(xs[i])
    upper = b + c
    if b > 0 and upper < v["slope_ratio"] * b:
        status, reason = FOUNDER, (f"fitted upper slope {upper:.4g} < {v['slope_ratio']:g} x lower slope {b:.4g} "
                                   f"ft/h/klbf")
    elif b <= 0:
        status, reason = NO_FOUNDER, f"fitted lower slope {b:.4g} ft/h/klbf is not positive: no linear-response region"
    else:
        status, reason = NO_FOUNDER, (f"fitted upper slope {upper:.4g} stays at or above {v['slope_ratio']:g} x lower "
                                      f"slope {b:.4g} ft/h/klbf")
    return {"status": COMPUTED, **base, "founder_status": status, "reason": reason,
            "breakpoint_wob_klbf": breakpoint if status == FOUNDER else None,
            "fitted_breakpoint_wob_klbf": breakpoint, "slope_below": b, "slope_above": upper, "intercept": a,
            "sse": sse, "sse_single_line": sse_line, "r_squared": 1.0 - sse / sst if sst > 0 else None,
            "residual_std": sigma, "residuals": residuals, "flagged_wob_klbf": flagged, "steps_used": n}


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    lines = [LABEL, f"Method {METHOD_ID} {METHOD_VERSION}; {result['steps_used']} steps."]
    lines.append(f"Fit: ROP = {result['intercept']:.4g} + {result['slope_below']:.4g} WOB below "
                 f"{result['fitted_breakpoint_wob_klbf']:.4g} klbf, slope {result['slope_above']:.4g} ft/h/klbf above.")
    r2 = result["r_squared"]
    lines.append(f"SSE {result['sse']:.4g} (single line {result['sse_single_line']:.4g}); R² "
                 f"{'n/a' if r2 is None else f'{r2:.4f}'}; residual std {result['residual_std']:.4g} ft/h.")
    if result["founder_status"] == FOUNDER:
        lines.append(f"Founder at fitted WOB {result['breakpoint_wob_klbf']:.4g} klbf - {result['reason']}.")
    else:
        lines.append(f"Founder: {result['founder_status']} - {result['reason']}.")
    if result["flagged_wob_klbf"]:
        lines.append("Residual > 3 s(i) (leave-one-out) at WOB " + ", ".join(f"{w:g}" for w in result["flagged_wob_klbf"])
                     + " klbf (flagged, not removed).")
    return lines


RESULT_FIELDS = (("founder_status", ""), ("breakpoint_wob_klbf", "klbf"), ("fitted_breakpoint_wob_klbf", "klbf"),
                 ("slope_below", "ft/h/klbf"), ("slope_above", "ft/h/klbf"), ("intercept", "ft/h"), ("sse", ""),
                 ("r_squared", ""), ("residual_std", "ft/h"))


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
    return inputs, results


def unit_of(key: str) -> str:
    return dict(RESULT_FIELDS).get(key, "")


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != COMPUTED:
        raise ValueError(f"Nothing to store: not computed ({result.get('reason')}).")
    inputs, results = case_payload(result)
    return cc.save_case(db, calculator=CALCULATOR,
                        name=f"Drill-off fitted line, {result['steps_used']} steps, {result['founder_status']}",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; inputs SHA-256 {result['inputs_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    steps = (inputs.get("steps") or {}).get("value") or []
    if not isinstance(steps, list) or inputs_sha256(freeze(values, steps)) != (inputs.get("inputs_sha256") or
                                                                                {}).get("value"):
        raise IntegrityError("the stored drill-off fit inputs fail their SHA-256 check")
    return case_payload(evaluate(values, steps))[1]
