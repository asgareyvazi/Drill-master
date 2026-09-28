# P6 p6-batch-004 — class mixed HIGH (A safety/authorization/mutation, B data integrity, C engineering) - A:17, B:20, C:8

records **45** over **36** sites · VERIFIED-CORRECT: 24 · DUPLICATE/FALSE-POSITIVE: 14 · INTENTIONAL: 7

## Defects fixed

- NEW-P6-001 core/mud_ledger.py:208 — `float(None)` on a documented unknown closing broke `get_history` and the `check_mud_ledger` AI tool; fixed in 3f0cf3e with tests/test_mud_ledger_unknown_stock_history.py (mutation-validated), plus the same-class `check_continuity` None crash (core/mud_ledger.py:247-248).

## New findings (found while adjudicating this batch)

### NEW-P6-001 — `core/mud_ledger.py:208` (HIGH, class B (data integrity / robustness))

- **Trigger:** `MudChemicalLedger.get_history` -> `stocks = [float(m.closing_stock) for m in mats_sorted]` where `LedgerEntry.closing_stock` is a documented Optional that returns None whenever the opening was not reported
- **Observed:** float(None) raises TypeError, so the whole history call fails (and with it the AI tool `check_mud_ledger`, which returns entries/alerts/history from the same call, core/ai_tools.py:283-293) as soon as one material has an entry with an unknown opening.
- **Deciding contract:** core/mud_ledger.py:24-27 - 'opening_stock trichotomy: None = opening not reported (missing) ... An unknown opening propagates to an unknown closing (None) - it is never silently replaced by 0.'; the same module handles that case explicitly elsewhere: `if closing is None or entry.opening_stock is None:` with the comment 'Unknown opening/closing: no stock judgment is possible.' (140-141); the sibling lines in the same list do coalesce (`float(m.used or 0)`, 207/209).
- **Reachable:** yes - `get_ledger_for_well` sets `opening = previous_closing` (92), which is None for the first report of a material whose opening was not reported, and the Batch-materials model documents NULL openings as a normal state (core/database.py:1271-1275).
- **Status:** FIXED in this batch (dedicated commit, not mixed with the audit evidence)
- **Fix:** `stocks` keeps the unknown as None (series stays aligned with `dates`, so the chart breaks the line instead of shifting); `closing_stock`/`days_remaining` are None for an unknown last stock instead of a fabricated 0-day runway; an explicit 0.0 still reads as 0.0. Same-class site in the same module (`check_continuity` 247-248, `abs(curr.opening_stock - expected_opening)` with the previous closing None) skips the pair - validate() already states no stock judgment is possible. The pre-existing `avg_consumption == 0 -> 0` rule was deliberately left alone (separate product semantics).
- **Commit:** 3f0cf3e
- **Test:** tests/test_mud_ledger_unknown_stock_history.py - 5 tests over the facade and the AI-tool path (success=True, entries+alerts preserved, unknown last stock -> days_remaining None, explicit zero stays 0.0)
- **Validation:** mutation-validated: M1 pre-fix code -> TypeError 'float() argument must be a string or a real number, not NoneType', tool result {'success': False, 'error': 'float() ... NoneType'}; M2 unknown->0.0 -> 'assert [0.0, -30.0] == [None, -30.0]'; M3 reverted continuity guard -> TypeError at core/mud_ledger.py:267; each mutation fails the suite and the file is restored byte-identical (sha256 183a6cf5...6de828f)
- **Next action:** none for this defect; the AI tool/`get_history` path now degrades to 'unknown' instead of failing

## INV34-000283 — `core/database.py:2597`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class B)
- **Symbol:** `DatabaseManager._get_current_user_info`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_get_current_user_info` is a lazy property whose only consumer is the audit stamp (`user_info = self._get_current_user_info` ... `user_id=user_info['user_id'], username=user_info['username']`, 4150-4158). When core.permissions cannot be imported the fallback keeps the unknown explicit: `{'user_id': None, 'username': 'system'}` (2598) - no real person is named and `user_id` stays NULL. No user record named 'system' is created anywhere in core/ (grep: the only occurrence is this fallback), so it reads as the conventional non-human actor. Residual (recorded, not a defect claim): attribution degrades to 'system' whenever the permission layer is unavailable.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-000284 — `core/database.py:3460`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class B)
- **Symbol:** `DatabaseManager.release_session`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `release_session` is a best-effort close helper: `try: session.close() except Exception: pass` (3458-3461). batch 002 already stated the deciding contract for this exact construct (INV34-001258): a failure to close must not mask the original error, and named `core/database.py release_session` as the reference implementation. The module closes sessions best-effort everywhere (3449-3450, 3479-3480, 10278-10279), the session object is discarded by the caller, and the helper has no call site in the tracked tree (repo-wide grep finds only the definition), so no live path can be left half-closed by the swallow.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-000360 — `core/database.py:3460`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class B)
- **Symbol:** `DatabaseManager.release_session`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Same statement as INV34-000284 (core/database.py:3460 in `release_session`): duplicate record of one handler. Adjudicated once under INV34-000284 (best-effort close; batch 002 INV34-001258 states the same contract).
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-000785 — `core/database.py:10268`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class B)
- **Symbol:** `DatabaseManager.log_audit`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Rule mis-fire: the recorded line is the keyword argument `entity_id=entity_id,` inside `log = AuditLog(...)` (10263-10272) and there is no numeric truthiness test at or near it. The only truthiness expression in that statement is `details[:500] if details else ""` (10270) on a *string*, which is the correct guard for an optional detail text. No behaviour to adjudicate here.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001437 — `core/engineering/adapters/torque_drag_adapter.py:10`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class C)
- **Symbol:** `TorqueDragAdapter.available`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `available()` is the optional-dependency probe for the external torque_drag engine: `try: import torque_drag ... return True except ImportError: return False` (6-11). False is the documented 'not installed' answer, and the caller refuses to compute rather than fabricating a result - `if not TorqueDragAdapter.available(): return None` (14-16). The ImportError is the exact condition being tested, so swallowing it is the check itself.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001557 — `core/engineering/engines/anti_collision.py:64`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class C)
- **Symbol:** `AntiCollisionEngine._euclidean_distance`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_euclidean_distance` (58-66) is documented as 'Basic 3D distance retained for legacy callers' and has no caller anywhere in the tracked tree (repo-wide `grep -rn "_euclidean_distance"` finds only the definition), so `return float("inf")` cannot reach a consumer as a fabricated distance: it is the explicit sentinel of an unused legacy helper, next to the engine's strict `require_number` path.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001661 — `core/engineering/engines/torque_drag.py:632`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `TorqueDragEngine._axial_stretch`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `area = math.pi / 4.0 * (od**2 - (id_ or 0.0) ** 2)` (632): `el["id_in"]` is a float by construction - the element builder coalesces it (`id_ = optional_number(comp.get("id", comp.get("id_in")), ...) or 0.0`, 465; the sibling path repeats it, 646) - so the inner `or 0.0` is a redundant defensive coalesce that cannot change any value. Candidate observed and NOT patched (no register record): the upstream default at 465 makes an unknown BHA id behave as a solid bar for axial stretch; the engine documents unknown-wellbore handling for buckling (590 'wellbore_id_in not provided - buckling not checked') but not for stretch, so changing it would be a domain ruling, not a proven fix.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001665 — `core/engineering/engines/torque_drag.py:373`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `TorqueDragEngine.calculate`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `wob = (wob_klbf_value or 0.0) * 1000.0` (373): the parameter is declared `wob_klbf: float = 0.0` in the signature (356), so 0.0 is the declared default, not a fabricated measurement. `optional_number` (core/engineering/result.py:119-129) maps only None/'' to None and raises on invalid or non-finite input, and a supplied 0.0 coalesces to 0.0 unchanged; negative values already raise at 371-372.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001754 — `core/engineering/well_control_kill_sheet.py:287`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `md_ft=(_num(md_m) or 0.0) * FT_PER_M` (287): same builder and same refusal contract as INV34-001768 - md_m is in `required_raw` (261) so an absent value lands in `missing_inputs` (272) and `compute_kill_sheet` returns `KillSheetResult(success=False, error=...missing required kill-sheet inputs...)` (436-443) instead of computing from the defaulted 0.0.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001768 — `core/engineering/well_control_kill_sheet.py:286`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `tvd_ft=(_num(tvd_m) or 0.0) * FT_PER_M` (286): the 0.0 default cannot reach a computed result because the same builder tracks which required inputs were absent - `missing_inputs = tuple(name for name, value in required_raw.items() if _num(value) is None)` (272, covering tvd_m/md_m/shoe_tvd_m/hole_size_in/mw_pcf/frac_gradient/sidpp/sicp/scr1/pit_gain/pump_output, 259-271) - and `compute_kill_sheet` refuses with the documented reason: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002018 — `core/import_quality.py:780`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `decision_for_confidence`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `confidence = float(confidence or 0)` (780) inside `decision_for_confidence`, whose docstring states 'Conservative decision policy for automatic import' (776). An absent or unparseable confidence becomes 0.0 and therefore `REJECT` (783) - the fail-closed end of the policy, never ACCEPT. No legitimate confidence value is altered (0 is the floor of the scale).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002045 — `core/import_router.py:71`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class B)
- **Symbol:** `_sheet_names`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_sheet_names` (62-72) has no caller in the tracked tree (repo-wide `grep -rn "_sheet_names"` finds only its definition at core/import_router.py:62), so its `except Exception: return []` cannot be mistaken for 'the workbook has no sheets' by any consumer; the empty list is simply the unused helper's failure value.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002209 — `core/mud_ledger.py:209`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `MudChemicalLedger.get_history`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `received = [float(m.received or 0) for m in mats_sorted]` (209): same documented model rule as INV34-002210 (core/database.py:1277-1280, 'absent = no movement (0.0)').
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002210 — `core/mud_ledger.py:207`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `MudChemicalLedger.get_history`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `usages = [float(m.used or 0) for m in mats_sorted]` (207): the BulkMaterials model states the rule at the column - '# received/used absent = no movement (0.0) - established daily-report convention, distinct from the opening-stock trichotomy.' with `received = Column(Float, default=0.0)` / `used = Column(Float, default=0.0)` (core/database.py:1277-1280) - so the coalesce implements the documented model semantics rather than inventing a measurement, and it is deliberately distinct from the opening-stock trichotomy (1271-1275).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002211 — `core/mud_ledger.py:98`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `MudChemicalLedger.get_ledger_for_well`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `received=float(r.received or 0)` (98) in `get_ledger_for_well`: the same model convention (core/database.py:1277-1280) applied when the ledger row is built, and the resulting LedgerEntry documents the trichotomy it preserves for the *opening* ('None = opening not reported (missing) ... never silently replaced by 0', core/mud_ledger.py:24-27).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002212 — `core/mud_ledger.py:99`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `MudChemicalLedger.get_ledger_for_well`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `used=float(r.used or 0)` (99): identical to INV34-002211 - the documented 'absent = no movement (0.0)' convention for received/used while the opening keeps its NULL trichotomy.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002230 — `core/operations_intelligence.py:50`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `OperationsIntelligenceService.analyze_well`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `depths = [float(item.depth_2400 or 0) for item in reports if item.depth_2400 is not None]` (50): the comprehension already excludes the unknown case, so `or 0` only re-states 0.0 for a value that is genuinely zero - the series is a real depth either way, and no unknown sample is turned into a measurement.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003023 — `core/value_normalizer.py:284`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class B)
- **Symbol:** `ValueNormalizer.to_duration`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `int(match.group(3) or 0)` (284) is the correct handling of the regex's *optional* seconds group `(?::(\d{2}))?` (283): an absent group is None and becomes 0 seconds, while the string "00" is truthy and stays 0. The alternative (`int(None)`) would raise; the minute/second range check follows immediately (285-286).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-004409 — `tabs/w12_Analysis.py:1523`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `numeric-get-default` (HIGH, class B)
- **Symbol:** `AnalysisWidget.get_npt_data`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `cats[cat] = cats.get(cat, 0) + h` (1523) is an addition identity for a category key that is seen for the first time, not a measurement default: the loop separates the unknown case explicitly (`if h is None: unknown_count += 1`, 1520-1522) under the comment '0.0 is a real fact and is summed/displayed as 0.0.' (1517).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006022 — `tabs/w7_logistics_Widget.py:826`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class A)
- **Symbol:** `FuelWaterTab.update_bulk_stock_for_row`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** Duplicate of INV34-006021 (fixed in c2e0016, adjudicated in batch 003): the recorded statement is the second assignment of the same three-state computation (`received = float(received_item.text() or 0)`), which the fix rewrote to `_known()`. The defect, its contracts and its regression (tests/test_bulk_stock_three_state_smoke.py, mutation-killed) are recorded once under INV34-006021.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006023 — `tabs/w7_logistics_Widget.py:827`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class A)
- **Symbol:** `FuelWaterTab.update_bulk_stock_for_row`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** Duplicate of INV34-006021 (fixed in c2e0016, batch 003): third assignment of the same computation (`used = float(used_item.text() or 0)`), rewritten by the same fix. Counted once under INV34-006021.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006213 — `tabs/w7_logistics_Widget.py:1182`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `FuelWaterTab.save_bulk_materials_to_db`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `except ValueError: pass` around `material_data["id"] = int(id_item.text())` (1197-1201): the id cell is the hidden primary-key column (`self.bulk_table.setColumnHidden(0, True)`, 763) and is written only by the application (`QTableWidgetItem(str(item["id"]))` on load, `str(result)` after save, 1208-1209), so the handler is defensive code on a value the operator cannot type; a failed parse leaves the payload without an id, which `save_bulk_material` treats as the insert path. Residual (recorded, not reachable in the delivered UI): if the id cell ever held non-numeric text, the row would be inserted as a new record instead of updating the existing one.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006220 — `tabs/w8_Safety_Widget.py:596`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `numeric-get-default` (HIGH, class A)
- **Symbol:** `WasteManagementTab.calculate_waste_totals`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `volume_by_method[wm] = volume_by_method.get(wm,0) + vol` (596): same accumulator identity as INV34-006221 under the same completeness gate (602 'Unknown (incomplete records)').
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006221 — `tabs/w8_Safety_Widget.py:595`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `numeric-get-default` (HIGH, class A)
- **Symbol:** `WasteManagementTab.calculate_waste_totals`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** `volume_by_type[wt] = volume_by_type.get(wt,0) + vol` (595) is an addition identity for a first-seen waste type, and the report gate keeps partial sums out of the output: `volume_text = f"{total_volume:.1f}" if valid_volumes and valid_volumes == self.waste_table.rowCount() else "Unknown (incomplete records)"` (602). No defaulted volume is presented as a measurement.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006257 — `tabs/w8_Safety_Widget.py:401`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `SafetyBOPTab.load_from_database`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `data = (self.db.get_safety_report(well_id, report_id=report_id) or {}) if well_id else {}` (401): a missing report becomes an empty mapping which feeds `_load_nullable_safety_fields`, whose documented contract is 'Keep source NULL distinct from a widget's minimum display value.' - it records `missing = value is None` in `owner._missing_safety_fields`, sets `setSpecialValueText("Not supplied")` and `setMinimum(-1)` (tabs/w8_Safety_Widget.py:23-37), so an absent value is shown as Not supplied rather than as 0.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006260 — `tabs/w8_Safety_Widget.py:384`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `SafetyBOPTab.save_to_database`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if record_id:` (384): `save_safety_report` commits and `return record_id`, and its `except` path returns without an id (core/database.py:7698-7738), so the truth test is exactly the documented success test for a primary key (never 0). The failure branch is handled explicitly by the caller (reviews/message + SaveOutcome, 385-390).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006273 — `tabs/w8_Safety_Widget.py:676`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `WasteManagementTab.load_from_database`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `report_data = (self.db.get_safety_report(well_id, report_id=report_id) or {}) if well_id else {}` (676): same contract as INV34-006257 (the loader keeps NULL distinct from the widget minimum, 'Not supplied').
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006276 — `tabs/w8_Safety_Widget.py:659`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `WasteManagementTab.save_to_database`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if record_id:` (659): same contract as INV34-006260 - `save_safety_report` returns the committed row id or nothing, and the caller turns that into the save outcome (660-665).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006284 — `tabs/w8_Safety_Widget.py:299`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `SafetyBOPTab.calculate_bop_schedule`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `except (AttributeError, TypeError, ValueError): pass  # row without parseable last-test date` (299-300) in `calculate_bop_schedule`: only rows with a valid QDate are assessed (283-287) and the message explicitly reports the gap - `if assessed_count == 0 or assessed_count != self.bop_stack_table.rowCount(): message += "NOT ASSESSED: missing last-test dates for some/all components"` (306-307). The handler is also unreachable in practice (QDate.fromString/addDays and QTableWidgetItem construction do not raise in this flow). Residual (recorded, not a defect claim): a not-assessed row keeps its previous highlight and next-due cell while the message says NOT ASSESSED.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006285 — `tabs/w8_Safety_Widget.py:599`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `WasteManagementTab.calculate_waste_totals`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `except (AttributeError, TypeError, ValueError): pass  # incomplete waste row` (599-600): the swallowed row is excluded from the totals *and* the totals are refused when the row count does not match - `valid_volumes == self.waste_table.rowCount()` (602) - with pH reported as 'Unknown' when no value was supplied (601, 603). A partial sum is therefore never shown as a complete one.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006349 — `tabs/w9_Services_Widget.py:716`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `EquipmentDialog.save_equipment`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if self.equipment_id:` (716): the id comes from the selected row's hidden primary-key cell (`equipment_id = int(self.equipment_table.item(selected_row, 0).text())`, 444/455) or from the dialog's optional constructor argument (default None, 589-594). A falsy value therefore means 'new record', which is exactly the branch that omits `id` from the payload so `save_equipment_log` inserts instead of updating.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006366 — `tabs/w9_Services_Widget.py:574`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ServiceNoteDialog.save_note`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if self.note_id:` (574): same shape as INV34-006349 - the id is the selected row's primary key (337/348) or the constructor's optional argument (default None, 496-501), so falsy means insert and the branch adds `id` only for the update path.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006848 — `core/database.py:2597`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class B)
- **Symbol:** `DatabaseManager._get_current_user_info`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Same statement as INV34-000283 (core/database.py:2597, `except Exception:` of `_get_current_user_info`): identical rule and identical recorded text. One behaviour, adjudicated once under INV34-000283 (the fallback keeps the unknown explicit: user_id None, username 'system', consumed only by the audit stamp at 4150-4158).
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006868 — `core/database.py:3328`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class B)
- **Symbol:** `DatabaseManager._reject_unsafe_existing_credentials`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `_BCRYPT_AVAILABLE` is the optional-import capability flag already adjudicated in batch 002 (INV34-000717/000726): a boolean set by the import guard, so truthiness is the correct test, and in production the missing flag raises `CredentialLifecycleError("BCRYPT_REQUIRED", ...)` on the next line (3329). The flag cannot legitimately be 0.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006872 — `core/database.py:3460`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class B)
- **Symbol:** `DatabaseManager.release_session`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Same statement as INV34-000284 (core/database.py:3460 in `release_session`): duplicate record. Adjudicated once under INV34-000284.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007440 — `core/engineering/core.py:410`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class C)
- **Symbol:** `BitEngine.calculate_hsi`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not flow_rate_gpm or not pressure_drop_psi or not bit_size_in: raise MissingInputError("flow_rate, pressure_drop, bit_size required for HSI")` (410-411): a fail-loud required-input guard, not a silent default - the engine raises instead of returning a number computed from absent inputs, and the wrapper turns that into a blank cell (core/managers.py:415-426 documents the HSI/SPP screening caveat and returns None on failure; tabs/w3_drilling_report.calculate_hsi logs and leaves the field unset). Residual (recorded, product-level): a physically zero rate is treated as a missing input, because the spin boxes cannot distinguish 0 from 'not supplied'.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007443 — `core/engineering/core.py:505`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class C)
- **Symbol:** `HydraulicsEngine.calculate_annular_velocity`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not flow_rate_gpm or not hole_id_in or not pipe_od_in: raise MissingInputError("flow_rate, hole_id, pipe_od required")` (505-506): same fail-loud contract as INV34-007440 - the engine refuses to compute an annular velocity from absent inputs, and the wrapper reports `status` instead of presenting a number (core/managers.py:428-435, which batch 002 recorded as a domain decision at INV34-... managers.py:434). Residual (recorded, product-level): a physically zero rate is treated as a missing input.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007520 — `core/engineering/well_control_kill_sheet.py:286`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Same statement as INV34-001768 (core/engineering/well_control_kill_sheet.py:286, duplicate rule/line). Adjudicated once under INV34-001768: the missing-input gate at 272 + the refusal at 436-443 keeps the 0.0 default out of every computed result.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007521 — `core/engineering/well_control_kill_sheet.py:287`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Same statement as INV34-001754 (core/engineering/well_control_kill_sheet.py:287, duplicate rule/line). Adjudicated once under INV34-001754.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008456 — `tabs/w7_logistics_Widget.py:1183`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `FuelWaterTab.save_bulk_materials_to_db`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same handler as INV34-006213 (tabs/w7_logistics_Widget.py:1200/1201 in the current tree, recorded 1182/1183): the register records the `except ValueError:` line and this id the `pass` that follows it. Adjudicated once under INV34-006213.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-009612 — `core/engineering/engines/torque_drag.py:373`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `numeric-coalesce` (HIGH, class B)
- **Symbol:** `TorqueDragEngine.calculate`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** Same statement as INV34-001665 (core/engineering/engines/torque_drag.py:373, rule pair R-DEF-VALUE-PATH/or-zero vs /numeric-coalesce). Adjudicated once under INV34-001665: 0.0 is the declared parameter default and invalid values raise before the coalesce.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-009615 — `core/engineering/engines/torque_drag.py:632`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `numeric-coalesce` (HIGH, class B)
- **Symbol:** `TorqueDragEngine._axial_stretch`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** Same statement as INV34-001661 (core/engineering/engines/torque_drag.py:632, rule pair R-DEF-VALUE-PATH/or-zero vs /numeric-coalesce on one line). Adjudicated once under INV34-001661: `id_in` is always a float (coalesced at 465/646), so the expression is a no-op.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-010297 — `tabs/w7_logistics_Widget.py:825`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `float-or-zero-strict` (HIGH, class A)
- **Symbol:** `FuelWaterTab.update_bulk_stock_for_row`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** Duplicate of INV34-006021 (fixed in c2e0016, batch 003): same recorded text (`initial = float(initial_item.text() or 0)`), same line 825, rule R-DEF-VALUE-PATH/float-or-zero-strict instead of /or-zero. One statement, one defect, one fix; adjudicated under INV34-006021.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-010298 — `tabs/w7_logistics_Widget.py:826`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `float-or-zero-strict` (HIGH, class A)
- **Symbol:** `FuelWaterTab.update_bulk_stock_for_row`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** Duplicate of INV34-006021 (fixed in c2e0016, batch 003): same recorded text as INV34-006022/010297 on line 826. Adjudicated once under INV34-006021.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-010299 — `tabs/w7_logistics_Widget.py:827`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `float-or-zero-strict` (HIGH, class A)
- **Symbol:** `FuelWaterTab.update_bulk_stock_for_row`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** Duplicate of INV34-006021 (fixed in c2e0016, batch 003): same recorded text as INV34-006023 on line 827. Adjudicated once under INV34-006021.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit 3f0cf3e, evidence commit recorded in the ledger)
- **Remaining question:** none

