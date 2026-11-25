# M475–M485: Engineering (Phase E)

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.** Input class: SYNTHETIC.

| Mission | Item | Outcome |
|---|---|---|
| M475–M478 | E6b robust drill-off v2 | **IMPLEMENTED** as `m475.drilloff_robust`, a new method ID and version. M372 and M423 v1 are unchanged. |
| M479 | E8b open-ended surge | **NOT IMPLEMENTED — BLOCKED (validation source).** |
| M480–M481 | E1b HB eccentricity, rotation, κ < 0.3 | **NOT IMPLEMENTED — BLOCKED (validation data).** |
| M482 | Erge 2015 coefficients | **NOT VERIFIED** against the primary paper. Now reported as such in results, summaries and case notes. The numbers are unchanged. |
| M483–M485 | E1c, E11, E12 | **Owner packages only** (`docs/engineering/M483_M485_OWNER_PACKAGES_E1C_E11_E12.md`). No behaviour change. E1c fitting stays DISABLED. |

## M475–M478: Robust drill-off v2 (`core/drilloff_robust.py`)

### Method

- **Model:** the same continuous hinge as M423, ROP = a + bW + c·max(W − W*, 0).
- **Fit:** least absolute deviations (L1), solved exactly for each fixed W*. A basic L1 optimum interpolates at least
  three observations (the LP vertex property, Bloomfield & Steiger 1983), so every triple of steps is solved and the
  smallest Σ|r| is kept.
- **W* search:** the same as M423, restricted to [W₍₂₎, W₍ₙ₋₁₎]: a grid of 20 points per interval, then golden-section
  refinement. The better of the two is kept.
- **Outliers:** the robust scale is s = 1.4826 × median |r| over the steps that are not on the fitted vertex. A step
  with |r| > 3s is flagged, never removed.
- **Founder rule:** the same declared slope-ratio rule as M423.

### WOB basis (E6b, partial)

The WOB basis is a required input: `surface` or `downhole`. It is part of the frozen inputs and their SHA-256. The
method never converts one into the other and has no hook-load, drag or buoyancy model; a test checks this. A surface
basis is reported as "surface – not downhole WOB". Surface WOB is never silently substituted for downhole WOB.
Validated downhole drill-off is still **not implemented**.

### Limits (stated in the code and the catalogue)

- 6 to 30 distinct-WOB steps. The upper bound comes from the exact search: about 1.2 s for 30 steps on this machine.
- The L1 optimum may not be unique. Ties are broken by the first triple.
- The method is not robust to errors in WOB (leverage).
- It is not a validated downhole method.

### Integration

| Component | Change |
|---|---|
| `core/method_catalogue.py` | New entry; 67 entries, 0 approved. |
| `core/history_replay.py` | Generic SHA-checked adapter. |
| `dialogs/engineering_service_dialog.py` | `drilloff_robust_dialog`. The basis combo starts at "— not declared —". |
| W13 | `drilloff_robust_btn`. |
| `tests/test_m112_dependency_audit.py` | Catalogue count changed from 66 to 67, for the new entry only. |

### Evidence

**Tests.** `tests/test_m475_drilloff_robust.py` holds 20 tests. They check:

- exact recovery of the constructing hinge;
- a gross outlier below, at or after the knee (including the M423 limitation case, where least squares moves the
  breakpoint from 26 to 16 klbf and L1 keeps 26);
- L1 optimality, through 2000 random perturbations and a vertex check;
- grid dominance and the two-steps-per-side bound;
- the stated robust-scale formula;
- the WOB basis rules;
- refusals;
- that M372 and M423 are unchanged;
- replay and tampering;
- the catalogue entry;
- the real W13 dialog, through run, save and replay MATCH.

**Benchmark.** `tools/quality/benchmark_m478_drilloff_robust.py` runs 9 cases. The expected values come from the data
construction, not from the engine. Result: 9/9 pass (`m478_benchmark_drilloff_robust.json`). The M423 least-squares
breakpoint is reported for comparison only:

| Case | L1 breakpoint (expected) | M423 LS, for information |
|---|---|---|
| O1 +40 below the knee | 26 (26) | 16 |
| O2 +40 above the knee | 30 (30) | 35 |
| O4 two outliers | 30 (30) | 50 |
| O5 stall above the knee | 22 (22) | 20.19 |

**Mutation.** 13 DR-* mutants plus 3 for M482 (HB-erge-note-dropped, HB-erge-note-not-in-case,
SS-erge-note-dropped), all KILLED. The first run left 3 survivors: DR-golden-kept-blindly, DR-range-includes-ends and
DR-vertex-in-scale. Tests were added for each and all three are now killed.

## M479: Open-ended surge (E8b) — blocker recorded

An open-ended string needs the bore/annulus flow split and a validated reference to check it against. No primary
source or validation data set was available to this delivery. The sandbox can reach only GitHub and PyPI, and no
licensed paper or field data is in the repository. Following the rule, nothing was implemented: M420 still returns
NOT ASSESSED for `pipe_end = open`, and transient surge is still not implemented.

## M480–M481: HB extensions (E1b) — blocker recorded

Eccentricity, pipe rotation and an exact annulus for κ < 0.3 all need validated correlations or data. None is
available with rights. M416 still refuses κ < 0.3 and states that it handles no eccentricity or rotation.

## M482: Erge 2015

- **Primary source:** Erge et al. 2015, *SPE Drill. Complet.* 30(3), 257–271. It is paywalled and **not accessed**.
  No verification against it is claimed.
- **Secondary check performed:** BoreTHM (`ldocallaghan/BoreTHM`, Apache-2.0, commit
  `25f9a8ed0c9689bb06f2454a101caeebaf463e51`), `src/borethm/fluids.py::transition_band`. DrillMaster's Re1 and Re2 at
  e = 0 match that transcription term by term. Re1 = 2100 [N^0.331 (1 + 1.402κ − 0.977κ²) − 0.019 e N^−0.868 κ]; the
  eccentric term is zero at e = 0. Re2 = 2900 N^(−0.039 Re1^0.307).
- **Known difference:** BoreTHM clamps N to [0.15, 0.4] in Re2. DrillMaster refuses a flow at or above Re1 outside
  that range, which is more conservative. This is unchanged.
- **Change:** `hydraulics_hb_slot.UNVERIFIED_CRITERIA` and `verification_note()`.
  - Every M416 result for `erge-2015` carries `verification_note`.
  - The summary lines show "NOT VERIFIED: …", including for NOT ASSESSED results.
  - The case note stores the same text.
  - M420 surge summaries and case notes do the same.
- **Replay:** the note is not a replayed result field, so stored M416 and M420 cases still replay MATCH; a test checks
  this. **No numeric behaviour changed.**
- **Not disabled:** the criterion stays selectable for comparison, marked NOT VERIFIED.

## M483–M485: Owner packages

See `docs/engineering/M483_M485_OWNER_PACKAGES_E1C_E11_E12.md`. E1c stays DISABLED, and E11 and E12 are unchanged.
