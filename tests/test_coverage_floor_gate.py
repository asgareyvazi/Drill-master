"""The coverage floor must measure every tracked product module (M43 continuation).

The previously reported 44 % figure came from `--cov=.`, which silently drops
modules no test imports (core/, dialogs/, tabs/ and ui/ are namespace packages,
so coverage never discovered them). The gate counts them as 0 % and fails when
any tracked product file is absent from the report.
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

import verify_release

ROOT = Path(__file__).resolve().parents[1]


def _summary(statements, covered, branches=0, covered_branches=0):
    return {"summary": {"num_statements": statements, "covered_lines": covered,
                        "num_branches": branches, "covered_branches": covered_branches}}


def test_floor_passes_at_or_above_and_fails_below():
    report = {"files": {"core/a.py": _summary(80, 40, 20, 10), "tabs/b.py": _summary(0, 0)}}
    tracked = ["core/a.py", "tabs/b.py"]
    ok, message = verify_release.evaluate_coverage(report, tracked, 50.0)
    assert ok and "50.00%" in message and "2 tracked files" in message
    ok, _ = verify_release.evaluate_coverage(report, tracked, 50.01)
    assert not ok


def test_unimported_tracked_module_fails_instead_of_shrinking_the_denominator():
    report = {"files": {"core/a.py": _summary(10, 10)}}
    ok, message = verify_release.evaluate_coverage(report, ["core/a.py", "core/never_imported.py"], 1.0)
    assert not ok
    assert "denominator incomplete" in message and "core/never_imported.py" in message


def test_files_outside_the_population_do_not_count():
    report = {"files": {"core/a.py": _summary(10, 5), "tests/test_a.py": _summary(1000, 1000)}}
    ok, message = verify_release.evaluate_coverage(report, ["core/a.py"], 50.0)
    assert ok and "(5/10)" in message


def test_empty_population_is_a_failure():
    ok, _ = verify_release.evaluate_coverage({"files": {}}, [], 0.0)
    assert not ok


def test_population_is_tracked_product_code_only():
    tracked = verify_release.tracked_product_sources()
    assert "core/database.py" in tracked and "main_window.py" in tracked
    assert any(name.startswith("tabs/") for name in tracked)
    assert not any(name.startswith(("tests/", "tools/", "packaging/", "docs/")) for name in tracked)
    assert "verify_release.py" not in tracked


def test_coverage_config_walks_namespace_packages_and_omits_no_product_file():
    coverage = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]
    config = coverage["run"]
    assert config["branch"] is True and coverage["report"]["include_namespace_packages"] is True
    assert coverage["report"]["omit"] == config["omit"]
    tracked = verify_release.tracked_product_sources()
    excluded = [name for name in tracked if any(fnmatch.fnmatch(name, pattern) for pattern in config["omit"])]
    assert excluded == [], "an omit pattern would hide product code from the coverage floor"


def test_floor_file_is_a_measured_percentage():
    floor = json.loads((ROOT / verify_release.COVERAGE_FLOOR).read_text(encoding="utf-8"))
    assert 0.0 < float(floor["percent"]) <= 100.0
    assert len(floor["measured_at_sha"]) == 40 and floor["population"]


def test_pytest_runs_under_coverage_only_when_requested(tmp_path):
    ok = subprocess.CompletedProcess([], 0, "tests/test_example.py: 1\n", "")
    done = subprocess.CompletedProcess([], 0, "1 passed", "")
    for data, expect_coverage in ((None, False), (tmp_path / ".coverage", True)):
        with patch.object(verify_release.subprocess, "run", side_effect=[ok, done]) as run:
            verify_release.run_pytest(coverage_data=data)
        command = run.call_args_list[1].args[0]
        assert ("coverage" in command) is expect_coverage
        assert "pytest" in command and any(arg.startswith("--junitxml=") for arg in command)
        if expect_coverage:
            assert f"--data-file={data}" in command


def test_coverage_flag_refuses_a_missing_or_unpinned_tool(monkeypatch):
    for name in ("verify_repository", "verify_dependencies", "verify_resources", "verify_version", "verify_lint"):
        monkeypatch.setattr(verify_release, name, lambda *a, **k: True)
    monkeypatch.setattr(verify_release, "_run", lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(verify_release, "run_pytest", lambda *a, **k: pytest.fail("pytest must not start"))

    def fake_version(name):
        if name == "coverage":
            raise verify_release.importlib.metadata.PackageNotFoundError(name)
        return "0"

    monkeypatch.setattr(verify_release.importlib.metadata, "version", fake_version)
    assert verify_release.main(["--coverage"]) == 1


def test_ci_enforces_the_floor_on_one_leg_with_the_pinned_tool():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert f"coverage=={verify_release.COVERAGE_VERSION}" in workflow
    assert "matrix.python == '3.12' && '--coverage'" in workflow
