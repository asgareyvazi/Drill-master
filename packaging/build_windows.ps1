[CmdletBinding()]
param(
    [switch]$PortableOnly,
    [string]$Python = "py -3.11"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
Set-Location $Root

$version = (Select-String -Path (Join-Path $Root "core\version.py") -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if ([string]::IsNullOrWhiteSpace($version)) {
    throw "Could not read the authoritative version from core/version.py"
}

$buildVenv = Join-Path $Root ".windows-build-venv"
$buildPython = Join-Path $buildVenv "Scripts\python.exe"
if (-not (Test-Path $buildPython)) {
    Invoke-Expression "$Python -m venv `"$buildVenv`""
}

& $buildPython -m pip install --upgrade pip
& $buildPython -m pip install -r requirements-lock.txt -r requirements-build.txt

Remove-Item (Join-Path $Root "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Root "dist") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Root "release") -Recurse -Force -ErrorAction SilentlyContinue

& $buildPython -m PyInstaller --noconfirm --clean (Join-Path $Root "packaging\DrillMaster.spec")
$bundle = Join-Path $Root "dist\DrillMaster"
$exe = Join-Path $bundle "DrillMaster.exe"
if (-not (Test-Path $exe)) {
    throw "PyInstaller did not create $exe"
}

$releaseRoot = Join-Path $Root "release"
$releaseBundle = Join-Path $releaseRoot "DrillMaster-$version"
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
Copy-Item $bundle $releaseBundle -Recurse -Force

& $buildPython packaging\package_smoke.py --bundle-dir $releaseBundle --run
if ($LASTEXITCODE -ne 0) {
    throw "Packaged application smoke test failed"
}

if (-not $PortableOnly) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($null -eq $iscc) {
        throw "Inno Setup 6 (ISCC.exe) is required. Use -PortableOnly to build the folder without an installer."
    }
    & $iscc.Source "/DAppVersion=$version" "/DSourceDir=$releaseBundle" "/DOutputDir=$releaseRoot" (Join-Path $Root "packaging\DrillMaster.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed"
    }
}

Get-ChildItem $releaseRoot -File -Recurse |
    Get-FileHash -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash.ToLower())  $($_.Path.Substring($releaseRoot.Length + 1))" } |
    Set-Content (Join-Path $releaseRoot "SHA256SUMS.txt") -Encoding ascii

Write-Host "Build complete: $releaseRoot"
Write-Host "Version: $version"
Write-Host "Portable bundle: $releaseBundle"
if (-not $PortableOnly) {
    Write-Host "Installer: $releaseRoot\DrillMaster-$version-Setup.exe"
}
