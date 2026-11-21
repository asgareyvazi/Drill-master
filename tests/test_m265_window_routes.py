"""M263 / M265 (D74): ownership of the routes from process-wide objects into one MainWindow.

The process-wide ``SelectionManager`` outlives every window.  Before M265 a closed window's tabs stayed
connected to it and loaded every later selection for a hidden window, and the ``StatusBarManager`` singleton
held the last window strongly.  On an accepted close the window now cuts its recorded routes and the singleton
forgets it.  The closed window is NOT destroyed (destroying or freeing closed windows reaches the D63 native
crash; see docs/mission-reports/m261-m290-evidence/).  Real MainWindow, SYNTHETIC file database, offscreen Qt.
"""
from __future__ import annotations

import gc
import os
import time
import weakref

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QSettings, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.managers import StatusBarManager  # noqa: E402
from core.qt_lifetime import SignalRoutes, weak_or_strong  # noqa: E402
from core.selection_manager import SelectionManager  # noqa: E402


class _Sender(QObject):
    changed = Signal(int)


class _Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.seen = []

    def on_changed(self, value):
        self.seen.append(value)


def test_routes_deliver_until_disconnected_and_refuse_a_duplicate():
    app = QApplication.instance() or QApplication([])
    sender, receiver = _Sender(), _Receiver()
    routes = SignalRoutes()
    routes.connect(sender.changed, receiver.on_changed)
    with pytest.raises(ValueError):
        routes.connect(sender.changed, receiver.on_changed)
    sender.changed.emit(1)
    assert receiver.seen == [1]
    assert routes.disconnect_all() == 1
    assert len(routes) == 0
    sender.changed.emit(2)
    assert receiver.seen == [1], "a disconnected route still delivered"
    assert routes.disconnect_all() == 0, "a second disconnect must find nothing"
    del app


def test_the_route_registry_does_not_make_its_owner_cyclic_garbage():
    """A registry stored on its owner that held the owner's bound methods made every tab cyclic garbage, freed
    only inside a later gc pass - the D63 path (test_m132 SIGSEGV 2/2 until the registry recorded weak methods).
    With automatic gc off, dropping the owner's last reference must free it by reference counting alone."""
    from core.qt_lifetime import routes_of

    app = QApplication.instance() or QApplication([])
    sender, receiver = _Sender(), _Receiver()
    routes_of(receiver).connect(sender.changed, receiver.on_changed)
    sender.changed.emit(7)
    assert receiver.seen == [7]
    ref = weakref.ref(receiver)
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        del receiver
        assert ref() is None, "the route registry keeps its owner alive (reference cycle)"
    finally:
        if was_enabled:
            gc.enable()
    sender.changed.emit(8)                          # the freed receiver's connection went with its QObject
    del app


def test_disconnect_all_skips_a_slot_whose_owner_is_gone():
    routes = SignalRoutes()
    sender, receiver = _Sender(), _Receiver()
    routes.connect(sender.changed, receiver.on_changed)
    del receiver
    assert routes.disconnect_all() == 0
    assert len(routes) == 0


def test_weak_or_strong_keeps_none_and_test_doubles():
    assert weak_or_strong(None) is None
    plain = type("Plain", (), {})()
    ref = weak_or_strong(plain)
    assert ref() is plain
    del plain
    assert ref() is None, "a weak reference must not keep the object alive"
    slotted = 3.5                                   # floats cannot be weakly referenced: kept strongly
    assert weak_or_strong(slotted)() == 3.5


def _pump(seconds=0.2):
    app = QApplication.instance()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    from core.permissions import permissions, session_user
    from document_link_fixtures import build_link_world
    from synthetic_operations import make_file_database

    app = QApplication.instance() or QApplication([])
    work = tmp_path_factory.mktemp("m265_routes")
    mp = pytest.MonkeyPatch()
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"}.items():
        mp.setenv(key, value)
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    db = make_file_database(work / "m265.db")
    ids = build_link_world(db)
    previous = permissions.user
    user = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    yield db, ids, user
    SelectionManager().clear()
    permissions.set_user(previous)
    db.engine.dispose()
    mp.undo()
    del app


def _open(db, user):
    from main_window import MainWindow

    win = MainWindow(db_manager=db, user=user, startup_result=None)
    win.show()
    _pump(0.4)
    end = time.monotonic() + 10
    while win._hierarchy_worker is not None and time.monotonic() < end:
        _pump(0.05)
    return win


def _close(win):
    end = time.monotonic() + 10
    while win._hierarchy_worker is not None and time.monotonic() < end:
        _pump(0.05)
    win._close_confirmed = True
    win.close()
    _pump(0.2)


def _route_total(win):
    owners = [win, *win.findChildren(QObject)]
    return sum(len(o.__dict__["_lifetime_routes"]) for o in owners
               if hasattr(o, "__dict__") and isinstance(o.__dict__.get("_lifetime_routes"), SignalRoutes))


@pytest.fixture(scope="module")
def first_window(world):
    """Window A: opened, followed one selection, closed once - shared by the tests below.

    Closed windows stay alive by design (D63), so every window built here is retained for the rest of the
    session; M267 measured about 85 MB per window, hence one shared window instead of one per test."""
    db, ids, user = world
    selection = SelectionManager()
    selection.clear()
    win = _open(db, user)
    seen = {}
    try:
        seen["opened_routes"] = _route_total(win)
        selection.select_well(ids["alpha"], {"id": ids["alpha"], "name": "SYN-M265-ALPHA"}, force=True)
        _pump(0.3)
        seen["label_open"] = win.current_well_label.text()
        seen["well_info_open"] = win.well_info_tab.current_well_id
        seen["status_bar_open"] = StatusBarManager()._main_window is win
    finally:
        selection.clear()
        _pump(0.1)
        _close(win)
    yield win, seen


def test_an_open_window_follows_the_selection_and_a_closed_one_stops(world, first_window):
    _db, ids, _user = world
    win, seen = first_window
    selection = SelectionManager()
    opened_routes = seen["opened_routes"]
    assert opened_routes >= 40, opened_routes          # 6 per DrillTabBase tab + the window's own routes
    assert "SYN-M265-ALPHA" in seen["label_open"]
    assert seen["well_info_open"] == ids["alpha"]
    assert seen["status_bar_open"]
    assert win._closed_route_count == opened_routes, "every recorded route is cut exactly once"
    assert _route_total(win) == 0
    assert StatusBarManager()._main_window is None, "the status-bar singleton forgets the closed window"
    label_after_close = win.current_well_label.text()
    selection.select_well(ids["twin_1"], {"id": ids["twin_1"], "name": "SYN-M265-STALE"}, force=True)
    _pump(0.3)
    assert "SYN-M265-STALE" not in win.current_well_label.text(), "a closed window received a stale update"
    assert win.current_well_label.text() == label_after_close
    assert win.well_info_tab.current_well_id != ids["twin_1"], "a closed window's tab loaded a later selection"
    selection.clear()


def test_reopening_creates_one_route_set_and_routes_do_not_accumulate(world, first_window):
    """Window B after A: the same number of routes as A had (no accumulation), B follows, A stays cut off."""
    db, ids, user = world
    first, seen = first_window
    selection = SelectionManager()
    first_label = first.current_well_label.text()
    win = _open(db, user)
    try:
        assert _route_total(win) == seen["opened_routes"], (_route_total(win), seen["opened_routes"])
        selection.select_well(ids["alpha"], {"id": ids["alpha"], "name": "SYN-M265-CYCLE-1"}, force=True)
        _pump(0.3)
        assert "SYN-M265-CYCLE-1" in win.current_well_label.text()
        assert StatusBarManager()._main_window is win
        assert first.current_well_label.text() == first_label, "the first, closed window followed the reopen"
        assert _route_total(first) == 0
    finally:
        selection.clear()
        _pump(0.1)
        _close(win)
    assert _route_total(win) == 0
    assert win._closed_route_count == seen["opened_routes"]


def test_the_status_bar_singleton_does_not_keep_a_window_alive():
    app = QApplication.instance() or QApplication([])
    manager = StatusBarManager()
    previous = manager._main_window_ref

    class _Window(QObject):
        status_label = None

    window = _Window()
    probe = weakref.ref(window)
    manager.register_main_window(window)
    assert manager._main_window is window
    was_enabled = gc.isenabled()
    gc.disable()                # reference counting alone: no collection pass that could free unrelated Qt garbage
    try:
        del window
        assert probe() is None, "the singleton held the window strongly"
    finally:
        if was_enabled:
            gc.enable()
    assert manager._main_window is None
    manager._main_window_ref = previous
    del app


def test_unregistering_another_window_keeps_the_registered_one():
    """Closing window A must not detach the status bar from window B, which registered after it."""
    manager = StatusBarManager()
    previous = manager._main_window_ref

    class _Window(QObject):
        status_label = None

    first, second = _Window(), _Window()
    try:
        manager.register_main_window(first)
        manager.register_main_window(second)
        manager.unregister_main_window(first)
        assert manager._main_window is second
        manager.unregister_main_window(second)
        assert manager._main_window is None
    finally:
        manager._main_window_ref = previous
