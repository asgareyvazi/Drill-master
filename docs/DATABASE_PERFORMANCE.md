# Database performance: schema v6 secondary indexes

Evidence for the 95 secondary indexes added in schema v6
(`core/schema_indexes.py`, M43). Every figure below comes from
`tools/perf/db_workload.py` runs on synthetic data. No figure is estimated.

## Command

```bash
# after (schema v6, 95 secondary indexes)
python tools/perf/db_workload.py --output perf_after_v6.json
# same code and data with the secondary indexes dropped (control)
python tools/perf/db_workload.py --drop-secondary-indexes --output perf_after_v6_noidx.json
```

The "before" run used the same tool and arguments on the schema v5 code
(commit `0e43e84`). Defaults: `--wells 5 --reports-per-well 100 --repeats 25
--warmup 3 --seed 4300`.

## What is measured

* **Data:** deterministic synthetic hierarchy (seed 4300): 5 wells and 500
  daily reports with related rows (24-hour time logs, survey points, mud
  reports, cost records, revisions, approvals, audit entries). No real or
  personnel data. Building the data is separate from timing.
* **Operations (16):** the application's own queries: list reports by well
  and by section, open a report header and its full snapshot, time logs,
  surveys by well and by report, revisions, approval history, audit for a
  report, recent audit, the dashboard "reports today" count, the hierarchy
  tree, cost totals, latest mud report, and deleting a report (cascades).
* **Timing:** 3 warm-up runs, then 25 timed runs per operation; median and
  95th percentile in milliseconds.
* **Plans:** every SQL statement an operation issues is captured and run
  through `EXPLAIN QUERY PLAN`. A *full-scan statement* has a `SCAN <table>`
  step without `USING`; full scans of an index are reported separately below.
* **Settings:** production PRAGMAs applied by `core/sqlite_connection.py`.
  `ANALYZE` is not run in any mode because the application never runs it.
* **Default test suite:** `tests/test_db_workload.py` checks the plans
  structurally (no timing assertions).

## Environment

| Item | Value |
|---|---|
| Platform | Linux 6.1 x86_64, Intel Xeon 2.60 GHz, 2 vCPU, 3.9 GiB RAM (sandbox VM) |
| Python / SQLite / SQLAlchemy | 3.11.2 / 3.40.1 / 2.0.36 |
| PRAGMAs (read back) | `journal_mode=wal`, `synchronous=1` (NORMAL), `foreign_keys=1`, `busy_timeout=30000`, `cache_size=10000`, `page_size=4096` |
| Load during the after runs | load average about 0.4; no other test or benchmark process running |

## Results (milliseconds, median / p95; one run of 25 repeats per configuration)

| Operation | v5 (before) | v6 (after) | v6, indexes dropped | Full-scan statements v5 → v6 (dropped) | Statements |
|---|---|---|---|---|---|
| list_reports_by_well | 1.611 / 1.794 | 1.527 / 1.63 | 1.409 / 1.579 | 1 → 0 (1) | 1 |
| list_reports_by_section | 0.775 / 0.837 | 0.647 / 0.728 | 0.753 / 0.918 | 1 → 0 (1) | 1 |
| open_report_header | 0.393 / 0.441 | 0.277 / 0.318 | 0.339 / 0.435 | 0 → 0 (0) | 1 |
| open_report_full_snapshot | 6.285 / 6.53 | 5.263 / 6.077 | 5.654 / 6.329 | 26 → 0 (26) | 27 |
| report_time_logs | 0.622 / 0.697 | 0.346 / 0.379 | 0.558 / 0.756 | 1 → 0 (1) | 1 |
| survey_by_well | 3.573 / 3.782 | 3.283 / 3.402 | 3.537 / 3.979 | 1 → 0 (1) | 1 |
| survey_by_report | 0.435 / 0.517 | 0.319 / 0.365 | 0.393 / 0.451 | 1 → 0 (1) | 1 |
| report_revisions | 0.34 / 0.394 | 0.322 / 0.381 | 0.344 / 0.399 | 1 → 0 (1) | 1 |
| approval_history | 0.352 / 0.403 | 0.306 / 0.354 | 0.332 / 0.373 | 1 → 0 (1) | 1 |
| audit_for_report | 0.579 / 0.643 | 0.374 / 0.423 | 0.549 / 0.637 | 1 → 0 (1) | 1 |
| recent_audit | 1.785 / 1.923 | 1.118 / 1.204 | 1.568 / 1.661 | 1 → 0 (1) | 1 |
| dashboard_reports_today | 0.392 / 0.436 | 0.375 / 0.438 | 0.382 / 0.446 | 1 → 0 (1) | 1 |
| hierarchy | 18.955 / 19.551 | 15.964 / 17.211 | 16.43 / 19.11 | 1 → 1 (1) | 1 |
| cost_totals | 3.079 / 3.204 | 2.695 / 2.778 | 2.733 / 3.166 | 1 → 0 (1) | 1 |
| latest_mud_report | 0.436 / 0.467 | 0.315 / 0.366 | 0.385 / 0.436 | 1 → 0 (1) | 1 |
| delete_report | 11.487 / 48.492 | 9.172 / 9.393 | 10.358 / 14.404 | 52 → 0 (52) | 54 |
| **Total full-scan statements** | **91** | **1** | **91** | | |

| | v5 | v6 | v6, indexes dropped |
|---|---|---|---|
| Data setup (s, 500 reports) | 5.321 | 4.617 | 4.691 |
| Secondary indexes | 0 | 95 | 0 (95 dropped) |
| Database pages in use (bytes) | not recorded | 2,428,928 | 1,597,440 |

## Interpretation (limits stated)

* **Plans are the primary evidence.** Full-scan statements fall from 91 to 1.
  The largest structural changes are opening a full report snapshot (26 child
  table scans become index searches) and deleting a report (52 scans during
  the cascade, one per child table, become index searches).
* **Remaining scans in v6:**
  * `hierarchy`: `SCAN companies`. The tree starts from every company, so
    reading the whole table is the query's purpose; every joined level below
    it uses an index.
  * `dashboard_reports_today` filters on `report_date` alone. It now scans the
    covering `(well_id, report_date)` index instead of the table, which is
    still O(number of reports). A `report_date`-only index was not added
    because nothing in the measurements justified it at this scale.
  * `recent_audit` walks `ix_audit_logs_timestamp` in order and stops at the
    `LIMIT`.
  * `USE TEMP B-TREE` (sorting) steps fell from 9 statements to 4.
* **Timings are small and from one run per configuration.** The database
  (about 2.4 MB) fits entirely in SQLite's page cache and the OS cache, so the
  measurements show CPU cost, not disk I/O. Differences of a few hundredths of
  a millisecond are within run-to-run noise: for example `list_reports_by_well`
  is slightly faster in the dropped-index control than in v6. The v5 p95 for
  `delete_report` (48.492 ms) is a single outlier run. The control run (same
  code with the indexes dropped) is the fair comparison for the index effect.
  No general speed-up percentage is claimed. Larger databases are expected to
  benefit more from index searches over scans, but that was not measured.
* **Cost.** The indexes occupy 831,488 bytes in this dataset
  (2,428,928 − 1,597,440 bytes of pages in use), about a third of the indexed
  database. Setup time with and without indexes (4.617 s versus 4.691 s) shows
  no measurable insert overhead at this scale. Each index adds work to every
  insert and update of its table.
* Sizes use `(page_count − freelist_count) × page_size`; the main file size is
  not meaningful under WAL.

## Reproducing

Run the commands above on an otherwise idle machine. Do not run them alongside
the test suite. The tool removes its temporary directory and restores the
`DRILLMASTER_*` environment variables it changes. It never opens the user's
database.
