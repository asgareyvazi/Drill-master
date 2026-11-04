# M117 – User journeys A–Z through the real desktop widgets

Status: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.** These are automated journeys on SYNTHETIC
data in temporary SQLite databases, run with offscreen Qt on Linux. They are not a Windows desktop acceptance
and not a field acceptance; both remain owner gates.

## What counts as a widget journey

`tools/quality/journey_index.py` holds the register and computes the level of every cited test from its
source code (AST); no level is declared by hand.

- **widget**: the test function, or a fixture or helper in the same file that it reaches, uses a name imported
  from `tabs`, `dialogs`, `main_window` or `PySide6.QtWidgets`. A module-level child-process script that imports
  them also counts (subprocess journeys such as backup/restore).
- `QApplication` alone does **not** count. An application object is not a user-facing widget, so a test that
  only creates one (for example the M103 `ContextJobRunner` tests) is service level.
- **missing**: the citation does not resolve to a test function. The register then fails.

The computed level is necessary, not sufficient, so every citation was also read for what it asserts.
Example of a rejected citation: `tests/test_audited_mutations.py::test_main_window_delete_routes_through_the_audited_service`
imports `main_window`, so the classifier calls it widget level. It drives `MainWindow._delete_hierarchy_item`
with a `SimpleNamespace` stand-in rather than a real window, so it was not used for journey Z. Z cites a
new test with the real documents tab instead.

## New in M117 (`tests/test_m117_widget_journeys.py`)

| Journey | What the widget test proves |
|---|---|
| G | A survey revision tampered with outside the program shows `HASH MISMATCH` in the revision panel. Converting it is refused with the SHA-256 reason, and nothing is derived from it. The stored data is not repaired. Positive control: the intact revision converts |
| M | A trajectory record of the pre-M108 shape shows "unversioned (legacy)" in the history tab and "Reproducible: NOT REPRODUCIBLE" when selected. A re-run returns `NOT_REPRODUCIBLE` ("before M108"), nothing can be stored, and no method version is assigned |
| U | W11 batch export with "Professional workbook per report" writes one workbook per report through the real generators. Each workbook's provenance names only its own report and "Report revision: none recorded" (never "Rev 0") |
| X | With `socket.create_connection` and `socket.connect` patched to fail, the documents tab runs a well-scoped search with file and page citations. A search without hits states the text-layer limitation |
| Z | Deleting one well through the audited service removes only that well, its report and its document link. The other wells, their reports and the open search are unchanged, and the deleted well's document stays in the library, now unlinked |

## Register

<!-- journeys:begin -->

| Journey | Level | Tests (computed level) |
|---|---|---|
| A — Context selection reaches every tab, no leak | widget | `tests/test_m102_context_probes.py::test_switch_to_another_well_leaves_no_alpha_value_anywhere` (widget)<br>`tests/test_m102_context_probes.py::test_every_tab_receives_the_full_context` (widget) |
| B — Async job and a context switch | widget | `tests/test_m103_context_jobs.py::test_oa_switch_during_the_job_shows_nothing_of_either_well` (widget)<br>`tests/test_m103_context_jobs.py::test_oa_close_during_the_job_joins_the_worker` (widget) |
| C — DDR manual edit, save and reload | widget | `tests/test_m52_ddr_manual_edit.py::test_a_reordered_time_log_survives_save_and_reload` (widget) |
| D — DDR import cancel saves nothing | widget | `tests/test_import_dialog_reentrancy.py::test_preview_cancel_persists_nothing` (widget)<br>`tests/test_m111_isolated_parse.py::test_cancel_during_an_isolated_parse_saves_nothing_and_stops_the_child` (widget) |
| E — Source file changed during preview | widget | `tests/test_m84_ddr_identity_cleanup.py::test_a_file_changed_during_preview_is_never_saved` (widget) |
| F — Survey reference and datum declared | widget | `tests/test_m85_survey_references.py::test_panel_requires_declaration_and_converts_with_explicit_values` (widget) |
| G — Survey integrity: tampered results refused | widget | `tests/test_m117_widget_journeys.py::test_journey_g_a_tampered_survey_is_shown_as_such_and_refused_for_use` (widget) |
| H — Azimuth transform as a new revision | widget | `tests/test_m85_survey_references.py::test_panel_requires_declaration_and_converts_with_explicit_values` (widget) |
| I — Multi-segment plan through all targets | widget | `tests/test_m106_multi_segment_solver.py::test_designer_panel_solves_through_all_targets_and_an_s_profile` (widget) |
| J — Infeasible plan explained, not approximated | widget | `tests/test_m106_multi_segment_solver.py::test_designer_panel_solves_through_all_targets_and_an_s_profile` (widget) |
| K — Compare only in the same reference/scope | widget | `tests/test_m105_survey_references.py::test_the_compare_panel_refuses_a_plan_in_another_reference_and_labels_undeclared_ones` (widget)<br>`tests/test_m108_history_coverage.py::test_history_tab_compare_shows_the_full_field_table` (widget) |
| L — W13 calculation saved and re-run | widget | `tests/test_m87_w13_contracts.py::test_bit_case_save_reopen_rerun_clone_export_and_verify` (widget)<br>`tests/test_m107_w13_contracts.py::test_balanced_plug_parity` (widget) |
| M — Legacy record NOT_REPRODUCIBLE | widget | `tests/test_m117_widget_journeys.py::test_journey_m_a_legacy_record_is_not_reproducible_in_the_history_tab` (widget) |
| N — Lineage navigation in history | widget | `tests/test_m88_history_lineage.py::test_history_tab_opens_a_linked_record_on_another_page` (widget)<br>`tests/test_m70_verification_lineage.py::test_history_tab_lineage_navigation` (widget) |
| O — Architecture to casing with lineage | widget | `tests/test_m89_architecture_casing_cement.py::test_w13_casing_from_architecture_reaches_history_with_lineage` (widget) |
| P — Cement worksheet re-run as a linked case | widget | `tests/test_m109_cement_worksheet.py::test_a_rerun_is_stored_as_a_new_linked_case_and_the_original_is_unchanged` (widget) |
| Q — Wellbore-scoped operational analysis | widget | `tests/test_m102_context_probes.py::test_wellbore_reaches_every_tab_and_resets_on_a_well_switch` (widget)<br>`tests/test_m104_operational_kpis.py::test_the_panel_shows_the_kpi_register_first` (widget) |
| R — Operational analysis drill-down | widget | `tests/test_m94_e2e_journeys.py::test_journey_context_to_operational_analysis_drilldown_and_switch` (widget)<br>`tests/test_m91_operational_analysis.py::test_w12_page_refresh_drilldown_invalidation_and_export` (widget) |
| S — Plan vs actual in scope | widget | `tests/test_m55_directional.py::test_the_viewer_sends_a_designed_plan_to_plan_vs_actual` (widget) |
| T — Single report export (W11) | widget | `tests/test_m94_e2e_journeys.py::test_journey_report_export_through_w11_carries_the_selected_well_only` (widget) |
| U — Multi-report professional workbooks | widget | `tests/test_m117_widget_journeys.py::test_journey_u_w11_writes_one_professional_workbook_per_report` (widget) |
| V — Method catalogue (read-only) | widget | `tests/test_m92_method_catalogue.py::test_help_menu_opens_a_read_only_catalogue` (widget) |
| W — RTL and LTR | widget | `tests/test_m94_e2e_journeys.py::test_journey_persian_well_report_right_to_left` (widget)<br>`tests/test_m53_dashboard.py::test_dashboard_is_english_and_left_to_right_even_in_an_rtl_application` (widget) |
| X — Offline use | widget | `tests/test_m117_widget_journeys.py::test_journey_x_the_documents_tab_works_with_no_network` (widget) |
| Y — Backup and restore | widget | `tests/test_db_maintenance_ui.py::test_backup_and_restore_ui_flow_in_subprocess` (widget) |
| Z — Delete isolation | widget | `tests/test_m117_widget_journeys.py::test_journey_z_deleting_one_well_leaves_every_other_well_intact` (widget) |

Journeys walked through real widgets: 26 of 26.

<!-- journeys:end -->

## Limits

- Offscreen Linux only; no real display, no Windows file dialogs, fonts or DPI behaviour.
- Dialog boxes (`QMessageBox`, `QFileDialog`) are replaced by fixed answers in the tests; the code that uses
  the answers is the production code.
- "Walked through widgets" means the production widget methods that the buttons call were driven
  (`run_search`, `convert_selected`, `recalculate`, `_export_batch`, …). Mouse events are not synthesised.
