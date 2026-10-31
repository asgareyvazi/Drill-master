"""M52 §2.5: result slots never destroy a still-running QThread (native abort class).

Each case runs ``tests/m52_thread_release_child.py`` in a fresh process because
the failure mode is a process abort ("QThread: Destroyed while thread is still
running", SIGABRT / a native crash on Windows), which no in-process assertion can
observe.  The child keeps the worker inside ``run()`` after it emitted its result;
the case passes only when the process exits 0, prints ``OK <scenario>`` and the
worker was destroyed after ``finished``.  Offscreen Qt; not Windows desktop testing.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHILD = ROOT / "tests" / "m52_thread_release_child.py"


@pytest.mark.parametrize("scenario", ["helper", "status", "semantic", "mineru", "choices", "before_start",
                                      "chart_rerender"])
def test_result_slot_releases_the_worker_only_after_run_returned(scenario, tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "tests")]),
               DRILLMASTER_ENV="test", DRILLMASTER_DATA_DIR=str(tmp_path / "data"),
               DRILLMASTER_DB_PATH=str(tmp_path / "data" / "synthetic-m52-release.db"),
               DRILLMASTER_BACKUP_DIR=str(tmp_path / "data" / "backups"), DRILLMASTER_AI_IMPORT="0")
    with open(tmp_path / "child.out", "w+b") as out:          # bounded: a file, not an unbounded pipe
        process = subprocess.run([sys.executable, str(CHILD), scenario], cwd=str(ROOT), env=env,
                                 stdout=out, stderr=subprocess.STDOUT, timeout=180, check=False)
        out.seek(0)
        text = out.read()[-20000:].decode("utf-8", "replace")
    assert "Destroyed while thread is still running" not in text, text[-2000:]
    assert process.returncode == 0, (process.returncode, text[-2000:])
    assert f"OK {scenario}" in text, text[-2000:]
