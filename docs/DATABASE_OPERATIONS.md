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
* The database must be on a local file system. Network file systems commonly
  break SQLite locking and WAL.

## Diagnostics

`sqlite_connection.effective_settings(connection)` returns the read-back
values of `foreign_keys`, `busy_timeout`, `journal_mode` and `synchronous` for
a raw connection. The reliability tests use it to verify the settings on new,
reconnected and pooled connections.

## Performance

See [DATABASE_PERFORMANCE.md](DATABASE_PERFORMANCE.md) for the schema v6
index evidence (plans, timings, sizes).
