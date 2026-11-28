#!/usr/bin/env python3
"""M539: exact laminar HB concentric-annulus benchmark (SYNTHETIC). Expected values never come from the engine.

References computed here:
* N — Newtonian (n = 1, tau0 = 0): Lamb closed form for the annulus.
* B — Bingham (n = 1): closed-form velocity branches u_in / u_out, plug continuity solved by its own bisection,
  Q by dense trapezoidal integration of 2 pi r u (velocity formulation, not the engine's shear-rate quadrature).
* S — HB parallel-plate closed form for a very narrow annulus (kappa = 0.995): curvature error O(1 - kappa).
* P — power law: Q(8G) / Q(G) = 8^(1/n) exactly.
Timings are measured on this machine and reported, not compared.

Usage::

    PYTHONPATH=. python tools/quality/benchmark_m538_hb_exact.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def lamb(g, ro, kappa, mu):
    ri = kappa * ro
    return math.pi * g / (8 * mu) * (ro ** 4 - ri ** 4 - (ro ** 2 - ri ** 2) ** 2 / math.log(ro / ri))


def bingham(g, ro, kappa, tau0, mu, points=400_001):
    t = g * ro / 2.0

    def u_out(x, lam2):
        return ro / mu * (t * ((1 - x * x) / 2 + lam2 * np.log(x)) - tau0 * (1 - x))

    def u_in(x, lam2):
        return ro / mu * (t * (lam2 * np.log(x / kappa) - (x * x - kappa * kappa) / 2) - tau0 * (x - kappa))

    def edges(lam2):
        b = tau0 / (2 * t)
        return math.sqrt(b * b + lam2) - b, math.sqrt(b * b + lam2) + b

    lo, hi = kappa * kappa + kappa * tau0 / t, 1 - tau0 / t
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        xm, xp = edges(mid)
        lo, hi = (mid, hi) if u_out(xp, mid) - u_in(xm, mid) > 0 else (lo, mid)
    lam2 = 0.5 * (lo + hi)
    xm, xp = edges(lam2)
    x = np.linspace(kappa, 1.0, points)
    u = np.where(x <= xm, u_in(x, lam2), np.where(x >= xp, u_out(x, lam2), u_out(xp, lam2)))
    f = u * x
    return 2 * math.pi * ro ** 2 * float(np.sum((f[1:] + f[:-1]) * np.diff(x)) / 2)


def plates(g, ro, kappa, tau0, k, n):
    h = ro * (1 - kappa) / 2
    m = (n + 1) / n
    a = g * h - tau0
    return 2 * n / ((n + 1) * g * k ** (1 / n)) * (h * a ** m - a ** (m + 1) / (g * (m + 1))) * math.pi * ro * (1 + kappa)


#: name -> (kind, G Pa/m, Ro m, kappa, tau0 Pa, K Pa s^n, n, relative tolerance)
CASES = {
    "N1 kappa 0.01": ("N", 1500.0, 0.1, 0.01, 0.0, 0.03, 1.0, 1e-9),
    "N2 kappa 0.2": ("N", 1500.0, 0.1, 0.2, 0.0, 0.03, 1.0, 1e-9),
    "N3 kappa 0.6": ("N", 900.0, 0.15, 0.6, 0.0, 0.01, 1.0, 1e-9),
    "N4 kappa 0.9": ("N", 5000.0, 0.1, 0.9, 0.0, 0.05, 1.0, 1e-9),
    "B1 kappa 0.05": ("B", 2500.0, 0.1, 0.05, 4.0, 0.02, 1.0, 1e-7),
    "B2 kappa 0.2": ("B", 2500.0, 0.1, 0.2, 8.0, 0.02, 1.0, 1e-7),
    "B3 kappa 0.5": ("B", 2500.0, 0.1, 0.5, 3.0, 0.02, 1.0, 1e-7),
    "B4 kappa 0.7 near onset": ("B", 700.0, 0.1, 0.7, 10.0, 0.02, 1.0, 1e-7),
    "S1 slot n 0.3": ("S", 4.0e5, 0.1, 0.995, 2.0, 0.4, 0.3, 2e-4),
    "S2 slot n 0.6": ("S", 4.0e5, 0.1, 0.995, 2.0, 0.4, 0.6, 2e-4),
    "S3 slot n 1.0": ("S", 4.0e5, 0.1, 0.995, 2.0, 0.4, 1.0, 2e-4),
    "P1 power law n 0.25": ("P", 1000.0, 0.1, 0.25, 0.0, 0.5, 0.25, 1e-9),
    "P2 power law n 0.5": ("P", 1000.0, 0.1, 0.1, 0.0, 0.5, 0.5, 1e-9),
    "P3 power law n 0.8": ("P", 1000.0, 0.1, 0.6, 0.0, 0.5, 0.8, 1e-9),
}


def run(case):
    from core import hydraulics_hb_annulus_exact as ex

    kind, g, ro, kappa, tau0, k, n, tol = case
    t0 = time.perf_counter()
    if kind == "P":
        got = ex.annulus_flow_rate(8 * g, ro, kappa, tau0, k, n) / ex.annulus_flow_rate(g, ro, kappa, tau0, k, n)
        expected = 8.0 ** (1 / n)
    else:
        got = ex.annulus_flow_rate(g, ro, kappa, tau0, k, n)
        expected = {"N": lambda: lamb(g, ro, kappa, k), "B": lambda: bingham(g, ro, kappa, tau0, k),
                    "S": lambda: plates(g, ro, kappa, tau0, k, n)}[kind]()
    seconds = time.perf_counter() - t0
    rel = abs(got / expected - 1)
    return {"kind": kind, "expected": expected, "engine": got, "relative_error": rel, "tolerance": tol,
            "pass": rel <= tol, "seconds": seconds}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    results = {name: run(case) for name, case in CASES.items()}
    for name, r in results.items():
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {name:28s} rel {r['relative_error']:.2e} (tol {r['tolerance']:.0e})"
              f"  {r['seconds'] * 1000:.0f} ms")
    passed = sum(r["pass"] for r in results.values())
    print(f"M538 exact HB annulus benchmark: {passed}/{len(results)} passed")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
