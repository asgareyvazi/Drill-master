#!/usr/bin/env python3
"""Repeatable mutation run for M461-M520: the EOWR source-data sections (M464-M468) and the missions added later
in this delivery.

Same engine and rules as ``tools/quality/mutation_m401_m460.py`` (``tools/quality/mutation_m46.py``): one realistic
defect per mutant in a scratch copy, the listed tests must KILL it, an anchor that does not match exactly once is
INVALID, ``--only`` never gives complete=True. Mutation results show which defects the tests detect; they are not a
proof of correctness.

Usage::

    python tools/quality/mutation_m461_m520.py [--json OUT] [--only ID[,ID...]]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

ES = "core/eowr_sections.py"
RE = "core/report_engine.py"
RS = "core/report_sections.py"
RP = "core/report_provenance.py"
W11 = "tabs/w11_Export.py"
CP = "core/citation_passage.py"
DT = "tabs/documents_tab.py"
KA = "tabs/knowledge_assistant.py"
DR = "core/drilloff_robust.py"
HB = "core/hydraulics_hb_slot.py"
SS = "core/surge_swab.py"

T = ["tests/test_m464_eowr_source_sections.py"]
J = ["tests/test_m467_eowr_mainwindow_journey.py"]
TC = ["tests/test_m469_citation_passage_service.py"]
JC = TC + ["tests/test_m472_citation_mainwindow_journey.py"]
TD = ["tests/test_m475_drilloff_robust.py"]
TI = ["tests/test_m488_integration_consistency.py"]
ESD = "dialogs/engineering_service_dialog.py"
MDD = "dialogs/mse_drilloff_dialog.py"
VMD = "dialogs/well_control_volumetric_dialog.py"
HR = "core/history_replay.py"

MUTANTS = [
    # ------------------------------------------------------------------ M464-M466 EOWR source-data sections
    Mutant("ES-undated-in-period", ES, "    return d is not None and period[0] <= d <= period[1]\n",
           "    return d is None or period[0] <= d <= period[1]\n", T,
           "an undated record is reported inside every period"),
    Mutant("ES-query-failed-as-empty", ES,
           "        if records is None or status.get(key) == QUERY_FAILED_STATUS:\n",
           "        if records is None:\n            records = []\n        if status.get(key) == 'never':\n", T,
           "a failed table is reported as 'none recorded'"),
    Mutant("ES-empty-payload-as-included", ES, "        elif rows:\n", "        elif sources:\n", T,
           "a stored bit report with an empty payload is reported INCLUDED"),
    Mutant("ES-escape-dropped", ES, "    e = _html.escape\n", "    e = str\n", T,
           "stored (user / import) text is written into the report HTML unescaped"),
    Mutant("ES-unknown-keys-dropped", ES, "    out[\"Other fields\"] = \"; \".join(other) if other else \"—\"\n",
           "    out[\"Other fields\"] = \"—\"\n", T, "a payload key that is not a known column disappears"),
    Mutant("ES-missing-as-zero", ES, "    if value is None:\n        return \"—\"\n",
           "    if value is None:\n        return \"0\"\n", T, "a missing stored value is shown as 0"),
    Mutant("ES-time-order-insertion", ES, "    for log in sorted(records, key=key):\n",
           "    for log in records:\n", T, "time logs are listed in insertion order, not chronologically"),
    Mutant("ES-undated-first", ES, "    return (d is None, d or date.min)",
           "    return (d is not None, d or date.min)", T, "undated rows sort before dated ones"),
    Mutant("ES-inverted-period-accepted", ES, "    if out[0] > out[1]:\n", "    if False:\n", T,
           "a period that ends before it starts is accepted (empty report instead of an error)"),
    Mutant("ES-source-id-dropped", ES, "\"Source\": f\"{table} id {log.id} (", "\"Source\": f\"{table} (", T,
           "a time-log row no longer names its source record"),
    Mutant("ES-legacy-bha-unreadable", ES, "    if isinstance(value, dict):                          # legacy",
           "    if False:                          # legacy", T,
           "legacy named BHA configurations are reported unreadable instead of rendered"),
    # ------------------------------------------------------------------ engine / manifest / provenance wiring
    Mutant("RE-failed-query-as-empty", RE,
           "                        source_query_status[key] = eowr_sections.QUERY_FAILED_STATUS\n"
           "                        return None\n",
           "                        source_query_status[key] = eowr_sections.AVAILABLE\n"
           "                        return []\n", T, "the engine swallows a failed query as an empty table"),
    Mutant("RE-period-ignored", RE, "            data = self._collect_data(well_id, period=period)\n",
           "            data = self._collect_data(well_id, period=None)\n", T + J,
           "the requested period is silently replaced by the whole well"),
    Mutant("RE-period-time-logs-unfiltered", RE,
           "                    time_logs_24h = by_report(time_logs_24h, \"time_logs_24h\")\n",
           "                    time_logs_24h = time_logs_24h\n", T + J, "24-hour time logs ignore the period"),
    Mutant("RE-period-undated-equipment-kept", RE,
           "                    equipment_logs = dated(equipment_logs, \"equipment_logs\", \"service_date\")\n",
           "", T, "equipment logs ignore the period (undated ones included)"),
    Mutant("RE-sections-not-in-body", RE,
           "        html += '<div class=\"page-break\"></div>' + eowr_sections.html_sections(eowr_sections.analyse(data))\n",
           "", T + J, "the manifest names INCLUDED sections that the report body does not show"),
    Mutant("RE-sections-not-in-excel", RE,
           "                self._write_sheet_from_objects(wb, sheets[res.key], eowr_sections.sheet_records(res))\n",
           "                pass\n", T, "the Excel / CSV outputs lose the source-data sections"),
    Mutant("RS-eowr-scope-hidden", RS, "    entries.insert(0, _entry(\"Scope\", INCLUDED, None, "
           "eowr_sections.period_label(period) + (",
           "    entries.insert(0, _entry(\"Scope\", INCLUDED, None, eowr_sections.period_label(None) + (", T,
           "the manifest claims a whole-well scope for a period report"),
    Mutant("RP-period-not-stated", RP, "    if period is not None:                                   # M465",
           "    if False:                                   # M465", T,
           "the provenance scope keeps the daily-report span instead of the requested period"),
    Mutant("W11-period-ignored", W11, "            args = ((date_from, date_to),)\n", "            args = ()\n", J,
           "the W11 period option is shown but not applied"),
    Mutant("W11-inverted-period-accepted", W11, "            if date_from > date_to:\n", "            if False:\n", J,
           "the W11 tab starts an export with an inverted period"),
    # ------------------------------------------------------------------ M469-M472 citation passage service (U2)
    Mutant("CP-duplicate-keys-accepted", CP, "object_pairs_hook=_no_duplicates, ", "", TC,
           "a repeated key silently shadows the first (a second \"start\" wins)"),
    Mutant("CP-nan-accepted", CP, ", parse_constant=_no_constant)", ")", TC, "NaN / Infinity are accepted"),
    Mutant("CP-recursion-uncaught", CP, "    except RecursionError as exc:\n"
           "        raise PassageError(\"The citation file is nested too deeply; it is refused.\") from exc\n", "",
           TC, "a deeply nested file crashes the reader instead of being refused"),
    Mutant("CP-non-regular-file-read", CP, "    if not stat.S_ISREG(info.st_mode):\n", "    if False:\n", TC,
           "a directory / device / FIFO is opened as a record"),
    Mutant("CP-size-limit-raised", CP, "MAX_FILE_BYTES = 4 * 1024 * 1024\n", "MAX_FILE_BYTES = 4 * 1024 ** 3\n", TC,
           "the published file-size limit is not the enforced one"),
    Mutant("CP-bool-as-offset", CP, "        if isinstance(value, bool) or not isinstance(value, int)",
           "        if not isinstance(value, int)", TC, "a JSON boolean is accepted as an id or offset"),
    Mutant("CP-sha-unchecked", CP,
           "    if not isinstance(entry[\"text_version\"], str) or not SHA_PATTERN.fullmatch(entry[\"text_version\"]):\n",
           "    if not isinstance(entry[\"text_version\"], str):\n", TC, "any text is accepted as a page hash"),
    Mutant("CP-identity-unchecked", CP, "                and recorded != stored:\n", "                and False:\n", JC,
           "a record from another library opens an unrelated document with the same id"),
    Mutant("CP-invalid-entry-verified", CP, "        if problem:\n            label = ", "        if False:\n            label = ",
           TC, "a malformed citation is passed on to verification and navigation"),
    Mutant("DT-guard-dropped", DT, "        if not target[\"openable\"]:\n            self.citation_file_status.setText(",
           "        if False:\n            self.citation_file_status.setText(", TC + ["tests/test_m472_citation_mainwindow_journey.py"],
           "the library page opens a passage that is not openable"),
    Mutant("DT-stale-targets", DT, "            self.citation_file_status.setText(f\"Not opened: {exc}\")\n"
           "            self._set_citation_file_targets([])\n",
           "            self.citation_file_status.setText(f\"Not opened: {exc}\")\n", TC,
           "a refused file leaves the previous record's passages openable"),
    Mutant("DT-rich-text-status", DT,
           "        self.citation_file_status.setTextFormat(Qt.PlainText)       # record text is untrusted, never rich text\n",
           "", TC, "untrusted record text can render as rich text on the library page"),
    Mutant("KA-rich-text-status", KA,
           "        self.citation_status.setTextFormat(Qt.PlainText)      # M471: record text is untrusted, never rich text\n",
           "", TC, "untrusted record text can render as rich text in the assistant"),
    Mutant("KA-bypasses-service", KA,
           "            record, results, targets = cp.open_record(self.db_manager, path)   # M470: bounded strict read\n",
           "            record = cr.load(path)\n            results = cr.verify_record(self.db_manager, record)\n"
           "            targets = cr.navigation(record, results)\n", TC,
           "the assistant reads a record without the strict service"),
    # ------------------------------------------------------------------ M475-M478 robust drill-off v2 / M482 Erge
    Mutant("DR-l2-not-l1", DR, "    sad = np.abs(y[None, :] - coef @ design.T).sum(axis=1)\n",
           "    sad = ((y[None, :] - coef @ design.T) ** 2).sum(axis=1)\n", TD,
           "the vertex search minimises squared residuals (least squares), not absolute residuals"),
    Mutant("DR-last-tie", DR, "    index = int(np.flatnonzero(sad <= best + TIE_REL * max(1.0, best))[0])",
           "    index = int(np.argmax(sad))", TD, "the worst vertex is kept instead of the L1 minimum"),
    Mutant("DR-golden-kept-blindly", DR, "        if fit is not None and (best is None or fit[1] < best[2]):\n"
           "            best = (b, fit[0], fit[1], fit[2])\n",
           "        if fit is not None:\n            best = (b, fit[0], fit[1], fit[2])\n", TD,
           "the refined breakpoint replaces a better grid point"),
    Mutant("DR-range-includes-ends", DR, "    lo_index, hi_index = 1, len(xs) - 2\n",
           "    lo_index, hi_index = 0, len(xs) - 1\n", TD,
           "the breakpoint may sit at the first or last step (one-point segments)"),
    Mutant("DR-vertex-in-scale", DR, "    off_vertex = [abs(r) for i, r in enumerate(residuals) if i not in vertex]\n",
           "    off_vertex = [abs(r) for r in residuals] + [0.0] * 40\n", TD,
           "the robust scale is biased to zero, so ordinary residuals are flagged as outliers"),
    Mutant("DR-outlier-removed", DR, "    return {\"status\": COMPUTED, **base, \"founder_status\": status,",
           "    xs = [x for x in xs if x not in flagged]\n"
           "    return {\"status\": COMPUTED, **base, \"founder_status\": status,", TD,
           "flagged steps are silently dropped from the reported step count"),
    Mutant("DR-flags-dropped", DR, "            \"vertex_wob_klbf\": [xs[i] for i in vertex], \"flagged_wob_klbf\": flagged,",
           "            \"vertex_wob_klbf\": [xs[i] for i in vertex], \"flagged_wob_klbf\": [],", TD,
           "outliers are no longer reported"),
    Mutant("DR-basis-defaulted", DR, "    basis = basis.strip() if isinstance(basis, str) and basis.strip() else None\n",
           "    basis = basis.strip() if isinstance(basis, str) and basis.strip() else \"surface\"\n", TD,
           "a missing WOB basis is silently taken as surface"),
    Mutant("DR-basis-not-hashed", DR, "    frozen[\"wob_basis\"] = basis\n    rows = []\n",
           "    rows = []\n", TD, "the declared WOB basis is not part of the frozen inputs and their SHA-256"),
    Mutant("DR-surface-shown-as-downhole", DR, "    if basis == \"downhole\":\n", "    if basis:\n", TD,
           "a surface WOB is labelled as a downhole WOB"),
    Mutant("DR-founder-rule-inverted", DR, "    if b > 0 and upper < v[\"slope_ratio\"] * b:\n",
           "    if b > 0 and upper > v[\"slope_ratio\"] * b:\n", TD, "the declared founder rule is inverted"),
    Mutant("DR-min-steps-lowered", DR, "MIN_STEPS = 6\n", "MIN_STEPS = 4\n", TD,
           "too few steps are accepted for a robust fit"),
    Mutant("DR-rpm-tolerance-ignored", DR, "    if max(rpms) - min(rpms) > v[\"rpm_tolerance_rpm\"]:\n",
           "    if False:\n", TD, "a test with varying RPM is fitted as a drill-off test"),
    Mutant("HB-erge-note-dropped", HB, "            \"verification_note\": verification_note(v[\"transition_criterion\"])}\n",
           "            \"verification_note\": None}\n", TD, "Erge 2015 results no longer say NOT VERIFIED"),
    Mutant("HB-erge-note-not-in-case", HB,
           "    return f\"{label}; \" + (f\"NOT VERIFIED: {note}; \" if note else \"\") + f\"inputs SHA-256",
           "    return f\"{label}; \" + f\"inputs SHA-256", TD, "a stored Erge case loses the NOT VERIFIED note"),
    Mutant("SS-erge-note-dropped", SS,
           "    note = hb.verification_note((result.get(\"inputs\") or {}).get(\"transition_criterion\"))   # M482\n",
           "    note = None\n", TD, "the surge summary hides that Erge 2015 is NOT VERIFIED"),
    # ------------------------------------------------------------------ M488-M492 integration consistency
    Mutant("ESD-rich-text-summary", ESD, "        self.summary.setTextFormat(Qt.PlainText)     # M491: echoes typed text (error reasons), never rich text\n", "", TI, "typed text in an error reason renders as rich text"),
    Mutant("MDD-rich-text-summary", MDD, "        self.summary.setTextFormat(Qt.PlainText)     # M491: echoes typed text (error reasons), never rich text\n", "", TI, "the M372 dialog summary renders rich text"),
    Mutant("VMD-rich-text-summary", VMD, "        self.summary.setTextFormat(Qt.PlainText)     # M491: echoes typed text (error reasons), never rich text\n", "", TI, "the volumetric dialog summary renders rich text"),
    Mutant("HR-robust-adapter-missing", HR, "    \"m475.drilloff_robust\": (\"core.drilloff_robust\", \"robust (L1) drill-off\"),\n",
           "", TI + TD, "a catalogued case service has no replay adapter"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
