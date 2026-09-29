#!/usr/bin/env python3
"""Evidence-backed P6 adjudication for batch 028."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-028"
VC, INT, DUP, DDD, DEF = (
    "VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
    "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT",
)
sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

SOURCE_TREES = {
    "tabs/w7_logistics_Widget.py": "fd18a2bca5b849356c50f9da19c278ecdd8f9967",
}
SPECIAL = {
    "INV34-006210": (
        "tabs/w7_logistics_Widget.py", "FuelWaterTab.calculate_bulk_totals",
        "totals = summarize_bulk_display_rows(display_rows)",
    ),
}
CLASSIFICATION = {
    "INV34-004287": INT, "INV34-004290": INT, "INV34-004293": INT,
    "INV34-004318": VC, "INV34-004319": VC, "INV34-004525": INT,
    "INV34-004589": DDD, "INV34-004591": DDD,
    "INV34-004994": INT, "INV34-005006": INT, "INV34-005007": INT,
    "INV34-005016": INT, "INV34-005022": INT, "INV34-005028": INT,
    "INV34-005049": INT, "INV34-005069": INT, "INV34-005104": INT,
    "INV34-005180": INT, "INV34-005792": INT, "INV34-005829": INT,
    "INV34-005830": INT, "INV34-005967": INT, "INV34-005989": INT,
    "INV34-006134": INT, "INV34-006171": INT, "INV34-006173": INT,
    "INV34-006176": INT, "INV34-006210": DEF,
    "INV34-008094": INT, "INV34-008095": INT, "INV34-008102": INT,
    "INV34-008103": INT, "INV34-008106": INT,
    "INV34-008143": VC, "INV34-008144": VC,
    "INV34-008243": INT, "INV34-008375": INT, "INV34-008376": INT,
    "INV34-008377": INT, "INV34-008396": DUP, "INV34-008413": INT,
    "INV34-008420": INT, "INV34-008427": INT, "INV34-008431": DUP,
    "INV34-008441": INT,
}
NOTES = {
    "INV34-004287": "The selected well ID is the combo-box identity; lookup data is optional display context. A missing record maps to an empty presentation mapping without substituting a different well ID.",
    "INV34-004290": "Well-list population is conditional on an available database object; without a repository the widget does not query or fabricate a well list.",
    "INV34-004293": "The target chart widget is optional; the function checks it before modifying or replacing its layout.",
    "INV34-004318": "Bit-record depth and ROP parsing skips only malformed/non-numeric rows. The accepted values are separately required to be finite and nonnegative; explicit numeric zero remains a valid value.",
    "INV34-004319": "Alias parsing advances to the next named field on a type/value conversion failure and yields None only when no valid finite alias exists. It does not assign zero for missing input.",
    "INV34-004525": "Trend text is optional presentation metadata. A missing trend sets the card's trend_label attribute to None without changing its numeric KPI value.",
    "INV34-004589": "This is the second optional Matplotlib fallback branch in W12 Analysis. The UI canvas may be Agg/None while consumers pass it to Qt layouts; chart errors are caught and logged. It is the same unresolved chart-availability policy as NEW-P6-026 from batch 027, not a new independent engineering defect.",
    "INV34-004591": "Optional Qt canvas import failure selects the Agg fallback; W12 passes the resulting canvas to Qt layout consumers (see _draw_milestones_chart). The chart-availability question is already recorded as NEW-P6-026 in batch 027; no chart or measurement value is persisted by this fallback.",
    "INV34-004994": "Checklist cell-widget lookup may return None for a removed/malformed row; skipping a missing checkbox prevents a crash and never marks the missing item complete.",
    "INV34-005006": "Preview reads completion state only when a checkbox exists; a missing checkbox is represented as unchecked, which is the safe non-complete state.",
    "INV34-005007": "Step completion defaults to false when the optional checkbox widget is absent; missing UI state cannot report an operation as done.",
    "INV34-005016": "The optional N/A checkbox is false when no widget is present; the rendered preview does not claim a missing item was assessed as N/A.",
    "INV34-005022": "A missing step-number cell uses the deterministic display row ordinal; persisted procedure content and actual checklist completion are unchanged.",
    "INV34-005028": "The uncheck-all command safely skips rows without a checkbox; it does not infer a checked or completed value.",
    "INV34-005049": "Procedure-template loading is guarded by the optional database dependency; without it, the dialog remains open with no templates and performs no persistence.",
    "INV34-005069": "The selected reference-table item may not exist; the detail action returns no optional provenance pointer rather than selecting another row.",
    "INV34-005104": "Malformed well date text is caught at the UI parse boundary. Untouched source values are retained by form edit tracking on save, while a parseable user edit is explicit; the display fallback does not itself persist a current date.",
    "INV34-005180": "`ui.utils` is an optional styling/message helper. The local fallback constructs ordinary Qt controls and explicit success/error message boxes; it does not suppress a database or validation failure.",
    "INV34-005792": "The read-only parameter is an explicit editor mode. It chooses `NoEditTriggers` when true and interactive triggers when false; table content and values are unchanged.",
    "INV34-005829": "Pandas is optional for the downhole UI; absence is recorded in `PANDAS_AVAILABLE` and the widget can use its native table path without coercing equipment values.",
    "INV34-005830": "The shared optional_date parser raises ValueError for malformed dates; the service checker moves that equipment row to `service_review` rather than calling it current or overdue.",
    "INV34-005967": "Trajectory well loading is conditional on a configured database manager; absent DB means no query and no synthetic well identity.",
    "INV34-005989": "Repository search found no in-repository caller of this legacy get_survey_data adapter. On a bad optional cell it retains the original text for review rather than silently converting it to 0; active SurveyDataTab persistence uses its separate nullable parser.",
    "INV34-006134": "This guard distinguishes no selected well/no database from an active query. For a real well change, the loader clears current fuel/water controls before applying returned rows; absent records reset unknown stock and zero movement under the established field contract.",
    "INV34-006171": "The personnel loader returns without querying when there is no well/database. With an active well it clears rows before loading; a database absence does not create personnel count zero or a persisted row.",
    "INV34-006173": "The transport-note loader requires an explicit well and database. Its successful empty-result branch clears the note fields and loaded ID; it does not present prior notes as a successful empty result.",
    "INV34-006176": "POB loading requires an explicit well and database; with an active well it clears the current table before repopulating. The early return does not mutate a POB count or write data.",
    "INV34-006210": "The original `except ValueError: continue` swallowed an entire bulk-material row when any stock cell displayed the explicit unknown marker `—`; it thereby omitted known received/used movements and left stock totals as partial subtotals presented as complete. The fix extracts per-column semantics: SQL/display unknown propagates to a `NOT ASSESSED` total; independent known movements still sum; blank movement means no movement (0.0), explicit zero remains zero. Verified against BulkMaterials NULL/zero model contract, DatabaseManager.calculate_bulk_totals/complete_total, and regression/mutation tests.",
    "INV34-008094": "Code-management data is report/well dependent; without a database or valid current well ID the loader returns before querying. It does not borrow a globally selected report ID to fabricate code rows.",
    "INV34-008095": "Status distribution is explicitly scoped to the current well; without an active database/well, no aggregation is requested and no zero distribution is asserted.",
    "INV34-008102": "The drilling-parameter tab clears current arrays/table/chart before this no-context guard; an absent well therefore shows no previous well's parameter data.",
    "INV34-008103": "An absent BitReport or empty bit-record payload produces an explicit no-data state and clears charts; it does not treat missing JSON as a zero-depth record.",
    "INV34-008106": "Material inventory clears its table/chart when database or well context is absent. It is explicitly scoped by well and independently applies section/report filters when available.",
    "INV34-008143": "Non-finite chart bar heights are omitted from annotation; finite values including zero remain on the chart, and the operation's known/unknown values are not altered.",
    "INV34-008144": "Same finite-value guard for the second bar series; NaN/Inf labels are suppressed instead of rendered as misleading engineering numbers.",
    "INV34-008243": "Duplicate scanner capture of the optional database guard in TemplateSelectionDialog.load_templates at the same source site as INV34-005049; no database means no template query.",
    "INV34-008375": "The BHA table item may be absent or its optional named-text payload empty; `restore_named_text` restores only recorded names and preserves the row's displayed values/provenance.",
    "INV34-008376": "Same optional named-text restoration for downhole equipment; missing hidden metadata leaves the visible row intact and does not invent a description.",
    "INV34-008377": "Same optional named-text restoration for formations; the guard protects empty/missing table cells and does not change geologic numeric fields.",
    "INV34-008396": "Rule mis-fire: the record is a docstring describing `_optional_float`; executable code below preserves blank/None/garbage as None and converts explicit `0` to 0.0.",
    "INV34-008413": "Duplicate scanner record of the no-database guard in PersonnelLogisticsTab.load_pob_data; same optional DB contract as INV34-006176.",
    "INV34-008420": "Duplicate scanner record of the no-database guard in PersonnelLogisticsTab.load_crew_data; same optional DB contract as INV34-006171.",
    "INV34-008427": "Duplicate scanner record of the no-database guard in PersonnelLogisticsTab.load_notes_data; same optional DB contract as INV34-006173.",
    "INV34-008431": "Rule mis-fire: this is the `_stock_value` docstring stating its real contract. The executable helper returns None at the unknown sentinel and preserves explicit numeric 0.0.",
    "INV34-008441": "Duplicate scanner record of the no-database guard in FuelWaterTab.load_fuel_water_from_db, already reviewed at INV34-006134; no active query means no fabricated fuel/water values.",
}


def verify_changed_site(record: dict) -> dict:
    path, symbol, new_line = SPECIAL[record["id"]]
    tree_lines, tree_bytes, tree_desc = provenance.provenance_tree(path, record["source_sha256"])
    source = tree_bytes.decode("utf-8", "replace")
    line = record["line"]
    assert provenance.text_matches(record["current_source_line"], tree_lines[line - 1])
    start, end = provenance.record_scope(source, record.get("symbol", ""), line)
    assert start <= line <= end
    proof = provenance.fingerprint_proof(record, {}, source)
    assert proof is not None and proof != "MISMATCH", (record["id"], proof)
    current = (ROOT / path).read_text(encoding="utf-8").splitlines()
    current_source = "\n".join(current)
    cstart, cend = provenance.symbol_body(current_source, symbol)
    matches = [i + 1 for i, text in enumerate(current) if cstart <= i + 1 <= cend and text.strip() == new_line]
    assert len(matches) == 1, (record["id"], matches)
    return {
        "id": record["id"], "file": path,
        "previous_site": f"{path}:{line}",
        "previous_source_line": record["current_source_line"].strip(),
        "current_site": f"{path}:{matches[0]}",
        "current_source_line": current[matches[0] - 1].strip(),
        "tree": tree_desc, "source_sha256": record["source_sha256"],
        "context_fingerprint": record["context_fingerprint"],
        "fingerprint_proof": proof,
        "reason": "Original exception/hash/fingerprint verified in fd18 tree; the unsafe row-wide skip was replaced by a per-column unknown-aware helper and current call is mapped within the same UI method.",
    }


def main() -> int:
    provenance.RECHECK_AGAINST.update(SOURCE_TREES)
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    records = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(records) != 45 or {r["id"] for r in records} != set(CLASSIFICATION):
        raise SystemExit(f"batch/classification mismatch: {len(records)} records")
    if set(CLASSIFICATION) != set(NOTES):
        raise SystemExit("classification/note ids do not match")
    by_id = {r["id"]: r for r in records}
    regular = [r for r in records if r["id"] not in SPECIAL]
    reanchored, stats = provenance.check(regular)
    moved = [verify_changed_site(by_id[key]) for key in SPECIAL]
    counts = dict(Counter(CLASSIFICATION.values()))
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
                "Chart availability policy under missing Matplotlib Qt backend; linked to NEW-P6-026 from batch 027"
                if ident in {"INV34-004589", "INV34-004591"} else None
            ),
            "site": {"file": record["file"], "line": record["line"],
                     "symbol": record.get("symbol"), "expression": record.get("current_source_line"),
                     "source_sha256": record["source_sha256"],
                     "context_fingerprint": record["context_fingerprint"]},
        }
        if ident in SPECIAL:
            item["current_site"] = moved[0]["current_site"]
            item["current_source_line"] = moved[0]["current_source_line"]
        items.append(item)
    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": "phase-2 class G/H mixed review: Planning/Analysis widgets, procedure/reference/well/downhole/trajectory/logistics, nullable bulk inventory and chart summaries",
        "records": len(items), "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": dict(Counter(r["file"] for r in records)),
        "by_classification": counts,
        "defects_fixed": [{
            "id": "NEW-P6-027", "records": ["INV34-006210"], "file": "tabs/w7_logistics_Widget.py",
            "site": "FuelWaterTab.calculate_bulk_totals -> core.bulk_material_semantics.summarize_bulk_display_rows",
            "test": "tests/test_bulk_display_totals.py",
            "summary": "The W7 summary previously skipped every field in a row when any displayed value was the unknown em dash, and rendered partial stock subtotals as complete. It now totals each column independently, propagates unknown stock to NOT ASSESSED, preserves known movements, treats blank movements as the documented no-movement zero, and keeps explicit zero."
        }],
        "new_findings": [],
        "observations": [
            {"topic": "bulk inventory trichotomy and aggregation", "summary": "BulkMaterials documents NULL opening/closing stock as unknown, explicit 0.0 as reported zero, and absent received/used movement as 0.0. DatabaseManager.calculate_bulk_totals uses complete_total so any missing amount makes that column unknown; the W7 display summary now follows the same independent per-column completeness contract."},
            {"topic": "Planning and analysis scope", "summary": "Planning loaders clear view data before no-context returns and use current well/section/report IDs explicitly. The code catalog/management paths do not invent a report scope from global selection."},
            {"topic": "UI optionality and review", "summary": "Missing widgets are not treated as completion; invalid survey/service values stay unassessed/reviewable; optional pandas and DB boundaries do not synthesize persisted values."}
        ],
        "sibling_search": [
            {"family": "nullable inventory totals", "result": "Cross-checked BulkMaterials comments, tests/test_m31_scenarios.py unknown-stock total assertions, DatabaseManager.calculate_bulk_totals and core.cost_semantics.complete_total. `_stock_value` maps only its explicit unknown sentinel to None and preserves 0.0; the display aggregator was the isolated row-wide exception."},
            {"family": "W12 chart backend fallback", "result": "W12 Analysis has the same Qt/Agg canvas fallback/Qt-layout mismatch as W10 Planning recorded in NEW-P6-026 (batch 027); it is linked rather than duplicated. GUI execution remains blocked by libGL.so.1."},
            {"family": "field validators and imports", "result": "Bit ROP/depth requires finite nonnegative numbers; trajectory optional parser preserves None and explicit zero; equipment invalid service dates enter review rather than being treated overdue/current."}
        ],
        "tests": {
            "passed": [
                "68 passed: tests/test_bulk_display_totals.py tests/test_bulk_validator_zero.py tests/test_inventory_zero_semantics.py tests/test_mud_ledger_unknown_stock_history.py tests/test_fuel_water_truth.py tests/test_inventory_item_authority.py.",
                "1 passed: tests/test_m31_scenarios.py::test_stock_and_request_totals_are_unknown_when_a_quantity_is_unrecorded (database canonical-total contract).",
                "9 passed: tests/test_w7_null_zero_semantics.py."
            ],
            "environment_blocked": [
                "Two Qt subprocess UI tests failed before assertions because PySide6 cannot load missing libGL.so.1: tests/test_bulk_stock_three_state_smoke.py::test_w7_bulk_stock_three_state_in_subprocess and tests/test_w7_null_zero_ui_smoke.py::test_w7_null_zero_ui_smoke_in_subprocess. No GUI display/persistence integration test is claimed in this batch."
            ],
            "mutation": "Replaced summarize_bulk_display_rows temporarily with the original row-wide `try/except ValueError: continue` aggregation. Three regression cases failed (unknown stock and independent movements; blank stock; malformed/nonfinite values), 1 passed; restored fix then all 4 tests passed."
        },
        "head": "aae13dc", "commit": None, "evidence_commit": None,
        "evidence_files": ["tabs/w7_logistics_Widget.py", "core/bulk_material_semantics.py", "tests/test_bulk_display_totals.py", "tools/m36/p6_batch_028.py", "docs/audits/m36-evidence/p6-batch-028.json"],
        "staleness": {
            "checked": len(records), "stale": len(reanchored) + len(moved), "re_anchored": len(reanchored) + len(moved),
            "method": "All recorded file hashes, lines, symbols and fingerprints were verified against current or fd18 provenance trees. Three changed/stale sites were mapped: two prior W7 guard lines and the fixed bulk-summary site. Four original context fingerprints are not reproducible without the unavailable M34 ledger; their source hash/line/symbol anchors were verified.",
            "re_anchored_items": [
                {"id": ident, "file": path, "previous_site": f"{path}:{old}", "current_site": f"{path}:{new}", "tree": tree,
                 "source_sha256": next(r["source_sha256"] for r in regular if r["id"] == ident),
                 "context_fingerprint": next(r["context_fingerprint"] for r in regular if r["id"] == ident),
                 "reason": "Exact source tree/hash and recorded fingerprint were checked; current expression mapped in the same method."}
                for ident, path, old, new, tree in reanchored
            ] + moved,
            "provenance_trees": stats["trees"],
            "m34_fingerprint_ledger": {
                "manifest": "docs/audits/m34-evidence/M34_INVENTORY_LEDGER.json",
                "expected_path": "docs/audits/m34-evidence/m34-ledger.json",
                "expected_sha256": "d81a77bda0330c75493f4081c4a02e4d106fe7602e49c14f0c67d12977658a6b",
                "expected_bytes": 11394989, "present_in_workspace": False,
                "effect": "Four fingerprints in W12/W1/W4 import fallback sites did not reproduce ledger-free. Exact file hash and site/symbol evidence is retained and no pattern is fabricated."
            },
            "fingerprint_proof": {
                "checked": stats["fingerprints_checked"] + len(moved), "verified": stats["fingerprints_verified"] + len(moved),
                "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"],
                "records_without_a_reproducing_fingerprint_but_hash_anchored": stats["fingerprints_not_reproduced_but_hash_anchored"],
                "symbol_forms_that_reproduced": stats["fingerprints_by_form"],
                "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"],
                "method": stats["ledger_mode"] + "; changed bulk summary was separately proven in original tree and re-anchored to its current helper call"
            }
        },
        "method": "Trace source through selection, UI/load/save and persistence contracts; maintain SQL NULL/unknown versus explicit zero and established blank movement semantics; use complete totals rather than partial subtotals; classify Qt/backend limitations explicitly.",
        "items": items
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={counts}; reanchors={len(reanchored) + len(moved)} fingerprints={stats['fingerprints_verified'] + len(moved)}/{len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
