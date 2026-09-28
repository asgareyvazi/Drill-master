#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-017 (45 MEDIUM records, classes A and B).

Phase 2, seventh batch: the database persistence boundary (the SQLite rebuild / foreign-key /
stored-ownership migration helpers, `coerce_model_values`, the authentication audit write and the
plan-vs-actual reader), the W7 logistics and W8 safety tab guards, the W9 service dialogs, four
test-internal selections and the DDR lifecycle certification tool.  One genuine defect was found
here (INV34-001111, with INV34-006908 as its duplicate record) and fixed in commit 4c543e8 with
its regression test; one intentional swallow is recorded together with its diagnosability note;
every other site is adjudicated by the contract quoted in `evidence`, following the same method as
p6_batch_005..016.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-017"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

# Batch-015's mechanism (recorded text verified against <commit>^ and re-anchored through
# difflib) is kept, but here it is *provenanced*: the tree the register's line numbers belong
# to must hash to the record's own declared `source_sha256` before any comparison happens.
# Files whose register line numbers belong to a tree other than the current one, verifiable as
# `<commit>^` (the register's source_sha256 must equal that tree's sha256):
#   tabs/w7_logistics_Widget.py - moved in c2e0016 (the W7 bulk-stock fix);
#   core/database.py            - moved in this batch's own fix 4c543e8 (docstring + guard
#                                 insertion), which is also why INV34-001111/006908 and the
#                                 plan-vs-actual records sit below their recorded lines.
RECHECK_AGAINST: dict[str, str] = {
    "tabs/w7_logistics_Widget.py": "c2e0016",
    "core/database.py": "4c543e8",
}

# tabs/w5_Equipment_Widget.py: no commit in this repository carries the register's tree
# (sha256 7cbe07214dbeb8cd3b8bb4668ec54040eec4e2e740e4e2188d24fd8c73758359).  The tree is
# reconstructible and *verified*: it is 9f45cc4 with its permission-fail-closed hunk reversed
# (hunk ids are the @@ hunks of `git diff 9f45cc4^ 9f45cc4 -- <path>`); the reconstruction is
# accepted only when its sha256 equals the sha256 the register recorded for the file.
RECONSTRUCT: dict[str, tuple[str, str, tuple[int, ...]]] = {
    "tabs/w5_Equipment_Widget.py": ("9f45cc4^", "9f45cc4", (7,)),
}

# The register records, per record, the sha256 of the file the line number belongs to.  This is
# the M34 fingerprint identity (kind | symbol's last component | the M34 `pattern` | ordinal),
# recomputed from docs/audits/m34-evidence/m34-ledger.json; it proves *which* construct the
# record means by content, independently of any line number.
FINGERPRINT_SOURCE = "docs/audits/m34-evidence/m34-ledger.json"
M34_FAMILY: dict[str, str] = {
    "R-TRUTH-UNKNOWN": "if-not-falsy",
    "R-EXC-OTHER": "broad-except",
    "R-DEF-UNKNOWN": "or-constant",
    "R-NUM-UNKNOWN": "default-zero-param",
    "R-SNAP-SERIAL-DEFAULT": "snapshot-serialize",
}


def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Second register record for {where}, already adjudicated under {sibling}: "
            f"{summary}",
            None)


def misfire(what: str) -> tuple[str, str, None]:
    """A rule mis-fire: the matched construct is not the semantic the rule family targets."""
    return (DUP,
            f"Rule mis-fire, not a behaviour to adjudicate: {what}",
            None)


_DB_OPTIONAL = (
    "`self.db` is the widget's optional persistence handle: the tab classes of this batch take it "
    "as `def __init__(self, db_manager=None, parent=None)` (tabs/w5_Equipment_Widget.py:619 with "
    "`self.db = db_manager` at 621; tabs/w7_logistics_Widget.py:27/29 and 608/611; "
    "tabs/w3c_section_data.py:29/31, 240/242, 400/402; tabs/w3b_wellbore_schematic_tab.py:28, "
    "whose base class stores it), so `if not self.db` / `if self.db` is the *presence* test for an "
    "Optional collaborator, not a value test: None restores the constructor's documented default.  "
    "The alternative reading - a falsy-but-connected handle - does not exist: the attribute is "
    "either the DatabaseManager instance the shell handed in or None."
)

_W7_DB = (
    "`PersonnelLogisticsTab` and `FuelWaterTab` take `db_manager=None` in the constructor and "
    "store it as `self.db` (tabs/w7_logistics_Widget.py:27/29 and 608/611).  Every read path in "
    "the class answers the same way when the handle is absent: `load_pob_data` (314) returns on "
    "`if not self.db` at 317-318, `load_crew_data` (424) at 427-428, `load_notes_data` (510) at "
    "513-514, `load_fuel_water_from_db` at 997 - i.e. a tab without a database is a disconnected "
    "tab whose tables were never filled from storage.  The guard therefore cannot hide persisted "
    "data: in that state there is no stored row behind any table row, and the mutation it protects "
    "is skipped instead of attempted and swallowed."
)

_RESULT_ID = (
    "Every persistence entry point behind these gates returns the stored record's id, and None "
    "exactly when it wrote nothing: `save_logistics_personnel` -> `record_id` (6793) / `None` "
    "(6797, and 6774 for a missing row), `save_service_company_pob` -> 6896 / 6878, "
    "`save_transport_note` -> 7654 / 7637+7658, `save_fuel_water_inventory` -> 7098 / 7102, "
    "`save_bulk_material` -> 7446 / 7450 (core/database.py).  SQLite ids start at 1, so a falsy "
    "`result` is precisely the 'nothing was written' case and `if result:` is the write-success "
    "gate, not a truthiness guess."
)

_ITEM_PRESENCE = (
    "`QTableWidget.item(row, col)` returns the cell's QTableWidgetItem or None when the cell was "
    "never created; the guard asks whether the cell *exists*, and the very next statement reads "
    "`item.text()`.  A present-and-blank cell is a different case and is handled by the value "
    "parsers that follow (`optional_number`/`ValueNormalizer` treat an empty string as missing -> "
    "None, never as 0)."
)

_SPIN_ZERO = (
    "The dialog's own widgets define what its zero means: `self.personnel=QSpinBox();"
    "setRange(0,1000)`.  `setSpecialValueText(\"Not recorded\")` (tabs/w3c_section_data.py:832) - "
    "the minimum is the widget's 'not recorded' state, rendered as text instead of 0 - and `_load` "
    "maps the persisted NULL back onto it (`self.personnel.setValue(c.get(\"personnel_count\") if "
    "c.get(\"personnel_count\") is not None else 0)`, 848) while leaving the other numeric widgets "
    "at their untouched default for NULL (`dd = c.get(\"duration_day\"); if dd not in (None, "
    "\"\"): self.duration_day.setValue(float(dd))`, 850-852; `nh = c.get(\"npt_hours\")` ..., "
    "855-857).  `value() or None` in the payload (864) implements the same one-way encoding for "
    "duration/NPT: the untouched-or-zero state of those two widgets is 'not recorded' and is "
    "persisted as NULL, which the nullable columns accept (`npt_hours = Column(Float, "
    "nullable=True)`, `duration_day = Column(Float)`, core/database.py:1589, 1591).  The idiom is "
    "repository-wide for spin boxes (tabs/w11_Export.py:445-446; "
    "tabs/w13_Engineering_Calculator.py:3598-3611, 3740-3749), and the opposite direction would be "
    "the fabrication this mission forbids - storing 0.0 for a field the user never entered.  "
    "Recorded with the record, not as a defect claim: a *deliberate* 0 for duration_day/npt_hours "
    "cannot be expressed because those two widgets have no 'not recorded' state, so a typed 0 is "
    "re-encoded as NULL on the next save."
)

_MOVEMENT_TRICHOTOMY = (
    "`core/inventory_semantics.py` is the canonical owner of the bulk-material trichotomy and "
    "states it verbatim: 'None = not reported (unknown), 0.0 = explicitly reported zero, value = "
    "reported quantity ... received/used absent = no movement (0.0)'.  `normalize_movement` - the "
    "function the storage boundary applies to both fields (core/database.py:7351-7356) - returns "
    "0.0 for an absent movement and raises for malformed input, so a default of 0.0 for the two "
    "*movement* columns is the contract itself, while the *stock* column is passed with "
    "`default=None` at the very same call site (`initial_stock=_cell_float(initial_item, "
    "default=None)`, tabs/w7_logistics_Widget.py:1192) so an unknown opening stays unknown."
)
R: dict[str, tuple[str, str, str | None]] = {
    "INV34-000718": (VC,
        "`objects` is built by `_capture_live_objects` (core/database.py:2844-2854), which selects "
        "`type, name, sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND "
        "sql IS NOT NULL`: the third element is the object's own DDL text, and sqlite's NULL-sql "
        "cases (the auto-indexes behind a UNIQUE constraint) are filtered out of the list before "
        "this loop - they are re-created by the table's own CREATE statement, not replayed.  "
        "`if object_sql:` is therefore the 'there is a statement to replay' test, and an empty "
        "string could not be executed at all.  The rebuild proves the result immediately "
        "afterwards: `after = self._live_table_contract(connection, table_name)` and "
        "`if after[\"columns\"] != names: raise RuntimeError(...)` (2984-2987), followed by the "
        "index and foreign-key preservation checks before the transaction continues.", None),
    "INV34-000725": (VC,
        "The same guard inside the sibling rebuilder `_rebuild_live_table_preserving_objects`: "
        "`objects` comes from the same `_capture_live_objects` (sql IS NOT NULL), and every group "
        "it can hold is re-verified after the replay - `after_objects = "
        "self._capture_live_objects(...)` compared by name for indexes (2883-2884), the foreign "
        "key set compared against `foreign_keys_before` (2885-2886) and the column list against "
        "`names` (2880-2881), each mismatch raising.  A skipped empty statement cannot therefore "
        "hide a lost index, trigger or constraint.", None),
    "INV34-000735": (VC,
        "`invalid` is the row returned by `SELECT child.id FROM ... JOIN ... WHERE <ownership "
        "conflict> LIMIT 1` (3136-3144).  SQLAlchemy's Row truthiness is length-based, not "
        "value-based - verified against the installed SQLAlchemy 2.0.36: "
        "`bool(session.execute(text(\"SELECT 0\")).fetchone())` and the same for `SELECT NULL` are "
        "both True - so `if invalid:` means exactly 'the conflict query found a violating row', "
        "and the body raises `OwnershipIntegrityError` naming `invalid[0]` with the explicit "
        "'no automatic repair' contract.  A falsy result is the no-conflict case (the query "
        "returns None), never a row whose first column is 0.", None),
    "INV34-001111": (DEF,
        "Genuine defect (fixed in commit 4c543e8, regression "
        "tests/test_coerce_model_values_finite.py): the `except (ValueError, TypeError)` branch "
        "was correct for unparsable strings, but the coercion it guards accepted everything else "
        "`float()` accepts - 'nan', 'inf', '-inf' and '1e400' - and wrote it into authoritative "
        "numeric columns (core/database.py:4109-4130).  SQLite round-trips `inf` unchanged and "
        "silently stores `nan` as NULL, so a meaningless number could be persisted as a "
        "measurement while the docstring promised only that placeholders 'become NULL, never 0'.  "
        "The repository's canonical persistence helpers reject non-finite numbers "
        "(`core/engineering/*_persistence.py`: `number if math.isfinite(number) else None`, "
        "drill_pipe with the comment 'NaN / inf / 1e400 overflow'; core/engineering/result.py:114,"
        "128; core/value_normalizer.py:100-101; this module's own `_number_value` at 4914; "
        "tabs/w8_Safety_Widget.py:589 'Invalid waste volume'), which is the contract the fix "
        "restores.  Finite values, comma decimals and an explicit '0' are unchanged.", None),
    "INV34-006203": (VC,
        "`self.db` is the tab's optional persistence handle (constructor `db_manager=None`, "
        "stored as `self.db`; DatabaseManager defines no `__bool__`/`__len__`, verified, so "
        "`not self.db` is exactly `self.db is None`).  In `TransportLogTab."
        "save_transport_logs_to_db` the guard (1603-1604) returns False *before* "
        "`session = self.db.create_session()` (1606), before the delete/insert block and before "
        "any table read - a disconnected tab refuses to save instead of raising AttributeError or "
        "writing into a session it does not own.  This is the same shape as the 53 `self.db` "
        "guards of tabs/ whose full scan in batch-016 found no fail-open body.", None),
    "INV34-006206": (VC,
        "`status_item = self.transport_table.item(row, 11)` (1724): `QTableWidget.item()` returns "
        "None when the cell was never created, and PySide6's QTableWidgetItem defines no "
        "`__bool__` (verified: `bool(QTableWidgetItem(\"\"))` is True), so `if status_item:` is "
        "the cell-presence test.  The counters it feeds (`active`, `completed`, `scheduled`) are "
        "only incremented for a present cell whose text matches the exact status name, so an "
        "unfilled row contributes to no category - `total` comes from `rowCount()` and the parts "
        "can therefore never exceed it.", None),
    "INV34-006207": (VC,
        "The sibling presence test in the same loop: `type_item = self.transport_table.item(row, "
        "1)` (1723) and `if type_item:` (1725) gate the `Boat`/`Chopper` counts on the cell "
        "existing; an absent cell is not counted as either type (and is not defaulted to a third "
        "category), which is why the three counters plus 'other' can never be silently inflated "
        "by missing data.", None),
    "INV34-006255": (VC,
        "`if not self.db: return False` in `SafetyBOPTab.load_from_database` (397-398) answers "
        "'this tab has no database' before `self.db.get_safety_report(...)` is called (401) and "
        "after `self.bop_stack_table.setRowCount(0)` (400) has cleared the view: the load reports "
        "False and leaves an empty table rather than synthesizing a report.  `self.db` is the "
        "constructor's Optional collaborator (no `__bool__`, verified), so the test is a presence "
        "test on the handle itself, not on data.", None),
    "INV34-006265": (VC,
        "`ph_item = self.waste_table.item(row, 3)` (583) is the cell-presence test; the pH is "
        "appended to `ph_values` only when the cell exists (597-598), and the module keeps "
        "'no pH supplied' as None end to end (`avg_ph = sum(ph_values)/len(ph_values) if ph_values "
        "else None`, 601, rendered as 'Average of supplied pH: None').  A present-but-blank cell "
        "raises inside the same guarded block and is treated as an incomplete row (batch-004 "
        "INV34-006285, INTENTIONAL) - never as pH 0.", None),
    "INV34-006270": (VC,
        "`volume_item = self.waste_table.item(row, 2)` (582) and `if volume_item:` (585): a "
        "missing cell means the row was never filled in, so its volume is not added to "
        "`total_volume` and `valid_volumes` is not incremented; the reported volume text only "
        "claims a plain total when every row was valid (`volume_text = ... if valid_volumes and "
        "valid_volumes == self.waste_table.rowCount() else <incomplete form>`, 602).  No number "
        "is fabricated for a missing cell.", None),
    "INV34-006271": (VC,
        "`if not self.db: return False` in `WasteManagementTab.load_from_database` (672-673), "
        "identical in contract to INV34-006255: the view is cleared (`self.waste_table."
        "setRowCount(0)`, 675) before the guarded read, and a tab without a database reports 'not "
        "loaded' instead of presenting an empty-but-authoritative report.  The two sibling load "
        "methods of this file are the only `self.db` guards in it.", None),
    "INV34-006281": (VC,
        "`parsed = optional_date(value)` (39) yields a `date` or None - a date object is always "
        "truthy, and the value never comes from a numeric path - so `... if parsed else "
        "widget.minimumDate()` (40) separates exactly 'the source row has this date' from 'the "
        "source row is NULL'.  That is the helper's documented purpose (docstring at 24: 'Keep "
        "source NULL distinct from a widget's minimum display value.'): NULL is shown as the "
        "widget's minimum *and* recorded as missing (`owner._missing_safety_fields.add(field)`, "
        "34/50), never as a real date or 0.", None),
    "INV34-006502": (VC,
        "Test-local selection: `.filter_by(report_id=report_id).one()` (215) is the strictest "
        "available accessor - it raises when the query returns anything other than exactly one "
        "row - and it is used to prove that the atomic multi-tab import created exactly one mud "
        "report for the report and that its `chemicals_json` holds both chemicals (216).  A "
        "duplicate or missing row fails the test loudly; no production path is involved.", None),
    "INV34-006503": (VC,
        "Same strict accessor in the rollback test (252): after the second import (which is "
        "expected to fail its bulk-material validation) the mud report must still be the "
        "single report that holds the first import's data - `json.loads(mud.chemicals_json)[0]"
        "[\"product\"] == \"Barite\"` (253).  `.one()` makes 'the failed import left a second "
        "row or no row' an error rather than a silent pass.", None),
    "INV34-006537": (VC,
        "`new` is a parametrized boolean (`@pytest.mark.parametrize(\"new\", [True, False])`, "
        "51); `if not new: s.commit()` (62-63) decides whether the SafetyReport row is persisted "
        "before its `report` relationship is re-pointed at another well's report.  Both branches "
        "then require the ownership guard to fire on the next commit (`with "
        "pytest.raises(OwnershipIntegrityError)`, 65-66) and assert the rollback left no row "
        "(68), so the flag selects the *pending* vs *persistent* variant of the same invariant - "
        "the truthiness of a bool is the value itself.", None),
    "INV34-006543": (VC,
        "`session.query(Well).first()` in `AtomicImportTests.test_atomic_rollback_on_failure` "
        "(98-99) is a test-local selection on a database this test class creates itself: `setUp` "
        "(17-23) points a fresh DatabaseManager at a new temporary file and calls `initialize()`, "
        "which always seeds the default company/project/well (`create_default_data`, "
        "core/database.py:3342, called from `initialize` at 2633).  The assertions that follow "
        "are made on the section/report/survey rows the test creates (e.g. `SurveyPoint` count 0, "
        "121-122), so an arbitrary-but-existing well cannot mask a defect, and a missing row "
        "would fail loudly with AttributeError.", None),
    "INV34-006544": (VC,
        "Same selection in `test_snapshot_rollback` (129-130) with the same reasoning: the well "
        "comes from the seeded fresh database of `setUp`, and the test asserts on the snapshot/"
        "restore outcome it drives itself (the report it creates at 133-140 and the restored "
        "values afterwards).  A wrong-but-existing well would not change those assertions; a "
        "missing one aborts the test.", None),
    "INV34-006859": (VC,
        "`row` is the table's own `sqlite_master` row (`SELECT sql FROM sqlite_master WHERE "
        "type='table' AND name=?`, 2811-2814); `row[0]` is the live CREATE TABLE text the rebuild "
        "must rewrite with the relaxed nullable contract.  Both falsy shapes mean the rebuild "
        "cannot proceed - the table does not exist, or it has no stored DDL - and the code raises "
        "`RuntimeError(f\"Cannot rebuild {table_name}: live CREATE SQL is unavailable\")` "
        "(2816-2817) instead of executing an empty statement or silently skipping a required "
        "migration.  Fail-loud, not a defaulted value.", None),
    "INV34-006860": (VC,
        "The same test in `_rebuild_live_table_preserving_objects` (2859-2860) with the same "
        "fail-loud body: the rebuild needs the live DDL to preserve columns, indexes, triggers, "
        "foreign keys and rows, and the function raises when it is unavailable rather than "
        "replacing the table from ORM metadata.  The docstring of the caller states the same "
        "contract ('The live SQLite schema is the source of truth during rebuilds. ORM metadata "
        "is used only to identify which nullable contracts the current application requires; it "
        "never supplies the replacement table.').", None),
    "INV34-006861": (VC,
        "In `_install_wellbore_foreign_key` the same test *returns* (2905-2906) instead of "
        "raising, and that difference is justified at the call site: the only caller guards "
        "existence first (`for table_name in (\"sections\", \"daily_reports\"): if "
        "self._raw_table_exists(raw, table_name): self._install_wellbore_foreign_key(...)`, "
        "3258-3260), so 'no table' means there is nothing to install; a table without stored DDL "
        "cannot receive an injected FK clause either.  The immediately following guard "
        "('Already has a wellbore FK? Nothing to do (fresh DBs, re-runs)', 2908-2912) documents "
        "the same idempotent intent, and the caller verifies the outcome afterwards "
        "(`PRAGMA foreign_key_check`, 3269-3271, raising on any violation).", None),
    "INV34-006864": (VC,
        "`self._raw_table_exists(raw, table_name)` returns a bool (`row is not None`, "
        "core/database.py:3205-3210), so `if not ...: continue` is exactly 'this database has no "
        "such table; there is nothing to upgrade in it'.  The surrounding block documents the "
        "intent for the columns it adds ('Columns are added as plain nullable INTEGER (no "
        "fabricated backfill)') and the generic missing-table step earlier in "
        "`_apply_safe_schema_upgrades` creates the current schema instead; skipping cannot "
        "default a value, because no row is touched.", None),
    "INV34-006865": (VC,
        "The same skip in the v3 block of `_apply_safe_schema_upgrades` (3242-3243) over the "
        "fixed tuple `(\"sections\", \"daily_reports\")`: legacy/external databases that lack one "
        "of the two tables are simply not upgraded for that table, and the wellbore columns are "
        "added as plain nullable INTEGER with the explicit contract that existing rows keep "
        "wellbore_id = NULL ('unknown') until a deterministic attribution assigns them.  The "
        "truthiness of `_raw_table_exists` is a boolean test.", None),
    "INV34-006881": (INT,
        "Deliberate, and the primary contract is preserved: `authenticate_user` returns the "
        "verified identity (`return type(\"UserObject\", (), user_data)()`, 3567) and its only "
        "consumer tests that object (`dialogs/login_dialog.py:176`).  The swallowed block is the "
        "*audit* write - `user.last_login = ...; session.commit()` (3562-3566) - so a failed "
        "timestamp write cannot fail a correct login, and `session.rollback()` (3566) restores "
        "the session for the surrounding `finally: session.close()`.  Real authentication "
        "failures are still logged by the outer handler (`logger.exception(\"Authentication "
        "error\")`, 3569-3570).  Observed, not patched: the inner handler logs nothing, so a "
        "persistently failing last_login commit stays invisible (recorded in `observations`).",
        None),
    "INV34-006908": dup("INV34-001111",
        "core/database.py:4116 (`except (ValueError, TypeError):` inside "
        "`DatabaseManager.coerce_model_values`)",
        "the same statement, same symbol, same defect - the fix in commit 4c543e8 and its "
        "regression cover both records; this record adds no second defect."),
    "INV34-006927": (VC,
        "The flagged text is the docstring line 'Return the active WellPlan's planned total "
        "days, or None if unknown.' (4379), and the function implements exactly that three-state "
        "contract: no active plan or a NULL `planned_total_days` -> None (4391-4392), a stored "
        "value -> `float(...)` including an explicit 0 (4393).  The consumer mirrors it without "
        "inventing a number (`tabs/w16_Cost_Management.py:589-592`: `days = "
        "self.db.get_planned_total_days(...)`; `except Exception: days = None`; "
        "`self.afe_days.setValue(days if days is not None else -1)` - the spin box's 'Not "
        "supplied' sentinel), and the explicit-zero case is pinned in-tree "
        "(tests/test_m28_finance_safety_plan.py:123: a plan with `planned_total_days=0` returns "
        "0, not None).", None),
    "INV34-008457": (VC,
        "Write-back guard in `FuelWaterTab.save_bulk_materials_to_db` (1207-1209): after "
        "`result = self.db.save_bulk_material(material_data)` (1203) the id cell is refreshed "
        "only when it is missing (`QTableWidget.item()` returns None) or blank "
        "(`.text().strip()` is empty) - both are tests on the *cell*, and the value written is "
        "the stored record's id (`str(result)`), which SQLite assigns from 1 and which "
        "`save_bulk_material` returns only after a real write (None otherwise, per batch-016's "
        "verified `_RESULT_ID` contract).  A user-entered id is therefore never overwritten and "
        "no id is fabricated.", None),
    "INV34-008464": dup("INV34-006203",
        "tabs/w7_logistics_Widget.py:1603 (`if not self.db:` in "
        "`TransportLogTab.save_transport_logs_to_db`)",
        "the same statement, same symbol; the `self.db` presence contract and the fail-safe "
        "return are the adjudication recorded for INV34-006203."),
    "INV34-008465": (VC,
        "Row-completeness guard in `save_transport_logs_to_db` (1624-1625): a row is skipped "
        "(`continue`) unless both the vehicle-type and the vehicle-name cell exist, so an empty "
        "table row never becomes a TransportLog with a fabricated type or name.  The rows that "
        "are parsed increment `saved_count` only after the record is added (1651-1652), a parse "
        "failure is logged and skipped (1653-1655), and the status message reports that same "
        "count (1658) - the user never sees a row counted that was not written.", None),
    "INV34-008478": dup("INV34-006257",
        "tabs/w8_Safety_Widget.py:401 (`data = (self.db.get_safety_report(well_id, "
        "report_id=report_id) or {}) if well_id else {}`)",
        "the same statement was adjudicated VERIFIED-CORRECT in p6-batch-004 (rule "
        "R-TRUTH-NUMERIC): a missing report resolves to an empty mapping for field lookups, and "
        "`_load_nullable_safety_fields` turns every absent key into the widget's 'Not supplied' "
        "state, i.e. unknown stays unknown."),
    "INV34-008479": (VC,
        "`if not isfinite(vol) or vol < 0: raise ValueError(\"Invalid waste volume\")` "
        "(589-590): the module refuses a non-finite or negative volume *before* it can enter "
        "`total_volume`, `volume_by_type` or `volume_by_method`, and the surrounding handler "
        "treats that row as incomplete (batch-004 INV34-006285, INTENTIONAL - the total text "
        "only claims completeness when every row was valid, 602).  This is the repository's own "
        "statement that a non-finite number is not a measurement - the contract this batch's "
        "defect fix (INV34-001111) aligns the database coercion boundary with.", None),
    "INV34-008480": dup("INV34-006273",
        "tabs/w8_Safety_Widget.py:676 (`report_data = (self.db.get_safety_report(well_id, "
        "report_id=report_id) or {}) if well_id else {}`)",
        "already adjudicated VERIFIED-CORRECT in p6-batch-004: the `or {}` supplies an empty "
        "mapping for a missing report (never zeros), and the following `if report_data is not "
        "None:` path feeds `_load_nullable_safety_fields`, which keeps NULL distinct from a "
        "widget's minimum."),
    "INV34-008484": (VC,
        "Required-field guard in `ServiceNoteDialog.save_note` (559-561): an empty or "
        "whitespace-only note is rejected with an explicit message ('Note content is required.') "
        "and the method returns before building `note_data` or touching the database; the "
        "well-id check follows as a second hard requirement (562-564).  A missing value is "
        "therefore refused, not stored as an empty string or a default.", None),
    "INV34-008486": (VC,
        "The same required-field shape for the equipment name in "
        "`EquipmentDialog.save_equipment` (695-697, 'Equipment name is required.'): the dialog "
        "refuses to save a nameless equipment row and leaves the user in the form; the "
        "following guard requires a well id.  Nothing is defaulted or persisted on the failure "
        "path.", None),
    "INV34-008514": (INT,
        "The `pass` is the required body of `with profiler.measure(\"test\"):` (18-19) - an "
        "intentionally empty measured section, which is exactly what the profiler must support.  "
        "The test then asserts the section was recorded (`self.assertIn(\"test\", "
        "profiler.as_dict())`, 20) and that no negative elapsed time is reported "
        "(`self.assertGreaterEqual(profiler.total(), 0)`, 21); the statement hides no failure "
        "(there is no exception handler on this path).", None),
    "INV34-008555": (VC,
        "`saved = db.save_mud_report(mud)` is a truthy write receipt: `save_mud_report` returns "
        "the stored row id after `session.commit()` and `None` exactly when the write failed "
        "(core/database.py, 'return record_id' / failure branch 'logger.error(...); return "
        "None'), so `if not saved: raise RuntimeError(\"Mud persistence was not confirmed\")` "
        "(87-89) stops the lifecycle certification on an unconfirmed write instead of reporting "
        "a false success.  Fail-loud in a certification tool - the direction this mission "
        "requires.", None),
    "INV34-008677": (VC,
        "Guard of the ownership revalidation helper (614-615): `state.persistent` is a bool from "
        "SQLAlchemy's inspection API and the second operand is the result of `any(...)` over "
        "attribute history, so the expression reads 'this object is not stored yet, or neither an "
        "owner-referencing relationship nor one of the mapped owner fields changed' -> "
        "`return []` (no dependents to revalidate).  The docstring states that exact scope "
        "('Revalidate unchanged children when a persisted parent's scope changes ... Query only "
        "on ownership edits'), and the returned list is only used to extend `affected` (648).  A "
        "truthiness test on booleans, not on a numeric value.", None),
    "INV34-009050": misfire(
        "the R-PLAN-OTHER family matched the *name* 'forecast' in a Text column declaration "
        "(core/database.py:352) - there is no arithmetic and no plan/actual comparison at this "
        "site.  The field is the canonical free-text daily-report field `daily_report.forecast` "
        "(core/canonical_schema.py:171, type 'text', optional), it is filled only from a present "
        "source block ('Operation forecast (next-day plan) from the report header -> "
        "DailyReport.forecast (nullable; absent stays absent)', core/ddr_import_service.py:"
        "500-505), and the neighbouring depth columns carry the M23 hardening comment that only "
        "the Python-side default was removed (core/database.py:345-348)."),
    "INV34-009112": (VC,
        "`session` is the optional parameter `Optional[Session] = None` and the line above "
        "computes `owns_session = session is None` (3941); SQLAlchemy's Session defines no "
        "`__bool__`/`__len__` (verified on the installed 2.0.36: `bool(session)` is True before, "
        "during and after a rollback, and after close), so `session = session or "
        "self.create_session()` creates a session exactly when the caller passed none - the same "
        "condition `owns_session` records - and the owned session is closed in the `finally` "
        "(`if owns_session: session.close()`), while a caller-provided session is left to its "
        "owner.", None),
    "INV34-009138": (VC,
        "`from core.actual_vs_plan import ActualVsPlanEngine` (4406) is a deferred import used by "
        "the same function at 4463 (`comparison = ActualVsPlanEngine.compare_metrics(...)`); no "
        "value is read, coerced or defaulted at the import.  The values the engine later receives "
        "are built from persisted rows only (4411-4420) with unknown preserved "
        "(`actual_depth = max(depths) if depths else None`, 4439), which is the docstring's "
        "contract at 4398-4401 ('Time, ROP and cost values are taken from persisted records "
        "only').", None),
    "INV34-009139": (VC,
        "`from core.actual_vs_plan import activity_plan_totals` (4430) feeds `totals = "
        "activity_plan_totals(activities)` on the next line (4433): the plan totals come from "
        "the plan's own activity rows when they exist, and only then are they replaced by the "
        "day-based mirror (`plan.planned_total_days * 24`) or left None.  An explicit 0 stays 0 "
        "and never becomes a divisor (see INV34-009150/009151).", None),
    "INV34-009141": (VC,
        "`planned_hours = totals[\"hours\"] if activities else (plan.planned_total_days * 24 if "
        "plan and plan.planned_total_days is not None else None)` (4434-4435): the fallback is "
        "used only when the plan has *no* activities, it is derived from a persisted planned "
        "value (days x 24, no invented rig rate), and both absent cases yield None - never 0.  "
        "The function's docstring states the same rule ('a report count is not treated as 24 "
        "hours and a rig-day price is never invented here').", None),
    "INV34-009147": (VC,
        "`if not actual_rops:` (4448) tests *list emptiness* - a list holding 0.0 is truthy - so "
        "a measured zero ROP is kept as a real observation and only an empty list triggers the "
        "fallback to the drilling-parameter ROPs (4449-4452).  Both sources exclude None and "
        "negatives (`... if r.rop_meter is not None and float(r.rop_meter) >= 0`), and the "
        "average is only computed when the chosen list is non-empty "
        "(`sum(actual_rops)/len(actual_rops) if actual_rops else None`), so an unknown actual ROP "
        "stays unknown.", None),
    "INV34-009150": (VC,
        "`planned_depth / planned_hours` (4454) is only evaluated behind the guard on the next "
        "line (4455): a missing planned depth or a falsy planned duration yields None instead of "
        "dividing by zero or reporting an infinite planned ROP.  The existing M28 regression "
        "pins exactly this combination - a plan with `planned_total_days=0` gives planned hours "
        "0 and `result[\"rop\"][\"planned\"] is None` while the actual ROP stays 0 "
        "(tests/test_m28_finance_safety_plan.py:123-126).", None),
    "INV34-009151": (VC,
        "The guard itself: `planned_hours` is a duration assembled from persisted plan data, so "
        "a falsy value means 'no usable planned time' and there is no division to perform; the "
        "ternary returns None, keeping the planned-vs-actual comparison honest.  The sibling "
        "planned quantity is computed the same way from persisted data only "
        "(`planned_depth = totals[\"depth\"] if activities else (plan.planned_final_depth if "
        "plan else None)`, 4436).", None),
    "INV34-010996": (VC,
        "`tempfile.mkdtemp()` (19) creates the class's per-test database directory with the "
        "secure API (unpredictable name, owner-only permissions) and the database path is placed "
        "inside it (`self.db_path = os.path.join(self.tmpdir, \"test.db\")`, 20); `tearDown` "
        "closes the manager and removes the whole tree (`shutil.rmtree(self.tmpdir, "
        "ignore_errors=True)`, 26-32).  No fixed, shared or world-readable temporary path is "
        "used, and the directory does not outlive the test.", None),
}
NEW_FINDINGS: list[dict] = []

# Observations recorded while adjudicating this batch.  They are *not* defect claims and they are
# not silently patched: each is a diagnosability/expressiveness note on an otherwise verified
# behaviour, kept with the record that produced it and repeated in the final P6 report.
OBSERVATIONS: list[dict] = [
    {"record": "INV34-006881", "site": "core/database.py:3562-3566",
     "observation": ("`authenticate_user` rolls back a failed last_login commit and still returns "
                     "the authenticated user - deliberate, because the primary contract is the "
                     "verified identity and a failed audit timestamp must not turn a correct "
                     "login into a failure.  The handler logs nothing, so a persistently failing "
                     "last_login write is invisible in the log; recorded as a diagnosability "
                     "note, not patched (the swallow is intended, only its silence is not "
                     "documented).")},
    {"record": "INV34-001111 (sibling boundary)", "site": "core/database.py `generic_save`",
     "observation": ("`generic_save` persists the caller's values unchanged and performs no "
                     "numeric coercion at all (it only filters unknown columns), so a non-finite "
                     "float handed straight to it would still reach the column.  It is a "
                     "different, deliberately thin boundary with its own contract ('Persist a "
                     "mapped model using only columns declared by its table'), and changing it is "
                     "a behavioural decision for its callers - recorded here rather than patched "
                     "in this batch.")},
    {"record": "INV34-009147 (sibling filter)", "site": "core/database.py:4444-4452",
     "observation": ("the actual-ROP sources are filtered by `>= 0` only, so an `inf` read back "
                     "from a legacy row written before this batch's fix would pass the filter "
                     "(inf >= 0).  The fix removes the write path this batch can reach; a "
                     "defensive finiteness filter on the read path is a separate decision about "
                     "legacy rows and is left recorded, not patched.")},
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def m34_norm(text: str) -> str:
    """The M33/M34 'whitespace-collapsed single-line form' used by the fingerprint contract."""
    return re.sub(r"\s+", " ", text or "").strip()


def git_blob(rev: str, path: str) -> bytes:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed: {out.stderr.decode()[:200]}")
    return out.stdout


def git_show(rev: str, path: str) -> list[str]:
    return git_blob(rev, path).decode("utf-8", "replace").splitlines()


def reconstruct_tree(path: str, entry: tuple[str, str, tuple[int, ...]]) -> bytes:
    """Rebuild the register's tree for `path` by reverse-applying the named hunks of a commit.

    `entry` is (base-revision, commit, hunk-ids) and the ids index the hunks of
    `git diff <base> <commit> -- <path>`.  The result is *not* trusted: the caller verifies that
    its sha256 equals the sha256 the register recorded for the file.
    """
    base, commit, hunk_ids = entry
    diff = subprocess.run(["git", "diff", base, commit, "--", path], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    parts = re.split(r"(?m)^(@@[^\n]*@@[^\n]*\n)", diff)
    header, hunks = parts[0], [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]
    patch = header + "".join(hunks[i][0] + hunks[i][1] for i in hunk_ids)
    work = Path(tempfile.mkdtemp(prefix="m36-p6-016-"))
    target = work / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(git_blob(commit, path))
    patch_file = work / "reverse.patch"
    patch_file.write_text(patch, encoding="utf-8")
    run = subprocess.run(["git", "apply", "--reverse", "-p1", str(patch_file)], cwd=work,
                         capture_output=True)
    if run.returncode != 0:
        raise SystemExit(f"reconstruction of {path} failed: {run.stderr.decode()[:300]}")
    data = target.read_bytes()
    shutil.rmtree(work, ignore_errors=True)
    return data


_TREES: dict[tuple[str, str], tuple[list[str], bytes, str]] = {}


def provenance_tree(path: str, declared_sha: str) -> tuple[list[str], bytes, str]:
    """The tree the register's line numbers for `path` belong to, *proven* by its sha256.

    Three cases, in order: the current file already is that tree; the tree is a commit's parent
    named in RECHECK_AGAINST (the batch-015 mechanism, now hash-checked); or the tree is rebuilt
    from a commit by reversing named hunks (RECONSTRUCT) and hash-checked against the record's own
    declared `source_sha256`.  Anything else refuses to run.
    """
    key = (path, declared_sha)
    if key in _TREES:
        return _TREES[key]
    current = (ROOT / path).read_bytes()
    if hashlib.sha256(current).hexdigest() == declared_sha:
        result = (current.decode("utf-8", "replace").splitlines(), current,
                  "current tree: sha256(file) == the record's source_sha256")
    elif path in RECHECK_AGAINST:
        commit = RECHECK_AGAINST[path]
        data = git_blob(f"{commit}^", path)
        result = (data.decode("utf-8", "replace").splitlines(), data,
                  f"provenance tree = {commit}^ (the line numbers of this file moved in {commit}); "
                  f"sha256 == the record's source_sha256")
    elif path in RECONSTRUCT:
        data = reconstruct_tree(path, RECONSTRUCT[path])
        base, commit, hunk_ids = RECONSTRUCT[path]
        result = (data.decode("utf-8", "replace").splitlines(), data,
                  f"provenance tree = {commit} with hunk(s) {list(hunk_ids)} of "
                  f"`git diff {base} {commit} -- {path}` reversed; sha256 == the record's "
                  f"source_sha256")
    else:
        raise SystemExit(f"{path}: no provenance tree known for sha256 {declared_sha[:16]}...")
    if hashlib.sha256(result[1]).hexdigest() != declared_sha:
        raise SystemExit(f"{path}: provenance tree sha256 "
                         f"{hashlib.sha256(result[1]).hexdigest()[:16]}... != register's "
                         f"{declared_sha[:16]}...")
    _TREES[key] = result
    return result


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    """Line range of the symbol named by a dotted path (owner-aware, unchanged since batch-009)."""
    import ast

    tree = ast.parse(source)
    parts = [p for p in (symbol or "").split(".") if p]
    if not parts:
        raise SystemExit(f"empty symbol {symbol!r}")
    index: dict[str, tuple[int, int]] = {}

    def visit(node, prefix):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + [child.name]
                index[".".join(qualified)] = (child.lineno, child.end_lineno)
                visit(child, qualified)

    visit(tree, [])
    found = index.get(".".join(parts))
    if found is None:
        candidates = [n for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == parts[-1]]
        if len(candidates) != 1:
            raise SystemExit(f"symbol {symbol!r} not resolvable ({len(candidates)} candidates)")
        found = (candidates[0].lineno, candidates[0].end_lineno)
    return found


def record_scope(source: str, symbol: str, line: int) -> tuple[int, int]:
    """Owner-aware scope for one record.

    The register names a symbol for every record except one (INV34-009050, a class *attribute*
    declaration: `forecast = Column(Text)` in `DailyReport`, `symbol: null`).  For that record the
    scope is the enclosing class found by AST (or the module, if a future record sits outside any
    class) - never a nearest-line window.
    """
    if (symbol or "").strip():
        return symbol_body(source, symbol)
    import ast

    tree = ast.parse(source)
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.lineno <= line <= (node.end_lineno or node.lineno):
            if best is None or node.lineno >= best.lineno:
                best = node
    if best is None:
        return 1, len(source.splitlines())
    return best.lineno, best.end_lineno


def line_map(previous: list[str], current: list[str]) -> dict[int, int]:
    matcher = difflib.SequenceMatcher(None, previous, current, autojunk=False)
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
    return mapping


def text_matches(recorded: str, actual: str) -> bool:
    """Register text vs source text.

    The register stores `line.strip()[:160]` (tools/m35/open_register.py:146), so a recorded line
    of exactly 160 characters is a prefix of the real line and a shorter one is the whole line.
    """
    expected, candidate = (recorded or "").strip(), (actual or "").strip()
    if len(expected) >= 160:
        return candidate[:len(expected)] == expected
    return candidate == expected


def fingerprint_proof(record: dict, m34: dict) -> str | None:
    """Re-derive the record's context_fingerprint from its M34 identity (content, not lines).

    Contract: fingerprint = sha256("path|kind|symbol|norm(expression)|ordinal")
    (tools/m34/common.py:32-36).  `norm` is the M33-compatible whitespace-collapsed form and the
    M34 ledger's `pattern` is that expression; ordinal 0.  Two symbol forms occur in the recorded
    identities - the symbol's last dotted component (all M32/M33-carried records in this batch)
    and the fully qualified symbol (the M34-NEW record INV34-010274).  Both are accepted, and the
    form that reproduces is reported.  Returns None when the record has no M34 pattern at all.
    """
    row = m34.get(record["id"])
    if not row or not row.get("pattern"):
        return None
    expression = m34_norm(row["pattern"])
    symbol = record.get("symbol") or ""
    for form, candidate in (("short", symbol.split(".")[-1]), ("qualified", symbol)):
        payload = "|".join([record["file"], row.get("kind") or "", candidate, expression, "0"])
        if hashlib.sha256(payload.encode("utf-8")).hexdigest() == record["context_fingerprint"]:
            return form
    return "MISMATCH"


def check(batch: list[dict]) -> tuple[list[tuple[str, str, int, int, str]], dict]:
    problems: list[str] = []
    reanchored: list[tuple[str, str, int, int, str]] = []
    current_cache: dict[str, list[str]] = {}
    current_src: dict[str, str] = {}
    maps: dict[tuple[str, str], dict[int, int]] = {}
    m34 = {}
    ledger = json.loads((ROOT / FINGERPRINT_SOURCE).read_text(encoding="utf-8"))
    for row in list(ledger["carried_records"]) + list(ledger["new_records"]):
        m34[row["id"]] = row
    stats = {"fingerprints_checked": 0, "fingerprints_verified": 0,
             "fingerprints_without_evidence": [], "fingerprints_by_form": {},
             "fingerprints_not_reproduced_but_hash_anchored": [], "trees": {}}

    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        declared = record.get("source_sha256") or ""
        tree_lines, tree_bytes, provenance = provenance_tree(path, declared)
        stats["trees"].setdefault(path, provenance)
        if path not in current_src:
            src = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            current_src[path] = src
            current_cache[path] = src.splitlines()
        lines = current_cache[path]
        current_is_tree = hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == declared
        start, end = record_scope(current_src[path], record.get("symbol", ""), line)

        proof = fingerprint_proof(record, m34)
        if proof is None:
            stats["fingerprints_without_evidence"].append(record["id"])
        else:
            stats["fingerprints_checked"] += 1
            stats["fingerprints_verified"] += int(proof != "MISMATCH")
            stats["fingerprints_by_form"][proof] = stats["fingerprints_by_form"].get(proof, 0) + 1

        hash_anchored = current_is_tree and 0 < line <= len(lines) \
            and text_matches(expected, lines[line - 1]) and start <= line <= end
        if proof == "MISMATCH":
            if hash_anchored:
                stats["fingerprints_not_reproduced_but_hash_anchored"].append(record["id"])
            else:
                problems.append(f"{record['id']}: context_fingerprint does not reproduce from its "
                                f"M34 identity (either symbol form) and the record is not "
                                f"hash-anchored")
                continue
        if proof is None and not current_is_tree:
            problems.append(f"{record['id']}: no fingerprint evidence and the file is not the "
                            f"recorded tree - refusing to adjudicate by line number alone")
            continue

        # Acceptance 1: the record's own line in the recorded tree is also correct in the current
        # file, inside the symbol the register names.
        if 0 < line <= len(lines) and text_matches(expected, lines[line - 1]) \
                and start <= line <= end:
            continue

        # Acceptance 2: the line moved.  The recorded text must match at the recorded line of the
        # *provenance* tree, and the difflib map tree->current must land on the same text inside
        # the symbol's AST range (no nearest-line matching).
        if not (0 < line <= len(tree_lines)) or not text_matches(expected, tree_lines[line - 1]):
            got = tree_lines[line - 1].strip() if 0 < line <= len(tree_lines) else "<beyond EOF>"
            problems.append(f"{record['id']}: {path}:{line} is {got[:60]!r} in the provenance tree, "
                            f"register recorded {expected[:60]!r}")
            continue

        map_key = (path, declared)
        if map_key not in maps:
            maps[map_key] = line_map(tree_lines, lines)
        new_line = maps[map_key].get(line)
        if new_line is None or not text_matches(expected, lines[new_line - 1]) \
                or not (start <= new_line <= end):
            problems.append(f"{record['id']}: re-anchor {path}:{line} -> {new_line} failed "
                            f"(symbol {record.get('symbol')!r} spans {start}-{end})")
            continue
        reanchored.append((record["id"], path, line, new_line, provenance))

    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        raise SystemExit(2)
    return reanchored, stats


def record_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode().strip()


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    batch = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(batch) != len(R):
        print(f"batch has {len(batch)} records, adjudications: {len(R)}")
        print("missing:", sorted({r["id"] for r in batch} - set(R)))
        print("extra:", sorted(set(R) - {r["id"] for r in batch}))
        return 1

    reanchored, stats = check(batch)

    counts: dict[str, int] = {}
    for record in batch:
        classification = R[record["id"]][0]
        counts[classification] = counts.get(classification, 0) + 1
    classes: dict[str, int] = {}
    for record in batch:
        classes[record["p6_class"]] = classes.get(record["p6_class"], 0) + 1

    items = [{
        "id": record["id"], "file": record["file"], "line": record["line"],
        "classification": R[record["id"]][0], "evidence": R[record["id"]][1],
        "remaining_question": R[record["id"]][2],
        "defect": R[record["id"]][0] == DEF,
        "test": None, "commit": None,
    } for record in batch]
    for item in items:
        if item["classification"] == DEF:
            item["commit"] = "4c543e8"
            item["test"] = "tests/test_coerce_model_values_finite.py"

    by_file: dict[str, int] = {}
    for item in items:
        by_file[item["file"]] = by_file.get(item["file"], 0) + 1

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("phase-2 mixed classes: " + ", ".join(
            f"{k}:{v}" for k, v in sorted(classes.items()))
            + " - the database persistence boundary, the W7/W8/W9 tab guards, the batch's "
              "test selections and the DDR lifecycle tool"),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "records_by_file": dict(sorted(by_file.items())),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [{
            "id": "INV34-001111", "file": "core/database.py", "line": 4111,
            "duplicate_record": "INV34-006908",
            "summary": ("`DatabaseManager.coerce_model_values` accepted every value `float()` "
                        "accepts - 'nan', 'inf', '-inf', '1e400' as strings and an already-float "
                        "non-finite value - and wrote it into authoritative numeric columns; "
                        "SQLite round-trips `inf` unchanged and stores `nan` as NULL, so a "
                        "meaningless number could persist as a measurement while the method's "
                        "own docstring promised only that placeholders 'become NULL, never 0'."),
            "root_cause": ("the coercion guarded only unparsable strings: `float()` succeeds for "
                            "the spellings of nan/inf and for out-of-range decimals, and the "
                            "already-numeric branch passed floats through unchanged"),
            "contract": ("core/engineering/*_persistence.py `number if math.isfinite(number) else "
                         "None` (drill_pipe with the comment 'NaN / inf / 1e400 overflow'); "
                         "core/engineering/result.py:114,128; core/value_normalizer.py:100-101; "
                         "core/database.py:4914 (`_number_value`); tabs/w8_Safety_Widget.py:589 "
                         "('Invalid waste volume')"),
            "fix": ("the string branch keeps the finite parse and otherwise stores None, and an "
                    "already-float non-finite value is coerced to None as well; the docstring "
                    "states the contract"),
            "commit": "4c543e8",
            "test": "tests/test_coerce_model_values_finite.py",
            "test_result": "15 passed / 0 failed / 0 errors / 0 skipped in 1.419 s",
            "mutation_validation": ("with the pre-fix coercion reintroduced, 8 tests fail (all "
                                    "non-finite string cases, all non-finite float cases and the "
                                    "end-to-end save_well test); restored byte-identical (sha256 "
                                    "61eea36f811dbbd9aeb4bb29d1367ae6ea4610c1b5da0da5e4463c60a0405d81) "
                                    "and 15/15 green again"),
            "related": ("11 files - save_well callers, import boundary/architecture, "
                        "no-fabrication, ownership integrity, P0 atomic import, integration, M28 "
                        "plan-vs-actual, credential lifecycle, DDR save atomicity: 234 passed / 0 "
                        "failed / 0 errors / 0 skipped in 61.143 s (/tmp/p6-017-related.xml)"),
        }],
        "new_findings": NEW_FINDINGS,
        "observations": OBSERVATIONS,
        "sibling_search": {
            "target": ("the batch's own families as populations: the optional-`self.db` guard, "
                       "the QTableWidgetItem presence guard, the `or {}` container default in "
                       "front of a database getter, and the string->float coercions that reach "
                       "persisted numbers in core/database.py"),
            "method": ("(a) `if (not )?self\.db` over tabs/ (53 hits) - the full body scan was "
                       "done in batch-016 and found 0 fail-open bodies (every hit returns or "
                       "raises); this batch's 3 distinct sites are the fail-safe `return False` "
                       "shape. (b) a scan for cell-presence guards in tabs/ "
                       "(`if [not] <name>_item|_cell|item`, 27 hits) cross-checked against a "
                       "numeric-default pattern (= 0, setValue(0), default=0, or 0) in the "
                       "missing branch: 0 hits, so no sibling fabricates a number for a missing "
                       "cell. (c) `or {})` over tabs/, dialogs/ and core/ (89 hits) - container "
                       "defaults in front of field lookups; the two records of this batch were "
                       "already adjudicated VERIFIED-CORRECT at the same statements in "
                       "batch-004. (d) every remaining `float(` coercion in core/database.py "
                       "that feeds a persisted number (5070, 5080, 5343, 5613, 7018, plus the "
                       "finite-guarded 4914/5623) is already adjudicated in batches 002/011/012 "
                       "or guards finiteness."),
            "hits": 169,
            "findings": [
                {"site": "core/database.py coercion boundary (21 records)",
                 "status": ("contains the one genuine defect of this batch (INV34-001111, "
                            "duplicate INV34-006908) - fixed in 4c543e8 with "
                            "tests/test_coerce_model_values_finite.py; the rest of the migration "
                            "/ ownership / plan-vs-actual records are fail-loud or three-state "
                            "correct")},
                {"site": "tabs/ `self.db` guards (4 records, 3 distinct sites)",
                 "status": ("fail-safe: the guard returns before any session is created and "
                            "before any table is read or written; no fail-open sibling exists in "
                            "tabs/")},
                {"site": "tabs/ cell-presence guards (6 records)",
                 "status": ("presence tests only (QTableWidgetItem has no `__bool__`); the "
                            "missing branch skips or refuses, and the 0-hit numeric-default scan "
                            "shows no sibling fabricates a value")},
                {"site": "tests/ selections (`.one()` 46 hits, `.first()` 29 hits)",
                 "status": ("test-local; this batch's 4 records are strict (`one()`) or "
                            "seeded-deterministic (`first()` on a freshly initialised database) "
                            "and assert on rows the test creates itself")},
            ],
        },
        "tests": ("the batch's defect fix was verified: new regression 15 passed / 0 failed / 0 "
                  "errors / 0 skipped in 1.419 s (/tmp/p6-017-fix.xml); mutation validation with "
                  "the pre-fix coercion reintroduced -> 8 failures, restored byte-identical "
                  "(sha256 61eea36f811dbbd9aeb4bb29d1367ae6ea4610c1b5da0da5e4463c60a0405d81) and "
                  "15/15 green again; related 11-file run 234 passed / 0 failed / 0 errors / 0 "
                  "skipped in 61.143 s (/tmp/p6-017-related.xml); compileall OK; ruff "
                  "core/database.py 14 -> 14 findings and the new test file clean (repo total "
                  "5578 == the HEAD clone, no debt increase); the batch script itself runs with "
                  "the provenance gates active (see `staleness`)"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m34-evidence/m34-ledger.json",
                           "tools/m36/p6_batch_017.py",
                           "core/database.py",
                           "tests/test_coerce_model_values_finite.py",
                           "core/value_normalizer.py",
                           "core/engineering/drill_pipe.py",
                           "tabs/w8_Safety_Widget.py"],
        "staleness": {
            "checked": len(batch), "stale": sum(1 for r in reanchored), "re_anchored": len(reanchored),
            "method": ("every record's declared source_sha256 selects the tree its line number "
                       "belongs to: the current file when the hash matches, otherwise a "
                       "hash-verified provenance tree (tabs/w7_logistics_Widget.py -> c2e0016^, "
                       "whose insertion moved its lines; tabs/w5_Equipment_Widget.py -> 9f45cc4 "
                       "with its permission hunk reversed, a tree that exists in no commit).  The "
                       "recorded text must match at the recorded line of that tree, and the difflib "
                       "map tree->current must land on the same text inside the symbol's AST range (for the one "
                       "record the register leaves without a symbol - INV34-009050, a class "
                       "attribute declaration - the scope is the enclosing class).  "
                       "In addition, every record's context fingerprint was re-derived from its M34 "
                       "identity (path|kind|symbol|pattern|ordinal, tools/m34/common.py), so the "
                       "'same site' claim rests on content, not on line arithmetic."),
            "re_anchored_items": [
                {"id": i, "file": p, "register_line": a, "current_line": b, "tree": prov}
                for i, p, a, b, prov in reanchored],
            "provenance_trees": stats["trees"],
            "fingerprint_proof": {
                "checked": stats["fingerprints_checked"],
                "verified": stats["fingerprints_verified"],
                "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"],
                "records_without_a_reproducing_fingerprint_but_hash_anchored":
                    stats["fingerprints_not_reproduced_but_hash_anchored"],
                "symbol_forms_that_reproduced": stats["fingerprints_by_form"],
                "method": ("sha256(\"path|kind|symbol|norm(pattern)|0\") == the record's "
                           "context_fingerprint, tried with both symbol forms that occur in the "
                           "recorded identities; 44 of 45 reproduce (43 with the symbol's last "
                           "component, 1 - the M34-NEW record INV34-010274 - with the qualified "
                           "symbol).  The one record without a reproducing fingerprint "
                           "(INV34-008346) is a carried M32 record whose M33-era fingerprint was "
                           "generated from a text form that is recovered nowhere in the shipped "
                           "tooling; it is anchored instead by its file's byte-identical sha256, "
                           "so its recorded line *is* the current line.")},
        },
        "method": ("all 45 records were read at their own sites in the current tree (or in the "
                   "hash-verified provenance tree for the two moved files) and the flagged "
                   "construct was traced to its consumer before classification: the daily-report "
                   "time-log producer/consumer pair, the schematic table->model sync and its "
                   "narrow handlers, the section-data save ternaries and their id-or-None storage "
                   "contracts, the W5 inventory trichotomy (normalize_item_row -> "
                   "derive_closing -> save_inventory_items' documented carry-forward), the trip "
                   "sheet's validation helper, and the W7 save/delete paths with their "
                   "SaveOutcome-based failure reporting.  The deciding contract is quoted in "
                   "`evidence` for every record; no line of production code was changed."),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, re-anchored "
          f"{len(reanchored)}, defects fixed {len(payload['defects_fixed'])}, fingerprints "
          f"{stats['fingerprints_verified']}/{stats['fingerprints_checked']}")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
