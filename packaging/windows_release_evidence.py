"""Post-build Windows evidence: installed-application lifecycle and signature status.

Two separate subcommands are provided so each can run as its own CI step:

``lifecycle``  installs the *published* installer silently into a throwaway
             directory, runs the installed executable's own package smoke with
             isolated data/log roots, then uninstalls non-interactively and checks
             that the application files are gone while user data is preserved.
             Every path is derived from an explicit temp work root; nothing here
             touches an operator profile, a production database, or the repository.
``signing``   records Authenticode status for each published artifact using the
             Windows signature utility, and whether the build could sign at all.

Both commands write machine-readable JSON with bounded, redacted diagnostics.  A
green result means the automated steps above succeeded; it is deliberately not a
claim of interactive clean-machine, upgrade, or operator acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Protocol

_PACKAGING_DIR = Path(__file__).resolve().parent
if str(_PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGING_DIR))

from package_smoke import _smoke_environment  # noqa: E402  (isolated smoke environment is shared)
from release_metadata import sha256_file  # noqa: E402  (one streaming hash implementation)

DIAGNOSTIC_LIMIT = 4000
STEP_FIELDS = ("name", "status", "detail")
VERSION_QUERY_SCRIPT = (
    "$info = (Get-Item -LiteralPath $env:DRILLMASTER_TARGET_PATH).VersionInfo; "
    "@{FileVersion=$info.FileVersion; ProductVersion=$info.ProductVersion} | ConvertTo-Json -Compress"
)
SIGNATURE_QUERY_SCRIPT = (
    "$signature = Get-AuthenticodeSignature -LiteralPath $env:DRILLMASTER_TARGET_PATH; "
    "@{Status=[string]$signature.Status; "
    "StatusMessage=[string]$signature.StatusMessage; "
    "SignerSubject=$(if ($signature.SignerCertificate) { [string]$signature.SignerCertificate.Subject } else { $null })} "
    "| ConvertTo-Json -Compress"
)
SECRET_ENV_PATTERN = re.compile(r"(PASSWORD|API_KEY|TOKEN|SECRET|CREDENTIAL)", re.IGNORECASE)


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], dict[str, str] | None, Path | None, int], CommandResult]


def bound(text: str, limit: int = DIAGNOSTIC_LIMIT) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    keep = limit // 2
    return text[:keep] + f"\n...[{len(text) - 2 * keep} characters elided]...\n" + text[-keep:]


def redact(text: str, secret_values: list[str]) -> str:
    for value in secret_values:
        if value:
            text = text.replace(value, "[REDACTED]")
    return bound(text)


def default_runner(argv: list[str], environment: dict[str, str] | None,
                   cwd: Path | None, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(argv, env=environment, cwd=str(cwd) if cwd else None, check=False,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def run_powershell(script: str, target: Path, runner: Runner, timeout: int) -> dict:
    """Query Windows shell metadata for a path without interpolating it into the script."""
    environment = dict(os.environ)
    environment["DRILLMASTER_TARGET_PATH"] = str(target)
    completed = runner(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", script], environment, None, timeout)
    output = (getattr(completed, "stdout", "") or "").strip()
    if completed.returncode != 0 or not output:
        return {"error": f"powershell exit {completed.returncode}: {bound(output, 200)}"}
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {"error": f"powershell returned unreadable output: {bound(output, 200)}"}
    return payload if isinstance(payload, dict) else {"error": "powershell returned a non-object"}


def _step(name: str, status: str, detail: str = "") -> dict:
    return {"name": name, "status": status, "detail": bound(detail, 600)}


def _installer_entry(metadata: dict, installer: Path) -> dict:
    """Bind the file that will be executed to the hash published for that exact name."""
    wanted = installer.name.lower()
    for entry in metadata.get("artifacts", []):
        if Path(str(entry.get("filename", ""))).name.lower() == wanted:
            return entry
    raise ValueError(f"the installer {installer.name} is not listed in release metadata; refusing to run an unbound binary")


def normalize_version(value: str) -> tuple[str, ...]:
    parts = re.findall(r"\d+", value or "")
    return tuple(parts[:3]) if parts else ()


def snapshot(directory: Path) -> dict[str, int]:
    if not directory.exists():
        return {}
    entries: dict[str, int] = {}
    for path in directory.rglob("*"):
        if path.is_file():
            entries[path.relative_to(directory).as_posix()] = path.stat().st_size
    return entries


def run_lifecycle(*, installer: Path, expected_sha256: str, app_version: str, work_root: Path,
                  runner: Runner = default_runner, exe_name: str = "DrillMaster.exe",
                  timeout: int = 600, poll_interval: float = 0.5, settle_seconds: float = 120.0) -> dict:
    """Install, verify, smoke, and uninstall one artifact set; return a structured report."""
    if not expected_sha256 or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("expected_sha256 must be a 64-character hex digest")
    if installer.suffix.lower() == ".zip":
        raise ValueError("the lifecycle smoke must execute the compiled installer, not the portable ZIP archive")
    install_dir = work_root / "install"
    data_root = work_root / "userdata"
    evidence: dict[str, object] = {"steps": [], "diagnostics": {}}
    steps: list[dict] = evidence["steps"]
    started = time.time()
    sentinel: Path | None = None
    sentinel_text = "DRILLMASTER-LIFECYCLE-SENTINEL-PRESERVE\n"

    def record(name: str, status: str, detail: str = "") -> None:
        steps.append(_step(name, status, detail))

    try:
        # 1. The artifact that will be executed must be the artifact that was published.
        if not installer.is_file():
            record("verify_installer", "FAIL", f"missing installer: {installer.name}")
            return _finish(evidence, "FAIL", started)
        digest = sha256_file(installer)
        if digest.lower() != expected_sha256.lower():
            record("verify_installer", "FAIL",
                   f"SHA-256 mismatch: manifest {expected_sha256[:16]}..., observed {digest[:16]}...")
            return _finish(evidence, "FAIL", started)
        record("verify_installer", "PASS", f"sha256={digest}; size_bytes={installer.stat().st_size}")
        evidence["installer_hash_verified"] = True
        evidence["installer_filename"] = installer.name
        evidence["installer_sha256"] = digest

        # 2. Silent install into an isolated directory; the exit code is authoritative.
        install_dir.mkdir(parents=True, exist_ok=True)
        install_log = work_root / "install.log"
        argv = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                f"/DIR={install_dir}", f"/LOG={install_log}"]
        try:
            completed = runner(argv, None, work_root, timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            record("silent_install", "FAIL", f"{type(exc).__name__}: {exc}")
            return _finish(evidence, "FAIL", started)
        evidence["diagnostics"]["install_log"] = redact(_tail(install_log), [])
        if completed.returncode != 0:
            record("silent_install", "FAIL", f"exit {completed.returncode}")
            return _finish(evidence, "FAIL", started)
        record("silent_install", "PASS", f"target={install_dir.name}")

        # 3. The installed payload must exist and be the version this build produced.
        installed_exe = install_dir / exe_name
        uninstaller = install_dir / "unins000.exe"
        missing = [name for name, path in ((exe_name, installed_exe), ("unins000.exe", uninstaller))
                   if not path.is_file()]
        if missing:
            record("installed_files", "FAIL", f"absent after install: {', '.join(missing)}")
            return _finish(evidence, "FAIL", started)
        record("installed_files", "PASS", f"{exe_name} size_bytes={installed_exe.stat().st_size}")

        version_info = run_powershell(VERSION_QUERY_SCRIPT, installed_exe, runner, timeout)
        if "error" in version_info:
            record("installed_version", "FAIL", version_info["error"])
            return _finish(evidence, "FAIL", started)
        observed = normalize_version(str(version_info.get("ProductVersion") or version_info.get("FileVersion") or ""))
        wanted = normalize_version(app_version)
        evidence["installed_version"] = {"expected": app_version, **version_info}
        if not observed or observed != wanted:
            record("installed_version", "FAIL",
                   f"installed ProductVersion {version_info!r} does not match the authoritative application version {app_version}")
            return _finish(evidence, "FAIL", started)
        record("installed_version", "PASS", f"ProductVersion {'.'.join(observed)} == {app_version}")

        # 4. Run the installed executable's own smoke with isolated roots and prove
        #    that it wrote nothing into the installation directory.
        before = snapshot(install_dir)
        smoke_root = work_root / "smoke"
        smoke_root.mkdir(parents=True, exist_ok=True)
        environment, secret_values = _smoke_environment(smoke_root)
        # Point the configured user-data and backup roots at a directory this step
        # owns, so a leaked write inside {app} is detectable rather than assumed.
        data_root.mkdir(parents=True, exist_ok=True)
        environment["DRILLMASTER_DATA_DIR"] = str(data_root)
        environment["DRILLMASTER_BACKUP_DIR"] = str(data_root / "backups")
        try:
            smoke = runner([str(installed_exe), "--package-smoke"], environment, smoke_root, timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            record("installed_smoke", "FAIL", f"{type(exc).__name__}: {exc}")
            return _finish(evidence, "FAIL", started)
        smoke_output = f"{getattr(smoke, 'stdout', '') or ''}{getattr(smoke, 'stderr', '') or ''}"
        leaked = [value for value in secret_values if value and value in smoke_output]
        after = snapshot(install_dir)
        created = sorted(set(after) - set(before))
        changed = sorted(name for name in set(after) & set(before) if after[name] != before[name])
        log_written = (smoke_root / "logs" / "drillmaster.log").is_file()
        details = {"exit_code": smoke.returncode, "wrote_log_outside_install_dir": log_written,
                   "secret_leak_detected": bool(leaked), "new_files_in_install_dir": created[:20],
                   "changed_files_in_install_dir": changed[:20]}
        evidence["diagnostics"]["installed_smoke_output"] = redact(smoke_output, secret_values)
        evidence["installed_smoke"] = details
        if smoke.returncode != 0 or leaked or created or changed or not log_written:
            record("installed_smoke", "FAIL", json.dumps(details, sort_keys=True))
            return _finish(evidence, "FAIL", started)
        record("installed_smoke", "PASS", "exit 0; log written outside the install directory; install tree unchanged")

        # 5. User data lives outside {app}; record the containment proof explicitly.
        containment = {
            "data_root_outside_install_dir": not _is_within(data_root, install_dir),
            "log_root_outside_install_dir": not _is_within(smoke_root / "logs", install_dir),
            "backup_root_outside_install_dir": not _is_within(data_root / "backups", install_dir),
        }
        evidence["path_containment"] = containment
        if not all(containment.values()):
            record("data_outside_install_dir", "FAIL", json.dumps(containment, sort_keys=True))
            return _finish(evidence, "FAIL", started)
        record("data_outside_install_dir", "PASS", json.dumps(containment, sort_keys=True))

        # 6. A synthetic user-data file must survive uninstall.  This proves the
        #    uninstaller removes application files only; it is not an upgrade test.
        sentinel = data_root / "sentinel-preserve.txt"
        sentinel.write_text(sentinel_text, encoding="utf-8")

        # 7. Non-interactive uninstall, then prove the application files are gone.
        uninstall_log = work_root / "uninstall.log"
        try:
            removed = _uninstall(uninstaller, uninstall_log, install_dir, runner, timeout,
                                 poll_interval, settle_seconds, evidence)
        except (OSError, subprocess.SubprocessError) as exc:
            record("silent_uninstall", "FAIL", f"{type(exc).__name__}: {exc}")
            return _finish(evidence, "FAIL", started)
        if not removed["ok"]:
            record("silent_uninstall", "FAIL", json.dumps(removed, sort_keys=True))
            return _finish(evidence, "FAIL", started)
        record("silent_uninstall", "PASS", json.dumps(removed, sort_keys=True))

        leftovers = sorted(snapshot(install_dir))
        if leftovers:
            record("install_files_removed", "FAIL",
                   f"files remain under the install directory after uninstall: {leftovers[:20]}")
            return _finish(evidence, "FAIL", started)
        record("install_files_removed", "PASS", "install directory holds no application files")

        if not sentinel.is_file() or sentinel.read_text(encoding="utf-8") != sentinel_text:
            record("user_data_preserved", "FAIL", "the synthetic user-data sentinel did not survive uninstall")
            return _finish(evidence, "FAIL", started)
        record("user_data_preserved", "PASS", "synthetic file outside {app} survived uninstall")
        return _finish(evidence, "PASS", started)
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
        evidence["cleaned_up"] = not work_root.exists()
        if sentinel is not None:
            evidence["sentinel_cleanup_note"] = "the sentinel lived under the throwaway work root, which is removed here"


def _finish(evidence: dict, status: str, started: float) -> dict:
    evidence["status"] = status
    evidence["duration_seconds"] = round(time.time() - started, 3)
    evidence["schema"] = "drillmaster-installer-lifecycle/v1"
    evidence.setdefault("installer_hash_verified", False)
    for step in evidence.get("steps", []):
        if not all(field in step for field in STEP_FIELDS):
            raise ValueError(f"lifecycle step is malformed: {step}")
    return evidence


def _tail(path: Path, lines: int = 40) -> str:
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except (ValueError, OSError):
        return False
    return True


def _uninstall(uninstaller: Path, log: Path, install_dir: Path, runner: Runner, timeout: int,
               poll_interval: float, settle_seconds: float, evidence: dict) -> dict:
    """Run the uninstaller, then wait for the install directory to actually empty.

    Inno Setup's uninstaller copies itself to a temp location and can return before
    the deletion pass finishes, so the exit code alone is not sufficient evidence.
    """
    argv = [str(uninstaller), "/SILENT", "/NORESTART", "/SUPPRESSMSGBOXES", f"/LOG={log}"]
    completed = runner(argv, None, install_dir.parent, timeout)
    deadline = time.time() + max(settle_seconds, 0.0)
    while time.time() < deadline:
        if not install_dir.exists() or not snapshot(install_dir):
            break
        time.sleep(poll_interval)
    evidence["diagnostics"]["uninstall_log"] = redact(_tail(log), [])
    # The exit code judges the uninstall *process*; whether the application files are
    # really gone is a separate claim, recorded by the install_files_removed step.
    return {"ok": completed.returncode == 0, "exit_code": completed.returncode,
            "install_dir_emptied": not sorted(snapshot(install_dir))}


def run_signing(*, release_metadata_path: Path, runner: Runner = default_runner,
                timeout: int = 120) -> dict:
    """Record Authenticode status per published artifact, plus whether signing is possible."""
    metadata = json.loads(release_metadata_path.read_text(encoding="utf-8"))
    release_root = release_metadata_path.parent
    script_text = ""
    for candidate in (_PACKAGING_DIR / "build_windows.ps1", _PACKAGING_DIR / "DrillMaster.iss"):
        if candidate.is_file():
            script_text += candidate.read_text(encoding="utf-8", errors="replace")
    signing_configured = bool(re.search(r"signtool|SignTool=|SignedUninstaller", script_text, re.IGNORECASE))
    credential_env_present = sorted(key for key in os.environ
                                    if SECRET_ENV_PATTERN.search(key) and re.search(r"SIGN|CERT|PFX|AUTHENTICODE", key, re.IGNORECASE))
    files = []
    for entry in metadata.get("artifacts", []):
        path = release_root / str(entry["filename"]).replace("/", os.sep)
        record = {"filename": str(entry["filename"]), "size_bytes": path.stat().st_size if path.is_file() else None,
                  "sha256": sha256_file(path) if path.is_file() else None}
        if not path.is_file():
            record.update({"status": "UNKNOWN", "status_message": "artifact missing from the release directory"})
        else:
            payload = run_powershell(SIGNATURE_QUERY_SCRIPT, path, runner, timeout)
            if "error" in payload:
                record.update({"status": "UNKNOWN", "status_message": payload["error"]})
            else:
                status = str(payload.get("Status") or "Unknown")
                record["status"] = status
                record["status_message"] = bound(str(payload.get("StatusMessage") or ""), 300)
                subject = payload.get("SignerSubject")
                if subject:
                    # A subject is public information, but it is still bounded here.
                    record["signer"] = bound(str(subject), 300)
        files.append(record)
    statuses = {str(item["status"]) for item in files}
    if not files:
        status = "UNKNOWN"
    elif "UNKNOWN" in statuses:
        # Unverifiable evidence is never folded into "unsigned": they are different claims.
        status = "UNKNOWN"
    elif statuses == {"NotSigned"}:
        status = "UNSIGNED"
    elif statuses == {"Valid"}:
        status = "PASS"
    else:
        status = "FAIL"
    return {
        "schema": "drillmaster-signing-status/v1",
        "method": "Windows Get-AuthenticodeSignature",
        "status": status,
        "files": files,
        "signing_configured_in_build": signing_configured,
        "credentials_available": bool(credential_env_present),
        "credential_environment_variables": credential_env_present,
        "prerequisite": ("none" if status == "PASS" else
                         "an owner-controlled code-signing certificate (or a hosted signing service) plus "
                         "signtool/PowerShell signing configuration in the release build; none is referenced by "
                         "packaging/build_windows.ps1 or packaging/DrillMaster.iss"),
    }


def render_markdown(report: dict, title: str) -> str:
    lines = [f"### {title}", "", f"Status: **{report.get('status', 'UNKNOWN')}**", ""]
    steps = report.get("steps")
    if isinstance(steps, list):
        lines.append("| step | status |")
        lines.append("| --- | --- |")
        for step in steps:
            lines.append(f"| {step.get('name')} | {step.get('status')} |")
    files = report.get("files")
    if isinstance(files, list):
        lines.append("")
        for item in files:
            signer = f"; signer: {item['signer']}" if item.get("signer") else ""
            lines.append(f"- `{item['filename']}` — {item['status']}{signer}")
    if report.get("prerequisite"):
        lines += ["", f"Prerequisite: {report['prerequisite']}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    lifecycle = subparsers.add_parser("lifecycle")
    lifecycle.add_argument("--installer", required=True, type=Path)
    lifecycle.add_argument("--release-metadata", required=True, type=Path)
    lifecycle.add_argument("--expected-sha256", default="")
    lifecycle.add_argument("--app-version", required=True)
    lifecycle.add_argument("--work-root", required=True, type=Path)
    lifecycle.add_argument("--exe-name", default="DrillMaster.exe")
    lifecycle.add_argument("--timeout", type=int, default=600)
    lifecycle.add_argument("--settle-seconds", type=float, default=120.0,
                           help="how long to wait for the uninstaller to finish deleting files")
    lifecycle.add_argument("--json-out", required=True, type=Path)
    lifecycle.add_argument("--markdown-out", type=Path)

    signing = subparsers.add_parser("signing")
    signing.add_argument("--release-metadata", required=True, type=Path)
    signing.add_argument("--json-out", required=True, type=Path)
    signing.add_argument("--markdown-out", type=Path)
    signing.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)

    if args.command == "lifecycle":
        metadata = json.loads(args.release_metadata.read_text(encoding="utf-8"))
        entry = _installer_entry(metadata, args.installer.resolve())
        expected = str(entry["sha256"])
        if args.expected_sha256 and args.expected_sha256.lower() != expected.lower():
            print("ERROR: --expected-sha256 disagrees with release metadata", file=sys.stderr)
            return 2
        if sys.platform != "win32":
            report = _finish({"steps": [_step("platform_gate", "NOT_RUN",
                                              "installed-application lifecycle requires a Windows host")],
                              "diagnostics": {}, "installer_hash_verified": False}, "NOT_RUN", time.time())
        else:
            args.work_root.mkdir(parents=True, exist_ok=True)
            report = run_lifecycle(installer=args.installer.resolve(), expected_sha256=expected,
                                   app_version=args.app_version, work_root=args.work_root.resolve(),
                                   exe_name=args.exe_name, timeout=args.timeout,
                                   settle_seconds=args.settle_seconds)
    else:
        if sys.platform != "win32":
            report = {"schema": "drillmaster-signing-status/v1", "status": "NOT_RUN",
                      "reason": "Authenticode verification requires a Windows host", "files": [],
                      "signing_configured_in_build": False, "credentials_available": False, "prerequisite": ""}
        else:
            report = run_signing(release_metadata_path=args.release_metadata.resolve(), timeout=args.timeout)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(render_markdown(report, f"Windows {args.command} evidence"), encoding="utf-8")
    print(json.dumps({"command": args.command, "status": report.get("status"),
                      "json_out": str(args.json_out)}, sort_keys=True))
    statuses = {"PASS", "NOT_RUN", "UNSIGNED"}
    return 0 if str(report.get("status")) in statuses else 1


if __name__ == "__main__":
    raise SystemExit(main())
