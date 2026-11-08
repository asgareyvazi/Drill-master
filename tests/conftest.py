"""Explicit, disposable test-process defaults; application defaults stay production.

Configure before collection/session fixtures. Individual production tests override
or remove settings and exercise the real fail-closed policy. Never seed fixtures
in the normal per-user database when pytest is run without an explicit mode.
"""
import gc
import os
from pathlib import Path
import tempfile
import threading


def pytest_configure(config):
    config._drillmaster_test_mode_added = not any(
        key in os.environ for key in ("DRILLMASTER_ENV", "DRILLMASTER_ENVIRONMENT")
    )
    config._drillmaster_previous_paths = {key: os.environ.get(key) for key in (
        "DRILLMASTER_DATA_DIR", "DRILLMASTER_DB_PATH", "DRILLMASTER_LOG_DIR",
        "DRILLMASTER_BACKUP_DIR", "DRILLMASTER_AI_SETTINGS_PATH",
        "DRILLMASTER_MAPPING_MEMORY_PATH", "DRILLMASTER_STANDARDS_PATH",
        "DRILLMASTER_MINERU_SETTINGS_PATH",
    )}
    config._drillmaster_test_directory = tempfile.TemporaryDirectory(
        prefix="drillmaster-tests-", ignore_cleanup_errors=True)
    directory = config._drillmaster_test_directory.name
    # A supplied ENV=test is not proof that a supplied database is disposable.
    # Preserve explicit mode, but isolate paths in every pytest invocation.
    for key in config._drillmaster_previous_paths:
        os.environ.pop(key, None)
    if config._drillmaster_test_mode_added:
        os.environ["DRILLMASTER_ENV"] = "test"
    os.environ["DRILLMASTER_DATA_DIR"] = directory
    os.environ["DRILLMASTER_DB_PATH"] = str(Path(directory) / "test-session.db")
    _arm_hang_watchdog_output()
    config._drillmaster_gc_was_enabled = gc.isenabled()     # restored as found by pytest_unconfigure
    _install_session_gc_policy()



import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_session_principal():
    """Restore the process-wide signed-in principal after every test (M46).

    ``core.permissions.permissions`` is a module singleton.  Tests that sign a
    user in (``permissions.set_user``) without restoring it leaked that user
    into every later test: with an in-memory database the leaked user id then
    fails the mandatory audit's foreign key, imports roll back, and the later
    test fails (or passes for the wrong reason) depending on file order -
    e.g. ``test_p0_permissions`` before ``test_document_library``.  Each test
    still sets the principal it needs; nothing here grants a permission.
    """
    from core.permissions import permissions
    previous = permissions._user
    try:
        yield
    finally:
        permissions._user = previous


def flush_deferred_deletes() -> int:
    """Destroy the Qt objects whose ``deleteLater()`` is pending; returns how many widgets went away.

    D52: tests call ``deleteLater()`` outside an event loop and ``processEvents()`` does not run those deletions,
    so the objects stayed alive until the next nested ``QEventLoop.exec()`` - which then spent its time destroying
    the earlier modules' widgets (27,126 widgets before the M111 dialog test, 0.83 s, during which its 20 ms GUI
    timer could not fire). The application's own event loop destroys them continuously; this restores that parity.
    Qt is touched only when a test module already imported it.
    """
    import sys
    if "PySide6.QtWidgets" not in sys.modules:
        return 0
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        return 0
    before = len(QApplication.allWidgets())
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    return before - len(QApplication.allWidgets())


@pytest.fixture(autouse=True, scope="module")
def _flush_deferred_deletes_per_module():
    """After each test module (and after its own module fixtures), run the deletions it left pending (D52)."""
    yield
    flush_deferred_deletes()


# ---- D53: cyclic garbage collection only on the main (GUI) thread, as the application runs it ----------
# ``app.py`` installs ``core.qt_gc`` (M50) before any worker starts: automatic collection is off and a GUI
# thread timer collects. The test session ran with the interpreter default instead, so a collection could start
# in whichever thread allocated - a background ``ContextJobRunner`` read compiling SQLAlchemy - and destroy
# the cyclic garbage of earlier tests there: pyqtgraph plot items, a ``QGraphicsWidget``, 204
# ``QTableWidgetItem`` wrappers (traced with a ``gc.callbacks`` probe at the end of ``tests/test_m44_ui.py``).
# GUI objects destroyed off the GUI thread left the widget set corrupt and the next ``QApplication.allWidgets()``
# segfaulted. The session now follows the application's rule; the ``core.qt_gc`` singleton itself is left to the
# tests that exercise it.
_GC_WATCH = {"worker_collections": 0, "worker_threads": [], "reenabled": []}
_gc_timer = None


def _gc_watch(phase, _info):
    """``gc.callbacks`` hook; it runs in the collecting thread, so it only counts."""
    if phase == "start" and threading.current_thread() is not threading.main_thread():
        _GC_WATCH["worker_collections"] += 1
        if len(_GC_WATCH["worker_threads"]) < 10:
            _GC_WATCH["worker_threads"].append(threading.current_thread().name)


def collect_due_garbage() -> None:
    """The ``core.qt_gc`` M50 rule, main thread only: collect each generation whose threshold is exceeded."""
    if threading.current_thread() is not threading.main_thread():
        return
    threshold = gc.get_threshold()
    count0, count1, count2 = gc.get_count()
    if count0 > threshold[0]:
        gc.collect(0)
        if count1 > threshold[1]:
            gc.collect(1)
            if count2 > threshold[2]:
                gc.collect(2)


def _install_session_gc_policy() -> None:
    gc.disable()
    if _gc_watch not in gc.callbacks:
        gc.callbacks.append(_gc_watch)


def _arm_gc_timer() -> None:
    """Once a QApplication exists, also collect from a GUI-thread timer while tests process events."""
    global _gc_timer
    import sys
    if _gc_timer is not None or "PySide6.QtWidgets" not in sys.modules:
        return
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    _gc_timer = QTimer(app)
    _gc_timer.setInterval(1000)
    _gc_timer.timeout.connect(collect_due_garbage)
    _gc_timer.start()


@pytest.fixture(autouse=True)
def _gui_thread_garbage_collection(request):
    """Collect what is due on the main thread after every test (D53); ``interpreter_gc`` tests get the default."""
    _arm_gc_timer()
    interpreter = request.node.get_closest_marker("interpreter_gc") is not None
    if interpreter:
        gc.enable()
    try:
        yield
    finally:
        if interpreter:
            gc.disable()
        elif gc.isenabled():              # a test switched automatic collection back on: the qt_gc watchdog rule
            _GC_WATCH["reenabled"].append(request.node.nodeid)
            gc.disable()
        collect_due_garbage()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if _GC_WATCH["reenabled"]:
        terminalreporter.write_line(
            f"D53 GC policy: automatic collection was switched back on by {len(_GC_WATCH['reenabled'])} test(s) "
            f"and disabled again: {', '.join(_GC_WATCH['reenabled'][:10])}")
    if _GC_WATCH["worker_collections"]:
        terminalreporter.write_line(
            f"D53 GC policy: {_GC_WATCH['worker_collections']} collection(s) started off the main thread "
            f"(threads: {', '.join(_GC_WATCH['worker_threads'])})")


_HANG_SECONDS_ENV = "DRILLMASTER_TEST_HANG_SECONDS"
_hang_fd = None


def _hang_seconds() -> int:
    """Per-test hang limit in seconds from the environment; 0 (off) when unset or invalid."""
    try:
        value = int(os.environ.get(_HANG_SECONDS_ENV, "0"))
    except ValueError:
        return 0
    return value if value > 0 else 0


def _arm_hang_watchdog_output():
    """Keep a duplicate of the REAL stderr for the hang watchdog (M124).

    Opt-in (``verify_release.py`` sets the variable for its pytest run).  A test that never ends used to
    run into the CI job timeout, which cancels the job and loses every line of the captured output (the
    3.13 leg at ``b820552``), so a hang could not be told from a slow runner.  ``pytest_configure`` runs
    while pytest's global capture is suspended, so fd 2 is the real descriptor here; during a test it is
    redirected to a capture file that dies with the process.  The same technique as pytest's own
    faulthandler plugin.
    """
    global _hang_fd
    if _hang_seconds() and _hang_fd is None:
        _hang_fd = os.dup(2)


def _arm_hang_watchdog():
    """Re-arm faulthandler's watchdog for the test that starts now.

    faulthandler's watchdog is a C thread, so it fires even when the hang holds the GIL; it dumps every
    thread's stack to the real stderr and exits the process.  ``verify_release.describe_hang`` turns that
    dump into a CI annotation naming the test.  Nothing is retried and no test is skipped: the run FAILS.
    """
    seconds = _hang_seconds()
    if seconds and _hang_fd is not None:
        import faulthandler
        faulthandler.dump_traceback_later(seconds, exit=True, file=_hang_fd)


_CRASH_BREADCRUMB_ENV = "DRILLMASTER_CRASH_BREADCRUMB"
_CRASH_BREADCRUMB_PREFIX = "DRILLMASTER-TEST-START "


def pytest_runtest_logstart(nodeid, location):
    """Write the active test's identity where a hard interpreter death cannot lose it.

    A fatal crash during pytest's report pipeline (formatting or recording a result) leaves no JUnit
    report and a faulthandler stack of pytest's own plumbing, which names no test at either end -- three
    consecutive Windows release runs died in three different innocent places that way.  The identity has
    to be recorded *before* that phase, on the unbuffered error descriptor (the same channel faulthandler
    itself uses), or buffered output dies with the process.  Opt-in via the environment so every other
    run is byte-for-byte unchanged; ``packaging/junit_report.py`` quotes the last breadcrumb into the
    crash annotation.  A breadcrumb must never fail a test, so a dead descriptor is swallowed.
    """
    _arm_hang_watchdog()
    if os.environ.get(_CRASH_BREADCRUMB_ENV) != "1":
        return
    try:
        os.write(2, f"{_CRASH_BREADCRUMB_PREFIX}{nodeid}\n".encode("utf-8", errors="backslashreplace"))
    except OSError:
        return


def pytest_runtest_logfinish(nodeid, location):
    """The test (with its setup and teardown) ended: the watchdog covers tests only."""
    if _hang_fd is not None:
        import faulthandler
        faulthandler.cancel_dump_traceback_later()


def pytest_unconfigure(config):
    global _hang_fd
    if _hang_fd is not None:
        import faulthandler
        faulthandler.cancel_dump_traceback_later()
        os.close(_hang_fd)
        _hang_fd = None
    if getattr(config, "_drillmaster_test_mode_added", False):
        os.environ.pop("DRILLMASTER_ENV", None)
    for key, value in config._drillmaster_previous_paths.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    config._drillmaster_test_directory.cleanup()
    if _gc_watch in gc.callbacks:
        gc.callbacks.remove(_gc_watch)
    if getattr(config, "_drillmaster_gc_was_enabled", False):
        gc.enable()
