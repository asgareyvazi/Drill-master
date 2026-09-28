# M36 — RECOVERY AND P6 CONTINUATION REPORT

Written from the actual repository state, not from prior reports. Every claim below was checked with
a Git command or a source read in this session.

## 1. What happened to this repository (the single most important finding)

The prior missions' work is **not present in this repository and cannot be recovered here**:

```text
git reflog (in the clone this sandbox replaced) showed only:
    c28bbef HEAD@{0}: checkout: moving from drill-Master to arena/01a0c945-drill-master
    02053eb HEAD@{1}: clone: from https://github.com/asgareyvazi/Drill-master.git

git cat-file -t <any prior SHA>   ->  "Not a valid commit name"  (M35 A-E, M36, all of them)
git merge-base --is-ancestor <any prior SHA> HEAD  ->  NO
find / -name "*.pack" (newer than 2026-09-20)     ->  none
```

The sandbox was re-provisioned from a **fresh shallow clone** of `origin/drill-Master` at `c28bbef`
("M27: release-candidate integrity certification"). Because the previous missions were local-only by
instruction (no push), their commits existed only in the discarded object store. During *this* session
the Git object store was discarded a **second** time — two recovery commits (`5d43bb2`, `a43bd99`) and
the rebuilt toolchain (`/home/user/verify-venv`, `/tmp/qtstub`) disappeared mid-turn while the
worktree files survived. The recovery commits below re-establish the state, but the structural lesson
stands: **in this environment nothing is durable until it is committed, and even then it is lost if the
object store is discarded again**.

Reconciliation of the brief's claims against Git:

| Claim | Actual |
|---|---|
| HEAD `28ef1f0` / `0c07b6d9` / `c5b56d9` | HEAD **`c28bbef`** at session start; none of those SHAs resolve here |
| `d7f4efe` fixed the W5 gate | absent — the defect was **live in the worktree** and is fixed again in `9f45cc4` |
| open 1 199 / HIGH 346 / 1 099 / 307 | the surviving register says **1 224 open, 371 HIGH, 853 MEDIUM, 0 CRITICAL** (the later numbers belonged to the lost M36 runs) |
| 253 untracked | was **287** at clone (the extra files are the M35-era additions that were untracked then) |

## 2. Recovery commits (this session)

| SHA | Subject | Files |
|---|---|---|
| `fd18a2b` | recover: persist the surviving release tree | 103 |
| `1f6ae56` | recover: persist the M27–M35 audit corpus and evidence chain | 267 |
| `9f45cc4` | fix(security): fail closed when the W5 equipment permission control cannot be evaluated | 1 (+ the regression file, added in `1f6ae56`) |

All three verified with `git cat-file -t` → `commit`. Five oversized evidence files
(m31-adjudication-pass1, m32-ledger, m33-ledger, m33-reconciliation, m34-ledger, 6.8–11.1 MB) remain
untracked exactly as the surviving M35 commit manifest classified them ("REVIEW-REQUIRED — large file,
confirm provenance"); they were neither deleted nor committed.

Known hygiene defect: `.github/workflows/ci.yml` was untracked in the fresh clone and was swept into
the corpus commit (`1f6ae56`) instead of the release-tree commit. History was **not** rewritten to fix
this (no amend/rebase); it is recorded here.

## 3. The W5 defect (re-confirmed from source, not from reports)

`tabs/w5_Equipment_Widget.py`, `EquipmentWidget.save_all_data` — read at 758–772:

```python
try:
    from core.permissions import permissions
    if permissions.is_viewer(): ... return False
    if not permissions.has_permission("can_edit_reports"): ... return False
except Exception:
    pass                                   # <- continued into save_all(steps)
```

Control flow after the handler reaches `save_all(steps)` → `db.save_equipment_records()` /
`db.save_inventory_items()`, i.e. an unevaluable access control authorised the mutation the comment
above the block forbids. The repository-wide contract is fail-closed and was quoted at both siblings:

* `core/permissions.py:83-95` `require_permission` — on exception it logs and sets `allowed = False`,
  then returns **without** calling the guarded function.
* `tabs/w16_Cost_Management.py:505-516` — on exception it returns
  `SaveOutcome(issues=[SaveIssue(..., status="SYSTEM_ERROR")])` before any write.

Fix applied (`9f45cc4`): log the failure, tell the user nothing was saved, `return False` before any
persistence step — the same shape as the siblings, nothing else touched.

Regression: `tests/test_permission_failclosed_regression.py` drives the **real** `save_all_data` with a
stub persistence layer and a controllable permission double, and asserts: unevaluable control, denied
control and viewer role each produce a falsy result, **no call to `save_all`** and an **empty
persistence recorder**, plus a control case proving a granted permission still reaches the save path
(so the first three cannot pass by refusing everything).

> **Execution status: NOT-RUN — environment blocked.** The test file compiles (`py_compile` OK) but
> this image has no system `libGL/libEGL/libxkbcommon/libdbus`, and the virtualenv + stub libraries
> that made PySide6 importable were destroyed by the second re-provision. It is therefore **not**
> claimed as passing, here or anywhere else.

Command to run once dependencies exist:

```bash
QT_QPA_PLATFORM=offscreen DRILLMASTER_AI_IMPORT=0 python -m pytest -q \
    tests/test_permission_failclosed_regression.py
```

## 4. P6 status (honest arithmetic)

The register this mission works from is the surviving M35 register, rebuilt into
`docs/audits/m36-evidence/m36-open-item-register.json` (1 224 records, input never edited).

```text
register ....................... 1 224 records = 1 222 open + 2 DEFECT-FIXED (W5 fail-open gate 9f45cc4,
                                 W7 bulk-stock three-state c2e0016)
adjudicated in batches 002-004 .. 135 records (45 + 45 + 45)
open ........................... 1 087 = HIGH 234 / MEDIUM 853 / CRITICAL 0
arithmetic ..................... 1224 - 2 - 135 = 1087   (ledger check: true)
batch 002 (audit-only) .......... 45 records / 36 sites -> VERIFIED-CORRECT 24, INTENTIONAL 16,
                                 DOMAIN_DECISION_REQUIRED 3, DUPLICATE/FALSE-POSITIVE 2
batch 003 (code c2e0016) ........ 45 records / 43 sites -> INTENTIONAL 16, DUPLICATE/FALSE-POSITIVE 15,
                                 VERIFIED-CORRECT 13, GENUINE_DEFECT 1 (w7:825)
batch 004 (code 3f0cf3e) ........ 45 records / 36 sites -> VERIFIED-CORRECT 24, DUPLICATE/FALSE-POSITIVE 14,
                                 INTENTIONAL 7; 1 new defect found and fixed (NEW-P6-001)
```

Staleness is proven per record, never assumed: the register's recorded text must equal the current
line, records pointing at a fixed block are verified against the fix's parent revision, and lines the
fix merely shifted are re-anchored through the line map derived from the real diff (batch 004:
3 re-anchored, 0 stale).

## 5. Exact resume point (for the next agent, without chat history)

```text
current HEAD ...... 3f0cf3e (code) -> a375b06 (batch-004 evidence)  [git log --oneline -5]
branch ............ arena/01a0c945-drill-master  LOCAL-ONLY — NOT SYNCHRONIZED TO GITHUB
worktree .......... see `git status --porcelain -uall`; the only untracked entries are the five
                    review-required M31-M34 ledgers and the full-suite JUnit copy (kept out of the
                    wheel on purpose: tests/test_release_boundary_imports.py forbids docs/audits)
recovery bundle ... /home/user/recovery/drillmaster-a375b06.bundle
                    sha256 22dc2b89aa6d5915d233d1890fd325ec1df65cae2c6c3a6849e1dce322a8b17b
                    (clone-verified, 809 tracked files; earlier bundles 2f61e6f, acb6279, ...)
tooling ........... tools/m36/p6_{plan,dump,apply,stamp}.py + p6_batch_00{2,3,4}.py (committed)
progress file ..... docs/audits/m36-evidence/P6_PROGRESS.md (authoritative resume point)

environment:
  python ........ /home/user/verify-venv/bin/python  (pytest 9.1.1, PySide6 6.8.1.1, sqlalchemy 2.0.36,
                   ruff 0.16.9, build) - the system python has no pytest/ruff
  Qt tests ...... LD_LIBRARY_PATH=/tmp/qtstub QT_QPA_PLATFORM=offscreen DRILLMASTER_AI_IMPORT=0
  ruff gate ..... /home/user/verify-venv/bin/ruff check core dialogs tabs tests
                  baseline: 5 338 findings - byte-identical before and after the mud_ledger fix
                  ("no debt increase"), and 0 findings in every file this session added

next batch:   p6-batch-005, first item INV34-001765
next site:    core/engineering/well_control_kill_sheet.py:288  (R-DEF-RETURN-NUM / or-zero)  [class C]
command:      /home/user/verify-venv/bin/python tools/m36/p6_dump.py p6-batch-005 45
              # then write the adjudication (tools/m36/p6_batch_005.py, modelled on p6_batch_004.py)
              # and run /home/user/verify-venv/bin/python tools/m36/p6_apply.py p6-batch-005
NOTE: no push is permitted; every commit is local-only, and this environment has demonstrably
      discarded the object store twice - the bundle is the continuity artifact, take a new one and
      clone-verify it after every checkpoint.

## 6. Untracked corpus status

287 untracked files at the start of this session → 267 committed in `1f6ae56` → **5 remain untracked**,
all Review-Required oversized evidence files, untouched. No production source is untracked: the only
non-corpus untracked entries that existed (`.github/workflows/ci.yml`, the two recovered modules, the
M-era test files) are all committed now.

## 7. P6 batch log and validation evidence (as executed, this session)

```text
batch 002  commit 3b60dfd   evidence: p6-batch-002.{json,md}      45 records / 36 sites
batch 003  commit 2f61e6f   code c2e0016 (w7 fix)                45 records / 43 sites
batch 004  commit a375b06   code 3f0cf3e (mud-ledger fix)        45 records / 36 sites
```

Defects found and fixed by P6 (each with its own killing regression, mutation-validated, and its own
code commit — never mixed into an audit commit):

```text
1. tabs/w7_logistics_Widget.py:825  (INV34-006021 / INV34-008432, batch 003)
   `float(cell.text() or 0)` turned an unreported opening stock into 0 and displayed a fabricated
   "Current Stock" (observed '5.0'), while the loader's own em dash for unknown ("Unknown stock
   displays as an em dash, never as 0.0", 1217) raised through the handler.  Fix c2e0016.
   Regression: tests/test_bulk_stock_three_state_smoke.py (subprocess-isolated, offscreen Qt).
2. core/mud_ledger.py:208  (NEW-P6-001, batch 004)
   `float(m.closing_stock)` raised TypeError on the documented unknown closing (None), so one
   unreported opening broke the whole history call and with it the check_mud_ledger AI tool
   (observed: {'success': False, 'error': "float() ... 'NoneType'"}).  The same class in
   check_continuity (:247-248) raised too.  Fix 3f0cf3e.  Regression:
   tests/test_mud_ledger_unknown_stock_history.py (5 tests, facade + AI-tool path).
```

Validation evidence on the fixed tree (`3f0cf3e` / `a375b06`):

```text
full suite ....... 1 831 tests, 0 failures, 0 errors, 4 skipped, 297.773 s
                   skips are all opt-in/external: DDR xlsx + DDR pdf acceptance,
                   MinerU real integration, Windows bundle smoke
                   (JUnit: /home/user/recovery/p6-full-suite-batch-004.xml,
                    sha256 09316734954cafd11052c7198668f106a9a30752cc08e971816aea4c0c72a604)
focused slice .... 163 tests (ledger/inventory/bulk/mud), 0 failures, 0 errors, 0 skipped, 24.795 s
mutation checks .. each fix re-broken: pre-fix text -> TypeError / fabricated 5.0 / 0.0 != None,
                   then restored byte-identical (sha256 verified)
ruff ............. no debt increase (5 338 == 5 338)
```

## 8. What is still NOT done (no green-washing)

* HIGH 234 remain open: P6 covered batches 002-004 (135 of 1 222 open records). Mission condition A
  (all HIGH adjudicated) is **not** met; the mission stops at a clean, resumable checkpoint
  (condition B) with the exact next item recorded above.
* Packaging was not re-run in this session: no check in P6 has shown breakage, and the release
  boundary test (wheel from `git ls-files`, no `docs/audits`, no `__pycache__`) passes in the full
  suite. Windows runtime remains WINDOWS-RUNTIME-NOT-RUN.
* The five M31-M34 ledgers stay untracked and review-required; nothing was deleted.
* The M36 P6 work is local-only: no push, so the remote copy does not contain it.
