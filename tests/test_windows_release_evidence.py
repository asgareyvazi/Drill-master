"""Unit tests for the Windows release evidence steps (M42.2).

The lifecycle and signing steps can only *execute* on a Windows runner, but every
decision they make -- refusing to run an unbound binary, treating a nonzero exit as
failure, proving user-data retention, and never overstating signature state -- is
plain logic.  A scripted fake host exercises that logic here, so the Windows job is
the first place a mechanical failure can appear, not the first place a mistake in
the decision rules can appear.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _release_metadata_module():
    spec = importlib.util.spec_from_file_location(
        "drillmaster_release_metadata_for_evidence", ROOT / "packaging" / "release_metadata.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _evidence_module():
    spec = importlib.util.spec_from_file_location(
        "drillmaster_windows_release_evidence", ROOT / "packaging" / "windows_release_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeHost:
    """A scripted stand-in for the installer, uninstaller and PowerShell queries."""

    def __init__(self, *, install_exit_code: int = 0, uninstall_exit_code: int = 0,
                 product_version: str = "1.0.0.0", smoke_exit_code: int = 0,
                 smoke_output: str = "PACKAGE_SMOKE_OK", uninstall_removes: bool = True,
                 smoke_marker_in: str = "both",
                 leak_value: str = "", write_into_install_dir: bool = False,
                 signature_status: str = "NotSigned", signer_subject: str = "",
                 signature_message: str = "No signature is present.", signature_error: str = "",
                 signature_stderr: str = "", signature_cmdlet: str = "available",
                 keep_sentinel: bool = True, install_writes_exe: bool = True,
                 run_stdout: str = "", powershell_version_output: str | None = None,
                 run_returncode: int | None = None, raise_on_call: int | None = None,
                 remove_uninstaller_during_smoke: bool = False,
                 unlaunchable_uninstall_attempts: int = 0, unlink_uninstaller_on_refusal: bool = False,
                 take_away_install_dir_before_launch: bool = False, uninstall_refusal_error: Exception | None = None,
                 uninstall_log_text: str = "", empty_install_dir_on_refusal: bool = False,
                 uninstaller_lock_clears_after: float | None = None,
                 module_import_result: str | None = "succeeded", module_import_error: str = "",
                 probe_omits_cmdlet: bool = False):
        self.install_exit_code = install_exit_code
        self.uninstall_exit_code = uninstall_exit_code
        self.product_version = product_version
        self.smoke_exit_code = smoke_exit_code
        self.smoke_output = smoke_output
        self.smoke_marker_in = smoke_marker_in
        self.uninstall_removes = uninstall_removes
        self.leak_value = leak_value
        self.write_into_install_dir = write_into_install_dir
        self.signature_status = signature_status
        self.signature_message = signature_message
        self.signature_error = signature_error
        self.signature_stderr = signature_stderr
        self.signature_cmdlet = signature_cmdlet
        self.signer_subject = signer_subject
        self.keep_sentinel = keep_sentinel
        self.install_writes_exe = install_writes_exe
        self.run_stdout = run_stdout
        self.powershell_version_output = powershell_version_output
        self.run_returncode = run_returncode
        self.raise_on_call = raise_on_call
        self.remove_uninstaller_during_smoke = remove_uninstaller_during_smoke
        self.module_import_result = module_import_result
        self.module_import_error = module_import_error
        self.probe_omits_cmdlet = probe_omits_cmdlet
        self.unlaunchable_uninstall_attempts = unlaunchable_uninstall_attempts
        self.unlink_uninstaller_on_refusal = unlink_uninstaller_on_refusal
        self.take_away_install_dir_before_launch = take_away_install_dir_before_launch
        self.empty_install_dir_on_refusal = empty_install_dir_on_refusal
        self.uninstaller_lock_clears_after = uninstaller_lock_clears_after
        self.first_refusal_monotonic: float | None = None
        self.uninstall_refusal_error = uninstall_refusal_error
        self.uninstall_log_text = uninstall_log_text
        self.calls: list[list[str]] = []
        self.envs: list[dict | None] = []

    def __call__(self, argv, environment, cwd, timeout):
        self.calls.append(list(argv))
        if self.raise_on_call is not None and len(self.calls) == self.raise_on_call:
            raise RuntimeError("harness interrupted (simulated runner crash)")
        self.envs.append(dict(environment) if environment else None)
        program = Path(argv[0]).name.lower()
        if program == "powershell.exe":
            script = argv[-1]
            target = str((environment or {})["DRILLMASTER_TARGET_PATH"])
            assert target, "the queried path must be passed out of band, never interpolated"
            if "Get-Command Get-AuthenticodeSignature" in script:
                # The capability probe, answered before any file is queried.  The import result and
                # the command lookup are reported from separate knobs on purpose: a host that says
                # one must not be allowed to imply the other, which is the confusion this fixture
                # used to encode.
                payload = {"ps_version": "5.1.20348.2402", "cmdlet": self.signature_cmdlet,
                           "module": "Microsoft.PowerShell.Security"}
                # `None` omits the field: a host that says nothing about the import must be handled
                # as silence, which is a different case from a host that reports it failed.
                if self.module_import_result is not None:
                    payload["security_module_import"] = self.module_import_result
                if self.probe_omits_cmdlet:
                    payload.pop("cmdlet", None)
                if self.module_import_error:
                    payload["security_module_import_error"] = self.module_import_error
                if self.signature_cmdlet == "probe-fails":
                    return SimpleNamespace(returncode=1, stdout="", stderr="probe unsupported")
            elif "Get-AuthenticodeSignature" in script:
                if self.signature_error:
                    # A statement-level failure: the script still prints a payload and exits 0.
                    payload = {"Status": "", "StatusMessage": "", "SignerSubject": None,
                               "QueryError": self.signature_error}
                else:
                    payload = {"Status": self.signature_status, "StatusMessage": self.signature_message,
                               "SignerSubject": self.signer_subject or None}
                if self.signature_stderr:
                    return SimpleNamespace(returncode=0, stdout=json.dumps(payload),
                                           stderr=self.signature_stderr)
            elif self.powershell_version_output is not None:
                return SimpleNamespace(returncode=0, stdout=self.powershell_version_output, stderr="")
            else:
                payload = {"FileVersion": self.product_version, "ProductVersion": self.product_version}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        if program.endswith("setup.exe"):
            install_dir = _arg_value(argv, "/DIR=")
            install_dir.mkdir(parents=True, exist_ok=True)
            if self.install_writes_exe:
                (install_dir / "DrillMaster.exe").write_bytes(b"installed executable")
                (install_dir / "unins000.exe").write_bytes(b"uninstaller")
            _arg_value(argv, "/LOG=").write_text("Setup process started.\n", encoding="utf-8")
            return SimpleNamespace(returncode=self.install_exit_code, stdout="", stderr="")
        if self.remove_uninstaller_during_smoke and program == "drillmaster.exe":
            # Something outside the installer's control removed the uninstaller while the
            # application ran; the lifecycle must describe that, not lose it in a FileNotFoundError.
            (Path(argv[0]).parent / "unins000.exe").unlink(missing_ok=True)
        if program == "unins000.exe":
            if self.uninstall_log_text:
                # A log Inno Setup wrote during an earlier pass: the only trace that survives an
                # uninstaller that deletes itself, and the fact that separates "already uninstalled"
                # from "never present".
                _arg_value(argv, "/LOG=").write_text(self.uninstall_log_text, encoding="utf-8")
            if self.take_away_install_dir_before_launch:
                shutil.rmtree(Path(argv[0]).parent, ignore_errors=True)
                raise FileNotFoundError(2, "The system cannot find the file specified")
            if self.empty_install_dir_on_refusal:
                # What a completed uninstall looks like when it then deletes itself: the directory
                # and its own log survive, every application file does not.
                for path in sorted(Path(argv[0]).parent.rglob("*")):
                    if path.is_file():
                        path.unlink()
                raise FileNotFoundError(2, "The system cannot find the file specified")
            if self.uninstall_refusal_error is not None:
                raise self.uninstall_refusal_error
            if self.uninstaller_lock_clears_after is not None:
                # A real lock or scan clears in seconds; the settle is what makes the difference
                # between "busy" and "gone".  Timing is measured, not scripted, so a lifecycle that
                # re-lists instantly cannot pass this.
                now = time.monotonic()
                if self.first_refusal_monotonic is None:
                    self.first_refusal_monotonic = now
                    raise FileNotFoundError(2, "The process cannot access the file because it is being used")
                if now - self.first_refusal_monotonic < self.uninstaller_lock_clears_after:
                    raise FileNotFoundError(2, "The process cannot access the file because it is being used")
                # past the wait: the lock released, so the uninstall runs normally and the step passes
            if self.unlaunchable_uninstall_attempts > 0:
                # The file is listed and the OS will not start it: what an uninstaller under
                # antivirus quarantine looks like from userspace.
                self.unlaunchable_uninstall_attempts -= 1
                if self.unlink_uninstaller_on_refusal:
                    Path(argv[0]).unlink(missing_ok=True)
                raise FileNotFoundError(2, "The system cannot find the file specified")
            install_dir = Path(argv[0]).parent
            if self.uninstall_removes:
                for path in sorted(install_dir.rglob("*")):
                    if path.is_file():
                        path.unlink()
                if not self.keep_sentinel:
                    sentinel = install_dir.parent / "userdata" / "sentinel-preserve.txt"
                    if sentinel.is_file():
                        sentinel.unlink()
            _arg_value(argv, "/LOG=").write_text("Uninstall process started.\n", encoding="utf-8")
            return SimpleNamespace(returncode=self.uninstall_exit_code, stdout="", stderr="")
        if program == "drillmaster.exe":
            if self.run_returncode == 124:
                return SimpleNamespace(returncode=124, stdout="", stderr="")
            log_dir = Path((environment or {})["DRILLMASTER_LOG_DIR"])
            log_dir.mkdir(parents=True, exist_ok=True)
            log_lines = ["INFO application smoke complete"]
            if self.smoke_marker_in in {"both", "log"}:
                log_lines.insert(0, "INFO PACKAGE_SMOKE_OK schema=7 modules=17")
            (log_dir / "drillmaster.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
            if self.smoke_marker_in not in {"both", "stdout"}:
                # A windowed build has no console at all: nothing reaches stdout.
                self.smoke_output = "application started"
            if self.write_into_install_dir:
                # A frozen application writing next to itself is the regression guarded here.
                (Path(argv[0]).parent / "drillmaster.db").write_bytes(b"leaked into the install tree")
            output = self.smoke_output
            if self.run_stdout:
                output += "\n" + self.run_stdout
            if self.leak_value:
                output += f"\ncould not authenticate with {self.leak_value}\n"
            return SimpleNamespace(returncode=self.smoke_exit_code, stdout=output, stderr="")
        raise AssertionError(f"unexpected command: {argv}")


def _arg_value(argv, prefix: str) -> Path:
    for item in argv:
        if item.startswith(prefix):
            return Path(item[len(prefix):])
    raise AssertionError(f"{prefix} missing from {argv}")


def _step(report, name):
    return next(step for step in report["steps"] if step["name"] == name)


def _write_portable_zip(root: Path, *, exe_bytes: bytes = b"frozen executable",
                        member: str = "DrillMaster-1.0.0/DrillMaster.exe") -> tuple[Path, str]:
    """A real portable archive with the bundle executable inside, as the build produces."""
    import io
    import zipfile

    archive = root / "DrillMaster-1.0.0-windows-x64.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        if member:
            bundle.writestr(member, exe_bytes)
        else:
            bundle.writestr("DrillMaster-1.0.0/README.txt", io.BytesIO(b"no executable inside").read())
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def _release(root: Path, *, exe_bytes: bytes = b"installer-bytes", with_zip: bool = True) -> tuple[Path, Path, str]:
    installer = root / "DrillMaster-1.0.0-Setup.exe"
    installer.parent.mkdir(parents=True, exist_ok=True)
    installer.write_bytes(exe_bytes)
    digest = hashlib.sha256(exe_bytes).hexdigest()
    metadata = root / "release-metadata.json"
    entries = [{"filename": installer.name, "sha256": digest, "size_bytes": len(exe_bytes)}]
    if with_zip:
        archive, archive_digest = _write_portable_zip(root)
        entries.append({"filename": archive.name, "sha256": archive_digest, "size_bytes": archive.stat().st_size})
    metadata.write_text(json.dumps({
        "schema": "drillmaster-release-artifacts/v2",
        "version": "1.0.0",
        "git_sha": "a" * 40,
        "platform": "windows-x64",
        "python": "3.12.10",
        "build_tools": {"pip": "25.3", "pyinstaller": "6.11.1", "innosetup_package_version": "6.7.1",
                        "innosetup_compiler_file_version": "0.0.0.0",
                        "innosetup_version_source": "installed-package-metadata",
                        "innosetup_identity_verified": True},
        "reproducible_build": {"status": "NOT_CLAIMED", "reason": "single build"},
        "artifact_scope": "outer release artifacts; inner bundle files inside the portable ZIP are not "
                          "individually hashed here",
        "artifacts": entries,
    }), encoding="utf-8")
    return installer, metadata, digest


def _run(root: Path, host: FakeHost, module=None, **overrides):
    # `module` is injected rather than rebuilt for the tests that have to hook the reader itself: each
    # call to `_evidence_module()` executes a *fresh* module object, so a monkeypatch installed on one
    # instance is invisible to the run if the run loads another.
    module = module or _evidence_module()
    installer, _, digest = _release(root / "release")
    options = {"installer": installer, "expected_sha256": digest, "app_version": "1.0.0",
               "work_root": root / "work", "runner": host, "poll_interval": 0.001,
               "settle_seconds": 0.05}
    options.update(overrides)
    return module, module.run_lifecycle(**options)


def test_lifecycle_passes_only_when_install_run_and_uninstall_are_all_proven(tmp_path):
    _, report = _run(tmp_path, FakeHost())
    assert [step["name"] for step in report["steps"]] == [
        "verify_installer", "silent_install", "installed_files", "installed_version",
        "installed_smoke", "data_outside_install_dir", "silent_uninstall",
        "install_files_removed", "user_data_preserved",
    ]
    assert report["status"] == "PASS"
    assert report["installer_hash_verified"] is True
    assert report["path_containment"] == {
        "data_root_outside_install_dir": True, "log_root_outside_install_dir": True,
        "backup_root_outside_install_dir": True,
    }
    assert report["installed_smoke"] == {
        "exit_code": 0, "wrote_log_outside_install_dir": True, "secret_leak_detected": False,
        "new_files_in_install_dir": [], "changed_files_in_install_dir": [],
        # deletions are their own channel, so "the install tree is intact" means what it says
        "deleted_files_in_install_dir": [],
        "success_marker_found": True, "fatal_marker_found": False, "success_marker_channel": "stdout",
    }
    assert _step(report, "installed_smoke")["detail"].startswith("exit 0; success marker via stdout")
    assert report["cleaned_up"] is True and not (tmp_path / "work").exists()


def test_installed_exe_runs_with_isolated_roots_and_cleared_credentials(tmp_path):
    host = FakeHost()
    _run(tmp_path, host)
    smoke_env = next(env for env, call in zip(host.envs, host.calls)
                     if Path(call[0]).name.lower() == "drillmaster.exe")
    assert smoke_env["DRILLMASTER_ENV"] == "test"
    assert smoke_env["DRILLMASTER_AI_IMPORT"] == "0"
    assert (tmp_path / "work" / "userdata") == Path(smoke_env["DRILLMASTER_DATA_DIR"])
    for secret_key in ("DRILLMASTER_ADMIN_PASSWORD", "DRILLMASTER_USER_PASSWORD", "DRILLMASTER_VIEWER_PASSWORD"):
        assert secret_key not in smoke_env, "bootstrap credentials must never reach the installed smoke"
    install_call = host.calls[0]
    assert "/VERYSILENT" in install_call and "/SUPPRESSMSGBOXES" in install_call and "/NORESTART" in install_call


def test_installer_hash_is_bound_before_anything_is_executed(tmp_path):
    host = FakeHost()
    installer, _, digest = _release(tmp_path / "release")
    module = _evidence_module()
    report = module.run_lifecycle(installer=installer, expected_sha256="f" * 64, app_version="1.0.0",
                                  work_root=tmp_path / "work", runner=host, poll_interval=0.001,
                                  settle_seconds=0.01)
    assert report["status"] == "FAIL"
    assert report["steps"][0]["name"] == "verify_installer"
    assert "SHA-256 mismatch" in report["steps"][0]["detail"]
    assert host.calls == [], "an artifact whose hash does not match must never be executed"


def test_portable_archive_is_refused_as_a_lifecycle_target(tmp_path):
    module = _evidence_module()
    _, metadata, digest = _release(tmp_path / "release")
    archive = metadata.parent / "DrillMaster-1.0.0-windows-x64.zip"
    archive.write_bytes(b"zip")
    with pytest.raises(ValueError, match="not the portable ZIP"):
        module.run_lifecycle(installer=archive, expected_sha256=digest, app_version="1.0.0",
                             work_root=tmp_path / "work", runner=FakeHost())


def test_release_metadata_binding_refuses_an_unlisted_installer(tmp_path):
    module = _evidence_module()
    installer, metadata, _ = _release(tmp_path / "release")
    payload = {"artifacts": [{"filename": "other.exe", "sha256": "0" * 64}]}
    with pytest.raises(ValueError, match="not listed in release metadata"):
        module._installer_entry(payload, installer)


@pytest.fixture
def secret_in_environment(monkeypatch):
    """The smoke isolation clears bootstrap credentials, so a leak needs one to exist."""
    monkeypatch.setenv("DRILLMASTER_ADMIN_PASSWORD", "hunter2-super-secret")


@pytest.mark.parametrize("host, expected_step, fragment", [
    (FakeHost(install_exit_code=1), "silent_install", "exit 1"),
    (FakeHost(uninstall_exit_code=2), "silent_uninstall", "exit_code"),
    (FakeHost(smoke_exit_code=3), "installed_smoke", "exit_code"),
    (FakeHost(product_version="0.9.0.0"), "installed_version", "does not match the authoritative"),
    (FakeHost(product_version=""), "installed_version", "does not match the authoritative"),
    (FakeHost(leak_value="hunter2-super-secret"), "installed_smoke", "secret_leak_detected"),
    (FakeHost(write_into_install_dir=True), "installed_smoke", "drillmaster.db"),
    (FakeHost(uninstall_removes=False), "install_files_removed", "files remain"),
    (FakeHost(keep_sentinel=False), "user_data_preserved", "did not survive"),
])
def test_each_missing_proof_fails_the_lifecycle(tmp_path, host, expected_step, fragment, secret_in_environment):
    case_root = tmp_path / "case"
    _, report = _run(case_root, host)
    assert report["status"] == "FAIL"
    failed = [step for step in report["steps"] if step["status"] == "FAIL"]
    assert [step["name"] for step in failed] == [expected_step], report["steps"]
    assert fragment in failed[0]["detail"], failed[0]["detail"]
    assert not (case_root / "work").exists(), "the throwaway work root is cleaned up even on failure"


def test_secret_value_is_redacted_from_the_persisted_diagnostics(tmp_path, secret_in_environment):
    _, report = _run(tmp_path, FakeHost(leak_value="hunter2-super-secret"))
    assert "hunter2-super-secret" not in json.dumps(report)
    assert "[REDACTED]" in report["diagnostics"]["installed_smoke_output"]
    assert report["status"] == "FAIL"


def test_diagnostics_are_bounded():
    module = _evidence_module()
    bounded = module.bound("x" * 200000)
    assert len(bounded) < module.DIAGNOSTIC_LIMIT + 200 and "elided" in bounded
    assert module.bound("short") == "short"
    assert module.redact("a secret-value b", ["secret-value"]) == "a [REDACTED] b"


def test_signing_status_reports_unsigned_without_failing(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost(signature_status="NotSigned"))
    assert report["status"] == "UNSIGNED"
    assert report["examined_count"] == 2
    assert report["signing_configured_in_build"] is False
    assert report["credentials_available"] is False
    assert "code-signing certificate" in report["prerequisite"]
    names = [item["filename"] for item in report["files"]]
    assert "DrillMaster-1.0.0-Setup.exe" in names
    assert "signer" not in report["files"][0], "an unsigned artifact has no signer to name"


def test_inner_bundle_executable_is_examined_from_the_verified_archive(tmp_path):
    """A claim about the shipped exe must be about bytes the published archive contains."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    inner = next(item for item in report["files"] if item["filename"] == "DrillMaster.exe")
    assert inner["provenance"] == "extracted from DrillMaster-1.0.0-windows-x64.zip"
    assert inner["sha256"] == hashlib.sha256(b"frozen executable").hexdigest()
    assert inner["manifest_digest_match"] is True
    # the outer archive digest is recorded separately and never conflated with the inner one
    assert inner["container_archive_sha256"] == hashlib.sha256(
        (tmp_path / "release" / "DrillMaster-1.0.0-windows-x64.zip").read_bytes()).hexdigest()
    assert inner["container_archive"] == "DrillMaster-1.0.0-windows-x64.zip"
    assert inner["container_member"] == "DrillMaster-1.0.0/DrillMaster.exe"
    assert inner["container_archive_sha256"] == hashlib.sha256(
        (tmp_path / "release" / "DrillMaster-1.0.0-windows-x64.zip").read_bytes()).hexdigest()
    # inner and outer digests are distinct values in distinct fields
    assert inner["sha256"] != inner["container_archive_sha256"]
    archive_row = next(item for item in report["files"] if item["filename"].endswith(".zip"))
    assert archive_row["status"] == "NOT_APPLICABLE"
    assert archive_row["signature_bearing"] is False


def test_a_release_dir_copy_of_the_executable_is_never_quietly_accepted_as_evidence(tmp_path):
    """Only the manifest-listed installer and the archive-derived inner exe are examined."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    decoy = tmp_path / "release" / "DrillMaster-1.0.0" / "DrillMaster.exe"
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_bytes(b"different bytes than the published archive holds")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    inner = next(item for item in report["files"] if item["filename"] == "DrillMaster.exe")
    assert inner["sha256"] == hashlib.sha256(b"frozen executable").hexdigest()
    assert len([item for item in report["files"] if item["filename"] == "DrillMaster.exe"]) == 1


def test_corrupt_or_mismatched_archive_is_refused_before_any_extraction(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    archive = tmp_path / "release" / "DrillMaster-1.0.0-windows-x64.zip"
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="digest does not match release metadata"):
        module.run_signing(release_metadata_path=metadata, runner=FakeHost())


@pytest.mark.parametrize("member, fragment", [
    ("", "no DrillMaster.exe member"),
    ("../DrillMaster.exe", "unsafe member path"),
    ("DrillMaster.exe", "unsafe member path"),
])
def test_extraction_refuses_an_archive_without_a_single_safe_executable_member(tmp_path, member, fragment):
    module = _evidence_module()
    root = tmp_path / "release"
    root.mkdir(parents=True)
    installer = root / "DrillMaster-1.0.0-Setup.exe"
    installer.write_bytes(b"installer")
    archive, archive_digest = _write_portable_zip(root, member=member)
    metadata = root / "release-metadata.json"
    metadata.write_text(json.dumps({"schema": "drillmaster-release-artifacts/v2", "version": "1.0.0",
                                    "git_sha": "a" * 40, "platform": "windows-x64", "python": "3.12.10",
                                    "build_tools": {"pip": "25.3", "pyinstaller": "6.11.1",
                                                    "innosetup_package_version": "6.7.1",
                                                    "innosetup_compiler_file_version": "0.0.0.0",
                                                    "innosetup_version_source": "installed-package-metadata",
                                                    "innosetup_identity_verified": True},
                                    "reproducible_build": {"status": "NOT_CLAIMED", "reason": "single build"},
                                    "artifact_scope": "outer release artifacts",
                                    "artifacts": [
                                        {"filename": installer.name,
                                         "sha256": hashlib.sha256(b"installer").hexdigest(), "size_bytes": 8},
                                        {"filename": archive.name, "sha256": archive_digest,
                                         "size_bytes": archive.stat().st_size},
                                    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match=fragment):
        module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    assert not (root.parent / "DrillMaster.exe").exists(), "an unsafe member must never escape the scratch root"
    assert not (root / "DrillMaster.exe").exists()


def test_extraction_bound_and_duplicate_member_are_refused(tmp_path):
    import zipfile

    module = _evidence_module()
    root = tmp_path / "release"
    root.mkdir(parents=True)
    archive = root / "DrillMaster-1.0.0-windows-x64.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("DrillMaster-1.0.0/DrillMaster.exe", b"one")
        bundle.writestr("DrillMaster-1.0.0/sub/DrillMaster.exe", b"two")
    with pytest.raises(ValueError, match="not unambiguously identified"):
        module.extract_verified_member(archive, "DrillMaster.exe", root)
    single = tmp_path / "single.zip"
    with zipfile.ZipFile(single, "w") as bundle:
        bundle.writestr("DrillMaster-1.0.0/DrillMaster.exe", b"one")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(ValueError, match="exceeds the extraction bound"):
        module.extract_verified_member(single, "DrillMaster.exe", scratch, max_bytes=1)
    extracted, member = module.extract_verified_member(single, "DrillMaster.exe", scratch)
    assert member == "DrillMaster-1.0.0/DrillMaster.exe" and extracted.read_bytes() == b"one"


def test_missing_artifact_or_manifest_entry_is_reported_without_inventing_a_state(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    (tmp_path / "release" / "DrillMaster-1.0.0-Setup.exe").unlink()
    with pytest.raises(ValueError, match="missing"):
        module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["artifacts"] = [item for item in payload["artifacts"] if not item["filename"].endswith(".zip")]
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="lists no .zip"):
        module.run_signing(release_metadata_path=metadata, runner=FakeHost())


def test_mixed_and_untrusted_signature_states(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")

    def host(argv, environment, cwd, timeout):
        if Path(argv[0]).name.lower() == "powershell.exe":
            target = Path((environment or {})["DRILLMASTER_TARGET_PATH"])
            signed = target.name == "DrillMaster-1.0.0-Setup.exe"
            payload = {"Status": "NotTrusted" if signed else "Valid",
                       "StatusMessage": "A certificate chain processed, but terminated in a root certificate which is not trusted.",
                       "SignerSubject": "CN=DrillMaster Inc." if signed else None}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        raise AssertionError(f"unexpected command {argv}")

    report = module.run_signing(release_metadata_path=metadata, runner=host)
    statuses = {item["filename"]: item["status"] for item in report["files"]}
    raw = {item["filename"]: item["raw_status"] for item in report["files"]}
    # The Windows spelling is preserved verbatim next to the normalized finding, so a reader
    # can see what the host actually said and what the policy made of it.
    assert raw["DrillMaster-1.0.0-Setup.exe"] == "NotTrusted"
    assert raw["DrillMaster.exe"] == "Valid"
    assert statuses["DrillMaster-1.0.0-Setup.exe"] == "FAIL"
    assert statuses["DrillMaster.exe"] == "PASS"
    assert report["status"] == "FAIL", "a mixed state must not be reported as a clean signature"
    assert statuses.get("DrillMaster-1.0.0-windows-x64.zip") == "NOT_APPLICABLE"


def test_uniformly_valid_signatures_are_the_only_pass(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata,
                               runner=FakeHost(signature_status="Valid", signer_subject="CN=DrillMaster Inc."))
    assert report["status"] == "PASS"
    assert all(item.get("signer") == "CN=DrillMaster Inc." for item in report["files"] if item["signature_bearing"])


def test_unreadable_powershell_result_is_unknown_and_never_unsigned(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")

    def host(argv, environment, cwd, timeout):
        if Path(argv[0]).name.lower() == "powershell.exe":
            return SimpleNamespace(returncode=0, stdout="not json at all", stderr="")
        raise AssertionError("no other command should run")

    report = module.run_signing(release_metadata_path=metadata, runner=host)
    assert report["status"] == "UNKNOWN"
    assert all(item["status"] == "UNKNOWN" for item in report["files"] if item["signature_bearing"])
    assert "unreadable output" in report["files"][0]["status_message"]


def test_powershell_invocation_failure_is_unknown(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")

    def host(argv, environment, cwd, timeout):
        # The shell ran and refused the statement: a nonzero exit with the reason on stderr.
        return SimpleNamespace(returncode=1, stdout="", stderr="Get-AuthenticodeSignature : Access denied")

    report = module.run_signing(release_metadata_path=metadata, runner=host)
    assert report["status"] == "UNKNOWN"
    assert "powershell exit 1" in report["files"][0]["status_message"]


def test_a_query_that_never_answers_is_attributed_instead_of_crashing(tmp_path, monkeypatch):
    """A timeout is a host limitation with a cause, not a missing record.

    Before this rule the exception escaped the tool: the release directory held no
    signing-status.json, the workflow could only say "signature verification produced no record",
    and the actual reason survived only as a traceback in the console scrollback.
    """
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    timeout = 45  # an arbitrary budget; the record must quote the one that actually applied

    def host(argv, environment, cwd, given_timeout):
        assert given_timeout == timeout
        raise subprocess.TimeoutExpired(argv, given_timeout)

    report = module.run_signing(release_metadata_path=metadata, runner=host, timeout=timeout)
    assert report["status"] == "UNKNOWN", "an unanswered query is never promoted or demoted"
    assert report["harness"]["probe_error"] == f"powershell did not answer within {timeout} seconds"
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert rows and all(f"did not answer within {timeout} seconds" in item["status_message"] for item in rows)
    module.validate_signing_document(report)
    # The tool must still exit successfully with a valid record on disk: the workflow's rule is
    # that a step which wrote nothing is the failure, and this step wrote everything it knows.
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "default_runner", host)
    out = tmp_path / "signing-status.json"
    assert module.main(["signing", "--release-metadata", str(metadata), "--json-out", str(out),
                        "--timeout", str(timeout)]) == 0
    assert f"did not answer within {timeout} seconds" in out.read_text(encoding="utf-8")


def test_a_timed_out_query_fails_the_lifecycle_step_with_a_cause(tmp_path):
    """The lifecycle shell queries go through the same rule: a cause, not a traceback."""
    module = _evidence_module()

    def host(argv, environment, cwd, timeout):
        if Path(argv[0]).name.lower() == "powershell.exe":
            raise subprocess.TimeoutExpired(argv, timeout)
        return FakeHost()(argv, environment, cwd, timeout)

    installer, _, digest = _release(tmp_path / "release")
    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work", runner=host, timeout=45,
                                  poll_interval=0.001, settle_seconds=0.05)
    assert report["status"] == "FAIL"
    step = _step(report, "installed_version")
    assert step["status"] == "FAIL"
    assert "did not answer within 45 seconds" in step["detail"]


def test_a_shell_that_cannot_be_started_reports_the_cause_per_file(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")

    def host(argv, environment, cwd, timeout):
        raise FileNotFoundError(2, "The system cannot find the file specified")

    report = module.run_signing(release_metadata_path=metadata, runner=host)
    assert report["status"] == "UNKNOWN"
    assert "powershell could not be started" in report["harness"]["probe_error"]
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert all("could not be started" in item["status_message"] for item in rows)


def test_the_markdown_record_publishes_the_query_host(tmp_path):
    """The step summary is uncapped and reachable, so the harness facts belong in it too."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata,
                               runner=FakeHost(signature_cmdlet="missing"))
    text = module.render_markdown(report, "Windows signing evidence")
    assert "Query host: PowerShell 5.1.20348.2402" in text
    assert "Microsoft.PowerShell.Security import succeeded" in text, (
        "the import outcome must be readable as text, and must not be inferred from the host that "
        "also reported the command missing")
    assert "cmdlet unavailable" in text, "availability must be readable as its own fact"
    assert "separate observations" in text, (
        "the summary must state the rule, or a reader of the summary alone repeats the conflation")
    assert "probe exit code 0" in text


def _harness_for(tmp_path, name, **host_kwargs):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / name)
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost(**host_kwargs))
    return module, report


def test_an_import_failure_alone_never_suppresses_a_query_the_host_can_answer(tmp_path):
    """The determinative rule of this correction, in both directions.

    PowerShell that imported the security module badly can still resolve the cmdlet and answer about
    a file; and PowerShell that imported it cleanly can still lack the cmdlet.  Only the second case
    excuses the run from asking, and only the first yields a state about the files.
    """
    _, report = _harness_for(tmp_path, "import-failed-cmdlet-available",
                             module_import_result="failed",
                             module_import_error="Exception calling \"Add\": access denied "
                                                 "at line 4 char 1 in C:\\Users\\runner\\docs\\x.ps1",
                             signature_status="NotSigned", signature_message="No signature is present.")
    harness = report["harness"]
    assert harness["security_module_import"] == "failed"
    assert harness["cmdlet_available"] is True, ("a complaint about the import must not become a claim "
                                                 "that the cmdlet is unavailable")
    assert harness["probe_usable"] is True
    assert "access denied" in harness["security_module_import_error"]
    assert len(harness["security_module_import_error"]) <= 300, (
        "a PowerShell error is untrusted text: it is bounded like every other diagnostic")
    assert "characters elided" not in harness["security_module_import_error"]
    assert report["status"] == "UNSIGNED", "the answered query decides, not the import anomaly"
    assert [item["raw_status"] for item in report["files"] if item["signature_bearing"]] == ["NotSigned"] * 2
    assert all(item["status_message"] == "No signature is present." for item in report["files"]
               if item["signature_bearing"])


def test_an_overlong_import_error_is_clipped_and_says_so(tmp_path):
    """A host that dumps a stack trace into the exception message must not enlarge the record."""
    _, report = _harness_for(tmp_path, "long-import-error", signature_cmdlet="missing",
                             module_import_result="failed",
                             module_import_error=("Module loading failed. " * 60))
    error = report["harness"]["security_module_import_error"]
    assert len(error) < len("Module loading failed. " * 60), "the published diagnostic must be clipped"
    assert "characters elided" in error, "truncation must be visible rather than silent"


def test_a_missing_cmdlet_with_a_clean_import_is_attributed_to_the_host_not_the_import(tmp_path):
    _, report = _harness_for(tmp_path, "import-ok-cmdlet-missing", signature_cmdlet="missing",
                             module_import_result="succeeded")
    assert report["harness"]["security_module_import"] == "succeeded"
    assert "security_module_import_error" not in report["harness"]
    reasons = {item["status_message"] for item in report["files"] if item["signature_bearing"]}
    assert len(reasons) == 1
    reason = reasons.pop()
    assert "imported successfully" in reason and "did not resolve" in reason
    assert "failed" not in reason, ("the import succeeded; the record must not imply otherwise while "
                                   "explaining why no query was made")


def test_a_failed_import_with_a_missing_cmdlet_states_the_import_as_the_cause(tmp_path):
    _, report = _harness_for(tmp_path, "import-failed-cmdlet-missing", signature_cmdlet="missing",
                             module_import_result="failed",
                             module_import_error="The specified module 'Microsoft.PowerShell.Security' "
                                                 "was not loaded because no valid module file was found")
    assert report["harness"]["security_module_import"] == "failed"
    assert report["harness"]["cmdlet_available"] is False
    assert report["status"] == "UNKNOWN"
    reason = {item["status_message"] for item in report["files"] if item["signature_bearing"]}.pop()
    assert "explicit Import-Module of Microsoft.PowerShell.Security failed" in reason
    assert "no valid module file was found" in reason, "the bounded error belongs in the reason"
    # a missing cmdlet is a statement about the host only: the files stay uncharacterised
    assert all(item["raw_status"] == "" for item in report["files"] if item["signature_bearing"])


def test_an_unreported_import_state_is_recorded_as_unreported_not_as_a_failure(tmp_path):
    """A host that answers the cmdlet lookup but not the import question must not be read as failing it."""
    _, report = _harness_for(tmp_path, "import-unreported", signature_cmdlet="missing",
                             module_import_result="unreported")
    assert report["harness"]["security_module_import"] == "unreported"
    reason = {item["status_message"] for item in report["files"] if item["signature_bearing"]}.pop()
    assert "did not report whether the module import succeeded" in reason
    assert "failed" not in reason


def test_a_payload_that_is_json_but_not_an_object_is_unknown(tmp_path):
    """`[]` and `"text"` parse; neither answers the question, so neither may become a status."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "not-object")

    class ArrayHost(FakeHost):
        def __call__(self, argv, environment=None, cwd=None, timeout=None, **kwargs):
            if "Get-AuthenticodeSignature" in argv[-1] and "Get-Command" not in argv[-1]:
                return SimpleNamespace(returncode=0, stdout="[]", stderr="")
            return super().__call__(argv, environment, cwd, timeout)

    report = module.run_signing(release_metadata_path=metadata, runner=ArrayHost())
    assert report["status"] == "UNKNOWN"
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert len(rows) == 2, "only the executables were queried"
    assert all("returned a non-object" in item["status_message"] for item in rows)
    assert all(item["raw_status"] == "" for item in report["files"])
    assert report["files"][2]["status"] == "NOT_APPLICABLE", (
        "the container row is described by provenance and is untouched by a failed query")


def test_a_probe_that_times_out_still_leaves_the_queries_to_answer(tmp_path):
    """Probe unusable + queries answered: the run reports a determinate state with a broken diagnostic."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "probe-timeout")

    class ProbeTimeoutHost(FakeHost):
        def __call__(self, argv, environment=None, cwd=None, timeout=None, **kwargs):
            if "Get-Command Get-AuthenticodeSignature" in argv[-1]:
                raise subprocess.TimeoutExpired(argv, timeout or 0)
            return super().__call__(argv, environment, cwd, timeout)

    report = module.run_signing(release_metadata_path=metadata,
                                runner=ProbeTimeoutHost(signature_status="NotSigned",
                                                         signature_message="No signature is present."))
    assert report["harness"]["probe_usable"] is False
    assert report["status"] == "UNSIGNED", "a broken probe must not soften an answered question"
    assert report["files"][0]["raw_status"] == "NotSigned"


def test_a_quiet_successful_query_still_reports_its_exit_code(tmp_path):
    """The record carries the status the host returned; a printed payload is not itself a 0.

    Before this, `powershell_exit_code` accompanied only payloads that came with stderr, so
    `probe_exit_code: 0` was an inference the reader had to redo - and an inference that a
    different caller could get wrong.
    """
    module = _evidence_module()
    host = FakeHost(signature_status="Valid", signer_subject="CN=Drill Master", signature_message="The signature is OK.")
    payload = module.run_powershell(module.SIGNING_PROBE_SCRIPT, tmp_path, host, 5)
    assert payload["powershell_exit_code"] == 0
    assert "powershell_stderr" not in payload, "a clean run has no stderr to attach"


def test_a_probe_that_says_nothing_about_the_import_does_not_say_it_failed(tmp_path):
    """Silence is not a failure.

    The import field can be absent for a reason the probe cannot control - an older script, a host
    that answers part of the hashtable - and a record that filled that gap with `failed` would
    republish exactly the over-claim M42.6 exists to remove.
    """
    _, report = _harness_for(tmp_path, "import-field-absent", signature_cmdlet="missing",
                             module_import_result=None)
    assert report["harness"]["security_module_import"] == "unreported"
    reason = {item["status_message"] for item in report["files"] if item["signature_bearing"]}.pop()
    assert "did not report whether the module import succeeded" in reason
    assert "failed" not in reason, "an absent observation must not be written up as a refused import"


def test_a_probe_that_reports_no_command_is_not_recorded_as_having_answered(tmp_path):
    """`probe_usable` is about the answer, not about the exit code.

    A payload that parses and exits 0 while naming no command told the run nothing; recording that
    as usable would leave a reader to guess whether the probe ran at all.
    """
    module = _evidence_module()
    _, report = _harness_for(tmp_path, "probe-answers-nothing", probe_omits_cmdlet=True,
                             signature_status="NotSigned", signature_message="No signature is present.")
    assert report["harness"]["probe_usable"] is False
    assert report["harness"]["query_command"] == "unknown"
    assert report["harness"]["cmdlet_available"] is None, ("no answer about availability may be read as "
                                                          "either available or missing")
    assert report["status"] == "UNSIGNED", "the queries still answered, and they are what decides"
    assert [item["raw_status"] for item in report["files"] if item["signature_bearing"]] == ["NotSigned"] * 2


def test_release_examination_does_not_mutate_the_published_artifacts(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted((tmp_path / "release").iterdir()) if path.is_file()}
    module.run_signing(release_metadata_path=metadata, runner=FakeHost(signature_status="Valid",
                                                                       signer_subject="CN=x"))
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted((tmp_path / "release").iterdir()) if path.is_file()}
    assert before == after


def test_record_declares_its_own_policy_and_counts_examined_files(tmp_path):
    """The published evidence states what it covered and what the gate does with it."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    assert report["examined_count"] == 2 and report["archive_count"] == 1
    assert "never fails the packaging gate" in report["policy"]
    assert "no interpretable record" in report["policy"]
    markdown = module.render_markdown(report, "signature evidence")
    for fragment in ("DrillMaster.exe", "NOT_APPLICABLE", "inside `DrillMaster-1.0.0/DrillMaster.exe`",
                     "Policy:"):
        assert fragment in markdown, fragment
    assert "sha256:" in markdown and "from: extracted from" in markdown


def test_an_out_of_vocabulary_aggregate_from_the_tool_is_refused(tmp_path, monkeypatch):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    monkeypatch.setattr(module, "aggregate_signing_status", lambda files: "SIGNED")
    with pytest.raises(ValueError, match="outside the vocabulary"):
        module.run_signing(release_metadata_path=metadata, runner=FakeHost())


def test_markdown_summary_lists_every_step(tmp_path):
    module, report = _run(tmp_path, FakeHost())
    text = module.render_markdown(report, "Windows lifecycle evidence")
    assert "Status: **PASS**" in text
    for step in report["steps"]:
        assert f"| {step['name']} | PASS |" in text


@pytest.mark.skipif(sys.platform == "win32", reason="this test proves the non-Windows refusal")
def test_lifecycle_on_a_non_windows_host_reports_not_run(tmp_path):
    module = _evidence_module()
    installer, metadata, _ = _release(tmp_path / "release")
    json_out = tmp_path / "installer-lifecycle.json"
    assert module.main(["lifecycle", "--installer", str(installer), "--release-metadata", str(metadata),
                        "--app-version", "1.0.0", "--work-root", str(tmp_path / "work"),
                        "--json-out", str(json_out)]) == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["status"] == "NOT_RUN"
    assert payload["steps"] == [{"name": "platform_gate", "status": "NOT_RUN",
                                 "detail": "installed-application lifecycle requires a Windows host"}]


def test_main_refuses_a_disagreeing_expected_hash(tmp_path, capsys):
    module = _evidence_module()
    installer, metadata, _ = _release(tmp_path / "release")
    exit_code = module.main(["lifecycle", "--installer", str(installer), "--release-metadata", str(metadata),
                             "--expected-sha256", "0" * 64, "--app-version", "1.0.0",
                             "--work-root", str(tmp_path / "work"), "--json-out", str(tmp_path / "out.json")])
    assert exit_code == 2
    assert "disagrees with release metadata" in capsys.readouterr().err


def test_an_untrusted_signature_is_recorded_as_a_finding_but_still_exits_cleanly(tmp_path, capsys, monkeypatch):
    """Signing state must never redden a packaging gate; only a missing record may."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    host = FakeHost(signature_status="NotTrusted", signer_subject="CN=Revoked")
    report = module.run_signing(release_metadata_path=metadata, runner=host)
    assert report["status"] == "FAIL"
    assert report["files"][0]["raw_status"] == "NotTrusted"
    assert "CN=Revoked" == report["files"][0]["signer"]
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "default_runner", host)
    json_out = tmp_path / "signing-status.json"
    assert module.main(["signing", "--release-metadata", str(metadata), "--json-out", str(json_out)]) == 0
    assert json.loads(json_out.read_text(encoding="utf-8"))["status"] == "FAIL"
    assert "FAIL" in capsys.readouterr().out


def test_a_missing_signature_status_field_is_unknown_not_unsigned(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")

    def host(argv, environment, cwd, timeout):
        if Path(argv[0]).name.lower() == "powershell.exe":
            return SimpleNamespace(returncode=0, stdout=json.dumps({"Status": "", "StatusMessage": ""}), stderr="")
        raise AssertionError("only the signature query should run")

    report = module.run_signing(release_metadata_path=metadata, runner=host)
    assert report["status"] == "UNKNOWN"
    assert report["files"][0]["status"] == "UNKNOWN"


def test_signing_fails_loudly_when_no_record_can_be_written(tmp_path, capsys, monkeypatch):
    module = _evidence_module()
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "default_runner", FakeHost())
    exit_code = module.main(["signing", "--release-metadata", str(tmp_path / "absent.json"),
                             "--json-out", str(tmp_path / "signing-status.json")])
    assert exit_code == 1
    assert "produced no record" in capsys.readouterr().err

def test_install_succeeding_without_an_installed_executable_fails_the_lifecycle(tmp_path):
    """A zero exit code from the installer is not proof that anything was installed."""
    _, report = _run(tmp_path, FakeHost(install_writes_exe=False))
    assert report["status"] == "FAIL"
    step = _step(report, "installed_files")
    assert step["status"] == "FAIL"
    assert "DrillMaster.exe" in step["detail"] and "unins000.exe" in step["detail"]


def test_a_clean_exit_without_the_success_marker_is_a_failure(tmp_path):
    """An executable that exits 0 without running the smoke (help, early return) is rejected."""
    _, report = _run(tmp_path, FakeHost(smoke_marker_in="none",
                                        smoke_output="DrillMaster 1.0.0\nusage: --package-smoke"))
    assert report["status"] == "FAIL"
    assert report["installed_smoke"]["success_marker_found"] is False
    assert _step(report, "installed_smoke")["status"] == "FAIL"


def test_a_fatal_marker_with_a_zero_exit_code_is_still_a_failure(tmp_path):
    _, report = _run(tmp_path, FakeHost(run_stdout="FATAL: could not create the database"))
    assert report["status"] == "FAIL"
    assert report["installed_smoke"]["fatal_marker_found"] is True
    assert _step(report, "installed_smoke")["status"] == "FAIL"


def test_uninstall_exit_code_is_never_inherited_from_the_previous_command(tmp_path):
    """The uninstall verdict reads its own captured exit code, whatever ran before it."""
    _, report = _run(tmp_path, FakeHost(uninstall_exit_code=3))
    step = _step(report, "silent_uninstall")
    assert step["status"] == "FAIL"
    assert '"exit_code": 3' in step["detail"]


def test_uninstaller_returning_cleanly_while_files_remain_is_a_failure(tmp_path):
    """Inno Setup's uninstaller can return before the deletion pass finishes."""
    host = FakeHost()
    host.uninstall_removes = False
    _, report = _run(tmp_path, host)
    assert _step(report, "silent_uninstall")["status"] == "PASS", "the process itself did succeed"
    step = _step(report, "install_files_removed")
    assert step["status"] == "FAIL"
    assert "unins000.exe" in step["detail"] and "DrillMaster.exe" in step["detail"]


def test_uninstall_deleting_user_data_is_a_failure(tmp_path):
    _, report = _run(tmp_path, FakeHost(keep_sentinel=False))
    step = _step(report, "user_data_preserved")
    assert step["status"] == "FAIL" and "did not survive uninstall" in step["detail"]


def test_the_sentinel_is_written_so_no_platform_translates_its_newline(tmp_path, monkeypatch):
    """The survival proof is byte for byte, so the write must not go through a text-mode translation.

    ``Path.write_text`` translates "\\n" to the platform's line ending -- on Windows, "\\r\\n" -- while the
    read that decides whether the sentinel survived is binary and exact, so the sentinel's own bytes failed
    the comparison on Windows in every lifecycle, real and scripted, whatever the uninstaller did.  The
    translation is emulated here the way this suite emulates a failing open and a growing log, which is the
    only way the shared source gate can see a platform behaviour it does not have; what is asserted is the
    step's verdict as well as the mechanism, so a repair that keeps the text write fails too.
    """
    real_write_text = Path.write_text
    translated: list[str] = []

    def windows_text_write(self, data, *args, **kwargs):
        if self.name == "sentinel-preserve.txt" and "\r\n" not in data:
            data = data.replace("\n", "\r\n")
            translated.append(str(self))
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", windows_text_write)
    _, report = _run(tmp_path, FakeHost())
    assert translated == [], (
        "the sentinel went through a platform-translating write; it wrote " + ", ".join(translated))
    step = _step(report, "user_data_preserved")
    assert step["status"] == "PASS", step
    assert report["status"] == "PASS"


def test_executable_query_returning_malformed_output_fails_the_version_step(tmp_path):
    _, report = _run(tmp_path, FakeHost(powershell_version_output="not-json"))
    step = _step(report, "installed_version")
    assert step["status"] == "FAIL" and "unreadable output" in step["detail"]


def test_executable_timeout_is_recorded_as_a_nonzero_exit(tmp_path):
    _, report = _run(tmp_path, FakeHost(run_returncode=124))
    step = _step(report, "installed_smoke")
    assert step["status"] == "FAIL"
    assert report["installed_smoke"]["exit_code"] == 124


def test_every_executed_path_stays_inside_the_isolated_root_and_nothing_is_left_behind(tmp_path):
    """Synthetic install/data/log roots must be contained by one throwaway directory."""
    host = FakeHost()
    work = tmp_path / "work"
    _, report = _run(tmp_path, host, work_root=work)
    assert report["status"] == "PASS" and report["path_containment"] == {
        "data_root_outside_install_dir": True, "log_root_outside_install_dir": True,
        "backup_root_outside_install_dir": True}
    root = work.resolve()
    # Everything the lifecycle creates is contained by the throwaway root; the only thing
    # outside it is the published installer, which is read, never written into.
    created = [_arg_value(call, "/DIR=") for call in host.calls if any(str(a).startswith("/DIR=") for a in call)]
    for call, env in zip(host.calls, host.envs):
        if Path(call[0]).name.lower() == "drillmaster.exe":
            created += [Path(env[key]) for key in ("DRILLMASTER_DATA_DIR", "DRILLMASTER_LOG_DIR",
                                                   "DRILLMASTER_BACKUP_DIR")]
    assert len(created) == 4, created
    for path in created:
        assert root in path.resolve().parents, f"{path} escaped the isolated root"
    written = sorted(item for item in root.iterdir()) if root.exists() else []
    assert not written, f"scratch entries survived: {written}"
    assert report["cleaned_up"] is True
    assert not work.exists() or not list(work.iterdir())


def test_a_crash_inside_a_step_still_removes_the_scratch_tree(tmp_path):
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / "release")
    work = tmp_path / "work-crash"
    with pytest.raises(RuntimeError):
        module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                             work_root=work, runner=FakeHost(raise_on_call=1), poll_interval=0.001,
                             settle_seconds=0.05)
    assert not work.exists() or not list(work.iterdir())


@pytest.mark.parametrize("folder", ["DrillMaster 1.0.0 (x64)", "پیش‌بینی DrillMaster"])
def test_spaces_and_non_ascii_paths_behave_like_their_ascii_equivalent(tmp_path, folder):
    """Windows installs under names with spaces and non-ASCII characters; quoting must survive."""
    if not folder.isascii() and sys.getfilesystemencoding().lower() not in {"utf-8", "utf8"}:
        pytest.skip("the POSIX test process cannot even create a non-ASCII path under a non-UTF-8 "
                    "locale; Windows uses wide file APIs, so this environment limitation is not what "
                    "the assertion is about")
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / folder)
    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work" / folder, runner=FakeHost(),
                                  poll_interval=0.001, settle_seconds=0.05)
    assert report["status"] == "PASS", report["steps"]
    assert _step(report, "silent_install")["detail"] == "target=install"


def test_a_file_version_disagreeing_with_the_product_version_fails_the_lifecycle(tmp_path):
    """The verdict uses the queried metadata, never the installer's file name."""
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / "release")

    def host(argv, environment, cwd, timeout):
        if Path(argv[0]).name.lower() == "powershell.exe" and "Get-AuthenticodeSignature" not in argv[-1]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"FileVersion": "9.9.9.9"}), stderr="")
        return FakeHost()(argv, environment, cwd, timeout)

    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work", runner=host, poll_interval=0.001,
                                  settle_seconds=0.05)
    assert report["status"] == "FAIL"
    step = _step(report, "installed_version")
    assert step["status"] == "FAIL" and "authoritative application version" in step["detail"]


@pytest.mark.parametrize("channel, expected", [("log", "application-log"), ("stdout", "stdout"),
                                               ("both", "stdout"), ("none", "none")])
def test_the_success_marker_is_accepted_from_either_channel_and_only_from_a_real_one(tmp_path, channel, expected):
    """A frozen windowed build has no console; its log is an equally authoritative channel."""
    _, report = _run(tmp_path, FakeHost(smoke_marker_in=channel))
    assert report["installed_smoke"]["success_marker_channel"] == expected
    assert report["installed_smoke"]["success_marker_found"] is (channel != "none")
    assert report["status"] == ("FAIL" if channel == "none" else "PASS")


# --- M42.4: the cause of a non-pass signature state must survive into the published record ---


def test_an_uninstaller_that_vanishes_mid_lifecycle_is_described_not_lost(tmp_path):
    """The gate run on 58b3912 failed exactly here, and the record could not say what happened.

    installed_files proved unins000.exe was there; the uninstall then found it gone, and the only
    published detail was a FileNotFoundError.  The lifecycle now names the sequence, lists what the
    install tree actually holds, and attaches the installer's own log tail, so the finding is
    attributable from the record without log or artifact access.
    """
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / "release")
    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work",
                                  runner=FakeHost(remove_uninstaller_during_smoke=True),
                                  poll_interval=0.001, settle_seconds=0.05)
    assert report["status"] == "FAIL"
    assert _step(report, "installed_files")["status"] == "PASS"
    uninstall = _step(report, "silent_uninstall")
    assert uninstall["status"] == "FAIL"
    assert "and is absent now" in uninstall["detail"], uninstall["detail"]
    assert "install tree holds 1 file(s) (directory present): DrillMaster.exe" in uninstall["detail"]
    # the sample behind that sentence is published too, so the claim is not just prose
    sample = report["diagnostics"]["uninstall_forensics"]["uninstaller_absent_before_launch"]
    assert sample["install_dir"]["is_dir"] is True and sample["install_dir_entries"]["count"] == 1
    assert sample["uninstaller"]["exists"] is False and sample["uninstall_log"]["exists"] is False
    assert "installer log tail" in uninstall["detail"]
    assert "Setup process started." in uninstall["detail"], "the tail is the point, not the label"
    assert "Setup process started" in sample["install_log"]["tail"]
    # and the smoke step must have recorded the disappearance it witnessed
    smoke = report["installed_smoke"]
    assert smoke["deleted_files_in_install_dir"] == ["unins000.exe"]
    assert "disappeared while it ran" in _step(report, "installed_smoke")["detail"]


def test_a_listed_but_unlaunchable_uninstaller_gets_one_bounded_retry(tmp_path):
    """A file the OS refuses to start is retried once -- and the anomaly stays in the record.

    This is the shape both Windows gate runs of the release produced: installed_files PASS, then
    CreateProcess on unins000.exe reporting that no such file exists.  A single settle-and-retry
    distinguishes a transient lock or scan from a deleted uninstaller without excusing anything:
    a second refusal still fails the step, and the recovery note is published either way.
    """
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / "release")
    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work",
                                  runner=FakeHost(unlaunchable_uninstall_attempts=1),
                                  poll_interval=0.001, settle_seconds=0.05)
    assert report["status"] == "PASS"
    assert _step(report, "silent_uninstall")["status"] == "PASS"
    assert _step(report, "install_files_removed")["status"] == "PASS"
    note = report["uninstall_launch_recovered"]
    assert "was listed but could not be launched" in note
    assert "after a 2 second settle the uninstaller is still listed" in note


def test_a_permanently_unlaunchable_uninstaller_still_fails_the_lifecycle(tmp_path):
    """The retry is not a waiver: two refusals fail the step, with both attempts recorded."""
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / "release")
    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work",
                                  runner=FakeHost(unlaunchable_uninstall_attempts=2),
                                  poll_interval=0.001, settle_seconds=0.05)
    assert report["status"] == "FAIL"
    detail = _step(report, "silent_uninstall")["detail"]
    assert "attempt 1:" in detail and "attempt 2:" in detail, detail
    # the detail is clipped to the diagnostic bound, so the tree prose lives in the notes beside it
    notes = report["uninstall_launch_notes"]
    assert "install tree holds 2 file(s) (directory present): DrillMaster.exe, unins000.exe" in notes
    assert "uninstall_launch_recovered" not in report


def test_an_uninstaller_deleted_after_the_refusal_is_recorded_as_gone(tmp_path):
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / "release")
    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work",
                                  runner=FakeHost(unlaunchable_uninstall_attempts=1,
                                                 unlink_uninstaller_on_refusal=True),
                                  poll_interval=0.001, settle_seconds=0.05)
    assert report["status"] == "FAIL"
    detail = _step(report, "silent_uninstall")["detail"]
    assert "the uninstaller is gone" in detail, detail
    assert "install tree holds" in report["uninstall_launch_notes"]


# --- M42.7: the shapes a launch refusal can stand for, told apart by what was sampled --


def _forensics(report: dict, label: str) -> dict:
    block = report["diagnostics"]["uninstall_forensics"]
    assert label in block, f"{label} missing from {sorted(block)}"
    return block[label]


def _lifecycle(tmp_path, host, name="work"):
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / "release")
    return module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                work_root=tmp_path / name, runner=host,
                                poll_interval=0.001, settle_seconds=0.05)


def test_a_removed_install_tree_is_told_apart_from_an_emptied_one(tmp_path):
    """Two failures leave an empty install directory; the sample says which of them it was.

    The Windows gate run on the M42.6 records published "install tree holds 0 file(s): nothing", a
    sentence that fits three events: the directory was taken away, an uninstall really ran and
    removed the uninstaller with it, or the files were never created.  Nothing in the record could
    separate them, so the anomaly could be neither repeated nor dismissed.  The parent directory, the
    work root, the file counts and the uninstaller's own log are now read at the instant of the
    refusal, which is the only moment the distinction is observable.
    """
    taken = _lifecycle(tmp_path, FakeHost(take_away_install_dir_before_launch=True))
    assert taken["status"] == "FAIL" and _step(taken, "silent_uninstall")["status"] == "FAIL"
    sample = _forensics(taken, "after_refusal_1")
    assert sample["install_dir"]["exists"] is False and sample["install_dir"]["is_dir"] is False
    assert sample["parent_dir"]["is_dir"] is True, "only the install tree is gone, not the runner's temp root"
    assert sample["work_root"]["is_dir"] is True
    assert sample["uninstaller"]["exists"] is False and sample["install_dir_entries"]["count"] == 0
    assert sample["uninstall_log"]["exists"] is False, "no completed uninstall is claimed by an absent log"
    assert "dir=absent" in _step(taken, "silent_uninstall")["detail"]

    emptied = _lifecycle(tmp_path, FakeHost(empty_install_dir_on_refusal=True,
                                            uninstall_log_text="Uninstall process started.\n"
                                                               "Uninstall process finished.\n"),
                         name="work2")
    assert emptied["status"] == "FAIL"
    other = _forensics(emptied, "after_refusal_1")
    assert other["install_dir"]["is_dir"] is True, "the directory survives a real uninstall"
    assert other["install_dir_entries"]["count"] == 0 and other["uninstaller"]["exists"] is False
    assert other["uninstall_log"]["exists"] is True and "Uninstall process finished." in other["uninstall_log"]["tail"]
    assert other["sentinel"]["exists"] is True, "user data outside {app} is not evidence of an uninstall"
    assert "dir=present" in _step(emptied, "silent_uninstall")["detail"]
    assert "uninslog=present" in _step(emptied, "silent_uninstall")["detail"]
    assert "uninslog=present" in emptied["uninstall_launch_notes"]
    assert "after a 2 second settle the uninstaller is gone" in emptied["uninstall_launch_notes"]


def test_an_unexplained_refusal_is_recorded_as_unexplained(tmp_path):
    """A refusal with the whole tree intact is its own finding, and it is not attributed to anything.

    This is the shape the two M42.6 gate runs produced.  Everything the step can see says the
    uninstaller is there -- listed, non-zero size, hashable -- and the launch still refuses, so the
    record keeps the observation and says plainly that the cause is outside what an unprivileged
    process can read.  Naming antivirus, a lock, or a race here would be a guess dressed as a result.
    """
    report = _lifecycle(tmp_path, FakeHost(unlaunchable_uninstall_attempts=2))
    assert report["status"] == "FAIL"
    sample = _forensics(report, "after_refusal_1")
    assert sample["install_dir"]["is_dir"] is True and sample["install_dir_entries"]["count"] == 2
    assert sample["uninstaller"]["is_file"] is True and sample["uninstaller"]["size_bytes"] > 0
    assert sample["uninstaller"]["sha256"] == hashlib.sha256(b"uninstaller").hexdigest()
    assert sample["launch_error"]["class"] == "FileNotFoundError" and sample["launch_error"]["errno"] == 2
    assert sample["host_side_evidence"].startswith("host-side evidence is not collected")
    assert "cause" not in sample, "no cause field may be invented"
    detail = _step(report, "silent_uninstall")["detail"]
    assert "settle: the uninstaller is still listed" in detail, detail
    assert "after a 2 second settle the uninstaller is still listed" in report["uninstall_launch_notes"]
    assert "attempt 1:" in _step(report, "silent_uninstall")["detail"]


def test_the_launch_error_codes_come_from_the_exception(tmp_path):
    """errno and winerror are copied, never read off the message, and no retry is invented for them."""
    refusal = PermissionError(5, "Access is denied")
    refusal.winerror = 5
    target = tmp_path / "work" / "install" / "unins000.exe"
    refusal.filename = str(target)
    report = _lifecycle(tmp_path, FakeHost(uninstall_refusal_error=refusal))
    assert report["status"] == "FAIL"
    detail = _step(report, "silent_uninstall")["detail"]
    assert detail.startswith("PermissionError"), detail
    assert "launch=PermissionError (errno=5,winerror=5)" in detail, detail
    sample = _forensics(report, "launch_error_PermissionError")
    assert sample["launch_error"] == {"class": "PermissionError", "errno": 5, "winerror": 5,
                                      "filename": str(target), "filename2": "",
                                      "message": str(refusal)[:300]}
    assert "uninstall_launch_notes" not in report, "a non-retryable refusal must not look like a retry"


def test_the_forensic_sample_is_redacted_like_every_other_diagnostic(tmp_path, secret_in_environment):
    """An uninstaller log can echo an environment value, so its tail passes through the same filter."""
    report = _lifecycle(tmp_path, FakeHost(unlaunchable_uninstall_attempts=2,
                                           uninstall_log_text="Setup found DRILLMASTER_ADMIN_PASSWORD="
                                                              "hunter2-super-secret in the environment.\n"))
    assert _step(report, "installed_smoke")["status"] == "PASS", "the log tail is the only new channel"
    sample = _forensics(report, "after_refusal_1")
    assert "[REDACTED]" in sample["uninstall_log"]["tail"]
    assert "hunter2-super-secret" not in json.dumps(report)


def test_a_transient_lock_is_distinguished_from_a_gone_file_by_the_settled_retry(tmp_path):
    """The settle is a real wait, not a re-listing microsecond later, and the fake can tell.

    A lock or scan that releases is a different event from a deleted uninstaller, and the single
    bounded retry is what separates them.  If the wait were dropped the second launch would be
    instant and the run would fail; the recovery note would still read correctly, so the assertion is
    about the outcome, not the wording.
    """
    report = _lifecycle(tmp_path, FakeHost(uninstaller_lock_clears_after=1.5))
    assert report["status"] == "PASS", _step(report, "silent_uninstall")["detail"]
    assert "was listed but could not be launched" in report["uninstall_launch_recovered"]
    assert "after a 2 second settle the uninstaller is still listed" in report["uninstall_launch_recovered"]
    assert _forensics(report, "after_refusal_1")["launch_error"]["errno"] == 2
    assert _forensics(report, "after_settle")["uninstaller"]["is_file"] is True


def test_a_log_tail_is_bounded_and_says_so(tmp_path):
    """A 16 KB log contributes at most its bounded tail, and the reader is told about the elision.

    `bound` is the only thing keeping a runner-side log from becoming a dump in the published record,
    so the cap is asserted as a value and as behaviour -- including the elision marker, which is what
    distinguishes clipped from complete.
    """
    module = _evidence_module()
    assert module.MAX_FORENSIC_HASH_BYTES == 64 * 1024 * 1024, "the hashing bound is policy, not a default"
    verbose = "".join(f"line {index} of the uninstaller log {'x' * 100}\n" for index in range(400))
    report = _lifecycle(tmp_path, FakeHost(unlaunchable_uninstall_attempts=2, uninstall_log_text=verbose))
    tail = _forensics(report, "after_refusal_1")["uninstall_log"]["tail"]
    assert len(tail) <= 480, len(tail)
    assert "characters elided" in tail
    assert tail.rstrip().endswith("line 399 of the uninstaller log " + "x" * 100), "the last line survives clipping"
    assert "line 394 of" in tail and "line 0 of" not in tail, "the six most recent lines are the sample"


# --- M42.8: the reads behind the diagnostics, and what survives when they fail ---


class _ReadCounter:
    """A handle wrapper that counts the bytes actually fetched, so a claim of bounded reading is checked."""

    def __init__(self, handle, counter):
        self._handle, self._counter = handle, counter

    def read(self, size=-1):
        data = self._handle.read(size)
        self._counter["bytes"] += len(data)
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return self._handle.__exit__(*exc_info)

    def __getattr__(self, name):
        return getattr(self._handle, name)


@pytest.fixture
def read_counter(monkeypatch):
    """Count reads through `Path.open`, which delegates to `io.open` at call time."""
    counter = {"bytes": 0}
    real_open = io.open

    def wrapper(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        return _ReadCounter(handle, counter) if "b" in str(mode) else handle

    monkeypatch.setattr(io, "open", wrapper)
    return counter


class _VisibleOpen:
    """The host's own Windows reader with the step *before an open* handed to the test.

    Everything else stays real: the create, the identity calls, the final path, the close and the stream
    all go to the helper the module bound, so the module's judgement is still what is being tested.  What
    the test gains is the one moment a swap has to happen -- between the caller naming an object and the
    operating system handing one back.
    """

    def __init__(self, api, hook):
        self._api = api
        self._hook = hook

    def open_handle(self, path, *, directory):
        replacement = self._hook(Path(path), directory)
        return self._api.open_handle(path if replacement is None else replacement, directory=directory)

    def __getattr__(self, name):
        return getattr(self._api, name)


def _ride_the_open_the_host_actually_uses(monkeypatch, module, hook) -> str:
    """Install ``hook(path, directory) -> Path | None`` at the open the *running host's* reader makes.

    A file inside a permitted root is not opened the same way on both platforms, and that difference has
    already cost this suite its subject once: POSIX walks the components with ``os.open(..., dir_fd=...)``
    while Windows asks kernel32 for the name through the reader's own ``open_handle``.  A fixture wired
    only to ``os.open`` therefore fired nowhere on Windows -- four tests whose swap never happened, and
    whose assertions then reported *that* instead of the behaviour they exist to pin (the Windows gate
    said so: "the swap has to happen inside the read's own open, or nothing was tested").

    On POSIX this installs nothing and returns the seam the caller's own double rides; on Windows it
    returns the helper the module will call, so a test can say which seam it used rather than assume one.

    The question asked is the *module's* view of the host -- the same `os.name` check its own `_open_binary`
    makes -- not this file's, so a test that hands the module a Windows view of the platform gets the seam
    that view selects.
    """
    if getattr(module.os, "name", os.name) != "nt":
        return "os.open(dir_fd=...)"
    real = module._win32_api()
    assert real is not None, ("this host is Windows but the module reports no kernel32 helper, so the "
                              "reader's own open cannot be intercepted and this test would prove nothing")
    monkeypatch.setattr(module, "_win32_api", lambda: _VisibleOpen(real, hook))
    return "kernel32 CreateFileW via _Win32HandleMetadata.open_handle"


def _failing_open(monkeypatch, module, target: Path, error: OSError, *, after_first: bool = False):
    """Make the open of one specific path fail, which is the only deterministic way to test a race.

    Every seam the module can reach this file through is patched, because there are three ways it reads:
    by name for a read that claims no boundary, through the anchored descriptor walk inside a permitted
    root (where the object is opened component by component relative to the root, never by the full name),
    and on Windows through kernel32, which has no such walk.  Patching only `io.open` would quietly turn a
    rooted assertion into a test of a path production no longer takes -- which is exactly how a
    check-then-use bug could survive its own regression test, and what the gate run showed happening to
    the Windows branch of this fixture.
    """
    real_open, real_os_open = io.open, os.open
    state = {"seen": 0}

    def fires() -> bool:
        state["seen"] += 1
        return not after_first or state["seen"] > 1

    def wrapper(file, mode="r", *args, **kwargs):
        if Path(str(file)) == target and "b" in str(mode) and fires():
            raise error
        return real_open(file, mode, *args, **kwargs)

    def os_wrapper(file, flags, mode=0o777, *args, **kwargs):
        # the anchored walk names the final component with a `dir_fd`; that is the only moment a rooted
        # read touches this file, so it is the only moment the double fires
        if "dir_fd" in kwargs and str(file) == target.name and fires():
            raise error
        return real_os_open(file, flags, mode, *args, **kwargs)

    def windows_hook(path, directory):
        if directory or path.name != target.name or not fires():
            return None
        if isinstance(error, FileNotFoundError):
            # The object goes away here and the operating system is left to report it, so what gets
            # tested is the reader's own classification of the create's status -- the same finding the
            # POSIX seam produces by raising, reached the way this platform reaches it.
            path.unlink(missing_ok=True)
            return None
        raise error

    monkeypatch.setattr(io, "open", wrapper)
    monkeypatch.setattr(os, "open", os_wrapper)
    _ride_the_open_the_host_actually_uses(monkeypatch, module, windows_hook)
    return state


def test_a_short_log_tail_is_complete_and_unchanged(tmp_path):
    """The last-N-lines promise an operator already relies on still holds for ordinary logs."""
    module = _evidence_module()
    log = tmp_path / "uninstall.log"
    log.write_text("first\nsecond\nUninstall process finished.\n", encoding="utf-8")
    observed = module._bounded_tail(log, 2)
    assert observed["state"] == "complete"
    assert observed["tail"] == "second\nUninstall process finished."
    assert observed["lines_returned"] == 2 and observed["dropped_partial_first_line"] is False
    assert observed["size_bytes"] == observed["bytes_read"] + 0 or observed["bytes_read"] == log.stat().st_size


def test_the_tail_read_is_bounded_in_bytes_not_only_in_output(tmp_path, read_counter):
    """Four megabytes of log must not become four megabytes of reading, and the old prefix stays unread.

    A returned string clipped to 400 characters proves nothing about cost: the previous helper read
    the whole file and sliced it afterwards, which is the same thing to a small log and a completely
    different thing to a runner-side log during a failure.  The counter wraps the real reads, so this
    measures bytes fetched, and the content assertions show the window is the *recent* end.
    """
    module = _evidence_module()
    log = tmp_path / "big.log"
    old_prefix = "OLD-PREFIX-never-to-be-published " + ("x" * 200 + "\n") * 20000
    recent = "".join(f"line {index} RECENT-END\n" for index in range(200))
    log.write_text(old_prefix + recent, encoding="utf-8")
    assert log.stat().st_size > module.LOG_TAIL_BYTES * 4
    observed = module._bounded_tail(log, 6)
    assert read_counter["bytes"] <= module.LOG_TAIL_BYTES + 1, read_counter["bytes"]
    assert observed["state"] == "truncated"
    # exactly the window plus the one byte that decides whether its first line is a fragment: `start` is
    # measured from the end, so the read is bounded whether or not the file grows under it, and growth is
    # detected from the same handle rather than by asking for a byte past the end
    assert observed["bytes_read"] == module.LOG_TAIL_BYTES + 1
    assert observed["size_bytes"] == log.stat().st_size
    assert observed["dropped_partial_first_line"] is True
    # "the recent end" has to mean exactly that: compare against the file's real last lines, so a
    # window taken from the wrong side (or one byte short of EOF) cannot pass on a plausible suffix
    assert observed["tail"].splitlines() == log.read_text(encoding="utf-8").splitlines()[-6:], \
        "the published text is not the end of the log"
    assert "OLD-PREFIX-never-to-be-published" not in observed["tail"]
    assert observed["tail"].rstrip().endswith("line 199 RECENT-END")
    assert "older content was not inspected" in observed["reason"]
    published = module._tail(log, 6)
    assert published.startswith("[only the last") and "RECENT-END" in published


def test_a_window_cut_midway_through_a_multibyte_character_still_produces_evidence(tmp_path, read_counter):
    """The bound lands wherever the bytes fall, so the decode policy is load-bearing, not decorative.

    A 512 KiB window measured from the end of a text file full of two-byte characters starts in the
    middle of a character.  `errors="replace"` makes that one U+FFFD in a truncated tail; a strict
    decode would raise, and because this runs while a lifecycle failure is being described the raise
    would have become the finding.
    """
    module = _evidence_module()
    log = tmp_path / "multibyte.log"
    # The cut has to be deterministic, not lucky: the file is sized so the window begins exactly on the
    # continuation byte of a two-byte character, which is the byte a strict decode refuses.  An earlier
    # version of this test wrote 300k repetitions and happened to land on a character boundary, so it
    # passed against a mutation that replaced `errors="replace"` with a raise.
    two_byte = "\u00e9".encode("utf-8")
    assert len(two_byte) == 2
    log.write_bytes(two_byte + b"a" * (module.LOG_TAIL_BYTES - 12) + b"end-of-log\n")
    assert log.stat().st_size - module.LOG_TAIL_BYTES == 1, "the window must start on byte 1 of the file"
    observed = module._bounded_tail(log, 6)
    assert observed["state"] == "truncated"
    assert observed["size_bytes"] == module.LOG_TAIL_BYTES + 1
    # the window is the whole bound, and the one extra byte is the boundary probe, never the log
    assert observed["bytes_read"] == module.LOG_TAIL_BYTES + 1
    assert observed["tail"].startswith("\ufffd"), ("a window cut mid-character is replaced, not raised on and "
                                                   "not quietly dropped")
    assert observed["tail"].endswith("end-of-log"), "the recent end still has to survive the replacement"
    assert read_counter["bytes"] <= module.LOG_TAIL_BYTES + 1
    sample = module._uninstall_forensics(install_dir=tmp_path, work_root=tmp_path, uninstaller=log,
                                         install_log=log, uninstall_log=log, sentinel=None, error=None,
                                         hash_uninstaller=False)
    assert sample.get("state") != "sampler_failed", "the decode policy leaked into a sampler failure"
    assert "read_state" in sample["uninstall_log"], "the tail came back as a structured observation"


def test_a_huge_single_line_log_is_bounded_marked_and_publishable(tmp_path, read_counter):
    """One enormous line is the case where 'take the last N lines' has no line to take."""
    module = _evidence_module()
    log = tmp_path / "one-line.log"
    log.write_text("y" * (3 * 1024 * 1024), encoding="utf-8")
    observed = module._bounded_tail(log, 6)
    assert read_counter["bytes"] <= module.LOG_TAIL_BYTES + 1
    assert observed["state"] == "truncated" and observed["lines_returned"] == 1
    assert len(observed["tail"]) <= module.LOG_TAIL_BYTES
    assert observed["dropped_partial_first_line"] is False, "there is no earlier line to drop here"
    sample = module._uninstall_forensics(install_dir=tmp_path, work_root=tmp_path,
                                         uninstaller=log, install_log=log, uninstall_log=log,
                                         sentinel=None, error=None, hash_uninstaller=False)
    assert len(sample["uninstall_log"]["tail"]) <= 400 + 40, "published text is clipped again, independently"
    assert "only the last" in sample["uninstall_log"]["read_reason"]


def test_a_vanished_log_is_recorded_without_replacing_the_launch_error(tmp_path, monkeypatch):
    """The race the sampler exists to describe can also happen to the sampler itself.

    A log that is present for the existence check and gone by the read used to raise inside the
    failure handler, which would have replaced `WinError 2` with a diagnostic error and lost the
    finding.  Absence is now a state in the record, and the original exception keeps its codes.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "uninstall.log"
    log.write_text("Uninstall process started.\n", encoding="utf-8")
    # the existence check has already happened by the time the sampler opens the file, which is the
    # whole race: the open itself is what reports the file gone
    seen = _failing_open(monkeypatch, module, log, FileNotFoundError(2, "No such file or directory"))
    assert log.is_file() is True
    observed = module._bounded_tail(log, 6)
    assert seen["seen"] == 1, "the read was attempted once, then it was not there"
    assert observed["state"] == "absent"
    assert observed["bytes_read"] == 0 and observed["tail"] == ""
    assert "no such file" in observed["reason"]
    # and a whole sample built while the read fails still publishes, with distinct states per log
    sample = module._uninstall_forensics(install_dir=root / "install", work_root=root,
                                        uninstaller=root / "install" / "unins000.exe",
                                        install_log=root / "install.log", uninstall_log=log,
                                        sentinel=None, error=None, hash_uninstaller=False)
    assert sample["uninstall_log"]["read_state"] == "absent"
    assert sample["install_log"]["read_state"] == "absent"
    assert json.dumps(sample)


def test_an_unreadable_log_is_a_different_fact_from_a_missing_one(tmp_path, monkeypatch):
    """`PermissionError` during the read is classified by code, never transcribed or re-raised."""
    module = _evidence_module()
    log = tmp_path / "uninstall.log"
    log.write_text("secret-bearing content\n", encoding="utf-8")
    _failing_open(monkeypatch, module, log, PermissionError(13, "Permission denied"))
    refused = module._bounded_tail(log, 6)
    assert refused["state"] == "unreadable" and refused["bytes_read"] == 0
    assert "PermissionError" in refused["reason"] and "errno=13" in refused["reason"]
    assert "secret-bearing" not in json.dumps(refused), "text that could not be read is not published"
    assert refused["size_bytes"] is None, "an open that never succeeded cannot know the size, and says so"

    # a handle that opens and then fails mid-read is a different fact: the size is known, the text is
    # not.  A second file is used so the two doubles above do not stack on the same path.
    readable = tmp_path / "readable.log"
    readable.write_text("secret-bearing content\n", encoding="utf-8")
    real_open = io.open

    def open_then_fail(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if Path(str(file)) != readable or "b" not in str(mode):
            return handle

        class _Refusing:
            def __getattr__(self, name):
                return getattr(handle, name)

            def read(self, size=-1):
                raise PermissionError(13, "Permission denied")

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return handle.__exit__(*exc_info)

        return _Refusing()

    monkeypatch.setattr(io, "open", open_then_fail)
    partial = module._bounded_tail(readable, 6)
    # the size is what the handle measured, so the expectation cannot depend on line-endianess: an
    # earlier version hard-coded 23 bytes, which was Linux's LF count and wrong on a CRLF runner
    assert partial["state"] == "unreadable" and partial["size_bytes"] == readable.stat().st_size
    assert partial["bytes_read"] == 0 and partial["tail"] == ""
    assert "PermissionError" in partial["reason"]


def test_a_refusal_that_embeds_a_credential_in_its_message_stays_out_of_the_record(tmp_path, monkeypatch):
    """The reader publishes codes, not prose, because the prose is the host's and the host leaks.

    A Windows path echoed by the OS can carry a bootstrap token or a SAS query string, and this record is
    published in a job annotation; `bound()` clips length, which was never the protection.  The refusal
    therefore travels as class plus `errno`/`winerror`, and the test plants a credential-shaped value in the
    message the exception would have printed and asserts it appears nowhere.
    """
    module = _evidence_module()
    log = tmp_path / "install.log"
    log.write_text("Setup process started.\n", encoding="utf-8")
    token = "Super-Secret-TOKEN-9dbe6357c1c54954"
    _failing_open(monkeypatch, module, log, PermissionError(13, f"blocked by https://user:{token}@host/blob?sig=x"))
    observed = module._bounded_tail(log, 6, permitted_root=None)
    assert observed["state"] == "unreadable" and observed["bytes_read"] == 0
    assert "PermissionError" in observed["reason"] and "errno=13" in observed["reason"]
    published = json.dumps(observed)
    for fragment in (token, "https://", "sig=x", "blocked by"):
        assert fragment not in published, f"{fragment!r} reached the published diagnostic"


def test_an_empty_log_and_a_missing_log_are_told_apart(tmp_path):
    """Four truthfully different states, none of them an empty string standing in for all of them."""
    module = _evidence_module()
    empty, absent = tmp_path / "empty.log", tmp_path / "gone.log"
    empty.write_text("", encoding="utf-8")
    assert module._bounded_tail(empty)["state"] == "empty"
    assert module._bounded_tail(absent)["state"] == "absent"
    assert module._bounded_tail(tmp_path)["state"] == "unreadable", "a directory is not a log"
    assert module._bounded_tail(tmp_path)["reason"] == "not a regular file"
    assert module._bounded_tail(empty)["reason"] == "" and module._bounded_tail(absent)["tail"] == ""
    with pytest.raises(ValueError):
        module._bounded_tail(empty, byte_limit=0)


def test_a_directory_is_reported_as_such_whatever_the_platform_calls_it(tmp_path, monkeypatch):
    """The exact-SHA Windows run found this: the fact is platform-free, the exception name is not.

    On POSIX, opening a directory raises `IsADirectoryError`; the Windows runner answered
    `PermissionError(errno=13)`.  A classification that keys off the exception name therefore publishes a
    different reason for the same file, which is how this defect escaped a green local run.  Here the
    Windows behaviour is *simulated* by making the open itself refuse, so the guarantee is pinned on every
    host rather than asserted only where the platform happens to agree.
    """
    module = _evidence_module()
    directory = tmp_path / "logs"
    directory.mkdir()
    assert module._bounded_tail(directory)["reason"] == "not a regular file", "the POSIX path still works"

    real_open = io.open

    def windows_like(file, mode="r", *args, **kwargs):
        if Path(str(file)) == directory:
            raise PermissionError(13, "Permission denied")  # what the Windows runner really raises
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(io, "open", windows_like)
    observed = module._bounded_tail(directory, 6)
    assert observed["state"] == "unreadable"
    assert observed["reason"] == "not a regular file", (
        "a directory must be classified by what it is, not by the exception name the platform picked")
    assert observed["bytes_read"] == 0 and observed["tail"] == ""
    assert json.dumps(observed)


def test_a_log_that_grows_while_it_is_being_read_still_returns_the_recent_end(tmp_path, monkeypatch):
    """The size and the window come from one handle, so concurrent appends cannot crash or lie."""
    module = _evidence_module()
    log = tmp_path / "growing.log"
    log.write_text("old line\n", encoding="utf-8")
    real_open = io.open
    grown = {"done": False}

    def wrapper(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if Path(str(file)) != log or "b" not in str(mode):
            return handle

        class _Grower:
            def seek(self, offset, whence=0):
                result = handle.seek(offset, whence)
                if not grown["done"] and whence == os.SEEK_END:
                    grown["done"] = True
                    with real_open(log, "a", encoding="utf-8") as append:
                        append.write("appended-newest-line\n")
                return result

            def read(self, size=-1):
                return handle.read(size)

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return handle.__exit__(*exc_info)

            def __getattr__(self, name):
                return getattr(handle, name)

        return _Grower()

    monkeypatch.setattr(io, "open", wrapper)
    observed = module._bounded_tail(log, 6)
    assert observed["state"] in {"truncated", "complete"}
    assert observed["tail"].rstrip().endswith("appended-newest-line"), observed["tail"]
    assert observed["size_bytes"] < log.stat().st_size, "the recorded size is the one the read was measured against"

def test_a_read_that_lands_past_the_window_keeps_the_newest_bytes(tmp_path, monkeypatch):
    """The clip direction is proven, not assumed: one extra byte has to cost the oldest byte, not the newest.

    `data[:byte_limit]` and `data[-byte_limit:]` are the same thing whenever the read returned exactly
    the window, which is why an earlier version of this test could not tell them apart.  A log that
    grew between the size check and the read is the only case where they differ, so the handle here is
    made to return one byte more than the window, front and back marked.  Dropping the newest byte of
    a log that is still being written is the wrong way round for a failure being described.
    """
    module = _evidence_module()
    log = tmp_path / "overflow.log"
    log.write_bytes(b"filler line\n" * (module.LOG_TAIL_BYTES // 12 + 1))
    size = log.stat().st_size
    assert size > module.LOG_TAIL_BYTES
    real_open = io.open

    class _Overflow:
        """A handle whose read returns `byte_limit + 1` bytes: one byte appeared after `tell()`."""

        def __init__(self, handle):
            self._handle = handle

        def seek(self, offset, whence=0):
            if whence == os.SEEK_END:
                return size + 1
            return None

        def tell(self):
            return size + 1

        def read(self, count=-1):
            return b"Q" + b"y" * (module.LOG_TAIL_BYTES - 1) + b"Z"

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    def wrapper(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if Path(str(file)) != log or "b" not in str(mode):
            return handle
        return _Overflow(handle)

    monkeypatch.setattr(io, "open", wrapper)
    observed = module._bounded_tail(log, 6)
    assert observed["state"] == "truncated"
    assert observed["size_bytes"] == size + 1
    assert observed["bytes_read"] == module.LOG_TAIL_BYTES + 1, ("the reported read is the read actually performed, "
                                                                "including the one byte that probes for growth")
    assert observed["tail"].endswith("Z"), "the newest byte was thrown away instead of the oldest"
    assert not observed["tail"].startswith("Q"), "the window starts on the wrong side"
    assert observed["reason"] == (f"only the last {module.LOG_TAIL_BYTES} of {size + 1} bytes were read; "
                                  "older content was not inspected")



def test_a_path_leaving_the_evidence_root_is_never_read(tmp_path, read_counter):
    """The boundary is a rule about the resolved target, because a log name is attacker-visible.

    The portable half proves the check itself with an ordinary outside file; the symlink half proves
    that a name *inside* the root which resolves outside it is caught the same way.  Where a host
    forbids unprivileged symlink creation the second half skips, and only the first half is claimed.
    """
    module = _evidence_module()
    root, outside = tmp_path / "work", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    secret = outside / "host-file.log"
    secret.write_text("DO-NOT-PUBLISH outside content\n", encoding="utf-8")
    observed = module._bounded_tail(secret, 6, permitted_root=root)
    assert observed["state"] == "skipped_unsafe_path" and observed["bytes_read"] == 0
    assert "outside the permitted evidence root" in observed["reason"]
    assert "DO-NOT-PUBLISH" not in json.dumps(observed)
    assert read_counter["bytes"] == 0, "a skipped path must not be opened at all"

    link = root / "uninstall.log"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):  # pragma: no cover - platform privilege, not a code path
        pytest.skip("this host does not allow unprivileged symlink creation; the portable case above ran")
    replaced = module._bounded_tail(link, 6, permitted_root=root)
    assert replaced["state"] == "skipped_unsafe_path" and replaced["tail"] == ""
    assert read_counter["bytes"] == 0
    # an in-boundary log is still read normally, so the check is a boundary and not a blanket refusal
    inside = root / "install.log"
    inside.write_text("Setup process started.\n", encoding="utf-8")
    assert module._bounded_tail(inside, 6, permitted_root=root)["state"] == "complete"

    # The same boundary must hold where it is expensive.  Hashing is the one read the forensics do on
    # the install tree itself, and a symlinked uninstaller is exactly how an outside file would be
    # dragged into it, so the refusal has to be proven behaviourally, not only by its reason string.
    exe = root / "unins000.exe"
    try:
        exe.symlink_to(secret)
    except (OSError, NotImplementedError):  # pragma: no cover - platform privilege, not a code path
        pytest.skip("this host does not allow unprivileged symlink creation")
    sample = module._uninstall_forensics(install_dir=root, uninstaller=exe, work_root=root,
                                         install_log=inside, uninstall_log=inside, sentinel=None,
                                         error=None)
    assert sample["uninstaller"]["is_file"] is True, "the link resolves, which is why it must not be trusted"
    assert sample["uninstaller"]["hash_state"] == "skipped_unsafe_path"
    assert "resolves outside the permitted evidence root; not hashed" in sample["uninstaller"]["hash_reason"]
    assert "sha256" not in sample["uninstaller"], "a path outside the evidence root must never be digested"
    assert "DO-NOT-PUBLISH" not in json.dumps(sample)


def test_the_entry_count_and_the_names_come_from_one_snapshot(tmp_path, monkeypatch):
    """One sample must not describe two filesystem moments as if they were one."""
    module = _evidence_module()
    calls = {"n": 0}

    def counting_snapshot(directory):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"a.txt": 1, "b.txt": 2}
        return {"a.txt": 1}

    monkeypatch.setattr(module, "snapshot", counting_snapshot)
    sample = module._uninstall_forensics(install_dir=tmp_path / "install", work_root=tmp_path,
                                         uninstaller=tmp_path / "unins000.exe",
                                         install_log=tmp_path / "i.log", uninstall_log=tmp_path / "u.log",
                                         sentinel=None, error=None, hash_uninstaller=False)
    assert calls["n"] == 1, "the sample took two listings and published them as one"
    assert sample["install_dir_entries"] == {"count": 2, "first": ["a.txt", "b.txt"]}
    assert sample["install_dir_entries"]["count"] == len(sample["install_dir_entries"]["first"])


def test_a_sampler_defect_is_visible_and_still_does_not_replace_the_failure(tmp_path, monkeypatch):
    """A diagnostic that crashes says so, and the lifecycle result underneath it survives."""
    module = _evidence_module()
    installer, _, digest = _release(tmp_path / "release")

    def broken(*args, **kwargs):
        raise RuntimeError("harness: sampler bug")

    monkeypatch.setattr(module, "_uninstall_forensics", broken)
    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work",
                                  runner=FakeHost(unlaunchable_uninstall_attempts=2),
                                  poll_interval=0.001, settle_seconds=0.05)
    assert report["status"] == "FAIL", "a broken sampler may not turn a failure into a pass"
    block = report["diagnostics"]["uninstall_forensics"]
    assert block["after_refusal_1"]["state"] == "sampler_failed"
    assert "RuntimeError" in block["after_refusal_1"]["reason"]
    assert "diagnostics unavailable" in _step(report, "silent_uninstall")["detail"]
    assert "attempt 1:" in _step(report, "silent_uninstall")["detail"]
    assert "install_files_removed" not in [step["name"] for step in report["steps"]]


def test_a_secret_in_an_error_path_is_redacted_like_a_secret_in_a_log(tmp_path, monkeypatch, secret_in_environment):
    """Both text channels a diagnostic can carry - log tail and error description - pass the filter."""
    module = _evidence_module()
    secret = "hunter2-super-secret"
    installer, _, digest = _release(tmp_path / "release")
    refusal = FileNotFoundError(2, "The system cannot find the file specified")
    refusal.filename = str(tmp_path / secret / "unins000.exe")
    report = module.run_lifecycle(installer=installer, expected_sha256=digest, app_version="1.0.0",
                                  work_root=tmp_path / "work",
                                  runner=FakeHost(uninstall_refusal_error=refusal,
                                                 uninstall_log_text=f"Setup used {secret} from the environment.\n"),
                                  poll_interval=0.001, settle_seconds=0.05)
    serialised = json.dumps(report)
    assert secret not in serialised, "a credential reached the published record"
    sample = report["diagnostics"]["uninstall_forensics"]["after_refusal_1"]
    assert "[REDACTED]" in sample["uninstall_log"]["tail"]
    assert "[REDACTED]" in sample["launch_error"]["filename"]


def test_a_passing_lifecycle_reports_its_own_read_state_and_cleans_up(tmp_path):
    """The boundary work is visible on green runs too, and cleanup is unchanged."""
    report = _lifecycle(tmp_path, FakeHost())
    assert report["status"] == "PASS"
    assert report["diagnostics"]["smoke_log_read_state"] == "complete"
    assert report["diagnostics"]["smoke_log_bytes_read"] > 0
    assert report["cleaned_up"] is True and not (tmp_path / "work").exists()
    uninstall_sample = _forensics(report, "pre_launch")
    assert uninstall_sample["uninstall_log"]["read_state"] == "absent"
    assert uninstall_sample["install_log"]["read_state"] == "complete"
    assert uninstall_sample["install_log"]["bytes_read"] == uninstall_sample["install_log"]["size_bytes"] > 0, (
        "the sample has to carry the measured read itself, not only the state word it came from")
    assert uninstall_sample["uninstaller"]["hash_state"] == "hashed"


def test_a_sentinel_swapped_for_an_outside_link_does_not_certify_user_data(tmp_path, monkeypatch):
    """The one read that can turn a FAIL into a PASS carries the same anchor as the logs.

    The sentinel exists because "the exit code was 0" is not proof that user data outside `{app}` survived;
    if its *name* can be re-pointed at a file holding the expected text, that proof becomes a statement
    about somebody else's file.  The swap is performed inside the lifecycle's own open, so the run sees a
    link where it expected a file: the step fails, the refusal is recorded as the reason, and the outside
    content is never consumed.
    """
    real_os_open = os.open
    outside = tmp_path / "attacker-held.txt"
    outside.write_text("DRILLMASTER-LIFECYCLE-SENTINEL-PRESERVE\n", encoding="utf-8")
    state = {"swapped": 0}

    def swap_once():
        state["swapped"] += 1
        target = tmp_path / "work" / "userdata" / "sentinel-preserve.txt"
        target.unlink(missing_ok=True)
        target.symlink_to(outside)

    def os_wrapper(file, flags, mode=0o777, *args, **kwargs):
        if "dir_fd" in kwargs and str(file) == "sentinel-preserve.txt" and not state["swapped"]:
            swap_once()
        return real_os_open(file, flags, mode, *args, **kwargs)

    def windows_hook(path, directory):
        # The same swap, reached through the open this host's reader performs: on Windows there is no
        # descriptor walk for `os.open` to intercept, and a fixture wired only to that seam left this
        # test asserting a swap that had not happened ("the lifecycle never reached the sentinel read it
        # was supposed to anchor" -- the Windows gate's own words).
        if not directory and path.name == "sentinel-preserve.txt" and not state["swapped"]:
            swap_once()
        return None

    monkeypatch.setattr(os, "open", os_wrapper)
    module = _evidence_module()
    _ride_the_open_the_host_actually_uses(monkeypatch, module, windows_hook)
    _, report = _run(tmp_path, FakeHost(), module=module)
    assert state["swapped"] == 1, "the lifecycle never reached the sentinel read it was supposed to anchor"
    assert report["status"] == "FAIL"
    step = _step(report, "user_data_preserved")
    assert step["status"] == "FAIL" and "sentinel read refused" in step["detail"]
    assert report["diagnostics"]["sentinel_read_state"] == "refused"
    published = json.dumps(report)
    assert "DRILLMASTER-LIFECYCLE-SENTINEL-PRESERVE" not in published, "the linked file's content leaked"
    assert outside.read_text(encoding="utf-8") == "DRILLMASTER-LIFECYCLE-SENTINEL-PRESERVE\n"
    assert not (tmp_path / "work").exists(), "the refusal must not leave the work root behind"
    assert module is not None  # the run still produced a structured report


def test_a_green_lifecycle_records_one_baseline_sample_and_still_cleans_up(tmp_path):
    """The extra observation costs a passing run nothing, and the work root is still removed."""
    report = _lifecycle(tmp_path, FakeHost())
    assert report["status"] == "PASS"
    block = report["diagnostics"]["uninstall_forensics"]
    assert list(block) == ["pre_launch"], block
    assert block["pre_launch"]["uninstaller"]["sha256"] == hashlib.sha256(b"uninstaller").hexdigest()
    assert block["pre_launch"]["install_dir"]["is_dir"] is True
    assert not (tmp_path / "work").exists(), "evidence is captured before the work root is deleted"

    def leaves(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from leaves(item)
        elif isinstance(value, list):
            for item in value:
                yield from leaves(item)
        else:
            yield value

    assert all(len(item) <= 400 for item in leaves(block) if isinstance(item, str))
    json.dumps(block)  # publishable: no live paths or handles in the record


@pytest.mark.parametrize("raw, expected, recognized", [
    ("Valid", "PASS", True),
    ("valid", "PASS", True),
    ("OK", "PASS", True),
    ("NotSigned", "UNSIGNED", True),
    ("NOTSIGNED", "UNSIGNED", True),
    ("HashMismatch", "FAIL", True),
    ("NotTrusted", "FAIL", True),
    ("NottrustedForData", "FAIL", True),
    ("Unknown", "UNKNOWN", True),
    ("UnknownError", "UNKNOWN", True),
    # An answer with no rule stays unknown: it is not evidence of a broken signature, and it is
    # not evidence of a deliberately unsigned build either.
    ("nonsense", "UNKNOWN", False),
    ("", "UNKNOWN", False),
])
def test_every_windows_answer_maps_through_one_rule(tmp_path, raw, expected, recognized):
    """Casing and vocabulary differences must never decide whether a run reads as FAIL."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    host = FakeHost(signature_status=raw,
                    signature_message="" if expected != "UNSIGNED" else "No signature is present.")
    report = module.run_signing(release_metadata_path=metadata, runner=host)
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert rows, "the installer and the packaged executable must both be examined"
    assert [item["status"] for item in rows] == [expected, expected]
    assert [item["raw_status"] for item in rows] == [raw, raw]
    assert all(item["raw_status_recognized"] is recognized for item in rows)
    if expected != "PASS":
        # a clean verdict needs no explanation; every other state must carry one
        assert all(item["status_message"] for item in rows)
    assert report["status"] == (expected if expected != "PASS" else "PASS")


def test_the_published_mapping_covers_every_documented_signature_status():
    """A new Windows status must be given a rule, not discovered as a gate surprise later."""
    release_meta = _release_metadata_module()
    for spelling in release_meta.AUTHENTICODE_RAW_STATUSES:
        assert spelling.lower() in release_meta.AUTHENTICODE_TO_FILE_STATUS, spelling


def test_an_empty_answer_is_published_with_the_stderr_that_explains_it(tmp_path):
    """The exact shape that made the shipped run unattributable: exit 0, parseable, no Status."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    host = FakeHost(signature_status="",
                    signature_stderr="Get-AuthenticodeSignature : The trust provider verified, but "
                                     "did not sign, this file.")
    report = module.run_signing(release_metadata_path=metadata, runner=host)
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert [item["status"] for item in rows] == ["UNKNOWN", "UNKNOWN"]
    assert report["status"] == "UNKNOWN"
    for item in rows:
        assert "trust provider" in item["status_message"], item["status_message"]


def test_an_empty_answer_from_a_quiet_host_still_names_the_missing_field(tmp_path):
    """Exit 0 plus a parseable payload is not an answer when the requested field is absent.

    This is the shape of the first shipped run: no stderr at all, an empty Status, exit code zero.
    Only the required-field rule makes that attributable, so it is pinned here separately from the
    stderr path -- otherwise the guard could be deleted and the run would still look explained.
    """
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost(signature_status=""))
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert rows and all(item["status"] == "UNKNOWN" for item in rows)
    for item in rows:
        assert "without reporting Status" in item["status_message"], item["status_message"]
        assert "exit code 0" in item["status_message"]
        assert item["raw_status_recognized"] is False
    assert report["status"] == "UNKNOWN"
    module.validate_signing_document(report)


def test_a_child_killed_mid_query_is_attributed_not_lost(tmp_path):
    """A harness-level subprocess failure is a cause in the record, not a traceback."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")

    def host(argv, environment, cwd, timeout):
        raise subprocess.SubprocessError("child process died before its output was collected")

    report = module.run_signing(release_metadata_path=metadata, runner=host)
    assert report["status"] == "UNKNOWN"
    assert "powershell invocation failed" in report["harness"]["probe_error"]
    assert "SubprocessError" in report["harness"]["probe_error"]
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert rows and all("invocation failed" in item["status_message"] for item in rows)
    module.validate_signing_document(report)


def test_a_statement_level_query_failure_reports_itself(tmp_path, capsys, monkeypatch):
    """A cmdlet error inside the script is now a cause in the record, not a silent empty field."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    host = FakeHost(signature_error="Cannot bind to the certificate store")
    report = module.run_signing(release_metadata_path=metadata, runner=host)
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert all(item["status"] == "UNKNOWN" for item in rows)
    assert all("Cannot bind to the certificate store" in item["status_message"] for item in rows)
    assert all(item["raw_status"] == "" for item in rows)
    assert report["status"] == "UNKNOWN"
    # the finding is published, and the gate still exits cleanly on it, per the recorded policy
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "default_runner", host)
    json_out = tmp_path / "signing-status.json"
    assert module.main(["signing", "--release-metadata", str(metadata), "--json-out", str(json_out)]) == 0
    written = json.loads(json_out.read_text(encoding="utf-8"))
    assert written["status"] == "UNKNOWN"
    assert "Cannot bind to the certificate store" in written["files"][0]["status_message"]


def test_report_only_absence_states_are_never_signature_states(tmp_path):
    """NOT_VERIFIED means "there is no record"; it may never be a status Windows is said to have given."""
    release_meta = _release_metadata_module()
    assert not release_meta.SIGNING_STATUS_VOCABULARY & release_meta.SIGNING_ABSENCE_VOCABULARY
    assert not release_meta.SIGNING_FILE_VOCABULARY & release_meta.SIGNING_ABSENCE_VOCABULARY
    _, metadata, _ = _release(tmp_path / "release")
    document = _evidence_module().run_signing(release_metadata_path=metadata, runner=FakeHost())
    for mutation in ({"status": "NOT_VERIFIED"},
                     {"files": [dict(document["files"][0], status="NOT_VERIFIED"),
                                dict(document["files"][1], status="NOT_VERIFIED"), document["files"][2]],
                      "status": "UNKNOWN"}):
        import copy
        tampered = copy.deepcopy(document)
        tampered.update(mutation)
        with pytest.raises(ValueError, match="outside the"):
            release_meta.validate_signing_document(tampered)


def test_nothing_examined_is_unknown_and_never_a_verdict(tmp_path):
    """An empty examined set is an absence of evidence, not an implicit pass or implicit failure."""
    module = _evidence_module()
    release_meta = _release_metadata_module()
    assert module.aggregate_signing_status([]) == "UNKNOWN"
    assert release_meta.aggregate_signing_status(
        [{"status": release_meta.SIGNING_NOT_APPLICABLE}]) == "UNKNOWN"
    # one unknown among determinate answers keeps the unknown visible
    assert module.aggregate_signing_status([{"status": "PASS"}, {"status": "UNKNOWN"}]) == "UNKNOWN"
    assert module.aggregate_signing_status([{"status": "PASS"}, {"status": "FAIL"}]) == "FAIL"


def test_published_diagnostics_never_carry_a_credential_value(tmp_path, monkeypatch):
    """A captured stderr is only safe if the signing secret values are removed from it first."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    secret = "sup3r-signing-passphrase"
    monkeypatch.setenv("DRILLMASTER_SIGN_PFX_PASSWORD", secret)
    host = FakeHost(signature_status="",
                    signature_stderr=f"Get-AuthenticodeSignature : bad password {secret} for the PFX")
    report = module.run_signing(release_metadata_path=metadata, runner=host)
    text = json.dumps(report, sort_keys=True)
    assert secret not in text, "a signing credential value must not reach the published record"
    assert "[REDACTED]" in text
    assert "DRILLMASTER_SIGN_PFX_PASSWORD" in report["credential_environment_variables"], (
        "the variable name stays auditable even though its value is removed"
    )


def test_the_query_capability_is_published_alongside_the_verdict(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    assert report["harness"] == {"query_command": "available", "cmdlet_available": True,
                                "powershell_version": "5.1.20348.2402",
                                "signature_command_module": "Microsoft.PowerShell.Security",
                                "security_module_import": "succeeded", "probe_usable": True,
                                "probe_exit_code": 0}


def test_a_host_without_the_cmdlet_records_one_cause_for_every_file(tmp_path, monkeypatch):
    """"The cmdlet is missing" is a fact about the host, so it is stated once, per file."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    host = FakeHost(signature_cmdlet="missing")
    report = module.run_signing(release_metadata_path=metadata, runner=host)
    assert report["harness"]["query_command"] == "missing"
    rows = [item for item in report["files"] if item["signature_bearing"]]
    assert all(item["status"] == "UNKNOWN" for item in rows)
    assert all("not available in this PowerShell host" in item["status_message"] for item in rows)
    assert all("imported successfully, and Get-Command still did not resolve" in item["status_message"]
               for item in rows), ("the cmdlet was reported missing while the import reported success, "
                                  "so the reason must say exactly that and nothing more")
    assert report["harness"]["security_module_import"] == "succeeded"
    assert report["harness"]["cmdlet_available"] is False
    assert report["status"] == "UNKNOWN"
    # the probe is a diagnostic, not an authority: the files are still described, not skipped
    assert [item["raw_status"] for item in rows] == ["", ""]


def test_a_failing_probe_does_not_suppress_the_real_queries(tmp_path):
    """A diagnostic that itself broke must not turn a determinable answer into an unknown."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost(signature_cmdlet="probe-fails"))
    assert report["status"] == "UNSIGNED"
    assert report["harness"]["query_command"] == "unknown"
    assert "probe unsupported" in report["harness"]["probe_error"]


def test_the_record_is_bound_to_the_manifest_bytes_it_was_derived_from(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    assert report["schema"] == module.SIGNING_STATUS_SCHEMA
    assert report["release_metadata_sha256"] == module.sha256_file(metadata)
    assert report["source_sha"] == json.loads(metadata.read_text(encoding="utf-8"))["git_sha"]
    # the document the tool writes is the document the contract accepts
    release_meta = _release_metadata_module()
    assert release_meta.validate_signing_document(report)["status"] == "UNSIGNED"


def test_a_self_inconsistent_document_is_refused_before_it_is_written(tmp_path, monkeypatch):
    """The generator validates what it computed, not only what it looked up.

    A per-file status inside the vocabulary that the aggregate misrepresents passes every local
    check except the shared contract, so this is the case that proves the writer's self-validation
    is not decoration.
    """
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    monkeypatch.setattr(module, "aggregate_signing_status", lambda files: "PASS")
    with pytest.raises(ValueError, match="contradicts the per-file findings"):
        module.run_signing(release_metadata_path=metadata, runner=FakeHost())


def test_a_record_that_violates_its_own_contract_is_never_published(tmp_path, monkeypatch, capsys):
    """The writer is held to the shared contract, so a malformed record fails at the source.

    The alternative was to write a document the acceptance step would refuse minutes later, which
    is how a stale schema and a contradicted aggregate used to travel as far as the report.
    """
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "default_runner", FakeHost())
    contradictions = [
        {"schema": "drillmaster-signing-status/v1"},
        {"status": "PASS", "files": [], "examined_count": 0, "archive_count": 0},
        {"somebody": "else"},
    ]
    for change in contradictions:
        stale = {"schema": "drillmaster-signing-status/v2", "method": "Windows Get-AuthenticodeSignature",
                 "status": "UNSIGNED", "policy": module.SIGNING_POLICY, "files": [], "examined_count": 0,
                 "archive_count": 0, "signing_configured_in_build": False, "credentials_available": False,
                 "release_metadata_sha256": "a" * 64, "source_sha": "b" * 40}
        stale.update(change)
        document = stale
        # late binding is intended: main() runs inside this iteration, before document changes
        monkeypatch.setattr(module, "run_signing", lambda **kwargs: document)
        json_out = tmp_path / "signing-status.json"
        if json_out.exists():
            json_out.unlink()
        assert module.main(["signing", "--release-metadata", str(metadata),
                            "--json-out", str(json_out)]) == 1
        assert "signing record violates drillmaster-signing-status/v2" in capsys.readouterr().err
        assert not json_out.exists(), "a refused record must not be uploaded as evidence"


def test_a_non_windows_host_still_publishes_a_contract_valid_record(tmp_path, monkeypatch):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    monkeypatch.setattr(module.sys, "platform", "linux")
    json_out = tmp_path / "signing-status.json"
    assert module.main(["signing", "--release-metadata", str(metadata), "--json-out", str(json_out)]) == 0
    report = json.loads(json_out.read_text(encoding="utf-8"))
    assert report["status"] == "NOT_RUN"
    assert report["schema"] == module.SIGNING_STATUS_SCHEMA
    assert report["files"] == [] and report["examined_count"] == 0
    assert "Windows host" in report["reason"]
    assert _release_metadata_module().validate_signing_document(report)["status"] == "NOT_RUN"


def test_the_console_summary_carries_the_reason_for_a_non_pass_state(tmp_path, monkeypatch, capsys):
    """Job-log output is the only evidence a reviewer can read without artifact access."""
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    host = FakeHost(signature_error="The system cannot find the file specified")
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "default_runner", host)
    assert module.main(["signing", "--release-metadata", str(metadata),
                        "--json-out", str(tmp_path / "signing-status.json")]) == 0
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed["status"] == "UNKNOWN"
    assert printed["harness"]["query_command"] == "available"
    assert all("cannot find the file specified" in item["reason"] for item in printed["files"]
               if item["status"] == "UNKNOWN")
    assert printed["files"][0]["raw_status"] == ""


@pytest.mark.parametrize("spelling, expected, recognized", [
    ("   ", "UNKNOWN", False),
    ("NotSigned   ", "UNSIGNED", True),
    ("  valid", "PASS", True),
    (None, "UNKNOWN", False),
    (17, "UNKNOWN", False),
])
def test_a_raw_status_is_read_after_padding_and_case_only(spelling, expected, recognized):
    """Windows pads and capitalizes; nothing else may change the mapping, and a non-string answer
    is not evidence of anything."""
    release_meta = _release_metadata_module()
    assert release_meta.normalize_authenticode_status(spelling) == (expected, recognized)


@pytest.mark.parametrize("mutation, fragment", [
    (lambda d: d.update(signing_configured_in_build="yes"), "must be a boolean"),
    (lambda d: d.update(credentials_available=None), "must be a boolean"),
    (lambda d: d.update(examined_count=-1), "non-negative integer"),
    (lambda d: d.update(examined_count=True), "non-negative integer"),
    (lambda d: d.update(archive_count=1.5), "non-negative integer"),
    (lambda d: d.update(source_sha="a" * 39), "full source SHA"),
    (lambda d: d.update(source_sha="A" * 40), "full source SHA"),
    (lambda d: d.update(release_metadata_sha256="B" * 64), "SHA-256 of the manifest"),
    (lambda d: d.update(files=[]), "at least one published file"),
    (lambda d: d["files"][0].update(filename="sub/DrillMaster.exe"), "bare file name"),
    (lambda d: d["files"][0].update(filename=""), "bare file name"),
    (lambda d: d["files"][0].update(size_bytes=-5), "negative or non-integer size_bytes"),
    (lambda d: d["files"][0].update(size_bytes="2048"), "negative or non-integer size_bytes"),
    (lambda d: d["files"][0].update(signature_bearing="true"), "signature_bearing as a boolean"),
    (lambda d: d["files"][0].update(status=None), "outside the per-file vocabulary"),
    (lambda d: d["files"][0].update(sha256=None), "malformed SHA-256"),
    (lambda d: d["files"][0].update(unreported_field=1), "unknown field"),
    (lambda d: d["files"][0].update(status="UNKNOWN", status_message="   "), "UNKNOWN without a reason"),
    (lambda d: d["files"][1].update(container_member="Other.exe"), "which is a different file"),
    (lambda d: d["files"][1].update(container_archive_sha256="C" * 64), "malformed container digest"),
    (lambda d: d["files"][1].update(container_archive=""), "incomplete container provenance"),
    (lambda d: d.update(policy=1), None),
])
def test_the_validator_refuses_every_shape_of_record_the_contract_forbids(tmp_path, mutation, fragment):
    """Type, count, naming and provenance guards are contract clauses, not decoration.

    These are the refusals a hand-edited or truncated record would hit.  The last case records
    the deliberate limit of the contract: a top-level field outside the vocabulary (here ``policy``,
    which is free text) is not type-checked, because the schema's job is the statuses, digests,
    counts and bindings a gate acts on -- and that boundary is a decision, not an oversight.
    """
    import copy

    module = _evidence_module()
    release_meta = _release_metadata_module()
    _, metadata, _ = _release(tmp_path / "release")
    document = module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    release_meta.validate_signing_document(document)  # the fixture itself is valid
    tampered = copy.deepcopy(document)
    mutation(tampered)
    if fragment is None:
        assert release_meta.validate_signing_document(tampered)["policy"] == 1
        return
    with pytest.raises(ValueError, match=fragment):
        release_meta.validate_signing_document(tampered)


@pytest.mark.parametrize("mutation, fragment", [
    (lambda d: d.update(files=[d["files"][0]], examined_count=0), "cannot also carry per-file findings"),
    (lambda d: d.update(examined_count=1), "zero examined_count"),
    (lambda d: d.update(archive_count=3), "zero archive_count"),
    (lambda d: d.update(reason=""), "must carry a bounded reason"),
    (lambda d: d.update(reason="x" * 700), "exceeded the bound"),
    (lambda d: d.update(signing_configured_in_build="no"), "must be a boolean"),
])
def test_a_not_run_record_stays_degenerate(tmp_path, mutation, fragment):
    """"Windows never ran" is allowed to be thin, but it is not allowed to be slippery."""
    import copy

    module = _evidence_module()
    release_meta = _release_metadata_module()
    _, metadata, _ = _release(tmp_path / "release")
    document = module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    base = copy.deepcopy(document)
    base.update({"status": "NOT_RUN", "files": [], "examined_count": 0, "archive_count": 0,
                 "reason": "Authenticode verification requires a Windows host"})
    base.pop("release_metadata_sha256", None)
    base.pop("source_sha", None)
    release_meta.validate_signing_document(base)

    def with_row(row):
        def mutate(payload):
            payload["files"] = [copy.deepcopy(row)]
        return mutate

    if fragment == "cannot also carry per-file findings":
        mutation = with_row(document["files"][0])
    tampered = copy.deepcopy(base)
    mutation(tampered)
    with pytest.raises(ValueError, match=fragment):
        release_meta.validate_signing_document(tampered)


# --- M42.9: handle-anchored confinement, a ceiling that cannot be raised, boundary truth ----------------


def _swapping_open(monkeypatch, module, target: Path, replacement: Path):
    """Re-point `target` at `replacement` at the exact moment the reader tries to open it.

    No sleeps and no threads: the swap is performed by the test double, inside the open call itself, so the
    window between "the name was checked" and "the object was opened" is opened on demand.  Every seam the
    reader can open this file through is hooked, for the reason :func:`_ride_the_open_the_host_actually_uses`
    gives: POSIX opens the final component relative to the root's descriptor, Windows asks kernel32 for the
    name -- and a fixture wired to only one of them fires nowhere on the other platform, which leaves the
    assertions below reporting that the swap never happened instead of what the reader did about it.

    The returned dict counts swaps and, separately, every attempt to open `replacement` by name, so "the
    outside file was never touched" is a measurement rather than an inference from a reason string.
    """
    real_io_open, real_os_open = io.open, os.open
    state = {"swapped": 0, "outside_opens": 0}

    def swap_once():
        if state["swapped"]:
            return
        state["swapped"] += 1
        target.unlink()
        target.symlink_to(replacement)

    def io_wrapper(file, mode="r", *args, **kwargs):
        name = Path(str(file))
        if "b" in str(mode):
            if name == target:
                swap_once()
            elif name == replacement:
                state["outside_opens"] += 1
        return real_io_open(file, mode, *args, **kwargs)

    def os_wrapper(file, flags, mode=0o777, *args, **kwargs):
        if "dir_fd" in kwargs and str(file) == target.name:
            swap_once()
        elif str(file) == replacement.name:
            state["outside_opens"] += 1
        return real_os_open(file, flags, mode, *args, **kwargs)

    def windows_hook(path, directory):
        # The name is re-pointed with a real symbolic link even here: the Windows reader opens the name it
        # was given once and judges the handle afterwards, so a link planted at this instant is exactly the
        # object it must refuse -- and refusing it is what the test then requires it to have done.
        if not directory and path.name == target.name:
            swap_once()
        elif path.name == replacement.name:
            state["outside_opens"] += 1
        return None

    monkeypatch.setattr(io, "open", io_wrapper)
    monkeypatch.setattr(os, "open", os_wrapper)
    _ride_the_open_the_host_actually_uses(monkeypatch, module, windows_hook)
    return state


def test_a_log_replaced_between_the_check_and_the_open_is_never_consumed(tmp_path, monkeypatch, read_counter):
    """The reproduction the M42.8 test suite did not contain: the swap happens *during* the open.

    The earlier guarantee was "we resolve the name, and if it points outside we do not open it", which is a
    statement about a moment that has already passed by the time the read happens.  Here the file is a normal
    in-root log while it is checked and becomes a link to an outside sentinel before it is opened.  A reader
    that trusts the check consumes the sentinel; a reader that trusts the handle refuses, and the refusal is
    what this asserts -- including that the outside bytes were never read by anybody.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "install.log"
    log.write_text("IN-ROOT setup line\n", encoding="utf-8")
    sentinel = tmp_path / "host-secret.log"
    sentinel.write_text("DO-NOT-PUBLISH outside credential content\n", encoding="utf-8")
    swap = _swapping_open(monkeypatch, module, log, sentinel)

    observed = module._bounded_tail(log, 6, permitted_root=root)

    assert swap["swapped"] == 1, "the swap has to happen inside the read's own open, or nothing was tested"
    assert observed["state"] == "skipped_unsafe_path", observed
    assert observed["tail"] == "" and observed["bytes_read"] == 0
    if os.name == "nt":
        # The Windows reader has no component walk to refuse in: it opened the name once and asked the
        # handle where it really lives, so the refusal names the object that was reached -- the outside
        # path -- rather than a link.  Either sentence is the same finding, and only one of them can be
        # written by the host that produced it.
        assert "resolves outside the permitted evidence root" in observed["reason"], observed["reason"]
    else:
        assert "symbolic link" in observed["reason"], observed["reason"]
    assert "DO-NOT-PUBLISH" not in json.dumps(observed), "outside content reached the published record"
    assert read_counter["bytes"] == 0, "a refused observation must not have consumed a single byte"
    assert swap["outside_opens"] == 0, "the sentinel was never even opened, by name or otherwise"
    assert sentinel.is_file() and "DO-NOT-PUBLISH" in sentinel.read_text(encoding="utf-8")
    # and an untouched in-root log still reads normally: the fix is a boundary, not a refusal to work
    other = root / "uninstall.log"
    other.write_text("Uninstall process started.\n", encoding="utf-8")
    calm = module._bounded_tail(other, 6, permitted_root=root)
    assert calm["state"] == "complete" and calm["bytes_read"] == other.stat().st_size
    assert calm["confinement"].startswith("anchored")


def test_the_uninstaller_digest_never_becomes_a_hash_of_the_object_the_name_reached(tmp_path, monkeypatch,
                                                                                    read_counter):
    """Same race, second consumer: the forensic digest, which is the one read of the install tree.

    A digest is evidence about a file only if it was taken from the file that was validated.  The old shape
    hashed `sha256_file(path)` -- a second lookup of a name that had already been checked -- so an
    uninstaller swapped for a link produced a confident hash of somebody else's bytes.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    install = root / "install"
    install.mkdir(parents=True)
    exe = install / "unins000.exe"
    exe.write_bytes(b"REAL-UNINSTALLER-BYTES")
    sentinel = tmp_path / "other.exe"
    sentinel.write_bytes(b"DO-NOT-PUBLISH")
    swap = _swapping_open(monkeypatch, module, exe, sentinel)

    observed = module._observed_path(exe, hash_file=True, permitted_root=root)

    assert swap["swapped"] == 1
    assert observed["hash_state"] == "skipped_unsafe_path", observed
    assert "sha256" not in observed, "a refused digest must not publish a digest of anything"
    assert read_counter["bytes"] == 0 and swap["outside_opens"] == 0
    assert "DO-NOT-PUBLISH" not in json.dumps(observed)

    # The one-object property, without any link: replace the file with a *different regular file* between
    # the stat and the open.  The published size and digest must then describe the same object, whichever
    # one it was -- never the size of one file with the hash of another.
    exe.unlink()  # the fixture above left a dangling link behind; this phase needs the plain name back
    exe.write_bytes(b"REAL-UNINSTALLER-BYTES")
    second = install / "second.exe"
    second.write_bytes(b"REPLACEMENT-BYTES")
    real_os_open = os.open
    state = {"swapped": 0}

    def swap_regular_file_once():
        if state["swapped"]:
            return
        state["swapped"] += 1
        os.replace(second, exe)

    def os_wrapper(file, flags, mode=0o777, *args, **kwargs):
        if "dir_fd" in kwargs and str(file) == exe.name and not state["swapped"]:
            swap_regular_file_once()
        return real_os_open(file, flags, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", os_wrapper)

    def windows_hook(path, directory):
        # Same moment, reached through the open this host's reader actually performs: a different regular
        # file takes the name between the stat and the create, and the digest must still describe the
        # object the handle reached.
        if not directory and path.name == exe.name:
            swap_regular_file_once()
        return None

    _ride_the_open_the_host_actually_uses(monkeypatch, module, windows_hook)
    after = module._observed_path(exe, hash_file=True, permitted_root=root)
    assert state["swapped"] == 1
    assert after["hash_state"] == "hashed"
    keep = install / "keep.exe"
    keep.write_bytes(b"REPLACEMENT-BYTES")
    original = install / "original.exe"
    original.write_bytes(b"REAL-UNINSTALLER-BYTES")
    assert after["sha256"] == module.sha256_file(keep), ("the digest is of the object that was opened, not of "
                                                          "the name that was checked")
    assert after["sha256"] != module.sha256_file(original), ("the validated file's hash was published as if it "
                                                              "had been read, and it was not")
    assert after["hash_bytes"] == exe.stat().st_size == len(b"REPLACEMENT-BYTES")
    assert after["hash_confinement"].startswith("anchored")
    assert after.get("replaced_before_open", True) is True, "the record shows that the name moved (POSIX)"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="the platform has no FIFO to plant")
@pytest.mark.skipif(os.name == "nt", reason="POSIX object type; Windows shape is covered separately")
def test_a_blocking_object_where_a_log_is_expected_is_refused_rather_than_read(tmp_path):
    """A FIFO is the object that turns a careless reader into a hung CI step, so it must be refused fast.

    The anchored open sets `O_NONBLOCK`, so an unplanted-by-anybody queue cannot block the attempt, and the
    type test runs on the opened descriptor: a pipe is not a log, and saying so is the whole requirement.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    fifo = root / "uninstall.log"
    os.mkfifo(fifo)

    # The bound on this test is wall-clock, and `signal` is what keeps a regression from turning the suite
    # into a hang: a reader that opens the queue without O_NONBLOCK and without a type check blocks in the
    # open, so the test arms an alarm and fails instead of waiting for the CI job timeout.  (When the M42.8
    # design is restored -- resolve the name, then open the name -- this is exactly what happens, which is
    # why the alarm is part of the assertion rather than a courtesy.)
    def expire(signum, frame):
        raise AssertionError("the read did not return: the object was opened and awaited, not refused")

    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, 20.0)
    started = time.monotonic()
    try:
        observed = module._bounded_tail(fifo, 6, permitted_root=root)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)
    assert time.monotonic() - started < 15, "the read blocked on a queue nobody was writing to"
    assert observed["state"] == "unreadable" and observed["reason"] == "not a regular file"
    assert observed["bytes_read"] == 0 and observed["tail"] == ""


def test_the_root_itself_is_part_of_the_anchor(tmp_path):
    """Replacing the work root must stop the reads, not quietly move the boundary somewhere else.

    The identity is whatever the run recorded when it created the directory; a caller that supplies the
    wrong one is treated as having lost the boundary, and a caller that supplies the right one is
    unaffected -- so the check costs a read nothing and buys the case where `work_root` is a symlink to,
    or has been re-created as, an entirely different directory.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "install.log"
    log.write_text("Setup process started.\n", encoding="utf-8")
    identity = module._directory_identity(root)
    assert identity, "the identity of a directory this process created must be readable"
    assert module._bounded_tail(log, 6, permitted_root=root, root_identity=identity)["state"] == "complete"

    hijacked = tmp_path / "elsewhere"
    hijacked.mkdir()
    (hijacked / "install.log").write_text("DO-NOT-PUBLISH from a different root\n", encoding="utf-8")
    observed = module._bounded_tail(log, 6, permitted_root=root, root_identity=module._directory_identity(hijacked))
    assert observed["state"] == "skipped_unsafe_path" and observed["bytes_read"] == 0
    assert "not the one this run created" in observed["reason"]
    assert "DO-NOT-PUBLISH" not in json.dumps(observed)


def test_the_root_identity_survives_work_done_inside_the_root(tmp_path):
    """The identity that anchors every read is the directory *object*, so its contents may change underneath it.

    Windows identity is the volume serial with the file index, and the lifecycle depends on exactly that:
    the run creates `install/`, writes logs, and empties the tree again *inside* the work root, and every
    later read re-derives the root's identity and compares it against the one captured at the start.  An
    identity that drifted with the directory's own timestamps -- which is what a short
    BY_HANDLE_FILE_INFORMATION declaration turned it into -- refused those reads as if the root had been
    swapped, and a lifecycle that had passed every step reported a user-data sentinel that "did not survive"
    an uninstall it had in fact survived.  This runs on the Windows job too, where the native identity is
    what is being asked.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "install.log"
    log.write_text("Setup process started.\n", encoding="utf-8")
    captured = module._directory_identity(root)
    assert captured is not None

    (root / "install").mkdir()
    (root / "install" / "DrillMaster.exe").write_bytes(b"installed executable")
    (root / "userdata").mkdir()
    (root / "userdata" / "sentinel-preserve.txt").write_text("DRILLMASTER-LIFECYCLE-SENTINEL-PRESERVE\n",
                                                             encoding="utf-8")
    log.write_text(log.read_text(encoding="utf-8") + "Setup process finished.\n", encoding="utf-8")

    assert module._directory_identity(root) == captured, (
        "the root's identity describes the directory object, not the times its contents changed")
    observed = module._bounded_tail(log, 6, permitted_root=root, root_identity=captured)
    assert observed["state"] == "complete" and observed["bytes_read"] > 0, (
        "work done inside the root must not invalidate the root's own identity")


def test_the_uninstall_log_read_re_validates_the_work_root_identity(tmp_path):
    """The uninstaller's own log is read inside the run's root, so it re-checks *which* root that is.

    `_uninstall` runs after the install tree has been emptied and takes the work root from
    `install_dir.parent`; that path is the boundary by construction, but "the directory this run created"
    is the identity, not the name, and this is the last read a lifecycle performs.  A read that skipped the
    comparison would be confined to whatever the path denotes at that moment -- the substitution every
    other anchored read refuses -- so the same refusal has to cover it.  `unins000.exe` here is the real
    scripted stand-in, so the log the assertion reads is the one the fake uninstaller wrote.
    """
    module = _evidence_module()
    work = tmp_path / "work"
    install_dir = work / "install"
    install_dir.mkdir(parents=True)
    log = work / "uninstall.log"

    evidence = {"diagnostics": {}}
    module._uninstall(install_dir / "unins000.exe", log, install_dir, FakeHost(), 30, 0.001, 0.0, evidence,
                      root_identity=module._directory_identity(work))
    assert "Uninstall process started." in evidence["diagnostics"]["uninstall_log"], (
        "the run's own work root has to be readable, or the identity check is not a check but a shutdown")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    replaced = {"diagnostics": {}}
    module._uninstall(install_dir / "unins000.exe", log, install_dir, FakeHost(), 30, 0.001, 0.0, replaced,
                      root_identity=module._directory_identity(elsewhere))
    assert replaced["diagnostics"]["uninstall_log"] == "", (
        "a log under a root that is not the one this run created must be refused, not read")


def test_the_windows_confinement_rule_is_decided_on_handle_metadata_not_on_following_links():
    """Windows has no descriptor-relative open, so the verdict is computed from what the handle reports.

    Every fact below is the answer to a kernel32 call on an *open handle* -- final path, file type, volume
    serial with file index, attribute bits -- and the junction case is the one a prefix test cannot see: a
    link inside the root whose target is also inside the root still resolves to a plausible path, so the
    comparison that matters is between the object's real path and the object that was *named*.  Symlinks and
    junctions are simulated here; the native path is only proven on a Windows host, and this file says so.
    """
    module = _evidence_module()
    root = "C:\\runner\\temp\\drillmaster-lifecycle"
    verdict = module._confinement_verdict

    assert verdict(root + "\\install.log", root, object_kind="disk", same_volume=True, is_reparse=False) == (
        "within", "")
    assert verdict(root.upper() + "\\INSTALL.LOG", root, object_kind="disk", same_volume=True,
                   is_reparse=False)[0] == "within", "case differences are how Windows spells the same file"
    outside = verdict("C:\\users\\operator\\.ssh\\id_rsa", root, object_kind="disk", same_volume=True,
                      is_reparse=False)
    assert outside[0] == "skipped_unsafe_path" and "outside the permitted evidence root" in outside[1]
    sibling = verdict("C:\\runner\\temp\\drillmaster-lifecycle-evil\\install.log", root, object_kind="disk",
                      same_volume=True, is_reparse=False)
    assert sibling[0] == "skipped_unsafe_path", "a prefix of the root's name is not containment"

    # the junction that lands inside the root anyway: the named object and the opened object differ
    junction = verdict(root + "\\other\\install.log", root, object_kind="disk", same_volume=True,
                       is_reparse=False, expected_target=root + "\\install\\install.log")
    assert junction[0] == "skipped_unsafe_path" and "link was followed" in junction[1]
    reparse = verdict(root + "\\install.log", root, object_kind="disk", same_volume=True, is_reparse=True)
    assert reparse[0] == "skipped_unsafe_path" and "reparse point" in reparse[1]
    other_volume = verdict(root + "\\install.log", root, object_kind="disk", same_volume=False,
                           is_reparse=False)
    assert other_volume[0] == "skipped_unsafe_path", "a same-named path on another volume is another file"
    for kind in ("pipe", "character device", "unknown"):
        assert verdict(root + "\\install.log", root, object_kind=kind, same_volume=True, is_reparse=False) == (
            "unreadable", f"the opened object is a {kind}, not a regular disk file; nothing was read")
    # metadata that cannot be answered is a refusal, and the caller turns it into one: no fallback open
    assert verdict("", root, object_kind="disk", same_volume=True, is_reparse=False)[0] == "skipped_unsafe_path"


class _DevicePathKernel32:
    r"""The kernel32 questions in the spelling Windows answers them with, over files that exist here.

    A device namespace cannot be mounted on this host, so this fixture renames rather than copies: the files
    it opens are the real ones, and only the *final path* it reports -- the single answer the containment
    comparison is built on -- is the Windows form (``\\?\C:\...``).  A fixture that reported the POSIX path
    could not tell a correct join from a doubled-separator one, and a doubled separator is what refused
    every anchored read on the first Windows runs to reach that comparison.
    """

    def __init__(self, device_paths: dict[Path, str]):
        self.device_paths = {str(path): device for path, device in device_paths.items()}
        self.handles: dict[int, tuple[str, Path]] = {}
        self.closed: list[int] = []
        self.next_handle = 0x1000
        # Plain function objects per instance, for the same reason the ABI fixture uses them: the helper
        # assigns ``restype``/``argtypes`` to every call it binds, and a bound method refuses that.
        self.CreateFileW = lambda *args: self._create(*args)
        self.CloseHandle = lambda handle: self._close(handle)
        self.GetFileType = lambda handle: 1  # FILE_TYPE_DISK
        self.GetFinalPathNameByHandleW = lambda *args: self._final_path(*args)
        self.GetFileInformationByHandle = lambda handle, pointer: self._information(handle, pointer)

    def _create(self, path, access, share, security, disposition, flags, template):
        key = str(path)
        if key not in self.device_paths:
            return 0  # CreateFileW's "no such file": the helper reads a falsy handle as a refusal
        self.next_handle += 0x10
        self.handles[self.next_handle] = (self.device_paths[key], Path(key))
        return self.next_handle

    def _close(self, handle):
        self.closed.append(handle)
        self.handles.pop(handle, None)

    def _final_path(self, handle, buffer, length, flags):
        text, _ = self.handles.get(handle, ("", None))
        buffer.value = text
        return len(text)

    def _information(self, handle, pointer):
        import ctypes
        import struct

        _, path = self.handles[handle]
        image = bytearray(52)
        struct.pack_into("<I", image, 0, 0x00000080)          # FILE_ATTRIBUTE_NORMAL
        struct.pack_into("<I", image, 28, 0x7A11CE55)         # dwVolumeSerialNumber
        size = path.stat().st_size
        struct.pack_into("<I", image, 32, size >> 32)         # nFileSizeHigh
        struct.pack_into("<I", image, 36, size & 0xFFFFFFFF)  # nFileSizeLow
        struct.pack_into("<I", image, 44, 0x0000ABCD)         # nFileIndexHigh
        struct.pack_into("<I", image, 48, 0x0000EF01)         # nFileIndexLow
        ctypes.memmove(pointer, bytes(image), 52)
        return 1


class _PosixOsfHandle:
    """``msvcrt``'s descriptor calls, backed by a real descriptor, so the bytes read are real bytes.

    Attaching the validated handle is what turns it into the stream the content comes from; stubbing that
    out would leave the read asserted only up to the point where the module stops using kernel32.
    """

    def __init__(self, kernel32: _DevicePathKernel32):
        self.kernel32 = kernel32

    def open_osfhandle(self, handle, flags):
        _, path = self.kernel32.handles[int(handle)]
        return os.open(path, os.O_RDONLY)

    def close(self, descriptor):
        os.close(descriptor)


def test_the_expected_device_path_is_joined_with_exactly_one_separator():
    """The expectation is compared character for character, so the separator is pinned rather than implied."""
    module = _evidence_module()
    assert module._join_device_path("\\\\?\\C:\\work", ["logs", "drillmaster.log"]) == (
        "\\\\?\\C:\\work\\logs\\drillmaster.log")
    # a directory's final path may or may not carry a trailing separator; both spellings join the same way
    assert module._join_device_path("\\\\?\\C:\\work\\", ["logs"]) == "\\\\?\\C:\\work\\logs"
    assert module._join_device_path("C:\\", []) == "C:" and module._join_device_path("", ["a"]) == "\\a"


def test_the_anchored_windows_open_accepts_the_object_the_name_denotes(tmp_path, monkeypatch):
    """The joined expectation has to be the spelling the handle reports, or every Windows read is refused.

    The containment decision compares the path ``GetFinalPathNameByHandleW`` reports for the opened object
    against the permitted root's own final path with the caller's components appended.  Those components are
    joined with one separator; with a doubled one the expectation was a path no handle can report, and every
    anchored read on Windows -- installer log, uninstall log, smoke log, the user-data sentinel, the
    uninstaller digest -- was refused as "a different object ... through a link", while the same code passed
    on this host, where the branch is never entered.  That is what the first Windows run of this comparison
    produced: 35 failures, every one of them waiting on a read inside the permitted root.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "uninstall.log"
    log.write_bytes(b"Uninstall process finished.\n")  # bytes, so the object holds exactly these bytes on
    #                                                   every host: a text write would put CRLF on the
    #                                                   Windows runner and the comparison below would be
    #                                                   measuring the platform's newline, not the reader
    device_root = "\\\\?\\C:\\runner\\temp\\work"
    kernel32 = _DevicePathKernel32({root: device_root, log: f"{device_root}\\uninstall.log"})
    monkeypatch.setattr(module, "_win32_api", lambda: module._Win32HandleMetadata(kernel32))
    monkeypatch.setitem(sys.modules, "msvcrt", _PosixOsfHandle(kernel32))

    stream, meta = module._open_binary_windows(log, root, None)
    with stream:
        assert stream.read() == b"Uninstall process finished.\n"
    assert meta["confinement"].startswith("anchored: opened once"), meta["confinement"]
    assert meta["size"] == log.stat().st_size
    assert meta["object_identity"] == [0x7A11CE55, (0x0000ABCD << 32) | 0x0000EF01]

    # The refusal this comparison exists for still happens: content inside the root that is not the object
    # the name denotes is refused, never read.
    elsewhere = _DevicePathKernel32({root: device_root, log: f"{device_root}\\other\\uninstall.log"})
    monkeypatch.setattr(module, "_win32_api", lambda: module._Win32HandleMetadata(elsewhere))
    monkeypatch.setitem(sys.modules, "msvcrt", _PosixOsfHandle(elsewhere))
    with pytest.raises(module.AnchorRefusal) as refusal:
        module._open_binary_windows(log, root, None)
    assert refusal.value.state == "skipped_unsafe_path" and "link was followed" in refusal.value.reason


class _HostNamedWindows:
    """The `os` module with one field answered differently: the reader's own platform check.

    Patching `os.name` itself is not available -- `pathlib` picks its flavour class from it at call time, so
    on this host every `Path(...)` in the interpreter, pytest's own error reporting included, would become a
    WindowsPath and raise.  This forwards every attribute to the real module and answers only the question
    the reader's branch asks, which is what a test needs and nothing more.
    """

    name = "nt"

    def __getattr__(self, attribute):
        return getattr(os, attribute)


def test_the_race_fixtures_fire_inside_the_open_the_reader_actually_makes(tmp_path, monkeypatch):
    """The seam the Windows halves of the race fixtures ride, exercised where it can be.

    Those fixtures hook `os.open(dir_fd=...)` on this host and the reader's own `open_handle` on Windows, and
    the source gate cannot run the Windows half of that.  What it can run is the wiring, and the wiring is
    where this went wrong: a hook that never fires leaves the assertions reporting that nothing happened,
    which the Windows gate then read as the tests failing to prove their subject.  So with the reader taking
    its Windows branch -- pointed at the scripted device-path helper -- the hook must fire at the reader's
    open, the path it returns must be the object that actually gets opened, and an error it raises must
    arrive at the module as the state that error means.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "uninstall.log"
    log.write_bytes(b"IN-ROOT setup line\n")
    other = root / "other.log"
    other.write_bytes(b"ANOTHER OBJECT\n")
    device_root = "\\\\?\\C:\\runner\\temp\\work"
    kernel32 = _DevicePathKernel32({root: device_root, log: f"{device_root}\\uninstall.log",
                                   other: f"{device_root}\\other.log"})
    monkeypatch.setattr(module, "os", _HostNamedWindows())  # the reader's branch check, not a stand-in for it
    monkeypatch.setitem(sys.modules, "msvcrt", _PosixOsfHandle(kernel32))
    monkeypatch.setattr(module, "_win32_api", lambda: module._Win32HandleMetadata(kernel32))

    seen: list[tuple[str, bool]] = []

    def redirect(path, directory):
        seen.append((path.name, directory))
        return other if path.name == "uninstall.log" else None

    seam = _ride_the_open_the_host_actually_uses(monkeypatch, module, redirect)
    assert seam == "kernel32 CreateFileW via _Win32HandleMetadata.open_handle"
    observed = module._bounded_tail(log, 6, permitted_root=root)
    assert seen and seen[-1] == ("uninstall.log", False), (
        "the hook has to fire at the reader's own open of the named object, not at the root's")
    assert observed["state"] == "skipped_unsafe_path", observed
    assert observed["bytes_read"] == 0 and observed["tail"] == ""
    assert "the named path reached a different object" in observed["reason"], observed["reason"]
    assert "ANOTHER OBJECT" not in json.dumps(observed)

    def refuse(path, directory):
        if not directory and path.name == "uninstall.log":
            raise FileNotFoundError(2, "No such file or directory")
        return None

    _ride_the_open_the_host_actually_uses(monkeypatch, module, refuse)
    vanished = module._bounded_tail(log, 6, permitted_root=root)
    assert vanished["state"] == "absent" and vanished["bytes_read"] == 0, vanished


class _ScriptedKernel32:
    """The kernel32 subset the handle-metadata helper binds, without a Windows host.

    A real ``ctypes.windll.kernel32`` does not exist here, so the fixture answers the calls the helper
    makes and records what was declared on it.  ``GetFileInformationByHandle`` copies an ABI-shaped image
    of ``BY_HANDLE_FILE_INFORMATION`` into the buffer the helper passes, bounded by that helper's own
    declaration: a declaration that is too small then fails an assertion instead of corrupting this
    process the way it corrupted the Windows runner's.
    """

    def __init__(self, image: bytes, declared_size: int):
        self.image = image
        self.declared_size = declared_size
        self.information_bytes_written = 0
        # Plain function objects stored on the instance, not bound methods: the helper assigns
        # ``restype``/``argtypes`` to every one of these, exactly as it does to kernel32's own entries.
        self.CreateFileW = lambda *args: 0x1234
        self.CloseHandle = lambda handle: None
        self.GetFileType = lambda handle: 1
        self.GetFinalPathNameByHandleW = lambda *args: 0
        self.GetFileInformationByHandle = lambda handle, pointer: self._write_information(handle, pointer)

    def _write_information(self, handle, pointer):
        import ctypes

        size = min(len(self.image), self.declared_size)
        ctypes.memmove(pointer, self.image[:size], size)
        self.information_bytes_written = size
        return 1


def test_the_handle_metadata_declaration_is_the_structure_the_windows_abi_writes():
    """``GetFileInformationByHandle`` fills 52 bytes, so both the size and the offsets have to match it.

    The defect this pins is not cosmetic.  A declaration that listed only the fields this module consumes
    was 24 bytes, so the kernel wrote 28 bytes past the end of the ctypes object -- into the interpreter's
    own heap -- and the fault appeared at whatever allocation came next: on four consecutive Windows gate
    runs that was redaction, traceback formatting, and JUnit recording, none of which can fault on their
    own.  The offsets matter for the second half of the same defect: with the short declaration
    ``nFileIndexHigh`` read a timestamp, so the identity every anchored read compares the root against
    changed whenever the directory did, which refused reads that were inside the boundary.
    """
    import ctypes

    module = _evidence_module()
    struct_type = module._by_handle_file_information(ctypes)
    assert ctypes.sizeof(struct_type) == 52, "the Windows ABI writes the whole structure"
    assert {name: getattr(struct_type, name).offset for name, _ in struct_type._fields_} == {
        "dwFileAttributes": 0, "ftCreationTime": 4, "ftLastAccessTime": 12, "ftLastWriteTime": 20,
        "dwVolumeSerialNumber": 28, "nFileSizeHigh": 32, "nFileSizeLow": 36, "nNumberOfLinks": 40,
        "nFileIndexHigh": 44, "nFileIndexLow": 48,
    }, "every field of BY_HANDLE_FILE_INFORMATION, in ABI order"
    # the widths are fixed-width, not the host's `unsigned long`, or the layout would differ per host
    assert [name for name, field_type in struct_type._fields_ if field_type is ctypes.c_uint32] == [
        "dwFileAttributes", "dwVolumeSerialNumber", "nFileSizeHigh", "nFileSizeLow", "nNumberOfLinks",
        "nFileIndexHigh", "nFileIndexLow",
    ], "the DWORD fields are 32-bit on every host this gate runs on"
    for name, field_type in struct_type._fields_:
        if field_type is not ctypes.c_uint32:  # the three FILETIME fields
            assert [inner[0] for inner in field_type._fields_] == ["dwLowDateTime", "dwHighDateTime"], name
            assert all(inner[1] is ctypes.c_uint32 for inner in field_type._fields_), name


def test_a_declaration_that_disagrees_with_the_abi_is_refused_instead_of_used(monkeypatch):
    """A wrong declaration has to cost a read, never the run: the factory refuses it and the path fails closed."""
    import ctypes

    module = _evidence_module()
    monkeypatch.setattr(module, "_WIN32_HANDLE_METADATA_FIELDS",
                        tuple(field for field in module._WIN32_HANDLE_METADATA_FIELDS
                              if field[0] != "nNumberOfLinks"))
    with pytest.raises(ValueError, match="must be 52 bytes"):
        module._by_handle_file_information(ctypes)


def test_the_handle_metadata_reads_the_file_index_and_never_a_timestamp():
    """The identity is the volume serial with the file index, read by offset -- not the FILETIMEs next to them.

    A structure can be 52 bytes and still describe the wrong fields, so the answer is read out of a
    documented image of the structure: recognisable FILETIME values sit at their ABI offsets and the
    metadata has to return the volume serial and file index instead of any of them.  This is the value the
    work root's identity is recorded from and compared back against on every anchored read.
    """
    import ctypes
    import struct

    module = _evidence_module()
    image = bytearray(52)
    struct.pack_into("<I", image, 0, 0x00000020)           # FILE_ATTRIBUTE_ARCHIVE
    struct.pack_into("<Q", image, 4, 0x01D9000000000000)   # ftCreationTime
    struct.pack_into("<Q", image, 12, 0x01D9111122223333)  # ftLastAccessTime
    struct.pack_into("<Q", image, 20, 0x01D9444455556666)  # ftLastWriteTime
    struct.pack_into("<I", image, 28, 0xA1B2C3D4)          # dwVolumeSerialNumber
    struct.pack_into("<I", image, 32, 0x00000001)          # nFileSizeHigh
    struct.pack_into("<I", image, 36, 0x89ABCDEF)          # nFileSizeLow
    struct.pack_into("<I", image, 40, 3)                   # nNumberOfLinks
    struct.pack_into("<I", image, 44, 0x11223344)          # nFileIndexHigh
    struct.pack_into("<I", image, 48, 0x55667788)          # nFileIndexLow
    declared = ctypes.sizeof(module._by_handle_file_information(ctypes))
    kernel32 = _ScriptedKernel32(bytes(image), declared)
    metadata = module._Win32HandleMetadata(kernel32)

    info = metadata.identity(object())
    assert info == {"size": (0x00000001 << 32) | 0x89ABCDEF, "volume": 0xA1B2C3D4,
                    "identity": (0xA1B2C3D4, (0x11223344 << 32) | 0x55667788), "is_reparse": False}
    assert kernel32.information_bytes_written == 52, (
        "the kernel writes all 52 bytes; a smaller declaration is where the write leaves the object")

    image[0:4] = struct.pack("<I", 0x00000020 | 0x00000400)  # FILE_ATTRIBUTE_REPARSE_POINT
    kernel32.image = bytes(image)
    assert metadata.identity(object())["is_reparse"] is True


def test_every_kernel32_call_a_handle_travels_to_declares_it_as_a_pointer():
    """A handle silently converted to a C int is a call about some other object, so each one declares its type.

    ``CreateFileW`` returns a pointer-sized handle; without an ``argtypes`` entry on the calls that receive
    it, ctypes converts the value back to a 32-bit int on a 64-bit runner, and a truncated handle either
    fails the call or -- the case this check exists for -- answers a question about the wrong object.
    """
    import ctypes

    module = _evidence_module()
    kernel32 = _ScriptedKernel32(b"\x00" * 52, 52)
    module._Win32HandleMetadata(kernel32)
    assert kernel32.CreateFileW.restype == ctypes.c_void_p
    for call in (kernel32.CloseHandle, kernel32.GetFileType):
        assert call.argtypes == [ctypes.c_void_p], call
    assert kernel32.GetFileInformationByHandle.argtypes == [ctypes.c_void_p, ctypes.c_void_p]
    assert kernel32.GetFinalPathNameByHandleW.argtypes[0] == ctypes.c_void_p


def test_the_handle_is_attached_in_binary_mode_so_no_byte_is_invented_or_lost(tmp_path, monkeypatch):
    """`attach` must ask the CRT for a binary descriptor, and this proves it on a host that has no CRT.

    Windows text mode rewrites ``CRLF`` to ``LF`` while reading, so a handle attached without ``O_BINARY``
    yields a stream whose bytes are a plausible but *shortened* copy of the object: the recorded read would
    disagree with the size measured on the same handle, and the tail would not be the file's last bytes.
    Nothing on Linux can show that by itself, so the fake below models the documented CRT behaviour: it hands
    back a descriptor over the untranslated file only when the binary flag was requested, and over a
    newline-folded copy otherwise.  A run on the Windows job still decides the native question; this test
    decides that the code asks the question correctly, everywhere.
    """
    module = _evidence_module()
    log = tmp_path / "install.log"
    raw = b"first line\r\nsecond line\r\n"
    log.write_bytes(raw)
    requested = {}

    class _FakeKernel32:
        """Just enough of kernel32 for the metadata helper's declaration pass; nothing here reads bytes."""

        def __init__(self):
            self.closed = []
            # Plain function objects on the instance, exactly as a ctypes library exposes them: the helper
            # declares ``restype``/``argtypes`` on every entry point it binds, and a bound method could not
            # carry those declarations.
            self.CreateFileW = lambda *args: 0
            self.GetFinalPathNameByHandleW = lambda *args: 0
            self.GetFileInformationByHandle = lambda *args: 0
            self.GetFileType = lambda *args: 0
            self.CloseHandle = lambda handle: self.closed.append(handle)

    class _FakeMsvcrt:
        O_BINARY = 0x8000  # the value Windows uses; absent from the flags means "translate newlines"

        def open_osfhandle(self, value, flags):
            requested["flags"] = int(flags)
            source = tmp_path / ("binary.bin" if int(flags) & self.O_BINARY else "text.bin")
            source.write_bytes(raw if int(flags) & self.O_BINARY else raw.replace(b"\r\n", b"\n"))
            return os.open(source, os.O_RDONLY)

        def close(self, descriptor):
            os.close(descriptor)

    kernel32 = _FakeKernel32()
    monkeypatch.setitem(sys.modules, "msvcrt", _FakeMsvcrt())
    api = module._Win32HandleMetadata(kernel32)
    stream = api.attach(type("H", (), {"value": 4242})())
    try:
        observed = stream.read()
    finally:
        stream.close()

    assert observed == raw, (f"the stream returned {observed!r} instead of the object's own bytes, which is "
                             "newline translation: the descriptor was not requested in binary mode")
    assert requested["flags"] == module._WIN32_READ_FLAGS, (
        "the descriptor was not created with the reader's declared flags")
    if hasattr(os, "O_BINARY"):
        assert module._WIN32_O_BINARY == os.O_BINARY, (
            "the mirrored literal no longer matches this platform's os.O_BINARY, so the flag is not the one "
            "that suppresses text translation here")
    assert kernel32.closed == [], "a successful attach must not leave the handle closeable twice"


def test_a_log_that_uses_windows_line_endings_is_still_counted_in_bytes(tmp_path):
    """A CRLF log is the ordinary case on Windows, and the reader must not quietly shrink it.

    The published record carries a byte count next to the tail, and the tail itself is a *rendering* of the
    last lines (`splitlines` is what removes the terminators, on every platform, by design).  So the property
    a CRLF file has to preserve is the arithmetic, not the punctuation: the bytes read must equal the bytes the
    handle measured, or the record reports a smaller object than it opened -- and a digest taken through the
    same shortcut would no longer match the same file read another way.
    """
    module = _evidence_module()
    log = tmp_path / "install.log"
    line = b"Setup process started.\r\n"
    log.write_bytes(line * 5)
    size = log.stat().st_size
    assert size == len(line) * 5 and b"\r\n" in log.read_bytes()

    observed = module._bounded_tail(log, 40, permitted_root=tmp_path)
    assert observed["state"] == "complete", observed["reason"]
    assert observed["size_bytes"] == size and observed["bytes_read"] == size, (
        "the read returned fewer bytes than the object holds, which is newline translation on the way in")
    assert observed["tail"].count("Setup process started.") == 5, (
        "a line was lost or two were merged: the tail is no longer the log's own lines")
    assert "\r" not in observed["tail"], "the carriage returns survived splitlines and became content"


def _make_native_link(link: Path, target: Path) -> str:
    """Create a link the operating system itself made, and say which kind.

    Junctions are used on Windows because they need no privilege and no developer mode -- `os.symlink`
    there does, so a test that insisted on a symlink could only ever skip on a normal runner, and a skip in
    the source gate is a failure, not a pass.
    """
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True,
                                text=True, check=False)
        if result.returncode != 0 or not link.exists():
            raise AssertionError("this host could not create a native junction, so the Windows branch is "
                                 f"unexercised and the run must not be read as proof ({result.stderr.strip()})")
        return "junction"
    os.symlink(str(target), str(link))
    return "symbolic link"


def test_a_native_link_inside_the_root_is_refused_on_the_host_that_made_it(tmp_path):
    """The link is refused by the platform's own mechanism, on every gate platform, with no stand-in.

    On Windows this is the case the simulated handle metadata cannot establish: what `CreateFileW` and
    `GetFinalPathNameByHandleW` actually report for a junction.  On POSIX the same shape is a symbolic link,
    which the anchored walk refuses component by component.  Either way the outside object is never read, so
    one test holds both platforms to one guarantee instead of leaving the Windows half reasoned about.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    target = tmp_path / "elsewhere"
    (root / "install").mkdir(parents=True)
    target.mkdir()
    secret = target / "secret.log"
    secret.write_bytes(b"DO-NOT-PUBLISH outside content\r\nand more of it\r\n")
    before = secret.stat()
    kind = _make_native_link(root / "linked", target)
    assert kind in {"junction", "symbolic link"}

    observed = module._bounded_tail(root / "linked" / "secret.log", 6, permitted_root=root)
    assert observed["state"] == "skipped_unsafe_path", (
        f"a real {kind} under the root was read through: {observed['reason']}")
    assert observed["bytes_read"] == 0 and observed["tail"] == ""
    assert "DO-NOT-PUBLISH" not in json.dumps(observed)
    after = secret.stat()
    assert (after.st_size, int(after.st_mtime)) == (before.st_size, int(before.st_mtime))
    assert module._bounded_tail(secret, 6, permitted_root=root)["state"] == "skipped_unsafe_path", (
        "the same object reached by its own name was published while the linked name was refused")


def test_the_byte_limit_is_a_ceiling_that_a_caller_cannot_raise(tmp_path, monkeypatch):
    """`LOG_TAIL_BYTES` was a default, and a default is only a preference somebody can pass over.

    The ceiling has to hold for the value that matters -- an accidental or deliberate request for
    gigabytes -- so the request is refused before the file is opened rather than clamped: a clamped
    request would report a smaller read than the caller believes it asked for, which is a wrong number in
    the record, and honouring it is the unbounded read this bound exists to prevent.
    """
    module = _evidence_module()
    log = tmp_path / "install.log"
    log.write_text("Setup process started.\n", encoding="utf-8")
    real_io_open, real_os_open = io.open, os.open
    seen = {"io": 0, "os": 0}

    def counting_io_open(file, mode="r", *args, **kwargs):
        seen["io"] += 1
        return real_io_open(file, mode, *args, **kwargs)

    def counting_os_open(file, flags, mode=0o777, *args, **kwargs):
        seen["os"] += 1
        return real_os_open(file, flags, mode, *args, **kwargs)

    monkeypatch.setattr(io, "open", counting_io_open)
    monkeypatch.setattr(os, "open", counting_os_open)
    ceiling = module.LOG_TAIL_BYTES
    for oversized in (ceiling + 1, ceiling * 2, 3 * 1024 ** 3, 10 ** 12):
        with pytest.raises(ValueError, match="cannot exceed the global tail bound"):
            module._bounded_tail(log, 6, byte_limit=oversized)
        with pytest.raises(ValueError, match="cannot exceed the global tail bound"):
            module._tail(log, 6, byte_limit=oversized, permitted_root=tmp_path)
    for invalid in (0, -1, -ceiling):
        with pytest.raises(ValueError, match="positive bound"):
            module._bounded_tail(log, 6, byte_limit=invalid)
    assert seen == {"io": 0, "os": 0}, "an oversized request must be refused before touching the file"
    # the boundary of the allowed set: exactly the ceiling, and anything below it
    assert module._bounded_tail(log, 6, byte_limit=ceiling)["state"] == "complete"
    smallest = module._bounded_tail(log, 6, byte_limit=1)
    assert smallest["state"] == "truncated" and smallest["bytes_read"] == 2, (
        "the one permitted probe byte is still read, so the reported number cannot be rounded down to flatter "
        "the bound")


def test_the_ceiling_is_measured_through_the_wrapper_production_calls(tmp_path, read_counter):
    """Not the length of a returned string and not the reported counter: the bytes the OS was asked for.

    `_tail` with a `permitted_root` is the exact call the lifecycle step makes, so measuring there is what
    keeps the claim honest about the shipped path.  A smaller override is allowed and has to be honoured as
    a smaller *read*, which is the other half of "the ceiling is a ceiling, not a target".
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "install.log"
    log.write_text("OLD-PREFIX " + ("x" * 200 + "\n") * 40000 + "recent line\n", encoding="utf-8")
    assert log.stat().st_size > module.LOG_TAIL_BYTES * 4

    text = module._tail(log, 6, permitted_root=root)
    assert read_counter["bytes"] <= module.LOG_TAIL_BYTES + 1, read_counter["bytes"]
    assert len(text.encode("utf-8")) <= module.LOG_TAIL_BYTES + 200, "the wrapper published more than it read"
    assert text.endswith("recent line"), "the newest line has to survive the wrapper"
    assert text.startswith(f"[only the last {module.LOG_TAIL_BYTES} of {log.stat().st_size} bytes were read")
    assert "OLD-PREFIX" not in text

    read_counter["bytes"] = 0
    narrowed = module._bounded_tail(log, 6, byte_limit=4096, permitted_root=root)
    assert read_counter["bytes"] <= 4097, read_counter["bytes"]
    assert narrowed["bytes_read"] <= 4097 and narrowed["state"] == "truncated"


def test_the_first_line_is_dropped_only_when_the_boundary_proves_it_is_a_fragment(tmp_path):
    """Two windows of the same file, one byte apart, and the record has to tell them apart.

    M42.8 inferred "partial" from `start > 0`, which threw away a complete line whenever the cut happened
    to land on a boundary, and kept a fragment whenever the file was small enough that only one line
    remained.  The byte before the window settles the question, and it costs one byte inside the existing
    allowance rather than an unbounded probe.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    lines = [f"line-{index:06d}-{'x' * 20}\n".encode() for index in range(50)]  # 33 bytes each
    log = root / "install.log"
    log.write_bytes(b"".join(lines))
    size = log.stat().st_size
    assert size == 1650 and len(lines[0]) == 33, "the fixture's arithmetic is the test's oracle"

    mid_line = module._bounded_tail(log, 5, byte_limit=size - 5, permitted_root=root)
    assert mid_line["state"] == "truncated"
    assert mid_line["bytes_read"] == size - 4, "the window plus the one boundary byte, and nothing more"
    assert mid_line["size_bytes"] == size
    assert mid_line["dropped_partial_first_line"] is True
    assert mid_line["first_line_is_fragment"] is True
    assert mid_line["lines_returned"] == 5
    assert mid_line["tail"].splitlines() == [line.decode().rstrip("\n") for line in lines[-5:]]

    aligned = module._bounded_tail(log, 5, byte_limit=size - 33, permitted_root=root)
    assert aligned["state"] == "truncated"
    assert aligned["dropped_partial_first_line"] is False
    assert "first_line_is_fragment" not in aligned, "the window began on a line boundary; nothing was partial"
    assert aligned["lines_returned"] == 5
    assert aligned["tail"].splitlines() == [line.decode().rstrip("\n") for line in lines[-5:]], (
        "an aligned window must keep the line that starts it, or the record loses real evidence")
    assert aligned["bytes_read"] == size - 32, "the window is 32 bytes short of the file, plus the probe"


def test_a_window_with_fewer_lines_than_asked_for_says_so_instead_of_padded(tmp_path):
    """Three fat lines and a request for ten: the truth is one whole line plus a reported bound."""
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "install.log"
    log.write_bytes(b"A" * 100 + b"\n" + b"B" * 100 + b"\n" + b"C" * 100 + b"\n")
    observed = module._bounded_tail(log, 10, byte_limit=150, permitted_root=root)
    assert observed["state"] == "truncated"
    assert observed["lines_returned"] == 1 and observed["dropped_partial_first_line"] is True
    assert observed["tail"] == "C" * 100
    assert observed["reason"] == "only the last 150 of 303 bytes were read; older content was not inspected"
    assert observed["size_bytes"] == 303 and observed["bytes_read"] == 151


def test_a_single_line_beyond_the_bound_is_kept_and_labelled(tmp_path, read_counter):
    """A log that is one line long cannot be "the last 40 lines", and the fragment flag says so.

    Dropping the fragment would leave an empty tail, which is how a failure path loses the only evidence it
    had; the honest record is the fragment, marked as starting mid-line, plus the bound that was honoured.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "install.log"
    log.write_bytes(b"Z" * 2000)
    observed = module._bounded_tail(log, 40, byte_limit=1000, permitted_root=root)
    assert observed["state"] == "truncated" and observed["lines_returned"] == 1
    assert observed["dropped_partial_first_line"] is False
    assert observed["first_line_is_fragment"] is True
    assert observed["tail"] == "Z" * 1000 and len(observed["tail"]) == 1000
    assert observed["bytes_read"] == 1001
    assert read_counter["bytes"] <= 1001, read_counter["bytes"]


def test_a_short_log_whose_read_overruns_the_bound_is_clipped_at_the_recent_end(tmp_path):
    """The clip direction has to be pinned where it can actually be observed.

    With the boundary probe spent in front, the over-read clip only runs when the window starts at byte 0 and
    the object grew past the request -- a rare pair, and exactly the pair that decides whether an operator
    reads the newest lines or the oldest ones.  A handle double supplies the overrun, so the direction is
    forced rather than waited for.
    """
    module = _evidence_module()
    log = tmp_path / "install.log"
    log.write_bytes(b"started\n")  # smaller than the bound, so the window starts at byte 0
    size = log.stat().st_size
    real_open = io.open
    over = b"Q" + b"y" * 15 + b"Z"

    def wrapper(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if Path(str(file)) != log or "b" not in str(mode):
            return handle

        class _Overrun:
            def seek(self, offset, whence=0):
                handle.seek(offset, whence)
                return None

            def tell(self):
                return size

            def read(self, count=-1):
                return over[:count]

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return handle.__exit__(*exc_info)

        return _Overrun()

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(io, "open", wrapper)
        observed = module._bounded_tail(log, 4, byte_limit=16)
    finally:
        monkeypatch.undo()
    assert observed["size_bytes"] == size and observed["bytes_read"] == len(over)
    assert observed["state"] == "truncated" and observed["dropped_partial_first_line"] is False
    assert observed["tail"] == "y" * 15 + "Z", (
        "an overrun is clipped at the recent end; keeping the first bytes would publish the oldest content "
        "and label it the tail")
    assert not observed["tail"].startswith("Q")
    assert "grew_during_read" not in observed, "the handle reported the same end twice, so nothing grew"


def test_a_boundary_split_through_a_multibyte_character_is_replaced_not_raised(tmp_path, read_counter):
    """The window edge is a byte offset, and a byte offset owes nothing to a character boundary.

    The published text therefore contains the replacement character the decode produced, which is a truth
    about a cut byte sequence -- and it is still bounded, because the reader that clips the string is not
    the reader that bounded the read.
    """
    module = _evidence_module()
    root = tmp_path / "work"
    root.mkdir()
    log = root / "install.log"
    # one line, so the only thing in the window is the line whose first byte the cut destroyed: `é` is two
    # bytes, and a window starting on the second of them has to say so rather than raise or truncate to empty
    encoded = ("é" * 5 + ("u" * 600) + "\n").encode("utf-8")
    log.write_bytes(encoded)
    size = len(encoded)
    assert size == 611, "the fixture is 5 two-byte characters, 600 single-byte ones and a newline"
    observed = module._bounded_tail(log, 4, byte_limit=size - 1, permitted_root=root)
    assert observed["state"] == "truncated"
    assert observed["bytes_read"] == size, "the window is the bound and the probe byte, no more"
    assert observed["tail"].startswith("\ufffd"), "a split lead byte must decode to the replacement character"
    assert observed["tail"].endswith("u" * 600)
    assert observed["lines_returned"] == 1
    assert observed["dropped_partial_first_line"] is False, "one line remained, and an empty tail is not a fix"
    assert observed["first_line_is_fragment"] is True
    assert read_counter["bytes"] <= size, read_counter["bytes"]


def test_a_log_that_grows_past_the_measured_end_keeps_the_newest_measured_bytes(tmp_path, monkeypatch):
    """Growth detection moved from an over-read to the handle's own end, and says which it saw.

    Asking for one byte past the window used to be the growth probe, which cannot work for a window already
    at the ceiling: the extra byte is what the boundary needs, and a growth of more than one byte was
    invisible in the tail direction.  Re-seeking to the end of the *same handle* is exact, costs no bytes,
    and is reported instead of being silently clipped away.
    """
    module = _evidence_module()
    log = tmp_path / "install.log"
    body = "".join(f"line {index:06d} {'y' * 20}\n" for index in range(10))
    log.write_text(body, encoding="utf-8")
    size = log.stat().st_size
    real_open = io.open

    def open_that_grows(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if Path(str(file)) != log or "b" not in str(mode):
            return handle

        grown = {"done": False}

        class _Grower:
            def __init__(self):
                self._handle = handle

            def seek(self, offset, whence=0):
                result = handle.seek(offset, whence)
                if not grown["done"] and whence == os.SEEK_END:
                    grown["done"] = True
                    with real_open(log, "a", encoding="utf-8", newline="\n") as append:
                        append.write("appended-newest-line\n")
                return result

            def tell(self):
                return handle.tell()

            def read(self, count=-1):
                return handle.read(count)

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return handle.__exit__(*exc_info)

        return _Grower()

    monkeypatch.setattr(io, "open", open_that_grows)
    observed = module._bounded_tail(log, 4, byte_limit=size - 7)
    assert observed["size_bytes"] == size, "the size is what the handle measured, before the append"
    assert observed["grew_during_read"] is True
    assert "grew past the end that was measured" in observed["reason"]
    assert observed["bytes_read"] == size - 6 <= observed["size_bytes"], "exactly the window plus the probe byte"
    # the window, minus the fragment the boundary proved, clipped to the four lines that were asked for
    expected = body[7:].splitlines()[1:][-4:]  # the window is the *last* byte_limit bytes, minus the fragment
    assert observed["tail"].splitlines() == expected and observed["lines_returned"] == 4
    assert "appended-newest-line" not in observed["tail"], (
        "bytes beyond the measured end were never part of what this read promised")

    # and a file that vanishes under the window is recorded as a failure to read, not as an empty log
    real_open_two = io.open
    shrinking = {"done": False}

    def open_that_shrinks(file, mode="r", *args, **kwargs):
        handle = real_open_two(file, mode, *args, **kwargs)
        if Path(str(file)) != log or "b" not in str(mode):
            return handle

        class _Shrinker:
            def seek(self, offset, whence=0):
                result = handle.seek(offset, whence)
                if not shrinking["done"] and whence == 0:
                    shrinking["done"] = True
                    with real_open_two(log, "r+", encoding="utf-8") as truncate:
                        truncate.truncate(0)
                return result

            def tell(self):
                return handle.tell()

            def read(self, count=-1):
                return handle.read(count)

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return handle.__exit__(*exc_info)

        return _Shrinker()

    monkeypatch.setattr(io, "open", open_that_shrinks)
    shrunk = module._bounded_tail(log, 4, byte_limit=size - 7)
    assert shrunk["state"] == "unreadable" and shrunk["bytes_read"] == 0
    assert shrunk["tail"] == "" and "shrank" in shrunk["reason"]
