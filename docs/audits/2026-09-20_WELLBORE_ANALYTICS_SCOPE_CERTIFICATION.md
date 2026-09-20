# Mission 24 — Wellbore Scope Convergence, Analytics Truth & Explicit Aggregate Certification

Date: 2026-09-20
Branch: `arena/01a085e0-drill-master`
Base (verified): `2722020` — *M23: harden import, wellbore scope, and analytics truth*
Environment: Python 3.11.2 · SQLAlchemy 2.0.54 · pytest 9.1.1 · PySide6 6.11.2 · Qt offscreen · Linux x86_64

---

## 0. Gate A — repository identity (VERIFIED)

At session start the local branch pointer had drifted to the branch base commit
`b05ea768` (1-commit local history) while the **authoritative remote tip** was
`2722020` (M23). The working tree content already matched remote M23 file-for-file
(verified by content diff of key files: `w12_Analysis.py`, `database.py`,
`wellbore_schematic_engine.py`, `main_window.py`, `scope_attribution.py`,
`w7_logistics_Widget.py` all MATCH). Reconciled with `git reset --mixed 2722020`
(pointer + index only, working tree untouched). Result: HEAD `2722020`, parity to
remote `0/0`, working tree clean except pre-existing untracked `.github/workflows/`.

M23 independently reconfirmed: its 4 test files (44 tests) + affected suites
(scope_attribution, selection_manager_context, wellbore_ownership,
schematic_no_fabrication, operations_intelligence_regressions, fuel_water_truth,
inventory_item_authority, kpi_parity = 111 tests) all pass.

---

## 1. The concrete defect after M23

M23 introduced the **Wellbore** dimension into the read/display path
(`get_full_hierarchy` groups sections under bores, the tree renders bore nodes,
`SelectionManager.select_wellbore` is called on click, W3b schematic is bore-aware).

But the dimension **stops at W3b**. The primary analytical consumer, **W12
Analysis**, is entirely `well_id`-centric: it never reads `current_wellbore_id`,
does not connect to `wellbore_changed`, and every KPI / chart / prediction is
computed at Well level. For a well with an Original bore + a Sidetrack, W12
**silently aggregates both bores** with no way for the user to know.

This is the gap Mission 24 closes.

---

## 2. Scope matrix (source- and ownership-derived, not guessed)

Legend: **WELL** = whole-well; **BORE** = should follow selected wellbore;
**SECTION**/**REPORT** = finer scope; **AGG** = whole-well aggregate by design.

| Consumer | Current scope | Correct scope | Bore-aware now? | Action |
|---|---|---|---|---|
| **W12 Analysis (KPI/charts/predict)** | WELL only | BORE when a bore is selected, else WELL (explicit aggregate) | No | **FIX (Track B–H)** |
| OperationsIntelligenceService | WELL + BORE + SECTION already exist (`analyze_well/analyze_wellbore/analyze_section`, canonical ownership-chain) | — | Yes | **VERIFIED-CORRECT — reuse, do not duplicate** |
| W3b Schematic | BORE-aware (M23) | BORE | Yes | VERIFIED-CORRECT (regression-check only) |
| W6 Trajectory | WELL + REPORT (`current_report_id`) | Report-scoped survey editing is correct | Report | VERIFIED-CORRECT — NO CHANGE |
| W10 Planning | WELL (`current_well_id`) | Planning is a well-level plan | WELL | INTENTIONALLY-WHOLE-WELL — NO CHANGE (§20) |
| W11 Export | WELL/REPORT via report engines | Reports declare own scope | mixed | see report engines |
| W16 Cost | WELL (`CostRecord.well_id`, AFE) | Cost is well-level by contract | WELL | INTENTIONALLY-WHOLE-WELL — NO CHANGE (§19); label only if cheap |
| EOWR report | WELL aggregate | End-of-well is whole-well by design | AGG | INTENTIONALLY-WHOLE-WELL (§21) |
| NPT report | WELL aggregate | Whole-well historical NPT | AGG | INTENTIONALLY-WHOLE-WELL (§21) |
| Plan report | WELL | whole-well plan vs actual | AGG | INTENTIONALLY-WHOLE-WELL |
| DDR report | REPORT (`report_id`) | single report | REPORT | VERIFIED-CORRECT — NO CHANGE |
| BHA / Bit | REPORT JSON snapshots | report-scoped | REPORT | VERIFIED-CORRECT — NO CHANGE (§33, no new entity) |
| Inventory (InventoryItem) | separate domain | — | n/a | VERIFIED-CORRECT (§54/§55) |
| Fuel/Water (W7) | well/report | three-state truth | n/a | **Track J review** |
| get_actual_vs_plan | WELL | well-level plan comparison | WELL | INTENTIONALLY-WHOLE-WELL unless evidence (§36) |

**Rule applied (§6):** a consumer is only made bore-aware when ownership evidence
proves the selected bore should change its output. Cost, Planning, EOWR/NPT
reports are whole-well *by design* and are left aggregating — but the multi-bore
ambiguity is made explicit where cheap, never hidden.

---

## 3. Ownership chain used for bore scoping

Only authoritative FK chains are used (never rig/name/date/first-row):

```
DailyReport.wellbore_id                      (direct)
Child.report_id → DailyReport.wellbore_id    (DrillingParameters, TimeLog24H, MudReport, …)
Child.section_id → Section.wellbore_id        (fallback for section-only children)
```

`DrillingParameters`, `TimeLog24H`, `MudReport`, `DailyReport` all carry
`report_id`; `DailyReport` carries `wellbore_id` and `section_id`. No schema change
is required (§42). This is the exact chain `OperationsIntelligenceService._analyze_scope`
already implements — W12 routes to it rather than re-implementing.

**Unknown bore:** `DailyReport.wellbore_id IS NULL` is *never* attributed to a
specific bore. In a bore-scoped view such records are excluded; in the whole-well
aggregate they are included and the aggregate is labelled explicitly.

---

## 4. Tracks implemented (see commit + tests)

- **Track B/C/D/E** — W12 becomes wellbore-aware: consumes `wellbore_changed`,
  tracks `current_wellbore_id`, routes KPI to `analyze_wellbore`/`analyze_well`,
  scope-tags every cache key, shows a visible scope indicator, resets on well change.
- **Track G/H** — remaining `get_performance_data` / ROP-prediction `or 0`
  fabrications classified and fixed where they contaminate values.
- **Track J** — W7 fuel/water NULL vs explicit-zero stock — **FIXED**. Evidence:
  a persisted NULL stock (genuine unknown, reachable via the import path
  `hierarchy_dialogs.py:1449` and the restore path `database.py:5150`, which
  deliberately preserves nullable Float columns) was collapsed to a fabricated
  `0.0` by W7's `_val(key, default=0.0)` load and by the DB save path's
  `float(get(k,0.0) or 0.0)`. A "0 stock" (empty tank) is a critical fact; an
  "unknown stock" is the absence of one — they must never collapse.
  Fix (three concrete states, no generic framework, no schema change):
  - **UI**: physical STOCK spinboxes (`fuel_stock`, `water_stock`, `dw_stock`,
    `fuel_camp_stock`) use the standard Qt special-value idiom — minimum sentinel
    (`-1.0`) rendered as `—` = UNKNOWN; any value ≥ 0 is a real number. Helpers
    `_make_stock_spinbox` / `_stock_value` / `_set_stock_value`. Movement fields
    (consumed/received) keep `0.0` = "no movement". Load preserves NULL as `—`;
    save emits `None` for the unknown mark; remaining/runway/low-stock are only
    computed for a KNOWN stock.
  - **DB `save_fuel_water_inventory`**: reads openings with a three-state
    `_stock_in` (missing key or NULL/blank → None, explicit number incl. 0.0 →
    fact); carry-forward fills ONLY a missing (None) opening, never an explicit
    0.0; unknown opening → unknown remaining; the insert branch emits an explicit
    SQL `null()` for `fuel_stock`/`water_stock` so the column `default=0.0` cannot
    re-fabricate a zero.
  - **Tests**: `tests/test_w7_null_zero_semantics.py` (9, Qt-free, real DB —
    Cases A–E + carry-forward-fills-missing-only + explicit-zero-not-overwritten)
    and `tests/test_w7_null_zero_ui_smoke.py` (1, subprocess Qt — widget loads
    NULL as `—` and re-saves NULL; loads explicit 0.0 as 0.0; states stay
    distinct). No regression in `test_fuel_water_truth.py`,
    `test_w7_carry_forward_preview_smoke.py`, `test_inventory_zero_semantics.py`.
- **Track K** — `scope_attribution.py` usage classification.
- **Tracks F (reports), I, M** — explicit whole-well contracts documented; no
  forced bore-scoping.

Exact per-file rationale and the test matrix are recorded in the Mission 24 final
report section below and in the commit message.
