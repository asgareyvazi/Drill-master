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
import errno
import io
import json
import os
import re
import shutil
import stat
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
    SIGNING_FILE_VOCABULARY as FILE_STATUS_VOCABULARY,
    SIGNING_NOT_APPLICABLE as NOT_APPLICABLE,
    SIGNING_SCHEMA as SIGNING_STATUS_SCHEMA,
    SIGNING_STATUS_VOCABULARY,
    aggregate_signing_status as signing_aggregate,
    normalize_authenticode_status,
    sha256_file,
    sha256_stream,
    validate_document,
    validate_signing_document,
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
# The query has to distinguish "Windows answered" from "the statement that asks failed".
# Without the try/catch a cmdlet error is written to stderr, $signature stays null, the
# hashtable still serialises, and the script exits 0 with an empty Status: an UNKNOWN that
# carried no cause anywhere in the published record.  ErrorAction Stop plus a captured message
# makes the same failure report itself.
# The Windows gate confirmed on its first instrumented run that the runner's `-NoProfile`
# Windows PowerShell host does not resolve Get-AuthenticodeSignature at all ("cmdlet=missing"),
# so the answer was never a signature state.  A profileless session does not auto-load the
# Security module the way an interactive one does, so both scripts import it explicitly first;
# if that import is itself refused, the record says so instead of reporting a bare UNKNOWN.
SIGNATURE_QUERY_SCRIPT = (
    "Import-Module Microsoft.PowerShell.Security -ErrorAction SilentlyContinue; "
    "$result = @{Status=''; StatusMessage=''; SignerSubject=$null; QueryError=''}; "
    "try { "
    "$signature = Get-AuthenticodeSignature -LiteralPath $env:DRILLMASTER_TARGET_PATH -ErrorAction Stop; "
    "$result.Status = [string]$signature.Status; "
    "$result.StatusMessage = [string]$signature.StatusMessage; "
    "if ($signature.SignerCertificate) { $result.SignerSubject = [string]$signature.SignerCertificate.Subject } "
    "} catch { $result.QueryError = $_.Exception.Message }; "
    "$result | ConvertTo-Json -Compress"
)
# Capability probe, run before any file is queried, so "this host cannot answer the question"
# is recorded once as a cause instead of surfacing as several unexplained UNKNOWN rows.
#
# The probe answers two separate questions and never mixes them up.  Whether
# `Import-Module Microsoft.PowerShell.Security` worked is captured from the import itself, with
# `-ErrorAction Stop` inside `try`/`catch` so the real message survives; whether
# `Get-AuthenticodeSignature` can then be resolved is a second, independent lookup.  An earlier
# version published `module_import` as a renaming of the command lookup, which let a record claim
# that an import had failed on the strength of evidence about something else.  Both observations
# are published, and the field names say which one each is.
SIGNING_PROBE_SCRIPT = (
    "$probe = @{ps_version=[string]$PSVersionTable.PSVersion; cmdlet='missing'; module=''; "
    "security_module_import='unreported'; security_module_import_error=''}; "
    "try { Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; "
    "$probe.security_module_import = 'succeeded' } "
    "catch { $probe.security_module_import = 'failed'; "
    "$probe.security_module_import_error = [string]$_.Exception.Message }; "
    "$command = Get-Command Get-AuthenticodeSignature -ErrorAction SilentlyContinue; "
    "if ($command) { $probe.cmdlet = 'available'; "
    "if ($command.Source) { $probe.module = [string]$command.Source } }; "
    "$probe | ConvertTo-Json -Compress"
)
SECRET_ENV_PATTERN = re.compile(r"(PASSWORD|API_KEY|TOKEN|SECRET|CREDENTIAL)", re.IGNORECASE)
# Stated once, because both the record a Windows run produces and the record a non-Windows host
# publishes have to promise the same thing about what a signature finding does to the gate.
SIGNING_POLICY = ("unsigned publication is the current release policy: a recorded signature state, including "
                  "FAIL, is a distribution-trust finding and never fails the packaging gate, a result that could "
                  "not be examined is never reported as UNSIGNED, and a run that produced no interpretable "
                  "record does fail the gate")


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], dict[str, str] | None, Path | None, int], CommandResult]


def aggregate_signing_status(files: list[dict]) -> str:
    """Signing aggregation is defined once, in ``release_metadata``, and used unchanged here.

    The name deliberately stays in this module: the acceptance report has to fold the same
    per-file findings the same way, so a second, subtly different rule cannot drift into being.
    """
    return signing_aggregate(files)


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


def run_powershell(script: str, target: Path, runner: Runner, timeout: int, *,
                   required_field: str = "") -> dict:
    """Query Windows shell metadata for a path without interpolating it into the script.

    ``required_field`` names the answer the caller actually needs.  A script can exit 0 while
    the statement that produced that field failed, and that used to read as a successful empty
    answer: exit code zero plus a parseable payload was never cross-checked against the reason
    PowerShell wrote to stderr.  Carrying the bounded stderr and the exit code with the payload
    is what turns "UNKNOWN" into "UNKNOWN because ...".  A call that never returned -- a timed-out
    or unstartable shell -- is reported the same way rather than allowed to escape as a traceback.
    """
    environment = dict(os.environ)
    environment["DRILLMASTER_TARGET_PATH"] = str(target)
    try:
        completed = runner(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", script], environment, None, timeout)
    except subprocess.TimeoutExpired:
        # The host did not answer inside the budget.  That is a capability finding with a stated
        # cause, and it has to reach the record: an escaping TimeoutExpired instead left the
        # release directory with no signing-status.json at all, which the gate could only report
        # as "produced no record" while the real reason sat in a traceback in the console.
        return {"error": f"powershell did not answer within {timeout} seconds"}
    except OSError as exc:
        # powershell.exe is not launchable here at all.  Every row records that cause instead of
        # the tool dying, so a run that could not ask the question stays separable from a tool
        # that broke -- which is the distinction the report's contract depends on.
        return {"error": f"powershell could not be started: {type(exc).__name__}: {str(exc)[:120]}"}
    except subprocess.SubprocessError as exc:
        # The shell ran and the harness could not collect its result (killed, pid recycled).
        return {"error": f"powershell invocation failed: {type(exc).__name__}: {str(exc)[:120]}"}
    output = (getattr(completed, "stdout", "") or "").strip()
    error_text = (getattr(completed, "stderr", "") or "").strip()
    if completed.returncode != 0 or not output:
        # The exit code alone cannot be acted on: PowerShell reports the reason on stderr.
        return {"error": f"powershell exit {completed.returncode}: "
                         f"{bound(error_text or output, 300)}"}
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        detail = error_text or output
        return {"error": f"powershell returned unreadable output: {bound(detail, 200)}"}
    if not isinstance(payload, dict):
        return {"error": f"powershell returned a non-object (exit code {completed.returncode})"}
    # The exit code is carried for every payload that parsed, not only for the ones that also wrote
    # to stderr: the record should report what the host returned rather than let a reader infer that
    # a printed payload implies a zero exit status.
    payload.setdefault("powershell_exit_code", completed.returncode)
    if error_text:
        # A statement-level failure inside a script that still printed a payload used to be
        # invisible, because a parseable object was treated as a complete answer.
        payload.setdefault("powershell_stderr", bound(error_text, 600))
    if required_field and not str(payload.get(required_field, "") or "").strip():
        detail = error_text or f"exit code {completed.returncode}"
        payload.setdefault("error", f"powershell exited {completed.returncode} without reporting "
                                    f"{required_field}: {bound(detail, 300)}")
    return payload


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


MAX_FORENSIC_HASH_BYTES = 64 * 1024 * 1024
FORENSIC_NOTE = ("host-side evidence is not collected: this step reads only userspace filesystem state "
                 "and cannot open security or defender event logs, so an external removal can be observed "
                 "and bounded but never attributed to an agent")


def _observed_path(path: Path, *, hash_file: bool = False, permitted_root: Path | None = None,
                   root_identity: tuple[int, ...] | None = None) -> dict:
    """What one unprivileged stat can say about a path, right now, without creating or touching it.

    Absence and unreadability are separate observations from "present with these properties", because
    the failure this records is precisely a disagreement between a check and a later use of the same
    path.  Values are bounded, and no path content is published beyond a digest of the uninstaller
    itself when it is small enough to hash.
    """
    # Every key is written on every path through this function: a reader of the published JSON should
    # not have to infer what an absent field meant, and "not a file" and "not reported" are different
    # claims.  The exception is the `*_error` keys, whose presence is itself the finding.
    observed: dict = {"path": bound(str(path), 200), "exists": False, "is_file": False, "is_dir": False}
    try:
        resolved = path.resolve()
    except OSError as exc:  # a dangling reparse point can fail even to resolve
        observed["resolve_error"] = bound(f"{type(exc).__name__}: {exc}", 120)
        return observed
    observed["resolves_to"] = bound(str(resolved), 200)
    observed["resolves_identity"] = str(resolved) == str(path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return observed
    except OSError as exc:
        # Present enough to resolve, unusable enough to fail a stat: that is its own finding.
        observed["exists"] = True
        observed["stat_error"] = bound(f"{type(exc).__name__}: {exc}", 120)
        return observed
    observed.update({"exists": True, "is_file": path.is_file(), "is_dir": path.is_dir(),
                     "size_bytes": stat.st_size, "modified_ns": stat.st_mtime_ns,
                     "device": stat.st_dev, "inode": stat.st_ino})
    attributes = getattr(stat, "st_file_attributes", None)
    observed["file_attributes_reported"] = attributes is not None  # Windows only, never guessed at
    if attributes is not None:
        observed["file_attributes"] = int(attributes)
        observed["reparse_point"] = bool(attributes & getattr(stat, "ST_REPARSE_POINT", 0))
    if hash_file and observed["is_file"]:
        # The bound and the digest are decided on the object that is *open*, never on a second stat of the
        # name: the size that triggers the bound, the bytes that are hashed, and the identity that gets
        # published all come from one handle.  A pathname digest is a digest of whatever the name denoted
        # when it was opened, which on a machine where the path can be re-pointed is not a claim about the
        # file that was checked.  A refusal is its own recorded state; it never degrades into a zero, an
        # empty string, or the digest of something nearby.
        if permitted_root is not None and not _is_within(path, permitted_root):
            # A name already outside the boundary needs no open to refuse.  This is a fast reject, not the
            # guarantee -- `_open_binary` below decides on the object it reached, because `resolve` follows
            # links and can be answered differently a moment later.
            observed["hash_state"] = "skipped_unsafe_path"
            observed["hash_reason"] = "resolves outside the permitted evidence root; not hashed"
            return observed
        try:
            stream, meta = _open_binary(path, permitted_root, root_identity)
        except AnchorRefusal as refusal:
            # Which refusal it was stays visible: a name that led out of the boundary is a different fact
            # from an object that could not be read, and only the first is a confinement finding.  Neither
            # is ever reported as a hash.
            observed["hash_state"] = refusal.state if refusal.state in _HASH_STATES else "unreadable"
            observed["hash_reason"] = bound(refusal.reason, 200)
            return observed
        except FileNotFoundError:
            observed["hash_state"] = "unreadable"
            observed["hash_reason"] = "no such file when the digest was attempted"
            return observed
        except OSError as exc:
            observed["hash_state"] = "unreadable"
            observed["hash_reason"] = bound(f"{type(exc).__name__}(errno={exc.errno}, "
                                            f"winerror={getattr(exc, 'winerror', None)})", 160)
            return observed
        with stream:
            size = int(meta.get("size", stat.st_size))
            if not meta.get("is_regular", True):
                observed["hash_state"] = "unreadable"
                observed["hash_reason"] = "not a regular file"
                return observed
            if size > MAX_FORENSIC_HASH_BYTES:
                # Over the bound the object was not hashed, and saying "hashed" here would be the record
                # claiming a property it did not establish; the note travels in both fields for that reason.
                observed["hash_state"] = "unreadable"
                observed["hash_reason"] = (f"not hashed: {size} bytes exceeds the {MAX_FORENSIC_HASH_BYTES}"
                                           "-byte forensic bound")
                observed["sha256"] = observed["hash_reason"]
                return observed
            observed["hash_state"] = "hashed"
            observed["sha256"] = sha256_stream(stream)
            observed["hash_bytes"] = size
            observed["hash_confinement"] = meta.get("confinement", "")
            opened_identity = meta.get("object_identity")
            if opened_identity is not None and stat.st_dev and stat.st_ino:
                # A disagreement here is the check-then-use race caught in the act: the name still described
                # a file, but the object behind it is not the one that was stat'd.  It is recorded and never
                # repaired, and it never changes what the lifecycle step itself decided.
                observed["replaced_before_open"] = list(opened_identity) != [stat.st_dev, stat.st_ino]
    return observed


def _uninstall_forensics(*, install_dir: Path, work_root: Path, uninstaller: Path,
                         install_log: Path, uninstall_log: Path, sentinel: Path | None,
                         error: BaseException | None, hash_uninstaller: bool = True,
                         root_identity: tuple[int, ...] | None = None) -> dict:
    """A single bounded sample of every filesystem fact that distinguishes the failure shapes.

    Five states look alike from a launch refusal: the uninstaller was never created; it exists and
    something else refused the process; it was present and then taken away; the whole install tree was
    removed; or an uninstall genuinely ran and deleted the uninstaller along with the application (a
    completed run leaves its own log behind, which is why the log's presence is part of the sample).
    Recording these fields at each point of use is what lets the published record tell them apart
    later, without a runner log or artifact access.
    """
    def log_state(path: Path) -> dict:
        """Whether an Inno log exists, whether it could be read, and what the readable part said.

        The installer and uninstaller write their logs under the work root, so the gate can read them
        without elevation; their tails are the only place a completed uninstall is visible after the
        uninstaller has deleted itself.  Four facts are kept apart on purpose -- present, measurable,
        readable, and read -- because the log can change between any two of them, and this sampler runs
        while an unrelated failure is being described: an exception escaping here would replace the
        launch error with a diagnostic error and lose both findings.  Tails are collapsed onto one
        line, bounded again for publication, and pass through the same credential redaction as the
        rest of the sample, because a log can echo a value from the launching environment.
        """
        state: dict = {"path": bound(str(path), 200)}
        try:
            state["exists"] = path.is_file()
        except OSError as exc:  # documented not to raise, yet a reparse point can disagree
            state["exists"] = False
            state["exists_error"] = bound(type(exc).__name__, 60)
        observed = _bounded_tail(path, 6, permitted_root=work_root, root_identity=root_identity)
        state["read_state"] = observed["state"]
        state["size_bytes"] = observed["size_bytes"]
        state["bytes_read"] = observed["bytes_read"]
        if observed["reason"]:
            state["read_reason"] = bound(observed["reason"], 200)
        if observed["dropped_partial_first_line"]:
            state["dropped_partial_first_line"] = True
        if observed.get("first_line_is_fragment"):
            state["first_line_is_fragment"] = True
        if observed.get("grew_during_read"):
            state["grew_during_read"] = True
        state["read_confinement"] = bound(observed.get("confinement", ""), 200)
        state["tail"] = bound(" ".join(observed["tail"].split()), 400)
        return state

    # One listing per sample: the count and the names are two views of the same moment, and taking
    # them in two passes would let a concurrent delete or create make the published count disagree
    # with the names printed beside it.
    entries = sorted(snapshot(install_dir))

    sample: dict = {"sampled_at": round(time.time(), 3),
                    "work_root": _observed_path(work_root),
                    "install_dir": _observed_path(install_dir),
                    "uninstaller": _observed_path(uninstaller, hash_file=hash_uninstaller,
                                                  permitted_root=work_root, root_identity=root_identity),
                    "install_dir_entries": {"count": len(entries), "first": entries[:8]},
                    "install_log": log_state(install_log),
                    "uninstall_log": log_state(uninstall_log),
                    "parent_dir": _observed_path(install_dir.parent),
                    "sentinel": {"exists": bool(sentinel and sentinel.is_file())},
                    "host_side_evidence": FORENSIC_NOTE}
    if error is not None:
        # errno and winerror are the fields that separate "no such file" from "no such directory"
        # or "access denied"; they are copied from the exception, never inferred from its text.
        sample["launch_error"] = {
            "class": type(error).__name__,
            "errno": getattr(error, "errno", None),
            "winerror": getattr(error, "winerror", None),
            "filename": bound(str(getattr(error, "filename", "") or ""), 200),
            "filename2": bound(str(getattr(error, "filename2", "") or ""), 200),
            "message": bound(str(error)[:300], 300)}
    return sample


def _forensic_brief(sample: dict) -> str:
    """The same scalars in a compact form, for places where the step bound would eat a label.

    `_step` clips a detail to the diagnostic bound, and clipping keeps the head and the tail: a long
    per-attempt note therefore used to lose the "attempt 2:" label itself while keeping its content,
    which is the one thing a reader needs to order the events.  The brief form keeps each entry short
    enough that every label survives, and the full block stays in `diagnostics`.
    """
    def flag(key: str, field: str) -> str:
        block = sample.get(key) or {}
        if "stat_error" in block:
            return "unreadable"
        return "present" if block.get(field) else "absent"

    error = sample.get("launch_error") or {}
    codes = ",".join(f"{key}={error[key]}" for key in ("errno", "winerror") if error.get(key) is not None)
    return (f"dir={flag('install_dir', 'is_dir')} entries={(sample.get('install_dir_entries') or {}).get('count', '?')} "
            f"root={flag('work_root', 'is_dir')} unins={flag('uninstaller', 'is_file')} "
            + (f"launch={error.get('class', '?')}{'' if not codes else ' (' + codes + ')'} " if error else "")
            + f"uninslog={'present' if (sample.get('uninstall_log') or {}).get('exists') else 'absent'}")


def _forensic_note(sample: dict) -> str:
    """The decisive scalars from a sample, short enough to live inside a step detail."""
    install = sample.get("install_dir") or {}
    uninstaller = sample.get("uninstaller") or {}
    parts = [f"install dir {'present' if install.get('is_dir') else 'absent'}",
             f"{(sample.get('install_dir_entries') or {}).get('count', 'unreported')} file(s)",
             f"work root {'present' if (sample.get('work_root') or {}).get('is_dir') else 'absent'}",
             f"uninstaller {'listed' if uninstaller.get('is_file') else 'not listed'}"]
    error = sample.get("launch_error") or {}
    if error:
        codes = [f"{key}={error[key]}" for key in ("errno", "winerror") if error.get(key) is not None]
        parts.append(f"launch {error.get('class', 'error')}" + (f" ({', '.join(codes)})" if codes else ""))
    log = sample.get("uninstall_log") or {}
    parts.append("uninstall log " + ("written" if log.get("exists") else "absent, so no uninstaller process completed"))
    return "; ".join(parts)


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
    # The identity of the root this run is working inside, captured once and compared by every anchored
    # open below.  It is the answer to "which directory?", which a pathname cannot answer for as long as
    # another actor can edit the parent: if the work root is deleted and re-created, or re-pointed, the
    # reads refuse rather than silently confining themselves to the replacement.
    work_root_identity = _directory_identity(work_root)
    evidence: dict[str, object] = {"steps": [], "diagnostics": {}}
    evidence["diagnostics"]["work_root_identity_reported"] = work_root_identity is not None
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
        evidence["diagnostics"]["install_log"] = redact(_tail(install_log, permitted_root=work_root,
                                                               root_identity=work_root_identity), [])
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
        # The marker scan is the reason this window is wider than a status line: 400 lines, bounded to
        # LOG_TAIL_BYTES of actual reading, and whatever it managed to see is stated in the record
        # rather than assumed to have been the whole log.
        smoke_log = _bounded_tail(smoke_root / "logs" / "drillmaster.log", 400, permitted_root=work_root,
                                  root_identity=work_root_identity)
        smoke_log_text = smoke_log["tail"]
        evidence["diagnostics"]["smoke_log_read_state"] = smoke_log["state"]
        evidence["diagnostics"]["smoke_log_bytes_read"] = smoke_log["bytes_read"]
        observed_output = f"{smoke_output}\n{smoke_log_text}"
        leaked = [value for value in secret_values if value and value in observed_output]
        after = snapshot(install_dir)
        created = sorted(set(after) - set(before))
        changed = sorted(name for name in set(after) & set(before) if after[name] != before[name])
        # Deletions are recorded as their own channel.  A file can disappear from {app} while the
        # installed executable runs -- on one gate run the uninstaller did exactly that, between the
        # step that had proved it present and the step that tried to use it -- and a claim about the
        # install tree that only looks at additions and edits cannot describe such a window.
        deleted = sorted(set(before) - set(after))
        log_written = (smoke_root / "logs" / "drillmaster.log").is_file()
        # An exit code of 0 is not the same claim as "the smoke ran": an executable that
        # returns cleanly without completing the smoke must never satisfy this step.
        marker_found = "PACKAGE_SMOKE_OK" in observed_output
        fatal_found = bool(re.search(r"FATAL|Traceback \(most recent call last\)", observed_output))
        details = {"exit_code": smoke.returncode, "wrote_log_outside_install_dir": log_written,
                   "secret_leak_detected": bool(leaked), "new_files_in_install_dir": created[:20],
                   "changed_files_in_install_dir": changed[:20],
                   "deleted_files_in_install_dir": deleted[:20],
                   "success_marker_found": marker_found, "fatal_marker_found": fatal_found,
                   "success_marker_channel": ("stdout" if "PACKAGE_SMOKE_OK" in smoke_output
                                              else "application-log" if marker_found else "none")}
        evidence["diagnostics"]["installed_smoke_output"] = redact(observed_output, secret_values)
        evidence["installed_smoke"] = details
        if (smoke.returncode != 0 or leaked or created or changed or not log_written
                or not marker_found or fatal_found):
            record("installed_smoke", "FAIL", json.dumps(details, sort_keys=True))
            return _finish(evidence, "FAIL", started)
        containment_note = (f"install tree gained nothing and changed nothing, but {len(deleted)} file(s) "
                            f"disappeared while it ran: {', '.join(deleted[:8])}" if deleted
                            else "install tree unchanged")
        record("installed_smoke", "PASS",
               f"exit 0; success marker via {details['success_marker_channel']}; no fatal marker; log written "
               f"outside the install directory; {containment_note}")

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
        def install_tree_note() -> str:
            entries = sorted(snapshot(install_dir))
            shown = entries[:12]
            presence = "directory present" if install_dir.is_dir() else "directory absent"
            return (f"install tree holds {len(entries)} file(s) ({presence}): {', '.join(shown) or 'nothing'}"
                    + (f" (+{len(entries) - len(shown)} more)" if len(entries) > len(shown) else ""))

        # Every sample is taken at the point of use and published twice: the structured block under
        # `diagnostics.uninstall_forensics`, which the acceptance report forwards, and the decisive
        # scalars inside the step detail, which is what a reviewer can still read from the job
        # annotation when the artifact and log endpoints are unreachable.  Samples are keyed by the
        # moment they were taken and never overwrite one another, because the order of the
        # observations is the finding: "listed, then refused, then absent" is a different event from
        # "never created", and only the sequence can say which one happened.
        samples: dict[str, dict] = {}

        def forensics(label: str, error: BaseException | None = None, *, hash_uninstaller: bool = True,
                      brief: bool = False) -> str:
            """Sample, redact and publish -- and never let the sampling itself become the finding.

            This runs from inside a `except FileNotFoundError:` handler.  A second exception raised
            while describing the first would replace the lifecycle result with a diagnostic one and
            lose both, so any unexpected failure here is recorded as a bounded observation of its own
            and the original launch error keeps travelling to the step detail.
            """
            try:
                sample = _uninstall_forensics(install_dir=install_dir, work_root=work_root,
                                              uninstaller=uninstaller, install_log=install_log,
                                              uninstall_log=uninstall_log, sentinel=sentinel, error=error,
                                              hash_uninstaller=hash_uninstaller,
                                              root_identity=work_root_identity)
            except Exception as exc:  # noqa: BLE001 - a sampler defect must not mask a lifecycle failure
                sample = {"state": "sampler_failed",
                          "reason": bound(f"{type(exc).__name__}: {str(exc)[:160]}", 200)}
            samples[label] = _redact_tree(sample, secret_values)
            evidence["diagnostics"]["uninstall_forensics"] = samples
            if sample.get("state") == "sampler_failed":
                return f"diagnostics unavailable ({sample['reason']})"
            return _forensic_brief(samples[label]) if brief else _forensic_note(samples[label])

        forensics("pre_launch")
        if not uninstaller.is_file():
            # installed_files already proved this file existed, so its absence here is a finding
            # about what happened in between -- not a missing-artifact mystery.  Saying so, with
            # the tree listing and the installer's own log tail, is what makes the failure
            # attributable from the published record alone.
            absent = forensics("uninstaller_absent_before_launch", hash_uninstaller=False)
            record("silent_uninstall", "FAIL",
                   "unins000.exe was present after install (installed_files) and is absent now; "
                   f"{install_tree_note()}; {absent}; installer log tail: "
                   f"{bound(_tail(install_log, 12, permitted_root=work_root), 200) or 'no log'}")
            return _finish(evidence, "FAIL", started)
        # A Windows runner can list a file it then refuses to launch: an uninstaller under
        # antivirus quarantine, or mid-replacement, looks exactly like this from userspace, with
        # the presence check and the exec microseconds apart.  The two shapes -- never created, and
        # created then taken away -- are different findings, so one bounded settle and a re-listing
        # follow the first refusal.  Nothing is excused: the uninstall still has to empty {app},
        # which is the claim this step exists to prove.
        notes: list[str] = []
        refused_attempts: list[str] = []
        last_brief = ""
        removed: dict | None = None
        for attempt in (1, 2):
            try:
                removed = _uninstall(uninstaller, uninstall_log, install_dir, runner, timeout,
                                     poll_interval, settle_seconds, evidence)
                break
            except FileNotFoundError as exc:
                refused = forensics(f"after_refusal_{attempt}", exc, brief=True)
                refused_attempts.append(f"attempt {attempt}: refused ({refused})")
                last_brief = refused
                notes.append(f"attempt {attempt}: unins000.exe was listed but could not be launched "
                             f"({type(exc).__name__}: {str(exc)[:120]}); {install_tree_note()}; {refused}")
                if attempt == 2:
                    break
                time.sleep(2.0)
                relisted = uninstaller.is_file()
                settled = forensics("after_settle", hash_uninstaller=relisted, brief=True)
                notes.append("after a 2 second settle the uninstaller is "
                             + (f"still listed; {settled}" if relisted else f"gone; {settled}"))
                if relisted:
                    refused_attempts.append(f"settle: the uninstaller is still listed "
                                           f"({_forensic_brief(samples['after_settle'])})")
                else:
                    refused_attempts.append(f"settle: the uninstaller is gone ({settled})")
                if not relisted:
                    # It was taken away, not merely busy: a second attempt would be a guess, and the
                    # finding the record has to carry is the disappearance itself.
                    break
            except (OSError, subprocess.SubprocessError) as exc:
                # Any other launch failure is sampled the same way: a refusal with the install tree
                # intact and its log absent is a different finding from a refusal after a completed
                # uninstall, and the winerror is copied from the exception rather than read off text.
                refused = forensics(f"launch_error_{type(exc).__name__}", exc, brief=True)
                record("silent_uninstall", "FAIL",
                       f"{type(exc).__name__}: {str(exc)[:200]}; {refused}")
                return _finish(evidence, "FAIL", started)
        if removed is None:
            # The step detail is clipped to the diagnostic bound, and clipping keeps the head and the
            # tail -- so a concatenation of long per-attempt notes used to drop the very labels that
            # ordered them.  The summary names every refusal in order; the full prose stays in
            # `uninstall_launch_notes` and the structured samples in `diagnostics.uninstall_forensics`.
            evidence["uninstall_launch_notes"] = bound("; ".join(notes), 1200)
            # mirrored into `diagnostics` because the acceptance report forwards that block; without
            # the copy the per-attempt prose would exist only in the evidence file on the runner.
            evidence["diagnostics"]["uninstall_launch_notes"] = evidence["uninstall_launch_notes"]
            summary = ("unins000.exe was listed before launch and no launch completed; "
                       + "; ".join(refused_attempts or [last_brief or "launch refused"])
                       + "; full notes in uninstall_launch_notes, samples in diagnostics.uninstall_forensics")
            record("silent_uninstall", "FAIL", bound(summary, 1200))
            return _finish(evidence, "FAIL", started)
        if notes:
            evidence["uninstall_launch_recovered"] = bound("; ".join(notes), 1200)
            evidence["diagnostics"]["uninstall_launch_recovered"] = evidence["uninstall_launch_recovered"]
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

        sentinel_state, sentinel_note, sentinel_content = "read", "", ""
        try:
            # The sentinel is the one content read whose result can turn a FAIL into a PASS, so it is read
            # through the same anchored handle as the logs: a `sentinel-preserve.txt` re-pointed at some
            # other file must not be able to certify that user data survived.  A refusal is reported as a
            # refusal, and the step still fails -- an unsafe observation never becomes a pass.
            stream, _meta = _open_binary(sentinel, work_root, work_root_identity)
            with stream:
                sentinel_content = stream.read(len(sentinel_text) + 1).decode("utf-8", errors="replace")
        except AnchorRefusal as refusal:
            sentinel_state, sentinel_note = "refused", refusal.reason
        except (OSError, ValueError) as exc:
            sentinel_state = "unreadable"
            sentinel_note = f"{type(exc).__name__}(errno={getattr(exc, 'errno', None)})"
        if sentinel_content != sentinel_text:
            record("user_data_preserved", "FAIL", "the synthetic user-data sentinel did not survive uninstall"
                   + (f" (sentinel read {sentinel_state}: {bound(sentinel_note, 120)})"
                      if sentinel_state != "read" else ""))
            evidence["diagnostics"]["sentinel_read_state"] = sentinel_state
            return _finish(evidence, "FAIL", started)
        evidence["diagnostics"]["sentinel_read_state"] = "read"
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


_WIN32_GENERIC_READ = 0x80000000
_WIN32_SHARE_ALL = 0x00000007  # READ | WRITE | DELETE: the sharing Python's own open() asks a file for
_WIN32_OPEN_EXISTING = 0x00000003
_WIN32_BACKUP_SEMANTICS = 0x02000000  # required to open a directory for metadata, not to read a file
_WIN32_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_WIN32_INVALID_HANDLE = 0xFFFFFFFFFFFFFFFF
# GetFileType, from winbase.h.  Both filesystem kinds are acceptable -- a redirected share is still a
# file -- while a pipe or a character device is not a log and is refused before anything is read.
_WIN32_FILE_KINDS = {0x0000: "unknown", 0x0001: "disk", 0x0002: "character device", 0x0003: "pipe",
                     0x8000: "disk"}
_WIN32_REGULAR_FILE_KINDS = frozenset({"disk"})
_WIN32_NOT_FOUND = (2, 3)  # ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND
_WIN32_LINK_OR_REPARSE = (1831, 1921)  # crossing an unsupported link target, refusing to follow it
_WIN32_HANDLE_METADATA_FIELDS = ("dwFileAttributes", "nFileSizeHigh", "nFileSizeLow", "dwVolumeSerialNumber",
                                 "nFileIndexHigh", "nFileIndexLow")
# `os.O_BINARY` exists only on Windows, and there it is not decorative: a CRT descriptor left in the default
# mode folds every CRLF to LF while it is read, so the bytes handed back are a shortened copy of the object
# and the recorded read stops agreeing with the size measured on the handle.  The literal mirrors the Windows
# value (0x8000 in the UCRT) so the expression means the same thing -- and can be asserted -- on a host that
# has no `os.O_BINARY` to consult; on such a host the value is never passed to the platform, because only the
# Windows branch attaches a handle at all.
_WIN32_O_BINARY = 0x8000
_WIN32_READ_FLAGS = os.O_RDONLY | getattr(os, "O_BINARY", _WIN32_O_BINARY)

_WIN32_API: object | None = None
_WIN32_API_UNAVAILABLE = False


class _Win32HandleMetadata:
    """The four kernel32 calls an anchored Windows open needs, bound once and used for no other purpose.

    Nothing here reads content: the class exists to answer "which object is this handle, where does it
    really live, and is it a file" *after* the create and *before* any byte is fetched.  Every method
    returns ``None`` (or a neutral value) rather than raising when a call is unavailable, because the
    caller's contract is fail closed -- an unanswerable question has to cost the read, not the run.
    """

    def __init__(self, kernel32) -> None:
        import ctypes  # noqa: PLC0415 -- stdlib, imported with the platform branch that needs it
        import ctypes.wintypes  # noqa: PLC0415

        self._ctypes = ctypes
        self._kernel32 = kernel32
        self.last_error = 0

        class _ByHandleFileInformation(ctypes.Structure):
            _fields_ = [(name, getattr(ctypes.wintypes, "DWORD")) for name in _WIN32_HANDLE_METADATA_FIELDS]

        self._info_type = _ByHandleFileInformation
        self._kernel32.CreateFileW.restype = ctypes.c_void_p
        self._kernel32.CreateFileW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
                                               ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD,
                                               ctypes.wintypes.DWORD, ctypes.c_void_p]
        self._kernel32.GetFinalPathNameByHandleW.restype = ctypes.wintypes.DWORD
        self._kernel32.GetFileInformationByHandle.restype = ctypes.wintypes.BOOL
        self._kernel32.GetFileType.restype = ctypes.wintypes.DWORD

    def open_handle(self, path: Path, *, directory: bool):
        handle = self._kernel32.CreateFileW(str(path), _WIN32_GENERIC_READ, _WIN32_SHARE_ALL, None,
                                            _WIN32_OPEN_EXISTING,
                                            _WIN32_BACKUP_SEMANTICS if directory else 0, None)
        value = getattr(handle, "value", handle)
        if not handle or value in (None, _WIN32_INVALID_HANDLE, -1):
            self.last_error = int(self._kernel32.GetLastError() or 0)
            return None
        self.last_error = 0
        return handle

    def close(self, handle) -> None:
        if handle:
            self._kernel32.CloseHandle(handle)

    def identity(self, handle) -> dict | None:
        info = self._info_type()
        if not self._kernel32.GetFileInformationByHandle(handle, self._ctypes.byref(info)):
            return None
        size = (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow)
        return {"size": size,
                "volume": int(info.dwVolumeSerialNumber),
                "identity": (int(info.dwVolumeSerialNumber), (int(info.nFileIndexHigh) << 32)
                             | int(info.nFileIndexLow)),
                "is_reparse": bool(int(info.dwFileAttributes) & _WIN32_FILE_ATTRIBUTE_REPARSE_POINT)}

    def final_path(self, handle) -> str:
        buffer = self._ctypes.create_unicode_buffer(16384)  # MAX_PATH is far too small for real installs
        length = self._kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            return ""
        return buffer.value

    def kind(self, handle) -> str:
        try:
            return _WIN32_FILE_KINDS.get(int(self._kernel32.GetFileType(handle) or 0), "unknown")
        except OSError:
            return "unknown"

    def attach(self, handle):
        """Wrap the already-verified handle in a binary stream, transferring the handle to the CRT fd.

        The fd is created with ``O_BINARY`` as well as ``O_RDONLY``, and that is not a formality:  a CRT
        descriptor left in the default mode on Windows performs text translation, which folds every
        ``CRLF`` into ``LF`` while the program is reading.  The bytes would still look like the log, but the
        count would not -- the recorded read would be smaller than the bytes measured on the handle, the
        tail would no longer be the last bytes of the object, and a digest taken this way would not match the
        same file read by any other route.  The gate that runs this file on Linux cannot see the difference,
        because ``os.O_BINARY`` is zero there and no translation exists, so the flag is asserted by name in
        the suite rather than left to the platform that needs it.

        On any failure this closes the handle itself, so the caller never double-closes an object whose
        ownership has already moved -- and the caller still refuses the read, because a stream that could
        not be built is not a reason to guess at content.
        """
        import msvcrt  # noqa: PLC0415 -- Windows only, reached only from the Windows branch

        value = int(getattr(handle, "value", handle))
        try:
            descriptor = msvcrt.open_osfhandle(value, _WIN32_READ_FLAGS)
        except OSError:
            self.close(handle)
            raise
        try:
            return io.open(descriptor, "rb", closefd=True)
        except OSError:
            msvcrt.close(descriptor)
            raise


def _win32_api():
    """Return the Windows metadata helper, or ``None`` when this host cannot provide one.

    Cached, and never substituted by a weaker path-based check: an unavailable ``kernel32`` means the
    anchored open cannot prove containment, and the caller turns that into a refusal.  ``ctypes`` is stdlib,
    so pinning nothing new -- the version identity of the interpreter remains what the manifest records.
    """
    global _WIN32_API, _WIN32_API_UNAVAILABLE
    if _WIN32_API is not None:
        return _WIN32_API
    if _WIN32_API_UNAVAILABLE or os.name != "nt":
        return None
    try:
        import ctypes  # noqa: PLC0415
        api = _Win32HandleMetadata(ctypes.windll.kernel32)
        for call in ("CreateFileW", "CloseHandle", "GetFinalPathNameByHandleW", "GetFileInformationByHandle",
                     "GetFileType"):
            getattr(api._kernel32, call)  # an AttributeError here is what "unavailable" means on odd hosts
    except Exception:
        _WIN32_API_UNAVAILABLE = True
        return None
    _WIN32_API = api
    return api


def _directory_identity_windows(path: Path) -> tuple[int, ...] | None:
    api = _win32_api()
    if api is None:
        return None
    handle = api.open_handle(path, directory=True)
    if handle is None:
        return None
    try:
        info = api.identity(handle)
    finally:
        api.close(handle)
    return tuple(info["identity"]) if info else None


LOG_TAIL_BYTES = 512 * 1024  # ceiling for any tail read: a caller may ask for less, never for more
MAX_TAIL_READ_BYTES = LOG_TAIL_BYTES + 1  # the most a single read may fetch: the ceiling plus one probe byte
# The states a log read may report, and nothing else.  A new internal refusal reason has to be expressed in
# this vocabulary rather than adding a seventh value to records a downstream consumer already parses, and a
# refusal that cannot be expressed in it degrades to "unreadable" -- which is "could not read", not "read
# successfully" and never a pass.
_READ_STATES = frozenset({"complete", "truncated", "empty", "absent", "unreadable", "skipped_unsafe_path"})
# The three states a forensic digest may report.  "absent" belongs to the read vocabulary but not to this
# one: an uninstaller that is not there is already reported by `exists`, and a digest field has to say
# either that a hash was taken, that it was refused as unsafe, or that it could not be read.
_HASH_STATES = frozenset({"hashed", "skipped_unsafe_path", "unreadable"})

# Reading a lifecycle log means deciding, *while the handle is held*, that the bytes came from something
# this tool is allowed to observe.  A pathname cannot carry that decision: between the check of a name and
# the open of a name the name can be re-pointed, and checking harder does not narrow the window -- only
# opening relative to a descriptor (POSIX) or binding the verdict to the opened handle (Windows) closes it.
# So the helpers below never re-open by name after validating it, and never hash or slice what they did not
# open.


class AnchorRefusal(Exception):
    """A read refused on policy before any byte was fetched, carrying the state to publish and why.

    This is deliberately not an ``OSError``: the object exists and the process could well read it, but the
    name no longer denotes something inside the boundary this tool may observe.  Folding the two together
    would hide the difference between "the machine refused" and "the path led out of the sandbox", and the
    second is the finding an operator needs to see.
    """

    def __init__(self, state: str, reason: str) -> None:
        super().__init__(reason)
        self.state, self.reason = state, reason


def _confinement_verdict(final_target: str, root_final_target: str, *, object_kind: str,
                         same_volume: bool, is_reparse: bool,
                         expected_target: str = "") -> tuple[str, str]:
    """Decide from *handle metadata alone* whether an opened object lies inside the permitted root.

    The Windows containment test lives here, as a pure function over the facts ``GetFinalPathNameByHandleW``,
    ``GetFileType``, ``FILE_ATTRIBUTE_REPARSE_POINT`` and ``BY_HANDLE_FILE_INFORMATION`` supply, so the rule
    is reviewable on any host and cannot drift between platforms.  A backslash separator is not a oversight:
    the strings compared are the device-namespace paths Windows reports for the handle, and on POSIX the
    anchored open below establishes the same property structurally -- by never following a component and
    never leaving the root's descriptor -- rather than by comparing text.

    A reparse point is refused on its own attributes, not on the answer ``resolve()`` gave earlier: a
    junction inside the root whose target is outside it resolves to something outside, and a junction whose
    target is a *different* directory inside the root resolves to something plausible.  Neither is the file
    the caller named, and neither is what this tool was allowed to read.
    """
    if object_kind != "disk":
        return "unreadable", (f"the opened object is a {object_kind}, not a regular disk file; nothing was read")
    if is_reparse:
        return "skipped_unsafe_path", ("the opened object is itself a reparse point, so its content lives behind "
                                       "another path; nothing was read")
    target = str(final_target or "").rstrip("\\/").lower()
    root = str(root_final_target or "").rstrip("\\/").lower()
    if not target or not root or not same_volume or not target.startswith(root + "\\"):
        return "skipped_unsafe_path", "resolves outside the permitted evidence root; not read"
    expected = str(expected_target or "").rstrip("\\/").lower()
    if expected and target != expected:
        # The bytes came from a file inside the root, but not from the file that was named: a directory
        # component between the two was a junction or a link, so the object the handle reached is somebody
        # else's file.  For an installer digest that is the difference between evidence and theatre.
        return "skipped_unsafe_path", ("the named path reached a different object, so a link was followed; "
                                       "nothing was read")
    return "within", ""


def _directory_identity(path: Path) -> tuple[int, ...] | None:
    """The identity of the *directory object* at `path`, for detecting that the root itself was swapped.

    A per-run identity is not a secret and not a credential: on POSIX it is the device and inode number of
    the directory, on Windows the volume serial with the file index.  It is recorded once, when the run
    creates or takes ownership of the root, and every anchored open compares the object it actually reached
    against it -- so a root that is deleted and re-created, or replaced by a link to somewhere else, stops
    the reads instead of silently redefining the boundary they are confined to.
    """
    if os.name == "nt":
        return _directory_identity_windows(path)
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
    except OSError:
        os.close(fd)
        return None
    os.close(fd)
    return (info.st_dev, info.st_ino)


def _read_open_error(observed: dict, exc: OSError, path: Path) -> dict:
    """Turn an environment error from the open or the read into the bounded record it justifies.

    Classification, not transcription: an exception's own text can quote a path that carries a credential,
    and a traceback is unbounded, so the name of the class and its codes are what get published.  A
    directory is reported as "not a regular file" whatever the platform chose to raise for it, because the
    fact -- this object is not a file -- is platform-free and an operator comparing two runs should not see
    two different reasons for one cause.
    """
    if isinstance(exc, IsADirectoryError) or os.path.isdir(path):
        observed["reason"] = "not a regular file"
        return observed
    observed["reason"] = bound(f"{type(exc).__name__}(errno={exc.errno}, "
                               f"winerror={getattr(exc, 'winerror', None)})", 160)
    return observed


def _open_binary(path: Path, permitted_root: Path | None,
                 root_identity: tuple[int, ...] | None = None) -> tuple[object, dict]:
    """Open one file for reading so the object cannot change underneath the reader.

    With no permitted root there is nothing to anchor to and nothing is claimed: the ordinary
    :meth:`pathlib.Path.open` is returned and ``meta`` says the containment was not established.  With a
    permitted root the open is anchored to it and the returned stream is the *only* handle the caller gets,
    so a validated pathname is never re-opened by name afterwards.

    Raises :class:`AnchorRefusal` for a policy refusal (before any byte is read), ``FileNotFoundError`` for
    a name that is simply not there, and any other ``OSError`` for an environment failure; the caller turns
    those into published states.  Nothing here retries, substitutes, or degrades a refusal into a success.
    """
    if permitted_root is None:
        return (path.open("rb"),
                {"confinement": "unanchored: no permitted root supplied, so containment is not claimed"})
    if os.name == "nt":
        return _open_binary_windows(path, Path(permitted_root), root_identity)
    return _open_binary_posix(path, Path(permitted_root), root_identity)


def _relative_parts(name: str, root_name: str) -> list[str]:
    """Lexically split `name` into components relative to `root_name`, resolving nothing.

    Deliberately ``normpath`` and not ``resolve``: resolving follows links, and a walk that has already
    followed a link has answered a different question from the one being asked (which object would the open
    reach?).  A component that escapes upwards is refused here, before any open is attempted.
    """
    relative = os.path.relpath(name, root_name)
    parts = [part for part in relative.split(os.sep) if part not in ("", ".")]
    if not parts or ".." in parts:
        raise AnchorRefusal("skipped_unsafe_path", "lies outside the permitted evidence root; not opened")
    return parts


def _open_binary_posix(path: Path, root: Path,
                       root_identity: tuple[int, ...] | None) -> tuple[object, dict]:
    """Open relative to a descriptor for the root, following no component, and prove what was opened.

    ``O_NOFOLLOW`` on every component is what closes the check-then-use window: if the name is swapped for a
    link between any earlier look and this open, the open itself fails with ``ELOOP`` instead of quietly
    handing back the link target's bytes, and there is no later moment at which the path could be
    re-pointed again because the object is already open.  ``O_NONBLOCK`` on the final component keeps a FIFO
    that somehow got past the flags from hanging the reader, and ``S_ISREG`` on the *opened* descriptor --
    not on a second ``stat`` of the name -- is what says the bytes are a file's.
    """
    name = os.path.abspath(os.path.normpath(str(path)))
    root_name = os.path.abspath(os.path.normpath(str(root)))
    parts = _relative_parts(name, root_name)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_fd = os.open(root_name, directory_flags)
    except OSError as exc:
        raise AnchorRefusal("unreadable", bound(f"the permitted evidence root could not be opened for anchoring "
                                                f"({type(exc).__name__}, errno={exc.errno}); nothing was read",
                                                200)) from exc
    meta: dict = {}
    try:
        anchor = os.fstat(parent_fd)
        meta["root_identity"] = [anchor.st_dev, anchor.st_ino]
        if root_identity is not None and [anchor.st_dev, anchor.st_ino] != list(root_identity):
            raise AnchorRefusal("skipped_unsafe_path", ("the directory behind the permitted root name is not the "
                                                       "one this run created; nothing was read"))
        for part in parts[:-1]:
            try:
                child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            except OSError as exc:
                # Linux answers `ENOTDIR`, not `ELOOP`, when `O_DIRECTORY | O_NOFOLLOW` meets a symbolic link,
                # so the refusal is decided by what the component is rather than by which errno arrived: a
                # link is an unsafe path (the guarantee is that links are not followed), while a component
                # that is simply not a directory stays the ordinary unreadable case.  Both read nothing.
                if exc.errno in (getattr(errno, "ELOOP", -1), getattr(errno, "ENOTDIR", -1)):
                    try:
                        is_link = stat.S_ISLNK(os.lstat(part, dir_fd=parent_fd).st_mode)
                    except OSError:
                        is_link = False
                    if is_link:
                        raise AnchorRefusal(
                            "skipped_unsafe_path",
                            (f"the path component {part!r} is a symbolic link, and the walk to a log follows no "
                             "link; nothing was read")) from exc
                raise
            os.close(parent_fd)
            parent_fd = child_fd
        try:
            file_fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                              | getattr(os, "O_NONBLOCK", 0), dir_fd=parent_fd)
        except FileNotFoundError as exc:
            raise AnchorRefusal("absent", "no such file when the read was attempted") from exc
        except OSError as exc:
            if exc.errno == getattr(errno, "ELOOP", -1):
                raise AnchorRefusal("skipped_unsafe_path", ("the name is a symbolic link, or became one before the "
                                                            "open; it was not followed and nothing was read")) from exc
            raise
        opened = os.fstat(file_fd)
        meta["object_identity"] = [opened.st_dev, opened.st_ino]
        meta["size"] = opened.st_size
        meta["is_regular"] = stat.S_ISREG(opened.st_mode)
        meta["confinement"] = ("anchored: opened relative to the root descriptor with O_NOFOLLOW on every "
                              "component; the opened object, not the name, was validated")
        if not meta["is_regular"]:
            os.close(file_fd)
            raise AnchorRefusal("unreadable", "not a regular file")
        try:
            return io.open(file_fd, "rb", closefd=True), meta  # the fd is the object; no second lookup by name
        except OSError:
            os.close(file_fd)
            raise
    except FileNotFoundError as exc:  # an intermediate directory disappeared mid-walk
        raise AnchorRefusal("absent", "no such file when the read was attempted") from exc
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass


def _open_binary_windows(path: Path, root: Path,
                         root_identity: tuple[int, ...] | None) -> tuple[object, dict]:
    """Bind the containment decision to the opened handle, which is the strongest practical Windows anchor.

    Win32 has no descriptor-relative open, and ``O_NOFOLLOW`` in the CRT is not a guard against junctions or
    symlinks at all, so the guarantee is built the other way round: the object is opened once, then
    ``GetFinalPathNameByHandleW`` and ``GetFileInformationByHandle`* on that handle* say which object the
    bytes will come from, and the answer is compared against the root's own final path and volume identity.
    A reparse point is caught by its attribute bit even when its target is inside the root, because the file
    the caller named and the file the handle reached are then different objects.

    Anything that cannot be established fails closed: if the metadata calls are unavailable, or they fail,
    the handle is closed and nothing is read.  The residual limit is stated rather than papered over -- the
    create happens before the metadata, so an object type whose open blocks (a named pipe) would block
    before it could be classified; those cannot be created *inside* an ordinary directory, so a file planted
    in the work root cannot reach that path, but a hostile mount point could, and on such a host this helper
    narrows the race rather than eliminating it.
    """
    api = _win32_api()
    if api is None:
        raise AnchorRefusal("skipped_unsafe_path", ("Windows handle metadata is unavailable on this host, so "
                                                     "containment cannot be proven; the file was not read"))
    name = os.path.abspath(os.path.normpath(str(path)))
    root_name = os.path.abspath(os.path.normpath(str(root)))
    parts = _relative_parts(name, root_name)
    root_opened = api.open_handle(Path(root_name), directory=True)
    if root_opened is None:
        raise AnchorRefusal("unreadable", bound(f"the permitted evidence root could not be opened for anchoring "
                                                f"(CreateFileW error {api.last_error}); nothing was read", 200))
    try:
        root_info = api.identity(root_opened)
        if root_info is None:
            raise AnchorRefusal("skipped_unsafe_path", "the permitted root's own identity is unreadable; nothing "
                                                        "was read")
        if root_identity is not None and tuple(root_info["identity"]) != tuple(root_identity):
            raise AnchorRefusal("skipped_unsafe_path", ("the directory behind the permitted root name is not the "
                                                        "one this run created; nothing was read"))
        root_final = api.final_path(root_opened)
        expected = "\\\\".join([root_final, *parts]) if root_final else ""
        opened = api.open_handle(Path(name), directory=False)
        if opened is None:
            error = api.last_error
            if error in _WIN32_NOT_FOUND:
                raise FileNotFoundError(error, "No such file or directory", name)
            if error in _WIN32_LINK_OR_REPARSE:
                raise AnchorRefusal("skipped_unsafe_path", ("the name could not be opened without following a "
                                                            "link; nothing was read"))
            raise AnchorRefusal("unreadable", bound(f"CreateFileW error {error} refused the open; nothing was "
                                                     f"read", 200))
        try:
            info = api.identity(opened)
            if info is None:
                raise AnchorRefusal("skipped_unsafe_path", ("the opened object's metadata could not be read, so "
                                                             "containment cannot be proven; nothing was read"))
            state, reason = _confinement_verdict(api.final_path(opened), root_final,
                                                 object_kind=api.kind(opened),
                                                 same_volume=info["volume"] == root_info["volume"],
                                                 is_reparse=info["is_reparse"], expected_target=expected)
            if state != "within":
                raise AnchorRefusal(state, reason)
        except Exception:
            api.close(opened)  # never hand back a handle whose verdict was not "within"
            raise
        # From here the handle belongs to the stream: `attach` closes it itself if it cannot take it over,
        # so the failure paths below must not close it a second time.
        meta = {"confinement": ("anchored: opened once, then validated through GetFinalPathNameByHandleW and "
                                "GetFileInformationByHandle on that handle"),
                "size": info["size"], "is_regular": True, "object_identity": list(info["identity"])}
        return api.attach(opened), meta
    finally:
        api.close(root_opened)


def _bounded_tail(path: Path, lines: int = 40, *, byte_limit: int = LOG_TAIL_BYTES,
                  permitted_root: Path | None = None, root_identity: tuple[int, ...] | None = None) -> dict:
    """Read the last `byte_limit` bytes of one log through an anchored handle, and report what was proven.

    Three separate things could be confused here, so each is named:

    * **how much was read** -- ``bytes_read``, never above ``MAX_TAIL_READ_BYTES``, because the window is
      sought from the end of the *opened object* instead of the file being loaded and sliced;
    * **how much may be asked for** -- ``byte_limit``, which a caller may lower but never raise past
      ``LOG_TAIL_BYTES``, so the ceiling is a property of the reader rather than of one default value;
    * **how much is published** -- each caller clips with ``bound()``, which is presentation and was never a
      statement about I/O.

    Because only a suffix is inspected, the result says which state it saw: ``complete``, ``truncated``,
    ``empty``, ``absent``, ``unreadable`` or ``skipped_unsafe_path``.  A caller must not describe
    ``truncated`` as "the log", which is why the reason travels with the text.  Nothing here raises for an
    environment condition: a log that vanishes, turns out to be a directory, or refuses to open is recorded,
    the original lifecycle finding survives, and the refused read stays at zero bytes.
    """
    observed: dict = {"state": "unreadable", "bytes_read": 0, "size_bytes": None, "lines_returned": 0,
                      "reason": "", "dropped_partial_first_line": False, "tail": ""}
    if byte_limit <= 0:
        raise ValueError("byte_limit must be a positive bound")  # a programming error, never an environment event
    if byte_limit > LOG_TAIL_BYTES:
        # Not a warning and not a quiet clamp: a caller that could raise this ceiling could also raise it to
        # "the whole hundred-megabyte log", which is the cost this bound exists to prevent, and a clamped
        # request would report a smaller read than the caller believes it asked for.
        raise ValueError(f"byte_limit cannot exceed the global tail bound of {LOG_TAIL_BYTES} bytes")
    try:
        stream, meta = _open_binary(path, permitted_root, root_identity)
    except AnchorRefusal as refusal:
        observed["state"] = refusal.state if refusal.state in _READ_STATES else "unreadable"
        observed["reason"] = bound(refusal.reason, 200)
        return observed
    except FileNotFoundError:
        observed["state"] = "absent"
        observed["reason"] = "no such file when the read was attempted"
        return observed
    except OSError as exc:
        return _read_open_error(observed, exc, path)
    try:
        with stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            observed["size_bytes"] = size
            observed["confinement"] = meta.get("confinement", "")
            if size == 0:
                observed["state"] = "empty"
                return observed
            start = max(0, size - byte_limit)
            # One byte *before* the window is the only evidence that separates a first line which happens to
            # start where the window starts from one that starts mid-line, and reading it from the front
            # rather than asking for a byte past the end is what keeps the ceiling intact: the request stays
            # at `byte_limit + 1` bytes total, and growth is detected from the handle's own end (below)
            # instead of by over-reading the tail, which a single spare byte could not detect anyway.
            probe = 1 if start > 0 else 0
            stream.seek(start - probe)
            data = stream.read(byte_limit + 1)
            try:
                after = stream.seek(0, os.SEEK_END) or stream.tell()
            except OSError:
                after = None  # growth unknown is a weaker statement, not a wrong one
    except OSError as exc:
        return _read_open_error(observed, exc, path)
    observed["bytes_read"] = len(data)
    if not data:
        observed["state"] = "unreadable"
        observed["reason"] = "the file shrank below the requested window while it was being read"
        return observed
    boundary = data[:probe]
    content = data[probe:]  # the probe byte is a fact about the window's edge, never part of the window
    grew = after is not None and after > size
    truncated = start > 0 or len(content) > byte_limit
    if truncated:
        content = content[-byte_limit:]  # keep the recent end; the older prefix is what the bound excludes
    window = content.decode("utf-8", errors="replace").splitlines()
    if start > 0 and boundary != b"\n":
        # Recorded whether or not the fragment is dropped: an operator reading a one-line window off a
        # huge log is entitled to know that its first character is not the first character of a line.
        observed["first_line_is_fragment"] = True
    if start > 0 and len(window) > 1 and boundary != b"\n":
        # The fragment is dropped only when the byte before the window proves it is a fragment.  A window
        # that begins exactly on a line boundary keeps its first line: dropping it would cost an operator a
        # line of real evidence, and a start offset alone has never been evidence about the line.
        window = window[1:]
        observed["dropped_partial_first_line"] = True
    tail = window[-max(lines, 1):]
    observed["lines_returned"] = len(tail)
    observed["state"] = "truncated" if truncated else "complete"
    if grew:
        observed["grew_during_read"] = True
    if truncated:
        observed["reason"] = (f"only the last {len(content)} of {size} bytes were read; "
                              "older content was not inspected")
    if grew:
        observed["reason"] = (f"{observed['reason']}; " if observed["reason"] else "") + (
            "the log grew past the end that was measured while it was being read; the window covers the "
            "measured size")
    observed["tail"] = "\n".join(tail)
    return observed


def _tail(path: Path, lines: int = 40, *, byte_limit: int = LOG_TAIL_BYTES,
          permitted_root: Path | None = None, root_identity: tuple[int, ...] | None = None) -> str:
    """The text form of :func:`_bounded_tail`, for callers that publish only the string.

    Absent or unreadable still yields the empty string, as it did when this helper read the whole
    file, and a clipped read announces itself inside the returned text so a suffix can never be
    presented as the log.
    """
    observed = _bounded_tail(path, lines, byte_limit=byte_limit, permitted_root=permitted_root,
                             root_identity=root_identity)
    tail = observed["tail"]
    if observed["state"] == "truncated" and tail:
        return f"[{observed['reason']}] {tail}"
    return tail


def _is_within(child: Path, parent: Path) -> bool:
    """A cheap look at the *name*, used only to refuse obvious cases early -- never to authorize a read.

    ``resolve`` follows links, so this can be fooled in both directions by a path that changes underneath
    it.  That is harmless precisely because it is not the security check: every read and digest goes through
    :func:`_open_binary`, which decides on the object it opened.  A False answer here means "do not even
    attempt the open"; a True answer proves nothing.
    """
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
    # install_dir.parent is the work root by construction, so the same boundary applies here.
    evidence["diagnostics"]["uninstall_log"] = redact(_tail(log, permitted_root=install_dir.parent), [])
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


def _redact_tree(value: object, secret_values: list[str]) -> object:
    """Remove signing credential values from every string the record publishes.

    Diagnostics now include what PowerShell wrote to stderr.  A tool that echoes its own
    environment into an error message must not turn a release log into a credential leak, so
    redaction is applied to the whole document rather than to one field.
    """
    if isinstance(value, str):
        return redact(value, secret_values)
    if isinstance(value, dict):
        return {key: _redact_tree(item, secret_values) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_tree(item, secret_values) for item in value]
    return value


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
    # Ask the host whether it can answer the question at all, and record what it said.  This is
    # what makes a published UNKNOWN attributable without downloading any artifact.
    probe = run_powershell(SIGNING_PROBE_SCRIPT, release_root, runner, timeout)
    # A probe is a diagnostic, not an authority: only a host that positively answers "the cmdlet
    # is missing" may excuse the run from asking about each file.  A probe that itself failed is
    # recorded and the queries still run, because each query reports its own cause.
    reported_command = str(probe.get("cmdlet") or "unknown") if "error" not in probe else "unknown"
    # Three separate observations, published under names that say which is which: did the module
    # import, is the cmdlet resolvable, and did the probe itself answer.  `cmdlet_available` is the
    # only one of the three that may excuse a run from asking about each file; an import complaint
    # never suppresses a query the host can actually answer.
    import_state = str(probe.get("security_module_import") or "unreported")
    import_error = bound(str(probe.get("security_module_import_error") or "").strip(), 300)
    harness = {"query_command": reported_command,
               "cmdlet_available": {"available": True, "missing": False}.get(reported_command),
               "powershell_version": str(probe.get("ps_version") or ""),
               "signature_command_module": str(probe.get("module") or ""),
               "security_module_import": import_state,
               # "usable" means the probe answered the question it was asked, which is not the same
               # as exiting 0: a payload that parsed but named no command told us nothing either way.
               "probe_usable": "error" not in probe and bool(probe.get("cmdlet")),
               "probe_exit_code": probe.get("powershell_exit_code", 0)}
    if import_error:
        harness["security_module_import_error"] = import_error
    for key in ("error", "powershell_stderr"):
        if probe.get(key):
            harness[f"probe_{key}"] = bound(str(probe[key]), 300)
    if harness["cmdlet_available"] is False:
        if import_state == "failed":
            cause = ("explicit Import-Module of Microsoft.PowerShell.Security failed"
                     + (f": {import_error}" if import_error else " and reported no message"))
        elif import_state == "succeeded":
            cause = ("Microsoft.PowerShell.Security imported successfully, and Get-Command still did "
                     "not resolve Get-AuthenticodeSignature in this host")
        else:
            cause = "the capability probe did not report whether the module import succeeded"
        unavailable_reason = (f"Get-AuthenticodeSignature is not available in this PowerShell host "
                              f"(PowerShell {harness['powershell_version'] or 'unknown'}; {cause})")
    else:
        unavailable_reason = ""
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
            if unavailable_reason:
                # The query itself was never possible: that is an unknown, recorded with its
                # cause, and never silently relabelled as "unsigned".
                record.update({"status": "UNKNOWN", "raw_status": "", "raw_status_recognized": False,
                               "status_message": bound(unavailable_reason, 300)})
            else:
                payload = run_powershell(SIGNATURE_QUERY_SCRIPT, path, runner, timeout,
                                         required_field="Status")
                raw_status = str(payload.get("Status") or "").strip()
                query_error = str(payload.get("QueryError") or "").strip()
                stderr_note = str(payload.get("powershell_stderr") or "").strip()
                # The script's own error record is the most specific cause available, so it is
                # preferred over the harness's generic "no Status was reported" wording; the
                # harness text remains the fallback when the payload itself says nothing.
                detail = query_error or stderr_note or str(payload.get("error") or "").strip()
                status, recognized = normalize_authenticode_status(raw_status)
                record["raw_status"] = bound(raw_status, 80)
                record["raw_status_recognized"] = recognized
                record["status"] = status
                # An empty answer is only ever an UNKNOWN, and it must say what the host reported.
                message = str(payload.get("StatusMessage") or "").strip()
                if not message and status == "FAIL":
                    message = "Windows reported a signature problem and gave no explanation"
                if not message and status == "UNKNOWN":
                    message = ("the signature query returned no status; "
                               + (detail or "the host reported nothing further"))
                elif status == "UNKNOWN" and detail and detail not in message:
                    message = f"{message}; {detail}"
                record["status_message"] = bound(message, 300)
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
                              "raw_status": "", "raw_status_recognized": True,
                              "status_message": "container archive; Authenticode applies to the executables it carries"})

    status = aggregate_signing_status(files)
    if status not in SIGNING_STATUS_VOCABULARY:
        raise ValueError(f"signature tool produced a status outside the vocabulary: {status!r}")
    outside = sorted({str(item.get("status")) for item in files} - FILE_STATUS_VOCABULARY)
    if outside:
        raise ValueError("signature tool produced a per-file status outside the vocabulary: "
                         + ", ".join(outside))
    document = {
        "schema": SIGNING_STATUS_SCHEMA,
        "method": "Windows Get-AuthenticodeSignature",
        "release_metadata_sha256": sha256_file(release_metadata_path),
        "source_sha": str(metadata.get("git_sha") or ""),
        "harness": harness,
        "status": status,
        "policy": SIGNING_POLICY,
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
    document = _redact_tree(document, [os.environ.get(key, "") for key in credential_env_present])
    # Publish nothing the shared contract would not accept: the generator is held to the same
    # rules the acceptance report will apply, so a malformed record fails here, at the source.
    return validate_signing_document(document)


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
    harness = report.get("harness")
    if isinstance(harness, dict) and harness:
        # This text is appended to the job summary, the one channel that is both uncapped and
        # reachable when the artifact endpoints are not, so the query host belongs in it.
        version = harness.get("powershell_version") or "unreported"
        command = harness.get("query_command") or "unreported"
        module_import = str(harness.get("security_module_import") or "unreported").replace("_", " ")
        import_error = (f" ({harness['security_module_import_error']})"
                        if harness.get("security_module_import_error") else "")
        available = harness.get("cmdlet_available")
        availability = {True: "cmdlet available", False: "cmdlet unavailable"}.get(available, "cmdlet unreported")
        probe_exit = harness.get("probe_exit_code", "unreported")
        probe_error = f"; probe error: {harness['probe_error']}" if harness.get("probe_error") else ""
        lines += ["", f"Query host: PowerShell {version}; {availability} ({command}); "
                      f"Microsoft.PowerShell.Security import {module_import}{import_error}; "
                      f"probe usable: {harness.get('probe_usable', 'unreported')}; "
                      f"probe exit code {probe_exit}{probe_error}"]
        lines += ["", "Import outcome and command availability are separate observations: an import "
                      "failure does not suppress a query the host can answer, and a missing command is "
                      "not an Authenticode finding about the file."]
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
            # Even "this platform cannot answer" is published as a contract-valid record, so a
            # reader never has to guess whether a missing file means a missing check.
            report = {"schema": SIGNING_STATUS_SCHEMA, "method": "Windows Get-AuthenticodeSignature",
                      "status": "NOT_RUN", "policy": SIGNING_POLICY, "files": [],
                      "examined_count": 0, "archive_count": 0,
                      "signing_configured_in_build": False, "credentials_available": False,
                      "prerequisite": "a Windows host; none of the release artifacts were queried here",
                      "reason": "Authenticode verification requires a Windows host"}
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
        try:
            # Publish nothing the report would refuse later; the writer is held to its own contract.
            validate_signing_document(report)
        except ValueError as exc:
            print(f"ERROR: signing record violates {SIGNING_STATUS_SCHEMA}: {exc}", file=sys.stderr)
            return 1

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(render_markdown(report, f"Windows {args.command} evidence"), encoding="utf-8")
    # The console line is what a reader of the job log sees without downloading an artifact, so it
    # carries the reason for any state that is not a clean pass.
    print(json.dumps({"command": args.command, "status": report.get("status"),
                      "harness": report.get("harness") or {},
                      "files": [{"filename": item.get("filename"), "status": item.get("status"),
                                 "raw_status": item.get("raw_status", ""),
                                 "reason": bound(str(item.get("status_message") or ""), 200)}
                                for item in report.get("files", [])]}, sort_keys=True))
    if args.command == "signing":
        return 0
    return 0 if str(report.get("status")) in {"PASS", "NOT_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
