#!/usr/bin/env python3
"""Evidence-backed P6 adjudication for batch 026."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-026"
VC, INT, DUP, DDD, DEF = (
    "VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
    "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT",
)
sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

BASE = "7f0186e3e6ac966f1fe9cbd804785129b9246fbe"
SOURCE_TREES = {
    "core/mineru_engine.py": BASE,
    "core/operations_intelligence.py": BASE,
    "core/report_engine.py": BASE,
    "core/scope_attribution.py": BASE,
    "core/selection_manager.py": BASE,
    "core/standards.py": BASE,
    "core/unit_manager.py": BASE,
    "core/universal_import.py": BASE,
    "core/validators.py": BASE,
    "core/value_normalizer.py": BASE,
    "core/rag_search.py": BASE,
    "core/report_lifecycle.py": BASE,
    "dialogs/casing_history_dialog.py": BASE,
    "dialogs/cement_history_dialog.py": BASE,
    "dialogs/engineering_dialogs.py": BASE,
    "dialogs/hierarchy_dialogs.py": BASE,
    "dialogs/excel_import_dialog.py": BASE,
}
CLASSIFICATION = {
    "INV34-002204": INT, "INV34-002246": INT, "INV34-002477": DDD,
    "INV34-002634": INT, "INV34-002784": INT, "INV34-002787": INT,
    "INV34-002797": INT, "INV34-002798": INT, "INV34-002799": INT,
    "INV34-002812": INT, "INV34-002892": INT, "INV34-002961": INT,
    "INV34-002962": INT, "INV34-002984": VC, "INV34-002987": VC,
    "INV34-002988": VC, "INV34-003022": INT, "INV34-003026": INT,
    "INV34-003027": INT, "INV34-003028": INT, "INV34-003036": INT,
    "INV34-003037": INT, "INV34-003151": INT, "INV34-003162": INT,
    "INV34-003280": INT, "INV34-003453": INT, "INV34-003462": INT,
    "INV34-003467": INT, "INV34-003469": INT, "INV34-007651": INT,
    "INV34-007686": INT, "INV34-007691": INT, "INV34-007708": INT,
    "INV34-007710": DUP, "INV34-007727": INT, "INV34-007741": INT,
    "INV34-007746": INT, "INV34-007762": DUP, "INV34-007850": INT,
    "INV34-007856": DUP, "INV34-007874": DDD, "INV34-007888": DUP,
    "INV34-007935": INT, "INV34-007953": INT, "INV34-007954": INT,
}
NOTES = {
    "INV34-002204": "The JSON payload parser catches only type/value failures for an individual node; unusable source nodes are skipped while other document structure and provenance remain available.",
    "INV34-002246": "NPT insight is optional by threshold: analyze_well calls the analyzer only for a known percentage, and appends an insight only when the analyzer returns one. No 0% substitute is created for missing data.",
    "INV34-002477": "The EOWR collection path currently catches cost-query exceptions and supplies an empty cost list, making query failure indistinguishable from a successful query with no cost rows. A product decision is needed: fail the report, or retain an explicit unavailable/error state for only the cost section. There is no production cost report consumer contract in this path that authorizes treating DB failure as no rows.",
    "INV34-002634": "A watermark is optional report-branding metadata; absence suppresses only the watermark and does not affect measurement or report content fields.",
    "INV34-002784": "The flag is a computed boolean consistency result; invalid ownership candidates are counted and excluded before any proposed attribution is applied.",
    "INV34-002787": "`applied` records the count of rows actually changed; commit is correctly conditional on a nonzero write count, not on a scope or identifier.",
    "INV34-002797": "`changed` compares the new section identity to the selected identity; dependent report state is cleared only when section identity changes, while same-ID payload refresh is handled separately.",
    "INV34-002798": "`changed` compares well identity; changing the well clears all descendant wellbore/section/report context, whereas same-ID data refresh does not.",
    "INV34-002799": "`changed` compares wellbore identity; changing the wellbore clears only descendant section/report context, preserving the selected well.",
    "INV34-002812": "Unreadable or malformed optional standards configuration falls back to the module's explicit configured default; it does not convert a drilling measurement to zero. The resulting default policy is visible through standards accessors.",
    "INV34-002892": "Unit normalization preserves the original value when conversion is unsupported and documents that downstream validation will flag it; it does not silently return a converted zero or mark conversion successful.",
    "INV34-002961": "A failed numeric parse contributes to the text type bucket for workbook-layout consistency scoring; the source cell remains unchanged and this is not canonical measurement conversion.",
    "INV34-002962": "A failed numeric parse is classified as text while evaluating header-row layout; values are not accepted as numeric engineering inputs here.",
    "INV34-002984": "Survey inclination is checked against the inclusive 0-to-180 degree domain; zero is a valid vertical survey angle.",
    "INV34-002987": "Longitude is checked against the inclusive geographic range -180 to 180; zero is valid and is not treated as missing.",
    "INV34-002988": "Latitude is checked against the inclusive geographic range -90 to 90; zero is valid and is not treated as missing.",
    "INV34-003022": "This returns stripped optional text as text and maps only blank text to None. The explicit string `\"0\"` remains a nonblank string. Same expression is also recorded at INV34-007888.",
    "INV34-003026": "`fraction` is a regex match object for a recognized fraction syntax, not an engineering quantity whose numeric zero is tested for presence.",
    "INV34-003027": "`mixed` is a regex match object for a recognized mixed-number syntax; successful parsing may produce numeric zero without the match condition confusing presence.",
    "INV34-003028": "No recognized numeric syntax is explicitly the invalid-text path; it returns an unknown/invalid conversion result instead of zero.",
    "INV34-003036": "A failed parse format advances to the next declared date format; if all formats fail, the converter returns None rather than a fabricated date.",
    "INV34-003037": "A failed datetime format advances to the next declared format; exhaustion remains an invalid/unknown result, not a zero datetime.",
    "INV34-003151": "The application entry point checks for a missing casing-history repository and displays that history cannot be opened before constructing this dialog. The optional `None -> []` guard is defensive for standalone/test construction; the live UI does not tell a database failure that no records exist.",
    "INV34-003162": "The application entry point checks for a missing cement-history repository and displays that history cannot be opened before constructing this dialog. The optional `None -> []` guard is defensive for standalone/test construction; the live UI does not tell a database failure that no records exist.",
    "INV34-003280": "`prev_survey` is optional prior survey data used only to prefill the preview; an absent/empty prior survey disables that preview and does not seed a survey measurement.",
    "INV34-003453": "`existing` is the repository lookup result for a company name; the branch handles an existing entity, not a numeric measurement or zero-valued key.",
    "INV34-003462": "`existing` is the repository lookup result for project identity; a found entity is rejected as a duplicate before insertion.",
    "INV34-003467": "The create result is the repository's success/entity result; the dialog closes only after success and displays validation/error state otherwise. This is not a numeric engineering measurement default.",
    "INV34-003469": "`existing` is a repository entity lookup for a well; the branch prevents duplicate creation and does not test an optional numeric well field.",
    "INV34-007651": "Source-table name is optional extraction provenance metadata; absent or blank table labels become None without changing the extracted cell values or table geometry.",
    "INV34-007686": "Historical search uses parameters for the explicit current report only; no parameters means an empty comparison context, not zero drilling parameters. Search identity remains the supplied report ID and its well.",
    "INV34-007691": "A missing related well produces a blank metadata mapping for report rendering; it does not replace a well ID or engineering quantity. Well/report relationship is persisted separately and lookup exceptions are not swallowed here.",
    "INV34-007708": "A missing related well produces a blank metadata mapping for EOWR rendering; it does not replace a well ID or cost amount. Lookup exceptions are not swallowed by this expression.",
    "INV34-007710": "Duplicate scanner capture of the exact EOWR cost-query `except Exception` already recorded at INV34-002477; the underlying query-failure-versus-no-rows question is recorded once there.",
    "INV34-007727": "A missing related well produces a blank metadata mapping for NPT report rendering; it does not replace a well ID or NPT hours. Lookup exceptions are not swallowed by this expression.",
    "INV34-007741": "A missing related well produces a blank metadata mapping for cost report rendering; it does not replace a well ID or cost amount. Lookup exceptions are not swallowed by this expression.",
    "INV34-007746": "A missing related well produces a blank metadata mapping for plan report rendering; it does not replace a well ID or plan value. Lookup exceptions are not swallowed by this expression.",
    "INV34-007762": "Rule mis-fire: this is a docstring describing that resolve_transition may return None; it is not an executable default expression.",
    "INV34-007850": "The row adapter accepts an optional row mapping and copies an absent mapping as empty input; each absent field remains absent and no field-specific value is invented.",
    "INV34-007856": "Rule mis-fire: the reported text is a docstring explaining header detection, not executable behavior.",
    "INV34-007874": "SafetyValidator has no in-repository caller. Its BOP date branch is an explicit no-op despite the comment saying validation checks dates. The active safety widget independently uses configured test intervals and NOT ASSESSED handling, so there is no demonstrated current user-visible production path through this helper. Owner decision: either retire the dead validation branch or define/wire its date-validation contract; no interval/date rule is invented here.",
    "INV34-007888": "Duplicate scanner capture of the same `return text or None` expression as INV34-003022; blank optional text maps to None and literal string zero is retained.",
    "INV34-007935": "The importer filters metadata/non-business keys from its meaningful-data decision; this prevents worksheet labels and formatting-only data from being treated as a canonical drilling record.",
    "INV34-007953": "Project location is optional descriptive text; blank input persists as NULL/None, not a geographic coordinate or numeric zero.",
    "INV34-007954": "Project manager is optional descriptive text; blank input persists as NULL/None, not an employee identifier zero.",
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
    items = []
    for record in records:
        ident = record["id"]
        items.append({
            "id": ident, "file": record["file"], "line": record["line"],
            "symbol": record.get("symbol"), "rule": record.get("rule"), "kind": record.get("kind"),
            "register_line_text": record.get("current_source_line"),
            "classification": CLASSIFICATION[ident],
            "evidence": (
                f"Hash-anchored source {record['file']}:{record['line']} "
                f"`{record['current_source_line'].strip()}`; source_sha256={record['source_sha256']}; "
                f"context_fingerprint={record['context_fingerprint']}. {NOTES[ident]}"
            ),
            "defect": CLASSIFICATION[ident] == DEF,
            "remaining_question": (
                "Report policy for distinguishing cost-query failure from an empty cost collection"
                if ident == "INV34-002477" else
                "SafetyValidator date-validation ownership/contract (helper currently has no in-repository caller)"
                if ident == "INV34-007874" else None
            ),
            "site": {"file": record["file"], "line": record["line"],
                     "symbol": record.get("symbol"), "expression": record.get("current_source_line"),
                     "source_sha256": record["source_sha256"],
                     "context_fingerprint": record["context_fingerprint"]},
        })
    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": "phase-2 mixed review: report collection and metadata fallback, hierarchy/scope selection, validation, import normalization and engineering dialogs",
        "records": len(items), "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": dict(Counter(r["file"] for r in records)),
        "by_classification": counts,
        "defects_fixed": [{
            "id": "NEW-P6-022", "file": "core/validators.py", "site": "BulkValidator.validate current_stock reconciliation",
            "test": "tests/test_bulk_validator_zero.py",
            "summary": "Removed the explicit-zero exemption from stock mismatch validation. With known opening/receipts/usage, a closing stock of 0 is compared to the calculated expected stock; unknown opening/current stock remains outside the reconciliation. The helper has no in-repository production caller, so this corrects its exposed validation contract without claiming a live UI impact."
        }],
        "new_findings": [
            {"id": "NEW-P6-023", "line": 480, "severity": "LOW", "status": "DOMAIN_DECISION_REQUIRED", "file": "core/validators.py", "site": "SafetyValidator.validate last_rams_test branch",
             "summary": "The last-RAMS-test branch is a no-op; no in-repository caller exists. The active safety widget has independent configured-interval/NOT ASSESSED behavior. Decide whether the legacy helper should be retired or given an explicit date-validation contract before wiring it into a live path.",
             "evidence": "core/validators.py:475-482 and repository-wide search: no SafetyValidator callers; tabs/w8_Safety_Widget.py has configured interval logic and unknown-state UI."},
            {"id": "NEW-P6-024", "line": 774, "severity": "MEDIUM", "status": "DOMAIN_DECISION_REQUIRED", "file": "core/report_engine.py", "site": "EOWRReportEngine._collect_data cost-record query exception",
             "summary": "Broad exception handling converts a failed cost query into the same empty collection used for a successful zero-row query. Define whether report generation should fail or mark the cost section unavailable while retaining non-cost report data.",
             "evidence": "core/report_engine.py:774-777; duplicate scanner record INV34-007710; no source/test evidence establishes the intended partial-report/error presentation."}
        ],
        "observations": [
            {"topic": "unknown, zero and range semantics", "summary": "Inclusive survey/geographic bounds admit legitimate zero values; string zero survives text normalization; stock reconciliation now compares explicit zero only when both sides of the ledger are known. SQL NULL/missing remains outside that comparison."},
            {"topic": "scope selection and attribution", "summary": "Selection changes clear only descendants; same-identity refreshes are separately emitted. Scope attribution counts invalid ownership chains and commits only when writes occurred. This does not equate cumulative scope with whole-well scope."},
            {"topic": "consumer reachability", "summary": "Casing/cement history entry points reject a missing repository before opening dialogs; SafetyValidator and BulkValidator have no in-repository production callers. Findings distinguish exposed helper contracts from demonstrated live product impact."}
        ],
        "sibling_search": [
            {"family": "zero-versus-missing validator paths", "result": "BulkMaterials documents SQL NULL as missing and 0.0 as explicit reported zero. BulkValidator uses `is not None` to enter numeric validation; the previous `current != 0` exception was the isolated mismatch-suppression sibling. Added tests cover explicit zero mismatch, matching zero ledger and unknown NULL values."},
            {"family": "BOP interval validation", "result": "SafetyValidator has no in-repository caller. tabs/w8_Safety_Widget.py uses configured interval policy and displays NOT ASSESSED for unavailable test dates. No change was made to the independent active widget or domain interval policy."},
            {"family": "report lookup fallback", "result": "The five `get_well_by_id(...) or {}` branches only build optional report metadata; `None` does not become an engineering zero. Exceptions from the lookup are not handled by these expressions. Cost query exception semantics remain an owner decision."},
            {"family": "source review tooling", "result": "The M34 fingerprint-ledger file expected by its manifest is absent; source SHA, line, symbol and expression anchoring are verified, but unavailable original fingerprint patterns are not fabricated."}
        ],
        "tests": {
            "passed": [
                "184 passed, 2 deselected: focused run covering BulkValidator/unknown stock, MinerU, report lifecycle/snapshots, scope attribution/selection/ownership, unit preservation, hierarchy and safety/business regressions. Includes tests/test_bulk_validator_zero.py; full command is recorded in the session verification.",
                "69 passed: tests/test_mineru_engine.py tests/test_mineru_timeout_zero.py tests/test_report_lifecycle.py tests/test_report_snapshot.py.",
                "Ruff --select E722,F821 on changed source/tests/audit tool, compileall and git diff --check are recorded at final verification."
            ],
            "environment_blocked": [
                "Six Qt-backed tests failed before exercising assertions because PySide6 could not load missing system library libGL.so.1: tests/test_bulk_stock_three_state_smoke.py (1), tests/test_history_well_scope.py (2), tests/test_whole_well_scope_labels_m25.py (1), and tests/test_m28_finance_safety_plan.py (2). Selection-manager module reported 17 skips. No GUI/Qt end-to-end workflow, production database, real DDR report corpus, or safety-widget deployment acceptance is claimed."
            ],
            "mutation": "Temporarily restored the original `and current != 0` condition and reran tests/test_bulk_validator_zero.py: the explicit-zero mismatch regression failed (1 failed, 1 passed); the production fix was restored and the focused tests pass."
        },
        "head": "e6a1ffb23a7641d09ad0a94e693b879de45ec612", "commit": None, "evidence_commit": None,
        "evidence_files": ["core/validators.py", "tests/test_bulk_validator_zero.py", "tools/m36/p6_batch_026.py", "docs/audits/m36-evidence/p6-batch-026.json"],
        "staleness": {
            "checked": len(records), "stale": len(reanchored),
            "re_anchored": len(reanchored),
            "method": "All recorded source hashes were resolved to provenance tree 7f0186e3e6ac966f1fe9cbd804785129b9246fbe; recorded lines/symbols were checked, and changed-current-file mappings were verified by the ledger-aware provenance helper. The manifest-listed M34 item ledger is absent, so only reproducible source fingerprints are asserted.",
            "re_anchored_items": [
                {"id": ident, "file": path, "previous_site": f"{path}:{old}", "current_site": f"{path}:{new}", "tree": tree, "source_sha256": next(r["source_sha256"] for r in records if r["id"] == ident), "context_fingerprint": next(r["context_fingerprint"] for r in records if r["id"] == ident), "reason": "Hash-verified recorded site was mapped to its current enclosing symbol/expression."}
                for ident, path, old, new, tree in reanchored
            ],
            "provenance_trees": stats["trees"],
            "m34_fingerprint_ledger": {
                "manifest": "docs/audits/m34-evidence/M34_INVENTORY_LEDGER.json",
                "expected_path": "docs/audits/m34-evidence/m34-ledger.json",
                "expected_sha256": "d81a77bda0330c75493f4081c4a02e4d106fe7602e49c14f0c67d12977658a6b",
                "expected_bytes": 11394989, "present_in_workspace": False,
                "effect": "Missing item ledger prevents reproduction of some historical context fingerprints; source hash, line and symbol evidence is kept distinct and no fingerprint result is fabricated."
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
        "method": "Trace producer, transformation, caller/consumer, contract and tests; distinguish current production reachability from exposed utility behavior; preserve unknown-versus-zero and hierarchical scope; record unresolved product policy instead of inventing it.",
        "items": items
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={counts}; reanchors={len(reanchored)} fingerprints={stats['fingerprints_verified']}/{len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
