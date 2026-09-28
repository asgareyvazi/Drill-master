# P6 p6-batch-003 — class A (safety / authorization / mutation) - all 45 records are class A (A:45)

records **45** over **43** sites · INTENTIONAL: 16 · DUPLICATE/FALSE-POSITIVE: 15 · VERIFIED-CORRECT: 13 · GENUINE_DEFECT: 1

## Defects fixed

- INV34-006021 / INV34-008432 - tabs/w7_logistics_Widget.py FuelWaterTab.update_bulk_stock_for_row (line 825): `float(cell.text() or 0)` turned an unreported opening balance into 0 and displayed a fabricated "Current Stock", while the em dash the loader writes for unknown raised through the handler. One statement, one defect, two register records. Fix commit c2e0016, regression tests/test_bulk_stock_three_state_smoke.py (mutation-killed: fabricated '5.0' observed with the original expression).

## INV34-002453 — `core/profile_import_engine.py:928`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `ProfileImportEngine._convert_time`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_convert_time` (915-930) returns `None` explicitly for input it cannot convert - an explicit sentinel, not a swallowed success. The consumer validates that sentinel at the persistence boundary: `time_from = ValueNormalizer.to_time(log.get("time_from"))` / `if time_from is None or time_to is None:` (core/ddr_import_service.py:972-974) creates a review item with `"classification": "invalid_time_range"`, `"reason": "Both time anchors are required for persistence"`, `"status": "REVIEW_REQUIRED"` and `continue`s without writing (975-984). The column is `time_from = Column(Time, nullable=False)` (core/database.py:719-720, 739-740), so an unconverted value cannot be stored silently either way.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003292 — `dialogs/engineering_dialogs.py:1079`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `AddSurveyDialog._save`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Inline contract at the handler: `pass  # uncalculated labels stay at 0 in the result payload` (1080). The five labels start as `"--"` (`_result_label`, 113-114) and `_update_calc` (1002-1051) is connected to every input spinner (998-1000) and always writes a parseable `"<number> <unit>"` string; the only early return (md2 <= md1, 1019-1021) is re-checked by `_save` before building the payload and aborts it (1062-1064). In the only reachable `pass` case - a dialog untouched since `--` - md, inc and azi are all 0, so the fallback zeros equal the true min-curvature result (`_update_calc` writes 0.00 north/east for a survey with no predecessor, 1004-1008). No fabricated measurement can reach `self.result`.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003296 — `dialogs/excel_import_dialog.py:285`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `ImportPreviewDialog._accept_high`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The helper's failure is fail-closed: on an unparseable confidence cell nothing is decided (`_set_decision` is not called, 283-284), so the row stays undecided - and the apply path requires an explicit decision: `decision = str(payload.get("decision", "REVIEW")).upper()` ... `if decision not in {"ACCEPT", "CONFIRMED"}: continue` (473-479). The protected action (auto-accepting a low-confidence row into the imported payload) therefore cannot happen after the check fails.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003300 — `dialogs/excel_import_dialog.py:191`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `ImportPreviewDialog._init_ui`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The handler covers only the confidence-based row tinting (`it.setBackground(QColor(...))`, 186-190). The item itself is written and the payload collected *outside* it - `self.table.setItem(row, col, it)` (193) and `self._row_payloads.append(item)` (196) - so a parse failure can skip a colour and nothing else: no row is dropped, no value is changed.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003301 — `dialogs/excel_import_dialog.py:330`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `ImportPreviewDialog._reject_low`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Same fail-closed shape as INV34-003296 in the mirror helper: an unparseable confidence cell means no automatic REJECT is recorded (328-329), the row stays undecided, and the apply filter accepts only explicit `ACCEPT`/`CONFIRMED` (473-479). A failure can therefore never turn into an automatic acceptance.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003362 — `dialogs/excel_import_dialog.py:628`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class A)
- **Symbol:** `ExcelImportDialog._result_key`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_result_key` is a key-normalisation helper, not a data path: `str(Path(source).expanduser().resolve())` with the documented fallback `except OSError: return str(source)` (625-629). The same function is applied to the same value on both sides (store: 632-634; lookup: 750), so the fallback key is deterministic and symmetric. No absent/failed result is mapped onto a 'no data' sentinel.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003864 — `main_window.py:1531`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MainWindow._delete_company`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Post-commit bookkeeping, and the mutation is independently fail-closed: `_check_delete_permission("company")` runs first (1498-1499) and is itself fail-closed - `core/hierarchy_operations.py:14-32` denies a viewer, denies when the permission is missing and returns False from `except Exception: logger.exception(...)` - then `session.delete(company)`/`session.commit()` (1518-1519) and a truthful success message. The audit write is wrapped for a reason: the delete is already committed, so propagating a logging failure would report a successful delete as failed. `log_audit` cannot raise at all - it rolls back, `logger.error(f"Audit log error: {e}")` and returns (core/database.py:10259-10279) - so the `pass` swallows nothing that is not already logged. Residual (recorded, not a defect claim): an audit-trail gap is logged, not shown to the user.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003866 — `main_window.py:1577`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MainWindow._delete_project`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Identical shape to INV34-003864 for projects: fail-closed permission gate first (`_check_delete_permission("project")`, 1544-1545 -> core/hierarchy_operations.py:14-32), then `session.commit()`, then the best-effort audit write whose failure is already logged inside `log_audit` (core/database.py:10275-10277) and which cannot be allowed to falsify the already-committed delete.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003868 — `main_window.py:1668`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MainWindow._delete_section`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Identical shape to INV34-003864 for sections: fail-closed permission gate first (`_check_delete_permission("section")`), then the committed delete, then the best-effort audit write (`log_audit` logs its own failure, core/database.py:10275-10277).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003870 — `main_window.py:1621`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MainWindow._delete_well`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Identical shape to INV34-003864 for wells: the fail-closed permission gate runs before the mutation (`_check_delete_permission("well")`), the `else` branch reports a refused delete explicitly (1623-1626), and the audit write is best-effort with its own logging inside `log_audit`.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003874 — `main_window.py:402`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MainWindow._restore_dock_state`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_restore_dock_state` touches only QSettings layout keys - `dock/hierarchy_geometry` and `dock/hierarchy_visible` (395-401); a failure leaves the default dock layout. No domain state is read or written, and nothing is reported as saved.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-003875 — `main_window.py:416`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MainWindow._save_dock_state`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_save_dock_state` writes the same two QSettings layout keys (407-415); a failure means only that window layout is not remembered. Cosmetic UI preference, no domain state.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-004382 — `tabs/w12_Analysis.py:1658`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `AnalysisWidget.update_time_depth_data`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The try in `update_time_depth_data` wraps only the trend-line decoration (`np.polyval` + `pg.mkPen(...)`/`name="Trend Line"`, 1640-1657). The plot is then reset and rebuilt independently (`self.daily_gain_plot.clear()` 1661 ff.), so a failure can only omit an annotation - no computed value is stored, exported or reported as saved.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-004593 — `tabs/w12_Analysis.py:2922`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class A)
- **Symbol:** `AnalysisWidget._export_charts_to_pdf`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** The handler is typed (`except ImportError`, 2922) and its body is an explicit, documented fallback: write PNG instead of PDF and `return False` (2923-2925) - the caller can distinguish the fallback from success because the return value says so. In addition `_export_charts_to_pdf` has no reference anywhere in the tracked tree (repo-wide `grep -rn "_export_charts_to_pdf"` finds only its definition), so no consumer can mistake the result for a written PDF.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-004918 — `tabs/w13_Engineering_Calculator.py:1426`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `EngineeringCalculatorTab._hy_update_tfa`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Inline contract at the handler: `pass  # non-numeric nozzle cell` (1427). The only sink is a display label - `self.hy_tfa_label.setText(...)` (1428), created at 1131 and never read back anywhere (grep: no `hy_tfa_label.text()`), and the nozzle Area column is `setEditTriggers(QTableWidget.NoEditTriggers)` (1140), i.e. filled by the application. Nothing persisted or calculated depends on this total.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005023 — `tabs/w14_Procedure_Widget.py:951`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ProcedureEditorPage.save_procedure`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `save_procedure` is typed `-> int`, commits and returns the procedure id, and on failure rolls back and `return None` (core/database.py:9575-9602). Ids are primary keys (never 0), so `if not proc_id:` is exactly the documented failure test - and the caller reports it and returns False instead of continuing with a non-existent procedure (952-953).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005316 — `tabs/w2_Daily_Report.py:1207`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DailyReportWidget._validate_save_preconditions`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `well_id` is the id of the selected well: 0/None means 'no well selected' - which is what the message says (1208) - and the value is additionally proven against the database (`sections = self.db_manager.get_sections_by_well(well_id)` ... `if section_id not in valid_ids: return False, "Selected section does not belong to this well..."`, 1213-1217). A legitimate primary key cannot be 0.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005374 — `tabs/w2_Daily_Report.py:1899`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `DailyReportWidget.update_statistics`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Inline contract at the handler: `pass  # incomplete row — excluded from totals` (1900). The totals feed three display labels and a colour threshold (`total_time_label`/`total_npt_label`/`productivity_label`, 1901-1912) - no persistence, no exported value, and no fabricated number: the rows that are excluded contribute nothing to a sum.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005534 — `tabs/w3b_wellbore_schematic_tab.py:785`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `WellboreSchematicTab._update_casings_from_table`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The handler is scoped to per-field numeric parses, and the same function implements the explicit three-state contract where the field is a measurement the user can leave unknown: `id_text in ("", "—", "-")` -> `casing.id_inch = None` with the comment "explicitly unknown wall thickness (None); a numeric value (including 0) is a real fact." (772-778). A failed parse leaves that field unchanged (the last known fact) and still applies the remaining fields of the row; nothing fabricates a 0. The persisted model (save_data, 953-991) stores whatever the shared model holds and reports failures (997-1000). Residual (recorded, not a defect claim): clearing a previously known OD/depth cell keeps the prior value in the model - a stale fact, not a fabricated one - and only the id column has an explicit unknown path.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005535 — `tabs/w3b_wellbore_schematic_tab.py:815`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `WellboreSchematicTab._update_formations_from_table`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The rebuild is wholesale (`new_formations` is built and then assigned to `self.schematic.formations`, 818), and a row whose depth cells cannot be parsed is left out of it - the same convention the sibling export documents for incomplete rows: `pass  # incomplete formation row stays out of the LAS export` (tabs/w4_Downhole_Widget.py:889). No depth is invented; an incomplete formation cannot be drawn.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005744 — `tabs/w3c_section_data.py:573`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `CasingTallyWidget.update_statistics`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The three statistics are initialised inside the method (`tl=tw=tc=0.0`, 562) and feed only QLabel text (`self.stats_labels[...]`, 576-579). The cells they read are written by the application itself as numbers (`it.setText(f"{val:.2f}" ...)`, 555), so the handler cannot hide a miscalculation of the tally - it can only skip a column for an uncomputed row.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005834 — `tabs/w4_Downhole_Widget.py:888`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `FormationManager.export_to_las`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Inline contract at the handler: `pass  # incomplete formation row stays out of the LAS export` (889). The export reports its own failure - `except Exception as e: logger.error(f"LAS export error: {e}")` ... `return False` (895-897) - and returns True only after `las.write(...)` (890-894), so an incomplete row is excluded from the artifact while the caller still learns whether the file was written.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005839 — `tabs/w5_Equipment_Widget.py:888`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class A)
- **Symbol:** `EquipmentWidget._report_date_for_current`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Re-anchored: the register's `except Exception:` at line 888 is line 898 in the current tree (the W5 fix 9f45cc4 shifted the file by +10; verified against the previous blob). The site is `_report_date_for_current`, documented "Best-effort report_date for the current report (for carry-forward)." (893): on a missing report, a failed lookup or an unusable row it returns `None` - never a substituted date - and the caller passes that None through (`report_date=self._report_date_for_current()`, 918) instead of inventing today's date.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005886 — `tabs/w5_Equipment_Widget.py:959`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `EquipmentWidget._load_inventory_rows`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Re-anchored: the register's `if legacy:` at line 959 is line 969 in the current tree (same +10 offset, verified against the previous blob). `legacy` is a boolean flag set by `legacy = bool(items)` (950), so truthiness is the correct test, and the numeric trichotomy in the same function is handled by `_inv_cell` for every quantity (opening_stock/received/used/current_stock/min_level/max_level, 960-966) under the documented "Read-only, unknown preserved." (945-946) - asserted on the real widget by tests/test_inventory_live_calc_smoke.py, which passes on this worktree.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-005964 — `tabs/w6_Trajectory_Widget.py:640`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `TrajectoryPlotTab.save_plot`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `save_plot` returns True only for a real id: the callee commits and `return plot.id`, and on any failure rolls back, logs `Error saving trajectory plot` and `return None` (core/database.py:6707-6727). Ids are primary keys, so `if plot_id:` cannot mistake a success for a failure or vice versa; the False return is the documented failure result.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-006021 — `tabs/w7_logistics_Widget.py:825`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class A)
- **Symbol:** `FuelWaterTab.update_bulk_stock_for_row`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** GENUINE DEFECT (fixed in c2e0016, this batch). `initial = float(initial_item.text() or 0)` turned a blank cell into 0, so a row whose opening stock was never reported displayed a fabricated "Current Stock" balance, and the same expression fed the em dash that the widget's own loader writes (`_fmt_stock`: "Unknown stock displays as an em dash, never as 0.0.", 1217) into `float("—")`, raising into the outer handler and leaving the cell without a value. Both contradict the persistence boundary of the same widget: "an EMPTY cell is 'not reported' (None) - carry-forward/unknown downstream. A typed 0 is an explicit zero and is preserved exactly." (`_cell_float`, 1156-1158). Fix: blank and em dash are unknown -> the computed stock is unknown (em dash); a typed 0 stays a fact. Evidence: tests/test_bulk_stock_three_state_smoke.py passes on the fix and fails under mutation with AssertionError ('blank opening must leave the computed stock UNKNOWN, not fabricated', '5.0'). Same-class search: 7 hits repo-wide, all in this widget; the three fixed here and `calculate_bulk_totals` (1118-1121) left unchanged because its `or 0` is numerically neutral in a sum that only feeds a transient message box.
- **Classification:** GENUINE_DEFECT
- **Defect:** yes
- **Test:** tests/test_bulk_stock_three_state_smoke.py (subprocess-isolated; fails under mutation)
- **Commit:** c2e0016
- **Remaining question:** none

## INV34-007682 — `core/profile_import_engine.py:929`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `ProfileImportEngine._convert_time`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second record of the handler already adjudicated under INV34-002453 (core/profile_import_engine.py:923-929): R-EXC-PASS records the `except (TypeError, ValueError):` line and this id the `pass`/`return None` that follow it, i.e. one behaviour counted twice by the rule engine. Adjudicated once under INV34-002453 (the explicit `None` sentinel is turned into REVIEW_REQUIRED by core/ddr_import_service.py:972-984); no independent finding here.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007937 — `dialogs/excel_import_dialog.py:192`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `ImportPreviewDialog._init_ui`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003300 (dialogs/excel_import_dialog.py:191/192): the register holds a second record for the identical try/except handler - `INV34-003300` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003300`; the failure only skips row tinting, the payload is appended outside the handler.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007938 — `dialogs/excel_import_dialog.py:286`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `ImportPreviewDialog._accept_high`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003296 (dialogs/excel_import_dialog.py:285/286): the register holds a second record for the identical try/except handler - `INV34-003296` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003296`; a failed parse leaves the row undecided, which the apply filter (473-479) refuses to import.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007939 — `dialogs/excel_import_dialog.py:331`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `ImportPreviewDialog._reject_low`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003301 (dialogs/excel_import_dialog.py:330/331): the register holds a second record for the identical try/except handler - `INV34-003301` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003301`; a failed parse leaves the row undecided rather than auto-rejected, and undecided rows are not applied (473-479).
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008039 — `main_window.py:403`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `MainWindow._restore_dock_state`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003874 (main_window.py:402/403): the register holds a second record for the identical try/except handler - `INV34-003874` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003874`; the failure can only mean the default dock layout.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008040 — `main_window.py:417`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `MainWindow._save_dock_state`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003875 (main_window.py:416/417): the register holds a second record for the identical try/except handler - `INV34-003875` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003875`; the failure can only mean window layout is not remembered.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008047 — `main_window.py:1532`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `MainWindow._delete_company`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003864 (main_window.py:1531/1532): the register holds a second record for the identical try/except handler - `INV34-003864` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003864`; the delete is already committed and `log_audit` logs its own failure.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008050 — `main_window.py:1578`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `MainWindow._delete_project`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003866 (main_window.py:1577/1578): the register holds a second record for the identical try/except handler - `INV34-003866` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003866`; the delete is already committed and `log_audit` logs its own failure.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008052 — `main_window.py:1622`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `MainWindow._delete_well`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003870 (main_window.py:1621/1622): the register holds a second record for the identical try/except handler - `INV34-003870` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003870`; the delete is already committed and `log_audit` logs its own failure.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008055 — `main_window.py:1669`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `MainWindow._delete_section`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-003868 (main_window.py:1668/1669): the register holds a second record for the identical try/except handler - `INV34-003868` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-003868`; the delete is already committed and `log_audit` logs its own failure.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008112 — `tabs/w11_Export.py:194`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ExportWidget._load_ddr_reports`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `well_id = self.ddr_well.currentData()` (193) is the combo box's payload, i.e. a report well id or None; `if not well_id or not self.db: return` (194) is the pre-condition for listing reports and no legitimate primary key is 0. The guard protects a read-only list population (`get_daily_reports_by_well`, 196-201).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008126 — `tabs/w12_Analysis.py:1659`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `AnalysisWidget.update_time_depth_data`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-004382 (tabs/w12_Analysis.py:1658/1659): the register holds a second record for the identical try/except handler - `INV34-004382` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-004382`; the failure only omits the trend-line annotation on the plot.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008242 — `tabs/w14_Procedure_Widget.py:951`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ProcedureEditorPage.save_procedure`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Exact duplicate register record of INV34-005023: same file, same line (tabs/w14_Procedure_Widget.py:951), same rule (R-TRUTH-NUMERIC), same recorded source text (`if not proc_id:`). One statement, adjudicated once under INV34-005023 (`save_procedure` returns a primary key or None, core/database.py:9575-9602); this record adds no second finding.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008295 — `tabs/w2_Daily_Report.py:1245`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DailyReportWidget.save_report`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Documented fallback with its own comment (`# fallback از گزارش جاری`, 1244): when the widget's cached selection is empty it reads the ids from the report that is already loaded (`self.current_report.get("well_id")` / `.get("section_id")`, 1245-1248) - a read-only attribution, no invented owner - and the result is validated before any write (1250-1252 -> 1213-1217).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008328 — `tabs/w3b_wellbore_schematic_tab.py:786`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `WellboreSchematicTab._update_casings_from_table`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-005534 (tabs/w3b_wellbore_schematic_tab.py:785/786): the register holds a second record for the identical try/except handler - `INV34-005534` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-005534`; a failed parse leaves the field unchanged and the id column has its own explicit unknown path (772-778).
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008330 — `tabs/w3b_wellbore_schematic_tab.py:945`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `WellboreSchematicTab.save_data`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `save_data` guards on a primary key and the presence of the store before writing anything (`if not self.current_well_id or not self.db: return False`, 945-946); every failure path reports (`logger.error` + `self.show_error(...)`, 997-999) and returns False. Zero cannot be a legitimate well id.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008333 — `tabs/w3c_section_data.py:574`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `CasingTallyWidget.update_statistics`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same construct as INV34-005744 (tabs/w3c_section_data.py:573/574): the register holds a second record for the identical try/except handler - `INV34-005744` fired on the `except` line and this id on the `pass` line of the same handler. One behaviour, adjudicated once under `INV34-005744`; the statistics are initialised per call and feed display labels only.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008432 — `tabs/w7_logistics_Widget.py:825`

- **Rule / kind:** `R-DEF-VALUE-PATH` / `or-zero` (HIGH, class A)
- **Symbol:** `FuelWaterTab.update_bulk_stock_for_row`
- **Register question:** Is this default allowed to reach a consumer?
- **Evidence:** Exact duplicate register record of INV34-006021: same file, same line (825), same rule (R-DEF-VALUE-PATH), same `source_sha256` (c5aee6d2...) and the same recorded source text (`initial = float(initial_item.text() or 0)`). The statement is defective and is fixed once under INV34-006021 (commit c2e0016, regression tests/test_bulk_stock_three_state_smoke.py); this record adds no second defect and is counted once.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** c2e0016
- **Remaining question:** none

## INV34-008845 — `tabs/w2_Daily_Report.py:1210`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DailyReportWidget._validate_save_preconditions`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `section_id` is a primary key with an explicit 'not selected' sentinel: `if not section_id or section_id == -1:` (1210-1211), and the resolved value is then validated against the well's own sections (1213-1217). Zero/-1 mean 'nothing selected', not a real section.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit c2e0016, evidence commit recorded in the ledger)
- **Remaining question:** none

