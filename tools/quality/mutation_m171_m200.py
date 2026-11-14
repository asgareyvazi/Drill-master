#!/usr/bin/env python3
"""Repeatable mutation run for the M171-M200 guards (review-queue correction, description headers, well identity).

Each mutant removes ONE guard in a scratch copy of the working tree and must be KILLED by the listed tests.
Engine: ``tools/quality/mutation_m46.py``. It runs a green baseline first, and an anchor that does not match
exactly once is reported INVALID, never killed. The repository is never modified.

Usage::

    python tools/quality/mutation_m171_m200.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

RSC = "core/review_scalar_correction.py"
RDLG = "dialogs/import_review_dialog.py"
DB = "core/database.py"
HA = "core/ddr_header_aliases.py"
MIN = "core/mineru_engine.py"
WI = "core/ddr_well_identity.py"
SVC = "core/ddr_import_service.py"
T173 = ["tests/test_m173_scalar_correction.py"]
T174 = ["tests/test_m174_header_aliases.py"]
T175 = ["tests/test_m175_well_identity.py"]
T176 = ["tests/test_m176_route_parity.py"]
PGT = "core/import_adapters/pdf_generic_tables.py"
PIPE = "core/ddr_import_pipeline.py"

MUTANTS = [
    # ---- M173 correction of a deferred scalar from the persisted queue ----
    Mutant("M173-bool-accepted", RSC, '    if isinstance(raw, bool) and target.sql_type != "boolean":\n',
           "    if False:\n", T173, "a yes/no value is stored as the text 'True' in a text field"),
    Mutant("M173-non-finite-accepted", RSC, "        if not math.isfinite(value) or abs(value) > MAX_MAGNITUDE:\n",
           "        if False:\n", T173, "NaN/inf/overflow reach the canonical record"),
    Mutant("M173-empty-becomes-value", RSC, "    if not text:\n        raise CorrectionRefused(\"An empty",
           "    if False:\n        raise CorrectionRefused(\"An empty", T173, "an empty edit is saved instead of refused"),
    Mutant("M173-bounds-ignored", RSC, "        if spec.min_val is not None and value < spec.min_val:\n",
           "        if False:\n", T173, "a value below the field's plausible minimum is saved"),
    Mutant("M173-percent-unbounded", RSC, '    if canonical_unit == "%" and not 0 <= value <= 100:\n',
           "    if False:\n", T173, "a percentage above 100 is saved"),
    Mutant("M173-unit-not-converted", RSC, "    if unit and canonical_unit and unit.strip() != canonical_unit:\n",
           "    if False:\n", T173, "a value entered in ft is stored as metres without conversion"),
    Mutant("M173-confirmation-skipped", RSC, "    if not confirmed:\n", "    if False:\n", T173,
           "an unconfirmed correction is written"),
    Mutant("M173-reason-optional", RSC,
           '    if not str(reason or "").strip():\n        raise CorrectionRefused("A reason is required for a correction',
           '    if False:\n        raise CorrectionRefused("A reason is required for a correction', T173,
           "a correction without a reason is written"),
    Mutant("M173-concurrency-ignored", RSC, "        if current != expected:\n", "        if False:\n", T173,
           "a value someone changed meanwhile is silently overwritten"),
    Mutant("M173-foreign-well-item", RSC, "    if item is None or item.well_id != well_id:\n",
           "    if item is None:\n", T173, "an item of another well is corrected from the selected well"),
    Mutant("M173-bulk-table-guessed", RSC, "    if entity in NOT_CORRECTABLE:\n", "    if False:\n", T173,
           "a multi-row table value is written to a guessed row"),
    Mutant("M173-decided-item-overwritten", RSC,
           "            raise CorrectionRefused(f\"The review item is already decided ({item.state}); reopen it first\")\n",
           "            pass\n", T173, "an already decided item is corrected again without being reopened"),
    Mutant("M173-history-lost", RSC, "    item.decision_history_json = json.dumps(entries",
           "    item.decision_history_json = json.dumps(entries[-1:]", T173,
           "earlier decisions are dropped from the item's history"),
    Mutant("M173-mud-loss-not-redirected", RSC,
           'STORED_AS = {"daily_report.mud_lost_downhole": "mud_report.loss_downhole"}',
           "STORED_AS = {}", T173, "the mud-loss item cannot be corrected although the import stores it on the mud report"),
    Mutant("M173-save-without-preview", RDLG,
           '        ready = bool(self.preview and not self.preview.get("conflict") and self.confirm_box.isChecked()\n',
           '        ready = bool(self.confirm_box.isChecked()\n', T173, "Save is enabled without a valid preview"),
    Mutant("M173-snapshot-missing", DB, '                    payload["target_at_creation"] = snapshot_target(active, row)\n',
           "                    pass\n", T173, "new queue items lose their target-at-creation snapshot"),
    # ---- M174 description headers ----
    Mutant("M174-ambiguity-guessed", HA, "    if len(candidates) > 1:\n", "    if False:\n", T174,
           "two candidate description columns: the first one is mapped without an operator decision"),
    Mutant("M174-outside-time-log", HA, "    if section is None:\n        return fields, dict(outcome, state=\"NOT_TIME_LOG\")\n",
           "    if section is None:\n        section = \"time_log\"\n", T174,
           "a generic 'Description' column outside a time log is mapped as activity text"),
    Mutant("M174-explicit-overridden", HA, "    if target in fields:\n", "    if False:\n", T174,
           "a generic header overrides an explicitly mapped activity column"),
    Mutant("M174-fuzzy-prefix", HA,
           "if index < len(fields) and fields[index] is None and normalize_header(header) in keys]",
           "if index < len(fields) and fields[index] is None and any(normalize_header(header).startswith(k) "
           "for k in keys)]", T174, "partial matches such as 'Activity Code' are mapped as the description"),
    Mutant("M174-override-ignored", HA, "    if RULE_KEY in rules:\n", "    if False:\n", T174,
           "a profile's own header list (or an explicit off switch) is ignored"),
    Mutant("M174-persian-forms-lost", HA, "    value = unicodedata.normalize(\"NFKC\", str(text or \"\")).translate(_LETTERS)\n",
           "    value = unicodedata.normalize(\"NFKC\", str(text or \"\"))\n", T174,
           "Arabic-script letter variants of a Persian header no longer match"),
    Mutant("M174-provenance-dropped", MIN,
           "            outcome = dict(outcome, source=self._table_source(table.provenance, table),\n",
           "            outcome = dict(outcome, source={},\n", T174,
           "the mapped header loses its page and bounding box"),
    # ---- M175 well identity ----
    Mutant("M175-twin-hidden", WI,
           "    return [w for w in wells if getattr(w, attribute) and _norm(getattr(w, attribute)) == _norm(value)]\n",
           "    exact = [w for w in wells if getattr(w, attribute) == value]\n    return exact or [w for w in wells "
           "if getattr(w, attribute) and _norm(getattr(w, attribute)) == _norm(value)]\n", T175,
           "an equivalent spelling on another well is hidden and the import routed to the exact spelling"),
    Mutant("M175-stale-decision-accepted", WI, "    if stale:\n        raise WellIdentityRefused(",
           "    if False:\n        raise WellIdentityRefused(", T175,
           "a decision made against another source or database state is applied"),
    Mutant("M175-decision-not-required", WI,
           "    if not isinstance(decision, Mapping):\n        raise WellIdentityRefused(f\"NOT SAVED: {assessment.message} "
           "Choose the target well explicitly.\", assessment)\n",
           "    if not isinstance(decision, Mapping):\n        return assessment.selected.id, False\n", T175,
           "a source naming another well is imported into the selected well without a decision"),
    Mutant("M175-refusal-ignored", WI, "    if assessment.refused:\n        raise WellIdentityRefused(assessment.message, "
           "assessment)\n", "    if False:\n        raise WellIdentityRefused(assessment.message, assessment)\n", T175,
           "an ambiguous or contradictory identity is imported"),
    Mutant("M175-project-scope-lost", WI,
           "    scope = [w for w in wells if selected is None or w.project_id == selected.project_id]\n",
           "    scope = list(wells)\n", T175, "a same-named well in another project makes the selected well's import ambiguous"),
    Mutant("M175-master-overwritten", SVC, "            if wi and keep_selected_master:\n", "            if False:\n",
           T175, "importing into the selected well overwrites its master data with the other well's header"),
    Mutant("M175-decision-in-fingerprint", SVC,
           '        if isinstance(metadata, dict) and {"well_identity_decision", "source_provenance"} & set(metadata):\n',
           "        if False:\n", T175, "a retry with a fresh decision is not recognised as the same source"),
    # ---- M176 route parity and provenance ----
    Mutant("M176-wrapped-join-silent", PGT,
           '                    joins.append({"row": len(rows), "column": col, "text": row_cells[0][2]})\n',
           "                    pass\n", T176, "a PDF line is joined to the row above without a review notice"),
    Mutant("M176-join-row-offset-lost", PGT, '                    dict(j, row=j["row"] + offset) for j in table["wrapped_joins"])',
           '                    dict(j) for j in table["wrapped_joins"])', T176,
           "a join on page 2 of a continued table points at the wrong row"),
    Mutant("M176-row-page-lost", MIN, "    if 0 < row_number <= len(pages) and pages[row_number - 1] is not None:\n",
           "    if False:\n", T176, "rows that continue on the next PDF page are recorded on the first page"),
    Mutant("M176-morning-heading-ignored", MIN,
           '        target = "time_log_morning" if named("time_log_morning") else "time_log" if named("time_log") else None\n',
           '        target = None\n', T176, "a morning time log under an explicit heading is parked unstored"),
    Mutant("M176-unstored-table-silent", MIN, '                if storage_key == "document_tables" and table_records:\n',
           "                if False:\n", T176, "rows of a mixed table are parked without telling the operator"),
    Mutant("M176-sha-missing", PIPE, '        "sha256": file_fingerprint(str(source)),\n', '        "sha256": None,\n', T176,
           "the imported file's SHA-256 is not recorded"),
    Mutant("M176-size-zero", PIPE, "        size = None\n", "        size = 0\n", T176,
           "an unreadable file size is recorded as 0 instead of unknown"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
