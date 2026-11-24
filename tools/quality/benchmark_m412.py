"""M412 / M417 / M421 / M424 / M425 / M426 / M429 — independent benchmarks added in M401-M460.

Every expected value is computed HERE from a published closed form, exact geometry, an independent numerical
procedure or first-principles physics; the production code is called only to obtain the value under test. Input
class of every case: SYNTHETIC. Tolerances are stated per case with the reason. The 31 M396 cases are reproduced by
``tools/quality/benchmark_m396.py --check`` (not duplicated here).

Groups (numeric, counted):

* R   — R-HYD-2 HB slot annulus (``core.hydraulics_hb_slot``): plane Poiseuille, power-law slot, Buckingham slot
        (bisection), HB slot by Simpson quadrature, the exact concentric annulus (slot-idealisation check), turbulent
        and transitional points with Colebrook solved here by bisection on f (a different algorithm);
* SS  — quasi-steady closed-end surge (``core.surge_swab``): Couette-Poiseuille slot with a moving wall; EMW with the
        exact 12/231 psi/ft per ppg;
* DF  — fitted drill-off (``core.drilloff_fitted``): exact hinge recovered;
* D94 — the 3D closest approach of two straight wells (``AntiCollisionEngine`` ``closest_approach_3d``): the AC2 skew
        geometry (20 m, the value AC2 does NOT test) and a non-planar skew pair by the cross-product distance;
* F   — fishing (``FishingEngine``): steel 490 lb/ft3 plain-end weight, Hooke free point, self-weight stretch in air
        (gamma L^2 / 2E), the published mud form, jar forces;
* B   — bit performance (``BitPerformanceEngine``): revolutions, Bourgoyne full-cycle cost per foot, Jorden-Shirley
        d-exponent, dc with a declared normal gradient, footage-weighted ROP;
* Z   — zero inputs that are values (zero flow, zero trip speed, explicit zero footage);
* U   — unit constants (exact definitions).

Status checks (missing / refused inputs) are listed separately and NOT counted as benchmarks.

``--write`` stores the table (``docs/mission-reports/m401-m460-evidence/m412_benchmarks.txt``); ``--check``
recomputes and fails on any case outside tolerance, any failed status check or any table drift.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "mission-reports" / "m401-m460-evidence" / "m412_benchmarks.txt"
Case = Tuple[str, float, float, float, str]          # id, expected, actual, relative tolerance, note
Status = Tuple[str, str, str, str]                   # id, expected status, actual status, note

IN, FT = 0.0254, 0.3048
GPM = 3.785411784e-3 / 60.0
PPG = 0.45359237 / 3.785411784e-3                     # kg/m3 per lb/gal
LBF = 4.4482216152605
HBU = LBF / (100.0 * FT ** 2)                         # Pa per lbf/100 ft2
PSI = LBF / IN ** 2


def _rel(expected: float, actual: float) -> float:
    return abs(actual) if expected == 0 else abs(actual - expected) / abs(expected)


def _bisect(f, lo, hi, it=200):
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return 0.5 * (lo + hi)


def _colebrook_bisection(re, rr):
    """Darcy f with g(f) = 1/sqrt(f) + 2 log10(rr/3.7 + 2.51/(Re sqrt f)) = 0, by bisection (g decreases in f)."""
    return _bisect(lambda f: -(1 / math.sqrt(f) + 2 * math.log10(rr / 3.7 + 2.51 / (re * math.sqrt(f)))), 1e-4, 1.0)


def _geometry(do_in, di_in, q_gpm):
    gap = (do_in - di_in) / 2 * IN
    area = math.pi / 4 * ((do_in * IN) ** 2 - (di_in * IN) ** 2)
    return gap, q_gpm * GPM / area


def _psi(gradient, length_ft):
    return gradient * length_ft * FT / PSI


def _hb_inputs(**over):
    values = {"hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 10000.0, "flow_rate_gpm": 300.0,
              "density_ppg": 10.0, "tau0_lbf_100ft2": 8.0, "k_lbf_sn_100ft2": 1.2, "n_index": 0.6,
              "roughness_in": 0.0018, "transition_criterion": "founargiotakis-2008"}
    values.update(over)
    return values


# ---- R ------------------------------------------------------------------------------------------------------------
def r_cases() -> List[Case]:
    from core import hydraulics_hb_slot as hb

    out: List[Case] = []
    mu = 0.06
    gap, v = _geometry(8.5, 5.0, 250.0)
    r = hb.evaluate(_hb_inputs(flow_rate_gpm=250.0, tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=mu / HBU, n_index=1.0))
    out.append(("R1 Newtonian laminar = plane Poiseuille 12 mu V L / H^2", _psi(12 * mu * v / gap ** 2, 10000.0),
                r["pressure_loss_psi"], 1e-9, "exact"))
    k, n = 0.9, 0.55
    gap, v = _geometry(8.5, 5.0, 300.0)
    h = gap / 2
    r = hb.evaluate(_hb_inputs(tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=k / HBU, n_index=n))
    out.append(("R2 power-law slot tau_w = K((2n+1)V/(n h))^n", _psi(k * ((2 * n + 1) * v / (n * h)) ** n / h, 10000.0),
                r["pressure_loss_psi"], 1e-9, "exact closed form"))
    mu_p, tau0 = 0.025, 6.0
    gap, v = _geometry(8.5, 5.0, 250.0)
    h = gap / 2
    tw = _bisect(lambda t: t * h / (3 * mu_p) * (1 - 1.5 * tau0 / t + 0.5 * (tau0 / t) ** 3) - v, tau0, 1e4)
    r = hb.evaluate(_hb_inputs(flow_rate_gpm=250.0, tau0_lbf_100ft2=tau0 / HBU, k_lbf_sn_100ft2=mu_p / HBU,
                               n_index=1.0))
    out.append(("R3 Bingham slot (Buckingham form, bisection)", _psi(tw / h, 10000.0), r["pressure_loss_psi"], 1e-8,
                "bisection 200 halvings"))
    tau0, kk, n = 8.0 * HBU, 1.2 * HBU, 0.6
    gap, v = _geometry(8.5, 5.0, 400.0)
    h = gap / 2

    def vel(tau_w, m=4000):
        def gamma(y):
            tau = tau_w * y / h
            return ((tau - tau0) / kk) ** (1 / n) if tau > tau0 else 0.0
        step = h / m
        total = h * gamma(h) + sum((4 if i % 2 else 2) * (i * step) * gamma(i * step) for i in range(1, m))
        return total * step / 3 / h

    tw = _bisect(lambda t: vel(t) - v, tau0 * (1 + 1e-12), 1e4, it=80)
    r = hb.evaluate(_hb_inputs(flow_rate_gpm=400.0))
    out.append(("R4 HB slot laminar by Simpson quadrature of the velocity profile", _psi(tw / h, 10000.0),
                r["pressure_loss_psi"], 2e-5, "quadrature 4000 panels; 2e-5 covers its error"))
    mu = 0.060
    do, di = 8.5 * IN, 5.1 * IN                                     # kappa 0.6
    ro, ri = do / 2, di / 2
    q = 300.0 * GPM
    g_exact = q * 8 * mu / (math.pi * (ro ** 4 - ri ** 4 - (ro ** 2 - ri ** 2) ** 2 / math.log(ro / ri)))
    r = hb.evaluate(_hb_inputs(pipe_od_in=5.1, tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=mu / HBU, n_index=1.0))
    out.append(("R5 slot vs EXACT concentric annulus, Newtonian, kappa 0.6", _psi(g_exact, 10000.0),
                r["pressure_loss_psi"], 1e-2, "slot idealisation error ~0.4 % at kappa 0.6 (stated <= 2.5 %)"))
    mu = 0.002
    gap, v = _geometry(8.5, 5.0, 800.0)
    dh = 2 * gap
    re = 10.0 * PPG * v * dh / mu
    fd = _colebrook_bisection(re, 0.0018 * IN / dh)
    r = hb.evaluate(_hb_inputs(flow_rate_gpm=800.0, tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=mu / HBU, n_index=1.0))
    out.append(("R6 turbulent Newtonian, Colebrook (bisection here), Fanning = Darcy/4",
                _psi(2 * fd / 4 * 10.0 * PPG * v ** 2 / dh, 10000.0), r["pressure_loss_psi"], 1e-8, "exact"))
    mu = 0.020
    gap, v = _geometry(8.5, 5.0, 180.0)
    dh = 2 * gap
    re = 10.0 * PPG * v * dh / mu
    fd = _colebrook_bisection(3000.0, 0.0018 * IN / dh)            # Newtonian n' = 1: Re1 2100, Re2 3000
    f = 24 / 2100 + (fd / 4 - 24 / 2100) * (re - 2100) / 900
    r = hb.evaluate(_hb_inputs(flow_rate_gpm=180.0, tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=mu / HBU, n_index=1.0))
    out.append(("R7 transitional Newtonian, linear blend 2100-3000", _psi(2 * f * 10.0 * PPG * v ** 2 / dh, 10000.0),
                r["pressure_loss_psi"], 1e-8, f"Re {re:.0f}; band per Founargiotakis et al. 2008 at n' 1"))
    smooth = _colebrook_bisection(1e5, 0.0)
    out.append(("R8 Colebrook smooth Re 1e5 vs Moody chart 0.0180", 0.0180, hb.colebrook_darcy(1e5, 0.0)[0], 3e-3,
                f"chart read to 3 sf (bisection here {smooth:.6f})"))
    return out


# ---- SS / DF --------------------------------------------------------------------------------------------------------
def ss_df_cases() -> List[Case]:
    from core import drilloff_fitted as df
    from core import surge_swab as ss

    mu = 0.020
    inputs = {"trip_speed_ft_min": 60.0, "clinging_constant": 0.5, "density_ppg": 10.0, "tau0_lbf_100ft2": 0.0,
              "k_lbf_sn_100ft2": mu / HBU, "n_index": 1.0, "roughness_in": 0.0, "tvd_ft": 10000.0,
              "transition_criterion": "founargiotakis-2008", "pipe_end": "closed"}
    sections = [{"hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 6000.0},
                {"hole_id_in": 8.5, "pipe_od_in": 6.5, "length_ft": 600.0}]
    r = ss.evaluate(inputs, sections)
    vp = 60.0 * FT / 60.0
    total = 0.0
    for sec in sections:
        do, di = sec["hole_id_in"] * IN, sec["pipe_od_in"] * IN
        vf = vp * di ** 2 / (do ** 2 - di ** 2)
        total += _psi(12 * mu * (vf + vp / 2) / ((do - di) / 2) ** 2, sec["length_ft"])
    steps = [{"wob_klbf": w, "rpm": 120.0, "rop_ft_hr": 4 * w if w <= 22.5 else 90 + 0.4 * (w - 22.5)}
             for w in (10.0, 15.0, 20.0, 25.0, 30.0, 35.0)]
    fit = df.evaluate({"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5}, steps)
    return [("SS1 closed-end surge = Couette-Poiseuille slot (K_c 0.5 exact, Newtonian laminar)", total,
             r["surge_psi"], 1e-9, "two sections, moving inner wall"),
            ("SS2 surge EMW = MW + dP / ((12/231) TVD)", 10.0 + total / (12.0 / 231.0 * 10000.0), r["surge_emw_ppg"],
             1e-12, "1 lb/gal over 12 in on 231 in3"),
            ("DF1 fitted breakpoint of an exact hinge", 22.5, fit["fitted_breakpoint_wob_klbf"], 1e-6,
             "break between tested WOB 20 and 25"),
            ("DF2 fitted upper slope of an exact hinge", 0.4, fit["slope_above"], 1e-6, "ft/h per klbf")]


# ---- D94 -------------------------------------------------------------------------------------------------------------
def d94_cases() -> List[Case]:
    from core.engineering.engines.anti_collision import AntiCollisionEngine

    ref = [{"md": 0.0, "north": 0.0, "east": 0.0, "tvd": 0.0}, {"md": 500.0, "north": 0.0, "east": 0.0, "tvd": 500.0}]
    skew = [{"md": 0.0, "north": -50.0, "east": 20.0, "tvd": 0.0},
            {"md": 141.42, "north": 50.0, "east": 20.0, "tvd": 100.0}]
    a = AntiCollisionEngine.screen_clearance(ref, skew, coordinates_unit="m").values["closest_approach_3d"]
    p0, p1 = (0.0, 0.0, 0.0), (300.0, 100.0, 600.0)
    q0, q1 = (200.0, -150.0, 100.0), (-100.0, 250.0, 500.0)

    def sub(x, y):
        return [i - j for i, j in zip(x, y)]

    d1, d2 = sub(p1, p0), sub(q1, q0)
    cross = [d1[1] * d2[2] - d1[2] * d2[1], d1[2] * d2[0] - d1[0] * d2[2], d1[0] * d2[1] - d1[1] * d2[0]]
    dist = abs(sum(c * w for c, w in zip(cross, sub(q0, p0)))) / math.sqrt(sum(c * c for c in cross))
    length_p, length_q = math.dist(p0, p1), math.dist(q0, q1)
    ref2 = [{"md": 0.0, "north": p0[0], "east": p0[1], "tvd": p0[2]},
            {"md": length_p, "north": p1[0], "east": p1[1], "tvd": p1[2]}]
    off2 = [{"md": 0.0, "north": q0[0], "east": q0[1], "tvd": q0[2]},
            {"md": length_q, "north": q1[0], "east": q1[1], "tvd": q1[2]}]
    b = AntiCollisionEngine.screen_clearance(ref2, off2, coordinates_unit="m").values["closest_approach_3d"]
    return [("D94-1 AC2 skew geometry, 3D closest approach (perpendicular offset)", 20.0, a["distance"], 1e-9,
             "exact geometry; AC2 tests the equal-MD value instead"),
            ("D94-2 non-planar skew wells, |(q0-p0).(d1 x d2)| / |d1 x d2|", dist, b["distance"], 1e-6,
             "cross-product line distance; interior closest points (6-dp engine rounding)")]


# ---- F / B ------------------------------------------------------------------------------------------------------------
def fishing_bit_cases() -> List[Case]:
    from core.engineering.engines.bit_performance import BitPerformanceEngine as B
    from core.engineering.engines.fishing import FishingEngine as F

    od, idd = 5.0, 4.276
    area = math.pi / 4 * (od ** 2 - idd ** 2)
    steel_lb_in3_per_ft = 490.0 / 144.0                              # lb/ft per in2 of steel at 490 lb/ft3
    w_plain = steel_lb_in3_per_ft * area
    stretch, pull = 24.0, 40000.0
    hooke = 30e6 * area * stretch / (pull * 12.0)
    length = 10000.0
    air = (65.44 / 231.0) * (12.0 * length) ** 2 / (2 * 30e6)       # gamma_steel (lb/in3) L^2 / 2E, L in in
    mud = length ** 2 * (65.44 - 1.44 * 12.0) / 96_250_000.0
    jar = F.jar_operating_range(200000.0, 0.817, 50000.0).value
    revs = B.bit_revolutions(100.0, 140.0, 20.0).value
    cpf = B.cost_per_foot(48000.0, 10.0, 25000.0, 1500.0, rotating_hours=30.0).value
    d_hand = math.log10(30.0 / (60 * 120.0)) / math.log10(12 * 25000.0 / (1e6 * 8.5))
    rows = [{"depth_in": 1000.0, "depth_out": 1300.0, "hours_on_bottom": 10.0},
            {"depth_in": 1300.0, "depth_out": 1300.0, "hours_on_bottom": 2.0},
            {"depth_in": 1300.0, "depth_out": None, "hours_on_bottom": 5.0},
            {"depth_in": 1300.0, "depth_out": 1500.0, "hours_on_bottom": 8.0}]
    return [("F1 plain-end weight vs steel 490 lb/ft3", w_plain, F.adjusted_weight(od, idd).value, 1.5e-3,
             "engine constant 2.67 vs 2.6725 (rounded) + 2-dp display"),
            ("F2 free point vs Hooke L = E A dL / (12 P), exact body area", hooke,
             F.free_point(stretch, w_plain, pull).value, 1.5e-3, "A ~ W/3.4 vs 490/144 = 3.4028 (0.08 %)"),
            ("F3 self-weight stretch in air = gamma L^2 / 2E", air, F.string_stretch(length, 0.0).value, 1e-3,
             "first principles, 65.44 ppg steel, 231 in3/gal; 2-dp display"),
            ("F4 stretch in 12 ppg mud, published form L^2 (65.44 - 1.44 MW) / 9.625e7", mud,
             F.string_stretch(length, 12.0).value, 1e-3, "textbook form (Poisson factor 1.44 not derived here)"),
            ("F5 jar up force = W BF + overpull", 200000.0 * 0.817 + 50000.0, jar, 1e-6, "arithmetic; 0-dp display"),
            ("B1 bit revolutions = mean RPM x h x 60 / 1000", 120.0 * 20.0 * 60.0 / 1000.0, revs, 1e-12, "k.rev"),
            ("B2 cost per foot, Bourgoyne full cycle (B + R(t_r + t_t)) / F",
             (25000.0 + 48000.0 / 24.0 * (30.0 + 10.0)) / 1500.0, cpf, 1e-4, "2-dp display; currency unlabelled (P9)"),
            ("B3 d-exponent, Jorden & Shirley", d_hand, B.d_exponent(30.0, 120.0, 25000.0, 8.5).value, 1e-4,
             "4-dp display"),
            ("B4 dc = d x normal / actual MW (normal 9.0 declared)", round(d_hand, 4) * 9.0 / 11.0,
             B.d_exponent_corrected(30.0, 120.0, 25000.0, 8.5, 11.0, normal_mw_ppg=9.0).value, 1e-4, "4-dp display"),
            ("B5 footage-weighted ROP over valid pairs only", (300.0 + 0.0 + 200.0) / (10.0 + 2.0 + 8.0),
             B.weighted_rop(rows).value, 1e-9, "explicit zero footage is a pair; a missing depth_out row is not")]


# ---- Z / U ------------------------------------------------------------------------------------------------------------
def zero_unit_cases() -> List[Case]:
    from core import hydraulics_hb_slot as hb
    from core import surge_swab as ss

    r = hb.evaluate(_hb_inputs(flow_rate_gpm=0.0))
    s = ss.evaluate({"trip_speed_ft_min": 0.0, "clinging_constant": 0.45, "density_ppg": 10.0,
                     "tau0_lbf_100ft2": 0.0, "k_lbf_sn_100ft2": 0.5, "n_index": 0.7, "roughness_in": 0.0,
                     "tvd_ft": None, "transition_criterion": "founargiotakis-2008", "pipe_end": "closed"},
                    [{"hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 1000.0}])
    return [("Z1 zero flow is a value: 0 psi friction", 0.0, r["pressure_loss_psi"], 0.0, "NO FLOW, not missing"),
            ("Z2 zero flow: yield onset 4 tau0 L / Dh reported separately",
             _psi(4 * 8.0 * HBU / (3.5 * IN), 10000.0), r["yield_onset_psi"], 1e-12, "exact"),
            ("Z3 zero trip speed: 0 psi surge", 0.0, s["surge_psi"], 0.0, "explicit zero"),
            ("U1 psi/ft per ppg = 12/231", 12.0 / 231.0, ss.PSI_FT_PER_PPG, 1e-12, "exact definition"),
            ("U2 Pa per psi = 4.4482216152605 N / (0.0254 m)^2", 6894.757293168361, hb.PA_PER_PSI, 1e-15, "exact"),
            ("U3 Pa per lbf/100 ft2", 0.4788025898033584, hb.PA_PER_HB_UNIT, 1e-12, "exact")]


def status_checks() -> List[Status]:
    from core import drilloff_fitted as df
    from core import hydraulics_hb_slot as hb
    from core import surge_swab as ss
    from core.engineering.engines.bit_performance import BitPerformanceEngine as B

    base_ss = {"trip_speed_ft_min": 60.0, "clinging_constant": 0.45, "density_ppg": 10.0, "tau0_lbf_100ft2": 0.0,
               "k_lbf_sn_100ft2": 0.5, "n_index": 0.7, "roughness_in": 0.0, "tvd_ft": None,
               "transition_criterion": "founargiotakis-2008", "pipe_end": "open"}
    sec = [{"hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 1000.0}]
    four = [{"wob_klbf": w, "rpm": 120.0, "rop_ft_hr": 3 * w} for w in (10.0, 15.0, 20.0, 25.0)]
    revs = B.bit_revolutions(100.0, None, 20.0)
    return [("S1 HB yield stress not entered", hb.NOT_ASSESSED,
             hb.evaluate(_hb_inputs(tau0_lbf_100ft2=None))["status"], "missing stays missing"),
            ("S2 transition band not declared", hb.NOT_ASSESSED,
             hb.evaluate(_hb_inputs(transition_criterion=None))["status"], "never defaulted"),
            ("S3 wide annulus kappa 0.286", hb.NOT_ASSESSED,
             hb.evaluate(_hb_inputs(hole_id_in=17.5))["status"], "slot idealisation not used"),
            ("S4 open-ended string surge", ss.NOT_ASSESSED, ss.evaluate(base_ss, sec)["status"], "not implemented v1"),
            ("S5 drill-off with 4 steps", df.NOT_ASSESSED,
             df.evaluate({"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5}, four)["status"], "needs >= 5"),
            ("S6 bit revolutions with RPM max missing", "MISSING",
             "MISSING" if not revs.success and revs.value is None else "COMPUTED", "never zero-filled")]


GROUPS: List[Callable[[], List[Case]]] = [r_cases, ss_df_cases, d94_cases, fishing_bit_cases, zero_unit_cases]


def run() -> Tuple[List[str], int]:
    lines = ["# M412 independent benchmarks (expected values never from the production code; input class SYNTHETIC)",
             "id | expected | actual | rel. error | tolerance | result | note"]
    failures = cases = 0
    for group in GROUPS:
        for case_id, expected, actual, tol, note in group():
            cases += 1
            if actual is None or not math.isfinite(actual):
                err, ok = float("inf"), False
            else:
                err = _rel(expected, actual)
                ok = err <= tol
            failures += 0 if ok else 1
            lines.append(f"{case_id} | {expected:.6g} | {actual if actual is None else format(actual, '.6g')} | "
                         f"{err:.2e} | {tol:.0e} | {'PASS' if ok else 'FAIL'} | {note}")
    lines.append(f"TOTAL {cases} benchmark cases, {failures} outside tolerance")
    lines.append("")
    lines.append("# status checks (refusals; not counted as benchmarks)")
    bad = 0
    checks = status_checks()
    for case_id, expected, actual, note in checks:
        ok = expected == actual
        bad += 0 if ok else 1
        lines.append(f"{case_id} | expected {expected} | actual {actual} | {'PASS' if ok else 'FAIL'} | {note}")
    lines.append(f"TOTAL {len(checks)} status checks, {bad} failed")
    return lines, failures + bad


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    lines, failures = run()
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
    if args.check and OUT.exists() and OUT.read_text(encoding="utf-8") != text:
        print("benchmark table drifted from the stored file", file=sys.stderr)
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
