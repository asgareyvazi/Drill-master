"""Machine-readable release acceptance report truth-boundary tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _report_module():
    spec = importlib.util.spec_from_file_location(
        "drillmaster_acceptance_report", ROOT / "packaging" / "acceptance_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _release_root(tmp_path: Path, *, bundle: bytes = b"zip", installer: bytes = b"exe",
                  inno_version: str = "6.7.1", smoke_log: str | None = None,
                  sha: str = "a" * 40, identity_source: str = "installed-package-metadata",
                  identity_verified: bool = True, file_version: str = "0.0.0.0",
                  schema: str = "drillmaster-release-artifacts/v2") -> Path:
    """Build a release directory that contains the evidence the report requires."""
    root = tmp_path / "release"
    root.mkdir(parents=True, exist_ok=True)
    (root / "bundle.zip").write_bytes(bundle)
    (root / "DrillMaster-1.2.3-Setup.exe").write_bytes(installer)
    (root / "release-metadata.json").write_text(json.dumps({
        "schema": schema,
        "git_sha": sha,
        "version": "1.2.3",
        "platform": "windows-x64",
        "python": "3.12.1",
        "build_tools": {
            "pip": "24.3.1",
            "pyinstaller": "6.11.1",
            "innosetup_package_version": inno_version,
            "innosetup_compiler_file_version": file_version,
            "innosetup_version_source": identity_source,
            "innosetup_identity_verified": identity_verified,
        },
        "reproducible_build": {"status": "NOT_CLAIMED", "reason": "single build"},
        "artifacts": [
            {"filename": "bundle.zip", "sha256": hashlib.sha256(bundle).hexdigest(),
             "size_bytes": len(bundle)},
            {"filename": "DrillMaster-1.2.3-Setup.exe", "sha256": hashlib.sha256(installer).hexdigest(),
             "size_bytes": len(installer)},
        ],
    }), encoding="utf-8")
    if smoke_log is None:
        smoke_log = "exit_code=0\nlog_generated=true\nsecret_leak_detected=false\nsmoke ok\n"
    (root / "package-smoke.log").write_text(smoke_log, encoding="utf-8")
    return root


def _lifecycle_file(root: Path, status: str = "PASS", *, steps: list | None = None,
                    name: str = "installer-lifecycle.json") -> Path:
    payload = {"status": status,
               "installer_hash_verified": True,
               "steps": steps if steps is not None else [
                   {"name": "verify_installer_hash", "status": "PASS"},
                   {"name": "silent_install", "status": "PASS"},
                   {"name": "installed_smoke", "status": "PASS"},
                   {"name": "silent_uninstall", "status": "PASS"},
               ]}
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _junit(tmp_path: Path, body: str, name: str = "tests.xml") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


PASSING_JUNIT = ('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="1">'
                 '<testcase classname="suite" name="passed" />'
                 '<testcase classname="suite" name="external" ><skipped message="not configured" /></testcase>'
                 '</testsuite></testsuites>')


def test_acceptance_report_separates_automated_gates_from_external_acceptance(tmp_path):
    root = _release_root(tmp_path)
    report = _report_module().build_report(
        metadata_path=root / "release-metadata.json", junit_path=_junit(tmp_path, PASSING_JUNIT),
        source_sha="a" * 40,
        ci={"workflow": "Windows release validation", "run_id": "37607124482",
            "run_url": "https://github.com/o/r/actions/runs/37607124482", "branch": "arena/x"},
    )
    assert report["repository_automation"]["windows_regression_suite"] == {
        "status": "PASS_WITH_SKIPS",
        "collected": 2,
        "passed": 1,
        "skipped": 1,
        "failed": 0,
        "errors": 0,
        "skipped_tests": [{"test": "suite.external", "reason": "not configured"}],
    }
    assert report["repository_automation"]["installer_compilation"]["status"] == "PASS"
    assert report["repository_automation"]["installer_compilation"]["hash_verified"] is True
    assert report["repository_automation"]["frozen_executable_smoke"]["evidence"]["exit_code"] == 0
    assert report["external_acceptance"]["real_ddr_pdf_acceptance"] == "NOT_RUN"
    assert report["external_acceptance"]["real_mineru_acceptance"] == "NOT_RUN"
    assert report["external_acceptance"]["interactive_clean_machine_install"] == "NOT_RUN"
    assert "NOT_REAL_DDR_ACCEPTANCE" in report["external_acceptance"]["synthetic_workbook_scenario"]
    assert report["ci"]["run_id"] == "37607124482"
    assert report["ci"]["workflow"] == "Windows release validation"


def test_acceptance_report_records_run_identity_as_not_provided_for_local_runs(tmp_path):
    root = _release_root(tmp_path)
    report = _report_module().build_report(
        metadata_path=root / "release-metadata.json", junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40
    )
    assert report["ci"] == {"workflow": "NOT_PROVIDED", "run_id": "NOT_PROVIDED",
                            "run_url": "NOT_PROVIDED", "branch": "NOT_PROVIDED",
                            "note": report["ci"]["note"]}


def test_acceptance_report_rejects_sha_mismatch_failed_tests_and_missing_installer(tmp_path):
    root = _release_root(tmp_path)
    metadata_path = root / "release-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    junit_path = _junit(tmp_path, PASSING_JUNIT)
    module = _report_module()

    with pytest.raises(ValueError, match="SHA"):
        module.build_report(metadata_path=metadata_path, junit_path=junit_path, source_sha="d" * 40)
    failing = _junit(tmp_path, '<testsuite><testcase classname="x" name="bad">'
                               '<failure message="broken" /></testcase></testsuite>', name="failed.xml")
    with pytest.raises(ValueError, match="did not pass"):
        module.build_report(metadata_path=metadata_path, junit_path=failing, source_sha="a" * 40)
    metadata["artifacts"] = [item for item in metadata["artifacts"] if item["filename"] != "DrillMaster-1.2.3-Setup.exe"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="portable ZIP and compiled installer"):
        module.build_report(metadata_path=metadata_path, junit_path=junit_path, source_sha="a" * 40)


def test_acceptance_report_requires_artifacts_to_exist_and_match_their_hashes(tmp_path):
    root = _release_root(tmp_path)
    module = _report_module()
    (root / "bundle.zip").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        module.build_report(metadata_path=root / "release-metadata.json",
                            junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)
    root2 = _release_root(tmp_path, sha="b" * 40)
    (root2 / "DrillMaster-1.2.3-Setup.exe").unlink()
    with pytest.raises(ValueError, match="artifact missing"):
        module.build_report(metadata_path=root2 / "release-metadata.json",
                            junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="b" * 40)


@pytest.mark.parametrize("log, expected", [
    ("exit_code=1\nlog_generated=true\nsecret_leak_detected=false\n", "exit_code=0"),
    ("exit_code=0\nlog_generated=false\nsecret_leak_detected=false\n", "wrote no log"),
    ("exit_code=0\nlog_generated=true\nsecret_leak_detected=true\n", "secret leak"),
    ("smoke_timeout=true\n", "timeout or execution error"),
    ("", "exit_code=0"),
])
def test_acceptance_report_refuses_unproven_frozen_smoke(tmp_path, log, expected):
    root = _release_root(tmp_path, smoke_log=log)
    with pytest.raises(ValueError, match=expected):
        _report_module().build_report(metadata_path=root / "release-metadata.json",
                                      junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)


def test_acceptance_report_never_promotes_installer_compilation_to_installation(tmp_path):
    root = _release_root(tmp_path)
    report = _report_module().build_report(
        metadata_path=root / "release-metadata.json", junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40
    )
    assert report["decision"].startswith("WINDOWS_AUTOMATION_PASS")
    assert report["repository_automation"]["source_release_gate"] == "SEPARATE_EXACT_SHA_WORKFLOW_REQUIRED"
    assert report["external_acceptance"]["interactive_upgrade_and_uninstall_data_retention"] == "NOT_RUN"
    assert report["external_acceptance"]["production_database_acceptance"] == "NOT_RUN"
    assert report["external_acceptance"]["operator_business_signoff"] == "NOT_RUN"
    assert report["external_acceptance"]["field_validation"] == "NOT_RUN"


# --- M42.2: streaming verification, tool identity, lifecycle and signing truth ----


def test_report_hashes_large_artifacts_by_streaming_not_whole_file_reads(tmp_path, monkeypatch):
    """A ~300 MB installer must never be materialised to be verified."""
    big = b"z" * (1024 * 1024 + 5)
    root = _release_root(tmp_path, bundle=big, installer=b"i" * (2 * 1024 * 1024))
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: (_ for _ in ()).throw(AssertionError("whole-file read")))
    report = _report_module().build_report(metadata_path=root / "release-metadata.json",
                                           junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)
    identity = report["identity"]
    assert identity["portable_zip_sha256"] == hashlib.sha256(big).hexdigest()
    assert identity["portable_zip_size_bytes"] == len(big)
    assert identity["installer_size_bytes"] == 2 * 1024 * 1024
    assert report["repository_automation"]["artifact_verification"]["status"] == "PASS"


def test_report_detects_a_single_altered_byte_in_a_large_artifact(tmp_path):
    payload = bytearray(b"y" * (1024 * 1024 + 1))
    root = _release_root(tmp_path, bundle=bytes(payload))
    # Flip one byte past the first block: only a genuine streaming re-hash notices it.
    path = root / "bundle.zip"
    with path.open("r+b") as stream:
        stream.seek(len(payload) - 1)
        stream.write(b"\x00")
    with pytest.raises(ValueError, match="hash mismatch"):
        _report_module().build_report(metadata_path=root / "release-metadata.json",
                                       junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)


def test_report_rejects_legacy_metadata_without_a_verified_toolchain_identity(tmp_path):
    root = _release_root(tmp_path, schema="drillmaster-release-artifacts/v1")
    with pytest.raises(ValueError, match="must use drillmaster-release-artifacts/v2"):
        _report_module().build_report(metadata_path=root / "release-metadata.json",
                                      junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)


@pytest.mark.parametrize("mutation", [
    {"inno_version": "0.0.0.0"},
    {"inno_version": ""},
    {"inno_version": "NOT_BUILT"},
    {"inno_version": "6.7"},
    {"inno_version": "latest"},
    {"identity_verified": False},
    {"identity_source": "operator-attested", "identity_verified": True},
])
def test_report_rejects_unverified_or_inconsistent_innosetup_identity(tmp_path, mutation):
    root = _release_root(tmp_path, **mutation)
    with pytest.raises(ValueError, match="innosetup|Inno Setup|verified"):
        _report_module().build_report(metadata_path=root / "release-metadata.json",
                                      junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)


def test_report_rejects_expected_and_observed_identity_disagreement(tmp_path):
    root = _release_root(tmp_path, inno_version="6.7.1")
    with pytest.raises(ValueError, match="identity disagreement"):
        _report_module().build_report(metadata_path=root / "release-metadata.json",
                                      junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                      expected_innosetup_version="6.4.3")
    # The pinned value that agrees is accepted and published in the report.
    report = _report_module().build_report(metadata_path=root / "release-metadata.json",
                                           junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                           expected_innosetup_version="6.7.1")
    assert report["identity"]["innosetup_package_version"] == "6.7.1"
    assert report["identity"]["innosetup_version_source"] == "installed-package-metadata"
    # The raw executable resource stays visible as a diagnostic, clearly labelled.
    assert report["identity"]["innosetup_compiler_file_version"] == "0.0.0.0"


def test_report_records_both_artifact_names_hashes_and_sizes(tmp_path):
    root = _release_root(tmp_path, bundle=b"portable-zip-bytes", installer=b"setup-exe")
    report = _report_module().build_report(metadata_path=root / "release-metadata.json",
                                           junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)
    identity = report["identity"]
    assert identity["installer_filename"] == "DrillMaster-1.2.3-Setup.exe"
    assert identity["installer_sha256"] == hashlib.sha256(b"setup-exe").hexdigest()
    assert identity["installer_size_bytes"] == len(b"setup-exe")
    assert identity["portable_zip_filename"] == "bundle.zip"
    assert identity["portable_zip_sha256"] == hashlib.sha256(b"portable-zip-bytes").hexdigest()
    assert identity["portable_zip_size_bytes"] == len(b"portable-zip-bytes")
    # An inner bundle path must never be published as if it were the outer archive.
    assert "/" not in identity["portable_zip_filename"] and "\\" not in identity["portable_zip_filename"]


def test_report_detects_a_recorded_size_disagreement(tmp_path):
    root = _release_root(tmp_path)
    metadata_path = root / "release-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["artifacts"][0]["size_bytes"] += 1
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="size mismatch"):
        _report_module().build_report(metadata_path=metadata_path, junit_path=_junit(tmp_path, PASSING_JUNIT),
                                       source_sha="a" * 40)


def test_installed_lifecycle_is_only_claimed_when_its_evidence_agrees(tmp_path):
    module = _report_module()
    root = _release_root(tmp_path)
    junit = _junit(tmp_path, PASSING_JUNIT)
    without = module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                                  source_sha="a" * 40)
    automation = without["repository_automation"]["installed_application_lifecycle"]
    assert automation["status"] == "NOT_RUN"
    assert "not a claim" in automation["note"] or "not interactive" in automation["note"]
    assert "INSTALLED_LIFECYCLE_NOT_RUN" in without["decision"]
    with pytest.raises(ValueError, match="lifecycle evidence is required"):
        module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                           source_sha="a" * 40, require_lifecycle=True)
    path = _lifecycle_file(root)
    passed = module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                                source_sha="a" * 40, lifecycle_report_path=path, require_lifecycle=True)
    assert passed["repository_automation"]["installed_application_lifecycle"]["status"] == "PASS"
    assert "INSTALLED_LIFECYCLE_PASS" in passed["decision"]
    assert passed["identity"]["installed_lifecycle_status"] == "PASS"


@pytest.mark.parametrize("payload, fragment", [
    ({"status": "PASS", "installer_hash_verified": True, "steps": [{"name": "silent_install", "status": "FAIL"}]},
     "non-passing steps"),
    ({"status": "PASS", "installer_hash_verified": False, "steps": [{"name": "silent_install", "status": "PASS"}]},
     "without having verified"),
    ({"status": "MAGICAL", "installer_hash_verified": True, "steps": [{"name": "x", "status": "PASS"}]},
     "unknown status"),
    ({"status": "PASS", "installer_hash_verified": True, "steps": []}, "lists no steps"),
])
def test_lifecycle_evidence_cannot_claim_more_than_it_proves(tmp_path, payload, fragment):
    root = _release_root(tmp_path)
    (root / "installer-lifecycle.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=fragment):
        _report_module().build_report(metadata_path=root / "release-metadata.json",
                                      junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                      lifecycle_report_path=root / "installer-lifecycle.json")


def test_a_failing_lifecycle_is_reported_without_being_softened(tmp_path):
    root = _release_root(tmp_path)
    path = _lifecycle_file(root, "FAIL", steps=[{"name": "silent_uninstall", "status": "FAIL"}])
    report = _report_module().build_report(metadata_path=root / "release-metadata.json",
                                           junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                           lifecycle_report_path=path, require_lifecycle=True)
    assert report["repository_automation"]["installed_application_lifecycle"]["status"] == "FAIL"
    assert report["identity"]["installed_lifecycle_status"] == "FAIL"
    assert "INSTALLED_LIFECYCLE_PASS" not in report["decision"]


def test_signing_status_is_recorded_as_observed_never_inferred(tmp_path):
    module = _report_module()
    root = _release_root(tmp_path)
    junit = _junit(tmp_path, PASSING_JUNIT)
    absent = module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                                 source_sha="a" * 40)
    assert absent["repository_automation"]["code_signing"]["status"] == "NOT_VERIFIED"
    (root / "signing-status.json").write_text(json.dumps({
        "method": "Windows Get-AuthenticodeSignature", "signing_configured_in_build": False,
        "credentials_available": False, "prerequisite": "an owner-controlled code-signing certificate",
        "files": [{"filename": "DrillMaster-1.2.3-Setup.exe", "status": "NotSigned", "signer": None}],
    }), encoding="utf-8")
    unsigned = module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                                   source_sha="a" * 40,
                                   signing_report_path=root / "signing-status.json")
    signing = unsigned["repository_automation"]["code_signing"]
    assert signing["status"] == "UNSIGNED"
    assert signing["signing_configured_in_build"] is False
    assert unsigned["identity"]["signing_status"] == "UNSIGNED"
    assert unsigned["decision"].startswith("WINDOWS_AUTOMATION_PASS")
    (root / "signing-status.json").write_text(json.dumps({"files": []}), encoding="utf-8")
    unknown = module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                                  source_sha="a" * 40, signing_report_path=root / "signing-status.json")
    assert unknown["identity"]["signing_status"] == "UNKNOWN"


def test_report_rejects_incomplete_or_fabricated_ci_identity(tmp_path):
    module = _report_module()
    root = _release_root(tmp_path)
    base = {"metadata_path": root / "release-metadata.json", "junit_path": _junit(tmp_path, PASSING_JUNIT),
            "source_sha": "a" * 40}
    with pytest.raises(ValueError, match="incomplete"):
        module.build_report(**base, ci={"workflow": "Windows release validation"})
    with pytest.raises(ValueError, match="numeric"):
        module.build_report(**base, ci={"workflow": "w", "run_id": "run-42", "run_url": "u", "branch": "b"})
    with pytest.raises(ValueError, match="run id"):
        module.build_report(**base, ci={"workflow": "w", "run_id": "42", "run_url": "https://x/actions/runs/43",
                                       "branch": "b"})
    report = module.build_report(**base, ci={"workflow": "w", "run_id": "42",
                                            "run_url": "https://x/actions/runs/42", "branch": "b"})
    assert report["ci"]["run_url"].endswith("/actions/runs/42")
    with pytest.raises(ValueError, match="full lowercase commit hash"):
        module.build_report(metadata_path=root / "release-metadata.json",
                            junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="deadbeef")


def test_report_publishes_the_required_field_set_with_vocabulary_statuses(tmp_path):
    module = _report_module()
    root = _release_root(tmp_path)
    _lifecycle_file(root)
    (root / "signing-status.json").write_text(json.dumps(
        {"files": [{"filename": "DrillMaster-1.2.3-Setup.exe", "status": "NotSigned"}]}), encoding="utf-8")
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                 lifecycle_report_path=root / "installer-lifecycle.json")
    flat = module._flatten_for_verification(report)
    assert set(module.REQUIRED_REPORT_FIELDS) <= set(flat)
    # Counts may legitimately be zero; nothing in the contract may be absent.
    empty = [field for field in module.REQUIRED_REPORT_FIELDS if flat[field] is None]
    assert not empty, f"unpopulated contract fields: {empty}"
    module.verify_report_fields(report)
    for value in (report["identity"]["installed_lifecycle_status"], report["identity"]["signing_status"],
                  report["repository_automation"]["installer_compilation"]["status"]):
        assert value in module.STATUS_VOCABULARY
    assert report["schema"] == "drillmaster-windows-acceptance/v2"


def test_verify_report_fields_reports_omissions_and_bad_statuses():
    module = _report_module()
    report = {"identity": {"installed_lifecycle_status": "GREAT"},
              "repository_automation": {"windows_regression_suite": {}, "frozen_executable_smoke": {},
                                        "installer_compilation": {}, "code_signing": {}}}
    with pytest.raises(ValueError, match="missing required fields"):
        module.verify_report_fields(report)
