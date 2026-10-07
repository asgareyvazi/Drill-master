"""Machine-readable release acceptance report truth-boundary tests."""
from __future__ import annotations

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


def test_acceptance_report_separates_automated_gates_from_external_acceptance(tmp_path):
    metadata_path = tmp_path / "release-metadata.json"
    metadata_path.write_text(json.dumps({
        "git_sha": "a" * 40,
        "version": "1.2.3",
        "platform": "windows-x64",
        "build_tools": {"inno_setup": "6.4.3"},
        "artifacts": [
            {"filename": "DrillMaster-1.2.3-windows-x64.zip", "sha256": "b" * 64},
            {"filename": "DrillMaster-1.2.3-Setup.exe", "sha256": "c" * 64},
        ],
    }), encoding="utf-8")
    junit_path = tmp_path / "tests.xml"
    junit_path.write_text(
        '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="1">'
        '<testcase classname="suite" name="passed" />'
        '<testcase classname="suite" name="external" ><skipped message="not configured" /></testcase>'
        '</testsuite></testsuites>',
        encoding="utf-8",
    )

    report = _report_module().build_report(
        metadata_path=metadata_path, junit_path=junit_path, source_sha="a" * 40
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
    assert report["external_acceptance"]["real_ddr_pdf_acceptance"] == "NOT_RUN"
    assert report["external_acceptance"]["real_mineru_acceptance"] == "NOT_RUN"
    assert report["external_acceptance"]["interactive_clean_machine_install"] == "NOT_RUN"
    assert "NOT_REAL_DDR_ACCEPTANCE" in report["external_acceptance"]["synthetic_workbook_scenario"]


def test_acceptance_report_rejects_sha_mismatch_failed_tests_and_missing_installer(tmp_path):
    metadata = {
        "git_sha": "a" * 40, "version": "1.2.3", "platform": "windows-x64",
        "build_tools": {"inno_setup": "6.4.3"},
        "artifacts": [
            {"filename": "bundle.zip", "sha256": "b" * 64},
            {"filename": "setup.exe", "sha256": "c" * 64},
        ],
    }
    metadata_path = tmp_path / "release.json"
    junit_path = tmp_path / "tests.xml"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    junit_path.write_text('<testsuite><testcase classname="x" name="ok" /></testsuite>', encoding="utf-8")
    module = _report_module()

    with pytest.raises(ValueError, match="SHA"):
        module.build_report(metadata_path=metadata_path, junit_path=junit_path, source_sha="d" * 40)
    junit_path.write_text(
        '<testsuite><testcase classname="x" name="bad"><failure message="broken" /></testcase></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="did not pass"):
        module.build_report(metadata_path=metadata_path, junit_path=junit_path, source_sha="a" * 40)
    junit_path.write_text('<testsuite><testcase classname="x" name="ok" /></testsuite>', encoding="utf-8")
    metadata["artifacts"] = [{"filename": "bundle.zip", "sha256": "b" * 64}]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="portable ZIP and compiled installer"):
        module.build_report(metadata_path=metadata_path, junit_path=junit_path, source_sha="a" * 40)
