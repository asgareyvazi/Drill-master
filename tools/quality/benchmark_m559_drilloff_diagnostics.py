#!/usr/bin/env python3
"""M559: drill-off L1 diagnostics benchmark (SYNTHETIC). Expected values come from the data construction.

Extends the nine M478 cases (re-run unchanged, their M475 checks repeated) with diagnostics expectations and adds
five construction cases. Every expectation below is derived by hand from how the data are built, not from the engine:

* exact hinge with a founder: the L1 optimum is UNIQUE; when each line holds at least three steps, removing any one
  step leaves an exact hinge with the same knee (both lines keep two points, continuity fixes the intersection) ->
  leave-one-out shift 0 (not asserted when a line holds only two steps: D1, D2);
* exact straight line (N cases): every breakpoint fits exactly -> flat interval = the whole search range
  [W_(2), W_(n-1)];
* knee within one tested step of the search edge -> the edge warning; fewer than three steps above the knee -> the
  upper-slope warning; a surface basis -> the surface warning; outliers -> the flagged-residual warning;
* leverage is recomputed here by a different formulation (QR: h_ii = sum_j Q_ij^2) and compared;
* T1: four steps 0, 1, 2, 3 klbf, breakpoint 1.5, a bump d at 0 klbf. The null vector of the hinge design is
  (-1, 3, -3, 1), so dropping the 0 klbf step and dropping the 3 klbf step both give sum |r| = d: two tied optima
  (NOT UNIQUE) at that breakpoint, checked through ``tied_optima`` directly.

Usage::

    PYTHONPATH=. python tools/quality/benchmark_m559_drilloff_diagnostics.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "quality"))

EDGE = "search edge"
FEW_ABOVE = "fewer than three steps beyond"
SURFACE = "WOB basis is surface"
FLAGGED = "residuals flagged"

#: name -> (a, lower slope, upper slope, knee, WOB list, {WOB: outlier}, basis, expected warning fragments)
EXTRA = {
    "D1 knee one step from the lower edge": (0.0, 4.0, 0.4, 13.0, [8 + 4 * i for i in range(10)], {}, "downhole",
                                             {EDGE}),
    "D2 two steps above the knee": (5.0, 2.0, 0.4, 42.0, [10 + 5 * i for i in range(9)], {}, "downhole",
                                    {FEW_ABOVE, EDGE}),          # 45 - 42 = 3 klbf < one 5 klbf step: also the edge
    "D3 clean mid-range knee, downhole": (5.0, 2.0, 0.4, 32.5, [10 + 5 * i for i in range(10)], {}, "downhole",
                                          set()),
    "D4 surface basis, clean": (5.0, 2.0, 0.4, 32.5, [10 + 5 * i for i in range(10)], {}, "surface", {SURFACE}),
}


def hat_qr(xs, knee):
    import numpy as np

    x = np.asarray(xs, float)
    q, _r = np.linalg.qr(np.column_stack([np.ones_like(x), x, np.maximum(x - knee, 0.0)]))
    return (q ** 2).sum(axis=1)


def run_case(a, b, up, knee, wobs, bumps, basis, expected_warnings=None):
    import benchmark_m478_drilloff_robust as m478

    from core import drilloff_diagnostics as dd
    from core import drilloff_robust as dr

    fn = m478.hinge(a, b, up, knee)
    steps = [{"wob_klbf": float(w), "rpm": 120.0, "rop_ft_hr": fn(w) + bumps.get(w, 0.0)} for w in wobs]
    r = dr.evaluate({"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5, "wob_basis": basis}, steps)
    d = dd.diagnose(r)
    founder = b > 0 and up < 0.5 * b
    xs = sorted(float(w) for w in wobs)
    checks = {"m475_breakpoint": (not founder) or abs(r["breakpoint_wob_klbf"] - knee) <= 1e-6}
    if not bumps:
        if founder:
            checks["unique"] = d["uniqueness"] == dd.UNIQUE
        if founder and min(sum(1 for x in xs if x <= knee), sum(1 for x in xs if x >= knee)) >= 3:
            checks["loo_shift_zero"] = d["max_loo_shift_klbf"] is not None and d["max_loo_shift_klbf"] <= 1e-6
            checks["no_decision_flip"] = d["loo_decision_flips_wob_klbf"] == []
        if not founder:
            checks["flat_whole_range"] = d["flat_interval_wob_klbf"] == [xs[1], xs[-2]]
    else:
        checks["flag_warning"] = any(FLAGGED in w for w in d["warnings"])
    checks["leverage_qr"] = max(abs(h - q) for h, q in zip(d["leverage"],
                                                           hat_qr(xs, r["fitted_breakpoint_wob_klbf"]))) <= 1e-9
    checks["surface_warning"] = (basis == "surface") == any(SURFACE in w for w in d["warnings"])
    if expected_warnings is not None:
        fragments = {EDGE, FEW_ABOVE, SURFACE}
        present = {f for f in fragments if any(f in w for w in d["warnings"])}
        checks["warnings"] = present == expected_warnings
    return {"checks": checks, "passed": all(checks.values()), "uniqueness": d["uniqueness"],
            "flat_interval": d["flat_interval_wob_klbf"], "max_loo_shift": d["max_loo_shift_klbf"],
            "warnings": d["warnings"]}


def tie_case():
    from core import drilloff_diagnostics as dd

    fn = lambda w: 2.0 * w if w <= 1.5 else 3.0 + 0.5 * (w - 1.5)       # noqa: E731
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [fn(x) + (4.0 if x == 0.0 else 0.0) for x in xs]
    optima = dd.tied_optima(xs, ys, 1.5)
    checks = {"two_tied_optima": len(optima) == 2}
    return {"checks": checks, "passed": all(checks.values()), "optima": optima}


def main(argv=None) -> int:
    import benchmark_m478_drilloff_robust as m478

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    results = {}
    for name, case in m478.CASES.items():
        results["M478 " + name] = run_case(*case, basis="surface")
    for name, case in EXTRA.items():
        *params, basis, expected = case
        results[name] = run_case(*params, basis=basis, expected_warnings=expected)
    results["T1 constructed L1 tie (null vector -1, 3, -3, 1)"] = tie_case()
    for name, res in results.items():
        flag = "PASS" if res["passed"] else "FAIL " + ",".join(k for k, ok in res["checks"].items() if not ok)
        print(f"{name:60s} {flag}")
    failed = sum(1 for r in results.values() if not r["passed"])
    print(f"TOTAL {len(results)} benchmark cases, {failed} failed")
    if args.json:
        from core import drilloff_diagnostics as dd
        args.json.write_text(json.dumps({"version": dd.DIAGNOSTICS_VERSION, "input_class": "SYNTHETIC",
                                         "cases": results, "failed": failed}, indent=2, sort_keys=True, default=str)
                             + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
