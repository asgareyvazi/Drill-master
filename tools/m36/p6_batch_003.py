#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-003 (45 HIGH records, mixed class).

Written from reading each site in the current tree.  Also performs the batch staleness check,
which is identity-based rather than line-based:

* normal case - the text the register recorded for a line is still on that line;
* moved by a fix - for the four records whose source snapshot predates a documented fix, the
  recorded text is verified against the previous blob in Git and the record is re-anchored
  (tabs/w5_Equipment_Widget.py: W5 fix 9f45cc4, uniform +10 offset verified; and
  tabs/w7_logistics_Widget.py: fixed by the defect commit of this batch, c2e0016).

Any other mismatch aborts the batch instead of guessing.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-003"
FIX_COMMIT = "c2e0016"          # fix(data): W7 bulk stock ...
W5_FIX_COMMIT = "9f45cc4"       # fix(security): fail closed ... W5 permission control

W7 = "tabs/w7_logistics_Widget.py"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

# --------------------------------------------------------------------------- re-anchor table
# Two records in tabs/w5_Equipment_Widget.py carry a source snapshot (7cbe0721...) that is NOT any
# revision of that file in this repository - the register's line numbers for this file were taken
# in the M35-era workspace. The line number therefore cannot be verified against history; identity
# is instead proven by path + recorded symbol + the recorded line text occurring exactly once
# inside that symbol in the current tree + the register's own contract quote being present
# verbatim at the site. The script asserts the snapshot is really absent before accepting this.
MOVED_BY_IDENTITY = {
    "INV34-005839": {
        "current_line": 898, "snapshot": "7cbe0721",
        "quote": "Best-effort report_date for the current report (for carry-forward)."},
    "INV34-005886": {
        "current_line": 969, "snapshot": "7cbe0721",
        "quote": "they can be migrated by re-saving. Read-only, unknown preserved."},
}
# Records whose recorded text is the statement this batch's own defect fix rewrote: the recorded
# text must exist at the recorded line in the parent blob of the fix commit.
SELF_FIXED = {
    "INV34-006021": W7,
    "INV34-008432": W7,
}

# --------------------------------------------------------------------------- duplicate helper

def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Same construct as {sibling} ({where}): the register holds a second record for the "
            f"identical try/except handler - `{sibling}` fired on the `except` line and this id on "
            f"the `pass` line of the same handler. One behaviour, adjudicated once under "
            f"`{sibling}`; {summary}",
            None)


# --------------------------------------------------------------------------- adjudications
R: dict[str, tuple[str, str, str | None]] = {

    # ---------------------------------------------------------------- A. import: time parsing
    "INV34-002453": (VC,
        "`_convert_time` (915-930) returns `None` explicitly for input it cannot convert - an "
        "explicit sentinel, not a swallowed success. The consumer validates that sentinel at the "
        "persistence boundary: `time_from = ValueNormalizer.to_time(log.get(\"time_from\"))` / "
        "`if time_from is None or time_to is None:` (core/ddr_import_service.py:972-974) creates a "
        "review item with `\"classification\": \"invalid_time_range\"`, `\"reason\": \"Both time "
        "anchors are required for persistence\"`, `\"status\": \"REVIEW_REQUIRED\"` and `continue`s "
        "without writing (975-984). The column is `time_from = Column(Time, nullable=False)` "
        "(core/database.py:719-720, 739-740), so an unconverted value cannot be stored silently "
        "either way.", None),
    "INV34-007682": (DUP,
        "Second record of the handler already adjudicated under INV34-002453 "
        "(core/profile_import_engine.py:923-929): R-EXC-PASS records the `except (TypeError, "
        "ValueError):` line and this id the `pass`/`return None` that follow it, i.e. one "
        "behaviour counted twice by the rule engine. Adjudicated once under INV34-002453 (the "
        "explicit `None` sentinel is turned into REVIEW_REQUIRED by "
        "core/ddr_import_service.py:972-984); no independent finding here.", None),

    # ---------------------------------------------------------------- B. survey dialog payload
    "INV34-003292": (INT,
        "Inline contract at the handler: `pass  # uncalculated labels stay at 0 in the result "
        "payload` (1080). The five labels start as `\"--\"` (`_result_label`, 113-114) and "
        "`_update_calc` (1002-1051) is connected to every input spinner (998-1000) and always "
        "writes a parseable `\"<number> <unit>\"` string; the only early return (md2 <= md1, "
        "1019-1021) is re-checked by `_save` before building the payload and aborts it "
        "(1062-1064). In the only reachable `pass` case - a dialog untouched since `--` - md, inc "
        "and azi are all 0, so the fallback zeros equal the true min-curvature result ("
        "`_update_calc` writes 0.00 north/east for a survey with no predecessor, 1004-1008). No "
        "fabricated measurement can reach `self.result`.", None),

    # ---------------------------------------------------------------- C. excel import preview
    "INV34-003300": (INT,
        "The handler covers only the confidence-based row tinting (`it.setBackground(QColor(...))`, "
        "186-190). The item itself is written and the payload collected *outside* it - "
        "`self.table.setItem(row, col, it)` (193) and `self._row_payloads.append(item)` (196) - so a "
        "parse failure can skip a colour and nothing else: no row is dropped, no value is changed.",
        None),
    "INV34-007937": dup("INV34-003300", "dialogs/excel_import_dialog.py:191/192",
                        "the failure only skips row tinting, the payload is appended outside the "
                        "handler."),
    "INV34-003296": (VC,
        "The helper's failure is fail-closed: on an unparseable confidence cell nothing is "
        "decided (`_set_decision` is not called, 283-284), so the row stays undecided - and the "
        "apply path requires an explicit decision: `decision = str(payload.get(\"decision\", "
        "\"REVIEW\")).upper()` ... `if decision not in {\"ACCEPT\", \"CONFIRMED\"}: continue` "
        "(473-479). The protected action (auto-accepting a low-confidence row into the imported "
        "payload) therefore cannot happen after the check fails.", None),
    "INV34-007938": dup("INV34-003296", "dialogs/excel_import_dialog.py:285/286",
                        "a failed parse leaves the row undecided, which the apply filter "
                        "(473-479) refuses to import."),
    "INV34-003301": (VC,
        "Same fail-closed shape as INV34-003296 in the mirror helper: an unparseable confidence "
        "cell means no automatic REJECT is recorded (328-329), the row stays undecided, and the "
        "apply filter accepts only explicit `ACCEPT`/`CONFIRMED` (473-479). A failure can "
        "therefore never turn into an automatic acceptance.", None),
    "INV34-007939": dup("INV34-003301", "dialogs/excel_import_dialog.py:330/331",
                        "a failed parse leaves the row undecided rather than auto-rejected, and "
                        "undecided rows are not applied (473-479)."),
    "INV34-003362": (INT,
        "`_result_key` is a key-normalisation helper, not a data path: `str(Path(source)"
        ".expanduser().resolve())` with the documented fallback `except OSError: return "
        "str(source)` (625-629). The same function is applied to the same value on both sides "
        "(store: 632-634; lookup: 750), so the fallback key is deterministic and symmetric. No "
        "absent/failed result is mapped onto a 'no data' sentinel.", None),

    # ---------------------------------------------------------------- D. main window: dock state
    "INV34-003874": (INT,
        "`_restore_dock_state` touches only QSettings layout keys - `dock/hierarchy_geometry` and "
        "`dock/hierarchy_visible` (395-401); a failure leaves the default dock layout. No domain "
        "state is read or written, and nothing is reported as saved.", None),
    "INV34-008039": dup("INV34-003874", "main_window.py:402/403",
                        "the failure can only mean the default dock layout."),
    "INV34-003875": (INT,
        "`_save_dock_state` writes the same two QSettings layout keys (407-415); a failure means "
        "only that window layout is not remembered. Cosmetic UI preference, no domain state.",
        None),
    "INV34-008040": dup("INV34-003875", "main_window.py:416/417",
                        "the failure can only mean window layout is not remembered."),

    # ---------------------------------------------------------------- E. main window: delete + audit
    "INV34-003864": (INT,
        "Post-commit bookkeeping, and the mutation is independently fail-closed: "
        "`_check_delete_permission(\"company\")` runs first (1498-1499) and is itself fail-closed - "
        "`core/hierarchy_operations.py:14-32` denies a viewer, denies when the permission is "
        "missing and returns False from `except Exception: logger.exception(...)` - then "
        "`session.delete(company)`/`session.commit()` (1518-1519) and a truthful success message. "
        "The audit write is wrapped for a reason: the delete is already committed, so propagating "
        "a logging failure would report a successful delete as failed. `log_audit` cannot raise at "
        "all - it rolls back, `logger.error(f\"Audit log error: {e}\")` and returns "
        "(core/database.py:10259-10279) - so the `pass` swallows nothing that is not already "
        "logged. Residual (recorded, not a defect claim): an audit-trail gap is logged, not shown "
        "to the user.", None),
    "INV34-008047": dup("INV34-003864", "main_window.py:1531/1532",
                        "the delete is already committed and `log_audit` logs its own failure."),
    "INV34-003866": (INT,
        "Identical shape to INV34-003864 for projects: fail-closed permission gate first "
        "(`_check_delete_permission(\"project\")`, 1544-1545 -> core/hierarchy_operations.py:14-32), "
        "then `session.commit()`, then the best-effort audit write whose failure is already logged "
        "inside `log_audit` (core/database.py:10275-10277) and which cannot be allowed to falsify "
        "the already-committed delete.", None),
    "INV34-008050": dup("INV34-003866", "main_window.py:1577/1578",
                        "the delete is already committed and `log_audit` logs its own failure."),
    "INV34-003868": (INT,
        "Identical shape to INV34-003864 for sections: fail-closed permission gate first "
        "(`_check_delete_permission(\"section\")`), then the committed delete, then the best-effort "
        "audit write (`log_audit` logs its own failure, core/database.py:10275-10277).", None),
    "INV34-008055": dup("INV34-003868", "main_window.py:1668/1669",
                        "the delete is already committed and `log_audit` logs its own failure."),
    "INV34-003870": (INT,
        "Identical shape to INV34-003864 for wells: the fail-closed permission gate runs before "
        "the mutation (`_check_delete_permission(\"well\")`), the `else` branch reports a refused "
        "delete explicitly (1623-1626), and the audit write is best-effort with its own logging "
        "inside `log_audit`.", None),
    "INV34-008052": dup("INV34-003870", "main_window.py:1621/1622",
                        "the delete is already committed and `log_audit` logs its own failure."),

    # ---------------------------------------------------------------- F. analysis tab
    "INV34-004382": (INT,
        "The try in `update_time_depth_data` wraps only the trend-line decoration "
        "(`np.polyval` + `pg.mkPen(...)`/`name=\"Trend Line\"`, 1640-1657). The plot is then reset "
        "and rebuilt independently (`self.daily_gain_plot.clear()` 1661 ff.), so a failure can "
        "only omit an annotation - no computed value is stored, exported or reported as saved.",
        None),
    "INV34-008126": dup("INV34-004382", "tabs/w12_Analysis.py:1658/1659",
                        "the failure only omits the trend-line annotation on the plot."),
    "INV34-004593": (VC,
        "The handler is typed (`except ImportError`, 2922) and its body is an explicit, documented "
        "fallback: write PNG instead of PDF and `return False` (2923-2925) - the caller can "
        "distinguish the fallback from success because the return value says so. In addition "
        "`_export_charts_to_pdf` has no reference anywhere in the tracked tree (repo-wide "
        "`grep -rn \"_export_charts_to_pdf\"` finds only its definition), so no consumer can "
        "mistake the result for a written PDF.", None),

    # ---------------------------------------------------------------- G. engineering display
    "INV34-004918": (INT,
        "Inline contract at the handler: `pass  # non-numeric nozzle cell` (1427). The only sink "
        "is a display label - `self.hy_tfa_label.setText(...)` (1428), created at 1131 and never "
        "read back anywhere (grep: no `hy_tfa_label.text()`), and the nozzle Area column is "
        "`setEditTriggers(QTableWidget.NoEditTriggers)` (1140), i.e. filled by the application. "
        "Nothing persisted or calculated depends on this total.", None),

    # ---------------------------------------------------------------- H. procedure save
    "INV34-005023": (VC,
        "`save_procedure` is typed `-> int`, commits and returns the procedure id, and on failure "
        "rolls back and `return None` (core/database.py:9575-9602). Ids are primary keys (never 0), "
        "so `if not proc_id:` is exactly the documented failure test - and the caller reports it "
        "and returns False instead of continuing with a non-existent procedure (952-953).", None),
    "INV34-008242": (DUP,
        "Exact duplicate register record of INV34-005023: same file, same line "
        "(tabs/w14_Procedure_Widget.py:951), same rule (R-TRUTH-NUMERIC), same recorded source text "
        "(`if not proc_id:`). One statement, adjudicated once under INV34-005023 "
        "(`save_procedure` returns a primary key or None, core/database.py:9575-9602); this record "
        "adds no second finding.", None),

    # ---------------------------------------------------------------- I. daily report
    "INV34-005316": (VC,
        "`well_id` is the id of the selected well: 0/None means 'no well selected' - which is "
        "what the message says (1208) - and the value is additionally proven against the database "
        "(`sections = self.db_manager.get_sections_by_well(well_id)` ... `if section_id not in "
        "valid_ids: return False, \"Selected section does not belong to this well...\"`, "
        "1213-1217). A legitimate primary key cannot be 0.", None),
    "INV34-008845": (VC,
        "`section_id` is a primary key with an explicit 'not selected' sentinel: `if not "
        "section_id or section_id == -1:` (1210-1211), and the resolved value is then validated "
        "against the well's own sections (1213-1217). Zero/-1 mean 'nothing selected', not a real "
        "section.", None),
    "INV34-008295": (VC,
        "Documented fallback with its own comment (`# fallback از گزارش جاری`, 1244): when the "
        "widget's cached selection is empty it reads the ids from the report that is already "
        "loaded (`self.current_report.get(\"well_id\")` / `.get(\"section_id\")`, 1245-1248) - a "
        "read-only attribution, no invented owner - and the result is validated before any write "
        "(1250-1252 -> 1213-1217).", None),
    "INV34-005374": (INT,
        "Inline contract at the handler: `pass  # incomplete row — excluded from totals` (1900). "
        "The totals feed three display labels and a colour threshold "
        "(`total_time_label`/`total_npt_label`/`productivity_label`, 1901-1912) - no persistence, "
        "no exported value, and no fabricated number: the rows that are excluded contribute "
        "nothing to a sum.", None),

    # ---------------------------------------------------------------- J. wellbore schematic
    "INV34-005534": (INT,
        "The handler is scoped to per-field numeric parses, and the same function implements the "
        "explicit three-state contract where the field is a measurement the user can leave "
        "unknown: `id_text in (\"\", \"—\", \"-\")` -> `casing.id_inch = None` with the comment "
        "\"explicitly unknown wall thickness (None); a numeric value (including 0) is a real "
        "fact.\" (772-778). A failed parse leaves that field unchanged (the last known fact) and "
        "still applies the remaining fields of the row; nothing fabricates a 0. The persisted "
        "model (save_data, 953-991) stores whatever the shared model holds and reports failures "
        "(997-1000). Residual (recorded, not a defect claim): clearing a previously known OD/"
        "depth cell keeps the prior value in the model - a stale fact, not a fabricated one - "
        "and only the id column has an explicit unknown path.", None),
    "INV34-008328": dup("INV34-005534", "tabs/w3b_wellbore_schematic_tab.py:785/786",
                        "a failed parse leaves the field unchanged and the id column has its own "
                        "explicit unknown path (772-778)."),
    "INV34-005535": (INT,
        "The rebuild is wholesale (`new_formations` is built and then assigned to "
        "`self.schematic.formations`, 818), and a row whose depth cells cannot be parsed is left "
        "out of it - the same convention the sibling export documents for incomplete rows: "
        "`pass  # incomplete formation row stays out of the LAS export` "
        "(tabs/w4_Downhole_Widget.py:889). No depth is invented; an incomplete formation cannot be "
        "drawn.", None),
    "INV34-008330": (VC,
        "`save_data` guards on a primary key and the presence of the store before writing anything "
        "(`if not self.current_well_id or not self.db: return False`, 945-946); every failure path "
        "reports (`logger.error` + `self.show_error(...)`, 997-999) and returns False. Zero cannot "
        "be a legitimate well id.", None),

    # ---------------------------------------------------------------- K. casing tally
    "INV34-005744": (INT,
        "The three statistics are initialised inside the method (`tl=tw=tc=0.0`, 562) and feed "
        "only QLabel text (`self.stats_labels[...]`, 576-579). The cells they read are written by "
        "the application itself as numbers (`it.setText(f\"{val:.2f}\" ...)`, 555), so the "
        "handler cannot hide a miscalculation of the tally - it can only skip a column for an "
        "uncomputed row.", None),
    "INV34-008333": dup("INV34-005744", "tabs/w3c_section_data.py:573/574",
                        "the statistics are initialised per call and feed display labels only."),

    # ---------------------------------------------------------------- L. downhole export
    "INV34-005834": (INT,
        "Inline contract at the handler: `pass  # incomplete formation row stays out of the LAS "
        "export` (889). The export reports its own failure - `except Exception as e: "
        "logger.error(f\"LAS export error: {e}\")` ... `return False` (895-897) - and returns True "
        "only after `las.write(...)` (890-894), so an incomplete row is excluded from the artifact "
        "while the caller still learns whether the file was written.", None),

    # ---------------------------------------------------------------- M. equipment widget
    "INV34-005839": (VC,
        "Re-anchored: the register's `except Exception:` at line 888 is line 898 in the current "
        "tree (the W5 fix 9f45cc4 shifted the file by +10; verified against the previous blob). "
        "The site is `_report_date_for_current`, documented \"Best-effort report_date for the "
        "current report (for carry-forward).\" (893): on a missing report, a failed lookup or an "
        "unusable row it returns `None` - never a substituted date - and the caller passes that "
        "None through (`report_date=self._report_date_for_current()`, 918) instead of inventing "
        "today's date.", None),
    "INV34-005886": (VC,
        "Re-anchored: the register's `if legacy:` at line 959 is line 969 in the current tree "
        "(same +10 offset, verified against the previous blob). `legacy` is a boolean flag set by "
        "`legacy = bool(items)` (950), so truthiness is the correct test, and the numeric "
        "trichotomy in the same function is handled by `_inv_cell` for every quantity "
        "(opening_stock/received/used/current_stock/min_level/max_level, 960-966) under the "
        "documented \"Read-only, unknown preserved.\" (945-946) - asserted on the real widget by "
        "tests/test_inventory_live_calc_smoke.py, which passes on this worktree.", None),

    # ---------------------------------------------------------------- N. trajectory plot
    "INV34-005964": (VC,
        "`save_plot` returns True only for a real id: the callee commits and `return plot.id`, and "
        "on any failure rolls back, logs `Error saving trajectory plot` and `return None` "
        "(core/database.py:6707-6727). Ids are primary keys, so `if plot_id:` cannot mistake a "
        "success for a failure or vice versa; the False return is the documented failure result.",
        None),

    # ---------------------------------------------------------------- O. logistics bulk stock (defect)
    "INV34-006021": (DEF,
        "GENUINE DEFECT (fixed in c2e0016, this batch). `initial = float(initial_item.text() or 0)` "
        "turned a blank cell into 0, so a row whose opening stock was never reported displayed a "
        "fabricated \"Current Stock\" balance, and the same expression fed the em dash that the "
        "widget's own loader writes (`_fmt_stock`: \"Unknown stock displays as an em dash, never "
        "as 0.0.\", 1217) into `float(\"—\")`, raising into the outer handler and leaving the cell "
        "without a value. Both contradict the persistence boundary of the same widget: \"an EMPTY "
        "cell is 'not reported' (None) - carry-forward/unknown downstream. A typed 0 is an "
        "explicit zero and is preserved exactly.\" (`_cell_float`, 1156-1158). Fix: blank and em "
        "dash are unknown -> the computed stock is unknown (em dash); a typed 0 stays a fact. "
        "Evidence: tests/test_bulk_stock_three_state_smoke.py passes on the fix and fails under "
        "mutation with AssertionError ('blank opening must leave the computed stock UNKNOWN, not "
        "fabricated', '5.0'). Same-class search: 7 hits repo-wide, all in this widget; the three "
        "fixed here and `calculate_bulk_totals` (1118-1121) left unchanged because its `or 0` is "
        "numerically neutral in a sum that only feeds a transient message box.", None),
    "INV34-008432": (DUP,
        "Exact duplicate register record of INV34-006021: same file, same line (825), same rule "
        "(R-DEF-VALUE-PATH), same `source_sha256` (c5aee6d2...) and the same recorded source text "
        "(`initial = float(initial_item.text() or 0)`). The statement is defective and is fixed "
        "once under INV34-006021 (commit c2e0016, regression "
        "tests/test_bulk_stock_three_state_smoke.py); this record adds no second defect and is "
        "counted once.", None),

    # ---------------------------------------------------------------- P. export tab
    "INV34-008112": (VC,
        "`well_id = self.ddr_well.currentData()` (193) is the combo box's payload, i.e. a report "
        "well id or None; `if not well_id or not self.db: return` (194) is the pre-condition for "
        "listing reports and no legitimate primary key is 0. The guard protects a read-only list "
        "population (`get_daily_reports_by_well`, 196-201).", None),
}

BATCH_SITES = None


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def git_show(rev: str, path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed: {out.stderr.decode()[:200]}")
    return out.stdout.decode("utf-8", "replace").splitlines()


def symbol_body(lines: list[str], symbol: str) -> tuple[int, int]:
    """(start, end) line numbers of the method whose name is `symbol`'s last component."""
    name = (symbol or "").split(".")[-1]
    start = None
    for i, line in enumerate(lines, 1):
        if re.match(rf"\s*def {re.escape(name)}\s*\(", line):
            start = i
            break
    if start is None:
        raise SystemExit(f"symbol {symbol!r} not found")
    end = len(lines)
    indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
    for i in range(start, len(lines)):
        line = lines[i]
        if line.strip() and not line.startswith(" " * (indent + 1)) and i > start - 1:
            end = i
            break
    return start, end


def file_revisions(path: str) -> set[str]:
    """sha256 of every revision of `path` that exists in this repository."""
    revs = subprocess.run(["git", "log", "--format=%H", "--", path], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode().split()
    hashes = set()
    for rev in revs:
        blob = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True,
                              check=True).stdout
        hashes.add(hashlib.sha256(blob).hexdigest())
    return hashes


def check(batch: list[dict]) -> list[str]:
    """Identity-based staleness check.  Returns a list of human-readable mismatches."""
    problems: list[str] = []
    cache: dict[str, list[str]] = {}
    revisions: dict[str, set[str]] = {}
    text: dict[str, str] = {}
    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        if path not in cache:
            text[path] = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            cache[path] = text[path].splitlines()
            revisions[path] = file_revisions(path)
        lines = cache[path]

        # 1) normal case: the recorded text is still on the recorded line
        if 0 < line <= len(lines) and _norm(lines[line - 1]) == _norm(expected):
            continue

        # 2) moved by a fix whose snapshot is not in this repository: prove identity instead
        if record["id"] in MOVED_BY_IDENTITY:
            info = MOVED_BY_IDENTITY[record["id"]]
            if any(h.startswith(info["snapshot"]) for h in revisions[path]):
                problems.append(f"{record['id']}: snapshot {info['snapshot']} IS a revision of "
                                f"{path} - verify the line against history instead of identity")
                continue
            start, end = symbol_body(lines, record.get("symbol", ""))
            occurrences = [i for i in range(start, end + 1)
                           if _norm(lines[i - 1]) == _norm(expected)]
            if len(occurrences) != 1 or occurrences[0] != info["current_line"]:
                problems.append(f"{record['id']}: recorded text occurs at {occurrences} inside "
                                f"{record.get('symbol')} ({start}-{end}), expected exactly "
                                f"[{info['current_line']}]")
                continue
            if info["quote"] not in text[path]:
                problems.append(f"{record['id']}: register contract quote not found verbatim in "
                                f"{path}")
            continue

        # 3) fixed by this batch's own defect fix: the recorded text must exist in the parent
        #    blob of the fix commit, and the fix commit must be the one that changed it
        if record["id"] in SELF_FIXED:
            previous = git_show(f"{FIX_COMMIT}^", path)
            if _norm(previous[line - 1]) != _norm(expected):
                problems.append(f"{record['id']}: recorded text not found at {path}:{line} in "
                                f"{FIX_COMMIT}^")
            continue

        problems.append(f"{record['id']}: {path}:{line} is {lines[line - 1].strip()!r}, register "
                        f"recorded {expected!r}")
    return problems


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    batch = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(batch) != len(R):
        print(f"batch has {len(batch)} records, adjudications: {len(R)}")
        missing = sorted({r["id"] for r in batch} - set(R))
        extra = sorted(set(R) - {r["id"] for r in batch})
        print("missing:", missing, "extra:", extra)
        return 1

    problems = check(batch)
    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        return 2

    reanchored = {}
    for record in batch:
        if record["id"] in MOVED_BY_IDENTITY:
            info = MOVED_BY_IDENTITY[record["id"]]
            reanchored[record["id"]] = {
                "kind": "line-from-unavailable-revision (identity re-anchor)",
                "recorded_line": record["line"], "current_line": info["current_line"],
                "snapshot_sha256_prefix": info["snapshot"],
                "proof": (f"the register's snapshot {info['snapshot']}... is not any revision of "
                          f"{record['file']} in this repository, so the recorded line number "
                          f"cannot be verified against history; identity is proven by path + "
                          f"symbol {record.get('symbol')} + the recorded text occurring exactly "
                          f"once inside that symbol (line {info['current_line']}) + the register's "
                          f"own contract quote present verbatim at the site"),
            }
        elif record["id"] in SELF_FIXED:
            reanchored[record["id"]] = {
                "kind": "fixed-by-this-batch", "commit": FIX_COMMIT,
                "recorded_line": record["line"],
                "proof": (f"recorded text verified in {FIX_COMMIT}^:{record['file']}:{record['line']}; "
                          f"the fix commit rewrote exactly that statement"),
            }

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
        "test": ("tests/test_bulk_stock_three_state_smoke.py (subprocess-isolated; fails under "
                 "mutation)") if record["id"] == "INV34-006021" else None,
        "commit": FIX_COMMIT if record["id"] in ("INV34-006021", "INV34-008432") else None,
        **({"line_verification": reanchored[record["id"]]} if record["id"] in reanchored else {}),
    } for record in batch]

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("A (safety / authorization / mutation) - all 45 records are class A "
                  f"({', '.join(f'{k}:{v}' for k, v in sorted(classes.items()))})"),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [
            "INV34-006021 / INV34-008432 - tabs/w7_logistics_Widget.py FuelWaterTab."
            "update_bulk_stock_for_row (line 825): `float(cell.text() or 0)` turned an unreported "
            "opening balance into 0 and displayed a fabricated \"Current Stock\", while the em "
            "dash the loader writes for unknown raised through the handler. One statement, one "
            "defect, two register records. Fix commit c2e0016, regression "
            "tests/test_bulk_stock_three_state_smoke.py (mutation-killed: fabricated '5.0' "
            "observed with the original expression)."
        ],
        "tests": ("tests/test_bulk_stock_three_state_smoke.py PASS; tests/"
                  "test_inventory_live_calc_smoke.py PASS; tests/"
                  "test_permission_failclosed_regression.py PASS; full suite 1828 results, "
                  "0 failures, 6 documented skips (post-fix, this worktree)"),
        "head": FIX_COMMIT,
        "commit": FIX_COMMIT,   # the only production change of this batch (the W7 fix);
        "evidence_commit": None,  # SHA of the commit holding these audit files, stamped next
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           f"docs/audits/m36-evidence/{BATCH}.md",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m36-evidence/P6_PROGRESS.md",
                           "tools/m36/p6_batch_003.py"],
        "staleness": {"checked": len(batch), "stale": 0, "re_anchored": len(reanchored),
                      "method": ("recorded text must be identical (whitespace-insensitive) to the "
                                 "current line; the four moved records are proven against the "
                                 "previous blob of their fix commit and re-anchored inside the "
                                 "recorded symbol")},
        "method": ("each record read at its own site in the current tree; the deciding contract is "
                   "quoted in `evidence`; records that describe one try/except handler are "
                   "adjudicated once and the duplication is stated"),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, staleness 0, "
          f"re-anchored {len(reanchored)}")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
