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
non-empty; and a capability probe (`Get-Command Get-AuthenticodeSignature`) runs first and is published as `harness`
(`powershell_version`, `query_command`, `signature_command_module`, and any probe error).  A probe that *positively* answers
`missing` records that one cause for every file; a probe that itself failed is recorded and the real queries still run, because a
diagnostic must not become an authority that suppresses evidence.

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
| REL-03 | Signature-state attribution closed | next exact-SHA run after M42.4 | `signing-status.json` `harness` block and the per-file `status_message`, readable from the annotation | the aggregate is `UNSIGNED`/`PASS`/`FAIL` - a determinate state - or `UNKNOWN` with a stated cause | a bare `UNKNOWN` with no reason is still the open blocker | repository maintainer | open until the next exact-SHA record exists |
| REL-04 | Artifact byte-integrity re-verification | the downloaded CI artifact | the procedure above, run on the operator's machine | `MATCH` for both artifacts and no `SUMS DIFFERENCE` | any `MISMATCH`, or no independent run at all | reviewer holding the download | `NOT_RUN` in-repository (`NOT_VERIFIED` in the report) |
| REL-05 | Reproducibility requirement | Decision C below | either a claim with two independent builds compared byte-for-byte, or the recorded `NOT_CLAIMED` | an explicit owner position, recorded in this file | a `PASS` gate silently read as reproducibility | product owner | `OWNER_DECISION` |
| REL-06 | POSIX permission policy | Decision D below | a documented position on mode bits for the portable ZIP on non-Windows extraction | recorded policy statement | absence of a statement | product owner | `OWNER_DECISION` |
| REL-07 | Clean-machine interactive install | a disposable Windows 10/11 x64 VM | the procedure under "Interactive installation procedure", with the VM image and installer SHA recorded | install, first run, sign-in, restart, and data-outside-`{app}` all confirmed by a named operator | any step unexecuted | field/QA owner | `NOT_RUN` |
| REL-08 | Upgrade and uninstall data retention | an earlier candidate installed first | steps 4-5 of the same procedure | prior test data readable, no second database, user data survives uninstall | not executed on a real upgrade pair | field/QA owner | `NOT_RUN` |
| REL-09 | Real DDR Excel acceptance | a sanctioned, non-confidential client DDR workbook | parser and database round-trip against that workbook, reviewed by an engineer | an engineer confirms the imported values and units | the synthetic workbook is `AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE` and never satisfies this row | business/technical owner | `NOT_RUN` |
| REL-10 | Real DDR PDF and MinerU acceptance | a licensed MinerU environment outside this repository | import of a real PDF with the opt-in path enabled | extracted fields reviewed against the source document | not provided or exercised by the Windows workflow | business/technical owner | `NOT_RUN` |
| REL-11 | Production database and field validation | approved test/prod separation, operator time | restore, concurrency, and field use on target hardware | operator sign-off naming the environment and SHA | no repository automation can substitute | operations owner | `NOT_RUN` |
| REL-12 | Open P6 owner decisions | none (they are decisions, not defects) | the six register entries carried forward from M36 | each decision recorded with its rationale | `NEW-P6-007`, `NEW-P6-008`, `NEW-P6-015`, `NEW-P6-020`, `NEW-P6-023`, `NEW-P6-024` remain open | product owner | `OWNER_DECISION` |

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
