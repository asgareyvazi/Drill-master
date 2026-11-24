# M390 — acceptance matrix, M361–M400

Results use exactly **PASS / FAIL / BLOCKED / NOT RUN**. PASS means the stated evidence exists on the final tree
and its gate ran; it is never field acceptance. Synthetic data throughout. The final SHA, CI runs and the final
mutation run are named in `../M361_M400_INTEGRATED_ENGINEERING_COMPLETION_REPORT.md` §1 (a file cannot name the
commit that contains it).

| Item | Acceptance check | Evidence | Result |
|---|---|---|---|
| M361 baseline + CI reconciliation | `3ca8b80` (docs) and `246e7bf` (product) CI kept separate; `3ca8b80` Source = TIMEOUT (3.12) | `m361_live_baseline.md` §3 | PASS |
| M362 workspace recovery | non-destructive; no reset / clean / force | `m361_live_baseline.md` §2 | PASS |
| M363 residual audit | code, UI path, persistence, provenance, tests, mutation, benchmarks, SHA per M321–M360 item | `m363_m321_m360_residual_audit.md` | PASS |
| M364 addenda | stale claims corrected by addenda, history intact | M364 addenda; M379 row-31 addendum | PASS |
| M365 D87 identity | fingerprint pinning; VERIFIED / SOURCE_REPLACED / TIMESTAMP_ONLY | `test_m365_d87_identity`; ID-* mutants | PASS |
| M366 hydraulics | losses, bit ΔP, TFA, HHP, HSI, jet velocity, impact force, AV; ECD only with complete geometry; budget, pump limits, sensitivities, plan vs actual; P8 kept | `test_m366_hydraulics_workflow`; HW-*; M396 H-group | PASS |
| M367 T&D | benchmarks, PU/SO, torque, buckling D93, side force, WOB, FF sweep, replay, revision pinning; soft string named as such | `test_m367_m369_m396_engineering`, `test_m318_*`, `test_m349_*`; TD-*, TDP-*, TDS-* | PASS |
| M368 survey | plan vs actual, targets, tie-in, revision hashes, replay | `test_m368_survey_plan_deviation`; SPD-* | PASS |
| M368 survey: datum / azimuth conversion | conversion | refused instead (P10) | BLOCKED |
| M369 anti-collision | centreline only, never "ISCWSA SF" | `test_m367_m369_m396_engineering`; AC-* | PASS |
| M369 ISCWSA SF | – | P19 | BLOCKED |
| M370 mud / hole cleaning | CCI with refusal rules | `test_m366_hydraulics_workflow` | PASS |
| M371 casing beyond 5C3 subset | bending, thermal, ballooning, fibre stress, worn-wall ratings; UI → service → engine → case → replay | `test_m371_casing_axial_loads`; CAL-*; M396 N1–N3 | PASS |
| M371 triaxial envelope / connection ratings | – | P12, P18 | BLOCKED |
| M372 MSE / bit / BHA | drill-off founder, step MSE, efficiency; UI → case → replay | `test_m372_mse_drilloff`; MDO-*; M396 N4 | PASS |
| M373 kill sheet (TRAINING AID, P11) | volumetric method + migration as TRAINING AID; operational use not claimed | `test_m373_volumetric_method`; WCV-*; M396 N5 | PASS |
| M374 KPI definitions | structured W12 KPI specs, shown in tooltips | `test_m374_w12_kpi_specs`; KPI-* | PASS |
| M375 MainWindow journey | 35 steps through the real MainWindow | `test_m375_main_window_journey` | PASS |
| M376 Qt lifecycle | dialogs parented and destroyed; background job shut down, never terminated | `test_m376_qt_lifecycle` | PASS |
| M376 closed-window release on the shipped pin | – | PySide pin (P2) | BLOCKED |
| M377 CI states | SUCCESS / SUPERSEDED / TIMEOUT / FAILURE / IN_PROGRESS; worst state wins | `test_m377_ci_run_states`; CRS-* | PASS |
| M377 D88 | 3.12 leg under the 60 min limit with margin | timeout not raised (owner / CI design decision) | BLOCKED |
| M378 PySide decision record | wording fixed; 6.8.1.1 / 6.8.2.1 / 6.8.3 compared; pin unchanged | `m378_pyside_decision_record.md` | PASS |
| M379 OSS re-audit | all 50 repositories; new commits read; one register | `m379_oss_reaudit.md`, `oss_reaudit_m379.json` | PASS |
| M380–M384 method adaptation | REUSE ALGORITHM rows resolved; clean-room only | register "M380–M384 method adaptation outcome"; BoreTHM port = roadmap R-HYD-2 (NOT IMPLEMENTED) | PASS (outcome recorded); R-HYD-2 NOT RUN |
| M385 owner decisions P1–P19 | none marked approved | `M196_OWNER_DECISION_PACKAGES.md` "M400 status"; `OWNER_APPROVALS` empty | PASS |
| M386 security | lock vulnerability audit; findings resolved without touching owner-gated pins | `vuln_audit_m386.py`, `m386_vuln_audit_{before,after}.json`, `test_m386_vuln_audit` | PASS |
| M387 shared well context | dialogs freeze their well; cases attributed; cleared selection → no well | `test_m387_shared_well_context` | PASS |
| M388 units and constants | every replay unit has a tolerance; inventories current; P8 untouched | `test_m388_units_contract`, `constant_inventory --check` | PASS |
| M389 mutation | full catalogue on a committed SHA, classified | `m389_run*.txt` | see report §1 |
| M391 catalogue | 48 domains, strict labels, planned section | `DRILLMASTER_COMPLETE_ENGINEERING_CAPABILITY_CATALOGUE_M400.md` | PASS |
| M392 doc sections | six documents | M241, PRODUCT_CAPABILITY_MATRIX, ENGINE_INVENTORY (generated section), METHODS_AND_LIMITATIONS, register, M196 | PASS |
| M393 planned capabilities | listed as NOT IMPLEMENTED | catalogue §"PLANNED…" | PASS |
| M394 roadmap | – | `DRILLMASTER_ENGINEERING_ROADMAP_M400.md` | PASS |
| M395 E2E | MainWindow journey + per-workflow W13 UI tests | M375, M387, M371/M372/M373 W13 tests | PASS |
| M396 benchmarks | independent of the production engine | `m396_benchmarks.txt` (31 cases) | PASS |
| M397 final CI | 3.11 / 3.12 / 3.13 + Windows on the exact final SHA | report §1 | see report §1 |
| Real DDR, Windows desktop, field acceptance | – | P17 | NOT RUN |
