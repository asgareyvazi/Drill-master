"""M324 / D51: the hang report of the PySide6 evaluation probe fits one GitHub annotation and names the threads."""
import importlib.util
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe_loop = _load("m324_probe_loop", "tools/quality/pyside_eval/probe_loop.py")

SITE = "/opt/hostedtoolcache/Python/3.13.18/x64/lib/python3.13/site-packages"
APP = "/home/runner/work/Drill-master/Drill-master"


def _dump():
    return "\n".join([
        "Timeout (0:02:15)!",
        "Thread 0x00007f5f03fff6c0 (most recent call first):",
        f'  File "{SITE}/sqlalchemy/engine/result.py", line 442 in _row_getter',
        f'  File "{SITE}/sqlalchemy/orm/query.py", line 2673 in all',
        f'  File "{APP}/core/operations_dashboard.py", line 365 in build_snapshot',
        f'  File "{APP}/tabs/home_tab.py", line 495 in job',
        f'  File "{APP}/core/async_workers.py", line 130 in run',
        "",
        "Thread 0x00007f5f0bfff6c0 (most recent call first):",
        f'  File "{APP}/tools/quality/d63_window_release_probe.py", line 163 in run',
        '  File "/usr/lib/python3.13/threading.py", line 975 in run',
        "",
        "Thread 0x00007f5f1ffff6c0 (most recent call first):",
        '  File "/usr/lib/python3.13/threading.py", line 363 in wait',
        f'  File "{APP}/core/db_maintenance.py", line 900 in _loop',
        "",
        "Thread 0x00007f5f2ffff6c0 (most recent call first):",
        f'  File "{SITE}/pyqtgraph/graphicsItems/AxisItem.py", line 350 in _updateLabel',
        f'  File "{SITE}/pyqtgraph/graphicsItems/AxisItem.py", line 633 in boundingRect',
        f'  File "{APP}/tools/quality/d63_window_release_probe.py", line 81 in pump',
        f'  File "{APP}/tools/quality/d63_window_release_probe.py", line 97 in one_window',
        f'  File "{APP}/tools/quality/d63_window_release_probe.py", line 172 in <module>',
    ])


def test_roles_and_frames_are_named():
    report = probe_loop.compact_hang_report(_dump() + "\n" + _dump())
    assert report.startswith("2 dump(s), 0 heartbeat(s) - NO heartbeat printed")
    assert " dash-worker: result.py:442 _row_getter < query.py:2673 all < operations_dashboard.py:365 build_snapshot" \
        in report
    assert " main: AxisItem.py:350 _updateLabel < AxisItem.py:633 boundingRect < d63_window_release_probe.py:81" \
        in report
    assert " hb: d63_window_release_probe.py:163 run" in report
    assert " maint: threading.py:363 wait < db_maintenance.py:900 _loop" in report
    assert report.count("DUMP ") == 2


def test_report_fits_one_annotation_and_keeps_the_newest_heartbeats():
    beats = "\n".join(f"HB {n} t={30 * n}s main=AxisItem.py:350 _updateLabel < " + "x" * 300 for n in range(1, 40))
    report = probe_loop.compact_hang_report(_dump() + "\n" + beats + "\n" + _dump())
    assert len(report) <= 3600
    assert "HB 39 " in report and "HB 1 " not in report
    assert "39 heartbeat(s)" in report


def test_heartbeat_line_lists_the_main_thread_first():
    probe = _load("m324_d63_probe", "tools/quality/d63_window_release_probe.py")
    lines = []
    reporter = threading.Thread(target=lambda: lines.append(probe.heartbeat_line(7, 12.4)), daemon=True)
    reporter.start()                                     # the reporting thread leaves itself out, as in the probe
    reporter.join(5)
    line = lines[0]
    assert re.match(r"HB 7 t=12s main=\S+:\d+ \S+", line), line   # main thread first, as file:line function


def test_heartbeat_thread_prints(capsys):
    probe = _load("m324_d63_probe_hb", "tools/quality/d63_window_release_probe.py")
    thread, stop = probe.start_heartbeat(0.05)
    seen = ""
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "HB 1 " not in seen:
            time.sleep(0.05)
            seen += capsys.readouterr().err
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()
    assert "HB 1 " in seen, f"no heartbeat line printed ({sys.version.split()[0]})"


GDB_SAMPLE = """\
[New LWP 4243]
Thread 4 (Thread 0x7f5f1ffff6c0 (LWP 4244) "QXcbEventQueue"):
#0  0x00007f5f2a51b4cd in __GI___poll (fds=0x1, nfds=1, timeout=-1) at ../sysdeps/unix/sysv/linux/poll.c:29
#1  0x00007f5f28a0c1e2 in QEventDispatcherUNIX::processEvents(QFlags<QEventLoop::ProcessEventsFlag>) () from /x/libQt6Core.so.6
Thread 3 (Thread 0x7f5f03fff6c0 (LWP 4242) "python"):
#0  0x00007f5f2a49a117 in __futex_abstimed_wait_common64 (private=0, cancel=true) at ./nptl/futex-internal.c:57
#1  __futex_abstimed_wait_common (cancel=true, private=0) at ./nptl/futex-internal.c:87
#2  0x00007f5f2a7c2a10 in take_gil (tstate=0x55d0) at Python/ceval_gil.c:331
#3  0x00007f5f2a7c3001 in PyEval_RestoreThread () from /opt/hostedtoolcache/Python/3.13.18/x64/lib/libpython3.13.so.1.0
Thread 1 (Thread 0x7f5f2b1e8740 (LWP 4200) "python"):
#0  0x00007f5f2a49e0a2 in __lll_lock_wait (futex=futex@entry=0x55d1, private=0) at ./nptl/lowlevellock.c:49
#1  0x00007f5f2a4a5a41 in pthread_mutex_lock@@GLIBC_2.2.5 () from /lib/x86_64-linux-gnu/libc.so.6
#2  0x00007f5f28b1d2c3 in QMutex::lock() () from /x/libQt6Core.so.6
#3  0x00007f5f29c4f111 in QGraphicsTextItem::setHtml(QString const&) () from /x/libQt6Widgets.so.6
"""


def test_gdb_report_puts_the_main_thread_and_blocked_threads_first():
    report = probe_loop.compact_gdb_report(GDB_SAMPLE)
    lines = report.splitlines()
    assert lines[0] == "native stacks: 3 thread(s)"
    assert lines[1] == ("T1 python: __lll_lock_wait < pthread_mutex_lock@@GLIBC_2.2.5 < QMutex::lock < "
                        "QGraphicsTextItem::setHtml")
    assert lines[2].startswith("T3 python: __futex_abstimed_wait_common64 < __futex_abstimed_wait_common < take_gil")
    assert lines[3].startswith("T4 QXcbEventQueue: __GI___poll < QEventDispatcherUNIX::processEvents")


def test_gdb_report_fits_one_annotation():
    many = "\n".join(
        f'Thread {n} (Thread 0x7f{n:04x} (LWP {5000 + n}) "worker"):\n' + "\n".join(
            f"#{k}  0x00007f in some_long_native_function_name_number_{k}_padding (a=1) at x.c:{k}"
            for k in range(30)) for n in range(1, 40))
    report = probe_loop.compact_gdb_report(many)
    assert len(report) <= 3900
    assert report.startswith("native stacks: 39 thread(s)\nT1 worker: ")


def test_hung_probe_is_killed_and_reported(tmp_path):
    script = tmp_path / "sleepy.py"
    script.write_text("import time\ntime.sleep(60)\n")
    started = time.monotonic()
    proc, native = probe_loop.run_probe([sys.executable, str(script)], timeout=1, native_dump=False)
    assert proc.returncode == "HANG" and "(no exit after 1 s)" in proc.stderr
    assert native == "" and time.monotonic() - started < 30
