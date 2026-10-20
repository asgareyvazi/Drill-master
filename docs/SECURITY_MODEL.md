# DrillMaster security model

Status: M43 (2026-10-19). Describes what the code enforces and what it does
not. Verified by the tests named in each section; nothing here is a claim of
penetration testing or production acceptance.

## 1. Deployment assumption

DrillMaster is a **single-user-at-a-time desktop application** on Windows with
a local SQLite database in the OS user-data directory (override:
`DRILLMASTER_DATA_DIR` / `DRILLMASTER_DB_PATH`). There is no network service:
`core/api/rest_api.py` deliberately never builds an HTTP application
(`tests/test_rest_api_disabled.py`).

**Trust boundary.** Authentication and authorization protect the data
*through the application*. They do not protect the database file from someone
who can read or write it directly (same OS account, administrator, stolen
disk): the file is **not encrypted** (SQLCipher is not used; see §7). Protect
it with OS account separation and full-disk encryption.

## 2. Modes

`DRILLMASTER_ENV` selects `production`, `development` or `test`
(`core/credential_policy.py`). Production refuses to start with development
fixture passwords or any non-bcrypt stored credential, and refuses them at
login (`tests/test_credential_lifecycle.py`).

## 3. Authentication

| Property | Implementation | Tests |
|---|---|---|
| Password storage | bcrypt, 12 rounds (`DatabaseManager._hash_password`) | `test_credential_lifecycle.py` |
| Verification fails closed | malformed bcrypt hash or bcrypt error → refused (no fall-through to another format); the retired static-salt SHA-256 format no longer verifies; the salted `sha256:` format (only produced without bcrypt) verifies outside production only and is upgraded to bcrypt on the next successful login | `test_login_throttle.py::test_retired_and_malformed_hash_formats_fail_closed`, `::test_salted_sha256_is_refused_in_production`, `::test_successful_login_upgrades_a_development_sha256_hash_to_bcrypt` |
| Generic outcome | wrong password, unknown/inactive account, locked account and development password in production all return `None`; the login dialog shows one message | `::test_account_locks_after_the_configured_failures_with_one_generic_outcome` |
| Unknown-user timing | a bcrypt verification is spent when no account matches | code review (no timing assertion by design) |
| Remembered login | only the username is stored in QSettings; legacy stored passwords are purged | `dialogs/login_dialog.py` |

### Lockout / backoff (`core/login_throttle.py`, schema v5 `login_throttle`)

- Persistent per submitted username (survives restarts, shared by processes).
- Keyed by a SHA-256 digest of the normalized name, tracked whether or not the
  account exists; raw input (which may be a mistyped password) is never stored.
- Defaults: 5 consecutive failures within 900 s lock the name for 300 s; each
  further lockout before a successful login doubles the period up to 3600 s.
  Configurable with `DRILLMASTER_LOGIN_MAX_FAILURES`,
  `DRILLMASTER_LOGIN_FAILURE_WINDOW_SECONDS`, `DRILLMASTER_LOGIN_LOCKOUT_SECONDS`,
  `DRILLMASTER_LOGIN_LOCKOUT_MAX_SECONDS`; invalid values fall back to the
  default with a warning and never disable throttling.
- While locked the password is not verified.
- Concurrency: the counter is advanced by one atomic UPSERT that also takes
  SQLite's write lock, so parallel failures neither lose increments nor lock
  twice (`::test_concurrent_failures_are_all_counted`,
  `::test_concurrent_failures_lock_exactly_once_per_threshold`).
- Administration: `DatabaseManager.unlock_account(username, actor)` and
  `get_locked_accounts(actor)` require `can_manage_users`; without an actor
  and without an enforced principal they refuse (fail closed). **There is no
  UI for unlocking yet**; an administrator can call it from a maintenance
  script, or wait for the lock to expire.
- Audit: `login_failed`, `login_locked`, `login_rejected_locked`,
  `account_unlocked`, `authorization_denied` rows in `audit_logs` (usernames
  recorded only for existing accounts).

## 4. Authorization

Roles (`core/permissions.py`): admin (`*`), supervisor, engineer, manager,
viewer; a user's explicit `permissions` map overrides the role default.

**UI layer.** `@require_permission` slots and `DrillTabBase` checks.

**Data layer (M43, `core/authorization.py`).** After login the application
calls `DatabaseManager.enforce_authorization(permissions)`. From then on every
ORM insert/update/delete — every `save_*`, `delete_*`, `generic_*`, repository
and import write — is checked in a `before_flush` hook against a per-table
policy; ORM bulk `update()`/`delete()` statements are checked in
`do_orm_execute`; textual DML through a session is refused.

| Tables | Insert/update | Delete |
|---|---|---|
| companies, projects, wells, wellbores | `can_create_well` | `can_delete_well` |
| sections, daily reports and all report-scoped data, engineering calculation records, plans, procedures, costs | `can_edit_reports` | `can_delete_reports` or `can_delete_well` |
| users | `can_manage_users` | `can_manage_users` |
| drill_pipe_specs (reference catalog) | `can_import` | `can_manage_users` |
| audit_logs | insert: any signed-in principal; update: nobody | nobody |
| report_revisions, approval_actions | only through the report lifecycle | `can_delete_reports` or `can_delete_well` (removed with their report) |
| login_throttle | system only | system only |

Operations that authorize themselves declare a narrower scope:
`transition_report` (the action-specific permission is checked by
`decide_transition`; inside the scope only `status`/`updated_at`, a revision
and an approval action may be written), the DDR import (`can_import`; covers
the report data it creates), and system bookkeeping (bootstrap, default
template seeding, login throttling).

Fail-closed rules: a table without a policy is denied (a completeness test
requires every mapped table to have one); a principal whose permission
resolution raises is denied; denials raise `AuthorizationError` with a generic
message and are written to `audit_logs`.

Detection of unguarded mutations: the ORM hooks cover every ORM path; raw SQL
writers (`INSERT INTO`/`UPDATE … SET`/`DELETE FROM` literals) are allowed only
in reviewed migration/system functions, enforced by
`tests/test_data_layer_authorization.py::test_no_unreviewed_raw_sql_writer_bypasses_the_orm_guard`.

Tests: `tests/test_data_layer_authorization.py` (role matrix through direct
service calls for all five roles, explicit overrides, lifecycle, import,
bulk/textual paths, audit immutability, denial audit). Mutation check: disabling
the flush hook, the lifecycle scope or its column restriction, or the import
scope each fails a test.

**Finding closed by M43.** Saving an engineering calculation run
(`w13` "Save Calculation", `*_repository.save_run`) had no permission check,
so a viewer could persist records despite the documented read-only viewer
contract (`core/base_tab.py`). The data-layer policy now refuses it
(`::test_viewer_cannot_persist_engineering_calculation_runs`).

**Not covered.** A `DatabaseManager` on which `enforce_authorization` was not
called (tests, maintenance scripts) is unrestricted — such code already has
direct file access. Reads are not restricted by role (every signed-in role may
view all wells).

**Copying or replacing the whole database file.** A database copy contains
every row, the password hashes and the audit log, so it is a privileged
operation: `BackupService.create_backup` (interactive) and
`RestoreService.restore` require `can_maintain_database` at the service
boundary, write a manifest/journal and audit the outcome; denials are audited.
Scheduled backups run as `system:backup-scheduler`. `DatabaseManager.backup_to()`
is a low-level primitive without a permission check and no application module
may call it (`tests/test_backup_settings.py::test_no_application_module_copies_the_database_around_the_verified_service`).

**Finding closed by the M43 release hardening.** *Settings > Database >
Backup Database Now* called `backup_to()` directly, so any signed-in role
(including viewer) could copy the entire database file to any folder without
a permission check or audit entry; an unused `MainWindow.backup_database` had
the same defect. The button now runs the verified service and is disabled
without `can_maintain_database`; the unused method was removed
(`tests/test_backup_settings_ui.py::test_backup_now_uses_the_main_windows_verified_backup`).

### Read policy (audited 2026-10-20)

Reads are not restricted by role inside the application: every signed-in role
may view every company, project, well and report. The audit found no read path
that exposes credentials — password hashes are read only by the
authentication code in `core/database.py`, and there is no user-listing screen
— and no documented read rule that the code fails to enforce. Restricting
reads further (per company/project isolation, hiding costs from viewers) would
be a new business policy and is **not invented here; it is an owner decision**.

### Trust boundary: direct SQLite access

Every control above runs inside the DrillMaster process. Anyone who can open
the database file directly — the same OS account, an administrator, malware
running as the user, a copied backup, a stolen unencrypted disk — bypasses
authentication, authorization, lockout and the audit trail, and can read or
alter every row. Backups and pre-restore safety copies carry the same data and
the same exposure. Mitigations are operational: OS account separation, a
data and backup folder readable only by the user, and full-disk encryption
(BitLocker on Windows). See §7 for why the file itself is not encrypted.

## 5. Audit trail

`audit_logs` is append-only for every principal when enforcement is active
(`::test_audit_log_is_append_only_even_for_admin`). Lifecycle transitions
write immutable revisions. Without enforcement (direct file access) audit rows
can be altered; the audit trail is evidence, not tamper-proof storage.

## 6. Privacy

See `docs/privacy/README.md`: no real operational data in the repository,
enforced by `tools/privacy/privacy_check.py`; Git history still contains the
removed data until the owner-gated purge.

## 7. Not implemented (decisions)

- **Database encryption (SQLCipher)**: not used. Feasibility assessment
  (2026-10-20, no code written): it would need (a) a SQLCipher-enabled SQLite
  build for Python on Windows and Linux in the lock file and both release
  gates — the standard library `sqlite3` cannot open encrypted files; (b) a key
  source that is not stored next to the file on a single-user desktop (for
  example Windows DPAPI bound to the OS account, which protects only against
  other accounts and offline disk theft, the same threats BitLocker already
  covers); (c) re-keying and migration of existing databases and of every
  backup and safety copy, with restore tests for wrong/missing keys; and
  (d) a recovery story for a lost key. Until those are designed and tested,
  full-disk encryption is the recommended control; SQLCipher is not added
  blindly.
- Password change / user management UI, password expiry, MFA: not present.
- Code signing: builds are UNSIGNED (owner-gated).
