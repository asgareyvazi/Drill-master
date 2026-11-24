# M379 — re-audit of the 50 repositories in the adoption register

Read-only (`tools/quality/oss_reaudit_m193.py`, GitHub REST API, 2026-11-23). Nothing was cloned, installed, run or
copied. Machine-readable evidence: `oss_reaudit_m379.json` (same directory). The register
`docs/engineering/OPEN_SOURCE_ADOPTION_REGISTER.md` stays the single source of truth; this file is its M379 evidence,
not a second register.

**Result:** 46 UNCHANGED, 3 NEW COMMITS, 1 ARCHIVED, 0 licence changes, 0 gone. **No classification changed. Nothing
was adopted, and no dependency was added.**

## 1. New commits, read (the M193 "NOT RE-REVIEWED" items)

| # | Repository | Recorded → current head | Commits read | Engineering content | Decision |
|---|---|---|---|---|---|
| 11 | Himageo2006/mud-engineer-pro | `e244ce1e2e` → `e1c25144be` | 1: "iOS 1.1: add Meta SDK for app-install ad measurement" (`codemagic.yaml`, `scripts/add-fbsdk-ios.cjs`) | none (advertising SDK build script) | INSPIRE ONLY unchanged; still no licence (GitHub: 404), so nothing may be used beyond ideas |
| 33 | B0yko/wellbrief | `100cb4a871` → `8dd3b8d8ca` | 2: social-preview image, README header image | none | INSPIRE ONLY unchanged (Apache-2.0) |
| 41 | ldocallaghan/BoreTHM | `1756c0bb8a` → `8fdf5fa79b` (185 commits, 300 files; 2026-10-29 … 2026-11-21) | commit list and file list read: Bingham → Herschel-Bulkley **slot** annulus model with three yield-stress hypotheses (`src/borethm/hydraulic_losses.py`, `fluids.py`), Erge laminar–turbulent transition band, power-law direct solve at zero yield stress, one regime criterion for pressure and heat transfer, Colebrook friction, FORGE 58-32 / 16B trip-pressure comparisons (`studies/pressure_comparison.py`), tapered tool-joint geometry, v1.7.0–v1.9.0 releases | relevant to DrillMaster hydraulics: HB annulus losses are currently **refused** by the W13 engine | INSPIRE ONLY → candidate for a **clean-room** method port (Apache-2.0 permits adaptation with attribution, but no code is taken). Recorded as roadmap item R-HYD-2; **not implemented in M361–M400** |

## 2. All 50 repositories

| # | Repository | Current head (default branch) | Last push | Licence (GitHub) | State | Classification (unchanged) | Target in DrillMaster |
|---|---|---|---|---|---|---|---|
| 1 | ShreshthSrivastav/DrillingAdvisor | `ba971ba729` (main) | 2024-12-05 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 2 | jonnymaserati/welleng | `d29adf906b` (main) | 2026-10-28 | Apache-2.0 | UNCHANGED | REUSE ALGORITHM | optional adapter only (core/engineering/adapters/welleng_adapter.py); ISCWSA stays P19 |
| 3 | BillyFrcs/DrillingEngineeringOperations | `5195e1129d` (main) | 2026-05-08 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 4 | Kukuruza24110/well-engineer | `ebd02d9b26` (main) | 2026-08-09 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 5 | dasvan/engineering-calculations | `684ba9ef9c` (main) | 2025-11-09 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 6 | manjramkar/Drilling-Engineering | `3c0418b3f3` (master) | 2020-09-04 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 7 | Otto-Destiny/3d_well_trajectory_visualization | `a66e754ce5` (main) | 2025-06-27 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 8 | juangjuang74-eng/drilling-engineer-toolkit | `8537e1df1d` (main) | 2026-04-28 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 9 | mengyangcup/drilling_engineering_design | `43342279c6` (main) | 2021-12-03 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 10 | johnryan417/python-for-drilling-engineers | `61e88036e0` (main) | 2025-06-26 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 11 | Himageo2006/mud-engineer-pro | `e1c25144be` (main) | 2026-11-11 | none detected | NEW COMMITS | INSPIRE ONLY | none (ideas only) |
| 12 | f0nzie/volve-drilling | `3698c43d4a` (master) | 2019-02-01 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 13 | jntran08/DataAnalyticsforEngineering | `823e1e53af` (main) | 2020-10-29 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 14 | ejbo2001/3D-directional-drilling-engine | `f96787d7c5` (main) | 2026-05-04 | GPL-3.0 | UNCHANGED | REJECT | — |
| 15 | pro-well-plan/pwptemp | `a6d73e24b4` (master) | 2021-03-02 | LGPL-3.0 | UNCHANGED | OWNER REVIEW REQUIRED | P3 — not adopted (LGPL) |
| 16 | fraclad/wellArchitectureDesign | `0573d473df` (main) | 2025-04-06 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 17 | bpamos/welltrajconvert | `86ee684fdb` (master) | 2020-10-27 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 18 | pro-well-plan/torque_drag | `701cfff599` (master) | 2021-07-28 | LGPL-3.0 | UNCHANGED | OWNER REVIEW REQUIRED | P3 — not adopted (LGPL); DrillMaster T&D is its own Johancsik implementation |
| 19 | almasovAzad/Wellbore_Stability | `834e52c5d9` (main) | 2020-11-06 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 20 | Atashnezhad/Petroleum_Engineering | `f074c07a1d` (master) | 2021-02-25 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 21 | maribickpostanes/Interactive-Well-Trajectory-Plot | `6231dc346f` (main) | 2026-06-06 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 22 | ArokyaMatthew/DrillMind | `bcc9e5d502` (main) | 2026-06-02 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 23 | geoharkat/Directional-Well-Planner | `5bd74dd145` (main) | 2026-05-04 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 24 | FrancisFM/Smart-PAD-Scheduler | `54b1632d9a` (master) | 2020-05-23 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 25 | kcabrera-oil-gas/drilling-optimization | `fc9cc87c7a` (main) | 2026-07-29 | none detected | UNCHANGED | REJECT | — |
| 26 | poetabdullah/DrillSense | `4ac25221c6` (main) | 2025-10-12 | none detected | UNCHANGED | REJECT | — |
| 27 | wjwhitmire/npt-cost | `3ae72097d4` (main) | 2026-10-24 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 28 | wjwhitmire/wellpath | `8e3bb5896f` (main) | 2026-10-24 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 29 | djimrastephane/DDR_UTAH_FORGE | `092fa7c789` (main) | 2026-07-24 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 30 | wjwhitmire/kill-sheet | `5e0c571e76` (main) | 2026-10-24 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 31 | wjwhitmire/cement-calc | `2a6145007f` (main) | 2026-10-24 | MIT | UNCHANGED | REUSE ALGORITHM | method already reflected in cement worksheet (M109); no code copied |
| 32 | gewazy/DrillingManagementStudio | `7286e70fcf` (main) | 2024-06-17 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 33 | B0yko/wellbrief | `8dd3b8d8ca` (main) | 2026-11-06 | Apache-2.0 | NEW COMMITS | INSPIRE ONLY | none (ideas only) |
| 34 | chinuckb/Drilling-Well-Path-Design | `bfcc42ada8` (main) | 2024-10-08 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 35 | awojinrin/ML-Workflow-for-the-Determination-of-Hole-Cleaning-Conditions | `027b7e9071` (main) | 2022-09-15 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 36 | mhnajafi7/pdf-report-table-extractor | `fb1a0b863c` (main) | 2026-08-08 | Apache-2.0 | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 37 | nmamzada/drilling-report-database | `075642a358` (main) | 2026-09-09 | NOASSERTION | UNCHANGED | REJECT | — |
| 38 | aytacbie/drilling-reports-ds-pipeline | `5a43ad6a64` (main) | 2026-10-27 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 39 | djimrastephane/ddr-rag-book | `4c94867c3c` (main) | 2026-09-15 | NOASSERTION | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 40 | geoharkat/welltraj | `3fa8661086` (main) | 2026-05-19 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 41 | ldocallaghan/BoreTHM | `8fdf5fa79b` (main) | 2026-11-22 | Apache-2.0 | NEW COMMITS | INSPIRE ONLY | PLANNED: clean-room Herschel-Bulkley annulus (slot) loss + Colebrook — roadmap R-HYD-2; not adopted in M361–M400 |
| 42 | SiliconWit/drillstring-surface-recoverability | `fb11ec2143` (main) | 2026-09-22 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 43 | imadeddinedjekoune/DrillAR-Sonatrach | `cc71c83997` (master) | 2023-09-30 | none detected | UNCHANGED | REJECT | — |
| 44 | NajafiIB/wellbore-stability-model-selector | `9c2062a568` (main) | 2026-10-26 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 45 | Anatoly5ms/drilling_complication_prognostication | `a0e16ed97f` (main) | 2026-10-19 | MIT | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 46 | Athori99/RigTrack-Drilling-Dashboard-PHR | `7807366e88` (main) | 2026-07-01 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 47 | DrillerDB/drillerdb-mcp | `4707fb6174` (main) | 2026-10-07 | MIT | UNCHANGED | REJECT | — |
| 48 | api-evangelist/national-oilwell-varco | `1ed5ab7f97` (main) | 2026-09-23 | none detected | ARCHIVED | REJECT | — |
| 49 | BJZ-BJZ/marine-deepsea-drilling | `a20b25c147` (main) | 2026-10-08 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |
| 50 | avrangainulloev/DrillingCore | `b874026ec6` (main) | 2025-07-08 | none detected | UNCHANGED | INSPIRE ONLY | none (ideas only) |

Method / files per repository: unchanged from the register's "Details" section (each entry lists language,
file count, dependencies, tests and the reason for its classification); only repositories with new commits were
re-read above. Status: **PASS** (all 50 checked, 0 NOT CHECKED).

## Addendum (M364 rule: the row above is kept, the correction is here)

Row 31 says the cement-calc method is "already reflected in cement worksheet (M109)". That is **wrong in its
attribution**: the cement-calc method reference is the **balanced-plug** method behind `CementEngine.balanced_plug`
(`core/engineering/engines/cement.py`), added in **M52** (commit `77d0ab4`), tested against hand references in
`tests/test_m52_balanced_plug.py`, and recorded in `THIRD_PARTY_NOTICES.md` ("cement-calc (method reference")).
M109 is the cement-worksheet contract with its re-run adapter (`tests/test_m109_cement_worksheet.py`:
annular capacity (D² − d²)/1029.4, no inferred yield or sacks), which does not use the balanced-plug method. The classification (REUSE ALGORITHM, MIT,
no code copied) is unchanged.
