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

The P6 batches 002–004 requested for this mission were **not executed**. The reason is not a blocker in
the repository: it is that this session had to spend its budget (a) proving the loss of the prior Git
history, (b) re-persisting the surviving tree and corpus before they could be lost a third time, and
(c) rebuilding the Python/Qt toolchain that the re-provision destroyed. The adjudications that the lost
session had produced (batch 001, the `tools/m36` pipeline, `docs/audits/m36-evidence/`) no longer
exist; they are not silently presented as done.

Authoritative counts, recomputed from the surviving register
(`docs/audits/m35-evidence/m35-open-item-register.json`, committed in `1f6ae56`):

```text
register records ............... 1 224 open of 11 554 ledger records
open by priority ............... HIGH 371   MEDIUM 853   CRITICAL 0
open by rule (top) ............. R-TRUTH-UNKNOWN 367, R-DEF-UNKNOWN 152, R-EXC-PASS 98,
                                 R-TRUTH-NUMERIC 88, R-PASS-EXC 74, R-EXC-OTHER 60,
                                 R-EXC-SILENT-RETURN 52, R-DEF-RETURN-NUM 52
records with a stated contract .. 73
stale source records ............ 0
```

## 5. Exact resume point (for the next agent, without chat history)

```text
current HEAD ...... 9f45cc44  (see `git log -1 --format=%H`; branch arena/01a0c945-drill-master)
worktree .......... 0 modified, 0 staged, 5 untracked (the review-required evidence files)
register .......... docs/audits/m35-evidence/m35-open-item-register.json  (1 224 open, 371 HIGH)
adjudications ..... docs/audits/m35-evidence/m35-contract-adjudications{,-final}.json (25 closures)
tooling ........... tools/m34/ and tools/m35/ are committed; tools/m36/ does NOT exist and must be
                    rebuilt before new batches (the lost session's pipeline is gone)

first actions of the next session (in order):
 1. verify: git status --short && git log --oneline -5 && git cat-file -t 9f45cc44
 2. rebuild the environment (the image has no Qt system libs):
      python3 -m venv /home/user/verify-venv
      /home/user/verify-venv/bin/pip install -r requirements-lock.txt pytest
      # fail-loud stubs for libGL/libEGL/libxkbcommon/libdbus are required for any Qt import;
      # the previous session's generator is gone - regenerate from PySide6's undefined symbols
 3. run the pending regression (it is the acceptance test of 9f45cc4):
      QT_QPA_PLATFORM=offscreen DRILLMASTER_AI_IMPORT=0 python -m pytest -q \
          tests/test_permission_failclosed_regression.py
    - if it passes, mutation-check it: restore `except Exception: pass`, expect failure, restore
 4. rebuild tools/m36/ (adjudicate_batch.py, verify_fingerprints.py, p6_batches.py, p6_dump.py,
    apply_p6.py, open_register.py, finalize_ledger.py) from the committed register + M35
    adjudications; keep the proven discipline: read each site, quote the deciding contract,
    withdraw any predicate that closes a record on evidence belonging to another subject
 5. start P6 batch 002 at the first open HIGH record of the register, class A first

next file/line: first open HIGH record in the committed register (regenerate the ordered list with
                tools/m34 tooling or by sorting register records by priority then file/line)
NOTE: no push is permitted; every commit is local-only, and this environment has demonstrably
      discarded the object store twice - treat the remote as the only durable destination, and tell
      the user when a push would be required to make the work permanently safe.
```

## 6. Untracked corpus status

287 untracked files at the start of this session → 267 committed in `1f6ae56` → **5 remain untracked**,
all Review-Required oversized evidence files, untouched. No production source is untracked: the only
non-corpus untracked entries that existed (`.github/workflows/ci.yml`, the two recovered modules, the
M-era test files) are all committed now.
