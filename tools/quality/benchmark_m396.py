"""M396 — independent engineering benchmarks for domains M349 did not cover.

Every expected value is computed HERE from a published closed form or exact geometry; the production engine is
called only to obtain the value under test. Tolerances are stated per group with the reason.

Groups:

* H  — circulating-system hydraulics (W13 engine through ``core.hydraulics_workflow``): laminar Bingham pipe and
       annular losses (API RP 13D field form), ECD = MW + APL / (0.052 TVD), bit ΔP, P8 density divisor 7.48052;
* S  — survey minimum curvature: a quarter circle in a vertical plane (TVD = N = R exactly) and a straight slant;
* TD — torque and drag: vertical string (no friction contribution, hookload = buoyed weight − WOB, torque 0) and the
       side force of a straight slant (w_b L sin θ);
* AC — anti-collision centre-line separation of parallel and skew straight wells (exact geometry);
* CS — casing: API 5C3 Barlow burst 0.875·2·Yp·t/D and pipe-body yield π/4 (D² − d²) Yp;
* M  — MSE (Teale 1965): WOB / A + 120 π N T / (A ROP);
* WC — kill sheet (IWCF form): KMW = OMW + SIDPP / (0.052 TVD), ICP = SCR + SIDPP, FCP = SCR · KMW / OMW.

``--write`` stores the table; ``--check`` recomputes and fails on any case outside tolerance or any table drift.
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

OUT = ROOT / "docs" / "mission-reports" / "m361-m400-evidence" / "m396_benchmarks.txt"
FT = 1 / 0.3048
Case = Tuple[str, float, float, float, str]          # id, expected, actual, relative tolerance, note


def _rel(expected: float, actual: float) -> float:
    if expected == 0:
        return abs(actual)
    return abs(actual - expected) / abs(expected)


# ---- H: hydraulics ----------------------------------------------------------------------------------------
H_VALUES = {
    "pumps": [{"name": "BM P1", "output_bbl_stk": 0.1, "spm": 20.0, "max_pressure": 0.0, "hp": 0.0}],   # 84 gpm
    "pipes": [{"type": "Drill Pipe", "od": 5.0, "id": 4.276, "length": 2000.0, "weight": 19.5}],
    "casings": [{"type": "Open Hole", "od": 8.5, "id": 8.5, "from": 0.0, "to": 2000.0}],
    "nozzles": [{"size": 12, "qty": 3}], "model": "Bingham Plastic", "confirmed": True,
    "mw": 74.8052, "pv": 20.0, "yp": 15.0, "t600": 55.0, "t300": 35.0, "t6": 0.0, "t3": 0.0,
    "standpipe_length": 30.0, "standpipe_id": 4.0, "hose_length": 0.0, "hose_id": 0.0, "bit_diameter": 8.5,
    "well_type": "Vertical", "kop": 0.0, "eob": 0.0, "max_inc": 0.0, "build_rate": 0.0, "bit_depth": 2000.0,
}


def hydraulics_cases() -> List[Case]:
    from core import hydraulics_workflow as hw

    r = hw.evaluate(H_VALUES)
    base = r["base"]
    q, mw_ppg, length_ft = 84.0, 74.8052 / 7.48052, 2000.0 * FT              # 10.0 ppg exactly (P8)
    pv, yp, d, dh, dp = 20.0, 15.0, 4.276, 8.5, 5.0
    v_pipe = q / (2.448 * d ** 2)                                             # ft/s
    pipe = pv * v_pipe * length_ft / (1500 * d ** 2) + yp * length_ft / (225 * d)
    gap = dh - dp
    v_ann = q / (2.448 * (dh ** 2 - dp ** 2))
    ann = pv * v_ann * length_ft / (1000 * gap ** 2) + yp * length_ft / (200 * gap)
    v_sp, sp_ft = q / (2.448 * 4.0 ** 2), 30.0 * 3.28084                       # engine converts m with 3.28084
    surface = pv * v_sp * sp_ft / (1500 * 4.0 ** 2) + yp * sp_ft / (225 * 4.0)
    tfa = 3 * math.pi / 4 * (12 / 32) ** 2
    bit = q ** 2 * mw_ppg / (10858 * tfa ** 2)
    ecd = mw_ppg + ann / (0.052 * length_ft)
    regimes = {row["kind"]: row["regime"] for row in __import__("core.w13_hydraulics", fromlist=["x"]).component_rows(
        hw._engine_run(H_VALUES)[1]) if row["regime"]}
    note = f"regimes {regimes}"
    return [("H1 string loss, laminar Bingham pipe", pipe, base["string_loss_psi"], 2e-3, note),
            ("H2 annular loss, laminar Bingham annulus", ann, base["annular_loss_psi"], 2e-3, note),
            ("H3 bit nozzle ΔP", bit, base["bit_loss_psi"], 1e-3, "ΔP = Q² MW / (10858 TFA²)"),
            ("H4 ECD at bit", ecd, base["ecd_at_bit_ppg"], 2e-4, "MW + APL / (0.052 TVD); MW = 74.8052 pcf / 7.48052"),
            ("H5 surface line (30 m standpipe, 4 in ID)", surface, base["surface_loss_psi"], 3e-3, "laminar pipe form"),
            ("H6 predicted SPP = sum of components", surface + pipe + ann + bit, base["spp_psi"], 2e-3,
             "surface + string + annulus + bit")]


# ---- S: survey ----------------------------------------------------------------------------------------------
def survey_cases() -> List[Case]:
    from core.engineering.engines.trajectory import TrajectoryCalculator

    length = 900.0
    radius = length / (math.pi / 2)
    arc = TrajectoryCalculator.calculate([{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": length, "inc": 90.0, "azi": 0.0}],
                                         vs_azimuth=0.0)[-1]
    slant_len = 500.0
    slant = TrajectoryCalculator.calculate([{"md": 0.0, "inc": 30.0, "azi": 45.0},
                                            {"md": slant_len, "inc": 30.0, "azi": 45.0}], vs_azimuth=45.0)[-1]
    return [("S1 quarter circle TVD = R", radius, arc["tvd"], 1e-9, "exact for a circular arc"),
            ("S2 quarter circle north = R", radius, arc["north"], 1e-9, "exact"),
            ("S3 quarter circle DLS (deg/30 m)", 90.0 / length * 30.0, arc["dls"], 1e-6, "90° over 900 m"),
            ("S4 quarter circle VS (azimuth 0)", radius, arc["vs"], 1e-9, "VS = north"),
            ("S5 slant TVD", slant_len * math.cos(math.radians(30)), slant["tvd"], 1e-9, "L cos I"),
            ("S6 slant east", slant_len * math.sin(math.radians(30)) * math.sin(math.radians(45)), slant["east"], 1e-9,
             "L sin I sin A"),
            ("S7 slant VS along 45°", slant_len * math.sin(math.radians(30)), slant["vs"], 1e-9, "horizontal departure")]


# ---- TD: torque and drag ----------------------------------------------------------------------------------
def td_cases() -> List[Case]:
    from core.engineering.engines.torque_drag import TorqueDragEngine

    vertical = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 2000.0, "inc": 0.0, "azi": 0.0}]
    pipe = [{"name": "BM DP", "od_in": 5.0, "id_in": 4.276, "length_m": 2000.0, "weight_ppf": 19.5}]
    bf = 1 - 10.0 / 65.5                                                      # API buoyancy, steel 65.5 ppg
    buoyed = 19.5 * 2000.0 * FT * bf / 1000.0                                  # klbf
    r = TorqueDragEngine.calculate(vertical, pipe, 10.0, 0.3, wob_klbf=10.0).values
    slant = [{"md": 0.0, "inc": 60.0, "azi": 0.0}, {"md": 1000.0, "inc": 60.0, "azi": 0.0}]
    pipe_s = [{"name": "BM DP", "od_in": 5.0, "id_in": 4.276, "length_m": 1000.0, "weight_ppf": 19.5}]
    rs = TorqueDragEngine.calculate(slant, pipe_s, 10.0, 0.3).values
    side = 19.5 * 1000.0 * FT * bf * math.sin(math.radians(60))
    return [("TD1 vertical pickup = buoyed − WOB", buoyed - 10.0, r["hookload_pickup"], 1e-3, "no normal force; 0.01 klbf display"),
            ("TD2 vertical slack-off = pickup", buoyed - 10.0, r["hookload_slackoff"], 1e-3, "friction has no effect"),
            ("TD3 vertical rotating torque", 0.0, r["surface_torque_rotating_ft_lbf"], 1e-9, "Fn = 0"),
            ("TD4 slant side force (rotating)", side, rs["side_force_profile"][0]["side_force_lbf"], 1e-4,
             "Σ w_b ΔL sin 60°; 0.1 lbf display")]


# ---- AC: anti-collision -----------------------------------------------------------------------------------
def ac_cases() -> List[Case]:
    from core.engineering.engines.anti_collision import AntiCollisionEngine

    ref = [{"md": md, "north": 0.0, "east": 0.0, "tvd": md} for md in (0.0, 500.0, 1000.0)]
    parallel = [{"md": md, "north": 10.0, "east": 0.0, "tvd": md} for md in (0.0, 500.0, 1000.0)]
    skew = [{"md": 0.0, "north": -50.0, "east": 20.0, "tvd": 0.0}, {"md": 141.42, "north": 50.0, "east": 20.0, "tvd": 100.0}]
    a = AntiCollisionEngine.screen_clearance(ref, parallel, coordinates_unit="m").values
    b = AntiCollisionEngine.screen_clearance(ref[:2], skew, coordinates_unit="m").values
    # the engine separates points at EQUAL measured depth (its declared method), not the geometric closest approach
    # of the two curves (which would be 20 m here). Equal-MD distance² = (k m − 50)² + 20² + ((1 − k) m)², k = 100/141.42
    k = 100.0 / 141.42
    m_star = min(max(50.0 * k / (k ** 2 + (1 - k) ** 2), 0.0), 141.42)
    equal_md = math.sqrt((k * m_star - 50.0) ** 2 + 20.0 ** 2 + ((1 - k) * m_star) ** 2)
    return [("AC1 parallel wells 10 m apart", 10.0, a["minimum_separation"], 1e-9, "exact"),
            ("AC2 skew well, minimum equal-MD separation", equal_md, b["minimum_separation"], 1e-6,
             "exact minimisation; NOT the 3D closest approach (20 m)")]


# ---- CS / M / WC ------------------------------------------------------------------------------------------
def casing_mse_wc_cases() -> List[Case]:
    from core.engineering.engines.casing import CasingEngine
    from core.engineering.engines.mse import MSEEngine
    from core.engineering.engines.well_control import WellControlEngine

    burst = CasingEngine.burst(9.625, 0.472, 80000.0).value
    tensile = CasingEngine.tensile(9.625, 8.681, 80000.0).value
    area = math.pi / 4 * 8.5 ** 2
    mse = MSEEngine.calculate(25000.0, 120.0, 12000.0, 60.0, 8.5).value
    kmw = WellControlEngine.calculate_kill_mw(10.0, 500.0, 10000.0)
    icp = WellControlEngine.calculate_icp(800.0, 500.0)
    fcp = WellControlEngine.calculate_fcp(800.0, 10.0 + 500.0 / (0.052 * 10000.0), 10.0)
    return [("CS1 API 5C3 Barlow burst", 0.875 * 2 * 80000 * 0.472 / 9.625, burst, 1e-3, "display rounding"),
            ("CS2 pipe-body yield", math.pi / 4 * (9.625 ** 2 - 8.681 ** 2) * 80000, tensile, 1e-4, "display rounding"),
            ("M1 MSE Teale", 25000 / area + 120 * math.pi * 120 * 12000 / (area * 60), mse, 1e-3, "display rounding"),
            ("WC1 kill mud weight", 10.0 + 500.0 / (0.052 * 10000.0), kmw, 1e-3, "TRAINING AID; display rounding"),
            ("WC2 ICP", 1300.0, icp, 1e-9, "SCR + SIDPP"),
            ("WC3 FCP", 800.0 * (10.0 + 500.0 / 520.0) / 10.0, fcp, 1e-3, "SCR × KMW / OMW")]


GROUPS: List[Callable[[], List[Case]]] = [hydraulics_cases, survey_cases, td_cases, ac_cases, casing_mse_wc_cases]


def run() -> Tuple[List[str], int]:
    lines = ["# M396 independent benchmarks (expected values from closed forms, never from the engine)",
             "id | expected | actual | rel. error | tolerance | result | note"]
    failures = 0
    for group in GROUPS:
        for case_id, expected, actual, tol, note in group():
            if actual is None or not math.isfinite(actual):
                err, ok = float("inf"), False
            else:
                err = _rel(expected, actual)
                ok = err <= tol
            failures += 0 if ok else 1
            lines.append(f"{case_id} | {expected:.6g} | {actual if actual is None else format(actual, '.6g')} | "
                         f"{err:.2e} | {tol:.0e} | {'PASS' if ok else 'FAIL'} | {note}")
    lines.append(f"TOTAL {len(lines) - 2} cases, {failures} outside tolerance")
    return lines, failures


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
