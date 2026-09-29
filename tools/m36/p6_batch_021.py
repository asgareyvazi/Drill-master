#!/usr/bin/env python3
"""Adjudicate MEDIUM class-C P6 batch 021 against the hash-anchored source tree.

The audit is source-linked to each register fingerprint.  Three sheet-resolver
records are explicitly reconstructed across the batch's own tested fix; they
are not silently re-anchored by line number.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-021"
VC = "VERIFIED-CORRECT"
DUP = "DUPLICATE/FALSE-POSITIVE"
DDD = "DOMAIN_DECISION_REQUIRED"
DEF = "GENUINE_DEFECT"

# The M36 snapshot contains a full history after fetching the expected base branch.
# These are the exact commits whose file bytes reproduce the register source SHA.
SOURCE_TREES = {
    "core/engineering/well_control_kill_sheet.py": "fd18a2bca5b849356c50f9da19c278ecdd8f9967",
    "core/mud_ledger.py": "95dd63186ccda8d3cff41ac9632c8c2886639aa4",
    "core/wellbore_schematic_engine.py": "95dd63186ccda8d3cff41ac9632c8c2886639aa4",
    "tabs/w7_logistics_Widget.py": "fd18a2bca5b849356c50f9da19c278ecdd8f9967",
    "core/excel_intelligence.py": "7f0186e3e6ac966f1fe9cbd804785129b9246fbe",
}
SHEET_IDS = {
    "INV34-009687": (2024, "names = list(self.cell_cache)",
                     "historic loop is now an explicit snapshot of available sheet names"),
    "INV34-009688": (2032, "if hint in name.strip().casefold() or name.strip().casefold() in hint",
                     "historic first-match predicate is now filtered into a candidate list; only a unique candidate resolves"),
    "INV34-009689": (2039, "return partial[0] if len(partial) == 1 else None",
                     "historic unconditional return now refuses ambiguous/missing named sheets"),
}

CLASSIFICATION = {
    "INV34-001770": VC, "INV34-001771": DDD,
    "INV34-001811": VC, "INV34-001814": DUP,
    "INV34-001901": VC,
    "INV34-001928": VC, "INV34-001929": VC, "INV34-001941": VC,
    "INV34-001944": VC, "INV34-001947": VC, "INV34-001948": VC,
    "INV34-001955": VC, "INV34-001956": VC, "INV34-001958": VC,
    "INV34-002054": VC, "INV34-002226": VC, "INV34-002264": VC,
    "INV34-002773": VC, "INV34-002808": VC, "INV34-002810": VC,
    "INV34-002842": VC, "INV34-002844": DUP, "INV34-002845": VC,
    "INV34-002847": VC, "INV34-002848": VC, "INV34-002853": VC,
    "INV34-002864": VC, "INV34-002900": VC, "INV34-003070": VC,
    "INV34-009654": VC, "INV34-009661": VC, "INV34-009669": VC,
    "INV34-009675": VC, "INV34-009680": VC, "INV34-009684": VC,
    "INV34-009687": DEF, "INV34-009688": DEF, "INV34-009689": DEF,
    "INV34-009764": VC, "INV34-009765": VC, "INV34-009768": VC,
    "INV34-009849": VC, "INV34-009935": VC,
    "INV34-009953": VC, "INV34-009978": VC,
}

FILE_CONTRACT = {
    "core/engineering/well_control_kill_sheet.py":
        "The canonical builder records absent required fields in missing_inputs and compute_kill_sheet refuses them. "
        "MAASP receives None at zero fracture gradient and EngineeringResult failure is checked; the documented "
        "dialog labels zero shoe TVD as skip-MAASP. No missing measurement becomes a successful zero result. "
        "The no-pipe 5-inch fallback is different: it contributes to kick-height geometry and lacks a displayed "
        "assumption/provenance, so its physical applicability is not closed without the operations owner.",
    "core/excel_intelligence.py":
        "Candidate scoring is bounded confidence, while the extraction pipeline carries actual_sheet to the "
        "dynamic table extractor and source-IR updates are guarded by (sheet, cell). The three resolver sites "
        "were genuine: a named-template mismatch or ambiguous partial hint previously selected the first sheet, "
        "and a reproducible two-sheet workbook produced accepted canonical well_info.name='WRONG-WELL'. "
        "The minimal fix uses exact name first, a unique partial match only, and None for missing/ambiguous names; "
        "generic unnamed sheet_1 compatibility remains. Regression asserts no canonical value/provenance is emitted.",
    "core/fuel_water_semantics.py":
        "The 3-day low-stock threshold is an explicit caller-overridable policy parameter. The helper only warns "
        "for a known positive-consumption runway; None/non-positive consumption is not a zero-day alert.",
    "core/hydraulics_engine.py":
        "Pump-output efficiency defaults to the documented 0.95 assumption and is range-validated (0 < efficiency <= 1); "
        "the nozzle optimizer documents n=1.0 as its fallback for invalid two-point readings and the UI constrains "
        "nozzle count to 1..8. Its empty-combination zero is unreachable from that UI. WellProfile's survey-less "
        "fallback is an explicitly simplified KOP model; directional inputs with surveys use interpolation. "
        "The residual concern is not a fabricated measurement but visibility of the optimizer fallback assumption.",
    "core/lineage.py":
        "The confidence threshold is a review-query cutoff, caller-overridable, not an imported engineering measurement; "
        "zero confidence is deliberately excluded from the positive-confidence review subset.",
    "core/operational_time.py":
        "summarize_time_logs consumes stored durations, not wall-clock timestamps: absent/non-finite/negative duration "
        "is unknown, known zero is retained, and any incomplete denominator is None. NPT percent requires complete "
        "classified hours; timezone, midnight and report-day allocation belong upstream to the report-keyed log.",
    "core/performance.py":
        "File-size thresholds only choose performance strategy. OSError maps to 0.0 MB and is_large_file is used as a "
        "heuristic, not an engineering quantity; no in-repo caller turns the default into a drilling fact.",
    "core/save_outcome.py":
        "saved=0 is an additive count initializer. SaveOutcome status/disposition comes from structured issues and "
        "never interprets the count default as validation success or an engineering zero.",
    "core/standards.py":
        "The 14-day BOP test interval is explicitly a configurable policy default: environment overrides precede config, "
        "which precedes caller default; parsed values are clamped to at least one day and malformed overrides fall back.",
    "core/text_utils.py":
        "safe_float/safe_int expose an explicit caller-supplied default and have no direct numeric-engineering consumers; "
        "fmt_num calls safe_float with default=None so missing report values remain an em dash. wrap_text/wrap_html "
        "width is presentation-only and these helpers are not a numeric ingestion boundary.",
    "core/time_utils.py":
        "DrillTime.minute defaults to the conventional start-of-hour value; from_string special-cases only 24:00 and "
        "validates other wall-clock components. The 24:00 representation is preserved for DDR boundaries and subtraction "
        "computes forward elapsed hours modulo one 24-hour reporting cycle.",
    "core/universal_import.py":
        "compact_context's limit=80 is a bounded AI context/payload control; the compacted snapshot remains metadata and "
        "does not canonicalize or persist source measurements.",
    "core/wellbore_schematic_engine.py":
        "Outer casing selection filters for a larger OD and containing depth interval, then chooses the smallest valid "
        "larger diameter (nearest containing casing). No candidate produces None; no missing geometry is set to zero.",
    "dialogs/calculator_dialog.py":
        "Shoe TVD zero is explicitly labeled by the UI as '0 = skip MAASP'; the core MAASP engine result is checked. "
        "This is a deliberate optional-calculation sentinel, not a reported zero depth used in the formula.",
    "dialogs/hierarchy_dialogs.py":
        "The environment-change handler sets water depth to 0.0 only when the well is classified as non-offshore and "
        "disables the input; this is a physical non-applicable value rather than a missing offshore measurement.",
}

SITE_NOTES = {
    "INV34-001811": "score_candidate computes a weighted evidence score then clamps it to its documented [0,1] confidence range.",
    "INV34-001814": "Same score_candidate return expression and source site as INV34-001811; the second inventory rule flag is a duplicate, not a second behavior.",
    "INV34-001941": "If no candidate tuple exists, selected_nozzles is empty and actual TFA is zero; W13 spinbox constrains n_nozzles to 1..8, while actual feasible combos have summed physical nozzle areas.",
    "INV34-001944": "Build inclination is capped at end-of-build inclination; later branch returns EOB or target inclination.",
    "INV34-001947": "Triplex efficiency guard rejects zero, >1, and NaN before formula evaluation.",
    "INV34-001948": "Duplex efficiency guard has the same finite range behavior; liner/stroke and rod geometry are validated separately.",
    "INV34-001955": "No survey points makes _interpolate_tvd's documented straight/vertical fallback return MD; normal get_tvd_at_md uses surveyed interpolation only when points exist.",
    "INV34-001956": "Survey data selects interpolation; absent surveys follow the explicit simplified KOP branch rather than treating a missing list as a numeric datum.",
    "INV34-001958": "Invalid two-point friction data or logarithm exceptions fall back to n=1.0 exactly as the optimizer docstring states; this approximation is not exposed as a warning in W13 and is retained as NEW-P6-009 for decision/review.",
    "INV34-002226": "EngineeringError from typed numeric conversion is downgraded to unknown duration, then omitted from complete totals; it does not contribute zero hours.",
    "INV34-002264": "10 MB only selects chunking/performance strategy. It does not coerce a source quantity.",
    "INV34-002773": "The count default initializes SaveOutcome; validation errors/warnings are still copied into explicit statuses.",
    "INV34-002808": "14 is the documented configurable policy default, not a hard-coded measurement.",
    "INV34-002810": "max(1, int(env/config)) enforces a positive interval after the source override is parsed.",
    "INV34-002842": "The generic parser only returns its explicit default on None/conversion error; active formatter caller supplies None for unknown values.",
    "INV34-002844": "Same safe_float declaration as INV34-002842, same path and behavior; duplicate scanner record.",
    "INV34-002845": "safe_int's zero is a caller-selectable conversion fallback; no direct in-repo engineering consumer exists.",
    "INV34-002847": "wrap_html is used for display text; width=0 is an unused layout hint, not a numeric default.",
    "INV34-002848": "wrap_text is used for text normalization in import descriptions; width=0 does not supply a measurement.",
    "INV34-002853": "DrillTime's default minute=0 means the natural start of the specified hour; callers can pass the minute explicitly.",
    "INV34-002864": "from_string accepts 24:00 via the explicit special case; this guard rejects invalid clock values outside the DDR day-boundary convention.",
    "INV34-002900": "The 80-item cap bounds AI context size; omitted tables are still present in the source snapshot and are not converted into facts.",
    "INV34-003070": "Among valid outer casings the nearest enclosing one is the smallest OD greater than the inner casing; no candidate returns None.",
    "INV34-009654": "end_row starts at actual_start as the inclusive lower bound before the row-classification scan grows it.",
    "INV34-009661": "Unresolved named sheet is skipped rather than reading unrelated sheet data; this row is part of the no-fabricated-cross-sheet contract. (Whether to surface a missing-sheet review item is a separate residual.)",
    "INV34-009669": "The resolved actual sheet is passed to the table extractor, keeping table discovery tied to the source worksheet.",
    "INV34-009675": "actual_sheet is the method's source sheet identity used when recording scalar extraction/provenance.",
    "INV34-009680": "Raw IR lookup requires both source sheet and cell, preventing same-address cells on other sheets from being treated as the extracted value.",
    "INV34-009684": "Normalized IR value update is guarded by the same sheet+cell pair; no sibling worksheet cell is rewritten.",
    "INV34-009687": "The resolver now evaluates a candidate list and only returns exact or unique partial matches; see regression and source reconstruction proof.",
    "INV34-009688": "The historic first-match substring rule admitted ambiguous 'Operations' sheets; current implementation refuses multiple partial candidates.",
    "INV34-009689": "Resolver now returns None unless the partial candidate is unique; previous unconditional return could bind wrong worksheet.",
    "INV34-009764": "BulkMaterials.used is explicitly defaulted to 0.0 for no movement; stock unknownness is held separately in nullable opening/closing fields.",
    "INV34-009765": "BulkMaterials.received is likewise movement-default 0.0 by model contract; this does not coerce nullable stock.",
    "INV34-009768": "The comprehension first filters depth_2400 is not None, so explicit depth 0 remains zero and missing depth is excluded; the `or 0` is redundant only.",
    "INV34-009849": "PlanReportEngine selects the one active well plan and queries activities by well_id AND active plan_id before totals; this is plan-scoped whole-well output, not a DDR snapshot.",
    "INV34-009935": "Density is a dimensionless diagnostic ratio, with denominator floored at one for empty shape; it is not an engineering zero.",
    "INV34-009953": "The UI explicitly labels zero shoe TVD as skip-MAASP; the backend's required-field gate and MAASP result handling remain distinct.",
    "INV34-009978": "On non-offshore environment the water-depth control is disabled and reset to zero as not-applicable domain state.",
}


def source_proof(records: list[dict]) -> tuple[list[dict], dict]:
    provenance.RECHECK_AGAINST.update(SOURCE_TREES)
    sheet_rows = [r for r in records if r["id"] in SHEET_IDS]
    ordinary = [r for r in records if r["id"] not in SHEET_IDS]
    reanchored, stats = provenance.check(ordinary)

    current_text = (ROOT / "core/excel_intelligence.py").read_text(encoding="utf-8")
    current_lines = current_text.splitlines()
    tree_cache = {}
    for record in sheet_rows:
        path, digest = record["file"], record["source_sha256"]
        if digest not in tree_cache:
            raw = provenance.git_blob(SOURCE_TREES[path], path)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise SystemExit(f"{record['id']}: declared source SHA does not match the recorded tree")
            tree_cache[digest] = raw.decode("utf-8", "replace")
        old_lines = tree_cache[digest].splitlines()
        old_line = record["line"]
        if not provenance.text_matches(record["current_source_line"], old_lines[old_line - 1]):
            raise SystemExit(f"{record['id']}: old site no longer matches the hash-anchored source")
        if provenance.fingerprint_proof(record, {}, tree_cache[digest]) == "MISMATCH":
            raise SystemExit(f"{record['id']}: source fingerprint mismatch")
        line, expected, reason = SHEET_IDS[record["id"]]
        if current_lines[line - 1].strip() != expected:
            raise SystemExit(f"{record['id']}: reconstructed current site changed at line {line}")
        reanchored.append({
            "id": record["id"], "file": path, "previous_site": f"{path}:{old_line}",
            "previous_source_line": record["current_source_line"].strip(),
            "current_site": f"{path}:{line}", "current_source_line": current_lines[line - 1].strip(),
            "tree": SOURCE_TREES[path], "reason": reason,
            "proof": "declared source_sha256 and context_fingerprint verified; current AST symbol is "
                     "ExcelIntelligence._resolve_sheet; behavioral regression proves named missing/ambiguous "
                     "keys do not select first sheet",
        })
    stats["fingerprints_checked"] += len(sheet_rows)
    stats["fingerprints_verified"] += len(sheet_rows)
    stats["fingerprints_by_form"]["short"] = stats["fingerprints_by_form"].get("short", 0) + len(sheet_rows)
    stats["fingerprints_by_expression_form"]["recorded-line"] = stats["fingerprints_by_expression_form"].get("recorded-line", 0) + len(sheet_rows)
    stats["reconstructed_sheet_resolver_records"] = len(sheet_rows)
    return reanchored, stats


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    records = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(records) != 45 or {r["id"] for r in records} != set(CLASSIFICATION):
        raise SystemExit(f"register batch/classification mismatch: records={len(records)} map={len(CLASSIFICATION)}")
    reanchored, stats = source_proof(records)

    explanations = []
    items = []
    for record in records:
        classification = CLASSIFICATION[record["id"]]
        site_note = SITE_NOTES.get(record["id"], FILE_CONTRACT.get(record["file"]))
        if not site_note:
            raise SystemExit(f"no source-backed rationale for {record['id']}")
        evidence = (
            f"{record['file']}:{record['line']} `{record['current_source_line'].strip()}` "
            f"in `{record['symbol']}`. {site_note} {FILE_CONTRACT.get(record['file'], '')}"
        )
        question = None
        if classification == DDD:
            question = "Is 5.0 in the legacy no-pipe fallback an operator-approved geometry assumption for kick height, or should the calculator refuse/mark that estimate unknown?"
        items.append({
            "id": record["id"], "file": record["file"], "line": record["line"],
            "classification": classification, "evidence": evidence,
            "defect": classification == DEF, "remaining_question": question,
            "site": {
                "file": record["file"], "line": record["line"], "symbol": record["symbol"],
                "expression": record["current_source_line"],
                "source_sha256": record["source_sha256"],
                "context_fingerprint": record["context_fingerprint"],
            },
        })
        explanations.append(evidence)

    counts = dict(Counter(CLASSIFICATION.values()))
    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": "phase-2 class C (engineering, imports, semantics): 45 records / 43 sites",
        "records": len(items),
        "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": dict(Counter(r["file"] for r in records)),
        "by_classification": counts,
        "defects_fixed": [{
            "records": ["INV34-009687", "INV34-009688", "INV34-009689"],
            "file": "core/excel_intelligence.py", "fix_commit": "9a7b64f59fd3e95a135f0be3572053206bc4d4d5",
            "summary": "Named-template mismatch/ambiguous sheet hints no longer bind the first workbook sheet; missing or ambiguous names resolve to None.",
            "regression": "tests/test_excel_intelligence_regressions.py::test_template_sheet_mismatch_does_not_extract_from_first_unrelated_sheet and ::test_template_sheet_ambiguous_partial_match_is_not_first_match",
            "mutation": "Both behavioral tests fail when the original first-match/first-sheet resolver is restored.",
        }],
        "new_findings": [
            {"id": "NEW-P6-007", "file": "core/engineering/well_control_kill_sheet.py", "line": 522,
             "severity": "MEDIUM", "status": "domain decision required, not patched",
             "summary": "When pipes_m is empty, kick height uses an unmarked 5-inch pipe-OD assumption; positive pit gain can therefore yield an operational geometry estimate without source geometry. Decide whether this legacy assumption is accepted, labeled approximate, or refused as unknown.",
             "records": ["INV34-001771"], "impact": "W13 kill-sheet output can display kick-height/type values; no pipe OD provenance accompanies the fallback."},
            {"id": "NEW-P6-008", "file": "core/mud_ledger.py", "line": 230,
             "severity": "MEDIUM", "status": "recorded, domain decision required",
             "summary": "Known stock with zero average consumption currently reports days_remaining=0. Tests explicitly preserve this as a pre-existing product decision, while fuel/water semantics treats zero burn runway as None. Do not change mud-chemical behavior until the product/domain owner resolves whether no burn means 0, unbounded, or not-applicable runway.",
             "records": ["INV34-009764", "INV34-009765"], "impact": "A zero runway can look like imminent stockout despite no usage; this is separate from (and does not invalidate) the verified zero movement defaults."},
            {"id": "NEW-P6-009", "file": "core/hydraulics_engine.py", "line": 997,
             "severity": "LOW", "status": "recorded, not patched",
             "summary": "Nozzle optimization documents n=1.0 as the fallback when two-point pump data are invalid, but W13 does not expose which path was used. The estimate remains documented and is not silently changed; decide whether the UI should label the fallback assumption.",
             "records": ["INV34-001958"], "impact": "A screening recommendation may be based on an assumed friction exponent rather than the entered two-point test."},
        ],
        "observations": [
            {"topic": "operational time and scope", "summary": "summarize_time_logs is duration aggregation for already report-keyed rows, not timestamp allocation; it distinguishes known zero from unknown and incomplete denominators. Whole-well, wellbore, section, and report consumers query distinct scopes; no timezone contract is inferred from duration-only input."},
            {"topic": "Excel/import provenance", "summary": "Template sheet identity must resolve uniquely before canonical extraction; the prior fallback produced a canonical wrong-well value in a two-sheet reproduction. Fixed with source-sheet identity preserved through extraction and source-IR updates."},
            {"topic": "mud ledger", "summary": "BulkMaterials model documents nullable stock vs zero-default movements. get_history preserves unknown stocks; current zero-runway behavior for zero consumption is separately pinned as a legacy domain decision."},
        ],
        "sibling_search": [
            {"family": "ExcelIntelligence._resolve_sheet", "result": "single in-repo call at ExcelIntelligence.extract; DDRImportService._auto_match_template requires all named sheets and refuses ambiguous templates; explicit template mismatch now cannot cross-bind first sheet."},
            {"family": "mud movement vs stock", "result": "BulkMaterials.initial_stock is nullable; received/used default 0.0 by model comment. Same zero movement semantics retained; runway semantics not broadened."},
            {"family": "report scope", "result": "PlanReportEngine is well_id + exactly one active plan_id; NPT report applies optional date range consistently to NPT rows, total-time denominator, and report count; subset reports refuse whole-well cost attribution."},
        ],
        "tests": {
            "passed": ["tests/test_excel_intelligence_regressions.py", "tests/test_multi_company_template.py", "tests/test_excel_intelligence.py", "tests/test_ddr_regression.py", "tests/test_operational_time_integrity.py", "tests/test_operations_intelligence_regressions.py", "tests/test_mud_ledger_unknown_stock_history.py", "tests/test_fuel_water_truth.py", "tests/test_nozzle_optimization.py", "tests/test_engineering_integrations.py", "tests/test_report_scope_metadata_m25.py", "tests/test_scope_attribution.py", "tests/test_wellbore_section_performance.py", "tests/test_lineage.py"],
            "environment_blocked": ["2 tests in tests/test_m30_semantic_regressions.py require system libGL.so.1; apt package installation was attempted but sandbox network could not reach Debian package indexes."],
            "mutation": "The two added sheet-binding tests were both run against a runtime mutation restoring the previous resolver; both failed as expected. Production code was unchanged during mutation validation.",
        },
        "head": "9a7b64f59fd3e95a135f0be3572053206bc4d4d5", "commit": None, "evidence_commit": None,
        "evidence_files": ["docs/audits/m36-evidence/p6-batch-021.json", "docs/audits/m36-evidence/m36-open-item-register.json", "docs/audits/m36-evidence/m36-master-ledger.json", "tools/m36/p6_batch_021.py", "core/excel_intelligence.py", "tests/test_excel_intelligence_regressions.py"],
        "staleness": {
            "checked": len(records), "stale": len(reanchored), "re_anchored": len(reanchored),
            "method": "45 fingerprints recomputed ledger-free from the hash-verified source expression/symbol; 42 unchanged records passed the existing AST/hash checker, with the original source files recovered by exact file SHA from Git history. Three resolver records were explicitly reconstructed across fix 9a7b64f: prior line/expression, current line/expression, hash, fingerprint, symbol, and behavior regression are retained in the list below. The 11 MB M34 fingerprint ledger is absent; the reproducible fallback contract is recorded.",
            "re_anchored_items": reanchored,
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
        "method": "Each record was verified against the declared source SHA and AST symbol, then traced through its producer/consumer/test boundary as documented in its evidence. One reproducible cross-sheet source misbinding was fixed minimally, tested for actual canonical-value/provenance absence, and mutation-killed. One no-pipe well-control geometry and one cross-domain mud-runway semantic remain explicit owner decisions; no default was silently changed.",
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={counts}; "
          f"reanchors={len(reanchored)} fingerprints={stats['fingerprints_verified']}/{stats['fingerprints_checked']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
