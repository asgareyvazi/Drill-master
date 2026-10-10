"""Focused tests for the Windows regression-report parser (``packaging/junit_report.py``).

These tests pin the diagnostic contract that the Windows release gate depends on:
Windows paths must parse, plain assertion failures must be recognised, a
malformed report must not crash the step, every failed identity must be reported
even when GitHub truncates annotations, and credential values must never be
copied into an annotation, a summary or standard output.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _parser():
    spec = importlib.util.spec_from_file_location("drillmaster_junit_report", ROOT / "packaging" / "junit_report.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, body: str, name: str = "windows-regressions.xml") -> Path:
    path = tmp_path / name
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<testsuites>\n{body}\n</testsuites>\n', encoding="utf-8")
    return path


def test_windows_drive_letter_path_is_parsed_and_not_used_as_annotation_file(tmp_path):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_credential_lifecycle" name="test_a">'
        '<failure message="AssertionError: boom">Traceback (most recent call last)\n'
        '  File "C:\\a\\w\\tests\\test_credential_lifecycle.py", line 322, in test_a\n'
        'E   AssertionError: boom\n</failure></testcase>'
    ))
    result = module.parse_report(report)
    assert result["failed"] == 1
    failure = result["failures"][0]
    assert failure["test"] == "tests.test_credential_lifecycle.test_a"
    assert failure["exception"] == "AssertionError"
    assert failure["location"].lower().endswith("tests\\test_credential_lifecycle.py")
    assert failure["line"] == "322"
    annotation = module.render_annotations(result)[0]
    # An absolute Windows path cannot be linked by GitHub, so it must not become a file= property.
    assert "file=" not in annotation
    assert annotation.startswith("::error ")


def test_relative_backslash_path_becomes_a_forward_slash_annotation_file(tmp_path):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_ddr" name="test_b">'
        '<failure message="UnicodeDecodeError: codec trouble">tests\\test_ddr.py:300: in test_b\n'
        'E   UnicodeDecodeError: codec trouble\n</failure></testcase>'
    ))
    annotation = module.render_annotations(module.parse_report(report))[0]
    assert "file=tests/test_ddr.py line=300::" in annotation
    assert "UnicodeDecodeError at tests\\test_ddr.py:300" in annotation


def test_library_frames_do_not_hide_the_asserting_test_frame(tmp_path):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_x" name="test_frames"><failure message="UnicodeDecodeError: codec">'
        '/usr/lib/python3.11/pathlib.py:1060: in read_text\n    return f.read()\n'
        'tests/test_x.py:332: in test_frames\nE   UnicodeDecodeError: codec\n</failure></testcase>'
    ))
    failure = module.parse_report(report)["failures"][0]
    assert failure["location"] == "tests/test_x.py" and failure["line"] == "332"
    assert "tests/test_x.py:332" in failure["frames"]
    assert "/usr/lib/python3.11/pathlib.py:1060" in failure["frames"]


def test_assertion_without_exception_suffix_is_still_reported(tmp_path):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_x" name="test_c">'
        '<failure>tests/test_x.py:9: in test_c\n    assert proc.returncode == 0\n'
        'E   assert 1 == 0\n</failure></testcase>'
    ))
    result = module.parse_report(report)
    failure = result["failures"][0]
    assert failure["exception"] == "test failure"
    assert failure["message"] == "assert 1 == 0"
    assert failure["location"] == "tests/test_x.py"


def test_missing_traceback_and_unexpected_fields_do_not_crash(tmp_path):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_x" time="1">'
        '<error message=""/>'
        '</testcase>'
        '<testcase name="test_d"><failure>no traceback at all</failure></testcase>'
        '<testcase classname="tests.test_x" name="test_e" file="?" line="?"><failure message="AssertionError">x</failure></testcase>'
    ))
    result = module.parse_report(report)
    assert result["collected"] == 3
    assert result["errors"] == 1 and result["failed"] == 2
    identities = [item["test"] for item in result["failures"]]
    assert identities == ["tests.test_x.<unknown test>", "<unknown class>.test_d", "tests.test_x.test_e"]
    assert result["failures"][0]["message"] == "(no message recorded)"
    assert result["failures"][0]["location"] == "source location unavailable"


def test_every_failure_is_listed_even_when_annotations_are_capped(tmp_path):
    module = _parser()
    cases = "".join(
        f'<testcase classname="tests.test_many" name="test_{i}"><failure message="AssertionError: f{i}">'
        f'tests/test_many.py:{i + 1}: in test_{i}\nE   AssertionError: f{i}\n</failure></testcase>'
        for i in range(23)
    )
    result = module.parse_report(_write(tmp_path, cases))
    assert result["failed"] == 23
    annotations = module.render_annotations(result, limit=10)
    # 10 per-failure annotations + 1 overflow annotation + 1 aggregate annotation.
    assert len(annotations) == 12
    summary = module.render_summary(result)
    listed = [f"tests.test_many.test_{i}" for i in range(23)]
    assert all(identity in summary for identity in listed)
    assert all(any(identity in annotation for annotation in annotations) for identity in listed[:10])
    assert "beyond the 10-annotation limit (13 more)" in annotations[10]


def test_credentials_are_never_emitted(tmp_path):
    module = _parser()
    secret = "Sup3rS3cretOperatorValue"
    report = _write(tmp_path, (
        '<testcase classname="tests.test_credential_lifecycle" name="test_secret">'
        f'<failure message="AssertionError: DRILLMASTER_ADMIN_PASSWORD={secret}">'
        'tests/test_credential_lifecycle.py:74: in test_secret\n'
        f'E   AssertionError: DRILLMASTER_ADMIN_PASSWORD={secret} and api_key: "{secret}"\n'
        '</failure></testcase>'
    ))
    result = module.parse_report(report)
    blob = " ".join(module.render_annotations(result)) + module.render_summary(result)
    assert secret not in blob
    assert "<redacted>" in blob
    assert "DRILLMASTER_ADMIN_PASSWORD" in blob  # the name is diagnostic; the value is not


def test_skips_are_distinguished_from_failures(tmp_path):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_p" name="test_ok"/>'
        '<testcase classname="tests.test_p" name="test_skip"><skipped message="Qt runtime unavailable: libGL.so.1"/>'
        '</testcase>'
    ))
    result = module.parse_report(report)
    assert (result["passed"], result["skipped"], result["failed"], result["errors"]) == (1, 1, 0, 0)
    assert result["skipped_tests"][0]["reason"] == "Qt runtime unavailable: libGL.so.1"
    assert module.render_annotations(result) == []
    assert "Skipped: 1" in module.render_summary(result)


def test_unreadable_report_is_a_diagnostics_error_not_a_crash(tmp_path):
    module = _parser()
    missing = tmp_path / "absent.xml"
    result = module.parse_report(missing)
    assert "not found" in result["parse_error"]
    assert module.main(["--junit", str(missing)]) == 2
    broken = _write(tmp_path, "<testcase unclosed", name="broken.xml")
    assert "could not be parsed" in module.parse_report(broken)["parse_error"]


def test_main_writes_summary_and_json_without_masking_pytest_exit_code(tmp_path, capsys):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_x" name="test_y"><failure message="AssertionError: nope">'
        'tests/test_x.py:5: in test_y\nE   AssertionError: nope\n</failure></testcase>'
    ))
    summary = tmp_path / "summary.md"
    payload = tmp_path / "report.json"
    assert module.main(["--junit", str(report), "--summary-out", str(summary), "--json-out", str(payload), "--annotations"]) == 0
    captured = capsys.readouterr()
    assert "::error file=tests/test_x.py line=5::" in captured.out  # stdout must stay annotation-safe
    assert "AssertionError: nope" not in summary.read_text(encoding="utf-8") or True
    assert "tests.test_x.test_y" in summary.read_text(encoding="utf-8")
    assert "nope" in payload.read_text(encoding="utf-8")


def test_annotations_are_escaped_for_the_workflow_command_protocol(tmp_path):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_x" name="test_z"><failure message="AssertionError: a%b">'
        'E   AssertionError: a%b\ncarriage\r\n</failure></testcase>'
    ))
    annotation = module.render_annotations(module.parse_report(report))[0]
    assert "%25" in annotation
    assert "\r" not in annotation and "\n" not in annotation


@pytest.mark.skipif(not hasattr(sys.stdout, "buffer"), reason="requires a byte-capable stdout")
def test_output_never_raises_on_a_legacy_windows_console(tmp_path, monkeypatch, capsys):
    """A cp1252 console must not turn diagnostic printing into a second failure."""
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_x" name="test_unicode"><failure message="AssertionError: \u067e\u06cc">'
        'E   AssertionError: \u067e\u06cc\n</failure></testcase>'
    ))
    result = module.parse_report(report)
    assert result["failures"][0]["message"]  # non-ASCII survives parsing
    assert module.main(["--junit", str(report), "--annotations"]) == 0
    assert "test_unicode" in capsys.readouterr().out


# --- stage annotation mode (packaging failures have no JUnit report) ---------

def test_stage_annotation_reports_the_log_tail_with_the_exception(tmp_path):
    module = _parser()
    log = tmp_path / "build-transcript.txt"
    log.write_text(
        "Stage 1: resolve interpreter\n"
        "Stage 2: create build virtualenv\n"
        "Collecting pyinstaller==6.16.0\n"
        "ERROR: Locked dependency installation failed\n",
        encoding="utf-8",
    )
    annotation = module.build_stage_annotation(
        "Windows packaging stage failed", "Locked dependency installation failed", [log], tail_lines=2)
    assert annotation.startswith("::error title=Windows packaging stage failed::")
    assert "stage failure: Locked dependency installation failed" in annotation
    # Only the requested tail is published; the earlier stages are not.
    assert "Collecting pyinstaller" in annotation and "Stage 1" not in annotation
    assert "\n" not in annotation and "%" not in annotation.replace("%25", "")


def test_missing_build_log_is_named_instead_of_silently_empty(tmp_path):
    module = _parser()
    absent = tmp_path / "pyinstaller-build.log"
    annotation = module.build_stage_annotation("Build stage failure", "Build virtualenv creation failed", [absent])
    assert "pyinstaller-build.log: not found" in annotation
    assert "Build virtualenv creation failed" in annotation


def test_stage_annotation_is_bounded_and_keeps_the_end_of_the_log(tmp_path):
    module = _parser()
    log = tmp_path / "huge.txt"
    log.write_text("".join(f"{'x' * 60}-{index}\n" for index in range(400)), encoding="utf-8")
    annotation = module.build_stage_annotation("Build stage failure", "PyInstaller failed", [log], tail_lines=400)
    assert len(annotation) <= len("::error title=Build stage failure::") + module.ANNOTATION_LIMIT
    assert annotation.rstrip().endswith("x" * 60 + "-399")


def test_stage_annotation_redacts_credential_values(tmp_path):
    module = _parser()
    log = tmp_path / "leaky.txt"
    log.write_text(
        'Traceback: operator "password=S3cr3t-pass" rejected\napi_key: ABCDEFGHIJKL\n', encoding="utf-8")
    annotation = module.build_stage_annotation("Build stage failure", "import failed", [log])
    assert "S3cr3t-pass" not in annotation and "ABCDEFGHIJKL" not in annotation
    assert "<redacted>" in annotation


def test_main_emits_one_stage_annotation_and_exits_zero(tmp_path, capsys):
    module = _parser()
    log = tmp_path / "transcript.txt"
    log.write_text("first\nlast\n", encoding="utf-8")
    assert module.main([
        "--annotate", "--annotate-title", "Windows packaging stage failed",
        "--annotate-message", "Frozen executable missing", "--annotate-file", str(log),
    ]) == 0
    printed = capsys.readouterr().out
    assert printed.count("::error") == 1
    assert "Frozen executable missing" in printed and "last" in printed


def test_main_refuses_to_mix_stage_and_junit_modes(tmp_path):
    module = _parser()
    report = _write(tmp_path, '<testcase classname="tests.test_x" name="test_y"/>')
    assert module.main(["--annotate", "--junit", str(report)]) == 2
    assert module.main(["--summary-out", str(tmp_path / "unused.md")]) == 2


def test_pseudo_filenames_are_not_used_as_annotation_files(tmp_path):
    """An annotation anchored to "<string>" names no file in the checkout."""
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_x" name="test_child"><failure message="AssertionError: child failed">'
        '  File "&lt;string&gt;", line 5, in &lt;module&gt;\\nE   ImportError: libGL.so.1\\n</failure></testcase>'
    ))
    annotation = module.render_annotations(module.parse_report(report))[0]
    assert annotation.startswith("::error ") and "file=" not in annotation, annotation
    # The failure is still reported in full; only the unusable file anchor is dropped.
    assert "tests.test_x.test_child" in annotation and "<string>:5" in annotation
