# DrillMaster engineering roadmap after M320

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

This roadmap is written against the M291–M320 final code and supersedes `DRILLMASTER_ENGINEERING_ROADMAP_M290.md`
for ordering. The evidence is in `docs/mission-reports/M291_M320_INTEGRATED_IMPLEMENTATION_AND_RELIABILITY_REPORT.md`.
No item here approves an owner decision (P1–P19) or adopts external code or data.

## 1. Reliability (Qt lifecycle, CI)

| # | Item | State after M320 | Exit criterion |
|---|---|---|---|
| R1 | D63 freed object | **Identified (M307).** It is the QDoubleValidator `notationChanged` signal-instance cache: a PySide6 6.8.1.x weakref use-after-free, fixed upstream in 6.8.2 (`e226b5827c`). A/B: 6.8.1.1 5/5 SIGSEGV, 6.8.2.1 0/5 | **Owner decision:** raise the lock to PySide6 ≥ 6.8.2 (P2 terms unchanged, LGPL-3.0) |
| R2 | D74: release closed windows | The policy is implemented and gated on the version (M308). On 6.8.2.1, 0/3 windows were retained; on the shipped 6.8.1.1 pin, windows are still retained (3/3) | After R1, the full suite and the Windows gate stay green with release active, and the D63 probe in `--mode product` shows 0/N |
| R3 | Tab-internal lambdas that capture tabs | unchanged | per-tab holder count; no behaviour change |
| R4 | D51 | NOT REPRODUCED. The M309 monitor found 0 watchdog events from 2026-11-18 to 2026-11-22 | keep `tools/quality/d51_ci_monitor.py` running for each push window; re-open on a second `AxisItem._updateLabel` frame |
| R5 | D88: the 3.12 coverage leg runs close to 60 minutes | PARTIALLY RESOLVED; superseded runs are now classified separately by the monitor | a documented CI design decision (split coverage across jobs); never raise the limit silently |
| R6 | Repo-wide AST guards run only in the full suite (the `registry()` regression in `d57f5b2`) | process fix: run the guard tests before each push | optional: a fast pre-push guard job in CI |

## 2. Engineering qualification

| # | Item | Exit criterion |
|---|---|---|
| E1 | Mutation catalogue for the M291–M320 modules (`architecture_diff`, `ddr_hydraulics_check`, `cement_job_reconciliation`, `torque_drag_sensitivity`, `report_sections`, `citation_record`, `qt_lifetime` release policy) | a complete catalogue with every survivor justified; only then is any of them labelled QUALIFIED |
| E2 | History re-run adapters (contracts) for the three M314/M317/M318 calculation kinds | Calculation History shows REPRODUCIBLE and passes MATCH/DIFFERENT tests; until then it says NOT REPRODUCIBLE |
| E3 | Cement reconciliation for yield units other than `ft3/sk` | a declared unit table with tests; never a guessed unit |
| E4 | Independent references for hydraulics, cement, T&D, MSE, bit performance and fishing (carried over) | a second permitted source per method |
| E5 | Kill Sheet R-2 (P11) | owner decision |

## 3. Product implementation

| # | Item | Notes |
|---|---|---|
| P1 | Report section manifest for NPT, Cost and Plan reports | DONE in M333 (manifest v2); kept for history |
| P2 | Render the EOWR NOT_RENDERED tables (bit and BHA reports, time logs, material requests, equipment logs), or keep them listed | the manifest already counts their rows |
| P3 | Citation records: open a cited passage straight from a `.citations.json` file in the Documents tab | verification exists; navigation goes through the library |
| P4 | Architecture diff: show it as a table and export it, not just the status line | core result is complete |
| P5 | M289 journey through the real MainWindow | blocked in practice until R1/R2 |
| P6 | Mutation-only items from M261–M290 (M275, M276, M278, M279, M282, M283) | not re-implemented in M291–M320; still PARTIALLY RESOLVED |

## 4. Data, standards and licences (owner-gated)

P8 (7.48 vs 7.48052; M314 uses the existing hydraulics divisor and does not touch the decision), P10, P11, P12, P18
and P19: see `docs/engineering/M196_OWNER_DECISION_PACKAGES.md`.

## 5. Security and release

P13–P17 are unchanged. The runner images moved to Ubuntu 26.04 during the window; the headless Qt setup passed on
the hosted runners.

## 6. Acceptance

Real DDR acceptance, Windows desktop acceptance and field acceptance: **NOT RUN**.
