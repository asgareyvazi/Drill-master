"""A successful process exit is not sufficient release evidence."""

import subprocess
from unittest.mock import patch

import pytest

import verify_release


@pytest.mark.parametrize(
    "summary",
    [
        "2 passed, 1 xfailed",
        "2 passed, 1 xpassed",
        "2 passed, 1 deselected",
        "2 passed",
        "",
        "3 skipped, 1 passed",
    ],
)
def test_gate_rejects_unaccounted_or_unexpected_outcomes(summary):
    responses = [
        subprocess.CompletedProcess([], 0, "tests/test_example.py: 3\n", ""),
        subprocess.CompletedProcess([], 0, summary, ""),
    ]
    with patch.object(verify_release.subprocess, "run", side_effect=responses):
        assert not verify_release.run_pytest()


@pytest.mark.parametrize(
    "dirty,allow,expected,result",
    [
        (" M app.py", False, "a" * 40, False),
        ("?? config/new.json", False, "a" * 40, False),
        (" M app.py", True, "a" * 40, True),
        ("", False, "b" * 40, False),
        ("", False, "a" * 40, True),
    ],
)
def test_git_identity_and_worktree_are_explicit(dirty, allow, expected, result):
    responses = [
        subprocess.CompletedProcess([], 0, "a" * 40, ""),
        subprocess.CompletedProcess([], 0, dirty, ""),
        subprocess.CompletedProcess([], 0, "test-branch", ""),
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "", ""),
    ]
    with patch.object(verify_release, "_run", side_effect=responses):
        assert verify_release.verify_repository(expected, allow) is result


def test_version_gate_detects_source_packaging_drift(tmp_path, monkeypatch):
    files = (
        "core/version.py",
        "pyproject.toml",
        "app.py",
        "packaging/DrillMaster.spec",
        "packaging/build_windows.ps1",
        "packaging/DrillMaster.iss",
    )
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((verify_release.ROOT / name).read_text())
    monkeypatch.setattr(verify_release, "ROOT", tmp_path)
    assert verify_release.verify_version()
    (tmp_path / "core/version.py").write_text('__version__ = "invalid"')
    assert not verify_release.verify_version()
    (tmp_path / "core/version.py").write_text('__version__ = "1.0.0"')
    (tmp_path / "app.py").write_text('APP_VERSION = "0.0.0"')
    assert not verify_release.verify_version()


def test_version_comment_cannot_mask_wrong_runtime_binding(tmp_path, monkeypatch):
    import shutil

    for name in (
        "core/version.py",
        "pyproject.toml",
        "app.py",
        "packaging/DrillMaster.spec",
        "packaging/build_windows.ps1",
        "packaging/DrillMaster.iss",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(verify_release.ROOT / name, target)
    monkeypatch.setattr(verify_release, "ROOT", tmp_path)
    (tmp_path / "app.py").write_text(
        'from core.version import __version__\n# APP_VERSION = __version__\nAPP_VERSION = "0.0.0"'
    )
    assert not verify_release.verify_version()


@pytest.mark.parametrize(
    "case", ["missing", "malformed", "duplicate", "unexpected-skip", "wrong-reason", "valid-external"]
)
def test_junit_accounting_and_optional_skip_policy(tmp_path, case):
    from xml.etree.ElementTree import Element, SubElement, ElementTree

    path = tmp_path / "report.xml"
    root = Element("testsuites")
    suite = SubElement(root, "testsuite")
    optional = ("test_packaging_smoke", "test_real_windows_bundle_smoke_when_provided")
    node = SubElement(suite, "testcase", classname="tests." + optional[0], name=optional[1])
    counts = dict(passed=0, skipped=1)
    if case == "duplicate":
        SubElement(suite, "testcase", classname="tests." + optional[0], name=optional[1])
    if case == "unexpected-skip":
        node.set("name", "test_required_repository_behavior")
    reason = verify_release.OPTIONAL_ACCEPTANCE_SKIPS[optional] if case != "wrong-reason" else "core import failed"
    SubElement(node, "skipped", message=reason)
    if case == "malformed":
        path.write_text("<broken>")
    elif case != "missing":
        ElementTree(root).write(path)
    assert verify_release.validate_pytest_report(path, 1, counts) == (case == "valid-external")
