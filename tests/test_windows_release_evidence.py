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
                 leak_value: str = "", write_into_install_dir: bool = False,
                 signature_status: str = "NotSigned", signer_subject: str = "",
                 keep_sentinel: bool = True):
        self.install_exit_code = install_exit_code
        self.uninstall_exit_code = uninstall_exit_code
        self.product_version = product_version
        self.smoke_exit_code = smoke_exit_code
        self.smoke_output = smoke_output
        self.uninstall_removes = uninstall_removes
        self.leak_value = leak_value
        self.write_into_install_dir = write_into_install_dir
        self.signature_status = signature_status
        self.signer_subject = signer_subject
        self.keep_sentinel = keep_sentinel
        self.calls: list[list[str]] = []
        self.envs: list[dict | None] = []

    def __call__(self, argv, environment, cwd, timeout):
        self.calls.append(list(argv))
        self.envs.append(dict(environment) if environment else None)
        program = Path(argv[0]).name.lower()
        if program == "powershell.exe":
            script = argv[-1]
            target = str((environment or {})["DRILLMASTER_TARGET_PATH"])
            assert target, "the queried path must be passed out of band, never interpolated"
            if "Get-AuthenticodeSignature" in script:
                payload = {"Status": self.signature_status, "StatusMessage": "No signature is present.",
                           "SignerSubject": self.signer_subject or None}
            else:
                payload = {"FileVersion": self.product_version, "ProductVersion": self.product_version}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        if program.endswith("setup.exe"):
            install_dir = _arg_value(argv, "/DIR=")
            install_dir.mkdir(parents=True, exist_ok=True)
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
            log_dir = Path((environment or {})["DRILLMASTER_LOG_DIR"])
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "drillmaster.log").write_text("INFO application smoke complete\n", encoding="utf-8")
            if self.write_into_install_dir:
                # A frozen application writing next to itself is the regression guarded here.
                (Path(argv[0]).parent / "drillmaster.db").write_bytes(b"leaked into the install tree")
            output = self.smoke_output
            if self.leak_value:
                output += f"\ncould not authenticate with {self.leak_value}\n"
            return SimpleNamespace(returncode=self.smoke_exit_code, stdout=output, stderr="")
        raise AssertionError(f"unexpected command: {argv}")


def _arg_value(argv, prefix: str) -> Path:
    for item in argv:
        if item.startswith(prefix):
            return Path(item[len(prefix):])
    raise AssertionError(f"{prefix} missing from {argv}")


def _release(root: Path, *, exe_bytes: bytes = b"installer-bytes") -> tuple[Path, Path, str]:
    installer = root / "DrillMaster-1.0.0-Setup.exe"
    installer.parent.mkdir(parents=True, exist_ok=True)
    installer.write_bytes(exe_bytes)
    digest = hashlib.sha256(exe_bytes).hexdigest()
    metadata = root / "release-metadata.json"
    metadata.write_text(json.dumps({
        "schema": "drillmaster-release-artifacts/v2",
        "artifacts": [{"filename": installer.name, "sha256": digest, "size_bytes": len(exe_bytes)}],
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
    }
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
    assert report["signing_configured_in_build"] is False
    assert report["credentials_available"] is False
    assert "code-signing certificate" in report["prerequisite"]
    assert report["files"][0]["filename"] == "DrillMaster-1.0.0-Setup.exe"
    assert report["files"][0]["sha256"] == hashlib.sha256(b"installer-bytes").hexdigest()
    assert "signer" not in report["files"][0], "an unsigned artifact has no signer to name"


def test_signing_status_records_the_signer_when_valid(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost(
        signature_status="Valid", signer_subject="CN=DrillMaster Inc., O=DrillMaster Inc."))
    assert report["status"] == "PASS"
    assert report["files"][0]["signer"].startswith("CN=DrillMaster Inc.")


def test_signing_status_is_unknown_for_a_missing_artifact(tmp_path):
    module = _evidence_module()
    _, metadata, _ = _release(tmp_path / "release")
    (tmp_path / "release" / "DrillMaster-1.0.0-Setup.exe").unlink()
    report = module.run_signing(release_metadata_path=metadata, runner=FakeHost())
    assert report["status"] == "UNKNOWN"
    assert report["files"][0]["status_message"] == "artifact missing from the release directory"


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
