#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-018 (45 MEDIUM records, class B).

Phase 2, eighth batch: the daily-report persistence readers and the revision writer
(`transition_report`, the report getters, the chart builders, the audit writer), the import
IR/quality/diagnostics boundary (`SourceLocation`, `ReviewItem`, `TimeLogValidator`,
`PersistenceError`, the workbook adapter), the repository layer that was split out of
`DatabaseManager` (the six empty domain subclasses plus `resolve_identity`,
`check_due_tests` and the drill-pipe lookup), one PDF-adapter plan/actual guard, one report-history
serializer and one casing-persistence assertion.

No genuine defect was found in this batch: every flagged construct was read at its own site and
its contract traced to the consumer, and each one either survives the read (an explicit
`is not None` test, a documented default, a typed handler that reports instead of swallowing, or a
class body that is the mandatory syntax of an empty subclass).  The batch's harder records - the
MAX+1 revision numbering and the two fingerprint exceptions - are recorded with the evidence that
made them decidable, and the observations that are *not* defect claims are kept in OBSERVATIONS.
"""
from __future__ import annotations

import ast
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
BATCH = "p6-batch-018"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

# The register's line numbers for core/database.py belong to the tree *before* batch-017's own
# fix: `source_sha256 578d6a9c3eb83c405d7c3fb5d532416c2612137117a7bfa6d8d32b83562e54c2` is exactly
# `4c543e8^` (the fix inserted 11 lines - its docstring and its finite-guard - so every record of
# this file sits 11 lines lower today).  The tree is verified by hash before any comparison.
RECHECK_AGAINST: dict[str, str] = {
    "core/database.py": "4c543e8",
}

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


# ----------------------------------------------------------------- shared contract fragments
_ORM_OR_NONE = (
    "SQLAlchemy-2.0 `Query.first()`/`.one_or_none()` return an ORM instance or None, and the "
    "declarative models of this repository define neither `__bool__` nor `__len__` (grep over "
    "core/database.py and core/repositories/*.py: 0 hits), so an instance is always truthy and "
    "the only falsy value the test can see is None"
)
_PK_FROM_ONE = (
    "SQLite assigns primary keys from 1 (`id = Column(Integer, primary_key=True)`), and every "
    "caller passes either a stored id or the declared default None, so the id test is exactly "
    "`is not None` over the reachable domain - an id of 0 cannot name a stored row"
)
_DATE_NEVER_FALSY = (
    "`report_date`/`last_test_date` are `Date` columns: a stored date object is never falsy and "
    "an absent one is None, so a truthiness test on them is a presence test"
)
_CLASS_BODY_PASS = (
    "`pass` here is the mandatory body of an otherwise empty concrete subclass - Python requires "
    "one statement in a class body and `pass` is that statement.  The class is not a swallowed "
    "operation: it inherits the whole generic CRUD surface from `BaseRepository` "
    "(core/repositories/base.py: `save`, `get_by_id`, `get_list`, `delete`, plus the "
    "`session()` unit-of-work context manager) and adds no members, and it is exported as part "
    "of the repository API in core/repositories/__init__.py (line 12-31 `__all__`)"
)


# ----------------------------------------------------------------- adjudications, register order
R: dict[str, tuple[str, str, str | None]] = {}


R["INV34-000699"] = (
    VC,
    "`transition_report` numbers the report's revisions from its own current maximum *inside the "
    "transaction that inserts the revision*: the whole mutation - actor/permission check, "
    "state-machine validation, `report.status = next_status`, `report.updated_at`, the snapshot "
    "build and `ReportRevision(report_id=report_id, revision_no=(latest.revision_no + 1 if latest "
    "else 1), status=status, snapshot=snapshot, comment=comment)` - runs in one "
    "`with self.session_scope() as session:` block (core/database.py:4599-4706), so the select at "
    "4680 and the insert at 4681 see the same transaction and `latest` cannot be stale with "
    "respect to this writer.  `latest` is the `.first()` of `ReportRevision` filtered by "
    "`report_id` and ordered by `revision_no.desc()` (4680), i.e. the maximum revision of *that "
    "report*, and the reader of the same data orders by the same column "
    "(`get_report_revisions`, 4716-4717), so the sequence the UI shows is the sequence this code "
    "maintains.  `revision_no` is `nullable=False` (core/database.py:691) and the value written is "
    "always >= 1.  Consumers: the only production caller is `tabs/w2_Daily_Report.py:2148` (the "
    "lifecycle action handler); the second writer in this class (4530-4555) carries an in-module "
    "docstring that names `transition_report` the authoritative production mutation path and is "
    "itself the compatibility/test path, and `get_report_revisions` (4716) only reads.  "
    "`LifecycleResult` reports the new status back to that single caller (4681-4705).  "
    "Recorded with the record, not as a defect: there is no `UniqueConstraint(report_id, "
    "revision_no)` at the storage level and no single-instance guard in the repository, so the "
    "MAX+1 numbering is exactly as safe as the one-writer-at-a-time assumption above - nothing in "
    "the repository proves or implements a second concurrent writer, and no code is changed for "
    "that unproven case.",
    "does any supported deployment run two DrillMaster processes against the same SQLite file?  "
    "That is the single assumption the MAX+1 numbering rests on; it is a deployment fact, not a "
    "source fact, and it would be resolved by a storage-level UNIQUE(report_id, revision_no) - a "
    "migration decision outside this batch.",
)

R["INV34-000736"] = (
    VC,
    "The truthiness subject is `backup_dir`, the optional first argument of `auto_backup` "
    "(`def auto_backup(self, backup_dir=None)`, core/database.py:10365): "
    "`target_dir = Path(backup_dir) if backup_dir else configured_backup_dir()` (10367).  The "
    "parameter is either the directory the caller chose or nothing at all - and `\"\"` is not a "
    "directory but would be silently read as `Path('.')`, so routing both falsy inputs to "
    "`configured_backup_dir()` is the documented behaviour ('Create a rotating automatic backup "
    "in the configured data area', 10366).  The write itself is guarded by the id-or-None "
    "contract of the callee: `backup_to(destination)` returns `str(destination)` or None "
    "(10350/10353) and `if not result: return None` (10375-10376) refuses to report a backup "
    "that was not written; a `:memory:` database or a missing file returns None before any path "
    "is touched (10369-10370).  Rotation deletes only `drillmaster_backup_*.db` files above "
    "`DBConstants.MAX_BACKUP_FILES` and logs (does not hide) an unlink failure (10378-10386).  "
    "Sole caller `main_window.py:3024` (`path = self.db_manager.auto_backup()`), which treats "
    "None as 'no backup today'.",
    "the backup name carries a one-second timestamp (`%Y%m%d_%H%M%S`, 10372), so two backups in "
    "the same second would map to the same path - recorded as an observation; the existing "
    "contract is one backup per invocation and no caller drives that frequency.",
)

R["INV34-000770"] = (
    VC,
    "The loop's own contract is quoted in the code above the flag: \"Unrecorded parameters are "
    "gaps, never 0 data points (a 0 WOB point would read as a real slack-off). None keeps the "
    "arrays aligned.\" (core/database.py:9294-9295).  The entry condition "
    "`if p.report_date and p.avg_rop is not None and p.depth_out is not None:` (9296) therefore "
    "admits a report row only when the date and *both* plotted measurements exist: `report_date` "
    "is a `Date` column (never falsy when present), and the two measurements use explicit "
    "`is not None`, so an explicitly recorded 0.0 ROP or 0.0 depth is plotted rather than "
    "dropped.  The derived mid-points are computed only when both bounds exist and otherwise "
    "stay None (9297-9300), and every list is appended to in the same iteration, so the parallel "
    "arrays stay aligned; `data[\"data_points\"]` is the appended count (9306) and an all-gap "
    "result is returned as None (9307), never as an empty-but-zero-filled series.  The site is "
    "reachable only through `generate_rop_chart_data` (no in-repo caller today); its sibling "
    "`generate_time_depth_chart_data` is asserted for exactly this gap semantics by "
    "tests/test_m31_scenarios.py:687-693 ('only the fully known day', `data_points == 1`).",
    None,
)

R["INV34-000772"] = (
    VC,
    "Same construct and same in-code contract as its sibling `generate_rop_chart_data`, quoted "
    "above the flag: \"A missing depth/ROP is not a zero data point: skip the pair so the chart "
    "shows a gap instead of an invented value (arrays stay aligned).\" "
    "(core/database.py:9256-9257).  `if r.report_date and r.depth_2400 is not None and "
    "r.rop_meter is not None:` (9258) admits a day only when the date and both measurements "
    "exist; a persisted 0.0 depth or ROP is `is not None` and is plotted.  The three arrays are "
    "appended in the same branch (9259-9263) so timestamps/depths/rop stay index-aligned and "
    "`data_points` is their length (9264); a result with no complete day is None (9265).  "
    "Consumer contract: tests/test_m31_scenarios.py:687-693 seeds one fully-known day and two "
    "half-known days and asserts `chart[\"data_points\"] == 1` with `depths == [1000.0]` and "
    "`rop == [10.0]` - i.e. the consumer asserts the gap, not a fabricated zero.",
    None,
)

R["INV34-000786"] = (
    VC,
    "The record is a drifted M32 anchor whose fingerprint no longer reproduces (see "
    "`staleness.fingerprint_proof`); its identity is 'truthiness of `entity_type` in the audit "
    "path' and its recorded line/symbol point at `DatabaseManager.log_audit` "
    "(core/database.py:10278 today, `entity_type=entity_type,`).  Both readings of that identity "
    "are adjudicated here: (a) inside `log_audit` the value is *passed through unchanged* into "
    "the audit row - the parameter is declared `entity_type=\"\"` and the row stores it as given, "
    "so there is no truthiness test and nothing is dropped; the only test in that construct is "
    "the documented best-effort truncation `details=details[:500] if details else \"\"` (10281), "
    "where \"\" means 'no detail recorded' and the 500-character cap is the audit table's own "
    "contract.  (b) The only truthiness test on `entity_type` in this file is "
    "`if entity_type:` in `get_audit_logs` (core/database.py:10297), which adds "
    "`AuditLog.entity_type == entity_type` to the query only when a filter value was supplied - "
    "an optional filter, where None/\"\" means 'all entity types'; both its callers pass a real "
    "value (`core/professional_export.py:82` `entity_type=\"daily_report\"`, "
    "tests/test_integration.py:337 `entity_type=\"well\"`), and an audit read that filters by a "
    "falsy label would be filtering by nothing rather than by a meaningful column value.  The "
    "audit write itself is deliberately best-effort (10286-10288: rollback + `logger.error`, no "
    "re-raise) - recorded as an observation, not a defect, because the caller is a report "
    "mutation whose success must not depend on the audit row.",
    "the M32 line for this record has drifted inside the record's own lifetime (its fingerprint "
    "was generated from a text form that no longer exists at, or near, the recorded line), so the "
    "site was adjudicated on both surviving readings; if the M32 register is ever re-derived, "
    "this record's line should be re-anchored to 10297 (`get_audit_logs`).",
)

R["INV34-000790"] = (
    VC,
    "`get_bit_report` (core/database.py:9562-9582) reads the newest `BitReport` of a well and "
    "returns it as a dict or None.  Two truthiness tests compose it: `if report_id:` (9566) adds "
    "`BitReport.report_id == report_id` to the query - " + _PK_FROM_ONE + " - and `if report:` "
    "(9569) switches between the column dict (9570-9579, every column of the model, so no field "
    "is invented) and `return None` (9580).  " + _ORM_OR_NONE + ".  Callers "
    "(e.g. tabs/w4_Downhole_Widget.py:347 style reads) use the returned dict or None, and the "
    "missing report is expressed as None rather than an empty row.",
    None,
)

R["INV34-000798"] = (
    VC,
    "`get_casing_report(well_id=None, section_id=None, report_id=None, report_date=None)` "
    "(core/database.py:5995-6025) builds one query and narrows it with an elif chain - "
    "`if section_id:` / `elif report_id:` / `elif well_id:` (6000-6011) - so the filter is applied "
    "only for a supplied id and the most specific context wins; all three are nullable ids passed "
    "by callers as stored values or omitted (tabs/w3c_section_data.py:315 `report_id=report_id`, "
    ":361/:650 `well_id=self.current_well`), and " + _PK_FROM_ONE + ".  The flag itself sits on "
    "the ordering, and the returned row is guarded by `if report:` (6015): " + _ORM_OR_NONE + ", "
    "with the missing row expressed as `return None` (6020) and the columns read out verbatim "
    "(6016-6019) rather than defaulted.  The handler above it logs and returns None only for an "
    "*unexpected* failure (6021-6023) - a query error is not turned into an empty report by the "
    "guard itself.",
    "the `report_date` parameter of this signature is accepted but never applied (the filter "
    "chain uses section/report/well only), and when several arguments are given the elif order "
    "silently prefers the earlier one; no in-repo caller passes `report_date` (checked), so this "
    "is recorded as a contract note and not patched in this batch.",
)

R["INV34-000802"] = (
    VC,
    "`get_cement_report(well_id=None, section_id=None, report_id=None, report_date=None)` "
    "(core/database.py:5926-5956) is the cement twin of the casing reader adjudicated under "
    "INV34-000798 and is read at its own site: the elif chain `if section_id:` / `elif report_id:` "
    "/ `elif well_id:` (5931-5942) narrows the query only for supplied ids (" + _PK_FROM_ONE + "), "
    "the ordering line is the flagged one (5943-5945), and `if report:` (5946) is the "
    "existence test over " + _ORM_OR_NONE + " - the row is read out verbatim (5947-5950) and a "
    "missing report is None (5951), while the broad handler above only logs an unexpected failure "
    "(5952-5954).  Callers (tabs/w3c_section_data.py:146 `report_id=report_id`, :193 "
    "`well_id=self.current_well`) treat None as 'this section has no report yet', which is the "
    "same state the writer leaves behind when nothing was saved.",
    "same signature note as INV34-000798: `report_date` is accepted and never used, and the elif "
    "order prefers the first supplied argument; no in-repo caller passes `report_date`.",
)

R["INV34-000807"] = (
    VC,
    "`get_daily_report_by_id(report_id)` (core/database.py:4518-4531) is the one-row reader "
    "behind 40 in-repo call sites.  The flagged text is the filter `DailyReport.id == report_id` "
    "(4521-4522) and the test that follows is `if report:` (4524), i.e. the existence test over "
    + _ORM_OR_NONE + ".  The found row is projected column by column (4525-4528) - no field is "
    "invented and no value is coerced - and a missing report returns `None` (4529), which every "
    "caller already handles as 'no report' (core/data_quality.py:33 `... if report_id else None`, "
    "core/managers.py:330 `... if report_id else {}`, tabs/w2_Daily_Report.py:1580).  The id "
    "itself is a primary key and callers pass a stored id or None (" + _PK_FROM_ONE + ").",
    None,
)

R["INV34-000808"] = (
    VC,
    "`get_downhole_equipment(well_id, report_id=None)` (core/database.py:6282-6309) selects the "
    "newest equipment snapshot of a well and, when `report_id` was supplied, of one report "
    "(`if report_id:` at 6288, " + _PK_FROM_ONE + ").  The flagged name is `equip`, the result of "
    "`query.order_by(DownholeEquipment.updated_at.desc()).first()` (6292-6294): " + _ORM_OR_NONE +
    ".  The payload is built from the row's own columns plus `equipment_data_json` (6295-6303) "
    "and a missing snapshot is None (6304); the broad handler re-raises (6307) rather than "
    "returning an empty snapshot, which is the fail-loud shape the export path needs.  Caller "
    "tabs/w4_Downhole_Widget.py:347 reads the dict or None.",
    None,
)

R["INV34-000810"] = (
    VC,
    "`get_drilling_parameters(well_id=None, report_id=None, report_date=None)` "
    "(core/database.py:5757-5792) narrows one query with `if report_id:` / `elif well_id:` and "
    "then `if report_date:` *inside the well branch* (5766-5777) - all three optional filters, "
    "present only when supplied (" + _PK_FROM_ONE + " for the two ids; " + _DATE_NEVER_FALSY +
    " for the date).  The flagged name is `params`, the result of "
    "`query.order_by(DrillingParameters.report_date.desc()).first()` (5778-5780): " + _ORM_OR_NONE +
    ".  The row is projected verbatim (5782-5786) and a missing row returns None (5787).  "
    "Consumers depend on that distinction: core/ddr_pdf_export.py:35, core/report_engine.py:112, "
    "tabs/w3_drilling_report.py:818 and core/professional_export.py:213 either guard the result "
    "or fall back explicitly, and core/rag_search.py:117 spells the contract out as "
    "`... or {}` at its own boundary.",
    None,
)

R["INV34-000825"] = (
    VC,
    "`get_formation_report(well_id, report_id=None)` (core/database.py:6358-6379) filters by the "
    "required well and, when a report was given, by `report_id` - here with the explicit form "
    "`if report_id is not None:` (6362), which is the same predicate as the truthiness variant "
    "used by its siblings, since " + _PK_FROM_ONE + ".  The flagged text is the filter line and "
    "the test that follows is `if report:` (6365): " + _ORM_OR_NONE + ".  The payload is built "
    "from the row, with the child collection read as `report.formations_json or []` (6370) - the "
    "stored collection or an empty list for a report that stored none, which is the "
    "collection-level contract of the model - and a missing report is None (6374); the broad "
    "handler re-raises (6377) instead of reporting an empty formation set.  Caller "
    "tabs/w4_Downhole_Widget.py:349.",
    None,
)

R["INV34-000839"] = (
    VC,
    "`get_mud_report(well_id=None, report_id=None, report_date=None)` (core/database.py:5832-5886) "
    "applies the filters only when they were supplied: `if report_id:` (5836) then `elif well_id:` "
    "(5838) and, nested in the well branch, `if report_date:` (5840) - " + _PK_FROM_ONE + " for "
    "the ids and " + _DATE_NEVER_FALSY + " for the date, whose recorded text is the filter line "
    "itself (`query = query.filter(MudReport.report_date == report_date)`).  The flagged name is "
    "`report`, the result of `query.order_by(MudReport.report_date.desc()).first()` (5842): "
    + _ORM_OR_NONE + ".  All 30+ returned keys are read from the row (5844-5880) - a NULL column "
    "comes back as None, never as 0 - and a missing report is None (5881).  Consumers distinguish "
    "the two: core/ddr_pdf_export.py:36, core/report_engine.py:115, tabs/w3_drilling_report.py:1499 "
    "and core/professional_export.py:202 guard the result or fall back explicitly, and "
    "tests/test_ddr_followup_lifecycle.py:197-203 asserts a saved report is read back complete.",
    None,
)

R["INV34-000857"] = (
    VC,
    "`get_procedure_templates(procedure_type: str = None)` (core/database.py:9850-9872) filters "
    "by procedure type only when one was supplied: `if procedure_type:` (9853).  The caller "
    "contract is in-repo and explicit: `tabs/w14_Procedure_Widget.py:1520-1524` fills the filter "
    "combo with `addItem(\"All Types\")` *without* a user-data value and then "
    "`addItem(label, key)` for each real type, and `:1565-1566` passes "
    "`self.type_filter.currentData()` straight to this method - i.e. None (the 'All Types' item) "
    "means 'no filter', and every real value is a non-empty `PROCEDURE_TYPES` key, so the "
    "truthiness test is exactly the intended 'filter supplied' test.  The collection itself is "
    "returned as a list of dicts (9856-9870); the handler above it does not hide a query failure "
    "(9869-9871: `logger.error` then bare `raise`, commented 'collection query failure is not an "
    "empty dataset'), so an unreadable template table cannot be shown as an empty list.",
    None,
)

R["INV34-000912"] = (
    VC,
    "`get_wellbore_schematic(well_id=None, report_id=None, report_date=None)` "
    "(core/database.py:6063-6090) narrows the query with `if report_id:` / `elif well_id:` and "
    "`if report_date:` inside the well branch (6067-6072) - supplied ids and an optional date "
    "only (" + _PK_FROM_ONE + "; " + _DATE_NEVER_FALSY + ").  The flagged name is `schematic`, "
    "the result of `query.order_by(WellboreSchematic.report_date.desc()).first()` (6073): "
    + _ORM_OR_NONE + ".  The payload reads the row's own columns, including the stored "
    "`layers_json`/`elements_json` collections (6075-6084), and a missing schematic is None "
    "(6085) - the state the schematic engine already handles when a well has no saved layout.",
    None,
)

R["INV34-001106"] = (
    VC,
    "`_sync_safety_children` (core/database.py:7766-7812) rebuilds one explicitly edited safety "
    "collection.  Every row passes through the typed `try` at 7790-7799, whose only raising "
    "statement is the domain refusal itself: `if model is WasteRecord and row.get(\"record_date\") "
    "is None: raise ValueError(\"Waste record date is required; no report/today date invented\")` "
    "- so the `except ValueError as exc:` handler (7797-7799) exists to convert *that* refusal "
    "(and a failed `optional_date` parse) into an INVALID_SOURCE review item carrying the row's "
    "own source location and the reason string, not to swallow an arbitrary failure.  Its effect "
    "is fail-closed for the edited collection and non-destructive for the stored one: "
    "`if issues:` then `reviews.extend(issues)` and `continue` (7806-7811) - the `query.delete(...)`"
    " / re-insert block below is skipped, with the in-code comment 'Keep the stored collection "
    "intact. Other independent safety collections may still save. Preserve attempted edits in "
    "audit.', and because the loop continues, the *other* mapping (BOP vs waste) is still "
    "processed.  The reviews are returned to the caller and also written to the audit trail "
    "(7810-7811), so the refusal is visible.  The handler is typed (ValueError), matching the "
    "only exception the guarded block raises; no broader `except Exception` shadows it.",
    None,
)

R["INV34-009313"] = (
    VC,
    "The flagged call is the audit-trail write at the end of `_sync_safety_children` "
    "(core/database.py:7810-7811): "
    "`session.add(AuditLog(action=\"safety_review\", entity_type=\"safety_report\", "
    "entity_id=safety_id, details=json.dumps(reviews, default=str)))`.  It serializes the *review "
    "list* - the return value described above, whose entries are the `review_item(...).to_dict()` "
    "payloads and may carry non-JSON-native values such as dates - into the audit row's free-text "
    "`details` column; `default=str` is what makes that human-readable record possible without "
    "changing any value.  The authoritative data is not this string: the edited collections are "
    "persisted through the ORM rows above and the same review list is returned to the caller "
    "(7812 `return reviews`) and shown by the safety UI, and the snapshot/export serializers use "
    "their own explicit converter (core/report_snapshot.py:31-46 `serialize_value`, whose "
    "docstring states 'NULL / unknown stays None - never coerced to 0, \"\", today or now').  A "
    "`default=str` here can therefore only affect the audit text, never a measurement.",
    None,
)

R["INV34-001987"] = (
    VC,
    "The `except Exception: continue` sits around the *optional* formal-table rebuild inside "
    "`raw_document_from_workbook` (core/import_ir.py:486-504): "
    "`from openpyxl.utils.cell import range_boundaries` + `range_boundaries(defined_table.ref)` "
    "for a table the workbook declares.  The loop's only effect is "
    "`raw.tables.append(RawTable(headers=..., rows=..., ...))`; the cells are *not* built here - "
    "`raw.cells.extend(sheet_cells[...])` happens earlier (470), from the worksheet walk, and the "
    "worksheet itself is already appended as a `classification=\"worksheet\"` RawTable (474-480) "
    "with the documented note 'A worksheet is a source region even when it has no formal Excel "
    "table... no first-row guessing is performed'.  So a malformed declared-table reference can "
    "cost the IR's *formal grouping* of a table (headers/row membership), never a cell, and the "
    "only consumers of `RawDocument.tables` are the IR dump (`to_dict`, import_ir.py:222-229), "
    "the round-trip reader (`from_dict`, 244) and the DDR acceptance test's cell review states "
    "(tests/test_ddr_acceptance.py:272) - the workbook import path itself consumes "
    "`raw_document.cells` (core/excel_intelligence.py:1261, 1285, 1301, 1341), which is complete "
    "either way.",
    "the skip writes no diagnostic into `raw.metadata`, so an IR-only consumer cannot tell a "
    "workbook that declares no formal tables from one whose declared table failed to parse; "
    "recorded as an observation (no cell or measurement is affected), not patched.",
)

R["INV34-001992"] = (
    VC,
    "`section_title = table_name or None` (core/import_ir.py:316) is a no-op fallback: its input "
    "cannot be empty.  Three lines above it, `table_name = str(getattr(table, \"name\", \"\") or "
    "f\"table_{table_index}\")` (313) guarantees a non-empty string - an absent or empty table "
    "name has already been replaced by the positional `table_{index}` placeholder - so the "
    "`or None` never fires and never turns a present name into None.  The value is carried into "
    "the emitted IR only as provenance (`RawCell.section_title` / `RawTable.section_title`, "
    "import_ir.py:145 and the cell constructor at 322-330), where None would mean 'this table "
    "declares no section title' - a state the code never claims here.  Consumers read it as a "
    "label: `resolve_canonical_field(label, context, section=...)` scopes alias lookup by section "
    "(core/canonical_mapper.py:107-143) and the mapper records it as provenance "
    "(core/canonical_mapper.py:192 `section_title=str(source.get(\"section_title\") or \"\")`).",
    None,
)

R["INV34-007588"] = dup(
    "INV34-001992",
    "the same `section_title = table_name or None` statement in `raw_document_from_mineru` "
    "(core/import_ir.py:316)",
    "the no-op fallback whose input is already guaranteed non-empty by the placeholder on line 313",
)

R["INV34-002027"] = (
    VC,
    "`if not self.detected_table:` in `ReviewItem.__post_init__` (core/import_quality.py:168-169) "
    "fills a *missing label* from the item's own entity: `self.detected_table = self.entity`.  "
    "`detected_table` is a review-matrix classification label (the declared field is "
    "`detected_table: str = \"\"`), never a measured value; the block only runs when the label is "
    "empty, and it copies the entity the producer already stated rather than inventing a table "
    "name.  The class documents this boundary in the comment above the block ('Normalize "
    "provenance at the contract boundary... no ReviewItem leaves this boundary without a "
    "structured source location', 96-99), and when both fields are empty the label stays empty "
    "instead of becoming a guessed table.",
    None,
)

R["INV34-002032"] = (
    VC,
    "`if self.row:` in `ReviewItem.__post_init__` (core/import_quality.py:135-136) guards "
    "`location.setdefault(\"row\", self.row)`, and the class declares its own 'not recorded' "
    "value for that field: `row: int = 0` (core/import_quality.py:74), with the comment "
    "'Backward-compatible row/column fields used by legacy Excel records'.  Every producer that "
    "sets a row uses a 1-based source coordinate - openpyxl `cell.row` "
    "(core/import_ir.py:420), `enumerate(..., 1)` for MinerU rows (import_ir.py:340), "
    "`range_boundaries`' `min_row` (import_ir.py:510) - and the legacy constructor helper uses "
    "the same convention when it builds a cell token "
    "(`if not kwargs.get(\"source_cell\") and kwargs.get(\"row\"):`, import_quality.py:268).  So "
    "the truthiness test distinguishes 'row recorded' from the declared 0/'not recorded', and it "
    "only affects whether the row is copied into the location mapping: the item's own `row` "
    "attribute is untouched either way.",
    "the sibling `column` test three lines below uses the explicit form "
    "`if self.column not in (None, \"\"):`; both are equivalent over the reachable 1-based "
    "domain, and the asymmetry is recorded as a readability note, not patched.",
)

R["INV34-002034"] = (
    VC,
    "`if self.source_cell:` in `ReviewItem.__post_init__` (core/import_quality.py:139-140) guards "
    "`location.setdefault(\"cell\", self.source_cell)`.  The field is declared "
    "`source_cell: str = \"\"  # Excel cell or PDF coordinate token` (core/import_quality.py:50), "
    "so the empty string is the class's own 'no cell recorded' value, and the test decides only "
    "whether a cell token is copied into the source-location mapping - it never invents one (the "
    "derivation from the mapping happens in the *following* block, which runs only when this "
    "field is still empty, 142-158).  A present token is copied verbatim.",
    None,
)

R["INV34-002044"] = (
    VC,
    "`except (TypeError, ValueError, OverflowError):` in `TimeLogValidator.validate_logs` "
    "(core/import_quality.py:495-512) is a typed handler around exactly one operation - "
    "`dur_f = float(dur)` and the arithmetic that follows - and it does not swallow the failure: "
    "it appends `report.error(sheet, idx + 2, \"Duration must be numeric\", \"duration\", dur)` "
    "(511) and sets `duration_value = None` (512).  `ImportReport.error` (import_quality.py:349-354) "
    "records an issue at level 'error', counts the row as failed and makes the report "
    "non-successful (`success` is `self.failed == 0 and not self.errors`, 345-347), so an "
    "unparsable duration is a reported import error, never a silent pass.  The handler is also "
    "deliberately paired with the finiteness refusal above it (`if not math.isfinite(dur_f): "
    "raise ValueError`, 495-496), so the same path converts a non-finite token into 'unknown + "
    "error' instead of a measurement; `duration_value = None` keeps the rejected token out of "
    "the parsed record while the raw token is retained on the issue for the review UI.",
    None,
)

R["INV34-002706"] = (
    VC,
    "`return self._to_spec(row) if row else None` in `DrillPipeReferenceRepository.get_by_identity` "
    "(core/repositories/drill_pipe_reference_repository.py:90).  `row` is the result of "
    "`.filter(DrillPipeSpecRecord.identity_fingerprint == fingerprint).one_or_none()` (87-89): "
    + _ORM_OR_NONE + ".  The branch therefore means 'the stored spec exists' vs 'no such spec', "
    "and the None branch is the documented absence the module's own contract requires - the file "
    "header states the controlled-persistence rules (no silent overwrite, no fabrication) it "
    "enforces through this lookup.  `_to_spec` (220-221) reconstructs the spec from the stored "
    "`payload_json` and is only called with a real row, so a missing row can never be "
    "reconstructed as an empty spec.",
    None,
)

R["INV34-002742"] = (
    INT,
    "`def check_due_tests(self, well_id: int, interval_days: int = 14)` "
    "(core/repositories/safety_repository.py:16-17) documents its own default in the line below "
    "the signature: '\"\"\"Configurable test interval, not hard-coded.\"\"\"'.  The 14 is a "
    "*parameter* default, not a stored value: the caller can override it, and the repository's "
    "canonical policy source agrees with it - `core/standards.py:27` "
    "`def bop_test_interval_days(default=14)` reads the configured "
    "`bop_test_interval_days` (`max(1, int(cfg[...]))`, 39-40) and is what the UI uses "
    "(tabs/w8_Safety_Widget.py:288, 343), while `core/validators.py:487` declares the same "
    "14-day default for its own configurable interval.  The value is therefore a documented "
    "business default consistent with the standard, and the method has no in-repo caller, so no "
    "due-date calculation in this repository can be wrong because of it.",
    "if this method ever gains a caller, the interval should come from "
    "`core.standards.bop_test_interval_days()` rather than from the signature default, so a "
    "user-configured interval cannot be silently ignored; recorded, not patched (no caller "
    "exists, and changing the signature of an exported repository method is a behavioural "
    "decision for its future consumer).",
)

R["INV34-002743"] = (
    VC,
    "`if not c.last_test_date:` in `BOPRepository.check_due_tests` "
    "(core/repositories/safety_repository.py:24-26) sends a component with no recorded test to "
    "the due list with the reason 'No test history' and `continue`s - i.e. an unknown test date "
    "is treated as *overdue-unknown*, never as 'tested today'.  The subject is the model's "
    "`last_test_date` and " + _DATE_NEVER_FALSY + ".  Components with a date proceed on the "
    "interval arithmetic (`next_due = c.last_test_date + timedelta(days=interval_days)`, 27) and "
    "are reported only when due (28-37), so a recorded date is never dropped by this guard and a "
    "missing one is never turned into a fabricated date.",
    None,
)

R["INV34-007578"] = (
    VC,
    "`self.result = result or {}` in `PersistenceError.__init__` "
    "(core/import_diagnostics.py:102-108) normalizes an *explicitly optional* constructor "
    "argument: `def __init__(self, issue: PersistenceIssue, *, result: Optional[dict] = None)` "
    "(105).  `{}` is this exception's 'no partial result was captured' value, not a measurement: "
    "both raise sites in the application pass a real result when there is one "
    "(core/database.py:3107 `result={\"diagnostics\": [issue.to_dict()]}`, 5701 "
    "`result=results` - the partially filled import result), and the only consumer that reads "
    "the attribute is the import-architecture test "
    "(tests/test_import_architecture.py:151 `assert raised.value.result[\"diagnostics\"]`), which "
    "runs against the raise site that supplies it.  A missing key on an empty default raises "
    "KeyError - fail-loud - rather than being answered with an invented empty diagnostics list, "
    "and the sibling exception in the same file shows the pattern is deliberate: "
    "`SchemaMigrationError` defaults to `{\"diagnostics\": [issue.to_dict()]}` (line 133) because "
    "*its* contract promises diagnostics.",
    None,
)

R["INV34-007579"] = (
    VC,
    "`payload = payload or {}` opens `SourceLocation.from_dict(cls, payload: Optional[dict])` "
    "(core/import_ir.py:42-56), an explicitly optional deserializer: every field is then read "
    "with `payload.get(...)` and the dataclass supplies the rest of the defaults "
    "(`file: str = \"\"`, `sheet/page/row/column/cell/table`: None).  `None` and `{}` therefore "
    "produce the same documented object - a location with no recorded position, which is exactly "
    "what a legacy record without provenance means - and no field can be fabricated from the "
    "empty mapping.  The inverse direction is the same contract: `to_dict` (35-45) writes the "
    "same fields back, so a round-trip of an empty location stays empty.",
    None,
)

R["INV34-007597"] = (
    VC,
    "`if not self.source_cell and isinstance(self.source_location, Mapping):` "
    "(core/import_quality.py:142-158) is the derivation block that gives a ReviewItem a "
    "human-readable source token when the producer supplied only a structured location: it reads "
    "the recorded provenance itself (`cell` / `address`, then the `cells` mapping, then the "
    "remaining locator keys) and joins the values that are present.  It runs only when the item "
    "has no token yet, it copies recorded values rather than computing any, and the values it "
    "rejects are exactly the empty ones (`value not in (None, \"\")`), so nothing is invented and "
    "nothing recorded is dropped.  The guard is what keeps a producer-supplied token untouched - "
    "the boundary comment at 96-99 promises only that no ReviewItem leaves without a structured "
    "source location.",
    None,
)

R["INV34-007600"] = (
    VC,
    "`if not self.canonical_field and self.target_field:` (core/import_quality.py:184-185) is one "
    "half of the alias synchronization of the review contract - the four lines 182-187 fill "
    "`field`/`target_field` and `canonical_field`/`target_field` from whichever of the pair the "
    "producer supplied, in both directions.  Both names denote the same canonical field identity, "
    "the block only writes a missing member from a present one, and the declared defaults are "
    "`str = \"\"`; an item that supplies neither keeps both empty instead of being assigned a "
    "guessed field name.  The review matrix and the persistence boundary therefore see one field "
    "identity, not two disagreeing ones.",
    None,
)

R["INV34-007602"] = (
    VC,
    "`payload = dict(payload or {})` opens `ReviewItem.from_dict(cls, payload: Optional[dict])` "
    "(core/import_quality.py:220-238), the deserializer whose docstring states its contract: "
    "'Deserialize old and new review rows without dropping provenance.'  The argument is "
    "explicitly optional; the copy is then only used to translate legacy keys into current ones "
    "(`aliases`, 224-233) and every remaining key is filtered against the dataclass fields before "
    "construction (`allowed`, 235-238), so an unknown or empty payload produces the documented "
    "default item and can never inject a field the class does not declare.  `None` and `{}` "
    "denote the same 'nothing recorded' state.",
    None,
)

R["INV34-007614"] = (
    VC,
    "`if not math.isfinite(dur_f):` (core/import_quality.py:495-496) deliberately raises "
    "`ValueError` for a non-finite duration so the surrounding typed handler converts it into a "
    "reported error and `duration_value = None` (511-512).  That is the required semantic for a "
    "measurement boundary: 'nan'/'inf'/'-inf'/overflow parse successfully with `float()` but are "
    "not durations, so they must become unknown-and-reported rather than a plotted value - the "
    "same contract the engineering layer states as `number if math.isfinite(number) else None` "
    "(core/engineering/drill_pipe.py) and that batch-017 fixed at the persistence boundary "
    "(INV34-001111, commit 4c543e8).  `math.isfinite` also rejects a `None`/non-numeric token "
    "with `TypeError`, which the same handler catches, so the refusal path is complete.",
    None,
)

R["INV34-007784"] = (
    INT,
    "`class CostRepository(BaseRepository): pass` (core/repositories/cost_repository.py:6-7).  "
    + _CLASS_BODY_PASS + ".  The file's docstring names the class's purpose ('Cost "
    "repository.'), its only in-repo references are its own definition and the export in "
    "core/repositories/__init__.py (line 9 import, line 29 in `__all__`), and no code "
    "instantiates it today - recorded as an observation about the repository split, not a defect: "
    "an exported, empty domain subclass with the full generic CRUD is exactly what the split "
    "module describes, and the alternative ('there was supposed to be code here') is not "
    "supported by anything in the repository - the cost logic the class would wrap lives in "
    "`core/cost_semantics.py` and is reached through `DatabaseManager.get_cost_totals` "
    "(core/database.py:10255-10258 in the recorded tree).",
    None,
)

R["INV34-007788"] = (
    INT,
    "`class EquipmentRepository(BaseRepository): pass` (core/repositories/logistics_repository.py:29-30), "
    "the second of the four placeholders in this module.  " + _CLASS_BODY_PASS + ".  Read at its "
    "own site: the module imports only the base class and the engineering ledger types used by "
    "`BulkRepository.validate_ledger` above it (lines 3-8), `EquipmentRepository` appears nowhere "
    "else in the repository except its export (core/repositories/__init__.py line 6 import, line "
    "23 in `__all__`), and equipment persistence is served by the database layer "
    "(`get_downhole_equipment` reads the stored equipment snapshot) rather than by this class.",
    None,
)

R["INV34-007789"] = (
    INT,
    "`class LogisticsRepository(BaseRepository): pass` (core/repositories/logistics_repository.py:33-34).  "
    + _CLASS_BODY_PASS + ".  Its family members in the same file are read for contrast: "
    "`BulkRepository` (11-26) adds `validate_ledger` because the mud/chemical ledger has an "
    "engine-backed validation contract, while the equipment/logistics/fuel classes (29-38) add "
    "nothing.  The class is exported once (core/repositories/__init__.py line 6, `__all__` line "
    "24) and instantiated nowhere in-repo; logistics persistence is reached through the "
    "`DatabaseManager` personnel/fuel/transport methods used by tabs/w7_logistics_Widget.py.",
    None,
)

R["INV34-007790"] = (
    INT,
    "`class FuelRepository(BaseRepository): pass` (core/repositories/logistics_repository.py:37-38), "
    "the last of this module's three placeholders.  " + _CLASS_BODY_PASS + ".  Its site evidence "
    "is the same file-level contract: the module's real work is `BulkRepository.validate_ledger` "
    "(11-26) with the engineering ledger dataclass, and the file's `logger` (line 8) is used only "
    "there.  `FuelRepository` is referenced by its definition and its export "
    "(core/repositories/__init__.py line 6, `__all__` line 25) and by nothing else; fuel/water "
    "persistence is implemented by the database layer "
    "(`save_fuel_water_inventory`, used by tabs/w7_logistics_Widget.py:997+).",
    None,
)

R["INV34-007810"] = (
    INT,
    "`class SafetyRepository(BaseRepository): pass` (core/repositories/safety_repository.py:11-12), "
    "in the module that also defines the one non-empty safety subclass, `BOPRepository` "
    "(15-38).  " + _CLASS_BODY_PASS + ".  The file's imports show which members need code - "
    "`BOPComponent` for the due-test query - and the empty class needs none.  It is referenced by "
    "its definition and its export (core/repositories/__init__.py line 7, `__all__` line 26) and "
    "instantiated nowhere in-repo; the safety read/write paths the UI uses are "
    "`DatabaseManager.get_safety_report` / `_sync_safety_children` (adjudicated in this batch "
    "under INV34-001106 and INV34-009313).",
    None,
)

R["INV34-007811"] = (
    INT,
    "`class ServiceRepository(BaseRepository): pass` (core/repositories/service_repository.py:6-7).  "
    + _CLASS_BODY_PASS + ".  The whole file is the module docstring ('Service Company "
    "repositories.'), the base-class import, and this class; it is referenced by its definition "
    "and its export (core/repositories/__init__.py line 8, `__all__` line 27) and instantiated "
    "nowhere in-repo, while service-company persistence is implemented by the database layer "
    "(`save_service_company_pob` etc., used by the W7 service dialogs).",
    None,
)

R["INV34-007830"] = (
    VC,
    "`v = (well_info or {}).get(k)` in `WellRepository.resolve_identity` "
    "(core/repositories/well_repository.py:33-35, the first of the record's two occurrences - the "
    "name loop).  The parameter is the *imported* well description, declared `well_info: Dict`; "
    "guarding it with `or {}` means an absent/empty description yields no candidate keys, so "
    "`name` stays empty, and with no code either, the method refuses: "
    "`if not name and not code: return None` (43-44) - the identity is *not* fabricated from the "
    "empty mapping.  That refusal is the in-repo contract: the acceptance test "
    "tests/test_real_user_acceptance_regressions.py:270-281 drives exactly this method and "
    "asserts that an unscoped well raises `ValueError` ('project') and an ambiguous name raises "
    "'Ambiguous', i.e. the caller must decide identity explicitly.  `name_keys`/`code_keys` are "
    "the documented universal-import aliases listed in the method docstring.",
    None,
)

R["INV34-007831"] = (
    VC,
    "`v = (well_info or {}).get(k)` in the code loop of the same method "
    "(core/repositories/well_repository.py:40-42) - the second occurrence, adjudicated at its own "
    "site rather than by similarity: an empty `well_info` again contributes no code candidate, "
    "and the method's two refusal points remain intact - the `if not name and not code: return "
    "None` above (43-44) and, for a name/code that resolves ambiguously or without a unique "
    "project, `raise ValueError(\"Ambiguous well identity...\")` in `get_by_name_or_code` (20-21) "
    "and `raise ValueError(\"Select a project explicitly; no unique project context exists\")` in "
    "the create branch (56-59).  The `or {}` therefore cannot turn a missing source into a stored "
    "well identity.",
    None,
)

R["INV34-009696"] = (
    VC,
    "`if summary_index is not None or forecast_index is not None:` (core/import_adapters/pdf_tables.py:106-111) "
    "decides whether the page carries the two merged full-width text rows at all.  Both indices "
    "come from `next((...), None)` searches for the 'Summary of Activities' / 'Operation Forecast' "
    "markers (104-105), so the guard is true iff at least one marker was found - when neither "
    "exists, *no* `daily_report_text` table is emitted, i.e. the adapter refuses to fabricate an "
    "empty text row for a page that has none.  When one marker exists, both fields are emitted and "
    "the absent one is `\"\"` (`... if summary_index is not None and summary_index + 1 < len(matrix) "
    "else \"\"`, 107-108) because its cell genuinely does not exist - the source text of the "
    "present field is preserved verbatim ('Preserve the exact source text as two fields', 103-105), "
    "and the empty value is a text field, never a measurement (`DailyReport.summary`/`forecast` "
    "are `Column(Text)`, core/database.py:351-352).  The same 'emit only what exists' shape is "
    "used by the neighbouring blocks (the report header needs 8 rows and 12 columns, the casing "
    "block is appended only when records were collected), and the section is asserted by "
    "tests/test_pdf_structured_fallback.py:43.",
    None,
)

R["INV34-010015"] = (
    VC,
    "`raw.setPlainText(json.dumps(snap, indent=2, default=str, ensure_ascii=False))` "
    "(dialogs/report_history_dialog.py:133) fills the dialog's *secondary debug* view: the widget "
    "is created read-only, hidden and behind an unchecked 'Raw snapshot (debug)' group box "
    "(114-124, `raw.setVisible(False)` / `raw_box.setChecked(False)`), while the primary "
    "representation of the same revision is the structured tree built by "
    "`self._populate_revision_tree(detail, snap)` (128) with the comment 'Structured, "
    "human-readable view of the selected revision's frozen operational content - NOT a raw JSON "
    "dump as the primary UI'.  `default=str` only affects how a non-JSON-native value is *rendered "
    "in that text box*; the authoritative snapshot is written by a different path with its own "
    "explicit converter (`core/report_snapshot.build_report_snapshot` -> `serialize_value`, "
    "core/report_snapshot.py:31-46, whose docstring states 'NULL / unknown stays None - never "
    "coerced to 0, \"\", today or now'), and it is that stored JSON the dialog displays "
    "(`revisions[row].get(\"snapshot\")`, 127).  The try/except around it degrades to `str(snap)` "
    "for display only.",
    None,
)

R["INV34-010367"] = (
    VC,
    "`first = json.dumps(recalculate_from_snapshot(snap).values, sort_keys=True, default=str)` "
    "(tests/test_casing_persistence.py:135-136) is a *test-internal* comparison inside "
    "`test_engine_deterministic_and_no_input_mutation` (131-142).  The test compares two "
    "recomputations of the same snapshot taken before and after five unrelated engine calls "
    "(`first` vs `second`, 138-141) and asserts unchanged inputs (`assert INPUTS == before`, "
    "142); `sort_keys=True` makes the comparison order-independent and `default=str` only makes "
    "a non-JSON-native value (e.g. a `Decimal`) representable so the equality check is possible.  "
    "It cannot mask non-determinism: a value that changed between the two calls would produce a "
    "different string and fail the assertion, and a value with an unstable `str()` (an object "
    "address) would also differ.  No production data is serialized here - the persistence path "
    "for these runs is `CasingCalculationRepository` with its own converter "
    "(core/repositories/casing_repository.py).",
    None,
)

R["INV34-006940"] = dup(
    "INV34-000699",
    "the same `latest = session.query(ReportRevision)...first()` statement in "
    "`DatabaseManager.transition_report` (core/database.py:4669 in the recorded tree; 4680 today)",
    "the MAX+1 revision numbering, its single-transaction context and its single production caller",
)

# ----------------------------------------------------------------- observations (not defects)
NEW_FINDINGS: list[dict] = []

OBSERVATIONS: list[dict] = [
    {"record": "INV34-000699 / INV34-006940", "site": "core/database.py:4680-4681",
     "observation": ("the revision sequence is maintained in application code (MAX(revision_no)+1 "
                     "inside the report's transaction) while the schema has `revision_no "
                     "nullable=False` and no `UniqueConstraint(report_id, revision_no)`.  With the "
                     "single production caller this is correct; a storage-level UNIQUE would make "
                     "the invariant enforced rather than assumed, which is a migration decision "
                     "outside this batch.  Recorded, not patched.")},
    {"record": "INV34-000736", "site": "core/database.py:10372-10373",
     "observation": ("the automatic-backup filename is stamped to the second "
                     "(`%Y%m%d_%H%M%S`), so two backups inside one second resolve to the same path "
                     "and the second write replaces the first.  No caller drives that frequency "
                     "(the only caller is the startup path in main_window.py:3024) and the "
                     "documented contract is one backup per invocation; recorded, not patched.")},
    {"record": "INV34-000786", "site": "core/database.py:10267 (M32 anchor)",
     "observation": ("this carried M32 record's line has drifted inside its own lifetime: the "
                     "recorded line now holds the audit-row keyword `entity_type=entity_type,` "
                     "and the truthiness test its rule family targets (`if entity_type:`) lives in "
                     "the neighbouring `get_audit_logs` (line 10297 today).  Both readings were "
                     "adjudicated; the drifted line is an identity-quality note for a future "
                     "register re-derivation, not a code defect.")},
    {"record": "INV34-000786 / audit boundary", "site": "core/database.py:10286-10288",
     "observation": ("`log_audit` is best-effort by design (rollback + `logger.error`, no re-raise) "
                     "so an audit write can never fail a report mutation, and its optional text "
                     "fields store \"\" rather than NULL for 'not provided' while `details` is "
                     "capped at 500 characters.  A persistently failing audit write is therefore "
                     "visible only in the log; recorded as a diagnosability note, not patched.")},
    {"record": "INV34-001106 (ledger pattern)", "site": "tools/m34/sweep34.py:79",
     "observation": ("the M34 sweep stores its expression as `norm(raw)[:200]`, so the ledger's "
                     "`pattern` for a multi-line statement is a 200-character *prefix*.  For "
                     "INV34-001106 this is why the fingerprint does not reproduce from the stored "
                     "pattern but does reproduce from the statement's AST segment - a tooling "
                     "truncation, not a missing identity.")},
    {"record": "INV34-001987", "site": "core/import_ir.py:486-504",
     "observation": ("a workbook table whose declared ref cannot be parsed is skipped with no "
                     "entry in `raw.metadata`, so an IR-only consumer cannot distinguish 'declares "
                     "no formal tables' from 'declared table unparsable'.  No cell or measurement "
                     "is affected (the worksheet table and `raw.cells` are built independently); "
                     "recorded, not patched.")},
    {"record": "repository placeholders (INV34-007784 / 007788 / 007789 / 007790 / 007810 / 007811)",
     "site": "core/repositories/*.py",
     "observation": ("the six empty domain subclasses are exported in "
                     "core/repositories/__init__.py `__all__` but instantiated nowhere in the "
                     "repository, while the application reaches persistence through "
                     "`DatabaseManager`.  The classes are correct as they stand (full inherited CRUD, "
                     "mandatory empty body); how much of the repository split is actually wired is "
                     "an architecture question for the post-P6 reconciliation, recorded here.")},
    {"record": "INV34-002032", "site": "core/import_quality.py:135-141",
     "observation": ("within the same block `row` is tested by truthiness (135, against the "
                     "declared legacy default `row: int = 0`) while `column` uses the explicit "
                     "`not in (None, \"\")` form (137-138).  Both are equivalent over the reachable "
                     "1-based source coordinates; the asymmetry is a readability note.")},
]


# ----------------------------------------------------------------- helpers (017 architecture)
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

    Kept from batch-016/017 (batch-018 needs no reconstruction, but the mechanism is the same
    provenance gate and stays available for a hash that no commit carries).
    """
    base, commit, hunk_ids = entry
    diff = subprocess.run(["git", "diff", base, commit, "--", path], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    parts = re.split(r"(?m)^(@@[^\n]*@@[^\n]*\n)", diff)
    header, hunks = parts[0], [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]
    patch = header + "".join(hunks[i][0] + hunks[i][1] for i in hunk_ids)
    work = Path(tempfile.mkdtemp(prefix="m36-p6-018-"))
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
    """The tree the register's line numbers for `path` belong to, *proven* by its sha256."""
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


RECONSTRUCT: dict[str, tuple[str, str, tuple[int, ...]]] = {}


_AST_CACHE: dict[str, object] = {}


def _parsed(source: str):
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if key not in _AST_CACHE:
        _AST_CACHE[key] = ast.parse(source)
    return _AST_CACHE[key]


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    """Line range of the symbol named by a dotted path (owner-aware, unchanged since batch-009)."""
    tree = _parsed(source)
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

    Batch-018's six repository records have no symbol (the register stores `symbol: null` for the
    `pass` statements that constitute a class body): for those the scope is the enclosing class
    found by AST at the recorded line (or the module, if a future record sits outside any class)
    - never a nearest-line window.
    """
    if (symbol or "").strip():
        return symbol_body(source, symbol)
    tree = _parsed(source)
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.lineno <= line <= (node.end_lineno or node.lineno):
            if best is None or node.lineno >= best.lineno:
                best = node
    if best is None:
        return 1, len(source.splitlines())
    return best.lineno, best.end_lineno


def scope_symbol_forms(source: str, line: int) -> list[str]:
    """The qualified names of the classes/functions enclosing `line`, innermost first.

    The M32/M33-era identity of a *symbol-less* record (a `pass` that is a class body) used the
    enclosing class name as its symbol component - that is the form under which the six
    repository records' fingerprints reproduce, and the AST supplies it, not a line guess.
    """
    tree = _parsed(source)
    forms: list[str] = []

    def walk(node, prefix):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + [child.name]
                if child.lineno <= line <= (child.end_lineno or child.lineno):
                    forms.append(".".join(qualified))
                    forms.append(child.name)
                walk(child, qualified)

    walk(tree, [])
    return forms


def ast_segment_forms(source: str, line: int, limit: int = 60) -> list[str]:
    """Normalized source segments of the AST nodes containing `line`, smallest span first.

    The M34 sweep stores a 200-character prefix of the collapsed line (`tools/m34/sweep34.py:79`),
    so for a statement that spans several lines the ledger's `pattern` cannot reproduce the
    fingerprint.  The statement itself can: this is the same expression the record was fingerprinted
    from, recovered from the source rather than from the truncated copy.
    """
    tree = _parsed(source)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
        if not (node.lineno <= line <= (node.end_lineno or node.lineno)):
            continue
        segment = ast.get_source_segment(source, node)
        if not segment or len(segment) > 4000:
            continue
        normalized = m34_norm(segment)
        if normalized and normalized not in [f[1] for f in found]:
            found.append(((node.end_lineno or node.lineno) - node.lineno, normalized))
    found.sort(key=lambda item: (item[0], len(item[1])))
    return [text for _, text in found[:limit]]


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


def fingerprint_proof(record: dict, m34: dict, tree_source: str) -> tuple[str, str] | str | None:
    """Re-derive the record's context_fingerprint from its M34 identity (content, not lines).

    Contract: fingerprint = sha256("path|kind|symbol|norm(expression)|ordinal")
    (tools/m34/common.py:52-54).  Three symbol forms occur in the recorded identities and all are
    tried: the symbol's last dotted component (M32/M33-carried records), the qualified symbol, and
    the *enclosing class* of a symbol-less record (the six `pass`-as-class-body records, whose
    register `symbol` is null).  The expression is first the M34 ledger's `pattern`; for a record
    whose pattern cannot reproduce it (the sweep truncated the expression to 200 characters) the
    statement's AST segments are tried as well.  Returns (symbol form, expression form) or None
    when the record has no M34 pattern at all.
    """
    row = m34.get(record["id"])
    if not row or not row.get("pattern"):
        return None
    symbol = record.get("symbol") or ""
    line = record["line"]
    forms: list[tuple[str, str]] = []
    for form, candidate in (("short", symbol.split(".")[-1]), ("qualified", symbol)):
        if candidate and all(candidate != existing for _, existing in forms):
            forms.append((form, candidate))
    for candidate in scope_symbol_forms(tree_source, line):
        if all(candidate != existing for _, existing in forms):
            forms.append((f"enclosing-scope:{candidate}", candidate))
    expressions: list[tuple[str, str]] = [("m34-pattern", m34_norm(row["pattern"]))]
    for segment in ast_segment_forms(tree_source, line):
        if segment != expressions[0][1]:
            expressions.append(("ast-segment", segment))
    for expression_form, expression in expressions:
        for form, candidate in forms:
            payload = "|".join([record["file"], row.get("kind") or "", candidate, expression, "0"])
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() == record["context_fingerprint"]:
                return (form, expression_form)
    return "MISMATCH"


def check(batch: list[dict]) -> tuple[list[tuple[str, str, int, int, str]], dict]:
    problems: list[str] = []
    reanchored: list[tuple[str, str, int, int, str]] = []
    current_cache: dict[str, list[str]] = {}
    current_src: dict[str, str] = {}
    tree_src: dict[tuple[str, str], str] = {}
    maps: dict[tuple[str, str], dict[int, int]] = {}
    m34 = {}
    ledger = json.loads((ROOT / FINGERPRINT_SOURCE).read_text(encoding="utf-8"))
    for row in list(ledger["carried_records"]) + list(ledger["new_records"]):
        m34[row["id"]] = row
    stats = {"fingerprints_checked": 0, "fingerprints_verified": 0,
             "fingerprints_without_evidence": [], "fingerprints_by_form": {},
             "fingerprints_by_expression_form": {},
             "fingerprints_not_reproduced_but_hash_anchored": [], "trees": {}}

    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        declared = record.get("source_sha256") or ""
        tree_lines, tree_bytes, provenance = provenance_tree(path, declared)
        stats["trees"].setdefault(path, provenance)
        source_key = (path, declared)
        if source_key not in tree_src:
            tree_src[source_key] = tree_bytes.decode("utf-8", "replace")
        if path not in current_src:
            src = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            current_src[path] = src
            current_cache[path] = src.splitlines()
        lines = current_cache[path]
        current_is_tree = hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == declared
        start, end = record_scope(current_src[path], record.get("symbol", ""), line)
        if current_is_tree:
            fstart, fend = start, end
        else:
            fstart, fend = record_scope(tree_src[source_key], record.get("symbol", ""), line)

        proof = fingerprint_proof(record, m34, tree_src[source_key])
        if proof is None:
            stats["fingerprints_without_evidence"].append(record["id"])
        else:
            stats["fingerprints_checked"] += 1
            stats["fingerprints_verified"] += int(proof != "MISMATCH")
            if proof == "MISMATCH":
                form = "MISMATCH"
            else:
                form, expression_form = proof
                stats["fingerprints_by_expression_form"][expression_form] = \
                    stats["fingerprints_by_expression_form"].get(expression_form, 0) + 1
            stats["fingerprints_by_form"][form] = stats["fingerprints_by_form"].get(form, 0) + 1

        # Hash-anchored: the record's own declared sha256 has selected a tree (current or
        # provenance) in which the recorded text sits at the recorded line inside the record's
        # AST scope.  Batch-018 generalises batch-017's rule from 'the current file is the
        # recorded tree' to 'a hash-verified tree is', because this batch's core/database.py
        # records legitimately belong to 4c543e8^.
        hash_anchored = 0 < line <= len(tree_lines) \
            and text_matches(expected, tree_lines[line - 1]) and fstart <= line <= fend
        if proof == "MISMATCH":
            if hash_anchored:
                stats["fingerprints_not_reproduced_but_hash_anchored"].append(record["id"])
            else:
                problems.append(f"{record['id']}: context_fingerprint does not reproduce from its "
                                f"M34 identity (any symbol form, any expression form) and the "
                                f"record is not hash-anchored")
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
        "symbol": record.get("symbol"), "rule": record.get("rule"), "kind": record.get("kind"),
        "register_line_text": record.get("current_source_line"),
        "classification": R[record["id"]][0], "evidence": R[record["id"]][1],
        "remaining_question": R[record["id"]][2],
        "defect": R[record["id"]][0] == DEF,
        "test": None, "commit": None,
    } for record in batch]

    by_file: dict[str, int] = {}
    for item in items:
        by_file[item["file"]] = by_file.get(item["file"], 0) + 1

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("phase-2 class B (persistence / import-IR semantics): "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))
                  + " - the daily-report readers and the revision writer, the import IR/quality/"
                    "diagnostics boundary, the repository layer split out of DatabaseManager, one "
                    "PDF-adapter plan/actual guard, one report-history serializer and one "
                    "casing-persistence assertion"),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "records_by_file": dict(sorted(by_file.items())),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "observations": OBSERVATIONS,
        "sibling_search": {
            "target": ("the batch's own families as populations: the `pass` that is a class body, "
                       "the `default=str` serialization default, the container default `or {}` / "
                       "`or None` in front of stored or imported data, the truthiness test on an "
                       "id/ORM/date, and the broad/typed exception handler at an import boundary"),
            "method": ("deterministic re-scan of the repository (342 source files, `tools/` "
                       "excluded) for each construct shape, then per-family cross-check against "
                       "the register so nothing in this batch's files is left un-adjudicated: "
                       "(a) AST scan for a `pass` that is the sole non-docstring body of a class "
                       "- 20 sites, of which 8 are exception classes (core/error_handler.py, "
                       "core/excel_normalizer.py, core/legacy_bha.py, core/engineering/*), 6 are "
                       "this batch's repository placeholders, 3 are UI/test stubs (LogData, Boom, "
                       "Stub) and 3 are the acceptance-test stubs - a repository-wide idiom, none "
                       "of which is a swallowed operation; (b) `default=str` - 27 sites "
                       "(8 in core/database.py, 4 in tabs/, 3 in dialogs/, others in "
                       "core/lineage.py, core/ddr_import_service.py, "
                       "core/professional_export.py, core/engineering/drill_pipe.py, tests/); this "
                       "batch's two are a hidden debug view and a test-internal comparison, and "
                       "the remaining 15 are carried by other batches' records (R-SNAP-SERIAL-"
                       "DEFAULT: 16 total, 13 already adjudicated in batches 002-017 or scheduled "
                       "for 019); (c) `or {}` (176 sites) / `or None` (98 sites) - the "
                       "documented-default family; this batch's four are the import boundary and "
                       "the well-identity resolver, and the register's R-DEF-UNKNOWN population "
                       "(152 records) is spread across batches 018-029, so no sibling is "
                       "unassigned; (d) `X if X else None` selections - 106 sites, whose "
                       "R-SEL-UNPROVEN population (20 records) is this batch's 2 plus batch-019's "
                       "12 plus 6 already adjudicated; (e) exception handlers in the import path - "
                       "R-EXC-OTHER (60) and R-EXC-CONTINUE (35) populations are fully assigned to "
                       "batches 018-029, and this batch's three are typed-and-reporting "
                       "(INV34-001106, INV34-002044) or a skip that cannot lose data "
                       "(INV34-001987)."),
            "counts": {
                "source_files_scanned": 342,
                "pass_as_sole_class_body": 20,
                "default_str_occurrences": 27,
                "or_empty_mapping": 176,
                "or_none": 98,
                "x_if_x_else_none": 106,
                "R-DEF-UNKNOWN_records_total": 152,
                "R-TRUTH-UNKNOWN_records_total": 367,
                "R-PASS-OTHER_records_total": 23,
                "R-EXC-OTHER_records_total": 60,
                "R-EXC-CONTINUE_records_total": 35,
                "R-SEL-UNPROVEN_records_total": 20,
                "R-SNAP-SERIAL-DEFAULT_records_total": 16,
                "R-NUM-UNKNOWN_records_total": 45,
                "R-PLAN-OTHER_records_total": 48,
            },
            "findings": [
                {"site": "repository placeholders (6 records)",
                 "status": ("the `pass` is the mandatory body of an empty subclass; all six are "
                            "exported and none is instantiated in-repo - adjudicated INTENTIONAL "
                            "with the inherited-CRUD evidence, not by similarity")},
                {"site": "import IR / quality boundary (12 records)",
                 "status": ("every container default and truthiness test read there is either the "
                            "declared 'not recorded' value of the class itself (`row: int = 0`, "
                            "`source_cell: str = \"\"`) or an explicitly Optional argument; the "
                            "two handlers report instead of swallowing (an error row, an "
                            "INVALID_SOURCE review) and the one skip cannot lose data")},
                {"site": "daily-report readers (10 records)",
                 "status": ("all ten are the ORM-or-None existence test, the primary-key truthiness "
                            "of an optional filter, or a date presence test; every getter returns "
                            "None for a missing row and a column-by-column projection for a found "
                            "one, and the only fail-open-looking handler in the family re-raises")},
                {"site": "chart builders (2 records)",
                 "status": ("both loops are explicitly gap-preserving with in-code contracts; the "
                            "consumer test asserts the gap (data_points == 1 for three seeded "
                            "days)")},
            ],
        },
        "tests": ("no production code was changed in this batch, so no new regression was written "
                  "and no mutation validation applies; the batch script itself runs with the "
                  "provenance and fingerprint gates active (see `staleness`), i.e. all 45 records "
                  "were re-anchored and re-identified against the hash-verified tree before any "
                  "classification was written"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m34-evidence/m34-ledger.json",
                           "tools/m36/p6_batch_018.py",
                           "core/database.py",
                           "core/import_ir.py",
                           "core/import_quality.py",
                           "core/import_diagnostics.py",
                           "core/repositories/base.py",
                           "core/import_adapters/pdf_tables.py",
                           "dialogs/report_history_dialog.py"],
        "staleness": {
            "checked": len(batch), "stale": len(reanchored), "re_anchored": len(reanchored),
            "method": ("every record's declared source_sha256 selects the tree its line number "
                       "belongs to: the current file when the hash matches, otherwise a "
                       "hash-verified provenance tree.  For this batch all 18 core/database.py "
                       "records belong to `4c543e8^` (sha256 "
                       "578d6a9c3eb83c405d7c3fb5d532416c2612137117a7bfa6d8d32b83562e54c2 - the "
                       "tree before batch-017's own fix inserted its docstring and guard, a "
                       "uniform +11 shift), and the other 13 files are byte-identical to the "
                       "recorded tree, so 27 records are anchored in the current tree.  The "
                       "recorded text must match at the recorded line of that tree, and the "
                       "difflib map tree->current must land on the same text inside the symbol's "
                       "AST range (for the six records the register leaves without a symbol - the "
                       "`pass` statements that are class bodies - the scope is the enclosing class "
                       "found by AST).  In addition, every record's context fingerprint was "
                       "re-derived from its M34 identity (path|kind|symbol|pattern|ordinal, "
                       "tools/m34/common.py), so the 'same site' claim rests on content, not on "
                       "line arithmetic."),
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
                "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"],
                "method": ("sha256(\"path|kind|symbol|norm(expression)|0\") == the record's "
                           "context_fingerprint, with three symbol forms (the symbol's last "
                           "component, the qualified symbol, and - for the six symbol-less "
                           "repository records - the enclosing class found by AST) and two "
                           "expression forms (the M34 ledger's `pattern`, and for a pattern the "
                           "sweep truncated to 200 characters, the statement's own AST segments).  "
                           "44 of 45 reproduce this way; the single exception (INV34-000786) is a "
                           "carried M32 record whose line drifted inside its own lifetime (its "
                           "fingerprint was generated from a text form that survives nowhere in "
                           "the shipped tooling), and it is anchored instead by the "
                           "hash-verified provenance tree, the recorded text at the recorded line "
                           "and the record's AST scope - both of its surviving readings were "
                           "adjudicated by reading the source.")},
        },
        "method": ("all 45 records were read at their own sites in the hash-verified tree (the "
                   "current file, or `4c543e8^` for core/database.py) and the flagged construct "
                   "was traced to its consumer before classification: the revision writer and its "
                   "single UI caller, the ten report readers and their export/report consumers, "
                   "the two chart builders and the consumer test that asserts their gap "
                   "semantics, the audit writer/reader pair, the import IR (SourceLocation, "
                   "RawDocument tables, ReviewItem, TimeLogValidator, PersistenceError) and the "
                   "canonical-mapper/review-matrix contracts it feeds, the six exported empty "
                   "repository subclasses against BaseRepository's inherited CRUD, the well "
                   "identity resolver against its acceptance test, the drill-pipe controlled "
                   "lookup against its module contract, and the PDF adapter's summary/forecast "
                   "guard against the emitted table and its test.  The deciding contract is "
                   "quoted in `evidence` for every record; no line of production code was changed."),
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
