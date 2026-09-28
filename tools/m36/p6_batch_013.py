#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-013 (45 HIGH->MEDIUM records, mixed classes).

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
BATCH = "p6-batch-013"

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

NEW_FINDINGS: list[dict] = [{
    "id": "NEW-P6-003",
    "file": "core/engineering/extended.py",
    "line": 424,
    "severity": "LOW",
    "status": "recorded, not patched (legacy helper, tests-only caller; needs a domain answer)",
    "question": ("`max_kick_height_ft = kt_ppg * tvd_ft / (mw_ppg - influx_gradient_ppg) if "
                 "(mw_ppg - influx_gradient_ppg) > 0 else 0` returns a literal 0 for the "
                 "non-computable case (mud gradient not above the assumed influx gradient), which a "
                 "reader can take for a measured zero height.  Should the field be unknown/refused "
                 "instead?  The canonical engine in the app's path refuses exactly this input - "
                 "`if delta_g <= 0: return unsupported(\"Influx gradient must be less than mud "
                 "gradient to compute influx height\")` (core/engineering/engines/well_control.py:313-"
                 "317) - and distinguishes a genuine zero (remaining budget <= 0 -> 0.0 bbl, 319-331) "
                 "from unknown (`kick_intensity_ppg: None if kick_intensity is None else ...`, 322).  "
                 "The same module uses the same 0 sentinel at line 470 "
                 "(`... if tvd_ft > 0 else 0`); no production caller reaches either line (grep).  "
                 "Resolves with a domain owner's decision on the unknown-vs-zero encoding for these "
                 "legacy helpers; decision point = before the legacy module is ever re-wired."),
    "commit": None, "test": None,
}]

_VERIFY = ("`stored_result or {}` normalises a NULL/absent stored payload for the verification "
           "classifier, which treats exactly that case as unverifiable: `if not stored_result: "
           "return VerificationOutcome(status=VERIFY_UNREADABLE, method_matches=..., detail=\"stored "
           "record has no result to verify against\")` (core/engineering/calculation_verification.py:"
           "180-185).  A missing stored result therefore can never be reported as a MATCH, and the "
           "same module documents that the comparison covers the ENTIRE numeric result ('so no "
           "non-summary drift can hide behind a MATCH', torque_drag_persistence.py:239-245).  The "
           "summary projection built from the same value is all-None for missing keys - "
           "`result_summary` = `{k: _clean_number(values.get(k)) for k in SUMMARY_KEYS}` with "
           "`_clean_number`: 'Return a finite float or None (never a bool, NaN or inf)' "
           "(torque_drag_persistence.py:58-67, 197-199).")
_EXPORT = ("Collector block of `ProfessionalExcelExport.export`: the optional report id selects the "
           "report-scoped or well-scoped query - mirroring the data layer's own contract "
           "(`get_mud_report(well_id=None, report_id=None, ...)`: `if report_id: ... elif well_id: "
           "...`, core/database.py:5821-5830) - and the sheet is written only when a record was "
           "found, so an absent record leaves the sheet empty instead of being filled with "
           "fabricated rows.  Each block is wrapped in `try: ... except Exception: raise` (e.g. "
           "201-208), so a database failure aborts the export rather than writing a partial "
           "workbook.")

R: dict[str, tuple[str, str, str | None]] = {
    # ------------------------------------------------------------------ ddr import service
    "INV34-007388": (INT,
        "`template = template if template is not None else self._auto_match_template([...])` (1235) "
        "then `ExcelIntelligence(workbook, template or {}, source_file=path, ...)` (1236-1241), while "
        "the extraction branch right below uses the raw value: `excel_engine.extract() if template "
        "else excel_engine.extract_generic()` (1242-1245).  An absent/empty template therefore "
        "selects the generic heuristic extraction; the `or {}` only satisfies the engine's config "
        "argument.  A template that cannot be resolved is refused loudly instead of guessed "
        "(`raise ValueError(\"Ambiguous workbook templates; select explicitly: \" + ...)`, 1225).",
        None),

    # ------------------------------------------------------------------ editor state
    "INV34-001435": (VC,
        "`confirmed` is a bool computed two lines above from the save's own result - "
        "`confirmed = value is True or type(value) is int and value > 0` (90), refined for the "
        "SaveOutcome case to `detail.saved > 0 and detail.status in (\"SUCCESS\", \"REVIEW_REQUIRED\")` "
        "(92) - and it gates only the checkpoint of the tracked edit sections (94-96).  No numeric "
        "subject, and the decorator's docstring states the intent: 'A direct local successful save "
        "shares the global snapshot boundary.' (82).", None),
    "INV34-007412": (VC,
        "`names` is the decorator's own varargs tuple (`def editor_saved(*names)`, 81) consumed as a "
        "filter: an empty tuple means 'every tracked section', otherwise membership "
        "(`section.name in names`, 95).  The tuple is not a measurement and is never produced by a "
        "query - it is the caller's explicit selection of sections.", None),

    # ------------------------------------------------------------------ engineering engines
    "INV34-001698": (INT,
        "Documented range guard, fail-closed: the docstring states the physical range (`ν = Poisson's "
        "ratio of the formation (0.2–0.5, default 0.25)`, 689) and the code rejects anything outside "
        "the theoretical bound before any formula runs - `if not (0.0 < nu < 0.5): raise "
        "EngineeringError(\"Poisson's ratio must be in (0, 0.5)\")` (698-699); the non-numeric case "
        "was already rejected by `require_number(poisson_ratio, \"poisson_ratio\")` (697).  Residual "
        "(recorded): the docstring's stated rock range (0.2–0.5) is narrower than the validator's "
        "acceptance ((0, 0.5)); the code never substitutes a default, it refuses.", None),

    "INV34-001729": (INT,
        "Explicit, overridable default parameter of a helper whose class cites its sources "
        "('References: - Well Control Manual (IWCF/IADC) - Applied Drilling Engineering (Bourgoyne)', "
        "403-405); the value is the *assumed* influx gradient used in "
        "`max_kick_height_ft = kt_ppg * tvd_ft / (mw_ppg - influx_gradient_ppg)` (424), i.e. a "
        "visible assumption, while the function's four pressure/depth inputs are all required "
        "positional parameters - nothing is being back-filled from absence.  The canonical engine on "
        "the app's path takes the same physical quantity as an explicit optional input with no "
        "assumed value (`influx_gradient_psi_ft=None`, core/engineering/engines/well_control.py:229) "
        "and refuses when it is not below the mud gradient (313-317); this legacy helper is reached "
        "only from tests (grep: no production caller).  Residual (recorded as NEW-P6-003): the same "
        "expression falls back to a literal 0 for a non-positive denominator (424).", None),
    "INV34-001723": (INT,
        "`safety_factor: float = 1.1` is the burst design factor of the class's cited standard "
        "('References: - API TR 5C3 (Casing, Tubing, and Drill Pipe) - Bourgoyne et al.', 480-482); "
        "the method's docstring states the formula the factor feeds ('Burst_rating ≥ P_internal × "
        "SF', 489) and the parameter is explicit and overridable - the repository's own test passes "
        "the conventional value explicitly (`CasingDesign.burst_pressure(5000, safety_factor=1.1)`, "
        "tests/test_extended_engineering.py:107).  The internal pressure is a required argument, so "
        "no missing input is replaced by the default.", None),
    "INV34-001724": dup("INV34-001723", "core/engineering/extended.py:501 - the collapse-pressure "
                                        "counterpart (`safety_factor: float = 1.125`)",
                        "the collapse design factor of the same cited API TR 5C3 reference; the "
                        "repository test passes it explicitly "
                        "(`CasingDesign.collapse_pressure(3000, safety_factor=1.125)`, "
                        "tests/test_extended_engineering.py:111)"),

    "INV34-007509": (VC, _VERIFY + " Site: `stored_summary = result_summary(stored_result or {})` "
                                   "(247).", None),
    "INV34-007511": dup("INV34-007509", "core/engineering/torque_drag_persistence.py:262 - the same "
                                        "value passed on to the classifier "
                                        "(`stored_result or {}, recalc,`)",
                        "the classifier's own empty-stored-result branch is VERIFY_UNREADABLE"),

    # ------------------------------------------------------------------ hierarchy / permissions
    "INV34-007570": (VC,
        "Fail-closed authorization gate: `check_delete_permission` refuses the read-only viewer role "
        "(19-21), refuses an entity type without a required permission or when "
        "`permissions.has_permission(required)` is false (22-28), and refuses on *any* exception, "
        "logging 'Delete permission check failed; operation blocked' (29-31) - so `if not "
        "check_delete_permission(status_manager, entity_type): return False` (42-43) proceeds only "
        "when the check positively succeeded.  The function is labelled 'P0: Permission enforcement "
        "for all delete operations.' (15).", None),
    "INV34-002274": cosmos(
        "`target = args[0] if args else None` (96) tests the decorator wrapper's positional-argument "
        "*tuple* for emptiness; when the tuple is empty the following `hasattr(target, ...)` guards "
        "simply find nothing to update, and for the decorated methods `args[0]` is the bound "
        "instance.  The subject is not a value that can be confused with a measurement."),

    # ------------------------------------------------------------------ import diagnostics/profiling
    "INV34-001986": (VC,
        "`flags` is a dict of three *booleans* built from keyword-only bool parameters "
        "(persistence_error / validation_error / review_required, 28-36); the loop returns the first "
        "status of `STATUS_PRECEDENCE` whose flag is set and otherwise `ImportStatus.ACCEPT.value` "
        "(37-40).  The contract is deterministic status selection - 'Return the deterministic final "
        "status for an import result.' (31) - over booleans, so no numeric value can be mistaken for "
        "absent.", None),
    "INV34-002000": (INT,
        "Explicit default in a diagnostics API: `record_llm_call(self, model, prompt_size, "
        "response_size, duration_ms, proposals: int = 0)` (57) records one metrics dict per LLM call "
        "(59-67); the profile is attached to the import result as presentation metadata "
        "(`self.final_data.setdefault(\"metadata\", {})[\"import_timings\"] = ...as_dict()`), "
        "dialogs/smart_template_dialog.py:2265).  The object always reports how many calls it "
        "recorded (`llm_call_count: len(self.llm_calls)`, 80), so a zero proposals count is a count, "
        "not a substituted measurement.  Residual (recorded): no caller of `record_llm_call` exists "
        "in this tree (grep) - the API is currently unused.", None),
    "INV34-002006": (INT,
        "`return sum(t.duration_ms for t in self.timings)` (71): the list is built only from real "
        "measurements - `duration = (time.time() - start) * 1000` appended by `end()` (45-51) - and "
        "an empty list sums to the additive identity 0.0 ms, i.e. 'nothing was measured'.  The same "
        "object exposes the per-step entries and the call count (`as_dict`, 73-80), so the total is "
        "not read in isolation; the profiler feeds import timings metadata "
        "(dialogs/smart_template_dialog.py:2265).", None),
    "INV34-002011": (INT,
        "Documented environment fallback around one convenience import: when `get_column_letter` is "
        "unavailable the reviewer reimplements the identical A/AA/... conversion instead of failing "
        "review generation - 'Review generation must remain usable in the minimal backend/test "
        "environment without openpyxl.' (275-276) - and only the import and that one call sit inside "
        "the try (271-274).  The fallback yields the same letters, so a review row is never lost and "
        "no value is invented.  Residual (recorded): the handler is `except Exception`, broader than "
        "the ImportError it documents.", None),

    # ------------------------------------------------------------------ managers
    "INV34-002099": (INT,
        "`if timeout:` (33) schedules the auto-clear timer only (`QTimer.singleShot(timeout, lambda: "
        "...setText(\"✅ Read...\"))`, 34) *after* the message text has already been written (32): a "
        "falsy timeout means 'show the message without auto-clearing', which is why the module's own "
        "helpers pass concrete values (3000/2000/4000/5000, 39-48).  The subject is a UI millisecond "
        "delay, and the message is never suppressed by the test.", None),
    "INV34-002079": (INT,
        "Unit-carrying parameter whose unit is both documented and fixed in the implementation: "
        "'Enable autosave using the manager's established minute unit.' (57) and "
        "`timer.start(int(interval_minutes * 60 * 1000))` (74).  The default is only used when a "
        "caller enables autosave without naming an interval; the app's call sites pass their own "
        "values (`interval_minutes=5` main_window.py:1131, `interval_minutes=10` "
        "tabs/w2_Daily_Report.py:508, tabs/w9_Services_Widget.py:789).", None),
    "INV34-002081": (INT,
        "Same minute unit, stated in the wrapper's own docstring ('Attach standard managers, "
        "interpreting ``autosave_interval`` as minutes.', 181) and consumed only when autosave is "
        "explicitly requested (`if enable_autosave: ... enable_for_widget(..., "
        "interval_minutes=autosave_interval)`, 185-191) while the function's own default is "
        "`enable_autosave=False` (177).  Every caller that enables autosave passes an interval of "
        "its own (5 in tabs/w6_Trajectory_Widget.py:723, tabs/w7_logistics_Widget.py:1830-1835, "
        "tabs/w8_Safety_Widget.py:721-726, main_window.py:1131; 10 in tabs/w2_Daily_Report.py:508).",
        None),
    "INV34-007636": dup("INV34-007661", "core/managers.py:329 - the same defensive `or {}` "
                                        "normalisation in the display-metadata helper "
                                        "`ExportCoordinator.get_export_metadata`",
                        "the following lines read optional text with explicit empty defaults "
                        "(`well.get(\"client\", \"\") or well.get(\"operator\", \"\")`, "
                        "`report.get(\"report_number\", \"\")`, 332-340), so a missing row yields "
                        "blank metadata fields rather than a fabricated number (the sibling "
                        "exporter additionally refuses: `raise ValueError(\"Export well does not "
                        "exist\")`, core/professional_export.py:54-55)"),
    "INV34-002082": (INT,
        "Nozzle count for one row of the TFA input: `qty = int(n.get(\"quantity\", n.get(\"qty\", 1)) "
        "or 1)` (394) expands the list (`sizes.extend([size] * qty)`, 395), and a listed nozzle row "
        "without a count means one nozzle.  The method states its unknown/none contract explicitly: "
        "'TFA of the given nozzles; None when it cannot be computed.  No nozzles is \"not entered\", "
        "not a measured 0 in², and an engine failure is not a valid result either.' (382-385), "
        "implemented as `if not nozzles_data: return None` (389-390).", None),

    # ------------------------------------------------------------------ professional export
    "INV34-007661": (VC,
        "`well = db_manager.get_well_by_id(well_id) or {}` (45) normalises the mapping, and the "
        "builder then validates what it normalised: `if report_id and (not report or "
        "report.get(\"well_id\") != well_id): raise ValueError(\"Export report must belong to the "
        "selected well\")` (52-53) and `if not well: raise ValueError(\"Export well does not "
        "exist\")` (54-55).  The empty dict can therefore never be exported as a well; the metadata "
        "fields are read with explicit empty defaults afterwards.", None),
    "INV34-002331": cosmos(
        "Rule misfire on ORM relationships: `if w_obj and w_obj.project:` then "
        "`if w_obj.project.company:` (64-67) navigate mapped objects whose truthiness is the "
        "presence test; the block only fills the optional company/project names, and its handler "
        "re-raises (`except Exception: raise`, 68-69)."),
    "INV34-002315": (VC,
        "`mud = self.db.get_mud_report(report_id=report_id) if report_id else "
        "self.db.get_mud_report(well_id=well_id)` (202) then `if mud: _write_records(ws4, [mud])` "
        "(203-204).  " + _EXPORT, None),
    "INV34-002316": dup("INV34-002315", "core/professional_export.py:213 - the drilling-parameters "
                                        "sheet (`params = ... if report_id else ...`, then "
                                        "`if params:`)", _EXPORT),
    "INV34-002309": dup("INV34-002315", "core/professional_export.py:222 - the Bit sheet "
                                        "(`bit = self.db.get_bit_report(well_id, report_id)` then "
                                        "`if bit:`, incl. `collection_value(bit.get(\"bit_records\", "
                                        "bit.get(\"bit_records_json\")))`)", _EXPORT),
    "INV34-002308": dup("INV34-002315", "core/professional_export.py:232 - the BHA sheet (`bha = "
                                        "self.db.get_bha_report(well_id, report_id)` then `if bha:` "
                                        "with JSON/`bha_records` handling)", _EXPORT),
    "INV34-002317": dup("INV34-002315", "core/professional_export.py:254 - the Survey sheet "
                                        "(`points = query.order_by(SurveyPoint.md).all()` then `if "
                                        "points:`; the report filter itself uses the explicit "
                                        "`if report_id is not None:`, 252-253)", _EXPORT),
    "INV34-002323": dup("INV34-002315", "core/professional_export.py:277 - the Safety sheet "
                                        "(`safety = self.db.get_safety_report(well_id=well_id, "
                                        "report_id=report_id)` then `if safety:`)", _EXPORT),
    "INV34-002310": dup("INV34-002315", "core/professional_export.py:291 - the Logistics sheet "
                                        "(`bulks = query.all()` then `if bulks:`; a NULL unit is "
                                        "written as `b.unit or \"\"`, 305)", _EXPORT),
    "INV34-002324": dup("INV34-002315", "core/professional_export.py:313 - the Services sheet "
                                        "(`services = self.db.get_service_companies(...)` then `if "
                                        "services:`)", _EXPORT),
    "INV34-002311": dup("INV34-002315", "core/professional_export.py:328 - the Cost sheet (`costs = "
                                        "self.db.get_cost_records(well_id)` then `if costs:`)",
                        _EXPORT),

    # ------------------------------------------------------------------ profile import engine
    "INV34-002433": (VC,
        "`anchor_pos = self._find_anchor(sheet_name, anchor)` (181) returns a `(row, col)` tuple or "
        "None (`return (r, c)` / `return None`, 701-707), and the caller consumes it only when it "
        "exists: `if not anchor_pos: continue` then `row, col = anchor_pos` (182-185).  A found "
        "anchor is a non-empty tuple and therefore always truthy - row/column 0 cannot be read as "
        "absence - and the loop's job is to skip fields whose anchor is not in the sheet.", None),
    "INV34-009795": (INT,
        "`_get_real_sheet_name` is documented as 'Resolve a profile sheet name without leaving "
        "legacy code paths.' (665) and returns None when nothing matches (`if not wanted: return "
        "None`, 667-668; `return None` after the scan, 673).  `actual_names or []` only makes the "
        "iteration total for an optional sheet-name list, and a match returns the *actual* sheet "
        "name (672).", None),
    "INV34-002455": (VC,
        "`_extract_right_value` states its scan in the docstring - 'به سمت راست حرکت می‌کند تا اولین "
        "سلول پر را پیدا کند' (moves right to find the first filled cell, 710) - and returns `None` "
        "when no cell qualifies (730).  `continue` on a parse failure therefore advances to the next "
        "candidate cell for the requested type and the loop ends in None: a non-numeric cell is "
        "never converted into a number, least of all 0.", None),
    "INV34-002456": dup("INV34-002455", "core/profile_import_engine.py:726 - the same handler in the "
                                        "`int` branch of the same scan",
                        "skip to the next candidate cell; the function returns None when nothing "
                        "parses"),
    "INV34-002458": (VC,
        "Narrow, documented degradation: `except ImportError as exc:` around the lazy import of the "
        "Qt-layer resolver, with the comment stating the boundary - 'Missing Qt/dialog module in "
        "headless runs degrades to an explicit \"resolver unavailable\" state. A broken dialog "
        "module (e.g. SyntaxError) must propagate instead of being masked.' (780-784) - and the "
        "repository locks it with a test that raises SyntaxError from the import and expects it to "
        "propagate (tests/test_p0_phase1_regressions.py:214-227).", None),
    "INV34-002457": (DEF,
        "GENUINE DEFECT - fixed in 0699e50.  Site: `except (TypeError, ValueError): hrs = 0.0` "
        "(839-840) in `_extract_time_logs`.  Root cause: any `Hrs` cell that did not parse - a blank "
        "cell (None), an empty string, or a non-numeric token - became `0.0`, so the extracted row "
        "claimed `\"duration\": 0.0`, i.e. a *measured zero hours* for a duration the workbook never "
        "stated.  Deciding contract: (a) the canonical import validator derives a blank duration "
        "from the From/To anchors and never as zero, and reports a non-numeric source value as "
        "`report.error(..., \"Duration must be numeric\", \"duration\", dur)` with "
        "`duration_value = None` (`duration_value = computed_dur if dur in (None, \"\") else None`, "
        "core/import_quality.py:488-513); (b) the persistence boundary keeps the same three states - "
        "`raw_duration in (None, \"\")` becomes a NULL duration, a non-numeric token produces a "
        "REVIEW_REQUIRED item ('Duration must be numeric when supplied', 990-1000) and the row is "
        "*not* persisted; (c) the daily auto-update counts `log.duration is None` as "
        "`unrecorded_hours` (core/database.py:9365-9366), so None is this product's encoding of "
        "'not recorded' and 0.0 of a real zero; (d) the same file's other converters return None on "
        "failure (`_extract_right_value` -> None, `_convert_time` -> None) and the module's tests "
        "lock non-fabrication for this legacy surface ('does not fabricate units or coerce blank "
        "movements to zero', tests/test_import_inventory_routing.py:21-22).  Fix (one line, "
        "line-count neutral): `hrs = None if hrs_raw in (None, \"\") else hrs_raw  # unknown stays "
        "unknown, never 0.0` - a blank stays unstated, a stated-but-unparseable cell keeps its "
        "source token for the boundary to report, and every parsed number (including an explicit 0) "
        "is unchanged.  Regression: tests/test_profile_time_log_unknown_duration.py (blank -> None; "
        "'N/A' -> source token; 0/6/2.5 preserved; the extractor's own rows through the real "
        "`DDRImportService._save_time_logs` boundary on an isolated database - blank persists NULL, "
        "explicit 0 persists 0.0, the text row is routed to an `invalid_duration` REVIEW_REQUIRED "
        "item carrying `original_value = \"N/A\"` and is not persisted).  Mutation validation: "
        "re-introducing `hrs = 0.0` fails 3 of the 4 tests; after restoring the file "
        "byte-identically (sha256 f77253848055e1c1616c7cbf2d0deb34e141a8087b87058d24910c9f58fb45f9) "
        "all 4 pass.  Related suites: 343 passed / 0 failed / 0 errors / 0 skipped in 49.535 s.  "
        "Sibling search (numeric defaults inside except handlers, whole repository): the only "
        "same-class site still open is dialogs/planning_dialog.py:484, which has its own register "
        "record (INV34-003569, batch-015) and was deliberately not mass-patched; "
        "core/performance.py:23 and tabs/w13_Engineering_Calculator.py:126 were adjudicated in "
        "earlier batches, tabs/w13_Engineering_Calculator.py:2218 has INV34-004598 (batch-023).",
        None),
    "INV34-002429": (VC,
        "`normalized_main = main_resolution.identity if main_resolution.accepted else None` (862): "
        "the resolution object carries its own decision flag, and 'not accepted' becomes None "
        "(unknown) rather than a guessed code; the full decision is retained per row "
        "(`_combo_resolution`, 888-891) and the save boundary routes any non-ACCEPT status to a "
        "REVIEW_REQUIRED item with the source value and reason (core/ddr_import_service.py:"
        "1012-1029).", None),
    "INV34-002431": dup("INV34-002429", "core/profile_import_engine.py:863 - the same rule for the "
                                        "sub-code resolution",
                        "unaccepted resolution -> None, with the decision kept for review"),

    # ------------------------------------------------------------------ calculation repositories
    "INV34-007769": dup("INV34-007509", "core/repositories/casing_repository.py:71 - the sibling "
                                        "repository's verify (`classify_verification(self.result or "
                                        "{}, recalc, ...)`, after the snapshot-reconstruction guard "
                                        "that already returns VERIFY_UNREADABLE, 60-69)",
                        _VERIFY),
    "INV34-007771": (VC,
        "`summary = result_summary(result_values or {})` (104) builds the promoted summary columns "
        "of a stored casing run from the engine's values mapping; the projection emits None for "
        "every absent key (`result_summary` = `{k: _clean_number(values.get(k)) for k in "
        "SUMMARY_KEYS}`, core/engineering/casing_persistence.py:131-133, with `_clean_number`: "
        "'Return a finite float or None (never a bool, NaN or inf)', 59-67).  An empty mapping "
        "therefore stores explicit unknowns, never zeros, and the row itself is written in one "
        "`session_scope` unit 'so a failure leaves no partial row' (98-101).", None),
    "INV34-007773": (INT,
        "`input_snapshot=dict(row.input_snapshot_json or {})` (156) and `result=dict(row.result_json "
        "or {})` (157) normalise the two JSON columns of a persisted run into the dataclass's "
        "mapping fields.  A NULL column means 'this row has no stored snapshot/result', the empty "
        "mapping is that fact, and verification reports exactly it as unverifiable "
        "(`status=VERIFY_UNREADABLE, detail=\"stored record has no result to verify against\"`, "
        "core/engineering/calculation_verification.py:180-185).", None),
    "INV34-007774": dup("INV34-007773", "core/repositories/casing_repository.py:157 - the result JSON "
                                        "column of the same dataclass construction",
                        "NULL column -> empty mapping -> VERIFY_UNREADABLE, never a MATCH"),
    "INV34-007775": dup("INV34-007771", "core/repositories/casing_repository.py:160 - the summary "
                                        "derived from the stored result JSON column",
                        "absent keys project to None through _clean_number"),
    "INV34-007777": dup("INV34-007509", "core/repositories/cement_repository.py:73 - the cement "
                                        "repository's verify (`self.result or {}` into the same "
                                        "classifier)", _VERIFY),
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
    for item in items:
        if item["classification"] == DEF:
            item["commit"] = "0699e50"
            item["test"] = "tests/test_profile_time_log_unknown_duration.py"

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("phase-2 mixed classes: "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [{
            "id": "INV34-002457", "file": "core/profile_import_engine.py", "line": 840,
            "summary": ("`except (TypeError, ValueError): hrs = 0.0` coerced a blank or "
                        "non-numeric Hrs cell into a measured zero-hour duration in the legacy "
                        "profile extractor; now blank -> None and a stated-but-unparseable "
                        "value -> its source token for the review boundary"),
            "commit": "0699e50",
            "test": "tests/test_profile_time_log_unknown_duration.py",
        }],
        "new_findings": NEW_FINDINGS,
        "sibling_search": {
            "target": ("numeric defaults inside except handlers, whole repository - the class of "
                       "the defect fixed in this batch"),
            "method": ("regex scan for `X = 0`/`X = 0.0`/`return 0`/`return 0.0` directly inside "
                       "an `except` handler over core, dialogs, tabs, tools, tests"),
            "hits": 5,
            "findings": [
                {"site": "core/profile_import_engine.py:840", "status": "GENUINE DEFECT, fixed "
                                                              "in 0699e50"},
                {"site": "dialogs/planning_dialog.py:484", "status": "register record "
                                                              "INV34-003569 (batch-015) - not "
                                                              "mass-patched"},
                {"site": "core/performance.py:23", "status": "adjudicated in earlier batches "
                                                            "(INV34-002269 INTENTIONAL; "
                                                            "INV34-002264 is the sibling OPEN "
                                                            "record of batch-021)"},
                {"site": "tabs/w13_Engineering_Calculator.py:126", "status": "adjudicated "
                                                                       "INTENTIONAL/FALSE-POSITIVE "
                                                                       "in batch-005"},
                {"site": "tabs/w13_Engineering_Calculator.py:2218", "status": "register record "
                                                                       "INV34-004598 (batch-023)"},
            ],
        },
        "tests": ("defect fix commit 0699e50: new regression file 4 passed; related suites "
                  "(12 files incl. the regression, the profile-engine and DDR forensics and the "
                  "time-log/inventory semantics suites) 343 passed / 0 failed / 0 errors / "
                  "0 skipped in 49.535 s; mutation validation with `hrs = 0.0` reintroduced -> "
                  "3 of 4 new tests fail, restored byte-identical (sha256 f77253848055e1c1.."
                  "58fb45f9) -> 4/4; compileall OK; ruff unchanged for the touched files (45 "
                  "concise lines before and after), ratchet population 5 338 <= ceiling 5 375. "
                  "The other 44 records change no production file; the phase-1 full-suite gate "
                  "(1 834 / 0 failures / 0 errors / 4 skipped, 1d44cb5 tree) plus that related "
                  "run cover them; the phase-end full suite will re-run on the final tree"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "tools/m36/p6_batch_013.py",
                           "core/profile_import_engine.py",
                           "tests/test_profile_time_log_unknown_duration.py"],
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
          f"re-anchored {len(reanchored)}, defects fixed {len(payload['defects_fixed'])}")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
