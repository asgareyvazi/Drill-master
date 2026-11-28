#!/usr/bin/env python3
"""Repeatable mutation run for M521-M600 (exact HB annulus M538, Erge record M541 and the later missions).

Same engine and rules as ``tools/quality/mutation_m461_m520.py`` (``tools/quality/mutation_m46.py``): one realistic
defect per mutant in a scratch copy, the listed tests must KILL it, an anchor that does not match exactly once is
INVALID, ``--only`` never gives complete=True. Mutation results show which defects the tests detect; they are not a
proof of correctness.

Usage::

    python tools/quality/mutation_m521_m600.py [--json OUT] [--only ID[,ID...]]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

EX = "core/hydraulics_hb_annulus_exact.py"
HB = "core/hydraulics_hb_slot.py"
HR = "core/history_replay.py"
ESD = "dialogs/engineering_service_dialog.py"
W13 = "tabs/w13_Engineering_Calculator.py"

TX = ["tests/test_m538_hb_annulus_exact.py"]
TE = ["tests/test_m541_erge_record.py"]
TI = ["tests/test_m488_integration_consistency.py"]

MUTANTS = [
    # ------------------------------------------------------------------ M536-M540 exact HB concentric annulus
    Mutant("EX-plug-edges-swapped", EX, "    return root - b, root + b\n", "    return root - b, root - b\n", TX,
           "the plug has zero width (yield stress ignored in the plug edges)"),
    Mutant("EX-flow-weight", EX, "_integral(lambda x: x * x * outer(x), x_plus, 1.0)",
           "_integral(lambda x: x * outer(x), x_plus, 1.0)", TX, "the flow-rate integral loses one power of r"),
    Mutant("EX-inner-region-dropped", EX, "                               - _integral(lambda x: x * x * inner(x), kappa, x_minus))",
           "                               - 0.0)", TX, "the flow inside the zero-shear radius is ignored"),
    Mutant("EX-laminar-check-dropped", EX, "    if re >= re1:\n", "    if False:\n", TX,
           "turbulent flow is reported with the laminar solution"),
    Mutant("EX-kappa-range-widened", EX, "KAPPA_RANGE = (0.01, 0.99)\n", "KAPPA_RANGE = (0.001, 0.999)\n", TX,
           "diameter ratios outside the validated range are computed"),
    Mutant("EX-n-range-widened", EX, "N_RANGE = (0.1, 1.0)\n", "N_RANGE = (0.05, 1.5)\n", TX,
           "shear-thickening / extreme n is extrapolated"),
    Mutant("EX-wall-shear-factor", EX, "    tau_w = g * dh / 4.0\n", "    tau_w = g * dh / 2.0\n", TX,
           "the mean wall shear stress is doubled"),
    Mutant("EX-onset-as-loss", EX, "\"regime\": NO_FLOW, \"pressure_loss_psi\": 0.0,",
           "\"regime\": NO_FLOW, \"pressure_loss_psi\": onset_psi,", TX,
           "zero flow reports the yield onset as a friction loss"),
    Mutant("EX-onset-factor", EX, "    onset_psi = 4.0 * tau0 / dh * length / PA_PER_PSI\n",
           "    onset_psi = 2.0 * tau0 / dh * length / PA_PER_PSI\n", TX, "the yield onset is halved"),
    Mutant("EX-unknown-input-accepted", EX, "    if unknown:\n", "    if False:\n", TX,
           "an undeclared input (e.g. eccentricity) is silently ignored"),
    Mutant("EX-negative-flow-accepted", EX, "        if v[key] < 0:\n", "        if False:\n", TX,
           "negative flow rate or yield stress is accepted"),
    Mutant("EX-replay-sha-skipped", EX,
           "    if inputs_sha256(freeze(values)) != (inputs.get(\"inputs_sha256\") or {}).get(\"value\"):\n",
           "    if False:\n", TX, "tampered stored inputs replay without an integrity error"),
    Mutant("EX-not-assessed-saved", EX, "    if result.get(\"status\") != COMPUTED:\n        raise ValueError(",
           "    if False:\n        raise ValueError(", TX, "a NOT ASSESSED result is stored as a case"),
    Mutant("EX-unit-conversion", EX, "PA_PER_HB_UNIT = 4.4482216152605 / (100.0 * M_PER_FT ** 2)",
           "PA_PER_HB_UNIT = 4.4482216152605 / (100.0 * M_PER_FT)", TX, "lbf/100 ft2 converted with ft, not ft2"),
    Mutant("HR-m538-adapter-missing", HR,
           "    \"m538.hb_annulus_exact\": (\"core.hydraulics_hb_annulus_exact\", \"Herschel-Bulkley exact concentric annulus\"),\n",
           "", TX + TI, "the new case service has no replay adapter"),
    Mutant("HR-m538-tolerance-missing", HR, "    \"lbf/100ft²\": 1e-6,", "", TX,
           "a stored M538 unit has no replay tolerance"),
    Mutant("ESD-m538-prefix", ESD, "labels=EX_LABELS, page_values=page_values, object_prefix=\"m538\"",
           "labels=EX_LABELS, page_values=page_values, object_prefix=\"svc\"", TX,
           "the dialog widgets lose their M538 object names"),
    Mutant("W13-m538-well-dropped", W13,
           "        return hb_exact_annulus_dialog(db=getattr(self, \"db\", None), well_id=getattr(self, \"current_well_id\", None),\n",
           "        return hb_exact_annulus_dialog(db=getattr(self, \"db\", None), well_id=None,\n", TX,
           "the W13 entry point drops the selected well"),
    # ------------------------------------------------------------------ M541 Erge record
    Mutant("HB-erge-jpse-dropped", HB, "the transition paper J. Pet. Sci. Eng. 128:128-139 (DOI 10.1016/j.petrol.2015.02.\"",
           "the transition paper (DOI unknown.\"", TE, "the Erge record forgets the distinct JPSE paper"),
    Mutant("HB-erge-claimed-verified", HB, "    \"erge-2015\": (\"Erge et al. 2015 transition coefficients NOT VERIFIED",
           "    \"erge-2015\": (\"Erge et al. 2015 transition coefficients VERIFIED", TE + ["tests/test_m482_erge_secondary_consistency.py"],
           "Erge 2015 is claimed verified"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
