# M47 — SQLite connection isolation, transaction safety and search contract closure

Repository `asgareyvazi/Drill-master`, branch `arena/72010272-drill-master`.
Start `46a6948af94836886f3733e93266922e06cc59b8` (M46 report tip). Code tip
`aaaebc855ccf3f387aa4a9bc84960fbc054244e2`. The report commit is the one that
adds this file. Status: **UNSIGNED**. This is not a release, acceptance or
approval document. Every number below comes from a command run during M47
unless it is marked "copied".

## A. Verdict

| # | Item | Status | Evidence (section) |
|---|---|---|---|
| 1 | File sessions never share a DB-API connection | **PASS** | C, D, H |
| 2 | Call-site audit and classification | **PASS** | E |
| 3 | Per-connection settings, pool sizing, diagnostics | **PASS** | C, H |
| 4 | Authorization: identity, read-only workers, denial without write, audit actor | **PASS** | E, H |
| 5 | Maintenance gate, restore drain, multi-instance fail-safe | **PASS** | F, H |
| 6 | File-backed isolation, H1, writers, maintenance, in-memory, leak and order tests | **PASS** | G, H, I |
| 7 | Workers: own connection, plain data, cancellation | **PASS** | E |
| 8 | P3-A group-aware highlight spans | **PASS** | J |
| 9 | P3-B U+1E9B / FTS5 fold alignment (normalisation v3) | **PASS** | J |
| 10 | P3-C link notes: one stored form, note-only change rules | **PASS** | J |
| 11 | Broader audit (init/migration, hooks, import/export, ownership, shutdown, restart, managers) | **PASS** with limitations | E, N |
| 12 | `docs/DATABASE_OPERATIONS.md` | **PASS** | K |
| 13 | CI on the exact code and report SHAs | code tip: **PASS** (both gates); report tip: see L | L |
| 14 | Synthetic end-to-end (persistence, documents, maintenance) | **PASS** (12/12); screenshots **NOT RUN** | I |
| 15 | Delivery (commits, pushes, report, README row, clean tree) | **PASS** | M |

Root cause in one sentence: until M47 a file database used SQLAlchemy's
`StaticPool`, so **every session of a `DatabaseManager` shared one DB-API
connection and therefore one SQLite transaction**. One session's rollback or
close discarded another session's uncommitted writes without an error, and a
reader saw another session's uncommitted rows. M46 had removed the one
background reader that triggered it (H1) but not the shared connection.

## B. SHAs

| What | SHA |
|---|---|
| Start (M46 report tip) | `46a6948af94836886f3733e93266922e06cc59b8` |
| `fix(db)` pool, gate, in-memory policy | `561c6628a7ec46cc7814f18b191a3466e56c6bcb` |
| `fix(search)` spans, fold order, v3 | `64f4d76bb6d4c6d0bed3a821f36c226020901c1c` |
| `fix(links)` note policy | `9a6242958a47c5fdf0f24c2a9f235551339d1548` |
| `test(m47)` modules, mutation and workflow tools | `f8da37c8adc4b685d44e6b0544a3c6556c1863c7` |
| `docs(db)+ci` guide and Windows gate | `b68b141d21744f5da4a1d74a3d24c678a3dc6ccf` |
| **Code tip** `test(m47)` read-only hierarchy worker probe (section M) | **`aaaebc855ccf3f387aa4a9bc84960fbc054244e2`** |
| Report tip | the commit that adds this file (see L) |
| `drill-Master` (not touched) | `e3fa42a3257e981d9bdf9d012c97919e3352a53a` |

## C. Architecture before and after

| Aspect | Before (M46) | After (M47) |
|---|---|---|
| File engine | `StaticPool`, `check_same_thread=False`: one DB-API connection for all sessions and threads | `QueuePool` with a `creator`: each session checks out its own connection for its transaction |
| Settings | `connect` event ran `configure` on the shared connection | The creator calls `sqlite_connection.connect` (apply and verify, fail closed); a `checkout` listener discards a connection without `foreign_keys=1` |
| Pool sizing | n/a | `DRILLMASTER_DB_POOL_SIZE` 5 (1..32), overflow = size, `DRILLMASTER_DB_POOL_TIMEOUT_S` 30 (1..600); invalid values fall back with a warning |
| In-memory engine | `StaticPool` (same) | `StaticPool` kept; `shares_single_connection` detects it; worker threads refused; hierarchy and export run on the calling thread |
| Maintenance gate | One integer `active`, `max(0, n-1)` on every checkin, reset and reopened by every `initialize` | Per-connection-record checkout counts, plus a `connecting` count around the creator; refused checkouts are never counted; never reset; second `close` refused |
| Worker readers | `worker_database`: own `mode=ro` connection; gate counted checkouts only | Same, and the creator itself is gated (no connection is opened during a restore) |
| Diagnostics | `effective_settings` | plus `DatabaseManager.connection_diagnostics()` (pool counts, gate snapshot; no SQL, no data) |

**Pool choice.** `QueuePool` is SQLAlchemy's standard bounded pool, so no new
dependency is needed. `NullPool` would open a new connection, and re-run the
WAL and settings round-trip, for every session. A thread-local design
(`SingletonThreadPool`, `scoped_session`) would tie a transaction to a thread
instead of to the code that owns the session, and the brief forbids it unless
proven necessary. It was not necessary: the session owner is always one
`session_scope` block or one explicitly closed `create_session()`.

**SQLite single writer.** Isolation does not remove SQLite's rule of one
writer at a time. While session A holds a flushed write, session B's write
waits `busy_timeout` and then fails with `database is locked`. B's statement
never reaches constraint checks, so nothing of it is stored. This is tested
across two managers, and `save_well` returns `False` instead of a false
success.

## D. Root causes found (old code)

| ID | Defect | Old-code evidence |
|---|---|---|
| P1 | File engine shared one connection, so rollback, close or failed flush of one session reached another's transaction; dirty reads | StaticPool mutant on the M47 tree: 14 test bodies fail, e.g. `test_rollback_in_one_session_does_not_touch_another` (persisted `[]` instead of `['SYN-M47-KEEP']`), `test_h1_reader_thread_on_the_manager_during_a_pending_write` (dirty read, `1 == 0`) (section H) |
| G1 | A refused worker checkout's checkin lowered the shared count while another session still held its connection, so a restore could proceed with an active writer | probe on `46a6948` (`/home/user/m47_gate_probe_old.txt`, not in the repository); mutant `G-unmatched-checkin` killed |
| G2 | A refused main checkout invalidated the shared connection and so closed the UI thread's in-flight transaction | same probe; covered by `test_a_refused_checkout_never_lowers_the_drain_count` |
| G3 | `install_gate` reopened and reset the gate on every `initialize`, even during a restore | mutant `G-install-reset` killed |
| G4 | A refused connection was still opened and configured (WAL switch on the file being replaced) | mutant `G-connect-guard` killed (no `sqlite_connection.connect` call allowed while closed) |
| G5 | A connection left with `foreign_keys=OFF` by a migration could return to the pool | mutant `P-fk-checkout` killed |
| M1 | In-memory managers: worker threads queried the one shared StaticPool connection | mutants `M-worker-thread`, `M-hierarchy-thread`, `M-export-thread`, `M-detect` killed |
| P3-A/B/C | see J | mutants `A-*`, `B-*`, `C-*` killed |

## E. Call-site audit

Counts in product code (`core tabs dialogs ui main_window.py run.py api`,
grep on `b68b141`; product code is unchanged at `aaaebc8`): `session_scope(` 74, `create_session(` 235,
`raw_connection(` 5, `engine.connect(` 1, `sqlite3.connect(` 7,
`sqlite_connection.connect(` 8, `.dispose(` 4, `worker_database(` 3, pool
`event.listen` 14. A static AST scan flagged 32 sites in which a session might
outlive its block or cross a thread. All 32 were inspected; none passes an ORM
object or session to another thread.

| Class | Sites | Finding |
|---|---|---|
| Unit of work | `session_scope` blocks; service methods take `session=` | Write paths pass the caller's session; no nested independent write session on the same thread except the restore audit (F) |
| Read-only background | `worker_database`: Export Center, Home KPI `ReadOnlyQueryWorker`, `HierarchyWorker` | Own `mode=ro` connection (`NullPool`), gated; a write fails as read-only (`test_export_worker.py:178`) |
| Write (UI thread) | services under `session_scope`; `save_well` | Commit is the success criterion; lock errors are reported, not swallowed |
| Long-running | document extraction (`ExtractionWorker`), MinerU and AI mapping (`FunctionWorker`, `excel_import_dialog.py:634`, `smart_template_dialog.py:2335`) | No database access on the thread; results applied on the UI thread |
| Maintenance | `RestoreService` (`dispose` at `db_maintenance.py:1038`), `BackupService`/`BackupScheduler` (`sqlite_connection.connect`, backup API), `database_reset.py:48` (offline CLI, refuses unless exclusive), `raw_connection` in initialize/migrations | Migration connections that leave `foreign_keys=OFF` are discarded on checkout; staged and backup files use direct `sqlite3` on non-live paths |
| Test / memory | `:memory:` StaticPool; `document_library.py:599` (FTS5 probe on `:memory:`) | `shares_single_connection` policy (C) |
| Unsafe (fixed) | file StaticPool; gate counting; ungated creator; in-memory worker threads | D |

Shutdown: `DatabaseManager.close()` disposes the engine (`database.py:4622`);
restart re-runs `initialize`, which re-joins the same gate without resetting it.
Several managers on one file are covered by tests (H). Authorization: the
read-only principal test uses real authenticated users on a file database
(`engineer` creates, `viewer` is refused with `denied`, raw note and audit rows
unchanged). Audits record the session principal, as before.

## F. Maintenance

* `close(drain_timeout)` refuses new connections (creator) and checkouts,
  then waits until no record is checked out and nothing is connecting. On
  timeout it reopens and raises `MaintenanceBusy`; nothing has changed.
* A second maintenance is refused (`MaintenanceBusy`).
* After the drain, `engine.dispose()` closes the idle connections. Another
  manager or process holding the file is detected at the exclusivity step
  (`journal_mode=DELETE`), and restore fails safe (`MaintenanceBusy` at stage
  `exclusive`, tested with a second manager and with an untracked direct
  `sqlite3` connection).
* Safety copy, atomic replace, verification and recovery are unchanged.
  Recovery after an injected reopen failure is tested, and the pool is usable
  afterwards.
* **Known case (pre-existing, now asserted).** If the thread that calls
  `restore` itself holds an uncommitted write, the restore aborts at the
  drain. The outcome audit row, written on another connection, then waits
  `busy_timeout` behind that write and is reported as
  `audit_recorded=False`, and the sidecar journal records `restore_failed`.
  The pending writer stays valid.

## G. Tests

Environment: Linux, Python 3.11.2, SQLite 3.40.1, SQLAlchemy 2.0.36, PySide6
6.8.1.1 with Qt offscreen (`QT_QPA_PLATFORM=offscreen`, bundled libraries),
pytest 9.1.1. Product code is never stubbed. These are **not** Windows desktop
results; the Windows runner is in L.

Test types:

* `test_sqlite_pool_isolation_m47.py` (34): source tests on real temporary
  file databases. The H1, hierarchy and export tests use Qt offscreen; the
  restore tests use the real `RestoreService`.
* `test_search_closure_m47.py` (42): source tests. The FTS5 probe uses the
  real SQLite FTS5 (`fts5vocab`); the widget test uses Qt offscreen.
* No mocks of product code. Fault injection uses the existing `fault` hooks
  and a monkeypatched `_add_mandatory_audit`.

| Run | Command | Tree | Result | Time |
|---|---|---|---|---|
| Baseline | `python -m pytest -p no:cacheprovider --tb=short -rfEs --continue-on-collection-errors` | `46a6948` | 3170 passed, 0 failed, 4 skipped | copied from M47 start run |
| Full suite | same | working tree = code tip except `workflow_m47.py` (tool) | 3246 passed, 0 failed, 4 skipped | 576.97 s |
| Reverse file order | same, with `$(ls tests/test_*.py \| sort -r)` | same | 3246 passed, 0 failed, 4 skipped | 574.19 s |
| Full suite, exact SHA | same, `tests` | `b68b141` (clean tree) | 3246 passed, 0 failed, 4 skipped | 593.62 s |
| **Full suite, exact code tip** | same command on the two alphabetical halves of `tests/test_*.py` (121 + 122 files; 1701 + 1550 = 3251 collected, equal to `tests`) | `aaaebc8` (clean tree) | **3247 passed, 0 failed, 4 skipped** (1698 + 3 skipped; 1549 + 1 skipped) | 314.59 s + 273.66 s |

Why the exact-tip suite ran in two halves: two single-process full runs in
this sandbox (one on `b68b141`, one on `aaaebc8`) were terminated from outside
at 93% and 97%. The log stops mid-line, with no pytest summary and no exit
line from the wrapper shell, so no test result was recorded. The cause is not
known: no OOM record was visible, and free memory was ample. These truncated
runs are not counted. Single-process forward and reverse runs did complete
on the `b68b141` tree (3246/0/4 each), and so did one exact `b68b141` run.

Count change: 3170 + 34 (pool module) + 42 (search module) + 1 (the obsolete
shared-connection assertion in `test_sqlite_connection_reliability.py` was
replaced by two file-backed pool tests) = 3247. The runs on `b68b141` show
3246 because the read-only probe was added afterwards. The 4 skips are unchanged:
`test_ddr_acceptance.py:33` ×2 (opt-in, real data never used),
`test_mineru_real_integration.py:26` (no MinerU), and
`test_packaging_smoke.py:218` (no Windows bundle on Linux).

Changed existing tests (no assertion weakened):

* `test_sqlite_connection_reliability.py`: the assertion "the engine is one
  shared connection" described the defect. It was replaced by assertions for
  distinct verified pooled connections and an in-memory `StaticPool`.
* `test_search_parity_m46.py`, `test_m45_ui.py`: the version pin moved from 2
  to 3.
* `tools/quality/mutation_m46.py`: the `S-version` mutant follows the new
  value (3 → 2).

## H. H1 and isolation evidence

* **New code:** all 34 pool tests pass on a file database. The cases are:
  * A's pending write survives B's rollback, close and failed flush;
  * a commit never carries another session's write;
  * the real `HierarchyWorker` sees committed rows only; then commit, and an
    independent `sqlite3` sees the row with `integrity_check` = ok;
  * two readers run during a writer and see its pre-commit snapshot;
  * writers on two managers serialise, the second fails explicitly after
    `busy_timeout` with no partial data, and a later retry succeeds;
  * a contended `save_well` returns `False`;
  * connections are released on success, error and rollback;
  * the `HierarchyWorker`'s own connection cannot write: a real ORM write
    through its view fails as read-only;
  * no pool leak at teardown (`checkedout` 0; gate `checked_out` and
    `connecting` 0).
* **Old pool behaviour:** the StaticPool mutant (the M46 engine
  configuration) on the M47 tree gives 14 failed test bodies, among them:
  * `test_closing_one_session_does_not_roll_back_another_sessions_pending_write`
    (B sees A's uncommitted row: `1 == 0`);
  * `test_rollback_in_one_session_does_not_touch_another` (A's write lost);
  * `test_h1_reader_thread_on_the_manager_during_a_pending_write` (dirty
    read).

  The other 25 errors are the teardown leak check, which needs `QueuePool`
  counts. The real-`HierarchyWorker` variant passes its body on the old pool,
  because M46 already gave that worker its own connection. It is a regression
  guard, as documented in the test.
* An honest run of the M47 modules on the `46a6948` tree is **NOT RUN**. They
  import M47 APIs (`POOL_SIZE_ENV`, `connection_diagnostics`), so collection
  would fail without proving anything. The mutant run above is the
  old-behaviour evidence.

## I. Order runs, repetition, leaks, end-to-end

Order runs and repetitions ran on `b68b141`; the code tip only adds one test.

| Run | Result | Time |
|---|---|---|
| M46 modules alone | 22 passed | 6.3 s |
| M47 modules alone | 75 passed | 27.9 s |
| Hostile order (M46 command) | 92 passed | 5.9 s |
| Hostile order + M47 | 167 passed | 32.5 s |
| M44+M45+M46+M47 forward | 217 passed | 53.3 s |
| M47+M46+M45+M44 reversed file list | 217 passed | 55.4 s |
| Concurrency modules ×5 (pool M47, hierarchy M46, hierarchy lifecycle, restore service, reliability, export worker) | 5 × 90 passed | 92–95 s each |
| Same, reversed ×3 | 3 × 90 passed | 93–95 s each |

All runs use `-p no:randomly`. Every pool test checks for leaks at teardown.
Warnings are third-party matplotlib/pyparsing deprecations only.

**Synthetic end-to-end:** `tools/quality/workflow_m47.py` uses real
authenticated users, a temporary file database and Qt offscreen. Result: 12
steps, 12 passed, 1.3 s.

* **Persistence 3:**
  * the real `HierarchyWorker` during a pending write sees committed rows
    only;
  * an independent connection and `integrity_check` confirm the commit;
  * a second manager is refused with `locked`, stores nothing, and a later
    retry succeeds.
* **Documents 6:**
  * import;
  * Persian search through FTS5;
  * `SYN-DEV-01` hits only its document, and the highlight is exactly
    `SYN-DEV-01`;
  * a whitespace-only note is stored as NULL;
  * a forced audit failure gives `audit_failed` with note and audit
    unchanged;
  * the audited note-only change is stored trimmed, and the audit holds
    lengths only.
* **Maintenance 3:**
  * a restore with a held reader aborts after the drain bound and the
    database stays valid;
  * after the reader closes, the snapshot is live and the settings are
    re-applied (FK 1, WAL, `busy_timeout`);
  * no connection is left checked out.

Screenshots: **NOT RUN.** No UI layout changed. The highlight is verified in
the real `DocumentsTab` (Qt offscreen) by its extra-selection positions.

## J. P3 fixes

* **P3-A spans.** `find_spans(text, groups)`:
  * single-word groups prefix-match a word start;
  * multi-token groups (identifiers, quoted phrases) match only exact
    adjacent tokens, with the span from the first token's start to the last
    token's end in the original text;
  * half-space alternatives are included, and spans are merged and sorted
    whatever the group order.

  `DocumentLibrary.search` returns `groups`, and the viewer highlights with
  them and maps code points to UTF-16 (`utf16_offset`). FTS5 and fallback
  parity is parametrised over both search paths.
* **P3-B fold.** Probed against the real `unicode61 remove_diacritics 2`
  through `fts5vocab`. That tokenizer folds case **first**, one character to
  one character, and then removes diacritics: U+1E9B → U+1E61 → `s`, while
  U+01E0/U+01E1 are kept. `_fold` now does the same: `_simple_fold` and then
  the diacritic map, with `_FTS5_KEEPS`. The corpus is built at run time:
  every word character in U+00C0–024F, U+1E00–1EFF, U+0600–06FF,
  U+0750–077F, U+FB50–FDFF and U+FE70–FEFF, plus `s S ſ ẛ ẞ ß ŉ ẚ Ǡ ǡ`,
  1608 characters in all. For each one, the token that FTS5 stores
  (`fts5vocab`) must equal the comparison form. Only this probe is skipped
  when FTS5 is missing. Result on SQLite 3.40.1: 0 mismatches. `NORMALIZATION_VERSION` 2 → 3, so older indexes are
  rebuilt.
* **P3-C notes.** `normalize_note`:
  * strips Unicode whitespace, caps the note at 200 characters and strips
    again;
  * stores an empty result as NULL, on create and update (the only write
    paths);
  * reads a legacy `""` back as `None`.

  `update_link(note=...)` follows the unchanged, duplicate, authorization and
  mandatory-audit rules. An audit failure rolls back. The audit records
  `note_chars`, never the text. No migration was needed. No UI displays link
  notes, so NULL and `""` cannot be told apart.

## K. Documentation

`docs/DATABASE_OPERATIONS.md` gains a new section, "Connection pool and
session ownership (M47)", covering:

* the file pool;
* pool timeout versus busy timeout;
* the single writer;
* the in-memory policy;
* the worker table;
* diagnostics.

The restore steps are updated (gate, drain, dispose, accounting), and the
known restore-audit case is documented. The obsolete "one shared connection
per process" limitation was removed.

## L. CI

| SHA | Source release gate | Windows release validation |
|---|---|---|
| `b68b141d21744f5da4a1d74a3d24c678a3dc6ccf` | 40279553687 success (3.11, 3.12, 3.13; coverage 57.32%, 43942/76657, floor 45.50%) | 40279553662 success (job 121429617810; UNSIGNED; Python 3.12.10) |
| **Code tip** `aaaebc855ccf3f387aa4a9bc84960fbc054244e2` | **40283830866 success** (3.11, 3.12, 3.13; coverage 57.32%, 43942/76657, floor 45.50%) | **40283830802 success** (job 121442786919; UNSIGNED; Python 3.12.10) |
| Report | see the final reply (the report cannot contain its own SHA) | — |

The Windows gate now also runs `test_sqlite_connection_reliability.py`,
`test_sqlite_pool_isolation_m47.py` and `test_search_closure_m47.py`. The
contract test lists them (66 passed). Per-test counts on the Windows runner
are in its JUnit artifact, which cannot be downloaded from this sandbox (the
blob host is unreachable). A CI runner is not Windows acceptance.

## M. Mutation, gates, Git

* **Mutation (fresh, complete, on the code tip tree):**
  * `tools/quality/mutation_m47.py`: 26 mutants, 26 killed, 0 survivors, 0
    equivalent, 0 invalid; baseline 100 passed; 311 s; exit 0. Each mutant
    reinstates one old behaviour or removes one guard (C, D, J).
  * `tools/quality/mutation_m46.py`: 29 mutants, 29 killed, 0 survivors, 0
    invalid; baseline 83 passed; 66 s; exit 0.
* **A finding from the M46 mutation run.** On `b68b141`, `mutation_m46`
  reported `H1-shared-connection` as **SURVIVED** (28/29). That mutant makes
  the `HierarchyWorker` read through the application pool instead of
  `worker_database`. M47 gave every session its own connection, so the M46
  H1 test could no longer detect the mutant, because no data is lost any
  more. The mutant still removed a real guarantee: the worker's connection
  is `mode=ro`, and read-only workers must never write. A new test,
  `test_the_hierarchy_worker_connection_cannot_write`, attempts a real ORM
  write through the worker's own view and requires a read-only failure.
  Both tools list it, `mutation_m47` has the same mutant as
  `W-hierarchy-not-read-only`, and both are killed. The mutant was not
  declared equivalent.
* The `S-version` mutant in `mutation_m46` follows the new version (3 → 2).
* **Workflows:** `workflow_m47.py` 12/12; `workflow_m46.py` 24/24.
  Schema compatibility (`schema_compat_check.py`, old `0822a28` to new
  `b68b141`): 26/26.
* **Gates:**
  * ruff: no new findings in changed files (per-file counts identical to
    `46a6948`);
  * lint debt 749 / ceiling 749;
  * exception scan exit 0;
  * `git diff --check` clean;
  * privacy check 0 findings before every commit.
* **Git:** six code commits (B), each pushed and confirmed with `git ls-remote`.
  There was no force-push, reset, rebase or history rewrite, and
  `drill-Master` was not touched.

## N. Privacy, licence, limitations, owner items

* **Privacy:** synthetic data only (`SYNTHETIC`/`SYN-*`); no real DDR, names
  or values. Audits store note lengths, not note text. No new binary data
  files.
* **Licence:** no new dependency. The open owner decisions (PyMuPDF
  AGPL/commercial, OCR weights) are unchanged.
* **Limitations:**
  * SQLite allows one writer, so a long write blocks other writers up to
    `busy_timeout`.
  * Multi-instance use is coordinated only by SQLite locks, plus the backup
    and restore file lock.
  * On POSIX an open handle can survive a replace (unlinked inode).
  * Network file systems are unsupported.
  * The restore-audit case is described in F.
  * Native Windows desktop behaviour was not exercised here.
  * The Windows stack-overflow cause from M46 remains unproven.
* **Owner items (unchanged):** signing; release tag and approval;
  Windows/field acceptance; licence choices; history purge; merging the
  containment PR.
