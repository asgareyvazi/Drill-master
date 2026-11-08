#!/usr/bin/env python3
"""D46 probe: what CPU-bound Python threads do to a thread that releases the GIL around C calls.

No Qt and no product code.  For 0, 1, 2 and 4 "burner" threads (the loop of the M122 load body:
``x = (x * 31 + 7) % 1000003``) it measures, in a fresh run per burner count:

* the extra wait of ``time.sleep(0.01)`` - the GIL re-acquisition after a blocking call;
* ``executemany`` of N rows into an in-memory SQLite table and ``fetchall`` of the same N rows - the
  ``sqlite3`` module releases the GIL around every step, so each row is one re-acquisition;
* a pure-Python loop (the victim keeps the GIL once it has it).

Mechanism (CPython ``Python/ceval_gil.c``, ``take_gil``): a waiting thread asks the holder to drop the
GIL only when its timed wait (the switch interval, 5 ms) expired *and no switch happened meanwhile*.
With two or more burners the GIL changes hands between the burners every interval, so the waiter's
request is suppressed and it gets the GIL only when it happens to win a hand-off.  Each re-acquisition
then costs up to many intervals, and code that re-acquires per row or per callback slows by orders of
magnitude while pure-Python code does not.

Usage::

    python tools/quality/d46_gil_convoy_probe.py [--rows 3000] [--seconds 10] [--json OUT]

The numbers depend on the machine (cores, load, scheduler); they are evidence of the mechanism, not a
gate.  SYNTHETIC data only.
"""
from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import subprocess
import sys
import threading
import time

BURNER_COUNTS = (0, 1, 2, 4)


def _burn(stop: threading.Event) -> None:
    x = 0
    while not stop.is_set():
        x = (x * 31 + 7) % 1000003


def _percentile(values: list, fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def measure(burners: int, rows: int, seconds: float) -> dict:
    """One measurement with ``burners`` CPU-bound threads running for the whole of it."""
    stop = threading.Event()
    threads = [threading.Thread(target=_burn, args=(stop,), daemon=True) for _ in range(burners)]
    for thread in threads:
        thread.start()
    result: dict = {"burners": burners}

    def victim() -> None:
        started = time.monotonic()
        total = 0
        for i in range(300_000):
            total += i * i
        result["pure_python_loop_s"] = round(time.monotonic() - started, 4)
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE t(a)")
        started = time.monotonic()
        connection.executemany("INSERT INTO t VALUES (?)", ((i,) for i in range(rows)))
        result[f"executemany_{rows}_rows_s"] = round(time.monotonic() - started, 4)
        started = time.monotonic()
        connection.execute("SELECT a FROM t").fetchall()
        result[f"fetchall_{rows}_rows_s"] = round(time.monotonic() - started, 4)
        connection.close()
        waits = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            before = time.monotonic()
            time.sleep(0.01)
            waits.append(time.monotonic() - before - 0.01)
        result["sleep_extra_wait_ms"] = {"n": len(waits), "p50": round(_percentile(waits, 0.5) * 1000, 2),
                                         "p99": round(_percentile(waits, 0.99) * 1000, 2),
                                         "max": round(max(waits) * 1000, 2)}

    thread = threading.Thread(target=victim)
    thread.start()
    thread.join()
    stop.set()
    for burner in threads:
        burner.join(5)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=3000)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--one", type=int, help=argparse.SUPPRESS)      # internal: a single fresh run
    args = parser.parse_args(argv)
    if args.one is not None:
        print(json.dumps(measure(args.one, args.rows, args.seconds)))
        return 0
    runs = []
    for burners in BURNER_COUNTS:       # a fresh interpreter per count: no thread of a previous run is left
        out = subprocess.run([sys.executable, __file__, "--one", str(burners), "--rows", str(args.rows),
                              "--seconds", str(args.seconds)], capture_output=True, text=True, check=True)
        runs.append(json.loads(out.stdout))
        print(json.dumps(runs[-1]))
    report = {"probe": "D46 GIL convoy", "python": platform.python_version(),
              "implementation": platform.python_implementation(), "machine": platform.machine(),
              "cpu_count": __import__("os").cpu_count(), "switch_interval_s": sys.getswitchinterval(),
              "runs": runs}
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
