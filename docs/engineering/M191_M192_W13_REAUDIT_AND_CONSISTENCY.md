# M191 – W13 leaf re-audit; M192 – cross-module consistency

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED

## M191 – the 27 W13 leaves after M171–M200

- **Source of truth:** `core/calculator_contracts.LEAF_CLASSES`, pinned by `tests/test_m125_w13_classification.py`.
- **What M171–M200 changed in W13:**
  - `tabs/w13_Engineering_Calculator.py` gained the M184–M188 **Library…** paths.
  - `core/calculator_contracts.py` gained one additive casing-origin kind, `reference`
    (`git diff 43b1115 6731be5 -- core/calculator_contracts.py`: two lines).
  - No formula, method version or classification changed.

**Class counts at `6731be5`:**

| Class | Count |
|---|---|
| CONTRACT | 9 |
| SCREENING CONTRACT | 10 |
| WORKSHEET | 4 |
| TRAINING AID | 1 |
| REFERENCE-ONLY | 1 |
| NOT_SUPPORTED | 2 |
| **Total** | **27** |

These are the M125 counts, unchanged.

**Leaves touched by M184–M188, and why the class still holds:**

| Leaf | Class | M171–M200 change | Why the class still holds | Evidence |
|---|---|---|---|---|
| Volume › Well Volumes | CONTRACT | **Library…** in the pipe dialog (`_vol_add_pipe` / `_vol_edit_pipe` append or replace the whole dialog result, binding included) | Same formula (ID² / 1029.4 × L); a snapshot is an extra input record | `test_volumes_case_stores_the_snapshot_keeps_the_golden_and_reports_drift_on_reopen` |
| Volume › Quick Calc | CONTRACT | the quick pipe pick opens the same dialog (`_vol_quick_select_pipe`) | values only; no case input changed | covered by the dialog tests |
| Hydraulics | SCREENING CONTRACT | row binding in column 0 (`_hy_add_pipe_dialog`, `_hy_edit_pipe`) | totals and ECD identical with and without the pick | `test_hydraulics_results_are_identical_with_and_without_the_binding` |
| Weight | SCREENING CONTRACT | binding on `wt_pipes` entries | weight-card golden; T&D UNKNOWN without a pinned survey (M127) | `test_weight_case_with_a_library_component_matches_the_weight_card_golden` |
| CSG/CMT › Casing Strength | SCREENING CONTRACT | `load_casing_from_library`, origin `reference` | yield never filled; "Not calculated: yield strength unknown"; TR 5C3 subset unchanged | `test_casing_from_the_library_keeps_yield_unknown_and_records_the_snapshot` |
| Well Control › Kill Sheet | **TRAINING AID** | the pipe dialog has the button (`_wc_add_pipe`) | still no re-runnable contract and still NOT_SUPPORTED for case capture; owner gate P11 | `tests/test_m125_w13_classification.py` |

- **Untouched leaves:** the other 21 leaves have no M171–M200 change. They are re-pinned by the same
  classification test and by the M126 / M127 / M133 golden tests in the full regression.
- **Directional › Anti-Collision:** NOT_SUPPORTED as a W13 case. The UI is labelled **SCREENING – NO ISCWSA
  UNCERTAINTY – NO SEPARATION FACTOR – NOT APPROVED**. Owner gate P19 decides whether any error model may be used.
- **DP Database:** REFERENCE-ONLY. It is the legacy drill-pipe catalogue, and its values are not tubular-library
  snapshots.

## M192 – cross-module consistency

### Water density constant (pcf ↔ ppg)

**Inventory:** `tools/quality/density_constant_inventory_m192.py` (`--write` / `--check`).
- Evidence: `docs/mission-reports/m171-m200-evidence/density_constants_m192.json`.
- Test: `tests/test_m192_density_constants.py`. It fails on any added, removed or changed use.

| Constant | Uses | Files |
|---|---|---|
| 7.48 | 17 | calculator_contracts (2), engines/torque_drag (1), well_control_kill_sheet (3), w13_weight (2), calculator_dialog (2), w13 tab (6), w15 (1) |
| 7.48052 | 14 | calculator_contracts (1), engineering/extended (2), hydraulics_engine (4), mud_engineering (1), w13_weight (1), calculator_dialog (1), w13 tab (1), w15 (3) |
| 7.4805 | 2 | engines/mud_volume (1), hydraulics_engine (1) |

**Size of the difference:**
- The relative difference is 6.95 × 10⁻⁵ (0.007 %).
- 75 pcf converts to 10.0267 ppg with 7.48 and to 10.0260 ppg with 7.48052.
- That is below the 0.01 ppg resolution of a mud balance. Six files nevertheless mix two of the constants
  (calculator_contracts, w13_weight, calculator_dialog, the W13 tab, w15, hydraulics_engine), so two displays of
  one mud weight can differ in the fourth decimal.

**No global change.**
- Changing a constant would move every stored golden. The buoyancy factor golden, for one,
  BF = 1 − (MW / 7.48) / 65.5, is part of the M127 weight card.
- The repository rule is to version methods rather than edit constants.
- Owner decision **P8** (`M196_OWNER_DECISION_PACKAGES.md`) chooses between keeping both, with display rounding
  making them indistinguishable, and a versioned method change.

### Other cross-module checks done in M171–M200

| Check | Result | Evidence |
|---|---|---|
| Missing value never becomes 0 across the new flows (review correction, saved-view export, tubular import, library pick) | holds | `tests/test_m173_scalar_correction.py`, `tests/test_m178_trajectory_views.py`, `tests/test_m181_m183_tubular_import.py`, `tests/test_m184_m189_reference_integration.py` |
| Units: saved-view export ft / m and °/30 m ↔ °/100 ft | 800 m = 2624.671916 ft; 3°/30 m = 3.048°/100 ft | `tests/test_m178_trajectory_views.py` |
| One canonical validator for scalar edits | `core/review_scalar_correction` parses against `core.canonical_schema.FIELD_SPECS` and converts units with `core.unit_manager.UnitManager` | `tests/test_m173_scalar_correction.py` |
| A library value and a hand-typed value give the same result | identical for Volumes, Hydraulics, Weight | §M191 table |
| Currency mixing | refused (M130), unchanged; no M171–M200 change touches cost code | M130 cost tests in the full regression; owner gate P9 |
