# M349: engineering benchmarks (M314 / M317 / M318) and D92

**Harness:** `tools/quality/benchmark_m349.py`
- `--write` stores the evidence in `m349_benchmarks.json` / `.txt`.
- `--check` recomputes every case. It fails if a case falls outside its tolerance or if the stored evidence is stale.

**Test:** `tests/test_m349_benchmarks_d92.py` (9 tests) runs `--check` in the normal suite, so a change in any engine that moves a benchmark value fails CI.

All data is SYNTHETIC. The label is unchanged: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**.

## Independence rule

Each reference value is computed inside the harness, from a published closed form or from an independent fine-step integration. No reference comes from the engine under test, and the harness imports no engine constant.

| Group | Reference | Source |
|---|---|---|
| M314 bit hydraulics | ΔPb = 8.311e-5 ρ q² / (Cd² At²), Cd 0.95; vn = 0.3208 q / At; Fj = 0.01823 Cd q √(ρ ΔPb); HHP = ΔP q / 1714; HSI over π d²/4 | Bourgoyne et al., *Applied Drilling Engineering*, eqs. 4.85, 4.86, 4.89 |
| M317 cement volumes | area π/4 (D² − d²) in² ÷ 144; 9702/1728 ft³ per US bbl; 1 m = 1/0.3048 ft | exact geometry and exact unit definitions |
| M318 torque and drag | slant hole: F = w_b L (cos θ ± μ sin θ), T = μ w_b L sin θ · OD/24; build-and-turn well: the Johancsik equations integrated in the harness at 0.05 m steps | closed form; convergence reference |

## Result (`m349_benchmarks.txt`)

**44 cases, 0 outside tolerance.**

| Group | Cases | Largest relative error | Tolerance (reason) |
|---|---|---|---|
| M314: 3 bit/nozzle/flow/mud combinations × (TFA, ΔP, HSI, jet velocity, impact force) | 15 | 1.1e-3 (HSI 2.60 vs 2.597, which is display rounding to 0.01) | TFA 1e-9 (exact). ΔP, HSI and velocity 0.2 % (display rounding; 10858 vs 0.9025/8.311e-5). Impact force 0.5 % (two published forms that agree to 0.3 %) |
| M317: pumped volume in ft³/sk, gal/sk and L/sk; gauge annulus; capacity to the shoe | 5 | 1.4e-5 | 1e-4 (1029.4 and 5.6146 are the exact values to 0.002 %) |
| M318: slant 30° / 60° × FF 0.2 / 0.4 (pickup, slack-off, torque) | 12 | 9.9e-5 | 1e-4 (display rounding) |
| M318: build-and-turn well × FF 0.2 / 0.3, pipe entered as 1 or 10 entries | 12 | 8.5e-4 | 0.2 % (5 m integration segments vs the converged reference) |

**M311 / M329 (architecture comparison)** has no numeric result, so a numeric benchmark does not apply. It is qualified by its behaviour tests and by the M327 mutants (AD-*).

## D92: T&D integration resolution followed the drill-string entries (found by this benchmark)

**Root cause.** `TorqueDragEngine._integrate` treated every drill-string entry as one element. The element's inclination was the mean of the inclinations at its two ends, and ΔI / Δφ spanned the whole entry. The usual input is one long drill-pipe entry above the BHA, so in a curved well the soft-string equations were evaluated over hundreds or thousands of metres in a single step.

On the build-and-turn well with FF 0.3, the old (whole-entry) method gave these errors against the converged reference:

| Pipe entered as | Pickup | Slack-off | Rotating torque |
|---|---|---|---|
| 1 entry (3,048 m) | +3.15 % | **+18.54 %** | **−19.56 %** |
| 10 entries | −1.29 % | +1.10 % | −5.16 % |
| 100 entries | −0.18 % | +0.09 % | −0.53 % |

The same pipe gave a different answer depending on how it was typed in. Every result from `TorqueDragEngine.calculate` had this defect: W13 T&D, the M318 sweep, the torque-and-drag history verification, and the assistant's `calculate_torque_drag` tool. The weight card and the casing landing load do not integrate along the survey and were not affected. The slant-hole and vertical anchors in the earlier tests could not reveal it, because a single element is exact when the inclination is constant.

**Fix.** The engine now integrates segments no longer than `MAX_SEGMENT_M = 5.0` m (each entry is split into equal segments).
- With the pipe entered as 1 or 10 entries, the largest error is 0.085 % (torque) and pickup / slack-off are within 0.07 %. The result no longer depends on the number of entries (test: 1 / 7 / 10 / 100 entries agree within 0.1 %).
- The profiles keep one row per entry, at the entry's top. The side force of an entry is the sum over its segments. Buckling reports one row per entry, taken from its most severe segment, and entries with the same name stay separate.
- Integration is first-order, so the error scales roughly with the segment length: 30 m gives 0.5 % and 10 m gives 0.16 %. 5 m was chosen to keep the error at or below 0.1 %.

**Saved work is never relabelled.**

| Saved item | Behaviour |
|---|---|
| New results | Named `Johancsik soft-string (SPE 11380), segments <= 5 m — SCREENING` |
| Torque-and-drag history runs saved with the old method name | Recalculated with the old whole-entry method (`max_segment_m=None`), so their verification still compares like with like |
| M318 cases | M318 is now `v2`. A `v1` case replays with the v1 integration and matches. The same v1 numbers presented as v2 replay as DIFFERENT, never as a silent match. An unknown version is refused. |

Regression tests are in `tests/test_m349_benchmarks_d92.py`. The mutation catalogue has 8 new mutants for this change (TD-*, TDP-*, TDS-v1-*, TDS-unknown-*).

**Limitations, unchanged and stated in the engine:**
- Soft-string model; no stiffness and no tool joints.
- Simple buoyancy.
- Constant friction factor.
- Inclination and azimuth are interpolated linearly in MD between survey stations. This is the existing convention, and the benchmark reference uses the same convention because it tests the discretisation, not the trajectory model.

## Effect on the labels

These benchmarks give the M314 / M317 / M318 numbers an independent check on synthetic cases. They do not change what each tool is:
- M314 and M318 stay **SCREENING**.
- M317 stays a **WORKSHEET** (its displacement check is an upper bound).

The qualification status is recorded in the M323 register and in the M360 closure report.
