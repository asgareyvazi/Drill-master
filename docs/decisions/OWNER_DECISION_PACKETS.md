# Owner decision packets (M43 continuation, 2026-10-21)

Each packet gives the facts, the options and the exact next action. **None of
these were decided or executed by the agent.** Status vocabulary: `VERIFIED`,
`IMPLEMENTED_NOT_FULLY_VERIFIED`, `OWNER_GATED`, `BLOCKED`, `NOT_RUN`, `FAILED`.

## P1. Default-branch privacy containment (URGENT): OWNER_GATED

- **Facts (re-checked 2026-10-21):** `origin/drill-Master` =
  `e3fa42a3257e981d9bdf9d012c97919e3352a53a`. Its tree still contains the real DDR
  workbook and the second real DDR PDF, plus the redaction-pending files
  inventoried in `docs/privacy/HISTORY_PURGE_PLAN.md` §1. No containment PR exists.
  This session can push only `arena/72010272-drill-master`.
- **Prepared:** `tools/privacy/contain_default_branch.sh` builds a privacy-only
  branch from the actual `drill-Master` tip. The verified result tree is
  `7f3c9ca4f68d24724123de5bcd1109aee671c3c2`: 0 findings, 0 of 18 protected blobs,
  245 passed / 1 skipped, 23 files. The script never pushes.
- **Action:** run the script in a fresh clone, push the branch it prints, open a
  PR to `drill-Master`, review that the diff is privacy-only, and merge. Then
  re-run `python tools/privacy/privacy_check.py` on the merged tip.
- **Note:** merging does **not** remove the data from history (P2).

## P2. History purge: OWNER_GATED, NOT EXECUTED

- Plan: `docs/privacy/HISTORY_PURGE_PLAN.md`. It is a single `git filter-repo`
  run (path removal for the xlsx and pdf, `--replace-text`, and a blob
  substitution), with the §6 verification over 18 blobs and the §9 checklist.
- Requires: P1 merged; an encrypted offline mirror backup; a coordinated
  force-push window; every collaborator re-clones; GitHub Support purges cached
  views and the `refs/pull/*` refs (PRs #1–#4 reference the old objects).

## P3. Read policy: OWNER_GATED

- **Facts:** writes are enforced at the data layer (`core/authorization.py`
  `TABLE_POLICY`, `before_flush`). Reads are **not** restricted by role
  (`docs/SECURITY_MODEL.md`, "Read policy"). Anyone with file access can read
  the SQLite file directly.
- **Options:** (a) keep "every signed-in role reads everything" and document it;
  (b) per-role read filters in the service layer, which is UI-level and bypassable
  by direct file access; (c) (b) plus encryption at rest (SQLCipher-class; new
  dependency, key management). The agent did not invent a policy.

## P4. Licence: OWNER_GATED

- `docs/decisions/0001-license.md` lists the options and the procedure. Until
  decided, the repository has no grant of rights.

## P5. Money (D1–D7): OWNER_GATED; no migration performed

- Worksheet: `docs/MONEY_MIGRATION.md`. It covers storage type, currencies and
  scales, rounding (the 2.675 semantics are preserved), unknown currency, NPT
  currency, inexact conversion and legacy columns.
- Verified 2026-10-21: amounts are still `Float`. `money_audit.py` left a
  synthetic database byte-identical; it creates SQLite `-wal`/`-shm` side files
  (details in `docs/MONEY_MIGRATION.md`).

## P6. Windows / operator acceptance: OWNER_GATED, NOT_RUN

- The automated Windows gate passes on CI for each pushed code SHA (see the M43
  report, section D). It is **not** operator acceptance.
- Manual procedure: `packaging/WINDOWS_RELEASE_ACCEPTANCE.md`, "Interactive
  installation procedure" (six steps). The acceptance register in the same file
  must be filled by an operator.

## P7. Deployment and backups: decision required

- **Facts:** `core/db_maintenance.py` defaults to keep = 10 backups (range
  1–1000) and an interval of 30 min (range 5–1440). An interval of 0 in the
  environment variable disables the schedule; the saved setting has its own
  `enabled` flag. Precedence is
  environment > saved `database_backup/*` setting > default. Network paths are
  rejected. Backups are verified before they are kept, and restore keeps a
  safety copy.
- **Decisions:** backup directory (a different physical disk from the live
  database: a copy on the same disk does not protect against disk loss), external
  or offline copy cadence, retention, interval, disk-space budget, and a periodic
  restore drill on a spare machine. Procedure: `docs/DATABASE_OPERATIONS.md`.

## P8. Code signing: OWNER_GATED, UNSIGNED

- Every CI Windows run reports `UNSIGNED/NotSigned`.
- Prerequisites: an OV or EV code-signing certificate (EV is hardware-token
  based), storage as a protected CI secret or a cloud HSM, a timestamp
  authority URL, and approval to add a signing step. The signing record
  contract is described in `packaging/WINDOWS_RELEASE_ACCEPTANCE.md`
  ("Signature status").
