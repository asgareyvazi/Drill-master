#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-002 (45 HIGH records, class A).

Written from reading each site in the current tree. Also performs the staleness check for the
batch: every record's line must still carry the text the register recorded, otherwise the record
is reported and the batch must not be applied.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-002"

VC, INT, DUP, DDD = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                     "DOMAIN_DECISION_REQUIRED")

# id -> (classification, evidence, remaining_question)
R: dict[str, tuple[str, str, str | None]] = {
    "INV34-000074": (VC,
        "`_valid_proposal` is the predicate of a validity filter; its only caller builds "
        "`valid = [p for p in proposals if self._valid_proposal(p, fields)]` (line 131) and every "
        "other malformed-field branch in the same function also returns False (lines 144-148). An "
        "unparseable confidence makes the proposal invalid - by design, not a swallowed failure.",
        None),
    "INV34-000716": (INT,
        "`if _BCRYPT_AVAILABLE:` selects the bcrypt path; the else branch is the SHA-256 fallback "
        "documented in the same docstring ('weak fallback is development-only'). Production is "
        "already refused at lines 3484-3487, so the fallback cannot serve production.",
        None),
    "INV34-000717": (VC,
        "`_BCRYPT_AVAILABLE` is a capability flag set by the optional-import guard (lines 45-49: "
        "`try: import bcrypt; _BCRYPT_AVAILABLE = True except ImportError: _BCRYPT_AVAILABLE = "
        "False` + warning), so truthiness is the correct test; in production the missing flag "
        "raises CredentialLifecycleError('BCRYPT_REQUIRED').",
        None),
    "INV34-000726": (VC,
        "Same capability flag in `_bootstrap_passwords`; docstring 'Resolve the same secure policy "
        "used by desktop setup and reset'. `is_production_environment() and not "
        "_BCRYPT_AVAILABLE` raises; a legitimate zero cannot occur for an import flag.", None),
    "INV34-000995": (VC,
        "`count(key, ok, *, review=False, reason='')` is the atomic import's per-entity counter: "
        "`amount = 1 if not isinstance(ok, int) else ok`, `if amount:` accumulates and increments "
        "`results['imported']`, `elif review:` records an explicit REVIEW_REQUIRED row (4814-4831). "
        "Zero means 'nothing imported for this entity' and is handled.", None),
    "INV34-001026": (VC,
        "`audit_report_id = next(iter(contexts))[1] if len(contexts) == 1 else None` exists only to "
        "type the audit row (`entity_type='daily_report' if audit_report_id else 'survey_batch'`). "
        "The subject is a primary-key report id; None means 'more than one context', the intended "
        "branch.", None),
    "INV34-001116": (DDD,
        "`save_daily_report` parses report_date with the single format '%Y-%m-%d' and swallows the "
        "ValueError. The column is `report_date = Column(Date, nullable=False)` "
        "(core/database.py:337), so a non-parseable string cannot be stored silently: SQLAlchemy "
        "fails at bind time and the caller's transaction rolls back. Every producer of a string "
        "emits ISO: excel_intelligence.py:1624 `.isoformat()`, mineru_engine.py:1600 `.isoformat()`, "
        "w1_well_info.py:723 and w2_Daily_Report.py:1869 `yyyy-MM-dd`.",
        "Should an unparseable report_date be rejected at the persistence boundary with a domain "
        "message instead of surfacing as an ORM bind error?"),
    "INV34-001117": (VC,
        "`_number_value` returns None for absent, non-numeric or non-finite values and its callers "
        "test exactly that: `if value not in (None, '') and _number_value(value) is None and ...` "
        "(4941) and `elif _number_value(row.get('working_pressure')) is None:` (4962) - None routes "
        "the row to validation/review, per the comment 'Validate every row that would otherwise be "
        "discarded'.", None),
    "INV34-001119": (INT,
        "The parsed `hours` only decorates the remarks text (`hrs = f'[HRs: {hours:.0f}] '`, 5068); "
        "the persisted row is SevenDaysLookahead, whose columns (core/database.py:1706-1725) contain "
        "no hours field. A failed parse drops the prefix and keeps the remarks - no numeric loss.",
        None),
    "INV34-001125": (VC, "Same site as INV34-001117 (core/database.py:4901): duplicate record of "
                    "the same construct; the contract quoted there decides both.", None),
    "INV34-001126": (VC, "Same site as INV34-001117 (core/database.py:4901): duplicate record.", None),
    "INV34-001258": (INT,
        "`session.close()` in a `finally` whose handler is `pass`: a close failure must not mask the "
        "import's original exception (`logger.error('Import rollback failed', exc_info=True)` is the "
        "rollback path above it). The same contract is implemented in core/database.py "
        "`release_session`.", None),
    "INV34-001321": (VC,
        "`fallback = session.get(Well, self.well_id) if self.well_id else None` is a primary-key "
        "presence test; the well is used only to scope the candidate query to the same project "
        "before identity resolution by code/name (lines 151-156). A falsy id means 'no well context "
        "supplied'. Covered by tests/test_ddr_forensic_regressions.py:368.", None),
    "INV34-001370": (DUP,
        "The construct is `return False` in the export error handler (lines 62-64) - a boolean "
        "success signal for `export(...) -> bool`, not a numeric measurement. The rule that raised "
        "the finding (numeric-get-default) does not apply to this construct.", None),
    "INV34-001380": (DUP, "Same site as INV34-001370 (core/ddr_pdf_export.py:64): the returned value "
                    "is a boolean, so the or-zero rule mis-fired here.", None),
    "INV34-002042": (VC,
        "The ordering check `float(depth_out) < float(depth_in)` can only raise when a value is "
        "non-numeric, and that case is already reported above it: both depth_in and depth_out are in "
        "`NUMERIC_FIELDS` (676-677), whose loop (724-731) emits "
        "`report.error(sheet, row_number, 'Must be numeric', field, value)`.", None),
    "INV34-002065": (DDD,
        "On failure the facade returns `{'ft_min': 0, 'm_min': 0, 'status': str(exc)}` while the "
        "sibling `calculate_hsi` two methods above returns None. The single caller renders "
        "`result.get('ft_min', 0)` into the field and ignores `status` "
        "(tabs/w3_drilling_report.py:778-781); the widget minimum is documented in that file as the "
        "'not computed' state, so no wrong number reaches the screen - but the dict presents 0 "
        "ft/min as a value to any other consumer and the error text never reaches the user.",
        "Should a failed annular-velocity computation report an absent value (like "
        "calculate_hsi/None) instead of zeros, and should the widget surface `status`?"),
    "INV34-002066": (VC,
        "`EngineeringManager.calculate_hsi` returns None on failure and its only caller passes the "
        "result through `_set_calc(self.hsi, hsi_val)` (tabs/w3_drilling_report.py:737), whose "
        "docstring says 'Show a real result, or fall back to the explicit \"not computed\" state' and "
        "which maps None to the field minimum. The failure stays visible.", None),
    "INV34-002069": (INT,
        "`apply_permissions` disables only the UI action (`auto_save_action.setEnabled(not "
        "is_viewer)`). The mutation path is independently gated: the timer calls "
        "`AutoSaveManager.save_widget` -> the widget's own `save_changes`/`save_data` "
        "(core/managers.py:79-86), and those tab save paths enforce their own permission contract "
        "(tabs/w5 save_all_data fail-closed, tabs/w16 save_data SYSTEM_ERROR, "
        "core.permissions.require_permission). A viewer cannot persist through this affordance.",
        None),
    "INV34-002072": (VC,
        "`_widget_for` imports QTableWidgetItem/Qt inside a try and returns None when the optional Qt "
        "binding is unavailable; the caller treats None as 'no widget for this value'. Optional "
        "dependency guard, not a swallowed domain failure.", None),
    "INV34-002075": (INT, "Same site as INV34-002069 (core/managers.py:316): duplicate record.", None),
    "INV34-002076": (INT, "Same site as INV34-002069 (core/managers.py:316): duplicate record.", None),
    "INV34-002095": (VC,
        "`report = self.db.get_daily_report_by_id(report_id) if report_id else {}` is an id presence "
        "test feeding the metadata dict; the same idiom is used and validated across the module "
        "(e.g. professional_export.py:51-53 raises when the fetched report does not belong to the "
        "well).", None),
    "INV34-002319": (VC,
        "`logs = ... if report_id else []` - a primary-key id presence test in the export section "
        "builder; the same parameter is validated at the top of the export "
        "(professional_export.py:51-53: `if report_id and (not report or report.get('well_id') != "
        "well_id): raise ValueError`).", None),
    "INV34-002320": (VC, "Same idiom as INV34-002319: `... if report_id else ...` id presence test "
                    "(core/professional_export.py:202).", None),
    "INV34-002321": (VC, "Same idiom as INV34-002319 (core/professional_export.py:213).", None),
    "INV34-002322": (VC, "Same idiom as INV34-002319 (core/professional_export.py:345).", None),
    "INV34-002327": (VC,
        "`report = db_manager.get_daily_report_by_id(report_id) if report_id else {}` is guarded by "
        "the very next statement - `if report_id and (not report or report.get('well_id') != "
        "well_id): raise ValueError('Export report must belong to the selected well')` (52-53) - and "
        "the selected well is validated on the next line.", None),
    "INV34-002333": (INT,
        "The merged-cell scan builds the set of slave cells to skip (line 693: `if (r, c) in "
        "merged_slaves: continue`). If it fails, slave cells are no longer skipped - but openpyxl "
        "returns None for non-anchor cells of a merged range, so the result is an unread cell, not a "
        "duplicated value. A failed optimisation degrades safely.", None),
    "INV34-002454": (VC,
        "`_extract_date_triplet` returns None when the three cells cannot be parsed, and its caller "
        "tests it: `if val is not None: ... extracted_data[section][key] = val` (line 193). None is "
        "the documented 'not extracted' signal; no wrong date is written.", None),
    "INV34-006875": (VC, "Same site as INV34-000717 (core/database.py:3485): duplicate record.", None),
    "INV34-006876": (INT,
        "`_verify_password` tries bcrypt for non-`sha256:` hashes; if bcrypt raises (malformed or "
        "foreign stored hash) execution falls through to the SHA-256 branch "
        "(`secrets.compare_digest`, 3512-3519) and then to the legacy static-salt comparison. A "
        "failed bcrypt check can therefore never return True - authentication fails closed.",
        None),
    "INV34-006877": (INT, "Same site as INV34-006876 (core/database.py:3510): the `pass` body is "
                    "that fall-through path.", None),
    "INV34-006916": (DDD, "Same site as INV34-001116 (core/database.py:4224): duplicate record of "
                     "the report_date boundary question.",
                     "Should an unparseable report_date be rejected at the persistence boundary with "
                     "a domain message instead of surfacing as an ORM bind error?"),
    "INV34-006954": (VC, "Same site as INV34-001117 (core/database.py:4901): duplicate record.", None),
    "INV34-006974": (INT, "Same site as INV34-001119 (core/database.py:5070): duplicate record.", None),
    "INV34-006975": (INT, "Same site as INV34-001119 (core/database.py:5071): duplicate record.", None),
    "INV34-007009": (VC,
        "`_fwf` returns None for absent or non-numeric fuel/water values, and the derived fields are "
        "computed only when all three inputs exist: `if None not in (fuel_stock, fuel_recv, "
        "fuel_cons): fw['fuel_remaining'] = ...` (5394-5397), likewise water. An unparseable reading "
        "yields 'not computed', never a fabricated total.", None),
    "INV34-007618": (VC, "Same site as INV34-002042 (core/import_quality.py:737): duplicate record.", None),
    "INV34-007635": (INT, "Same site as INV34-002069 (core/managers.py:317): duplicate record.", None),
    "INV34-007637": (INT,
        "`save()` persists only window geometry and dock state through QSettings "
        "(`setValue('window/geometry', ...)`, `setValue('window/state', ...)`, lines 450-455). A "
        "failure to remember window layout is a cosmetic UI preference; no domain state is written.",
        None),
    "INV34-007638": (INT, "Same site as INV34-007637 (core/managers.py:455): duplicate record.", None),
    "INV34-007673": (INT, "Same site as INV34-002333 (core/profile_import_engine.py:688): duplicate "
                    "record.", None),
    "INV34-007678": (VC, "Same site as INV34-002454 (core/profile_import_engine.py:753): duplicate "
                    "record.", None),
    "INV34-008737": (INT, "Same site as INV34-007637 (core/managers.py:454): duplicate record.", None),
}


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    batch = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(batch) != len(R):
        print(f"batch has {len(batch)} records, adjudications: {len(R)}")
        return 1

    stale = []
    for record in batch:
        expected = (record.get("current_source_line") or "").strip()
        try:
            actual = (ROOT / record["file"]).read_text(encoding="utf-8",
                                                       errors="replace").splitlines()[record["line"] - 1].strip()
        except IndexError:
            stale.append((record["id"], record["file"], record["line"], expected, "<beyond EOF>"))
            continue
        if re.sub(r"\s+", "", expected) != re.sub(r"\s+", "", actual):
            stale.append((record["id"], record["file"], record["line"], expected, actual))
    if stale:
        print("STALE EVIDENCE - not applying:")
        for item in stale:
            print("  ", item)
        return 2

    items = [{"id": record["id"], "file": record["file"], "line": record["line"],
              "classification": R[record["id"]][0], "evidence": R[record["id"]][1],
              "remaining_question": R[record["id"]][2],
              "defect": R[record["id"]][0] == "GENUINE_DEFECT",
              "test": None, "commit": None} for record in batch]

    counts: dict[str, int] = {}
    for item in items:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    payload = {
        "schema": "m36-p6-batch", "batch": BATCH, "class": "A (safety / authorization / mutation)",
        "records": len(items), "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [], "tests": "ledger/register validation (no production change)",
        "staleness": {"checked": len(batch), "stale": 0},
        "method": ("each record read at its own site in the current tree; the deciding contract is "
                   "quoted in `evidence`; duplicate records of one site are adjudicated once and the "
                   "duplication is stated in the evidence"),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, staleness 0")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
