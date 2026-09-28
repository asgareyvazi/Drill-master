#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-006 (45 HIGH records, all class D).

Class-D batch (UI guards, preview helpers, optional conveniences).  Same contract as
p6_batch_005.py: read each site, quote the deciding contract, adjudicate one construct once.
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
BATCH = "p6-batch-006"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

RECHECK_AGAINST: dict[str, str] = {}


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

R: dict[str, tuple[str, str, str | None]] = {
    # ---------------------------------------------------------------- w2 truthiness guards
    "INV34-005351": (INT,
        "`on_section_changed`'s guard means 'no section selected', and the subject's domain is the "
        "Section primary key (positive integers - a legitimate zero cannot occur). The `-1` sentinel "
        "that other flows produce is handled where it is consumed: `load_reports_for_section` "
        "re-guards it explicitly (`if not section_id or section_id == -1: return`, 682), and it is "
        "the only lookup this handler performs with the id (585). Residual (recorded, not a defect "
        "claim): a `-1` delivered through the section_changed signal (no such call site found) would "
        "be stored as the current section and neutralised by that downstream guard.",
        None),
    "INV34-005324": (INT,
        "`auto_calculate_rig_day` branches on truthiness to choose its data source, and both "
        "branches converge on the same documented default when nothing matches: the section path "
        "falls back to `self.rig_day.setValue(1)` (650) exactly like the well path (674). The "
        "subject is a Section PK, so only the `-1` sentinel is outside the test, and it is "
        "re-guarded at the consumption sites (682/1510/1650).", None),
    "INV34-008842": (VC,
        "The guard is complete for this subject: `if not section_id or section_id == -1: return` "
        "(682) covers both the unselected case and the combo's `-1` sentinel before the only DB "
        "call in the method (`get_daily_reports_by_section`), and the method's own docstring marks "
        "the load as optional.", None),
    "INV34-005297": (VC,
        "`services = ... if self.current_well_id else []`: a Well PK tested for truthiness with an "
        "explicit empty-list fallback, inside the suggestion builder. No query is issued for an "
        "absent well and nothing is fabricated.", None),
    "INV34-008294": (VC,
        "`if not well_id or not self.db_manager: return {}` followed by `if not well: return {}` "
        "(1180-1182): an empty snapshot is this method's documented answer for both 'no well "
        "selected' and 'well not found', and every field of the snapshot is read with a defaulted "
        "``.get`` from the real row - no value is invented.", None),
    "INV34-005346": (VC,
        "`if not well_id: show_error(\"DailyReport\", \"Please select a well first\"); return` - a "
        "required-input guard with a user-visible reason before any write; the subject is a Well PK "
        "(positive).", None),
    "INV34-008846": (VC,
        "`if not section_id or section_id == -1: show_error(...\"Please select a section first\"); "
        "return` - the complete guard (absent and `-1` sentinel) with a visible reason, immediately "
        "before the save path.", None),
    "INV34-008847": (VC,
        "`if not section_id or section_id == -1: show_error(...\"Please select a section first\"); "
        "return` inside `create_daily_report_for_current_section` (which is itself gated by "
        "`@require_permission(\"can_edit_reports\")`, 1647) - the complete guard, with the reason "
        "shown, before the report-creation flow.", None),
    "INV34-008305": (VC,
        "`if not well_id or not section_id: self.show_error(\"Well or section not selected\"); "
        "return` - both required ids are checked with a visible reason before the operation.", None),
    "INV34-008302": cosmos(
        "the subject is a *boolean* return, not a number - "
        "`dialog._copy_all_report_data(session, previous_id, created_id)` is a copy operation whose "
        "``False`` is turned into `raise PermissionError(\"Copy denied\")` (1667-1668), i.e. a "
        "fail-closed treatment of a documented success flag; no numeric value is involved."),
    "INV34-008308": cosmos(
        "the subject is a *boolean* return - `copy_data_from_report(self, source, target) -> bool` "
        "(1745) and its ``False`` is answered with an explicit error and `return False` (1995-1997, "
        "'Copy failed; existing target data was not replaced'); no numeric value is involved."),

    # ---------------------------------------------------------------- w2 exception guards
    "INV34-005192": (INT, ROW_PAINT + " Site: completer setup on the contractor editor (893).", None),
    "INV34-005182": (INT, ROW_PAINT + " Site: `_adjust_row_height` (962).", None),
    "INV34-005181": (INT, ROW_PAINT + " Site: `_adjust_all_row_heights` (973).", None),
    "INV34-005188": (INT, ROW_PAINT + " Site: NPT contractor map (983).", None),
    "INV34-005189": (INT, ROW_PAINT + " Site: contractor names from the DB (996); the session is "
                                     "closed in a `finally` (994-995), so the swallow cannot leak "
                                     "it.", None),
    "INV34-005190": (INT, ROW_PAINT + " Site: service companies for the well (1005).", None),
    "INV34-005371": (INT,
        "The guard is narrow (`except (ValueError, TypeError)`) and applies to a QLabel's text; the "
        + TIME_LOG.split("`_extract_time_log_row` reads", 1)[1], None),
    "INV34-005186": (INT, TIME_LOG + " Site: from-time parse (1417).", None),
    "INV34-005187": (INT, TIME_LOG + " Site: to-time parse (1429).", None),

    # ---------------------------------------------------------------- w3
    "INV34-005375": (INT,
        "Matplotlib backend selection at import time: the fallback is an environment concern (the "
        "backend is set to Qt5Agg only when the current one is Agg/empty) and failing to set it "
        "cannot alter any computed or stored value - plotting then runs headless.", None),
    "INV34-005448": (VC,
        "`set_current_report`'s `if not report_id: return` is a primary-key truthiness guard "
        "(positive ids; None means 'no report'). The method is a fan-out that loads the selected "
        "report into each tab, so returning early leaves the tabs as they are rather than loading "
        "anything with an invalid id.", None),
    "INV34-005481": (DUP,
        "Cross-batch duplicate: same construct as p6-batch-005 INV34-008852 / INV34-008876 "
        "(`safe_val`'s `except (ValueError, TypeError): return default` in this very file, line 913 "
        "is the handler line of that helper). Adjudicated there: the default sits inside the "
        "widget's legal entry range and the same function's `safe_opt` carries the documented "
        "'no recorded number -> None' contract for recorded/derived fields (916-917, used at 962). "
        "Counted once.", None),
    "INV34-005484": (DUP,
        "Same line as INV34-005481 (the register fired two rules on one handler) and the same "
        "construct as p6-batch-005 INV34-008852 / INV34-008876. Adjudicated there; counted once.",
        None),
    "INV34-005480": (INT,
        "`nozzles_json` is stored JSON, and the guard is narrow (`except (json.JSONDecodeError, "
        "TypeError)`). The table was just cleared (`self.nozzle_table.setRowCount(0)`, 950), so a "
        "malformed blob leaves an empty nozzle table instead of inventing rows, and the computed "
        "total area is taken from the recorded value through `safe_opt(\"tfa\")` (962 - None when "
        "the report holds no recorded number).", None),

    # ---------------------------------------------------------------- w3b
    "INV34-005485": (INT,
        "Signal wiring at construction time: `self.sel_manager.wellbore_changed.connect(...)` is an "
        "optional hook ('the bore signal is wired here', comment 43). A failure leaves the tab "
        "without that notification, which affects no stored value and no computation; the socket "
        "exists in every delivered build.", None),
    "INV34-008327": (VC,
        "`auto_generate`'s guard checks both required preconditions and says so: `if not "
        "self.current_well_id or not self.db: self.canvas_status.setText(\"No well selected\"); "
        "return` - the subject is a Well PK and the database handle; nothing is generated from an "
        "absent well.", None),

    # ---------------------------------------------------------------- w13
    "INV34-008231": (INT,
        "Interactive volume preview: `_vol_update_quick()` is called from the dimension-control "
        "change handler only when both widgets exist (`hasattr` guards on the line before), and the "
        "display keeps its previous text if the recalculation fails. The canonical computation "
        "itself refuses invalid input loudly elsewhere (the engine raises), so this handler can "
        "only fail on a partial UI state during construction.", None),
    "INV34-010131": (INT,
        "Same shape as INV34-008231 for the annular preview (`_vol_update_annular()`, 5344): an "
        "interactive display refresh whose failure leaves the previous text - no value is written "
        "to the model or the DB by either call.", None),
}

# duplicates of the one-construct-two-rules pairs inside this batch
for _id, _sib, _where in [
    ("INV34-008287", "INV34-005192", f"{W2}:893/894 - rule pair on one handler"),
    ("INV34-008288", "INV34-005182", f"{W2}:962/963 - rule pair on one handler"),
    ("INV34-008289", "INV34-005181", f"{W2}:973/974 - rule pair on one handler"),
    ("INV34-008290", "INV34-005188", f"{W2}:983/984 - rule pair on one handler"),
    ("INV34-008291", "INV34-005189", f"{W2}:996/997 - rule pair on one handler"),
    ("INV34-008292", "INV34-005190", f"{W2}:1005/1006 - rule pair on one handler"),
    ("INV34-008298", "INV34-005371", f"{W2}:1405/1406 - rule pair on one handler"),
    ("INV34-008299", "INV34-005186", f"{W2}:1417/1418 - rule pair on one handler"),
    ("INV34-008300", "INV34-005187", f"{W2}:1429/1430 - rule pair on one handler"),
    ("INV34-008314", "INV34-005375", "tabs/w3_drilling_report.py:72/73 - rule pair on one handler"),
    ("INV34-008316", "INV34-005480", "tabs/w3_drilling_report.py:959/960 - rule pair on one handler"),
    ("INV34-008326", "INV34-005485", "tabs/w3b_wellbore_schematic_tab.py:46/47 - rule pair on one "
                                     "handler"),
    ("INV34-008233", "INV34-008231", "tabs/w13_Engineering_Calculator.py:5338 - second rule on the "
                                     "same handler"),
    ("INV34-008232", "INV34-008231", "tabs/w13_Engineering_Calculator.py:5338/5339 - the `pass` "
                                     "line of INV34-008231's handler"),
    ("INV34-008234", "INV34-008231", "tabs/w13_Engineering_Calculator.py:5338/5339 - the `pass` "
                                     "line of INV34-008231's handler (fourth rule on one construct)"),
    ("INV34-010132", "INV34-010131", "tabs/w13_Engineering_Calculator.py:5344/5345 - the `pass` "
                                     "line of INV34-010131's handler"),
]:
    R[_id] = dup(_sib, _where, "see the adjudication of " + _sib)


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def git_show(rev: str, path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed")
    return out.stdout.decode("utf-8", "replace").splitlines()


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    import ast

    parts = [p for p in (symbol or "").split(".") if p]
    name = parts[-1] if parts else ""
    tree = ast.parse(source)
    candidates = [n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if not candidates:
        raise SystemExit(f"symbol {symbol!r} not found")
    node = min(candidates, key=lambda n: n.lineno)
    return node.lineno, node.end_lineno


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
        "class": ("class D (lower-risk guards/preview conveniences): "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": [],
        "tests": ("no production change in this batch; the full suite was re-run on the 3f0cf3e fix "
                  "(1 831 tests / 0 failures / 0 errors / 4 skipped) and the focused slices before "
                  "it, as recorded in P6_PROGRESS.md"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           f"docs/audits/m36-evidence/{BATCH}.md",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m36-evidence/P6_PROGRESS.md",
                           "tools/m36/p6_batch_006.py"],
        "staleness": {"checked": len(batch), "stale": 0, "re_anchored": len(reanchored),
                      "method": ("every record's recorded text must match the current line exactly; "
                                 "no file in this batch changed since the register was built, so no "
                                 "record needed re-anchoring"),
                      "re_anchored_items": []},
        "method": ("each record read at its own site in the current tree (windows printed and "
                   "traced: for the w2 time-log block through the duration fallback at 1432-1440, "
                   "for the truthiness guards through the selection manager's signal contract and "
                   "the downstream `== -1` re-guards) with the deciding contract quoted in "
                   "`evidence`"),
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
