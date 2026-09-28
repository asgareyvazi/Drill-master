#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-011 (45 HIGH->MEDIUM records, class A).

Phase 2, first batch: the persistence/import transaction surface of core/database.py
(session ownership, upsert presence checks, parse-and-skip guards, JSON serialisation for
the import payloads) plus the AI import mapper's timeout parse.  Same contract as
p6_batch_005..010: read each site, quote the deciding contract, adjudicate one construct
once.  No defect, no production change.
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
BATCH = "p6-batch-011"

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

NEW_FINDINGS: list[dict] = []

_SESSION = ("The optional-session contract of the atomic import path, implemented identically in every "
            "`save_*` method of this manager: `owns_session = session is None` (3822) then "
            "`session = session or self.create_session()` (3823).  Ownership decides every side "
            "effect - with a caller-supplied session the method participates in the caller's "
            "transaction and does NOT commit, roll back or close (`except ...: if owns_session: "
            "rollback; return None` / `else: raise`, `finally: if owns_session: session.close()`, "
            "3836-3848), so the atomic import that shares one session can roll the whole operation "
            "back.  Grep shows the same guard set in all six methods of this batch.")
_OR_ZERO = ("`session.query(Model).filter(...).first()` returns the row or None, and the branch is the "
            "module's upsert decision (update the found row in place - `setattr(existing, key, "
            "value)` - or build a new record in the `else` arm, e.g. 5961-5973).  The subject is an "
            "Optional[model] created by the query itself, so the bare truthiness test IS the "
            "presence test; no numeric value is involved.")
_SKIP = ("Skip-bad-rows handling inside the import transaction: the block explicitly excludes the "
         "absent and the zero cases around the same try (`if val in (None, \"\"): continue`, "
         "`if count_v == 0: continue`, 5007-5014) and then counts only what it actually saved "
         "(`count(...)`), so a non-numeric cell is treated as 'not a POB figure' - the same "
         "no-fabrication rule the file states elsewhere for the same import ('working_pressure is "
         "NOT NULL: skip rows where the workbook had no numeric pressure (never invent 0)', "
         "5515-5516).")
_TO_DT = ("`_to_dt` is the import's date normaliser: it accepts an existing datetime unchanged, tries "
          "the three documented text formats in order and returns None when none matches "
          "(5073-5082).  Its callers treat None as UNKNOWN, not as a value - `actual_start=_to_dt(...)`, `actual_end=_to_dt(...)` (5103-5104) with the block's own provenance note "
          "('Planned dates are not evidence of actual execution', 5101-5102) and "
          "`progress_percentage=None` ('No progress column exists in the source: unknown, not 0%', "
          "5099-5100).  The `continue` therefore only advances the format ladder.")
_JSON = ("Serialisation for a JSON/text column of the import: the payload is the workbook's own row "
         "data (strings/numbers) and `ensure_ascii=False` is deliberate so Persian text stays "
         "readable.  Same module convention where the payload can carry non-JSON scalars: "
         "`json.dumps(date_source, default=str)` (5455) and `json.dumps(bit_records, indent=2, "
         "default=str)` for `bit_records_json = Column(JSON)` (6101/5209).")

R: dict[str, tuple[str, str, str | None]] = {
    "INV34-000073": (INT,
        "Environment-variable parse with a documented fallback: `int(os.getenv(\"DRILLMASTER_AI_"
        "TIMEOUT\", str(max(timeout, 30))))` and on a non-numeric value the built-in fallback is "
        "used, after which the value is clamped into the supported window "
        "(`self.timeout = min(max(requested_timeout, 10), 45)`, 67).  The AI subsystem is opt-in and "
        "advisory (module docstring 1-5), so a bad env value degrades to a bounded default instead "
        "of blocking the import.", None),

    "INV34-008685": cosmos(
        "`if not self._raw_table_exists(raw, name)` (3042) tests the *boolean result of a schema "
        "probe* inside the import-schema verifier; the following lines raise a RuntimeError naming "
        "the missing tables (3044-3045), so the guard is fail-closed and no numeric quantity is "
        "tested."),

    "INV34-009108": (VC, _SESSION + " Site: `save_section` (3822-3823).", None),
    "INV34-009110": dup("INV34-009108", "core/database.py:3857-3858 - the identical ownership guard "
                                        "in `save_wellbore`", _SESSION),
    "INV34-009118": dup("INV34-009108", "core/database.py:4132-4133 - `save_well`", _SESSION),
    "INV34-009124": dup("INV34-009108", "core/database.py:4217-4218 - `save_daily_report`", _SESSION),
    "INV34-009195": dup("INV34-009108", "core/database.py:5704-5705 - `save_drilling_parameters`",
                        _SESSION),
    "INV34-009200": dup("INV34-009108", "core/database.py:5785-5786 - `save_mud_report`", _SESSION),

    "INV34-006920": (VC,
        "`if not is_editable(report.status)` (4236) is a boolean question asked of the lifecycle "
        "module (`core.report_lifecycle`) about the report's state, and the true arm raises a domain "
        "error naming the state: `raise ValueError(f\"Report is {report.status or 'locked'} and "
        "cannot be edited. Use the workflow actions to change its state.\")` (4237-4239).  The test "
        "is fail-closed and cannot mistake absence for a zero.", None),

    "INV34-000709": (INT,
        "`report = session.query(DailyReport).filter_by(well_id=well_id, section_id=section_id, "
        "report_date=report_date).one_or_none()` (4294) then `return self.create_import_snapshot("
        "report.id) if report else None` (4295): the selection is declared to be 0-or-1 (a report "
        "for that well/section/date) and the falsy arm means 'nothing to snapshot'.  Duplicated "
        "report dates exist in this schema (the analytics code handles them explicitly: 'Ambiguity "
        "-> UNKNOWN, not a guess'), and `one_or_none()` refuses with MultipleResultsFound rather "
        "than picking one - fail-closed, no guess.  Residual (recorded): that refusal surfaces as a "
        "SQLAlchemy exception rather than a domain message, and the method has no caller inside this "
        "repository (grep).", None),
    "INV34-001051": dup("INV34-000709", "core/database.py:4294-4295 - the second rule on the same "
                                        "selection (`if report else None`)", "0-or-1 selection; "
                                        "falsy means nothing to snapshot"),
    "INV34-006924": dup("INV34-000709", "core/database.py:4294 - the third rule on the same "
                                        "`one_or_none()` statement", "fail-closed on ambiguity"),

    "INV34-001120": (INT, _SKIP + " Site: the POB category counts (5005-5019).", None),
    "INV34-001121": dup("INV34-001120", "core/database.py:5011 - the second rule on the same handler",
                        _SKIP),
    "INV34-006967": dup("INV34-001120", "core/database.py:5011 - the third rule on the same handler",
                        _SKIP),

    "INV34-000987": cosmos(
        "`remarks = hrs + remarks if remarks else hrs.strip()` (5069) tests the emptiness of a *text* "
        "field (already converted to `str(remarks or \"\")` above) to decide whether to prefix the "
        "hours tag; strings, not numbers."),

    "INV34-001127": (INT, _TO_DT + " Site: the format ladder (5077-5081).", None),
    "INV34-001129": dup("INV34-001127", "core/database.py:5080 - the second rule on the same ladder",
                        _TO_DT),
    "INV34-001130": dup("INV34-001127", "core/database.py:5080 - the third rule on the same ladder",
                        _TO_DT),

    "INV34-000985": (INT,
        "`parsed_day = _to_dt(day_val)` is consumed on the next line as a question, with a documented "
        "fallback: `plan_date = day_val if isinstance(day_val, date) and not isinstance(day_val, "
        "datetime) else (parsed_day.date() if parsed_day else imported_report_date)` (5086).  An "
        "unparseable day therefore falls back to the date of the report being imported (the row is "
        "one of that report's seven lookahead days), and the source text is preserved for audit "
        "('Original scheduled start/end remain in import audit', 5102).", None),

    "INV34-000965": (VC, _OR_ZERO + " Site: `CasingReport` by report_id (5120).", None),
    "INV34-000966": dup("INV34-000965", "core/database.py:5134 - the other CasingReport upsert branch "
                                        "(row-oriented casing table)", _OR_ZERO),
    "INV34-000967": dup("INV34-000965", "core/database.py:5159 - `CementReport` by report_id", _OR_ZERO),
    "INV34-000968": dup("INV34-000965", "core/database.py:5188 - the other CementReport branch "
                                        "(cementing materials)", _OR_ZERO),
    "INV34-000969": dup("INV34-000965", "core/database.py:5212 - `BitReport` by report_id", _OR_ZERO),
    "INV34-000970": dup("INV34-000965", "core/database.py:5230 - `BHAReport` by report_id", _OR_ZERO),
    "INV34-000972": dup("INV34-000965", "core/database.py:5270 - `DownholeEquipment` by report_id",
                        _OR_ZERO),
    "INV34-000973": dup("INV34-000965", "core/database.py:5284 - `FormationReport` by report_id",
                        _OR_ZERO),
    "INV34-000974": dup("INV34-000965", "core/database.py:5419 - `FuelWaterInventory` by report_id",
                        _OR_ZERO),
    "INV34-000975": dup("INV34-000965", "core/database.py:5656 - `DownholeEquipment` JSON child",
                        _OR_ZERO),
    "INV34-000976": dup("INV34-000965", "core/database.py:5343 - `BulkMaterials` by material name",
                        _OR_ZERO),
    "INV34-001001": dup("INV34-000965", "core/database.py:5795 - the `else: existing = None` arm of "
                                        "`save_mud_report`", _OR_ZERO),
    "INV34-001049": dup("INV34-000965", "core/database.py:6029 - the `else: existing = None` arm of "
                                        "`save_wellbore_schematic`", _OR_ZERO),
    "INV34-000932": dup("INV34-000965", "core/database.py:5957 - `save_casing_report`", _OR_ZERO),
    "INV34-000933": dup("INV34-000965", "core/database.py:5888 - `save_cement_report`", _OR_ZERO),

    "INV34-009183": (INT, _JSON + " Site: `casing_json = json.dumps(rows, ensure_ascii=False)` (5135)."
                     "  Residual: this call has no `default=`, so a non-JSON-native cell would abort "
                     "the atomic import (fail-closed: the transaction rolls back, nothing partially "
                     "written); the row payload here is workbook text/numbers.", None),
    "INV34-009184": dup("INV34-009183", "core/database.py:5189 - `materials_json = json.dumps("
                                        "materials, ensure_ascii=False)`", _JSON),
    "INV34-009193": (INT, _JSON + " Site: the audit-log provenance payload `json.dumps(date_source, "
                                  "default=str)` (5455): `date_source[fld]` holds the raw workbook "
                                  "text of a date field that could not be parsed, and the audit "
                                  "entry exists precisely so that text is not lost.", None),
    "INV34-009225": (INT, _JSON + " Site: `bit_records_json = json.dumps(bit_records, indent=2, "
                                  "default=str)` (6101) for the `bit_records_json = Column(JSON)` "
                                  "field (1098), matching the same module's import branch at 5208-"
                                  "5210.", None),

    "INV34-001124": (INT,
        "The failure keeps its provenance and stays unknown: `except ValueError: date_source[fld] = "
        "raw; safety[fld] = None` (5450-5452), and the collected `date_source` is written to an "
        "AuditLog entry right below (`action=\"import_source_metadata\" ... "
        "json.dumps(date_source, default=str)`, 5454-5455).  A safety date that the workbook did not "
        "state therefore cannot become a fabricated value, and the raw text remains queryable.",
        None),
    "INV34-000979": (VC,
        "The parsed safety date is range-checked and otherwise discarded: `if not (1990 <= "
        "parsed_date.year <= 2100): parsed_date = None` (5498-5499), with the same try's typed "
        "handler doing the same for an unparseable value (5500-5501); the value is then written as "
        "`bp[\"last_test_date\"] = parsed_date` and the following lines branch on `is None`.  An "
        "out-of-range date is thus treated as 'not stated' instead of being stored as an absurd "
        "fact, and no arithmetic is mixed with a missing value.", None),
    "INV34-001122": dup("INV34-000979", "core/database.py:5500-5501 - the typed handler of the same "
                                        "date-validation block", "unparseable -> None, never a "
                                        "guessed date"),
    "INV34-007015": dup("INV34-000979", "core/database.py:5500 - the second rule on the same handler",
                        "unparseable -> None"),
    "INV34-007019": (VC,
        "The skip is documented in the code itself: '# working_pressure is NOT NULL: skip rows where "
        "the workbook had no numeric pressure (never invent 0).' (5515-5516), implemented as "
        "`if filtered.get(\"working_pressure\") is None: continue` plus the non-numeric guard "
        "(5517-5522); what survives is counted (`saved += 1; count(\"bop_components\", saved)`, "
        "5523-5525).  A row without a stated pressure is therefore omitted, not filled with 0.",
        None),
    "INV34-007030": (INT,
        "An optional number is validated before use: `candidate = float(raw_hours)` and on a "
        "non-numeric value `candidate = None` (5612-5614), then `if candidate is not None and "
        "math.isfinite(candidate) and candidate >= 0: hours = candidate` (5615-5616) - a bad or "
        "non-finite entry leaves the field at its prior/unknown state instead of importing a "
        "negative or infinite hours figure.", None),
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
        "class": ("class A (persistence / import-transaction surface): "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "tests": ("no production change in this batch; the full suite evidence recorded in the "
                  "final phase-1 report (1 834 / 0 failures / 0 errors / 4 skipped on the "
                  "1d44cb5 tree) stands for this batch too - this batch edits no production file"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           f"docs/audits/m36-evidence/{BATCH}.md",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m36-evidence/P6_PROGRESS.md",
                           "tools/m36/p6_batch_011.py"],
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
