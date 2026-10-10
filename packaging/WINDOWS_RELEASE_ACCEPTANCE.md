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
  --signing-report (Join-Path $release 'signing-status.json')
```

Every command above is the same one the CI gate runs; the local lifecycle invocation needs administrator elevation because `DrillMaster.iss` declares `PrivilegesRequired=admin`, and it installs only into the throwaway `--work-root` you pass.

Pass the interpreter explicitly with `-PythonExe` whenever the environment's `python` is the one you intend to package with; that is what the CI gate does. `-PythonLauncher py -PythonVersion 3.12` remains available on a workstation where the Python launcher is registered, but note that the launcher resolves registry-registered runtimes only, so it can silently select a different Python than the one whose dependencies were tested.

The build refuses dirty source trees, requires an explicit Python minor version and verifies that the build virtualenv actually satisfies it, uses the locked runtime/build requirements, does not delete pre-existing release output, and keeps PyInstaller temporary work outside the repository. Use a new output directory for each build. The prior `-Python "py -3.12"` form remains accepted through a non-evaluated parser; new scripts should use `-PythonExe` or the separate launcher/version parameters. `-PortableOnly` deliberately omits installer compilation and cannot establish installer evidence.

### Failure diagnostics and text encodings

GitHub publishes at most ten `::error::` annotations per step, so a suite with more failures than that would otherwise hide the rest.  The regression step therefore runs `python packaging\junit_report.py --junit <report> --summary-out <markdown> --json-out <json> --annotations`: one annotation per failure up to the cap, an aggregate annotation that names the overflow, and a full Markdown table in the job step summary.  The parser reports test identities, exception names and `file:line` locations only, redacts anything that looks like a password, token or API-key value, and writes UTF-8 regardless of the console codepage so that printing a diagnostic can never become the second failure.  The step still propagates pytest's own exit code.

Repository source files contain UTF-8 Persian UI strings.  Any test or release tool that reads them must state `encoding="utf-8"`; the runner's default codepage (cp1252) raises `UnicodeDecodeError` otherwise.  `tests/test_windows_release_gate_contract.py` enforces this for every module in the Windows suite, verifies that the workflow still lists the required modules and existing files, keeps the disposable `RUNNER_TEMP` isolation and the Inno Setup pin, and confirms that the committed M42.1 checkpoint does not claim a CI result.

### Packaging stage diagnostics

The build step cannot emit a JUnit report, so it reports differently: it publishes `release_dir` to the job outputs *before* building (the evidence upload runs on `always()`, and a step that set that output only on success uploads nothing exactly when it matters), records a `Start-Transcript` file next to the release directory, and wraps every assertion in `try`/`catch`. The `catch` runs `python packaging\junit_report.py --annotate`, which emits one bounded `::error title=Windows packaging stage failed::` annotation containing the stage message plus the redacted tails of the transcript and `pyinstaller-build.log`, then re-throws so the step stays red. A packaging failure is therefore identifiable from the check run alone, even when the log and artifact endpoints are unreachable.
The dependency stage is logged the same way as the bundle stage: `pip install -r requirements-lock.txt -r requirements-build.txt` and `pip check` are teed into `pip-install.log` inside the release directory (which is uploaded on `always()`), their exit codes are captured individually, and the last thirty log lines are embedded in the thrown message so they reach the annotation. The release output directory and its emptiness guard are resolved before any log is written, so a refusal to overwrite existing output cannot be caused by the build's own diagnostics. An annotation that quotes a PowerShell transcript is produced only after `Stop-Transcript`; while the transcript is open, native command output may not have been flushed yet, and the tail then reads as a header and nothing else — which is exactly how one packaging failure stayed nameless for a run.

PowerShell handling matters here for two reasons. The step sets `$ErrorActionPreference = 'Stop'` so an error thrown inside `build_windows.ps1` terminates the step at the throw instead of being reported and then falling through into the artifact assertions (which would mislabel a build failure as "Frozen executable missing"). Inside the build script, the redirected PyInstaller pipeline runs with the preference temporarily relaxed and `$PSNativeCommandUseErrorActionPreference = $false`, because PyInstaller writes its progress log to stderr; under `Stop` that output can become a terminating `NativeCommandError` and abort a build that actually succeeded. The captured `$LASTEXITCODE` is the only build-status signal the script trusts.

`acceptance_report.py` re-hashes the portable ZIP and the setup executable from the release directory — streamed in 1 MiB blocks through the
single `release_metadata.sha256_file` helper, never `path.read_bytes()`, so a ~300 MB artifact is verified without loading it —
and checks each recorded byte size.  It reads `package-smoke.log`, re-validates (rather than copies) the Inno Setup identity
against the pinned version, folds in `installer-lifecycle.json` and `signing-status.json` when they exist, records
`NOT_RUN`/`NOT_VERIFIED` when they do not, validates the CI identity it was invoked with (numeric run id, matching run URL,
branch and workflow name all present or none), and records the workflow run identity it was passed instead of a committed
value.  Any claim it cannot tie to evidence raises `ReportError`, which fails the report step: the report is derived from
artifacts, never written by hand.

The output directory contains the versioned portable folder and ZIP, `package-smoke.log`, `pip-install.log`, `pyinstaller-build.log`, `release-metadata.json`, `SHA256SUMS.txt`, and—when run in CI—`acceptance-report.json`, `installer-lifecycle.json`/`.md`, `signing-status.json`/`.md` plus the compiled setup executable. The manifest records the full source SHA, application version, exact Python/pip/PyInstaller versions, the *verified* Inno Setup package version with its provenance and the raw compiler file version as a separate diagnostic, and per-artifact filename, SHA-256 and byte size. `SHA256SUMS.txt` covers exactly those artifacts, so an operator can re-verify with `Get-FileHash -Algorithm SHA256` and `Get-Content SHA256SUMS.txt` without trusting any report. Preserve the folder and evidence together; matching version strings and a single successful build are not reproducibility, which would require two independent builds compared by artifact hash.

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

### Installed-application lifecycle evidence (M42.2)

`python packaging\windows_release_evidence.py lifecycle --installer <Setup.exe> --release-metadata <release-metadata.json>
--app-version <version> --work-root <disposable dir> --json-out <installer-lifecycle.json>` performs, in one disposable tree:
silent install (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR= /LOG=`), presence of `DrillMaster.exe` and `unins000.exe`, an
installed-executable `ProductVersion` comparison against `core/version.py`, a run of the installed
`DrillMaster.exe --package-smoke` with isolated data/log/backup roots and cleared bootstrap credentials, a before/after manifest of
the install directory proving nothing was written into it, a non-interactive uninstall that is then waited on (the Inno
uninstaller can return before deletion finishes), removal of the application files, survival of a synthetic user-data sentinel that
lives outside `{app}`, and cleanup of the work root in a `finally` block so a mid-sequence failure still cleans up.  It verifies the
installer's SHA-256 against `release-metadata.json` before executing it and refuses a portable ZIP as the target, so an inner
bundle path can never be confused with the outer archive.

Diagnostics are bounded and redacted: secret-valued environment variables are stripped before anything is written, and log tails
are truncated.  `acceptance-report.json` folds the result in as `installed_lifecycle_status` and refuses to publish `PASS` when the
evidence file is absent, when a step inside it did not pass, or when the lifecycle did not verify the installer hash it executed.

What this proves: the shipped installer installs, the installed binary is the built binary, the installed binary starts and writes
only outside its own directory, and it uninstalls without taking user data with it.  What it does not prove: interactive
clean-machine behaviour, UAC/elevation experience on a workstation, an upgrade over a previous installation (that needs two
*different* installers, and is never simulated by running one installer twice), retention of a real operator profile, or operator
acceptance.  Those remain the manual procedure below.

### Signature status (M42.2)

`python packaging\windows_release_evidence.py signing --release-metadata <release-metadata.json> --json-out <signing-status.json>`
asks Windows (`Get-AuthenticodeSignature`) about each published artifact and records `Status`, a bounded status message, and the
signer subject only when a signature exists.  The current result is `UNSIGNED`, and the report says so; that is a finding about
distribution trust, not a packaging failure, so the step never fails the gate for it.  Nothing reads, prints or stores a private
key, certificate file or password.  Producing a valid signature requires an owner-controlled code-signing certificate (or a hosted
signing service) and a signing step in `packaging/build_windows.ps1`; `packaging/DrillMaster.iss` sets no `SignTool` and no
`SignedUninstaller` override today, and the report records `signing_configured_in_build: false` accordingly.

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
