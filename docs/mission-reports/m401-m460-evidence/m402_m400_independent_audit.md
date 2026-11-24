# M402 — Independent audit of the M361–M400 delivery against the source

Method: every claim was re-derived from the tree at `e9244e80364641315d1da31e62e055b9548d57dd` (`git archive` into a scratch directory, read-only) or from the GitHub API. The historical report is not edited; corrections go to the M404 addendum (`m404_reconciliation_addendum.md`).

Input class: repository source and CI metadata. No DDR data was opened.

## A. Identity

| Claim (M400 report / hand-over) | Check | Result |
|---|---|---|
| Report SHA `e9244e8` differs from the tested `ed68380` only in docs | `git rev-parse <sha>:<dir>` for core, dialogs, tabs, tests, tools, ui, packaging and .github at `41ea53e` and `e9244e8` | **VERIFIED.** All 8 trees are identical (`core d108d165…`, `tests 8d0d1da5…`, …). The diff is 6 docs files. |
| `drill-Master` untouched at `e3fa42a` | `git ls-remote` | **VERIFIED** (`e3fa42a3257e981d9bdf9d012c97919e3352a53a`). |
| Only branch written | `git log` on the remote branch, fast-forward chain from `3ca8b80` | **VERIFIED.** |

## B. CI

| Claim | Check (`gh api …/runs/<id>` and `/jobs`) | Result |
|---|---|---|
| `ed68380` Source `45345379551` SUCCESS: 3.11 45m23s, 3.12 58m35s, 3.13 47m27s | jobs: 3.11 07:06:06→07:51:29, 3.12 07:06:06→08:04:41, 3.13 07:06:05→07:53:32; `head_sha` = `ed68380…` | **VERIFIED.** |
| Windows `45345379462` SUCCESS 26m09s | run 07:06:02→07:32:15 (26m13s run-level); conclusion success; `head_sha` = `ed68380…` | **VERIFIED** (the 4 s difference is job vs run wall time). |
| `e9244e8` Source `45353234275`: attempt 1, 3.12 TIMEOUT; attempt 2, 3.12 SUCCESS | `jobs?filter=all` for attempts 1 and 2 | **VERIFIED.** Both attempts are reported, and the TIMEOUT is not called green. |
| `e9244e8` Windows `45353234306` SUCCESS | run API | **VERIFIED.** The attempt-2 jobs endpoint returns 404, because there was no attempt 2. |
| `8ceaeb7` Source FAILURE (1 test, `test_m113`) | annotations | **VERIFIED.** |

## C. Counts and gates

| Claim | Re-derived | Result |
|---|---|---|
| Method catalogue: 62 entries, 0 approved | `core.method_catalogue.catalogue()` at `e9244e8` gives 62; entries with approval "APPROVED" give 0 | **VERIFIED.** |
| Mutation catalogue: 53 mutants, 53 killed (run 3) | `tools/quality/mutation_m361_m400.py` defines 53 `Mutant(`; `m389_run3_41ea53e.txt` reports 53 killed and complete=True | **VERIFIED** (count and evidence; not re-executed on `e9244e8` because the trees are identical). |
| 31 benchmarks, 0 outside tolerance | `benchmark_m396.py --check` on the M401 tree: exit 0, 31 PASS, table identical | **VERIFIED (reproduced).** |
| 35-step MainWindow journey | `tests/test_m375_main_window_journey.py` has 35 `step("…")` calls | **VERIFIED.** |
| Capability catalogue: 48 domains | the catalogue table has 48 numbered rows | **VERIFIED.** |
| Inventories current | `engine_inventory`, `dependency_audit` and `constant_inventory` `--check` at `e9244e8`: all exit 0 | **VERIFIED.** |
| pillow 13.0.0; PySide6 four packages at 6.8.1.1 | `requirements-lock.txt` | **VERIFIED.** |
| Local suite 8/8 shards exit 0 | `suite_final_sharded.txt` | **VERIFIED AS STATED, BUT WEAK.** The runner trusted exit codes and recorded no per-test counts, so exit 0 alone was taken as a pass. This was fixed in M407 (`tools/quality/run_suite_sharded.py` with the `pytest_outcome_recorder` plugin). |

## D. Contradictions and inaccuracies found (corrected by addendum, not by editing history)

1. **M370 CCI storage.**
   - The report (§5) and catalogue row 16 say "CCI appears in the M366 summary lines only, not as its own case field".
   - The source since `70fa14b` stores `base_cci` (value) and `base_hole_cleaning_status` in every M366 case's results (`core/hydraulics_workflow.py` `case_payload`), and `test_m366` asserts it.
   - Catalogue row 16 also says "in the M366 case", which contradicts its own limitation column.
   - **Correct statement:** the value and status were stored; the provenance (n, K, AV, MW, rheology source, inclination, method) was not.
   - M422 adds those fields as `M366 v2`, with v1 cases still replayable.
2. **D88 wording.** "1m25s under the 60 min limit" is correct for `ed68380`. However, the 3.12 leg on `e9244e8` attempt 1 timed out. D88 is therefore an active risk, not a resolved one.
3. **Local-suite evidence strength.** See C, last row.
4. **AC2 benchmark.** It is correctly labelled as equal-MD rather than the 3D closest approach. No benchmark covered the D94 value itself until M412 (D94-1, D94-2).
5. **M372 limitation.** "Not a fitted line" is still true for M372. The fitted line is a separate method in M423.

## E. Not checked

- Windows desktop behaviour on real hardware, field data and real DDR workbooks: NOT RUN (unchanged).
- Branch protection: the API returned 403, so it is NOT CHECKED (`protected=false` in the branch object; no rulesets).
