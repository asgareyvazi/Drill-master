# P6 p6-batch-008 — class class E (import statistics/heuristics, validator comparison guards, dialog formatters and legacy parsers): E:45

records **45** over **42** sites · DUPLICATE/FALSE-POSITIVE: 25 · INTENTIONAL: 15 · VERIFIED-CORRECT: 5

## INV34-002893 — `core/universal_import.py:163`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `WorkbookScanner._scan_sheet`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** A *statistic* on the sheet analysis, not a decision input: the value is assigned a safe default before the try (`hidden_rows = 0` / `has_merged = False`, 160-162, 222), computed inside it, and only ever written into the analysis dataclass (`has_merged=has_merged`, 386). Nothing branches on it (the field is declared with the same default at 44 and has no other reader - verified by grep), so a failure cannot change what is imported; it only leaves the reported statistic at its default. Site: hidden row/column counts (163).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002894 — `core/universal_import.py:225`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `WorkbookScanner.detect_tables`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** A *statistic* on the sheet analysis, not a decision input: the value is assigned a safe default before the try (`hidden_rows = 0` / `has_merged = False`, 160-162, 222), computed inside it, and only ever written into the analysis dataclass (`has_merged=has_merged`, 386). Nothing branches on it (the field is declared with the same default at 44 and has no other reader - verified by grep), so a failure cannot change what is imported; it only leaves the reported statistic at its default. Site: `has_merged` (225).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002933 — `core/universal_import.py:408`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `WorkbookScanner._detect_header_rows`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Rule mis-fire, not a behaviour to adjudicate: the subject is a *list*, not a number: `return [band[0]] if band else []` (408) is the empty-collection guard of a short band, which is the correct way to avoid an IndexError; no numeric value is tested.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002947 — `core/universal_import.py:545`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `WorkbookScanner.profile_column`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Rule mis-fire, not a behaviour to adjudicate: the subject is a *list*: `min_val = min(numeric) if numeric else None` (545) is the empty-list guard that avoids `min()`'s ValueError, and the enclosing branch already established that the list is non-empty statistically - the ternary keeps the value None when there is nothing to measure.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002948 — `core/universal_import.py:546`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `WorkbookScanner.profile_column`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for core/universal_import.py:546 - the same empty-list guard for `max()`, already adjudicated under INV34-002947: same construct, one line below
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002963 — `core/universal_import.py:538`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `WorkbookScanner.profile_column`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Column-type inference: a cell that does not parse as a number is simply not added to the numeric *sample* (`numeric.append(...)` inside the try), and the type decision afterwards is a ratio test with an explicit floor (`if numeric and len(numeric) >= max(1, len(values) * 0.6)`, 543). Excluding an unparseable cell is the correct behaviour for a 'is this column numeric?' heuristic - the alternative would be inventing a number for it. Site: building the numeric sample (537-539).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002964 — `core/validators.py:454`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `LogisticsValidator.validate`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Inside a validator whose whole purpose is to *report* problems, and the guarded block only adds a comparison-based message (warning/error) that cannot be evaluated without parseable operands. The parse failures that matter are reported by the numeric loops immediately above (e.g. 'Depth must be numeric', 135-136; 'Length must be numeric', 320-321), so the swallow cannot hide an unreported problem - it avoids a *second*, misleading message for a value that is already flagged. Residual (recorded, not a defect claim): for the fields whose only check is the comparison (dls/od/id/date ordering/overdue dates) a non-numeric value produces no message at all; the engine boundary still refuses such values loudly when they are computed with (e.g. `optional_number` raises for non-numeric geometry), so no wrong result is produced. Site: the logistics Date Out >= Date In check (445-455) on optional date fields.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002965 — `core/validators.py:454`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `LogisticsValidator.validate`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for core/validators.py:454 - the second rule on the same handler, already adjudicated under INV34-002964: optional date ordering check
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002998 — `core/validators.py:287`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `SurveyValidator.validate_points`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Inside a validator whose whole purpose is to *report* problems, and the guarded block only adds a comparison-based message (warning/error) that cannot be evaluated without parseable operands. The parse failures that matter are reported by the numeric loops immediately above (e.g. 'Depth must be numeric', 135-136; 'Length must be numeric', 320-321), so the swallow cannot hide an unreported problem - it avoids a *second*, misleading message for a value that is already flagged. Residual (recorded, not a defect claim): for the fields whose only check is the comparison (dls/od/id/date ordering/overdue dates) a non-numeric value produces no message at all; the engine boundary still refuses such values loudly when they are computed with (e.g. `optional_number` raises for non-numeric geometry), so no wrong result is produced. Site: the DLS warning in the survey loop (283-288). DLS is optional there (`if dls not in (None, "")`) and the block's only action is a >15 deg/30m warning.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003004 — `core/validators.py:142`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `DailyReportValidator.validate`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Inside a validator whose whole purpose is to *report* problems, and the guarded block only adds a comparison-based message (warning/error) that cannot be evaluated without parseable operands. The parse failures that matter are reported by the numeric loops immediately above (e.g. 'Depth must be numeric', 135-136; 'Length must be numeric', 320-321), so the swallow cannot hide an unreported problem - it avoids a *second*, misleading message for a value that is already flagged. Residual (recorded, not a defect claim): for the fields whose only check is the comparison (dls/od/id/date ordering/overdue dates) a non-numeric value produces no message at all; the engine boundary still refuses such values loudly when they are computed with (e.g. `optional_number` raises for non-numeric geometry), so no wrong result is produced. Site: the depth@00:00 / depth@24:00 ordering warning, whose operands were already validated at 129-136.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003009 — `core/validators.py:142`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `DailyReportValidator.validate`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for core/validators.py:142 - the second rule on the same handler, already adjudicated under INV34-003004: the depth operands are already reported
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003012 — `core/validators.py:287`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `SurveyValidator.validate_points`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for core/validators.py:287 - the second rule on the same handler, already adjudicated under INV34-002998: DLS is an optional warning threshold
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003153 — `dialogs/casing_history_dialog.py:54`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `_fmt`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** A *display* formatter: it renders the number when it parses (`f"{float(value):,.{digits}f}{suffix}"`) and otherwise returns the value's own string form (`return str(value)`) - it can never invent a number, and the raw text stays visible in the table/export. This is the family's primary instance (dialogs/casing_history_dialog.py:52-55); the three sibling history dialogs carry the identical helper.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003164 — `dialogs/cement_history_dialog.py:55`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `_fmt`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for dialogs/cement_history_dialog.py:53-56 - the identical formatter helper, already adjudicated under INV34-003153: A *display* formatter: it renders the number when it parses (`f"{float(value):,.{digits}f}{suffix}"`) and otherwise returns the value's own string form (`return str(value)`) - it can never invent a number, and the raw text stays visible in the table/export.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003177 — `dialogs/daily_report_dialogs.py:295`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `AddActivityDialog._load`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Legacy text is parsed back into the dialog's spin boxes and on failure the widgets keep their current (default) contents - the same 'keep widget defaults' contract stated in the sibling branch's comment ('prev_time absent or not HH:MM - keep widget defaults', 152). No time is invented for a malformed legacy value. Site: the from-time branch at 295.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003178 — `dialogs/daily_report_dialogs.py:304`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `AddActivityDialog._load`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for dialogs/daily_report_dialogs.py:304 - the same parse for the to-time branch, same contract, already adjudicated under INV34-003177: the widgets keep their defaults
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003179 — `dialogs/daily_report_dialogs.py:151`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `AddActivityDialog.init_ui`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Legacy text is parsed back into the dialog's spin boxes and on failure the widgets keep their current (default) contents - the same 'keep widget defaults' contract stated in the sibling branch's comment ('prev_time absent or not HH:MM - keep widget defaults', 152). No time is invented for a malformed legacy value. Site: 149-152, with that comment.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003466 — `dialogs/hierarchy_dialogs.py:1210`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `NewSectionDialog.create_section`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `estimated_rop = (depth_to - depth_from) / planned_days if planned_days else None` (1210) - the divisor guard returns None ('no estimate') instead of dividing by zero or inventing a rate; planned_days is an operator entry that is legitimately absent.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003472 — `dialogs/hierarchy_dialogs.py:855`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `NewWellDialog.init_ui`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if self.project_id: self.select_project_by_id(self.project_id)` (855): the subject is a Project primary key and the dialog's constructor argument is optional ('set the initial project if one was given', 854) - a falsy id means 'no initial project', so nothing is selected.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003493 — `dialogs/mse_history_dialog.py:55`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `_fmt`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for dialogs/mse_history_dialog.py:53-56 - the identical formatter helper, already adjudicated under INV34-003153: A *display* formatter: it renders the number when it parses (`f"{float(value):,.{digits}f}{suffix}"`) and otherwise returns the value's own string form (`return str(value)`) - it can never invent a number, and the raw text stays visible in the table/export.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003504 — `dialogs/mud_volume_history_dialog.py:56`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `_fmt`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for dialogs/mud_volume_history_dialog.py:54-57 - the identical formatter helper, already adjudicated under INV34-003153: A *display* formatter: it renders the number when it parses (`f"{float(value):,.{digits}f}{suffix}"`) and otherwise returns the value's own string form (`return str(value)`) - it can never invent a number, and the raw text stays visible in the table/export.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003571 — `dialogs/planning_dialog.py:1096`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `WellPlanDialog.load_well_info`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Stored spud date parsed into the planning dialog's date widget; the handler's own comment states the contract - 'spud date absent/unparseable - keep widget date' (1097) - so a bad stored value cannot fabricate a date, and the widget keeps the operator's current entry.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003585 — `dialogs/report_history_dialog.py:42`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `_fmt_dt`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for dialogs/report_history_dialog.py:40-43 - the same display-fallback contract for a date value (`strftime` -> `str(value)`), already adjudicated under INV34-003153: A *display* formatter: it renders the number when it parses (`f"{float(value):,.{digits}f}{suffix}"`) and otherwise returns the value's own string form (`return str(value)`) - it can never invent a number, and the raw text stays visible in the table/export.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003608 — `dialogs/smart_template_dialog.py:2099`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `SmartTemplateDialog._unmerge`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Template-layout analysis: merged-cell bookkeeping over the worksheet (`merged_slaves.add((r, c))`) whose failure leaves the collected set incomplete - it feeds the template analysis only, and the scan continues with its own bounds checks (`range(1, min(ws.max_row + 1, MAX_SCAN_ROWS))`, 2102). No extracted value is changed.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003705 — `dialogs/smart_template_dialog.py:1411`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `CodeResolver.resolve_main_code`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if best_match:` (1411) guards the fuzzy-match result of a name -> code search where `best_match` is initialised to None and can only be set to a key of `MAIN_CODE_MAP` (1405-1410). Those keys are non-empty strings ('1'..'12'+), so no legitimate code is falsy and the test is exactly 'did the fuzzy search find anything?'.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003707 — `dialogs/smart_template_dialog.py:1485`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `CodeResolver.resolve_sub_code`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for dialogs/smart_template_dialog.py:1485 - the identical guard for the sub-code fuzzy search (`SUB_CODE_MAP` keys are '1.1'-style non-empty strings), already adjudicated under INV34-003705: same 'did the search find anything?' test
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003799 — `dialogs/smart_template_dialog.py:1395`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `CodeResolver.resolve_main_code`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** A *probe* in the code-resolution helper: an integer main code is tried first and a non-integer value falls through to the reverse (name -> code) lookup at 1398-1402. The swallow implements 'not an integer code', after which the helper still resolves the value by name.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003800 — `dialogs/smart_template_dialog.py:1448`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `CodeResolver.resolve_sub_code`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** A *probe* in the sub-code helper: a numeric sub-code is tried first and a non-numeric value falls through to the sub-code's own reverse lookup ('try sub code number', 1451). Same shape as INV34-003799.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003802 — `dialogs/smart_template_dialog.py:1258`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `FieldDetector._is_label`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** A *probe* inside the label heuristic: `float(...)` is attempted only to decide 'this is a number, hence not a label' (`return False` on success) and the swallow means 'not a number - continue with the date-like and text checks that follow' (1261+). The failure is the branch's expected outcome, not a hidden error.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003810 — `dialogs/startup_dialog.py:699`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `StartupDialog.use_template`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Best-effort session close in the startup dialog's cleanup path: the same contract already adjudicated for `core/database.py release_session` (p6-batch-004 INV34-000284) - a failure to close must not mask the operation's outcome, and the session object is discarded immediately afterwards.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007854 — `core/universal_import.py:164`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `WorkbookScanner._scan_sheet`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/universal_import.py:163/164 - the `pass` line of INV34-002893's handler, already adjudicated under INV34-002893: sheet statistics only; no import decision reads them
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007855 — `core/universal_import.py:226`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `WorkbookScanner.detect_tables`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/universal_import.py:225/226 - the `pass` line of INV34-002894's handler, already adjudicated under INV34-002894: `has_merged` is written into the analysis result and never branched on
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007857 — `core/universal_import.py:539`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `WorkbookScanner.profile_column`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/universal_import.py:538/539 - the `pass` line of INV34-002963's handler, already adjudicated under INV34-002963: non-numeric cells are excluded from the numeric sample by design
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007863 — `core/validators.py:143`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `DailyReportValidator.validate`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/validators.py:142/143 - the `pass` line of INV34-003004's handler, already adjudicated under INV34-003004: the depth ordering warning is best-effort on already-validated operands
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007864 — `core/validators.py:288`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `SurveyValidator.validate_points`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/validators.py:287/288 - the `pass` line of INV34-002998's handler, already adjudicated under INV34-002998: no fabricated DLS warning for an unparseable value
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007865 — `core/validators.py:330`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `BHAValidator.validate`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Inside a validator whose whole purpose is to *report* problems, and the guarded block only adds a comparison-based message (warning/error) that cannot be evaluated without parseable operands. The parse failures that matter are reported by the numeric loops immediately above (e.g. 'Depth must be numeric', 135-136; 'Length must be numeric', 320-321), so the swallow cannot hide an unreported problem - it avoids a *second*, misleading message for a value that is already flagged. Residual (recorded, not a defect claim): for the fields whose only check is the comparison (dls/od/id/date ordering/overdue dates) a non-numeric value produces no message at all; the engine boundary still refuses such values loudly when they are computed with (e.g. `optional_number` raises for non-numeric geometry), so no wrong result is produced. Site: the BHA `id < od` check (325-330); the same loop reports 'Length must be numeric' for its own length field (320-321).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007873 — `core/validators.py:455`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `LogisticsValidator.validate`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/validators.py:454/455 - the `pass` line of INV34-002964's handler, already adjudicated under INV34-002964: no false 'Date Out must be >= Date In' for unparseable dates
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007877 — `core/validators.py:513`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `BOPValidator.validate`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/validators.py:512/513 - the `pass` line of INV34-008774's handler, already adjudicated under INV34-008774: the overdue warning is skipped rather than emitted on unparseable dates
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007928 — `dialogs/daily_report_dialogs.py:296`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `AddActivityDialog._load`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for dialogs/daily_report_dialogs.py:295/296 - the `pass` line of INV34-003177's handler, already adjudicated under INV34-003177: the widgets keep their defaults
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007929 — `dialogs/daily_report_dialogs.py:305`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `AddActivityDialog._load`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for dialogs/daily_report_dialogs.py:304/305 - the `pass` line of INV34-003178's handler, already adjudicated under INV34-003177: the widgets keep their defaults
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007987 — `dialogs/smart_template_dialog.py:1259`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `FieldDetector._is_label`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for dialogs/smart_template_dialog.py:1258/1259 - the `pass` line of INV34-003802's probe, already adjudicated under INV34-003802: the probe's miss is a normal outcome of the heuristic
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007988 — `dialogs/smart_template_dialog.py:1396`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `CodeResolver.resolve_main_code`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for dialogs/smart_template_dialog.py:1395/1396 - the `pass` line of INV34-003799's probe, already adjudicated under INV34-003799: the reverse lookup follows
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007989 — `dialogs/smart_template_dialog.py:1449`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `CodeResolver.resolve_sub_code`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for dialogs/smart_template_dialog.py:1448/1449 - the `pass` line of INV34-003800's probe, already adjudicated under INV34-003800: the sub-code reverse lookup follows
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007995 — `dialogs/smart_template_dialog.py:2100`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `SmartTemplateDialog._unmerge`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for dialogs/smart_template_dialog.py:2099/2100 - the `pass` line of INV34-003608's handler, already adjudicated under INV34-003608: template-layout analysis only
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008774 — `core/validators.py:512`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `BOPValidator.validate`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Inside a validator whose whole purpose is to *report* problems, and the guarded block only adds a comparison-based message (warning/error) that cannot be evaluated without parseable operands. The parse failures that matter are reported by the numeric loops immediately above (e.g. 'Depth must be numeric', 135-136; 'Length must be numeric', 320-321), so the swallow cannot hide an unreported problem - it avoids a *second*, misleading message for a value that is already flagged. Residual (recorded, not a defect claim): for the fields whose only check is the comparison (dls/od/id/date ordering/overdue dates) a non-numeric value produces no message at all; the engine boundary still refuses such values loudly when they are computed with (e.g. `optional_number` raises for non-numeric geometry), so no wrong result is produced. Site: the BOP test-overdue warning (504-512).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

