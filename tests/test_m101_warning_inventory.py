"""M101: the pytest warning inventory printed (and annotated in CI) by verify_release."""
import verify_release as vr

SAMPLE = """\
tests/test_x.py ....                                                     [100%]

=============================== warnings summary ===============================
tests/test_a.py::test_one
tests/test_a.py::test_two
tests/test_b.py::test_three
  /venv/lib/python3.12/site-packages/matplotlib/_fontconfig_pattern.py:89: PyparsingDeprecationWarning: 'resetCache' deprecated
    parser.resetCache()

tests/test_c.py::test_four
  /repo/core/report_engine.py:120: DeprecationWarning: datetime.datetime.utcnow() is deprecated
    stamp = datetime.utcnow()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
5 passed, 5 warnings in 1.00s
"""


def test_groups_count_every_occurrence_and_separate_origins():
    rows = vr.summarize_warnings(SAMPLE)
    assert sum(r[0] for r in rows) == 5
    assert rows[0] == (3, "third-party", "PyparsingDeprecationWarning", "matplotlib/_fontconfig_pattern.py:89",
                       "'resetCache' deprecated")
    repo = [r for r in rows if r[1] == "repository"]
    assert repo == [(1, "repository", "DeprecationWarning", "/repo/core/report_engine.py:120",
                     "datetime.datetime.utcnow() is deprecated")]
    assert any(r[1] == "third-party" and r[3].startswith("<frozen") for r in rows)


def test_no_summary_means_no_rows_and_no_annotation(capsys):
    assert vr.summarize_warnings("3 passed in 0.1s") == []
    assert vr.report_warnings("3 passed in 0.1s", environ={"GITHUB_ACTIONS": "true"}) == 0
    assert "::notice" not in capsys.readouterr().out


def test_ci_notices_are_bounded_and_outside_ci_none_are_emitted(capsys):
    assert vr.report_warnings(SAMPLE, environ={}) == 5
    assert "::notice" not in capsys.readouterr().out
    vr.report_warnings(SAMPLE, environ={"GITHUB_ACTIONS": "true"}, limit=2)
    notices = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::notice")]
    assert len(notices) == 2
    assert "5 occurrence(s)" in notices[0] and "repository: 1" in notices[0] and "third-party: 4" in notices[0]
