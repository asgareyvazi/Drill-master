# Surge / swab — quasi-steady, closed-end string (M419 specification)

Status: **IMPLEMENTED — SCREENING — QUASI-STEADY ONLY — NOT APPROVED — OWNER REVIEW REQUIRED.**
- Method: `m420.surge_swab`, version `M420 quasi-steady surge/swab, closed-end string v1`.
- Module: `core/surge_swab.py`.
- UI: W13 Hydraulics toolbar button **📉 Surge/Swab HB (closed-end)**.
- Cases: saved with an inputs SHA-256 and replayable from Calculation History.

## 1. Model

For each annular section (hole ID, string OD, length):

1. The pipe speed v_p (ft/min) is a magnitude. Running in gives surge; pulling out gives swab of the same magnitude in this quasi-steady model.
2. For a closed-end string, the displaced flow up the annulus is Q = v_p·(π/4)·Di², so V_f = Q/A_ann.
3. Burkhardt (1961) effective velocity: V_eff = V_f + K_c·v_p. The clinging constant K_c (0–1) is **declared** and never defaulted.
   - For a Newtonian laminar slot, the exact moving-wall (Couette–Poiseuille) solution corresponds to K_c = 0.5. Benchmark SS1 checks this independently.
   - Other rheologies and regimes require the user's choice; there is no published universal value.
4. Each section's pressure change is the R-HYD-2 HB slot friction loss (`core/hydraulics_hb_slot.py`) at the equivalent flow V_eff·A_ann. The formulas are not duplicated.
5. Total = Σ sections. If any section is NOT ASSESSED, the total is NOT ASSESSED, because a partial sum is not a total.
6. EMW (only when TVD is declared): MW ± ΔP/((12/231)·TVD). 12/231 psi/ft per ppg is exact (1 lb/gal over 12 in on 231 in³/gal).

## 2. Explicitly not modelled

- Not modelled: fluid inertia, acceleration and deceleration, compressibility, pressure waves (no transient model), gel breaking, tool joints, eccentricity, and temperature.
- The open-ended string (bore/annulus flow split) is **NOT IMPLEMENTED** in v1 and returns NOT ASSESSED.
- No claim of transient surge is made.

## 3. Relationship to the legacy W13 surge dialog

The existing **📉 Surge/Swab** button (`AdvancedHydraulicsEngine.calc_surge_swab`, a Bingham/power-law screening with a fixed 0.45 clinging factor and a 1.5 maximum-velocity factor) is unchanged.
- The two are different, separately versioned methods.
- The new method neither duplicates nor replaces the legacy one.
- Consolidation is an owner decision (backlog item `BL-SS-CONSOLIDATE`).

## 4. Verification (SYNTHETIC)

- Tests: `tests/test_m415_m427_engineering_services.py`, surge group, replay and dialog.
- Benchmarks: `benchmark_m412.py` SS1, SS2 and Z3, plus status check S4.
- Mutation: `mutation_m401_m460.py`, mutants SS-*.
