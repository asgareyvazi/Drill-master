#!/usr/bin/env python3
"""Repeatable mutation run for the M70-M76 guards and the M75 engine formulas.

Each mutant changes ONE formula constant or removes ONE guard in a scratch copy
of the working tree and must be KILLED by the listed tests (independent
references, not the code under test). Engine: ``tools/quality/mutation_m46.py``.
The repository is never modified.

Usage::

    python tools/quality/mutation_m70_m76.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

HY = "core/hydraulics_engine.py"
MSE = "core/engineering/engines/mse.py"
SG = "core/storage_guards.py"
WP = "core/well_plan_designer.py"
DP = "core/directional_plans.py"
CON = "core/calculator_contracts.py"
CH = "core/calculation_history.py"
WA = "core/well_architecture.py"
GOLD = ["tests/test_engineering_independent_golden.py", "tests/test_engineering_ground_truth.py"]
T40 = ["tests/test_hydraulics_m40_regressions.py"]  # asserts PV/YP from Fann readings
T72 = ["tests/test_m72_surveys_solver.py"]
T73 = ["tests/test_m73_contracts_history.py"]
T74 = ["tests/test_m74_well_architecture.py"]

MUTANTS = [
    # ---- M75 formulas (independent hand references) --------------------------------------------
    Mutant("HY-bit-dp-constant", HY,
           "        return gpm**2 * mw_ppg / (10858.0 * tfa_in2**2)",
           "        return gpm**2 * mw_ppg / (10000.0 * tfa_in2**2)",
           GOLD, "bit pressure drop uses a wrong constant"),
    Mutant("HY-hhp-constant", HY,
           "        return gpm * pressure_drop_psi / 1714.0",
           "        return gpm * pressure_drop_psi / 1700.0",
           GOLD, "bit hydraulic horsepower uses a wrong constant"),
    Mutant("HY-jet-velocity-constant", HY,
           "        return gpm / (3.117 * tfa_in2)",
           "        return gpm / (3.0 * tfa_in2)",
           GOLD, "nozzle jet velocity uses a wrong constant"),
    Mutant("HY-annular-capacity-constant", HY,
           "        return AdvancedHydraulicsEngine._annular_area_factor_in2(hole_id, pipe_od) / 1029.4\n",
           "        return AdvancedHydraulicsEngine._annular_area_factor_in2(hole_id, pipe_od) / 1000.0\n",
           GOLD + T74, "annular capacity uses a wrong constant"),
    Mutant("HY-pipe-capacity-constant", HY,
           "        return pipe_id**2 / 1029.4\n",
           "        return pipe_id**2 / 1000.0\n",
           GOLD + T73, "pipe capacity uses a wrong constant"),
    Mutant("HY-fann-pv", HY,
           "        pv = theta600 - theta300\n        yp = theta300 - pv",
           "        pv = theta600 - 0.9 * theta300\n        yp = theta300 - pv",
           GOLD + T40, "plastic viscosity from Fann readings is wrong"),
    Mutant("MSE-rotary-term", MSE,
           "            rotary = (TEALE_120_PI * n * tq) / denominator",
           "            rotary = (480.0 * n * tq) / denominator",
           GOLD, "MSE uses the 480 spreadsheet constant instead of 120*pi"),
    # ---- M70/M74 storage immutability --------------------------------------------------------
    Mutant("SG-architecture-frozen-columns", SG,
           "        _frozen(_ARCH_FROZEN),\n",
           "",
           T74, "a saved architecture revision's components can be rewritten"),
    # ---- M72 solver and survey pin ----------------------------------------------------------
    Mutant("WP-inside-build-circle-accepted", WP,
           "        if rho < radius:\n            return _fail(out, \"INSIDE_TURN_RADIUS\",",
           "        if False:\n            return _fail(out, \"INSIDE_TURN_RADIUS\",",
           T72, "a target inside the build circle is not reported infeasible"),
    Mutant("WP-tie-in-shift-dropped", WP,
           "    d_tvd = float(tie_in[\"tvd\"]) - stations[0][\"tvd\"]",
           "    d_tvd = 0.0",
           T72, "a plan tied to a survey station is not shifted to the tie-in TVD"),
    Mutant("DP-survey-sha-unchecked", DP,
           "    if tie_in.get(\"survey_sha256\") != row.stations_sha256:",
           "    if False:",
           T72, "a plan pinned to a survey revision with a different SHA-256 is accepted"),
    # ---- M73 contracts and comparison --------------------------------------------------------
    Mutant("CON-unversioned-reproducible", CON,
           "    if not method_version or method_version == W13_UNVERSIONED:",
           "    if not method_version:",
           T73, "a case without a method version is treated as reproducible"),
    Mutant("CON-tolerance-widened", CON,
           "        tolerance = 0.5 * 10 ** -(spec.decimals if spec.decimals is not None else 9)",
           "        tolerance = 5e3 * 10 ** -(spec.decimals if spec.decimals is not None else 9)",
           T73, "a stored result outside display rounding still verifies as MATCH"),
    Mutant("CH-unit-mismatch-compared", CH,
           "            if ua != ub:",
           "            if False:",
           T73, "values in different units are compared numerically"),
    # ---- M74 architecture rules and cement geometry ----------------------------------------------
    Mutant("WA-liner-fit-unchecked", WA,
           "            elif all(item[\"od_in\"] >= h[\"id_in\"] for h in hosts):",
           "            elif False:",
           T74, "a liner larger than its host string is accepted"),
    Mutant("WA-shoe-depth-unchecked", WA,
           "                    abs(item[\"top_md\"] - host[\"bottom_md\"]) > DEPTH_TOLERANCE:",
           "                    False:",
           T74, "a shoe away from its string bottom is accepted"),
    Mutant("WA-open-hole-assumed", WA,
           "        outer = host[\"id_in\"] if host else hole",
           "        outer = host[\"id_in\"] if host else (hole or 8.5)",
           T74, "an unknown open-hole size is replaced by an assumed one"),
    Mutant("WA-cased-interval-as-open-hole", WA,
           "        outer = host[\"id_in\"] if host else hole",
           "        outer = hole",
           T74, "a cased interval uses the open-hole size"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
