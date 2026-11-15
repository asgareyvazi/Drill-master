#!/usr/bin/env python3
"""Repeatable mutation run for the M201-M230 guards (tubular REPLACE / upsert guards, report-revision and restore
guards, missing weights and legacy-preset provenance, schematic ownership, Excel limits, header mapping, review
claims, import target context and confirmed DDR carry-forward).

Each mutant removes ONE guard in a scratch copy of the working tree and must be KILLED by the listed tests.
Engine: ``tools/quality/mutation_m46.py``. It runs a green baseline first, and an anchor that does not match
exactly once is reported INVALID, never killed. The repository is never modified.

Usage::

    python tools/quality/mutation_m201_m230.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

SG = "core/storage_guards.py"
DBM = "core/db_maintenance.py"
VP = "core/engineering/value_provenance.py"
SD = "core/schematic_document.py"
W3B = "tabs/w3b_wellbore_schematic_tab.py"
WB = "core/workbook_io.py"
SVC = "core/ddr_import_service.py"
PIPE = "core/ddr_import_pipeline.py"
TRM = "core/table_record_mapper.py"
EI = "core/excel_intelligence.py"
RSC = "core/review_scalar_correction.py"
DB = "core/database.py"
XID = "dialogs/excel_import_dialog.py"
CF = "core/ddr_carry_forward.py"
CFD = "dialogs/carry_forward_dialog.py"

T203 = ["tests/test_m203_tubular_replace_guards.py", "tests/test_m204_immutable_write_paths.py"]
T204R = ["tests/test_m204_restore_migration_cascade.py"]
T205 = ["tests/test_m205_m207_schematic_provenance.py"]
T213 = ["tests/test_m213_excel_limits.py"]
T214 = ["tests/test_m214_header_mapping.py", "tests/test_table_mapper.py"]
T215 = ["tests/test_m215_scalar_correction_adversarial.py", "tests/test_m173_scalar_correction.py"]
T216 = ["tests/test_m216_import_context_switch.py"]
T217 = ["tests/test_m217_day_by_day_carry_forward.py"]
T218 = ["tests/test_m218_ddr_revision_lineage.py"]

MUTANTS = [
    # M203 (D61 residual): REPLACE / upsert into a tubular set or item.
    Mutant("M203-tubular-noreplace", SG,
           "                     f\"WHEN EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id) \"\n"
           "                     f\"BEGIN SELECT RAISE(ABORT, '{table}: a stored row cannot be replaced'); END\")",
           "                     f\"WHEN 0 AND EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id) \"\n"
           "                     f\"BEGIN SELECT RAISE(ABORT, '{table}: a stored row cannot be replaced'); END\")",
           T203, "INSERT OR REPLACE / upsert on the id of a published set or item accepted"),
    Mutant("M203-tubular-nodupkey", SG,
           "out[name] = (f\"CREATE TRIGGER {name} BEFORE INSERT ON {table} WHEN EXISTS (SELECT 1 FROM {table} WHERE {match}) \"",
           "out[name] = (f\"CREATE TRIGGER {name} BEFORE INSERT ON {table} WHEN 0 AND EXISTS (SELECT 1 FROM {table} WHERE {match}) \"",
           T203, "REPLACE on the (name, version) / (set, fingerprint) key replaces a published row"),
    Mutant("M203-tubular-nodupkey-partial-key", SG,
           "        match = \" AND \".join(f\"{c} = NEW.{c}\" for c in key)\n        name = f\"{prefix}_nodupkey_v{v}\"",
           "        match = \" AND \".join(f\"{c} = NEW.{c}\" for c in key[1:])\n        name = f\"{prefix}_nodupkey_v{v}\"",
           T203, "the duplicate-key guard compares only part of the unique key"),
    # M218: report revision snapshots.
    Mutant("M218-revision-snapshot-unfrozen", SG,
           '_REPORT_REVISION_FROZEN = ("id", "report_id", "revision_no", "status", "snapshot", "created_at", "comment")',
           '_REPORT_REVISION_FROZEN = ("id", "report_id", "revision_no", "status", "created_at", "comment")',
           T218, "the snapshot of a report revision can be rewritten"),
    Mutant("M218-revision-update-guard", SG,
           'f"report_revisions WHEN {_frozen(_REPORT_REVISION_FROZEN)} OR "',
           'f"report_revisions WHEN 0 AND {_frozen(_REPORT_REVISION_FROZEN)} AND "',
           T218, "a report revision can be updated by any writer"),
    Mutant("M218-revision-noreplace", SG,
           '"report_revisions WHEN EXISTS (SELECT 1 FROM report_revisions WHERE id = NEW.id) "',
           '"report_revisions WHEN 0 AND EXISTS (SELECT 1 FROM report_revisions WHERE id = NEW.id) "',
           T218, "INSERT OR REPLACE over a stored report revision accepted"),
    # M204 (D70): restore installs the current guards.
    Mutant("M204-restore-guards", DBM, "        self._guard_staged(staged)\n", "", T204R,
           "a restored backup without the current guards stays unguarded for the session"),
    # M205: missing weight stays None.
    Mutant("M205-document-weight-zero", SD,
           '                            weight_ppf=values["weight_ppf"] if not legacy else None,',
           '                            weight_ppf=(values["weight_ppf"] or 0.0) if not legacy else None,',
           T205, "a missing weight read from a schematic document becomes 0.0"),
    Mutant("M205-table-weight-zero", W3B,
           'casing.weight_ppf = None if wt_text in ("", "—", "-") else float(wt_text)',
           'casing.weight_ppf = 0.0 if wt_text in ("", "—", "-") else float(wt_text)',
           T205, "an empty weight cell is stored as 0.0"),
    # M206: legacy preset provenance.
    Mutant("M206-preset-label", VP, 'PRESET_LABEL = "LEGACY_PRESET — SOURCE UNVERIFIED"',
           'PRESET_LABEL = "Manufacturer data"', T205, "a legacy preset is labelled as manufacturer data"),
    Mutant("M206-preset-holds-ignores-values", VP,
           "    return bool(copied) and all(k in values and _same(values[k], v) for k, v in copied.items())",
           "    return bool(copied)", T205, "an edited value keeps the preset origin"),
    # M207: schematic ownership and bindings.
    Mutant("M207-foreign-well-accepted", SD, "    if foreign and not accept_foreign:\n", "    if False:\n", T205,
           "another well's schematic is imported without confirmation"),
    Mutant("M207-tampered-binding-kept", SD,
           '        if binding is not None and tr.verify_snapshot((binding or {}).get("snapshot") or {}):',
           "        if False:", T205, "a binding whose snapshot does not verify is kept"),
    # M213: Excel limits.
    Mutant("M213-profile-loosens", WB,
           "    values = {name: min(int(rule.get(name, getattr(HARD_LIMITS, name))), getattr(HARD_LIMITS, name))",
           "    values = {name: max(int(rule.get(name, getattr(HARD_LIMITS, name))), getattr(HARD_LIMITS, name))",
           T213, "a profile limit is not applied (the built-in limit wins)"),
    Mutant("M213-file-size", WB, "    if size > limits.max_bytes:\n", "    if False:\n", T213,
           "an oversized file is read"),
    Mutant("M213-sheet-count", WB, "    if len(sheets) > limits.max_sheets:\n", "    if False:\n", T213,
           "a workbook with too many sheets is read"),
    Mutant("M213-declared-shape-precheck", SVC,
           "        try:\n            check_workbook_shape(declared, limits)\n",
           "        try:\n            pass\n", T213, "the declared dimensions are not checked before the cells are read"),
    Mutant("M213-pipeline-pass-through", PIPE,
           "            _rep, extracted = extract_file(path) if limits is HARD_LIMITS else extract_file(path, limits=limits)",
           "            _rep, extracted = extract_file(path)", T213,
           "the profile's shape limits never reach the extractor"),
    # M214: header mapping.
    Mutant("M214-substring-match", TRM,
           "    if compact_header == compact_alias or _norm(header) == _norm(alias):\n        return EXACT",
           "    if compact_alias in compact_header or compact_header in compact_alias:\n        return EXACT",
           T214, "substring header matching again (one header fills several fields)"),
    Mutant("M214-tie-not-ambiguous", TRM, "        if len(top) > 1:\n", "        if False:\n", T214,
           "a tie between two fields is resolved silently"),
    Mutant("M214-short-alias-phrase", TRM,
           "    if len(compact_alias) < 3 or not phrase or len(phrase) > len(words):",
           "    if not phrase or len(phrase) > len(words):", T214, "1-2 character aliases match inside headers"),
    Mutant("M214-never-accepted-sources", EI, 'NEVER_ACCEPTED_SOURCES = frozenset({"fuzzy_match", "spatial"})',
           "NEVER_ACCEPTED_SOURCES = frozenset()", T214, "a fuzzy or spatial candidate is accepted"),
    # M215 (D67): one decision at a time.
    Mutant("M215-claim-apply", RSC,
           "    with db.session_scope() as session:\n        claim_review_item(session, item_id)\n"
           "        item = _item(session, item_id, well_id)\n        if item.state not in (DEFERRED_UNRESOLVED",
           "    with db.session_scope() as session:\n"
           "        item = _item(session, item_id, well_id)\n        if item.state not in (DEFERRED_UNRESOLVED",
           T215, "two operators can both apply the same correction"),
    Mutant("M215-claim-reopen", RSC,
           "        claim_review_item(session, item_id)\n        item = _item(session, item_id, well_id)\n"
           "        if item.state not in (ACCEPTED, REJECTED, IGNORED):",
           "        item = _item(session, item_id, well_id)\n"
           "        if item.state not in (ACCEPTED, REJECTED, IGNORED):",
           T215, "two operators can both reopen the same item"),
    Mutant("M215-claim-resolve", DB,
           "            claim_review_item(session, item_id)          # M215 (D67): one decision at a time per database\n",
           "", T215 + ["tests/test_m169_end_to_end_journey.py"], "two operators can both resolve the same review item"),
    # M216 (D68): import target context.
    Mutant("M216-save-recheck", XID,
           "                if self.well_id != batch_well_id:                    # M216 (D68): re-checked at the save, too\n",
           "                if False:\n", T216, "a well switch during the preview reaches the save"),
    Mutant("M216-batch-target-restored", XID, "                    self.well_id = batch_well_id\n",
           "                    pass\n", T216, "a file routed to another well retargets the rest of the batch"),
    # M217 (D71): confirmed carry-forward.
    Mutant("M217-confirmation", CF, "    if not confirmed:\n        raise CarryForwardRefused(",
           "    if False:\n        raise CarryForwardRefused(", T217, "carry-forward without confirmation"),
    Mutant("M217-never-carried", CF, "        if key in NEVER_CARRIED:\n", "        if False:\n", T217,
           "a daily measurement is offered for carrying (refused only as 'unknown')"),
    Mutant("M217-existing-rows", CF, "        if existing:\n            raise CarryForwardRefused(",
           "        if False:\n            raise CarryForwardRefused(", T217,
           "a section that already has rows today is added to"),
    Mutant("M217-unentered-header", CF, "        if getattr(target, field) in UNENTERED_HEADER[field]:",
           "        if True:", T217, "a derived header overwrites an entered value"),
    Mutant("M217-fuel-movements-zero", CF,
           "fuel_consumed=null(), fuel_received=null(), water_consumed=null(),",
           "fuel_consumed=0.0, fuel_received=0.0, water_consumed=0.0,", T217,
           "carried fuel / water movements become a measured 0"),
    Mutant("M217-foreign-well", CF,
           " or source.id == target.id or source.well_id != target.well_id:",
           " or source.id == target.id:", T217, "a report of another well is a carry source"),
    Mutant("M217-dialog-ok-without-confirmation", CFD,
           "        ready = self.confirm_box.isChecked() and bool(self.selected_sections() or self.selected_header())",
           "        ready = bool(self.selected_sections() or self.selected_header())", T217,
           "OK is enabled without the confirmation box"),
    Mutant("M217-dialog-preselects", CFD,
           "            box.setEnabled(not item[\"blocked\"])\n",
           "            box.setEnabled(not item[\"blocked\"])\n            box.setChecked(True)\n", T217,
           "sections are preselected"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
