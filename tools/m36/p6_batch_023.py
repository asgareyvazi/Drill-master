#!/usr/bin/env python3
"""Adjudicate P6 batch 023 from its hash-anchored source records."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-023"
VC = "VERIFIED-CORRECT"
INT = "INTENTIONAL"
DUP = "DUPLICATE/FALSE-POSITIVE"
DDD = "DOMAIN_DECISION_REQUIRED"
DEF = "GENUINE_DEFECT"
sys.path.insert(0, str(ROOT))
from tools.m36 import p6_batch_020 as provenance

SOURCE_TREES = {
    "core/wellbore_schematic_engine.py": "95dd63186ccda8d3cff41ac9632c8c2886639aa4",
}

CLASSIFICATION = {
    "INV34-003047": DDD, "INV34-003048": DDD, "INV34-003049": DDD,
    "INV34-003050": DDD,
    "INV34-003088": VC, "INV34-003090": VC, "INV34-003091": VC,
    "INV34-003095": VC, "INV34-003101": VC, "INV34-003103": VC,
    "INV34-003114": INT,
    "INV34-004598": VC, "INV34-004608": INT, "INV34-004846": INT,
    "INV34-004849": VC, "INV34-004867": VC, "INV34-004891": VC,
    "INV34-004892": VC, "INV34-004915": VC, "INV34-004916": VC,
    "INV34-004917": VC,
    "INV34-005330": VC, "INV34-005331": VC, "INV34-005342": VC,
    "INV34-005372": DDD, "INV34-005373": DDD,
    "INV34-006629": DUP, "INV34-006714": DUP,
    "INV34-007626": VC, "INV34-007628": VC, "INV34-007629": VC,
    "INV34-007630": VC,
    "INV34-008170": INT, "INV34-008177": INT, "INV34-008180": INT,
    "INV34-008189": INT, "INV34-008206": INT, "INV34-008210": INT,
    "INV34-008229": INT,
    "INV34-009731": VC,
    "INV34-010837": DUP, "INV34-010842": VC, "INV34-010867": DUP,
    "INV34-010969": DUP, "INV34-011096": DUP,
}

NOTES = {
    "INV34-003047": "The fallback OD is used only to size bridge-plug drawing geometry in pixels; it is not persisted or consumed by an engineering engine. Because it presents an unspecified completion diameter as a plausible geometry, retain the visual-assumption decision NEW-P6-015 rather than claiming it is a measured OD.",
    "INV34-003048": "Packer OD fallback affects only the schematic drawing width; the CompletionItem remains unchanged and no database value is written. An owner should decide whether to label/omit the assumed geometry. See NEW-P6-015.",
    "INV34-003049": "Perforation casing-width fallback is renderer-only and does not alter source casing OD or the report. Its unmarked default may look authoritative in the diagram; see NEW-P6-015.",
    "INV34-003050": "Sand-screen OD fallback changes only the rendered width, not persisted or engine input. No displayed provenance marks the assumed width; see NEW-P6-015.",
    "INV34-003088": "Bore-scoped casing lookup returns None when scope has no attributable sections/reports or no owned report; `_add_casings_from_db` then returns without inventing a casing.",
    "INV34-003090": "Missing formation report returns without adding formations. Whole-well and bore-scoped paths use their corresponding query scopes.",
    "INV34-003091": "The latest casing query is constrained to the selected well and section/report ids resolved to that bore; missing rows produce None, not a fallback to another bore.",
    "INV34-003095": "Formation selection is constrained to report ids owned by the selected bore. If there are no report ids or no match, it returns None.",
    "INV34-003101": "A missing casing name changes only its display label to the generic word `Casing`; the numeric source OD and depth remain source-owned.",
    "INV34-003103": "No casing means no open-hole segment is drawn. It does not synthesize casing dimensions or a bottom depth.",
    "INV34-003114": "Dark mode selects presentation colors only; it does not alter schematic values or engineering calculations.",
    "INV34-004598": "The TFA calculation is guarded; when the nozzle list cannot produce positive area, the UI explicitly displays `Add nozzles first`, clears recommendation and returns before computing hydraulic numbers. The fallback zero is a control value, not a success result.",
    "INV34-004608": "The drill-pipe repository is optional; no DB/import yields None and the AddPipe dialog still offers manual input and built-in presets. Fail-open applies only to reference-catalog availability, not a canonical engineering input.",
    "INV34-004846": "A canceled file dialog returns an empty filename and leaves `_drill_pipe_df` unchanged. A selected file is read with explicit Excel engine; errors are shown in a critical dialog.",
    "INV34-004849": "Tail density passes into the canonical `CementEngine.job_volumes`; failed EngineeringResult is rendered as an error and clears the cached successful-run snapshot. Zero-valued optional spin controls are normalized as not supplied and the core required-input gate decides whether the run can succeed.",
    "INV34-004867": "`it` is a QTableWidgetItem existence guard before styling a presentation row; it does not test an engineering number or omit calculation inputs.",
    "INV34-004891": "The table item lookup is followed by an existence guard; absent cells are not dereferenced or converted to a numeric result.",
    "INV34-004892": "This `if it` only guards color formatting for an existing table item. Choke schedule values were already computed and are unaffected.",
    "INV34-004915": "Hydraulics geometry rows come from non-editable tables populated by AddPipeDialog; malformed/missing cells are skipped rather than defaulted to zero. The dialog validates dimensions; the exception is a defensive malformed-row guard.",
    "INV34-004916": "Same pipe-row parsing site and same dialog validation as INV34-004915; duplicate scanner capture of the same exception line, not a second behavior.",
    "INV34-004917": "Nozzle rows are inserted through the validated AddNozzleDialog into a non-editable table. Parsing failures skip malformed rows rather than inventing a nozzle size/quantity.",
    "INV34-005330": "The explicit `is_2400` flag maps end-of-day 24:00 to 86,400 seconds, separate from ordinary time-of-day arithmetic; regression tests exercise the 24:00 report boundary.",
    "INV34-005331": "Same explicit 24:00 boundary for an interval end; normal midnight remains an ordinary time, and duration is computed with one reporting-day wrap.",
    "INV34-005342": "A missing cell widget is skipped during NPT row highlighting; only styling/statistics refresh is affected.",
    "INV34-005372": "For malformed string-valued legacy `time_from`, parsing exceptions substitute 08:00. TimeLog24H is typed as SQL Time and normal ORM records reach the time-object path; if malformed legacy strings are accepted, this fallback fabricates an operational time. Owner decision is recorded as NEW-P6-016; no contract for malformed historical strings was found.",
    "INV34-005373": "For malformed string-valued legacy `time_to`, exceptions substitute 16:00. Normal records are SQL Time objects; malformed input could become a synthetic interval and duration. See NEW-P6-016.",
    "INV34-006629": "`_report` is a test fixture factory supplying a synthetic report and explicit test depth; it is not used by production report ingestion or persistence.",
    "INV34-006714": "`_ddr` creates test-only daily-report inputs; `npt_h=0.0` is an explicit known-zero fixture value and `prod_h=None` represents missing source data for the scenario.",
    "INV34-007626": "The docstring states the inventory trichotomy: missing opening stock yields None, while movement normalization separately treats absent received/used as zero. The behavior is covered by test_inventory_item_authority.",
    "INV34-007628": "Blank item name normalizes to None rather than an empty string; database validation can then reject/mark the missing required identity.",
    "INV34-007629": "Blank category normalizes to None, preserving absence rather than creating an empty category token.",
    "INV34-007630": "Blank unit normalizes to None; no default physical unit is fabricated at this normalization boundary.",
    "INV34-008170": "History repository creation is lazy and returns None when persistence is unavailable; callers refuse save/history operations with an explicit UI message while calculations remain independent.",
    "INV34-008177": "Same optional lazy-repository contract for torque/drag history; the helper does not replace a calculation result with zero.",
    "INV34-008180": "Same optional lazy-repository contract for mud-volume history; callers check for None before persistence.",
    "INV34-008189": "Same optional lazy-repository contract for casing history; calculation path and history storage remain separate.",
    "INV34-008206": "Same optional lazy-repository contract for cement history; save is unavailable without a repository and no synthetic run is created.",
    "INV34-008210": "The kill-sheet history repository may be unavailable; callers require both a successful calculation and a repository before saving.",
    "INV34-008229": "Missing well metadata becomes an empty context dictionary used for UI labels/attribution; it does not pass a numeric zero into the kill-sheet or engineering engine.",
    "INV34-009731": "Absent movement normalizes to zero under the explicit inventory contract; malformed/non-finite/bool values are rejected by `optional_number`, and unknown opening stock remains None in `derive_closing`.",
    "INV34-010837": "Test-only import of the actual-vs-plan API; behavioral assertions are in the test bodies, not an input default.",
    "INV34-010842": "This assertion proves a plan-only result has no fabricated actual counterpart; it is a direct regression contract, not a production numeric initializer.",
    "INV34-010867": "Test-only import of `section_actual_days`; the test creates same-named entities under distinct wells and asserts ownership isolation.",
    "INV34-010969": "Test-only import of the comparison function; no numeric default is introduced by the import statement.",
    "INV34-011096": "`actual_class` is a test helper/factory that builds a fake class for instrumentation; it is not a production result class or runtime numeric source.",
}

QUESTIONS = {
    "INV34-003047": "Should a schematic render a visibly labeled standard-OD approximation, omit the dimension-dependent shape, or render it with unknown geometry when CompletionItem.od_inch is absent?",
    "INV34-003048": "Same completion-rendering decision: how should missing packer OD be represented without implying the default is source data?",
    "INV34-003049": "Same completion-rendering decision: should the missing perforation casing OD be labeled, omitted, or represented as unknown?",
    "INV34-003050": "Same completion-rendering decision for the sand-screen width.",
    "INV34-005372": "Should malformed legacy time strings be rejected/marked for review rather than defaulted to 08:00?",
    "INV34-005373": "Should malformed legacy time strings be rejected/marked for review rather than defaulted to 16:00?",
}


def main() -> int:
    provenance.RECHECK_AGAINST.update(SOURCE_TREES)
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    records = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(records) != 45 or {r["id"] for r in records} != set(CLASSIFICATION):
        raise SystemExit(f"register/classification mismatch: {len(records)} records, {len(CLASSIFICATION)} classifications")
    reanchored, stats = provenance.check(records)
    by_id = {r["id"]: r for r in records}
    items = []
    for record in records:
        classification = CLASSIFICATION[record["id"]]
        items.append({
            "id": record["id"], "file": record["file"], "line": record["line"],
            "symbol": record.get("symbol"), "rule": record.get("rule"), "kind": record.get("kind"),
            "register_line_text": record.get("current_source_line"),
            "classification": classification,
            "evidence": (
                f"Hash-anchored site {record['file']}:{record['line']} "
                f"`{record['current_source_line'].strip()}` in `{record.get('symbol')}`; "
                f"source_sha256={record['source_sha256']}; context_fingerprint={record['context_fingerprint']}. "
                + NOTES[record["id"]]
            ),
            "defect": classification == DEF,
            "remaining_question": QUESTIONS.get(record["id"]),
            "site": {"file": record["file"], "line": record["line"], "symbol": record.get("symbol"),
                     "expression": record.get("current_source_line"),
                     "source_sha256": record["source_sha256"],
                     "context_fingerprint": record["context_fingerprint"]},
        })
    current_cache = {}
    moved = []
    for ident, path, old_line, new_line, tree in reanchored:
        if path not in current_cache:
            current_cache[path] = (ROOT / path).read_text(encoding="utf-8").splitlines()
        r = by_id[ident]
        moved.append({
            "id": ident, "file": path, "previous_site": f"{path}:{old_line}",
            "previous_source_line": r["current_source_line"].strip(),
            "current_site": f"{path}:{new_line}",
            "current_source_line": current_cache[path][new_line - 1].strip(),
            "tree": tree, "source_sha256": r["source_sha256"],
            "context_fingerprint": r["context_fingerprint"],
            "reason": "Prior edits shifted the renderer source; shared line map, exact expression, source hash/fingerprint and enclosing AST symbol verified the current site.",
        })
    counts = dict(Counter(CLASSIFICATION.values()))
    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": "phase-2 class C/D/E mixed review: schematic rendering, W13 engineering UI adapters, W2 report-time boundaries, inventory semantics and actual-vs-plan fixtures",
        "records": len(items), "sites": len({(r['file'], r['line']) for r in records}),
        "records_by_file": dict(Counter(r["file"] for r in records)),
        "by_classification": counts, "defects_fixed": [],
        "new_findings": [
            {"id": "NEW-P6-015", "file": "core/wellbore_schematic_engine.py", "line": 787,
             "severity": "LOW", "status": "domain decision required; not patched",
             "summary": "Completion renderer substitutes plausible ODs for missing bridge-plug, packer, perforation and sand-screen diameters. The values affect pixels only and are not persisted/used in calculations, but the diagram does not identify the approximation.",
             "records": ["INV34-003047", "INV34-003048", "INV34-003049", "INV34-003050"],
             "impact": "A schematic viewer may appear to show real relative completion geometry when source OD is absent."},
            {"id": "NEW-P6-016", "file": "tabs/w2_Daily_Report.py", "line": 759,
             "severity": "LOW", "status": "domain decision required; not patched",
             "summary": "Malformed string time values in legacy/mocked time-log rows fall back to 08:00/16:00. Current TimeLog24H columns are typed SQL Time and normal ORM data uses time objects; decide whether abnormal string inputs should be rejected/marked instead of converted to a synthetic interval.",
             "records": ["INV34-005372", "INV34-005373"],
             "impact": "If malformed legacy time strings reach the widget, re-saving could create plausible but unverified report times/duration."},
        ],
        "observations": [
            {"topic": "wellbore schematic source scope", "summary": "Bore-specific casing and formation readers constrain queries to the selected bore's owned section/report ids; missing queries return None and the renderer omits absent casing/open-hole geometry rather than manufacturing database rows."},
            {"topic": "visual approximations", "summary": "Four OD fallbacks are limited to completion-item rendering. They are not persisted or reused by calculations, but are not visibly labeled, so they remain an owner decision."},
            {"topic": "inventory semantics", "summary": "Opening stock remains unknown when absent; movement normalization maps absent movement to zero but rejects invalid values. Empty item labels/categories/units normalize to None."},
            {"topic": "report time boundary", "summary": "24:00 uses an explicit flag and is converted to the reporting-day boundary; duration wraps once across the DDR day. SQL Time storage cannot retain the 24:00 distinction itself, so verify the exact end-to-end behavior in Qt-capable CI."},
        ],
        "sibling_search": [
            {"family": "schematic missing source geometry", "result": "Database casing/formation absence returns no elements; completion OD fallbacks are renderer-only and grouped for an explicit visibility decision. Builder bore filtering uses resolved section/report ownership."},
            {"family": "W13 plain-return failures and optional repositories", "result": "The bit TFA failure branch displays an explicit `Add nozzles first` error. History repositories can be absent without changing calculations, and callers block persistence or retain manual/built-in reference entry."},
            {"family": "time and inventory normalization", "result": "24:00 is an explicit reporting boundary in the widget/helper; inventory opening NULL and movement zero remain distinct. Only malformed legacy time strings fall back to fixed times, captured as NEW-P6-016."},
        ],
        "tests": {
            "passed": [
                "35 passed: tests/test_scope_attribution.py tests/test_wellbore_section_performance.py tests/test_operations.py",
                "26 passed: tests/test_p0_time_log_validation.py tests/test_profile_time_log_unknown_duration.py tests/test_operational_time_integrity.py",
                "27 passed: tests/test_inventory_item_authority.py",
                "61 passed: tests/test_wellbore_ownership_integrity.py tests/test_wellbore_schema_v3.py tests/test_wellbore_identity_conflict_m25.py tests/test_wellbore_discriminator_import.py",
            ],
            "environment_blocked": [
                "tests/test_schematic_no_fabrication.py fails collection because PySide6 cannot load missing system libGL.so.1.",
                "A mixed batch23 regression run reported eight UI failures (five W13/M31 widget tests and three real-user W12/W10 tests), each before assertions due missing libGL.so.1.",
            ],
            "mutation": "No production code changed in this batch; existing tests exercise bore ownership, missing-source behavior, time validation and inventory unknown/zero semantics. Qt-only schematic render assertions remain unverified locally because libGL.so.1 is missing.",
        },
        "head": "db5fbbb",
        "commit": None, "evidence_commit": None,
        "evidence_files": ["docs/audits/m36-evidence/p6-batch-023.json", "docs/audits/m36-evidence/m36-open-item-register.json", "docs/audits/m36-evidence/m36-master-ledger.json", "tools/m36/p6_batch_023.py", "core/wellbore_schematic_engine.py", "core/inventory_semantics.py", "tabs/w13_Engineering_Calculator.py", "tabs/w2_Daily_Report.py"],
        "staleness": {
            "checked": len(records), "stale": len(moved), "re_anchored": len(moved),
            "method": "All 45 source SHA, source-line, AST symbol and context fingerprints were verified; 11 schematic-engine records were re-anchored across known source-tree changes by exact line mapping. No fingerprint was unreproduced.",
            "re_anchored_items": moved, "provenance_trees": stats["trees"],
            "fingerprint_proof": {
                "checked": stats["fingerprints_checked"], "verified": stats["fingerprints_verified"],
                "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"],
                "records_without_a_reproducing_fingerprint_but_hash_anchored": stats["fingerprints_not_reproduced_but_hash_anchored"],
                "symbol_forms_that_reproduced": stats["fingerprints_by_form"],
                "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"],
                "method": stats["ledger_mode"],
            },
        },
        "method": "Trace every flagged source site from producer/input through normalization, engine/query, UI/report and persistence/test; only mark behavior verified where the consuming contract and tests agree. No production changes were justified; two bounded domain/visibility decisions remain explicit.",
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: records={len(items)} sites={payload['sites']} classifications={counts}; reanchors={len(moved)} fingerprints={stats['fingerprints_verified']}/{stats['fingerprints_checked']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
