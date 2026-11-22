# M320 D (M287) — Report Center section manifest

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC data only.

* `core/report_sections.py` (`MANIFEST_VERSION` "M320-D report section manifest v1").
* **Section statuses.** Every DDR and EOWR template section is listed with one of these:
  * **INCLUDED**, with a row count;
  * **NOT_RECORDED**;
  * **SUMMARISED** (counts only: EOWR 7 Casing/cementing, 10 Logistics);
  * **QUERY_FAILED** (EOWR 11 Cost, when the cost query failed);
  * **NOT_RENDERED**, with row counts (bit and BHA reports, 24-hour and morning time logs, material requests,
    equipment logs).
* **Explicit details:**
  * Time analysis with no hours is NOT_RECORDED: "percentages are unknown, not 100 % productive".
  * No cost data is NOT_RECORDED, "not a reported zero".
* **Distribution:** the manifest travels in the report provenance (`report_provenance.emit` and `rows`), so it
  reaches HTML, PDF, the Excel Provenance sheet and the CSV `# section manifest` row.
* **Other report kinds:** NPT, Cost and Plan reports say that no manifest is available for that kind.
* **Report body:** `report_engine` now prints "Not recorded: no X data was submitted for this scope." for drilling
  parameters, mud, the 24-hour operations table, the morning tour and the operations summary. EOWR sections 4 and
  5 get the same treatment. Previously these sections were silently omitted.

**Tests:** `tests/test_m320d_report_sections.py` has 8 tests, 0 failures. Together with `test_m93_report_provenance`
and `test_eowr_cost_query_status`, they are included in the full-suite run. Ruff is clean.

**Status:** COMPLETE for DDR and EOWR; NPT, Cost and Plan are explicitly out of scope.
