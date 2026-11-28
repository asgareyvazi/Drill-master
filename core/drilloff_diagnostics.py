"""M556-M560: diagnostics for the M475 robust (L1) drill-off fit — uniqueness, sensitivity, leverage and warnings.

Separate from M475: ``core.drilloff_robust`` results, method version, stored cases and replay are unchanged. The
diagnostics are recomputed from a COMPUTED M475 result (its frozen steps) whenever they are shown; they are not
stored in the case and not replay-compared. ``drilloff_robust.summary_lines`` appends ``summary_lines`` below.

* **Uniqueness.** At the fitted breakpoint every interpolating triple whose sum |r| ties the optimum (relative
  ``TIE_REL``) is collected; distinct coefficient vectors mean the L1 optimum is NOT UNIQUE. Over the breakpoint the
  sum |r| curve is sampled on the M475 grid; the set of grid points within ``FLAT_REL`` of the optimum is the flat
  interval - a wide interval means the breakpoint is weakly identified.
* **Sensitivity (leave-one-out).** The M475 search is re-run with each step removed (when at least ``MIN_LOO``
  steps remain); the largest breakpoint shift and any change of the founder decision are reported.
* **Leverage.** Hat values h_ii of the hinge design [1, WOB, max(WOB - W*, 0)] at the fitted W* (the least-squares
  projection; p = 3). h_ii > 2p/n flags a step whose WOB position dominates the fit. LAD resists ROP outliers but not
  WOB (leverage) errors - stated in M475 and repeated here.
* **Warnings** (wording only; no value is changed, E12 bit-performance defaults are untouched): surface WOB basis,
  breakpoint within one tested step of the search edge, fewer than three steps beyond the breakpoint, flagged
  residuals, non-unique optimum, high-leverage steps, a leave-one-out shift of more than one tested WOB step,
  unstable leave-one-out decision.

SCREENING statistics of one test; not a drilling optimiser and not a validated downhole method.
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

DIAGNOSTICS_VERSION = "M556 drill-off L1 diagnostics v1"
TIE_REL = 1e-9
COEF_REL = 1e-7
FLAT_REL = 0.01
MIN_LOO = 5
LEVERAGE_FACTOR = 2.0
UNIQUE, NON_UNIQUE = "UNIQUE", "NOT UNIQUE"


def _steps(result: Mapping[str, Any]):
    usable = [s for s in (result.get("inputs") or {}).get("steps") or []
              if None not in (s.get("wob_klbf"), s.get("rpm"), s.get("rop_ft_hr"))]
    ordered = sorted(usable, key=lambda s: s["wob_klbf"])
    return [float(s["wob_klbf"]) for s in ordered], [float(s["rop_ft_hr"]) for s in ordered]


def tied_optima(xs: Sequence[float], ys: Sequence[float], breakpoint: float) -> List[List[float]]:
    """Distinct coefficient vectors of the interpolating triples that tie the L1 optimum at ``breakpoint``."""
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    design = np.column_stack([np.ones_like(x), x, np.maximum(x - breakpoint, 0.0)])
    out: List[List[float]] = []
    best = math.inf
    fits = []
    for triple in itertools.combinations(range(len(x)), 3):
        system = design[list(triple)]
        if abs(np.linalg.det(system)) <= 1e-9 * max(1.0, float(np.abs(design).max())) ** 2:
            continue
        coef = np.linalg.solve(system, y[list(triple)])
        sad = float(np.abs(y - design @ coef).sum())
        fits.append((sad, coef))
        best = min(best, sad)
    for sad, coef in fits:
        if sad <= best + TIE_REL * max(1.0, best):
            if not any(np.allclose(coef, other, rtol=COEF_REL, atol=COEF_REL) for other in map(np.asarray, out)):
                out.append([float(c) for c in coef])
    return out


def flat_interval(xs: Sequence[float], ys: Sequence[float]) -> Optional[List[float]]:
    from core import drilloff_robust as dr

    lo_index, hi_index = 1, len(xs) - 2
    grid = []
    for k in range(lo_index, hi_index):
        a, b = xs[k], xs[k + 1]
        grid.extend(a + (b - a) * i / dr.GRID for i in range(dr.GRID))
    grid.append(xs[hi_index])
    sads = []
    for b in grid:
        fit = dr.lad_hinge(xs, ys, b)
        sads.append(math.inf if fit is None else fit[1])
    best = min(sads)
    if not math.isfinite(best):
        return None
    inside = [b for b, s in zip(grid, sads) if s <= best + FLAT_REL * max(best, 1e-12) + 1e-12]
    return [min(inside), max(inside)]


def leverage(xs: Sequence[float], breakpoint: float) -> List[float]:
    x = np.asarray(xs, float)
    design = np.column_stack([np.ones_like(x), x, np.maximum(x - breakpoint, 0.0)])
    gram = design.T @ design
    if abs(np.linalg.det(gram)) < 1e-12 * max(1.0, float(np.abs(gram).max())) ** 3:
        return []
    return [float(h) for h in np.einsum("ij,jk,ik->i", design, np.linalg.inv(gram), design)]


def leave_one_out(result: Mapping[str, Any], xs: Sequence[float], ys: Sequence[float]) -> List[Dict[str, Any]]:
    from core import drilloff_robust as dr

    ratio = (result.get("inputs") or {}).get("slope_ratio")
    out = []
    if len(xs) - 1 < MIN_LOO:
        return out
    for i in range(len(xs)):
        sub_x, sub_y = xs[:i] + xs[i + 1:], ys[:i] + ys[i + 1:]
        best = dr.best_breakpoint(list(sub_x), list(sub_y))
        if best is None:
            out.append({"removed_wob_klbf": xs[i], "breakpoint_wob_klbf": None, "founder": None})
            continue
        bp, (_a, b, c), _sad, _vertex = best
        founder = bool(b > 0 and ratio is not None and b + c < ratio * b)
        out.append({"removed_wob_klbf": xs[i], "breakpoint_wob_klbf": bp, "founder": founder})
    return out


def diagnose(result: Mapping[str, Any]) -> Dict[str, Any]:
    from core import drilloff_robust as dr

    if result.get("status") != dr.COMPUTED:
        return {"version": DIAGNOSTICS_VERSION, "status": "NOT ASSESSED", "reason": "the fit was not computed"}
    xs, ys = _steps(result)
    bp = float(result["fitted_breakpoint_wob_klbf"])
    optima = tied_optima(xs, ys, bp)
    flat = flat_interval(xs, ys)
    hats = leverage(xs, bp)
    n, p = len(xs), 3
    high = [x for x, h in zip(xs, hats) if h > LEVERAGE_FACTOR * p / n]
    loo = leave_one_out(result, xs, ys)
    founder = result.get("founder_status") == dr.FOUNDER
    shifts = [abs(r["breakpoint_wob_klbf"] - bp) for r in loo if r["breakpoint_wob_klbf"] is not None]
    flips = [r["removed_wob_klbf"] for r in loo if r["founder"] is not None and r["founder"] != founder]
    spacing = min((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    warnings: List[str] = []
    if result.get("wob_basis") != "downhole":
        warnings.append("WOB basis is surface: the founder WOB is a surface value, not downhole WOB")
    if n >= 4 and (bp - xs[1] <= spacing + 1e-12 or xs[-2] - bp <= spacing + 1e-12):
        warnings.append("the breakpoint lies within one tested step of the search edge; extend the test range")
    if sum(1 for x in xs if x > bp) < 3:
        warnings.append("fewer than three steps beyond the breakpoint; the upper slope rests on few points")
    if result.get("flagged_wob_klbf"):
        warnings.append("residuals flagged at WOB " + ", ".join(f"{w:g}" for w in result["flagged_wob_klbf"])
                        + " klbf; check those steps")
    if len(optima) > 1:
        warnings.append(f"the L1 optimum is not unique ({len(optima)} tied fits at the breakpoint)")
    if high:
        warnings.append("high-leverage step(s) at WOB " + ", ".join(f"{w:g}" for w in high)
                        + " klbf: an error in those WOB values would move the fit (LAD is not robust to that)")
    if shifts and max(shifts) > spacing + 1e-9:
        warnings.append(f"leave-one-out moves the breakpoint by up to {max(shifts):.4g} klbf, more than one tested "
                        f"WOB step ({spacing:.4g} klbf)")
    if flips:
        warnings.append("removing the step at WOB " + ", ".join(f"{w:g}" for w in flips)
                        + " klbf changes the founder decision")
    return {"version": DIAGNOSTICS_VERSION, "status": "COMPUTED", "uniqueness": UNIQUE if len(optima) <= 1
            else NON_UNIQUE, "tied_optima": optima, "flat_interval_wob_klbf": flat, "leverage": hats,
            "leverage_threshold": LEVERAGE_FACTOR * p / n, "high_leverage_wob_klbf": high, "leave_one_out": loo,
            "max_loo_shift_klbf": max(shifts) if shifts else None, "loo_decision_flips_wob_klbf": flips,
            "warnings": warnings}


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    d = diagnose(result)
    if d["status"] != "COMPUTED":
        return []
    lines = [f"Diagnostics ({DIAGNOSTICS_VERSION}, not stored, recomputed): L1 optimum {d['uniqueness']}"
             + (f"; breakpoint weakly identified over {d['flat_interval_wob_klbf'][0]:.4g}-"
                f"{d['flat_interval_wob_klbf'][1]:.4g} klbf (sum |r| within 1 %)" if d["flat_interval_wob_klbf"] else "")
             + "."]
    if d["max_loo_shift_klbf"] is not None:
        lines.append(f"Leave-one-out: largest breakpoint shift {d['max_loo_shift_klbf']:.4g} klbf.")
    lines.extend(f"WARNING: {w}." for w in d["warnings"])
    return lines
