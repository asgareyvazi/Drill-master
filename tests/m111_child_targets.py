"""M111 test targets for ``core.isolated_parse.run_isolated`` (imported by spawn children; synthetic only)."""
from __future__ import annotations

import os
import signal
import time


class Opaque:
    """Not plain data: must never be accepted from a parser process."""


def hang(conn, cancel_event, request):
    while True:                                   # ignores the cancel event: needs terminate()
        time.sleep(0.05)


def hang_ignoring_terminate(conn, cancel_event, request):
    if hasattr(signal, "SIGTERM") and os.name == "posix":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(0.05)


def crash(conn, cancel_event, request):
    os._exit(3)


def send_opaque(conn, cancel_event, request):
    conn.send({"status": "OK", "prepared": Opaque()})


def slow_ok(conn, cancel_event, request):
    time.sleep(float(request.get("sleep", 1.0)))
    conn.send({"status": "OK", "prepared": {"late": True}, "child_pid": os.getpid()})


def honour_cancel(conn, cancel_event, request):
    while not cancel_event.is_set():
        time.sleep(0.02)
    conn.send({"status": "OK", "prepared": {"after_cancel": True}})


def pid_alive(pid: int) -> bool:
    """Whether ``pid`` is a running process (portable; never sends a signal on Windows)."""
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:                                          # a zombie is not a running child
        with open(f"/proc/{pid}/stat", encoding="ascii") as handle:
            return handle.read().split()[2] != "Z"
    except OSError:
        return True
