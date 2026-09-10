"""SelectionManager context-coherence tests (master handoff §22).

Desired hierarchy: Well → Section → DDR.

* Selecting a parent must invalidate stale child context (already true).
* A child selection that explicitly belongs to a different well than the
  currently selected well must be rejected (guard added 2026-09-09).
* Payloads without ``well_id`` pass through unchanged — the guard is
  defensive and does not add an API requirement.
"""

import os

import pytest


def _qt_gui_importable() -> bool:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import PySide6.QtWidgets  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _qt_gui_importable(),
    reason="SelectionManager is a QObject; PySide6 GUI modules cannot load here",
)


@pytest.fixture()
def selection():
    from core.selection_manager import SelectionManager

    SelectionManager._instance = None  # reset the singleton between tests
    manager = SelectionManager()
    yield manager
    manager.clear()
    SelectionManager._instance = None


def test_parent_change_clears_children(selection):
    selection.select_well(1, {"id": 1, "name": "AZNS 12"})
    selection.select_section(11, {"id": 11, "well_id": 1})
    selection.select_report(111, {"id": 111, "well_id": 1})
    assert selection.current_section_id == 11
    assert selection.current_report_id == 111

    selection.select_well(2, {"id": 2, "name": "AZNS 15"})
    assert selection.current_well_id == 2
    assert selection.current_section_id is None, "stale section must be cleared"
    assert selection.current_report_id is None, "stale report must be cleared"


def test_section_change_clears_report(selection):
    selection.select_well(1, {"id": 1})
    selection.select_section(11, {"id": 11, "well_id": 1})
    selection.select_report(111, {"id": 111, "well_id": 1})
    selection.select_section(12, {"id": 12, "well_id": 1})
    assert selection.current_report_id is None


def test_cross_well_section_is_rejected(selection):
    selection.select_well(1, {"id": 1, "name": "AZNS 12"})
    selection.select_section(99, {"id": 99, "well_id": 2, "name": "other-well section"})
    assert selection.current_section_id is None, (
        "section belonging to a different well must not enter the context"
    )


def test_cross_well_report_is_rejected(selection):
    selection.select_well(1, {"id": 1, "name": "AZNS 12"})
    selection.select_section(11, {"id": 11, "well_id": 1})
    selection.select_report(777, {"id": 777, "well_id": 2})
    assert selection.current_report_id is None


def test_payloads_without_well_id_pass_through(selection):
    selection.select_well(1, {"id": 1})
    # main_window sometimes selects a report with only {"id": report_id}
    selection.select_report(123, {"id": 123})
    assert selection.current_report_id == 123


def test_matching_well_id_is_accepted(selection):
    selection.select_well(1, {"id": 1})
    selection.select_section(11, {"id": 11, "well_id": 1})
    assert selection.current_section_id == 11
    selection.select_report(111, {"id": 111, "well_id": 1})
    assert selection.current_report_id == 111
