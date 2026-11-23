"""M349: engineering benchmarks for the M314 / M317 / M318 calculations against independent references.

Every reference value is computed HERE, from a published closed form or from an independent fine-step integration.
It never comes from the engine under test, and no engine constant is imported:

* M314 bit hydraulics: Bourgoyne et al., *Applied Drilling Engineering* (SPE Textbook 2), eqs. 4.85 (bit pressure
  drop, ``8.311e-5 ρ q² / (Cd² At²)``, Cd = 0.95), 4.86 (nozzle velocity ``0.3208 q / At``) and 4.89 (jet impact force
  ``0.01823 Cd q √(ρ ΔPb)``). Hydraulic horsepower ``ΔP q / 1714`` and HSI over the bit area ``π d² / 4``.
* M317 cement volumes: exact geometry. Area ``π/4 (D² − d²)`` in² ÷ 144 in²/ft² and 9702/1728 ft³ per US bbl
  (231 in³/gal × 42 gal / 1728 in³/ft³); 1 m = 1/0.3048 ft (exact).
* M318 torque and drag: (a) the straight slant hole in closed form,
  ``F = w_b L (cos θ ± μ sin θ)`` and ``T = μ w_b L sin θ · r``; (b) a build-and-turn well against the same
  Johancsik equations integrated here at 0.05 m steps (convergence reference); (c) invariance: the answer must
  not depend on how one pipe is split into drill-string entries (this check found D92).

``--write`` stores the results as evidence; ``--check`` recomputes them and fails when a case is outside its tolerance
or the stored evidence is stale. Tolerances are stated per case, with the reason (rounding of displayed results,
the textbook constant's own precision, discretisation).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE = ROOT / "docs" / "mission-reports" / "m321-m360-evidence" / "m349_benchmarks.json"
VERSION = "M349 v1"
FT_PER_M = 1 / 0.3048                     # exact
FT3_PER_BBL = 231 * 42 / 1728             # exact US oil barrel
CD = 0.95                                 # Bourgoyne's nozzle discharge coefficient
STEEL_PPG = 65.5                          # the stated buoyancy basis (BF = 1 − MW/65.5)


def _case(group: str, name: str, quantity: str, reference: float, computed: float, tolerance: float,
          basis: str, why: str) -> Dict[str, Any]:
    error = abs(computed - reference) / abs(reference) if reference else abs(computed)
    return {"group": group, "case": name, "quantity": quantity, "reference": round(reference, 6),
            "computed": round(computed, 6), "relative_error": round(error, 8), "tolerance": tolerance,
            "pass": error <= tolerance, "reference_basis": basis, "tolerance_reason": why}


# ---- M314 ---------------------------------------------------------------------------------------------------------
HYDRAULICS = [   # (name, gpm, ppg, nozzle sizes in 32nds, bit in)
    ("3x12 8.5in 500gpm 12ppg", 500.0, 12.0, [12, 12, 12], 8.5),
    ("3x14+1x12 12.25in 850gpm 10ppg", 850.0, 10.0, [14, 14, 14, 12], 12.25),
    ("6x11 8.5in 380gpm 15.5ppg", 380.0, 15.5, [11] * 6, 8.5),
]
ROUNDING = 0.002   # the engine rounds ΔP to 0.1 psi, HSI to 0.01 hp/in², velocity to 0.1 ft/s (≤ 0.08 % here)


def _m314() -> List[Dict[str, Any]]:
    from core import ddr_hydraulics_check as hc

    out = []
    for name, q, mw, sizes, bit in HYDRAULICS:
        tfa = sum(math.pi / 4 * (s / 32) ** 2 for s in sizes)
        nozzles = json.dumps([{"row": i + 1, "size_32nd": s, "quantity": 1} for i, s in enumerate(sizes)])
        derived = hc.tfa_from_nozzles(nozzles)["value"]
        inputs = {"bit_size_in": {"value": bit}, "tfa_recorded_in2": {"value": None},
                  "tfa_nozzles_in2": {"value": derived}, "mw_ppg": {"value": mw}, "flow_min_gpm": {"value": q},
                  "flow_max_gpm": {"value": None}, "hsi_recorded": {"value": None}}
        result = hc.evaluate({"report_id": 0, "well_id": 0, "drilling_parameters_id": 0, "inputs": inputs,
                              "problems": []})
        got = result["computed"]["min"]
        dp = 8.311e-5 * mw * q ** 2 / (CD ** 2 * tfa ** 2)
        hhp = dp * q / 1714
        hsi = hhp / (math.pi / 4 * bit ** 2)
        vn = 0.3208 * q / tfa
        fj = 0.01823 * CD * q * math.sqrt(mw * dp)
        out += [
            _case("M314", name, "TFA from nozzles (in²)", tfa, derived, 1e-9, "Σ π/4 (s/32)²", "exact geometry"),
            _case("M314", name, "bit pressure drop (psi)", dp, got["bit_pressure_drop_psi"], ROUNDING,
                  "Bourgoyne eq. 4.85, Cd 0.95", "10858 = 0.9025/8.311e-5 to 0.01 %; display rounding"),
            _case("M314", name, "HSI (hp/in²)", hsi, got["hsi"], ROUNDING, "ΔP q / 1714 over π d²/4",
                  "display rounding to 0.01 hp/in²"),
            _case("M314", name, "jet velocity (ft/s)", vn, got["jet_velocity_fps"], ROUNDING,
                  "Bourgoyne eq. 4.86", "1/3.117 = 0.32082; display rounding"),
            _case("M314", name, "impact force (lbf)", fj, got["impact_force_lbs"], 0.005,
                  "Bourgoyne eq. 4.89, Cd 0.95", "MW q v / 1930 and 0.01823 Cd q √(ρΔP) are two published "
                  "forms; they agree to 0.3 %"),
        ]
    return out


# ---- M317 ---------------------------------------------------------------------------------------------------------
ARCH = [
    {"kind": "section", "name": "12-1/4 in hole", "top_md": 0, "bottom_md": 1000, "hole_in": 12.25},
    {"kind": "casing", "name": "9-5/8 csg", "top_md": 0, "bottom_md": 1000, "od_in": 9.625, "id_in": 8.681,
     "hole_in": 12.25},
    {"kind": "shoe", "name": "9-5/8 csg", "top_md": 1000},
    {"kind": "cement", "name": "9-5/8 csg", "top_md": 500, "bottom_md": 1000},
]


def _bbl(area_in2: float, length_m: float) -> float:
    return area_in2 / 144 * length_m * FT_PER_M / FT3_PER_BBL


def _m317() -> List[Dict[str, Any]]:
    from core import cement_job_reconciliation as cj
    from core import well_architecture as wa

    revision = {"id": 0, "revision": 1, "well_id": 1, "components": ARCH,
                "components_sha256": wa.components_sha256(ARCH)}
    out = []
    for name, sacks, yield_value, unit, cubic_ft in (("500 sk x 1.15 ft3/sk", 500, 1.15, "ft3/sk", 1.15),
                                                     ("620 sk x 8.6 gal/sk", 620, 8.6, "gal/sk", 8.6 * 231 / 1728),
                                                     ("400 sk x 37.4 L/sk", 400, 37.4, "L/sk",
                                                      37.4 / 1000 / 0.3048 ** 3)):
        job = {"well_id": 1, "sacks": sacks, "yield": yield_value, "toc_m": 400.0, "boc_m": 1000.0,
               "displacement_bbl": 238.0, "recorded_zero": []}
        result = cj.compute(job, revision, "9-5/8 csg", yield_unit=unit)
        out.append(_case("M317", name, "pumped slurry (bbl)", sacks * cubic_ft / FT3_PER_BBL, result["pumped_bbl"],
                         1e-4, "sacks × yield in ft³ ÷ 9702/1728 ft³/bbl",
                         "the cement engine's 5.6146 ft³/bbl is the exact 5.614583 to 0.0003 %"))
    job = {"well_id": 1, "sacks": 500, "yield": 1.15, "toc_m": 400.0, "boc_m": 1000.0, "displacement_bbl": 238.0,
           "recorded_zero": []}
    result = cj.compute(job, revision, "9-5/8 csg", yield_unit="ft3/sk")
    out.append(_case("M317", "12.25 x 9.625 in, 400-1000 m", "gauge annulus (bbl)",
                     _bbl(math.pi / 4 * (12.25 ** 2 - 9.625 ** 2), 600.0), result["gauge_bbl"], 1e-4,
                     "π/4 (D² − d²) ÷ 144 × L ÷ 9702/1728", "1029.4 is the exact 1029.42 to 0.002 %"))
    out.append(_case("M317", "8.681 in ID, 0-1000 m", "capacity to the shoe (bbl)",
                     _bbl(math.pi / 4 * 8.681 ** 2, 1000.0), result["displacement"]["capacity_to_shoe_bbl"], 1e-4,
                     "π/4 ID² ÷ 144 × L ÷ 9702/1728", "1029.4 constant; 3.28084 ft/m is exact to 1e-7"))
    return out


# ---- M318 ---------------------------------------------------------------------------------------------------------
PIPE = {"od": 5.0, "id": 4.276, "weight": 19.5}
LENGTH_M = 3048.0
MW_PPG = 10.0
BUILD = [{"md": 0, "inc": 0, "azi": 0}, {"md": 500, "inc": 0, "azi": 0}, {"md": 1500, "inc": 45, "azi": 30},
         {"md": 3048, "inc": 60, "azi": 40}]


def _string(entries: int) -> List[Dict[str, Any]]:
    return [{"name": f"DP {i + 1}", "length": LENGTH_M / entries, **PIPE} for i in range(entries)]


def _reference_integration(survey, ff: float, step_m: float = 0.05) -> Dict[str, float]:
    """Johancsik soft string, bit to surface, at ``step_m`` (inclination and azimuth linear in MD between stations)."""
    def at(md):
        for a, b in zip(survey, survey[1:]):
            if b["md"] >= md:
                f = (md - a["md"]) / (b["md"] - a["md"])
                return a["inc"] + f * (b["inc"] - a["inc"]), a["azi"] + f * (b["azi"] - a["azi"])
        return survey[-1]["inc"], survey[-1]["azi"]

    bf = 1 - MW_PPG / STEEL_PPG
    w_step = PIPE["weight"] * step_m * FT_PER_M * bf
    radius_ft = PIPE["od"] / 24
    forces = {"pickup": 0.0, "slackoff": 0.0, "rotating": 0.0}
    torque = 0.0
    for k in range(int(round(LENGTH_M / step_m))):
        bottom = LENGTH_M - k * step_m
        (i1, a1), (i2, a2) = at(bottom), at(bottom - step_m)
        inc, d_inc, d_azi = math.radians((i1 + i2) / 2), math.radians(i2 - i1), math.radians(a2 - a1)
        for mode, force in forces.items():
            normal = math.hypot(force * math.sin(inc) * d_azi, force * d_inc + w_step * math.sin(inc))
            sign = {"pickup": 1, "slackoff": -1, "rotating": 0}[mode]
            forces[mode] = force + w_step * math.cos(inc) + sign * ff * normal
            if mode == "rotating":
                torque += ff * normal * radius_ft
    return {"pickup": forces["pickup"] / 1000, "slackoff": forces["slackoff"] / 1000, "torque": torque}


def _engine(survey, entries: int, ff: float):
    from core.engineering.engines.torque_drag import TorqueDragEngine

    result = TorqueDragEngine.calculate(survey, _string(entries), MW_PPG, ff)
    if not result.success:
        raise RuntimeError(result.error)
    v = result.values
    return {"pickup": v["hookload_pickup"], "slackoff": v["hookload_slackoff"],
            "torque": v["surface_torque_rotating_ft_lbf"]}


def _m318() -> List[Dict[str, Any]]:
    out = []
    bf = 1 - MW_PPG / STEEL_PPG
    weight = PIPE["weight"] * LENGTH_M * FT_PER_M * bf
    for theta in (30.0, 60.0):
        survey = [{"md": 0, "inc": theta, "azi": 0}, {"md": LENGTH_M, "inc": theta, "azi": 0}]
        c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))
        for ff in (0.2, 0.4):
            got = _engine(survey, 1, ff)
            name = f"slant {theta:g} deg FF {ff:g}"
            basis = "w_b L (cos θ ± μ sin θ); T = μ w_b L sin θ · OD/24"
            out += [_case("M318", name, "pickup (klbf)", weight * (c + ff * s) / 1000, got["pickup"], 1e-4, basis,
                          "display rounding to 0.01 klbf"),
                    _case("M318", name, "slack-off (klbf)", weight * (c - ff * s) / 1000, got["slackoff"], 1e-4, basis,
                          "display rounding to 0.01 klbf"),
                    _case("M318", name, "rotating torque (ft·lbf)", ff * weight * s * PIPE["od"] / 24, got["torque"],
                          1e-4, basis, "display rounding to 0.1 ft·lbf")]
    for ff in (0.2, 0.3):
        ref = _reference_integration(BUILD, ff)
        for entries in (1, 10):
            got = _engine(BUILD, entries, ff)
            name = f"build-and-turn FF {ff:g}, pipe as {entries} entr{'y' if entries == 1 else 'ies'}"
            basis = "Johancsik equations integrated here at 0.05 m"
            why = "5 m integration segments vs the converged 0.05 m reference (discretisation)"
            out += [_case("M318", name, "pickup (klbf)", ref["pickup"], got["pickup"], 0.002, basis, why),
                    _case("M318", name, "slack-off (klbf)", ref["slackoff"], got["slackoff"], 0.002, basis, why),
                    _case("M318", name, "rotating torque (ft·lbf)", ref["torque"], got["torque"], 0.002, basis, why)]
    return out


def _d92_legacy() -> List[Dict[str, Any]]:
    """The pre-D92 whole-component method on the build-and-turn well (informational: why D92 was fixed)."""
    from core.engineering.engines.torque_drag import TorqueDragEngine

    rows = []
    ref = _reference_integration(BUILD, 0.3)
    for entries in (1, 10, 100):
        v = TorqueDragEngine.calculate(BUILD, _string(entries), MW_PPG, 0.3, max_segment_m=None).values
        got = {"pickup": v["hookload_pickup"], "slackoff": v["hookload_slackoff"],
               "torque": v["surface_torque_rotating_ft_lbf"]}
        rows.append({"pipe_entries": entries, **{f"{k}_error_pct": round((got[k] / ref[k] - 1) * 100, 2)
                                                 for k in ("pickup", "slackoff", "torque")}})
    return rows


def run() -> Dict[str, Any]:
    cases = _m314() + _m317() + _m318()
    return {"version": VERSION, "cases": cases, "total": len(cases), "failed": sum(not c["pass"] for c in cases),
            "d92_legacy_whole_component_ff_0_3": _d92_legacy(),
            "not_benchmarked": {"M311/M329 architecture comparison": "no numeric result; qualified by behaviour "
                                                                     "tests and M327 mutants"}}


def _text(report: Dict[str, Any]) -> str:
    lines = [f"{report['version']}: {report['total']} cases, {report['failed']} outside tolerance"]
    for c in report["cases"]:
        lines.append(f"{'PASS' if c['pass'] else 'FAIL'} {c['group']} | {c['case']} | {c['quantity']}: computed "
                     f"{c['computed']:g} vs reference {c['reference']:g} (rel {c['relative_error']:.2e}, "
                     f"tol {c['tolerance']:g})")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="store the results as evidence")
    parser.add_argument("--check", action="store_true", help="fail on a case outside tolerance or stale evidence")
    args = parser.parse_args(argv)
    report = run()
    print(_text(report))
    if args.write:
        EVIDENCE.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        EVIDENCE.with_suffix(".txt").write_text(_text(report) + "\n", encoding="utf-8")
    if report["failed"]:
        return 1
    if args.check:
        stored = json.loads(EVIDENCE.read_text(encoding="utf-8")) if EVIDENCE.exists() else None
        if stored != json.loads(json.dumps(report, ensure_ascii=False)):
            print("benchmark evidence is stale: run with --write and review the diff")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
