#!/usr/bin/env python3
"""Repeatable mutation run for the M53 dashboard, M54 DDR, M55 directional and M56 finder contracts.

Each mutant removes ONE guard (or restores one old behaviour) in a scratch copy
of the working tree and must be KILLED by the listed tests. The engine (copy,
exact-once snippet check, baseline run, JSON report, exit status) is the M46
one: ``tools/quality/mutation_m46.py``. The repository is never modified.

Deliberately not included (equivalent, evidence in the M53-M60 report): removing
the dashboard's own ``single-currency`` guard on the portfolio cost KPI — the
canonical ``cost_semantics.summarize_costs`` already returns
``total_actual=None`` for mixed currencies, so no observable change exists.

Usage::

    python tools/quality/mutation_m53_m56.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

OD = "core/operations_dashboard.py"
HT = "tabs/home_tab.py"
W2 = "tabs/w2_Daily_Report.py"
PG = "core/import_adapters/pdf_generic_tables.py"
PR = "core/ddr_report_profiles.py"
ME = "core/mineru_engine.py"
T53 = ["tests/test_m53_dashboard.py", "tests/test_operations_dashboard.py"]
T54W = ["tests/test_m54_ddr_workflow.py"]
T54P = ["tests/test_m54_pdf_generic_tables.py"]
T54R = ["tests/test_m54_report_profiles.py"]
SI = "core/survey_file_import.py"
WP = "core/well_plan_designer.py"
CP = "tabs/trajectory_compare_panel.py"
TV = "tabs/trajectory_viewer.py"
W6 = "tabs/w6_Trajectory_Widget.py"
EB = "core/editor_bindings.py"
CF = "tabs/calculator_finder.py"
T55 = ["tests/test_m55_directional.py"]
T56 = ["tests/test_m56_calculator_finder.py"]

MUTANTS = [
    # ------------------------------------------------------------------ M53 dashboard
    Mutant("OD-negative-footage-counted", OD,
           "        if end_v is not None and start_v is not None and end_v - start_v >= 0:",
           "        if end_v is not None and start_v is not None:",
           T53, "a plug-back / typo (24:00 below 00:00 depth) is summed as negative footage"),
    Mutant("OD-npt-alert-dropped", OD,
           "        if logged and 100.0 * npt / logged > NPT_SHARE_ALERT:",
           "        if False:",
           T53, "a well above 20 % NPT raises no NPT_HIGH alert"),
    Mutant("OD-afe-alert-dropped", OD,
           "            if used is not None and used > 100.0:",
           "            if False:",
           T53, "a well over its AFE raises no COST_OVER_AFE alert"),
    Mutant("OD-portfolio-cost-per-metre", OD,
           "    single = well_list[0] if len(well_list) == 1 else None",
           "    single = well_list[0] if well_list else None",
           T53, "cost per metre / NPT cost are shown for a multi-well portfolio (first well's figure)"),
    Mutant("OD-company-filter-ignored", OD,
           "        if filters.company and company != filters.company:\n            continue",
           "        if False:\n            continue",
           T53, "the company filter does not scope the KPIs and lists"),
    Mutant("OD-options-from-filtered-wells", OD,
           "               \"rigs\": sorted({w[6] for w in all_wells if w[6]}),",
           "               \"rigs\": sorted({w[6] for w in all_wells if w[6] and (not filters.rig or w[6] == filters.rig)}),",
           T53, "filter choices shrink to the current filter, so the user cannot switch rig"),
    Mutant("HT-stale-result-accepted", HT,
           "        if filters != self.filters:\n            # The filter changed",
           "        if False:\n            # The filter changed",
           T53, "a load for an old filter overwrites the dashboard of the new filter"),
    Mutant("HT-rtl-inherited", HT,
           "        self.setLayoutDirection(Qt.LeftToRight)       # English-only dashboard, never RTL",
           "        pass",
           T53, "the dashboard inherits the application's RTL direction"),
    # ------------------------------------------------------------------ M54 W2 workflow
    Mutant("W2-overlap-saves", W2,
           "            if blocking:\n                more =",
           "            if False:\n                more =",
           T54W, "an overlapping time log is saved (pre-M54)"),
    Mutant("W2-midnight-start-as-2400", W2,
           "                \"time_from\": \"00:00\" if f24 else f\"{fh:02d}:{fm:02d}\",",
           "                \"time_from\": \"24:00\" if f24 else f\"{fh:02d}:{fm:02d}\",",
           T54W, "a stored 00:00 start (loaded with the 24:00 flag) is validated as end-of-day"),
    Mutant("W2-gap-blocks", W2,
           "                elif issue.field == \"time_range\" and check_gaps and \"Gap\" in issue.message:\n                    notes.append",
           "                elif issue.field == \"time_range\" and check_gaps and \"Gap\" in issue.message:\n                    blocking.append",
           T54W, "an incomplete day cannot be saved"),
    Mutant("W2-duplicate-keeps-source-id", W2,
           "        self.current_report = None\n        self.current_report_id = None\n        self.current_daily_report_id = None\n        self.related_documents.set_report(None)\n        if options.get(\"target_date\")",
           "        self.current_report = None\n        self.current_daily_report_id = None\n        self.related_documents.set_report(None)\n        if options.get(\"target_date\")",
           T54W, "saving a duplicate overwrites the source report"),
    Mutant("W2-timeline-ignores-guard", W2,
           "        if self._has_unsaved_edits() and not self.confirm_discard_edits():\n            self._highlight_timeline()",
           "        if False:\n            self._highlight_timeline()",
           T54W, "double-clicking the timeline discards unsaved edits without asking"),
    Mutant("W2-new-report-ignores-guard", W2,
           "        if self._has_unsaved_edits() and not self.confirm_discard_edits():\n            return False\n        self.current_report = None\n        self.current_report_id = None\n        self.related_documents",
           "        self.current_report = None\n        self.current_report_id = None\n        self.related_documents",
           T54W, "New Report discards unsaved edits without asking (pre-M54)"),
    # ------------------------------------------------------------------ M54 generic PDF tables
    Mutant("PG-header-row-as-data", PG,
           "        body = rows[header_index + 1:]",
           "        body = rows[header_index:]",
           T54P, "a ruled table's header row is emitted as a data row (M52 limit)"),
    Mutant("PG-margins-kept", PG,
           "        if in_band and _margin_key(\" \".join(w[4] for w in words)) in repeated:",
           "        if False:",
           T54P, "repeated page headers/footers leak into tables and text"),
    Mutant("PG-no-repeated-header-join", PG,
           "                and last[\"headers\"] == table[\"headers\"]\n            ):",
           "                and False\n            ):",
           T54P, "a table continued on the next page is split into fragments"),
    Mutant("PG-wrapped-cell-new-row", PG,
           "            if col > 0:\n                rows[-1][col]",
           "            if False:\n                rows[-1][col]",
           T54P, "a wrapped description line ends the table instead of joining its row"),
    Mutant("PG-scanned-not-reported", PG,
           "            if has_images or not words:\n                scanned.append(page_no)",
           "            if False:\n                scanned.append(page_no)",
           T54P, "a scanned page is not reported, so OCR-unavailable is never stated"),
    Mutant("PG-ruled-headerless-not-joined", PG,
           "            headerless = (not report.get(\"header_detected\")) and len(headers) == len(prev_headers) and prev_headers",
           "            headerless = False",
           T54P, "a header-less ruled continuation keeps Column N keys instead of the table's headers"),
    # ------------------------------------------------------------------ M54 report profiles
    Mutant("PR-unknown-field-accepted", PR,
           "        if target not in FIELD_SPECS:\n            errors.append(f\"Alias",
           "        if False:\n            errors.append(f\"Alias",
           T54R, "an alias to a non-existent canonical field is saved"),
    Mutant("PR-version-not-incremented", PR,
           "        version = (latest[0] if latest else 0) + 1",
           "        version = 1",
           T54R, "a second save cannot create a new immutable version"),
    Mutant("ME-profile-ignored", ME,
           "        if profile is not None:\n            hit = profile.resolve(label)",
           "        if False:\n            hit = profile.resolve(label)",
           T54R, "the selected report profile has no effect on mapping"),
    Mutant("ME-profile-unit-overrides-header", ME,
           "        if unit and not re.search(r\"[\\[(].*[\\])]\\s*$\", str(header)):",
           "        if unit:",
           T54R, "a profile unit overrides an explicit unit in the header"),
    # ------------------------------------------------------------------ M54 regression fix
    Mutant("EB-display-panel-counted-as-edit", EB,
           "        if widget.property(EDITOR_SNAPSHOT_EXCLUDE):\n            return None",
           "        if False:\n            return None",
           T54W, "a document link made elsewhere makes New report open a modal discard prompt"),
    # ------------------------------------------------------------------ M55 survey import
    Mutant("SI-unit-conflict-ignored", SI,
           "    if header_unit and unit and header_unit != unit:",
           "    if False:",
           T55, "an MD header in feet is silently overridden by a metres choice"),
    Mutant("SI-missing-unit-assumed", SI,
           "    if result.unit not in (\"m\", \"ft\"):",
           "    if False:",
           T55, "a file without a depth unit is imported as if in metres"),
    Mutant("SI-feet-not-converted", SI,
           "    factor = FT_TO_M if result.unit == \"ft\" else 1.0",
           "    factor = 1.0",
           T55, "feet are stored as metres"),
    Mutant("SI-azimuth-range-unchecked", SI,
           "        if azi is not None and not 0.0 <= float(azi) < 360.0:",
           "        if False:",
           T55, "an azimuth of 400 degrees is accepted"),
    Mutant("W6-refused-import-applied", W6,
           "        if result is None or not result.ok or not result.stations:",
           "        if result is None:",
           T55, "a refused import clears the editable survey table"),
    # ------------------------------------------------------------------ M55 plan designer and handover
    Mutant("WP-dls-limit-not-warned", WP,
           "            if dls_limit is not None and dls > dls_limit + 1e-9:",
           "            if False:",
           T55, "a curve above the DLS limit raises no warning"),
    Mutant("WP-dls-per-100ft-arc", WP,
           "            length = dogleg / dls * 30.0",
           "            length = dogleg / dls * 30.48",
           T55, "the DLS course length is taken as 100 ft instead of 30 m"),
    Mutant("WP-target-radius-ignored", WP,
           "\"hit\": radius > 0 and distance <= radius",
           "\"hit\": True",
           T55, "every target is reported as hit"),
    Mutant("CP-single-station-plan-accepted", CP,
           "        if len(stations) < 2:",
           "        if not stations:",
           T55, "a one-station plan is accepted for comparison"),
    Mutant("TV-callback-reference-cycle", TV,
           "        self.plan_designer = WellPlanDesignerPanel(handover=True)",
           "        self.plan_designer = WellPlanDesignerPanel(use_plan=self.use_designed_plan)",
           T55 + ["tests/test_m50_trajectory_3d_disposal.py"],
           "the designer holds the viewer in a Python cycle (Qt wrappers left to an arbitrary GC)"),
    # ------------------------------------------------------------------ M56 calculator finder
    Mutant("CF-any-term-matches", CF,
           "        return all(term in haystack for term in terms)",
           "        return any(term in haystack for term in terms)",
           T56, "a multi-word search matches calculators containing only one word"),
    Mutant("CF-recents-unbounded", CF,
           "if p != entry.path]][:MAX_RECENTS]",
           "if p != entry.path]]",
           T56, "the recent list grows without bound"),
    Mutant("CF-stale-favourites-kept", CF,
           "        return [p for p in _as_list(self.store.value(\"favorites\")) if p in self.by_path]",
           "        return list(_as_list(self.store.value(\"favorites\")))",
           T56, "a favourite pointing at a removed calculator is still listed"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
