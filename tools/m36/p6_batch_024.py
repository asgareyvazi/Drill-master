#!/usr/bin/env python3
"""Evidence-backed P6 adjudication for batch 024."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-024"
VC, INT, DUP, DDD, DEF = (
    "VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
    "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT",
)
sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

SOURCE_TREES = {
    "core/data_quality.py": "7f0186e3e6ac966f1fe9cbd804785129b9246fbe",
    "tabs/w3c_section_data.py": "7f0186e3e6ac966f1fe9cbd804785129b9246fbe",
}
CLASSIFICATION = {
    "INV34-006773": VC, "INV34-006774": VC, "INV34-006779": VC,
    "INV34-000072": VC,
    "INV34-006790": VC, "INV34-006791": VC, "INV34-006792": VC,
    "INV34-006793": VC, "INV34-006794": VC, "INV34-006795": VC,
    "INV34-006811": VC, "INV34-008983": VC,
    "INV34-006816": DUP,
    "INV34-000234": INT,
    "INV34-006841": DEF,
    "INV34-001133": INT, "INV34-007340": INT,
    "INV34-007350": VC,
    "INV34-008296": VC, "INV34-008303": VC, "INV34-008311": INT,
    "INV34-005398": DDD, "INV34-005449": VC, "INV34-005450": VC,
    "INV34-005452": INT, "INV34-005455": VC, "INV34-005456": VC,
    "INV34-005457": VC, "INV34-005458": VC, "INV34-005459": VC,
    "INV34-005478": INT, "INV34-005479": DUP, "INV34-005483": INT,
    "INV34-008315": VC, "INV34-008317": VC, "INV34-008322": VC,
    "INV34-005532": INT, "INV34-005536": INT,
    "INV34-005706": VC, "INV34-005709": DEF, "INV34-005715": VC,
    "INV34-005717": VC, "INV34-008336": VC, "INV34-008358": VC,
    "INV34-008359": VC,
}
NOTES = {
    "INV34-006773": "Startup stops and exits if first-run credential setup is declined or fails; this is a fail-closed gate, not a truthiness-based data value.",
    "INV34-006774": "The database initializer has an explicit boolean success contract; failure displays diagnostics and terminates startup before using an uninitialized database.",
    "INV34-006779": "The package smoke returns failure if the temporary database cannot initialize or its schema version is wrong; the boolean is a gate, not a domain measurement.",
    "INV34-000072": "An empty model name is rejected by the settings writer; model discovery and advisory AI are opt-in and deterministic imports do not depend on it.",
    "INV34-006790": "Selection metadata is optional UI context; `{}` represents no selected well data and is not passed as a numeric or whole-well value.",
    "INV34-006791": "Selection metadata is optional UI context; `{}` does not claim a section was found and section identity remains separately nullable.",
    "INV34-006792": "Selection metadata is optional UI context; `{}` does not imply a selected report or substitute a report id.",
    "INV34-006793": "A missing well payload is normalized to empty UI metadata; the identity and pending-load guard remain separate.",
    "INV34-006794": "A missing section payload is normalized to empty UI metadata; it does not broaden a section query.",
    "INV34-006795": "A missing report payload is normalized to empty UI metadata; report selection remains an independent id.",
    "INV34-006811": "`review_item` accepts absent source-location metadata and builds an empty lineage object while keeping field/value and review status separate.",
    "INV34-008983": "Missing confidence is explicitly normalized to zero certainty; actual zero is preserved and the method remains advisory/review metadata, not an engineering value.",
    "INV34-006816": "Rule mis-fire: the `or None` phrase is in the `get_field_spec` docstring, whose contract explicitly says the lookup returns `None` when absent.",
    "INV34-000234": "Unreadable or malformed optional company-template files are skipped; unknown mappings retain passthrough values with zero/low confidence for review rather than being asserted as canonical.",
    "INV34-006841": "The old orphan loop never incremented its counter and always returned 100/good. A raw SQLite child row with a dangling FK reproduced the false-good result. The new `PRAGMA foreign_key_check` reports table/row/parent/index evidence; query failure is `None/unknown`, never a pass. Regression tests cover clean, violated, and unavailable-query states.",
    "INV34-001133": "SQLite `wal_checkpoint(TRUNCATE)` returns an integer busy flag; nonzero means an active reader/writer and reset refuses before replacing the configured database.",
    "INV34-007340": "The candidate database must initialize successfully before promotion; a false result aborts and preserves the existing file.",
    "INV34-007350": "The canonical review-row boundary accepts an optional payload and creates an empty row only for absent input; review defaults remain explicit and no engineering measurement is created.",
    "INV34-008296": "The table row is ignored only if a required time widget is structurally absent; normal UI rows create both widgets, and values are read from their typed time API.",
    "INV34-008303": "Copying report data is blocked unless the target report lifecycle state is editable; this protects finalized reports rather than treating status as a numeric truth value.",
    "INV34-008311": "`class LogData: pass` is a local carrier type populated immediately from a validated dialog result; it is not a swallowed production failure.",
    "INV34-005398": "The 5-inch pipe-OD fallback feeds the annular-velocity engine and visible calculated result when no pipe OD is sourced. It is not labeled as an assumption. Whether 5 inches is an approved default for this UI is not established; retained as an owner decision, not treated as verified engineering input.",
    "INV34-005449": "Missing well display metadata falls back to the selected well id for a label only; it does not alter query scope or persist a name.",
    "INV34-005450": "Validation returns an error list; a non-empty list blocks the save path and an empty list means no form errors.",
    "INV34-005452": "Optional chemical quantities use `None` at the row-builder API; loaded-source provenance and explicit-edit tracking distinguish missing from a real zero downstream.",
    "INV34-005455": "Every chemical row is created with a product widget; if a malformed UI row lacks it, collection produces a blank identity that the required-product validator rejects before persistence.",
    "INV34-005456": "Every chemical row is created with a type widget; unresolved types are preserved and surfaced as a review issue rather than treated as a trusted category.",
    "INV34-005457": "Every chemical row is created with a received widget; source-null values are restored from provenance when untouched, while edited values are distinct.",
    "INV34-005458": "Every chemical row is created with a type widget; absent/malformed rows are guarded, and normal loading preserves the source category and review state.",
    "INV34-005459": "Every chemical row is created with a unit widget; an empty selection normalizes to `None`, not a fabricated unit.",
    "INV34-005478": "Matplotlib is an optional plotting dependency; import failure selects the documented no-plot fallback while calculations remain independent.",
    "INV34-005479": "Duplicate capture of the same optional-Matplotlib import fallback block; the assignment records capability false and does not catch or suppress a calculation error.",
    "INV34-005483": "Malformed imported pit-volume JSON clears only the derived text display; the original `_pit_volumes_json` payload is retained and passed through on save.",
    "INV34-008315": "A blank pump-liner text field is represented as `None`; the optional field is not converted to a numeric zero or a fabricated size.",
    "INV34-008317": "The bit number is a required identifier; blank input is rejected before save.",
    "INV34-008322": "Blank chemical unit is normalized to `None`; the row remains reviewable and does not inherit an arbitrary physical unit.",
    "INV34-005532": "Dark-mode truthiness selects presentation colors only; it does not change data, geometry, or calculation inputs.",
    "INV34-005536": "Database target depth is a nullable numeric column. A non-conforming legacy string falls back only in the editable display; the schematic builder reads authoritative database geometry and the control is not saved automatically.",
    "INV34-005706": "The read-only flag is a UI widget configuration guard; it does not omit or convert the material values.",
    "INV34-005709": "Re-anchored from the recorded whole-well lookup to the current section-scoped `get_cement_report(section_id=...)` path (scope fix in 6c07d3). Semantic sweep of its consumer exposed a separate loss: nullable cement/casing fields were displayed as numeric defaults and those defaults were saved over SQL NULL. Both tabs now capture source/display baselines and restore untouched source values; explicit edits still persist, including zero. Qt round-trip coverage is added but is locally blocked by missing libGL.",
    "INV34-005715": "A table item existence guard protects the style/renumbering operation; a missing presentation cell is skipped, not translated into a domain quantity.",
    "INV34-005717": "Empty failure-report text produces empty wrapped HTML rather than an invented narrative; non-empty text is escaped/wrapped by the shared helper.",
    "INV34-008336": "Without a database or selected well, the service-company table is cleared and returns; this is a scope guard, not a whole-well fallback.",
    "INV34-008358": "Same empty-text guard in failure-report HTML generation; the report body remains blank when no source narrative exists.",
    "INV34-008359": "Whitespace-only paragraphs are kept as blank layout lines; they do not become factual report content.",
}

# Two records changed semantically at their source line after capture / during this
# batch. Their original source hash, line, symbol and fingerprint are checked against
# the original tree, then their current method/expression anchors are verified here.
SPECIAL = {
    "INV34-006841": ("core/data_quality.py", "DataQualityService.for_report",
                     'violations = session.execute(text("PRAGMA foreign_key_check")).fetchall()'),
    "INV34-005709": ("tabs/w3c_section_data.py", "CementReportTab.load_data",
                     "data = ("),
}


def verify_special(record: dict) -> dict:
    path, symbol, current_line = SPECIAL[record["id"]]
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
    matches = [i + 1 for i, text in enumerate(current)
               if text.strip() == current_line and cstart <= i + 1 <= cend]
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
        "reason": "Original source hash/line/symbol/fingerprint are verified in the recorded tree; source expression changed in a reviewed fix and the current consumer anchor is manually re-attested.",
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
    stats["trees"]["tabs/w3c_section_data.py"] = (
        f"provenance tree = {SOURCE_TREES['tabs/w3c_section_data.py']} "
        "(blob sha256 equals all seven recorded source hashes; later section-scope change is in 6c07d3)"
    )
    stats["trees"]["core/data_quality.py"] = (
        f"provenance tree = {SOURCE_TREES['core/data_quality.py']} "
        "(blob sha256 equals the recorded source hash; current working source includes the reviewed fix)"
    )
    moved = [verify_special(by_id[key]) for key in SPECIAL]
    counts = dict(Counter(CLASSIFICATION.values()))
    items = []
    for record in records:
        ident = record["id"]
        note = NOTES[ident]
        items.append({
            "id": ident, "file": record["file"], "line": record["line"],
            "symbol": record.get("symbol"), "rule": record.get("rule"), "kind": record.get("kind"),
            "register_line_text": record.get("current_source_line"),
            "classification": CLASSIFICATION[ident],
            "evidence": (
                f"Hash-anchored source {record['file']}:{record['line']} "
                f"`{record['current_source_line'].strip()}`; source_sha256={record['source_sha256']}; "
                f"context_fingerprint={record['context_fingerprint']}. {note}"
            ),
            "defect": CLASSIFICATION[ident] == DEF,
            "remaining_question": (
                "Does the UI's annular-velocity output permit the conventional 5-inch OD when the selected well has no pipe OD, and if so how must the assumption be labeled?"
                if ident == "INV34-005398" else None
            ),
            "site": {"file": record["file"], "line": record["line"],
                     "symbol": record.get("symbol"), "expression": record.get("current_source_line"),
                     "source_sha256": record["source_sha256"],
                     "context_fingerprint": record["context_fingerprint"]},
        })

    manual_reanchors = {r["id"]: r for r in moved}
    current_lines = (ROOT / "tabs/w3c_section_data.py").read_text(encoding="utf-8").splitlines()
    items_by_id = {r["id"]: r for r in items}
    items_by_id["INV34-005709"]["current_site"] = manual_reanchors["INV34-005709"]["current_site"]
    items_by_id["INV34-005709"]["current_source_line"] = manual_reanchors["INV34-005709"]["current_source_line"]
    items_by_id["INV34-006841"]["current_site"] = manual_reanchors["INV34-006841"]["current_site"]
    items_by_id["INV34-006841"]["current_source_line"] = manual_reanchors["INV34-006841"]["current_source_line"]

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": "phase-2 mixed review: application gates, optional AI/import mapping, database reset/import contracts, W2 report editability, W3 drilling inputs, W3c section scope and data quality",
        "records": len(items), "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": dict(Counter(r["file"] for r in records)),
        "by_classification": counts,
        "defects_fixed": [
            {"id": "NEW-P6-017", "file": "core/data_quality.py", "site": "DataQualityService.for_report", "test": "tests/test_data_quality_orphan_integrity.py", "summary": "Replace the hard-coded 100/good orphan claim with SQLite foreign_key_check evidence and unknown-on-query-failure behavior."},
            {"id": "NEW-P6-018", "file": "tabs/w3c_section_data.py", "site": "CementReportTab/CasingReportTab load-save round trip", "test": "tests/test_cement_report_null_roundtrip.py", "summary": "Preserve nullable source fields when displayed defaults are untouched; explicit edits remain distinguishable and persist."},
        ],
        "new_findings": [
            {"id": "NEW-P6-019", "file": "tabs/w3_drilling_report.py", "line": 769, "severity": "MEDIUM", "status": "domain decision required; not patched", "summary": "Annular velocity uses a 5-inch pipe OD when no sourced drill-pipe OD exists (and replaces a zero OD with 5). The value feeds a visible engineering result but is not marked as an assumption.", "records": ["INV34-005398"], "impact": "The displayed annular velocity may be materially wrong for a different actual pipe geometry."},
            {"id": "NEW-P6-020", "file": "tabs/w3c_section_data.py", "line": 191, "severity": "MEDIUM", "status": "domain decision required; not patched", "summary": "Cement material Inventory is recalculated as Received minus Consumed, ignoring the Backload field and any opening stock. A domain owner must define whether it is a per-report derived remainder or a true closing balance before changing the formula.", "records": ["INV34-005706"], "impact": "Editing a receipt/consumption can overwrite the existing inventory with a different semantic total."},
        ],
        "observations": [
            {"topic": "orphan integrity", "summary": "The check is database-wide and reports actual SQLite FK violations with bounded row details; an unavailable check is unknown. The existing summary excludes unknown values from its score."},
            {"topic": "W3c nullable round-trip", "summary": "Both CementReportTab and CasingReportTab rendered SQL NULLs as plausible widget values, then wrote them back. New baseline/touched tracking restores unchanged source values; explicitly edited fields, including zero, are not restored."},
            {"topic": "scopes", "summary": "The current W3c cement reader is section-scoped after the earlier scope fix; the record's original whole-well expression is retained as provenance and manually mapped to the current consumer. No global report id was substituted."},
            {"topic": "material inventory", "summary": "The UI formula is Received minus Consumed. Backload and opening stock do not participate; no in-repository domain contract resolves the correct balance semantics, so no formula was invented."},
        ],
        "sibling_search": [
            {"family": "database integrity claims", "result": "Checked stored FK state (not merely current FK enforcement). Clean, orphaned and failed-query branches have regression coverage; no other hard-coded orphan pass remains in DataQualityService.for_report."},
            {"family": "nullable W3c report fields", "result": "Reviewed CementReportTab and CasingReportTab producer→widget→save paths and added unchanged-source preservation for scalar/text fields. JSON row payload behavior was not expanded into a separate migration in this batch."},
            {"family": "drilling pipe geometry defaults", "result": "The 5-inch OD fallback participates in the annular-velocity engine input, unlike renderer-only schematic fallbacks; it remains an owner decision until an approved default/label contract is established."},
            {"family": "application and scope guards", "result": "Initializer results guard process startup/reset; UI context empty mappings remain separate from well/section/report IDs; report lifecycle gating blocks copy to finalized reports."},
        ],
        "tests": {
            "passed": [
                "4 passed, 1 skipped: tests/test_data_quality_orphan_integrity.py tests/test_cement_report_null_roundtrip.py (Qt integration test skipped locally because PySide6 cannot load libGL.so.1; pure preservation and all data-quality tests passed).",
                "75 passed: tests/test_m31_scenarios.py excluding five Qt widget tests blocked by libGL.so.1.",
                "20 passed: tests/test_report_scope_metadata_m25.py tests/test_operational_time_integrity.py; this also independently verifies batch-022's previously unverified 20-test claim.",
                "13 passed: tests/test_credential_lifecycle.py -k 'reset and not gui'.",
                "2 passed: tests/test_engineering_ground_truth.py -k CompanyTemplateMapping.",
                "Ruff --select E722,F821, compileall, and git diff --check passed for changed production/test/tool files.",
            ],
            "environment_blocked": [
                "Five Qt tests in the complete tests/test_m31_scenarios.py run failed before assertions because PySide6 could not load system libGL.so.1; 75 non-Qt tests passed.",
                "The new Cement/Casing nullable round-trip integration test is collected but skipped locally for the same missing libGL.so.1; exact-HEAD GitHub CI with real Qt libraries must execute it.",
            ],
            "mutation": "Orphan regression was run before the fix: the clean case had no evidence and the injected orphan incorrectly returned 100/good; after the fix, clean/orphan/query-failure tests pass. The SQL-NULL UI mutation is source-proven (old widget fallback flowed into save) and the new Qt regression asserts unchanged NULL plus explicit zero; local runtime is blocked, so CI is required before treating that path as executed.",
        },
        "head": "db5fbbb", "commit": None, "evidence_commit": None,
        "evidence_files": ["core/data_quality.py", "tabs/w3c_section_data.py", "tests/test_data_quality_orphan_integrity.py", "tests/test_cement_report_null_roundtrip.py", "tools/m36/p6_batch_024.py", "docs/audits/m36-evidence/p6-batch-024.json"],
        "staleness": {
            "checked": len(records), "stale": len(reanchored) + len(moved),
            "re_anchored": len(reanchored) + len(moved),
            "method": "All source hashes, recorded lines, enclosing symbols and current mappings were verified. The ledger-free context-fingerprint check reproduced 41/45; four hash-anchored fingerprints did not reproduce because the 11.4 MB M34 item ledger named by its manifest is absent. Two changed source expressions were manually re-anchored with their original fingerprint proof plus current method/expression verification. The four unreproduced fingerprints are explicitly listed and are not claimed as verified.",
            "re_anchored_items": [
                {"id": ident, "file": path, "previous_site": f"{path}:{old}", "current_site": f"{path}:{new}", "tree": tree, "source_sha256": by_id[ident]["source_sha256"], "context_fingerprint": by_id[ident]["context_fingerprint"], "reason": "Exact source expression, original hash and fingerprint verified; line map verified current scope."}
                for ident, path, old, new, tree in reanchored
            ] + moved,
            "provenance_trees": stats["trees"],
            "m34_fingerprint_ledger": {
                "manifest": "docs/audits/m34-evidence/M34_INVENTORY_LEDGER.json",
                "expected_path": "docs/audits/m34-evidence/m34-ledger.json",
                "expected_sha256": "d81a77bda0330c75493f4081c4a02e4d106fe7602e49c14f0c67d12977658a6b",
                "expected_bytes": 11394989,
                "present_in_workspace": False,
                "effect": "The ledger-free recorded-line/AST proof reproduces 41/45 P6 fingerprints; four remain hash/line/symbol-anchored but their original M34 pattern cannot be recovered or fingerprint-reproduced here.",
            },
            "fingerprint_proof": {"checked": stats["fingerprints_checked"] + len(moved), "verified": stats["fingerprints_verified"] + len(moved), "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"], "records_without_a_reproducing_fingerprint_but_hash_anchored": stats["fingerprints_not_reproduced_but_hash_anchored"], "symbol_forms_that_reproduced": stats["fingerprints_by_form"], "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"], "method": stats["ledger_mode"] + "; two source-changed records were separately proven by the same recorded-line/AST method"},
        },
        "method": "Trace source/input through normalization, query or engine, UI/report and persistence; distinguish unknown from zero and selected report/section/well scope; fix only reproducible defects and retain unresolved engineering contracts as owner decisions.",
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={counts}; reanchors={len(reanchored) + len(moved)} fingerprints={stats['fingerprints_verified'] + len(moved)}/{len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
