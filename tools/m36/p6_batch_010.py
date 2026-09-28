#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-010 (the last 9 HIGH records, class E).

The tail of the HIGH set: a dialog date parse, the release gate's fail-closed return-code
tests, two test-oracle guards and two theme/acceptance helpers.  Same contract as
p6_batch_005..009: read each site, quote the deciding contract, adjudicate one construct
once.  This batch closes the HIGH priority (HIGH 9 -> 0); no defect, no production change.
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
BATCH = "p6-batch-010"

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

NEW_FINDINGS: list[dict] = []

RC = ("`_run(...)` returns a `subprocess.CompletedProcess`, so the subject is its exit status: "
      "zero means 'the command succeeded', a non-zero value means 'the command failed' (negative "
      "for a signalled process). `if rc:` is therefore exactly the fail-closed test - it proceeds "
      "only on a successful command - and no read of the value can be confused with 'absent "
      "number', because the value is always set by the call itself. In this same file the explicit "
      "form is used where the success set is wider ('if debt.returncode not in (0, 1) or "
      "defects.returncode:', verify_lint, 254).")
_THEME = ("A theme helper ('رنگ hex را تیره‌تر می‌کند' = 'darkens a hex colour'): the failure mode is "
          "a colour token that is not a 6-digit hex value, in which case the caller's own token is "
          "returned unchanged - presentation only, no measurement, no persistence, and it cannot "
          "invent a colour. Residual (recorded, cosmetic): after `hex_color.lstrip('#')` a value "
          "that fails the hex parse is returned without its leading '#', exactly as in the sibling "
          "helper `HomeTab.darken_color` (adjudicated as INV34-004079 in p6-batch-009).")

R: dict[str, tuple[str, str, str | None]] = {
    # ------------------------------------------------------------ tabs/w9_Services_Widget.py
    "INV34-006370": (INT,
        "A stored service date ('%Y-%m-%d' string) is parsed back into the dialog's date widget; on "
        "an unparseable/partial value the widget keeps its current (default) contents, so no date is "
        "invented for a malformed legacy row. The typed guard matches the only failures the parse "
        "can raise (`strptime` -> ValueError, a missing attribute -> AttributeError) and the "
        "following fields are loaded independently (673-682), so a bad date cannot abort the rest "
        "of the load.", None),
    "INV34-008485": dup("INV34-006370", "tabs/w9_Services_Widget.py:671/672 - the `pass` line of "
                                        "INV34-006370's handler",
                        "the date widget keeps its default"),

    # ------------------------------------------------------------ tests/
    "INV34-006523": (VC,
        "Test-oracle arithmetic in `test_required_eleven_pair_plan_matrix`: the matrix at 54-68 "
        "contains (0, 0), and the branch structure decides every other p == 0 case before this line "
        "(`elif p == 0 and a != 0: assert scalar.variance_pct is None and scalar.status == "
        "\"unavailable\"`, 80-81). So `expected = (a - p) / abs(p) * 100 if p else 0` (83) is "
        "reached with p == 0 only for (0, 0), where 0% is the correct relative variance (planned "
        "and actual are both zero) - and it also avoids a ZeroDivisionError. The guard therefore "
        "cannot mask a failing case: (0, 100) is asserted as None/unavailable one branch above.",
        None),
    "INV34-006524": cosmos(
        "`first` is a boolean one-shot flag inside the monkeypatched `sqlite3.connect` "
        "(`first = True` ... `if first: first = False; source.unlink()`, 174-179), not a numeric "
        "quantity; the guard makes the disappearing-source condition fire once."),

    # ------------------------------------------------------------ ui/utils.py
    "INV34-006718": (INT, _THEME + " Site: ui/utils.py:121-131.", None),

    # ------------------------------------------------------------ verify_release.py (release gate)
    "INV34-006764": (VC,
        RC + " Site: `git ls-files -z` (265-267) - an inventory failure must abort the wheel check "
        "rather than build from an unknown source set.", None),
    "INV34-006763": dup("INV34-006764", "verify_release.py:276-278 - the same fail-closed test on "
                                        "the `python -m build --wheel` result",
                        "a failed wheel build must not be verified as a wheel"),
    "INV34-006762": dup("INV34-006764", "verify_release.py:294-297 - the same fail-closed test on "
                                        "the `pip install --target` result",
                        "a failed install must not be smoke-tested as an installed package"),

    # ------------------------------------------------------------ tools/real_user_acceptance.py
    "INV34-008562": (INT,
        "This `pass` is the *expected* path of a negative acceptance assertion: the probe tries to "
        "save an invalid date and raises `AssertionError('Invalid date was accepted')` if the write "
        "is accepted; reaching the handler means the database refused it. Nothing is hidden - the "
        "assert immediately below (160) proves the previously stored value survived "
        "(`assert db.get_well_by_id(well)[\"spud_date\"] == date(2026, 9, 1)`), so an accepted-but-"
        "silent write could not pass this probe.", None),
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
        "class": ("class E (dialog date parse, release-gate return-code checks, test-oracle "
                  "guards, theme/acceptance helpers): "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "tests": ("no production change in this batch; the full suite evidence recorded in "
                  "P6_PROGRESS.md (1 831 tests / 0 failures / 0 errors / 4 skipped on the "
                  "3f0cf3e tree) stands for this batch too - this batch edits no production "
                  "file at all"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           f"docs/audits/m36-evidence/{BATCH}.md",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m36-evidence/P6_PROGRESS.md",
                           "tools/m36/p6_batch_010.py"],
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
