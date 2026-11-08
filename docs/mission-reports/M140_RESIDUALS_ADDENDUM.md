# Addendum to the M121–M140 completion report — post-M140 technical residuals

Base: final M140 report commit `74c81d6` (final code `456a5b9`). Code of this addendum: **`5c0c0c8`**.
Branch `arena/72010272-drill-master`. Main report: `docs/mission-reports/M121_M140_PRODUCT_COMPLETION_REPORT.md`
(unchanged). Live register: `docs/engineering/PRODUCT_CAPABILITY_MATRIX.md` (D59 row, D51 row, M135 rows, section
"Post-M140 residuals").

Label: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

## A. Git

| Commit | Content |
|---|---|
| `74c81d6` | base: final M140 report (CI Source 42494666748 ✅, Windows 42494666655 ✅) |
| `5c0c0c8` | R1 `utcnow()` fix; D59 fix; stale `.partial` folder workflow; 15 tests; 19 mutants; `dependency_audit.json` regenerated |
| this commit | addendum, matrix rows, complete-mutation evidence for `5c0c0c8` |

Sandbox reset at the start of this work: the local branch ref had fallen back to `4336ea3`; recovered with
`git fetch`, a compare-and-swap `update-ref` to the remote tip `74c81d6` and `read-tree HEAD`. No reset, force push,
stash or history rewrite.

## B. Defects

| ID | Status | Summary |
|---|---|---|
| **D59** (new, P2) | **RESOLVED** in `5c0c0c8` | `finalize_package` commits the audit record, then renames. A rename failure (Windows folder held open, a name that appeared meanwhile) made the W11 panel call `discard_package`, deleting an **audited** package and saying "The unaudited folder was removed". Reproduced at `74c81d6` through the real panel (1 audit record, empty export folder). Now kept (`PackageAuditedNotRenamed`) with "Complete rename"; `discard_package(result, db)` refuses an audited manifest; the cancel message no longer claims a `.partial` folder is "never audited" |
| D51 | **OPEN** (re-examined) | no recurrence in the 10 later Source runs (30 legs) nor on `5c0c0c8`; no new frame or dump; the D52 and D46 mechanisms are related classes but neither explains a ~10 min block, so neither is claimed |
| D46 | RESOLVED with residual (unchanged) | the load test passed on all three Source legs of `5c0c0c8` (another sample; a recurrence still reopens it) |
| D6, D11 | PARTIAL (unchanged) | by design / owner gate |

Everything else in the main report's register is unchanged; no defect was reopened.

## C. Residuals done

1. **R1 — `datetime.utcnow()`** (`core/report_snapshot.py`, `captured_at`; 63 of the 67 repository warnings on
   Python 3.12/3.13). `_utc_now_naive()` keeps the stored format (naive UTC ISO text). Three tests: one patches
   `datetime` so `utcnow` raises and the local clock is not UTC — a revert or a local-time variant fails on every
   Python version, not only on 3.12+.
2. **R2 — stale `.partial` folders.** A build stopped by an error or a cancel removes its folder (`finally`); only a
   killed process leaves one — while writing (unaudited) or between the audit commit and the rename (audited).
   `inspect_stale_folder` classifies from the audit log only: AUDITED (hash **and** package name of one record) →
   rename after `verify_package` passes and the final name is free; UNAUDITED → removal after a confirmation, file by
   file without a recursive delete; REFUSED → untouched (link, non-plain entry, finalized package, no database, a
   hash audited under another name, a name audited with a changed or missing manifest). Found while testing: two
   builds of one well in the same second write **byte-identical manifests** (the folder name is not in the
   manifest), so a hash-only match would have called an unaudited twin "audited"; the name is therefore required.
   Each action writes a mandatory audit record in the same transaction; a failing audit removes nothing. W11 ›
   End-of-well package: "Stale folders…", "Remove unaudited", "Complete rename". Nothing is cleaned automatically.
3. **D51** re-examined — see B.
4. Lint-debt reduction — not done (726 ≤ 727 unchanged).

## D. Quality and CI

| Gate | Result |
|---|---|
| Full suite (local, 3.11.2, offscreen, `5c0c0c8` tree) | 5050 passed, 4 skipped (opt-in), 0 failed, 0 errors, 1788 s (+15: R1 3, D59 12) |
| New mutants | 19/19 KILLED (`R1-*` 3, `D59-*` 16) |
| Complete mutation `mutation_m121_m140.py` on `5c0c0c8` | 323: 322 KILLED, 1 declared EQUIVALENT (`SEC-empty-password-unlocks`), 0 SURVIVED, 0 INVALID, complete, 2201 s — `m140-evidence/mutation_m121_m140_complete_5c0c0c8.json` |
| Mutation anchors (all suites) | 893 valid, 0 invalid |
| Lint debt | 726 ≤ 727; changed files clean |
| Exception ratchet | 0 unexplained silent handlers |
| Privacy | 1442 files, 0 findings |
| Schema | 26/26 (old `0822a28`, new `5c0c0c8`) |
| Inventories (constant, engine, journey) | `--check` rc 0; dependency audit regenerated, 0 findings |
| CI Source on `5c0c0c8` | ✅ run 42501948499 — 3.11 job 128796404017, 3.12 job 128796403839, 3.13 job 128796404156; coverage 70.03 % (71500/102102, 3.12 leg) |
| CI Windows on `5c0c0c8` | ✅ run 42501948497 — job 128796403902 |
| Warnings (CI) | 3.12 and 3.13: 39 occurrences / 12 groups (repository 4, third-party 35), down from 102 / 13 — the `utcnow()` group (63) is gone; 3.11: 39 / 12, unchanged |

The CI of this addendum's own commit cannot be recorded inside it; it is reported in the hand-off message.

## E. Conclusion

Unchanged from the main report: integrated drilling engineering product candidate — implemented and qualified within
the documented technical scope; Windows desktop acceptance, field acceptance, legal approvals and release
authorization remain open (owner gates). The residual work fixed one real data-integrity defect (D59), removed the
dominant repository warning (R1) and left D51 OPEN with its bound.

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
