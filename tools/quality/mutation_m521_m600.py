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
CP = "core/citation_passage.py"
CR2 = "core/citation_record_v2.py"
DT = "tabs/documents_tab.py"
EC = "core/eowr_consistency.py"
RE = "core/report_engine.py"
RP = "core/report_provenance.py"
DD = "core/drilloff_diagnostics.py"
DRB = "core/drilloff_robust.py"

TX = ["tests/test_m538_hb_annulus_exact.py"]
TE = ["tests/test_m541_erge_record.py"]
TI = ["tests/test_m488_integration_consistency.py"]
TU = ["tests/test_m546_citation_record_v2.py"]
TC5 = ["tests/test_m551_eowr_consistency.py"]
TG = ["tests/test_m556_drilloff_diagnostics.py"]

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
    # ------------------------------------------------------------------ M546-M550 (U4) citation record v2
    Mutant("CP-symlink-followed", CP, "    if stat.S_ISLNK(info.st_mode):\n", "    if False:\n", TU,
           "a symbolic link is followed instead of refused"),
    Mutant("CP-v2-bare-name-skipped", CP, "    if name is not None and (\"/\" in name", "    if False and (\"/\" in name", TU,
           "a v2 file name with directory parts is accepted"),
    Mutant("CP-v2-integrity-skipped", CP, "    return cr2.integrity_problem(entry)\n", "    return \"\"\n", TU,
           "an edited v2 citation (passage id / hashes) is accepted"),
    Mutant("CP-v2-content-check-skipped", CP, "        v1_results = cr2.content_check(db, valid, v1_results)\n",
           "        pass\n", TU, "the library document content hash is never compared"),
    Mutant("CR2-hash-for-non-exact", CR2,
           "        doc_hash = hashes.get(int(entry[\"document_id\"])) if exact else None\n",
           "        doc_hash = _library_hashes(db, {int(entry[\"document_id\"])}).get(int(entry[\"document_id\"]))\n",
           TU, "a citation that did not verify EXACT receives a document content hash"),
    Mutant("CR2-passage-id-check-dropped", CR2, "    if entry.get(\"passage_id\") != expected:\n", "    if False:\n", TU,
           "a passage id that does not match its fields is accepted"),
    Mutant("CR2-quote-hash-check-dropped", CR2,
           "    if entry.get(\"quote_sha256\") != sha256_text(entry.get(\"quote\") or \"\"):\n", "    if False:\n", TU,
           "a quote that does not match its hash is accepted"),
    Mutant("CR2-content-compare-dropped", CR2, "        elif hashes.get(int(entry[\"document_id\"])) != recorded:\n",
           "        elif False:\n", TU, "a changed library file is still reported EXACT"),
    Mutant("CR2-verified-without-hash", CR2,
           "    if state == VERIFIED_EXACT and not entry.get(\"document_sha256\"):\n", "    if False:\n", TU,
           "VERIFIED_EXACT is accepted without a content hash"),
    Mutant("CR2-unreadable-carried", CR2,
           "        if not isinstance(entry, dict) or result.get(\"status\") == cr.UNREADABLE:\n",
           "        if not isinstance(entry, dict):\n", TU, "an unreadable v1 citation is carried into v2"),
    Mutant("DT-v2-save-always-enabled", DT, "        self.save_citation_v2_button.setEnabled(is_v1)\n",
           "        self.save_citation_v2_button.setEnabled(True)\n", TU, "a v2 record is offered for re-upgrade"),
    # ------------------------------------------------------------------ M551-M555 (U5) EOWR consistency analyzer
    Mutant("EC-continuity-ignored", EC, "            if abs(end - start) > DEPTH_TOL_M:\n", "            if False:\n", TC5,
           "a depth gap between consecutive reports is not reported"),
    Mutant("EC-decrease-ignored", EC, "        if end < start - DEPTH_TOL_M:\n", "        if False:\n", TC5,
           "a depth decrease within a day is not reported"),
    Mutant("EC-24h-limit", EC, "        if total > 24.0 + HOURS_TOL:\n", "        if total > 48.0:\n", TC5,
           "more than 24 h of time logs in one day is accepted"),
    Mutant("EC-midnight-wrap", EC, "        b += timedelta(days=1)                       # 24:00 wrap",
           "        pass                       # 24:00 wrap", TC5, "an interval ending at 24:00 is misread"),
    Mutant("EC-failed-query-assessed", EC,
           "    return (data.get(\"source_query_status\") or {}).get(source) == QUERY_FAILED or data.get(source, []) is None\n",
           "    return False\n", TC5, "a failed query is assessed as if it were empty"),
    Mutant("EC-unclassified-npt-counted", EC,
           "            complete = False                          # an unclassified row cannot be counted either way\n",
           "            pass\n", TC5, "an unclassified time log is counted as productive"),
    Mutant("EC-duplicate-report-missed", EC, "            if key in seen:\n", "            if False:\n", TC5,
           "two reports with the same date and number are not reported"),
    Mutant("EC-drilled-check-dropped", EC,
           "            elif drilled is not None and abs((d_out - d_in) - drilled) > DEPTH_TOL_M:\n",
           "            elif False:\n", TC5, "metres drilled that contradict depth in/out are accepted"),
    Mutant("EC-survey-period-compared", EC, "    if data.get(\"period\") is not None:\n        return _result(\"survey_within_depth\"",
           "    if False:\n        return _result(\"survey_within_depth\"", TC5,
           "unfiltered surveys are compared with a period's depths"),
    Mutant("EC-empty-is-consistent", EC, "    if checked:\n        return _result(key, CONSISTENT",
           "    if True:\n        return _result(key, CONSISTENT", TC5, "nothing checked is reported CONSISTENT"),
    Mutant("RE-review-not-rendered", RE, "        html += eowr_consistency.html_section(eowr_consistency.analyze(data))\n",
           "", TC5 + ["tests/test_m555_eowr_consistency_mainwindow_journey.py"],
           "the EOWR body omits the consistency review"),
    Mutant("RP-review-not-in-manifest", RP, "        prov[\"consistency\"] = eowr_consistency.analyze(data)\n",
           "        pass\n", TC5, "the provenance manifest omits the consistency statuses"),
    # ------------------------------------------------------------------ M556-M560 drill-off diagnostics
    Mutant("DD-tie-hidden", DD, "    if len(optima) > 1:\n", "    if False:\n", TG,
           "a non-unique L1 optimum is not warned"),
    Mutant("DD-tie-collapsed", DD, "            if not any(np.allclose(", "            if not out and not any(np.allclose(",
           TG, "tied fits are collapsed to one, so a non-unique optimum reads UNIQUE"),
    Mutant("DD-loo-shift-silent", DD, "    if shifts and max(shifts) > spacing + 1e-9:\n", "    if False:\n", TG,
           "a breakpoint that moves on removing one step is not warned"),
    Mutant("DD-leverage-threshold", DD, "LEVERAGE_FACTOR = 2.0\n", "LEVERAGE_FACTOR = 20.0\n", TG,
           "an isolated WOB step is not flagged as high leverage"),
    Mutant("DD-surface-silent", DD, "    if result.get(\"wob_basis\") != \"downhole\":\n", "    if False:\n", TG,
           "a surface WOB founder is not warned as surface WOB"),
    Mutant("DD-edge-silent", DD, "    if n >= 4 and (bp - xs[1]", "    if False and (bp - xs[1]", TG,
           "a breakpoint at the search edge is not warned"),
    Mutant("DD-flat-narrowed", DD, "FLAT_REL = 0.01\n", "FLAT_REL = -1.0\n", TG,
           "the weakly identified breakpoint interval is not reported"),
    Mutant("DD-not-shown", DRB, "    lines.extend(drilloff_diagnostics.summary_lines(result))\n", "", TG,
           "the W13 summary omits the diagnostics"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
