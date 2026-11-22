# M328 — Calculation History replay for M314 / M317 / M318 saved cases

**Status: IMPLEMENTED — PARTIALLY QUALIFIED.** Code: `core/history_replay.py` (`REPLAY_VERSION = "M328 v1"`), wired into `core/calculation_history.py` (`_replay_adapter()`) and `tabs/calculation_history_tab.py` (`recalculate()` writes the outcome to the detail pane). Commit `bc8e15b`. Tests: `tests/test_m323_m328_residuals_and_replay.py` (21 tests, 7 of them M328-specific). Mutation coverage: the `HR-*` mutants in `tools/quality/mutation_m321_m360.py` (results in `m327_mutation_catalogue.md`).

## 1. What a replay does

A replay runs the **current** method on the **immutable input snapshot** stored with the case, then compares every stored result field with the fresh one. It never re-reads the mutable source (daily report, cement report, W13 widgets). The snapshot is the record of what was computed, so an edited report cannot silently change a saved case. `test_m328_cement_replay_uses_the_frozen_job_not_the_edited_report` covers this.

| Method | Snapshot replayed | Pinned dependencies checked |
|---|---|---|
| `m314.ddr_bit_hydraulics_check` (SCREENING) | the gathered DDR fields (`hc.evaluate(gather())` split, M323 A-5) | none |
| `m317.cement_job_reconciliation` (WORKSHEET "M317 v2") | the frozen job values, yield unit, open hole / caliper | architecture revision through `_architecture_users` (SHA-256 verified) |
| `m318.td_friction_sensitivity` (SCREENING) | `run_snapshot` (survey + string + factors, M323 A-6) | the snapshot's own SHA-256 |

## 2. Outcome vocabulary

| Status | Meaning | Test |
|---|---|---|
| `MATCH` | every stored field equals the fresh field within its tolerance | `test_m328_history_tab_replays_and_stores_a_linked_rerun` |
| `DIFFERENT` | at least one field differs; each is listed with stored, current, unit and tolerance | `test_m328_a_changed_stored_field_is_different_with_unit_and_tolerance` |
| `NOT_REPRODUCIBLE` | no snapshot (saved before M328), a method version this build does not carry, or an unreadable pinned revision | `test_m328_pre_snapshot_and_unknown_version_cases_are_not_reproducible` |
| `UNREADABLE` | the snapshot or result is malformed, or fails its SHA-256 check | `test_m328_a_tampered_architecture_pin_is_unreadable`, `test_m328_td_replay_checks_the_frozen_survey_and_string` |

`verify()` never raises for a bad record. `KeyError` (a field missing from the snapshot) is caught before `LookupError` and reported as UNREADABLE.

## 3. Tolerances (absolute, repeatability only)

| Unit | Tolerance | Unit | Tolerance |
|---|---|---|---|
| gpm | 1e-6 | bbl | 0.001 |
| psi | 0.01 | % | 0.01 |
| hp | 0.01 | m | 0.001 |
| hp/in² | 0.001 | klbf | 0.001 |
| ft/s | 0.01 | ft·lbf | 0.1 |
| lbf | 0.1 | unitless | 1e-9 |

Text and status fields compare exactly. A field present on only one side is always a difference. The M314 ±5 % HSI band is an engineering display band and is **not** used for replay. Units come from the field-name conventions of each method (`_unit_of`), never guessed.

## 4. Writing

`verify()` writes nothing. `save_rerun()` stores a **new** case linked by `rerun_of` to the original, with `verification_status` set to the outcome. The original case is never modified (immutability is preserved).

## 5. Limits (why PARTIALLY QUALIFIED)

- Covers only the three methods above. Other history entries keep their existing per-calculator recalculation path.
- Replay proves *repeatability of the current code on the stored inputs*. It does not validate the method against field data. M314 and M318 stay SCREENING and M317 stays WORKSHEET.
- Cases saved before M328 have no snapshot and are permanently NOT_REPRODUCIBLE, which is stated rather than guessed.
- Mutation coverage: see M327. Full CI on the closure SHA is still required (M360).
