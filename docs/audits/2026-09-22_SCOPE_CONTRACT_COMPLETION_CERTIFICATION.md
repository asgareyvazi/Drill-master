# Mission 25 — Scope Contract Completion, Import→Selection Chain & Whole-Well Certification

Date: 2026-09-22
Branch: `arena/01a085e0-drill-master`
Base (verified): `0527e95` — *M24: Wellbore Scope Convergence, Analytics Truth & Explicit Aggregate Certification*
Parent of base: `2722020` (M23)
Environment: Python 3.11.2 · SQLAlchemy 2.0.54 · pytest 9.1.1 · PySide6 6.11.2 · Qt offscreen · Linux x86_64

This is a **completion / hardening** mission, not a feature branch. No new
features were added for change-count, no generic frameworks (no scope layer,
nullable-widget framework, report engine, or aggregation engine), no new
dependencies, no schema change for symmetry, no engineering-formula changes,
no blind deletions, no silent cross-bore aggregation or attribution, and no
fabricated engineering data.

---

## 0. Gate A — repository identity (VERIFIED)

At session start the local branch pointer was at the shallow-clone base
`b05ea768` while the authoritative remote tip was `0527e95` (M24, pushed).
Reconciled with `git fetch origin arena/01a085e0-drill-master` +
`git reset --hard 0527e95`. `.github/workflows/` is pre-existing untracked —
DO NOT stage. `.venv` and `/home/user/qt-libs` are snapshot-excluded and were
rebuilt this session.

Full suite re-confirmed green on the finished branch: **1468 passed, 4 skipped**
(281.88s).

---

## 1. The four axes and what was actually wrong

M24 made W12 Analysis bore-aware and certified which surfaces are whole-well
"by design". M25 finishes the scope contract end-to-end:

1. **Explicit Whole-Well scope contracts** — the whole-well surfaces existed
   but did not *say so*. An operator could read a whole-well NPT/Cost aggregate
   believing it was scoped to the selected bore. Fixed by declaring scope in
   both the reports (HTML/PDF + Excel) and the live UI.
2. **Import → Wellbore → Selection → UI chain** — `_targeted_refresh` set
   well/section/report after import but *omitted the bore dimension*, so a
   freshly-imported bore-tagged report opened analytics at Well level. Fixed by
   resolving the effective bore from the persisted ownership chain and passing
   it through `select_full_context`.
3. **Scope-attribution classification + safe legacy handling** — classified the
   `scope_attribution.py` surface honestly by its branch-specific caller graph;
   left the unwired `resolve(apply=True)` path DEFERRED (no auto-backfill).
4. **Adversarial multi-bore certification** — every scope claim is backed by a
   test using an *independent* oracle (e.g. Original NPT 1h + Sidetrack NPT 4h
   ⇒ whole-well 5h computed separately from the code under test).

---

## 2. Per-item evidence

### §3–6 — W12 read-path truth (commit `74e1246`)

| Item | Old behaviour | Defect | Fix (minimal) | Test |
|---|---|---|---|---|
| §3 `get_today_data`/MudReport | same-well+same-date fallback when no report selected | in a multi-bore well this can return **another bore's** record | fallback forbidden when report is selected; unprovable ownership → UNKNOWN, never another record | `test_w12_scope_leakage_m25.py` |
| §4 `load_milestones_data` | `Section.well_id == current_well_id` | whole-well set unlabelled | classified whole-well, labelled | `test_w12_milestones_m25.py` |
| §5 milestones PLAN | `(depth_to-depth_from)/50`, `5` | fabricated plan number | when no stored plan → `—` (UNKNOWN), no synthetic calc | `test_w12_milestones_m25.py` |
| §6 recent reports | `r.rig_day or 0` | None collapsed to 0.0 | None→`—`, 0.0→0.0, positive→value (presentation truth) | `test_w12_recent_reports_display_m25.py` |

### §7–8 — W12 advanced-analysis scope classification (FINAL, no code change)

rop_prediction = BORE; npt_forecasting = BORE; cost / risk = WHOLE-WELL
(labelled); plan_variance = WHOLE-WELL; intelligence = WHOLE-WELL;
data_quality = REPORT. All truthful against their queries — no W12 edit needed.

### §9–15 — Track I whole-well UI labels (commit `2949d5b`)

Well-level surfaces now declare their scope, consistent wording, no framework:

- **W16 Cost** — "Scope: Whole-Well Aggregate — costs sum across all
  wellbores/sidetracks" banner under the header.
- **W10 children** — NPT and activity/code group titles carry
  "Scope: Whole-Well Aggregate (all wellbores/sidetracks)"; the Milestones info
  label carries "Scope: Whole-Well Aggregate — all sections across every
  wellbore/sidetrack".
- **W11 Export** — a whole-well banner on the EOWR, NPT, Cost, Plan and Batch
  tabs; Plan reads "Scope: Whole-Well (Well-Level Plan)". **DDR is
  report-scoped and intentionally carries no banner.**

Test: `test_whole_well_scope_labels_m25.py` (subprocess-isolated) asserts each
surface declares whole-well scope and that W11 shows ≥5 banners with DDR
excluded.

### §12–14, §40–43 — report-engine scope metadata (commit `bba9324`)

`core/report_engine.py`: EOWR / NPT / Cost declare "Scope: Whole-Well
Aggregate" and Plan declares "Whole-Well (Well-Level Plan)" in both the HTML/PDF
cover/section header and the Excel summary sheet (`Summary`, `NPT Summary`,
`Cost Summary`, `Plan Summary` each carry a Scope row). Labels match the query
semantics — these engines query by `well_id` across every bore — so there are no
fake scope fields (§39: reader semantics match the label). DDR
(`DDRReportEngine`, report-scoped) is intentionally NOT labelled.

Independent-oracle tests (`test_report_scope_metadata_m25.py`, 8):
- EOWR/NPT HTML declare "Whole-Well Aggregate"; DDR HTML does NOT.
- NPT multi-bore aggregate: Original 1h + Sidetrack 4h ⇒ **5.0h** (oracle
  computed separately), spanning both bores.
- Cost is well-level (CostRecord has **no** wellbore column — §43): 100k + 40k
  ⇒ **140k**; Excel `Cost Summary` carries the Scope row.
- Plan is well-level and labelled as such.

### §16–19, §45–47 — Track L import→selection chain (commit `dd34ad9`)

`main_window._targeted_refresh()` now reads the **persisted** ownership chain
(never stale pre-import payloads, §47), resolves the effective bore as
`report.wellbore_id else section.wellbore_id else None` (a blank bore stays
`None` = Whole-Well, **never** inferred as Original), and passes explicit
`wellbore_id` / `wellbore_data` into `select_full_context()`. §45/46 read/save
helpers preserve `wellbore_id` in their payloads/returns.

Tests: `test_import_to_selection_m25.py`,
`test_import_to_selection_ui_smoke_m25.py`.

### §46 — save return carries bore (commit `bba9324`)

`core/database.save_daily_report` return payload now includes `wellbore_id` so
callers building post-save context keep the bore dimension. Additive; existing
callers (`dialogs/hierarchy_dialogs.py`, `tabs/w2_Daily_Report.py`) unaffected.

### §22–23 — `get_or_create_wellbore` identity reconciliation (commit `302c253`)

Identity is `(well_id, name)`. Conflict matrix Cases A–E audited: idempotent
match; CONFLICT-REVIEW-SAFE-UPDATE for type/parent/kickoff mismatch;
authoritative identity/lineage is never silently mutated
(`OwnershipIntegrityError`). Test: `test_wellbore_identity_conflict_m25.py`.

### §24–28 — Track K scope_attribution.py (FINAL, no code change)

`coverage()` / `analyze()` (apply=False) = **ACTIVE PRODUCTION** (read-only via
DataQualityService → W11). `resolve()` (apply=True) = **USEFUL-BUT-UNWIRED** —
per §26 it must NOT be auto-wired; left in place, DEFERRED. No auto-backfill /
repair of INVALID. `test_scope_attribution.py` covers §27 exhaustively
(ALREADY / RESOLVED / AMBIGUOUS / UNRESOLVED / INVALID / idempotent / via_section
/ sidetrack-sibling / coverage-real-not-fabricated / kpi-improves) — 15 passed.

### §30–32 — SelectionManager cascade (already correct, re-verified)

`select_well → clears wellbore/section/report`; `select_wellbore → clears
section/report`; `select_section → clears report`. `_ownership_conflict` rejects
a child selection whose explicit `well_id`/`wellbore_id` contradicts the current
selection. `select_full_context` emits in order well → wellbore → section →
report. Tests: `test_selection_manager_context.py`,
`test_schematic_no_fabrication.py` (§32 W3b bore isolation).

---

## 3. Final scope matrix (verified, no guessed cells)

| Surface | Scope | Declared? | Evidence |
|---|---|---|---|
| W12 Analysis KPIs/charts | **Bore-aware** (selected bore) | yes (M24 label) | `test_w12_wellbore_scope.py`, `test_w12_scope_leakage_m25.py` |
| W12 rop_prediction / npt_forecast | Bore | via header | §7 classification |
| W12 cost / risk / plan_variance / intelligence | Whole-Well | yes | §8 classification |
| W12 data_quality | Report | n/a | §8 |
| W10 NPT / activity(code) / milestones | Whole-Well | **yes (M25)** | `test_whole_well_scope_labels_m25.py` |
| W16 Cost | Whole-Well | **yes (M25)** | `test_whole_well_scope_labels_m25.py` |
| W11 EOWR / NPT / Cost / Plan / Batch export | Whole-Well | **yes (M25)** | `test_whole_well_scope_labels_m25.py` |
| W11 DDR export | Report | n/a (intentionally unlabelled) | idem |
| EOWR / NPT / Cost report output | Whole-Well | **yes (M25)** | `test_report_scope_metadata_m25.py` |
| Plan report output | Whole-Well (well-level plan) | **yes (M25)** | idem |
| DDR report output | Report | n/a | idem |
| W6 / BHA / Bit / DDR tabs | Report/Section (correct) | — | M24 matrix |
| W7 Logistics inventory | per-report (three domains separate) | — | M24 (Track J) |
| W3b Schematic | Bore-isolated | — | `test_schematic_no_fabrication.py` |
| CostRecord model | well-level (no bore column, by design §43) | — | schema |

---

## 4. Certification categories & gates

- **Gate A** — repo identity reconciled to `0527e95`; env rebuilt; ✅
- **Import→selection chain** — bore preserved import→UI; ✅ (`dd34ad9`)
- **Whole-well declaration** — reports + UI declare scope; DDR excluded; ✅
- **Scope attribution** — classified honestly; unwired resolve DEFERRED; ✅
- **Adversarial multi-bore** — independent-oracle aggregate tests (1+4=5, 100k+40k=140k); ✅
- **No fabrication** — milestones PLAN → `—` when unstored; recent None→`—`; ✅
- **No forbidden changes** — no new deps, no schema change, no formula change,
  no generic framework, no blind deletion; ✅
- **Full regression** — 1468 passed / 4 skipped; ✅

---

## 5. Commits (on top of `0527e95`)

```
74e1246 M25 W12: close cross-bore fallback + milestones scope/plan-truth + recent-reports None/zero
dd34ad9 M25 Track L: import->wellbore->selection chain preserves bore
302c253 M25 §22-23: get_or_create_wellbore identity reconciliation
bba9324 M25 §12-14,§40-43: report-engine scope metadata + save return bore
2949d5b M25 §9-15 Track I: whole-well scope labels on W10/W16/W11 UI
```

New M25 test files: `test_w12_milestones_m25.py`, `test_w12_recent_reports_display_m25.py`,
`test_w12_scope_leakage_m25.py`, `test_import_to_selection_m25.py`,
`test_import_to_selection_ui_smoke_m25.py`, `test_wellbore_identity_conflict_m25.py`,
`test_report_scope_metadata_m25.py`, `test_whole_well_scope_labels_m25.py`.
