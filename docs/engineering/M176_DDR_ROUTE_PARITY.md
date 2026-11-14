# M176: DDR import route parity and file provenance

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. **Real-document acceptance: NOT RUN.** The standing rule "never open 08-DDR … .xlsx" is not reversed, and no owner-authorized confidential DDR was used. Every row below rests on SYNTHETIC fixtures only.

Tests: `tests/test_m176_route_parity.py` (13 tests). Mutants: `tools/quality/mutation_m171_m200.py`, 8 `M176-*` mutants (including `M176-applied-profile-lost`).

## 1. Provenance contract `ddr-source-provenance-v1`

`core.ddr_import_pipeline.source_provenance(source, *, route, route_reason, fallback_engine, extracted)` builds one record per import. `prepare_import` writes it to `import_report["source_provenance"]` and `extracted["metadata"]["source_provenance"]`. The smart template dialog builds the same record with route `smart_template`.

| Field | Meaning |
|---|---|
| `file_name`, `sha256`, `size_bytes` | the file as read. An unreadable file gives `sha256 = None` and `size_bytes = None` (**unknown, never 0**; `test_unreadable_size_is_unknown_not_zero`) |
| `route`, `route_reason`, `fallback_engine` | the route taken and why (`core.import_router.route_file`) |
| `engine` / `backend` / `method` | e.g. `pdf_fallback` / `pdf-native-fallback` |
| `profile` | `{key, version}` of the profile the route **applied** (from `extracted.metadata.profile`), otherwise None. The offered profile is never recorded: the isolated-process and worker-thread paths must give identical results (`tests/test_m111_isolated_parse.py`; `test_provenance_names_a_profile_only_when_the_route_applied_it`) |
| versions | pipeline 2, profile rules 2 (M174), header rules 1 |

Cell-level provenance keeps `{page, row, column}` (PDF / MinerU) or `_source_cells` / sheet+cell (XLSX profile). The payload fingerprint (`core.ddr_import_service`) **excludes** `source_provenance` and `well_identity_decision`, so re-importing the same content is still recognised (`test_file_provenance_is_not_part_of_the_payload_fingerprint`).

## 2. Route parity matrix (synthetic)

Fixture rows: 00:00–06:00 "Drill ahead", a wrapped continuation line "with full returns", 06:00–08:00 "POOH".

| Route | Morning / 24 h | Multi-page | Multi-table | Mixed headers | Missing time anchor | Continuation line | Provenance | Test |
|---|---|---|---|---|---|---|---|---|
| XLSX profile (golden) | profile sections | n/a | per profile | profile aliases (M174) | no time invented | review queue (M147) | sha256 + sheet / cell | `test_xlsx_profile_route_golden_fixture_provenance` |
| Generic Excel (`generic-ir`) | **LIMITATION**: label/value only | n/a | **LIMITATION**: 1 log; a table-like region (e.g. A5:E9) goes to `unmapped_content` and is reported | REVIEW proposals | no time invented | — | sha256; no `_source_cells` | `test_generic_excel_route_is_label_value_only_and_reports_the_rest` |
| Smart template | template mapping | n/a | template mapping | template mapping | no time invented | — | sha256 + source rows, route `smart_template` | `test_smart_template_route_keeps_source_rows_and_file_provenance` |
| Native PDF fallback | heading binds the section (`SECTION_FROM_HEADING`) | **per-row page** (`row_pages`) | each table to its section | same records | no time invented | joined **as a review notice** (`pdf-wrapped-line-v1`, page / row / column), never silently | sha256, backend `pdf-native-fallback` | `test_native_pdf_route_reports_its_wrapped_line_join…`, `test_native_pdf_multi_page_table_keeps_row_pages…` |
| MinerU (when installed; owner-gated) | `SECTION_FROM_HEADING` | per-row page | each table to its section | same records | no time invented | kept as its own row, eligible for review (parent 0, proposed, not merged) | cells `{page, row, column}` | `test_mineru_route_keeps_the_continuation…`, `test_morning_heading_binds…`, `test_multi_table_document…`, `test_mixed_headers_give_the_same_records` |
| Fallback (no route) | — | — | — | — | — | — | route `fallback` with reason | covered by `route_file` tests |

## 3. Defects found and fixed in M176

1. **A morning-heading table was parked unstored.** Bare From/To resolved to `time_log` while Hrs under a morning heading resolved to `time_log_morning`, so the mixed table was parked in `document_tables`. Fix: `_bind_time_log_section` (`ddr-time-log-section-v1`, state `SECTION_FROM_HEADING`). Test: `test_morning_heading_binds_the_morning_section_and_24h_stays_24h`.
2. **Rows on page 2 of a continued table were attributed to page 1.** Fix: `DocumentTable.row_pages` and `_row_page()` at all 5 provenance sites. Test: `test_native_pdf_multi_page_table_keeps_row_pages_and_join_positions`.
3. **A table that could not be stored was parked silently.** Fix: explicit review warning `document-table-not-stored-v1`. Test: `test_missing_time_anchors_invent_no_times_and_mixed_tables_are_never_silent`.
4. **The provenance profile differed between the isolated and thread paths** (it recorded the offered profile). Fix: record only the applied profile. Tests: `tests/test_m111_isolated_parse.py` (4 tests restored), and `test_provenance_names_a_profile_only_when_the_route_applied_it`.

## 4. Not claimed

* Real-document acceptance: **NOT RUN**. No confidential DDR was opened, uploaded or committed.
* Generic Excel parity with the profile route is not claimed (see LIMITATION).
* MinerU itself is owner-gated (licence). Its route is tested with synthetic `MinerUDocument` objects.
