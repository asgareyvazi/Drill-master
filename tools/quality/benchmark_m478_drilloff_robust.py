#!/usr/bin/env python3
"""M478: robust (L1) drill-off v2 benchmark (SYNTHETIC). Expected values come from the data construction, not the engine.

Every case is generated HERE on a continuous hinge ROP = a + b W + c max(W - W*, 0) with known (a, b, b + c, W*).
Gross ROP outliers are then added at stated WOB values. The expected L1 result is the constructing hinge, with
sum |r| = sum |outliers| and exactly the outlier WOB values flagged. Cases where the outliers outnumber what one side
of the knee can absorb are excluded on purpose: LAD does not claim to recover those. For each case the M423
least-squares breakpoint is also reported for comparison. It is informational only and is not checked, since the
method is unchanged. Timings are measured on this machine; they are reported, not compared.

Usage::

    PYTHONPATH=. python tools/quality/benchmark_m478_drilloff_robust.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TOL_BREAK = 1e-6        # klbf
TOL_SLOPE = 1e-8        # ft/h/klbf
TOL_SAD = 1e-7          # ft/h


def hinge(a, b, up, knee):
    return lambda w: a + b * w if w <= knee else a + b * knee + up * (w - knee)


#: name -> (a, lower slope, upper slope, knee, WOB list, {WOB: outlier ft/h})
CASES = {
    "H1 exact, knee between steps": (0.0, 4.0, 0.4, 26.0, [8 + 4 * i for i in range(10)], {}),
    "H2 exact, knee on a step": (5.0, 2.0, 0.4, 30.0, [10 + 5 * i for i in range(11)], {}),
    "H3 exact, flat upper slope": (12.0, 3.0, 0.0, 22.0, [10 + 2 * i for i in range(12)], {}),
    "O1 +40 below the knee (M423 limitation case)": (0.0, 4.0, 0.4, 26.0, [8 + 4 * i for i in range(10)], {16: 40.0}),
    "O2 +40 just above the knee": (5.0, 2.0, 0.4, 30.0, [10 + 5 * i for i in range(11)], {35: 40.0}),
    "O3 +40 at the knee step": (5.0, 2.0, 0.4, 30.0, [10 + 5 * i for i in range(11)], {30: 40.0}),
    "O4 two outliers of opposite sign": (5.0, 2.0, 0.4, 30.0, [10 + 5 * i for i in range(11)], {35: -30.0, 50: 25.0}),
    "O5 drop to zero ROP (stall) above the knee": (12.0, 3.0, 0.0, 22.0, [10 + 2 * i for i in range(12)], {28: -78.0}),
    "N1 linear, no founder": (5.0, 3.0, 3.0, 25.0, [10 + 3 * i for i in range(8)], {}),
}


def run(case):
    from core import drilloff_fitted as df
    from core import drilloff_robust as dr

    a, b, up, knee, wobs, bumps = case
    fn = hinge(a, b, up, knee)
    steps = [{"wob_klbf": float(w), "rpm": 120.0, "rop_ft_hr": fn(w) + bumps.get(w, 0.0)} for w in wobs]
    params = {"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5, "wob_basis": "surface"}
    t0 = time.perf_counter()
    r = dr.evaluate(params, steps)
    seconds = time.perf_counter() - t0
    founder_expected = b > 0 and up < 0.5 * b
    checks = {
        "founder_status": r["founder_status"] == (dr.FOUNDER if founder_expected else dr.NO_FOUNDER),
        "sum_abs_residuals": abs(r["sum_abs_residuals"] - sum(abs(v) for v in bumps.values())) <= TOL_SAD,
        "flagged": sorted(r["flagged_wob_klbf"]) == sorted(float(w) for w in bumps),
        "slope_below": abs(r["slope_below"] - b) <= TOL_SLOPE,
        "slope_above": abs(r["slope_above"] - up) <= TOL_SLOPE,
        "intercept": abs(r["intercept"] - a) <= 1e-7,
    }
    if founder_expected:
        checks["breakpoint"] = abs(r["breakpoint_wob_klbf"] - knee) <= TOL_BREAK
    ls = df.evaluate({"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5}, steps)
    return {"expected": {"knee": knee if founder_expected else None, "slope_below": b, "slope_above": up,
                         "intercept": a, "outliers": {str(k): v for k, v in bumps.items()}},
            "l1": {"breakpoint": r["breakpoint_wob_klbf"], "fitted_breakpoint": round(r["fitted_breakpoint_wob_klbf"], 9),
                   "founder_status": r["founder_status"], "flagged": r["flagged_wob_klbf"],
                   "sum_abs_residuals": round(r["sum_abs_residuals"], 9)},
            "m423_least_squares_breakpoint_info": round(ls["fitted_breakpoint_wob_klbf"], 6),
            "checks": checks, "passed": all(checks.values()), "seconds": round(seconds, 4)}


def timing():
    from core import drilloff_robust as dr

    rng = random.Random(478)
    fn = hinge(5.0, 2.0, 0.4, 30.0)
    out = {}
    for n in (10, 20, 30):
        wobs = [10 + 40 * i / (n - 1) for i in range(n)]
        steps = [{"wob_klbf": w, "rpm": 120.0, "rop_ft_hr": fn(w) + rng.uniform(-1, 1)} for w in wobs]
        t0 = time.perf_counter()
        dr.evaluate({"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5, "wob_basis": "downhole"}, steps)
        out[str(n)] = round(time.perf_counter() - t0, 3)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    results = {name: run(case) for name, case in CASES.items()}
    for name, res in results.items():
        flag = "PASS" if res["passed"] else "FAIL " + ",".join(k for k, ok in res["checks"].items() if not ok)
        print(f"{name:52s} L1 {res['l1']['fitted_breakpoint']:>10.6f}  LS(info) "
              f"{res['m423_least_squares_breakpoint_info']:>10.6f}  {flag}")
    failed = sum(1 for r in results.values() if not r["passed"])
    times = timing()
    print(f"timing (s) by step count: {times}")
    print(f"TOTAL {len(results)} benchmark cases, {failed} failed")
    if args.json:
        from core import drilloff_robust as dr
        args.json.write_text(json.dumps({"method": dr.METHOD_ID, "version": dr.METHOD_VERSION, "input_class": "SYNTHETIC",
                                         "cases": results, "failed": failed, "timing_seconds": times},
                                        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
