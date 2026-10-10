[CmdletBinding()]
param(
    [switch]$PortableOnly,
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "3.12",
    [string]$OutputDir = "",
    [string]$Python = "",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
# PowerShell 7.3+ turns redirected native-command stderr into terminating errors.
# PyInstaller writes its INFO log to stderr, so that behaviour would abort a
# successful build.  Exit codes are checked explicitly at every call site below.
if (Test-Path -LiteralPath Variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$Root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
Set-Location $Root

# Preserve the former -Python "py -3.12" interface without evaluating an
# arbitrary command string. New callers should pass launcher and minor version
# separately.
if (-not [string]::IsNullOrWhiteSpace($Python)) {
    if ($Python -notmatch '^\s*(?<launcher>\S+)\s+-(?<version>3\.\d+)\s*$') {
        throw 'Legacy -Python must be a launcher followed by a minor selector, such as "py -3.12"'
    }
    $PythonLauncher = $Matches.launcher
    $PythonVersion = $Matches.version
}

if ($PythonVersion -notmatch '^3\.\d+$') {
    throw "PythonVersion must be an explicit minor version such as 3.12"
}

$versionSource = Join-Path $Root "core\version.py"
$versionMatch = Select-String -Path $versionSource -Pattern '^__version__\s*=\s*["'']([^"'']+)["'']$'
if ($null -eq $versionMatch -or $versionMatch.Matches.Count -ne 1) {
    throw "Could not read exactly one authoritative version from core/version.py"
}
$version = $versionMatch.Matches[0].Groups[1].Value

$sourceSha = (& git -C $Root rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceSha -notmatch '^[0-9a-f]{40}$') {
    throw "A full Git source SHA is required to build a release artifact"
}
$dirty = & git -C $Root status --porcelain=v1 --untracked-files=all
if ($LASTEXITCODE -ne 0 -or $dirty) {
    throw "Refusing release build from a dirty worktree; commit the intended source first"
}

# An explicit interpreter path is the reproducible choice: CI already provisioned
# and tested with it, while the "py" launcher only sees registry-registered runtimes.
$launcherArgs = @()
if (-not [string]::IsNullOrWhiteSpace($PythonExe)) {
    $interpreter = $PythonExe
} else {
    $interpreter = $PythonLauncher
    $launcherArgs = @("-$PythonVersion")
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $releaseRoot = Join-Path $Root "release"
} else {
    $releaseRoot = [System.IO.Path]::GetFullPath($OutputDir)
}
if (Test-Path $releaseRoot) {
    $existing = @(Get-ChildItem -LiteralPath $releaseRoot -Force -ErrorAction Stop)
    if ($existing.Count -gt 0) {
        throw "Refusing to delete or overwrite existing release output: $releaseRoot. Choose a new -OutputDir."
    }
} else {
    New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
}

$buildVenv = Join-Path $Root ".windows-build-venv"
$buildPython = Join-Path $buildVenv "Scripts\python.exe"
if (-not (Test-Path $buildPython)) {
    & $interpreter @launcherArgs -m venv $buildVenv
    if ($LASTEXITCODE -ne 0) { throw "Build virtualenv creation failed using '$interpreter $($launcherArgs -join ' ')'" }
}

$requestedVersion = (& $interpreter @launcherArgs -c 'import sys; print(sys.version.split()[0])')
if ($LASTEXITCODE -ne 0 -or -not $requestedVersion) { throw "Requested Python $PythonVersion is unavailable via '$interpreter'" }
$actualVersion = (& $buildPython -c 'import sys; print(sys.version.split()[0])')
if ($LASTEXITCODE -ne 0 -or "$actualVersion" -ne "$requestedVersion") {
    throw "Existing build virtualenv ($actualVersion) does not match the requested interpreter ($requestedVersion). Remove .windows-build-venv only after preserving any needed local environment."
}
if ("$actualVersion" -notmatch "^$([regex]::Escape($PythonVersion))\.") {
    throw "Build interpreter Python $actualVersion does not satisfy the required minor version $PythonVersion"
}

# pip failures are the most common packaging-environment defect and its output is
# otherwise invisible in a run whose log endpoint is unreachable, so it is captured
# and its tail is carried inside the thrown message that CI annotates.
$dependencyLog = Join-Path $releaseRoot "pip-install.log"
$preferenceBeforePip = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $buildPython -m pip install --disable-pip-version-check --progress-bar off -r requirements-lock.txt -r requirements-build.txt 2>&1 | Tee-Object -FilePath $dependencyLog
$pipExit = $LASTEXITCODE
& $buildPython -m pip check 2>&1 | Tee-Object -FilePath $dependencyLog -Append
$pipCheckExit = $LASTEXITCODE
$ErrorActionPreference = $preferenceBeforePip
if ($pipExit -ne 0 -or $pipCheckExit -ne 0) {
    $pipTail = @()
    if (Test-Path -LiteralPath $dependencyLog) { $pipTail = @(Get-Content -LiteralPath $dependencyLog -Tail 30) }
    $stage = if ($pipExit -ne 0) { "Locked dependency installation failed (exit $pipExit)" } else { "Dependency consistency check failed (exit $pipCheckExit)" }
    throw "$stage; inspect $dependencyLog`n$($pipTail -join [Environment]::NewLine)"
}


$buildId = [guid]::NewGuid().ToString("N")
$buildRoot = Join-Path ([System.IO.Path]::GetTempPath()) "DrillMaster-build-$sourceSha-$buildId"
$buildWork = Join-Path $buildRoot "work"
$buildDist = Join-Path $buildRoot "dist"
New-Item -ItemType Directory -Path $buildWork, $buildDist -Force | Out-Null
$oldBuildRoot = $env:DRILLMASTER_BUILD_ROOT
$env:DRILLMASTER_BUILD_ROOT = $buildRoot

try {
    $buildLog = Join-Path $releaseRoot "pyinstaller-build.log"
    # PyInstaller writes its progress log to stderr.  With Stop active, a redirected
    # stderr line becomes a terminating NativeCommandError on Windows PowerShell 5.1
    # and PowerShell 7.0-7.2, aborting a build that actually succeeded.  The relaxed
    # preference covers this pipeline only; the captured exit code is authoritative.
    $preferenceBeforePyInstaller = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $buildPython -m PyInstaller --noconfirm --clean --workpath $buildWork --distpath $buildDist `
        (Join-Path $Root "packaging\DrillMaster.spec") 2>&1 | Tee-Object -FilePath $buildLog
    $pyinstallerExit = $LASTEXITCODE
    $ErrorActionPreference = $preferenceBeforePyInstaller
    if ($pyinstallerExit -ne 0) {
        $tail = @()
        if (Test-Path -LiteralPath $buildLog) { $tail = @(Get-Content -LiteralPath $buildLog -Tail 20) }
        throw "PyInstaller failed (exit $pyinstallerExit); inspect $buildLog`n$($tail -join [Environment]::NewLine)"
    }

    $bundle = Join-Path $buildDist "DrillMaster"
    $exe = Join-Path $bundle "DrillMaster.exe"
    if (-not (Test-Path $exe)) {
        throw "PyInstaller did not create $exe"
    }

    $releaseBundle = Join-Path $releaseRoot "DrillMaster-$version"
    Copy-Item -LiteralPath $bundle -Destination $releaseBundle -Recurse
    $smokeLog = Join-Path $releaseRoot "package-smoke.log"
    & $buildPython packaging\package_smoke.py --bundle-dir $releaseBundle --run --log-path $smokeLog
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged application smoke test failed; inspect $smokeLog"
    }

    $installerPath = $null
    $innoVersion = "NOT_BUILT"
    if (-not $PortableOnly) {
        $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($null -eq $iscc) {
            throw "Inno Setup 6 (ISCC.exe) is required. Use -PortableOnly to build the folder without an installer."
        }
        $innoVersion = (Get-Item -LiteralPath $iscc.Source).VersionInfo.FileVersion
        & $iscc.Source "/DAppVersion=$version" "/DSourceDir=$releaseBundle" "/DOutputDir=$releaseRoot" `
            (Join-Path $Root "packaging\DrillMaster.iss")
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
        $installerPath = Join-Path $releaseRoot "DrillMaster-$version-Setup.exe"
        if (-not (Test-Path $installerPath)) { throw "Inno Setup did not create $installerPath" }
    }

    $portableArchive = Join-Path $releaseRoot "DrillMaster-$version-windows-x64.zip"
    Compress-Archive -LiteralPath $releaseBundle -DestinationPath $portableArchive -CompressionLevel Optimal
    $pyinstallerVersion = (& $buildPython -m PyInstaller --version).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not resolve PyInstaller build version" }
    $pipVersionLine = (& $buildPython -m pip --version).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not resolve pip build version" }
    $pipVersion = $pipVersionLine.Split()[1]
    $metadataArgs = @(
        "packaging\release_metadata.py", "--release-root", $releaseRoot,
        "--source-sha", $sourceSha, "--version", $version,
        "--python-version", $actualVersion, "--pyinstaller-version", $pyinstallerVersion,
        "--pip-version", $pipVersion, "--innosetup-version", $innoVersion, "--bundle-zip", $portableArchive
    )
    if ($installerPath) { $metadataArgs += @("--installer", $installerPath) }
    & $buildPython @metadataArgs
    if ($LASTEXITCODE -ne 0) { throw "Release metadata generation failed" }

    Write-Host "Build complete: $releaseRoot"
    Write-Host "Source SHA: $sourceSha"
    Write-Host "Version: $version"
    Write-Host "Portable bundle: $releaseBundle"
    Write-Host "Portable archive: $portableArchive"
    if ($installerPath) { Write-Host "Installer: $installerPath" }
}
finally {
    if ($null -eq $oldBuildRoot) {
        Remove-Item Env:DRILLMASTER_BUILD_ROOT -ErrorAction SilentlyContinue
    } else {
        $env:DRILLMASTER_BUILD_ROOT = $oldBuildRoot
    }
    Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
}
