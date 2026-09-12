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


# --------------------------------------------------------------------------
# Wellbore level (Schema v3): Well → Wellbore → Section → Report
# --------------------------------------------------------------------------
def test_well_change_clears_wellbore(selection):
    selection.select_well(1, {"id": 1, "name": "AZNS 12"})
    selection.select_wellbore(5, {"id": 5, "well_id": 1, "name": "Original"})
    selection.select_section(11, {"id": 11, "well_id": 1, "wellbore_id": 5})
    selection.select_report(111, {"id": 111, "well_id": 1, "wellbore_id": 5})
    assert selection.current_wellbore_id == 5

    selection.select_well(2, {"id": 2, "name": "AZNS 15"})
    assert selection.current_wellbore_id is None, "stale wellbore must be cleared"
    assert selection.current_section_id is None
    assert selection.current_report_id is None


def test_wellbore_change_clears_section_and_report(selection):
    selection.select_well(1, {"id": 1})
    selection.select_wellbore(5, {"id": 5, "well_id": 1})
    selection.select_section(11, {"id": 11, "well_id": 1, "wellbore_id": 5})
    selection.select_report(111, {"id": 111, "well_id": 1, "wellbore_id": 5})
    assert selection.current_section_id == 11
    assert selection.current_report_id == 111

    selection.select_wellbore(6, {"id": 6, "well_id": 1, "name": "ST #1"})
    assert selection.current_wellbore_id == 6
    assert selection.current_section_id is None, "section cleared on wellbore change"
    assert selection.current_report_id is None, "report cleared on wellbore change"


def test_cross_well_wellbore_is_rejected(selection):
    selection.select_well(1, {"id": 1, "name": "AZNS 12"})
    selection.select_wellbore(9, {"id": 9, "well_id": 2, "name": "other-well bore"})
    assert selection.current_wellbore_id is None, (
        "wellbore belonging to a different well must not enter the context"
    )


def test_cross_wellbore_section_is_rejected(selection):
    selection.select_well(1, {"id": 1})
    selection.select_wellbore(5, {"id": 5, "well_id": 1})
    selection.select_section(11, {"id": 11, "well_id": 1, "wellbore_id": 6})
    assert selection.current_section_id is None, (
        "section belonging to a different wellbore must not enter the context"
    )


def test_full_context_selects_wellbore(selection):
    selection.select_full_context(
        1, 11, 111,
        well_data={"id": 1},
        section_data={"id": 11, "well_id": 1, "wellbore_id": 5},
        report_data={"id": 111, "well_id": 1, "wellbore_id": 5},
        wellbore_id=5,
        wellbore_data={"id": 5, "well_id": 1},
    )
    assert selection.current_well_id == 1
    assert selection.current_wellbore_id == 5
    assert selection.current_section_id == 11
    assert selection.current_report_id == 111


def test_full_context_without_wellbore_stays_backward_compatible(selection):
    selection.select_full_context(
        1, 11, 111,
        well_data={"id": 1},
        section_data={"id": 11, "well_id": 1},
        report_data={"id": 111, "well_id": 1},
    )
    assert selection.current_well_id == 1
    assert selection.current_wellbore_id is None
    assert selection.current_section_id == 11
    assert selection.current_report_id == 111
