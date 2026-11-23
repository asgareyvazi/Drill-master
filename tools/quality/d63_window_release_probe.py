"""M264 (D63) opt-in diagnostic: free closed MainWindows by reference counting and watch the process crash.

Not part of the test suite and not a fix.  The three tabs that store their window in a plain attribute
(``HomeTab.parent_window``, ``WellInfoTab.main_window``, ``DailyReportWidget.parent_window``) are switched to a
weak attribute AT RUNTIME, which is exactly what makes a closed window freeable (M265: lambda connections that
capture those tabs otherwise keep the window alive).  The probe then builds ``--windows`` real MainWindows on
fresh SYNTHETIC file databases one after the other, closes each, drops the last reference and reports.

Observed on db0cba3 + the M265 route changes (Python 3.11.2, PySide6 6.8.1.1, offscreen):
  --mode auto        (automatic gc, as Python ships)      3 windows: SIGSEGV in 3 / 3 runs (+2 / 2 under malloc)
  --mode collect     (gc.collect() right after each free)  3 windows: no crash in 2 / 2 runs
  --mode retain      (attributes left strong = product)    3 windows: no crash in 2 / 2 runs, 3 windows retained
  PYTHONMALLOC=debug with --mode auto                      no crash in 3 / 3 runs (the fault depends on reuse)
Native evidence (tools/quality/native/segv_bt.c via LD_PRELOAD, no gdb in the sandbox): the fault is
``call *0x30(%rax)`` - CPython's dict deallocation calling ``Py_TYPE(value)->tp_dealloc`` - with a NULL or
anonymous-memory function pointer, beneath recursive ``SbkDeallocWrapper`` frames: a value in an instance
``__dict__`` of a deallocating Shiboken wrapper is an already-freed object.  Which object is NOT identified.

    LD_LIBRARY_PATH=... QT_QPA_PLATFORM=offscreen python tools/quality/d63_window_release_probe.py --windows 3
    [LD_PRELOAD=/path/segv_bt.so]   (gcc -shared -fPIC -o segv_bt.so tools/quality/native/segv_bt.c -ldl)
"""
from __future__ import annotations

import argparse
import faulthandler
import gc
import os
import sys
import tempfile
import time
import weakref
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--mode", choices=("auto", "collect", "retain", "product"), default="auto",
                        help="product (M308): no runtime patch; the product's window_release_policy decides")
    parser.add_argument("--hang-dump", type=int, default=0,
                        help="M324: every N seconds dump every thread's Python stack to stderr (0 = off); two "
                             "dumps show whether a stuck thread still moves")
    args = parser.parse_args(argv)
    if args.hang_dump > 0:
        faulthandler.dump_traceback_later(args.hang_dump, repeat=True)
    work = Path(tempfile.mkdtemp(prefix="d63_probe_"))
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0", "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM",
                                                                                     "offscreen")}.items():
        os.environ[key] = value
    from PySide6.QtCore import QCoreApplication, QEvent, QSettings
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    from core.permissions import permissions, session_user
    from core.qt_lifetime import WeakWindowAttribute
    from core.selection_manager import SelectionManager
    from synthetic_operations import make_file_database

    if args.mode == "product":
        from core.qt_lifetime import window_release_policy
        print(f"product policy: {window_release_policy()}", flush=True)
    if args.mode not in ("retain", "product"):
        import tabs.home_tab as home
        import tabs.w1_well_info as w1
        import tabs.w2_Daily_Report as w2
        for cls, name in ((home.HomeTab, "parent_window"), (w1.WellInfoTab, "main_window"),
                          (w2.DailyReportWidget, "parent_window")):
            descriptor = WeakWindowAttribute()
            descriptor.__set_name__(cls, name)
            setattr(cls, name, descriptor)

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    def stage(index, text):                       # M324: where a run stops when it hangs
        print(f"window {index + 1}: {text}", flush=True)

    def one_window(index):
        stage(index, "building")
        db = make_file_database(work / f"w{index}.db")
        user = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
        permissions.set_user(user)
        db.enforce_authorization(permissions)
        from main_window import MainWindow
        win = MainWindow(db_manager=db, user=user, startup_result=None)
        stage(index, "constructed")
        win.show()
        pump(0.5)
        end = time.monotonic() + 10
        while win._hierarchy_worker is not None and time.monotonic() < end:
            pump(0.05)
        stage(index, f"shown (hierarchy worker {'running' if win._hierarchy_worker is not None else 'done'})")
        SelectionManager().clear()
        win._close_confirmed = True
        win.close()
        pump(0.2)
        stage(index, "closed")
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        db.engine.dispose()
        stage(index, "deferred deletes sent, database disposed")
        return weakref.ref(win)

    refs = []
    for index in range(args.windows):
        refs.append(one_window(index))
        print(f"window {index + 1}: alive after its last reference was dropped: {refs[-1]() is not None}",
              flush=True)
        if args.mode == "collect":
            gc.collect()
    stage(args.windows - 1, "final gc.collect()")
    gc.collect()
    alive = sum(ref() is not None for ref in refs)
    print(f"mode={args.mode} windows={args.windows} alive_at_end={alive} "
          f"live_widgets={len(QApplication.allWidgets())} - no crash", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
