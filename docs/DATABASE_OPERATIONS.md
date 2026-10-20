# Database operations

How DrillMaster opens and configures its SQLite database, and what that
means for operators. Source of truth: `core/sqlite_connection.py` and
`DatabaseManager.initialize` in `core/database.py`. Tests:
`tests/test_sqlite_connection_reliability.py`.

## Connection settings

Every connection the application opens, including the engine's connection and
direct `sqlite3` connections for maintenance, goes through
`sqlite_connection.configure`. The settings are re-applied whenever a new
DB-API connection is created (for example after `engine.dispose()`) and read
back to verify them.

| Setting | Value | Why |
|---|---|---|
| `foreign_keys` | `ON`, verified | Referential integrity and `ON DELETE CASCADE`. A connection that does not report `foreign_keys=1` after configuration is refused with `ConnectionConfigurationError` (fail closed). |
| `busy_timeout` | `DRILLMASTER_DB_BUSY_TIMEOUT_MS`, default `30000` | How long a connection waits for another connection's lock before failing. |
| `journal_mode` | `WAL` (persistent, database-level) | Readers do not block the writer, and the writer does not block readers. |
| `synchronous` | `NORMAL` | See durability below. |
| `cache_size` | 10000 pages | Page cache per connection. |

### `DRILLMASTER_DB_BUSY_TIMEOUT_MS`

* Integer milliseconds in the range `100` to `600000`. Unset or empty means
  the default of `30000`, the previous behaviour.
* An invalid or out-of-range value is ignored with a logged warning, and the
  default is used. The application never runs with an unvalidated timeout.

### WAL: what it does and does not do

* WAL lets readers continue while **one** writer commits. It does **not**
  allow two concurrent writers.
* A second writer waits up to the busy timeout and then fails with
  `database is locked`. Long write transactions in one process or tool can
  therefore make another writer fail after the timeout. Keep maintenance
  writes short, and do not run external tools that write to the live database.
* The mode is read first and changed only when it differs. Switching to WAL
  needs exclusive access. If that is not possible (another process holds the
  database, or the file system does not support WAL, as with some network
  shares), the connection keeps its current mode and logs a warning. It is
  never reported as WAL.
* Read-only connections (`connect(path, read_only=True)`, opened with
  `mode=ro`) never change the journal mode.
* A WAL database consists of up to three files: `<name>.db`, `<name>.db-wal`
  and `<name>.db-shm`. Copying only the `.db` file while the application is
  running can produce an incomplete copy. Use the application's backup
  function (SQLite backup API), never a plain file copy of a live database.
* The size of the main `.db` file alone is not a measure of the database
  size under WAL.

### Durability (`synchronous=NORMAL`)

With WAL and `synchronous=NORMAL`, committed transactions survive an
application crash. The most recent commits can be lost on a power failure or
operating-system crash, but the database remains consistent (not corrupt).
`FULL` would close that window at the cost of an fsync on every commit. This
is a deliberate trade-off. Regular verified backups are the protection against
loss.

## Known limitations

* **One shared connection per process.** The engine uses SQLAlchemy's
  `StaticPool` with `check_same_thread=False`: all sessions of a
  `DatabaseManager`, including the `HierarchyWorker` background thread in
  `main_window.py`, share one DB-API connection. Work on that connection is
  serialised, not parallel. Concurrent access from several threads relies on
  sessions not overlapping their use of the connection. Replacing the pool
  (per-thread connections) would be a separate, tested change.
* **Several application instances** on the same database file are
  coordinated only by SQLite locking (busy timeout, then
  `database is locked`). There is no application-level single-instance lock.
  (M43: backups and restores additionally take an OS file lock, see
  "Backups" below; ordinary reads and writes are still coordinated only by
  SQLite.)
* The database must be on a local file system. Network file systems commonly
  break SQLite locking and WAL.

## Backups

Source of truth: `BackupService` and `BackupScheduler` in
`core/db_maintenance.py`. Tests: `tests/test_db_backup_service.py`.

### Configuration (one source of truth)

Resolved once at start-up by `resolve_backup_settings()` in
`core/db_maintenance.py` and used by both the scheduler and *Backup Database
Now*. Tests: `tests/test_backup_settings.py`, `tests/test_backup_settings_ui.py`.

| Setting | Environment variable (wins; shown locked in Settings) | Saved user setting (*Settings > Auto-Save*) | Default | Valid values |
|---|---|---|---|---|
| Automatic backups on/off | `DRILLMASTER_BACKUP_INTERVAL_MINUTES=0` forces off | `database_backup/enabled` | on | yes/no |
| Folder | `DRILLMASTER_BACKUP_DIR` | `database_backup/directory` | `<data dir>/backups` | absolute local path |
| Interval | `DRILLMASTER_BACKUP_INTERVAL_MINUTES` | `database_backup/interval_minutes` | 30 | 5–1440 minutes |
| Backups to keep | `DRILLMASTER_BACKUP_KEEP` | `database_backup/keep` | 10 | 1–1000 |

* **Precedence:** environment variable > saved setting > default, per field.
  An environment variable is a deployment/administrator override; the dialog
  shows that field disabled with the variable's name and does not save it.
* **Invalid values are never applied.** An invalid saved value is ignored and
  reported (log warning and a note in the dialog) and the default is used;
  an invalid environment value falls back the same way. The dialog refuses to
  save an invalid folder and then saves nothing at all.
* **Folder validation:** must be an absolute path; must not be the live
  database file; must not point at or go through a file; network locations are
  rejected (`\\server\share`, `//server/share`, `\\?\UNC\…`, and a mapped
  drive when Windows resolves it to a UNC path). Other remote mounts (for
  example a cloud-sync folder or an NFS mount) cannot be detected and are
  **unsupported**: locking, `fsync` and rename guarantees are not given there.
  A second **local** disk is supported and recommended; a backup on the same
  disk does not survive a disk failure.
* **When changes apply:** at the next start of DrillMaster (deterministic: the
  running scheduler is not reconfigured). Changing a setting never moves,
  copies or deletes existing backups. Backups left in a previous folder stay
  there and are not listed for restore; move them into the current folder
  (with their `.json` manifests) to restore one.
* **Legacy keys:** before M43 the dialog saved `backup/enabled` and
  `backup/path`, which nothing ever read, and showed backups as "off" while the
  scheduler ran every 30 minutes. Those keys are ignored on purpose: a saved
  "off" there was never a real choice and must not switch backups off.

**How a backup is made.**

1. Exclusive maintenance lock: an in-process lock plus an OS lock on
   `<backup dir>/.drillmaster-maintenance.lock` (`fcntl.flock` on POSIX,
   `msvcrt.locking` on Windows). Only one backup or restore runs at a time,
   also across application instances on the same machine. The OS releases
   the lock when a process exits or is killed, so a crash cannot leave a
   permanent lock (tested on POSIX and in the Windows gate).
2. SQLite online backup API from a read-only connection into a
   `.drillmaster-backup-*.partial` file in the backup directory. This is a
   consistent snapshot that includes committed WAL content.
3. The copy is switched to `journal_mode=DELETE` (one self-contained file)
   and verified: `integrity_check`, `foreign_key_check`, required application
   tables and a schema version not newer than the application supports.
4. Only then is it renamed to
   `drillmaster_backup_<UTC yyyymmddThhmmssffffffZ>_<8 hex>.db`. The name is
   claimed with exclusive creation, so an existing file is never overwritten.
   A manifest `<same name>.json` is written next to it.
5. Any failure removes the partial file, and the result carries the error.
   Nothing unverified is ever promoted.

**Manifest.** It contains the format, kind, file name, schema version, UTC
time, size, SHA-256 and application version, and nothing from the database
(no names, rows or credentials). A backup counts as *verified* only when its
manifest matches the file name, kind and size. Listing for retention and
restore also checks the SHA-256.

**Retention.** "Backups to keep" (see the table above).
Retention is count-based only; age-based retention is not implemented (it
would need a trustworthy clock and a minimum-copies rule). It runs only
after a new backup was verified, and only over manifest-verified managed
backups, newest first. It never touches:

* the live database;
* partial or unverified files;
* files that do not follow the naming scheme;
* pre-restore safety copies;
* the newest verified backup.

A file that cannot be deleted (for example locked by antivirus on Windows) is
skipped and reported in `retention_errors`. Lowering the number to keep deletes
nothing when the setting is changed; the surplus is removed after the **next**
successful backup, in the current folder only (tested).

**Schedule.** Interval and on/off from the table above. The scheduler is one
background thread, not a GUI timer, and
runs never overlap. A failed run is logged and retried at the next interval.
The scheduler does nothing destructive at startup.

On window close, the service first refuses new backups, then the scheduler
waits up to 120 s for a running backup. This can briefly delay closing.

**Permission and audit.**

* Interactive backups (*Tools > Backup Database Now*, and the same button in
  *Settings > Database*) require `can_maintain_database`, which only admins
  hold by default. The check is enforced in the service; denials are written
  to the audit log. (Until the M43 release hardening the Settings button
  copied the database file to any chosen path with no permission check, no
  manifest and no audit entry; it now runs the verified service.)
* Scheduled backups are recorded as `system:backup-scheduler`, not as a user.
* Outcomes are written to `audit_logs` on a separate short-lived connection.
* **Audit-failure policy:** if the audit row cannot be written, the verified
  backup is kept. The result says `ok=True, audit_recorded=False`, and the
  error is logged. A backup is not discarded because its audit row failed.

`DatabaseManager.backup_to()` and `auto_backup()` keep their previous
contracts. `backup_to()` verifies its copy before replacing the destination,
and `auto_backup()` delegates to the service. `backup_to()` is a low-level
primitive **without** a permission check or audit entry: no application module
may call it (enforced by
`test_no_application_module_copies_the_database_around_the_verified_service`).

## Restore

Source of truth: `RestoreService` in `core/db_maintenance.py`. Tests:
`tests/test_db_restore_service.py` (service) and
`tests/test_db_maintenance_ui.py` (UI).

**Who and what.**

* `can_maintain_database` is enforced in the service and denials are
  audited. An explicit `confirmed=True` is also required.
* Only **managed** files can be restored: a `drillmaster_backup_*` or
  `drillmaster_prerestore_*` file directly inside the backup directory, with
  a matching manifest and digest.
* Rejected:
  * files elsewhere;
  * symbolic links;
  * `..` traversal;
  * the live database itself;
  * files larger than 8 GiB;
  * non-DrillMaster SQLite files;
  * corrupt or incomplete files.
* To restore an external file, an operator must first place it in the backup
  directory together with a valid manifest. This is deliberate: the
  application does not accept arbitrary files as a database.

**Schema policy.**

* A backup with a schema **newer** than the application is rejected.
* An **older** one (1 to current) is copied, and the copy is upgraded with
  the application's normal migrations (`DatabaseManager.initialize`, the same
  code as an in-place upgrade at startup) and verified again. The backup file
  and the live database are never migrated in place.
* Coverage:
  * the v5 to v6 path is tested through restore;
  * the v1 to v5 upgrade paths are tested by
    `tests/test_database_migration_acceptance.py`.

**Sequence.** Each step must succeed before the next one runs:

1. Validate the candidate through a read-only connection. A failure here
   changes nothing.
2. Stage a verified copy (`.drillmaster-restore-*.staged`) beside the live
   database, on the same file system.
3. Journal `restore_started`. If this cannot be written, the restore aborts.
4. Maintenance state:
   * new database sessions are refused with `MaintenanceActive`;
   * open transactions are given 15 s to finish, otherwise the restore aborts;
   * the connection pool is disposed.
5. Pre-restore safety copy: a normal verified backup of the current database
   (`drillmaster_prerestore_*`). If it fails, the restore aborts.
6. Exclusivity check: WAL checkpoint, then `journal_mode=DELETE`. SQLite only
   allows this when no other connection has the file open. If another
   process or instance has the database open, the restore aborts.
7. `os.replace(staged, live)`: one rename on the same file system.
8. The application reopens the database through its own engine and verifies
   it (integrity, foreign keys, schema version, usable tables).

**Failure behaviour (all fault-injection tested).**

* Steps 1 to 7: the live database is unchanged (`original_intact=True`). The
  staged file is removed, and the safety copy, if made, is kept.
* Step 8: the safety copy is put back the same way (stage, rename, verify),
  giving `recovered=True` and the original data live again.
* If even that fails (`recovered=False`): the verified safety copy is kept,
  the outcome is logged as critical and journalled, and the UI tells the user
  to stop and contact an administrator.

**Retention of safety copies.** Pre-restore copies are never deleted
automatically and are excluded from retention. They appear in the restore
dialog, so a restore can be undone. Remove old ones manually when they are no
longer needed.

**Audit continuity.** The `audit_logs` table belongs to the database, so a
restore brings back the snapshot's audit history, and entries written after
the backup are no longer in the live table. Their record survives in two
places:

* the sidecar journal `<backup dir>/maintenance_journal.jsonl`
  (`restore_started` before any change; `restore_succeeded`,
  `restore_failed`, `restore_recovered` or `restore_recovery_failed` after);
* the pre-restore safety copy, which contains the full previous audit table.

The outcome is also written to the restored database's `audit_logs`.

* **Failure policy:** a failure to write the start event aborts the restore.
  A failure to write the outcome event or the audit row never changes the
  outcome. It is reported as `journal_complete=False` or
  `audit_recorded=False` and logged.
* **Limits:** the journal is a plain append-only text file. Anyone with
  write access to the backup directory can alter or delete it. It is
  evidence, **not** tamper-proof, and neither is the database audit table.

**Application state.** Restore runs on a worker thread. During it:

* the window is disabled;
* every autosave is paused;
* the hierarchy worker is stopped;
* closing the window is refused.

After a successful restore DrillMaster closes, so that no open screen keeps
showing or auto-saving pre-restore data, and must be started again. Unsaved
edits in open screens are lost; the dialog says so. After a failed restore
the window is usable again, and the message states whether the database was
unchanged or recovered.

**Limits.**

* **Windows:** `os.replace` fails while any process (another instance, a
  backup agent, antivirus, an indexer) holds the live file open. The restore
  then fails at step 6 or 7, with the original unchanged. This is simulated
  in tests (`PermissionError` from `os.replace`); the service tests also run
  in the Windows release gate. Interactive acceptance on real Windows
  machines is an owner action (see below).
* The cross-process lock and the exclusivity check cover processes on the
  **same machine** using a local file system. Network shares are not
  supported.
* The rename is atomic on POSIX file systems and uses `MoveFileEx` with
  replace on Windows. Power loss during step 7 or 8 is not simulated; the
  verified safety copy is the recovery path in that case.

### Residual risks (documented, not solved)

* **Power loss** during a backup, a restore replace or a recovery is not
  simulated by any test. Backups are promoted only after verification and the
  restore keeps a verified safety copy, which is the recovery path; a torn
  write of the live file itself is not tested.
* **Not tamper-proof:** the manifest SHA-256 detects accidental corruption, not
  a deliberate edit (anyone who can write the folder can rewrite file and
  manifest together); the journal and the audit table are evidence only.
* **Same machine only:** the cross-process lock does not protect against a
  second machine opening the database over a network share (unsupported).

**Owner checklist for Windows acceptance (manual, on a test machine, with a
copy of real data — never the production folder).** Record date, Windows
version, installer SHA-256 and the result of each item; none of these has been
performed by the project so far.

1. **Install** the UNSIGNED installer from the Windows gate artifact; note the
   install folder and that no admin-only path is required for the data folder.
2. **SmartScreen:** record the exact warning shown for the unsigned installer
   and the steps needed to proceed (expected until signing is set up).
3. **Launch** and log in as an admin; confirm the data folder location.
4. **Backup settings:** open *Settings > Auto-Save*; confirm the shown values
   (on, `<data dir>\backups`, 30, 10). Choose a folder on a second local disk,
   save, restart, and confirm the next backup lands there. Try a network path
   (`\\server\share`) and confirm it is refused with a message.
5. **Manual backup:** *Tools > Backup Database Now*; a
   `drillmaster_backup_*.db` and matching `.json` appear in the chosen folder.
   Log in as a viewer and confirm the action (and the Settings button) is
   disabled.
6. **Synthetic restore:** make a visible change, restore the backup from
   step 5, confirm DrillMaster closes, restart, and confirm the change is gone.
7. **Second instance:** with a second DrillMaster open on the same database,
   try the restore again; it must refuse and leave the data unchanged.
8. **Corrupt backup:** change a few bytes inside a backup (same size, keep its
   manifest). The restore list may still show it (the list compares name, kind
   and size only, for speed); selecting it must be refused before anything
   changes ("manifest … does not match", SHA-256 re-checked) and the data must
   be unchanged. A changed size makes it disappear from the list.
9. **Close after restore:** confirm no screen keeps or auto-saves pre-restore
   data after the restart; restore the `drillmaster_prerestore_*` safety copy
   and confirm the change is back.
10. **Audit:** review `maintenance_journal.jsonl` and the audit log entries for
    steps 5–9 (user names, scheduler identity, outcomes).
11. **Uninstall:** uninstall and record which folders remain (the data and
    backup folders are expected to remain; confirm and document it).
12. **Languages and daily work:** switch Persian/English (RTL layout), enter a
    daily report and a survey station, save, restart and confirm both persist.

## Diagnostics

`sqlite_connection.effective_settings(connection)` returns the read-back
values of `foreign_keys`, `busy_timeout`, `journal_mode` and `synchronous` for
a raw connection. The reliability tests use it to verify the settings on new,
reconnected and pooled connections.

## Performance

See [DATABASE_PERFORMANCE.md](DATABASE_PERFORMANCE.md) for the schema v6
index evidence (plans, timings, sizes).
