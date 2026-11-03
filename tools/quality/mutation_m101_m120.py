#!/usr/bin/env python3
"""Repeatable mutation run for the M101-M120 guards.

Each mutant removes ONE guard (or swaps one rule) in a scratch copy of the working tree and must be KILLED
by the listed phase tests. Engine: ``tools/quality/mutation_m46.py`` (green baseline first; an anchor that
does not match exactly once is reported INVALID, never killed). The repository is never modified.

Usage::

    python tools/quality/mutation_m101_m120.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

SR = "core/survey_revisions.py"
DP = "core/directional_plans.py"
TC = "core/trajectory_compare.py"
CP = "tabs/trajectory_compare_panel.py"
DB = "core/database.py"
T105 = ["tests/test_m105_survey_integrity.py", "tests/test_m105_survey_references.py"]
SM = "core/selection_manager.py"
SC = "core/selection_context.py"
BT = "core/base_tab.py"
MW = "main_window.py"
T102U = ["tests/test_m102_selection_context.py"]
T102 = ["tests/test_m102_selection_context.py", "tests/test_m102_context_probes.py"]

MUTANTS = [
    # ---- M102 selection context (D7) ---------------------------------------------------------------
    Mutant("SM-batch-not-suppressed", SM,
           "        if self._batch:\n            return\n        self.context_changed.emit",
           "        if False:\n            return\n        self.context_changed.emit",
           T102U, "a full-context selection emits one context per level (tabs see half-built contexts)"),
    Mutant("SM-batch-not-restored", SM,
           "        finally:\n            self._batch -= 1",
           "        finally:\n            pass",
           T102U, "after one full-context selection no context ever reaches the tabs again"),
    Mutant("SM-reversed-period-accepted", SM,
           "        if start and end and start > end:",
           "        if False:",
           T102U, "a period ending before it starts is stored"),
    Mutant("SM-datetime-not-normalised", SM,
           "        return value.date()",
           "        return value",
           T102U, "the same day given with a time is a new period (spurious refresh, unequal snapshots)"),
    Mutant("SM-clear-emits-no-context", SM,
           "        self.selection_cleared.emit()\n        self._emit_context()",
           "        self.selection_cleared.emit()",
           T102, "after a clear the tabs and status bar keep the previous well's context"),
    Mutant("SC-foreign-report-shown", SC,
           "            if report is None or well is None or report.well_id != well.id:",
           "            if report is None:",
           T102U, "a report of another well is shown in the selected well's context path"),
    Mutant("SC-foreign-wellbore-shown", SC,
           "            if bore is None or well is None or bore.well_id != well.id:",
           "            if bore is None:",
           T102U, "a wellbore of another well is labelled as the selected well's"),
    Mutant("BT-context-hook-not-connected", BT,
           "        self.sel_manager.context_changed.connect(self._on_context_changed_internal)",
           "        pass",
           T102, "tabs never receive the full context"),
    Mutant("BT-wellbore-kept-on-well-switch", BT,
           "        self.current_wellbore_id = self.sel_manager.current_wellbore_id   # a well switch clears it silently",
           "        pass",
           T102, "a tab keeps the previous well's wellbore after a well switch"),
    Mutant("W2-report-form-kept-on-well-switch", "tabs/w2_Daily_Report.py",
           "        if isinstance(self.current_report, dict) and self.current_report.get(\"well_id\") != well_id:",
           "        if False:",
           T102, "the daily report form shows (and could save) the previous well's report"),
    Mutant("W2-report-form-kept-on-clear", "tabs/w2_Daily_Report.py",
           "        self._empty_report_form()           # M102: no report values outlive their context",
           "        pass",
           T102, "after a clear the daily report form keeps the old report's date and summary"),
    Mutant("EX-report-list-kept-on-clear", "tabs/w11_Export.py",
           "        self._load_ddr_reports()                # M102: empties the report list and the preview",
           "        pass",
           T102, "after a clear the export centre keeps the old well's report list and preview"),
    Mutant("PL-tables-kept-on-clear", "tabs/w10_Planning_Widget.py",
           "        self.reset_context_view(pickers=(self.well_combo,), table_roots=(self,))",
           "        self.reset_context_view(pickers=(self.well_combo,))",
           T102, "after a clear the planning tables keep the old well's report dates"),
    Mutant("CM-clear-handler-empty", "tabs/w16_Cost_Management.py",
           "        self.current_well_id = None\n        self._show_empty_cost_state()",
           "        self.current_well_id = None",
           T102, "after a clear the cost cards keep the old well's cost"),
    Mutant("S3C-section-label-kept", "tabs/w3c_section_data.py",
           "        self.section_info.clear()              # M102: the previous well's section label never survives",
           "        pass",
           T102, "section data keeps the previous well's section label"),
    Mutant("MW-report-payload-not-enriched", MW,
           "                self.sel_manager.select_report(report_id, self._report_payload(report_id, data))",
           "                self.sel_manager.select_report(report_id, data)",
           T102 + ["tests/test_m44_ui.py"], "the context carries no report number/date after navigation"),
    Mutant("MW-status-path-not-connected", MW,
           "        self.sel_manager.context_changed.connect(self._show_context_path)",
           "        pass",
           T102, "the status bar never shows the context path"),
    Mutant("DOC-selected-well-filter-unfiltered", "tabs/documents_tab.py",
           "            documents = [d for d in documents if d[\"id\"] in linked]",
           "            pass",
           T102, "the 'selected well' library filter lists every document"),
    # ---- M105 survey derived-result integrity (D1) -------------------------------------------------
    Mutant("SR-field-set-unchecked", SR,
           "        if missing or extra:\n            issues.append(f\"station {index}: missing {missing} extra {extra}\")",
           "        if False:\n            issues.append(f\"station {index}: missing {missing} extra {extra}\")",
           T105, "a result station with a missing or extra field verifies as MATCH"),
    Mutant("SR-azimuth-not-wrapped", SR,
           "            if key == \"azi\":\n                delta = (delta + 180.0) % 360.0 - 180.0\n            worst[key]",
           "            if key == \"azi\":\n                delta = delta\n            worst[key]",
           T105, "an azimuth of 359.999999999 deg is reported as differing from 0 deg"),
    Mutant("SR-tolerance-loosened", SR,
           "            if abs(delta) > tol:",
           "            if abs(delta) > tol * 100:",
           T105, "a result field 10x outside its tolerance verifies as MATCH"),
    Mutant("SR-results-hash-not-checked", SR,
           "        return \"VERIFIED\" if results_sha256(json.loads(row.results_json)) == recorded else \"HASH MISMATCH\"",
           "        return \"VERIFIED\"",
           T105, "results edited after saving still read as hash VERIFIED"),
    Mutant("SR-save-hash-not-recorded", SR,
           "            results_sha256=results_sha256(results),\n            warnings_json=json.dumps(checked.warnings),",
           "            warnings_json=json.dumps(checked.warnings),",
           T105, "a new revision is saved without its results hash"),
    Mutant("SR-transform-hash-not-recorded", SR,
           "            results_sha256=results_sha256(results),\n            warnings_json=json.dumps([f\"Azimuths converted",
           "            warnings_json=json.dumps([f\"Azimuths converted",
           T105, "an azimuth-converted revision is saved without its results hash"),
    # ---- M105 fail-closed use (D2) ------------------------------------------------------------------
    Mutant("SR-missing-integrity-trusted", SR,
           "    if revision.get(\"integrity\") != \"VERIFIED\":",
           "    if revision.get(\"integrity\", \"VERIFIED\") != \"VERIFIED\":",
           T105, "a revision without an integrity state is used as VERIFIED"),
    Mutant("SR-use-without-recompute", SR,
           "    check = verify_results(revision)\n    if check[\"status\"] != \"MATCH\":",
           "    check = verify_results(revision)\n    if False:",
           T105, "forged results of a legacy (no results hash) revision feed a tie-in"),
    Mutant("SR-compare-unverified", SR,
           "            verify_for_use(revision, \"comparison\")",
           "            pass",
           T105, "a tampered revision is compared as if valid"),
    Mutant("DP-tie-in-results-unverified", DP,
           "        sr.verify_for_use(record, \"a plan tie-in\")",
           "        pass",
           T105, "a plan is saved against a survey revision whose results fail verification"),
    # ---- M105 datum shift --------------------------------------------------------------------------
    Mutant("SR-datum-offset-sign", SR,
           "    offset = round(source_elev - target_elev, 10)",
           "    offset = round(target_elev - source_elev, 10)",
           T105, "a datum shift moves depths the wrong way"),
    Mutant("SR-datum-missing-elevation-zero", SR,
           "    source_elev, target_elev = _finite(source_datum_elevation_m), _finite(target_datum_elevation_m)",
           "    source_elev, target_elev = _finite(source_datum_elevation_m) or 0.0, "
           "_finite(target_datum_elevation_m) or 0.0",
           T105, "a missing datum elevation is silently taken as zero"),
    Mutant("SR-datum-inclined-first-accepted", SR,
           "    if abs(float(stations_in[0][\"inc\"])) > 1e-9:",
           "    if False:",
           T105, "a datum shift is applied to a survey whose first station is inclined"),
    Mutant("SR-datum-stations-above-kept", SR,
           "    if above:\n        raise SurveyRevisionError(",
           "    if False:\n        raise SurveyRevisionError(",
           T105, "stations above the new datum are saved with negative MD"),
    # ---- M105 plan references ----------------------------------------------------------------------
    Mutant("DP-reference-contradiction-accepted", DP,
           "        if declared and str(declared).strip().lower() != str(getattr(row, key) or \"\").strip().lower():",
           "        if False:",
           T105, "a plan declaring GL is saved tied to an RKB survey"),
    Mutant("DP-references-dropped", DP,
           "    if references:                      # M105",
           "    if False:                           # M105",
           T105, "declared plan references are not stored"),
    Mutant("TC-reference-conflict-accepted", TC,
           "        if plan_value and actual_value and plan_value.lower() != actual_value.lower():",
           "        if False:",
           T105, "plan-vs-actual runs across different azimuth references or datums"),
    Mutant("TC-comment-rows-not-parsed", TC,
           "        while lines and lines[0].strip().lstrip('\"').startswith(\"#\"):",
           "        while False:",
           T105, "a plan file's declared reference is ignored (and the file is refused)"),
    Mutant("CP-reference-gate-removed", CP,
           "                if not check[\"ok\"]:\n                    self._clear_result(check[\"summary\"])",
           "                if False:\n                    self._clear_result(check[\"summary\"])",
           T105, "the desktop compares a plan in another reference"),
    # ---- M105 additive migration -------------------------------------------------------------------
    Mutant("DB-additive-column-skipped", DB,
           "                if column_name not in columns:\n                    raw.execute(f\"ALTER TABLE",
           "                if False:\n                    raw.execute(f\"ALTER TABLE",
           T105, "an existing database never gains the results-hash column"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
