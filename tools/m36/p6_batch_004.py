#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-004 (45 HIGH records, classes A/B/C).

Same contract as p6_batch_003.py: every record read at its own site, classified from a quoted
contract; the staleness check is identity-based and refuses to run on an unexplained mismatch.

Re-anchoring in this batch:
* tabs/w7_logistics_Widget.py - five records point at the three assignments the batch-003 fix
  rewrote (verified against ``c2e0016^``); two further records (the id-parsing handler) sit after
  the rewritten block, which the diff proves is a single 8-line -> 26-line hunk at 825-832, i.e. a
  uniform +18 offset for every later line in that file.
* every other file is untouched since the register was built, so the recorded line must match
  exactly.

Also records, in ``new_findings``, a defect found while tracing this batch (mud_ledger.get_history
crashes on the documented unknown-closing case); it is NOT patched here - a fix needs its own
regression and mutation validation, and it is carried as the next action instead of being lost.
"""
from __future__ import annotations

import hashlib
import json
import re
import difflib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-004"
FIX_COMMIT = "c2e0016"      # batch-003 W7 fix (parent blob carries the recorded text)
W7 = "tabs/w7_logistics_Widget.py"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

# file -> the commit that changed it inside this batch cycle; the line map is derived from the real
# diff (difflib opcodes), never hand-computed: a record whose recorded text sits on an *unchanged*
# pre-fix line is re-anchored to that line's new position, and a record whose own line was rewritten
# must be declared in SELF_FIXED (then its text is verified against <commit>^).
# records that point at a line the fix rewrote *because of that very record* (the three-state
# block of the batch-003 W7 defect): verified against the fix's parent revision instead.
SELF_FIXED = {f"INV34-0{n}": W7 for n in ("06022", "06023", "10297", "10298", "10299")}

RECHECK_AGAINST = {
    W7: FIX_COMMIT,                 # batch-003 three-state fix (+18 for everything after 831)
    "core/mud_ledger.py": "3f0cf3e",  # this batch's own get_history/check_continuity fix
}


def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Second register record for the construct adjudicated under {sibling} "
            f"({where}): the rule engine fired once on the `except` line (R-EXC-PASS) and once on "
            f"the `pass` line (R-PASS-EXC) of one handler - or twice on one line - so this id adds "
            f"no independent behaviour. Adjudicated once under {sibling}: {summary}",
            None)


R: dict[str, tuple[str, str, str | None]] = {

    # ===================================================== core/database.py
    "INV34-000283": (INT,
        "`_get_current_user_info` is a lazy property whose only consumer is the audit stamp "
        "(`user_info = self._get_current_user_info` ... `user_id=user_info['user_id'], "
        "username=user_info['username']`, 4150-4158). When core.permissions cannot be imported the "
        "fallback keeps the unknown explicit: `{'user_id': None, 'username': 'system'}` (2598) - "
        "no real person is named and `user_id` stays NULL. No user record named 'system' is created "
        "anywhere in core/ (grep: the only occurrence is this fallback), so it reads as the "
        "conventional non-human actor. Residual (recorded, not a defect claim): attribution "
        "degrades to 'system' whenever the permission layer is unavailable.", None),
    "INV34-006848": (DUP,
        "Same statement as INV34-000283 (core/database.py:2597, `except Exception:` of "
        "`_get_current_user_info`): identical rule and identical recorded text. One behaviour, "
        "adjudicated once under INV34-000283 (the fallback keeps the unknown explicit: user_id "
        "None, username 'system', consumed only by the audit stamp at 4150-4158).", None),
    "INV34-000284": (INT,
        "`release_session` is a best-effort close helper: `try: session.close() except Exception: "
        "pass` (3458-3461). batch 002 already stated the deciding contract for this exact "
        "construct (INV34-001258): a failure to close must not mask the original error, and named "
        "`core/database.py release_session` as the reference implementation. The module closes "
        "sessions best-effort everywhere (3449-3450, 3479-3480, 10278-10279), the session object is "
        "discarded by the caller, and the helper has no call site in the tracked tree (repo-wide "
        "grep finds only the definition), so no live path can be left half-closed by the swallow.",
        None),
    "INV34-000360": (DUP,
        "Same statement as INV34-000284 (core/database.py:3460 in `release_session`): duplicate "
        "record of one handler. Adjudicated once under INV34-000284 (best-effort close; batch 002 "
        "INV34-001258 states the same contract).", None),
    "INV34-006872": (DUP,
        "Same statement as INV34-000284 (core/database.py:3460 in `release_session`): duplicate "
        "record. Adjudicated once under INV34-000284.", None),
    "INV34-000785": (DUP,
        "Rule mis-fire: the recorded line is the keyword argument `entity_id=entity_id,` inside "
        "`log = AuditLog(...)` (10263-10272) and there is no numeric truthiness test at or near it. "
        "The only truthiness expression in that statement is `details[:500] if details else \"\"` "
        "(10270) on a *string*, which is the correct guard for an optional detail text. No "
        "behaviour to adjudicate here.", None),
    "INV34-006868": (VC,
        "`_BCRYPT_AVAILABLE` is the optional-import capability flag already adjudicated in batch "
        "002 (INV34-000717/000726): a boolean set by the import guard, so truthiness is the correct "
        "test, and in production the missing flag raises "
        "`CredentialLifecycleError(\"BCRYPT_REQUIRED\", ...)` on the next line (3329). The flag "
        "cannot legitimately be 0.", None),

    # ===================================================== torque_drag engine
    "INV34-001661": (VC,
        "`area = math.pi / 4.0 * (od**2 - (id_ or 0.0) ** 2)` (632): `el[\"id_in\"]` is a float by "
        "construction - the element builder coalesces it (`id_ = optional_number(comp.get(\"id\", "
        "comp.get(\"id_in\")), ...) or 0.0`, 465; the sibling path repeats it, 646) - so the inner "
        "`or 0.0` is a redundant defensive coalesce that cannot change any value. Candidate "
        "observed and NOT patched (no register record): the upstream default at 465 makes an "
        "unknown BHA id behave as a solid bar for axial stretch; the engine documents "
        "unknown-wellbore handling for buckling (590 'wellbore_id_in not provided - buckling not "
        "checked') but not for stretch, so changing it would be a domain ruling, not a proven fix.",
        None),
    "INV34-009615": (DUP,
        "Same statement as INV34-001661 (core/engineering/engines/torque_drag.py:632, rule pair "
        "R-DEF-VALUE-PATH/or-zero vs /numeric-coalesce on one line). Adjudicated once under "
        "INV34-001661: `id_in` is always a float (coalesced at 465/646), so the expression is a "
        "no-op.", None),
    "INV34-001665": (VC,
        "`wob = (wob_klbf_value or 0.0) * 1000.0` (373): the parameter is declared "
        "`wob_klbf: float = 0.0` in the signature (356), so 0.0 is the declared default, not a "
        "fabricated measurement. `optional_number` (core/engineering/result.py:119-129) maps only "
        "None/'' to None and raises on invalid or non-finite input, and a supplied 0.0 coalesces to "
        "0.0 unchanged; negative values already raise at 371-372.", None),
    "INV34-009612": (DUP,
        "Same statement as INV34-001665 (core/engineering/engines/torque_drag.py:373, rule pair "
        "R-DEF-VALUE-PATH/or-zero vs /numeric-coalesce). Adjudicated once under INV34-001665: 0.0 is "
        "the declared parameter default and invalid values raise before the coalesce.", None),

    # ===================================================== kill sheet
    "INV34-001768": (VC,
        "`tvd_ft=(_num(tvd_m) or 0.0) * FT_PER_M` (286): the 0.0 default cannot reach a computed "
        "result because the same builder tracks which required inputs were absent - "
        "`missing_inputs = tuple(name for name, value in required_raw.items() if _num(value) is "
        "None)` (272, covering tvd_m/md_m/shoe_tvd_m/hole_size_in/mw_pcf/frac_gradient/sidpp/sicp/"
        "scr1/pit_gain/pump_output, 259-271) - and `compute_kill_sheet` refuses with the documented "
        "reason: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. "
        "absent SIDPP becomes \"no overpressure\"). Refuse instead.' (436-443).", None),
    "INV34-007520": (DUP,
        "Same statement as INV34-001768 (core/engineering/well_control_kill_sheet.py:286, "
        "duplicate rule/line). Adjudicated once under INV34-001768: the missing-input gate at 272 + "
        "the refusal at 436-443 keeps the 0.0 default out of every computed result.", None),
    "INV34-001754": (VC,
        "`md_ft=(_num(md_m) or 0.0) * FT_PER_M` (287): same builder and same refusal contract as "
        "INV34-001768 - md_m is in `required_raw` (261) so an absent value lands in "
        "`missing_inputs` (272) and `compute_kill_sheet` returns "
        "`KillSheetResult(success=False, error=...missing required kill-sheet inputs...)` (436-443) "
        "instead of computing from the defaulted 0.0.", None),
    "INV34-007521": (DUP,
        "Same statement as INV34-001754 (core/engineering/well_control_kill_sheet.py:287, duplicate "
        "rule/line). Adjudicated once under INV34-001754.", None),

    # ===================================================== optional engine probe
    "INV34-001437": (VC,
        "`available()` is the optional-dependency probe for the external torque_drag engine: "
        "`try: import torque_drag ... return True except ImportError: return False` (6-11). False "
        "is the documented 'not installed' answer, and the caller refuses to compute rather than "
        "fabricating a result - `if not TorqueDragAdapter.available(): return None` (14-16). The "
        "ImportError is the exact condition being tested, so swallowing it is the check itself.",
        None),

    # ===================================================== anti-collision legacy helper
    "INV34-001557": (VC,
        "`_euclidean_distance` (58-66) is documented as 'Basic 3D distance retained for legacy "
        "callers' and has no caller anywhere in the tracked tree (repo-wide `grep -rn "
        "\"_euclidean_distance\"` finds only the definition), so `return float(\"inf\")` cannot "
        "reach a consumer as a fabricated distance: it is the explicit sentinel of an unused legacy "
        "helper, next to the engine's strict `require_number` path.", None),

    # ===================================================== import quality / router
    "INV34-002018": (VC,
        "`confidence = float(confidence or 0)` (780) inside `decision_for_confidence`, whose "
        "docstring states 'Conservative decision policy for automatic import' (776). An absent or "
        "unparseable confidence becomes 0.0 and therefore `REJECT` (783) - the fail-closed end of "
        "the policy, never ACCEPT. No legitimate confidence value is altered (0 is the floor of the "
        "scale).", None),
    "INV34-002045": (VC,
        "`_sheet_names` (62-72) has no caller in the tracked tree (repo-wide `grep -rn "
        "\"_sheet_names\"` finds only its definition at core/import_router.py:62), so its "
        "`except Exception: return []` cannot be mistaken for 'the workbook has no sheets' by any "
        "consumer; the empty list is simply the unused helper's failure value.", None),

    # ===================================================== mud ledger
    "INV34-002210": (VC,
        "`usages = [float(m.used or 0) for m in mats_sorted]` (207): the BulkMaterials model states "
        "the rule at the column - '# received/used absent = no movement (0.0) - established "
        "daily-report convention, distinct from the opening-stock trichotomy.' with "
        "`received = Column(Float, default=0.0)` / `used = Column(Float, default=0.0)` "
        "(core/database.py:1277-1280) - so the coalesce implements the documented model semantics "
        "rather than inventing a measurement, and it is deliberately distinct from the "
        "opening-stock trichotomy (1271-1275).", None),
    "INV34-002209": (VC,
        "`received = [float(m.received or 0) for m in mats_sorted]` (209): same documented model "
        "rule as INV34-002210 (core/database.py:1277-1280, 'absent = no movement (0.0)').", None),
    "INV34-002211": (VC,
        "`received=float(r.received or 0)` (98) in `get_ledger_for_well`: the same model convention "
        "(core/database.py:1277-1280) applied when the ledger row is built, and the resulting "
        "LedgerEntry documents the trichotomy it preserves for the *opening* "
        "('None = opening not reported (missing) ... never silently replaced by 0', "
        "core/mud_ledger.py:24-27).", None),
    "INV34-002212": (VC,
        "`used=float(r.used or 0)` (99): identical to INV34-002211 - the documented 'absent = no "
        "movement (0.0)' convention for received/used while the opening keeps its NULL trichotomy.",
        None),

    # ===================================================== operations intelligence
    "INV34-002230": (VC,
        "`depths = [float(item.depth_2400 or 0) for item in reports if item.depth_2400 is not "
        "None]` (50): the comprehension already excludes the unknown case, so `or 0` only re-states "
        "0.0 for a value that is genuinely zero - the series is a real depth either way, and no "
        "unknown sample is turned into a measurement.", None),

    # ===================================================== value normalizer
    "INV34-003023": (VC,
        "`int(match.group(3) or 0)` (284) is the correct handling of the regex's *optional* seconds "
        "group `(?::(\\d{2}))?` (283): an absent group is None and becomes 0 seconds, while the "
        "string \"00\" is truthy and stays 0. The alternative (`int(None)`) would raise; the "
        "minute/second range check follows immediately (285-286).", None),

    # ===================================================== w12 analysis
    "INV34-004409": (VC,
        "`cats[cat] = cats.get(cat, 0) + h` (1523) is an addition identity for a category key that "
        "is seen for the first time, not a measurement default: the loop separates the unknown case "
        "explicitly (`if h is None: unknown_count += 1`, 1520-1522) under the comment '0.0 is a "
        "real fact and is summed/displayed as 0.0.' (1517).", None),

    # ===================================================== w7 (the fixed block + its siblings)
    "INV34-006022": (DUP,
        "Duplicate of INV34-006021 (fixed in c2e0016, adjudicated in batch 003): the recorded "
        "statement is the second assignment of the same three-state computation "
        "(`received = float(received_item.text() or 0)`), which the fix rewrote to `_known()`. The "
        "defect, its contracts and its regression (tests/test_bulk_stock_three_state_smoke.py, "
        "mutation-killed) are recorded once under INV34-006021.", None),
    "INV34-006023": (DUP,
        "Duplicate of INV34-006021 (fixed in c2e0016, batch 003): third assignment of the same "
        "computation (`used = float(used_item.text() or 0)`), rewritten by the same fix. Counted "
        "once under INV34-006021.", None),
    "INV34-010297": (DUP,
        "Duplicate of INV34-006021 (fixed in c2e0016, batch 003): same recorded text "
        "(`initial = float(initial_item.text() or 0)`), same line 825, rule "
        "R-DEF-VALUE-PATH/float-or-zero-strict instead of /or-zero. One statement, one defect, one "
        "fix; adjudicated under INV34-006021.", None),
    "INV34-010298": (DUP,
        "Duplicate of INV34-006021 (fixed in c2e0016, batch 003): same recorded text as "
        "INV34-006022/010297 on line 826. Adjudicated once under INV34-006021.", None),
    "INV34-010299": (DUP,
        "Duplicate of INV34-006021 (fixed in c2e0016, batch 003): same recorded text as "
        "INV34-006023 on line 827. Adjudicated once under INV34-006021.", None),
    "INV34-006213": (INT,
        "`except ValueError: pass` around `material_data[\"id\"] = int(id_item.text())` "
        "(1197-1201): the id cell is the hidden primary-key column (`self.bulk_table.setColumnHidden"
        "(0, True)`, 763) and is written only by the application (`QTableWidgetItem(str(item[\"id\"]))` "
        "on load, `str(result)` after save, 1208-1209), so the handler is defensive code on a value "
        "the operator cannot type; a failed parse leaves the payload without an id, which "
        "`save_bulk_material` treats as the insert path. Residual (recorded, not reachable in the "
        "delivered UI): if the id cell ever held non-numeric text, the row would be inserted as a "
        "new record instead of updating the existing one.", None),
    "INV34-008456": (DUP,
        "Same handler as INV34-006213 (tabs/w7_logistics_Widget.py:1200/1201 in the current tree, "
        "recorded 1182/1183): the register records the `except ValueError:` line and this id the "
        "`pass` that follows it. Adjudicated once under INV34-006213.", None),

    # ===================================================== w8 safety
    "INV34-006221": (VC,
        "`volume_by_type[wt] = volume_by_type.get(wt,0) + vol` (595) is an addition identity for a "
        "first-seen waste type, and the report gate keeps partial sums out of the output: "
        "`volume_text = f\"{total_volume:.1f}\" if valid_volumes and valid_volumes == "
        "self.waste_table.rowCount() else \"Unknown (incomplete records)\"` (602). No defaulted "
        "volume is presented as a measurement.", None),
    "INV34-006220": (VC,
        "`volume_by_method[wm] = volume_by_method.get(wm,0) + vol` (596): same accumulator identity "
        "as INV34-006221 under the same completeness gate (602 'Unknown (incomplete records)').",
        None),
    "INV34-006285": (INT,
        "`except (AttributeError, TypeError, ValueError): pass  # incomplete waste row` (599-600): "
        "the swallowed row is excluded from the totals *and* the totals are refused when the row "
        "count does not match - `valid_volumes == self.waste_table.rowCount()` (602) - with pH "
        "reported as 'Unknown' when no value was supplied (601, 603). A partial sum is therefore "
        "never shown as a complete one.", None),
    "INV34-006284": (INT,
        "`except (AttributeError, TypeError, ValueError): pass  # row without parseable last-test "
        "date` (299-300) in `calculate_bop_schedule`: only rows with a valid QDate are assessed "
        "(283-287) and the message explicitly reports the gap - `if assessed_count == 0 or "
        "assessed_count != self.bop_stack_table.rowCount(): message += \"NOT ASSESSED: missing "
        "last-test dates for some/all components\"` (306-307). The handler is also unreachable in "
        "practice (QDate.fromString/addDays and QTableWidgetItem construction do not raise in this "
        "flow). Residual (recorded, not a defect claim): a not-assessed row keeps its previous "
        "highlight and next-due cell while the message says NOT ASSESSED.", None),
    "INV34-006257": (VC,
        "`data = (self.db.get_safety_report(well_id, report_id=report_id) or {}) if well_id else {}` "
        "(401): a missing report becomes an empty mapping which feeds "
        "`_load_nullable_safety_fields`, whose documented contract is 'Keep source NULL distinct "
        "from a widget's minimum display value.' - it records `missing = value is None` in "
        "`owner._missing_safety_fields`, sets `setSpecialValueText(\"Not supplied\")` and "
        "`setMinimum(-1)` (tabs/w8_Safety_Widget.py:23-37), so an absent value is shown as Not "
        "supplied rather than as 0.", None),
    "INV34-006273": (VC,
        "`report_data = (self.db.get_safety_report(well_id, report_id=report_id) or {}) if well_id "
        "else {}` (676): same contract as INV34-006257 (the loader keeps NULL distinct from the "
        "widget minimum, 'Not supplied').", None),
    "INV34-006260": (VC,
        "`if record_id:` (384): `save_safety_report` commits and `return record_id`, and its "
        "`except` path returns without an id (core/database.py:7698-7738), so the truth test is "
        "exactly the documented success test for a primary key (never 0). The failure branch is "
        "handled explicitly by the caller (reviews/message + SaveOutcome, 385-390).", None),
    "INV34-006276": (VC,
        "`if record_id:` (659): same contract as INV34-006260 - `save_safety_report` returns the "
        "committed row id or nothing, and the caller turns that into the save outcome (660-665).",
        None),

    # ===================================================== w9 services
    "INV34-006349": (VC,
        "`if self.equipment_id:` (716): the id comes from the selected row's hidden primary-key "
        "cell (`equipment_id = int(self.equipment_table.item(selected_row, 0).text())`, 444/455) or "
        "from the dialog's optional constructor argument (default None, 589-594). A falsy value "
        "therefore means 'new record', which is exactly the branch that omits `id` from the payload "
        "so `save_equipment_log` inserts instead of updating.", None),
    "INV34-006366": (VC,
        "`if self.note_id:` (574): same shape as INV34-006349 - the id is the selected row's primary "
        "key (337/348) or the constructor's optional argument (default None, 496-501), so falsy "
        "means insert and the branch adds `id` only for the update path.", None),

    # ===================================================== engineering core guards
    "INV34-007440": (INT,
        "`if not flow_rate_gpm or not pressure_drop_psi or not bit_size_in: raise "
        "MissingInputError(\"flow_rate, pressure_drop, bit_size required for HSI\")` (410-411): a "
        "fail-loud required-input guard, not a silent default - the engine raises instead of "
        "returning a number computed from absent inputs, and the wrapper turns that into a blank "
        "cell (core/managers.py:415-426 documents the HSI/SPP screening caveat and returns None on "
        "failure; tabs/w3_drilling_report.calculate_hsi logs and leaves the field unset). Residual "
        "(recorded, product-level): a physically zero rate is treated as a missing input, because "
        "the spin boxes cannot distinguish 0 from 'not supplied'.", None),
    "INV34-007443": (INT,
        "`if not flow_rate_gpm or not hole_id_in or not pipe_od_in: raise "
        "MissingInputError(\"flow_rate, hole_id, pipe_od required\")` (505-506): same fail-loud "
        "contract as INV34-007440 - the engine refuses to compute an annular velocity from absent "
        "inputs, and the wrapper reports `status` instead of presenting a number "
        "(core/managers.py:428-435, which batch 002 recorded as a domain decision at INV34-... "
        "managers.py:434). Residual (recorded, product-level): a physically zero rate is treated as "
        "a missing input.", None),
}

NEW_FINDINGS = [
    {
        "id": "NEW-P6-001",
        "file": "core/mud_ledger.py",
        "line": 208,
        "severity": "HIGH",
        "class": "B (data integrity / robustness)",
        "trigger": ("`MudChemicalLedger.get_history` -> `stocks = [float(m.closing_stock) for m in "
                    "mats_sorted]` where `LedgerEntry.closing_stock` is a documented Optional that "
                    "returns None whenever the opening was not reported"),
        "observed": ("float(None) raises TypeError, so the whole history call fails (and with it "
                     "the AI tool `check_mud_ledger`, which returns entries/alerts/history from the "
                     "same call, core/ai_tools.py:283-293) as soon as one material has an entry "
                     "with an unknown opening."),
        "deciding_contract": ("core/mud_ledger.py:24-27 - 'opening_stock trichotomy: None = "
                              "opening not reported (missing) ... An unknown opening propagates to "
                              "an unknown closing (None) - it is never silently replaced by 0.'; "
                              "the same module handles that case explicitly elsewhere: "
                              "`if closing is None or entry.opening_stock is None:` with the "
                              "comment 'Unknown opening/closing: no stock judgment is possible.' "
                              "(140-141); the sibling lines in the same list do coalesce "
                              "(`float(m.used or 0)`, 207/209)."),
        "reachable": ("yes - `get_ledger_for_well` sets `opening = previous_closing` (92), which is "
                      "None for the first report of a material whose opening was not reported, and "
                      "the Batch-materials model documents NULL openings as a normal state "
                      "(core/database.py:1271-1275)."),
        "status": "FIXED in this batch (dedicated commit, not mixed with the audit evidence)",
        "fix": ("`stocks` keeps the unknown as None (series stays aligned with `dates`, so the "
                "chart breaks the line instead of shifting); `closing_stock`/`days_remaining` are "
                "None for an unknown last stock instead of a fabricated 0-day runway; an explicit "
                "0.0 still reads as 0.0. Same-class site in the same module "
                "(`check_continuity` 247-248, `abs(curr.opening_stock - expected_opening)` with "
                "the previous closing None) skips the pair - validate() already states no stock "
                "judgment is possible. The pre-existing `avg_consumption == 0 -> 0` rule was "
                "deliberately left alone (separate product semantics)."),
        "commit": "3f0cf3e",
        "test": ("tests/test_mud_ledger_unknown_stock_history.py - 5 tests over the facade and the "
                 "AI-tool path (success=True, entries+alerts preserved, unknown last stock -> "
                 "days_remaining None, explicit zero stays 0.0)"),
        "validation": ("mutation-validated: M1 pre-fix code -> TypeError 'float() argument must be "
                       "a string or a real number, not NoneType', tool result "
                       "{'success': False, 'error': 'float() ... NoneType'}; M2 unknown->0.0 -> "
                       "'assert [0.0, -30.0] == [None, -30.0]'; M3 reverted continuity guard -> "
                       "TypeError at core/mud_ledger.py:267; each mutation fails the suite and the "
                       "file is restored byte-identical (sha256 183a6cf5...6de828f)"),
        "next_action": ("none for this defect; the AI tool/`get_history` path now degrades to "
                        "'unknown' instead of failing"),
    }
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def git_show(rev: str, path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed")
    return out.stdout.decode("utf-8", "replace").splitlines()


def symbol_body(lines: list[str], symbol: str) -> tuple[int, int]:
    name = (symbol or "").split(".")[-1]
    start = None
    for i, line in enumerate(lines, 1):
        if re.match(rf"\s*def {re.escape(name)}\s*\(", line):
            start = i
            break
    if start is None:
        raise SystemExit(f"symbol {symbol!r} not found")
    indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
    for i in range(start, len(lines)):
        line = lines[i]
        if line.strip() and not line.startswith(" " * (indent + 1)):
            return start, i
    return start, len(lines)


def offset_proof(path: str) -> int:
    """Prove from the real diff that one hunk covers the reported region, and return its delta.

    The delta is only applied to records *after* the hunk; anything inside it is a text change, not
    a shift, and is handled by the exact-text branches instead.
    """
    commit, old_start, old_count, new_start, new_count = OFFSET_REANCHOR[path]
    diff = subprocess.run(["git", "diff", "-U1", f"{commit}^", commit, "--", path],
                          cwd=ROOT, capture_output=True, check=True).stdout.decode()
    hunks = re.findall(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", diff, re.M)
    if len(hunks) != 1:
        raise SystemExit(f"expected exactly one hunk for {path}, found {len(hunks)}: {hunks}")
    got = hunks[0]
    got = (int(got[0]), int(got[1] or 1), int(got[2]), int(got[3] or 1))
    if got != (old_start, old_count, new_start, new_count):
        raise SystemExit(f"unexpected hunk for {path}: {got} (expected "
                         f"{(old_start, old_count, new_start, new_count)})")
    return new_count - old_count


def line_map(commit: str, path: str, current: list[str]) -> dict[int, int]:
    """Map pre-fix line numbers to current ones for lines the fix left untouched."""
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
    maps: dict[str, dict[int, int]] = {}
    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        if path not in cache:
            cache[path] = (ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines()
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

        if record["id"] in SELF_FIXED:
            # The recorded line itself was rewritten by the fix that this very record found.
            continue

        if path not in maps:
            maps[path] = line_map(commit, path, lines)
        new_line = maps[path].get(line)
        start, end = symbol_body(lines, record.get("symbol", ""))
        if new_line is None:
            problems.append(f"{record['id']}: {path}:{line} was rewritten by {commit} but the "
                            f"record is not declared SELF_FIXED")
            continue
        if _norm(lines[new_line - 1]) != _norm(expected) or not (start <= new_line <= end):
            problems.append(f"{record['id']}: re-anchor {path}:{line} -> {new_line} failed "
                            f"({lines[new_line - 1].strip()!r}, symbol {record.get('symbol')} "
                            f"{start}-{end})")
            continue
        reanchored.append((record["id"], path, line, new_line))
    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        raise SystemExit(2)
    return reanchored


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
        "class": ("mixed HIGH (A safety/authorization/mutation, B data integrity, C engineering) - "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [
            "NEW-P6-001 core/mud_ledger.py:208 — `float(None)` on a documented unknown closing "
            "broke `get_history` and the `check_mud_ledger` AI tool; fixed in 3f0cf3e with "
            "tests/test_mud_ledger_unknown_stock_history.py (mutation-validated), plus the "
            "same-class `check_continuity` None crash (core/mud_ledger.py:247-248).",
        ],
        "new_findings": NEW_FINDINGS,
        "tests": ("focused ledger/inventory/bulk/mud slice: 163 tests, 0 failures, 0 errors, 0 "
                  "skipped (24.795 s, JUnit /tmp/mudslice.xml); the new regression file is 5/5 and "
                  "mutation-validated (pre-fix code -> TypeError; unknown->0.0 -> 'assert "
                  "[0.0, -30.0] == [None, -30.0]'; reverted continuity guard -> TypeError at "
                  "core/mud_ledger.py:267 - each mutation fails, restored byte-identical "
                  "183a6cf5...6de828f); ruff clean on core/mud_ledger.py and the new test file"),
        "head": record_head(),
        "commit": "3f0cf3e",   # the batch's code commit (its own defect fix); evidence commit is
                               # recorded separately by tools/m36/p6_stamp.py
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           f"docs/audits/m36-evidence/{BATCH}.md",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m36-evidence/P6_PROGRESS.md",
                           "tools/m36/p6_batch_004.py"],
        "staleness": {
            "checked": len(batch), "stale": 0, "re_anchored": len(reanchored),
            "method": ("recorded text must match the current line exactly; for a file this batch "
                       "cycle changed (w7 via c2e0016, core/mud_ledger.py via 3f0cf3e) the recorded "
                       "text is first verified against <commit>^ at the recorded line, then the "
                       "record is re-anchored through the line map derived from the real diff "
                       "(difflib equal-blocks), and the recorded line itself must either be "
                       "unchanged (re-anchored) or declared SELF_FIXED (the fix that this record "
                       "found); nothing is skipped or hand-adjusted"),
            "re_anchored_items": [{"id": i, "file": f, "recorded_line": a, "current_line": b}
                                  for i, f, a, b in reanchored],
        },
        "method": ("each record read at its own site in the current tree; the deciding contract is "
                   "quoted in `evidence`; second records of one handler are adjudicated once and "
                   "say so"),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, staleness 0, "
          f"re-anchored {len(reanchored)}, new findings {len(NEW_FINDINGS)}")
    print("by classification:", payload["by_classification"])
    return 0


def record_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode().strip()


if __name__ == "__main__":
    sys.exit(main())
