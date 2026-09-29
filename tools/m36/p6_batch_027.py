#!/usr/bin/env python3
"""Evidence-backed P6 adjudication for batch 027."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-027"
VC, INT, DUP, DDD, DEF = (
    "VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
    "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT",
)
sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

SOURCE_TREES = {
    "dialogs/planning_dialog.py": "fd18a2bca5b849356c50f9da19c278ecdd8f9967",
}
CLASSIFICATION = {
    "INV34-003455": INT, "INV34-003460": INT, "INV34-003461": INT,
    "INV34-003491": INT, "INV34-003502": INT, "INV34-003565": INT,
    "INV34-003572": INT, "INV34-003581": VC, "INV34-003584": INT,
    "INV34-003603": INT, "INV34-003642": INT, "INV34-003751": INT,
    "INV34-003801": INT, "INV34-003844": INT, "INV34-003855": INT,
    "INV34-003880": INT, "INV34-003971": INT, "INV34-003992": INT,
    "INV34-003994": INT, "INV34-004047": INT, "INV34-004316": DDD,
    "INV34-004317": DDD, "INV34-007975": INT, "INV34-007990": INT,
    "INV34-007991": INT, "INV34-008011": INT, "INV34-008012": INT,
    "INV34-008017": INT, "INV34-008019": INT, "INV34-008021": INT,
    "INV34-008027": INT, "INV34-008031": INT, "INV34-008043": DDD,
    "INV34-008056": INT, "INV34-008057": INT, "INV34-008058": INT,
    "INV34-008059": INT, "INV34-008060": INT, "INV34-008061": INT,
    "INV34-008062": INT, "INV34-008070": INT, "INV34-008071": INT,
    "INV34-008084": INT, "INV34-008803": INT, "INV34-008804": INT,
}
NOTES = {
    "INV34-003455": "DatabaseManager.save_daily_report returns None on failure or a populated result mapping on success (core/database.py:4227-4296); the dialog's falsey gate prevents acceptance of a failed save, and report IDs are positive database identities rather than zero-valued measurements.",
    "INV34-003460": "The query returns an ORM DailyReport row or None. A row object is truthy independently of report_number; no prior row selects the documented first report number 1.",
    "INV34-003461": "The section query returns an ORM Section object or None; the branch only controls optional display of section/well/project labels and does not decide persisted scope.",
    "INV34-003491": "The Engineering Calculator entry point checks for a missing MSE history repository and warns before constructing the dialog. The None-to-empty guard is defensive for direct/test construction; repository query exceptions are displayed by the dialog's explicit error path.",
    "INV34-003502": "The Engineering Calculator entry point checks for a missing mud-volume history repository and warns before constructing the dialog. The None-to-empty guard is defensive; query exceptions are surfaced instead of described as zero stock.",
    "INV34-003565": "Exact recorded source hash/line/symbol/fingerprint belongs to dialogs/planning_dialog.py in tree fd18a2bca5b849356c50f9da19c278ecdd8f9967; current site is line 1053 after later source edits. IADC phase mapping takes optional textual codes; blank means no phase mapping and nonblank codes are normalized against explicit aliases. It is not a numeric depth or activity count.",
    "INV34-003572": "The selected report-revision snapshot is displayed as JSON when serializable; if an unusual object cannot be JSON encoded, the UI displays its string representation. This fallback affects debug display only; the structured revision tree is populated from the snapshot first.",
    "INV34-003581": "The selected row is checked against the actual revisions list bounds before indexing; row -1 or a stale/out-of-range selection is ignored, so no unrelated revision is shown.",
    "INV34-003584": "This is only the first human-readable summary candidate, not data filtering. Numeric zero in a field such as MD may be omitted from the one-line summary, but the same revision tree iterates every non-None/nonblank field and renders explicit `0`; the raw snapshot remains available as secondary detail.",
    "INV34-003603": "Learning corrections are optional advisory import metadata. A missing or unreadable/corrupt learning file leaves the current correction set empty; field extraction still proceeds through the explicit mapping/review pipeline and the catch does not manufacture an engineering value.",
    "INV34-003642": "Every worksheet is populated into SheetRouter.sheet_scores with all known section keys before this lookup. The `0` is a defensive score for an absent key; the > -5 threshold is a candidate-sheet inclusion heuristic, not a measurement default or automatic persistence decision.",
    "INV34-003751": "An empty workbook worksheet collection suppresses preview and auto-detection; the surrounding load path raises a visible error for an unusable workbook rather than creating a data row.",
    "INV34-003801": "Malformed optional main-code text leaves `main_num` empty; the resolver then continues with sub-code/direct aliases and otherwise returns no resolved label. It does not coerce invalid activity data to code zero.",
    "INV34-003844": "The Engineering Calculator entry point verifies the Torque & Drag history repository exists before dialog construction; direct None construction safely yields no rows, while repository errors have an explicit error banner.",
    "INV34-003855": "The Engineering Calculator entry point verifies the kill-sheet history repository exists before dialog construction; direct None construction safely yields no rows, while repository errors have an explicit error banner.",
    "INV34-003880": "A wellbore lookup failure leaves the already-resolved `wellbore_id` intact and only makes the optional `wellbore_data` mapping unknown. `select_full_context` receives that ID separately, so this fallback does not collapse a known wellbore to Whole-Well scope; outer refresh failures are logged and trigger full refresh.",
    "INV34-003971": "The backup path is an optional return value: only a nonempty path is logged as a successful backup. DatabaseManager.auto_backup owns creation and returns no path when no backup was produced; failures are separately logged.",
    "INV34-003992": "The Help menu's About action has no shortcut; only nonblank shortcut strings are installed on actions. The optional UI accelerator does not gate action creation or execution.",
    "INV34-003994": "QMainWindow.menuBar() returns the existing menu-bar widget; the branch is an existence guard before visibility/update operations, not an ID or measurement truthiness test.",
    "INV34-004047": "The package structure check is always performed; `--run` is an explicit opt-in to execute the packaged Windows binary smoke command, avoiding accidental process execution during static package inspection.",
    "INV34-004316": "The Qt canvas import falls back to FigureCanvasAgg, but chart consumers later pass FigureCanvas into Qt layout.addWidget. In that dependency configuration Agg is not a QWidget, and chart renderers catch the resulting exception and show a Chart error label. Decide whether chart-less fallback is supported and should render an image/disable charts; no backend/device-specific UI rule is invented.",
    "INV34-004317": "The second ImportError fallback sets FigureCanvas=None when even Matplotlib's Agg backend cannot import; chart call sites are caught and show a chart error rather than persisting bad data. It shares the chart-availability policy question recorded at INV34-004316; no independent measurement or scope defect.",
    "INV34-007975": "Report-copy editing is gated by report_lifecycle.is_editable(target.status); locked workflow states are refused before any child data is copied.",
    "INV34-007990": "LearningManager first checks the user learning file and then a packaged legacy learning file; if neither exists, the optional correction map remains empty and standard extraction continues.",
    "INV34-007991": "The optional preload template is a mapping; None and an empty mapping both mean no preload assignments. It does not convert a template measurement to zero; the importer still requires explicit detection/review.",
    "INV34-008011": "A missing user-template directory selects the packaged templates directory; this is a source-selection fallback, not a drilling-data default.",
    "INV34-008012": "The chosen user or packaged templates directory is verified to exist before opening the file picker; nonexistent paths return without reading or creating a template.",
    "INV34-008017": "QDialog.exec() uses Accepted as nonzero and Rejected/cancel as zero; cancellation stops hierarchy creation before creating a project, well, or report.",
    "INV34-008019": "QDialog.exec() acceptance is required before well creation; a rejected project dialog stops the sequence and creates no descendant.",
    "INV34-008021": "QDialog.exec() acceptance is required before final hierarchy completion; rejecting well creation leaves no new well/report attached.",
    "INV34-008027": "History snapshot is optional serialized result content; absent/empty snapshot maps to an empty display mapping. The immutable saved run identity and stored inputs remain separate and are shown elsewhere in the dialog.",
    "INV34-008031": "Saved result JSON is optional presentation content; absent/empty result maps to an empty detail view. The dialog does not change or recalculate the stored engineering result.",
    "INV34-008043": "The hierarchy worker is a live MainWindow background reader. If the joined load is still running after 3 seconds, the UI calls QThread.terminate(), which can kill execution before `get_full_hierarchy`'s `finally: session.close()` runs. The worker is read-only, but connection cleanup/thread safety and shutdown policy need an explicit fix/design; this is not a truthy domain value. No patch is made without a cooperative cancellation/lifecycle regression.",
    "INV34-008056": "Tree item carries a positive well ID independently of the returned metadata mapping. DatabaseManager.get_well_by_id returns None on missing/error; the empty mapping only avoids attribute errors, while SelectionManager retains the well ID and downstream tabs query by ID.",
    "INV34-008057": "Same optional well-metadata mapping for a wellbore tree item. Wellbore identity is read from the hierarchy payload and selected separately; a missing well display mapping does not become an empty wellbore ID.",
    "INV34-008058": "Same optional well-metadata fallback for a section tree item; persisted section identity and wellbore ownership are selected independently of the display mapping.",
    "INV34-008059": "Same optional well-metadata fallback for a daily-report tree item; report/section/wellbore IDs come from the tree payload, not from the optional dictionary returned here.",
    "INV34-008060": "Same optional well-metadata fallback for a well-tab item; the selected well ID remains the payload identity and no engineering number is defaulted.",
    "INV34-008061": "Same optional well-metadata fallback for a section-tab item; section and well IDs remain separate identity fields.",
    "INV34-008062": "The Section Data entry helper keeps well_id/section_id identities even if optional well labels are unavailable; saved report scope is not synthesized from this mapping.",
    "INV34-008070": "Targeted refresh uses an explicit well ID and expects the persisted well object only for display/section context; a missing lookup does not change the supplied well ID. Outer failures are logged and fall back to the normal refresh path.",
    "INV34-008071": "The persisted report lookup returns a row mapping or None; a query exception propagates to the outer refresh error handler. In the None case, the refresh retains explicit report_id and falls back to the selected section's persisted wellbore_id when available; all active tabs are then reloaded by explicit IDs. The empty mapping is not a zero-valued report result.",
    "INV34-008084": "Lookahead records are report-scoped: without a database or explicit current_report_id the widget does not issue a query. ID zero is not a valid persisted report identity; this does not reuse a globally selected report by accident.",
    "INV34-008803": "Router scores are computed for every loaded worksheet and every supported section; the 0 default is defensive for a missing score map. The filter only selects sheets for a reviewable detector and does not auto-persist candidates.",
    "INV34-008804": "The field detector result is accepted unless the explicit rejection predicate returns true; this is a boolean policy test on a candidate, not a truthiness check on the candidate's numeric value (tuple result remains truthy even when value is 0).",
}


def main() -> int:
    provenance.RECHECK_AGAINST.update(SOURCE_TREES)
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    records = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(records) != 45 or {r["id"] for r in records} != set(CLASSIFICATION):
        raise SystemExit(f"batch/classification mismatch: {len(records)} records")
    if set(CLASSIFICATION) != set(NOTES):
        raise SystemExit("classification/note ids do not match")
    reanchored, stats = provenance.check(records)
    counts = dict(Counter(CLASSIFICATION.values()))
    moved_map = {item[0]: item for item in reanchored}
    items = []
    for record in records:
        ident = record["id"]
        item = {
            "id": ident, "file": record["file"], "line": record["line"],
            "symbol": record.get("symbol"), "rule": record.get("rule"), "kind": record.get("kind"),
            "register_line_text": record.get("current_source_line"),
            "classification": CLASSIFICATION[ident],
            "evidence": (
                f"Hash-anchored source {record['file']}:{record['line']} `"
                f"{record['current_source_line'].strip()}`; source_sha256={record['source_sha256']}; "
                f"context_fingerprint={record['context_fingerprint']}. {NOTES[ident]}"
            ),
            "defect": CLASSIFICATION[ident] == DEF,
            "remaining_question": (
                "Whether the MainWindow hierarchy worker should use cooperative cancellation or remain alive until its read completes, instead of forced QThread termination"
                if ident == "INV34-008043" else
                "Whether Matplotlib Qt-backend absence is a supported chart-less mode and how charts should render/disable the Agg fallback"
                if ident in {"INV34-004316", "INV34-004317"} else None
            ),
            "site": {"file": record["file"], "line": record["line"],
                     "symbol": record.get("symbol"), "expression": record.get("current_source_line"),
                     "source_sha256": record["source_sha256"],
                     "context_fingerprint": record["context_fingerprint"]},
        }
        if ident in moved_map:
            _, path, old, new, tree = moved_map[ident]
            item["current_site"] = f"{path}:{new}"
            item["current_source_line"] = (ROOT / path).read_text(encoding="utf-8").splitlines()[new - 1].strip()
        items.append(item)
    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": "phase-2 class E/F mixed review: hierarchy dialogs, revision/history views, workbook templates, MainWindow selection/refresh, package smoke and planning tabs",
        "records": len(items), "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": dict(Counter(r["file"] for r in records)),
        "by_classification": counts,
        "defects_fixed": [],
        "new_findings": [
            {"id": "NEW-P6-025", "line": 1195, "severity": "MEDIUM", "status": "DOMAIN_DECISION_REQUIRED", "file": "main_window.py", "site": "MainWindow._stop_hierarchy_worker timeout path",
             "summary": "A slow hierarchy read is forcibly terminated after a 3-second wait. QThread.terminate can bypass normal cleanup, including get_full_hierarchy's SQLAlchemy session close. Define a cooperative cancellation/worker lifecycle and add a regression before replacing the timeout behavior.",
             "evidence": "main_window.py:65-85, 1186-1203; core/database.py:3656-3760. The worker calls a synchronous read and closes the session in finally; caller may terminate the thread after timeout."},
            {"id": "NEW-P6-026", "line": 45, "severity": "LOW", "status": "DOMAIN_DECISION_REQUIRED", "file": "tabs/w10_Planning_Widget.py", "site": "Matplotlib Qt canvas import fallback",
             "summary": "The Qt canvas import falls back to FigureCanvasAgg, but chart consumers insert the canvas into Qt layouts (and the later fallback can set the canvas to None). Define whether this mode should disable charts or provide a QWidget-backed image adapter; current render handlers show per-chart errors and preserve the rest of the tab.",
             "evidence": "tabs/w10_Planning_Widget.py:42-51, 641-661; core/common_widgets.py:403-424. GUI runtime confirmation is blocked locally by missing libGL.so.1."}
        ],
        "observations": [
            {"topic": "history and revision views", "summary": "History entry points check their repository and display a warning before opening dialogs when no database is available; repository failures have an explicit error UI. Revision details bounds-check the selected row, serialize snapshots with a string fallback, and include all non-NULL/nonblank fields in detail even where the short summary prefers truthy labels."},
            {"topic": "hierarchy and scope", "summary": "Creation/approval dialogs stop on QDialog rejection. Tree selections retain explicit IDs independently of optional display mappings. Targeted refresh carries known wellbore ID separately from its optional mapping, and report-scoped lookahead requires its explicit report ID."},
            {"topic": "smart template import", "summary": "Router scores are computed per worksheet/section; candidates pass through field detection, explicit rejection filters, reviewable assignments and shared save boundaries. Optional learning/template files are not numeric inputs."}
        ],
        "sibling_search": [
            {"family": "history repository availability", "result": "MSE, mud-volume, torque-drag and kill-sheet history launchers all refuse to open without a repository and show a warning; repository exceptions are surfaced by dialogs. The constructor's optional-repo guard is defensive rather than a production 'no records' result."},
            {"family": "well and report tree identities", "result": "MainWindow tree payloads carry well/section/report/wellbore IDs independently of `get_well_by_id(...) or {}` display mappings. Targeted refresh retains the resolved wellbore ID if its optional object mapping cannot be loaded. No ID is inferred from a display name and no report ID is substituted for cumulative scope."},
            {"family": "history summary unknown-versus-zero", "result": "The revision child tree retains `0` because it filters only None/empty string; only its short summary may omit a zero candidate, while raw snapshot and structured details remain available."},
            {"family": "missing source fingerprint ledger", "result": "All source hashes/recorded sites are anchored; the unavailable M34 pattern ledger leaves INV34-004316 and INV34-004317 as the only non-reproducing context fingerprints in this batch. No pattern is invented."}
        ],
        "tests": {
            "passed": [
                "70 passed: tests/test_hierarchy_updated_at.py tests/test_multi_company_template.py tests/test_torque_drag_history.py tests/test_torque_drag_persistence.py tests/test_well_control_kill_sheet.py tests/test_well_control_kill_sheet_persistence.py tests/test_kill_sheet_casing_id_gate.py."
            ],
            "environment_blocked": [
                "Qt dependency limitation: 3 history-viewmodel test modules failed collection, 2 history projection tests failed, and 11 dialog/Planning UI smoke tests failed before assertions because PySide6 cannot load missing libGL.so.1. The blocked tests were: tests/test_mse_history_viewmodel.py, tests/test_mud_volume_history_viewmodel.py, tests/test_well_control_kill_sheet_history_viewmodel.py; tests/test_torque_drag_history.py::test_history_rows_projection_and_ordering and ::test_history_rows_empty_when_no_runs; tests/test_report_history_ui.py (4), tests/test_m29_planning_ui.py (1), tests/test_planning_context_isolation.py (1), tests/test_planning_material_persistence.py (1), tests/test_planning_table_presentation.py (1), tests/test_torque_drag_history_widget_smoke.py (1), tests/test_torque_drag_save_widget_smoke.py (1), tests/test_well_control_kill_sheet_save_widget_smoke.py (1). No packaged Windows executable was built or run."
            ],
            "mutation": "No production code was changed in this batch; no mutation validation applies."
        },
        "head": "d07fba898a89cd8713a769ae1a66bcb82fbd6982", "commit": None, "evidence_commit": None,
        "evidence_files": ["tools/m36/p6_batch_027.py", "docs/audits/m36-evidence/p6-batch-027.json"],
        "staleness": {
            "checked": len(records), "stale": len(reanchored), "re_anchored": len(reanchored),
            "method": "Recorded SHA-256 file blobs, source lines, enclosing symbols and current expression mappings verified; dialogs/planning_dialog.py is anchored to fd18a2bca5b849356c50f9da19c278ecdd8f9967 and the changed IADC line re-anchored. The M34 item ledger is absent, so two context fingerprints remain explicitly non-reproduced while their source hash/line/symbol anchors verify.",
            "re_anchored_items": [
                {"id": ident, "file": path, "previous_site": f"{path}:{old}", "current_site": f"{path}:{new}", "tree": tree,
                 "source_sha256": next(r["source_sha256"] for r in records if r["id"] == ident),
                 "context_fingerprint": next(r["context_fingerprint"] for r in records if r["id"] == ident),
                 "reason": "Original tree blob/hash, recorded line and enclosing symbol were verified; current expression mapped within the same method."}
                for ident, path, old, new, tree in reanchored
            ],
            "provenance_trees": stats["trees"],
            "m34_fingerprint_ledger": {
                "manifest": "docs/audits/m34-evidence/M34_INVENTORY_LEDGER.json",
                "expected_path": "docs/audits/m34-evidence/m34-ledger.json",
                "expected_sha256": "d81a77bda0330c75493f4081c4a02e4d106fe7602e49c14f0c67d12977658a6b",
                "expected_bytes": 11394989, "present_in_workspace": False,
                "effect": "Two original context patterns could not be reproduced. Their source files matched recorded hashes, so line/symbol scope is still anchored and the uncertainty is listed separately."
            },
            "fingerprint_proof": {
                "checked": stats["fingerprints_checked"], "verified": stats["fingerprints_verified"],
                "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"],
                "records_without_a_reproducing_fingerprint_but_hash_anchored": stats["fingerprints_not_reproduced_but_hash_anchored"],
                "symbol_forms_that_reproduced": stats["fingerprints_by_form"],
                "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"],
                "method": stats["ledger_mode"]
            }
        },
        "method": "Trace producers through dialog/workflow callers, selection and scope consumers, optional file/backend boundaries and tests; keep unknown data distinct from zero; do not infer production reachability from a standalone helper; preserve owner decisions where failure/timeout behavior needs product policy.",
        "items": items
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={counts}; reanchors={len(reanchored)} fingerprints={stats['fingerprints_verified']}/{len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
