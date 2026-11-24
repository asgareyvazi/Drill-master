# M409 — suite profile (D88 decision input)

- Source run: SHA `1c5d0f7c023adbae10edc09055dee357ac406441`, Python 3.11.2, 8 shard(s).
- 6140 tests with a recorded duration in 447 files; summed test time 2946 s; summed shard wall time 3026 s (the difference is interpreter start-up, import and collection).
- LOCAL timings without coverage: only relative shares transfer to the CI 3.12 coverage leg.

## Top 25 files

| # | File | Seconds | Share | Cumulative |
|---|---|---|---|---|
| 1 | `tests/test_m215_scalar_correction_adversarial.py` | 105.4 | 3.6 % | 3.6 % |
| 2 | `tests/test_m300_m301_value_lineage.py` | 79.1 | 2.7 % | 6.3 % |
| 3 | `tests/test_m296_import_value_states.py` | 70.4 | 2.4 % | 8.7 % |
| 4 | `tests/test_m48_analysis_ui.py` | 61.7 | 2.1 % | 10.7 % |
| 5 | `tests/test_m102_context_probes.py` | 61.5 | 2.1 % | 12.8 % |
| 6 | `tests/test_m178_trajectory_views.py` | 61.5 | 2.1 % | 14.9 % |
| 7 | `tests/test_m50_analysis_async.py` | 57.6 | 2.0 % | 16.9 % |
| 8 | `tests/test_m326_window_lifecycle.py` | 54.9 | 1.9 % | 18.7 % |
| 9 | `tests/test_m173_scalar_correction.py` | 53.7 | 1.8 % | 20.6 % |
| 10 | `tests/test_db_restore_service.py` | 53.2 | 1.8 % | 22.4 % |
| 11 | `tests/test_m96_persistence_audit.py` | 53.0 | 1.8 % | 24.2 % |
| 12 | `tests/test_m70_integrity.py` | 52.7 | 1.8 % | 25.9 % |
| 13 | `tests/test_windows_release_evidence.py` | 47.4 | 1.6 % | 27.6 % |
| 14 | `tests/test_m51_analysis_snapshot.py` | 43.2 | 1.5 % | 29.0 % |
| 15 | `tests/test_m273_import_value_lineage.py` | 42.9 | 1.5 % | 30.5 % |
| 16 | `tests/test_m87_w13_contracts.py` | 42.6 | 1.4 % | 31.9 % |
| 17 | `tests/test_m204_immutable_write_paths.py` | 37.6 | 1.3 % | 33.2 % |
| 18 | `tests/test_m52_analysis_payloads.py` | 37.2 | 1.3 % | 34.5 % |
| 19 | `tests/test_credential_lifecycle.py` | 35.3 | 1.2 % | 35.7 % |
| 20 | `tests/test_m83_selection_lifecycle.py` | 33.5 | 1.1 % | 36.8 % |
| 21 | `tests/test_m181_m183_tubular_import.py` | 33.3 | 1.1 % | 37.9 % |
| 22 | `tests/test_sqlite_pool_isolation_m47.py` | 30.3 | 1.0 % | 39.0 % |
| 23 | `tests/test_ddr_followup_lifecycle.py` | 28.5 | 1.0 % | 39.9 % |
| 24 | `tests/test_r18_r19_save_preservation.py` | 28.5 | 1.0 % | 40.9 % |
| 25 | `tests/test_ddr_forensic_regressions.py` | 28.0 | 1.0 % | 41.8 % |

## Top 25 tests

| # | Test | Seconds |
|---|---|---|
| 1 | `tests/test_m48_analysis_ui.py::test_w12_scenario[no_global_warning_suppression_and_backend_untouched]` | 60.1 |
| 2 | `tests/test_m50_analysis_async.py::test_m50_analysis_scenario[currency_only_change_reaches_view_through_async_cycle]` | 56.9 |
| 3 | `tests/test_m51_analysis_snapshot.py::test_m51_analysis_scenario[no_gui_thread_sql_in_any_cycle_or_selection_path]` | 42.5 |
| 4 | `tests/test_m52_analysis_payloads.py::test_m52_analysis_scenario[snapshot_paint_builds_no_payload_on_the_gui_thread]` | 36.4 |
| 5 | `tests/test_db_restore_service.py::test_an_open_transaction_blocks_the_restore_until_it_ends` | 31.6 |
| 6 | `tests/test_m326_window_lifecycle.py::test_retained_windows_cost_is_bounded_and_stated` | 25.1 |
| 7 | `tests/test_privacy_check.py::test_tracked_repository_population_is_clean` | 20.6 |
| 8 | `tests/test_m83_selection_lifecycle.py::test_switching_wells_leaves_no_identifier_of_the_previous_well` | 18.3 |
| 9 | `tests/test_m115_ux_startup.py::test_the_startup_breakdown_accounts_for_every_tab` | 18.1 |
| 10 | `tests/test_m326_window_lifecycle.py::test_product_policy_closes_real_windows_without_a_crash_and_retains_them_on_the_pinned_pyside` | 17.8 |
| 11 | `tests/test_m102_context_probes.py::test_switch_to_another_well_leaves_no_alpha_value_anywhere` | 17.1 |
| 12 | `tests/test_m102_context_probes.py::test_clear_after_a_loaded_report_leaves_no_alpha_value` | 16.9 |
| 13 | `tests/test_m296_import_value_states.py::test_zero_is_stored_as_zero_and_blank_stays_none_without_events` | 14.6 |
| 14 | `tests/test_m102_context_probes.py::test_positive_controls_every_data_kind_is_visible_for_alpha` | 13.6 |
| 15 | `tests/test_m229_product_journey.py::test_m229_thirty_five_step_product_journey` | 13.5 |
| 16 | `tests/test_ddr_followup_lifecycle.py::test_actual_golden_lifecycle_save_all_and_clean_replay` | 13.0 |
| 17 | `tests/test_m51_gc_soak.py::test_mixed_load_never_collects_on_a_worker_and_reclaims_everything_on_the_gui_thread` | 12.7 |
| 18 | `tests/test_m83_selection_lifecycle.py::test_clear_leaves_an_empty_state_and_clean_edit_baselines` | 12.6 |
| 19 | `tests/test_m326_window_lifecycle.py::test_the_operator_can_force_retention_of_real_windows` | 12.1 |
| 20 | `tests/test_m95_ux_responsiveness.py::test_the_measurement_tool_runs_and_reports_every_path` | 11.7 |
| 21 | `tests/test_m169_end_to_end_journey.py::test_m169_twenty_step_journey` | 11.2 |
| 22 | `tests/test_m375_main_window_journey.py::test_thirty_five_step_journey_through_the_real_window` | 10.8 |
| 23 | `tests/test_release_boundary_imports.py::test_wheel_from_tracked_population_starts` | 10.3 |
| 24 | `tests/test_m122_assistant_worker_lifecycle.py::test_cancel_under_cpu_load_releases_every_worker` | 10.2 |
| 25 | `tests/test_m51_query_refinement.py::test_refining_every_refused_non_blind_question_keeps_scope_and_never_answers_an_unanswerable_one` | 10.1 |

Concentration: the 10 slowest files carry 22.4 % of the test time; 22 files take more than 30 s. No single file dominates, so a file-level split balances well.

## Balance of a file-level split (longest processing time first)

| Groups | Group seconds | Largest / ideal |
|---|---|---|
| 2 | 1473 / 1473 | 1.000 |
| 3 | 982 / 982 / 982 | 1.000 |

Scaling the 3.12 leg's last measured duration by the largest group's share estimates a split job's duration. The owner records the decision (split the coverage leg across jobs, shard it, or keep it and accept the TIMEOUT risk). Nothing in this report changes CI.
