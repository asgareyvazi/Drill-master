"""D74 (M234 / M235): pending deletions run after every test; closed main windows that stay alive are reported.

Root cause (``docs/mission-reports/m231-m260-evidence/d74_*``): deletions requested by function fixtures waited for
the end of their module (``test_m87_w13_contracts``: 49,428 widgets, +717 MB heap), and every module fixture that
closes its ``MainWindow`` leaves it alive (lambda slots on child widgets capture the window; Shiboken holds those
connections where the garbage collector cannot see them).
The first is fixed; the second is only reported - destroying those windows exposed a garbage-collector segfault
(M237). No ``MainWindow`` is created here, so this module adds nothing to the leak.
"""
import gc
import weakref

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QWidget

import conftest

_PENDING: dict = {}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _alive(name: str) -> bool:
    return any(widget.objectName() == name for widget in QApplication.allWidgets())


def test_a_deletion_requested_by_a_test_is_left_pending_here(app):
    widget = QWidget()
    widget.setObjectName("d74-pending")
    widget.deleteLater()
    _PENDING["requested"] = True
    assert _alive("d74-pending")                                # nothing ran it yet


def test_the_previous_tests_pending_deletion_ran_after_its_teardown(app):
    assert _PENDING.get("requested"), "runs after the previous test (file order)"
    assert not _alive("d74-pending")


class _Window(QMainWindow):
    """The MainWindow pattern: a lambda slot on a child widget's signal captures the window."""

    def __init__(self, slot: str = "lambda"):
        super().__init__()
        self.button = QPushButton(self)
        self.setCentralWidget(self.button)
        if slot == "lambda":
            self.button.clicked.connect(lambda: self.setWindowTitle("clicked"))
        elif slot == "bound":
            self.button.clicked.connect(self.close)
        else:                                                    # a plain attribute back-reference
            self.button.owner = self


@pytest.mark.parametrize("slot, survives", [("lambda", True), ("bound", False), ("attribute", False)])
def test_only_a_lambda_slot_capturing_the_window_keeps_a_closed_window_alive(app, slot, survives):
    window = _Window(slot)
    window.setObjectName(f"d74-{slot}")
    window.show()
    window.close()
    probe = weakref.ref(window)
    del window
    gc.collect()
    QApplication.processEvents()
    gc.collect()
    assert (probe() is not None) is survives
    assert _alive(f"d74-{slot}") is survives
    if survives:
        probe().deleteLater()                                    # this small window is safe to destroy
        conftest.flush_deferred_deletes()
        assert not _alive(f"d74-{slot}")


def test_closed_main_windows_are_detected_and_visible_ones_are_not(app, monkeypatch):
    import main_window
    monkeypatch.setattr(main_window, "MainWindow", _Window)
    shown, closed = _Window(), _Window()
    try:
        shown.show()
        closed.show()
        closed.close()
        found = conftest.closed_main_windows()
        assert closed in found and shown not in found
    finally:
        for window in (shown, closed):
            window.close()
            window.deleteLater()
        conftest.flush_deferred_deletes()
