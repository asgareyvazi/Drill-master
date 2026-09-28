# P6 p6-batch-006 — class class D (lower-risk guards/preview conveniences): D:45

records **45** over **42** sites · DUPLICATE/FALSE-POSITIVE: 20 · INTENTIONAL: 16 · VERIFIED-CORRECT: 9

## INV34-005181 — `tabs/w2_Daily_Report.py:973`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget._adjust_all_row_heights`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Row-height/completer/suggestion maintenance around the daily-report table. The guard wraps purely visual work whose failure mode is 'the convenience did not apply', never a wrong number: the row keeps its default height, the completer stays unset and the suggestion list simply lacks an entry (the method then adds its static fallbacks and returns the sorted set - `contractors.update([...])`, `return sorted(list(contractors))`). Site: `_adjust_all_row_heights` (973).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005182 — `tabs/w2_Daily_Report.py:962`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget._adjust_row_height`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Row-height/completer/suggestion maintenance around the daily-report table. The guard wraps purely visual work whose failure mode is 'the convenience did not apply', never a wrong number: the row keeps its default height, the completer stays unset and the suggestion list simply lacks an entry (the method then adds its static fallbacks and returns the sorted set - `contractors.update([...])`, `return sorted(list(contractors))`). Site: `_adjust_row_height` (962).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005186 — `tabs/w2_Daily_Report.py:1417`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget._extract_time_log_row`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_extract_time_log_row` reads a table row into a time-log record and every swallow is compensated by the code that follows it: the duration cell is re-derived from the from/to times right after ('compute duration if it was zero', 1432-1440), and the widgets' own `get_time()` contract defines midnight as this module's encoding of '24:00' (`if is_2400: from_python_time = time(0, 0)`, 1413-1416). The `hasattr` guard on the line before each try means a non-TimeLineEdit cell never reaches the parse. Site: from-time parse (1417).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005187 — `tabs/w2_Daily_Report.py:1429`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget._extract_time_log_row`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_extract_time_log_row` reads a table row into a time-log record and every swallow is compensated by the code that follows it: the duration cell is re-derived from the from/to times right after ('compute duration if it was zero', 1432-1440), and the widgets' own `get_time()` contract defines midnight as this module's encoding of '24:00' (`if is_2400: from_python_time = time(0, 0)`, 1413-1416). The `hasattr` guard on the line before each try means a non-TimeLineEdit cell never reaches the parse. Site: to-time parse (1429).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005188 — `tabs/w2_Daily_Report.py:983`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget._get_recent_contractors`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Row-height/completer/suggestion maintenance around the daily-report table. The guard wraps purely visual work whose failure mode is 'the convenience did not apply', never a wrong number: the row keeps its default height, the completer stays unset and the suggestion list simply lacks an entry (the method then adds its static fallbacks and returns the sorted set - `contractors.update([...])`, `return sorted(list(contractors))`). Site: NPT contractor map (983).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005189 — `tabs/w2_Daily_Report.py:996`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget._get_recent_contractors`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Row-height/completer/suggestion maintenance around the daily-report table. The guard wraps purely visual work whose failure mode is 'the convenience did not apply', never a wrong number: the row keeps its default height, the completer stays unset and the suggestion list simply lacks an entry (the method then adds its static fallbacks and returns the sorted set - `contractors.update([...])`, `return sorted(list(contractors))`). Site: contractor names from the DB (996); the session is closed in a `finally` (994-995), so the swallow cannot leak it.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005190 — `tabs/w2_Daily_Report.py:1005`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget._get_recent_contractors`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Row-height/completer/suggestion maintenance around the daily-report table. The guard wraps purely visual work whose failure mode is 'the convenience did not apply', never a wrong number: the row keeps its default height, the completer stays unset and the suggestion list simply lacks an entry (the method then adds its static fallbacks and returns the sorted set - `contractors.update([...])`, `return sorted(list(contractors))`). Site: service companies for the well (1005).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005192 — `tabs/w2_Daily_Report.py:893`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget.add_time_log_row`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Row-height/completer/suggestion maintenance around the daily-report table. The guard wraps purely visual work whose failure mode is 'the convenience did not apply', never a wrong number: the row keeps its default height, the completer stays unset and the suggestion list simply lacks an entry (the method then adds its static fallbacks and returns the sorted set - `contractors.update([...])`, `return sorted(list(contractors))`). Site: completer setup on the contractor editor (893).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005297 — `tabs/w2_Daily_Report.py:1000`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget._get_recent_contractors`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `services = ... if self.current_well_id else []`: a Well PK tested for truthiness with an explicit empty-list fallback, inside the suggestion builder. No query is issued for an absent well and nothing is fabricated.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005324 — `tabs/w2_Daily_Report.py:627`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.auto_calculate_rig_day`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `auto_calculate_rig_day` branches on truthiness to choose its data source, and both branches converge on the same documented default when nothing matches: the section path falls back to `self.rig_day.setValue(1)` (650) exactly like the well path (674). The subject is a Section PK, so only the `-1` sentinel is outside the test, and it is re-guarded at the consumption sites (682/1510/1650).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005346 — `tabs/w2_Daily_Report.py:1507`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.load_report_dialog`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not well_id: show_error("DailyReport", "Please select a well first"); return` - a required-input guard with a user-visible reason before any write; the subject is a Well PK (positive).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005351 — `tabs/w2_Daily_Report.py:570`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.on_section_changed`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `on_section_changed`'s guard means 'no section selected', and the subject's domain is the Section primary key (positive integers - a legitimate zero cannot occur). The `-1` sentinel that other flows produce is handled where it is consumed: `load_reports_for_section` re-guards it explicitly (`if not section_id or section_id == -1: return`, 682), and it is the only lookup this handler performs with the id (585). Residual (recorded, not a defect claim): a `-1` delivered through the section_changed signal (no such call site found) would be stored as the current section and neutralised by that downstream guard.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005371 — `tabs/w2_Daily_Report.py:1405`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class D)
- **Symbol:** `DailyReportWidget._extract_time_log_row`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The guard is narrow (`except (ValueError, TypeError)`) and applies to a QLabel's text; the  a table row into a time-log record and every swallow is compensated by the code that follows it: the duration cell is re-derived from the from/to times right after ('compute duration if it was zero', 1432-1440), and the widgets' own `get_time()` contract defines midnight as this module's encoding of '24:00' (`if is_2400: from_python_time = time(0, 0)`, 1413-1416). The `hasattr` guard on the line before each try means a non-TimeLineEdit cell never reaches the parse.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005375 — `tabs/w3_drilling_report.py:72`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `None`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Matplotlib backend selection at import time: the fallback is an environment concern (the backend is set to Qt5Agg only when the current one is Agg/empty) and failing to set it cannot alter any computed or stored value - plotting then runs headless.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005448 — `tabs/w3_drilling_report.py:195`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DrillingReportWidget.set_current_report`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `set_current_report`'s `if not report_id: return` is a primary-key truthiness guard (positive ids; None means 'no report'). The method is a fan-out that loads the selected report into each tab, so returning early leaves the tabs as they are rather than loading anything with an invalid id.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005480 — `tabs/w3_drilling_report.py:959`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class D)
- **Symbol:** `DrillingParametersTab.load_from_dict`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `nozzles_json` is stored JSON, and the guard is narrow (`except (json.JSONDecodeError, TypeError)`). The table was just cleared (`self.nozzle_table.setRowCount(0)`, 950), so a malformed blob leaves an empty nozzle table instead of inventing rows, and the computed total area is taken from the recorded value through `safe_opt("tfa")` (962 - None when the report holds no recorded number).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005481 — `tabs/w3_drilling_report.py:913`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class D)
- **Symbol:** `DrillingParametersTab.load_from_dict.safe_val`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Cross-batch duplicate: same construct as p6-batch-005 INV34-008852 / INV34-008876 (`safe_val`'s `except (ValueError, TypeError): return default` in this very file, line 913 is the handler line of that helper). Adjudicated there: the default sits inside the widget's legal entry range and the same function's `safe_opt` carries the documented 'no recorded number -> None' contract for recorded/derived fields (916-917, used at 962). Counted once.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005484 — `tabs/w3_drilling_report.py:913`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class D)
- **Symbol:** `DrillingParametersTab.load_from_dict.safe_val`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Same line as INV34-005481 (the register fired two rules on one handler) and the same construct as p6-batch-005 INV34-008852 / INV34-008876. Adjudicated there; counted once.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005485 — `tabs/w3b_wellbore_schematic_tab.py:46`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `WellboreSchematicTab.__init__`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Signal wiring at construction time: `self.sel_manager.wellbore_changed.connect(...)` is an optional hook ('the bore signal is wired here', comment 43). A failure leaves the tab without that notification, which affects no stored value and no computation; the socket exists in every delivered build.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008231 — `tabs/w13_Engineering_Calculator.py:5338`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `EngineeringCalculatorTab.refresh`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Interactive volume preview: `_vol_update_quick()` is called from the dimension-control change handler only when both widgets exist (`hasattr` guards on the line before), and the display keeps its previous text if the recalculation fails. The canonical computation itself refuses invalid input loudly elsewhere (the engine raises), so this handler can only fail on a partial UI state during construction.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008232 — `tabs/w13_Engineering_Calculator.py:5339`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `EngineeringCalculatorTab.refresh`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w13_Engineering_Calculator.py:5338/5339 - the `pass` line of INV34-008231's handler, already adjudicated under INV34-008231: see the adjudication of INV34-008231
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008233 — `tabs/w13_Engineering_Calculator.py:5338`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class D)
- **Symbol:** `EngineeringCalculatorTab.refresh`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for tabs/w13_Engineering_Calculator.py:5338 - second rule on the same handler, already adjudicated under INV34-008231: see the adjudication of INV34-008231
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008234 — `tabs/w13_Engineering_Calculator.py:5339`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `EngineeringCalculatorTab.refresh`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w13_Engineering_Calculator.py:5338/5339 - the `pass` line of INV34-008231's handler (fourth rule on one construct), already adjudicated under INV34-008231: see the adjudication of INV34-008231
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008287 — `tabs/w2_Daily_Report.py:894`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget.add_time_log_row`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:893/894 - rule pair on one handler, already adjudicated under INV34-005192: see the adjudication of INV34-005192
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008288 — `tabs/w2_Daily_Report.py:963`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget._adjust_row_height`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:962/963 - rule pair on one handler, already adjudicated under INV34-005182: see the adjudication of INV34-005182
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008289 — `tabs/w2_Daily_Report.py:974`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget._adjust_all_row_heights`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:973/974 - rule pair on one handler, already adjudicated under INV34-005181: see the adjudication of INV34-005181
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008290 — `tabs/w2_Daily_Report.py:984`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget._get_recent_contractors`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:983/984 - rule pair on one handler, already adjudicated under INV34-005188: see the adjudication of INV34-005188
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008291 — `tabs/w2_Daily_Report.py:997`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget._get_recent_contractors`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:996/997 - rule pair on one handler, already adjudicated under INV34-005189: see the adjudication of INV34-005189
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008292 — `tabs/w2_Daily_Report.py:1006`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget._get_recent_contractors`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:1005/1006 - rule pair on one handler, already adjudicated under INV34-005190: see the adjudication of INV34-005190
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008294 — `tabs/w2_Daily_Report.py:1178`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget._build_header_snapshot`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not well_id or not self.db_manager: return {}` followed by `if not well: return {}` (1180-1182): an empty snapshot is this method's documented answer for both 'no well selected' and 'well not found', and every field of the snapshot is read with a defaulted ``.get`` from the real row - no value is invented.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008298 — `tabs/w2_Daily_Report.py:1406`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget._extract_time_log_row`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:1405/1406 - rule pair on one handler, already adjudicated under INV34-005371: see the adjudication of INV34-005371
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008299 — `tabs/w2_Daily_Report.py:1418`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget._extract_time_log_row`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:1417/1418 - rule pair on one handler, already adjudicated under INV34-005186: see the adjudication of INV34-005186
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008300 — `tabs/w2_Daily_Report.py:1430`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DailyReportWidget._extract_time_log_row`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w2_Daily_Report.py:1429/1430 - rule pair on one handler, already adjudicated under INV34-005187: see the adjudication of INV34-005187
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008302 — `tabs/w2_Daily_Report.py:1667`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.create_daily_report_for_current_section`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Rule mis-fire, not a behaviour to adjudicate: the subject is a *boolean* return, not a number - `dialog._copy_all_report_data(session, previous_id, created_id)` is a copy operation whose ``False`` is turned into `raise PermissionError("Copy denied")` (1667-1668), i.e. a fail-closed treatment of a documented success flag; no numeric value is involved.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008305 — `tabs/w2_Daily_Report.py:1961`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.copy_previous_day`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not well_id or not section_id: self.show_error("Well or section not selected"); return` - both required ids are checked with a visible reason before the operation.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008308 — `tabs/w2_Daily_Report.py:1995`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.copy_previous_day`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Rule mis-fire, not a behaviour to adjudicate: the subject is a *boolean* return - `copy_data_from_report(self, source, target) -> bool` (1745) and its ``False`` is answered with an explicit error and `return False` (1995-1997, 'Copy failed; existing target data was not replaced'); no numeric value is involved.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008314 — `tabs/w3_drilling_report.py:73`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `None`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w3_drilling_report.py:72/73 - rule pair on one handler, already adjudicated under INV34-005375: see the adjudication of INV34-005375
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008316 — `tabs/w3_drilling_report.py:960`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `DrillingParametersTab.load_from_dict`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w3_drilling_report.py:959/960 - rule pair on one handler, already adjudicated under INV34-005480: see the adjudication of INV34-005480
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008326 — `tabs/w3b_wellbore_schematic_tab.py:47`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `WellboreSchematicTab.__init__`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w3b_wellbore_schematic_tab.py:46/47 - rule pair on one handler, already adjudicated under INV34-005485: see the adjudication of INV34-005485
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008327 — `tabs/w3b_wellbore_schematic_tab.py:502`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `WellboreSchematicTab.auto_generate`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `auto_generate`'s guard checks both required preconditions and says so: `if not self.current_well_id or not self.db: self.canvas_status.setText("No well selected"); return` - the subject is a Well PK and the database handle; nothing is generated from an absent well.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008842 — `tabs/w2_Daily_Report.py:682`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.load_reports_for_section`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** The guard is complete for this subject: `if not section_id or section_id == -1: return` (682) covers both the unselected case and the combo's `-1` sentinel before the only DB call in the method (`get_daily_reports_by_section`), and the method's own docstring marks the load as optional.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008846 — `tabs/w2_Daily_Report.py:1510`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.load_report_dialog`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not section_id or section_id == -1: show_error(..."Please select a section first"); return` - the complete guard (absent and `-1` sentinel) with a visible reason, immediately before the save path.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008847 — `tabs/w2_Daily_Report.py:1650`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DailyReportWidget.create_daily_report_for_current_section`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if not section_id or section_id == -1: show_error(..."Please select a section first"); return` inside `create_daily_report_for_current_section` (which is itself gated by `@require_permission("can_edit_reports")`, 1647) - the complete guard, with the reason shown, before the report-creation flow.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-010131 — `tabs/w13_Engineering_Calculator.py:5344`

- **Rule / kind:** `R-EXC-PASS` / `broad-except` (HIGH, class D)
- **Symbol:** `EngineeringCalculatorTab.refresh`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Same shape as INV34-008231 for the annular preview (`_vol_update_annular()`, 5344): an interactive display refresh whose failure leaves the previous text - no value is written to the model or the DB by either call.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-010132 — `tabs/w13_Engineering_Calculator.py:5345`

- **Rule / kind:** `R-EXC-PASS` / `pass-statement` (HIGH, class D)
- **Symbol:** `EngineeringCalculatorTab.refresh`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for tabs/w13_Engineering_Calculator.py:5344/5345 - the `pass` line of INV34-010131's handler, already adjudicated under INV34-010131: see the adjudication of INV34-010131
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

