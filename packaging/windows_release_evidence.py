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
import tempfile
import time
import zipfile
from pathlib import PurePosixPath
from pathlib import Path
from typing import Callable, Protocol

_PACKAGING_DIR = Path(__file__).resolve().parent
if str(_PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGING_DIR))

from package_smoke import _smoke_environment  # noqa: E402  (isolated smoke environment is shared)
from release_metadata import (  # noqa: E402  (shared schema-level constants and hashing)
    SIGNING_NOT_APPLICABLE as NOT_APPLICABLE,
    SIGNING_STATUS_VOCABULARY,
    sha256_file,
    validate_document,
)

DIAGNOSTIC_LIMIT = 4000
# The frozen application executable is a few tens of megabytes.  This bound exists so a
# malformed or hostile archive cannot fill the runner's disk during an evidence step.
MAX_EXTRACTED_MEMBER_BYTES = 256 * 1024 * 1024
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


def aggregate_signing_status(files: list[dict]) -> str:
    """Fold per-file Authenticode results into one status, never into a guess.

    ``NOT_APPLICABLE`` entries (archives) are excluded; if nothing signature-bearing
    could be examined the result is UNKNOWN rather than a fabricated UNSIGNED.
    """
    examined = [item for item in files if item.get("status") != NOT_APPLICABLE]
    statuses = {str(item.get("status")) for item in examined}
    if not examined:
        return "UNKNOWN"
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    if statuses == {"NotSigned"}:
        return "UNSIGNED"
    if statuses == {"Valid"}:
        return "PASS"
    return "FAIL"


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
    error_text = (getattr(completed, "stderr", "") or "").strip()
    if completed.returncode != 0 or not output:
        # The exit code alone cannot be acted on: PowerShell reports the reason on stderr.
        return {"error": f"powershell exit {completed.returncode}: "
                         f"{bound(error_text or output, 300)}"}
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
        # A frozen windowed executable has no console, so the application log is an equally
        # authoritative channel for the marker; both are read, neither is assumed.
        smoke_log_text = _tail(smoke_root / "logs" / "drillmaster.log", lines=400)
        observed_output = f"{smoke_output}\n{smoke_log_text}"
        leaked = [value for value in secret_values if value and value in observed_output]
        after = snapshot(install_dir)
        created = sorted(set(after) - set(before))
        changed = sorted(name for name in set(after) & set(before) if after[name] != before[name])
        log_written = (smoke_root / "logs" / "drillmaster.log").is_file()
        # An exit code of 0 is not the same claim as "the smoke ran": an executable that
        # returns cleanly without completing the smoke must never satisfy this step.
        marker_found = "PACKAGE_SMOKE_OK" in observed_output
        fatal_found = bool(re.search(r"FATAL|Traceback \(most recent call last\)", observed_output))
        details = {"exit_code": smoke.returncode, "wrote_log_outside_install_dir": log_written,
                   "secret_leak_detected": bool(leaked), "new_files_in_install_dir": created[:20],
                   "changed_files_in_install_dir": changed[:20],
                   "success_marker_found": marker_found, "fatal_marker_found": fatal_found,
                   "success_marker_channel": ("stdout" if "PACKAGE_SMOKE_OK" in smoke_output
                                              else "application-log" if marker_found else "none")}
        evidence["diagnostics"]["installed_smoke_output"] = redact(observed_output, secret_values)
        evidence["installed_smoke"] = details
        if (smoke.returncode != 0 or leaked or created or changed or not log_written
                or not marker_found or fatal_found):
            record("installed_smoke", "FAIL", json.dumps(details, sort_keys=True))
            return _finish(evidence, "FAIL", started)
        record("installed_smoke", "PASS",
               f"exit 0; success marker via {details['success_marker_channel']}; no fatal marker; log written "
               "outside the install directory; install tree unchanged")

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


def read_release_manifest(path: Path) -> dict:
    """Load a release manifest only when it satisfies the published v2 contract.

    Both evidence commands go through this: a manifest with a stale schema, a duplicated
    artifact row or a malformed digest cannot be used to bind a lifecycle run or a
    signature claim, because every field of that evidence would then be a guess.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"release metadata unreadable or malformed: {path.name} ({exc})") from exc
    return validate_document(payload)


def _artifact_by_suffix(metadata: dict, release_root: Path, suffix: str) -> tuple[Path, dict]:
    """Locate a manifest artifact by extension and return it with its recorded entry."""
    for entry in metadata.get("artifacts", []):
        name = Path(str(entry.get("filename", ""))).name
        if name.lower().endswith(suffix):
            path = release_root / str(entry["filename"]).replace("/", os.sep)
            return path, entry
    raise ValueError(f"release metadata lists no {suffix} artifact to examine")


def _digest_matches(path: Path, entry: dict, label: str) -> str:
    """A file may only be trusted for evidence when its own recorded digest matches."""
    if not path.is_file():
        raise ValueError(f"{label} is listed in release metadata but missing: {path.name}")
    digest = sha256_file(path)
    recorded = str(entry.get("sha256") or "")
    if recorded and digest.lower() != recorded.lower():
        raise ValueError(f"{label} digest does not match release metadata; refusing to derive evidence from it")
    return digest


def extract_verified_member(archive: Path, exe_name: str, destination: Path,
                            *, max_bytes: int = MAX_EXTRACTED_MEMBER_BYTES) -> tuple[Path, str]:
    """Extract exactly one named member from an archive, safely and bounded.

    The returned path is a copy inside the caller's temporary directory: the release
    artifact itself is never mutated, and a member that could escape the destination
    (absolute path or ``..``) or exceeds the size bound is refused.
    """
    with zipfile.ZipFile(archive) as bundle:
        candidates = [info for info in bundle.infolist()
                      if not info.is_dir() and PurePosixPath(info.filename).name.lower() == exe_name.lower()]
        if not candidates:
            raise ValueError(f"no {exe_name} member inside {archive.name}")
        if len(candidates) > 1:
            raise ValueError(f"{archive.name} holds {len(candidates)} members named {exe_name}; "
                             "the packaged executable is not unambiguously identified")
        info = candidates[0]
        member = PurePosixPath(info.filename)
        # Reject traversal, absolute and single-segment paths before any byte is written;
        # only the member's own final name is materialised, inside the caller's scratch root.
        if member.is_absolute() or member.drive or ".." in member.parts or len(member.parts) < 2:
            raise ValueError(f"unsafe member path inside archive: {info.filename}")
        if int(info.file_size) > max_bytes:
            raise ValueError(f"member {info.filename} exceeds the extraction bound of {max_bytes} bytes")
        payload = bundle.read(info)
        if len(payload) > max_bytes:
            raise ValueError(f"member {info.filename} expands beyond the extraction bound of "
                             f"{max_bytes} bytes")
        target = destination / member.name
        target.write_bytes(payload)
        return target, info.filename


def run_signing(*, release_metadata_path: Path, runner: Runner = default_runner,
                timeout: int = 120, exe_name: str = "DrillMaster.exe") -> dict:
    """Record Authenticode status for every executable this release actually ships.

    Two files decide the verdict: the compiled installer, and the portable bundle's
    application executable *as extracted from the hash-verified portable archive*.
    The bundle copy sitting in the release directory is not evidence, because nothing
    binds it byte-for-byte to the published ZIP; the inner copy therefore comes out of
    the archive after that archive's own recorded digest has been re-checked.  A
    container archive is recorded as ``NOT_APPLICABLE`` because "a ZIP is unsigned" is
    not a statement about trust.
    """
    metadata = read_release_manifest(release_metadata_path)
    release_root = release_metadata_path.parent
    script_text = ""
    for candidate in (_PACKAGING_DIR / "build_windows.ps1", _PACKAGING_DIR / "DrillMaster.iss"):
        if candidate.is_file():
            script_text += candidate.read_text(encoding="utf-8", errors="replace")
    signing_configured = bool(re.search(r"signtool|SignTool=|SignedUninstaller", script_text, re.IGNORECASE))
    credential_env_present = sorted(key for key in os.environ
                                    if SECRET_ENV_PATTERN.search(key)
                                    and re.search(r"SIGN|CERT|PFX|AUTHENTICODE", key, re.IGNORECASE))
    files: list[dict] = []
    examined: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="drillmaster-signing-") as directory:
        scratch = Path(directory)

        installer_path, installer_entry = _artifact_by_suffix(metadata, release_root, "-setup.exe")
        zip_path, zip_entry = _artifact_by_suffix(metadata, release_root, ".zip")
        # Both files are bound to a recorded digest before being queried: the installer by
        # its own manifest entry, the inner executable by the archive it was extracted from.
        _digest_matches(installer_path, installer_entry, "compiled installer")
        outer_digest = _digest_matches(zip_path, zip_entry, "portable archive")
        inner_path, inner_member = extract_verified_member(zip_path, exe_name, scratch)
        targets = [
            {"path": installer_path, "provenance": "compiled installer in the release directory",
             "container": None, "container_digest": None, "member": None},
            {"path": inner_path, "provenance": f"extracted from {zip_path.name}",
             "container": zip_path.name, "container_digest": outer_digest, "member": inner_member},
        ]

        for spec in targets:
            # Every path here has just been read and digest-verified, so its size and hash are
            # facts about the examined bytes; there is no "not found" branch to soften a result.
            path = spec["path"]
            record = {"filename": path.name, "provenance": spec["provenance"],
                      "size_bytes": path.stat().st_size, "sha256": sha256_file(path),
                      "signature_bearing": path.suffix.lower() in (".exe", ".dll", ".msi"),
                      "manifest_digest_match": True}
            if spec["container"]:
                # Inner and outer digests are separate fields and are never interchangeable.
                record["container_archive"] = spec["container"]
                record["container_archive_sha256"] = spec["container_digest"]
                record["container_member"] = spec["member"]
            payload = run_powershell(SIGNATURE_QUERY_SCRIPT, path, runner, timeout)
            if "error" in payload:
                record.update({"status": "UNKNOWN", "status_message": payload["error"]})
            else:
                raw_status = str(payload.get("Status") or "").strip()
                record["raw_status"] = bound(raw_status, 80)
                record["status"] = raw_status or "UNKNOWN"
                record["status_message"] = bound(str(payload.get("StatusMessage") or ""), 300)
                subject = payload.get("SignerSubject")
                if subject:
                    # A subject is public information, but it is still bounded here.
                    record["signer"] = bound(str(subject), 300)
            files.append(record)
            if record["signature_bearing"]:
                examined.append(record)

        # The archives themselves are recorded, but excluded from the verdict.
        for entry in metadata.get("artifacts", []):
            name = Path(str(entry.get("filename", ""))).name
            if name.lower().endswith((".zip", ".exe")) and not name.lower().endswith("-setup.exe"):
                files.append({"filename": name, "provenance": "published release artifact",
                              "size_bytes": entry.get("size_bytes"), "sha256": entry.get("sha256"),
                              "signature_bearing": False, "status": NOT_APPLICABLE,
                              "status_message": "container archive; Authenticode applies to the executables it carries"})

    status = aggregate_signing_status(files)
    if status not in SIGNING_STATUS_VOCABULARY:
        raise ValueError(f"signature tool produced a status outside the vocabulary: {status!r}")
    return {
        "schema": "drillmaster-signing-status/v1",
        "method": "Windows Get-AuthenticodeSignature",
        "status": status,
        "policy": ("unsigned publication is the current release policy: a recorded signature state, including "
                   "FAIL, is a distribution-trust finding and never fails the packaging gate, a result that could "
                   "not be examined is never reported as UNSIGNED, and a run that produced no interpretable "
                   "record does fail the gate"),
        "files": files,
        "examined_count": len(examined),
        "archive_count": len(files) - len(examined),
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
            digest = f"; sha256: {item['sha256'][:16]}..." if item.get("sha256") else ""
            reason = f"; reason: {bound(str(item['status_message']), 160)}" if item.get("status_message") else ""
            origin = f"; from: {item['provenance']}" if item.get("provenance") else ""
            container = (f"; inside `{item['container_member']}` of {item['container_archive']} "
                         f"(sha256 {item['container_archive_sha256'][:16]}...)"
                         if item.get("container_member") else "")
            lines.append(f"- `{item['filename']}` — {item['status']}{signer}{digest}{origin}{container}{reason}")
    if report.get("policy"):
        lines += ["", f"Policy: {report['policy']}"]
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
        try:
            metadata = read_release_manifest(args.release_metadata)
            entry = _installer_entry(metadata, args.installer.resolve())
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
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
                                   runner=default_runner, exe_name=args.exe_name, timeout=args.timeout,
                                   settle_seconds=args.settle_seconds)
    else:
        if sys.platform != "win32":
            report = {"schema": "drillmaster-signing-status/v1", "status": "NOT_RUN",
                      "reason": "Authenticode verification requires a Windows host", "files": [],
                      "signing_configured_in_build": False, "credentials_available": False, "prerequisite": ""}
        else:
            try:
                report = run_signing(release_metadata_path=args.release_metadata.resolve(),
                                     runner=default_runner, timeout=args.timeout)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                # No signing state can fail the packaging gate, but a signing step that
                # produced no record at all is a tooling failure and must look like one.
                print(f"ERROR: signature verification produced no record: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                return 1

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(render_markdown(report, f"Windows {args.command} evidence"), encoding="utf-8")
    print(json.dumps({"command": args.command, "status": report.get("status"),
                      "files": [{"filename": item.get("filename"), "status": item.get("status")}
                                for item in report.get("files", [])]}, sort_keys=True))
    if args.command == "signing":
        return 0
    return 0 if str(report.get("status")) in {"PASS", "NOT_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
