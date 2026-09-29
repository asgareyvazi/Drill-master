#!/usr/bin/env python3
"""Adjudicate P6 batch 022 from its hash-anchored source records.

Modified sites are explicitly reconstructed from the batch source tree to the
current lines; unchanged sites use the shared AST/fingerprint verifier. The M34
fingerprint ledger is absent, so the reproducible ledger-free fallback is used.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-022"
VC = "VERIFIED-CORRECT"
INT = "INTENTIONAL"
DUP = "DUPLICATE/FALSE-POSITIVE"
DDD = "DOMAIN_DECISION_REQUIRED"
DEF = "GENUINE_DEFECT"

sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

SOURCE_TREES = {
    "tabs/w7_logistics_Widget.py": "fd18a2bca5b849356c50f9da19c278ecdd8f9967",
    "tabs/w9_Services_Widget.py": "7f0186e3e6ac966f1fe9cbd804785129b9246fbe",
    "tabs/w3c_section_data.py": "7f0186e3e6ac966f1fe9cbd804785129b9246fbe",
}
# These fingerprints refer to source lines that were intentionally rewritten.
# Exact former bytes/hash/fingerprint and exact present expression are checked below.
RECONSTRUCTED = {
    "INV34-010301": ("tabs/w7_logistics_Widget.py", 1096,
                     "_set_stock_value(self.fuel_stock, None)",
                     "clear_fields now uses the nullable-stock unknown sentinel"),
    "INV34-010304": ("tabs/w7_logistics_Widget.py", 1099,
                     "_set_stock_value(self.water_stock, None)",
                     "clear_fields now uses the nullable-stock unknown sentinel"),
    "INV34-010307": ("tabs/w7_logistics_Widget.py", 1102,
                     "_set_stock_value(self.dw_stock, None)",
                     "clear_fields now uses the nullable-stock unknown sentinel"),
    "INV34-010310": ("tabs/w7_logistics_Widget.py", 1105,
                     "_set_stock_value(self.fuel_camp_stock, None)",
                     "clear_fields now uses the nullable-stock unknown sentinel"),
    "INV34-010318": ("tabs/w9_Services_Widget.py", 116,
                     "self.requested_qty_input.setValue(_REQUEST_QUANTITY_UNKNOWN)",
                     "the UI now displays an explicit unknown sentinel and maps it to NULL"),
    "INV34-010319": ("tabs/w9_Services_Widget.py", 401,
                     "self.requested_qty_input.setValue(_REQUEST_QUANTITY_UNKNOWN)",
                     "clearing the request form restores unknown, not zero"),
}

CLASSIFICATION = {
    "INV34-003911": VC, "INV34-003912": VC,
    "INV34-004703": INT, "INV34-004704": DDD, "INV34-004705": VC,
    "INV34-005394": DUP, "INV34-005574": DDD, "INV34-005588": DDD,
    "INV34-006015": VC, "INV34-006408": VC, "INV34-008925": DUP,
    "INV34-009982": VC, "INV34-009984": VC, "INV34-009985": VC,
    "INV34-009988": VC, "INV34-009992": VC,
    "INV34-010046": DUP, "INV34-010059": VC, "INV34-010063": VC,
    "INV34-010064": VC, "INV34-010109": DUP, "INV34-010134": INT,
    "INV34-010137": INT, "INV34-010138": INT, "INV34-010181": VC,
    "INV34-010259": VC,
    "INV34-010300": VC, "INV34-010301": DEF, "INV34-010302": VC,
    "INV34-010303": VC, "INV34-010304": DEF, "INV34-010305": VC,
    "INV34-010306": VC, "INV34-010307": DEF, "INV34-010308": VC,
    "INV34-010309": VC, "INV34-010310": DEF, "INV34-010311": VC,
    "INV34-010318": DEF, "INV34-010319": DEF,
    "INV34-010533": DUP, "INV34-010703": DUP, "INV34-010769": DUP,
    "INV34-010823": DUP, "INV34-010827": DUP,
}

NOTES = {
    "INV34-003911": "`current_depth=0` is the root call from `_filter_hierarchy`; each recursive child gets depth+1. It is traversal state, not a drilling measurement.",
    "INV34-003912": "The depth cap is a recursion guard. Tree depth in this UI is shallow (company/project/well/section/report); exceeding the cap excludes only deeper descendants instead of risking unbounded recursion.",
    "INV34-004703": "30e6 psi is the conventional steel modulus and matches `FishingEngine.backoff_depth`'s canonical default; tests compare a changed modulus to prove the parameter reaches the engine. Separately, the legacy plain-return back-off wrapper maps invalid inputs to 0 and is recorded in NEW-P6-013 for owner review.",
    "INV34-004704": "The adapter converts pcf to ppg and delegates to `TorqueDragEngine.buoyancy_factor`, but returns 0 on nonpositive input or engine exception. W13 then feeds that 0 into a successful landing-load card; the canonical engine rejects nonpositive mud density. This needs an owner decision on preserving the plain-return compatibility API versus surfacing an explicit failed/unknown result; no behavior was silently changed.",
    "INV34-004705": "The UI passes its friction control explicitly; the facade delegates to `TorqueDragEngine.casing_landing_load` and returns `{error: ...}` on failure. No failed result is replaced with a numeric zero at this site.",
    "INV34-005394": "The recorded line only places a read-only derived-output widget in the form layout; it assigns no value. The formula is in `calculate_bit_revolution`. The separate nullable persistence risk (empty RPM/time inputs yield a displayed/saved zero) is retained as NEW-P6-014 rather than misclassifying this layout call.",
    "INV34-005574": "CasingReport nullable numeric columns are read through `sv(k,d=0)` and the form save path writes every spinbox value, so SQL NULL reloads as a displayed zero and can be overwritten on save. Several fields may be optional measurements; whether blank controls should use explicit unknowns/preserve NULL requires product/domain policy. See NEW-P6-010.",
    "INV34-005588": "CementReport numeric columns and `thickening_time` are nullable; `sv` substitutes zero or engineering-looking defaults (density 120, yield 1.18, mix water 5.2, strength 2500), and save writes widget values. This is a concrete NULL-to-value round-trip risk; do not guess whether the defaults are intended baselines or optional measurements. See NEW-P6-010.",
    "INV34-006015": "`_val` is used for movement quantities only (consumed/received); model/database semantics specify absent movements as zero. Nullable stocks use the separate `_stock`/unknown sentinel path and are not passed through this default.",
    "INV34-006408": "This test deliberately compares the displayed cost summary's stored actuals with a direct `SUM(CostRecord.actual_cost)`; it tests cross-consumer parity rather than manufacturing a value from a default.",
    "INV34-008925": "`required_values` builds synthetic values only for non-nullable columns in an ownership-integrity test fixture. The zero is test data used to exercise FK ownership rejection, not a production initializer or saved business fact.",
    "INV34-009982": "The minimum -1 is the named `Not planned` sentinel; `create_section` maps negative to None. Zero remains a separate explicitly supplied value.",
    "INV34-009984": "One decimal place is UI precision, not a numeric fallback.",
    "INV34-009985": "Initial -1 is the UI's explicit `Not planned` sentinel, not zero days. The persistence boundary maps it to SQL NULL.",
    "INV34-009988": "The signal recomputes a derived ROP when days/depth change; handler emits an em dash for nonpositive days or invalid depth interval.",
    "INV34-009992": "ROP is undefined when planned days are zero, so the UI shows None/emdash instead of dividing by zero; the explicitly entered planned_days zero itself is retained. Whether a zero-day section plan is permitted remains product policy, but no division fallback is fabricated here.",
    "INV34-010046": "This line is a dependency import; actual report days are computed by the imported section-scoped complete-time helper. Importing the helper does not assign a numeric default.",
    "INV34-010059": "The plan header depth is used only at whole-plan scope. Section scope sets it to None and filters `PlannedActivity.section_id`; the plan query is bound to the selected well and active plan, not current_report_id.",
    "INV34-010063": "Each activity's nullable stored `planned_depth_from` is passed through as a plan point; there is no zero substitution at the load site. Chart/table consumers operate on the selected active plan and optional section filter.",
    "INV34-010064": "Same direct pass-through as depth-from: missing end depth remains None, while a reported zero is not collapsed by truthiness.",
    "INV34-010109": "This is a helper import only; the milestone reader calls `section_actual_days` for each section and keeps selected-wellbore filtering at the section query.",
    "INV34-010134": "The source comment states this context-only mud-weight control is not persisted by `save_procedure`; zero is a blank-entry placeholder, not a well mud-weight measurement. GLE-MSL is explicitly not copied into it.",
    "INV34-010137": "Checklist progress starts at zero items complete; it is a UI count and is recomputed as checklist state changes.",
    "INV34-010138": "Steps progress likewise starts at zero completed steps and is recomputed from the workflow table.",
    "INV34-010181": "This line only bounds the user-entered actual rig-days control. `load_well_data` captures displayed baselines and `save_data` calls `preserve_widget_values`, which restores untouched source NULL while allowing an explicitly touched zero; the control range itself is not the persistence default.",
    "INV34-010259": "Missing target depth is represented in the widget by zero with an explicit comment; the auto-builder independently reads nullable `Well.target_depth` as None and the neutral schematic scale treats None/zero as view geometry only. No depth is persisted by this control.",
    "INV34-010300": "Fuel consumed is a movement; clear-to-zero represents no movement and matches the DB movement semantics.",
    "INV34-010301": "Fuel stock is nullable physical inventory. Clearing it to 0 fabricated an empty-tank report; `clear_fields` now sets the unknown mark and save persists SQL NULL. Fixed in 4849e03.",
    "INV34-010302": "Fuel received is a movement; zero means no receipt, distinct from nullable stock.",
    "INV34-010303": "Water consumed is a movement; zero means no movement.",
    "INV34-010304": "Water stock is nullable; clear now restores unknown rather than asserting an empty tank. Fixed in 4849e03.",
    "INV34-010305": "Water received is a movement; zero is the additive identity for no movement.",
    "INV34-010306": "Drilling-water consumed is a movement; zero means no movement.",
    "INV34-010307": "Drilling-water stock is nullable; clear now restores unknown, not zero. Fixed in 4849e03.",
    "INV34-010308": "Drilling-water received is a movement; zero means no movement.",
    "INV34-010309": "Camp fuel consumed is a movement; zero means no movement.",
    "INV34-010310": "Camp fuel stock is nullable; clear now restores unknown, not zero. Fixed in 4849e03.",
    "INV34-010311": "Camp fuel received is a movement; zero means no movement.",
    "INV34-010318": "New material requests now start at an explicit `Not specified` sentinel; the save adapter translates it to None while preserving an explicitly entered 0.0. The nullable `MaterialRequest.requested_quantity` contract and totals already preserve NULL. Fixed in 219dc06.",
    "INV34-010319": "Clearing a request form now restores the unknown sentinel, not zero; save maps that sentinel to None and distinguishes explicit zero. Fixed in 219dc06.",
    "INV34-010533": "Import-only test line; behavioral assertions below exercise `ActualVsPlanEngine` rather than using the import as a value default.",
    "INV34-010703": "Import-only test line; the module's assertions compare plan/actual contracts and scope.",
    "INV34-010769": "Import-only test line; the release test imports the comparison API, with behavior asserted in test bodies.",
    "INV34-010823": "Import-only line in a test focused on negative planned cost denominators; no numeric default is introduced here.",
    "INV34-010827": "Import-only line in a test rejecting infinite financial facts; no numeric default is introduced here.",
}

QUESTIONS = {
    "INV34-004704": "Should the public W13 buoyancy facade keep its legacy 0.0-on-invalid behavior, or surface an explicit failed/unknown result so the caller cannot present an invalid landing-load card as valid?",
    "INV34-005574": "For nullable casing measurements, should an untouched field remain SQL NULL across load/save, or are any named fields intended to receive specified engineering defaults?",
    "INV34-005588": "For nullable cement values and thickening_time, which are measurements versus default job-design baselines, and how should NULL be represented/preserved in the form?",
}


def source_proof(records: list[dict]):
    provenance.RECHECK_AGAINST.update(SOURCE_TREES)
    custom_ids = set(RECONSTRUCTED)
    ordinary = [r for r in records if r["id"] not in custom_ids]
    reanchored, stats = provenance.check(ordinary)
    current_texts: dict[str, str] = {}
    custom = []
    for record in records:
        if record["id"] not in custom_ids:
            continue
        path, line, expected, reason = RECONSTRUCTED[record["id"]]
        old_lines, raw, tree = provenance.provenance_tree(path, record["source_sha256"])
        old_text = raw.decode("utf-8", "replace")
        if hashlib.sha256(raw).hexdigest() != record["source_sha256"]:
            raise SystemExit(f"{record['id']}: old source SHA mismatch")
        if not (0 < record["line"] <= len(old_lines)) or not provenance.text_matches(
            record["current_source_line"], old_lines[record["line"] - 1]
        ):
            raise SystemExit(f"{record['id']}: former source expression is not at the recorded line")
        proof = provenance.fingerprint_proof(record, {}, old_text)
        if proof == "MISMATCH" or proof is None:
            raise SystemExit(f"{record['id']}: source fingerprint is not reproduced")
        lines = current_texts.setdefault(path, (ROOT / path).read_text(encoding="utf-8")).splitlines()
        if not (0 < line <= len(lines)) or lines[line - 1].strip() != expected:
            raise SystemExit(f"{record['id']}: current reconstructed expression changed at {path}:{line}")
        symbol_start, symbol_end = provenance.record_scope(
            (ROOT / path).read_text(encoding="utf-8"), record.get("symbol", ""), line)
        if not symbol_start <= line <= symbol_end:
            raise SystemExit(f"{record['id']}: current expression escaped its recorded symbol")
        custom.append({
            "id": record["id"], "file": path,
            "previous_site": f"{path}:{record['line']}",
            "previous_source_line": record["current_source_line"].strip(),
            "current_site": f"{path}:{line}", "current_source_line": expected,
            "tree": SOURCE_TREES[path], "source_sha256": record["source_sha256"],
            "context_fingerprint": record["context_fingerprint"],
            "fingerprint_proof": proof, "reason": reason,
            "proof": "former bytes match source_sha256; recorded context_fingerprint reproduces from the former AST/source line; current expression and enclosing symbol were checked exactly",
        })
    stats["fingerprints_checked"] += len(custom)
    stats["fingerprints_verified"] += len(custom)
    stats["reconstructed_records"] = len(custom)
    return reanchored, custom, stats


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    records = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(records) != 45 or {r["id"] for r in records} != set(CLASSIFICATION):
        raise SystemExit(f"register/classification mismatch: {len(records)} records, {len(CLASSIFICATION)} classifications")
    reanchored, reconstructed, stats = source_proof(records)
    by_id = {r["id"]: r for r in records}
    items = []
    for record in records:
        classification = CLASSIFICATION[record["id"]]
        note = NOTES[record["id"]]
        evidence = (
            f"Hash-anchored register site {record['file']}:{record['line']} "
            f"`{record['current_source_line'].strip()}` in `{record.get('symbol')}`; "
            f"source_sha256={record['source_sha256']}; context_fingerprint={record['context_fingerprint']}. "
            + note
        )
        items.append({
            "id": record["id"], "file": record["file"], "line": record["line"],
            "symbol": record.get("symbol"), "rule": record.get("rule"), "kind": record.get("kind"),
            "register_line_text": record.get("current_source_line"),
            "classification": classification, "evidence": evidence,
            "defect": classification == DEF,
            "remaining_question": QUESTIONS.get(record["id"]),
            "commit": "4849e03a6cb9571bf82909732aeba3ec0c07483e" if record["id"] in {
                "INV34-010301", "INV34-010304", "INV34-010307", "INV34-010310"
            } else ("219dc06e5cafa30ec5e38bf48feefe95c1c4e12c" if record["id"] in {
                "INV34-010318", "INV34-010319"
            } else None),
            "site": {
                "file": record["file"], "line": record["line"], "symbol": record.get("symbol"),
                "expression": record.get("current_source_line"),
                "source_sha256": record["source_sha256"],
                "context_fingerprint": record["context_fingerprint"],
            },
        })

    reanchored_items = []
    for ident, path, old_line, new_line, tree in reanchored:
        r = by_id[ident]
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        reanchored_items.append({
            "id": ident, "file": path,
            "previous_site": f"{path}:{old_line}", "previous_source_line": r["current_source_line"].strip(),
            "current_site": f"{path}:{new_line}", "current_source_line": lines[new_line - 1].strip(),
            "tree": tree, "source_sha256": r["source_sha256"],
            "context_fingerprint": r["context_fingerprint"],
            "reason": "Only preceding comments/lines changed; shared line-map plus exact source expression and enclosing symbol verified the new site.",
        })
    reanchored_items.extend(reconstructed)

    classifications = dict(Counter(CLASSIFICATION.values()))
    counts_by_file = dict(Counter(r["file"] for r in records))
    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": "phase-2 medium class C/D/E mixed review: engineering adapters, nullable UI persistence, plan/report scopes and lifecycle defaults",
        "records": len(items), "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": counts_by_file, "by_classification": classifications,
        "defects_fixed": [
            {"records": ["INV34-010301", "INV34-010304", "INV34-010307", "INV34-010310"],
             "file": "tabs/w7_logistics_Widget.py", "fix_commit": "4849e03a6cb9571bf82909732aeba3ec0c07483e",
             "summary": "FuelWaterTab.clear_fields resets nullable stock controls to unknown while movement controls remain zero.",
             "regression": "tests/test_w7_null_zero_ui_smoke.py; tests/test_w7_null_zero_semantics.py",
             "mutation": "Directly executed current and pre-fix clear_fields AST bodies with fake controls: current yields four unknown stocks/zero movements; pre-fix yields four zero stocks and fails the regression expectation."},
            {"records": ["INV34-010318", "INV34-010319"],
             "file": "tabs/w9_Services_Widget.py", "fix_commit": "219dc06e5cafa30ec5e38bf48feefe95c1c4e12c",
             "summary": "The material-request quantity UI has a visible unknown sentinel, maps it to SQL NULL, preserves explicitly entered zero, and clear restores unknown.",
             "regression": "tests/test_w9_material_request_unknown_quantity.py",
             "mutation": "Executed the actual AST save expression for sentinel/zero/positive inputs; outputs are None/0.0/value. Mutating back to direct spinbox.value() yields -1.0 and violates the NULL expectation."},
            {"id": "NEW-P6-011", "file": "tabs/w7_logistics_Widget.py", "status": "fixed",
             "commit": "219dc06e5cafa30ec5e38bf48feefe95c1c4e12c",
             "summary": "Loading a well/report with no inventory used to leave prior selection values in W7 controls; loader now clears stocks to unknown and movements to zero.",
             "regression": "tests/test_w7_null_zero_ui_smoke.py (switches from a populated well to an empty well)",
             "mutation": "Executed the actual load_fuel_water_from_db AST against empty-result DB stubs: pre-fix retains old stock/movement values; current resets unknown/zero."},
            {"id": "NEW-P6-012", "file": "tabs/w3c_section_data.py", "status": "fixed",
             "commit": "6c07d3a2ed4782bb5dd707f43b0d78635dead162",
             "summary": "A well switch clears the previous selected section and W3c form state; cement/casing loads and saves now use the selected section id instead of leaking well-wide/other-section reports.",
             "regression": "tests/test_w3c_well_switch_scope_smoke.py",
             "mutation": "The isolated integration regression asserts section A does not load into B, saves attach section_id B, and a well switch clears stale form/tally/bit state; the prior implementation would fail these assertions."},
        ],
        "new_findings": [
            {"id": "NEW-P6-010", "file": "tabs/w3c_section_data.py", "line": 198,
             "severity": "MEDIUM", "status": "domain decision required; not patched",
             "summary": "Cement/casing nullable numeric fields (and cement thickening_time) collapse SQL NULL to spinbox/string defaults during load; saving writes the widget values and can overwrite unknowns. Determine field-by-field whether defaults are contractual baselines or nullable measurements and how untouched NULL should display/persist.",
             "records": ["INV34-005574", "INV34-005588"],
             "impact": "A load-and-save without editing can convert unknown values to 0, 120 pcf, 1.18 yield, 5.2 mix water, 2500 strength, or 04:30; current sources do not establish which are intentional defaults."},
            {"id": "NEW-P6-013", "file": "tabs/w13_Engineering_Calculator.py", "line": 119,
             "severity": "MEDIUM", "status": "domain decision required; not patched",
             "summary": "The legacy W13 buoyancy facade returns 0.0 for invalid/nonpositive mud weight or engine exceptions; `_csg_calc_landing` feeds that zero to a downstream accepted load card. The canonical engine rejects nonpositive mud density. Decide whether to preserve compatibility or surface an explicit failed/unknown result.",
             "records": ["INV34-004704"], "impact": "An invalid input can be presented as a numeric buoyancy/load output without an error marker."},
            {"id": "NEW-P6-014", "file": "tabs/w3_drilling_report.py", "line": 786,
             "severity": "MEDIUM", "status": "domain decision required; not patched",
             "summary": "Bit revolutions are calculated from default-zero RPM bounds and hours, and the derived value is saved into nullable DailyReport fields; an otherwise valid bit/depth form can therefore persist 0 before RPM/time are entered. Decide whether the product contract requires an explicit zero or represents these inputs as unknown until supplied.",
             "records": ["INV34-005394"], "impact": "A missing operational rotation/time entry can become a saved zero derived fact; the flagged layout line itself is a false positive, but the traced producer-to-persistence path merits a separate contract decision."},
        ],
        "observations": [
            {"topic": "report and plan scope", "summary": "W10's active plan is selected by well and active flag; activities are also constrained by plan id and optional section id. Section header depth is excluded when viewing a section. W12 milestones query section facts from complete time logs, filter sections by selected bore, and use whole-well report fallback only when no whole-well sections exist."},
            {"topic": "unknown versus zero", "summary": "W7 distinguishes nullable stock from zero-default movements; W9's nullable requested quantity/complete-total code already supports NULL and explicit zero. The two UI boundaries were corrected without changing DB semantics."},
            {"topic": "nullable cement/casing", "summary": "Database columns are nullable but UI widgets cannot encode unknown independently of numeric defaults. This is a documented domain decision, not closed by changing defaults arbitrarily."},
            {"topic": "audit tooling", "summary": "The 11 MB M34 fingerprint ledger is absent/untracked in the repository; all 45 batch records were checked ledger-free using exact source SHA, source expression, AST symbol and context fingerprint. One test-layout record has an unreproduced fingerprint but exact hash-anchored source line/symbol; it is retained with this exception disclosed."},
        ],
        "sibling_search": [
            {"family": "W7 nullable stock versus movements", "result": "FuelWaterInventory stock columns are nullable; movement fields default to zero. Clear/load-empty paths now preserve that distinction; carry-forward remains a visibly marked preview."},
            {"family": "W9 material quantities", "result": "MaterialRequest.requested_quantity is nullable with no DB default and complete totals turn unknown components into unknown totals; both form initialization and clearing now preserve NULL."},
            {"family": "W3c nullable measurement controls", "result": "CementReport and CasingReport numeric columns are nullable; all widget save paths write numeric widget values. No field-level product policy was found, so no schema or blanket conversion was made."},
            {"family": "well/section selection scope", "result": "SelectionManager clears wellbore/section/report state on well changes but emits only well_changed. W3c now clears its local section id/forms on well switches and filters cement/casing reads/writes by the selected section; W7 clears stale values on an empty inventory load."},
        ],
        "tests": {
            "passed": [
                "39 passed: tests/test_w7_null_zero_semantics.py tests/test_fuel_water_truth.py tests/test_inventory_zero_semantics.py",
                "76 passed: tests/test_cement_persistence.py tests/test_casing_persistence.py tests/test_w7_null_zero_semantics.py tests/test_fuel_water_truth.py tests/test_inventory_zero_semantics.py",
                "33 passed: tests/test_report_scoped_ownership_m26.py tests/test_report_scope_metadata_m25.py",
                "20 passed: tests/test_report_scope_metadata_m25.py tests/test_operational_time_integrity.py",
                "17 passed: tests/test_inventory_zero_semantics.py tests/test_m31_scenarios.py -k 'material_request or inventory or request_quantities'",
                "20 passed: tests/test_report_scope_metadata_m25.py tests/test_operational_time_integrity.py",
                "AST behavior/mutation checks: W7 current vs pre-fix clear_fields; W7 empty-load current vs pre-fix; W9 actual save expression sentinel/zero/positive plus direct-value mutation; W3c current vs pre-fix well-change handler",
                "ruff --select E722,F821; compileall; git diff --check",
            ],
            "environment_blocked": [
                "3 isolated Qt smoke tests (W7, W9, W3c) fail before assertions because PySide6 cannot load system libGL.so.1.",
                "4 W12 UI tests fail at collection for missing libGL.so.1; planning-context subprocess smoke also fails before assertions for the same dependency.",
                "2 cement/casing history-viewmodel test modules fail at collection for missing libGL.so.1.",
            ],
            "mutation": "Production/UI regression tests are committed, but their native Qt execution is blocked locally. AST execution of the actual current and pre-fix methods/expressions proved the targeted reset/unknown behavior and the pre-fix/direct-value mutations violate expectations. Exact-HEAD CI must run the isolated UI tests.",
        },
        "head": "6c07d3a",
        "commit": None, "evidence_commit": None,
        "evidence_files": ["docs/audits/m36-evidence/p6-batch-022.json", "docs/audits/m36-evidence/m36-open-item-register.json", "docs/audits/m36-evidence/m36-master-ledger.json", "tools/m36/p6_batch_022.py", "tabs/w7_logistics_Widget.py", "tabs/w9_Services_Widget.py", "tabs/w3c_section_data.py", "tests/test_w7_null_zero_ui_smoke.py", "tests/test_w9_material_request_unknown_quantity.py", "tests/test_w3c_well_switch_scope_smoke.py"],
        "staleness": {
            "checked": len(records), "stale": len(reanchored_items), "re_anchored": len(reanchored_items),
            "method": "All 45 records were verified against declared file SHA, recorded source expression, enclosing symbol and context fingerprint. 39 unchanged-expression records passed the shared AST/hash checker (the one non-reproducing fingerprint is source-hash anchored); six rewritten expressions were explicitly reconstructed with former/current site, exact hashes/fingerprints, current symbols and behavioral checks.",
            "re_anchored_items": reanchored_items,
            "provenance_trees": stats["trees"],
            "fingerprint_proof": {
                "checked": stats["fingerprints_checked"], "verified": stats["fingerprints_verified"],
                "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"],
                "records_without_a_reproducing_fingerprint_but_hash_anchored": stats["fingerprints_not_reproduced_but_hash_anchored"],
                "symbol_forms_that_reproduced": stats["fingerprints_by_form"],
                "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"],
                "method": stats["ledger_mode"],
            },
        },
        "method": "For each record, verify exact old file SHA/source line/context fingerprint and enclosing AST symbol, then trace its caller, normalization, engine/database consumer, UI/report/persistence and relevant tests. Genuine unknown-vs-zero and selection-scope defects were fixed minimally with regression coverage; nullable cement/casing and legacy W13 failure-to-zero behavior remain explicit owner decisions.",
        "items": items,
    }
    out = EVIDENCE / f"{BATCH}.json"
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={classifications}; "
          f"reanchors={len(reanchored_items)} fingerprints={stats['fingerprints_verified']}/{stats['fingerprints_checked']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
