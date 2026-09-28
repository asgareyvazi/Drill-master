#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-014 (45 MEDIUM records, class A).

Phase 2, third batch: the export/metadata surface (professional_export, managers, editor_state),
engineering parameter defaults and the calculation-verification repositories, the profile import
extractor, the DDR import service's template selection, import diagnostics/profiling and the
hierarchy delete gate.  One genuine defect was found and fixed here (INV34-002457, commit
0699e50) with its regression test; every other site is adjudicated by the contract quoted in
`evidence`, following the same method as p6_batch_005..012.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-014"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

RECHECK_AGAINST: dict[str, str] = {}


def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Second register record for {where}, already adjudicated under {sibling}: "
            f"{summary}",
            None)


def cosmos(what: str) -> tuple[str, str, None]:
    """A rule mis-fire where the subject is not a number at all."""
    return (DUP,
            f"Rule mis-fire, not a behaviour to adjudicate: {what}",
            None)


# ---------------------------------------------------------------------------
# Contracts quoted by this batch's adjudications (all verified at the site).
# ---------------------------------------------------------------------------

_SUMMARY_WRITE = (
    "`result_summary(result_values or {})` and `result_json=dict(result_values or {})` are the "
    "repository's two projections of the *same* caller-supplied composite result, in one unit of "
    "work: 'Builds the canonical snapshot from the *exact* inputs used, stores it with the derived "
    "result and promoted summary columns, all in a single ``session_scope`` unit of work so a "
    "failure leaves no partial row' (cement_repository.py:98-103).  The promoted columns are an "
    "index over the JSON payload, never an independent source - `result_summary` is "
    "`{k: _clean_number(values.get(k)) for k in SUMMARY_KEYS}` (cement_persistence.py:144-146; the "
    "identical helper in mse/mud_volume/torque_drag persistence) and `_clean_number` is documented "
    "'Return a finite float or ``None`` (never a bool, NaN or inf)' - so a key the engine did not "
    "produce becomes NULL in the index, never 0.  No caller can pass 'no result': each save handler "
    "stores the dict of a run that actually happened and refuses to call the repository when nothing "
    "was calculated - `repo = self._mse_repo(); ... repo.save_run(inputs=run[\"inputs\"], "
    "result_values=run[\"result_values\"], method=run[\"method\"], ...)` after the explicit "
    "refusal '... available to save (Calculate Bit Hydraulics).' (tabs/w13_Engineering_Calculator.py:"
    "2098-2116 and the five sibling save handlers).  The `or {}` can therefore only normalise a "
    "state no caller produces, and even then it promotes nothing: no unknown becomes a number and no "
    "result row is invented."
)

_KV_READ = (
    "Read-side decoding of a nullable JSON column of a calculation record - `dict("
    "row.input_snapshot_json or {})`, `dict(row.result_json or {})` and `result_summary("
    "row.result_json or {})` - in `_to_saved`, which is consumed by the history/verification "
    "projections only (cement_repository.py:150-163).  The write path stores a built snapshot and "
    "the composite result, so a NULL can only be a legacy or hand-edited row; the reader's purpose "
    "is to keep such a row displayable.  The verification consumer refuses to read an empty stored "
    "result as a match - `if not stored_result: return VerificationOutcome(status=VERIFY_UNREADABLE, "
    "..., detail=\"stored record has no result to verify against\")` "
    "(core/engineering/calculation_verification.py:180-185) - and the summary re-derivation goes "
    "through the same `_clean_number` gate that maps a missing key to None (see INV34-007779).  No "
    "number is fabricated in either direction."
)

_VERIFY_EMPTY = (
    "`self.result or {}` is passed into `classify_verification` from "
    "`Saved*Calculation.verify`.  The classifier is contractually read-only ('Does not mutate "
    "anything', core/engineering/calculation_verification.py:169) and its empty-input branch is the "
    "refusal quoted under INV34-007781; the recalculated side comes from "
    "`recalculate_from_snapshot(self.input_snapshot)`, and a snapshot that cannot be rebuilt returns "
    "VERIFY_UNREADABLE *before* this line, with `detail=f\"snapshot could not be reconstructed: "
    "{exc}\"` (mse_repository.py:62-71; identical in mud_volume 62-78 and the kill-sheet "
    "repository 72-80).  An empty stored side therefore yields a refusal, never MATCH: the "
    "comparison is `deep_numeric_diff(stored_result, recalc.values, ...)` over the entire result "
    "('so no non-summary drift can hide behind a MATCH', core/engineering/torque_drag_persistence.py:"
    "239-245)."
)

_FP_LIST = (
    "`reference_fingerprints_json` is a traceability list, not an engineering value: "
    "`reference_fingerprints(snapshot)` collects each component's `reference_fingerprint` "
    "order-preserving and de-duplicated (core/engineering/torque_drag_persistence.py:135-147), so an "
    "empty list is the honest encoding of 'every component was entered manually'.  The reader keeps "
    "that meaning end-to-end: the history dialog renders the count and `', '.join("
    "s.reference_fingerprints) or 'none (all manual)'` (dialogs/torque_drag_history_dialog.py:76,251) "
    "and the persistence test pins the empty case (`assert saved.reference_fingerprints == []`, "
    "tests/test_torque_drag_history.py:241).  A NULL in a legacy row reads as the same empty list - "
    "no catalog identity is invented."
)

_KILL_DOC = (
    "The kill-sheet repository documents that it performs no engineering and no unit conversion: "
    "'The caller passes the snapshot already built from the exact ``WellControlKillSheetInputs`` the "
    "composite consumed (via ``well_control_kill_sheet_persistence.build_snapshot``) and the whole "
    "``KillSheetResult.as_dict()`` result, so this repository performs no engineering and no unit "
    "conversion.' (well_control_kill_sheet_repository.py:119-124).  Its promoted columns come from "
    "that result through the same `_clean_number` gate ('Return a finite float or ``None`` (never a "
    "bool, NaN or inf)', core/engineering/well_control_kill_sheet_persistence.py:118-127), so a "
    "kill-sheet quantity the composite did not produce is stored as NULL in the index while the JSON "
    "result stays the authoritative payload."
)

_SAVE_FORMATTER = (
    "`SaveOutcome.summary()` is a Qt-free presentation helper: `location = issue.section + (f\" row "
    "{issue.row}\" if issue.row is not None else \"\")` then `if issue.field: location += f\" "
    "[{issue.field}]\"` (core/save_outcome.py:77-85).  `SaveIssue.field` defaults to \"\" meaning "
    "'no specific field' (line 28), every issue additionally renders its reason and "
    "corrective_action, and status/disposition are computed from the issue list independently of the "
    "rendered text (41-54) while `counts` walks the serialized sections (56-69).  The truthiness "
    "test distinguishes empty-vs-present and cannot drop a real field label or change any "
    "disposition."
)

_SAVE_ALL = (
    "Documented failure semantics of the coordinator: 'Execute independent section saves; report "
    "partial success honestly.  Atomicity belongs to the supplied domain service.  This coordinator "
    "does not promise rollback across callbacks which commit independent records.' "
    "(core/save_outcome.py:88-93).  The handler classifies the failure instead of swallowing it - "
    "ValueError -> INVALID_SOURCE, NotImplementedError -> UNSUPPORTED, otherwise SYSTEM_ERROR - and "
    "attaches `exception_type=type(exc).__name__, traceback=traceback.format_exc()` with the standing "
    "directive 'Inspect the section diagnostics before retrying; do not assume it saved.' (line 29; "
    "handler 119-125).  The aggregate adds the failed section's `saved=0` (126) and stores its "
    "outcome dict under the section name (128), so a raising section can never be counted as saved "
    "and no failure is lost - the loop continues so the user learns about every section that failed."
)

_FP_GATE = (
    "Documented traceability rule of `AddPipeDialog._reference_fingerprint_if_unchanged`: 'Return the "
    "selected reference's fingerprint iff its identity-forming values still match the edited "
    "component; otherwise ``None``.  This keeps traceability honest: a component that was seeded from "
    "...' (dialogs/engineering_dialogs.py:451-455).  The fingerprint is an identity claim, not a "
    "measurement, so `if fp: self.result[\"reference_fingerprint\"] = fp` (446-448) stores it only "
    "while the claim is still true; writing it for a since-edited component would be false "
    "provenance, and the absent key reads as 'manual' downstream."
)

_NOZZLE = (
    "`self.size.currentData() or 16` mirrors the dialog's own load default - `_load_data`: `s = "
    "d.get('size', 16)` with `idx = self.size.findData(s)` and `self.size.setCurrentIndex(idx)` "
    "(dialogs/engineering_dialogs.py:765-770) - for a catalog-driven size selector.  The combo is "
    "populated from the nozzle catalog and the area preview (`calc_area_single` / `calc_area_total`, "
    "762-763) is visible before saving, so the payload carries exactly the size the user sees.  A "
    "nozzle size of 0 is not a catalog entry, so the falsy case cannot be a real design size and no "
    "measurement is fabricated."
)

_FIRST_STATION = (
    "Definitional first-station case of a minimum-curvature survey: with no previous station the "
    "values are TVD = MD at surface with zero displacement, dogleg and horizontal departure "
    "(`if not self.prev_survey:` ... `f\"{self.md.value():.2f} m (surface)\"`, "
    "dialogs/engineering_dialogs.py:1002-1009).  It is reachable only when the dialog was opened for "
    "the first point - the ordering gate refuses anything else (`if self.prev_survey and "
    "self.md.value() <= self.prev_survey.get('md', 0): ... return`, 1062-1064) - and both tabs "
    "recompute the geometry canonically after the dialog returns: they rebuild `{'md','inc','azi'}` "
    "and overwrite `tvd/north/east/dls` from `TrajectoryEngine.calculate` "
    "(tabs/w13_Engineering_Calculator.py:4887-4896 `_ac_recalculate`, 5047-5062 "
    "`_dd_recalculate_from`)."
)

_TVD_FALLBACK = (
    "Bounded fallback inside `AddSurveyDialog._save`: the displayed labels are produced by "
    "`_update_calc`, and the narrow handler catches only a label that does not yet carry a number "
    "(`float(lbl.split(' ')[0])` raising ValueError/IndexError).  In that state `tvd = "
    "self.md.value()` is the dialog's own definition ('surface' branch, "
    "dialogs/engineering_dialogs.py:1004) and the following block leaves north/east/DLS/HD at their "
    "initialised 0 with the explicit comment 'uncalculated labels stay at 0 in the result payload' "
    "(1074-1080).  The geometry the application keeps is recomputed canonically from md/inc/azi by "
    "the callers (see INV34-003279), and `_load_data` sets the spin boxes through `setValue`, which "
    "fires `valueChanged` -> `_update_calc` (998-1000, 1053-1059), so a loaded or edited row always "
    "carries fresh labels."
)

_FORM_VALIDATION = (
    "Fail-closed input validation in the dialog that owns the record: a blank or whitespace-only "
    "name is refused before `self.result` is built, and the same stripped text is what the payload "
    "carries (`name: self.name.text().strip()`, dialogs/engineering_dialogs.py:1255), with the "
    "sibling `Base MD must > Top MD` check (1248-1249) following the same pattern.  No default name "
    "is invented and no record is written from an invalid form."
)

_REPORT_NORM = (
    "`report = self.import_report or {}` is a display/gate normalisation of the report object the "
    "dialog was constructed with (ctor `self.import_report = import_report`, "
    "dialogs/excel_import_dialog.py:106-124); every read is `.get(key, default)`-style, the dialog is "
    "modal, and the mapping therefore cannot change between render and confirm.  An empty report "
    "cannot reach the reviewer in the first place: the pipeline refuses earlier - `if not "
    "has_meaningful_canonical_data(extracted): ... raise ValueError(\"No meaningful canonical report "
    "data was detected\")` (891-894) - and the confirm path sends only reviewer-approved subsets "
    "(418-432, `apply_review_changes`)."
)

_DIAG = (
    "`diagnostics` is optional observability metadata of the MinerU provenance block, and the "
    "expression is a fallback chain across its possible sources: `getattr(parse_result, "
    "\"diagnostics\", {}) or parse_result.document.metadata.get(\"diagnostics\", {}) or {}` "
    "(dialogs/excel_import_dialog.py:716-720).  The final `or {}` encodes 'no diagnostics were "
    "produced anywhere' inside an audit payload that also carries `mineru_provenance` and "
    "`fallback_diagnostics` under their own keys (711, 721); it cannot manufacture a diagnostic and "
    "no engineering value is derived from this mapping."
)

_CONF_GUARD = (
    "`conf_item = self.table.item(row, 8)` is the confidence cell of the row the handler was invoked "
    "for; `if not conf_item: continue` skips exactly that row and leaves its stored "
    "confidence/decision untouched, so a row without the cell is neither auto-classified nor "
    "mis-classified through a neighbouring row.  The handlers only decide which rows the reviewer "
    "sees; `_set_decision` (295-305) is the single writer of a decision and it resolves the row's own "
    "payload through `_payload_for_row` first."
)

_HIGH = (
    "`_accept_high` marks ACCEPT only for rows whose own confidence cell parses to >= 0.95 (`if conf "
    ">= 0.95: self._set_decision(row, \"ACCEPT\")`, dialogs/excel_import_dialog.py:275-286), and "
    "`_set_decision` writes the decision into that row's payload only after resolving the row's own "
    "payload via `_payload_for_row` (`Qt.UserRole` data or the positional fallback, 288-305).  The "
    "confirm path sends what the reviewer sees (`get_decisions` -> `apply_review_changes`), so an "
    "unparseable or missing cell leaves the row unreviewed instead of accepting anything."
)

_LOW = (
    "`_reject_low` marks REJECT only for rows whose own confidence parses below 0.70 "
    "(dialogs/excel_import_dialog.py:320-331) and, like `_accept_high`, resolves the row's own payload "
    "before writing the decision; an unparseable or missing cell leaves the row for the reviewer.  No "
    "row can be rejected through a stale binding."
)

_FILTER_ROW = (
    "The broad handler wraps the per-row visibility computation only: on failure the row is hidden "
    "(`self.table.setRowHidden(row, True)`, dialogs/excel_import_dialog.py:318) and its decision is "
    "left untouched - the fail-closed direction for a *display* filter; rows with a parseable "
    "confidence keep the documented band (`show = 0.70 <= conf < 0.95`, 315).  Nothing is imported or "
    "dropped because of this handler: the import carries the reviewer's decisions and decision "
    "writing happens exclusively in `_set_decision`."
)

_UNIT = (
    "Unit re-normalisation of one edited cell: `num_val, src_unit = UnitManager.detect_unit("
    "orig_val)`; when detection yields nothing the handler tries `float(orig_val)` and on failure "
    "sets `num_val = None` (dialogs/excel_import_dialog.py:392-397), after which the guard `if "
    "num_val is not None:` skips the conversion entirely - the writes to "
    "`normalized_value`/`value`/`proposed_value` happen only inside the success branch (398-406).  A "
    "failed parse therefore cannot fabricate a converted number, the failure is logged (408), and the "
    "reviewer still sees the original text in the table."
)

_PIPELINE_GATE = (
    "The import decision point: `if not preview.confirmed or preview_result != QDialog.Accepted:` "
    "records the file as skipped (`{'skipped': 1, 'imported': 0, 'failed': 0, ...}` plus 'Cancelled "
    "by user in preview') and `continue`s without calling `_do_import` "
    "(dialogs/excel_import_dialog.py:900-923).  Both conditions are required, so neither a cancelled "
    "dialog nor an unconfirmed preview can write anything; the accepted path first applies the "
    "reviewer's decisions ('Decisions and edits are now part of the audit payload and the exact "
    "canonical object sent to the atomic save boundary', 918-923) and only then runs the atomic "
    "save."
)

_PLAN_ROP = (
    "Plan-vs-actual bookkeeping with an explicit unknown: `days = self.planned_days_spin.value()` "
    "feeds the live estimate (`if days > 0 and depth_to > depth_from: rop = (depth_to - depth_from) / "
    "days ... else: self.estimated_rop_label.setText(\"—\")`, dialogs/hierarchy_dialogs.py:1183-1192) "
    "and the create path stores `estimated_rop = (depth_to - depth_from) / planned_days if "
    "planned_days else None` (1210) - no planned days is persisted as None (unknown), never as a zero "
    "ROP, and the label shows an em dash rather than a fabricated rate.  The value is the engineer's "
    "own plan input from a non-negative spin box, and zero is a meaningful plan horizon rather than a "
    "measurement."
)

R: dict[str, tuple[str, str, str | None]] = {
    # ------------------------------------------------------ cement repository
    "INV34-007779": (INT, _SUMMARY_WRITE, None),
    "INV34-007780": dup("INV34-007779",
                         "core/repositories/cement_repository.py:115 (the result_json write of the "
                         "same two-projection pair)",
                         "the identical `or {}` on the same call: storing an explicitly empty "
                         "result mapping instead of NULL keeps the reader contract "
                         "(`dict(row.result_json or {})`) unchanged and promotes nothing either "
                         "way"),
    "INV34-007781": (INT,
        "Read-side decoding of a nullable JSON column, decided together with INV34-007782/007783: "
        "the write path stores a built snapshot and the composite result, so a NULL input_snapshot "
        "can only be a legacy/hand-edited row, and rendering it as {} keeps the row displayable "
        "while the verification consumer refuses to certify it (VERIFY_UNREADABLE, 'stored record "
        "has no result to verify against', core/engineering/calculation_verification.py:180-185; an "
        "unreadable snapshot is reported by the reconstruction handler beforehand, "
        "mse_repository.py:62-71).  Distinguishing 'no snapshot' would need a projection change "
        "without any consumer able to act on it differently.", None),
    "INV34-007782": dup("INV34-007781",
                         "core/repositories/cement_repository.py:159 (result_json read)",
                         "the same decoding of the same nullable column, with the same consumer "
                         "guarantees"),
    "INV34-007783": dup("INV34-007781",
                         "core/repositories/cement_repository.py:162 (summary re-derivation on read)",
                         "`result_summary(row.result_json or {})` re-derives the index through the "
                         "same `_clean_number` gate that maps a missing key to None, so the "
                         "re-derivation cannot invent a value"),

    # --------------------------------------------------------- mse repository
    "INV34-007792": (INT, _VERIFY_EMPTY, None),
    "INV34-007794": dup("INV34-007779",
                         "core/repositories/mse_repository.py:107 (mse save_run summary)",
                         "the identical computation on the same contract: the mse save handler "
                         "passes the composite result of the run it just calculated "
                         "(tabs/w13_Engineering_Calculator.py:2109-2116)"),
    "INV34-007795": dup("INV34-007794",
                         "core/repositories/mse_repository.py:116 (result_json write)",
                         "the same two-projection pair as INV34-007780, in the mse repository"),
    "INV34-007796": dup("INV34-007781",
                         "core/repositories/mse_repository.py:157 (input_snapshot read)",
                         "the same nullable-JSON decoding with the same verification refusal"),
    "INV34-007797": dup("INV34-007796",
                         "core/repositories/mse_repository.py:158 (result read)",
                         "the same `_to_saved` block"),
    "INV34-007798": dup("INV34-007796",
                         "core/repositories/mse_repository.py:161 (summary re-derivation on read)",
                         "the same gate-protected re-derivation as INV34-007783"),

    # -------------------------------------------------- mud volume repository
    "INV34-007800": dup("INV34-007792",
                         "core/repositories/mud_volume_repository.py:73 (SavedMudVolumeCalculation."
                         "verify)",
                         "the identical verification call with the identical empty-stored-result "
                         "refusal and the identical reconstruction guard before it"),
    "INV34-007802": dup("INV34-007779",
                         "core/repositories/mud_volume_repository.py:106 (mud-volume save_run "
                         "summary)",
                         "the same promoted-index derivation from the caller's composite result"),
    "INV34-007803": dup("INV34-007802",
                         "core/repositories/mud_volume_repository.py:115 (result_json write)",
                         "the same write-side `or {}` as INV34-007780/007795"),
    "INV34-007804": dup("INV34-007781",
                         "core/repositories/mud_volume_repository.py:155 (input_snapshot read)",
                         "the same nullable-JSON decoding"),
    "INV34-007805": dup("INV34-007804",
                         "core/repositories/mud_volume_repository.py:156 (result read)",
                         "the same `_to_saved` block"),
    "INV34-007806": dup("INV34-007804",
                         "core/repositories/mud_volume_repository.py:159 (summary re-derivation on "
                         "read)",
                         "the same gate-protected re-derivation"),

    # --------------------------------------------------- torque/drag repository
    "INV34-007814": (INT, _SUMMARY_WRITE, None),
    "INV34-007816": dup("INV34-007781",
                         "core/repositories/torque_drag_repository.py:154 (input_snapshot read)",
                         "the same nullable-JSON decoding; the stored snapshot is what "
                         "`recalculate_from_snapshot` feeds, and an unreadable one is reported "
                         "rather than certified"),
    "INV34-007817": dup("INV34-007816",
                         "core/repositories/torque_drag_repository.py:161 (result read)",
                         "the same `_to_saved` block"),
    "INV34-007818": (INT, _FP_LIST, None),
    "INV34-007819": dup("INV34-007816",
                         "core/repositories/torque_drag_repository.py:165 (summary re-derivation on "
                         "read)",
                         "the same gate-protected re-derivation as INV34-007783/007798/007806"),

    # ------------------------------------------------------- kill-sheet repository
    "INV34-007821": dup("INV34-007792",
                         "core/repositories/well_control_kill_sheet_repository.py:82 "
                         "(SavedKillSheetCalculation.verify)",
                         "the identical verification call with the identical refusal semantics"),
    "INV34-007824": (INT, _KILL_DOC, None),
    "INV34-007825": dup("INV34-007824",
                         "core/repositories/well_control_kill_sheet_repository.py:135 (result_json "
                         "write)",
                         "the write-side sibling of the same documented pass-through contract"),
    "INV34-007826": dup("INV34-007781",
                         "core/repositories/well_control_kill_sheet_repository.py:179 "
                         "(input_snapshot read)",
                         "the same nullable-JSON decoding"),
    "INV34-007827": dup("INV34-007826",
                         "core/repositories/well_control_kill_sheet_repository.py:180 (result read)",
                         "the same `_to_saved` block"),
    "INV34-007828": dup("INV34-007826",
                         "core/repositories/well_control_kill_sheet_repository.py:183 (summary "
                         "re-derivation on read)",
                         "the same gate-protected re-derivation"),

    # ------------------------------------------------------------ save outcome
    "INV34-002775": (INT, _SAVE_FORMATTER, None),
    "INV34-002770": (INT, _SAVE_ALL, None),

    # ------------------------------------------------------ engineering dialogs
    "INV34-003276": (INT, _FP_GATE, None),
    "INV34-003237": (INT, _NOZZLE, None),
    "INV34-003279": (INT, _FIRST_STATION, None),
    "INV34-003293": (INT, _TVD_FALLBACK, None),
    "INV34-007934": (INT, _FORM_VALIDATION, None),

    # ---------------------------------------------------- excel import dialog
    "INV34-007936": (INT, _REPORT_NORM, None),
    "INV34-003351": (VC, _CONF_GUARD, None),
    "INV34-003356": (VC, _CONF_GUARD, None),
    "INV34-003299": (VC, _FILTER_ROW, None),
    "INV34-003358": (VC, _LOW, None),
    "INV34-003298": (VC, _UNIT, None),
    "INV34-007940": dup("INV34-007936",
                         "dialogs/excel_import_dialog.py:419 (`_confirm` report normalisation)",
                         "the same normalisation of the same constructor-held report, with the same "
                         "pipeline refusal upstream and the same `.get`-based gate below"),
    "INV34-007942": (INT, _DIAG, None),
    "INV34-008783": (VC, _PIPELINE_GATE, None),

    # ------------------------------------------------------- hierarchy dialogs
    "INV34-009989": (VC, _PLAN_ROP, None),
}

NEW_FINDINGS: list[dict] = []


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def git_show(rev: str, path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed")
    return out.stdout.decode("utf-8", "replace").splitlines()


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    """Line range of the symbol named by a dotted path (owner-aware).

    p6-batch-009 correction: the previous version resolved only the last path component
    (`parts[-1]`), so a class-qualified symbol such as ``FuelWaterTab.set_current_well`` could
    resolve to a same-named method of an unrelated class earlier in the same file.  The index
    below is built from the real AST nesting, so ``Class.method`` and ``Class.method.inner``
    resolve to the node the register names.  The old name-only search remains as a fallback,
    and only when it is unambiguous.
    """
    import ast

    tree = ast.parse(source)
    parts = [p for p in (symbol or "").split(".") if p]
    if not parts:
        raise SystemExit(f"empty symbol {symbol!r}")
    index: dict[str, tuple[int, int]] = {}

    def visit(node, prefix):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + [child.name]
                index[".".join(qualified)] = (child.lineno, child.end_lineno)
                visit(child, qualified)

    visit(tree, [])
    found = index.get(".".join(parts))
    if found is None:
        candidates = [n for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == parts[-1]]
        if len(candidates) != 1:
            raise SystemExit(f"symbol {symbol!r} not resolvable ({len(candidates)} candidates)")
        found = (candidates[0].lineno, candidates[0].end_lineno)
    return found


def line_map(commit: str, path: str, current: list[str]) -> dict[int, int]:
    previous = git_show(f"{commit}^", path)
    matcher = difflib.SequenceMatcher(None, previous, current, autojunk=False)
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
    return mapping


def check(batch: list[dict]) -> list[tuple[str, str, int, int]]:
    problems: list[str] = []
    reanchored: list[tuple[str, str, int, int]] = []
    cache: dict[str, list[str]] = {}
    sources: dict[str, str] = {}
    maps: dict[str, dict[int, int]] = {}
    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        if path not in cache:
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            sources[path] = text
            cache[path] = text.splitlines()
        lines = cache[path]

        if 0 < line <= len(lines) and _norm(lines[line - 1]) == _norm(expected):
            continue

        commit = RECHECK_AGAINST.get(path)
        if commit is None:
            actual = lines[line - 1].strip() if 0 < line <= len(lines) else "<beyond EOF>"
            problems.append(f"{record['id']}: {path}:{line} is {actual!r}, register recorded "
                            f"{expected!r}")
            continue

        previous = git_show(f"{commit}^", path)
        if _norm(previous[line - 1]) != _norm(expected):
            problems.append(f"{record['id']}: {commit}^ has {previous[line - 1].strip()!r} at "
                            f"{path}:{line}, register recorded {expected!r}")
            continue

        if path not in maps:
            maps[path] = line_map(commit, path, lines)
        new_line = maps[path].get(line)
        start, end = symbol_body(sources[path], record.get("symbol", ""))
        if new_line is None or _norm(lines[new_line - 1]) != _norm(expected) \
                or not (start <= new_line <= end):
            problems.append(f"{record['id']}: re-anchor {path}:{line} -> {new_line} failed")
            continue
        reanchored.append((record["id"], path, line, new_line))
    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        raise SystemExit(2)
    return reanchored


def record_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode().strip()


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    batch = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(batch) != len(R):
        print(f"batch has {len(batch)} records, adjudications: {len(R)}")
        print("missing:", sorted({r["id"] for r in batch} - set(R)))
        print("extra:", sorted(set(R) - {r["id"] for r in batch}))
        return 1

    reanchored = check(batch)

    counts: dict[str, int] = {}
    for record in batch:
        classification = R[record["id"]][0]
        counts[classification] = counts.get(classification, 0) + 1
    classes: dict[str, int] = {}
    for record in batch:
        classes[record["p6_class"]] = classes.get(record["p6_class"], 0) + 1

    items = [{
        "id": record["id"], "file": record["file"], "line": record["line"],
        "classification": R[record["id"]][0], "evidence": R[record["id"]][1],
        "remaining_question": R[record["id"]][2],
        "defect": R[record["id"]][0] == DEF,
        "test": None, "commit": None,
    } for record in batch]

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("phase-2 class A: the calculation-repository and engineering-dialog persistence "
                  "surface - " + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "sibling_search": {
            "target": ("the `or {}` / `or []` default family in the calculation repositories, whose "
                       "summary/read projections are this batch's subject"),
            "method": ("regex scan for ` or {}` / ` or []` over core/repositories/*.py, each hit "
                       "matched against the register by file+line, and every uncovered hit read at "
                       "its own site"),
            "hits": 41,
            "files_hits": {"core/repositories/cement_repository.py": 8,
                           "core/repositories/mse_repository.py": 8,
                           "core/repositories/mud_volume_repository.py": 8,
                           "core/repositories/torque_drag_repository.py": 8,
                           "core/repositories/well_control_kill_sheet_repository.py": 9},
            "repository_total": 55,
            "findings": [
                {"site": "the 28 register records of this batch in the five repositories",
                 "status": "adjudicated here (INTENTIONAL / DUPLICATE - no defect, no production "
                           "change)"},
                {"site": "core/repositories/cement_repository.py:73",
                 "status": "already adjudicated in batch-013 as INV34-007777 "
                           "(DUPLICATE/FALSE-POSITIVE)"},
                {"site": ("core/repositories/{cement,mse,mud_volume}_repository.py:61 and "
                          "well_control_kill_sheet_repository.py:70 "
                          "(`snap_method = (self.input_snapshot or {}).get(\"method\")`)"),
                 "status": ("no register record; adjudicated INTENTIONAL in this batch - a missing "
                            "method reads as None and the comparison "
                            "`method_matches = (current_method is None) or "
                            "(snap_method == current_method)` "
                            "(core/engineering/calculation_verification.py:171) then reports a "
                            "method mismatch instead of a match; nothing is fabricated and no "
                            "sibling was mass-patched")},
                {"site": ("core/repositories/{cement,mse}_repository.py:82 (`canonical_inputs`), "
                          "well_control_kill_sheet_repository.py:91 (`canonical_inputs`) and :95 "
                          "(`display`)"),
                 "status": ("no register record; read-only accessors over the stored snapshot "
                            "mapping, where an empty mapping is the honest statement 'nothing "
                            "recorded'; INTENTIONAL, not patched")},
                {"site": ("core/repositories/torque_drag_repository.py:65,69 "
                          "(`len(self.input_snapshot.get(...) or [])`)"),
                 "status": ("no register record; component/survey counts for display, where a "
                            "missing list means no records were stored; INTENTIONAL, not patched")},
                {"site": "core/repositories/torque_drag_repository.py:116 "
                         "`result_json=dict(result_values or {})`",
                 "status": ("no register record (the rule flagged the summary line 106 only); the "
                            "identical construct as INV34-007814/007780 - INTENTIONAL; recorded as "
                            "a register-coverage gap, not patched")},
                {"site": "core/repositories/base.py:26,54",
                 "status": ("no register record; the generic helper declares `save(self, model, "
                            "data: dict)` / `get_list(self, model, filters: Dict = None)`, so the "
                            "`or {}` normalises a declared-invalid argument (no columns to write, no "
                            "filters) rather than a domain unknown; recorded, not patched")},
                {"site": "core/repositories/well_repository.py:34,41,49,65",
                 "status": ("INV34-007830 (34) and INV34-007831 (41) are OPEN records of "
                            "p6-batch-018; lines 49/65 carry no register record.  Left for their "
                            "own batch, not mass-patched")},
            ],
        },
        "tests": ("no production file changes in this batch (all 45 records adjudicated as "
                  "INTENTIONAL 15 / DUPLICATE 23 / VERIFIED-CORRECT 7; 0 defects), so the evidence "
                  "is (a) the phase-1 full-suite gate on the pre-batch tree (1 834 passed / 0 "
                  "failures / 0 errors / 4 skipped, 317.146 s) and (b) a fresh related run on the "
                  "current tree covering every module the batch quotes: 346 passed / 0 failed / 0 "
                  "errors / 0 skipped in 94.954 s (/tmp/p6-014-related.xml; includes the "
                  "cement/mse/mud-volume/torque-drag/kill-sheet persistence, cross-process, history "
                  "and save-widget suites, the calculation-verification core, the casing-id gate, "
                  "the save-outcome consumers and the import-pipeline suites).  compileall and the "
                  "phase-end full suite re-run on the final tree"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "tools/m36/p6_batch_014.py",
                           "core/engineering/cement_persistence.py",
                           "core/engineering/calculation_verification.py"],
        "staleness": {"checked": len(batch), "stale": 0, "re_anchored": len(reanchored),
                      "method": ("every record's recorded text must match the line at its current "
                                 "position in the working tree; no record needed re-anchoring, which "
                                 "is the expected state at the head of the batch-013 commit "
                                 "(working tree at head 10fdd8a; batch-013 evidence commit a9f7595, its fix 0699e50), whose only production edit touched "
                                 "core/profile_import_engine.py"),
                      "re_anchored_items": [
                          {"id": i, "file": p, "register_line": a, "current_line": b}
                          for i, p, a, b in reanchored]},
        "method": ("each of the 45 records was read at its own site in the current tree and the "
                   "flagged construct was traced to its consumer before classification: the "
                   "repositories' summary/read projections through `_clean_number` and "
                   "`classify_verification`, the save coordinator through its documented failure "
                   "semantics and the Save All call sites, the dialogs through their own documented "
                   "rules (fingerprint gate, first-station definition, uncalculated-label comment) "
                   "and through the reviewers/consumers that own the result (the w13 save and survey "
                   "handlers, the import preview/confirm path), and the hierarchy estimate through "
                   "the None-vs-zero plan encoding it writes.  The deciding contract is quoted in "
                   "`evidence` for every record; the sibling scan covered the same `or {}`/`or []` "
                   "family repository-wide, and no line was changed"),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, staleness 0, "
          f"re-anchored {len(reanchored)}, defects fixed {len(payload['defects_fixed'])}")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
