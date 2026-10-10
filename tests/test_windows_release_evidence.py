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
import json
import sys
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
                 run_returncode: int | None = None, raise_on_call: int | None = None):
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
                # The capability probe, answered before any file is queried.
                payload = {"ps_version": "5.1.20348.2402", "cmdlet": self.signature_cmdlet,
                           "module": "Microsoft.PowerShell.Security"}
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
        if program == "unins000.exe":
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


def _run(root: Path, host: FakeHost, **overrides):
    module = _evidence_module()
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
        return SimpleNamespace(returncode=1, stdout="", stderr="Get-AuthenticodeSignature : Access denied")

    report = module.run_signing(release_metadata_path=metadata, runner=host)
    assert report["status"] == "UNKNOWN"
    assert "powershell exit 1" in report["files"][0]["status_message"]


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
    assert report["harness"] == {"query_command": "available", "powershell_version": "5.1.20348.2402",
                                "signature_command_module": "Microsoft.PowerShell.Security",
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
