"""CI failure annotations emitted by verify_release (diagnostics only)."""
from __future__ import annotations

import verify_release

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4">
  <testcase classname="tests.test_a" name="test_ok"/>
  <testcase classname="tests.test_a" name="test_fails[50%-x]">
    <failure message="assert 1 == 2&#10;second line">traceback text</failure>
  </testcase>
  <testcase classname="tests.test_b" name="test_errors"><error>setup line 1
RuntimeError: fixture broke</error></testcase>
  <testcase classname="tests.test_b" name="test_skipped"><skipped message="why"/></testcase>
</testsuite></testsuites>
"""


def test_annotations_name_each_failure_and_error_on_one_escaped_line(tmp_path, capsys):
    report = tmp_path / "results.xml"
    report.write_text(JUNIT, encoding="utf-8")
    assert verify_release.annotate_failures(report, {"GITHUB_ACTIONS": "true"}) == 2
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "::error title=pytest failure::tests.test_a::test_fails[50%25-x] - assert 1 == 2 second line",
        "::error title=pytest error::tests.test_b::test_errors - RuntimeError: fixture broke",
    ]


def test_annotations_are_inert_outside_ci_or_without_a_report(tmp_path, capsys):
    report = tmp_path / "results.xml"
    report.write_text(JUNIT, encoding="utf-8")
    assert verify_release.annotate_failures(report, {}) == 0
    assert verify_release.annotate_failures(tmp_path / "missing.xml", {"GITHUB_ACTIONS": "true"}) == 0
    assert capsys.readouterr().out == ""


def test_malformed_report_is_reported_not_raised(tmp_path, capsys):
    report = tmp_path / "results.xml"
    report.write_text("<testsuites><testcase", encoding="utf-8")
    assert verify_release.annotate_failures(report, {"GITHUB_ACTIONS": "true"}) == 1
    assert capsys.readouterr().out.startswith("::error title=pytest report::")


def test_annotation_text_is_single_line_and_bounded():
    text = verify_release._annotation_text("a\r\nb%" + "x" * 500, limit=20)
    assert "\n" not in text and "\r" not in text and text.startswith("a b%25")
    assert len(text) <= 24
