# Windows release build and acceptance runbook

This runbook is an executable procedure for Windows release engineering. A successful automated build is not interactive installation, real DDR/PDF/MinerU, production database, field, or operator acceptance.

## Automated Windows release gate

The dedicated **Windows release validation** workflow runs on `windows-2022` for pushes, pull requests, and manual dispatch.
It installs the pinned runtime/build dependencies and the Inno Setup compiler pinned by `packaging/inno_setup_version.txt`
(currently 6.7.1) and *reads the installed package version back* before using it, runs the disposable
database/import/auth/packaging regression suite, builds the one-folder portable bundle, executes
`DrillMaster.exe --package-smoke` with temporary data/log paths, compiles the installer, re-verifies authoritative version,
source SHA, artifact SHA-256 values and byte sizes, then runs the installed-application lifecycle smoke, records Authenticode
signature status, and generates `acceptance-report.json` from that evidence.

From a clean checkout of the intended full commit SHA, a local equivalent is:

```powershell
$sha = (git rev-parse HEAD).Trim()
if ((git status --porcelain=v1 --untracked-files=all).Length -ne 0) { throw 'Worktree must be clean' }
$release = Join-Path $env:TEMP "DrillMaster-release-$sha"
.\packaging\build_windows.ps1 -PythonExe (Get-Command python).Source -PythonVersion 3.12 -OutputDir $release
$version = (python -c 'from core.version import __version__; print(__version__)').Trim()
$lifecycle = Join-Path $env:TEMP "DrillMaster-lifecycle-$sha"
python packaging\windows_release_evidence.py lifecycle --installer (Join-Path $release "DrillMaster-$version-Setup.exe") `
  --release-metadata (Join-Path $release 'release-metadata.json') --app-version $version `
  --work-root $lifecycle --json-out (Join-Path $release 'installer-lifecycle.json')
python packaging\windows_release_evidence.py signing --release-metadata (Join-Path $release 'release-metadata.json') `
  --json-out (Join-Path $release 'signing-status.json')
python packaging\acceptance_report.py --metadata (Join-Path $release 'release-metadata.json') --junit <junit.xml> `
  --source-sha $sha --output (Join-Path $release 'acceptance-report.json') `
  --expected-innosetup-version (Get-Content packaging\inno_setup_version.txt -Raw).Trim() `
  --lifecycle-report (Join-Path $release 'installer-lifecycle.json') `
  --require-lifecycle --signing-report (Join-Path $release 'signing-status.json') --require-signing
```

Every command above is the same one the CI gate runs; `--require-lifecycle` and `--require-signing` are what make the gate refuse a
missing evidence file instead of recording `NOT_RUN`, so drop them only when you deliberately intend to report on a partial
evidence set (for example a `-PortableOnly` build, which cannot produce installer evidence at all). the local lifecycle invocation needs administrator elevation because `DrillMaster.iss` declares `PrivilegesRequired=admin`, and it installs only into the throwaway `--work-root` you pass.

Pass the interpreter explicitly with `-PythonExe` whenever the environment's `python` is the one you intend to package with; that is what the CI gate does. `-PythonLauncher py -PythonVersion 3.12` remains available on a workstation where the Python launcher is registered, but note that the launcher resolves registry-registered runtimes only, so it can silently select a different Python than the one whose dependencies were tested.

The build refuses dirty source trees, requires an explicit Python minor version and verifies that the build virtualenv actually satisfies it, uses the locked runtime/build requirements, does not delete pre-existing release output, and keeps PyInstaller temporary work outside the repository. Use a new output directory for each build. The prior `-Python "py -3.12"` form remains accepted through a non-evaluated parser; new scripts should use `-PythonExe` or the separate launcher/version parameters. `-PortableOnly` deliberately omits installer compilation and cannot establish installer evidence.

### Failure diagnostics and text encodings

GitHub publishes at most ten `::error::` annotations per step, so a suite with more failures than that would otherwise hide the rest.  The regression step therefore runs `python packaging\junit_report.py --junit <report> --summary-out <markdown> --json-out <json> --annotations`: one annotation per failure up to the cap, an aggregate annotation that names the overflow, and a full Markdown table in the job step summary.  The parser reports test identities, exception names and `file:line` locations only, redacts anything that looks like a password, token or API-key value, and writes UTF-8 regardless of the console codepage so that printing a diagnostic can never become the second failure.  The step still propagates pytest's own exit code.

That guarantee had a hole in the test step itself.  pytest writes its JUnit report only when it reaches the end of a run, so a run that is interrupted, aborted by the shell, or refused at startup leaves the parser with no report to convert -- and the step then fails while publishing no test identity, no summary row and no annotation, which reads exactly like a suppressed failure.  The step therefore captures its own output (`2>&1 | Tee-Object` into `windows-regressions.log` under `RUNNER_TEMP`, never uploaded), runs that pipeline with `$ErrorActionPreference = "Continue"` and `$PSNativeCommandUseErrorActionPreference = $false` for the same reason the build script does -- a line on a native command's stderr must not become a terminating error and kill a run that was about to succeed -- and passes `--pytest-exit` and `--pytest-log` to the parser.  `junit_report.describe_abort` then emits one bounded, redacted `::error::` annotation naming pytest's exit code and whether the report was absent, unparsable or merely empty of cases, quoting the tail of the captured log; it stays silent when the report already names the failures, and it never becomes the verdict, because `$pytestExit` still decides the step.  Unlike the `Start-Transcript` case above, the tee'd file is complete by then: the pipeline has ended and its handles are closed, so the tail a reader sees is the real end of the run.

One further measurement shapes the wording: GitHub stores at most 3000 characters of an annotation and cuts from the *front* -- on the run whose silence prompted this machinery, a message emitted at exactly that size arrived as an ellipsis followed by its last 2999 characters, headline gone.  Both the abort note and the crash excerpt are therefore sized to `ANNOTATION_SAFE_LIMIT`, and the full dump goes to the job step summary, which no annotation store squeezes.

Repository source files contain UTF-8 Persian UI strings.  Any test or release tool that reads them must state `encoding="utf-8"`; the runner's default codepage (cp1252) raises `UnicodeDecodeError` otherwise.  `tests/test_windows_release_gate_contract.py` enforces this for every module in the Windows suite, verifies that the workflow still lists the required modules and existing files, keeps the disposable `RUNNER_TEMP` isolation and the Inno Setup pin, and confirms that the committed M42.1 checkpoint does not claim a CI result.

### Packaging stage diagnostics

The build step cannot emit a JUnit report, so it reports differently: it publishes `release_dir` to the job outputs *before* building (the evidence upload runs on `always()`, and a step that set that output only on success uploads nothing exactly when it matters), records a `Start-Transcript` file next to the release directory, and wraps every assertion in `try`/`catch`. The `catch` runs `python packaging\junit_report.py --annotate`, which emits one bounded `::error title=Windows packaging stage failed::` annotation containing the stage message plus the redacted tails of the transcript and `pyinstaller-build.log`, then re-throws so the step stays red. A packaging failure is therefore identifiable from the check run alone, even when the log and artifact endpoints are unreachable.
The dependency stage is logged the same way as the bundle stage: `pip install -r requirements-lock.txt -r requirements-build.txt` and `pip check` are teed into `pip-install.log` inside the release directory (which is uploaded on `always()`), their exit codes are captured individually, and the last thirty log lines are embedded in the thrown message so they reach the annotation. The release output directory and its emptiness guard are resolved before any log is written, so a refusal to overwrite existing output cannot be caused by the build's own diagnostics. An annotation that quotes a PowerShell transcript is produced only after `Stop-Transcript`; while the transcript is open, native command output may not have been flushed yet, and the tail then reads as a header and nothing else — which is exactly how one packaging failure stayed nameless for a run.

PowerShell handling matters here for two reasons. The step sets `$ErrorActionPreference = 'Stop'` so an error thrown inside `build_windows.ps1` terminates the step at the throw instead of being reported and then falling through into the artifact assertions (which would mislabel a build failure as "Frozen executable missing"). Inside the build script, the redirected PyInstaller pipeline runs with the preference temporarily relaxed and `$PSNativeCommandUseErrorActionPreference = $false`, because PyInstaller writes its progress log to stderr; under `Stop` that output can become a terminating `NativeCommandError` and abort a build that actually succeeded. The captured `$LASTEXITCODE` is the only build-status signal the script trusts.

`acceptance_report.py` re-hashes the portable ZIP and the setup executable from the release directory — streamed in 1 MiB blocks through the
single `release_metadata.sha256_file` helper, never `path.read_bytes()`, so a ~300 MB artifact is verified without loading it —
and checks each recorded byte size.  It reads `package-smoke.log`, re-validates (rather than copies) the Inno Setup identity
against the pinned version, and validates `release-metadata.json` against `release_metadata.validate_document` before using any
field of it: a stale schema, a duplicated artifact row, a malformed digest, an unknown field, or a missing one is a refusal, not a
partial read.  It folds in `installer-lifecycle.json` and `signing-status.json`; the release gate passes
`--require-lifecycle --require-signing`, so on that path an *absent* record is an error rather than a benign
`NOT_RUN`/`NOT_VERIFIED`, which is what keeps a skipped evidence step from reading as a successful unsigned build, validates the CI identity it was invoked with (numeric run id, matching run URL,
branch and workflow name all present or none), and records the workflow run identity it was passed instead of a committed
value.  Any claim it cannot tie to evidence raises `ReportError`, which fails the report step: the report is derived from
artifacts, never written by hand.

The output directory contains the versioned portable folder and ZIP, `package-smoke.log`, `pip-install.log`, `pyinstaller-build.log`, `release-metadata.json`, `SHA256SUMS.txt`, and—when run in CI—`acceptance-report.json`, `installer-lifecycle.json`/`.md`, `signing-status.json`/`.md` plus the compiled setup executable. The manifest records the full source SHA, application version, exact Python/pip/PyInstaller versions, the *verified* Inno Setup package version with its provenance and the raw compiler file version as a separate diagnostic, and per-artifact filename, SHA-256 and byte size. `SHA256SUMS.txt` covers exactly those artifacts, so an operator can re-verify with `Get-FileHash -Algorithm SHA256` and `Get-Content SHA256SUMS.txt` without trusting any report.  `acceptance-report.json` keeps the four provenance claims apart and labels them as such: what the build produced (`provenance`), what this report recomputed from the release directory (`artifact_verification.status`), what the workflow re-measured on the runner, and what only an operator holding the downloaded bytes can confirm (`independent_reverification: NOT_VERIFIED` until someone does). Preserve the folder and evidence together; matching version strings and a single successful build are not reproducibility, which would require two independent builds compared by artifact hash.


The lifecycle step can fail while every one of its own assertions is behaving correctly, and the two
cases read differently.  When `installed_files` lists `unins000.exe` and `silent_uninstall` then reports
`FileNotFoundError: [WinError 2]` for that same path, the file was present at the check and gone at the
use; the record says so, waits two seconds, retries the launch once, and fails on the second refusal -
that is the designed outcome, and it is the reason a green run of the *same code* is not evidence about
a red one.  If the same detail adds `install tree holds 0 file(s)`, the whole `{app}` directory had
emptied between the smoke step's post-check (which reported the tree unchanged) and the uninstall, which
is an external removal rather than a packaging defect; the workflow's own install root sits under the
runner's `_temp` path and nothing in this repository deletes it.  Neither case may be resolved by
dropping the retry, the empty-`{app}` proof or the second-refusal failure: the correct response is to
re-run the identical SHA and record both attempts, or to treat the gate as failed.

### Windows-marker constraints in the build lock

Build-tool pins must satisfy the constraints their consumers declare *under Windows markers*. `pip install` on Linux silently ignores a `sys_platform == "win32"` requirement, so a clean Linux resolve of `requirements-lock.txt` plus `requirements-build.txt` proves nothing about the Windows build environment; that is how `pefile==2024.8.26` survived here although `pyinstaller 6.11.1` declares `pefile>=2022.5.30,!=2024.8.26` for `win32` and pip answers `ResolutionImpossible` on the build machine. Before changing a pin in either file, evaluate every dependency edge in a Windows marker environment (`sys_platform=win32`, `platform_system=Windows`, `os_name=nt`, `platform_machine=AMD64`) against the repository pins, and keep `tests/test_windows_release_gate_contract.py::test_windows_build_toolchain_satisfies_its_own_windows_markers` green: it records the constraint edges with their provenance (PyPI metadata for the pinned versions, retrieved 2026-10-10) and refuses a pin that violates one. A recorded edge whose consumer version changes must be re-recorded from PyPI metadata rather than relaxed.

### The build environment must supply its own setuptools

A Python 3.12 or newer virtualenv no longer seeds `setuptools`, and current `setuptools` releases no longer ship `pkg_resources`. Any build tool that still imports `pkg_resources` therefore fails at start-up in exactly the environment a release build uses, before analysis, before the bundle exists, and identically on any platform - the Windows gate is simply the only job that builds. The observed symptom is a `ModuleNotFoundError: No module named 'pkg_resources'` raised from a dependency's module scope (here `altgraph/__init__.py`, reached through `PyInstaller.building.build_main`), not a PyInstaller error about the application. `requirements-build.txt` records both halves of the resolution: `setuptools==84.0.0` is pinned explicitly so the provider set is not decided by a transitive resolution, and `altgraph==0.17.5` is the release that stopped importing `pkg_resources`. When a build tool needs a removed stdlib-adjacent module, prefer the tool version that dropped the import over pinning an ancient provider, and state which was chosen and why in the lock file.

### Inno Setup toolchain identity (M42.2)

The compiler's own executable resource is not an identity: the `ISCC.exe` delivered by the pinned Chocolatey package carries no
`VS_VERSIONINFO` block, so `VersionInfo.FileVersion` reports `0.0.0.0`.  Publishing that value as the verified toolchain version is
what made the M42.1 manifest misleading while the workflow text was in fact correct.  The rules now enforced are:

- `packaging/inno_setup_version.txt` is the single source of the intended version.  The workflow installs from it, the build script
  validates against it, and the acceptance report compares the published manifest with it, so a request and a record cannot drift
  apart silently.  Nothing else in the release tooling contains a version literal.
- The identity that gets published is read back from the *installed package specification*
  (`%ProgramData%\chocolatey\lib\innosetup\innosetup.nuspec`, falling back to a local package-manager query).  A caller-supplied
  `-InnoSetupPackageVersion` is a cross-check on that read-back; disagreement aborts the build, and if no read-back is possible the
  value is recorded as `operator-attested` with `innosetup_identity_verified: false`.
- `release-metadata.json` `build_tools` therefore distinguishes `innosetup_package_version` (what was verified) from
  `innosetup_compiler_file_version` (the raw executable resource, kept only as a diagnostic and allowed to be `0.0.0.0` or
  `UNAVAILABLE`) and `innosetup_version_source`.  The manifest schema moved to `drillmaster-release-artifacts/v2` because the
  semantics of the Inno Setup field changed; `v1` manifests are refused by the report generator rather than reinterpreted.
- `0.0.0.0`, `NOT_BUILT`, empty, all-zero (`00.00.00`), and malformed (`6.7`, `6.7.x`, `latest`) values are rejected by
  `packaging/release_metadata.py` when an installer is being published, and independently re-validated by
  `packaging/acceptance_report.py` (which additionally rejects an unverified or self-contradictory identity and any disagreement
  with the pinned version).  `NOT_BUILT` remains valid only for `-PortableOnly`, where no installer exists to attribute.

A local build on a machine where Inno Setup was installed by its own installer (no package metadata) must pass
`-InnoSetupPackageVersion <verified version>`; the resulting manifest is marked operator-attested and the acceptance report will
refuse to treat it as release evidence.  That refusal is intended.

### Installed-application lifecycle evidence (M42.2, contract extended in M42.3)

`python packaging\windows_release_evidence.py lifecycle --installer <Setup.exe> --release-metadata <release-metadata.json>
--app-version <version> --work-root <disposable dir> --json-out <installer-lifecycle.json>` performs, in one disposable tree
(`install/`, `userdata/`, `smoke/` under the work root; there is no separate install-directory flag):
silent install (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR= /LOG=`), presence of `DrillMaster.exe` and `unins000.exe`, an
installed-executable `ProductVersion` comparison against `core/version.py`, a run of the installed
`DrillMaster.exe --package-smoke` with isolated data/log/backup roots and cleared bootstrap credentials, a before/after manifest of
the install directory proving nothing was written into it, a non-interactive uninstall that is then waited on (the Inno
uninstaller can return before deletion finishes), removal of the application files, survival of a synthetic user-data sentinel that
lives outside `{app}`, and cleanup of the work root in a `finally` block so a mid-sequence failure still cleans up.  It verifies the
installer's SHA-256 against `release-metadata.json` before executing it and refuses a portable ZIP as the target, so an inner
bundle path can never be confused with the outer archive.

Two claims are deliberately kept apart.  The uninstall *process* exit code is one step (`silent_uninstall`); whether the
application files actually disappeared is a second one (`install_files_removed`), because a zero exit code from an uninstaller that
copies itself to a temp location and returns early is not deletion evidence.  A zero exit code from the installed executable is
likewise not proof that it smoke-tested: `installed_smoke` requires the `PACKAGE_SMOKE_OK` marker that `app.py:run_package_smoke()`
emits into the application log *and* to stdout, and refuses a run carrying a `FATAL` or `Traceback` marker in either channel - an
executable that prints help and exits 0 fails, and so does one that exits 0 silently.  The log channel is not a convenience: a
frozen **windowed** build has no console, `print` is a no-op there, and requiring stdout alone turned a real green gate red on
exactly that platform, which is why `success_marker_channel` records where the marker was found (`stdout`, `application-log` or
`none`).
The `--expected-sha256` argument is optional and, when supplied, must agree with the manifest (disagreement exits `2`); the
manifest is the authority, so the lifecycle can never be run against an unbound binary.

The install tree is diffed in **both** directions.  `installed_smoke` records `new_files_in_install_dir`,
`changed_files_in_install_dir` and `deleted_files_in_install_dir`, and its PASS sentence states which of the three it checked
rather than claiming an unchanged tree on the strength of two of them; a deletion is reported, not treated as a failure of its own,
because a PyInstaller one-folder bundle legitimately creates and discards transient paths while it runs.  That channel exists
because two gate runs failed with `silent_uninstall` unable to launch `unins000.exe` although the preceding step had proved it
present, and the record could not distinguish "never created" from "created, then taken away while the application ran".  The
lifecycle therefore states the sequence explicitly - `unins000.exe was present after install (installed_files) and is absent now`,
with a bounded listing of what `{app}` actually holds and the installer's own log tail - and grants the launch exactly **one
bounded retry**: `unins000.exe was listed but could not be launched` is followed by a two-second settle and a re-listing, and
`uninstall_launch_recovered` publishes that sequence when the retry worked.  Nothing is excused by it.  A second refusal fails the
step, a file that is gone after the settle stops the retry rather than provoking a guess, and in every case the uninstall must
still empty `{app}` for the lifecycle to pass.

Diagnostics are bounded and redacted: secret-valued environment variables are stripped before anything is written, and log tails
are truncated.  `acceptance-report.json` folds the result in as `installed_lifecycle_status` and its `decision` distinguishes three outcomes -
every mandatory dimension passed, a mandatory dimension did not run, or a mandatory dimension ran and failed (`WINDOWS_AUTOMATION_FAIL;
INSTALLED_LIFECYCLE_FAIL; ...`) - because publishing `WINDOWS_AUTOMATION_PASS; INSTALLED_LIFECYCLE_NOT_RUN` over a failed lifecycle was
itself an overstatement, and `decision_basis` records which statuses were blocking and refuses to publish `PASS` when the
evidence file is absent, when a step inside it did not pass, when the lifecycle did not verify the installer hash it executed, or
when the recorded installer hash disagrees with the digest the report recomputes from the published artifact.

What this proves: the shipped installer installs, the installed binary is the built binary, the installed binary starts and writes
only outside its own directory, and it uninstalls without taking user data with it.  What it does not prove: interactive
clean-machine behaviour, UAC/elevation experience on a workstation, an upgrade over a previous installation (that needs two
*different* installers, and is never simulated by running one installer twice), retention of a real operator profile, or operator
acceptance.  Those remain the manual procedure below.

### Lifecycle failure forensics (M42.7)

Two exact-SHA gate runs of byte-identical packaging code disagreed about the uninstall: `a742170`
passed every lifecycle step, while `6c4979f` failed `silent_uninstall` with `WinError 2` after the
pre-launch listing had already said `unins000.exe` was there.  The published detail for the failure was
`install tree holds 0 file(s): nothing`, and the difficulty is exactly that sentence: a directory that
was deleted, a directory that an uninstall emptied, and a tree that was never populated all render the
same way, because `snapshot()` reports an empty mapping for a missing path and for an empty one.  The
record therefore could neither reproduce the event nor dismiss it.

The lifecycle step now samples the filesystem at each point of use and publishes the samples under
`installer-lifecycle.json` -> `diagnostics.uninstall_forensics`, keyed by the moment they were taken:

* `pre_launch` - before the first launch attempt, on every run, green included;
* `uninstaller_absent_before_launch` - when the pre-check itself finds the uninstaller gone;
* `after_refusal_1` / `after_refusal_2` - immediately after each refused launch, carrying the
  `FileNotFoundError` (or other) `errno` and `winerror` read off the exception object;
* `after_settle` - after the single bounded 2-second settle and re-listing;
* `launch_error_<ExceptionName>` - for a refusal that is not a missing file.

Each sample holds, for the work root, the install directory, its parent, and the uninstaller: whether
the path resolves, whether it exists, whether it is a file or a directory, size and modification time,
the device and inode the OS reported, and - on Windows only - `st_file_attributes` with a
`reparse_point` flag (a symlink or junction reparse point is recorded as such, never followed
silently).  The uninstaller's SHA-256 is computed while it is still present, so "listed, hashed, then
refused" is distinguishable from "a zero-length file the OS will not start"; files above the 64 MB
bound are reported as unhashed rather than skipped silently.  The install tree's entry count and first
eight names, the existence, size and bounded tail of the installer and uninstaller logs, and whether
the user-data sentinel survived, complete the sample.  Together these distinguish every case the mission
named: never present; present and refused for another reason; present and then gone; the parent or work
root gone; emptied by an uninstall that really ran (its log survives even when the uninstaller does
not); or cause undetermined at the permissions available.

Two limits are recorded rather than papered over.  The step is `bound` and redacted like every other
diagnostic - `_redact_tree` removes bootstrap credential values from log tails, no environment is
dumped, and no path content beyond the uninstaller digest is published - and `host_side_evidence`
states that no Windows event log, Defender quarantine record or security-audit entry is read, because
those need privileges the gate does not have and must not have.  An external removal can therefore be
observed and bounded, never attributed: naming antivirus as the cause of `6c4979f` would be a guess
wearing the gate's formatting.

On the current tip (`8f71beb`, records-only delta over the failing run's ancestry) the same code passed
lifecycle, so the failure did not reproduce and no code defect was found in the lifecycle logic: the
retry policy, the single bounded settle, the refusal to launch a second time once the file is gone, the
`{app}`-emptied requirement and the exit-code-is-not-success rule all behaved as specified, which is why
they are unchanged here.  The diagnostics exist so that the *next* occurrence is attributable from the
published record alone, and REL-13 stays `OPEN` until it is.

#### Bounded, handle-anchored log reads (M42.8; confined to a handle in M42.9)

The sampler above reads installer and uninstaller logs *while a failure is being described*, which is
the worst possible moment for two things it used to do: it read each log whole and sliced the string
afterwards, so the cost of explaining a failure scaled with the size of the thing being explained; and
a read error (`PermissionError`, or the file disappearing between the listing and the read) escaped and
became the report.  Both are fixed in one shared reader, `_bounded_tail`, and every caller of the old
`_tail()` goes through it - there is no second copy of the policy to drift.

* **The bound is on the read, not on the string, and it is a ceiling.** `LOG_TAIL_BYTES = 512 KiB`.
  One handle measures itself with `seek(0, END)` / `tell()` (no second `stat()` for the size), rewinds to
  `size - cap`, and asks for `cap + 1` bytes, so at most 524 289 bytes leave the disk per call whether the
  log is 1 KB or 1 GB.  `bytes_read` is what that call returned - a measurement, not a restatement of the
  cap.  A caller may pass a *smaller* `byte_limit`; it may not pass a larger one, and that is refused with
  `ValueError` before the file is opened rather than clamped, because a clamped request would report a
  smaller read than the caller believes it asked for while an honoured one is the unbounded read this
  constant exists to prevent.  The policy is therefore `MAX_TAIL_READ_BYTES = cap + 1` for every call,
  measured in the test suite against the real opens instead of against a returned string length.
* **A window is treated as a window, and its edge is examined.** Decoding is UTF-8 with
  `errors="replace"`, so a cut landing inside a multi-byte character costs one U+FFFD rather than a
  `UnicodeDecodeError` raised during a failure report.  Whether the window's first line is a fragment is
  answered by the byte *before* the window, which is what the one spare byte of the bound is spent on: a
  window that happens to start on a line boundary keeps that line (`dropped_partial_first_line=false`),
  and a window that starts mid-line drops the fragment only when something else remains to show - a
  one-line window keeps its fragment and publishes `first_line_is_fragment=true` instead of an empty
  tail, because losing the only evidence the failure had is not a cleaner answer than labelling it.
  Growth is detected on the same handle by re-seeking to its end and comparing with the measured size
  (`grew_during_read`), which is exact, costs no bytes, and does not depend on a single spare byte being
  enough to notice an append.
* **The states are named, and they are six different things.** `complete`, `truncated`, `empty`,
  `absent`, `unreadable`, `skipped_unsafe_path`, each with `size_bytes`, `bytes_read` and, where
  relevant, `read_reason`.  A truncated result carries its elision marker *inside* the published text
  (`[only the last N of M bytes were read; older content was not inspected]`), so a suffix can never be
  presented as "the log", and the text is clipped to 400 characters again for publication - a bound
  independent of the read bound, because 512 KiB of tail is as unpublishable as 512 MiB of it.
* **Reading cannot become the story.** `log_state()` keeps four facts apart - present, measurable,
  readable, read - and catches every `OSError` the read can raise: a log deleted between the listing and
  the read is recorded as `absent` while the launch error stays the finding, and a refusal is recorded
  as `unreadable` with the exception class and its `errno`/`winerror` copied off the object.  No
  traceback and no exception text is transcribed, because a Windows path can carry a credential from the
  launching environment; the same redaction that covers every other diagnostic runs over these samples.
  A defect inside the sampler itself publishes `state="sampler_failed"` plus `diagnostics unavailable
  (...)` in the detail line, and the lifecycle conclusion is still computed from the filesystem
  evidence: a broken diagnostic changes no verdict, in either direction.
* **The classification is platform-free, not Linux-flavoured.** POSIX raises `IsADirectoryError` where
  Windows raises `PermissionError` for the same attempt to open a directory, and the first exact-SHA run of this
  code caught the difference on the Windows runner.  The reason published for a directory is now
  "not a regular file" on both platforms, derived from the fact rather than from the exception name, and the test
  simulates the Windows exception on any host so the guarantee is pinned everywhere it is run.  A byte count that
  had assumed LF line endings in one test was replaced by the size the handle measured.

* **Reads stay inside the evidence root, and the proof is the handle.** Every lifecycle log read passes
  `permitted_root=work_root`, and the same boundary covers the uninstaller digest and the sentinel read.
  M42.8 checked the *name* (`resolve()` it, refuse if it left the root) and then opened it - which is a
  check-then-use window, closed only by deciding after the object is open.  On POSIX the file is opened
  component by component relative to a descriptor for the root, with `O_NOFOLLOW` on every component and
  `O_NONBLOCK` on the last one, and the object is then judged by `fstat` on that descriptor: `S_ISREG` or
  nothing is read, so a FIFO planted where a log is expected is refused rather than awaited, and a name
  swapped for a link between any earlier look and this open fails the open with `ELOOP` instead of
  yielding somebody else's bytes.  On Windows there is no descriptor-relative open and the CRT's
  `O_NOFOLLOW` is not a guard against junctions or symlinks, so the verdict moves onto the handle:
  `GetFileType`, `GetFileInformationByHandle` (attributes, volume serial, file index) and
  `GetFinalPathNameByHandleW` are read after the create, the final path must lie under the root's own
  final path on the root's volume *and* be the path the name implied, and a reparse attribute bit on the
  opened object is a refusal in its own right - which is what catches a junction that lands inside the
  root on a different file than the one that was named.  Any unreadable metadata or unavailable API is a
  refusal, never a fallback to opening the name again.
* **The root is anchored too, and the limits are stated.** `run_lifecycle` records the identity of the
  work root (`_directory_identity`: device and inode, or volume serial and file index) when the run takes
  the directory, and every anchored open compares the object it reached against that record; if the root
  itself has been deleted and re-created or re-pointed, the reads stop with a message saying so instead of
  silently confining themselves to the replacement.  Three limits are part of the claim, not exceptions
  to it: `CreateFileW` resolves a link before the handle exists, so the Windows guarantee is *use-then-verify
  on the verified handle* and not an atomic open-by-descriptor; a create on an object type that blocks
  would block before it can be classified (no ordinary file or directory can be named that way, since
  pipes live in `\\.\pipe\`, but a hostile mount could, and `O_NONBLOCK` has no Windows counterpart); and the
  what this closes is the window between a name-based look and the open, on both platforms and for the
  shape that motivates it: a re-pointed name can no longer send the bytes anywhere, because no content
  decision is taken from a name.  What it does *not* claim, on either platform, is that an actor who can
  rename whole directories inside the private work root cannot substitute a different file that is also
  inside that root - the confinement rule is about the boundary, and a same-root substitution stays
  inside it, so no version of this text says the race is eliminated by checking harder.  On Windows the
  guarantee is explicitly use-then-verify on the opened handle rather than an atomic open-by-descriptor.
  `st_file_attributes`/`reparse_point` is recorded on Windows and never simulated elsewhere, and simulated
  symlinks are never counted as native junction coverage.  No event-log, Defender or security-audit entry is read, so an outside
  actor can be bounded but not named.
* **One sample, one filesystem moment.** `install_dir_entries.count` and its first eight names now come
  from a single `snapshot()` call instead of two listings, so a concurrent create or delete cannot make
  the published count disagree with the names printed next to it.  The sampler remains read-only: it
  creates, changes and removes nothing (its only writes are inside the test fixtures that plant hostile
  shapes for it to refuse), which is what makes sampling a live install tree safe at all.
* **A digest is of the object, not of the name.** The forensic uninstaller hash no longer calls
  `sha256_file(path)`: it hashes through the anchored handle, and `MAX_FORENSIC_HASH_BYTES` is applied to
  the size that same handle reports, so size, bound and digest describe one object.  An object that is not
  regular, is outside the root, or cannot be classified publishes `hash_state` `unreadable` or
  `skipped_unsafe_path` with a `hash_reason` and publishes no digest at all - never the digest of
  something else nearby.  Where the platform can see that the inode behind the name differs from the one
  that was stat'd, `replaced_before_open` is published: the race caught and recorded, not repaired, and
  never allowed to change the lifecycle conclusion.  The streaming helper lives in `release_metadata` as
  `sha256_stream`, with `sha256_file` a one-line wrapper over it, so the repository still has exactly one
  implementation of the digest.

`drillmaster-installer-lifecycle/v1` is unchanged - the fields added by this pass are additive inside
`diagnostics`, so no published record had to be reinterpreted.

##### Reading a lifecycle failure without a rerun (REL-13 procedure)

The gate cannot re-run its own history: `POST /actions/runs/<id>/rerun`, `.../rerun-failed-jobs` and
`POST /actions/workflows/<file>/dispatches` all answer `403 Resource not accessible by integration` to
the credential this automation holds.  That is the boundary, not a workaround to simulate: repeatability
comes only from *other* runs of the exact SHA - a new push, or a repository administrator re-running a
specific run.  Everything below needs no access beyond the public run and its artifact.

1. List the runs for the SHA under review (`GET /repos/.../actions/runs?head_sha=<full sha>`), read the
   `Installed-application lifecycle smoke` step conclusion, and download that run's
   `drillmaster-windows-<sha>` artifact: installer, portable archive, `release-metadata.json`,
   `SHA256SUMS.txt`, the signing record, and `installer-lifecycle.json`.  Nothing in it is executed to
   read evidence.
2. In `installer-lifecycle.json`, open `diagnostics.uninstall_forensics.samples` and take the moment that
   matches the failing step: `pre_launch`, `uninstaller_absent_before_launch`, `after_refusal_1`,
   `after_refusal_2`, `after_settle`, or `launch_error_<Class>`.
3. Classify from the fields, never from the sentence beside them:

| shape | what the sample has to show |
| --- | --- |
| install tree removed | `install_dir.exists=false`, `install_dir.is_dir=false`, while `parent_dir.is_dir=true` |
| tree emptied by a real uninstall | `install_dir.is_dir=true` with `install_dir_entries.count=0`, and `uninstall_log.read_state="complete"` with completion text in its tail |
| uninstaller gone, application still installed | `install_dir.is_dir=true`, `count>0`, `uninstaller.exists=false` |
| listed but launch refused | `uninstaller.exists=true` and `hash_state="hashed"` at the same instant, with `launch_error.class`, `errno`, `winerror` (2 = path component missing, 5 = access denied, 267 = directory name invalid) |
| uninstall genuinely completed | `{app}` emptied, `uninstall_log` present with its lines, the user-data sentinel still in place, work root removed by cleanup |
| evidence collection itself failed | `state="sampler_failed"` and `read_state`/`bytes_read` for the logs that were still readable; the conclusion is the lifecycle one, unchanged |

4. What the record cannot settle is host-side, and only an operator with runner access can settle it:
   file-system audit or Defender quarantine entries for the work-root path, plus the runner's own job
   log, which this workspace cannot fetch (transport to the log host terminates the connection).
   Naming antivirus as the cause without those records would be a guess wearing the gate's formatting.

Required from the owner for a definitive close: the artifact of one failing run *and* one passing run of
the same or adjacent SHA, so the two samples can be diffed; runner-side retention long enough to fetch
them; and, if attribution is wanted rather than classification, the audit or quarantine entries for the
work-root path quoted above.


### Signature status (M42.2; evidence binding corrected in M42.3; record contract and diagnostics hardened in M42.4)

`python packaging\windows_release_evidence.py signing --release-metadata <release-metadata.json> --json-out <signing-status.json>`
queries Windows' `Get-AuthenticodeSignature` for exactly two executables: the compiled setup executable in the release directory,
and `DrillMaster.exe` **extracted from the portable archive listed in the same manifest**.  The release directory also contains a
loose `DrillMaster-1.0.0/DrillMaster.exe` copy left by the build; that copy is not examined, because nothing binds it to the
published ZIP.  Extraction happens only after the archive's own SHA-256 has been recomputed and matched against the manifest, the
member must be uniquely identified and free of `..` or absolute paths, its declared and actual size are bounded, the copy is made
inside a temporary directory that is deleted afterwards, and no release artifact is mutated.  A manifest whose archive digest
disagrees, an archive with no such member or with two of them, is a refusal (`ValueError`), not a fallback to a convenient file.

Each row records its own `sha256`, and the inner row additionally records `container_archive`, `container_archive_sha256` and
`container_member`, so the digest of the executable and the digest of the file that contains it cannot be conflated.  Container
archives are recorded as `NOT_APPLICABLE` and excluded from the aggregate, because "a ZIP is not signed" is not a statement about
trust.

**Four vocabularies, kept apart** (defined once, in `packaging/release_metadata.py`; the querying tool and the report both import
them, and `tests/test_windows_release_gate_contract.py` refuses a second definition):

| layer | values | meaning |
| --- | --- | --- |
| raw Windows answer (`raw_status`, verbatim) | `Unknown`, `NotSigned`, `HashMismatch`, `NotTrusted`, `Valid`, `UnknownError`, plus the equivalent spellings `Ok`, `NottrustedForData`, `NotGenuineSignedData` | what `Get-AuthenticodeSignature` actually replied, before any interpretation |
| normalized per-file (`status`) | `PASS`, `UNSIGNED`, `FAIL`, `UNKNOWN`, `NOT_APPLICABLE` | what that answer *means* under one shared rule: `Valid`/`Ok` -> `PASS`, `NotSigned` -> `UNSIGNED`, a mismatch or untrusted chain -> `FAIL`, `Unknown*` and any spelling with no rule -> `UNKNOWN` |
| aggregate of one run | `PASS`, `UNSIGNED`, `FAIL`, `UNKNOWN`, `NOT_RUN` | the fold over examined executables; `NOT_APPLICABLE` rows are excluded, nothing examined is `UNKNOWN`, never a fabricated `UNSIGNED` |
| report-level absence | `NOT_VERIFIED` | *no record exists to read*.  It is not an Authenticode state and never appears as a per-file or aggregate status |

Casing is normalised before the lookup on purpose: comparing raw Windows spellings used to let a legitimate `Unknown` fold into
`FAIL`, which reports an unattributable answer as if Windows had confirmed a signature problem.  An answer with no rule is
therefore recorded as `UNKNOWN` with `raw_status_recognized: false`, which says "our table needs updating" instead of inventing a
verdict either way.

Nothing in this step reads, prints or stores a private key, certificate file or password; only the *names* of credential-bearing
environment variables are recorded, so the presence or absence of CI signing credentials stays auditable without leaking anything.
Every diagnostic string the record publishes - including the captured stderr - is redacted against the values of those variables
before it is written.

#### The signing record contract (`drillmaster-signing-status/v2`)

The document names the bytes it describes: `release_metadata_sha256` (the digest of the exact `release-metadata.json` the run
read) and `source_sha` (the commit that produced them).  A `v1` record is refused rather than reinterpreted, and `validate_signing_document`
- called by the generator *before it writes* and by the report *before it reads* - refuses: an aggregate the per-file findings do
not support (a `PASS` while any row is `UNSIGNED`/`UNKNOWN`, a `FAIL` when every row is `PASS`, an `UNSIGNED` over a
`PASS`+`FAIL` mix, an `UNKNOWN` when the rows are determinate); a missing or unknown field at either level; a duplicate row; a
malformed digest or a negative size; a container row counted in the executable aggregate; `signature_bearing` contradicting the
status; an incomplete container binding; a `UNKNOWN` row without a reason; a diagnostic beyond the bound; and a `NOT_RUN` record
that also carries per-file findings.  The report then *verifies* the binding instead of trusting it: the row named as the shipped
installer must hash to the digest this report recomputed from the release directory, every container binding must name the published
archive with that archive's verified digest, and both executables must be present - so a stale record from another run, a record
about a different file, or a record that skipped the packaged executable is an error, not a finding.

#### Reading the cause of a signature state

`run_powershell` no longer treats a parseable payload as a complete answer.  The query script runs
`Get-AuthenticodeSignature -ErrorAction Stop` inside `try`/`catch` and publishes `QueryError`, so a statement-level failure that
still exits 0 reports itself; the harness attaches bounded, redacted `powershell_stderr` and the exit code whenever the channel is
non-empty; and a capability probe (`Get-Command Get-AuthenticodeSignature`) runs first and is
published as `harness` (`powershell_version`, `query_command`, `cmdlet_available`,
`signature_command_module`, `security_module_import`, `probe_usable`, and any probe error).  The
lookup and the import are separate steps of that probe on purpose: the first answers which command
this host can run, the second answers whether the module that owns it loaded, and neither may be
reported as the other.  A probe that
*positively* answers `missing` records that one cause for every file; a probe that itself failed is recorded and the real queries
still run, because a diagnostic must not become an authority that suppresses evidence.

Three facts are recorded, not two.  Whether the module imported, whether the cmdlet resolved, and whether the probe answered at
all are different observations, and only the second one may excuse the run from asking about each file:

| import | cmdlet lookup | what the record says | aggregate |
| --- | --- | --- | --- |
| `succeeded` | available | the per-file answer PowerShell gave (`PASS`/`UNSIGNED`/`FAIL`) | that answer |
| `failed` | available | the per-file answer, plus `security_module_import: failed` and its bounded message | the answer - the import complaint does not soften it |
| any | unavailable | `UNKNOWN`, with the cause stated as observed: import outcome and lookup result separately | `UNKNOWN` |
| any | unreported (probe broke) | the per-file answer if the queries answered, `probe_usable: false` regardless | what the queries answered |

An import anomaly therefore never produces `UNSIGNED`, `PASS` or `FAIL` on its own, and a missing cmdlet never produces a
statement about the files: it can only justify `UNKNOWN` with that cause.  Before this correction a single field carried both
meanings, and the row below shows why that mattered.

Confirmed on the first run of this instrumented harness (`windows-2022`, Windows PowerShell
5.1.20348.5622): the probe answered `cmdlet=missing`, and both executables were recorded `UNKNOWN`
with exactly that cause.  A profileless `powershell.exe -NoProfile -NonInteractive` session does not
auto-load the module that owns `Get-AuthenticodeSignature`, so the query statement failed while the
script still exited 0 - which is the mechanism that had made the state unattributable.  Both scripts
now begin with an explicit `Import-Module Microsoft.PowerShell.Security`.  That first remedy published a field named
`harness.module_import`, computed from the *command lookup* rather than from the import, and reported the import's own failure text
nowhere: a record reading `cmdlet=missing module_import=failed` proved only that the cmdlet did not resolve, and the wording invited
- and in the M42.4/M42.5 checkpoint did cause - the inference that the import itself had been refused.  The attribution was wrong,
not the observation.  The probe now imports inside `try`/`catch`, so `security_module_import` is the import outcome,
`security_module_import_error` carries the host's own bounded message when it failed, `cmdlet_available` is the lookup result, and
`query_command` remains which command the queries will use.
If a future run reports `cmdlet unavailable` with `security_module_import: failed`, the runner image - not this repository - is what
cannot answer, and the finding is then a Windows-host limitation recorded as `UNKNOWN` with its cause, never as `UNSIGNED`; with
`security_module_import: succeeded` the same `UNKNOWN` instead says the module loaded and the cmdlet still did not resolve, which is
a different host question and is now distinguishable from the log alone.

That last reading - "the runner image is what cannot answer" - is corrected here rather than deleted, because a later reader has to
be able to see what the evidence was taken to mean before the cause was found.  The host *could* answer; the launch environment
prevented it, and the launch environment is this repository's own.  Every step of the Windows workflow runs under `shell: pwsh`,
which is PowerShell 7, so `PSModulePath` reaches the Python process carrying PowerShell 7's module directories ahead of the ones
Windows PowerShell ships with.  `run_powershell` passed `dict(os.environ)` to the child, so those directories reached
`powershell.exe` - Windows PowerShell 5.1 - and its `Import-Module Microsoft.PowerShell.Security` resolved the *PowerShell 7* copy of
the module.  Since PowerShell 7.3 that manifest processes `Security.types.ps1xml`, whose
`System.Security.AccessControl.ObjectSecurity` type data duplicates members .NET Framework already provides on 5.1; the import is
refused with `FormatXmlUpdateException`, the module never loads, and every cmdlet it owns - `Get-AuthenticodeSignature` among them -
becomes unresolvable.  That is the observed pair exactly: `security_module_import: failed` with the host's own extended-type-data
message, and `cmdlet: missing` beside it.  The fix is `windows_powershell_environment`: the child is started without `PSModulePath`
(the comparison is case-insensitive, since Windows environment names are), so Windows PowerShell rebuilds its own default module
path from the registry and finds version 3.0.0.0 of the module instead of the incompatible 7.x one.  Nothing else in the parent
environment is touched - the caller's other settings are not this function's business - and the query still travels by
`DRILLMASTER_TARGET_PATH` rather than being interpolated into the script.  The isolation is published, not assumed: the parsed
payload carries `powershell_module_path_isolated` and the signing harness carries `module_path_isolated`, so a future
`cmdlet: missing` can be attributed to a host that was already isolated rather than to a launch nobody can see.

The confirmation this paragraph was waiting for arrived on the first Windows run after the correction, and it is worth stating what
it showed because it is what makes the diagnosis a finding rather than a plausible story.  On the *same* Windows PowerShell
(`5.1.20348.5622`) the probe now reports `security_module_import=succeeded` and `cmdlet=available`, both executables are recorded
`UNSIGNED` with raw status `NotSigned` and the host's own "not digitally signed" message, the container row is still
`NOT_APPLICABLE`, and the aggregate is `UNSIGNED` instead of `UNKNOWN`.  Nothing was promoted to get there: no missing command was
relabelled, the query genuinely ran, and the `Signature state needs review` warning that used to accompany `UNKNOWN` is correctly
absent, because `UNSIGNED` is the recorded policy outcome rather than a malfunction.  `UNSIGNED` is still not a trust verdict - it
says the executables carry no Authenticode signature, which is the intentional build configuration, and owner decision A (obtaining
a signing identity) is untouched.  Had the next run instead still reported `cmdlet: missing` with the isolation published as
applied, the launch environment would have been only part of the cause and the records would have said so rather than carrying the
diagnosis forward as settled.

Those fields are published where a reviewer can read them without artifact access: in `signing-status.json`, in the job console line
the tool prints (`status`, `harness`, and a `reason` for every non-`PASS` row), in the step summary under `Authenticode query
environment`, in the single `Signature status` annotation (now `aggregate; ps=... cmdlet=...; file=STATUS/raw [reason]`), and as a
`Signature state needs review` warning whenever the aggregate is `UNKNOWN` or `FAIL`.  `UNSIGNED` is only noticed, because it is the
recorded policy outcome, not a malfunction.

#### What the gate does with a signature state

A signing *state* - including `FAIL` for a `NotTrusted` or `HashMismatch` result - is recorded and annotated but never reddens the
packaging gate, because whether the release is signed is an owner decision about distribution trust.  What
does fail the step is an evidence failure of its own: a signing run that produced no record, a record that cannot be parsed
(annotated as `Signature record malformed`), or a record that violates its own schema.  Two different situations are deliberately
handled by two different policies: a Windows host that *cannot answer* still produces a valid record whose every executable row is
`UNKNOWN` with the reason, while a run whose record *cannot be constructed* (disagreeing archive digest, ambiguous or unsafe member,
no manifest) produces no record and fails.  The step snapshots `$LASTEXITCODE` and ends with an explicit `exit 0`, because the
Actions `pwsh` wrapper would otherwise propagate whatever the last native command returned.

**`UNSIGNED` and `UNKNOWN` are different facts, and both are published.**  `signing_configured_in_build: false`, no `SignTool` or
`SignedUninstaller` setting in `packaging/DrillMaster.iss`, and no certificate material in the repository describe the *build
configuration*: this release is intentionally unsigned.  The aggregate describes *what the query observed*: on the shipped candidate
it was `UNKNOWN`, which is a statement about the evidence, not a restatement of the policy.  One is never rewritten into the other.

Producing a valid signature requires an owner-controlled code-signing certificate (or a hosted signing service) and a signing step
in `packaging/build_windows.ps1`; `packaging/DrillMaster.iss` sets no `SignTool` and no `SignedUninstaller` override today, and the
report records `signing_configured_in_build: false` accordingly.

## Re-verifying a downloaded artifact yourself

A CI annotation, a job log, or this runbook is not byte-integrity proof of the file in your
Downloads folder: the artifact endpoint, the log endpoint and the CI summary all describe bytes
that were uploaded, not the bytes you now hold.  Nothing in this procedure requires the repository,
Python, or the application being installed, and it never executes a downloaded binary.  Run it in
a PowerShell session whose working directory is the folder you extracted the CI
`drillmaster-windows-<sha>.zip` into.

Obtaining that zip can itself fail in a way that says nothing about the package: the Actions
artifact and log endpoints redirect to Azure Blob storage, and a network that reaches
`api.github.com` but not `*.blob.core.windows.net` will list the artifact (id, name, size) and
then drop the TLS connection when fetching the bytes.  A release review environment reported
exactly that - an authenticated listing plus a valid signed download URL, and
`SSL_ERROR_SYSCALL` on the fetch - so a retrieval failure must be recorded as
`INDEPENDENT_ARTIFACT_REVERIFICATION=BLOCKED` with the transport error quoted, never as a
verification that passed and never as a missing artifact.

The same failure recurred on a later exact SHA, so it is a property of the review network rather than of
one run: DNS resolved, TCP 443 connected, and the TLS handshake was reset in every client variant tried
(`default`, `--http1.1`, `--tlsv1.2 --http1.1`, `-4 --http1.1`, `--no-alpn`) while HTTPS calls to
`api.github.com` from the same host succeeded minutes before and after.  A range request for the first
64 KB is the cheap way to learn this before committing to a full download, and resolving the redirect in
two steps - reading the `Location` header from the API, then fetching it with no credential attached -
keeps the token off the storage host and the signed URL out of any log.

```powershell
# 1. Integrity of the two published release artifacts, against the digests the build recorded.
$manifest = Get-Content -LiteralPath .\release-metadata.json -Raw | ConvertFrom-Json
foreach ($entry in $manifest.artifacts) {
  $path = Join-Path . $entry.filename
  if (-not (Test-Path -LiteralPath $path)) { "MISSING  $($entry.filename)"; continue }
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
  $size = [long](Get-Item -LiteralPath $path).Length
  $ok = ($hash -eq $entry.sha256) -and ($size -eq [long]$entry.size_bytes)
  "{0}  {1}  {2}B  sha256={3}" -f ($(if ($ok) { "MATCH  " } else { "MISMATCH" })), $entry.filename, $size, $hash
}
# 2. The checksum file must agree with the manifest and with the files, line for line.
$sums = Get-Content -LiteralPath .\SHA256SUMS.txt
$expected = @($manifest.artifacts | ForEach-Object { "$($_.sha256)  $($_.filename)" })
 Compare-Object -ReferenceObject $expected -DifferenceObject $sums |
   ForEach-Object { "SUMS DIFFERENCE: $($_.InputObject)" }

# 3. The executable inside the portable archive, bound to that archive's verified digest.  The
#    archive is expanded into a temporary directory and nothing there is executed.
$bundle = ($manifest.artifacts | Where-Object { $_.filename -like "*.zip" }).filename
$scratch = Join-Path $env:TEMP ("drillmaster-verify-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $scratch | Out-Null
Expand-Archive -LiteralPath (Join-Path . $bundle) -DestinationPath $scratch
$exe = Get-ChildItem -LiteralPath $scratch -Recurse -Filter DrillMaster.exe | Select-Object -First 1
if (-not $exe) { "NO EXECUTABLE MEMBER in $bundle" } else {
  "inner sha256=" + (Get-FileHash -Algorithm SHA256 -LiteralPath $exe.FullName).Hash.ToLowerInvariant()
  "container sha256=" + (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path . $bundle)).Hash.ToLowerInvariant()
  # 4. Authenticode as Windows sees it, on the copy you hold.  This is distribution trust, not
  #    a verdict on whether the application works.
  $signature = Get-AuthenticodeSignature -LiteralPath $exe.FullName
  "Status={0}  StatusMessage={1}" -f $signature.Status, $signature.StatusMessage
  if ($signature.SignerCertificate) { "Signer={0}" -f $signature.SignerCertificate.Subject }
}
Remove-Item -LiteralPath $scratch -Recurse -Force
```

Expected result for the current repository policy: both digests `MATCH`, no `SUMS DIFFERENCE`
lines, and `Status=NotSigned` for the executable and the installer.  A `MISMATCH` means the bytes
you hold are not the bytes the gate examined, and no statement in `signing-status.json`,
`acceptance-report.json` or a job annotation applies to them.  `Status=NotSigned` is the
intentional, documented state - see `signing_configured_in_build` - not a corruption finding.  Do
not run `DrillMaster.exe` or the setup executable to "check" the download; run the installer only
on a disposable machine, through the interactive procedure below, after the digests match.

## Acceptance register (owner-facing)

Each row is a decision or an acceptance activity that repository automation cannot supply.  A
green Windows gate proves the rows marked *automation* only; every other row stays `NOT_RUN` or
`OWNER_DECISION` until the evidence named in it exists outside this repository.

| id | item | prerequisite | required evidence | pass condition | fail / open condition | owner | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REL-01 | Internal packaging gate on the exact SHA | final commit pushed | Source and Windows workflow runs whose `headSha` equals that SHA | both conclusions `success` on the identical SHA | any other SHA, a cancelled run, or a run whose annotation cannot be read | repository maintainer | automation only; see the mission report for the current SHA |
| REL-02 | Distribution trust (code signing) | Decision A below | certificate or hosted-signing procurement, `SignTool` configuration, a `PASS` aggregate in `signing-status.json` | every examined executable reports `PASS` with a signer whose chain the target machines trust | `UNSIGNED` (policy), `FAIL` (broken/untrusted chain), `UNKNOWN` (unattributable) all remain open | product owner | `OWNER_DECISION` |
| REL-03 | Signature-state attribution closed | next exact-SHA run after M42.4 | `signing-status.json` `harness` block and the per-file `status_message`, readable from the annotation | the aggregate is `UNSIGNED`/`PASS`/`FAIL` - a determinate state - or `UNKNOWN` with a stated cause | a bare `UNKNOWN` with no reason is still the open blocker | repository maintainer | `PASS CONDITION MET` on `6f34bfa25ca415aa7f770a29aff2a6c1d5fb70ab` and recorded as such, with the history it supersedes kept whole.  That run's `Signature status` annotation reads `UNSIGNED; ps=5.1.20348.5622 cmdlet=available security_module_import=succeeded`, with both executables `UNSIGNED/NotSigned` and their host messages beside them, and the container row `NOT_APPLICABLE` - a determinate aggregate readable from the annotation without artifact access, which is exactly the pass condition above.  Every earlier record keeps its own `UNKNOWN` verdict, because that was the honest reading of the environment it ran in: since `58b3912` each stated a cause, M42.6 made it the right cause, and M42.11 removed the cause itself (the `PSModulePath` inherited from the PowerShell 7 parent that stopped Windows PowerShell loading its own Security module).  `UNSIGNED` is a configuration fact and not a trust verdict; this row is about attribution being possible, and it now is |
| REL-04 | Artifact byte-integrity re-verification | the downloaded CI artifact | the procedure above, run on the operator's machine | `MATCH` for both artifacts and no `SUMS DIFFERENCE` | any `MISMATCH`, or no independent run at all | reviewer holding the download | `NOT_RUN` in-repository (`NOT_VERIFIED` in the report).  Recorded 2026-10-11: an **external** reviewer ran the procedure above on the artifact published by source `a742170` (GitHub artifact `11696022238` of run `38122859040`, 321705858 bytes) and reported `MATCH` - outer container digest `3b85db6b0088ddde67bd3f2fc341f095874c03a3c37c368660343efc5a436b6d`, manifest `drillmaster-release-artifacts/v2` at `1.0.0`, installer `83259119B / b0676066d77ecbe0...17d40aba`, portable bundle `119941398B / 6e0e56580a6beb8d...c0f3586b`, `SHA256SUMS.txt` equal to the manifest entry set, signing-record manifest digest `e0170a4f3cc1821d2a953c4a4817f651f66e6d01e0838070779c2ad28547e756`, inner `DrillMaster.exe 21218228B / d143c8a33be8991325b21c6a6075bb812843be18ad0c93ad0728e51432d3ec2b`, both archives CRC-clean with no unsafe paths, symlinks, case collisions or special modes, one executable member, `UNKNOWN` signature aggregate agreeing with the manifest, nine PASS lifecycle steps, and `secret_leak_detected=false`.  That is `MATCH` for **those bytes only**: this workspace could not download them (the artifact host resets the TLS handshake), so no in-repository verification is claimed, the tip's artifact `11696578929` is unverified, and the report for the built artifact keeps `independent_reverification=NOT_VERIFIED`, which is correct for its own build.  **Recorded 2026-10-17 - `MATCH` for the current candidate, on independently downloaded bytes:** a reviewer working in a separate review environment (not this workspace, and not CI) downloaded the artifact published by source `ead0c7982b3b703622127006bf60c4451fe6027e`, recomputed its full digest, and reported `MATCH` for both inner artifacts with no `SUMS DIFFERENCE`, which is the pass condition above satisfied literally.  The bytes: outer archive 321,676,808 B with recomputed SHA-256 `aade53e1eefd32db0ebd94b75ebd246b379cbd4c170e545d2a4424fd38377151`, equal to the digest GitHub advertised for that upload; installer `DrillMaster-1.0.0-Setup.exe` 83,226,528 B / `4089052d006746410d3c8ce3e8e98135c695b43f2cdf82b6fa5573f6fde0b581`; portable archive `DrillMaster-1.0.0-windows-x64.zip` 119,941,399 B / `0e98babd5374ab3af9f589ca6b282f2bcd5bbc043dd538c7dc7b18a1175ab1d8`; each equal to `release-metadata.json` and to the run's published manifest.  `SHA256SUMS.txt` carried exactly the two rows the manifest declares, both matching, with no missing, malformed or extra rows.  Archive safety: 1,238 outer members and 1,236 members inside the portable archive, full CRC pass on both, no absolute, traversal, symlink, device, FIFO, duplicate or case-colliding entries.  The four `DrillMaster-M42-tests-*` and `DrillMaster-build-transcript-*` sidecars outside the release directory are declared workflow evidence, not unexpected members.  The embedded executable measured 21,218,228 B / `18b46c957dc6bfbe482699481e40ef33266b808c1259cc560143e4282247284e`, matching the `signing-status.json` row that binds it to that archive.  Cross-record: `release-metadata.json` hashed to `eee9d57ceca41b897eb13406f0d52e14584ed5551349cec60360d2fc6a9d4e67`, the signing record's `release_metadata_sha256` equals it, the acceptance report's signing evidence is bound to the same digest, all three name this source SHA, the acceptance report records the installed lifecycle as `PASS`, all nine `installer-lifecycle.json` steps are `PASS`, the signing aggregate is the determinate `UNSIGNED` with the Security module imported and the cmdlet available, and the acceptance report's external acceptance fields remain `NOT_RUN`.  No executable was run during the verification.  **Provenance, stated precisely:** this result belongs to the review environment that downloaded the bytes, not to this repository's CI and not to this workspace - the Arena egress path still cannot reach the artifact blob host (the TLS handshake is terminated with `SSL_ERROR_SYSCALL` and zero bytes while `api.github.com` answers in the same shell), so no Arena-local download is claimed.  What this workspace could and did do is confirm that every figure above agrees with GitHub's live artifact metadata and with the run's manifest annotation, both read directly, and that the verification's scope is exactly one SHA and one artifact.  It does not extend to any earlier or later artifact, and the CI-generated `acceptance-report.json` was produced before this download and rightly says `independent_reverification=NOT_VERIFIED` for its own build - the external result supersedes that state for the verified artifact without changing the meaning of the report |
| REL-05 | Reproducibility requirement | Decision C below | either a claim with two independent builds compared byte-for-byte, or the recorded `NOT_CLAIMED` | an explicit owner position, recorded in this file | a `PASS` gate silently read as reproducibility | product owner | `OWNER_DECISION` |
| REL-06 | POSIX permission policy | Decision D below | a documented position on mode bits for the portable ZIP on non-Windows extraction | recorded policy statement | absence of a statement | product owner | `OWNER_DECISION` |
| REL-07 | Clean-machine interactive install | a disposable Windows 10/11 x64 VM | the procedure under "Interactive installation procedure", with the VM image and installer SHA recorded | install, first run, sign-in, restart, and data-outside-`{app}` all confirmed by a named operator | any step unexecuted | field/QA owner | `NOT_RUN` |
| REL-08 | Upgrade and uninstall data retention | an earlier candidate installed first | steps 4-5 of the same procedure | prior test data readable, no second database, user data survives uninstall | not executed on a real upgrade pair | field/QA owner | `NOT_RUN` |
| REL-09 | Real DDR Excel acceptance | a sanctioned, non-confidential client DDR workbook | parser and database round-trip against that workbook, reviewed by an engineer | an engineer confirms the imported values and units | the synthetic workbook is `AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE` and never satisfies this row | business/technical owner | `NOT_RUN` |
| REL-10 | Real DDR PDF and MinerU acceptance | a licensed MinerU environment outside this repository | import of a real PDF with the opt-in path enabled | extracted fields reviewed against the source document | not provided or exercised by the Windows workflow | business/technical owner | `NOT_RUN` |
| REL-11 | Production database and field validation | approved test/prod separation, operator time | restore, concurrency, and field use on target hardware | operator sign-off naming the environment and SHA | no repository automation can substitute | operations owner | `NOT_RUN` |
| REL-12 | Open P6 owner decisions | none (they are decisions, not defects) | the six register entries carried forward from M36 | each decision recorded with its rationale | `NEW-P6-007`, `NEW-P6-008`, `NEW-P6-015`, `NEW-P6-020`, `NEW-P6-023`, `NEW-P6-024` remain open | product owner | `OWNER_DECISION` |
| REL-13 | Windows lifecycle step stability on the release runner family | any exact-SHA gate run | the `Installed-application lifecycle smoke` step conclusion together with `installer-lifecycle.json`, whose `silent_uninstall` detail carries the attempt count and the install-tree state at each attempt, and (from M42.7) `diagnostics.uninstall_forensics`, which samples the work root, the install directory, its parent and the uninstaller - existence, type, size, mtime, reparse-point attributes, digest, log tails, entry count and the exception's `errno`/`winerror` - at `pre_launch`, at each refusal, and after the settle, with each log tail a bounded read whose `read_state`/`bytes_read` say how much was inspected (M42.8) and no diagnostic error able to change the conclusion | the step concludes success on the SHA under review, with every recorded step PASS and `{app}` emptied | a step that fails after the recorded retry while an earlier run of byte-identical code passed is an environment condition on the runner, not a packaging pass: it stays open until the same SHA is re-run green or the instability is explained; the protections must not be relaxed to obtain green | repository maintainer with the infrastructure owner | `OPEN` (on `6c4979f` the install tree had emptied to 0 files before the uninstall was launched, while `a742170` - identical code, records-only delta - passed; recorded 2026-10-11: the published sentence could not separate an emptied tree from a removed one, the gate now samples both shapes as above, and the failure did not reproduce on `8f71beb`, where the same code passed lifecycle, so the cause stands as undetermined at the permissions the gate has and no protection was relaxed to reach that conclusion; from M42.8 the classification and the owner's next steps are the procedure above, which needs no rerun privilege to follow; recorded 2026-10-14: the shape recurred on a documentation-only successor of a green source SHA - the launch was refused with `winerror=2` while `uninstall_log` existed and the install tree held 0 file(s), so an uninstall completed without being attributable to the launch the gate made, while steps 1-5 of the same lifecycle and the whole regression suite passed; the code SHA it points at has its own fully green Windows run, and the workflow could not be re-run from the automation credential.  **Corrected 2026-10-14 (same day, in the M42.11 pass over this register):** the sentence this replaces paraphrased the closure test as "a run of the same code with the lifecycle step green".  That is not what this row requires, and it would have let a reader close the row on evidence the condition does not accept.  The condition is verbatim: *it stays open until the same SHA is re-run green or the instability is explained*.  The SHA that failed here is `9f7f47f06c90f6bb9787a52dc5af241756428bdc`, it was run once, and it has never been re-run - nor can it be from the automation credential, which is refused by `gh run rerun` and by the dispatch endpoint with `403 Resource not accessible by integration`.  The current tip `071118573de7ef1881ac8851877d33e78760885c` does satisfy the pass-condition column above: its lifecycle step concluded success with every recorded step PASS and `{app}` emptied.  But that is a different SHA from the one that failed, so the open condition still stands - a successor carrying byte-identical code is evidence *about the code*, not a re-run of the failing SHA, and this row does not accept it as closure.  Recorded later the same day: two further exact-SHA Windows runs have since taken the lifecycle step to success with every recorded step PASS and `{app}` emptied - one on a further documentation successor of the same code, and one on `6f34bfa25ca415aa7f770a29aff2a6c1d5fb70ab`, which changes the release tooling itself - so the instability has now failed to reproduce across three separate green runs while the single failing run remains unexplained.  That is evidence about reproducibility and it is recorded as such; it is still not a re-run of `9f7f47f06c90f6bb9787a52dc5af241756428bdc`, so the row stays `OPEN` and the residual is unchanged: an administrator re-running that run to green, or an explanation from someone with runner access.  **Recorded 2026-10-17 - the exact-SHA rerun was attempted and is refused by the platform, not by this automation:** both rerun endpoints were called against the failing run itself and both answered `403 Resource not accessible by integration` - `POST /actions/runs/<id>/rerun` and `POST /actions/runs/<id>/rerun-failed-jobs` - while the run still reads `completed / failure / attempt 1` and its timestamp is unchanged, so nothing was re-executed and no attempt was created.  Its lifecycle evidence is unaltered: `silent_install`, `installed_files`, `installed_version`, `installed_smoke` and `data_outside_install_dir` each `PASS`, then `silent_uninstall` `FAIL` with the uninstaller listed before launch and refused (`FileNotFoundError`, `errno=2`, `winerror=2`), the uninstall log present and the install tree holding 0 file(s).  Successor runs - three of them now green - are evidence about the code and are recorded as such, and none of them is a rerun of that SHA.  The row therefore stays `OPEN` on its own condition, and the residual is exactly one administrative action: a repository administrator with Actions permission re-runs that run, or the infrastructure owner supplies the runner-side explanation  **Recurrence, same day:** the identical shape then failed a *different* SHA - `2891f0f87bdb1100b503c052399dea993e048a66`, whose delta from the previous green tip is documentation plus one test - with steps 1-5 of the lifecycle `PASS`, `silent_uninstall` `FAIL`, the uninstaller listed before launch and refused (`FileNotFoundError`, `errno=2`, `winerror=2`), the install log present and the install tree already holding 0 file(s), while the regression suite (772 of 775 with three explicit platform skips), the build, the signing step and the acceptance report all passed.  That makes two failures of this shape across the runs of one code line, on SHAs whose deltas are records-only, and it is the strongest evidence yet that the condition is intermittent on the runner rather than a property of any commit - and it is still not an explanation, so the row stays `OPEN` and this occurrence is preserved as a failure rather than re-described) |

## Interactive installation procedure (manual; NOT automated by the workflow)

Use a disposable, supported, clean Windows 10/11 x64 VM or test workstation. Do not use a production operator profile or production database.

1. Record the VM image/build, Windows architecture, application source SHA, release version, installer SHA-256, operator, and test date.
2. Install the generated `DrillMaster-<version>-Setup.exe` using the intended privilege level. Launch the application and complete first-run credential setup with a new, unique test password. Confirm the app starts and the test account can sign in; do not record or attach the password.
3. Close and reopen the app. Confirm the test account still works and data/log/database paths are outside the installed program directory. Add a clearly synthetic test project/report only.
4. Install a subsequent candidate over the test installation. Confirm the test data remains readable and no second unexpected database is created.
5. Uninstall through Windows Apps/Programs. Verify the application is removed and user data remains available for explicit operator backup/removal; never imply that uninstall removes user data.
6. Record observed results and any deviations in a separately approved operator acceptance record. A CI package smoke or this checklist alone is not evidence that the steps were executed.

## Explicit external boundaries

- The synthetic workbook test is an automated parser/database scenario only. It is **not** real DDR Excel/operator acceptance.
- Real DDR PDF and MinerU execution are opt-in and are not provided by this Windows workflow. MinerU is not bundled; AI import remains disabled by default.
- No production database restore, field validation, engineering standards certification, or operator/business sign-off is performed by these jobs.
- `acceptance-report.json` reports Windows automation and separately marks these external items `NOT_RUN`. `release-metadata.json` identifies artifacts; it is not a suitability or standards-compliance certificate.

## Exact-SHA GitHub verification

After pushing the final commit to `arena/01a0ec23-drill-master`, verify that remote `HEAD`, local `HEAD`, the Source release gate, and the Windows release workflow all identify the same full SHA. Use Git for branch/status/SHA and `gh run list` / `gh run view <run-id> --json headSha,status,conclusion,workflowName,url` for workflow evidence. A successful Linux Source gate is not Windows evidence; a green Windows build is not interactive-install evidence.
