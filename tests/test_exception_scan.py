"""Exception-handler inventory and its unexplained-silent ratchet (M43)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CEILING = ROOT / ".github" / "exception-silent-ceiling.json"
_spec = importlib.util.spec_from_file_location("exception_scan", ROOT / "tools" / "quality" / "exception_scan.py")
scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)


def _records(tmp_path, source):
    path = tmp_path / "sample.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return scan.scan_file(path)


def test_classification_of_broad_bare_and_silent_handlers(tmp_path):
    records = _records(tmp_path, """
        import logging
        log = logging.getLogger(__name__)
        def f():
            try: pass
            except Exception: pass                      # broad, silent
            try: pass
            except: return None                         # bare (also broad), silent
            try: pass
            except (ValueError, BaseException): log.exception("x")  # broad, not silent
            try: pass
            except KeyError: return {}                  # narrow, silent
            try: pass
            except OSError: raise                       # narrow, not silent
            try: pass
            except Exception as exc: return str(exc)    # broad, not silent (uses the exception)
        """)
    got = [(r["broad"], r["bare"], r["silent"]) for r in sorted(records, key=lambda r: r["line"])]
    assert got == [
        (True, False, True),
        (True, True, True),
        (True, False, False),
        (False, False, True),
        (False, False, False),
        (True, False, False),
    ]


def test_silent_ok_marker_explains_only_the_marked_handler(tmp_path):
    records = _records(tmp_path, """
        import os
        def cleanup(p):
            try:
                os.remove(p)
            except FileNotFoundError:  # silent-ok: already removed by a concurrent cleanup
                pass
            try:
                os.remove(p)
            except OSError:
                pass
        """)
    by_line = sorted(records, key=lambda r: r["line"])
    assert [r["explained"] for r in by_line] == [True, False]
    assert scan.summarize(records)["silent_unexplained"] == 1


def test_a_comment_without_the_marker_does_not_explain(tmp_path):
    records = _records(tmp_path, """
        try:
            pass
        except Exception:  # ignore
            pass
        """)
    assert records[0]["silent"] and not records[0]["explained"]


def test_syntax_errors_are_reported_not_hidden(tmp_path):
    records = _records(tmp_path, "def broken(:\n")
    assert records[0]["kind"] == "syntax-error"
    assert scan.main([str(tmp_path / "sample.py")]) == 2


def test_ceiling_rejects_any_area_increase_and_unlisted_areas():
    summary = {"silent_unexplained": 5, "by_area": {
        "core": {"silent_unexplained": 3}, "tabs": {"silent_unexplained": 2}}}
    assert scan.check_ceiling(summary, {"silent_unexplained": {"total": 5, "core": 3, "tabs": 2}}) == []
    assert scan.check_ceiling(summary, {"silent_unexplained": {"total": 5, "core": 2, "tabs": 3}}) == ["core 3 > 2"]
    assert scan.check_ceiling(summary, {"silent_unexplained": {"total": 4, "core": 3, "tabs": 2}}) == ["total 5 > 4"]
    assert scan.check_ceiling(summary, {"silent_unexplained": {"core": 3}}) == ["tabs 2 > 0"]


def test_ceiling_file_is_consistent():
    ceiling = json.loads(CEILING.read_text(encoding="utf-8"))["silent_unexplained"]
    areas = {k: v for k, v in ceiling.items() if k != "total"}
    assert all(isinstance(v, int) and v >= 0 for v in ceiling.values())
    assert ceiling["total"] <= sum(areas.values())


def test_repository_does_not_exceed_the_unexplained_silent_ceiling():
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "quality" / "exception_scan.py"),
                           "--check", str(CEILING)], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
