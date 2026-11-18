# Qualification run on 649e33d (superseded)

Full local suite (5551 passed, 0 failed, 4 opt-in skips, 2462.57 s) and all 17 mutation catalogues on the then
final code `649e33d`; CI 4 / 4 green (`ci_649e33d.txt`). Superseded because the run exposed **D80**: the D74
conftest changes (`cfaf476`, `4b6514d`) had made `mutation_m121_m140` `D52-flush-is-a-no-op` INVALID (its anchor
also matched the per-test flush) and let `D52-module-fixture-skips-the-flush` SURVIVE (the per-test flush ran the
test's deletion). Fixed in the next code commit (unique anchor; the D52 test now leaves a deletion in a module
fixture's teardown; new mutant `D74-per-test-flush-skipped`). Kept unchanged as history.

`chain_progress.txt`: the `exit=` fields are NOT the commands' exit codes (the script expanded `$?` after a
`$(date …)` substitution in the same `echo`); the per-catalogue `mutants=` lines in `mutation_summary_lines.txt`
and the JSON files are authoritative, and the suite result is pytest's own summary line in the log.
