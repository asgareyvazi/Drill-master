# M327: mutation catalogue for the M291–M360 modules

**Catalogue:** `tools/quality/mutation_m321_m360.py`
**Engine:** `tools/quality/mutation_m46.py`

Each mutant puts ONE realistic defect into a scratch copy of the tree, and the listed tests must fail. Typical defects: a missing value read as zero, a dropped gate, a one-sided check, a widened tolerance, a provenance field that is not frozen.

Rules for the counts below:
- An anchor that does not match exactly once is INVALID and is never counted as killed.
- `--only` runs are reported as `complete=False`.

All data is SYNTHETIC. The label is unchanged: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**.

## Catalogue: 121 mutants

| Area | Prefix | Modules |
|---|---|---|
| M311 / M329 architecture comparison | AD- | `core/architecture_diff.py` |
| M314 DDR bit hydraulics | HC- | `core/ddr_hydraulics_check.py` |
| M317 / M331 cement reconciliation | CJ- | `core/cement_job_reconciliation.py` |
| M318 T&D sensitivity | TDS- | `core/torque_drag_sensitivity.py` |
| M320 D / M333 report manifests | RS- | `core/report_sections.py` |
| M320 E / M334 citation records | CR-, KA- | `core/citation_record.py`, `tabs/knowledge_assistant.py` |
| M308 window release | QL- | `core/qt_lifetime.py` |
| M328 History replay | HR- | `core/history_replay.py` |
| M323 / D89 new-record NULLs | W3C- | `tabs/w3c_section_data.py` |
| M349 / D92 T&D integration | TD-, TDP- | `core/engineering/engines/torque_drag.py`, `core/engineering/torque_drag_persistence.py` |

## Runs (evidence files in this folder)

| # | Run | Tree | Mutants | Killed | Survived | Equivalent | Invalid | File |
|---|---|---|---|---|---|---|---|---|
| 1 | complete catalogue at the time | `1d391fd` | 99 | 76 | 21 | 2 | 0 | `m327_mutation_run1_1d391fd.{json,txt}` |
| 2 | survivors of run 1 after the new tests (`b18706d`) | `b18706d` + tests | 21 | **21** | 0 | 0 | 0 | `m327_mutation_survivors_rerun.{json,txt}` |
| 3 | 14 new M333 / M334 mutants and 8 D92 mutants | `aff8344` | 22 | 19 | 3 | 0 | 0 | `m327_mutation_new_mutants_aff8344.{json,txt}` |
| 4 | survivors of run 3 after the new tests | `aff8344` + tests | 3 | **3** | 0 | 0 | 0 | `m327_mutation_survivors_rerun2.{json,txt}` |

An earlier run (`3ee54b97`) was invalid because the tree changed during it. It is not used.

Run 2 reports `seconds=57831`. That figure is a sandbox clock jump, not the run time.

**Result over the whole catalogue:**
- All 119 non-equivalent mutants have been killed.
- 2 mutants are declared EQUIVALENT, with their reasons in the catalogue:
  - `TDS-comma-decimal-accepted`
  - `HR-m314-problems-dropped`: `save_check` stores only COMPUTED checks, and `evaluate` computes only when there are no problems, so no frozen snapshot can carry problems.
- 0 mutants are invalid.

**Limitation:** this result is assembled from one complete run and three `--only` runs on successive trees. No single complete run of all 121 mutants on one SHA has been made. Each `--only` run ran its full baseline (all listed tests green) before mutating.

## What the survivors exposed (tests added, not code weakened)

| Survivor | Gap | Test that now kills it |
|---|---|---|
| 21 survivors of run 1 (AD, HC×7, CJ×3, CR, HR×4, QL, RS, TDS×3) | Mostly one-sided checks, missing band and tolerance edges, legacy replay claims and a lenient version parse | The survivor-kill tests in `b18706d` (see `m328_history_replay.md` and the test files named in each mutant) |
| `RS-listed-empty-as-included` | No test asserted the *status* of an empty NPT / cost / plan list, only its detail text | `test_m320d_report_sections.py::test_a_known_zero_is_included_and_an_empty_list_is_not_recorded` |
| `RS-known-zero-as-unknown` | A computed 0 (0 % NPT, 0 cost per metre, final depth 0) was never tested | same test |
| `TD-buckling-first-segment` | Every buckling case had its worst segment first (at the bit) | `test_m349_benchmarks_d92.py::test_buckling_row_of_an_entry_is_its_worst_segment` (horizontal well, slack-off without WOB: compression peaks at the heel) |

## Effect on the labels

This catalogue, together with the M349 benchmarks, meets roadmap exit criterion E1. The resulting labels are recorded in `docs/mission-reports/M321_M360_INTEGRATED_CLOSURE_REPORT.md` §4.
