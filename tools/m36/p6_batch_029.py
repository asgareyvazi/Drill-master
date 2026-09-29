#!/usr/bin/env python3
"""Evidence-backed P6 adjudication for batch 029."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-029"
VC, INT, DUP, DDD, DEF = (
    "VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
    "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT",
)
sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

SOURCE_TREES = {
    "tabs/w7_logistics_Widget.py": "fd18a2bca5b849356c50f9da19c278ecdd8f9967",
    "tabs/w9_Services_Widget.py": "95dd63186ccda8d3cff41ac9632c8c2886639aa4",
    "tests/test_wellbore_section_performance.py": "4a55288ed7f98a255b8af21eb6d618f11a3698c1",
}
SPECIAL = {
    "INV34-006214": (
        "tabs/w7_logistics_Widget.py", "FuelWaterTab.calculate_bulk_totals",
        "totals = summarize_bulk_display_rows(display_rows)",
    ),
}
CLASSIFICATION = {
    "INV34-006132": INT, "INV34-006161": INT,
    "INV34-006214": DUP, "INV34-006371": VC, "INV34-006381": INT,
    "INV34-006417": VC, "INV34-006452": INT, "INV34-006481": INT,
    "INV34-006482": VC, "INV34-006522": VC, "INV34-006574": INT,
    "INV34-006609": INT, "INV34-006628": VC,
    "INV34-006715": INT, "INV34-006716": INT, "INV34-006768": VC,
    "INV34-008460": DUP, "INV34-008470": DUP,
    "INV34-008481": INT, "INV34-008482": INT, "INV34-008483": INT,
    "INV34-008489": INT, "INV34-008490": INT, "INV34-008495": VC,
    "INV34-008518": INT, "INV34-008519": INT, "INV34-008520": INT,
    "INV34-008531": VC, "INV34-008532": VC, "INV34-008541": INT,
    "INV34-008542": INT, "INV34-008544": INT, "INV34-008546": INT,
    "INV34-008550": VC, "INV34-008552": VC, "INV34-008553": VC,
    "INV34-008559": VC, "INV34-008561": VC, "INV34-008563": INT,
    "INV34-008568": VC, "INV34-008569": VC, "INV34-008570": VC,
    "INV34-008914": INT,
}
NOTES = {
    "INV34-006132": "The W7 bulk-material loader returns without a database; with an active DB it clears the bulk table before loading the selected well's rows. This early guard does not produce an assessed zero or retain a prior successful table as an empty result.",
    "INV34-006161": "Logistics well selection cannot load without a DB manager. The guard avoids lookup/persistence; it does not replace the selected well ID with another scope.",
    "INV34-006214": "Duplicate historical capture of the exact W7 row-wide ValueError/continue defect adjudicated and fixed as NEW-P6-027 (INV34-006210) in batch 028. Its original source hash/line/fingerprint is verified and mapped to the same calculate_bulk_totals method's new helper call; no second fix is attributed to this batch.",
    "INV34-006371": "Pytest setup isolates every invocation's data/database paths and adds DRILLMASTER_ENV=test only when the caller did not supply an explicit mode. Teardown restores the prior environment; this is a test safety boundary, not production behavior.",
    "INV34-006381": "openpyxl is optional for fixture generation. The ImportError sets a capability flag; fixture creation raises an explicit dependency error rather than silently producing an empty workbook.",
    "INV34-006417": "The package-smoke test executes the actual app method against a probe, asserts it uses a temporary DB path and test-only credentials, checks both success/failure return codes, closes the manager, removes the temporary directory, and restores environment variables.",
    "INV34-006452": "Real-DDR regression fixtures skip explicitly when the operator workbook is not present; the suite does not substitute a synthetic workbook and claim real-DDR acceptance.",
    "INV34-006481": "Golden real-DDR test fixture likewise skips when the named source workbook is unavailable; the skip is explicit and no import outcome is claimed.",
    "INV34-006482": "The golden DDR test rejects a non-numeric mud weight with pytest.fail. The ValueError handler is the expected negative assertion, not swallowed production input.",
    "INV34-006522": "The regression parametrizes both assignment orders (relationship-first and foreign-key-first) and requires OwnershipIntegrityError for a cross-well section; it prevents a validation-order gap.",
    "INV34-006574": "The test fixture deliberately feeds both historical JSON text and native JSON mappings through the same legacy BHA preservation regression; the branch does not touch live user data.",
    "INV34-006609": "The optional real-world import test dependency is capability-checked; missing integration extras do not get represented as a successful production import.",
    "INV34-006628": "Review rows are selected for any non-OK status, low certainty, or explicit review token. The Boolean grouping is an OR; only fully OK, non-low-certainty, non-review fields are omitted.",
    "INV34-006715": "The expression is confined to test fixture control flow: missing `h`/`prod_h` and an explicit zero both cause no TimeLog row to be created; `worked` itself is not assigned to a persisted field. The actual unknown-depth fixture coercion on the adjacent DailyReport constructor was fixed separately as NEW-P6-028 and is regression-tested.",
    "INV34-006716": "The test helper creates an NPT log only for a positive NPT duration. Zero means no NPT interval in this fixture; no zero-valued substitute duration is persisted.",
    "INV34-006768": "Package metadata absence is translated to the explicit `NOT INSTALLED` state and fails verify_dependencies; the verifier does not treat a missing dependency as available.",
    "INV34-008460": "Duplicate record of INV34-006132 at the identical W7 bulk loader DB guard and exact source site.",
    "INV34-008470": "Duplicate record of INV34-006161 at the identical LogisticsWidget.select_well DB guard and exact source site.",
    "INV34-008481": "W9 notes loading requires both a DB manager and explicit current well. Without either, it performs no query and cannot show another well's notes as the current result.",
    "INV34-008482": "W9 material requests are explicitly well-scoped; missing DB/well context returns before query or persistence and does not invent zero requests.",
    "INV34-008483": "W9 equipment logs are explicitly well-scoped; the no-context guard performs no query or persistence and does not fabricate an empty successful result.",
    "INV34-008489": "The pass statement is the intentional body of a pytest.raises block for persistence failure; the test fails if the expected exception does not occur and separately asserts no partial row was saved.",
    "INV34-008490": "Same expected-failure test pattern for cement persistence: the database error is required and the test asserts no partial persistence.",
    "INV34-008495": "Real DDR acceptance requires an intersection between expected and actual workbook sheets; a missing/unrelated workbook fails the assertion instead of being accepted as a pass.",
    "INV34-008518": "The test explicitly skips Qt-dependent integration when `_qt_gui_importable()` is false; this is an environment limitation, not evidence that the UI behavior passed.",
    "INV34-008519": "Same explicit Qt availability skip for the profile-engine cache-shape integration test.",
    "INV34-008520": "Same explicit Qt availability skip for real Qt dialog construction safety; current environment lacks libGL.so.1, so no UI acceptance claim is made.",
    "INV34-008531": "The OEOC golden persistence assertion requires all expected BHA components after reload; None becomes an empty list only in the assertion and therefore fails rather than passing as 9 persisted records.",
    "INV34-008532": "The OEOC golden persistence assertion similarly requires expected downhole equipment rows after reload and cannot count SQL NULL as successful persisted equipment.",
    "INV34-008541": "Intentional pass in the expected persistence-exception context; the test fails if no exception is raised and asserts the failed operation created no partial row.",
    "INV34-008542": "The stub's pass body is an intentional test double for an operation with no side effect; it does not consume or synthesize engineering inputs.",
    "INV34-008544": "Same no-op stub used to isolate a W12 well-scope regression test; it does not implement production chart or persistence behavior.",
    "INV34-008546": "Same test-only stub for the W12 wellbore-scope regression; production code remains the subject under test.",
    "INV34-008550": "DDR certification refuses to continue if the initial database cannot initialize; failure is not converted to an empty successful acceptance result.",
    "INV34-008552": "The certification reload independently initializes a fresh database manager and aborts on failure; it does not reuse potentially stale in-memory state as persistence proof.",
    "INV34-008553": "Lifecycle certification requires successful explicit manager initialization before any open-database operation.",
    "INV34-008559": "Real-user acceptance exits when its database cannot initialize; the database error is a blocker, not an empty-DB pass.",
    "INV34-008561": "Schema/CRUD probe captures exceptions as explicit failure details for the acceptance report; it does not swallow the exception and mark the probe successful.",
    "INV34-008563": "The static audit is explicitly informational and separate from the release compile gate, which parses/compiles all selected files. It skips unreadable or syntactically invalid files rather than claiming to certify them; its printed scope is limited to reported patterns.",
    "INV34-008568": "The source release verifier stops with exit code 1 when any prerequisite gate returns false; it cannot continue to pytest/wheel verification and report success.",
    "INV34-008569": "A failed pytest gate returns nonzero immediately; it cannot be treated as a successful release check.",
    "INV34-008570": "A failed wheel verification returns nonzero and prevents the verifier's source-gate success message.",
    "INV34-008914": "The HTML renderer returns an explicit no-data string for a missing or empty table. It is a presentation placeholder only and does not serialize or persist a zero inventory amount.",
}


def verify_changed_site(record: dict) -> dict:
    path, symbol, current_expression = SPECIAL[record["id"]]
    lines, tree_bytes, tree_desc = provenance.provenance_tree(path, record["source_sha256"])
    source = tree_bytes.decode("utf-8", "replace")
    line = record["line"]
    assert provenance.text_matches(record["current_source_line"], lines[line - 1])
    start, end = provenance.record_scope(source, record.get("symbol", ""), line)
    assert start <= line <= end
    proof = provenance.fingerprint_proof(record, {}, source)
    assert proof is not None and proof != "MISMATCH", (record["id"], proof)
    current_lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    current_source = "\n".join(current_lines)
    cstart, cend = provenance.symbol_body(current_source, symbol)
    matches = [i + 1 for i, text in enumerate(current_lines)
               if cstart <= i + 1 <= cend and text.strip() == current_expression]
    assert len(matches) == 1, (record["id"], matches)
    return {
        "id": record["id"], "file": path,
        "previous_site": f"{path}:{line}",
        "previous_source_line": record["current_source_line"].strip(),
        "current_site": f"{path}:{matches[0]}",
        "current_source_line": current_lines[matches[0] - 1].strip(),
        "tree": tree_desc, "source_sha256": record["source_sha256"],
        "context_fingerprint": record["context_fingerprint"],
        "fingerprint_proof": proof,
        "reason": "Original historical source/hash/fingerprint verified; duplicate source site already maps to the replacement helper call in the same method.",
    }


def main() -> int:
    provenance.RECHECK_AGAINST.update(SOURCE_TREES)
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    records = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(records) != 43 or {r["id"] for r in records} != set(CLASSIFICATION):
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
            "remaining_question": None,
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
        "class": "phase-2 class H: W7/W9 logistics, test safety and scope regressions, real-DDR acceptance, persistence, release-verification gates",
        "records": len(items), "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": dict(Counter(r["file"] for r in records)),
        "by_classification": counts,
        "defects_fixed": [{
            "id": "NEW-P6-028", "records": [], "file": "tests/test_wellbore_section_performance.py",
            "site": "_ddr DailyReport construction (depth_2400)",
            "test": "test_fixture_preserves_unknown_daily_depth_as_null",
            "summary": "A test-only engineering-performance fixture converted a missing depth_out to DailyReport.depth_2400=0, creating an inconsistent synthetic report that hid unknown-vs-zero semantics. The nullable value is now passed through as None; a focused fixture regression asserts SQL NULL survives reload. This is a test-data quality fix, not a production acceptance claim."
        }],
        "new_findings": [],
        "observations": [
            {"topic": "prior W7 inventory repair", "summary": "INV34-006214 is a second scanner capture of the same historical W7 row-wide ValueError/continue implementation fixed in batch 028 (NEW-P6-027); verified in its source tree and linked to the current per-column summary helper call, not counted as an additional repair."},
            {"topic": "test fixtures and release boundaries", "summary": "The cross-batch semantic sweep found an adjacent test fixture default converting absent daily depth to numeric zero. It is corrected to preserve nullable SQL state. Test helpers that use zero only as a branch-control sentinel and do not persist a value remain intentional."},
            {"topic": "production/release acceptance", "summary": "No new production behavior defect was confirmed in the W7/W9 context guards, import capability checks, or release fail-fast gates. Missing real-DDR/Qt/Windows/production-database environments remain distinct from source test results."}
        ],
        "sibling_search": [
            {"family": "W7 duplicate bulk summary defect", "result": "INV34-006210 and INV34-006214 point to the same historical line/fingerprint in the same W7 method. The exact source tree is verified and the current helper call is the replacement; batch 028 owns the production fix and its mutation-tested regression."},
            {"family": "unknown depth in wellbore performance fixtures", "result": "DailyReport.depth_2400 is nullable; `_ddr` now preserves do=None, in agreement with DrillingParameters.depth_out=None and the test file's explicit unknown/scope contract. Added direct SQLAlchemy reload assertion."},
            {"family": "release and environment gates", "result": "verify_release returns nonzero at failed dependency/lint/test/wheel checks; real-DDR fixture skips only when absent; Qt integration skips explicitly when not importable. These checks do not certify Windows packaging, real MinerU/DDR or production DB."}
        ],
        "tests": {
            "passed": [
                "155 passed: tests/test_wellbore_section_performance.py, tests/test_credential_lifecycle.py, tests/test_ddr_regression.py, tests/test_golden_ddr.py, tests/test_real_world_import.py, tests/test_review_contract_certification.py.",
                "134 passed: tests/test_r18_r19_save_preservation.py, tests/test_casing_persistence.py, tests/test_cement_persistence.py, tests/test_torque_drag_persistence.py, tests/test_real_oeoc_golden.py.",
                "6 passed, 3 skipped: tests/test_p0_phase1_regressions.py; all skips are Qt-unavailable guards.",
                "236 passed, 11 environment failures: tests/test_m29_release_closure.py; the 11 listed below fail on Qt import before assertions. The separate targeted NULL fixture test passed (and is included in the 155-test command)."
            ],
            "environment_blocked": [
                "11 tests in tests/test_m29_release_closure.py could not import PySide6 because libGL.so.1 is missing: test_npt_report_scope_and_unknown_duration; test_milestone_unknown_and_zero_are_distinct_in_both_consumers; test_permission_is_entity_specific_and_main_window_fails_closed; test_copy_previous_uses_target_date_zero_closing_and_no_safety_assessment; test_learning_store_uses_user_data_not_application_directory; test_rop_forecast_uses_calendar_dates_not_observation_ordinals; both parameter cases of test_w12_calendar_rate_unique_endpoints_and_canonical_unknown; test_w12_mud_sample_is_not_two_directional_measurements; test_chart_export_false_result_is_not_success; test_template_save_io_failure_has_no_success_message.",
                "Collection of tests/test_w12_milestones_m25.py, tests/test_w12_scope_leakage_m25.py, and tests/test_w12_wellbore_scope.py is blocked by the same missing libGL.so.1 shared library."
            ],
            "mutation": "Restoring the missing-depth-to-zero fallback made the dedicated fixture SQL NULL assertion fail; the corrected helper was restored and the test passed."
        },
        "head": "ea3c3b0", "commit": None, "evidence_commit": None,
        "evidence_files": ["tests/test_wellbore_section_performance.py", "tools/m36/p6_batch_029.py", "docs/audits/m36-evidence/p6-batch-029.json"],
        "staleness": {
            "checked": len(records), "stale": len(reanchored) + len(moved), "re_anchored": len(reanchored) + len(moved),
            "method": "All record source hashes, original lines, symbols and fingerprints were checked against current or exact historical trees. Nine changed sites were re-anchored: duplicate W7 summary exception, paired W7 loader/selection guards, paired W9 guards, and the repeated same-method W7/W9 sites. Two fingerprints did not reproduce without the missing M34 ledger; hash/line/symbol evidence remains.",
            "re_anchored_items": [
                {"id": ident, "file": path, "previous_site": f"{path}:{old}", "current_site": f"{path}:{new}", "tree": tree,
                 "source_sha256": next(r["source_sha256"] for r in regular if r["id"] == ident),
                 "context_fingerprint": next(r["context_fingerprint"] for r in regular if r["id"] == ident),
                 "reason": "Exact hash tree and original fingerprint verified; mapped to the corresponding current method expression."}
                for ident, path, old, new, tree in reanchored
            ] + moved,
            "provenance_trees": stats["trees"],
            "m34_fingerprint_ledger": {
                "manifest": "docs/audits/m34-evidence/M34_INVENTORY_LEDGER.json",
                "expected_path": "docs/audits/m34-evidence/m34-ledger.json",
                "expected_sha256": "d81a77bda0330c75493f4081c4a02e4d106fe7602e49c14f0c67d12977658a6b",
                "expected_bytes": 11394989, "present_in_workspace": False,
                "effect": "Two fingerprints (fixture import fallbacks) did not reproduce ledger-free; source hash/line/symbol evidence is retained."
            },
            "fingerprint_proof": {
                "checked": stats["fingerprints_checked"] + len(moved), "verified": stats["fingerprints_verified"] + len(moved),
                "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"],
                "records_without_a_reproducing_fingerprint_but_hash_anchored": stats["fingerprints_not_reproduced_but_hash_anchored"],
                "symbol_forms_that_reproduced": stats["fingerprints_by_form"],
                "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"],
                "method": stats["ledger_mode"] + "; duplicate W7 summary exception separately verified in its historical tree and linked to the fixed helper call"
            }
        },
        "method": "Trace production source and test/release consumers separately; preserve missing SQL nullable state; verify failure gates fail closed; distinguish explicit environment skips from successful certification.",
        "items": items
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={counts}; reanchors={len(reanchored) + len(moved)} fingerprints={stats['fingerprints_verified'] + len(moved)}/{len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
