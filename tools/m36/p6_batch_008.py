#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-008 (45 HIGH records, all class E).

Class-E batch: import statistics/heuristics, the validators' comparison guards and the dialog
formatters/legacy parsers.  Same contract as p6_batch_005/006/007: read each site, quote the
deciding contract, adjudicate one construct once.  No defect and no production change.
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
BATCH = "p6-batch-008"

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

R: dict[str, tuple[str, str, str | None]] = {
    # ------------------------------------------------------------ core/universal_import.py
    "INV34-002893": (INT, _STAT + " Site: hidden row/column counts (163).", None),
    "INV34-007854": dup("INV34-002893", "core/universal_import.py:163/164 - the `pass` line of "
                                        "INV34-002893's handler",
                        "sheet statistics only; no import decision reads them"),
    "INV34-002894": (INT, _STAT + " Site: `has_merged` (225).", None),
    "INV34-007855": dup("INV34-002894", "core/universal_import.py:225/226 - the `pass` line of "
                                        "INV34-002894's handler",
                        "`has_merged` is written into the analysis result and never branched on"),
    "INV34-002933": cosmos(
        "the subject is a *list*, not a number: `return [band[0]] if band else []` (408) is the "
        "empty-collection guard of a short band, which is the correct way to avoid an IndexError; "
        "no numeric value is tested."),
    "INV34-002963": (INT, _HEURISTIC + " Site: building the numeric sample (537-539).", None),
    "INV34-007857": dup("INV34-002963", "core/universal_import.py:538/539 - the `pass` line of "
                                        "INV34-002963's handler",
                        "non-numeric cells are excluded from the numeric sample by design"),
    "INV34-002947": cosmos(
        "the subject is a *list*: `min_val = min(numeric) if numeric else None` (545) is the "
        "empty-list guard that avoids `min()`'s ValueError, and the enclosing branch already "
        "established that the list is non-empty statistically - the ternary keeps the value None "
        "when there is nothing to measure."),
    "INV34-002948": dup("INV34-002947", "core/universal_import.py:546 - the same empty-list guard "
                                        "for `max()`", "same construct, one line below"),

    # ------------------------------------------------------------ core/validators.py
    "INV34-003004": (VC, _VALIDATOR + " Site: the depth@00:00 / depth@24:00 ordering warning, whose "
                                      "operands were already validated at 129-136.", None),
    "INV34-003009": dup("INV34-003004", "core/validators.py:142 - the second rule on the same "
                                        "handler", "the depth operands are already reported"),
    "INV34-007863": dup("INV34-003004", "core/validators.py:142/143 - the `pass` line of "
                                        "INV34-003004's handler",
                        "the depth ordering warning is best-effort on already-validated operands"),
    "INV34-002998": (INT, _VALIDATOR + " Site: the DLS warning in the survey loop (283-288). DLS is "
                                       "optional there (`if dls not in (None, \"\")`) and the block's "
                                       "only action is a >15 deg/30m warning.", None),
    "INV34-003012": dup("INV34-002998", "core/validators.py:287 - the second rule on the same "
                                        "handler", "DLS is an optional warning threshold"),
    "INV34-007864": dup("INV34-002998", "core/validators.py:287/288 - the `pass` line of "
                                        "INV34-002998's handler",
                        "no fabricated DLS warning for an unparseable value"),
    "INV34-007865": (INT, _VALIDATOR + " Site: the BHA `id < od` check (325-330); the same loop "
                                       "reports 'Length must be numeric' for its own length field "
                                       "(320-321).", None),
    "INV34-002964": (INT, _VALIDATOR + " Site: the logistics Date Out >= Date In check (445-455) on "
                                       "optional date fields.", None),
    "INV34-002965": dup("INV34-002964", "core/validators.py:454 - the second rule on the same "
                                        "handler", "optional date ordering check"),
    "INV34-007873": dup("INV34-002964", "core/validators.py:454/455 - the `pass` line of "
                                        "INV34-002964's handler",
                        "no false 'Date Out must be >= Date In' for unparseable dates"),
    "INV34-008774": (INT, _VALIDATOR + " Site: the BOP test-overdue warning (504-512).", None),
    "INV34-007877": dup("INV34-008774", "core/validators.py:512/513 - the `pass` line of "
                                        "INV34-008774's handler",
                        "the overdue warning is skipped rather than emitted on unparseable dates"),

    # ------------------------------------------------------------ history-dialog formatters
    "INV34-003153": (VC, _FORMATTER + " This is the family's primary instance "
                                      "(dialogs/casing_history_dialog.py:52-55); the three sibling "
                                      "history dialogs carry the identical helper.", None),
    "INV34-003164": dup("INV34-003153", "dialogs/cement_history_dialog.py:53-56 - the identical "
                                        "formatter helper", _FORMATTER),
    "INV34-003493": dup("INV34-003153", "dialogs/mse_history_dialog.py:53-56 - the identical "
                                        "formatter helper", _FORMATTER),
    "INV34-003504": dup("INV34-003153", "dialogs/mud_volume_history_dialog.py:54-57 - the identical "
                                        "formatter helper", _FORMATTER),
    "INV34-003585": dup("INV34-003153", "dialogs/report_history_dialog.py:40-43 - the same "
                                        "display-fallback contract for a date value "
                                        "(`strftime` -> `str(value)`)", _FORMATTER),

    # ------------------------------------------------------------ daily_report_dialogs.py
    "INV34-003179": (INT, _TIME_KEEP + " Site: 149-152, with that comment.", None),
    "INV34-003177": (INT, _TIME_KEEP + " Site: the from-time branch at 295.", None),
    "INV34-003178": dup("INV34-003177", "dialogs/daily_report_dialogs.py:304 - the same parse for "
                                        "the to-time branch, same contract",
                        "the widgets keep their defaults"),
    "INV34-007928": dup("INV34-003177", "dialogs/daily_report_dialogs.py:295/296 - the `pass` line "
                                        "of INV34-003177's handler",
                        "the widgets keep their defaults"),
    "INV34-007929": dup("INV34-003177", "dialogs/daily_report_dialogs.py:304/305 - the `pass` line "
                                        "of INV34-003178's handler",
                        "the widgets keep their defaults"),

    # ------------------------------------------------------------ hierarchy / planning dialogs
    "INV34-003472": (VC,
        "`if self.project_id: self.select_project_by_id(self.project_id)` (855): the subject is a "
        "Project primary key and the dialog's constructor argument is optional ('set the initial "
        "project if one was given', 854) - a falsy id means 'no initial project', so nothing is "
        "selected.", None),
    "INV34-003466": (VC,
        "`estimated_rop = (depth_to - depth_from) / planned_days if planned_days else None` (1210) - "
        "the divisor guard returns None ('no estimate') instead of dividing by zero or inventing a "
        "rate; planned_days is an operator entry that is legitimately absent.", None),
    "INV34-003571": (INT,
        "Stored spud date parsed into the planning dialog's date widget; the handler's own comment "
        "states the contract - 'spud date absent/unparseable - keep widget date' (1097) - so a bad "
        "stored value cannot fabricate a date, and the widget keeps the operator's current entry.",
        None),

    # ------------------------------------------------------------ smart_template_dialog.py
    "INV34-003802": (INT,
        "A *probe* inside the label heuristic: `float(...)` is attempted only to decide 'this is a "
        "number, hence not a label' (`return False` on success) and the swallow means 'not a "
        "number - continue with the date-like and text checks that follow' (1261+). The failure is "
        "the branch's expected outcome, not a hidden error.", None),
    "INV34-007987": dup("INV34-003802", "dialogs/smart_template_dialog.py:1258/1259 - the `pass` "
                                        "line of INV34-003802's probe",
                        "the probe's miss is a normal outcome of the heuristic"),
    "INV34-003799": (INT,
        "A *probe* in the code-resolution helper: an integer main code is tried first and a "
        "non-integer value falls through to the reverse (name -> code) lookup at 1398-1402. The "
        "swallow implements 'not an integer code', after which the helper still resolves the value "
        "by name.", None),
    "INV34-007988": dup("INV34-003799", "dialogs/smart_template_dialog.py:1395/1396 - the `pass` "
                                        "line of INV34-003799's probe",
                        "the reverse lookup follows"),
    "INV34-003705": (VC,
        "`if best_match:` (1411) guards the fuzzy-match result of a name -> code search where "
        "`best_match` is initialised to None and can only be set to a key of `MAIN_CODE_MAP` "
        "(1405-1410). Those keys are non-empty strings ('1'..'12'+), so no legitimate code is "
        "falsy and the test is exactly 'did the fuzzy search find anything?'.", None),
    "INV34-003707": dup("INV34-003705", "dialogs/smart_template_dialog.py:1485 - the identical "
                                        "guard for the sub-code fuzzy search (`SUB_CODE_MAP` keys "
                                        "are '1.1'-style non-empty strings)",
                        "same 'did the search find anything?' test"),
    "INV34-003800": (INT,
        "A *probe* in the sub-code helper: a numeric sub-code is tried first and a non-numeric value "
        "falls through to the sub-code's own reverse lookup ('try sub code number', 1451). Same "
        "shape as INV34-003799.", None),
    "INV34-007989": dup("INV34-003800", "dialogs/smart_template_dialog.py:1448/1449 - the `pass` "
                                        "line of INV34-003800's probe",
                        "the sub-code reverse lookup follows"),
    "INV34-003608": (INT,
        "Template-layout analysis: merged-cell bookkeeping over the worksheet "
        "(`merged_slaves.add((r, c))`) whose failure leaves the collected set incomplete - it feeds "
        "the template analysis only, and the scan continues with its own bounds checks "
        "(`range(1, min(ws.max_row + 1, MAX_SCAN_ROWS))`, 2102). No extracted value is changed.",
        None),
    "INV34-007995": dup("INV34-003608", "dialogs/smart_template_dialog.py:2099/2100 - the `pass` "
                                        "line of INV34-003608's handler",
                        "template-layout analysis only"),

    # ------------------------------------------------------------ startup
    "INV34-003810": (INT,
        "Best-effort session close in the startup dialog's cleanup path: the same contract already "
        "adjudicated for `core/database.py release_session` (p6-batch-004 INV34-000284) - a failure "
        "to close must not mask the operation's outcome, and the session object is discarded "
        "immediately afterwards.", None),
}
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
        "class": ("class E (import statistics/heuristics, validator comparison guards, dialog "
                  "formatters and legacy parsers): "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "tests": ("no production change in this batch; the full suite evidence recorded in "
                  "P6_PROGRESS.md (1 831 tests / 0 failures / 0 errors / 4 skipped on the 3f0cf3e "
                  "tree) stands for this batch too - every site read here is untracked by this "
                  "session's changes"),
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
                                 "no file in this batch was changed by this session (verified: the "
                                 "batch touches only files untouched since the register was built), "
                                 "so no record needed re-anchoring"),
                      "re_anchored_items": []},
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
