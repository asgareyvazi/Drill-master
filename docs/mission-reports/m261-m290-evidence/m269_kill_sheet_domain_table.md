# M269 — R-2 review of `KS-unfilled-casing-id-assessed`

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. The Kill Sheet stays **TRAINING AID** (P11).

## The mutant

`tools/quality/mutation_m231_m260.py`, `core/engineering/well_control_kill_sheet.py`. The mutant deletes the
`and inp.casing_id_in > 0` term from the `annulus_assessable` guard. It survived the M239 run on `db0cba3`
(21/22 killed).

## Domain input table

The base inputs are those of `tests/test_m269_kill_sheet_geometry_table.py` (synthetic). "Current" is the code
at `7fe52ff`; "mutant" is the same code with the term removed. Values were measured on 2026-10-13 with the
same inputs.

| # | Casing ID input | Shoe MD | Other geometry | Current result | Mutant result | Same? |
|---|---|---|---|---|---|---|
| 1 | known 8.835 in | 2000 m (below surface) | valid | annulus = cased + open-hole sum (independent check, rel 1e-6) | same | yes |
| 2 | known 8.835 in | 0 m (at surface) | valid | 470.90 bbl, all open hole; casing ID not used | same | yes |
| 3 | unknown (`None`) | any | valid | refused: `missing required kill-sheet inputs: casing_id_in` | same (refused before the guard) | yes |
| 4 | explicit 0 | 2000 m | valid | annulus not assessed (`None`); string volume given | same: the first pipe's cased zone has ID 0 ≤ OD | yes |
| 5 | explicit 0 | **0 m** | valid | annulus **not assessed** (`None`) | **470.90 bbl open-hole annulus** | **no** |
| 6 | explicit −1 | 0 m | valid | not assessed | 470.90 bbl | no (same class as row 5) |
| 7 | explicit −1 | 2000 m | valid | not assessed | same | yes |
| 8 | known | missing (`None`) | valid | annulus not located: not assessed | same | yes |
| 9 | known | 3300 m (> MD 3200 m) | valid | refused: invalid input | same | yes |
| 10 | 5.0 or 4.9 in (≤ DP OD 5.0) | 2000 m | valid | not assessed (impossible geometry) | same | yes |
| 11 | known | 2000 m | hole 6.5 in (≤ DC OD 6.5) | not assessed | same | yes |
| 12 | known | 2000 m | open hole only below the shoe | assessed | same | yes |

Rows 1–4 and 7–12 are pinned by `tests/test_m269_kill_sheet_geometry_table.py`, with 10 tests passing. Rows 5 and 6 are deliberately **not** pinned.

## Proof that rows 5 and 6 are the only inputs that tell the mutant apart

Assume that every other term of the guard holds; otherwise both versions return `None` the same way.

* **casing ID > 0:** the deleted term is true, so both versions run the same code.
* **casing ID ≤ 0 and shoe MD > 0:** the first pipe starts at depth 0 with length > 0. Its cased length is
  `min(length, shoe) > 0`, and its cased-zone annular ID (≤ 0) is ≤ its OD (> 0, which the pipe validation
  enforces). The mutant therefore sets `annulus_assessable = False` and breaks out before appending any
  `ann_detail` row. The result is `None`, the same as the current code.
* **casing ID `None`:** the builder lists it in `missing_inputs` and `compute_kill_sheet` refuses it before the guard.
* **casing ID ≤ 0 and shoe MD = 0:** every cased length is `max(0, min(bottom, 0) − top) = 0`, so the casing ID
  never enters a zone. The mutant computes the full open-hole annulus, and the current code returns `None`.

So the mutant is **not equivalent**: it differs exactly on {shoe MD = 0, explicit casing ID ≤ 0}.

## Conclusion

This review gives **neither an equivalence proof nor a fix**. The survivor stays **SURVIVED**, with this justification.

* With the shoe at surface there is no cased section. An impossible casing ID (0 or negative) then describes a
  casing that the geometry never uses. Two readings are defensible:
  1. Refuse any annulus when an impossible casing ID was entered. This is the current behaviour, and the conservative one.
  2. Ignore the irrelevant value and report the open-hole annulus. This is the mutant's behaviour.
* Pinning either reading would decide a kill-sheet input policy. Two directives forbid deciding it here: R-2
  forbids an over-restrictive rule imposed only to kill a mutant, and the owner holds the Kill Sheet's status (P11).
* An explicit 0 cannot come from the W13 form. Its sentinel minimum (−1, "Not recorded") reads back as `None`,
  which is row 3, refused. Rows 5 and 6 can only come from a stored or programmatic input.
* **Observation:** a negative casing ID is not in the engine's `negative_values` refusal list (rows 6 and 7).
  The annulus is silently "not assessed" instead of refused. This is recorded, not changed: the behaviour is
  conservative, and the change would be a policy decision for the same P11 review.

The M271 reconciliation counts this mutant as **SURVIVED (justified)**, never KILLED and never EQUIVALENT.
