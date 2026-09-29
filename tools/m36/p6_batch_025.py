#!/usr/bin/env python3
"""Evidence-backed P6 adjudication for batch 025."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-025"
VC, INT, DUP, DDD, DEF = (
    "VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
    "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT",
)
sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

SOURCE_TREES = {
    "core/excel_intelligence.py": "7f0186e3e6ac966f1fe9cbd804785129b9246fbe",
    "core/mineru_engine.py": "7f0186e3e6ac966f1fe9cbd804785129b9246fbe",
}
CLASSIFICATION = {
    "INV34-007354": VC, "INV34-007355": VC,
    "INV34-001406": VC, "INV34-001408": VC, "INV34-001413": INT,
    "INV34-008700": VC,
    "INV34-007409": VC, "INV34-007410": VC, "INV34-007411": VC,
    "INV34-001783": VC, "INV34-007541": INT, "INV34-007542": INT,
    "INV34-007543": INT,
    "INV34-001810": VC, "INV34-001850": VC, "INV34-001851": VC,
    "INV34-001890": INT, "INV34-001891": INT,
    "INV34-007546": VC, "INV34-007547": VC, "INV34-007548": VC,
    "INV34-007549": VC, "INV34-007552": VC, "INV34-007555": DUP,
    "INV34-009659": DUP,
    "INV34-001899": INT, "INV34-007562": INT,
    "INV34-007563": DUP,
    "INV34-001904": VC, "INV34-001905": INT, "INV34-001907": INT,
    "INV34-001908": INT, "INV34-007566": DUP,
    "INV34-002058": VC, "INV34-002060": VC, "INV34-002061": VC,
    "INV34-002064": VC, "INV34-002107": VC,
    "INV34-002147": VC, "INV34-002148": VC, "INV34-002160": VC,
    "INV34-002161": VC, "INV34-002162": DEF,
    "INV34-002202": INT, "INV34-002208": INT,
}
NOTES = {
    "INV34-007354": "`records` is an optional input list at the review-lineage adapter; absent payloads yield no enrichment and do not create a persisted record.",
    "INV34-007355": "`items` is an optional input list at the same adapter boundary; an absent review collection remains empty rather than raising or becoming a value.",
    "INV34-001406": "Pandas `DataFrame.empty` is an explicit row/column emptiness contract; non-empty confident rows alone enter mapping.",
    "INV34-001408": "Pandas `DataFrame.empty` guards the optional extracted TSV table before it is added to the document; no values are defaulted.",
    "INV34-001413": "UTF-8 decode failure selects the next declared CSV encoding; all candidate encodings are tried before an unsupported-encoding error, while successful rows retain the selected encoding metadata.",
    "INV34-008700": "The editor snapshot excludes a read-only QTextEdit from writable state; derived display text cannot silently enter Save All persistence.",
    "INV34-007409": "An absent allowlist means no section-name filter; when names exist, only the requested section is selected.",
    "INV34-007410": "Same optional section-name filter for a second loader; empty names mean all sections, not a missing numeric input.",
    "INV34-007411": "Same optional section-name filter for a third loader; section identity and loaded-context checks remain separate.",
    "INV34-001783": "A wrapper may be called without positional arguments; `parent=None` is only for an optional error-dialog parent and does not hide the exception (logging/default behavior remains explicit).",
    "INV34-007541": "`DatabaseError` is a named exception type with no additional methods; `pass` is the required empty class body.",
    "INV34-007542": "`ValidationError` is a named exception type with no additional methods; `pass` is the required empty class body.",
    "INV34-007543": "`DataImportError` is a named exception type with no additional methods; `pass` is the required empty class body.",
    "INV34-001810": "Excel row index zero is a sentinel for missing location in the nearby-cell search; real worksheet rows are one-based. The original RawCell location/provenance is retained separately.",
    "INV34-001850": "A true conflict flag appends the alternate source/value to field provenance; it does not overwrite the chosen canonical value.",
    "INV34-001851": "A true duplicate flag records a duplicate-same-value audit entry and source location; it does not alter the primary mapping.",
    "INV34-001890": "A nonnumeric candidate receives a low compatibility score, not an accepted canonical measurement; deterministic normalization/validation is downstream authority.",
    "INV34-001891": "A value outside the score's numeric unit heuristic gets a reduced score; the exception is local scoring fallback, not value coercion.",
    "INV34-007546": "A label in the preferred anchor is not accepted as its own field value; the matcher searches only within the anchored row and stops at the next label boundary.",
    "INV34-007547": "A neighboring label is treated as a structural boundary, preventing extraction from wandering into another table.",
    "INV34-007548": "A merged label is not treated as a value; a rightward search is bounded by labels and canonical type validation.",
    "INV34-007549": "Same label-boundary guard for the right-side candidate path; only a non-label source value is proposed.",
    "INV34-007552": "An absent template becomes empty configuration; candidate values remain unresolved/reviewable and no field values are invented.",
    "INV34-007555": "Rule mis-fire: the `or None` wording is in `_assemble_date`'s docstring, describing its actual return contract.",
    "INV34-009659": "Duplicate scanner capture of `raw_cell.location.row or 0` at the same Excel label-search site as INV34-001810; the row fallback is a search sentinel, not a stored value.",
    "INV34-001899": "An absent/default OpenPyXL style has no style payload to copy; skipping it preserves the workbook's default presentation without changing cell values.",
    "INV34-007562": "`ExcelNormalizationError` is an exception type with no extra body; `pass` is the required class declaration.",
    "INV34-007563": "Rule mis-fire: the text describes the `None` return of `days_remaining`; actual function semantics keep unknown balances/rates separate from zero.",
    "INV34-001904": "The required fields are well name, project id and well type; empty/zero project identity is invalid, while optional numeric fields are validated by separate non-None paths. Repository search found no current production caller of this legacy CentralFunctions validator, so no downstream result/persistence behavior is claimed.",
    "INV34-001905": "Malformed optional mud numerics create a field-specific validation error; zero is still parsed because the guard is `is not None`.",
    "INV34-001907": "Malformed nonblank drilling numeric text creates a validation error; blank optional values remain absent.",
    "INV34-001908": "Depth conversion failures are already recorded by the numeric-field loop; this catch only prevents a duplicate ordering error and does not clear the validation result.",
    "INV34-007566": "Duplicate capture of the same required-field guard in `validate_well_data` as INV34-001904; no separate behavior.",
    "INV34-002058": "Lineage summary omits only an absent original label; the `value is not None` branch still displays explicit numeric zero.",
    "INV34-002060": "Source-file text is optional descriptive metadata; the actual raw value and structured lineage record are unchanged.",
    "INV34-002061": "Source-sheet text is optional descriptive metadata; it is not an engineering scope selector.",
    "INV34-002064": "Missing import timestamp is filled with current UTC time at ingestion; an existing timestamp is retained.",
    "INV34-002107": "An omitted mapping-store path selects the configured application data path; an explicit non-empty path is retained.",
    "INV34-002147": "An explicit executable config selects that executable as the child-process command prefix; absence falls through to the configured Python module route.",
    "INV34-002148": "An explicit Python executable selects the `python -m mineru` route; absence produces no command prefix and a clear unavailable state.",
    "INV34-002160": "Output directory is optional; only a non-empty path is expanded, otherwise the adapter's managed temporary output is used.",
    "INV34-002161": "Python executable configuration is optional; absent configuration does not trigger discovery from an empty string.",
    "INV34-002162": "Persisted numeric timeout `0` was treated as absent and became 600 seconds, while the equivalent environment string `\"0\"` was clamped to 1 second. Since the code's explicit lower bound is one second, the inconsistent falsy check was fixed to test `is not None`; two regressions prove both config channels now agree.",
    "INV34-002202": "An invalid/unavailable page number is represented as `None`, not page zero; the table remains available with its other source provenance.",
    "INV34-002208": "Bounding box is optional extraction metadata; absent/empty geometry maps to `None` and no table measurements are altered.",
}
SPECIAL = {
    "INV34-002162": ("core/mineru_engine.py", "MinerUConfig.from_environment",
                     "timeout_seconds = max(1, int(timeout_value)) if timeout_value is not None else 600"),
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
        "reason": "Original source hash/line/symbol/fingerprint verified; the falsy timeout branch is changed and current code is mapped within the same config method.",
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
    stats["trees"]["core/excel_intelligence.py"] = (
        f"provenance tree = {SOURCE_TREES['core/excel_intelligence.py']} "
        "(blob sha256 equals the twelve recorded source hashes; current line map was verified)"
    )
    moved = [verify_special(by_id[key]) for key in SPECIAL]
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
            "remaining_question": None,
            "site": {"file": record["file"], "line": record["line"],
                     "symbol": record.get("symbol"), "expression": record.get("current_source_line"),
                     "source_sha256": record["source_sha256"],
                     "context_fingerprint": record["context_fingerprint"]},
        })
    special = moved[0]
    item_map = {r["id"]: r for r in items}
    item_map["INV34-002162"]["current_site"] = special["current_site"]
    item_map["INV34-002162"]["current_source_line"] = special["current_source_line"]
    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": "phase-2 mixed review: DDR provenance adapters, editor boundaries, Excel semantic import, data lineage and optional MinerU configuration/fallbacks",
        "records": len(items), "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": dict(Counter(r["file"] for r in records)),
        "by_classification": counts,
        "defects_fixed": [{"id": "NEW-P6-021", "file": "core/mineru_engine.py", "site": "MinerUConfig.from_environment timeout_seconds", "test": "tests/test_mineru_timeout_zero.py", "summary": "Normalize explicit persisted numeric timeout zero and environment string zero through the same 1-second minimum instead of treating numeric zero as missing and silently using 600 seconds."}],
        "new_findings": [],
        "observations": [
            {"topic": "MinerU configuration", "summary": "Executable/Python/output paths are optional; backends and timeout are resolved before out-of-process invocation. Explicit timeout 0 now clamps consistently to one second. Real installation, real DDR OCR/quality and production deployment remain external acceptance."},
            {"topic": "Excel semantic mapping", "summary": "Preferred anchors are authoritative when populated; labels are structural boundaries; conflict and duplicate states append provenance without replacing the primary canonical result. Raw row zero is only a one-based worksheet search sentinel."},
            {"topic": "review and edit boundaries", "summary": "Empty import tables stay empty, invalid text is carried as validation/review rather than numeric defaults, and Save All snapshots exclude read-only derived views."},
        ],
        "sibling_search": [
            {"family": "zero and blank handling", "result": "Excel/DDL converters primarily receive text strings from parser adapters; textual `\"0\"` survives their blank normalizers. CentralFunctions required IDs reject zero; optional numeric validators use non-None checks where zero is numeric."},
            {"family": "PDF/MinerU fallback tables", "result": "Source adapter contracts yield textual cell values for Camelot/PyMuPDF/OCR; page parse failures remain `None`, and malformed extraction is left for review. No actual MinerU binary, CUDA stack, or production DDR corpus was present for external acceptance."},
            {"family": "exception/pass sites", "result": "The reviewed `pass` statements are named exception class bodies; caught decode/type errors select an alternate encoding, reduce candidate score, or preserve an unknown page state rather than asserting success."},
        ],
        "tests": {
            "passed": [
                "28 passed: tests/test_excel_intelligence.py tests/test_excel_intelligence_regressions.py.",
                "65 passed: tests/test_lineage.py tests/test_config_and_mapping.py tests/test_r18_r19_save_preservation.py.",
                "42 passed: tests/test_import_architecture.py tests/test_import_quality_extra.py tests/test_core_import.py tests/test_mineru_engine.py tests/test_mineru_timeout_zero.py.",
                "Ruff --select E722,F821, compileall, and git diff --check passed for changed files.",
            ],
            "environment_blocked": [
                "No MinerU installation, CUDA/GPU backend, operator DDR corpus, or production OCR acceptance was exercised; these are environment/domain acceptance gates, not source-test claims.",
            ],
            "mutation": "The persisted timeout-zero regression failed before the fix (600 seconds instead of 1); both persisted integer zero and environment string zero now pass. Existing MinerU adapter tests run without a real MinerU installation and do not establish OCR/real-DDR acceptance.",
        },
        "head": "dc0ad4b", "commit": None, "evidence_commit": None,
        "evidence_files": ["core/mineru_engine.py", "tests/test_mineru_timeout_zero.py", "tools/m36/p6_batch_025.py", "docs/audits/m36-evidence/p6-batch-025.json"],
        "staleness": {
            "checked": len(records), "stale": len(reanchored) + len(moved),
            "re_anchored": len(reanchored) + len(moved),
            "method": "All hashes resolve to their recorded trees; recorded lines, enclosing symbols and current mappings were verified. Context fingerprints were checked ledger-free and are reported with any hash-anchored non-reproductions. The timeout line was manually re-anchored with original fingerprint proof plus current method/expression verification.",
            "re_anchored_items": [
                {"id": ident, "file": path, "previous_site": f"{path}:{old}", "current_site": f"{path}:{new}", "tree": tree, "source_sha256": by_id[ident]["source_sha256"], "context_fingerprint": by_id[ident]["context_fingerprint"], "reason": "Exact recorded expression/hash/fingerprint verified; line map verified current enclosing symbol."}
                for ident, path, old, new, tree in reanchored
            ] + moved,
            "provenance_trees": stats["trees"],
            "m34_fingerprint_ledger": {
                "manifest": "docs/audits/m34-evidence/M34_INVENTORY_LEDGER.json",
                "expected_path": "docs/audits/m34-evidence/m34-ledger.json",
                "expected_sha256": "d81a77bda0330c75493f4081c4a02e4d106fe7602e49c14f0c67d12977658a6b",
                "expected_bytes": 11394989, "present_in_workspace": False,
                "effect": "The ledger-free proof was used; the unavailable original patterns are not claimed or fabricated.",
            },
            "fingerprint_proof": {"checked": stats["fingerprints_checked"] + len(moved), "verified": stats["fingerprints_verified"] + len(moved), "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"], "records_without_a_reproducing_fingerprint_but_hash_anchored": stats["fingerprints_not_reproduced_but_hash_anchored"], "symbol_forms_that_reproduced": stats["fingerprints_by_form"], "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"], "method": stats["ledger_mode"] + "; changed timeout source was separately checked in the original tree and re-anchored to its current method"},
        },
        "method": "Trace producers through import/editor adapters, normalization, review/persistence and tests; validate only known contracts, preserve source locations and unknown values, and keep external MinerU/real-DDR conditions explicitly outside source-test acceptance.",
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={counts}; reanchors={len(reanchored) + len(moved)} fingerprints={stats['fingerprints_verified'] + len(moved)}/{len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
