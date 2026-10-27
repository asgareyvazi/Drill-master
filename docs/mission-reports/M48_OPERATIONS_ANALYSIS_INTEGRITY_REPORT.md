# M48 — Operations Analysis integrity, engineering metrics and evidence-linked workflows

Branch `arena/72010272-drill-master`, base `8e1d1aca589c9d360f9f264ad6cc1329de74c932`
(the M47 report tip). Status values: PASS / FAIL / PARTIAL / BLOCKED / NOT RUN.
All data used in this mission is synthetic (`tests/m48_synthetic.py`, companies
`SYN-M48`, wells `SYN-A`, `SYN-B`, `SYN-C`). No real DDR, real well or real money
value was opened, used or reproduced. No EXE, installer or release bundle was
built by this mission (the Windows CI runner builds its own, see G). The
application stays **UNSIGNED**. Nothing in this report is release approval,
Windows acceptance or field validation.

## A. Summary

| Item | Status | Evidence |
|---|---|---|
| Start-state Git audit | PASS | G.1 |
| Deep audit and traceability matrix | PASS | B.3, D |
| Scope (well, wellbore, section, daily report, date range) without stale KPIs/charts | PASS | E.2, F (UI scenarios `S-*`) |
| Distinct states value / valid zero / partial / missing / ambiguous / invalid / error / running | PASS | C |
| KPI states No data / loading / value+unit / error with retry | PARTIAL | E.1: the retry action is the existing **Refresh Now** button named in the error text; there is no separate Retry button |
| ROP canonical source, no same-date double count, legacy fallback only when unambiguous | PASS | D.1, D22 |
| WOB / RPM / torque / pressure midpoints with units | PASS | D.2 |
| d-exponent unit contract and independent goldens (formula unchanged) | PASS | D.3 |
| NPT positive / valid zero / insufficient coverage, canonical denominator | PASS | D.4 |
| Projection sufficiency, label, rolling-origin backtest, no fake CI | PASS | D.5 |
| Cost canonical path, never mixing currencies, missing ≠ 0 | PASS | D.6 |
| Rule-based risk, missing data never LOW | PASS | D.7 |
| Evidence workflow (trend → point → report_id → source row → typed export) | PASS | E.3 |
| Cache key, revision invalidation, generation guard, errors not cached | PASS | B.2 |
| Qt / Matplotlib: global suppression and forced backend removed | PASS | B.2, mutants `B-*` |
| Three real-UI end-to-end flows | PASS (Qt offscreen, Linux) | F.2 |
| Fresh M48 mutation tool | PASS: 44 mutants, 44 killed, complete | F.4 |
| Screenshots from the real app, pinned | PASS (Qt offscreen, Linux) | E.4 |
| Full suite on the exact code tip | PASS: 3356 passed, 0 failed, 4 skipped | F.3 |
| CI on the exact code tip | PASS | G.2 |
| Lint ceiling | PASS: debt 749 → 727, ceiling lowered to 727 | F.5 |
| Windows desktop acceptance | NOT RUN (out of scope; never claimed) | H |

## B. Architecture

### B.1 Modules

* **`core/analysis_evidence.py` (new, 950 lines).** Pure, Qt-free rules that the
  page and the tests share, so there is one implementation of each KPI rule:
  * states `STATE_VALUE`, `STATE_PARTIAL`, `STATE_MISSING`, `STATE_AMBIGUOUS`,
    `STATE_INVALID`, `STATE_ERROR`, `STATE_RUNNING`, `STATE_NOT_ASSESSED`,
    `STATE_NO_SELECTION`, with `MetricValue` / `metric()`;
  * `classify_number()`, the single number gate;
  * `KPI_DEFINITIONS` and `kpi_tooltip()` (title, unit, definition per KPI);
  * ROP: `valid_rop_values`, `summarize_rop`, `rop_daily_series`,
    `LEGACY_DUPLICATE_REASON`; parameters: `midpoint_series`;
  * NPT: `npt_daily_series`, `npt_coverage_summary`;
  * projection: `least_squares`, `linear_projection`, `rolling_origin_backtest`,
    `describe_projection`;
  * risk: `RISK_RULES`, `risk_scores`, `risk_level`, `risk_assessment`;
  * scope and loaders: `AnalysisScope`, `scoped_reports_query`, `load_rop_rows`,
    `load_npt_inputs`, `load_depth_observations`, `evidence_for_metric`,
    `data_revision`;
  * typed export: `export_csv`, `export_xlsx`, `export_tables_csv`,
    `export_tables_xlsx`, `export_metadata`, `NULL_POLICY`, formula
    neutralisation (`_safe_text`).
* **`core/operations_intelligence.py`.** `canonical_params_clause()` keeps a
  legacy `DrillingParameters` row (no `report_id`) only when its date has no
  report-linked row, which fixes D22. KPIs expose `cost_currency_status` and
  per-currency `cost_groups`; the wellbore rollup respects `wellbore_id`.
* **`tabs/w12_Analysis.py`.** Same page, same tabs (no parallel Analysis app),
  plus an **Evidence** tab. It reads through the core module; it holds no
  duplicate KPI logic.

Not changed: `database.py`, `base_tab.py`, `core/sqlite_connection.py`,
`core/data_quality.py`, `core/actual_vs_plan.py`, `core/operational_time.py`,
`core/cost_semantics.py`, `core/engineering/engines/bit_performance.py`,
`export_jobs.py`, `managers.py`. The M47 session architecture is unchanged:
no session crosses a thread, and the page passes IDs, not ORM objects.

### B.2 Page lifecycle

* **Cache.** `_cache_key(name)` = metric name + scope (well, wellbore) + section +
  report + data revision. `data_revision()` is a fingerprint (row counts, max
  ids, `updated_at` and value sums) of the well's reports, parameters, time logs,
  costs and safety records; a change to any of these invalidates the cache (the
  limit is in H).
  A read error is a `_LoadError`: it is never cached and never shown as "No data".
* **Generation guard.** `_generation` increments on each selection change; a
  result read for an older generation is dropped (`_STALE`) and cannot overwrite
  the newer view.
* **Deselect / switch.** `_show_no_selection()` clears the KPIs, charts, tables,
  evidence rows and the analytics chart (`_reset_analytics_chart()`: title,
  axis labels and named ticks; pyqtgraph keeps these across `clear()`).
* **Qt / Matplotlib.** The module-level `warnings.filterwarnings("ignore")` and the
  forced `matplotlib.use(...)` are removed. The NPT pie uses
  `select_figure_canvas()` (no pyplot); its canvas is created once per page.
  PyQtGraph exporters are imported explicitly.

### B.3 Traceability matrix

| Metric | Function | Source | Scope | Formula / unit | Missing / invalid | UI | Test |
|---|---|---|---|---|---|---|---|
| Current depth | `load_depth_observations` | `DailyReport.depth_2400` | well / bore / section / report | latest valid value, m | missing → No data | KPI card 1; Time vs Depth | UI `full_well_values_units_and_tooltips` |
| Rig days | KPI service | distinct `DailyReport.report_date` | same | count, days | 0 reports → No data | KPI card 2 | UI `well_without_reports_is_no_data_not_zero` |
| Avg ROP | `summarize_rop` over `load_rop_rows` | `DrillingParameters.avg_rop` (canonical rows) | same | mean of valid rows, m/hr | None → excluded; NaN/inf/neg → invalid with reason | KPI card 3, Performance | `test_summarize_rop_golden`, `test_canonical_average_rop_*` |
| Best ROP | `summarize_rop` | same | same | max valid row, m/hr | same | Performance | same |
| Footage-weighted ROP | `BitPerformanceEngine.weighted_rop` | footage, on-bottom hours | same | Σ footage / Σ hours, m/hr | no complete pair → not assessed | KPI card 3 subtitle | UI `full_well_values_units_and_tooltips` |
| WOB / RPM / torque / SPP | `midpoint_series` | `*_min`, `*_max` columns | same | mean of (min + max) / 2; klb, rpm, klb.ft, psi | missing bound → excluded | Performance | `test_midpoint_series_golden` |
| d-exponent | `BitPerformanceEngine.d_exponent` (unchanged) | ROP, RPM, WOB, bit size | row | log10(R/60N) / log10(12W/10⁶D), ft/hr, rpm, lbf, in | zero or missing input → None | Performance | `test_d_exponent_independent_golden` |
| NPT hours / % | `npt_daily_series`, `npt_coverage_summary` | `TimeLog24H` | well / bore / section / report | Σ NPT h; % of recorded time | no logs → missing; > 24.1 h or unclassified → invalid; < 95 % → partial | KPI card 4, NPT tab | `test_npt_daily_states_golden`, `test_npt_coverage_boundaries` |
| Projection | `linear_projection`, `rolling_origin_backtest` | dated valid observations | same | OLS on calendar day | < 5 distinct dates → NOT ASSESSED | Advanced Analytics | `test_projection_*` |
| Cost | `operations_intelligence` KPIs | `CostRecord` | whole well only | Σ per currency; per metre only with valid depth | several currencies → not summed | Advanced Analytics (Cost) | UI `cost_golden_single_currency`, `cost_mixed_currency_is_never_summed`, `cost_is_never_attributed_to_a_wellbore` |
| Risk | `risk_assessment` | NPT %, safety records | whole well | rules in D.7 | missing → NOT ASSESSED, never LOW | Advanced Analytics (Risk) | `test_risk_*`, `test_missing_safety_never_gives_low` |
| Data quality | `DataQualityService` (unchanged) | selected report | report | score % | no report → "—" | header | UI flow 1 (tooltip line breaks) |

## C. Data-behaviour matrix

| Metric | Recorded 0.0 | `None` / NULL | Invalid (NaN, inf, negative, bool) | No rows | Read error |
|---|---|---|---|---|---|
| ROP (avg, best) | a real value, counted | excluded, state `missing` | excluded, state `invalid` with reason | No data | "Read error (...) - use Refresh Now to retry" |
| WOB / RPM / torque / SPP | midpoint 0.0 is real | row excluded | row excluded | No data | read error |
| Depth | real 0.0 m | missing | invalid | No data | read error |
| NPT | 0 h is "valid zero" **only** with complete coverage; otherwise partial | day missing | invalid (unclassified, > 24.1 h, negative) | missing (never 0) | read error |
| Projection | 0.0 is a valid point | excluded and listed | excluded and listed | NOT ASSESSED | "ERROR - no result" title |
| Cost | 0.00 in its currency | "— (currency unknown)" / not summed | not summed | No data | read error |
| Risk | NPT 0 % with full coverage → score 3 | criterion NOT ASSESSED | NOT ASSESSED | NOT ASSESSED (never LOW) | read error |
| Evidence row | `value` 0.0, exported as 0.0 | empty cell + state + reason | empty cell + `invalid` + reason | "no rows" | error state |

SQLite stores NaN as NULL, so a NaN reaching the database is reported as missing.
The NaN/inf rules are tested in memory.

## D. Calculations

1. **ROP.** Canonical rows are report-linked rows plus a legacy row only for a date
   without a linked row (`LEGACY_DUPLICATE_REASON` otherwise). Average = mean of
   per-row valid rates; best = max. Two rows on one date: hours-weighted only for
   a single wellbore with hours > 0, otherwise `ambiguous` (never drilled down).
   Golden values, derived by hand: SYN-A average 7.2 m/hr, best 12; SYN-B average
   15.5 (the old naive query gave 32.2); SYN-C 4.0.
2. **Parameters.** Midpoint (min + max) / 2 per row, then mean. Units WOB klb,
   torque klb.ft, SPP psi. Normalisation is display only.
3. **d-exponent.** The formula in `bit_performance.py` is unchanged. Unit contract:
   W12 converts m/hr × 3.28084 → ft/hr and klb × 1000 → lbf. Independent goldens
   computed with log10 by hand: (60 ft/hr, 100 rpm, 1000 lbf, 12 in) → 0.6667;
   (100, 50, 10 000, 8.5) → 0.7983; 18.288 m/hr converted reproduces 0.6667.
   Screening value only, not validated.
4. **NPT.** Denominator = recorded time-log hours of covered days. Coverage ≥ 95 %
   of 24 h per report date is complete. NPT codes are never remapped; a log with
   no code is shown as "Unclassified (no NPT code)". Negative durations are
   excluded. SYN-A: 3.5 h, 3.2 %, coverage 4/6; SYN-C: 7/168 h, 4.2 %.
5. **Projection.** At least 5 distinct dates; x = calendar day; OLS straight line
   (`test_projection_property_matches_numpy_polyfit` uses numpy as the independent
   reference); rolling-origin backtest against a mean baseline. Labelled
   "a projection, not a guarantee". No confidence interval is shown. No causal
   claim. Insufficient data → NOT ASSESSED with the count, period and exclusions.
6. **Cost.** Whole-well only (never attributed to a bore). Per-currency groups;
   several currencies → totals, variance and chart are **not** produced (no FX).
   Per metre only with valid depth. SYN-C: actual USD 7000 vs estimate 6000;
   NPT cost 291.67; 10.00 per metre.
7. **Risk.** Rules, not probabilities: NPT % > 30 → 9, > 20 → 7, > 10 → 5, else 3;
   days without LTI > 90 → 2, > 30 → 5, else 8; level ≥ 7 HIGH, ≥ 4 MEDIUM, else
   LOW. Overall only when both required criteria are assessed and NPT coverage is
   complete. Missing safety data or partial coverage → NOT ASSESSED.

## E. UI

1. **KPI cards** show value + unit, "No data", "—" with "No well selected", or a
   read error naming Refresh Now as the retry. Tooltips give the definition and
   unit. Trends appear only for valid values.
2. **Scope label** colours: wellbore `#bb8fce`, whole-well aggregate `#f5b041`,
   whole well `#7f8c8d`.
3. **Evidence tab:** metric, scope (well / wellbore, section, report), optional
   date range, trend with unit, date, scope and source; clicking a point rings it
   and selects its row; **Open Source Report** uses the row's `report_id` only and
   is disabled (visibly, since this mission) for ambiguous rows; CSV/XLSX export
   is built from the same typed rows with metadata and the null policy, never
   from table text.
4. **Screenshots** (8, `docs/mission-reports/m48-screenshots/`, pinned by SHA-256
   in `tools/privacy/policy.json`): `m48_kpi_cards_units`,
   `m48_npt_coverage_states`, `m48_evidence_trend_point`,
   `m48_evidence_ambiguous_disabled`, `m48_projection_not_assessed`,
   `m48_cost_mixed_currency`, `m48_risk_rule_based`, `m48_no_selection`.
   Environment: real application window 1600×1300 rendered by
   `tools/screenshots/capture_m48.py` on Linux, Python 3.11.2, PySide6 6.8.1.1,
   Qt `offscreen` platform, pyqtgraph 0.13.7, matplotlib 3.9.3, throw-away
   synthetic database. **Not** a Windows desktop capture.

Visual defects found from the screenshots and fixed: clipped KPI values, header
overlap, invisible scope label, untitled and unlabelled charts, unnamed ticks,
no point highlight, Qt `#RRGGBBAA` colours read as `#AARRGGBB` (pre-existing),
unreadable pie percentages, a disabled drill-down button that looked enabled,
clipped Depth History header titles (unscoped container padding), a clipped
gain-axis title.

## F. Tests

Environment: Linux, Python 3.11.2, SQLite 3.40.1, SQLAlchemy 2.0.36, PySide6
6.8.1.1 (Qt offscreen), pytest 9.1.1, openpyxl 3.1.5. Product code is never
stubbed. These are **not** Windows desktop results.

1. **`tests/test_m48_analysis_evidence.py` (67):** boundaries, independent goldens,
   seeded-random property tests (`hypothesis` is not installed), typed export,
   DB loaders on the multi-well / multi-bore fixture.
2. **`tests/test_m48_analysis_ui.py` (42 tests, 40 scenarios in
   `tests/m48_ui_child.py`)** run the real page in a child process: no well, full,
   no reports, no parameters, zero, None, error, A → B, deselect, refresh error
   after a result, well → bore → well, and the three end-to-end flows:
   performance → report → export → switch well; NPT coverage → forecast → NOT
   ASSESSED → export; cost and risk.
3. **Full suite on the exact code tip `0b298b8` (clean tree),** run as the two
   alphabetical halves of `tests/test_*.py` (122 + 123 files):
   1807 passed + 2 skipped, 1549 passed + 2 skipped → **3356 passed, 0 failed,
   4 skipped**. Count change from the 3247/0/4 baseline: +67 core + 42 UI = +109.
   The 4 skips are unchanged (`test_ddr_acceptance.py:33` ×2 opt-in,
   `test_mineru_real_integration.py:26`, `test_packaging_smoke.py:218`). No test
   was skipped, weakened or removed. `test_m29_release_closure.py` gained a stub
   that records `setTitle`/`setLabel` calls; no assertion was removed.
4. **Mutation (fresh M48 tool, final tree):** `tools/quality/mutation_m48.py`,
   **44 mutants, 44 killed, 0 survivors, 0 equivalent, 0 invalid,
   `complete=True`**, baseline 201 passed, 1090 s. Groups: N (None → 0, real zero
   dropped), V (NaN accepted), S (stale KPI / chart / section), R (wrong or lost
   report link, ring), F (dropped wellbore filter), D, C (zero NPT without
   coverage), P (forecast on too few points), K, M (mixed currencies), E (error →
   empty), W (wrong cache), B (global suppression, forced backend), Q (visual
   contracts), L (legacy double count), X (exports).
   History: an earlier complete run gave 40/41; the survivor
   `S-stale-analytics-title` exposed a real defect (the analytics chart kept its
   title, labels and ticks after a deselect), which was fixed (D23), not declared
   equivalent. Three mutants were added later for defects found from the
   screenshots and the audit. No M46/M47 mutation result is presented as M48.
5. **Gates:** ruff clean on all M48 files; lint debt **727 / ceiling 727** (749 on
   the base; W12 22 → 0; the ceiling was lowered on the measured drop); exception
   scan exit 0; privacy check 0 findings; `git diff --check` clean;
   `workflow_m48.py` 17/17; coverage in CI 57.60 % (M47: 57.32 %), floor 45.50 %.
6. **Windows gate wiring:** `.github/workflows/windows-release-gate.yml` and
   `tests/test_windows_release_gate_contract.py` now list both M48 test files; the
   UI parent decodes the child's output as UTF-8 (`PYTHONIOENCODING`), not the
   locale codec.

### Defects fixed

D1–D20 (M48 audit): fake 0 KPIs, stale state, errors shown as no data, ROP double
counting, cache keyed by well only, short-series projection, missing safety →
LOW, `$` labels on unknown currency, global warning suppression and forced
backend, missing exporters import, auto-update enum, PDF name ignored, HTML not
escaped, export scraped from table text, read error shown as "Updated", wellbore
`0` treated as none. D21: a `metric` attribute shadowing a Qt method (introduced
and fixed in M48). D22 (pre-existing): legacy ROP row double counted. D23: stale
analytics chart after deselect. Pre-existing: data-quality tooltip joined with a
literal backslash-n.

## G. Git and CI

### G.1 State

| Item | Value |
|---|---|
| Repository root | `/home/user/Drill-master` |
| Branch | `arena/72010272-drill-master` (upstream `origin/arena/72010272-drill-master`) |
| Base | `8e1d1aca589c9d360f9f264ad6cc1329de74c932`, 0/0 at start, clean, CI green |
| Code commits | `ecf1ef4` core, `749e0ba` W12, `17d22d8` tools/screenshots/gate, `0b298b8` tooltip fix |
| **Code tip** | `0b298b8c38856fe75adbedd55439df05b2c982b8`, pushed, `git ls-remote` equal |
| Report commit | see the final reply (a report cannot contain its own SHA) |
| Ahead / behind after push | 0 / 0 |
| Untracked / unpushed at the end | none / none |
| Force-push, reset of history, rebase, merge | none; `drill-Master` and `main` untouched |

A mid-session sandbox reset was recovered non-destructively: fetch, temp-index
comparison, compare-and-swap `update-ref` from `4336ea3` to `8e1d1ac`; no
uncommitted work was lost.

### G.2 CI (exact SHAs)

| SHA | Source release gate | Windows release validation |
|---|---|---|
| `17d22d8cf55e3d2f7bd27ed3a0f2b1c98d81c3ca` | 40459610675 success | 40459610632 success |
| **Code tip** `0b298b8c38856fe75adbedd55439df05b2c982b8` | **40461725710 success** (3.11, 3.12, 3.13; coverage 57.60 %, 44900/77946, floor 45.50 %) | **40461725648 success** (job 122047663797; Python 3.12.10; installer UNSIGNED) |

Per-test Windows counts are in the runner's JUnit artifact, which cannot be
downloaded from this sandbox. A CI runner is not Windows acceptance.

## H. Security and limitations

* Exports neutralise spreadsheet formulas (`=`, `+`, `-`, `@`, tab, CR) and HTML
  output is escaped. Only synthetic data was used; PNGs are pinned; the privacy
  gate passed before every commit. No new dependency, no LLM, no network use by
  the product.
* **Limitations:**
  * selector-less container stylesheet rules still exist elsewhere in W12; the
    ones that clipped visible content were scoped;
  * emoji render as boxes in the offscreen screenshots (no emoji font in the
    sandbox);
  * the Evidence table shows about five rows at 1600×1300; the plot area is
    compact;
  * the evidence scope label says "Well #id", not the well name;
  * the retry for a read error is the existing Refresh Now button;
  * the cache fingerprint does not see an edit that leaves every count, id,
    `updated_at` and summed value unchanged (for example, only an NPT code or a
    currency code); Refresh Now bypasses the cache;
  * 14 `PyparsingDeprecationWarning`s from third-party code remain in the
    targeted runs;
  * all UI evidence is Qt offscreen on Linux.
* **Owner-gated, not decided here:** licences (PyMuPDF, OCR weights), signing,
  release tag or approval, Windows / field / production acceptance, money
  column changes.
