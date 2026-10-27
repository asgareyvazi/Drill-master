#!/usr/bin/env python3
"""Repeatable mutation run for the M48 Operations Analysis contracts.

Each mutant puts ONE old behaviour (or removes one guard) in a scratch copy of
the working tree and must be KILLED by the listed tests. The engine (copy,
exact-once snippet check, baseline run, JSON report, exit status) is the M46
one: ``tools/quality/mutation_m46.py``. The repository is never modified.

Usage::

    python tools/quality/mutation_m48.py [--json OUT] [--only ID[,ID...]]

The environment must be able to run the tests (Qt offscreen etc., see
tools/qt_headless_env.sh). SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

EV = "core/analysis_evidence.py"
W12 = "tabs/w12_Analysis.py"
CORE = ["tests/test_m48_analysis_evidence.py"]
UI = ["tests/test_m48_analysis_ui.py"]
BOTH = CORE + UI
M29 = ["tests/test_m29_release_closure.py"]

MUTANTS = [
    # ------------------------------------------------------------ None -> 0 / real zero
    Mutant("N-none-is-zero", EV,
           '        return STATE_MISSING, None, "not recorded"',
           '        return STATE_VALUE, 0.0, ""',
           BOTH, "a missing (None) observation becomes a valid 0"),
    Mutant("N-state-text-zero", EV,
           '            return STATE_TEXT.get(self.state, "—")',
           '            return "0.0"',
           BOTH, "a metric without a value is displayed as 0.0"),
    Mutant("N-real-zero-dropped", EV,
           "            valid.append(number)",
           "            if number:\n                valid.append(number)",
           CORE, "a recorded 0.0 ROP is dropped from average/best"),
    # ------------------------------------------------------------ invalid values
    Mutant("V-nan-accepted", EV,
           "    if not math.isfinite(number):",
           "    if False:",
           CORE, "NaN / inf accepted as measurements"),
    # ------------------------------------------------------------ stale KPI / generation
    Mutant("S-deselect-keeps-kpis", W12,
           '            self._set_kpi_card(card, none, "No well selected")',
           "            pass",
           UI, "deselecting the well keeps the previous well's KPI cards"),
    Mutant("S-no-generation-guard", W12,
           "        if generation != self._generation:\n            return _STALE",
           "        if False:\n            return _STALE",
           UI, "a read that finished after a selection change paints over the new well"),
    Mutant("S-section-leak", "core/base_tab.py",
           "        self.current_section_id = self.current_report_id = None\n        self.current_section_data = {}",
           "        self.current_report_id = None\n        self.current_section_data = {}",
           UI, "a section of the previous well keeps scoping the new well (base well-change reset)"),
    # ------------------------------------------------------------ report_id / source link
    Mutant("R-ambiguous-drilldown", EV,
           "        if self.report_id is None or self.state == STATE_AMBIGUOUS:",
           "        if self.report_id is None:",
           CORE, "an ambiguous observation still offers a drill-down"),
    Mutant("R-source-link-lost", EV,
           '"hours": p.hours_on_bottom, "report_id": p.report_id,',
           '"hours": p.hours_on_bottom, "report_id": None,',
           BOTH, "the evidence row loses its report_id (source link)"),
    Mutant("R-wrong-report-id", EV,
           '                "rop", day, row["rop"], "m/hr", STATE_VALUE, "",\n'
           '                row.get("report_id"),',
           '                "rop", day, row["rop"], "m/hr", STATE_VALUE, "",\n'
           '                row.get("source_id"),',
           BOTH, "the drill-down opens the parameter row id instead of its report id"),
    # ------------------------------------------------------------ scope filters
    Mutant("F-evidence-bore-filter", EV,
           "    if scope.wellbore_id:\n        q = q.filter(DailyReport.wellbore_id == scope.wellbore_id)",
           "    if False:\n        q = q.filter(DailyReport.wellbore_id == scope.wellbore_id)",
           CORE, "evidence/NPT queries drop the wellbore filter"),
    Mutant("F-w12-bore-filter", W12,
           "            q = q.filter(DailyReport.wellbore_id == self.current_wellbore_id)\n        return q",
           "            pass\n        return q",
           UI, "W12 report queries drop the wellbore filter"),
    # ------------------------------------------------------------ same-date ROP
    Mutant("D-simple-mean", EV,
           '        value = sum(row["rop"] * h for row, (_, h, _) in zip(group, hours)) / total_h',
           '        value = sum(row["rop"] for row in group) / len(group)',
           CORE, "same-date rows averaged without their on-bottom hours"),
    # ------------------------------------------------------------ NPT coverage
    Mutant("C-zero-without-coverage", EV,
           "        if coverage < COVERAGE_SUFFICIENT_PERCENT:",
           "        if False:",
           BOTH, "a partially covered day becomes a valid (zero) NPT day"),
    Mutant("C-risk-ignores-coverage", EV,
           '    npt_ok = npt_pct is not None and bool(npt_coverage.get("complete"))',
           "    npt_ok = npt_pct is not None",
           CORE, "the NPT risk criterion is scored on incomplete time coverage"),
    Mutant("C-forecast-npt-days-only", W12,
           "        valid = [d for d in days if d.state == ev.STATE_VALUE]",
           "        valid = [d for d in days if d.state == ev.STATE_VALUE and d.npt_hours]",
           UI, "the NPT projection drops valid zero days (old: NPT days only)"),
    # ------------------------------------------------------------ projection
    Mutant("P-too-few-points", EV,
           "    if len(points) < minimum_points:",
           "    if len(points) < 2:",
           BOTH + M29, "a projection is fitted on fewer than five dates"),
    Mutant("P-ordinal-x", EV,
           "    xs = [(d - dates[0]).days + 1 for d in dates]",
           "    xs = list(range(1, len(dates) + 1))",
           CORE + M29, "the projection uses observation ordinals instead of calendar days"),
    # ------------------------------------------------------------ risk
    Mutant("K-missing-safety-low", EV,
           '        scores["Safety"] = None\n',
           '        scores["Safety"] = 2\n',
           CORE, "missing safety data scores as LOW risk"),
    # ------------------------------------------------------------ cost
    Mutant("M-mixed-currency-sum", W12,
           '        total_cost = kpis.get("total_cost")',
           '        total_cost = kpis.get("total_cost")\n'
           '        if total_cost is None and kpis.get("cost_groups"):\n'
           '            total_cost = sum(g["actual"] or 0 for g in kpis["cost_groups"])',
           UI, "cost lines in different currencies are summed"),
    # ------------------------------------------------------------ error -> empty
    Mutant("E-error-is-empty", W12,
           "            value = _LoadError(exc)",
           "            value = {}",
           UI, "a failed read is shown as empty data"),
    Mutant("E-canonical-error-swallowed", W12,
           "            raise RuntimeError(f\"canonical KPI read failed: {canonical['error']}\")",
           "            canonical = {}",
           UI, "the canonical service's error dict becomes 'No data'"),
    Mutant("E-status-hides-read-error", W12,
           '        failed += [f"read {name}" for name in dict.fromkeys(self._load_errors)]\n',
           "",
           UI, "a handled read failure is summarised as 'Updated'"),
    # ------------------------------------------------------------ cache
    Mutant("W-cache-key-scope-only", W12,
           "        return (f\"{name}|{self._scope_key()}|section={getattr(self, 'current_section_id', None)}\"\n"
           "                f\"|report={getattr(self, 'current_report_id', None)}|rev={self._data_rev}\")",
           '        return f"{name}|{self._scope_key()}"',
           UI, "the cache key ignores section, report and data revision"),
    Mutant("W-no-revision-invalidation", W12,
           "        if revision is None or revision != self._data_rev:",
           "        if False:",
           UI, "changed source data is served from the 30 s cache"),
    Mutant("W-auto-update-enum", W12,
           "        if state in (Qt.Checked, Qt.Checked.value, 2):",
           "        if state == Qt.Checked:",
           UI, "old toggle: stateChanged's int never equals the Qt.Checked enum"),
    # ------------------------------------------------------------ backend / suppression
    Mutant("B-global-suppression", W12,
           "import html as html_lib\n",
           'import html as html_lib\nimport warnings\nwarnings.filterwarnings("ignore")\n',
           UI, "module-level global warning suppression restored"),
    Mutant("B-forced-backend", W12,
           "import matplotlib\n",
           'import matplotlib\nmatplotlib.use("Qt5Agg")\n',
           UI, "module import forces a Matplotlib backend"),
    # ------------------------------------------------------------ legacy rows
    Mutant("L-canonical-legacy-double-count", "core/operations_intelligence.py",
           "                      .filter(canonical_params_clause(DrillingParameters))\n", "",
           CORE, "the canonical whole-well ROP counts a legacy row on a linked date"),
    Mutant("L-evidence-legacy-duplicate", EV,
           '        if row.get("report_id") is None and row.get("date") in linked_dates:',
           '        if False:',
           CORE, "the evidence trend keeps a legacy duplicate of a linked row"),
    Mutant("L-w12-legacy-double-count", W12,
           "            q = q.filter(canonical_params_clause(DrillingParameters))", "            pass",
           UI, "W12 best ROP / midpoints count a legacy row on a linked date"),
    # ------------------------------------------------------------ Qt object model
    Mutant("Q-metric-shadow", W12,
           '        card.metric_value = mv\n        card.value_label.setText(f"<b>{mv.number_text()}</b>")',
           '        card.metric_value = mv\n        card.metric = mv\n'
           '        card.value_label.setText(f"<b>{mv.number_text()}</b>")',
           UI, "a card attribute shadows the virtual QPaintDevice.metric() (crash in the event loop)"),
    Mutant("Q-card-style-unscoped", W12,
           "            QFrame#kpiCard {{", "            QFrame {{",
           UI, "the card rule leaks into its QLabel children (padding/border clip the KPI value)"),
    Mutant("Q-header-style-unscoped", W12,
           "            QWidget#analysisHeader {", "            QWidget {",
           UI, "the header box rule cascades padding/margin into the KPI card labels"),
    Mutant("Q-header-shared-cell", W12,
           "header_layout.addWidget(self.quality_label, 2, 0, 1, 2)",
           "header_layout.addWidget(self.quality_label, 1, 0, 1, 2)",
           UI, "the well row is painted over the Data Quality label again"),
    Mutant("Q-scope-label-invisible", W12,
           '"font-weight: bold; padding: 5px; color: #f5b041;")',
           '"font-weight: bold; padding: 5px; color: #2c3e50;")',
           UI, "the whole-well aggregate scope is drawn in the header background colour"),
    Mutant("S-stale-analytics-title", W12,
           "        self.analytics_plot.setTitle(None)\n", "",
           UI, "a previous analysis' chart title survives the next analysis or a deselect"),
    Mutant("Q-argb-hex-card", W12,
           '                border: 2px solid {_qss_rgba(color, "40")};',
           '                border: 2px solid {color}40;',
           UI, "a CSS-style #RRGGBBAA colour is parsed by Qt as #AARRGGBB (wrong card colour)"),
    Mutant("Q-depth-table-style-unscoped", W12,
           '            "QWidget#timeDepthTableBox { background: #2c3e50; border-radius: 8px; padding: 8px; }")',
           '            "background: #2c3e50; border-radius: 8px; padding: 8px;")',
           UI, "the Depth History container padding cascades into the table header"),
    Mutant("Q-quality-tooltip-literal-newline", W12,
           '            self.quality_label.setToolTip("\\n".join(',
           '            self.quality_label.setToolTip("\\\\n".join(',
           UI, "the data-quality tooltip shows a literal backslash-n instead of line breaks"),
    Mutant("Q-disabled-looks-enabled", W12,
           '        return styles.get(button_type, styles["default"]) + disabled',
           '        return styles.get(button_type, styles["default"])',
           UI, "a disabled drill-down button renders exactly like an enabled one"),
    Mutant("R-evidence-ring-stale", W12,
           "            self.evidence_plot.removeItem(old)\n", "",
           UI, "the previous selection ring stays on the evidence chart"),
    # ------------------------------------------------------------ exports
    Mutant("X-pdf-name-ignored", W12,
           "            self.export_dashboard(filename)",
           "            self.export_dashboard()",
           UI, "the chosen PDF file name is discarded"),
    Mutant("X-html-unescaped", W12,
           "        esc = html_lib.escape",
           "        esc = str",
           UI, "report HTML inserts names unescaped"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
