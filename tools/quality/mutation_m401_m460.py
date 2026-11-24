#!/usr/bin/env python3
"""Repeatable mutation run for M401-M460: R-HYD-2 HB slot annulus (M416), quasi-steady surge/swab (M420), fitted
drill-off (M423), IADC dull grade (M427), CCI as a stored case field (M422), the generic replay adapter and the W13
service dialog (M418 / M421).

Same engine and rules as ``tools/quality/mutation_m361_m400.py`` (``tools/quality/mutation_m46.py``): one realistic
defect per mutant in a scratch copy, the listed tests must KILL it, an anchor that does not match exactly once is
INVALID, ``--only`` never gives complete=True. Mutation results show which defects the tests detect; they are not a
proof of correctness.

Usage::

    python tools/quality/mutation_m401_m460.py [--json OUT] [--only ID[,ID...]]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

HB = "core/hydraulics_hb_slot.py"
SS = "core/surge_swab.py"
DF = "core/drilloff_fitted.py"
DG = "core/bit_dull_grade.py"
HW = "core/hydraulics_workflow.py"
HR = "core/history_replay.py"
DLG = "dialogs/engineering_service_dialog.py"

T = ["tests/test_m415_m427_engineering_services.py"]
TU = T + ["tests/test_m388_units_contract.py"]

MUTANTS = [
    # ------------------------------------------------------------------ M416 R-HYD-2
    Mutant("HB-gap-is-full-clearance", HB, "    delta = dh / 2.0\n", "    delta = dh\n", T,
           "the slot gap is taken as Do - Di instead of (Do - Di) / 2"),
    Mutant("HB-yield-ignored-laminar", HB, "    tau_lam = laminar_wall_stress(vel, tau0, k, n, delta)\n",
           "    tau_lam = laminar_wall_stress(vel, 0.0, k, n, delta)\n", T, "the yield stress is dropped in laminar flow"),
    Mutant("HB-darcy-used-as-fanning", HB, "            regime, fanning = TURBULENT, darcy / 4.0\n",
           "            regime, fanning = TURBULENT, darcy\n", T, "the Darcy factor is used as the Fanning factor"),
    Mutant("HB-band-swapped", HB, "        return 3250.0 - 1150.0 * n_prime, 4150.0 - 1150.0 * n_prime\n",
           "        return 4150.0 - 1150.0 * n_prime, 3250.0 - 1150.0 * n_prime\n", T, "Re1 and Re2 swapped"),
    Mutant("HB-erge-kappa-sign", HB, "(1.0 + 1.402 * kappa - 0.977 * kappa ** 2)",
           "(1.0 + 1.402 * kappa + 0.977 * kappa ** 2)", T, "Erge Re1 quadratic term sign"),
    Mutant("HB-blend-uses-turbulent-at-re", HB, "        re_turb = re if re > re2 else re2\n",
           "        re_turb = re\n", T, "the transitional blend evaluates Colebrook at Re instead of Re2"),
    Mutant("HB-wide-annulus-accepted", HB, "    if kappa < KAPPA_MIN:\n", "    if False:\n", T,
           "the slot idealisation is used for a wide annulus"),
    Mutant("HB-zero-flow-missing", HB, "    if q == 0.0:\n", "    if q == -1.0:\n", T,
           "zero flow is not handled as a value"),
    Mutant("HB-erge-re2-extrapolated", HB,
           "        if re >= re1 and not ERGE_RE2_N_RANGE[0] < n_prime < ERGE_RE2_N_RANGE[1]:\n",
           "        if False:\n", T, "the Erge Re2 fit is extrapolated outside its n' range"),
    Mutant("HB-psi-constant", HB, "PA_PER_PSI = 4.4482216152605 / M_PER_IN ** 2\n",
           "PA_PER_PSI = 6895.0\n", TU, "a rounded psi constant"),
    Mutant("HB-replay-sha-skipped", HB,
           "    if inputs_sha256(freeze(values)) != (inputs.get(\"inputs_sha256\") or {}).get(\"value\"):\n",
           "    if False:\n", T, "tampered HB inputs are replayed"),
    # ------------------------------------------------------------------ M420 surge / swab
    Mutant("SS-clinging-dropped", SS, "        v_eff = v_fluid + v[\"clinging_constant\"] * vp\n",
           "        v_eff = v_fluid\n", T, "the clinging (drag) term is dropped"),
    Mutant("SS-open-end-evaluated", SS, "    if v[\"pipe_end\"] == \"open\":\n", "    if False:\n", T,
           "an open-ended string is evaluated as closed"),
    Mutant("SS-displacement-uses-hole", SS,
           "        displaced = vp * math.pi / 4.0 * (di * hb.M_PER_IN) ** 2            # m3/s up the annulus\n",
           "        displaced = vp * math.pi / 4.0 * (do * hb.M_PER_IN) ** 2            # m3/s up the annulus\n", T,
           "the displaced volume uses the hole ID"),
    Mutant("SS-partial-sum-total", SS,
           "        if section_result[\"status\"] != hb.COMPUTED:\n            return {",
           "        if False:\n            return {", T, "a NOT ASSESSED section is skipped and the rest summed"),
    Mutant("SS-emw-sign", SS, "swab_emw_ppg=v[\"density_ppg\"] - delta", "swab_emw_ppg=v[\"density_ppg\"] + delta", T,
           "swab EMW above the mud weight"),
    # ------------------------------------------------------------------ M423 fitted drill-off
    Mutant("DF-upper-slope-is-c", DF, "    upper = b + c\n", "    upper = c\n", T,
           "the upper slope is reported as the change c"),
    Mutant("DF-min-steps-4", DF, "MIN_STEPS = 5\n", "MIN_STEPS = 4\n", T, "4 steps are fitted"),
    Mutant("DF-rpm-tolerance-ignored", DF, "    if max(rpms) - min(rpms) > v[\"rpm_tolerance_rpm\"]:\n",
           "    if False:\n", T, "a varying-RPM test is fitted"),
    Mutant("DF-pooled-outlier-scale", DF, "        scale = math.sqrt(rest / (n - 4)) if rest > 0 else 0.0\n",
           "        scale = sigma\n", T, "the pooled s masks the outlier"),
    Mutant("DF-founder-ratio-inverted", DF, "    if b > 0 and upper < v[\"slope_ratio\"] * b:\n",
           "    if b > 0 and upper > v[\"slope_ratio\"] * b:\n", T, "founder rule inverted"),
    # ------------------------------------------------------------------ M427 dull grade
    Mutant("DG-cone-code-on-pdc", DG, "        elif bit_type == \"fixed-cutter\" and code in CONE_ONLY:\n",
           "        elif False:\n", T, "a roller-cone code accepted on a fixed-cutter bit"),
    Mutant("DG-scale-9-accepted", DG, "    if not value.isdigit() or not 0 <= int(value) <= 8:\n",
           "    if not value.isdigit() or not 0 <= int(value) <= 9:\n", T, "row wear 9 accepted"),
    Mutant("DG-no-well-saved", DG, "    if well_id is None:\n        raise ValueError(", "    if False:\n        raise ValueError(",
           T, "a grade saved without a well"),
    Mutant("DG-trend-unordered", DG, "    return sorted(rows, key=lambda r: (r[\"depth_out_m\"] is None, r[\"depth_out_m\"] or 0.0, r[\"date_out\"] or \"\",\n                                       r[\"case_id\"]))\n",
           "    return rows\n", T, "the trend is newest-first instead of by depth"),
    # ------------------------------------------------------------------ M422 CCI field / replay / dialog
    Mutant("HW-cci-v2-fields-not-stored", HW, "        if version != METHOD_VERSION_V1:\n", "        if False:\n", T,
           "the CCI provenance fields are not stored"),
    Mutant("HW-v1-replays-with-v2-layout", HW, "    return case_payload(result, version)[1]\n",
           "    return case_payload(result)[1]\n", T, "a v1 case replays with the v2 layout (DIFFERENT)"),
    Mutant("HR-service-version-unchecked", HR, "        if version != module().METHOD_VERSION:\n", "        if False:\n", T,
           "an unknown method version is replayed"),
    Mutant("DLG-empty-is-zero", DLG, "        out: Dict[str, Any] = {key: edit.text().strip() or None for key, edit in self.edits.items()}\n",
           "        out: Dict[str, Any] = {key: edit.text().strip() or \"0\" for key, edit in self.edits.items()}\n", T,
           "an empty dialog field is sent as 0"),
    Mutant("DLG-save-without-run-status", DLG,
           "        self.save_btn.setEnabled(result.get(\"status\") in SAVABLE and self.db is not None)\n",
           "        self.save_btn.setEnabled(self.db is not None)\n", T, "Save is enabled for a NOT ASSESSED result"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
