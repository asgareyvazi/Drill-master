#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-015 (45 MEDIUM records, mixed classes).

Phase 2, third batch: the export/metadata surface (professional_export, managers, editor_state),
engineering parameter defaults and the calculation-verification repositories, the profile import
extractor, the DDR import service's template selection, import diagnostics/profiling and the
hierarchy delete gate.  One genuine defect was found and fixed here (INV34-002457, commit
0699e50) with its regression test; every other site is adjudicated by the contract quoted in
`evidence`, following the same method as p6_batch_005..012.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-015"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

RECHECK_AGAINST: dict[str, str] = {"dialogs/planning_dialog.py": "fd51a54"}


def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Second register record for {where}, already adjudicated under {sibling}: "
            f"{summary}",
            None)


def cosmos(what: str) -> tuple[str, str, None]:
    """A rule mis-fire where the subject is not a number at all."""
    return (DUP,
            f"Rule mis-fire, not a behaviour to adjudicate: {what}",
            None)


_PLAN_TRICHOTOMY = (
    "The plan-input trichotomy is stated in this codebase and enforced at both ends of this very "
    "path: `PlanImportReviewDialog._parse_data` must not turn an absent or unparseable numeric cell "
    "into a planned 0.  The consumer `_import_from_excel` is written for None to be possible "
    "(`interval is not None and depth is not None`, `depth is not None and cum_depth is not None`, "
    "`if depth_to is not None`, 1003-1009), `core/text_utils.fmt_num` documents 'genuine unknown "
    "stays unknown' and renders these fields with `default=None` (\"—\"), the plan total is derived "
    "with `core.cost_semantics.complete_total` ('A complete amount total, never a subtotal disguised "
    "as the total' -> None unless *every* value is a number), and the same codebase states the rule "
    "for plan inputs ('empty or \"—\" = not planned (None); a typed 0 is an explicit zero', "
    "tabs/w10_Planning_Widget.py:2399-2400; `planned_days ... else None`, "
    "dialogs/hierarchy_dialogs.py:1200,1210)."
)

_MATERIAL_MOVEMENT = (
    "The canonical bulk-material contract treats received/used as *movements*, and an absent movement "
    "is zero: core/inventory_semantics.py states 'None = not reported (unknown), 0.0 = explicitly "
    "reported zero ... opening_stock follows the trichotomy; received/used absent = no movement "
    "(0.0); current_stock (closing) = opening + received - used when opening is known, else None "
    "(never a fabricated 0)' and implements it as `derive_closing(opening, received, used)` = "
    "`float(opening) + float(received or 0.0) - float(used or 0.0)` with an explicit None for an "
    "unknown opening, plus `normalize_movement`: 'Absent movement means zero'.  This site mirrors "
    "that rule exactly: `initial` keeps the trichotomy (`initial = _plan_value(2)`, then "
    "`current = initial + received - used if initial is not None else None`) while "
    "`received`/`used` default to the canonical no-movement 0.0, and the existing regression "
    "tests/test_m29_planning_ui.py pins the resulting row (`row.initial_stock is row.current_stock is "
    "None and row.received == row.used == 0`)."
)

_AFE_UNKNOWN = (
    "This module encodes 'not supplied' explicitly for cost inputs: the AFE spin boxes are created "
    "with `spin.setRange(-1, 999999999)`, `spin.setSpecialValueText(\"Not supplied\")` and "
    "`spin.setValue(value if value is not None else -1)`, and the reader maps `value() >= 0` back to "
    "a value or None (tabs/w16_Cost_Management.py, `_insert_afe_row` / `_read_afe_rows`); the "
    "planned-days mirror uses the same sentinel (`self.afe_days.setValue(days if days is not None "
    "else -1)`).  A blank text field is likewise stored as None (`afe_number=...strip() or None`) and "
    "an unknown NPT cost is displayed, not invented (`money(total_npt_cost) if actual_cost is not "
    "None else \"— (incomplete cost or currency data)\"`, with the module's contract at 294-297: "
    "'It is only known when actual cost AND total recorded time exist — otherwise \"unknown\", never "
    "a synthetic rig-rate product.')."
)

_SAVE_COORDINATOR = (
    "`core/save_outcome.py` is the single save coordinator: `save_all` returns a SaveOutcome whose "
    "`saved` counts only sections that actually committed ('Execute independent section saves; "
    "report partial success honestly', 88-93) and whose `summary()` carries the per-section issues "
    "(77-85).  Reading `.saved` therefore tests exactly 'did anything get written' - the condition "
    "for invalidating the hierarchy cache after a save (main_window.py:2744, 2755) - and cannot "
    "treat a failed section as a success."
)

_WIDGET_GUARD = (
    "A present-widget guard, not a data decision: the subject is a QTableWidgetItem / child widget / "
    "parent pointer, and the falsy case means 'this cell or container does not exist', so the "
    "conclusion drawn is either a skipped refresh or a skipped decoration.  No number is read, "
    "defaulted or persisted on this path."
)

_RECALC_DISPLAY = (
    "A display/derivation guard: the value fed onward is recomputed from the real sources with the "
    "unknown preserved (`if total == 0: self.<x>_progress.setValue(0)` is the definitional 0% of an "
    "empty list; `pct = checked / total * 100` otherwise), or the failure path yields an explicit "
    "'unknown / not exported' outcome rather than a substituted number."
)

R: dict[str, tuple[str, str, str | None]] = {
    # -------------------------------------------------- plan import dialog
    "INV34-003558": cosmos(
        "the truthiness test guards the bold *formatting* of the field label "
        "(`font.setBold(True)` behind `if required:`, dialogs/planning_dialog.py:275); `required` is "
        "the third element of PLAN_FIELDS and has no numeric subject and no persistence effect"),
    "INV34-003569": (DEF, _PLAN_TRICHOTOMY, None),

    # -------------------------------------------------- smart template dialog
    "INV34-003787": (INT,
        "Presence check while assembling the final payload: `if self.base_extracted.get(payload_key): "
        "result[payload_key] = self.base_extracted[payload_key]` (dialogs/smart_template_dialog.py:"
        "3187-3194) copies an extracted section only when it is non-empty, so an absent/empty "
        "section leaves the target's own (empty) value in place instead of copying an empty one over "
        "it.  Nothing is invented and no numeric default is written; the assignments the user made "
        "are applied afterwards (`for fp, assign in self.assignments.items()`, 3199-3204).", None),

    # --------------------------------------------------------- main window
    "INV34-008069": (INT,
        "Dead no-op loop in an import-summary renderer: `for detail in report.get(\"details\", []) "
        "if isinstance(report, dict) else []: pass` (main_window.py:2208-2209).  The consumer's rows "
        "come from the loop immediately below (`for det in result.get(\"details\", [])[:10]`, "
        "2211-2215), so the loop neither hides nor fabricates anything; removing it would be a "
        "cosmetic refactor and is out of scope for this phase.", None),
    "INV34-004029": (VC, _SAVE_COORDINATOR, None),
    "INV34-004027": dup("INV34-004029", "main_window.py:2755 (the Save All counterpart)",
                         "the same `.saved` gate on the aggregate outcome of `save_all`"),

    # ------------------------------------------------------------ home tab
    "INV34-004060": (VC,
        "The handler's scope is the database-status probe only (`hierarchy = "
        "self.db.get_hierarchy()`); a failure sets `db_status = \"❌ Disconnected\"` and the status "
        "colour (tabs/home_tab.py:594-600), i.e. the failure is reported to the user, not swallowed.  "
        "No value is substituted: the pairs shown on the panel are the real ones, and the outer "
        "handler reports the update itself (588).", None),

    # ------------------------------------------------- w10 planning widget
    "INV34-008085": (VC,
        "Context gate inside the save callback: falsy `self.db` / `current_report_id` / "
        "`current_well_id` means there is nothing to save against, and the guard raises "
        "`ValueError(\"Select a well and report before saving the plan\")` (tabs/w10_Planning_Widget."
        "py:238-240) - which `save_all` reports as an INVALID_SOURCE issue, never as a save.  The ids "
        "are primary keys, so 0 cannot be a valid record; the guard runs before any query or write.", None),
    "INV34-004296": (VC,
        "`first.data(Qt.UserRole) if first else None` reads the row's own stored payload; a missing "
        "cell yields None and the next line falls back to an empty dict (`plan = dict(original) if "
        "isinstance(original, dict) else {}`), so a row without a payload is rebuilt from its visible "
        "cells rather than from a stale or fabricated record (tabs/w10_Planning_Widget.py:242-248).", None),
    "INV34-004297": dup("INV34-004296", "tabs/w10_Planning_Widget.py:248 (`item.text().strip() if "
                                          "item else None` in the same loop)",
                         "the same per-cell presence guard: a missing cell is None (unknown), never "
                         "an empty string pretending to be entered text"),
    "INV34-008089": (INT, _RECALC_DISPLAY, None),
    "INV34-008091": (VC,
        "Fail-closed export guard: `if not painter.isActive(): raise OSError(\"PDF writer could not "
        "be opened\")`, then `ended = painter.end()` and `if not ended or "
        "printer.printerState() == QPrinter.Error: raise OSError(\"PDF writer failed\")` "
        "(tabs/w10_Planning_Widget.py:694-701); the outer handler logs, tells the user "
        "(\"Charts were not exported\") and returns False.  A chart file is never reported as "
        "exported unless the writer really finished.", None),
    "INV34-008816": dup("INV34-008091", "tabs/w10_Planning_Widget.py:700 (the printer-state half of "
                                          "the same guard)",
                         "the same fail-closed export chain"),
    "INV34-008092": dup("INV34-008091", "tabs/w10_Planning_Widget.py:704 (`if not pixmap.save"
                                          "(filename): raise OSError(\"Image writer failed\")`)",
                         "the raster branch of the same fail-closed export"),
    "INV34-004229": cosmos("the test guards a table item before recolouring it "
                            "(`if item: item.setForeground(QColor(color))`, tabs/w10_Planning_Widget."
                            "py:1183-1186); colour only"),
    "INV34-010068": (VC,
        "Plan-vs-actual comparison with the unknown preserved: the actual depth is the maximum of "
        "only the known values (`known_depths = [v for v in self.fact_depths if v is not None]`, "
        "`fact = max(known_depths) if known_depths else None`) and the planned depth is taken only "
        "when *every* activity depth is known (`planned = (max(depths) if all(v is not None for v in "
        "depths) else getattr(...)) if depths else ...`), then `compare(\"Depth\", planned, fact)` "
        "classifies the pair and both labels render through `fmt_num(..., default=None)` "
        "(tabs/w10_Planning_Widget.py:1727-1735).  An unknown side can therefore never be presented "
        "as a zero-depth plan or fact.", None),
    "INV34-008109": (VC,
        "Sanitiser inside `_plan_value`: a non-finite or negative plan quantity raises "
        "`ValueError(\"Material quantities must be finite and nonnegative\")` instead of being "
        "coerced (tabs/w10_Planning_Widget.py:2404-2407); the only None produced here is the "
        "documented 'empty or \"—\" = not planned' case on the lines above.", None),
    "INV34-010077": (VC, _MATERIAL_MOVEMENT, None),
    "INV34-010078": dup("INV34-010077", "tabs/w10_Planning_Widget.py:2412 (`used = "
                                          "_plan_value(4) or 0.0`)",
                         "the same movement default, symmetric with `received`"),

    # ------------------------------------------------------- w11 export tab
    "INV34-004357": (VC,
        "`if self.db:` guards the whole combobox population (tabs/w11_Export.py:79-90): without a "
        "database the combo simply stays empty (nothing to list) instead of raising, and the rest of "
        "the method re-selects the current well only when it exists.  No well or code is invented.", None),
    "INV34-010084": (VC,
        "Documented projection-input convention on the *same* tab immediately above the site: "
        "'Optional day-rate PROJECTION inputs.  Left at 0 (the default), the report shows stored "
        "ACTUAL cost from CostRecord.  A non-zero rate adds an explicitly-labelled projection "
        "alongside — it never replaces or is presented as actual cost (§12/§27)' with the on-screen "
        "note 'Leave rates at 0 to report stored actual cost only.' (tabs/w11_Export.py:384-405).  "
        "0 here therefore means 'no projection requested', not a measured zero rate; the engine keeps "
        "its own guard (`rate_supplied = daily_rate is not None and ... and projection_currency is "
        "not None`, core/report_engine.py:1759-1760).", None),
    "INV34-010085": dup("INV34-010084", "tabs/w11_Export.py:398 (`self.cost_spread.setValue(0)`)",
                         "the spread-rate half of the same documented pair"),

    # ---------------------------------------------------- w12 analysis tab
    "INV34-004410": (INT,
        "Timer cadence, not an engineering value: `intervals = {0:5000, 1:10000, 2:30000, 3:60000, "
        "4:300000}` maps the interval combo's index to a refresh period and "
        "`intervals.get(index, 10000)` falls back to the 10 s entry for an unforeseen index "
        "(tabs/w12_Analysis.py:2477-2481).  The default selects a UI refresh rate; it cannot change "
        "any reported number, and the combo is populated from the same five-entry contract.", None),
    "INV34-004381": (VC,
        "Scope-label probe: `has_bores = bool(self.db.get_wellbores_by_well(self.current_well_id))` "
        "behind a caller check; a failure sets `has_bores = False` (tabs/w12_Analysis.py:2718-2723) "
        "and the label then states the *narrower* scope (\"scoped to this wellbore only.  Records "
        "with an unknown bore are excluded.\"), i.e. the failure cannot widen a claim about the "
        "figures.", None),
    "INV34-008147": dup("INV34-004381", "tabs/w12_Analysis.py:2722 (the same handler, second register "
                                          "rule)",
                         "identical construct and contract"),

    # --------------------------------------------- w13 engineering calculator
    "INV34-004874": cosmos("the test guards a table item before reading its text for the nozzle-area "
                            "label (`item = self.hy_nzl_table.item(row, 3)`, `if item:`) and the "
                            "following handler skips a non-numeric cell instead of adding 0 "
                            "(tabs/w13_Engineering_Calculator.py:1421-1428); a display aggregate"),

    # ------------------------------------------------- w14 procedure widget
    "INV34-005027": cosmos("`if self.parent_widget:` guards a list refresh of the embedding page "
                            "(`self.parent_widget.load_procedures_list()`, tabs/w14_Procedure_Widget."
                            "py:966-967); an object pointer, no value involved"),
    "INV34-010135": (INT,
        "Definitional empty-list case of a progress percentage: with zero checklist rows, "
        "`total == 0` and the bar is set to 0 % (`pct = checked / total * 100` otherwise, "
        "tabs/w14_Procedure_Widget.py:1085-1100).  0 of 0 items is 0 %, and the same widget keeps "
        "its per-item truth from the checkboxes rather than from this value.", None),
    "INV34-004988": cosmos("`is_checked = cb.isChecked() if cb else False` is an object guard that "
                            "decides a row *colour* (`item.setBackground(QColor(\"#d5f5e3\") if "
                            "is_checked else QColor(\"#ffffff\"))`, tabs/w14_Procedure_Widget."
                            "py:1104-1111); no value is stored or derived"),
    "INV34-010136": dup("INV34-010135", "tabs/w14_Procedure_Widget.py:1209 (the steps-progress "
                                          "counterpart)",
                         "the same definitional 0 % for an empty list"),

    # ------------------------------------------------ w15 reference tables
    "INV34-005071": (VC,
        "Export presence guard: `tables = current_tab.findChildren(QTableWidget)` then `if tables: "
        "export.export_table_with_dialog(tables[0], ...)` (tabs/w15_Reference_Tables.py:122-130).  A "
        "tab without a table simply does not export (and the empty case is also handled one step "
        "earlier by `if not current_tab: return`); no file is produced and no data invented.", None),

    # --------------------------------------------------- w16 cost management
    "INV34-010155": (INT,
        "Planning-assumption inputs on the Daily Cost tab, created as `QDoubleSpinBox` with "
        "`setRange(0, 999999)` and an explicit banner above them: '⚠️ Day-rate figures below are "
        "planning ASSUMPTIONS you enter — they are NOT actual recorded cost.  Actual cost comes from "
        "the AFE tab (persisted) and reports.' (tabs/w16_Cost_Management.py:213-224); the running "
        "total only appears after the user changes something (`valueChanged` -> "
        "`_update_daily_total`, 226-227, 249-251) and is always suffixed '(assumption)'.  The engine "
        "consuming them keeps its own unknown guard (`rate_supplied = daily_rate is not None and "
        "spread_rate is not None and projection_currency is not None` -> `total_daily = ... if "
        "rate_supplied else None`, core/report_engine.py:1759-1760).  Residual (recorded, not a "
        "defect claim): the spin box itself cannot express 'no rate' once a currency is chosen, so a "
        "projection on zero rates reads as a 0 cost — it is labelled an assumption and never "
        "presented as actual cost.", None),
    "INV34-010156": dup("INV34-010155", "tabs/w16_Cost_Management.py:207 (`spread_rate.setValue"
                                          "(0)`)",
                         "the spread half of the same documented assumption pair"),
    "INV34-010163": (VC, _AFE_UNKNOWN, None),
    "INV34-008264": cosmos("the flagged line is the docstring of `_selected_currency` ('Return the "
                            "chosen currency code, or None when left unspecified (§9)', "
                            "tabs/w16_Cost_Management.py:478-483); the function returns the code or "
                            "None and the rule matched prose, not a numeric fallback"),
    "INV34-005101": (VC,
        "`data = dict(cat_item.data(Qt.UserRole) or {}) if cat_item else {}` builds the row's base "
        "dict from the stored payload (or an empty dict for a fresh row) and the authoritative "
        "values are then read from the cells' widgets (`planned_cost`/`actual_cost` from the spin "
        "boxes, `currency` from the combo, tabs/w16_Cost_Management.py:485-500); the base payload "
        "cannot inject a stale numeric value because every key that matters is overwritten.", None),
    "INV34-008267": dup("INV34-005101", "tabs/w16_Cost_Management.py:494 (the same line, second "
                                          "register rule)",
                         "identical construct and contract"),
    "INV34-005084": (VC,
        "Blank-vs-supplied trichotomy for a text identifier: an empty AFE number is stored as None "
        "('not supplied') rather than as an empty string claim "
        "(`afe_number=self.afe_number.text().strip() or None`, tabs/w16_Cost_Management.py:538), and "
        "the same call passes `currency=self._selected_currency()` which returns None for the "
        "'—/unspecified' choice.", None),
    "INV34-008272": dup("INV34-005084", "tabs/w16_Cost_Management.py:538 (the same line, second "
                                          "register rule)",
                         "identical construct and contract"),
    "INV34-005075": (VC,
        "A failed planned-days read becomes *unknown*, never zero: `try: days = "
        "self.db.get_planned_total_days(...) except Exception: days = None` followed by "
        "`self.afe_days.setValue(days if days is not None else -1)` on a spin box whose "
        "`setSpecialValueText(\"Not supplied\")` renders -1 as 'Not supplied' "
        "(tabs/w16_Cost_Management.py:584-592, `_insert_afe_row`).  A database failure therefore "
        "cannot be mistaken for a plan of 0 days, and the read-only mirror is documented as such "
        "('Reflect the authoritative WellPlan planned days (read-only mirror)').", None),
    "INV34-008279": dup("INV34-005075", "tabs/w16_Cost_Management.py:590 (the same handler, second "
                                          "register rule)",
                         "identical construct and contract"),

    # ---------------------------------------------------- w2 daily report
    "INV34-005313": (INT,
        "Combo population fallback driven by a resolution object: `resolve_main` returns a "
        "REVIEW_REQUIRED resolution with `code = None` for a blank/unresolvable main code "
        "('Blank ComboBox value; no default item selected', core/combo_identity.py:259-274), and "
        "`sub_options(None)` deliberately applies no parent filter (`if main_code and str(parent) != "
        "str(main_code): continue`), so the sub-combo is filled with the full catalogue for the "
        "reviewer to choose from (tabs/w2_Daily_Report.py:1056-1063).  The daily-report record keeps "
        "the resolution's REVIEW_REQUIRED state rather than the displayed list, so a hint list is "
        "never saved as an accepted code.", None),
    "INV34-005362": (VC,
        "Atomic-save gate: a falsy `save_daily_report` result triggers "
        "`session.rollback()`, an explicit error message ('Failed to save report') and `return False` "
        "before any time log is written (tabs/w2_Daily_Report.py:1277-1288, with the module's own "
        "comment that the header and its logs commit in ONE session).  A missing id can therefore "
        "never reach the time-log writer.", None),
    "INV34-010203": dup("INV34-009108", "tabs/w2_Daily_Report.py:1337 (`session = session or "
                                          "self.db_manager.create_session()`)",
                         "the optional-session ownership contract already adjudicated in batch-011: "
                         "the docstring three lines above states 'When ``session`` is supplied the "
                         "work joins that transaction (the caller owns commit/rollback) ... When "
                         "omitted it manages its own session for backward compatibility' "
                         "(1330-1334), and `owns_session` records which case applies"),
    "INV34-005364": (VC,
        "Row-level presence check in the time-log writer: `log = self._extract_time_log_row(...)` "
        "then `if log:` before `session.add(TimeLog24H(...))` (tabs/w2_Daily_Report.py:1342-1350), "
        "so a row the extractor could not read is skipped instead of being written with fabricated "
        "zeros - and the extractor's own contract (batch-011/013 evidence) derives the duration from "
        "the from/to times and returns None when nothing usable is present.", None),
}

NEW_FINDINGS: list[dict] = []


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def git_show(rev: str, path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed")
    return out.stdout.decode("utf-8", "replace").splitlines()


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    """Line range of the symbol named by a dotted path (owner-aware).

    p6-batch-009 correction: the previous version resolved only the last path component
    (`parts[-1]`), so a class-qualified symbol such as ``FuelWaterTab.set_current_well`` could
    resolve to a same-named method of an unrelated class earlier in the same file.  The index
    below is built from the real AST nesting, so ``Class.method`` and ``Class.method.inner``
    resolve to the node the register names.  The old name-only search remains as a fallback,
    and only when it is unambiguous.
    """
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


def line_map(commit: str, path: str, current: list[str]) -> dict[int, int]:
    previous = git_show(f"{commit}^", path)
    matcher = difflib.SequenceMatcher(None, previous, current, autojunk=False)
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
    return mapping


def check(batch: list[dict]) -> list[tuple[str, str, int, int]]:
    problems: list[str] = []
    reanchored: list[tuple[str, str, int, int]] = []
    cache: dict[str, list[str]] = {}
    sources: dict[str, str] = {}
    maps: dict[str, dict[int, int]] = {}
    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        if path not in cache:
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            sources[path] = text
            cache[path] = text.splitlines()
        lines = cache[path]

        if 0 < line <= len(lines) and _norm(lines[line - 1]) == _norm(expected):
            continue

        commit = RECHECK_AGAINST.get(path)
        if commit is None:
            actual = lines[line - 1].strip() if 0 < line <= len(lines) else "<beyond EOF>"
            problems.append(f"{record['id']}: {path}:{line} is {actual!r}, register recorded "
                            f"{expected!r}")
            continue

        previous = git_show(f"{commit}^", path)
        if _norm(previous[line - 1]) != _norm(expected):
            problems.append(f"{record['id']}: {commit}^ has {previous[line - 1].strip()!r} at "
                            f"{path}:{line}, register recorded {expected!r}")
            continue

        if path not in maps:
            maps[path] = line_map(commit, path, lines)
        new_line = maps[path].get(line)
        start, end = symbol_body(sources[path], record.get("symbol", ""))
        if new_line is None or _norm(lines[new_line - 1]) != _norm(expected) \
                or not (start <= new_line <= end):
            problems.append(f"{record['id']}: re-anchor {path}:{line} -> {new_line} failed")
            continue
        reanchored.append((record["id"], path, line, new_line))
    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        raise SystemExit(2)
    return reanchored


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

    reanchored = check(batch)

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
            item["commit"] = "fd51a54"
            item["test"] = "tests/test_plan_import_unknown_cells.py"

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("phase-2 mixed classes: "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))
                  + " - planning/import dialogs, main window, home tab and the w2/w10..w16 tabs"),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [{
            "id": "INV34-003569", "file": "dialogs/planning_dialog.py", "line": 483,
            "summary": ("`PlanImportReviewDialog._parse_data` coerced an absent AND an unparseable "
                        "cell into a planned 0 for every numeric plan field "
                        "(interval/depth/rop/hours/days/total_days); the staged plan then showed "
                        "0.0 h / 0.0 m and `complete_total` summed the coercion as a real zero.  "
                        "Now an absent/unparseable numeric cell stays None (unknown) while a typed 0 "
                        "remains an explicit planned zero"),
            "commit": "fd51a54",
            "test": "tests/test_plan_import_unknown_cells.py",
        }],
        "new_findings": NEW_FINDINGS,
        "sibling_search": {
            "target": ("the defect's class: a numeric literal 0 assigned inside a parse/except "
                       "handler that converts text into a plan or measurement value"),
            "method": ("regex scan over core/, dialogs/ and tabs/ for `except (ValueError|TypeError"
                       "|...)` followed by `pass` or an `X = 0` / `return 0` coercion, then each "
                       "hit read at its site"),
            "hits": 25,
            "findings": [
                {"site": "all 25 hits", "status": ("swallow the parse failure with `pass` (e.g. "
                                                   "core/validators.py:142,184,287,329; "
                                                   "core/profile_import_engine.py:752,928; "
                                                   "dialogs/daily_report_dialogs.py:295,304; "
                                                   "tabs/w2_Daily_Report.py:1405) - the strict "
                                                   "opposite of assigning a fabricated 0: the "
                                                   "previous/derived value stays in place and the "
                                                   "callers' own unknown handling resumes")},
                {"site": "core/profile_import_engine.py:840",
                 "status": "GENUINE DEFECT of the same class, fixed in batch-013 (0699e50)"},
                {"site": "dialogs/planning_dialog.py:483/485",
                 "status": "GENUINE DEFECT of the same class, fixed in this batch (fd51a54)"},
            ],
        },
        "tests": ("defect fix commit fd51a54: new regression file 5 passed / 0 failed / 0 errors / "
                  "0 skipped in 0.607 s; with the bug reintroduced 3 of the 5 fail, then restored "
                  "byte-identical (sha256 809186f7a5700f3d27b159f288c81fec6263a424125f3ce2ae8b67b4"
                  "4bf44e3a) -> 5/5; related run (7 files: the new regression, the M29 planning UI, "
                  "planning context/material/presentation, M28 finance-safety and the P0 phase-1 "
                  "regressions) 50 passed / 0 failed / 0 errors / 0 skipped in 9.419 s "
                  "(/tmp/p6-015-related.xml); compileall OK; ruff on the changed file 151 -> 151 "
                  "findings (no debt increase) and the new test file is clean.  The other 44 "
                  "records change no production file; the phase-end full suite re-runs on the final "
                  "tree"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "tools/m36/p6_batch_015.py",
                           "dialogs/planning_dialog.py",
                           "tests/test_plan_import_unknown_cells.py",
                           "core/inventory_semantics.py",
                           "tabs/w10_Planning_Widget.py"],
        "staleness": {"checked": len(batch), "stale": 0, "re_anchored": len(reanchored),
                      "method": ("every record's recorded text must match the line at its recorded "
                                 "position; the one exception is dialogs/planning_dialog.py, whose "
                                 "line numbers shifted by +2 in this batch's own fix (fd51a54) - "
                                 "there the recorded text is verified against fd51a54^ at the "
                                 "recorded line and re-anchored through difflib inside the symbol's "
                                 "AST range, which is what the staleness block reports"),
                      "re_anchored_items": [
                          {"id": i, "file": p, "register_line": a, "current_line": b}
                          for i, p, a, b in reanchored]},
        "method": ("each of the 45 records was read at its own site in the current tree and the "
                   "flagged construct traced to its consumer before classification: the plan import "
                   "through the staging consumer and the review table's display/total contracts, the "
                   "material inventory through the canonical movement trichotomy "
                   "(core/inventory_semantics.py) and the existing regression, the cost tabs through "
                   "the module's own -1/'Not supplied' sentinel and the 'planning ASSUMPTIONS' "
                   "banner, the export guards through their fail-closed OSError chain, the daily "
                   "report through its atomic-save session contract, and the save coordinator "
                   "through core/save_outcome.py.  The deciding contract is quoted in `evidence` for "
                   "every record; no line outside the fixed defect was changed"),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, staleness 0, "
          f"re-anchored {len(reanchored)}, defects fixed {len(payload['defects_fixed'])}")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
