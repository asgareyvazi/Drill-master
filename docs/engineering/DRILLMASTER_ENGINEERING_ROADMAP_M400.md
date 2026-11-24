# DrillMaster engineering roadmap after M400

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

Written against the M361–M400 code. It supersedes `DRILLMASTER_ENGINEERING_ROADMAP_M320.md` for ordering; that file
stays as the M320 record. The capability states are in `DRILLMASTER_COMPLETE_ENGINEERING_CAPABILITY_CATALOGUE_M400.md`
and the evidence is in `docs/mission-reports/M361_M400_INTEGRATED_ENGINEERING_COMPLETION_REPORT.md`. No item here
approves an owner decision (P1–P19) or adopts external code or data.

## 1. Reliability (Qt lifecycle, CI)

| # | Item | State after M400 | Exit criterion |
|---|---|---|---|
| R1 | PySide6 pin (D63, D74 window release) | **BLOCKED BY OWNER DECISION.** The M378 decision record recommends 6.8.3 (alternative 6.8.2.1); the LGPL 6.8.4/6.8.5 LTS releases exist as source tags only, with no PyPI wheels. Pin stays 6.8.1.1 | owner approval; then all four packages move together and the full M378 checklist runs (suite, Windows gate, D63 probe `--mode product`, packaging) |
| R2 | D88: the 3.12 coverage leg runs 55–60+ min against a 60 min limit (`3ca8b80` timed out; `c2f6eaf` passed in 55m55s) | open; the timeout was **not** raised. M377 classifies such runs as TIMEOUT, never green | a CI design decision recorded by the owner: split the coverage leg, or shard it; never a silent limit change |
| R3 | D51 (`AxisItem._updateLabel`) | NOT REPRODUCED; the cross-thread hypothesis was refuted | keep the M309 monitor per push window |
| R4 | Local full-suite memory | one pytest process reached the 4 GB sandbox limit (OOM at 76 %); `tools/quality/run_suite_sharded.py` runs the suite as sequential shards | CI keeps the single-process run; the sharded run is a local aid only |
| R5 | M375 journey: a hidden tab applies a well change only when shown | by design (`_pending_well`); the W13 pin is cleared when the tab is opened | none (documented behaviour) |

## 2. Engineering

| # | Item | Notes | Gate |
|---|---|---|---|
| E1 | **R-HYD-2**: Herschel-Bulkley slot-annulus losses with the Erge transition band and Colebrook turbulent friction | BoreTHM (Apache-2.0) is a **method reference only**; clean-room implementation, independent benchmarks (published examples, not the production engine), and a side-by-side with the existing Bingham / power-law branches before any default changes | – |
| E2 | ISCWSA error models and separation factor | the M369 screening stays centreline-only and is never called an SF | P19 |
| E3 | Stiff-string T&D | own implementation; LGPL `torque_drag` not adoptable without approval | P3 |
| E4 | Casing: triaxial envelope with connection ratings, casing buckling, temperature-derated yield | extends M371 (today: pipe-body components, worn-wall ratings) | P12, P18 |
| E5 | Well control TRAINING AID: lubricate-and-bleed, bullheading, gas-law migration | extends M373 (volumetric method); stays TRAINING AID | P11 |
| E6 | Drill-off: founder from a fitted line instead of the stated slope-fraction rule; downhole WOB / torque | extends M372 | – |
| E7 | Survey datum / azimuth-reference conversion | M368 refuses a mismatch today | P10 |
| E8 | Surge and swab | not started | – |
| E9 | Independent benchmarks for fishing and bit performance (carried over from M349) | M396 added MSE, kill-sheet, casing and AC references | – |
| E10 | CCI outside the summary lines (M370) | expose in the M366 case results with its own field and unit | – |

## 3. Product

| # | Item | Notes |
|---|---|---|
| U1 | Render the EOWR NOT_RENDERED tables (bit/BHA reports, time logs, material requests, equipment logs) | carried over from M320 P2 |
| U2 | Open a `.citations.json` passage from the Documents tab | carried over from M320 P3 |
| U3 | Mutation-only items from M261–M290 (M275, M276, M278, M279, M282, M283) | carried over |

## 4. Data, standards and licences (owner-gated)

P8 (density divisor kept), P10, P11, P12, P18, P19: see `M196_OWNER_DECISION_PACKAGES.md`. The M386 pillow raise
(12.3.0 → 13.0.0, MIT-CMU, same licence) is a security fix to a non-Qt dependency and is recorded there.

## 5. Security and release

P13–P17 unchanged. M386 adds `tools/quality/vuln_audit_m386.py`: run it on every lock change; a lookup that fails is
NOT CHECKED, never clean.

## 6. Acceptance

Real DDR acceptance, Windows desktop acceptance and field acceptance: **NOT RUN**.
