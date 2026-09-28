#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-009 (45 HIGH records, all class E).

Class-E batch: the tab-level truthiness guards (primary keys / feature flags), the optional
plotting preludes and the history-dialog formatters.  Same contract as p6_batch_005..008: read
each site, quote the deciding contract, adjudicate one construct once.  No defect, no
production change.

Two tooling facts this batch had to establish (both recorded in the batch evidence):
  * the register's line numbers for tabs/w7_logistics_Widget.py predate the batch-003 fix
    c2e0016, so those anchors are re-anchored through the difflib map against c2e0016^;
  * symbol_body() is now owner-aware - the previous last-path-component lookup could resolve
    a class-qualified symbol to a same-named method of an unrelated class.
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
BATCH = "p6-batch-009"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

RECHECK_AGAINST: dict[str, str] = {"tabs/w7_logistics_Widget.py": "c2e0016"}


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


W2 = "tabs/w2_Daily_Report.py"
ROW_PAINT = ("Row-height/completer/suggestion maintenance around the daily-report table. The guard "
             "wraps purely visual work whose failure mode is 'the convenience did not apply', "
             "never a wrong number: the row keeps its default height, the completer stays unset and "
             "the suggestion list simply lacks an entry (the method then adds its static fallbacks "
             "and returns the sorted set - `contractors.update([...])`, `return sorted(list("
             "contractors))`).")
TIME_LOG = ("`_extract_time_log_row` reads a table row into a time-log record and every swallow is "
            "compensated by the code that follows it: the duration cell is re-derived from the "
            "from/to times right after ('compute duration if it was zero', 1432-1440), and the "
            "widgets' own `get_time()` contract defines midnight as this module's encoding of "
            "'24:00' (`if is_2400: from_python_time = time(0, 0)`, 1413-1416). The `hasattr` guard "
            "on the line before each try means a non-TimeLineEdit cell never reaches the parse.")

NEW_FINDINGS: list[dict] = []

_STAT = ("A *statistic* on the sheet analysis, not a decision input: the value is assigned a safe "
         "default before the try (`hidden_rows = 0` / `has_merged = False`, 160-162, 222), computed "
         "inside it, and only ever written into the analysis dataclass (`has_merged=has_merged`, "
         "386). Nothing branches on it (the field is declared with the same default at 44 and has "
         "no other reader - verified by grep), so a failure cannot change what is imported; it only "
         "leaves the reported statistic at its default.")
_HEURISTIC = ("Column-type inference: a cell that does not parse as a number is simply not added to "
              "the numeric *sample* (`numeric.append(...)` inside the try), and the type decision "
              "afterwards is a ratio test with an explicit floor "
              "(`if numeric and len(numeric) >= max(1, len(values) * 0.6)`, 543). Excluding an "
              "unparseable cell is the correct behaviour for a 'is this column numeric?' heuristic - "
              "the alternative would be inventing a number for it.")
_VALIDATOR = ("Inside a validator whose whole purpose is to *report* problems, and the guarded "
              "block only adds a comparison-based message (warning/error) that cannot be evaluated "
              "without parseable operands. The parse failures that matter are reported by the "
              "numeric loops immediately above (e.g. 'Depth must be numeric', 135-136; 'Length must "
              "be numeric', 320-321), so the swallow cannot hide an unreported problem - it avoids a "
              "*second*, misleading message for a value that is already flagged. Residual (recorded, "
              "not a defect claim): for the fields whose only check is the comparison "
              "(dls/od/id/date ordering/overdue dates) a non-numeric value produces no message at "
              "all; the engine boundary still refuses such values loudly when they are computed with "
              "(e.g. `optional_number` raises for non-numeric geometry), so no wrong result is "
              "produced.")
_FORMATTER = ("A *display* formatter: it renders the number when it parses "
              "(`f\"{float(value):,.{digits}f}{suffix}\"`) and otherwise returns the value's own "
              "string form (`return str(value)`) - it can never invent a number, and the raw text "
              "stays visible in the table/export.")
_TIME_KEEP = ("Legacy text is parsed back into the dialog's spin boxes and on failure the widgets "
              "keep their current (default) contents - the same 'keep widget defaults' contract "
              "stated in the sibling branch's comment ('prev_time absent or not HH:MM - keep widget "
              "defaults', 152). No time is invented for a malformed legacy value.")

NEW_FINDINGS: list[dict] = []

_NO_WELL = ("`well_id = self.current_well_id` is a Well primary key (the queries below compare "
            "`well_id == well_id`), so its falsy value means exactly 'no well selected': the guard "
            "returns the method's documented empty shape before any query runs - no query with an "
            "invalid id and no fabricated KPI. The file states the same no-fabrication contract for "
            "the values it would otherwise produce ('unknown source data yields None, never 0.0', "
            "1297-1301) and the renderer keeps it end-to-end ('Unknown values render as \"—\" (via "
            "fmt_num default=None), never 0.', 2066-2072).")
_NO_WELL_SHORT = ("Same construct as INV34-004519 in this file (a Well primary key tested for "
                  "truthiness before the query; falsy means 'no well selected'), with the method's "
                  "own documented empty return.")
_MPL = ("Module-level optional plotting backend: `matplotlib.use('Qt5Agg')` is attempted only when "
        "the already-installed backend is non-interactive/empty (`_current_backend.lower() in "
        "('agg', '')`), and the module then imports `pyplot` and degrades explicitly through "
        "`MATPLOTLIB_QT_OK`/`PYQTGRAPH_AVAILABLE` (33-43 in this file). A failure here means the "
        "backend selection did not apply - a rendering choice - while chart availability is "
        "reported by the explicit flags, not by this swallow.")
_OPENGL = ("`pg.setConfigOptions(useOpenGL=True)` is a rendering-performance option; the handler "
           "carries the module's own annotation ('# OpenGL اختیاری است' = OpenGL is optional, w12:55) "
           "and pyqtgraph stays importable either way. A miss means the charts fall back to the "
           "software renderer, which cannot change any value shown.")
for _unused in ():
    pass

R: dict[str, tuple[str, str, str | None]] = {
    # ------------------------------------------------------------ history-dialog formatters
    "INV34-003846": dup("INV34-003153", "dialogs/torque_drag_history_dialog.py:52-55 - the same "
                                        "`_fmt` display helper (float when parseable, `str(value)` "
                                        "otherwise) as the family adjudicated in p6-batch-008",
                        "a display formatter can neither invent nor hide a number"),
    "INV34-003857": dup("INV34-003153", "dialogs/well_control_kill_sheet_history_dialog.py:55-58 - "
                                        "the identical `_fmt` helper",
                        "a display formatter can neither invent nor hide a number"),

    # ------------------------------------------------------------ main_window.py
    "INV34-003883": (INT,
        "`center_window` is pure window geometry: the swallow can only leave the window at its "
        "default position. The QApplication/screen objects it touches carry no domain value, and "
        "nothing downstream reads the window's position.", None),
    "INV34-008041": dup("INV34-003883", "main_window.py:715/716 - the `pass` line of "
                                        "INV34-003883's handler", "window placement only"),
    "INV34-004044": (INT,
        "Qt worker teardown: `RuntimeError` is the documented error for touching a C++ object that "
        "has already been destroyed (the normal race when a finished worker is cleaned up), so the "
        "swallow implements 'the worker is already gone - nothing to stop'. The generic handler on "
        "the next lines still logs anything else at debug level (1200-1201), and the reference is "
        "cleared in `finally` (1202-1203) so no stale worker is kept.", None),
    "INV34-008044": dup("INV34-004044", "main_window.py:1198/1199 - the `pass` line of "
                                        "INV34-004044's handler", "already-destroyed Qt worker"),
    "INV34-004042": dup("INV34-004044", "main_window.py:3054-3057 - the identical teardown guard in "
                                        "`_cleanup_hierarchy_worker` (same try/except RuntimeError "
                                        "-> pass, then debug-logging generic handler at 3059-3060)",
                        "already-destroyed Qt worker"),
    "INV34-008079": dup("INV34-004044", "main_window.py:3057/3058 - the `pass` line of "
                                        "INV34-004042's handler", "already-destroyed Qt worker"),

    # ------------------------------------------------------------ tabs/home_tab.py
    "INV34-004079": (INT,
        "`darken_color` is a theme helper: it returns a darkened hex string for a colour token and "
        "the input unchanged when the token is not parseable (e.g. a named colour). The value is "
        "presentation only - no measurement, no persistence - and the fallback keeps the caller's "
        "own token instead of inventing a colour. Residual (recorded, cosmetic): a string that "
        "passes `lstrip` but fails hex parsing is returned without the leading '#' (the local "
        "rebinding happened before the failure) - a theme token, never data.", None),

    # ------------------------------------------------------------ matplotlib / pyqtgraph preludes
    "INV34-004080": (INT, _MPL + " Site: the W10 prelude (32-38).", None),
    "INV34-008083": dup("INV34-004080", "tabs/w10_Planning_Widget.py:37/38 - the `pass` line of "
                                        "INV34-004080's handler", "backend selection is a rendering "
                                        "choice"),
    "INV34-004362": dup("INV34-004080", "tabs/w12_Analysis.py:24-30 - the identical backend-selection "
                                        "prelude in W12", "same prelude, same rendering-only scope"),
    "INV34-008115": dup("INV34-004080", "tabs/w12_Analysis.py:29/30 - the `pass` line of "
                                        "INV34-004362's handler", "rendering choice only"),
    "INV34-004363": (INT, _OPENGL + " Site: the module-level pyqtgraph configuration (52-55).", None),
    "INV34-004364": dup("INV34-004363", "tabs/w12_Analysis.py:138-141 - the same optional-OpenGL "
                                        "guard repeated in the widget's own pyqtgraph configuration",
                        "rendering option; software rendering falls back"),
    "INV34-008116": dup("INV34-004363", "tabs/w12_Analysis.py:140/141 - the `pass` line of "
                                        "INV34-004364's handler", "rendering option only"),

    # ------------------------------------------------------------ W12 wiring and truthiness
    "INV34-004365": (INT,
        "The file documents this connection as deliberate - 'A wellbore selection must re-scope "
        "analytics. DrillTabBase wires well/section/report but not the bore signal, so - exactly "
        "like the W3b schematic tab - W12 consumes it directly (smallest, lowest-risk change...)' "
        "(167-170) - and the signal exists with the same name and signature on the manager "
        "(`wellbore_changed = Signal(int, object)`, core/selection_manager.py:43). The guard is "
        "therefore defensive only: in a correct build the connect cannot fail, and if it ever did, "
        "the symptom would be a stale analytics view (the tab's own reload paths and the "
        "well/section/report signals remain), not a wrong number or a write.", None),
    "INV34-008117": dup("INV34-004365", "tabs/w12_Analysis.py:173/174 - the `pass` line of "
                                        "INV34-004365's handler",
                        "defensive guard around a documented, existing signal"),
    "INV34-004553": cosmos(
        "`PYQTGRAPH_AVAILABLE` is a module-level bool set by the import guard (48/57) - a feature "
        "flag, not a numeric quantity; the guard selects the placeholder-message branch of the "
        "tab's UI (179-186)."),
    "INV34-004519": (VC, _NO_WELL + " Site: the overview/KPI method (1304-1307), which returns "
                                    "`dict.fromkeys([...], None)` - every KPI explicitly unknown, "
                                    "which is exactly what the renderer expects (2066-2072).", None),
    "INV34-004552": (VC, _NO_WELL + " Site: `get_today_data` (1369-1370) returns `None`, and its "
                                    "only consumer guards the same way before fetching "
                                    "(`update_daily_data`: `if not self.current_well_id: return`, "
                                    "2059) and treats `None` as 'leave the indicators as they are' "
                                    "(`if today:`, 2065-2066).", None),
    "INV34-004551": (VC,
        "`report = candidates[0] if len(candidates) == 1 else None` (1382) then `if not report:` "
        "(1383): the falsy subject is the absence of a *single unambiguous* report for the selected "
        "date - the `limit(2)` probe exists to detect a duplicate report date and the file's stated "
        "rule is 'Ambiguity -> UNKNOWN, not a guess' (1396). Returning None here leaves the "
        "indicators untouched instead of displaying one arbitrary day.", None),
    "INV34-004542": dup("INV34-004519", "tabs/w12_Analysis.py:1437-1438 - the same no-well pre-query guard in "
                                        "`get_performance_data`",
                        _NO_WELL_SHORT + " The method returns `[]`."),
    "INV34-004543": dup("INV34-004519", "tabs/w12_Analysis.py:1466 - the same no-well pre-query guard in "
                                        "`get_time_depth_data`",
                        _NO_WELL_SHORT + " The method returns `[]`."),
    "INV34-004539": dup("INV34-004519", "tabs/w12_Analysis.py:1500-1503 - the same no-well pre-query guard in "
                                        "`get_npt_data`",
                        _NO_WELL_SHORT + " The method returns the empty-NPT dict with `None` "
                        "totals (`total_npt`, `npt_percentage`, `total_hours`)."),
    "INV34-004514": (VC,
        "`if not well_id: self.results_text.setText(\"No well selected\"); return` (2190-2193): the "
        "guard is the analysis button's pre-condition, and its action is an explicit user-visible "
        "message instead of a query - the Well primary key's falsy value is reported to the "
        "operator, not silently ignored. The same contract is repeated by the sibling analysis "
        "handlers (2271-2273, 2393-2396).", None),
    "INV34-008132": dup("INV34-004514", "tabs/w12_Analysis.py:2191 - the second rule on the same "
                                        "handler", "'No well selected' is shown and the analysis "
                                        "returns"),
    "INV34-004512": dup("INV34-004514", "tabs/w12_Analysis.py:2271-2273 - the identical guard in the "
                                        "cost-analysis handler",
                        "same user-visible 'No well selected' pre-condition"),
    "INV34-008133": dup("INV34-004514", "tabs/w12_Analysis.py:2272 - the second rule on that "
                                        "handler", "same construct"),
    "INV34-004515": dup("INV34-004514", "tabs/w12_Analysis.py:2393-2396 - the identical guard in the "
                                        "risk-assessment handler", "same construct"),
    "INV34-008136": dup("INV34-004514", "tabs/w12_Analysis.py:2394 - the second rule on that "
                                        "handler", "same construct"),

    # ------------------------------------------------------------ tabs/w10_Planning_Widget.py
    "INV34-004272": (VC, _NO_WELL + " Site: `get_npt_data` (436-438), which returns "
                                    "`{'entries': [], 'categories': {}, 'total_npt': None, "
                                    "'npt_percentage': None, 'total_hours': None}`.", None),

    # ------------------------------------------------------------ tabs/w14_Procedure_Widget.py
    "INV34-005047": (VC,
        "`proc_id = item.data(Qt.UserRole)` (251) then `if proc_id:` (252): the value is the "
        "procedure's primary key, stored on the list item when it was built "
        "(`item.setData(Qt.UserRole, proc['id'])`, 246). A falsy value means the item carries no "
        "procedure (nothing to load), so rejecting it is correct - and when it is set, the guard "
        "proceeds to load exactly that procedure.", None),

    # ------------------------------------------------------------ tabs/w6_Trajectory_Widget.py
    "INV34-005984": (VC,
        "`set_current_well(well_id: int, section_id: int = None)` stores the id and then loads only "
        "when one is set (`if well_id: self.load_data()`): the falsy value is 'no well selected', "
        "and the table is documented to stay empty in that state ('Operational tables start empty; "
        "data comes from the selected report.', 92). No query runs with an invalid id.", None),
    "INV34-005956": dup("INV34-005984", "tabs/w6_Trajectory_Widget.py:343-346 - the identical "
                                        "`set_current_well` guard of the second trajectory tab "
                                        "(same docstring comment on the line above)",
                        "same 'no well selected -> stay empty' contract"),
    "INV34-005961": cosmos(
        "`PYQTGRAPH_AVAILABLE` is the module-level bool set by the import guard - a feature flag; "
        "the branch replaces the plot widget with a placeholder label (522-527)."),
    "INV34-005962": (VC,
        "`load_for_report(report_id: int)` stores the id and loads plots only when one is set "
        "(`if report_id: self.load_plots()`): a report primary key's falsy value means 'no report "
        "selected', and the plotting path must not run against it.", None),
    "INV34-005957": (VC,
        "`calc_id = self.db_manager.save_trajectory_calculation(calculation_data)`, then "
        "`if calc_id: return calc_id` / `return None` (700-704): the function's contract is the "
        "saved row's primary key or None (nothing saved / no database manager). A falsy return from "
        "the save cannot be reported as a successful save, so the guard is the correct "
        "success/failure test - the caller receives None rather than a fabricated id.", None),

    # ------------------------------------------------------------ tabs/w7_logistics_Widget.py
    "INV34-006198": (VC, _NO_WELL + " Site: `PersonnelLogisticsTab.set_current_well` (563-565), "
                                    "which loads POB/crew tables only when a well is set.", None),
    "INV34-006143": dup("INV34-006198", "tabs/w7_logistics_Widget.py:1263-1269 - the identical "
                                        "`set_current_well` guard of `FuelWaterTab` (loads the "
                                        "fuel/water and bulk-material tables)", _NO_WELL_SHORT),
    "INV34-006205": dup("INV34-006198", "tabs/w7_logistics_Widget.py:1739-1744 - the identical "
                                        "`set_current_well` guard of `TransportLogTab` (loads the "
                                        "transport log)", _NO_WELL_SHORT),
    "INV34-006212": (INT,
        "`load_fuel_water_from_db` defines two readers side by side: `_val(key, default=0.0)` "
        "returns the caller's default for an absent or non-numeric value (the same documented "
        "loader contract as `safe_float` in core/text_utils.py and `sv` in the w3/w3c dialogs), "
        "while `_stock(key)` states the domain rule 'Preserve NULL as UNKNOWN; only real numbers "
        "become values.' (1021) and returns None on the same failure (1027-1028) - which "
        "`_set_stock_value` renders as the unknown mark (597-602) and which the day's save path "
        "reads back as 'not reported'. So the swallow at `_val`'s typed except cannot hide a "
        "failure: the three states (value / explicit zero / unknown) are decided by the caller's "
        "explicit default and by `_stock`, and the fuel/water remainder arithmetic below uses only "
        "real values (1043-1044). Register anchor 999 predates the batch-003 fix c2e0016; the "
        "construct now sits at 1017 (verified by the re-anchor map).", None),
    "INV34-008442": dup("INV34-006212", "tabs/w7_logistics_Widget.py:999/1017 - the second register "
                                        "record on the same `_val` handler",
                        "the default/unknown split is carried by `_val` vs `_stock`"),

    # ------------------------------------------------------------ tabs/w9_Services_Widget.py
    "INV34-006361": (VC,
        "`if not self.note_id:` (537) distinguishes the *new note* path (compute the next note "
        "number for the well: `max(note_number) + 1`, else 1, 538-543) from the *edit existing* "
        "path (load the note with that id, 545-555). The note id is a primary key, so a falsy value "
        "means 'no stored note', and the branch's whole purpose is to prevent editing an unselected "
        "note - exactly the documented behaviour of the dialog.", None),
    "INV34-006343": (VC,
        "`load_equipment_data` returns immediately when no equipment is selected "
        "(`if not self.equipment_id: return`, 647-648); the value is the equipment log's primary "
        "key, and the method's next step is to find the row with `e.get('id') == self.equipment_id` "
        "(650) - running that lookup with a falsy/absent id could match an unrelated row, so the "
        "guard is required rather than merely defensive.", None),
}
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

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("class E (tab-level truthiness guards, optional plotting preludes, dialog "
                  "formatters): " + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "tests": ("no production change in this batch; the full suite evidence recorded in "
                  "P6_PROGRESS.md (1 831 tests / 0 failures / 0 errors / 4 skipped on the 3f0cf3e "
                  "tree) stands for this batch too - the only production files this session has "
                  "written are core/engineering/well_control_kill_sheet.py, core/mud_ledger.py "
                  "and tabs/w7_logistics_Widget.py, none of which this batch edits"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           f"docs/audits/m36-evidence/{BATCH}.md",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m36-evidence/P6_PROGRESS.md",
                           "tools/m36/p6_batch_009.py"],
        "staleness": {"checked": len(batch), "stale": 0, "re_anchored": len(reanchored),
                      "method": ("every record's recorded text must match the current line exactly; "
                                 "where it does not, the recorded text must match c2e0016^ at that "
                                 "line (the pre-fix revision of tabs/w7_logistics_Widget.py, whose "
                                 "line numbers the register carries) and the difflib map against "
                                 "c2e0016 must land on the same text inside the symbol's AST range - "
                                 "otherwise the batch refuses to apply"),
                      "re_anchored_items": [
                          {"id": i, "file": p, "register_line": a, "current_line": b}
                          for i, p, a, b in reanchored]},
        "method": ("each record read at its own site in the current tree with its fallback traced "
                   "to the consumer (the sheet statistics through their only reader at "
                   "universal_import.py:386, the validator guards through the numeric-field loops "
                   "that report the same values, the code-map guards through the map keys' types), "
                   "and the deciding contract quoted in `evidence`"),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, staleness 0, "
          f"re-anchored {len(reanchored)}, defects fixed 0")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
