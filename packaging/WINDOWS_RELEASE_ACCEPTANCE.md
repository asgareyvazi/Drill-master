# Windows release build and acceptance runbook

This runbook is an executable procedure for Windows release engineering. A successful automated build is not interactive installation, real DDR/PDF/MinerU, production database, field, or operator acceptance.

## Automated Windows release gate

The dedicated **Windows release validation** workflow runs on `windows-2022` for pushes, pull requests, and manual dispatch. It installs the pinned runtime/build dependencies and Inno Setup 6.7.1, runs the disposable database/import/auth/packaging regression suite, builds the one-folder portable bundle, executes `DrillMaster.exe --package-smoke` with temporary data/log paths, compiles the installer, and checks authoritative version, source SHA, and artifact SHA-256 values.

From a clean checkout of the intended full commit SHA, a local equivalent is:

```powershell
$sha = (git rev-parse HEAD).Trim()
if ((git status --porcelain=v1 --untracked-files=all).Length -ne 0) { throw 'Worktree must be clean' }
$release = Join-Path $env:TEMP "DrillMaster-release-$sha"
.\packaging\build_windows.ps1 -PythonExe (Get-Command python).Source -PythonVersion 3.12 -OutputDir $release
```

Pass the interpreter explicitly with `-PythonExe` whenever the environment's `python` is the one you intend to package with; that is what the CI gate does. `-PythonLauncher py -PythonVersion 3.12` remains available on a workstation where the Python launcher is registered, but note that the launcher resolves registry-registered runtimes only, so it can silently select a different Python than the one whose dependencies were tested.

The build refuses dirty source trees, requires an explicit Python minor version and verifies that the build virtualenv actually satisfies it, uses the locked runtime/build requirements, does not delete pre-existing release output, and keeps PyInstaller temporary work outside the repository. Use a new output directory for each build. The prior `-Python "py -3.12"` form remains accepted through a non-evaluated parser; new scripts should use `-PythonExe` or the separate launcher/version parameters. `-PortableOnly` deliberately omits installer compilation and cannot establish installer evidence.

### Failure diagnostics and text encodings

GitHub publishes at most ten `::error::` annotations per step, so a suite with more failures than that would otherwise hide the rest.  The regression step therefore runs `python packaging\junit_report.py --junit <report> --summary-out <markdown> --json-out <json> --annotations`: one annotation per failure up to the cap, an aggregate annotation that names the overflow, and a full Markdown table in the job step summary.  The parser reports test identities, exception names and `file:line` locations only, redacts anything that looks like a password, token or API-key value, and writes UTF-8 regardless of the console codepage so that printing a diagnostic can never become the second failure.  The step still propagates pytest's own exit code.

Repository source files contain UTF-8 Persian UI strings.  Any test or release tool that reads them must state `encoding="utf-8"`; the runner's default codepage (cp1252) raises `UnicodeDecodeError` otherwise.  `tests/test_windows_release_gate_contract.py` enforces this for every module in the Windows suite, verifies that the workflow still lists the required modules and existing files, keeps the disposable `RUNNER_TEMP` isolation and the Inno Setup pin, and confirms that the committed M42.1 checkpoint does not claim a CI result.

### Packaging stage diagnostics

The build step cannot emit a JUnit report, so it reports differently: it publishes `release_dir` to the job outputs *before* building (the evidence upload runs on `always()`, and a step that set that output only on success uploads nothing exactly when it matters), records a `Start-Transcript` file next to the release directory, and wraps every assertion in `try`/`catch`. The `catch` runs `python packaging\junit_report.py --annotate`, which emits one bounded `::error title=Windows packaging stage failed::` annotation containing the stage message plus the redacted tails of the transcript and `pyinstaller-build.log`, then re-throws so the step stays red. A packaging failure is therefore identifiable from the check run alone, even when the log and artifact endpoints are unreachable.

PowerShell handling matters here for two reasons. The step sets `$ErrorActionPreference = 'Stop'` so an error thrown inside `build_windows.ps1` terminates the step at the throw instead of being reported and then falling through into the artifact assertions (which would mislabel a build failure as "Frozen executable missing"). Inside the build script, the redirected PyInstaller pipeline runs with the preference temporarily relaxed and `$PSNativeCommandUseErrorActionPreference = $false`, because PyInstaller writes its progress log to stderr; under `Stop` that output can become a terminating `NativeCommandError` and abort a build that actually succeeded. The captured `$LASTEXITCODE` is the only build-status signal the script trusts.

`acceptance_report.py` re-hashes the portable ZIP and the setup executable from the release directory and reads `package-smoke.log`; it reports the frozen-executable and installer steps only when that evidence exists, and it records the workflow run identity it was invoked with instead of a committed value.

The output directory contains the versioned portable folder and ZIP, `package-smoke.log`, `release-metadata.json`, `SHA256SUMS.txt`, and—when run in CI—`acceptance-report.json` plus the compiled setup executable. The manifest records full source SHA, application version, exact Python/pip/PyInstaller/Inno Setup versions, and artifact hashes. Preserve the folder and evidence together; do not infer reproducible bit-for-bit binaries solely from matching version strings.

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
