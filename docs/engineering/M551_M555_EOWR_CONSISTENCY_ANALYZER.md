# M551–M555 (U5) — EOWR data-consistency analyzer

Code `core/eowr_consistency.py` (`M551 EOWR consistency analyzer v1`); wired into `core/report_engine.py` (EOWR HTML
section "Data consistency review", Excel sheet "Data Consistency") and `core/report_provenance.py` (manifest rows
`consistency.<rule>` in every format). SCREENING review aid; not a signed or approved report.

## Principles

* Non-destructive: reads the rows `EOWRReportEngine._collect_data` already loaded; never writes, repairs, converts,
  infers or fills a value; the rest of the EOWR is unchanged.
* Every contradiction lists its lineage: table, record id, field, stored value.
* Statuses: CONSISTENT, INCONSISTENT (a review item, not a verdict on which value is wrong), NOT_ASSESSED (query
  failed / nothing collected), INSUFFICIENT_DATA (values missing; nothing assumed), NOT_APPLICABLE (scope).

## Rules

| Key | Check | Not assessed / insufficient / not applicable |
|---|---|---|
| depth_continuity | depth 00:00 = previous report's depth 24:00 (per wellbore, 0.01 m) | < 2 consecutive reports with both depths |
| depth_within_day | depth 24:00 ≥ depth 00:00 (decrease = review: plug-back / sidetrack, not assumed) | no report with both depths |
| time_log_day_total | Σ 24 h durations of a report ≤ 24 h | query failed / incomplete durations |
| time_log_interval | duration = from→to interval (24:00 wrap) within 1 min | query failed / fields missing |
| npt_summary | EOWR summary NPT = NPT recomputed from the rows (known only if every row is classified and every NPT row has a duration — the `core.operational_time` definition) | query failed / unknown NPT |
| report_identity | no two reports of a wellbore share date and number | no dated, numbered report |
| bit_run_depths | depth out ≥ depth in; metres drilled = out − in (0.01 m) | query failed / depths missing |
| survey_within_depth | deepest survey MD ≤ deepest daily depth (m, as stored) | period report → NOT_APPLICABLE (surveys are not period-filtered) |

## Evidence

`tests/test_m551_eowr_consistency.py` (each rule, every status, non-destructive input, wellbore separation, HTML
escaping, engine HTML/Excel/manifest, stored rows unchanged), `tests/test_m555_eowr_consistency_mainwindow_journey.py`
(real MainWindow W11 export, well isolation), mutants EC-*/RE-*/RP-* (12/12 killed).

## Limitations

Synthetic data only; the rules are internal-consistency checks of stored values, not an engineering validation of
the report. No real EOWR or 08-DDR data was used.
