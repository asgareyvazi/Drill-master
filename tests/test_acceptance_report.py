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
        "artifact_scope": "outer release artifacts; inner bundle files inside the portable ZIP "
                          "are not individually hashed here",
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
                    name: str = "installer-lifecycle.json",
                    installer: str = "DrillMaster-1.2.3-Setup.exe",
                    sha256: str = hashlib.sha256(b"exe").hexdigest()) -> Path:
    payload = {"status": status,
               "installer_filename": installer,
               "installer_sha256": sha256,
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


def _signing_document(root: Path, *, mutate=None, name: str = "signing-status.json",
                      installer_status: str = "UNSIGNED", installer_raw: str = "NotSigned",
                      app_status: str = "UNSIGNED", app_raw: str = "NotSigned") -> Path:
    """Write a signing record that satisfies the published v2 contract for this release dir.

    Fixtures are built valid on purpose: each test below then perturbs exactly one axis, so a
    refusal can only be about the contradiction the test introduced.
    """
    import sys

    sys.path.insert(0, str(ROOT / "packaging"))
    from release_metadata import aggregate_signing_status

    manifest = root / "release-metadata.json"
    entries = {item["filename"]: item for item in json.loads(manifest.read_text(encoding="utf-8"))["artifacts"]}
    bundle = next(name for name in entries if name.lower().endswith(".zip"))
    installer = next(name for name in entries if name.lower().endswith("-setup.exe"))
    reason = "No signature is present." if installer_status != "PASS" else "Signature verified."
    files = [
        {"filename": installer, "status": installer_status, "raw_status": installer_raw,
         "raw_status_recognized": True, "status_message": reason, "signature_bearing": True,
         "provenance": "compiled installer in the release directory",
         "sha256": entries[installer]["sha256"], "size_bytes": entries[installer]["size_bytes"]},
        {"filename": "DrillMaster.exe", "status": app_status, "raw_status": app_raw,
         "raw_status_recognized": True, "status_message": reason, "signature_bearing": True,
         "provenance": f"extracted from {bundle}",
         "sha256": hashlib.sha256(b"frozen executable").hexdigest(), "size_bytes": 17,
         "container_archive": bundle, "container_archive_sha256": entries[bundle]["sha256"],
         "container_member": f"DrillMaster-1.2.3/{Path('DrillMaster.exe')}"},
        {"filename": bundle, "status": "NOT_APPLICABLE", "raw_status": "",
         "raw_status_recognized": True, "signature_bearing": False,
         "status_message": "container archive; Authenticode applies to the executables it carries",
         "provenance": "published release artifact", "sha256": entries[bundle]["sha256"],
         "size_bytes": entries[bundle]["size_bytes"]},
    ]
    payload = {"schema": "drillmaster-signing-status/v2",
               "method": "Windows Get-AuthenticodeSignature",
               "policy": "unsigned publication is the current release policy",
               "status": aggregate_signing_status(files), "files": files,
               "examined_count": 2, "archive_count": 1,
               "signing_configured_in_build": False, "credentials_available": False,
               "credential_environment_variables": [],
               "prerequisite": "an owner-controlled code-signing certificate",
               "release_metadata_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
               "source_sha": "a" * 40,
               "harness": {"query_command": "available", "powershell_version": "5.1.20348.2402",
                           "signature_command_module": "Microsoft.PowerShell.Security"}}
    if mutate is not None:
        mutate(payload)
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
    assert absent["repository_automation"]["code_signing"]["artifact_binding"] == "NOT_AVAILABLE"
    # NOT_VERIFIED describes an absent record; it is never a per-file or aggregate Authenticode
    # finding, so a reader cannot mistake "nobody asked" for "Windows answered".
    assert all(item["status"] != "NOT_VERIFIED" for item in absent["repository_automation"]["code_signing"]["files"])

    _signing_document(root)
    unsigned = module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                                   source_sha="a" * 40, signing_report_path=root / "signing-status.json")
    signing = unsigned["repository_automation"]["code_signing"]
    assert signing["status"] == "UNSIGNED"
    assert signing["schema"] == "drillmaster-signing-status/v2"
    assert signing["signing_configured_in_build"] is False
    assert signing["artifact_binding"] == "VERIFIED"
    assert unsigned["identity"]["signing_status"] == "UNSIGNED"
    assert unsigned["decision"].startswith("WINDOWS_AUTOMATION_PASS")
    # An unsigned build passes the internal gate while the trust boundary stays a finding.
    assert unsigned["external_acceptance"]["operator_business_signoff"] == "NOT_RUN"

    _signing_document(root, installer_status="PASS", installer_raw="Valid",
                      app_status="PASS", app_raw="Valid")
    signed = module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                                source_sha="a" * 40, signing_report_path=root / "signing-status.json")
    assert signed["repository_automation"]["code_signing"]["status"] == "PASS"

    def unexplainable_unknown(payload):
        payload["status"] = "UNKNOWN"
        for item in payload["files"]:
            if not item["signature_bearing"]:
                continue   # a container archive is never an unknown; it is not applicable
            item["status"] = "UNKNOWN"
            item["raw_status"] = ""
            item["status_message"] = "powershell exited 0 without reporting Status: Access is denied"

    _signing_document(root, mutate=unexplainable_unknown)
    unknown = module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                                  source_sha="a" * 40, signing_report_path=root / "signing-status.json")
    assert unknown["identity"]["signing_status"] == "UNKNOWN"
    assert "Access is denied" in unknown["repository_automation"]["code_signing"]["files"][0]["status_message"]


def test_report_keeps_the_diagnostics_that_explain_a_signature_state(tmp_path):
    """Dropping the reason is how a published finding becomes undiagnosable after the run."""
    module = _report_module()
    root = _release_root(tmp_path)
    _signing_document(root)
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                 signing_report_path=root / "signing-status.json")
    signing = report["repository_automation"]["code_signing"]
    assert signing["harness"]["query_command"] == "available"
    assert signing["harness"]["powershell_version"] == "5.1.20348.2402"
    installer_row = signing["files"][0]
    assert installer_row["raw_status"] == "NotSigned"
    assert installer_row["status"] == "UNSIGNED"
    assert "No signature is present." in installer_row["status_message"]
    inner_row = next(item for item in signing["files"] if item["filename"] == "DrillMaster.exe")
    assert inner_row["container_member"].startswith("DrillMaster-1.2.3/")
    assert inner_row["container_archive_sha256"] == report["identity"]["portable_zip_sha256"]
    assert inner_row["provenance"].startswith("extracted from ")


def test_a_run_that_did_not_execute_is_recorded_as_not_run(tmp_path):
    """A NOT_RUN record must stay distinct from UNKNOWN and from an absent document."""
    module = _report_module()
    root = _release_root(tmp_path)

    def not_run(payload):
        payload.update({"status": "NOT_RUN", "files": [], "examined_count": 0, "archive_count": 0,
                        "reason": "Authenticode verification requires a Windows host"})
        payload.pop("release_metadata_sha256")
        payload.pop("source_sha")

    _signing_document(root, mutate=not_run)
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                 signing_report_path=root / "signing-status.json")
    signing = report["repository_automation"]["code_signing"]
    assert signing["status"] == "NOT_RUN"
    assert signing["files"] == []
    assert "Windows host" in signing["reason"]


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(status="PASS"), "contradicts the per-file findings"),
    (lambda d: d.update(status="FAIL"), "contradicts the per-file findings"),
    (lambda d: d.update(status="UNSIGNED", files=[dict(d["files"][0], status="PASS"),
                                                 dict(d["files"][1], status="FAIL")]),
     "contradicts the per-file findings"),
    (lambda d: d.update(status="UNKNOWN"), "contradicts the per-file findings"),
    (lambda d: d.update(schema="drillmaster-signing-status/v1"), "must use schema"),
    (lambda d: d.update(somebody="else"), r"field\(s\) outside drillmaster-signing-status/v2"),
    (lambda d: d.update(status="NOT_VERIFIED"), "outside the vocabulary"),
    (lambda d: (d["files"][0].update(status="NOT_VERIFIED"), d.update(status="UNKNOWN")),
     "outside the per-file vocabulary"),
    (lambda d: d["files"][0].pop("status_message"), r"is missing field\(s\)"),
    (lambda d: d.update(files=[d["files"][0], dict(d["files"][0])]), "duplicate signing file record"),
    (lambda d: d["files"][0].update(signature_bearing=False), "contradicts status"),
    (lambda d: d["files"][0].update(status="UNKNOWN", status_message=""), "UNKNOWN without a reason"),
    (lambda d: d["files"][0].update(status_message="x" * 700), "unbounded diagnostic"),
    (lambda d: d["files"][0].update(sha256="deadbeef"), "malformed SHA-256"),
    (lambda d: d["files"][2].update(status="UNSIGNED", signature_bearing=True), "examined_count"),
    (lambda d: (d.update(files=d["files"][1:], status="UNSIGNED", examined_count=1, archive_count=1)),
     "does not record the shipped installer"),
    (lambda d: d.update(files=[d["files"][0], d["files"][2]], status="UNSIGNED", examined_count=1,
                        archive_count=1), "never examines the executable shipped inside"),
    (lambda d: d["files"][1].update(container_archive="other.zip"), "not to the published"),
    (lambda d: d["files"][1].update(container_archive_sha256="0" * 64),
     "archive bytes this report did not verify"),
    (lambda d: d["files"][1].update(container_member="DrillMaster-1.2.3/Other.exe"),
     "names archive member"),
    (lambda d: d["files"][1].pop("container_member"), "incomplete container provenance"),
    (lambda d: d["files"][0].update(sha256="0" * 64), "the record is stale"),
    (lambda d: d.update(release_metadata_sha256="f" * 64), "not bound to the release metadata"),
    (lambda d: d.update(source_sha="b" * 40), "produced for source"),
    (lambda d: d.update(files="a.exe"), "'files' must be a list"),
    (lambda d: d.update(files=["a.exe"]), "must be a JSON object"),
    (lambda d: d["files"][0].pop("signature_bearing"), r"is missing field\(s\)"),
])
def test_report_refuses_signing_evidence_it_cannot_interpret(tmp_path, mutate, fragment):
    """Every shape of missing, malformed, contradictory, stale or inconsistent record.

    The report refuses rather than re-deriving its own answer: two rules for one vocabulary is
    how a gate starts disagreeing with the tool that produced the evidence.
    """
    module = _report_module()
    root = _release_root(tmp_path)
    _signing_document(root, mutate=mutate)
    with pytest.raises(module.ReportError, match=fragment):
        module.build_report(metadata_path=root / "release-metadata.json",
                            junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                            signing_report_path=root / "signing-status.json")


def test_a_malformed_per_file_status_is_refused_not_coerced(tmp_path):
    """Coercing garbage into UNKNOWN here would hide a malformed record behind a real state.

    Normalising a raw Windows answer is the querying tool's job, where the answer is known; the
    report's job is to refuse a document that does not meet the contract.
    """
    module = _report_module()
    root = _release_root(tmp_path)
    _signing_document(root, mutate=lambda d: d["files"][0].update(status="   "))
    with pytest.raises(module.ReportError, match="outside the per-file vocabulary"):
        module.build_report(metadata_path=root / "release-metadata.json",
                            junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                            signing_report_path=root / "signing-status.json")
    _signing_document(root, mutate=lambda d: d["files"][0].update(status={"raw": "Valid"}))
    with pytest.raises(module.ReportError, match="outside the per-file vocabulary"):
        module.build_report(metadata_path=root / "release-metadata.json",
                            junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                            signing_report_path=root / "signing-status.json")


def test_unsigned_build_still_passes_the_gate_but_keeps_the_trust_finding(tmp_path):
    """The policy the contract encodes, asserted from the published record itself."""
    module = _report_module()
    root = _release_root(tmp_path)
    _signing_document(root)
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                 signing_report_path=root / "signing-status.json", require_signing=True)
    assert report["repository_automation"]["code_signing"]["status"] == "UNSIGNED"
    # the record's own policy statement is carried through verbatim, not paraphrased away
    assert report["repository_automation"]["code_signing"]["policy"] == \
        "unsigned publication is the current release policy"
    assert report["decision"].startswith("WINDOWS_AUTOMATION_PASS")
    # an unknown is never relabelled unsigned
    _signing_document(root, installer_status="UNKNOWN", installer_raw="",
                      app_status="UNKNOWN", app_raw="")
    unknown = module.build_report(metadata_path=root / "release-metadata.json",
                                   junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                   signing_report_path=root / "signing-status.json")
    assert unknown["repository_automation"]["code_signing"]["status"] == "UNKNOWN"


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


def test_streaming_hash_matches_the_reference_digest_for_edge_sizes(tmp_path):
    """Empty, exactly-one-block and multi-block artifacts must all verify correctly."""
    import hashlib

    module = _report_module()
    for payload in (b"", b"z" * 1024, b"z" * (1024 * 1024), b"z" * (1024 * 1024 + 7),
                    b"z" * (3 * 1024 * 1024)):
        root = _release_root(tmp_path / f"edge{len(payload)}", bundle=payload)
        report = module.build_report(metadata_path=root / "release-metadata.json",
                                      junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)
        assert report["identity"]["portable_zip_sha256"] == hashlib.sha256(payload).hexdigest()
        assert report["identity"]["portable_zip_size_bytes"] == len(payload)
        assert report["repository_automation"]["portable_bundle_build"]["hash_verified"] is True


def test_release_tooling_keeps_exactly_one_streaming_hash_implementation():
    """A second hash loop is how a report and a manifest start disagreeing."""
    report_source = (ROOT / "packaging" / "acceptance_report.py").read_text(encoding="utf-8")
    metadata_source = (ROOT / "packaging" / "release_metadata.py").read_text(encoding="utf-8")
    lifecycle_source = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    assert "from release_metadata import" in report_source and "sha256_file" in report_source
    assert "read_bytes()" not in report_source, "the report must not load an artifact into memory"
    for name, source in (("acceptance_report.py", report_source), ("windows_release_evidence.py", lifecycle_source)):
        assert "hashlib.sha256(" not in source, f"{name} would be a second hashing implementation"
    assert "hashlib.sha256()" in metadata_source, "the single implementation lives in release_metadata"
    assert metadata_source.count("def sha256_file") == 1


def test_lifecycle_pass_must_be_bound_to_the_verified_installer_bytes(tmp_path):
    """A PASS for some other file is not evidence about the shipped artifact."""
    module = _report_module()
    root = _release_root(tmp_path)
    junit = _junit(tmp_path, PASSING_JUNIT)
    good = _lifecycle_file(root)
    assert module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                               source_sha="a" * 40, lifecycle_report_path=good)[
        "repository_automation"]["installed_application_lifecycle"]["installer_sha256"] == \
        hashlib.sha256(b"exe").hexdigest()
    wrong_hash = _lifecycle_file(root, name="installer-lifecycle-wrong-hash.json", sha256="0" * 64)
    with pytest.raises(ValueError, match="not bound to the verified installer"):
        module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                           source_sha="a" * 40, lifecycle_report_path=wrong_hash)
    wrong_name = _lifecycle_file(root, name="installer-lifecycle-other-file.json",
                                installer="DrillMaster-1.0.0-Setup.exe")
    with pytest.raises(ValueError, match="not bound to the verified installer"):
        module.build_report(metadata_path=root / "release-metadata.json", junit_path=junit,
                           source_sha="a" * 40, lifecycle_report_path=wrong_name)


# --- evidence-document contract: the manifest and the signing record are validated, not guessed ---

def _mutate_metadata(root: Path, mutate) -> Path:
    payload = json.loads((root / "release-metadata.json").read_text(encoding="utf-8"))
    mutate(payload)
    path = root / "release-metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("mutate, fragment", [
    (lambda p: p.update({"signed_by_default": True}), "outside"),
    (lambda p: p.pop("artifact_scope"), "missing required field"),
    (lambda p: p.pop("python"), "missing required field"),
    (lambda p: p["artifacts"].append(dict(p["artifacts"][1])), "duplicate artifact entry"),
    (lambda p: p["artifacts"][0].update({"signature": "none"}), "unknown field"),
    (lambda p: p["artifacts"][0].pop("size_bytes"), "missing field"),
    (lambda p: p["artifacts"][0].update({"sha256": "5ae1e2"}), "malformed SHA-256"),
    (lambda p: p["artifacts"][0].update({"sha256": "A" * 64}), "malformed SHA-256"),
    (lambda p: p["artifacts"][0].update({"size_bytes": -1}), "negative"),
    (lambda p: p["artifacts"][0].update({"size_bytes": "12"}), "non-integer"),
    (lambda p: p["build_tools"].pop("innosetup_identity_verified"), "build_tools is missing"),
    (lambda p: p.update({"artifacts": []}), "non-empty list"),
])
def test_report_refuses_a_manifest_deviating_from_its_published_contract(tmp_path, mutate, fragment):
    module = _report_module()
    root = _release_root(tmp_path)
    metadata = _mutate_metadata(root, mutate)
    junit = _junit(tmp_path, PASSING_JUNIT)
    with pytest.raises(module.ReportError, match=fragment):
        module.build_report(metadata_path=metadata, junit_path=junit, source_sha="a" * 40)


def test_report_refuses_a_manifest_that_is_not_an_object(tmp_path):
    module = _report_module()
    root = _release_root(tmp_path)
    (root / "release-metadata.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(module.ReportError, match="published contract"):
        module.build_report(metadata_path=root / "release-metadata.json",
                            junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)


def test_report_accepts_the_document_the_generator_itself_publishes(tmp_path):
    """The validator must not reject its own producer's output, including zero-length artifacts."""
    import hashlib as _hashlib

    release_meta = importlib.import_module("release_metadata")
    root = tmp_path / "generated"
    root.mkdir()
    (root / "bundle.zip").write_bytes(b"")
    (root / "DrillMaster-9.9.9-Setup.exe").write_bytes(b"installer")
    path = release_meta.write_manifest(
        root, source_sha="a" * 40, version="9.9.9", python_version="3.12.10", pyinstaller_version="6.11.1",
        pip_version="25.3", innosetup_package_version="6.7.1", innosetup_file_version="0.0.0.0",
        innosetup_version_source="installed-package-metadata", bundle_zip=root / "bundle.zip",
        installer=root / "DrillMaster-9.9.9-Setup.exe")
    documented = release_meta.validate_document(json.loads(path.read_text(encoding="utf-8")))
    assert {Path(str(item["filename"])).name for item in documented["artifacts"]} == {
        "bundle.zip", "DrillMaster-9.9.9-Setup.exe"}
    assert all(len(item["sha256"]) == 64 for item in documented["artifacts"])
    assert _hashlib.sha256(b"").hexdigest() in {item["sha256"] for item in documented["artifacts"]}


def test_a_required_signing_record_cannot_be_absent(tmp_path):
    """A skipped signing step must never read as a successful unsigned build."""
    module = _report_module()
    root = _release_root(tmp_path)
    with pytest.raises(module.ReportError, match="required but missing"):
        module.build_report(metadata_path=root / "release-metadata.json", junit_path=_junit(tmp_path, PASSING_JUNIT),
                            source_sha="a" * 40, require_signing=True)
    # without the requirement the absence is still recorded honestly, never promoted
    absent = module.build_report(metadata_path=root / "release-metadata.json",
                                junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)
    assert absent["repository_automation"]["code_signing"]["status"] == "NOT_VERIFIED"
    assert absent["repository_automation"]["code_signing"]["files"] == []


def test_report_cli_exit_codes_follow_the_documented_contract(tmp_path, capsys):
    module = _report_module()
    root = _release_root(tmp_path)
    good = root / "acceptance-report.json"
    argv = ["--metadata", str(root / "release-metadata.json"), "--junit", str(_junit(tmp_path, PASSING_JUNIT)),
            "--source-sha", "a" * 40, "--output", str(good)]
    assert module.main(argv) == 0 and good.is_file()
    _signing_document(root)
    assert module.main(argv + ["--signing-report", str(root / "signing-status.json"), "--require-signing"]) == 0
    missing = root / "nothing.json"
    assert module.main(argv + ["--signing-report", str(missing), "--require-signing"]) == 1
    captured = capsys.readouterr()
    assert "required but missing" in captured.err and "Traceback" not in captured.err


def test_artifact_verification_keeps_the_four_provenance_claims_apart(tmp_path):
    """Build-produced, recomputed-here, re-measured-in-CI and operator-verified are different claims."""
    module = _report_module()
    root = _release_root(tmp_path)
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)
    verification = report["repository_automation"]["artifact_verification"]
    assert verification["status"] == "PASS"
    assert verification["independent_reverification"] == "NOT_VERIFIED"
    assert "packaging/build_windows.ps1" in verification["provenance"]
    assert "not byte-integrity proof" in verification["operator_verification_path"]
    module.verify_report_fields(report)
    report["repository_automation"]["artifact_verification"].pop("independent_reverification")
    with pytest.raises(module.ReportError, match="artifact_independent_reverification"):
        module.verify_report_fields(report)


def test_a_step_that_ran_and_failed_cannot_read_as_not_run(tmp_path):
    """The gate's own failure mode: a lifecycle FAIL must not be published as PASS + NOT_RUN."""
    module = _report_module()
    root = _release_root(tmp_path)
    _lifecycle_file(root, "FAIL", steps=[{"name": "installed_smoke", "status": "FAIL"}])
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                 lifecycle_report_path=root / "installer-lifecycle.json",
                                 require_lifecycle=True)
    assert report["decision"].startswith("WINDOWS_AUTOMATION_FAIL")
    assert "INSTALLED_LIFECYCLE_FAIL" in report["decision"]
    assert "WINDOWS_AUTOMATION_PASS" not in report["decision"]
    assert report["decision_basis"]["blocking"] == ["INSTALLED_LIFECYCLE"]
    assert report["decision_basis"]["mandatory_statuses"]["FROZEN_SMOKE"] == "PASS"


def test_an_unrun_mandatory_step_is_incomplete_rather_than_blocked(tmp_path):
    """Not run and failed stay distinct: one is a gap in coverage, the other is a verdict."""
    module = _report_module()
    root = _release_root(tmp_path)
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40)
    assert report["decision"].startswith("WINDOWS_AUTOMATION_PASS")
    assert "INSTALLED_LIFECYCLE_NOT_RUN" in report["decision"]
    assert report["decision_basis"]["not_run"] == ["INSTALLED_LIFECYCLE"]
    assert report["decision_basis"]["blocking"] == []


def test_a_full_pass_publishes_every_mandatory_dimension(tmp_path):
    module = _report_module()
    root = _release_root(tmp_path)
    _lifecycle_file(root, "PASS")
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                 lifecycle_report_path=root / "installer-lifecycle.json")
    for name in ("INSTALLED_LIFECYCLE_PASS", "FROZEN_SMOKE_PASS", "INSTALLER_COMPILATION_PASS"):
        assert name in report["decision"], name
