# P6 p6-batch-009 — class class E (tab-level truthiness guards, optional plotting preludes, dialog formatters): E:45

records **45** over **41** sites · DUPLICATE/FALSE-POSITIVE: 26 · VERIFIED-CORRECT: 12 · INTENTIONAL: 7

## INV34-003846 — `dialogs/torque_drag_history_dialog.py:54`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `_fmt`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for dialogs/torque_drag_history_dialog.py:52-55 - the same `_fmt` display helper (float when parseable, `str(value)` otherwise) as the family adjudicated in p6-batch-008, already adjudicated under INV34-003153: a display formatter can neither invent nor hide a number
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003857 — `dialogs/well_control_kill_sheet_history_dialog.py:57`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `_fmt`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for dialogs/well_control_kill_sheet_history_dialog.py:55-58 - the identical `_fmt` helper, already adjudicated under INV34-003153: a display formatter can neither invent nor hide a number
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-003883 — `main_window.py:715`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `MainWindow.center_window`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `center_window` is pure window geometry: the swallow can only leave the window at its default position. The QApplication/screen objects it touches carry no domain value, and nothing downstream reads the window's position.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004042 — `main_window.py:3057`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `MainWindow._cleanup_hierarchy_worker`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for main_window.py:3054-3057 - the identical teardown guard in `_cleanup_hierarchy_worker` (same try/except RuntimeError -> pass, then debug-logging generic handler at 3059-3060), already adjudicated under INV34-004044: already-destroyed Qt worker
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004044 — `main_window.py:1198`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `MainWindow._stop_hierarchy_worker`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Qt worker teardown: `RuntimeError` is the documented error for touching a C++ object that has already been destroyed (the normal race when a finished worker is cleaned up), so the swallow implements 'the worker is already gone - nothing to stop'. The generic handler on the next lines still logs anything else at debug level (1200-1201), and the reference is cleared in `finally` (1202-1203) so no stale worker is kept.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004079 — `tabs/home_tab.py:346`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `HomeTab.darken_color`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `darken_color` is a theme helper: it returns a darkened hex string for a colour token and the input unchanged when the token is not parseable (e.g. a named colour). The value is presentation only - no measurement, no persistence - and the fallback keeps the caller's own token instead of inventing a colour. Residual (recorded, cosmetic): a string that passes `lstrip` but fails hex parsing is returned without the leading '#' (the local rebinding happened before the failure) - a theme token, never data.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004080 — `tabs/w10_Planning_Widget.py:37`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `None`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Module-level optional plotting backend: `matplotlib.use('Qt5Agg')` is attempted only when the already-installed backend is non-interactive/empty (`_current_backend.lower() in ('agg', '')`), and the module then imports `pyplot` and degrades explicitly through `MATPLOTLIB_QT_OK`/`PYQTGRAPH_AVAILABLE` (33-43 in this file). A failure here means the backend selection did not apply - a rendering choice - while chart availability is reported by the explicit flags, not by this swallow. Site: the W10 prelude (32-38).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004272 — `tabs/w10_Planning_Widget.py:436`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `NPTReportTab.get_npt_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `well_id = self.current_well_id` is a Well primary key (the queries below compare `well_id == well_id`), so its falsy value means exactly 'no well selected': the guard returns the method's documented empty shape before any query runs - no query with an invalid id and no fabricated KPI. The file states the same no-fabrication contract for the values it would otherwise produce ('unknown source data yields None, never 0.0', 1297-1301) and the renderer keeps it end-to-end ('Unknown values render as "—" (via fmt_num default=None), never 0.', 2066-2072). Site: `get_npt_data` (436-438), which returns `{'entries': [], 'categories': {}, 'total_npt': None, 'npt_percentage': None, 'total_hours': None}`.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004362 — `tabs/w12_Analysis.py:29`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `None`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for tabs/w12_Analysis.py:24-30 - the identical backend-selection prelude in W12, already adjudicated under INV34-004080: same prelude, same rendering-only scope
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004363 — `tabs/w12_Analysis.py:54`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `None`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `pg.setConfigOptions(useOpenGL=True)` is a rendering-performance option; the handler carries the module's own annotation ('# OpenGL اختیاری است' = OpenGL is optional, w12:55) and pyqtgraph stays importable either way. A miss means the charts fall back to the software renderer, which cannot change any value shown. Site: the module-level pyqtgraph configuration (52-55).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004364 — `tabs/w12_Analysis.py:140`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `AnalysisWidget.__init__`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for tabs/w12_Analysis.py:138-141 - the same optional-OpenGL guard repeated in the widget's own pyqtgraph configuration, already adjudicated under INV34-004363: rendering option; software rendering falls back
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004365 — `tabs/w12_Analysis.py:173`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `AnalysisWidget.__init__`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The file documents this connection as deliberate - 'A wellbore selection must re-scope analytics. DrillTabBase wires well/section/report but not the bore signal, so - exactly like the W3b schematic tab - W12 consumes it directly (smallest, lowest-risk change...)' (167-170) - and the signal exists with the same name and signature on the manager (`wellbore_changed = Signal(int, object)`, core/selection_manager.py:43). The guard is therefore defensive only: in a correct build the connect cannot fail, and if it ever did, the symptom would be a stale analytics view (the tab's own reload paths and the well/section/report signals remain), not a wrong number or a write.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004512 — `tabs/w12_Analysis.py:2272`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.analyze_cost`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w12_Analysis.py:2271-2273 - the identical guard in the cost-analysis handler, already adjudicated under INV34-004514: same user-visible 'No well selected' pre-condition
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004514 — `tabs/w12_Analysis.py:2191`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.analyze_npt_forecasting`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not well_id: self.results_text.setText("No well selected"); return` (2190-2193): the guard is the analysis button's pre-condition, and its action is an explicit user-visible message instead of a query - the Well primary key's falsy value is reported to the operator, not silently ignored. The same contract is repeated by the sibling analysis handlers (2271-2273, 2393-2396).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004515 — `tabs/w12_Analysis.py:2394`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.analyze_risk`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w12_Analysis.py:2393-2396 - the identical guard in the risk-assessment handler, already adjudicated under INV34-004514: same construct
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004519 — `tabs/w12_Analysis.py:1304`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.calculate_kpis`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `well_id = self.current_well_id` is a Well primary key (the queries below compare `well_id == well_id`), so its falsy value means exactly 'no well selected': the guard returns the method's documented empty shape before any query runs - no query with an invalid id and no fabricated KPI. The file states the same no-fabrication contract for the values it would otherwise produce ('unknown source data yields None, never 0.0', 1297-1301) and the renderer keeps it end-to-end ('Unknown values render as "—" (via fmt_num default=None), never 0.', 2066-2072). Site: the overview/KPI method (1304-1307), which returns `dict.fromkeys([...], None)` - every KPI explicitly unknown, which is exactly what the renderer expects (2066-2072).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004539 — `tabs/w12_Analysis.py:1500`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.get_npt_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w12_Analysis.py:1500-1503 - the same no-well pre-query guard in `get_npt_data`, already adjudicated under INV34-004519: Same construct as INV34-004519 in this file (a Well primary key tested for truthiness before the query; falsy means 'no well selected'), with the method's own documented empty return. The method returns the empty-NPT dict with `None` totals (`total_npt`, `npt_percentage`, `total_hours`).
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004542 — `tabs/w12_Analysis.py:1437`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.get_performance_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w12_Analysis.py:1437-1438 - the same no-well pre-query guard in `get_performance_data`, already adjudicated under INV34-004519: Same construct as INV34-004519 in this file (a Well primary key tested for truthiness before the query; falsy means 'no well selected'), with the method's own documented empty return. The method returns `[]`.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004543 — `tabs/w12_Analysis.py:1466`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.get_time_depth_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w12_Analysis.py:1466 - the same no-well pre-query guard in `get_time_depth_data`, already adjudicated under INV34-004519: Same construct as INV34-004519 in this file (a Well primary key tested for truthiness before the query; falsy means 'no well selected'), with the method's own documented empty return. The method returns `[]`.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004551 — `tabs/w12_Analysis.py:1383`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.get_today_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `report = candidates[0] if len(candidates) == 1 else None` (1382) then `if not report:` (1383): the falsy subject is the absence of a *single unambiguous* report for the selected date - the `limit(2)` probe exists to detect a duplicate report date and the file's stated rule is 'Ambiguity -> UNKNOWN, not a guess' (1396). Returning None here leaves the indicators untouched instead of displaying one arbitrary day.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004552 — `tabs/w12_Analysis.py:1369`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.get_today_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `well_id = self.current_well_id` is a Well primary key (the queries below compare `well_id == well_id`), so its falsy value means exactly 'no well selected': the guard returns the method's documented empty shape before any query runs - no query with an invalid id and no fabricated KPI. The file states the same no-fabrication contract for the values it would otherwise produce ('unknown source data yields None, never 0.0', 1297-1301) and the renderer keeps it end-to-end ('Unknown values render as "—" (via fmt_num default=None), never 0.', 2066-2072). Site: `get_today_data` (1369-1370) returns `None`, and its only consumer guards the same way before fetching (`update_daily_data`: `if not self.current_well_id: return`, 2059) and treats `None` as 'leave the indicators as they are' (`if today:`, 2065-2066).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-004553 — `tabs/w12_Analysis.py:179`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.init_ui`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Rule mis-fire, not a behaviour to adjudicate: `PYQTGRAPH_AVAILABLE` is a module-level bool set by the import guard (48/57) - a feature flag, not a numeric quantity; the guard selects the placeholder-message branch of the tab's UI (179-186).
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005047 — `tabs/w14_Procedure_Widget.py:252`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `ProcedureWidget.on_procedure_selected`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `proc_id = item.data(Qt.UserRole)` (251) then `if proc_id:` (252): the value is the procedure's primary key, stored on the list item when it was built (`item.setData(Qt.UserRole, proc['id'])`, 246). A falsy value means the item carries no procedure (nothing to load), so rejecting it is correct - and when it is set, the guard proceeds to load exactly that procedure.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005956 — `tabs/w6_Trajectory_Widget.py:345`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `SurveyDataTab.set_current_well`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w6_Trajectory_Widget.py:343-346 - the identical `set_current_well` guard of the second trajectory tab (same docstring comment on the line above), already adjudicated under INV34-005984: same 'no well selected -> stay empty' contract
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005957 — `tabs/w6_Trajectory_Widget.py:702`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `TrajectoryCalculationManager.create_calculation`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `calc_id = self.db_manager.save_trajectory_calculation(calculation_data)`, then `if calc_id: return calc_id` / `return None` (700-704): the function's contract is the saved row's primary key or None (nothing saved / no database manager). A falsy return from the save cannot be reported as a successful save, so the guard is the correct success/failure test - the caller receives None rather than a fabricated id.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005961 — `tabs/w6_Trajectory_Widget.py:522`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `TrajectoryPlotTab.init_ui`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Rule mis-fire, not a behaviour to adjudicate: `PYQTGRAPH_AVAILABLE` is the module-level bool set by the import guard - a feature flag; the branch replaces the plot widget with a placeholder label (522-527).
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005962 — `tabs/w6_Trajectory_Widget.py:601`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `TrajectoryPlotTab.load_for_report`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `load_for_report(report_id: int)` stores the id and loads plots only when one is set (`if report_id: self.load_plots()`): a report primary key's falsy value means 'no report selected', and the plotting path must not run against it.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005984 — `tabs/w6_Trajectory_Widget.py:96`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `TripSheetTab.set_current_well`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `set_current_well(well_id: int, section_id: int = None)` stores the id and then loads only when one is set (`if well_id: self.load_data()`): the falsy value is 'no well selected', and the table is documented to stay empty in that state ('Operational tables start empty; data comes from the selected report.', 92). No query runs with an invalid id.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006143 — `tabs/w7_logistics_Widget.py:1249`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `FuelWaterTab.set_current_well`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w7_logistics_Widget.py:1263-1269 - the identical `set_current_well` guard of `FuelWaterTab` (loads the fuel/water and bulk-material tables), already adjudicated under INV34-006198: Same construct as INV34-004519 in this file (a Well primary key tested for truthiness before the query; falsy means 'no well selected'), with the method's own documented empty return.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006198 — `tabs/w7_logistics_Widget.py:563`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `PersonnelLogisticsTab.set_current_well`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `well_id = self.current_well_id` is a Well primary key (the queries below compare `well_id == well_id`), so its falsy value means exactly 'no well selected': the guard returns the method's documented empty shape before any query runs - no query with an invalid id and no fabricated KPI. The file states the same no-fabrication contract for the values it would otherwise produce ('unknown source data yields None, never 0.0', 1297-1301) and the renderer keeps it end-to-end ('Unknown values render as "—" (via fmt_num default=None), never 0.', 2066-2072). Site: `PersonnelLogisticsTab.set_current_well` (563-565), which loads POB/crew tables only when a well is set.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006205 — `tabs/w7_logistics_Widget.py:1725`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `TransportLogTab.set_current_well`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w7_logistics_Widget.py:1739-1744 - the identical `set_current_well` guard of `TransportLogTab` (loads the transport log), already adjudicated under INV34-006198: Same construct as INV34-004519 in this file (a Well primary key tested for truthiness before the query; falsy means 'no well selected'), with the method's own documented empty return.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006212 — `tabs/w7_logistics_Widget.py:999`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `FuelWaterTab.load_fuel_water_from_db._val`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `load_fuel_water_from_db` defines two readers side by side: `_val(key, default=0.0)` returns the caller's default for an absent or non-numeric value (the same documented loader contract as `safe_float` in core/text_utils.py and `sv` in the w3/w3c dialogs), while `_stock(key)` states the domain rule 'Preserve NULL as UNKNOWN; only real numbers become values.' (1021) and returns None on the same failure (1027-1028) - which `_set_stock_value` renders as the unknown mark (597-602) and which the day's save path reads back as 'not reported'. So the swallow at `_val`'s typed except cannot hide a failure: the three states (value / explicit zero / unknown) are decided by the caller's explicit default and by `_stock`, and the fuel/water remainder arithmetic below uses only real values (1043-1044). Register anchor 999 predates the batch-003 fix c2e0016; the construct now sits at 1017 (verified by the re-anchor map).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006343 — `tabs/w9_Services_Widget.py:647`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `EquipmentDialog.load_equipment_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `load_equipment_data` returns immediately when no equipment is selected (`if not self.equipment_id: return`, 647-648); the value is the equipment log's primary key, and the method's next step is to find the row with `e.get('id') == self.equipment_id` (650) - running that lookup with a falsy/absent id could match an unrelated row, so the guard is required rather than merely defensive.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006361 — `tabs/w9_Services_Widget.py:537`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `ServiceNoteDialog.load_note_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not self.note_id:` (537) distinguishes the *new note* path (compute the next note number for the well: `max(note_number) + 1`, else 1, 538-543) from the *edit existing* path (load the note with that id, 545-555). The note id is a primary key, so a falsy value means 'no stored note', and the branch's whole purpose is to prevent editing an unselected note - exactly the documented behaviour of the dialog.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008041 — `main_window.py:716`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `MainWindow.center_window`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for main_window.py:715/716 - the `pass` line of INV34-003883's handler, already adjudicated under INV34-003883: window placement only
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008044 — `main_window.py:1199`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `MainWindow._stop_hierarchy_worker`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for main_window.py:1198/1199 - the `pass` line of INV34-004044's handler, already adjudicated under INV34-004044: already-destroyed Qt worker
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008079 — `main_window.py:3058`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `MainWindow._cleanup_hierarchy_worker`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for main_window.py:3057/3058 - the `pass` line of INV34-004042's handler, already adjudicated under INV34-004044: already-destroyed Qt worker
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008083 — `tabs/w10_Planning_Widget.py:38`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `None`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w10_Planning_Widget.py:37/38 - the `pass` line of INV34-004080's handler, already adjudicated under INV34-004080: backend selection is a rendering choice
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008115 — `tabs/w12_Analysis.py:30`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `None`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w12_Analysis.py:29/30 - the `pass` line of INV34-004362's handler, already adjudicated under INV34-004080: rendering choice only
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008116 — `tabs/w12_Analysis.py:141`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `AnalysisWidget.__init__`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w12_Analysis.py:140/141 - the `pass` line of INV34-004364's handler, already adjudicated under INV34-004363: rendering option only
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008117 — `tabs/w12_Analysis.py:174`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `AnalysisWidget.__init__`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w12_Analysis.py:173/174 - the `pass` line of INV34-004365's handler, already adjudicated under INV34-004365: defensive guard around a documented, existing signal
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008132 — `tabs/w12_Analysis.py:2191`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.analyze_npt_forecasting`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w12_Analysis.py:2191 - the second rule on the same handler, already adjudicated under INV34-004514: 'No well selected' is shown and the analysis returns
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008133 — `tabs/w12_Analysis.py:2272`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.analyze_cost`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w12_Analysis.py:2272 - the second rule on that handler, already adjudicated under INV34-004514: same construct
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008136 — `tabs/w12_Analysis.py:2394`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `AnalysisWidget.analyze_risk`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for tabs/w12_Analysis.py:2394 - the second rule on that handler, already adjudicated under INV34-004514: same construct
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008442 — `tabs/w7_logistics_Widget.py:999`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `FuelWaterTab.load_fuel_water_from_db._val`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for tabs/w7_logistics_Widget.py:999/1017 - the second register record on the same `_val` handler, already adjudicated under INV34-006212: the default/unknown split is carried by `_val` vs `_stock`
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

