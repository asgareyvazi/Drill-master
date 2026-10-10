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
                  sha: str = "a" * 40) -> Path:
    """Build a release directory that contains the evidence the report requires."""
    root = tmp_path / "release"
    root.mkdir(parents=True, exist_ok=True)
    (root / "bundle.zip").write_bytes(bundle)
    (root / "DrillMaster-1.2.3-Setup.exe").write_bytes(installer)
    (root / "release-metadata.json").write_text(json.dumps({
        "git_sha": sha,
        "version": "1.2.3",
        "platform": "windows-x64",
        "build_tools": {"inno_setup": inno_version},
        "artifacts": [
            {"filename": "bundle.zip", "sha256": hashlib.sha256(bundle).hexdigest()},
            {"filename": "DrillMaster-1.2.3-Setup.exe", "sha256": hashlib.sha256(installer).hexdigest()},
        ],
    }), encoding="utf-8")
    if smoke_log is None:
        smoke_log = "exit_code=0\nlog_generated=true\nsecret_leak_detected=false\nsmoke ok\n"
    (root / "package-smoke.log").write_text(smoke_log, encoding="utf-8")
    return root


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
