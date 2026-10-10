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


@pytest.mark.parametrize("payload, fragment", [
    ({"status": "SIGNED", "files": [{"filename": "a.exe", "status": "Valid"}]}, "outside the published vocabulary"),
    ({"status": "PASS", "files": {"a.exe": "Valid"}}, "must be a list"),
    ({"status": "PASS", "files": [{"filename": "a.exe", "status": {"raw": "Valid"}}]}, "must be a string or null"),
])
def test_report_refuses_signing_evidence_it_cannot_interpret(tmp_path, payload, fragment):
    module = _report_module()
    root = _release_root(tmp_path)
    (root / "signing-status.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(module.ReportError, match=fragment):
        module.build_report(metadata_path=root / "release-metadata.json", junit_path=_junit(tmp_path, PASSING_JUNIT),
                            source_sha="a" * 40, signing_report_path=root / "signing-status.json")


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


def test_a_blank_per_file_status_is_unknown_not_unsigned(tmp_path):
    module = _report_module()
    root = _release_root(tmp_path)
    (root / "signing-status.json").write_text(json.dumps(
        {"files": [{"filename": "a.exe", "status": "   "}, {"filename": "a.zip", "status": None}]}),
        encoding="utf-8")
    report = module.build_report(metadata_path=root / "release-metadata.json",
                                 junit_path=_junit(tmp_path, PASSING_JUNIT), source_sha="a" * 40,
                                 signing_report_path=root / "signing-status.json")
    signing = report["repository_automation"]["code_signing"]
    assert [item["status"] for item in signing["files"]] == ["UNKNOWN", "UNKNOWN"]
    assert signing["status"] == "UNKNOWN"


def test_report_cli_exit_codes_follow_the_documented_contract(tmp_path, capsys):
    module = _report_module()
    root = _release_root(tmp_path)
    good = root / "acceptance-report.json"
    argv = ["--metadata", str(root / "release-metadata.json"), "--junit", str(_junit(tmp_path, PASSING_JUNIT)),
            "--source-sha", "a" * 40, "--output", str(good)]
    assert module.main(argv) == 0 and good.is_file()
    (root / "signing-status.json").write_text(json.dumps({"status": "UNSIGNED", "files": [
        {"filename": "DrillMaster-1.2.3-Setup.exe", "status": "NotSigned"}]}), encoding="utf-8")
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
