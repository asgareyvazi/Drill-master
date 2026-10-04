# M36 / P6 progress — current reconciled status

**Updated:** 2026-10-04 (Asia/Tehran)

**Status:** Original-register adjudication is numerically and structurally reconciled. Source-hash provenance is **PARTIAL** for one historical W5 file digest; external recovery bundles and operational acceptance remain **NOT RUN / NOT VERIFIED**. This is a current human-maintained status note; `tools/m36/p6_apply.py` does not generate it.

The machine-readable source of truth is `m36-master-ledger.json`, with per-batch evidence retained in `p6-batch-002.json` through `p6-batch-029.json` and record-level stamps in `m36-open-item-register.json`. No historical batch payload was rewritten for this reconciliation.

## Original-register accounting

```text
1,224 total original-register records
=     2 DEFECT-FIXED before P6 (not assigned to a P6 batch)
+ 1,222 unique records adjudicated by P6 batches 002–029
+     0 currently OPEN
```

- The two pre-P6 fixed HIGH records are `INV34-005842` and `INV34-008380`.
- Actual open records entering P6 adjudication: **1,222** — HIGH **369**, MEDIUM **853**. The full register had 371 HIGH and 853 MEDIUM records because the two already-fixed records were HIGH.
- P6 classifications over the 1,222 batch records: `VERIFIED-CORRECT` 502; `INTENTIONAL` 339; `DUPLICATE/FALSE-POSITIVE` 342; `DOMAIN_DECISION_REQUIRED` 21; `GENUINE_DEFECT` 18.
- Including the two pre-P6 records, the 1,224 register classifications sum to 502 + 339 + 342 + 21 + 18 + 2 = **1,224**.
- All 21 `DOMAIN_DECISION_REQUIRED` records have terminal register dispositions. This does **not** assert that an external/domain owner has made the corresponding policy decisions.
- The 17 batch-level `defects_fixed` entries are not one entry per original-register defect: some entries cover multiple records, some link to `NEW-P6-*`, and one is a test-fixture-only correction. Record-level reconciliation maps all **18** `GENUINE_DEFECT` records to fix commits and focused regressions: 15 are explicitly named in batch fix metadata, and 3 are cross-linked through `NEW-P6-021`, `NEW-P6-012`, and `NEW-P6-017`. The full map is in `m36-master-ledger.json`. These 18 are separate from the two pre-P6 `DEFECT-FIXED` records.

## Batch, overlap, and provenance reconciliation

- Batches **002–029**: 28 payloads, **1,222** items, 1,222 unique record IDs, no ID overlaps, and exact coverage of the batch-assigned register records. Every payload's record count, classification counts, distinct `(file,line)` site count, evidence fields, and ledger summary reconcile.
- Repeated source locations are retained as separate register records: 92 repeated `(file,line)` groups / 120 additional record occurrences, of which 27 groups span batches / 44 additional cross-batch occurrences. These are not repeated record IDs; per-batch site counts are local distinct sites and must not be summed as a global distinct-site count.
- All 28 evidence commits resolve, are ancestors of the reviewed source head, and contain their named batch payload. Recorded source heads resolve and their trees verify for **27/28** batches. `p6-batch-002` did not record a source head/tree; this gap is left explicit, not inferred.
- The `staleness.checked` count equals each batch's record count. Re-anchoring records are retained in the original payloads; moved sites were re-anchored rather than silently discarded. One source line (`INV34-008346`) is recorded as a prefix due to the source-register line-length limit; the exact source-file hash and prefix match.
- Git-history source-file SHA-256 check: **332/334 batch/file hash contexts matched** in available evidence ancestry. The two unmatched contexts are the same historical digest for `tabs/w5_Equipment_Widget.py` in batches 003 and 016, covering `INV34-005839`, `INV34-005886`, `INV34-005838`, `INV34-005840`, `INV34-005895`, `INV34-005897`, `INV34-005899`, and `INV34-005900`. The two pre-P6 fixed records share that same digest. The referenced `/home/user/recovery` directory is absent, so the external recovery bundles and their listed hashes cannot be verified here. This is a recorded provenance limitation, not silently treated as a successful hash check.
- `m36-master-ledger.json` now records each batch's declared head, resolved commit/tree where available, evidence commit, production/test-fix commit list, test evidence, staleness details, classifications, defects, and secondary findings. Original batch JSON remains unchanged.

## Secondary `NEW-P6-*` findings — separate scope

The 20 unique secondary findings are not part of the 1,224-record arithmetic and none overlaps an original register ID. The six owner-dependent findings remain preserved as open owner decisions in the W15 remediation evidence:

- `NEW-P6-007` — technically bounded; well-control assumption decision remains open.
- `NEW-P6-008` — conservative null-runway behavior implemented; mud-policy decision remains open.
- `NEW-P6-015` — unknown/invalid completion-OD presentation hardened; owner presentation decision remains open.
- `NEW-P6-020` — existing movement truth preserved; owner balance-policy decision remains open.
- `NEW-P6-023` — no validator contract invented; owner contract decision remains open.
- `NEW-P6-024` — failed cost query distinguished from empty results; owner report-policy decision remains open.

These mitigations do not imply owner acceptance or operational use.

## Validation and external boundaries

- Read-only reconciliation command: `python tools/m36/p6_validate.py --verify-git-history`.
- Latest local reconciliation: structural checks **PASS**; Git evidence/head/fix commit checks **PASS** (28/28 evidence commits, 27/28 recorded heads, 15 reconciled fix commits: 14 production-behavior commits plus one test-fixture-only commit); source-hash check **PARTIAL** for the W5 history above.
- Batch 029's local source-release attempt, recorded in that payload, was **BLOCKED** at pytest collection by missing `libGL.so.1`; its full pytest and wheel smoke were not run. Separately, GitHub Source release gate run `37104942437` passed on the **pre-bookkeeping** source SHA `23ab081ce9882aaa9631dcdfe62c0979cc97be3a` across Python 3.11, 3.12, and 3.13, including its real-Qt, test, and wheel steps. That older SHA is not evidence for the later accounting/updater commit; exact-final-SHA CI remains the release criterion.
- `w16-integration-acceptance-2026-09-30.json` is historical repository evidence, not proof that the actual external environment was exercised. Real DDR PDF input, MinerU service, Windows packaged executable, production database, and business/operator acceptance: **NOT RUN**. Sandbox-local Qt tests that require `libGL.so.1` remain environment-limited; no external acceptance is inferred.
- No next M36 batch is due. Continue only after the repository accounting changes have exact-SHA CI, are pushed to `arena/01a0ec23-drill-master`, and the remote SHA/worktree state are verified. Keep the six owner decisions and external gates visible.

## Historical snapshot retained (not current authority)

The following is the previous `P6_PROGRESS.md` snapshot, retained verbatim for history. Its batch-010 resume point, counts, branch statement, and next actions are stale and must not be followed.

````text
# P6 PROGRESS - authoritative resume point

```text
HEAD at generation:     <regenerated by the next p6_apply>   (snapshot - this file is written before its own commit;
                        `git log -1` is authoritative.  At the close of phase 1 it was 69c8553,
                        after the tooling/stamp/report commits.)
branch:                 arena/01a0c945-drill-master (local only - never pushed)
last completed batch:   p6-batch-010  (9 records, 9 sites, audit-only; evidence commit 5a17ee1)
HIGH remain:            0
MEDIUM remain:          853
OPEN remain:            853   (of 1224 register records)
CRITICAL:               0
register defect-fixed:  2
defects fixed by P6 batches: 3  (one entry per fixed defect; commits in the batch reports)
new findings recorded:  2
code commits by batch:  p6-batch-002 audit-only · p6-batch-003 c2e0016 · p6-batch-004 3f0cf3e · p6-batch-005 ff2000a · p6-batch-006 audit-only · p6-batch-007 audit-only · p6-batch-008 audit-only · p6-batch-009 audit-only · p6-batch-010 audit-only
last validation:        ledger check True; register 1224 -
                        2 fixed - 369 adjudicated = 853 open
tests (this batch):     no production change in this batch; the full suite evidence recorded in P6_PROGRESS.md (1 831 tests / 0 failures / 0 errors / 4 skipped on the 3f0cf3e tree) stands for this batch too - this batch edits no production file at all
worktree:               see `git status --porcelain -uall` - the six permanent review-required
                        evidence files stay untracked by design; nothing else is modified
recovery bundles:       /home/user/recovery/drillmaster-*.bundle - catalog + sha256 in
                        /home/user/recovery/MANIFEST.txt and in the master ledger
```

## Next exact actions

```text
next batch:   p6-batch-011
next item:    INV34-000073
next site:    core/ai_import_mapper.py:65  (R-EXC-OTHER / typed-exception)  [class A]
command:      python tools/m36/p6_dump.py p6-batch-011 45
              # then write docs/audits/m36-evidence/p6-batch-011.json and run:
              python tools/m36/p6_apply.py p6-batch-011
blockers:     none in the repository; environment needs LD_LIBRARY_PATH=/tmp/qtstub for Qt tests
```
````