# DrillMaster engineering roadmap after M290

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

This roadmap is written against the M261–M290 final code; see the M261–M290 report for evidence. It has six categories, and within each category items are ordered by priority. No item approves an owner decision (P1–P19) or adopts external code or data.

## 1. Reliability (Qt lifecycle, CI)

| # | Item | Why | Exit criterion |
|---|---|---|---|
| R1 | Identify the D63 freed object | M264 has a deterministic reproducer (`tools/quality/d63_window_release_probe.py`, 3/3) but only scanned native frames | a symbolized frame naming the freed object. This needs a debug build of PySide6/shiboken, or gdb/ASan on a developer machine; the sandbox has neither |
| R2 | D74 cause 1: release closed windows safely | only possible after R1. Freeing windows today reproduces D63 | windows freed by reference counting, the D63 probe 0/N in `auto` mode, and the full suite green |
| R3 | Convert the ~25 tab-internal lambdas that capture tabs (W2, Home, W1) to bound methods, one tab at a time | removes cycles without changing behaviour | per-tab holder count from the M263 probe; no behaviour change |
| R4 | D51 | 1 event in 300 runs; 0 in 99 jobs since | keep the watchdog at 900 s and keep collecting the watchdog frame. Re-open if a second event shows the same `AxisItem._updateLabel` frame |
| R5 | Raw CI log access for diagnosis | the job-log host is outside the sandbox allowlist | an owner/infrastructure decision, or none |

## 2. Engineering qualification

| # | Item | Exit criterion |
|---|---|---|
| E1 | Independent references for hydraulics, cement, T&D, MSE, bit performance and fishing | a second, permitted source per method; contract status raised only with that evidence |
| E2 | Kill Sheet input policy for impossible casing IDs (R-2: explicit ≤ 0 with the shoe at surface; negative IDs) | P11 decision; then pin it with a test; the survivor becomes KILLED or is declared out of scope |
| E3 | Review other legacy screening formulas the way D81 was found (dimensional check against first principles) | each W13 legacy formula carries a dimensional test |
| E4 | Mutation coverage for the fishing UI and the installer gate; structured specs for the w12 Analysis KPIs | catalogue entries |

## 3. Product implementation (Part II carry-over)

| # | Item | Notes |
|---|---|---|
| P1 | M289 journey through the real MainWindow (the M261–M290 journey crosses the engines, persistence, workbench and KPI card without a window) | blocked in practice by D63/D74: each closed window keeps about 200 MB |
| P2 | M272/M273 authoring states (unknown, zero, N/A, not reported, calculated) as one shared widget contract | exists per tab; not unified |
| P3 | M286 workbench: clone, compare and archive across calculation kinds | MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE exist |
| P4 | M287 end-of-well report sections per engineering module with provenance | package exists; sections are per area |
| P5 | Dashboard KPI spec drill-down (open the spec as a document) | the tooltip shows it today |

## 4. Data, standards and licences (owner-gated)

P8 (7.48), P10 (datum/CRS), P11 (Kill Sheet), P12 (methods), P18 (tubular data) and P19 (ISCWSA) – see `docs/engineering/M196_OWNER_DECISION_PACKAGES.md`. No item here can start without the owner.

## 5. Security and release

P13 (encryption at rest), P14 (ACL), P15 (idle lock), P16 (signing) and P17 (Windows/field acceptance). Runner images: `ubuntu-latest` moves to 26.04 between 2026-10-19 and 2026-11-19, so re-check the headless Qt setup when it does.

## 6. Acceptance

| # | Item | Gate |
|---|---|---|
| A1 | Real DDR acceptance (`tests/test_ddr_acceptance.py`, opt-in) | owner-supplied data; NOT RUN |
| A2 | Windows desktop acceptance | P17 |
| A3 | Field acceptance | P17 |
