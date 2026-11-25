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

T = ["tests/test_m464_eowr_source_sections.py"]
J = ["tests/test_m467_eowr_mainwindow_journey.py"]
TC = ["tests/test_m469_citation_passage_service.py"]
JC = TC + ["tests/test_m472_citation_mainwindow_journey.py"]

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
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
