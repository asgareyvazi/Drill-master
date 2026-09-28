#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-012 (45 HIGH->MEDIUM records, class A).

Phase 2, second batch: the remaining persistence surface of core/database.py (late save_*
upserts, the bulk-material closing trichotomy, more optional-session managers, lookahead
plan/actual guards) and the DDR import service (well-alias resolution, report numbering,
fraction parsing, review-item handling, template scanning).  Same contract as
p6_batch_005..011: read each site, quote the deciding contract, adjudicate one construct
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
BATCH = "p6-batch-012"

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

NEW_FINDINGS: list[dict] = []

_UP = ("Same construct as the phase-1 upsert primary INV34-000965 (p6-batch-011): "
       "`session.query(Model).filter(...).first()` / `.one_or_none()` returns the row or None and the "
       "branch is the update-or-insert decision.  The subject is an Optional[model] produced by the "
       "query itself, so the bare truthiness test IS the presence test - no numeric value is "
       "involved.")
_SESS = ("Same construct as the session-ownership primary INV34-009108 (p6-batch-011): "
         "`owns_session = session is None` then `session = session or self.create_session()`, with "
         "commit/rollback/close performed only when the session is owned, so a caller-supplied "
         "session stays inside the caller's (import) transaction.")
_BULK = ("The rule's premise (an unknown coerced to a synthetic zero) is refuted at this site: the "
         "two lines above set the closing to NULL whenever the opening is unknown - `if "
         "existing.initial_stock is None: existing.current_stock = None` with the comment 'Closing "
         "stays unknown (NULL) when the opening is unknown; never fabricated from a synthetic 0.' "
         "(7384-7387).  Inside the else arm `initial_stock` is therefore non-None, so "
         "`(existing.initial_stock or 0.0)` can only ever yield the real value; `received`/`used` "
         "are *movements*, for which the domain rule is documented in core/inventory_semantics.py: "
         "'Absent movement means zero' (`normalize_movement`, applied to this same payload at "
         "7354-7356).  The new-row arm below repeats the same trichotomy explicitly "
         "('Opening trichotomy: explicit value (incl. 0.0) is a fact and is preserved; missing "
         "(None) may be carried forward from the previous closing - never the other way around', "
         "7397-7401).")

R: dict[str, tuple[str, str, str | None]] = {
    # ------------------------------------------------------ core/database.py: presence checks
    "INV34-000928": dup("INV34-000965", "core/database.py:6168-6176 - `save_bha_report`'s "
                                        "`else: existing = None` arm feeding the same presence test",
                        _UP),
    "INV34-000942": dup("INV34-000965", "core/database.py:6241-6248 - `save_downhole_equipment`",
                        _UP),
    "INV34-000955": dup("INV34-000965", "core/database.py:6319-6322 - `save_formation_report`", _UP),
    "INV34-001035": dup("INV34-000965", "core/database.py:6598-6601 - `save_trajectory_calculation`",
                        _UP),
    "INV34-001011": dup("INV34-000965", "core/database.py:7713-7717 - the `else: existing = None` arm "
                                        "of `save_safety_report`", _UP),
    "INV34-000931": dup("INV34-000965", "core/database.py:7377-7380 - the bulk-material `else: "
                                        "existing = None` arm", _UP),
    "INV34-000763": dup("INV34-000965", "core/database.py:6839-6842 - `delete_logistics_personnel` "
                                        "selects the row by primary key and deletes only when it was "
                                        "found", _UP),
    "INV34-001010": dup("INV34-000965", "core/database.py:9579-9596 - `save_procedure` upsert "
                                        "(`data.get('id')` -> lookup -> `if proc:` update, else "
                                        "insert)", _UP),
    "INV34-000934": dup("INV34-000965", "core/database.py:10170-10188 - `save_cost_record` upsert",
                        _UP),

    # ------------------------------------------------------ core/database.py: bulk-material trichotomy
    "INV34-000497": (DUP, _BULK + " Site: `(existing.initial_stock or 0.0)` (7390).", None),
    "INV34-007158": dup("INV34-000497", "core/database.py:7390 - second rule on the same statement",
                       _BULK),
    "INV34-009290": dup("INV34-000497", "core/database.py:7390 - third rule (numeric-coalesce) on the "
                                        "same statement", _BULK),
    "INV34-000498": dup("INV34-000497", "core/database.py:7391 - `+ (existing.received or 0.0)`", _BULK),
    "INV34-007159": dup("INV34-000497", "core/database.py:7391 - second rule on the received term",
                        _BULK),
    "INV34-009291": dup("INV34-000497", "core/database.py:7391 - third rule on the received term",
                        _BULK),
    "INV34-000499": dup("INV34-000497", "core/database.py:7392 - `- (existing.used or 0.0)`", _BULK),
    "INV34-007160": dup("INV34-000497", "core/database.py:7392 - second rule on the used term", _BULK),
    "INV34-009292": dup("INV34-000497", "core/database.py:7392 - third rule on the used term", _BULK),

    # ------------------------------------------------------ core/database.py: session ownership
    "INV34-009310": dup("INV34-009108", "core/database.py:7699-7700 - `save_safety_report`", _SESS),
    "INV34-009353": dup("INV34-009108", "core/database.py:8457-8458 - `save_equipment_log` (whose "
                                        "ambiguity path is also fail-closed: `raise ValueError("
                                        "\"Equipment identity is ambiguous; select the record ID "
                                        "explicitly\")`, 8464-8465)", _SESS),
    "INV34-009379": dup("INV34-009108", "core/database.py:8831-8832 - `save_npt_report`", _SESS),
    "INV34-009389": dup("INV34-009108", "core/database.py:9047-9048 - `update_code_usage`", _SESS),
    "INV34-009391": dup("INV34-009108", "core/database.py:9076-9077 - `save_time_depth_data`", _SESS),
    "INV34-009403": dup("INV34-009108", "core/database.py:9306-9307 - "
                                        "`auto_update_from_daily_report`", _SESS),
    "INV34-009543": dup("INV34-009108", "core/ddr_import_service.py:145-146 - `_resolve_import_well` "
                                        "(a service method carrying the same ownership flag)", _SESS),
    "INV34-009564": dup("INV34-009108", "core/ddr_import_service.py:696-697 - `_ensure_report_number`",
                        _SESS),
    "INV34-009566": dup("INV34-009108", "core/ddr_import_service.py:710-711 - "
                                        "`_create_fallback_report`", _SESS),
    "INV34-009570": dup("INV34-009108", "core/ddr_import_service.py:958-959 - `_save_time_logs`",
                        _SESS),
    "INV34-009572": dup("INV34-009108", "core/ddr_import_service.py:1057-1058 - `_save_morning_logs`",
                        _SESS),

    # ------------------------------------------------------ core/database.py: other guards
    "INV34-000957": (VC,
        "The carry-forward guard of `save_fuel_water_inventory` is documented in the code above it: "
        "'...stock to zero; an explicitly-reported opening (incl. 0.0) is a fact and is never "
        "overwritten by carry-forward.' (7015-7016).  `previous` is the row result of the "
        "strictly-previous-date query and `if previous:` (7022) is the row-presence test that "
        "decides whether a projection exists at all; the per-fluid branches inside then only fill a "
        "stock that is still None (`if fuel_stock is None:`, 7023).", None),
    "INV34-009367": (VC,
        "In the lookahead update, actual execution timestamps are only written when they were "
        "supplied: `if actual_start is not None: plan.actual_start = actual_start` (8738-8739).  A "
        "save that carries no actual start therefore cannot blank an existing one, which matches the "
        "import path's stated rule that planned dates are not evidence of execution "
        "(core/database.py:5101-5102).", None),
    "INV34-009369": dup("INV34-009367", "core/database.py:8740-8741 - the same guard for "
                                        "`actual_end`", "same plan/actual separation"),
    "INV34-000738": cosmos(
        "The subject is the activity-code text of a time-log row (`code = log.main_code`, then "
        "`if not code: continue`, 9356-9358); codes are strings such as '2.1', and empties simply "
        "have no code usage to accumulate."),
    "INV34-007278": dup("INV34-000738", "core/database.py:9357 - the second rule on the same text "
                                        "guard", "same activity-code text"),
    "INV34-000744": (VC,
        "Derived-row tracking with an explicit ownership rule: the set difference "
        "`stale = set(previous.get(key, [])) - set(generated[key])` (9397) feeds "
        "`if stale: ...delete(...)` and is preceded by the block's own contract - 'Track only our "
        "own derived records. Never delete manual rows based merely on matching timestamps or an "
        "empty source report.' (9313-9314).  The ids compared come from the previous `daily_derived` "
        "audit entry, so a manual row can never fall into the difference.", None),
    "INV34-000824": (VC,
        "`get_export_templates(template_type: str = None, created_by: int = None)` uses the optional "
        "parameters as *filters*: `if template_type:` and `if created_by:` (9447-9449) add the "
        "respective clause, so a falsy value means 'do not filter' (all templates / all creators) - "
        "the empty selection an unfiltered listing is supposed to return.", None),

    # ------------------------------------------------------ core/ddr_import_service.py
    "INV34-007359": (INT,
        "Alias resolution over an optional mapping: `v = (well_info or {}).get(k)` walks the "
        "candidate key list and takes the first non-empty text (`if v and str(v).strip(): name = "
        "str(v).strip(); break`, 135-139); absence is handled explicitly right below - `if not name "
        "and not code: return self.well_id` (142-143) - where `well_id` is the import's already "
        "chosen well.  The `or {}` therefore only makes the traversal total.", None),
    "INV34-001295": (VC,
        "`density_lineage` is the provenance object returned by `mud_density_pcf(mud_data)` "
        "(541-542) - it is truthy exactly when the source densities were converted, and the block "
        "then appends the explanatory detail 'Density converted to PCF using the existing "
        "UnitManager' (543-544).  A dict/list provenance value, not a measurement.", None),
    "INV34-001293": (VC,
        "Report-number allocation with a documented floor: `return (last.report_number + 1) if last "
        "else 1` (702) - the section's highest number plus one, or 1 when the section has no report "
        "yet; a workbook-supplied number is honoured earlier (`if dr.get(\"report_number\"): num = "
        "ValueNormalizer.to_int(...); if num and num > 0: return num`, 690-693).  Nothing is "
        "invented for an existing number.", None),
    "INV34-001313": (VC,
        "`if not text: return None` (829) implements the function's own docstring: "
        "`'18/32\"' -> 18; '3/4\"' -> 24; None for Open/text values.` (828).  A blank cell is "
        "reported as None ('not a 32nds fraction'), never as 0/32.", None),
    "INV34-007379": (INT,
        "`scr_rows = scr_data or []` normalises an *optional* extracted table before iterating it, "
        "and the loop immediately re-checks the shape at both levels (`if isinstance(scr_rows, "
        "list):`, `if not isinstance(row, dict): continue`, 914-917) plus per-field emptiness "
        "(`if val not in (None, \"\"):`, 930).  The default therefore only makes the iteration "
        "total; no scr measurement is manufactured.", None),
    "INV34-001350": (VC,
        "The docstring of `_save_time_logs` states the contract: 'Invalid source rows are returned "
        "as review items rather than swallowed; a caller-owned session receives exceptions so the "
        "outer import can rollback every report-scoped object.' (952-956).  A duration that cannot "
        "be parsed becomes `duration = None` (986-989) and, when the source did state something, a "
        "REVIEW_REQUIRED item is appended with the original value and the normalized None "
        "(990-995).  The failure is reported, not hidden.", None),
    "INV34-001349": dup("INV34-001350", "core/ddr_import_service.py:1094-1101 - the same duration "
                                        "handling in `_save_morning_logs`, whose review item carries "
                                        "the reason 'Continuation row has no independent time anchor; "
                                        "no time was invented' / 'Both time anchors are required for "
                                        "persistence' (1085-1091)",
                        "unparseable duration -> None + REVIEW_REQUIRED"),
    "INV34-007384": (VC,
        "Documented fallback: the method's docstring says 'Returns None when no template matches, so "
        "imports fall back to heuristic detection.' (1181-1182), and the missing/unreadable templates "
        "directory is exactly that case (`if not os.path.isdir(templates_dir): return None`, 1188-"
        "1189).  The return value is a template or None - a boolean filesystem question, no numeric "
        "subject.", None),
    "INV34-001347": (INT,
        "Template scanning tolerates one bad file: an unreadable or invalid JSON template is skipped "
        "(`except (OSError, ValueError): continue`, 1201-1202) while the remaining candidates are "
        "still compared, and the method's documented outcome for 'nothing matched' is None so the "
        "import falls back to heuristic detection (1181-1182).  Skipping a broken optional file "
        "cannot invent a mapping.", None),
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
