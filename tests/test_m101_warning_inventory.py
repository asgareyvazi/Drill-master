"""M101: the pytest warning inventory printed (and annotated in CI) by verify_release.

M105 fix: pytest collapses ten or more locations into ``file: N warnings`` lines; those count N.
"""
import subprocess
import sys
import textwrap

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


COLLAPSED = """\
=============================== warnings summary ===============================
tests/test_db.py: 86 warnings
tests/test_io.py: 12 warnings
  /repo/core/database.py:3639: DeprecationWarning: The default datetime adapter is deprecated
    cursor.execute(sql)

tests/test_a.py::test_one
  /repo/core/report_snapshot.py:132: DeprecationWarning: utcnow() is deprecated
    stamp = datetime.utcnow()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
============================ warnings summary (final) ==========================
tests/test_late.py::test_end
  /venv/lib/python3.12/site-packages/pkg/mod.py:7: ResourceWarning: unclosed file
    open(path)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================= 4 passed, 100 warnings in 2.00s =================
"""


def test_collapsed_location_lines_count_every_occurrence_and_the_final_section_is_read(capsys):
    rows = vr.summarize_warnings(COLLAPSED)
    assert rows[0][:2] == (98, "repository") and rows[0][3] == "/repo/core/database.py:3639"
    assert sum(r[0] for r in rows) == 100
    assert any(r[2] == "ResourceWarning" and r[1] == "third-party" for r in rows)
    assert vr.pytest_reported_warnings(COLLAPSED) == 100
    assert vr.report_warnings(COLLAPSED, environ={}) == 100
    assert "matches pytest's own total (100)" in capsys.readouterr().out


def test_a_count_that_does_not_reconcile_is_reported_not_hidden(capsys):
    broken = COLLAPSED.replace("100 warnings in", "101 warnings in")
    vr.report_warnings(broken, environ={"GITHUB_ACTIONS": "true"})
    out = capsys.readouterr().out
    assert "DIFFERS from pytest's own total (101)" in out and "DIFFERS from pytest total 101" in out


def test_the_inventory_reconciles_with_a_real_pytest_run(tmp_path):
    test_file = tmp_path / "test_noisy.py"
    test_file.write_text(textwrap.dedent("""
        import warnings
        import pytest

        @pytest.mark.parametrize("n", range(12))
        def test_many(n):
            warnings.warn("synthetic many", DeprecationWarning)

        def test_twice():
            warnings.warn("synthetic twice", UserWarning)
            warnings.warn("synthetic twice", UserWarning)
    """), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")     # isolate from the repo config
    proc = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-W", "always", "-q",
                           "-c", str(tmp_path / "pytest.ini"), str(test_file)],
                          capture_output=True, text=True, cwd=tmp_path, timeout=120)
    output = proc.stdout
    reported = vr.pytest_reported_warnings(output)
    assert reported is not None and reported >= 13, output[-2000:]
    rows = vr.summarize_warnings(output)
    assert sum(r[0] for r in rows) == reported, output[-3000:]
    many = next(r for r in rows if r[4] == "synthetic many")
    assert many[0] == 12
