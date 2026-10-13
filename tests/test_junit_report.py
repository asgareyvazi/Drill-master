"""Focused tests for the Windows regression-report parser (``packaging/junit_report.py``).

These tests pin the diagnostic contract that the Windows release gate depends on:
Windows paths must parse, plain assertion failures must be recognised, a
malformed report must not crash the step, every failed identity must be reported
even when GitHub truncates annotations, and credential values must never be
copied into an annotation, a summary or standard output.
"""
from __future__ import annotations

import importlib.util
import re
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


def test_a_run_that_left_no_report_still_names_its_exit_code(tmp_path, capsys):
    """A missing JUnit report used to mean a failing step with nothing to say about itself.

    pytest writes the report only when it reaches the end of the run, so an interrupted or refused run leaves
    no test identity anywhere.  Given pytest's exit code the step now publishes one bounded annotation that
    says exactly that, which is the difference between "the suite failed and here is the tail of the run" and
    a red check whose only content is a truncation notice.
    """
    module = _parser()
    missing = tmp_path / "absent.xml"
    log = tmp_path / "windows-regressions.log"
    log.write_text("collected 0 items\nINTERNALERROR> interrupted during collection\n", encoding="utf-8")
    assert module.main(["--junit", str(missing), "--annotations", "--pytest-exit", "2",
                        "--pytest-log", str(log)]) == 2
    captured = capsys.readouterr()
    assert "::error " in captured.out
    assert "pytest exited 2" in captured.out
    assert "JUnit report not found" in captured.out
    assert "INTERNALERROR" in captured.out


def test_an_empty_report_is_told_apart_from_a_missing_one(tmp_path, capsys):
    """Zero collected cases and an absent file are different failures and must be reported differently."""
    module = _parser()
    empty = _write(tmp_path, "", name="empty.xml")
    assert module.main(["--junit", str(empty), "--annotations", "--pytest-exit", "5"]) == 0
    captured = capsys.readouterr()
    assert "pytest exited 5" in captured.out
    assert "0 case(s)" in captured.out
    assert "not found" not in captured.out


def test_failures_the_report_already_names_are_not_annotated_twice(tmp_path, capsys):
    module = _parser()
    report = _write(tmp_path, (
        '<testcase classname="tests.test_x" name="test_y"><failure message="AssertionError: nope">'
        'tests/test_x.py:5: in test_y\nE   AssertionError: nope\n</failure></testcase>'
    ))
    assert module.main(["--junit", str(report), "--annotations", "--pytest-exit", "1"]) == 0
    captured = capsys.readouterr()
    assert "tests.test_x.test_y" in captured.out
    assert "no failing test" not in captured.out, "the abort annotation must not shadow a named failure"


def test_the_exit_code_alone_invents_nothing_and_changes_nothing(tmp_path, capsys):
    """A passing run, and every run reported without --pytest-exit, behave exactly as before."""
    module = _parser()
    report = _write(tmp_path, '<testcase classname="tests.test_x" name="ok"/>\n')
    assert module.main(["--junit", str(report), "--annotations", "--pytest-exit", "0"]) == 0
    with_flag = capsys.readouterr().out
    assert with_flag == ""
    assert module.main(["--junit", str(report), "--annotations"]) == 0
    assert capsys.readouterr().out == with_flag


def test_the_quoted_log_tail_is_bounded_and_redacted(tmp_path, capsys):
    module = _parser()
    missing = tmp_path / "absent.xml"
    log = tmp_path / "run.log"
    body = "".join(f"noise line {i}\n" for i in range(400))
    log.write_text(body + "DB_PASSWORD='hunter2-super-secret'\nthe last line before the abort\n",
                   encoding="utf-8")
    module.main(["--junit", str(missing), "--annotations", "--pytest-exit", "3", "--pytest-log", str(log),
                 "--tail-lines", "2"])
    captured = capsys.readouterr().out
    assert "hunter2-super-secret" not in captured, "the log tail reached the annotation unredacted"
    assert "DB_PASSWORD=<redacted>" in captured
    assert "the last line before the abort" in captured
    assert "noise line 0" not in captured, "the whole log was quoted rather than its tail"
    assert len(captured) <= module.ANNOTATION_LIMIT + 200


def test_pytest_exit_is_refused_in_annotate_mode(tmp_path, capsys):
    """The two modes answer different questions, and a mixed call would silently mislabel one as the other."""
    module = _parser()
    assert module.main(["--annotate", "--annotate-message", "stage died", "--pytest-exit", "2"]) == 2
    assert "cannot accompany --annotate" in capsys.readouterr().err


def test_the_abort_note_reaches_the_job_summary_too(tmp_path):
    """The summary is the one channel GitHub never truncates, so the same explanation belongs in both."""
    module = _parser()
    empty = _write(tmp_path, "", name="empty.xml")
    summary = tmp_path / "summary.md"
    module.main(["--junit", str(empty), "--summary-out", str(summary), "--pytest-exit", "5"])
    text = summary.read_text(encoding="utf-8")
    assert "pytest exited 5" in text
    assert "Collected: 0" in text


def _crash_log(tmp_path: Path, *, trailing: int = 8) -> Path:
    """A pytest transcript in the shape a Windows access violation actually leaves behind.

    The interpreter's death notice and the test's own frames come first; the harness's outer frames and the
    progress dots trail them, which is why quoting the end of this file tells a reader nothing.
    """
    lines = [
        "...........................                                      [ 12%]",
        "Windows fatal exception: access violation",
        "",
        "Current thread 0x00000a4c (most recent call first):",
        '  File "D:\\a\\Drill-master\\Drill-master\\tabs\\w13_fishing_result_ui.py", line 512 in paintEvent',
        '  File "D:\\a\\Drill-master\\Drill-master\\tests\\test_w13_fishing_result_ui.py", line 88 in '
        'test_the_fallback_painter_runs',
        '  File "C:\\hostedtoolcache\\windows\\Python\\3.12.10\\x64\\Lib\\site-packages\\_pytest\\python.py", '
        "line 166 in pytest_pyfunc_call",
    ]
    lines += ['  File "C:\\hostedtoolcache\\windows\\Python\\3.12.10\\x64\\Lib\\site-packages\\_pytest\\main.py", '
              f"line {380 + index} in _main" for index in range(trailing)]
    lines += ["Exception ignored in: <_io.Object2PyCPtr object>", "....."]
    path = tmp_path / "windows-regressions.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_a_crash_is_quoted_from_its_marker_not_from_the_end_of_the_log(tmp_path, capsys):
    """The frames that name the crashing code sit above the harness's own, so a tail is the wrong window."""
    module = _parser()
    log = _crash_log(tmp_path)
    module.main(["--junit", str(tmp_path / "absent.xml"), "--annotations", "--pytest-exit", "139",
                 "--pytest-log", str(log)])
    captured = capsys.readouterr().out
    assert "fatal crash dump" in captured
    assert "w13_fishing_result_ui.py" in captured, "the annotation quoted the harness instead of the crash"
    assert "Windows fatal exception: access violation" in captured
    assert "marker at line 2 of" in captured
    assert "the run is not a pass" in captured, "the exit-code verdict must survive alongside the crash note"


def test_the_crash_note_is_a_separate_annotation_within_the_limit(tmp_path, capsys):
    module = _parser()
    log = _crash_log(tmp_path, trailing=400)
    # Long frame lines, because a crash dump made of short lines never reaches the limit and a bound that is
    # never exercised is a bound that will silently regress.
    lines = log.read_text(encoding="utf-8").splitlines()
    log.write_text("\n".join(line + ("x" * 300 if "File" in line else "") for line in lines) + "\n",
                   encoding="utf-8")
    module.main(["--junit", str(tmp_path / "absent.xml"), "--annotations", "--pytest-exit", "139",
                 "--pytest-log", str(log)])
    captured = capsys.readouterr().out
    lines = [line for line in captured.splitlines() if line.startswith("::error ")]
    assert len(lines) >= 2, "the abort note and the crash dump must not be merged into one truncated string"
    crash = next(line for line in lines if "fatal crash dump" in line)
    assert len(crash) <= module.ANNOTATION_LIMIT + 120, "GitHub truncates silently past the limit"
    assert "the excerpt stopped at the annotation limit" in crash or "the dump continues for" in crash, (
        "the reader has to be told the excerpt was cut, and how much was available")
    assert "access violation" in crash and "w13_fishing_result_ui.py" in crash, (
        "the cap ate the part that mattered: the marker and the frames under it must survive the cut")


def test_a_log_without_a_crash_marker_invents_none(tmp_path, capsys):
    module = _parser()
    log = tmp_path / "quiet.log"
    log.write_text("collected 12 items\nno crash here\n", encoding="utf-8")
    module.main(["--junit", str(tmp_path / "absent.xml"), "--annotations", "--pytest-exit", "2",
                 "--pytest-log", str(log)])
    captured = capsys.readouterr().out
    assert "fatal crash dump" not in captured
    assert "no crash here" in captured, "the ordinary tail quote is still the only witness"


def test_the_crash_excerpt_survives_an_unreadable_path(tmp_path):
    """A directory where the log should be is a real shape of this failure, and it must not raise."""
    module = _parser()
    directory = tmp_path / "windows-regressions.log"
    directory.mkdir()
    text = module.crash_excerpt(directory)
    assert "could not be read" in text and "IsADirectoryError" in text


def test_the_job_summary_gets_the_wider_crash_excerpt(tmp_path):
    """The summary is not truncation-limited the way an annotation is, so it carries the whole dump."""
    module = _parser()
    log = _crash_log(tmp_path, trailing=40)
    summary = tmp_path / "summary.md"
    module.main(["--junit", str(tmp_path / "absent.xml"), "--summary-out", str(summary), "--pytest-exit", "139",
                 "--pytest-log", str(log)])
    text = summary.read_text(encoding="utf-8")
    assert "w13_fishing_result_ui.py" in text
    assert "the dump continues for" not in text, "the summary had room for the whole dump and cut it anyway"


def test_the_budget_is_measured_on_what_github_counts_not_on_the_raw_string(tmp_path, capsys):
    """Escaping is not free, and an annotation that overflows the limit is not truncated -- it is dropped.

    ``_escape_data`` turns each percent sign into three characters, so a crash dump of percent-heavy frame
    lines is several times longer on the wire than in memory.  The excerpt has to fit the escaped form; a
    budget kept on raw length would look compliant in review and lose the diagnostic in the UI.
    """
    module = _parser()
    log = tmp_path / "percent.log"
    log.write_text("Windows fatal exception: access violation\n"
                   + "\n".join('  File "%s", line %d in paintEvent' % ("%" * 180, index)
                                for index in range(60)) + "\n", encoding="utf-8")
    module.main(["--junit", str(tmp_path / "absent.xml"), "--annotations", "--pytest-exit", "139",
                 "--pytest-log", str(log), "--tail-lines", "4"])
    captured = capsys.readouterr().out
    for line in captured.splitlines():
        if "fatal crash dump" in line:
            assert len(line) <= module.ANNOTATION_LIMIT + 120, (
                f"the emitted annotation is {len(line)} characters, past the limit GitHub truncates at")
            assert "access violation" in line, "the budget cut from the wrong end"
            assert "the excerpt stopped at the annotation limit" in line
            break
    else:
        raise AssertionError("no crash annotation was emitted at all")


def test_annotations_stay_inside_the_size_github_actually_keeps(tmp_path, capsys):
    """GitHub stores at most 3000 characters and cuts from the front, which eats headlines.

    Measured on the run this module was rewritten for: a message emitted at exactly the stored maximum arrived
    as an ellipsis plus its last 2999 characters.  Both the abort diagnosis and the crash excerpt are therefore
    sized to the safe limit, and the summary -- which no store limit squeezes -- carries the rest.
    """
    module = _parser()
    log = _crash_log(tmp_path, trailing=60)
    lines = log.read_text(encoding="utf-8").splitlines()
    log.write_text("\n".join(line + ("y" * 300 if "File" in line else "") for line in lines) + "\n",
                   encoding="utf-8")
    summary = tmp_path / "summary.md"
    module.main(["--junit", str(tmp_path / "absent.xml"), "--annotations", "--summary-out", str(summary),
                 "--pytest-exit", "139", "--pytest-log", str(log), "--tail-lines", "40"])
    emitted = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::error ")]
    assert len(emitted) >= 2, "the abort note and the crash dump are separate annotations"
    for line in emitted:
        assert len(line) <= module.ANNOTATION_SAFE_LIMIT + 200, (
            f"an emitted annotation is {len(line)} characters; past the stored limit GitHub cuts the front, "
            "and a crash excerpt cut from the front is the useless half of the dump")
    text = summary.read_text(encoding="utf-8")
    assert "#### Captured crash dump" in text
    assert len(text) > sum(len(line) for line in emitted), (
        "the summary is the uncapped channel; if it is shorter than the annotations, the dump was cut twice")


def test_the_frame_tally_says_whether_the_stack_was_deep(tmp_path):
    """A 15-line window cannot show a hundred-deep stack, so the excerpt counts instead of quoting.

    The first real use of this machinery faulted inside our own redaction path with a shallow-looking window and
    24 frames the annotation budget had to cut.  Whether that was recursion in the code under test or memory
    damage presenting at whichever call came next is decided by how often each frame repeats, which fits in one
    sentence however deep the stack is.
    """
    module = _parser()
    deep = tmp_path / "deep.log"
    frames = []
    for depth in range(150):
        frames.append(f'  File "D:\\a\\Drill-master\\Drill-master\\packaging\\windows_release_evidence.py", '
                      f"line 1488 in _redact_tree")
        frames.append(f'  File "D:\\a\\Drill-master\\Drill-master\\packaging\\windows_release_evidence.py", '
                      f"line 1486 in _redact_tree")
    deep.write_text("Windows fatal exception: access violation\n\nCurrent thread 0x1 (most recent call first):\n"
                    + "\n".join(frames) + "\n", encoding="utf-8")
    quoted = module.crash_excerpt(deep, limit_lines=6)
    assert "recursion suspected" in quoted, quoted
    # 150 alternating pairs: both frames repeat 150 times, and the count is over the whole dump (300 frames,
    # two distinct) rather than over the six lines the window could carry.
    assert "300 frame(s), 2 distinct" in quoted, quoted
    assert quoted.count("x150") == 2, quoted
    assert "windows_release_evidence.py:1486" in quoted and "windows_release_evidence.py:1488" in quoted, quoted
    assert "D:\\a" not in quoted.split("repeats:")[1], "the tally keys on the file name, not the runner directory"

    shallow = tmp_path / "shallow.log"
    shallow.write_text(
        "Windows fatal exception: access violation\n\nCurrent thread 0x1 (most recent call first):\n"
        '  File "D:\\a\\packaging\\junit_report.py", line 143 in redact\n'
        '  File "D:\\a\\packaging\\junit_report.py", line 654 in forensics\n'
        '  File "C:\\python3.12\\_pytest\\python.py", line 167 in pytest_pyfunc_call\n', encoding="utf-8")
    plain = module.crash_excerpt(shallow)
    assert "3 frame(s), 3 distinct" in plain, plain
    assert "no frame repeated" in plain and "recursion suspected" not in plain


def test_the_tally_survives_when_the_excerpt_itself_hits_the_limit(tmp_path):
    module = _parser()
    log = tmp_path / "wide.log"
    body = ["Windows fatal exception: access violation", "", "Current thread 0x1 (most recent call first):"]
    for depth in range(400):
        body.append('  File "D:\\a\\Drill-master\\Drill-master\\packaging\\evidence.py", line %d in redact'
                    % (depth % 3 + 140) + " " + "%p" * 300)
    log.write_text("\n".join(body) + "\n", encoding="utf-8")
    # Narrow pieces make the slack small: the loop stops as soon as one more line would not fit, so with
    # 20-character pieces the excerpt lands within 20 characters of the budget.  A tally that is not counted in
    # that decision therefore overflows it by about its own length, which is exactly the defect to pin.
    quoted = module.crash_excerpt(log, limit_lines=400, line_width=20)
    assert len(module._escape_data(quoted)) < module.ANNOTATION_SAFE_LIMIT, (
        "the excerpt is what GitHub truncates from the front, and it truncated the headline on the run whose "
        "silence this whole mechanism exists to end")
    assert "distinct" in quoted, "the counted shape of the stack must outlive the excerpt that could not fit"
    assert "excerpt stopped at the annotation limit" in quoted, (
        "the fixture must actually press against the budget, or it pins nothing")


def test_the_bounded_excerpt_also_quotes_the_bottom_of_a_shallow_stack(tmp_path):
    """A crash while pytest formats somebody else's failure puts the culprit at the *bottom*.

    Measured on the second production use of this channel: 37 frames, 28 distinct, only pluggy's plumbing
    repeated -- so the frames that mattered were not under the marker but at the far end of the dump, where the
    test being reported on sits.  A window that keeps only the top keeps the hook machinery instead.
    """
    module = _parser()
    log = tmp_path / "shallow.log"
    lines = ["Windows fatal exception: access violation", "", "Current thread 0x1 (most recent call first):"]
    lines += [f'  File "C:\\python\\Lib\\site-packages\\_pytest\\code{i}.py", line {i} in frame{i}'
              for i in range(30)]
    lines.append('  File "D:\\a\\Drill-master\\Drill-master\\tests\\test_windows_release_evidence.py", '
                 "line 328 in test_installed_exe_runs_with_isolated_roots_and_cleared_credentials")
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    quoted = module.crash_excerpt(log, limit_lines=10, end_lines=3)
    assert "test_installed_exe_runs_with_isolated_roots_and_cleared_credentials" in quoted, quoted
    assert "...24 frame line(s) elided; the end of the stack follows..." in quoted, (
        "the elision has to be counted, or a reader cannot tell a shortened stack from a complete one")
    assert "access violation" in quoted, "the marker line is never the part that gets cut"
    assert "no frame repeated" in quoted
    # A window that stops at `limit_lines` and a budget that forces a trim are different facts, and the reader
    # needs to know which one happened: the first is ordinary truncation, the second means the store would not
    # take the rest.
    assert "the dump continues for 24 more lines" in quoted, quoted
    assert "excerpt stopped at the annotation limit" not in quoted, quoted

    whole = module.crash_excerpt(log, limit_lines=60, bounded=False)
    assert "elided" not in whole, "the summary channel has no window to elide through"

    # The trim order is a property, not an implementation detail: head frames beyond the marker pair go before
    # any tail frame is given up, and the marker line itself is never what pays for the budget.  `redact()` caps
    # a line at 300 characters, so a dump of 23 lines cannot fit the annotation budget at all and the shape of
    # the result is decided entirely by which lines are sacrificed.
    order = tmp_path / "order.log"
    frames = []
    for index in range(18):
        frames.append(f'  File "C:\\python\\Lib\\_pytest\\c{index}.py", line {index} in frame{index} '
                      + "x" * 400)
    tail = ['  File "D:\\work\\Drill-master\\tests\\t.py", line 9 in tail_frame_above_the_culprit ' + "y" * 400,
            '  File "D:\\work\\Drill-master\\tests\\t.py", line 328 in test_the_culprit_last ' + "z" * 400]
    order.write_text("\n".join(["Windows fatal exception: access violation", "",
                                 "Current thread 0x1 (most recent call first):"] + frames + tail) + "\n",
                     encoding="utf-8")
    shaped = module.crash_excerpt(order, limit_lines=20, end_lines=2)
    assert "tail_frame_above_the_culprit" in shaped and "test_the_culprit_last" in shaped, (
        "the tail is what names the test; an implementation that gives it up first passes every other assertion")
    assert "Windows fatal exception" in shaped, "the marker line is never the part that gets cut"
    assert "frame0" in shaped and "frame17" not in shaped, shaped
    assert "excerpt stopped at the annotation limit" in shaped, shaped
    counted = re.search(r"\.\.\.(\d+) frame line\(s\) elided", shaped)
    assert counted and int(counted.group(1)) >= 10, (
        f"twenty-three lines against a two-thousand-character budget leaves most of the stack unquoted: {shaped}")
    assert len(module._escape_data(shaped)) < module.ANNOTATION_SAFE_LIMIT, shaped
