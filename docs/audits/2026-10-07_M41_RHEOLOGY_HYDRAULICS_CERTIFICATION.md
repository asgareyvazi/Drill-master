# M41 — Rheology & Hydraulics Model Certification (bounded repository evidence)

**Audit date:** 2026-10-07. **Scope:** `asgareyvazi/Drill-master`, fixed branch `arena/01a0ec23-drill-master`, M40 baseline `2f49bc0817425711cb994e1d8605a672a5aed7dd`.

This report records independent dimensional and numerical evidence, implementation changes, tests, and limitations. “Certified” here means internally verified against the stated equations and numerical oracles only; it does **not** mean standards compliance, field-loop validation, operational approval, or fitness for well-control decisions.

## 1. Verdict and current gate state

**M41 implementation and report evidence: PASS with explicit scope limitations.** The implementation commit `98b8118cecad198d95859eecdea0f970e7c70f5f` passed Source release gate `37596431831`. The first report-evidence commit `15e90852ff77ad7f1928162e537499bd4147dea2` then passed a fresh exact-SHA Source release gate, run `37597388628`, on Python 3.11, 3.12, and 3.13. The exact-SHA identity of the final handoff tip is reported from the live GitHub record; if this audit file is revised again, a new exact-SHA run is required. The M40 baseline workflow is not used as M41 evidence.

The bounded engineering result is **CERTIFIED WITH EXPLICIT LIMITATIONS** for the tested repository scope only. This is not standards compliance, field-loop validation, operational approval, or fitness for well-control decisions. A failed or missing exact-SHA gate on the final branch tip leaves status **BLOCKED**.

## 2. Branch, baseline, and ancestry reconciliation

- Required baseline: `2f49bc0817425711cb994e1d8605a672a5aed7dd`.
- M40 implementation: `93d824072d2175124018286e71433d82cf3c9621`.
- M40 documentation follow-up: `2f49bc0817425711cb994e1d8605a672a5aed7dd`.
- Baseline exact-source workflow: run `37461409652`, full head SHA `2f49bc0817425711cb994e1d8605a672a5aed7dd`, Python 3.11/3.12/3.13 successful. This is baseline evidence only.
- Local checkout initially pointed at ancestor `7f0186e3e6ac966f1fe9cbd804785129b9246fbe` with broad pre-existing modifications. Those 149 paths were captured (status, diff, untracked archive and file hashes), saved intact as a local recovery stash, and the fixed session branch was fast-forwarded—without reset/rebase/force-push—to the required remote M40 baseline. M41 source edits were then restored selectively. The pre-existing recovery stash is not part of this M41 commit and is intentionally not merged; M36/P6 history/evidence remains outside this change.

## 3. Reproduction and root causes

1. **Fann K dimensional ambiguity:** the numeric expression `510·theta300/511^n` was exposed as “equivalent cP” and consumed directly as field shear-stress consistency. That is dimensionally incomplete for `n != 1`, and skipped the cP-to-Pa-to-field-stress conversion in pressure and transition calculations.
2. **Cross-model transition drift:** pressure-loss branches and regime labels had separately embedded threshold formulae. Standalone Bingham loss methods accepted explicit rheology arguments but selected thresholds using the engine's default `MudProperties`, yielding a different branch than their arguments implied. Power Law loss dispatch also accidentally inherited the engine’s default Bingham model in direct calls.
3. **Unsupported HB presented as calculated:** the prior implementation added a yield term to a Power Law result and returned it as HB SCREENING. That is not a validated yield-corrected HB solver and could appear more complete than supported evidence.
4. **Duplicated geometry/formula ownership:** annular velocity/area, Bingham transition, ECD conversion, TFA, HSI, and compatibility wrappers repeated related calculations. Formula drift was possible across layers.
5. **Oracle defects caught during M41:** the K-scaling test originally changed only theta300, changing `n`; the correct physical K-only scale test keeps `theta600/theta300` fixed. Existing standalone Bingham/Power Law tests also exposed model/rheology dispatch assumptions; method-level overrides now preserve their input contract.

## 4. Fann derivation and unit contract

For standard R1-B1-F1 Model 35 readings, use the documented 300-rpm shear-rate reference of approximately `511 s^-1` and the nominal calibration `0.510 Pa` per dial unit. For the two-point Power Law slope:

```
n = 3.32 log10(theta600/theta300)                         [dimensionless]
K_SI = (0.510 Pa/dial) theta300 / (511 s^-1)^n           [Pa·s^n]
K_cP = 1000 K_SI                                          [cP·s^(n−1)]
K_field = K_SI / 0.4788025898                             [(lbf/100 ft²)·s^n]
```

`0.4788025898 Pa` is derived from `1 lbf / 100 ft²` using exact international-foot and pound-force conversions. `K_cP` is not plain cP unless `n=1`. The legacy output key `power_law_k_equivalent_cp` remains for compatibility, but the unit map and UI now identify its time exponent. The canonical Fann parameter helper owns the numeric expressions; the field conversion is a separate canonical helper. The field conversion is applied before both Power Law loss and critical-velocity calculations.

Bingham plastic readings remain `PV = theta600 - theta300 [cP]` and `YP = theta300 - PV [lbf/100 ft²]`. The two-reading Fann model rejects negative inferred Bingham YP. Optional 3/6-rpm HB yield is only an estimate; no HB `n`, `K`, or pressure-loss answer is returned.

## 5. Equation ownership and cross-layer decisions

- Fann `n/K`: `MudProperties._power_law_parameters_from_fann`; `calculate_fann_rheology` and properties delegate.
- K unit conversion: `MudProperties._power_law_k_field_from_cp`.
- Bingham pipe/annulus transition: `_bingham_critical_velocity_fps`, used by pressure branch selection, regime reporting, and the public annular critical-flow utility.
- Power Law transition: `_critical_velocity_fps`, used by pressure branches and regime labels with an explicit active model and converted K.
- Annular `Dh²−Dp²` factor and field velocity conversion: `_annular_area_factor_in2` and `_calc_annular_velocity`; surge/swab and compatibility adapters delegate.
- Annular cross-sectional area and interval ECD conversion: `_annular_area_ft2` and `_ecd_from_apl_ppg`; the profile integrates interval APL before delegating to the scalar ECD conversion.
- TFA: `BitEngine.calculate_tfa_program`; legacy `calculate_tfa`, `BitNozzle.area`, and `AdvancedHydraulicsEngine.calculate` delegate. Positive integer nozzle counts are required in the program path.
- HSI: `AdvancedHydraulicsEngine.calc_hsi`; `BitEngine.calculate_hsi` delegates.
- W13 rheology and bit/velocity wrappers delegate to the canonical engines. Formula-owner source guards cover the Fann, transition, annular geometry, ECD, TFA and W13 paths.

These are source-ownership decisions, not independent proof that every empirical coefficient represents a universal field standard.

## 6. Independent numerical matrix — constitutive/pressure checks

| Model/path | Independent oracle and case | Evidence/acceptance |
| --- | --- | --- |
| Fann K | SI stress: `0.510 theta300/511^n`, then Pa·s^n → cP·s^(n−1) → field stress units; theta300=25, theta600=45 | `tests/test_hydraulics_m41_model_certification.py::test_fann_power_law_k_unit_contract_matches_fann_si_calibration`; full precision unit assertions |
| Power Law pipe | SI generalized-Newtonian wall shear rate with Rabinowitsch correction; axial force balance `ΔP=4τwL/D`; n=0.70, v=0.004 ft/s, ID=4 in, L=1200 ft | `...::test_power_law_pipe_matches_independent_si_wall_stress_solution`; independent oracle, relative tolerance `2e-10` |
| Power Law scaling | Fixed theta600/theta300 ratio for K-only doubling; independent dimensional powers in L and velocity | `...::test_power_law_pipe_scaling_limits_k_length_and_flow`; L×2 → ΔP×2; v×2 → ΔP×2^n; both Fann readings ×2 → K and loss ×2 |
| Power Law annulus, n→1 | Exact concentric-cylinder Newtonian solution from SI radii and logarithmic conductance; theta300=25, theta600=50; hole=8 in, pipe=4 in, v=0.01 ft/s, L=1000 ft | `...::test_power_law_annulus_newtonian_limit_matches_exact_concentric_si_solution`; field estimate within 2% of exact SI solution |
| Bingham pipe, YP→0 | SI Hagen–Poiseuille balance with μ=PV×10⁻³ Pa·s | `...::test_bingham_pipe_newtonian_limit_is_si_hagen_poiseuille`; M40 unit ground truth and components tests also run |
| Bingham annulus, YP→0 | Exact concentric-cylinder Newtonian SI annulus solution | `...::test_bingham_annulus_zero_yield_matches_exact_si_cylindrical_solution`; field approximation within 1.5% |
| Annular flow conversion | GPM and SI cross-sectional area converted to m/s and ft/s; 24.51 field factor treated as rounded | `tests/test_hydraulics_m40_regressions.py::test_annular_velocity_and_critical_flow_match_independent_unit_conversion`; SI oracle with explicit `1e-5` allowance for rounded field factor |
| Surface empirical factor | Explicitly selected E-factor branch and stated formula; units/method label retained | `...::test_empirical_surface_factor_is_named_and_not_claimed_as_api`; behavior evidence only, not a field correlation validation |

## 7. Limiting, scaling, and transition matrix

| Limit/state | Expected behavior | Test evidence |
| --- | --- | --- |
| Bingham YP=0 | Newtonian pipe/annulus limit | SI regressions in Section 6 |
| Power Law n=1 | Newtonian constitutive viscosity from Fann calibration; calculated transition velocity yields dimensionless SI Reynolds number near the cited turbulent-transition convention | `...::test_newtonian_power_law_transition_has_dimensionally_consistent_si_reynolds_number`; both pipe and annulus within 5% of `Re_T=4270−1370n`. This is a correlation consistency check, not field transition validation. |
| PL pipe threshold | `v<vc` uses laminar branch; `v>=vc` uses empirical turbulent branch; regime label shares the same `vc` | `...::test_power_law_transition_uses_converted_consistency_and_pressure_branch_threshold` |
| Bingham pipe threshold | Inputs passed to direct loss method are also used for the shared threshold; exact threshold selects turbulent branch | `...::test_bingham_transition_label_and_pressure_branch_share_exact_threshold` |
| Zero flow | Zero pressure loss without nonfinite arithmetic | `...::test_zero_flow_does_not_produce_nonfinite_power_law_pressure` |
| Invalid `n`, K, finite values, geometry, velocity | Reject/NOT_ASSESSED; do not synthesize a number | `...::test_power_law_transition_rejects_unphysical_index_and_nonfinite_readings`, Fann validation tests, Bingham finite-input tests |
| HB selected | Explicit unsupported result; pressure, total loss and ECD remain unknown | `...::test_hb_yield_estimate_does_not_claim_hb_n_k_or_calculate_pressure_loss`; M40 regression verifies both pipe and annular HB direct helpers raise `NotImplementedError` |

Power Law critical-velocity coefficients remain simplified field correlations. Their dimensional conversion, n=1 Reynolds limit, branch consistency, and unit sensitivity are tested; the correlations are **not** claimed to be independently field-validated or standards-compliant. Reported regime names are screening classifications.

## 8. ECD interval integration matrix

The profile accumulates explicit annular losses interval-by-interval above each station and divides by selected trajectory TVD; it does not smear whole-well APL linearly over MD. A uniform vertical interval uses the independently derived SI annulus pressure as the APL oracle and `ECD = MW + APL/(0.052·TVD)`.

| Geometry/operating case | Check | Evidence |
| --- | --- | --- |
| Vertical, one uniform 1000-ft interval, Bingham YP=0, explicit 8-in bore / 3.5-in pipe OD, low flow | Exact SI annulus APL → bottom ECD; assert laminar branch and geometry match | `...::test_uniform_vertical_ecd_is_integrated_from_si_pressure_loss` |
| Multi-interval, incomplete/overlap/length mismatch, deviated trajectory | No inferred open-hole ID; ECD remains unknown for unmapped/unsupported interval geometry | M40 regressions and engine geometry validation tests |
| Directional TVD | Use supplied survey TVD; MD is not a substitute | M40 hydraulics and W13 chart tests |

`0.052` is the US oilfield ppg/ft-to-psi/ft conversion convention in the named equations. ECD remains a simplified screening profile and does not include cuttings loading or full transient multiphase effects.

## 9. Surge/swab geometry and state matrix

Trip-induced annular velocity is screening-only: explicit open/closed displacement area, `0.45` clinging-factor term, `1.5` maximum-velocity factor, explicit annular geometry, canonical velocity conversion, and the selected annular loss model. RIH adds the signed pressure-equivalent density; POOH subtracts it. No synthetic hole size or guessed shoe/depth is used.

| Pipe state | Operation | Independent geometry check | Density sign | Test |
| --- | --- | --- | --- | --- |
| Closed | RIH | `A_disp=OD²`; Q reconstructed from SI annular area and maximum ft/min | Positive | `...::test_surge_swab_geometry_and_signed_density_use_explicit_pipe_state[RIH-1.0-False]` |
| Open | RIH | `A_disp=OD²−ID²`; flow area includes explicit pipe ID² | Positive | same parameterized test, `True` |
| Closed | POOH | same closed-pipe geometry | Negative | parameterized POOH/False case |
| Open | POOH | same open-pipe geometry | Negative | parameterized POOH/True case |

The pressure-loss delegate is captured in this test to isolate geometry, velocity conversion, interval length and sign; independent Bingham/Power Law constitutive tests separately cover the delegate's model formulas. Factors and concentric-annulus assumptions are screening assumptions only, not operational guarantees.

## 10. Bit hydraulics / nozzle geometry matrix

- TFA independent oracle sums SI circular nozzle areas and converts to in². Size/count semantics are explicit; fractional counts are invalid.
- `BitNozzle.area`, the `BitEngine` UI/API, and the advanced profile use the same TFA owner.
- M40 tests retain forward/inverse bit pressure consistency, HHP/HSI, jet velocity, and impact-force regressions; HSI now delegates to one area/HHP implementation.
- Missing nozzle geometry is `NOT_ASSESSED`/missing, never a UI default input. Missing bit diameter leaves HSI unassessed.

Evidence: `...::test_tfa_program_matches_independent_si_circle_areas_and_rejects_fractional_counts`, `tests/test_hydraulics_m40_regressions.py::test_bit_hydraulics_ground_truth_and_inverse_tfa_consistency`, nozzle optimization and W13 UI tests.

## 11. UI and current-result behavior matrix

| Surface | Expected contract | Evidence |
| --- | --- | --- |
| W13 Fann display | Shows canonical corrected K key, `cP·s^(n−1)`, and screening scope; invalid readings say Not assessed | `...::test_w13_fann_display_uses_corrected_k_unit_label` |
| W13 model selector | HB explicitly marked unsupported; no computed HB proxy is surfaced | M40 regression plus UI/source checks |
| Hydraulics form | Missing/invalid geometry, nozzles, surface dimensions or model inputs leave no assessed numeric total | focused hydraulics and release smoke tests |
| Stale calculation display/export | Input edits or failed recomputation clear/invalidate stale outputs | W13 UI, release smoke and M40 result tests |
| Calculated nozzle/TFA | Only explicit positive sizes/counts enter the canonical calculation | M40 nozzle validation and M41 TFA tests |

## 12. Well-control and persistence cross-layer matrix

M41 makes no well-control equation change. It reruns the M40-relevant integration set to check that the hydraulics changes do not alter kill-sheet inputs/results, persistence identities, stale-result invalidation or cross-process reconstruction.

| Layer | Evidence exercised |
| --- | --- |
| Kill-sheet geometry/calculations | `tests/test_well_control_kill_sheet.py` |
| Persisted snapshots/history | `tests/test_well_control_kill_sheet_persistence.py` |
| Cross-process serialization | `tests/test_well_control_kill_sheet_cross_process.py` |
| Failed recompute cannot save stale success | `tests/test_well_control_kill_sheet_save_widget_smoke.py` |
| Compatibility/canonical wrappers | `tests/test_extended_engineering.py`, `tests/test_engineering_ground_truth.py`, `tests/test_engineering_integrations.py` |

M36/P6 register arithmetic, six open owner decisions, W5 provenance, and the 332/334 historical source-hash context are preserved as independent release evidence; no M41 operation adjudicates or rewrites them.

## 13. Focused test, static, build and GitHub evidence

Repository evidence recorded before commit (therefore not an exact-SHA release claim):

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_hydraulics_m41_model_certification.py tests/test_hydraulics_m40_regressions.py tests/test_engineering_ground_truth.py tests/test_extended_engineering.py tests/test_engineering_integrations.py tests/test_well_control_kill_sheet.py tests/test_well_control_kill_sheet_persistence.py tests/test_well_control_kill_sheet_cross_process.py tests/test_single_source_guard.py tests/test_release_smoke.py tests/test_nozzle_optimization.py tests/test_release_documentation_truth.py -q -o addopts=''` — **251 passed**. The focused M41 file alone — **24 passed**.
- Targeted mutation checks — **11/11 killed**: Fann 0.510 calibration, 511 s⁻¹ reference, Pa/field stress conversion, annular OD/ID swap, rounded annular velocity factor, Bingham annular threshold coefficient, Power Law critical K unit conversion, open-pipe displacement area, ECD depth clipping, TFA circle-area coefficient, and HB unsupported dispatch. Each source mutant was restored immediately; final `git diff --check` passes.
- `compileall` across core/dialogs/tabs/tests/packaging and application entry points — **PASS**; `pip check` — **PASS**; `git diff --check` — **PASS**.
- Ruff pinned tool 0.16.6: `ruff check --select E722,F821 .` — **PASS**. Full historical debt count **5338**, below unchanged ceiling **5375**; the debt scan exits 1 because it reports existing debt, so this is a ratchet pass, not lint-clean.
- `python -m build --sdist --wheel` — **PASS**. Installing the wheel to an isolated target passed, but running its application smoke check is **BLOCKED in this sandbox** by missing system `libGL.so.1` imported by PySide6.
- Full `pytest -q` — **NOT RUN TO COMPLETION**: collection stopped with 18 import errors, all caused by absent `libGL.so.1`; 2 tests were skipped. Installing system packages was attempted but network access to Debian repositories was unavailable. This is an environment limitation, not a test assertion failure. The complete CI runner remains necessary to resolve it.
- Exact-SHA Source release gate **PASS** for implementation commit `98b8118cecad198d95859eecdea0f970e7c70f5f`: GitHub Actions run [37596431831](https://github.com/asgareyvazi/Drill-master/actions/runs/37596431831), exact `head_sha=98b8118cecad198d95859eecdea0f970e7c70f5f`; Python 3.11, 3.12, and 3.13 all succeeded, including complete tests and isolated wheel verification.
- Exact-SHA Source release gate **PASS** for report-evidence commit `15e90852ff77ad7f1928162e537499bd4147dea2`: GitHub Actions run [37597388628](https://github.com/asgareyvazi/Drill-master/actions/runs/37597388628), exact matching `head_sha`, all three Python jobs successful. Remote tip matched this SHA at verification. The final handoff tip may include this last audit-only update; its identity and exact run are verified live and surfaced in the completion message.
- Baseline run `37461409652` remains baseline-only and is not used as M41 evidence.

The focused model-certification file and the expanded M40 regression file are `tests/test_hydraulics_m41_model_certification.py` and `tests/test_hydraulics_m40_regressions.py` respectively. The final report-commit SHA and its CI run are intentionally resolved from the branch/GitHub after that report update, to avoid treating this earlier candidate's run as proof for a later SHA.

## 14. Explicit limitations and external acceptance boundary

- No API RP/IWCF/ISO conformity claim is made. A formula reference is not a certification.
- PL critical-velocity thresholds and the transition/turbulent branches remain empirical screening correlations, not field-loop validated results.
- Bingham pressure-loss equations are simplified field-unit models; annular concentricity, eccentricity, pipe rotation, restrictions, tool joints and cuttings loading are not comprehensively modeled.
- HB yield is only a low-speed estimate. HB `n`, K, pressure losses and ECD are unsupported and return `NOT_ASSESSED`.
- The empirical surface E-factor has no universal/API provenance claim.
- No independent production mud-lab, field pressure-while-drilling, calibration-loop or operator acceptance is presented.
- Linux/source CI cannot establish Windows GUI, PE/installer, clean-machine upgrade/uninstall, real PDF/MinerU, production database migration, or business/operator acceptance. These remain NOT RUN unless separately recorded.

## 15. Machine checkpoint (finalize only after exact evidence)

```json
{
  "mission": "M41 rheology and hydraulics model certification",
  "verdict": "PASS_WITH_EXPLICIT_LIMITATIONS; FINAL_HANDOFF_SHA_VERIFIED_LIVE",
  "baseline_sha": "2f49bc0817425711cb994e1d8605a672a5aed7dd",
  "branch": "arena/01a0ec23-drill-master",
  "implementation_sha": "98b8118cecad198d95859eecdea0f970e7c70f5f",
  "implementation_remote_sha": "98b8118cecad198d95859eecdea0f970e7c70f5f",
  "implementation_worktree_clean_at_push": true,
  "exact_sha_ci_run_id": 37597388628,
  "exact_sha_ci_head_sha": "15e90852ff77ad7f1928162e537499bd4147dea2",
  "report_evidence_commit_remote_sha": "15e90852ff77ad7f1928162e537499bd4147dea2",
  "report_evidence_worktree_clean_at_push": true,
  "final_handoff_sha": "Resolved from live branch/GitHub record in completion message",
  "final_handoff_ci_run_id": "Resolved from live branch/GitHub record in completion message",
  "python_matrix": ["3.11", "3.12", "3.13"],
  "hb_full_solver": false,
  "windows_installer_accepted": false,
  "real_pdf_mineru_accepted": false,
  "production_database_accepted": false,
  "operator_business_accepted": false
}
```

## References and derivation sources

- Fann Instrument Company, *Model 35 Viscometer Instruction Manual*, Manual No. 208878, Rev. N (2013), sections 5.1, 7.1–7.2 and tables 7-1–7-2. The manual identifies Model 35 speed/readout behavior and R1-B1 calculation convention. <https://hamdon.net/wp-content/uploads/2015/02/Model-35-Viscometer-Instruction-Manual.pdf>
- Boyun Guo and Gefei Liu, *Applied Drilling Circulation Systems: Hydraulics, Calculations, and Models* (2011), Chapter 2, DOI `10.1016/B978-0-12-381957-4.00002-4`; rheology and field-unit pressure-loss context (not a compliance basis).
- Guo and Liu, “Mud Hydraulics Fundamentals,” Power Law Reynolds/transition relations, surfaced through ScienceDirect topic extracts for *Power Law Fluid* and *Flow Behavior Index*: <https://www.sciencedirect.com/topics/engineering/power-law-fluid> and <https://www.sciencedirect.com/topics/engineering/flow-behavior-index>. Transition ranges depend on criterion; the code's closed-form estimates are not a solver.
- SI Hagen–Poiseuille and concentric-annulus oracles in `tests/test_hydraulics_m41_model_certification.py` are independently derived from continuum momentum balance, force balance, and no-slip cylindrical geometry. They are test calculations, not copied field correlations.
