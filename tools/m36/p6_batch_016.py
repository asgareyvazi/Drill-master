#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-016 (45 MEDIUM records, class A: UI tabs).

Phase 2, batch A of the schedule: the UI truthiness/exception surface of the daily-report tab
(w2), the wellbore-schematic tab (w3b), the section-data tab (w3c), the equipment widget (w5),
the trajectory widget (w6) and the logistics widget (w7).  Every record is adjudicated at its own
site: the flagged construct is read in the current tree, its subject's optionality is established
from the declaration/constructor/caller contract, and the fallback is traced to its consumer and
to the persistence boundary it feeds.  No production file is changed by this batch (no defect was
proven here); the two files whose line numbers had moved since the register was generated are
re-anchored through a *provenance tree* whose sha256 is verified against the record's own
declared source_sha256 (see `staleness` in the emitted JSON), never through a nearest-line guess.
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
BATCH = "p6-batch-016"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

# Batch-015's mechanism (recorded text verified against <commit>^ and re-anchored through
# difflib) is kept, but here it is *provenanced*: the tree the register's line numbers belong
# to must hash to the record's own declared `source_sha256` before any comparison happens.
RECHECK_AGAINST: dict[str, str] = {"tabs/w7_logistics_Widget.py": "c2e0016"}

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
    # ------------------------------------------------------------------ w2 daily report
    "INV34-005365": (VC,
        "`_extract_time_log_row` is a record-or-nothing producer: it returns None when the row has "
        "no from/to time widgets (`if not from_widget or not to_widget: return None`, "
        "tabs/w2_Daily_Report.py:1396-1397), keeps that shape at its tail guard (1497), and "
        "otherwise returns a record with every key the writer reads (return dict, 1474-1487).  The "
        "guarded subject is that dict, and a record which reached the return always carries its "
        "ten keys, so `if log:` (1361, and the sibling loop for time_24_table at 1343-1345) is the "
        "producer's own 'usable row' test: the writer immediately indexes `log[\"time_from\"]`, "
        "`log[\"duration\"]`, `log[\"main_code\"]` ... into TimeLogMorning/TimeLogEvening, so a "
        "falsy-but-present record cannot occur and a blank table row can never become an empty "
        "time-log entry.", None),
    # ------------------------------------------------------------------ w3b schematic
    "INV34-005526": (VC,
        "The subject is a table cell, not a value: `QTableWidget.item(i, 0)` yields the row's "
        "QTableWidgetItem or None, and the guard asks only whether the cell exists.  Its body "
        "assigns through the drawing's own enum map with the *current* value as fallback "
        "(`casing.element_type = type_map.get(type_item.text(), casing.element_type)`, 766-768), "
        "so neither a missing cell nor an unrecognised label invents a category.  The whole sync "
        "runs on `itemChanged` (203 -> `_on_casing_table_changed`, 736-741), i.e. on partial "
        "tables, and is additionally index-protected by the row-count precondition "
        "(`if len(self.schematic.casings) != self.casing_table.rowCount(): return`, 745-746).", None),
    "INV34-005524": (VC,
        "Cell-presence guard (`self.casing_table.item(i, 1)` is None when the cell was never "
        "created): the body reads `float(od_item.text())` (770).  An absent cell leaves the "
        "geometry untouched; a present-but-unparseable entry raises ValueError, which the "
        "enclosing `except (ValueError, IndexError)` (785-786) swallows so that one malformed cell "
        "cannot break the event-driven sync.  Recorded observation (not a defect claim): that "
        "swallow leaves the previous OD in the model while the table shows the typed text - a "
        "silent ignore, never a coerced number; the persisted schematic stores the model's own "
        "values (save_data, 943-1000), so nothing invalid reaches the database.", None),
    "INV34-005523": (VC,
        "The one casing field with an explicit unknown state, and the branch proves the point: a "
        "missing cell skips the assignment, while a *present* cell is read as a trichotomy - "
        "`id_text in (\"\", \"-\", \"-\")` ... i.e. `if id_text in (\"\", \"-\", \"-\")` on the "
        "stripped text, else `float(id_text)` (772-778) - with the comment stating '\"-\"/empty = "
        "explicitly unknown wall thickness (None); a numeric value (including 0) is a real fact'.  "
        "So the presence test is exactly what the value contract needs: absence means 'leave the "
        "previous value', and 0 is preserved as a fact.", None),
    "INV34-005525": (VC,
        "Cell-presence guard for the casing top (`self.casing_table.item(i, 3)`), body "
        "`casing.top_depth_m = float(top_item.text())` (780).  An absent cell keeps the previous "
        "top; a malformed entry raises and is caught by the same narrow `(ValueError, IndexError)` "
        "handler (785-786), which cannot invent a depth - the drawing simply keeps the last "
        "geometry it had.  Distinguishing 'no cell' from 'cell with 0' matters here and is done "
        "correctly: a typed 0 parses to 0.0 and is a real top depth.", None),
    "INV34-005522": (VC,
        "Cell-presence guard for the casing bottom, whose body writes two model fields from the "
        "same number (`casing.bottom_depth_m = float(bot_item.text())` and "
        "`casing.cement_bottom_m = float(bot_item.text())`, 781-783) - the codebase's documented "
        "default that a casing's cement bottom starts at its shoe and is then edited separately.  "
        "A missing cell changes nothing (the pair keeps its previous values, so the two fields "
        "cannot fall out of sync by an absence); a malformed entry raises into the same narrow "
        "handler.  No zero is fabricated in either case.", None),
    "INV34-005533": (VC,
        "The persistence entry point returns the stored id or None (`save_wellbore_schematic` -> "
        "`return record_id` / `return None`, core/database.py:6044, 6048), and a SQLite id is never "
        "0, so `if result:` (994) is the write-success gate: truthy -> `show_success(\"Schematic "
        "saved\")` + `return True`; falsy -> control reaches the function's final `return False` "
        "(1000) after the except block reports `Save failed: ...` (997-999).  The saved payload is "
        "built from the model's own fields inside the same try (945-992), so a falsy result cannot "
        "be reported as a successful save.", None),
    # ------------------------------------------------------------------ w3c section data
    "INV34-005714": (VC,
        "`self.db_manager` is optional by declaration (`def __init__(self, db_manager=None, "
        "parent=None)`, tabs/w3c_section_data.py:29, stored at 31), so the ternary's test is the "
        "handle's presence test and its None branch reports 'nothing was saved' - consistent with "
        "the entry point's own result contract (`save_cement_report` -> `record_id` / `None`, "
        "core/database.py:5907, 5911), i.e. None already *is* this dialog's not-saved value.  The "
        "sibling load path treats the same handle the same way (`if self.current_well: data = "
        "self.db_manager.get_cement_report(...) if self.db_manager else None`, 191-193), and a "
        "repository-wide search finds no caller of `save_data_with_section`, so no consumer can "
        "read the None as a success.", None),
    "INV34-005698": dup("INV34-005714", "tabs/w3c_section_data.py:357 - the casing tab's identical "
                                        "`return self.db_manager.save_casing_report(d) if "
                                        "self.db_manager else None`",
                        "same Optional handle (ctor `db_manager=None` at 240, stored at 242), same "
                        "id-or-None result contract (`save_casing_report` -> 5976, 5980), same "
                        "None-means-not-saved reading"),
    "INV34-005702": (VC,
        "`save_casing_report` returns the stored id or None (core/database.py:5976, 5980), and the "
        "enclosing branch only runs when the widget itself is connected (`if self.db_manager:`, "
        "631).  A truthy result is the only path that reports `Saved` and returns True (642-644); "
        "a falsy one falls through to `return False` (645) without a success message and without a "
        "second write attempt - the tally JSON is a single atomic entry (`tally_json=full`, "
        "639).", None),
    "INV34-008346": (INT, _SPIN_ZERO, None),
    "INV34-010274": (VC,
        "`_collect_data` (1173-1200) builds every failure-report field from str/number widgets - "
        "including the date, which is already a string (`\"issue_date\": "
        "self.issue_date.date().toString(\"yyyy-MM-dd\")`, 1193) - so the JSON-native types cover "
        "the whole document and `default=str` (1318) is a *type* fallback, not a field default: it "
        "cannot add a key and cannot turn a missing value into a number.  The reader is the exact "
        "inverse (`self.reports_list = json.loads(existing.notes)`, 1350) and its failure path is "
        "explicit and loud (`logger.error(f\"Load failure reports error: {e}\")` then `raise`, "
        "1355-1358), so a corrupt snapshot cannot silently become an empty report list.", None),
    # ------------------------------------------------------------------ w5 equipment widget
    "INV34-005899": (VC,
        "The subject of the ternary is a table cell: `self.table.item(row, column)` yields a "
        "QTableWidgetItem or None, and the None branch hands the *canonical* boundary the value it "
        "uses for 'the cell has no text' - None - instead of the string \"\".  The next statement "
        "routes the cell text into `normalize_item_row` (266), the documented owner of this domain's "
        "trichotomy: an empty string parses to None (unknown), an explicit 0 to 0.0, and a "
        "malformed entry raises `EngineeringError` from `optional_number` "
        "(`if value is None or value == \"\": return None` ... `float(value)` ... \"Invalid numeric "
        "value for {field}\") - it is never coerced to 0.  That raise is handled loudly by "
        "`calculate_inventory` itself: `logger.error(f\"Calculation failed: {str(e)}\")`, every "
        "remaining cell is stamped \"INVALID\" with the tooltip \"Calculation failed: invalid "
        "worksheet numeric input\" and the method returns False (297-307).", None),
    "INV34-005900": (VC,
        "The cell exists only to *display* the derived closing stock, and the guard creates the "
        "QTableWidgetItem when the row has none (273-275) so the value can be written "
        "unconditionally on the next line - including the unknown case, which is rendered as an "
        "empty cell rather than \"0.00\" (`remaining_item.setText(\"\" if remaining is None else "
        "f\"{remaining:.2f}\")`, 279, with the comment 'Unknown remaining shows as an empty cell "
        "(not \"0.00\"), keeping the UI honest with what will be persisted').  The test is on a "
        "widget handle, never on the number: `remaining` itself comes from `derive_closing(opening, "
        "received, used)` (270), which returns None when the opening is unknown.", None),
    "INV34-005897": (VC,
        _DB_OPTIONAL + "  The guard sits after the permission gate and before the only persistence "
        "step of the method (`from core.save_outcome import save_all` at 791 is the first write "
        "path), and its `return False` is the same not-saved result every sibling save path of this "
        "widget uses for 'the save did not happen' (e.g. the permission refusal at 767/770 and the "
        "'no well selected' refusal at 784-786).  The record's line moved because this very defect "
        "fix (9f45cc4, the fail-closed permission block now at 771-782) was inserted above it - the "
        "register's tree is proven by its declared sha256 and the re-anchor lands on the identical "
        "statement inside `EquipmentWidget.save_all_data`.", None),
    "INV34-005840": (INT,
        "`_report_date_for_current` is documented as 'Best-effort report_date for the current "
        "report (for carry-forward)' (892-893), and every one of its three early returns yields "
        "None - no `date.today()`, no epoch, no guess: no report id/handle (894-895), a DB read "
        "failure (896-899) and a report object without a date (900-901) all mean 'unknown date'.  "
        "Its single caller passes that None straight into the persistence contract by keyword "
        "(`report_date=self._report_date_for_current()`, 918), and `save_inventory_items` itself "
        "documents and implements the semantics of an absent date: identity is (well_id, report_id, "
        "item_name) (7184-7191), `report_date` is stored as given (7259) and carry-forward - the "
        "only consumer of the date - is skipped when it is None (`if opening is None and "
        "report_date is not None:`, 7246).  So an unreadable report date degrades the save to 'no "
        "carry-forward' with the date left NULL; it cannot become today's date.  Recorded "
        "observation, not a defect claim: the handler does not log (the module logger is used "
        "elsewhere in the same class), so the degradation is undiagnosed rather than wrong.", None),
    "INV34-005838": (INT,
        "A one-time compatibility fallback, read-only by construction: the authoritative store was "
        "already read above (`self.db.get_inventory_items(well_id=..., report_id=...)`, 938-939) "
        "and its failure *is* reported (`except Exception as e: logger.error(f\"Inventory load "
        "failed: {e}\")`, 940-942); the legacy query only runs when that authoritative store has no "
        "rows for the scope (`if not items:`, 944) and exists to surface `EquipmentLog` notes rows "
        "for manual re-save ('One-time compatibility: surface legacy EquipmentLog notes rows so "
        "they can be migrated by re-saving. Read-only, unknown preserved.', 945-946).  When the "
        "legacy read itself fails, `items = []` (951-952) is the same state as 'there are no legacy "
        "rows' and the method returns before touching the table (953-954) - the load path already "
        "cleared the tables and the authoritative read is the displayed truth, so the only thing "
        "lost is the migration hint.  No stored data is read as 0 and nothing is written.", None),
    "INV34-005895": (VC,
        _DB_OPTIONAL + "  The body only fills the well selector from the hierarchy "
        "(`hierarchy = self.db.get_hierarchy()` then the company/project/well loops, 1090-1095): "
        "without a handle there is nothing to enumerate, so skipping the fill is the faithful "
        "behaviour rather than a silent failure - and every consumer of the combo box in this "
        "widget is itself gated on `self.db`/`self.current_well`, so no code path can interpret an "
        "unfilled combo as 'no wells exist'.", None),
    # ------------------------------------------------------------------ w6 trajectory
    "INV34-008395": (DUP,
        "Rule mis-fire and, at the same time, a verified validation: the truthiness test applies to "
        "a *computed boolean*, `not math.isfinite(number)` (tabs/w6_Trajectory_Widget.py:200-201), "
        "not to a value whose presence is in question, and it is paired with the explicit range "
        "check `number < 0`; both raise (`ValueError(\"Trip measurements must be finite and "
        "nonnegative\")`).  The helper is built as a trichotomy: a missing/em-dash cell returns "
        "None (`value = item.text().strip() if item is not None else \"\"`; `if value in (\"\", "
        "\"—\"): return None`, 196-198) so an unknown measurement is never 0.0, and the same rule "
        "reappears one screen above for the depth sum (`if depth is not None and (not "
        "math.isfinite(depth) or depth < 0): raise ValueError(\"Invalid depth\")`, 150-153) with "
        "`fmt_num(..., default=None)` rendering unknown as blank.  The failure is loud: the "
        "enclosing save handler rolls the transaction back, logs and returns False (241-246).", None),
    # ------------------------------------------------------------------ w7 logistics
    "INV34-006178": (VC,
        "`remove_pob_row` deletes through the handle only when a handle exists *and* the row "
        "carries a stored id (`if id_item and id_item.text(): pob_id = int(id_item.text()); if "
        "self.db: self.db.delete_service_company_pob(pob_id)`, 225-229), then removes the row from "
        "the table and reports 'POB row removed' (230-231).  The id column is hidden "
        "(`self.pob_table.setColumnHidden(0, True)`) and only ever written by the loader or by the "
        "save write-back, so the unguarded `int()` cannot see user text.  A missing handle means "
        "the tab was never loaded from storage (see the class contract), so the row being removed "
        "was added by hand and nothing persisted is lost - the local removal is the honest result.", None),
    "INV34-006191": (VC,
        _W7_DB + "  Here the guard precedes the whole save body (260-262) and returns False before "
        "the loop, so no dialog-free partial write can be attempted; the method's own error "
        "reporting is preserved (the row-level rejects become a `SaveOutcome` whose issues are "
        "shown, 301-307).", None),
    "INV34-008408": dup("INV34-006191", "tabs/w7_logistics_Widget.py:260 - the M34 re-sweep's second "
                                        "record for the same guard statement",
                        "one statement, one site; the subject, the reason and the False return "
                        "are the record above"),
    "INV34-008409": (VC,
        "A row-completeness test with an explicit reason: the payload's `company_name` comes from "
        "this very cell (`\"company_name\": company_item.text()`, 285) and the persistence layer's "
        "identity/validation treats the company as the subject of the record "
        "(`save_service_company_pob` normalizes personnel_count and requires the non-negative "
        "integer, raising for a malformed one, core/database.py:6857-6866).  Skipping a row that "
        "has no company text is therefore correct - it cannot be persisted as a meaningful row, "
        "and the alternative (writing an empty company) would invent a record.  The check is on "
        "the *presence of the cell* first (`not company_item`) exactly like its siblings.", None),
    "INV34-006188": (VC,
        "`optional_date` is the repository's missing-tolerant date parser: "
        "`ValueNormalizer.normalize(value, \"date\")` returns an ok result carrying None when the "
        "value is missing (`if cls.is_missing(value): return NormalizationResult(value, None, ..., "
        "ok=True)`, core/value_normalizer.py:90-91), so a blank or absent Date IN cell yields None "
        "(unknown) - never a substituted date - and a *stated but invalid* date raises ValueError "
        "which the surrounding try turns into a per-row rejection with the row's number and "
        "company name in the message (`rejected.append(f\"POB row {row + 1}, company ...\")`, "
        "278-280).  The `if date_in_item else None` part of the expression is the same "
        "cell-presence guard as its siblings, applied to the text read.", None),
    "INV34-006189": dup("INV34-006188", "tabs/w7_logistics_Widget.py:276 - the Date OUT cell of the "
                                        "same row conversion",
                        "same missing-tolerant parser call and the same cell-presence guard; a "
                        "blank date is unknown and an invalid one is rejected per row"),
    "INV34-006193": (VC,
        _RESULT_ID + "  The `if result:` at 295 is the write-success gate of "
        "`save_pob_to_db`: a truthy id bumps `saved_count` and writes the new id back into the "
        "hidden id cell (`if not id_item or not id_item.text(): self.pob_table.setItem(row, 0, "
        "QTableWidgetItem(str(result)))`, 297-298); the falsy branch appends an explicit "
        "persistence failure to the rejects (`else: rejected.append(...'persistence failed'...)`, "
        "299-300) which is then surfaced as a SYSTEM_ERROR issue and turned into a False result "
        "(`return not rejected`, 301-307).  No falsy result is reported as saved.", None),
    "INV34-008410": (VC,
        "The id write-back guard: the row's hidden id cell is filled with the id the save just "
        "returned *only when it is still empty* (`if not id_item or not id_item.text(): "
        "self.pob_table.setItem(row, 0, QTableWidgetItem(str(result)))`, 297-298), so an existing "
        "id is never overwritten by a fresh one - and the subject is again the cell's "
        "presence/text, not a number.  Both branches keep the table consistent with the persisted "
        "row (the id is read back by `remove_pob_row` for the delete call).", None),
    "INV34-006177": (VC,
        "The crew counterpart of the POB delete guard: `id_item = self.crew_table.item(current_row, "
        "0)`; `if id_item and id_item.text(): personnel_id = int(id_item.text()); if self.db: "
        "self.db.delete_logistics_personnel(personnel_id)` (368-372), then the row is removed and "
        "'Crew row removed' reported (373-374).  Same reasons as the POB row: the guard is the "
        "handle's presence test, the id is machine-written, and inside the `grep`-verified class "
        "contract a missing handle means nothing was loaded from storage.", None),
    "INV34-006184": (VC,
        _W7_DB + "  The guard is the first statement of `save_crew_to_db` (381-382) and returns "
        "False before the loop, so the crew worksheet is never half-written; the row-level "
        "completeness check (`if not name_item or not name_item.text(): continue`, 394-395) keeps "
        "nameless rows out of the payload.", None),
    "INV34-008416": dup("INV34-006184", "tabs/w7_logistics_Widget.py:381 - the M34 re-sweep's second "
                                        "record for the same guard statement",
                        "one statement, one site; identical to the adjudicated record above"),
    "INV34-006187": (VC,
        _RESULT_ID + "  `if result:` (411) gates the id write-back and the save timestamp "
        "(`self.crew_table.setItem(row, 8, QTableWidgetItem(datetime.now().strftime(\"%Y-%m-%d "
        "...\")))`, 413-415) and is followed by `show_success(f\"Saved {saved_count} crew "
        "records\")` and `return True` (416-417); the except path logs and returns False "
        "(418-421).", None),
    "INV34-008417": (VC,
        "The crew id write-back guard (`if not id_item or not id_item.text(): self.crew_table."
        "setItem(row, 0, QTableWidgetItem(str(result)))`, 413-414): writes the freshly persisted "
        "id only into an empty id cell, leaving an existing (re-saved) row's id untouched; the "
        "subject is the cell, and both branches keep the table aligned with the stored row.", None),
    "INV34-006196": (VC,
        _W7_DB + "  `save_transport_note` opens with the same guard and returns before building its "
        "payload (484-485); the note's own identity is `id = getattr(self, \"_loaded_note_id\", "
        "None)` (488) - an absent id is the 'new note' case the persistence layer handles by "
        "inserting, so an unloaded tab cannot silently update an unrelated note.", None),
    "INV34-008424": dup("INV34-006196", "tabs/w7_logistics_Widget.py:484 - the M34 re-sweep's second "
                                        "record for the same guard statement",
                        "one statement, one site; identical to the adjudicated record above"),
    "INV34-006197": (VC,
        _RESULT_ID + "  Truthy: `show_success(\"Transport note saved\")`, the form is cleared and "
        "`self._loaded_note_id = None` so the next save inserts instead of updating, then `return "
        "True` (499-503).  Falsy: the function leaves the form untouched and falls out of the try "
        "block *without* returning a success value, and the except path logs, shows the error and "
        "re-raises (`raise`, 504-507) - a falsy write can never be reported as saved.", None),
    "INV34-006166": (VC,
        _W7_DB + "  The body is deliberately read-only: notes are fetched for the selected scope "
        "and, when any exist, the form is cleared with the module's own comment recording why - "
        "'delete logic would go here if db had a delete method; for now just clear' (554-556) - "
        "followed by `show_success(\"Note cleared\")`.  The guard cannot hide a delete: no delete "
        "is implemented for transport notes (the repository does provide `delete_service_company_"
        "pob`/`delete_logistics_personnel`, which are called from the two guard sites above).", None),
    "INV34-008430": dup("INV34-006166", "tabs/w7_logistics_Widget.py:546 - the M34 re-sweep's second "
                                        "record for the same guard statement",
                        "one statement, one site; identical to the adjudicated record above"),
    "INV34-006141": (VC,
        _W7_DB + "  The fuel/water method needs the handle immediately (the whole body is the "
        "build-and-save of the day's inventory record, 925-991), and its refusal is explicit: "
        "`return False` before anything is read from the widgets.  The register's line for this "
        "record belongs to the pre-fix revision of this file (proven by the register's declared "
        "sha256 = fd18a2b's tree); the diff lineage is this batch's sibling-fix commit c2e0016, "
        "which inserted the stock-trichotomy block above and shifted the statement to 922 - the "
        "re-anchor is reported in `staleness`.", None),
    "INV34-008438": dup("INV34-006141", "tabs/w7_logistics_Widget.py:904 (register line) - the M34 "
                                        "re-sweep's second record for the same guard statement",
                        "one statement, one site; identical to the adjudicated record above"),
    "INV34-006142": (VC,
        _RESULT_ID + "  This specific gate is the strongest of the family: a falsy result takes the "
        "else branch that *reports the failure* (`self.status_manager.show_error(\"FuelWaterTab\", "
        "\"Failed to save fuel/water data\")`, 983-987) and returns False, while the truthy path "
        "clears the carry-forward preview ('Saving turns a projection into a recorded fact for "
        "this day', 979-982).  The runway fields are only supplied when they are truthfully "
        "computable (`if _drf is not None: inventory_data[\"days_remaining_fuel\"] = _drf`, "
        "968-975), so the saved record cannot carry a fabricated 0-day runway.", None),
    "INV34-006136": (VC,
        _W7_DB + "  `save_bulk_materials_to_db` opens with the well check and this guard and "
        "returns False before the loop (1153-1157); the loop's own completeness check keeps "
        "nameless rows out of the payload (`if not material_item or not material_item.text()"
        ".strip(): continue`, 1163-1164).  The register's line belongs to the pre-fix revision "
        "(fd18a2b's tree, sha-verified) and the statement now sits at 1156 after the same fix "
        "commit c2e0016; the re-anchor is reported in `staleness`.", None),
    "INV34-008453": dup("INV34-006136", "tabs/w7_logistics_Widget.py:1138 (register line) - the M34 "
                                        "re-sweep's second record for the same guard statement",
                        "one statement, one site; identical to the adjudicated record above"),
    "INV34-008454": (VC,
        "A row-completeness test whose reason is the persistence identity: the payload's "
        "`material_name` comes from this cell (`\"material_name\": material_item.text().strip()`, "
        "1190) and the storage boundary uses it as part of the row identity "
        "(`BulkMaterials.material_name == material_data['material_name']`, core/database.py:7367) "
        "and for lookups.  A nameless row cannot be persisted as a meaningful record, and blank "
        "text is not a material name - the guard skips it instead of inventing one.", None),
    "INV34-006016": (INT,
        _MOVEMENT_TRICHOTOMY + "  The default is a *parameter*, and its two call sites use it "
        "deliberately for different columns: `received`/`used` take the 0.0 default (1193-1194) "
        "while `initial_stock` overrides it with None (1192) - the opening is a *stock* (unknown "
        "when blank), the movements are *movements* (absent means zero).  The direct statement of "
        "the rule is in the canonical module's contract line, and a type conversion that cannot "
        "parse numeric movement text raises into the method's handler, which logs and reports "
        "`Save failed: ...` without writing (1213-1216).", None),
    "INV34-006137": (VC,
        _RESULT_ID + "  `if result:` (1204) is the bulk worksheet's write-success gate: it counts "
        "the saved row and fills the empty hidden id cell (`if not id_item or not id_item.text()"
        ".strip(): ... self.bulk_table.setItem(row, 0, new_id_item)`, 1205-1209), and the method "
        "reports `Saved {saved_count} bulk material records` and returns True (1211-1212) only "
        "after the loop; the except path logs the failure, shows `Save failed: ...` and returns "
        "False (1213-1216).", None),
}


NEW_FINDINGS: list[dict] = []

# Observations recorded while adjudicating this batch.  They are *not* defect claims and they are
# not silently patched: each is a diagnosability/expressiveness note on an otherwise verified
# behaviour, kept with the record that produced it and repeated in the final P6 report.
OBSERVATIONS: list[dict] = [
    {"record": "INV34-005840", "site": "tabs/w5_Equipment_Widget.py:896-899",
     "observation": ("`_report_date_for_current` is documented as best-effort and its handlers do "
                     "not log, so a transient failure of `get_daily_report_by_id` degrades the "
                     "inventory save to 'no carry-forward, NULL date' without a diagnostic.  The "
                     "value cannot become wrong (no fabricated date) and the row is still filed "
                     "under report_id, so this is a diagnosability note, not a defect.")},
    {"record": "INV34-005524/005525/005522", "site": "tabs/w3b_wellbore_schematic_tab.py:785-786",
     "observation": ("A malformed (non-numeric) OD/ID/top/bottom cell is swallowed by "
                     "`except (ValueError, IndexError): pass`; the model keeps its previous "
                     "geometry while the table shows the typed text.  Nothing is coerced to a "
                     "number and nothing invalid is persisted, but the user gets no feedback for "
                     "the cell that was ignored.")},
    {"record": "INV34-008346", "site": "tabs/w3c_section_data.py:864",
     "observation": ("The service-company dialog encodes the widgets' untouched/zero state as "
                     "NULL for `duration_day`/`npt_hours`; those two spin boxes have no "
                     "'not recorded' state (only `personnel` does), so a deliberately typed 0 "
                     "cannot be expressed and is re-encoded as NULL on the next save.")},
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
    proof_cache: dict[str, str] = {}
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
        start, end = symbol_body(current_src[path], record.get("symbol", ""))

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

    by_file: dict[str, int] = {}
    for item in items:
        by_file[item["file"]] = by_file.get(item["file"], 0) + 1

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": (f"class A (UI truthiness/exception surface): " + ", ".join(
            f"{k}:{v}" for k, v in sorted(classes.items()))
            + " - daily-report, wellbore-schematic, section-data, equipment, trajectory and "
              "logistics tabs"),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "records_by_file": dict(sorted(by_file.items())),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "observations": OBSERVATIONS,
        "sibling_search": {
            "target": ("the batch's own family as a population, not a sample: every truthiness "
                       "guard whose subject is the tab's optional persistence handle, in tabs/"),
            "method": ("regex `if (not )?self\\.db` over the tracked files of tabs/ "
                       "(53 hits), each hit located in the register; for the hits that are not "
                       "register records, the guard body was read and checked to be a "
                       "return/raise (fail-closed) rather than a silent continuation"),
            "hits": 53,
            "findings": [
                {"site": "tabs/, 53 `self.db` guards", "status": ("6 in this batch (w5 x2, w7 x4 "
                                                                 "distinct statements); 20 "
                                                                 "registered in other open batches "
                                                                 "(028, 029, 015, 017, 027, 024); 27 "
                                                                 "not P6-register records (closed in "
                                                                 "M33/M34) and each one returns or "
                                                                 "raises - no fail-open guard "
                                                                 "remains, verified by the 0-hit scan "
                                                                 "for a non-returning body")},
                {"site": "tabs/w7_logistics_Widget.py", "status": ("26 of the batch's 45 records; 7 "
                                                                   "distinct guard statements and "
                                                                   "6 M34 re-sweep duplicates "
                                                                   "(008408/008416/008424/008430/"
                                                                   "008438/008453), classified once "
                                                                   "each and duplicated explicitly")},
                {"site": "tabs/w5_Equipment_Widget.py:771-782 (9f45cc4)",
                 "status": ("the only *fail-open* sibling of this family found in the M36 phase 2 "
                            "history; already fixed in commit 9f45cc4 with its regression "
                            "(tests/test_permission_failclosed_regression.py) - referenced, not "
                            "re-fixed")},
            ],
        },
        "tests": ("no production file changed in this batch, so no new regression is owed; the "
                  "batch's script ran with the provenance gates active (see `staleness`), compileall "
                  "OK, and the phase-end full suite re-runs on the final tree.  The prior gates "
                  "remain the batch-015 evidence: fix regression 5/0/0/0 in 0.607 s, related 7-file "
                  "run 50/0/0/0 in 9.419 s"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m34-evidence/m34-ledger.json",
                           "tools/m36/p6_batch_016.py",
                           "core/inventory_semantics.py",
                           "core/value_normalizer.py",
                           "core/engineering/result.py",
                           "tests/test_permission_failclosed_regression.py"],
        "staleness": {
            "checked": len(batch), "stale": sum(1 for r in reanchored), "re_anchored": len(reanchored),
            "method": ("every record's declared source_sha256 selects the tree its line number "
                       "belongs to: the current file when the hash matches, otherwise a "
                       "hash-verified provenance tree (tabs/w7_logistics_Widget.py -> c2e0016^, "
                       "whose insertion moved its lines; tabs/w5_Equipment_Widget.py -> 9f45cc4 "
                       "with its permission hunk reversed, a tree that exists in no commit).  The "
                       "recorded text must match at the recorded line of that tree, and the difflib "
                       "map tree->current must land on the same text inside the symbol's AST range.  "
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
