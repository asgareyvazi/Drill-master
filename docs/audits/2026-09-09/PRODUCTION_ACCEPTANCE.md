# DrillMaster — Production Acceptance (2026-09-09)

Acceptance table per master handoff §40. Statuses: PASS / BLOCKED / NOT VERIFIED /
OUT OF SCOPE. Evidence column names the exact test or command actually run in
this session.

## Final acceptance table (session close)

| Area | Status | Evidence |
| --- | --- | --- |
| Well Identity | PASS | `tests/test_well_centric_acceptance.py` (7/7) — rig≠identity across 3 wells; variant labels resolve, new labels never silently merge; plus pre-existing `test_p0_well_identity.py`, `test_production_import_guarantees.py` green in full suite |
| Alias/Rename | PARTIAL / BLOCKED as feature | Alias resolution at import: PASS (combo_identity stages, incl. `AZNS-12`→`AZNS 12`); no persistent alias/history table exists — new feature, not silently attempted |
| Wellbore | OUT OF SCOPE (documented) | No persistent Wellbore entity; `MASTER_FORENSIC_AUDIT.md` §4. Requires schema v3 migration — scheduled work, not faked |
| Section | PASS | `test_well_centric_acceptance.py::TestHierarchyConsistency` (section↔report↔well coherence, per-well scoping) |
| DDR | PASS | same + `test_p0_atomic_import.py`, `test_ddr_*` green |
| Workover | BLOCKED (not modeled) | no workover entity/flag in schema; documented |
| Sidetrack | PARTIAL — PASS on identity separation | `test_sidetrack_never_merges` (`AZNS 12 ST #1` stays a distinct well); sidetrack-as-wellbore path awaits Wellbore entity |
| Schematic | PASS (no-fabrication contract + R18 save contract) | `test_r18_r19_save_preservation.py` green. **Fixed 2026-09-10 (zero-semantics phase):** `SchematicAutoBuilder` no longer fabricates TD/GL/KB defaults, default casing programs, shoe depths, wall thickness, metallurgy, cement, formation bases or lithology — unknown stays None/absent, explicit zeros are preserved, and `test_schematic_no_fabrication.py` (16 tests) pins the contract including saved-schematic preservation and real raster rendering of unknown states. |
| BHA | PASS (R19 protections; JSON-per-report pattern documented) | `test_r18_r19_save_preservation.py` green; run continuity evidence asserted in `test_two_ddrs_share_well_section_and_run_identity` |
| Bit | PASS (import mapping; cumulative identity = import logic) | `TestBitRunImport` green under real Qt; continuity in acceptance scenario |
| Inventory | PASS (zero≠missing semantics; no material-master/transaction tables — documented gap) | **Fixed 2026-09-10 (zero-semantics phase):** explicit-zero / missing / nonzero openings are now distinct end-to-end — `BulkMaterials.initial_stock`/`current_stock` no longer coerce NULL→0.0 (client-side defaults removed; DDL unchanged); ledger carry-forward fires only for genuinely missing openings; the save path never overwrites a supplied opening; extractors stop converting missing stock to 0.0; re-import upserts instead of duplicating. `test_inventory_zero_semantics.py` (16 tests) pins all of it. No material-master/transaction tables (still a documented next-phase gap). |
| Cost | PARTIAL | CostRecord Actual/Planned/Variance/AFE model + w16 tests green; Estimate/Forecast columns absent (documented) |
| KPI | BLOCKED (canonicalization pending) | `KPI_MATRIX.md` — duplicate ROP/NPT formula sites in operations_intelligence + w12_Analysis |
| Home | PARTIAL (progress/status UI; executive KPI evolution pending) | `tabs/home_tab.py` unchanged this session |
| Analysis | PARTIAL (own SQL KPIs — duplication documented) | `tabs/w12_Analysis.py:1211+` |
| Planning | PASS (PLAN≠FACT) | planning tests green; `core/actual_vs_plan.py` |
| Import | PASS | full suite green incl. previously-failing golden tests now running under real Qt; atomicity/rollback tests green |
| R18 | PASS | `test_r18_r19_save_preservation.py` green in final run |
| R19 | PASS | same |
| Ruff (defect gate E722/F821) | PASS | `ruff check --select E722,F821 core dialogs tabs main_window.py app.py tests` → 0 findings (was 40 E722 + 1 F821) |
| Ruff (full project config) | DEBT-RATCHETED | 5489 findings (was 5550); ceiling `.github/ruff-debt-ceiling.txt`=5489, CI blocks growth; breakdown: F405 4382, F401 460, E702 327, E701 124, F403 92, E741 22, E712 10, F811 10, E703 1, F402 1, F601 1, E711 1 |
| CI | ADDED — first remote execution NOT VERIFIED | `.github/workflows/ci.yml` (validated locally: YAML parse, step list, matrix 3.10–3.13, ratchet arithmetic 5489≤5489); runs on push |
| Windows GUI | NOT VERIFIED | no Windows environment in sandbox |
| Installer | NOT VERIFIED | no bundle built; `test_packaging_smoke` skips by design |

## Final test report (2026-09-09, final run)

Command: `QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=<qt-stubs> .venv/bin/python -m pytest -ra --tb=short`

```text
Collected: 812
Passed:    808
Failed:      0
Errors:      0
Skipped:     4   (2× ddr_acceptance opt-in env vars, 1× MinerU opt-in, 1× Windows bundle)
XFailed:     0
XPassed:     0
Duration:  ~185 s
```

Baseline at session start (same environment): 792 collected, 779 passed,
**7 failed**, 6 skipped (2 of which were DISPLAY-masks hiding 2 real bugs).
Every delta is accounted for:

* +7 new regression tests (`tests/test_p0_phase1_regressions.py`)
* +7 well-centric acceptance tests (`tests/test_well_centric_acceptance.py`)
* +6 selection-context tests (`tests/test_selection_manager_context.py`)
* 7 baseline failures fixed (6 golden construction + 1 stale test double)
* 2 DISPLAY-masked skips converted to capability probes → now running and passing

Compile gate: `python -m compileall -q core dialogs tabs tests` PASS;
`python -m py_compile app.py run.py main_window.py verify_release.py` PASS.

## Explicit non-claims

No Windows GUI verification, no installer verification, no physical PDF/printer
verification, no local-AI/MinerU verification, no production-database
verification, and no "production ready" claim is made by this session. CI's
first actual execution on GitHub runners is pending and is itself NOT VERIFIED
until observed.
