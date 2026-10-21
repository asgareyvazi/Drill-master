# M43 — Database reliability: verified backup, safe restore (Phase E/F)

Repository `asgareyvazi/Drill-master`, branch `arena/72010272-drill-master`.
Date 2026-10-20. Phase checkpoint `1fe80df2fd55da5e1daf3dd4620ab4c2896e06cb`.
Code-complete SHA `90016027b065dc32a8889b7a28a4bf154a3bceaa`; this report is
committed on top of it (documentation only).

Earlier M43 database work (connection reliability, schema v6 indexes, money
read-only audit) is recorded in `docs/DATABASE_OPERATIONS.md`,
`docs/DATABASE_PERFORMANCE.md` and `docs/MONEY_MIGRATION.md` and is not
repeated here except where this phase relies on it.

## A. Executive summary

* **Backup (Package E).** Backups are consistent online snapshots (SQLite
  backup API from a read-only connection). Each one is:
  * verified (`integrity_check`, `foreign_key_check`, required tables, schema
    version) before it is promoted to a unique name that is never
    overwritten;
  * described by a data-free manifest (SHA-256, size, schema, time, app
    version).

  Retention is count-based and deletes only manifest-verified managed backups
  older than the newest N. It runs only after a verified new backup and never
  touches the newest verified backup, pre-restore copies, unknown files or
  the live database. The scheduler moved from a GUI-thread `QTimer` to one
  background thread that never overlaps a backup or restore (in-process lock
  plus OS file lock) and is stopped before the database closes.
* **Restore (Package F).** Restore is a privileged service operation:
  * `can_maintain_database` is enforced at the service and denials are
    audited, plus an explicit confirmation;
  * the candidate is validated before anything is touched;
  * a staged copy is used, and older schemas are migrated on that copy only;
  * a verified pre-restore safety copy is made, and the restore is blocked if
    it cannot be;
  * a maintenance gate refuses new sessions and drains transactions;
  * an exclusivity check refuses while another connection or process has the
    file open;
  * a single same-volume rename is followed by reopen and verify through the
    application engine;
  * if verification fails after replacement, the safety copy is put back and
    verified;
  * a sidecar journal records start and outcome.

  Every stage has an injected-failure test.
* **UI.** *Tools > Backup Database Now* and *Tools > Restore Database…*:
  * a candidate list with metadata;
  * a consequences warning, a checkbox and a final Yes/No;
  * the operation runs on a worker thread;
  * during it the window is frozen, autosave is paused and closing is
    refused;
  * after a successful restore the app closes, so that stale screens cannot
    save pre-restore data.
* **Key criterion.** No tested restore failure path loses the original
  database. Failures before the replacement leave it untouched. Failures
  after the replacement restore it from the verified safety copy. If even
  that fails, the safety copy is kept and reported. Limits that tests do not
  cover (power loss during the rename, interactive Windows acceptance) are
  stated in D and H.
* **Regression.** No baseline test changed status:
  * locally, all 82 non-passing tests fail only because `libGL.so.1` is
    missing in this sandbox;
  * Source CI (3.11/3.12/3.13) and Windows CI passed on the exact
    code-complete SHA.
* **Not done, by policy or scope.** Monetary Float migration (D1–D7) was not
  executed and money code is unchanged. Signing stays `UNSIGNED`. There is no
  release tag and no Windows/field acceptance claim.

## B. Git evidence

| Commit | Content |
|---|---|
| `1fe80df2fd55da5e1daf3dd4620ab4c2896e06cb` | Phase checkpoint (start) |
| `0c73d7e3ae69ec383df80c6e2150f1023c3785ae` | (1)+(2) backup + integrity, retention + scheduling: `core/db_maintenance.py` (backup part), `backup_to` verification, `auto_backup` delegation, `can_maintain_database`, scheduler thread in `main_window.py`, `tests/test_db_backup_service.py` |
| `485647eb118e0bf7f0dd623025313f28e588d336` | (3) restore + recovery: `RestoreService`, maintenance gate hook in `DatabaseManager.initialize`, `tests/test_db_restore_service.py` |
| `dd50c15c1b8534f6b7c9ee430dfcaf61f863267b` | (4) UI: `dialogs/database_maintenance_dialog.py`, Tools menu wiring, `tests/test_db_maintenance_ui.py` |
| `90016027b065dc32a8889b7a28a4bf154a3bceaa` | (5a) Windows gate includes the new tests; cross-process lock test made Windows-capable; `docs/DATABASE_OPERATIONS.md` Backups/Restore |
| this commit | (5b) this report |

* Backup and retention/scheduling share one module and were verified as one
  tree, so they form one commit. The restore half was staged separately
  (blob staging) and verified in a clean worktree before committing.
* Each push was confirmed with `git ls-remote`.
* No force-push, reset, rebase or history rewrite was used.

CI (GitHub Actions run IDs, exact `head_sha`):

| SHA | Source release gate | Windows release validation |
|---|---|---|
| `0c73d7e` | 39380235772 cancelled (superseded by next push) | 39380235733 cancelled (superseded) |
| `485647e` | 39381010250 cancelled (superseded) | 39381010282 success |
| `dd50c15` | 39382014891 success | 39382015049 success |
| **`90016027b065dc32a8889b7a28a4bf154a3bceaa`** | **39383249614 success (jobs 3.11, 3.12, 3.13)** | **39383249495 success** |

* Cancelled runs are not failures. They were superseded by the next push and
  are not used as evidence.
* The Windows run on `9001602` produced a release manifest for that SHA
  (installer `DrillMaster-1.0.0-Setup.exe`, 83,276,309 bytes) and reported the
  signature status **UNSIGNED**.
* CI for the report commit itself is checked after pushing and stated in the
  final hand-off, not here.

## C. Backup

Source: `core/db_maintenance.py` (`BackupService`, `BackupScheduler`).
Operator documentation: `docs/DATABASE_OPERATIONS.md` § Backups.

* **Destination policy.** `DRILLMASTER_BACKUP_DIR` (default
  `<data dir>/backups`), local file system only. Off-machine copies are an
  operator responsibility.
* **Snapshot.**
  * Online backup API from a `mode=ro` connection into
    `.drillmaster-backup-*.partial` in the backup directory.
  * The copy is switched to `journal_mode=DELETE`, giving a self-contained
    file.
  * It is verified, then promoted with `os.replace`.
  * Any failure removes the partial file. Nothing unverified is ever
    promoted.
* **Naming.** `drillmaster_backup_<UTC to microseconds>Z_<8 hex>.db`, claimed
  with `O_EXCL`. A collision retries with a new name (5 attempts) and never
  touches the existing file (tested).
* **Manifest** `<name>.json`: format, kind, file name, schema version, UTC
  time, size, SHA-256, app version. It holds no names, rows or credentials.
  A backup counts as verified only if the manifest matches name, kind and
  size. Listings used by retention and restore also check the SHA-256.
* **Retention.** `DRILLMASTER_BACKUP_KEEP` (1–1000, default 10), count-based
  only; age-based retention is not implemented. Deletion is deterministic,
  newest first by the UTC timestamp embedded in the file name, then the name. It runs only after a verified new
  backup and only over verified managed backups. It never deletes:
  * the newest verified backup;
  * pre-restore copies;
  * partial, unverified or unrelated files;
  * the live database.

  A file that cannot be deleted is skipped and reported in
  `retention_errors`.
* **Scheduling.** `DRILLMASTER_BACKUP_INTERVAL_MINUTES` (5–1440, `0` off,
  default 30), one daemon thread.
  * Overlap: no in-process overlap (lock). Cross-process overlap on the same
    machine is prevented by an OS file lock (`flock` / `msvcrt.locking`),
    which the OS releases when a process dies. This is tested on Linux, and
    the test now also runs in the Windows gate.
  * Failure handling: a failure is logged and retried at the next interval;
    the first run happens one interval after start.
  * Startup: nothing destructive.
  * Shutdown: new backups are refused, then the scheduler waits up to 120 s
    for a running backup. This can briefly delay window close.
* **Permission and audit.**
  * Interactive backups require `can_maintain_database` (admins by default),
    enforced at the service, with denials audited.
  * Scheduled runs use the identity `system:backup-scheduler`.
  * Outcomes are written to `audit_logs` on a separate short-lived (NullPool)
    connection, because the app's StaticPool connection is shared across
    threads.
  * **Audit-failure policy:** the verified backup is kept, and the result is
    `ok=True, audit_recorded=False` with a logged error (tested).
* **Compatibility.** `DatabaseManager.backup_to()` keeps its contract (path or
  `None`, refuses the live path, destination unchanged on failure) and now
  verifies its copy before replacing anything. `auto_backup()` delegates to
  the service.
* **Known remaining item.** The Settings dialog's legacy `backup/enabled` and
  `backup/path` values were already unused before this phase and still do not
  control the environment-based configuration above. Wiring or removing them
  is a follow-up.

## D. Restore

Source: `core/db_maintenance.py` (`RestoreService`, `RestoreJournal`,
`MaintenanceGate`). Operator documentation: `docs/DATABASE_OPERATIONS.md`
§ Restore (sequence, failure behaviour, limits and owner checklist).

* **Authorization.** `require_permission` runs at the service before
  anything else. A viewer and a missing principal are refused with
  `AuthorizationError` and an audited denial. `confirmed=False` is refused.
* **Validation, before any change.** The candidate must be:
  * a regular file directly inside the backup directory, with no symlink,
    no `..` and not the live path;
  * a managed name with a matching manifest and digest;
  * at most 8 GiB;
  * verified through a read-only connection (integrity, foreign keys,
    required tables);
  * at a schema version between 1 and the current version.

  Future schemas and non-DrillMaster or corrupt files are rejected.
  External files are rejected by policy: they must first be placed in the
  backup directory with a valid manifest.
* **Schema policy.** An older schema is migrated only on the staged copy,
  using the application's normal migrations, then re-verified. The source
  backup is byte-identical afterwards (tested), and the live database is
  never migrated in place.
* **Sequence.** Validate → stage → journal `restore_started` → maintenance
  (refuse new sessions, drain transactions for up to 15 s, dispose the pool)
  → verified safety copy → exclusivity (WAL checkpoint plus
  `journal_mode=DELETE`, refused if another connection exists) →
  `os.replace` → reopen and verify through the app engine.
* **Failure behaviour.**
  * Before the replacement: the original is untouched and the staged file is
    removed.
  * After the replacement: the safety copy is put back and verified, giving
    `recovered=True`.
  * If recovery itself fails: the safety copy is kept, the outcome is logged
    as critical and journalled, and the UI instructs the user to stop.
* **Safety-copy policy.** Pre-restore copies are never auto-deleted and are
  excluded from retention. They are listed in the restore dialog, so a
  restore can be undone.
* **Audit continuity.**
  * The sidecar journal `maintenance_journal.jsonl` records the start event
    before any change and the outcome after.
  * The outcome is also written to the restored database's `audit_logs`.
  * The safety copy preserves the pre-restore audit table.
  * Failure policy: a start-event write failure aborts the restore. Outcome
    journal and audit failures are reported (`journal_complete=False` /
    `audit_recorded=False`) and never change the outcome.
  * Neither the journal nor the audit table is tamper-proof.
* **Application state.** The UI freezes during the restore (window disabled,
  all autosave managers paused, hierarchy worker stopped, close refused).
  After success the app closes and must be restarted. After a failure the
  window is usable again.
* **Limits that are not proven by tests.**
  * Power loss during the rename or reopen is not simulated; the verified
    safety copy is the recovery path in that case.
  * Real Windows sharing violations from other programs are only simulated
    (`PermissionError` from `os.replace`).
  * The exclusivity check runs in the Windows gate, but interactive Windows
    acceptance is still owner-gated (H).
  * Network file systems are unsupported.
  * The cross-process lock covers one machine.

## E. Tests

**Commands.**

* Full suite (environment: Linux sandbox, Python 3.11.2, SQLite 3.40.1, no
  `libGL.so.1`):

  ```
  QT_QPA_PLATFORM=offscreen python -m pytest -p no:cacheprovider --tb=no -rfE --continue-on-collection-errors
  ```
* The `--continue-on-collection-errors` flag is required, because one test
  module fails to collect without `libGL`.

**Baseline vs final.**

| | Tree | Passed | Failed | Skipped | Errors | Time |
|---|---|---|---|---|---|---|
| Baseline | `1fe80df` | 2491 | 63 | 45 | 18 | 426.60 s |
| Final | `90016027` | 2529 | 64 | 45 | 18 | 468.88 s |

* **Classification.** 0 regressions, 0 newly fixed, and 82 environment-only
  failures:
  * the 81 baseline non-passing ids are unchanged;
  * the +1 failure is the new UI test, whose subprocess cannot load Qt
    widgets.
* **Evidence for the environment classification.**
  * Every one of the 81 baseline ids was rerun with `--tb=short`, and every
    traceback is `ImportError: libGL.so.1`, either directly, at collection,
    or in subprocess output.
  * As supplementary evidence, a local stub for the missing GL, EGL, D-Bus
    and xkbcommon libraries was built. It is outside the repository and only
    lets Qt load offscreen.
  * With the stub, all non-passing ids pass on both trees: 173 tests at
    baseline, 174 at final (the extra one is the UI test).
* **Pass count.** +38 = 17 backup + 21 restore tests. The UI test passes
  where Qt loads (locally with the stub; in Source CI).

**New tests (39).**

| Module | Tests | Covers |
|---|---|---|
| `tests/test_db_backup_service.py` | 17 | valid snapshot, rows and relations, integrity and FK, manifest, permission, collision, failed or partial never promoted, corruption before promotion, corrupt file unlisted, retention order, unrelated files kept, failed latest attempt keeps the only copy, locked file during retention, settings validation, concurrent calls, cross-process lock (POSIX and Windows), scheduler no-overlap and clean stop, shutdown, audit-failure policy, `backup_to`/`auto_backup` |
| `tests/test_db_restore_service.py` | 21 | authorized restore (data, relations, FK, WAL back on, audit row, journal, safety copy contents, source unchanged, app usable), v5 migrated on a staged copy, unauthorized / no principal / unconfirmed, corrupt digest, forged content with a matching manifest, future schema, foreign schema, outside path / traversal / missing / live path / symlink, injected failures at stage, maintenance, safety_copy, exclusive and replace, safety-copy failure blocks, `os.replace` failure, post-replacement failure recovers, failed recovery keeps the safety copy, open transaction blocks, access during maintenance refused, another open connection blocks, concurrent restore refused and audited, journal start failure aborts, outcome journal/audit failures reported |
| `tests/test_db_maintenance_ui.py` | 1 (subprocess) | dialog gating (newer schema not selectable, checkbox required, older-schema note), window frozen, autosave paused, close refused, backup, refused restore keeps data, successful restore closes the app, viewer denied |

**Mutation checks.** Each injected defect was caught, and each original was
restored byte-identically (`cmp`).

| Area | Defect injected |
|---|---|
| Backup | Verification removed from backup creation |
| Restore | Failed safety copy ignored |
| Restore | Recovery removed |
| Restore | Exclusivity check disabled. The replacement then went ahead on Linux while another connection was open, so this check is the real guard. |
| Restore | Candidate validation skipped |
| UI | Window not frozen |
| UI | Autosave not paused |
| UI | No forced restart after a successful restore |

**Windows.**

* Run 39383249495 on `9001602` passed. Its regression step lists the
  backup, restore and UI modules and fails the job on any failure. Per-test
  results were not readable from this sandbox (logs and artifact storage are
  unreachable).
* The symlink case may return early on Windows when the runner lacks symlink privilege.
* Linux rename semantics do not prove Windows behaviour. The owner checklist
  is in `docs/DATABASE_OPERATIONS.md`.

**Other gates on the final tree.**

| Gate | Result |
|---|---|
| ruff debt (`core dialogs tabs tests`) | 5342, ceiling 5375 (unchanged) |
| E722/F821 | 0 |
| New modules | ruff clean |
| `main_window.py` ruff findings | 162 → 83 (explicit Qt imports; outside the debt scope) |
| Exception scan | passes: 1031 handlers / 629 broad / 192 unexplained silent (ceiling 192); no new silent handler |
| Privacy check | 974 files, 0 findings |
| Migration, connection, authorization and schema-index suites | included in the full run, no new failures |
| Coverage | not measured this phase |

**Money audit.** `tools/money/money_audit.py` was run on a temporary
synthetic database (one cost row 2.675 / 2.665) and exited 0.

* The SHA-256 of the main database file was identical before and after.
* SQLite created its normal `-wal` (0 bytes) and `-shm` (32 KiB) sidecar
  files when opening the WAL database read-only. The database content was
  not modified.

## F. Performance and operations

* **Schema** v6 = v5 + 95 additive secondary indexes on 48 tables. This
  phase adds no schema change.
* **Migration paths.** The v1 to v5 upgrades are covered by
  `tests/test_database_migration_acceptance.py`. The v5 to v6 upgrade is
  covered there and also through restore of a v5 backup on a staged copy.
  Restore rejects newer schemas.
* **Index evidence** (from `docs/DATABASE_PERFORMANCE.md`: seed 4300, 500
  reports, Python 3.11.2, SQLite 3.40.1, real `EXPLAIN QUERY PLAN`):
  * full-scan statements fell from 91 to 1;
  * statements with `USE TEMP B-TREE` fell from 9 to 4;
  * index storage is 831,488 bytes (about a third of the indexed database).
  * Medians, v5 → v6:

    | Operation | v5 (ms) | v6 (ms) |
    |---|---|---|
    | full snapshot | 6.285 | 5.263 |
    | time logs | 0.622 | 0.346 |
    | hierarchy | 18.955 | 15.964 |

  * No general speed-up percentage is claimed.
* **Backup and restore cost.** Not benchmarked. Backup time scales with
  database size. Free space needed for a restore:
  * on the database volume, one database size for the staged copy, plus one
    more only when recovery runs (the recovery stage);
  * on the backup volume, one database size for the safety copy.
* **WAL limits** (unchanged). There is one writer at a time. A WAL database
  is three files, so a plain file copy of a live database is unsafe; use the
  backup function. The busy timeout defaults to 30 s. Network shares are
  unsupported.

## G. Money status

* Unchanged:
  * no diff in `core/money.py` or `tools/money/` since `1fe80df`;
  * no column type changes in `core/database.py`;
  * `money_audit` stays read-only (E).
* `core/money.py` is still used only by `summarize_costs`. 2.675 display
  rounding is preserved (HALF_UP 2.675 → 2.68).
* Persisted monetary Float values are not migrated. D1–D7 remain owner
  decisions (H).

## H. Owner actions (open)

1. **Licence:** choose a binding licence.
2. **Monetary migration D1–D7:**
   * D1: whether to migrate at all;
   * D2: currencies and scales;
   * D3: display rounding;
   * D4: unknown currency;
   * D5: NPT currency;
   * D6: rounding rule and inexact rows;
   * D7: dropping the REAL columns.

   Only documentation and a read-only audit exist.
3. **Windows acceptance:** run the restore checklist in
   `docs/DATABASE_OPERATIONS.md` on a copy of real data, including the
   two-instance refusal and undoing a restore with the pre-restore copy.
   Field and production acceptance are not claimed.
4. **Deployment:**
   * decide the backup location (ideally a second disk), retention count and
     interval;
   * arrange off-machine copies;
   * grant `can_maintain_database` only to administrators;
   * periodically remove old pre-restore copies by hand.
5. **Signing:** installers remain `UNSIGNED`. No release tag was created.
6. **Follow-up decision:** wire or remove the legacy Settings-dialog backup
   options (C).

## I. Resume instructions

* Branch `arena/72010272-drill-master`. Code-complete SHA
  `90016027b065dc32a8889b7a28a4bf154a3bceaa`; this report is the next commit.
  Check `git ls-remote origin refs/heads/arena/72010272-drill-master` before
  continuing. If the checkout shows an older HEAD, fetch and fast-forward
  without resetting.
* Environment:

  ```
  python3 -m venv .venv
  .venv/bin/pip install -r requirements-lock.txt pytest==9.1.1 ruff==0.16.6 build==1.6.1 pyyaml pytest-cov hypothesis
  ```
* Focused gate:

  ```
  python -m pytest tests/test_db_backup_service.py tests/test_db_restore_service.py tests/test_db_maintenance_ui.py
  ```

  Then run the full suite with the command in E.
* Remaining M43 work outside this phase: priorities 6–10 and the final
  release-hardening report. Owner-gated items are in H.

## J. Addendum — 2026-10-20 (release hardening): CI reconciliation and corrections

Appended; nothing above was changed. Run and job IDs were re-read from the
GitHub REST API (`actions/runs?head_sha=<full sha>`, `/jobs`) on 2026-10-20.

| SHA | Nature | Source release gate | Windows release validation |
|---|---|---|---|
| `90016027b065dc32a8889b7a28a4bf154a3bceaa` | **code-complete** (evidence for this phase) | 39383249614 success, attempt 1 — jobs 3.11 `118496980925`, 3.12 `118496981140`, 3.13 `118496981255` | 39383249495 success, attempt 1 — job `118496980737` |
| `9060b08a9a31d0bf26c186365b08e757aa9b63a3` | documentation-only (this report) | 39384716176 success, attempt 1 — jobs 3.13 `118501705961`, 3.12 `118501706266`, 3.11 `118501706310` | 39384716078 success, attempt 1 — job `118501705771` |

* The green runs on `9060b08` prove that the report commit did not break the
  gates; they are **not** additional evidence for the code, which stays tied to
  `90016027`. The cancelled runs on `0c73d7e`/`485647e` remain excluded.
* Windows *manual* acceptance (the owner checklist, now 12 items in
  `docs/DATABASE_OPERATIONS.md`) has **not** been performed; the Windows CI
  job builds and tests an UNSIGNED installer and is not acceptance.

**Corrections found by the release-hardening re-audit** (fixed in commit
`28d7920`, on top of `9060b08`):

1. *Settings > Database > Backup Database Now* called
   `DatabaseManager.backup_to()` directly: any logged-in role could copy the
   whole database file to any path, with no `can_maintain_database` check, no
   manifest and no audit entry. Section C's permission statement was accurate
   for *Tools > Backup Database Now* only. The button now runs the verified
   service; an unused `MainWindow.backup_database` with the same defect was
   removed; a test forbids application modules from calling `backup_to()`.
2. The Settings dialog's backup checkbox and folder were saved but never read;
   the scheduler used environment variables only, and the dialog showed
   backups as off while they ran every 30 minutes. One resolver now feeds the
   scheduler and the service (environment > saved setting > default); see
   `docs/DATABASE_OPERATIONS.md` § Configuration.

## Addendum — M43 continuation (2026-10-21)

Defects found and fixed after this report was written (each has a test that
fails on the previous code):

3. **Restore could be overwritten by autosave** (`ec12eb2`). After a
   successful restore, `_on_maintenance_finished` resumed every autosave before
   the result message (modal) was shown; a timer firing while it was open — or
   after a restore whose rollback failed — would write the screens' stale
   contents into the restored or unrecovered database. Autosave now stays off
   until restart once the live database has been replaced
   (`MainWindow._keep_autosave_paused`, `_restart_required`);
   `tests/test_db_maintenance_ui.py` checks the timer while the message is open
   (it previously asserted that autosave resumed).
4. **Hierarchy deletes could lose their audit record** (`42ab17f`).
   `core/hierarchy_operations.delete_entity` (company/project/section) committed
   the delete and then wrote the audit entry in a separate call wrapped in
   `except Exception: pass`. The `AuditLog` row is now added in the same
   transaction, so an audit failure rolls the delete back
   (`tests/test_silent_handler_contracts.py`).
5. **Lookahead import** (`42ab17f`): non-numeric hours were silently dropped and
   `inf` aborted the whole atomic import with `OverflowError`; the raw value is
   now kept in remarks.

Remaining gaps (not fixed, recorded for the owner): well and daily-report
deletes (`db.delete_well`, `delete_daily_report`) write no audit record;
`DatabaseManager.log_audit` itself catches and only logs failures (used by
`app.py` and a few `database.py` paths). `money_audit.py` leaves the database
byte-identical but SQLite creates `-wal`/`-shm` side files
(`docs/MONEY_MIGRATION.md`). Schema version unchanged (6); no migration.

## Addendum — M43 final technical closure (2026-10-21)

Supersedes the "Remaining gaps" paragraph of the previous addendum where
noted. Full context: `M43_RELEASE_HARDENING_REPORT.md`, Part 3.

1. **Audit atomicity (`047bf90`, `98e0358`).**
   - `DatabaseManager.delete_hierarchy_entity` (company/project/well/section)
     and `delete_daily_report` write a mandatory `AuditLog` row in the same
     transaction; an audit failure rolls the delete back. `delete_well`
     previously wrote no audit record at all.
   - `save_well` and `save_daily_report` (owned session) audit inside the
     transaction.
   - If the session user has no row in the open database (restore, database
     switch), the record keeps `user_id NULL` plus the username instead of
     failing the save.
   - `log_audit` stays best-effort: it returns a bool and logs the exception
     type only.
   - Evidence: `tests/test_audited_mutations.py` (23 tests, 4 mutants).
2. **Second extraction (`b56b4a5`).** The computation behind
   `get_actual_vs_plan` moved unchanged to
   `core.actual_vs_plan.summarize_actual_vs_plan`. The method keeps its queries
   and session, and its result shape is unchanged. `core/database.py`: 10,547 →
   10,471 lines. The models stay in `core/database.py`
   (`tests/test_model_registry.py`).
3. **Worker database access (`6ffb4f6`).** The Export Center worker never uses
   the application's shared `StaticPool` connection. `core.export_jobs.worker_database`
   opens a separate `mode=ro` connection per checkout (`NullPool`, configured
   by `sqlite_connection.connect(read_only=True)`):
   - registered with the restore `MaintenanceGate`, so restore drains and
     refuses it;
   - carries the same authorization state into the session info.

   Tests prove it is read-only, gated, and produces byte-equal reports
   (timestamps masked). Writes from worker threads remain unsupported; an
   import worker needs a dedicated writable connection (not started).
4. **Read model:** `get_daily_reports_by_well` now also returns
   `report_number` (additive; no schema change). Its absence had made batch
   DDR file names collide.
5. **Operations:** `reset_database.py` refuses arguments before reading the
   configuration; `--help` prints usage and never reaches the prompt
   (`c039f6b`).
6. **Unchanged:**
   - schema version 6, no migration;
   - money still `Float` (P5); `money_audit.py` byte-identical with `-wal`/`-shm`
     side files;
   - restore and backup behaviour unchanged since the continuation.
