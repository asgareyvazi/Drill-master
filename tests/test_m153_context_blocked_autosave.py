"""M153: "Auto-save: CONTEXT_BLOCKED: 0 save operation(s) ..." on Procedure, Downhole, Drilling, Mud, Daily Report.

Lifecycle (traced in the real main window): every save-capable tab gets its own 5-minute auto-save timer
(``MainWindow`` -> ``AutoSaveManager.enable_for_widget``), visible or not. A selection change - an import's
``select_full_context`` included - reaches a hidden tab as a *pending* context that is loaded only when the tab is
shown (``DrillTabBase.showEvent``). Until then ``save_context_ready()`` is False and every timer tick hit the
CONTEXT_BLOCKED guard and logged a warning, although the hidden tab held no edits at all.

The guard is kept: a stale tab is never saved into the new context, edited or visible tabs are still blocked and
reported. Only a hidden, clean, pending tab is skipped by the timer (no saver is called: NO_CHANGES), and every
CONTEXT_BLOCKED message now says what is pending. Real Qt widgets and a real database (the M70 window fixture).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.database import Section  # noqa: E402
from core.managers import AutoSaveManager  # noqa: E402
from core.save_outcome import save_all  # noqa: E402
from test_m70_selection_audit import _pump, window  # noqa: E402,F401

# Drilling Parameters and Mud are sections of DrillingReportWidget (one timer, named sections in the summary).
TABS = ("ProcedureWidget", "DownholeWidget", "DrillingReportWidget", "DailyReportWidget")


def _tab(win, name):
    for index in range(win.tab_widget.count()):
        widget = win.tab_widget.widget(index)
        if type(widget).__name__ == name:
            return widget
    found = [w for w in win.findChildren(object) if type(w).__name__ == name]
    return found[0] if found else None


def _select_other_context(win, ids):
    from core.selection_manager import SelectionManager
    with win.db_manager.session_scope() as session:
        section = session.query(Section).filter_by(well_id=ids["twin_1"]).first()
        section_id = section.id if section else None
    manager = SelectionManager()
    manager.select_well(ids["twin_1"], {"name": "twin"}, force=True)
    if section_id is not None:
        manager.select_section(section_id, {"name": "s"}, force=True)
    _pump(0.2)


@pytest.mark.parametrize("name", TABS)
def test_m153_hidden_clean_pending_tab_is_not_reported_and_not_saved(window, name, caplog):  # noqa: F811
    win, db, ids = window
    tab = _tab(win, name)
    if tab is None:
        pytest.skip(f"{name} is not built in this window")       # recorded as NOT RUN, never as a pass
    win.tab_widget.setCurrentIndex(0)
    _pump(0.1)
    _select_other_context(win, ids)
    if tab.isVisible() or tab.save_context_ready():
        pytest.skip(f"{name} applied the context immediately (visible or no pending state)")
    called = []
    # The real bound saver stays in place (the guard finds its owner through it); the writers record calls.
    for section in getattr(tab, "_edit_sections", {}).values():
        section.writer = lambda section=section: called.append(section.name) or True
    with caplog.at_level("DEBUG", logger="core.managers"):
        clean = getattr(tab, "is_dirty", None) is False
        outcome = AutoSaveManager.save_widget(name, tab)
    if clean:
        assert outcome.disposition == "NO_CHANGES" and outcome.saved == 0 and called == []
        assert not [r for r in caplog.records if r.levelname == "WARNING" and "CONTEXT_BLOCKED" in r.getMessage()]
    else:
        # Unknown or dirty: the guard still blocks and says so.
        assert outcome.disposition == "CONTEXT_BLOCKED" and called == []


def test_m153_edited_pending_tab_is_still_blocked_with_an_explanation(window, monkeypatch):  # noqa: F811
    win, db, ids = window
    tab = _tab(win, "DailyReportWidget") or _tab(win, "ProcedureWidget")
    win.tab_widget.setCurrentIndex(0)
    _pump(0.1)
    _select_other_context(win, ids)
    if tab.isVisible() or tab.save_context_ready():
        pytest.skip("the tab applied the context immediately")
    monkeypatch.setattr(type(tab), "is_dirty", property(lambda self: True))
    for section in tab._edit_sections.values():
        monkeypatch.setattr(section, "writer", lambda: pytest.fail("stale tab saved into the new context"))
    outcome = AutoSaveManager.save_widget("Daily Report", tab)
    assert outcome.disposition == "CONTEXT_BLOCKED" and outcome.saved == 0
    summary = outcome.summary()
    assert "not loaded yet" in summary and "has not been opened since the selection changed" in summary


def test_m153_save_all_keeps_the_guard_for_a_clean_pending_tab(window):  # noqa: F811
    win, db, ids = window
    tab = _tab(win, "ProcedureWidget") or _tab(win, "DailyReportWidget")
    win.tab_widget.setCurrentIndex(0)
    _pump(0.1)
    _select_other_context(win, ids)
    if tab.save_context_ready():
        pytest.skip("the tab applied the context immediately")
    outcome = save_all([("Procedure", tab.save_data)])
    assert outcome.disposition == "CONTEXT_BLOCKED"           # an explicit save still reports the block
    win.tab_widget.setCurrentWidget(tab)
    _pump(0.3)
    assert tab.save_context_ready()                             # opening the tab loads the pending context


def test_m153_guard_answers_false_on_any_doubt():
    class Visible:
        is_dirty = False
        def save_context_ready(self):
            return False
        def isVisible(self):
            return True
    class Unknown(Visible):
        is_dirty = None
        def isVisible(self):
            return False
    class Broken(Visible):
        def save_context_ready(self):
            raise RuntimeError("x")
        def isVisible(self):
            return False
    class Hidden(Visible):
        def isVisible(self):
            return False
    assert not AutoSaveManager.hidden_clean_pending(Visible())
    assert not AutoSaveManager.hidden_clean_pending(Unknown())
    assert not AutoSaveManager.hidden_clean_pending(Broken())
    assert not AutoSaveManager.hidden_clean_pending(object())
    assert AutoSaveManager.hidden_clean_pending(Hidden())
