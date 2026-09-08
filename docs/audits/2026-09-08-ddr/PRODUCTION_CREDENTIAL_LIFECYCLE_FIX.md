# Production credential / reset lifecycle fix

Date: **2026-09-08**

**Scope:** database initialization, authentication bootstrap, offline reset, related configuration/fixtures and tests only. **Not whole-application Production certification. Windows/Python 3.12 acceptance remains NOT VERIFIED.**

## 1. Baseline and forensic conclusion

Repository: `asgareyvazi/Drill-master`. Fixed branch: `arena/01a0801f-drill-master`.

The requested `eb8041de79d44f6ac6099ca84e569116af0d617c` is preserved in ancestry. At this task's start both checkout and remote were already at **`c7d9f2ee6d513cf18c0f6a4eb5e2ebb181f869c2`**, containing the subsequent lifecycle work. Work continued from that commit without reverting either remediation. The final new SHA is reported after commit/push; it is the commit containing this report.

### Exact root cause

There were **two independent mode defaults**:

1. `run.py` constructs `DrillMasterApp`. Its constructor set `DRILLMASTER_ENV=production` **inside that Python process** if the operator had not configured a mode. That does not set the parent PowerShell environment for later commands.
2. `reset_database.py` constructed `DatabaseManager` directly, without the application constructor. `core.database.runtime_environment()` defaulted to **development** when neither mode variable existed.
3. Reset unlinked the configured DB and WAL/SHM files **before** validating the bootstrap configuration, then called `initialize()` → `create_default_data()`.
4. In that unconfigured CLI process, `_bootstrap_passwords()` selected deterministic development fixtures and stored their bcrypt hashes. Hashing a publicly known password does not make the credential safe. Reset could report success.
5. The next `run.py` process selected Production again. Users already existed, so first-run setup was skipped and environment bootstrap passwords were not applied. `_reject_unsafe_existing_credentials()` correctly detected the fixture hashes and blocked startup.

This explains the reset → same unsafe-credential failure cycle **without any failure of the security detector**.

A second confirmed defect was in Settings: the GUI reset handler did not reset anything; after confirmations it instructed the operator to run **`reset_db.py`**, which does not exist. The actual script is `reset_database.py`. Without the user's exact preceding reset transcript we cannot determine which route they used; both defects are proven in the inspected code and both are addressed.

### Complete path inspection

| Boundary inspected | Finding |
|---|---|
| `run.py`, `app.py`, console entry point | Desktop process-local Production default, first-run probe/dialog, database initialization, login and startup flow |
| `core/database.py` environment/bootstrap/hash/verify/authentication | Divergent development default; bootstrap only when users count is zero; bcrypt cost 12; development-only SHA compatibility; existing unsafe guard originally restricted fixture checks to three usernames |
| `reset_database.py` | Full file deletion, no secure preflight, initialization after destruction; uses shared runtime DB path rather than CWD |
| `dialogs/settings_dialog.py` | Offline guidance only, incorrect script name, no executed DB reset |
| `dialogs/bootstrap_dialog.py` | Existing secure setup UI; previously required three accounts; validation minimum 12 characters differed from environment bootstrap |
| `dialogs/login_dialog.py`, permissions | Login checks DB hash; Production auto-login is disabled; remembered usernames only; legacy password key was removed only after a later save |
| Schema upgrades / `core/db_models.py` | Migration copies existing user/hash columns, not password rotation. Duplicate model declarations are not another user-seeding path; active DatabaseManager uses its own mapped User |
| `core/runtime_config.py`, configuration / packaging | Shared per-user data location; environment overrides; no automatic `.env` loading; no filename-based security mode |
| `app.run_package_smoke`, packaging smoke launcher | Explicit test seed could inherit an operator's `DRILLMASTER_DB_PATH` despite selecting a temporary data directory, and could leave process mode changed if called in-process |
| Tests / standalone seed tools | Existing tests relied on the unsafe implicit library default. Test fixture mode must now be explicit and isolated; application code must not detect pytest and weaken itself |
| External settings/license/device state | Reset's intended scope is the SQLite database. No separate license/device credential reset is implemented in these paths; external files/settings are not removed |

## 2. Established security contract

### Environment selection

`core/credential_policy.py` is the single policy used by database, desktop bootstrap and reset. Existing imports from `core.database` remain compatible.

- No mode variables: **Production everywhere**, including direct DatabaseManager use and the reset CLI.
- Explicit `production` / `prod`: Production.
- Explicit `development` / `dev` or `test` / `testing`: deterministic development fixtures permitted.
- Values are normalized for case and surrounding whitespace. Unknown or explicitly empty selectors fail closed. Conflicting `DRILLMASTER_ENV` and `DRILLMASTER_ENVIRONMENT` values fail closed.
- Desktop startup does not overwrite an explicitly empty mode with another value.
- No CWD, filename, OS, frozen-package or pytest detection chooses a less secure runtime mode.
- `.env` files are **not automatically loaded**. Process environment variables are authoritative. An operator may use a restricted secret mechanism to populate that environment; do not commit secret files.

### Production bootstrap

A fresh Production database requires **only an administrator account**:

- Required: `DRILLMASTER_ADMIN_PASSWORD`, or the existing first-run setup dialog.
- Optional: `DRILLMASTER_USER_PASSWORD` and `DRILLMASTER_VIEWER_PASSWORD`. An omitted setting omits that account; an explicitly empty/invalid setting is rejected.
- Minimum 12 characters, maximum 72 UTF-8 bytes to avoid bcrypt truncation. Known development fixture values are forbidden, including trivial case/outer-whitespace variants at the bootstrap boundary.
- bcrypt is mandatory in Production; new hashes use independent salts and cost 12. No Production SHA fallback.
- Credentials supplied through environment settings are honored without an unnecessary setup dialog. Invalid supplied settings are reported, not replaced by defaults.
- Without environment credentials, a genuinely empty desktop database opens the existing setup dialog. Admin is required; other accounts may be left blank.
- GUI-created passwords are passed directly to initialization in process memory, **not assigned to `os.environ`**, inherited by child processes, or written to configuration files. The manager discards its bootstrap override after initialization, including failures.
- Production starts without demo company/project/well records. This was preserved.

### Existing database and authentication

Bootstrap configuration is used **only when no users exist**. It neither overwrites safe existing users nor silently rotates unsafe ones. Reopening a safe Production database does not require bootstrap variables.

The unsafe detector is retained and strengthened: it checks fixture passwords for **all usernames, including renamed accounts**, and rejects non-bcrypt/malformed-format credentials. Production login rejects known fixture input and does not use the legacy SHA verification path. Existing non-bcrypt/unsafe data is not silently converted.

Distinct password-free diagnostics now separate:

- `BOOTSTRAP_REQUIRED`: empty/new Production DB needs initial configuration/setup.
- `BOOTSTRAP_INVALID`: provided settings violate the bootstrap policy.
- `UNSAFE_EXISTING_CREDENTIAL`: existing users violate the Production guard; changing environment passwords does not repair them.
- `BCRYPT_REQUIRED`: install the required dependency.
- `ENVIRONMENT_INVALID`: fix mode configuration instead of downgrading.

The desktop displays these controlled messages rather than only a generic database error. Recovery guidance identifies the real offline reset script and explicitly warns that it erases all database data; back up first.

## 3. Reset contract and implementation

**Reset means replacing the complete configured SQLite database: schema, users and operational records. It does not preserve authentication.** External settings, logs and backups remain. A non-destructive account-rotation/data migration tool is not introduced in this focused fix.

The supported reset is **offline**: close all DrillMaster instances and keep them closed through completion. The GUI now truthfully states that it has changed no data and provides the correct offline instructions. The CLI displays the configured path before confirmation.

`core/database_reset.reset_configured_database()`:

1. Resolve the same environment/path contract as startup. Reject in-memory reset.
2. Validate the full requested bootstrap configuration and required bcrypt **before filesystem mutation or data destruction**.
3. Build a replacement in a temporary file in the destination directory using the existing schema initializer and default-data service. Production credentials are validated, not fixture-seeded.
4. Check the replacement's Production credential guard, close its handles, and ensure it does not depend on a live WAL file.
5. Refuse a mode change during reset. For an existing DB, checkpoint WAL, require offline access and close the connection before replacement. Do not unlink the operational database first.
6. Atomically promote the same-filesystem replacement with `os.replace`. Preparation/promotion failures retain the old logical database; temporary candidate files are cleaned up.
7. Restart normally. The new administrator can authenticate; bootstrap settings are no longer required for subsequent launches.

Chosen outcomes:

- **Outcome C:** missing/invalid Production bootstrap configuration refuses reset before deletion. Tests compare the old file byte-for-byte for these failures.
- **Outcome A:** valid configuration builds a complete secure replacement and startup/authentication succeeds in the executed service/CLI verification.
- Fresh GUI installation additionally retains the existing first-run setup flow. A failed empty initialization contains zero users, so it remains recoverable through setup rather than triggering the unsafe-existing-user error.

Windows-specific design: standard Python path/SQLite APIs, no Unix deletion commands; explicit handle closure (including the first-run SQLite probe), WAL handling, same-directory replacement, and refusal on open/locked files. These design choices and simulated Windows path/permission tests **do not constitute an actual Windows execution**.

Use the **same Windows account, environment and database-path settings** for reset and startup. Resetting a different user's `%LOCALAPPDATA%` profile cannot repair the intended database. The PowerShell procedure using masked `Read-Host -AsSecureString` input is documented in `DEPLOYMENT.md`; it contains no password value.

## 4. Development/test isolation and secret handling

- Explicit Development/Test retains all three existing default users and development sample hierarchy. Login, existing DB reopen and reset are regression-tested for all documented aliases.
- An otherwise unconfigured pytest process explicitly selects Test in `tests/conftest.py` and uses a disposable DB/data directory, not the normal per-user profile. Production tests override/remove that configuration. Standalone fixture tools must explicitly select Test/Development and isolated paths.
- Package smoke now forcibly selects its own temporary DB path, clears inherited credential settings for the fixture run, clears conflicting mode aliases, and restores original settings on success/failure. It closes the manager even if initialization fails. No unrelated engineering/import module is changed.
- GUI first-run fields use masked input. DB storage is salted bcrypt, not plaintext. SQLAlchemy exception parameters are hidden; controlled credential diagnostics and the reset CLI do not print password values.
- Login removes a legacy plaintext QSettings password key when loading the dialog, not only after a successful login/save. Only username/remember preference remains.
- Test passwords for the new successful Production scenarios are generated temporarily at runtime. No actual Production secret or password hash is included in this report or the saved verification summaries. Public development strings appear only where required for detection/negative fixtures.
- Environment-based bootstrap inherently exposes the value to the launched process; it is not an encrypted secret store. Use a restricted account/environment, remove temporary settings afterward, and protect DB/backups with OS permissions.

## 5. Regression matrix

New file: `tests/test_credential_lifecycle.py` — **49 collected, 49 passed**. Parameterization exercises aliases, missing/empty/known/oversized settings, optional accounts, mode errors, and failure paths.

| Required case | Executed evidence |
|---|---|
| 1–5 Development fresh DB/users/existing DB/reset/login | `test_development_fresh_users_login_reopen_and_reset`, four aliases; all three accounts authenticate |
| 6 Production fresh/secure | Admin-only and explicit optional-account tests; no demo hierarchy; bcrypt cost/salt storage assertions |
| 7–9 Missing/empty/development credentials | Parameterized bad bootstrap; initialization fails with bootstrap-specific code and zero users |
| 10 Existing safe DB | Reopen and authenticate after removing bootstrap environment settings |
| 11 Existing unsafe DB | Rename administrator in a development DB; Production guard still rejects it; secure environment does not overwrite it |
| 12 Production reset/valid | Real unsafe source DB replaced; one safe administrator; no fixture login; settings preserved |
| 13 Production reset/missing | Missing, empty and known-invalid preflight leave old bytes unchanged |
| 14–15 Restart/authentication after reset | Reopen without bootstrap variables and authenticate with the temporary configured credential |
| 16 Development passwords forbidden | All known fixtures, cross-role values and trivial variant rejected at bootstrap; fixture logins refused |
| 17 No password logs | Successful/failed initialization, CLI stdout/stderr, diagnostics and on-disk plaintext checks |
| 18 Reset cannot recreate unsafe Production users | Explicit post-reset guard invocation, account count and negative fixture authentication |
| 19 No implicit downgrade | Direct default-mode/CLI subprocess tests, invalid/empty/conflicting selectors, `.env` ignored, package-smoke state restoration |
| 20 Guard remains effective | Existing unsafe renamed user and legacy credential tests; bcrypt dependency refusal |
| Additional durability/path tests | Candidate initialization failure, promotion permission failure, active WAL reader refusal, other-CWD CLI invocation, Windows path simulation |
| First-run/GUI integration boundary | Actual first-run methods executed with protocol hosts; five empty/existing/corrupt DB probe states; setup honors environment without a dialog |
| Fixture isolation | Actual package-smoke coordinator executed with module/DB protocol probes for success and failure; operator DB path and secrets not used |

The protocol tests are explicitly **not native Qt/bundle tests**. No existing test is removed, weakened or disabled to bypass the Production guard.

## 6. Exact verification results

Executed on Linux x86-64, **Python 3.11.2**, SQLite **3.40.1**, bcrypt **4.3.0**, SQLAlchemy **2.0.52**.

| Run | Collected | Passed | Failed | Errors | Skipped | Warnings | Elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Focused credential lifecycle | 49 | 49 | 0 | 0 | 0 | 0 | 32.21 s |
| Authentication/database/release subsystem | 74 | 73 | 0 | 0 | 1 | 0 | 42.89 s |
| **Full existing + new suite** | **711** | **704** | **0** | **0** | **7** | **15** | **143.79 s** |

The prior combined DDR baseline had 662 tests / 655 passes / 7 skips. This change adds 49 credential tests; no prior failures were introduced. Full tests included the actual repository XLSX acceptance variable. No importer, BHA, survey, mud, safety, logistics, planning or engineering/chart implementation was edited.

Full-suite skips remain real PDF input, real MinerU input/runtime, Windows bundle, and four Qt-dependent checks blocked by libGL. Warnings are the existing openpyxl data-validation-extension and large-file warnings. Compilation, targeted Ruff F/F821 checks and whitespace checks pass.

Saved evidence: `evidence/credential-lifecycle/` — focused/subsystem/full logs and JUnit, `runtime.json`, `runtime.txt`, `environment.json`, native startup failure and reproduction commands. No operational databases are committed.

### Real service/CLI acceptance (not mocks)

A separate temporary SQLite run created a Development DB, removed the mode variable, and confirmed that the new default Production initializer rejects its unsafe accounts. The actual `reset_database.py` subprocess:

- refused missing configuration and retained original DB bytes;
- accepted a randomly generated secure administrator bootstrap setting;
- replaced the DB with one Production administrator;
- emitted no password value;
- allowed a new manager to initialize and authenticate after the bootstrap variable was removed.

Temporary DB/credentials were disposed. This independently verifies the reported reset loop's repair on the available platform.

## 7. Windows / Python 3.12 and acceptance limits

**Windows/Python 3.12: NOT VERIFIED.** No Windows execution environment, PowerShell or Wine is exposed in this workspace. No Windows runner was provisioned or executed. Path simulation and injected permission errors are not counted as Windows runtime proof.

Actual `QT_QPA_PLATFORM=offscreen .venv/bin/python run.py` was attempted after implementation. Native startup fails before the application constructor at `ImportError: libGL.so.1`. Consequently **native GUI startup, first-run dialog interaction and login clicks are NOT VERIFIED**, and the user-required Windows acceptance criterion G is still open.

| Acceptance | Result |
|---|---|
| A Fresh Production initialization | Verified at real service/DB boundary on Linux |
| B No development fixture passwords after Production reset | Verified with guard and authentication checks |
| C Recoverable reset | Verified preflight refusal and secure successful restart; initialization/promotion failure tests preserve old data |
| D Missing bootstrap distinct/actionable | Verified explicit bootstrap diagnostics and first-run state distinction |
| E Existing unsafe DB remains protected | Verified, including renamed user and legacy hash |
| F Development fixtures still work explicitly | Verified |
| G Windows + Python 3.12 startup/authentication | **NOT VERIFIED / remaining acceptance blocker** |
| H No actual secrets committed/logged/reported | New generated test credentials remain transient; storage/log/CLI regression checks pass |
| I Lifecycle regression tests | 49 passing tests |
| J Existing suite preserved | 704 passed, 0 failed/errors, 7 documented skips |

Remaining limits: offline reset requires all instances to remain closed; concurrent startup/reset is unsupported. Atomic replacement is not claimed to provide cross-process orchestration or power-loss guarantees beyond the underlying filesystem. Reset is destructive to all SQL data; there is no new non-destructive account recovery/migration tool. Actual Windows/GUI verification must be performed with temporary credentials before claiming full lifecycle acceptance.

**Conclusion:** root cause fixed and security guard preserved/strengthened, with successful Linux service/CLI lifecycle and regression verification. **No whole-application Production certification, and no assertion that Windows criterion G has passed.**
