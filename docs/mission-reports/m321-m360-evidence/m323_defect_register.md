# M323 — Defect register (residuals of M291–M320)

Branch `arena/72010272-drill-master`. Fix commit for every row below: **`bc8e15b`** (parent `6754e14`).
Source of findings: `m322_independent_audit.md`. All evidence uses SYNTHETIC data only.
Product label unchanged: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**.

| ID | Root cause | Severity | Fix commit | Regression test | Evidence | Limitation |
|---|---|---|---|---|---|---|
| **D89** (A-2) | `mud_records.preserve_widget_values` only protects values that were *loaded*. A new Cement/Casing form had no loaded record, so the spinbox placeholders (density 120, yield 1.18, mix water 5.2, CS 2500, thickening 04:30, TOC/BOC 0, casing zeros) were saved as recorded data. M317 then computed volume from a default yield and treated TOC 0 as cement to surface. | **high** | `bc8e15b` | `tests/test_cement_report_null_roundtrip.py::test_m323_d89_new_cement_and_casing_reports_never_store_placeholders` (it fails on `6754e14` and passes on `bc8e15b`; verified by swapping the file) | `tabs/w3c_section_data.py` `_start_new_cement_record` / `_start_new_casing_record`; the banner shows "⚠ NEW RECORD – NOT RECORDED YET" | Rows already saved by earlier builds keep their values. Placeholders that were saved cannot be told apart from values that were really entered, so historical rows are **not** reinterpreted. |
| A-1 | `architecture_diff._pinned_cases` scanned only `calculation_cases`, so casing-design runs (`casing_calculations`) pinned to the older revision were missing. | medium | `bc8e15b` | `tests/test_m323_m328_residuals_and_replay.py::test_a1_architecture_diff_lists_casing_runs_and_reconciliations_pinned_to_the_older_revision` | Uses the canonical `calculation_history._architecture_users` (one lookup for History and the diff) | Lists pinned work only. Nothing is recalculated. |
| A-3 | The M317 displacement check is one-sided: recorded displacement ≤ string capacity to the shoe. Yet it was labelled "CONSISTENT", which implies the displacement was right. | medium | `bc8e15b` | `test_a3_a_displacement_below_capacity_is_an_upper_bound_statement_not_consistency`; `tests/test_m317_*` (state renamed) | State is `WITHIN_UPPER_BOUND`; the reason says "under-displacement cannot be judged" | Under-displacement cannot be detected without the shoe-track length, which is not recorded. |
| A-4 | `_num` turned a recorded 0 into "must be recorded". | low | `bc8e15b` | `test_a4_a_recorded_zero_is_reported_as_recorded_not_as_missing[cement_volume / slurry_yield]` | Note: "sacks recorded as 0 (no slurry volume can be derived from a zero)" | — |
| A-4b | `summary_lines` used truthiness (`if result["toc_difference_m"]`), which hid a 0 m difference. | low | `bc8e15b` | `test_summary_shows_a_zero_toc_difference_instead_of_hiding_it` | Summary prints "recorded TOC equals the architecture record" | — |
| A-5 | M314, M317 and M318 cases had no History replay; History said "no re-run adapter". | medium | `bc8e15b` | `test_m328_*` (6 tests); `tests/test_m314_*`, `test_m317_*`, `test_m318_*` now assert REPRODUCIBLE → MATCH | `core/history_replay.py`; History tab detail lists the differing fields with unit and tolerance | Cases saved before `bc8e15b` have no snapshot and stay **NOT REPRODUCIBLE** (stated in the UI). M317 v1 cases are not replayed because of the method-version change. |
| A-6 | M318 `save_case` stored no survey stations, string or SHA, and a missing pin was stored silently. | medium | `bc8e15b` | `test_m328_td_replay_checks_the_frozen_survey_and_string` | The snapshot holds the stations, components, `components_sha256` and the survey pin. Replay re-checks the station SHA-256 and the components SHA-256. `sweep` refuses an unpinned run. | The survey revision row itself is not re-read during replay; the frozen stations are the record. |
| A-7 | NPT, Cost and Plan reports have no M320 D manifest. | — | open → M333 | — | — | **NOT IMPLEMENTED** until M333 |
| A-8 | No navigation from a citation record to its passage. | — | open → M334 | — | — | **NOT IMPLEMENTED** until M334 |
| A-9 | A Windows-only layout regression (narrower Linux fonts) reached CI. | — | open → M352 | — | — | Guarded only by the CI Windows job until the M352 pre-push large-font probe exists. |

## Status-claim corrections (vocabulary)

The M291–M320 evidence files used "COMPLETE". The corrected statuses are below; they supersede the earlier wording.

| Capability | Earlier wording | Corrected status |
|---|---|---|
| M311 architecture revision diff | COMPLETE | IMPLEMENTED — PARTIALLY QUALIFIED (synthetic tests; no mutation catalogue until M327) |
| M314 DDR bit-hydraulics check | COMPLETE | IMPLEMENTED — SCREENING (replay since `bc8e15b`) |
| M317 cement job reconciliation | COMPLETE | IMPLEMENTED — WORKSHEET (displacement is an upper-bound check only) |
| M318 T&D friction sensitivity | COMPLETE | IMPLEMENTED — SCREENING (no calibrated friction factor) |

None of these items is labelled QUALIFIED. That label needs the M327 mutation and M349 benchmark evidence.

## Gates run on `bc8e15b` content (local, not CI)

- ruff on `core dialogs tabs tests`: clean.
- Exception scan: silent-unexplained 83 / ceiling 83. The ceiling was not raised.
- Privacy check: 1,780 files, 0 findings.
- `dependency_audit.json` and `constant_inventory.json` regenerated with `--write`. The new 42.0 gal/bbl use is in `cement_job_reconciliation.py`.
- Targeted suites: 255 tests, 0 failures, 0 skipped. These cover the guards (`test_model_registry`, release boundary, m112, m192, exception scan), the History suites m67/m70/m73/m108/m109/m286/m303–m306, the cement and W3c suites, and M311/M314/M317/M318 plus the new file.
- CI on the pushed SHA: recorded in the M360 closure report, not here.
