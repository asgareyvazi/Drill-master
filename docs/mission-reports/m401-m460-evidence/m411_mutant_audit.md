# M411 — Mutant audit (first killing test per mutant)

**Tool.** `tools/quality/mutant_audit_m411.py`, using the scratch-copy engine of `mutation_m46.py`.

**How it works.**
- Each mutant is applied in a scratch copy of the working tree.
- Its listed tests run with `pytest -x -rf`, which stops at the first failure.
- The first `FAILED` / `ERROR` node id is recorded as the killing test.
- The mutated symbol is the innermost `def` or `class` that encloses the snippet.

**Run conditions.** The working tree was dirty: M401–M460 changes were uncommitted on top of `e9244e8`, and the audit read the tree as it stood at that time. Python was 3.11.2.

The audit re-executes every mutant, so it is also an **independent re-run** of both catalogues:

| Catalogue | Mutants | Killed | Survived | Invalid | Distinct first-killing tests | Table |
|---|---|---|---|---|---|---|
| `mutation_m401_m460` | 30 | 30 | 0 | 0 | 16 | `m411_audit_m401_m460.md` / `.json` |
| `mutation_m361_m400` | 53 | 53 | 0 | 0 | 38 | `m411_audit_m361_m400.md` / `.json` |

## Findings

1. **Every killing test is a behavioural test of the mutated module.**
   - No mutant was killed by an import error, a collection error or an unrelated file.
   - In each catalogue, the first failure comes from a test file that the catalogue lists for that mutant.
   - The M401–M460 mutants are all killed in `tests/test_m415_m427_engineering_services.py`.
   - The M361–M400 mutants are killed in ten files, one per service.
2. **Concentration.** At most 3 M401–M460 mutants share a first-killing test. In M361–M400 the maximum is 4: `test_d93_vertical_collars_under_5_klbf_are_not_helically_buckled` and `test_components_match_the_hand_values`. Mutants of one equation are killed by the test that checks that equation, which is the expected pattern. No single smoke test carries the catalogue.
3. **"First" means first in file order, not the only killer.** Because of `-x`, the audit does not show how many tests would fail for a mutant. A mutant whose first killer is a broad golden test may also be killed by a narrower test later in the file. The table is therefore a lower bound on specificity.
4. **History of the three M401–M460 run-1 survivors.** All three are now killed:
   - SS-partial-sum-total → `test_surge_refusals_open_end_partial_sections_and_no_tvd`, the test extended with the wide κ 0.286 section.
   - DG-trend-unordered → `test_dull_grade_needs_a_well_and_the_trend_orders_by_depth`, where the shallow case is saved first.
   - DLG-empty-is-zero → first killed by `test_w13_dialogs_run_save_and_replay_through_the_services`, which comes earlier in the file. That test now contains the assertion that empty fields are None. In run 1, before that assertion was added, the mutant survived. This illustrates finding 3: the "first killer" can be a broader test that gained the specific assertion.
5. **Parser defect found and fixed while running the audit.**
   - The first attempt split the `-rf` line on spaces. That truncated parametrised ids containing spaces, for example `test_m370_cci_never_guesses[over0-100.0-10.0-NOT …]`.
   - The tool now splits on ` - `.
   - Both tables in this directory come from the fixed tool, a complete second execution.
   - The kill / survive results of the two executions were identical (30/30 and 53/53).

Mutation results show that the listed tests detect the listed defects. They are **not proof of correctness**.
