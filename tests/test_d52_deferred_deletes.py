"""D52: widgets whose deleteLater() is pending are destroyed at the end of every test module.

Without that, the first nested QEventLoop.exec() of a later test destroyed every earlier module's widgets
(27,126 before the M111 dialog test) and stalled the GUI timer that test measures.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from conftest import flush_deferred_deletes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_process_events_leaves_deferred_deletes_and_the_helper_runs_them(app):
    destroyed = []
    widget = QWidget()
    widget.destroyed.connect(lambda *_a: destroyed.append(True))
    widget.deleteLater()
    del widget
    QApplication.processEvents()                 # outside an event loop: the deletion stays pending
    assert destroyed == []
    assert flush_deferred_deletes() >= 1 and destroyed == [True]


def test_the_conftest_flushes_between_modules(tmp_path):
    """Two real test modules under the repository's conftest: the second sees the first module's widget gone."""
    (tmp_path / "conftest.py").write_text((ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"),
                                          encoding="utf-8")
    common = ("import os\nos.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
              "import builtins\nfrom PySide6.QtWidgets import QApplication, QWidget\n"
              "app = QApplication.instance() or QApplication([])\n")
    (tmp_path / "test_a_first.py").write_text(common + (
        "def test_leave_a_pending_delete():\n"
        "    builtins.d52_destroyed = []\n"
        "    w = QWidget()\n"
        "    w.destroyed.connect(lambda *_a: builtins.d52_destroyed.append(True))\n"
        "    w.deleteLater()\n"
        "    QApplication.processEvents()\n"
        "    assert builtins.d52_destroyed == []\n"), encoding="utf-8")
    (tmp_path / "test_b_second.py").write_text(common + (
        "def test_the_previous_module_was_flushed():\n"
        "    assert builtins.d52_destroyed == [True]\n"), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    done = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", str(tmp_path)],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    assert "2 passed" in done.stdout
