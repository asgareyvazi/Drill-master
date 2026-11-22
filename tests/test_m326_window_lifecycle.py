"""M326 (D63 / D74): real MainWindow lifecycle under the product window-release policy.

The owner has not approved the PySide6 >= 6.8.2 pin (M324 decision package). Until then the product must keep the
RETAIN policy on the pinned 6.8.1.1: closed windows stay alive (never freed, so the D63 use-after-free cannot fire)
and they are cut off from the process (routes disconnected - covered by ``test_m265_window_routes``).

Each lifecycle test opens and closes REAL MainWindows on SYNTHETIC file databases in a SUBPROCESS
(``tools/quality/d63_window_release_probe.py``), so a native crash fails the test with its exit code instead of
killing the test runner.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from core import qt_lifetime as lt

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "quality" / "d63_window_release_probe.py"
SUMMARY = re.compile(r"mode=(\w+) windows=(\d+) alive_at_end=(\d+) live_widgets=(\d+) - no crash")


def _probe(mode: str, windows: int = 2, **env_extra: str):
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", **env_extra}
    proc = subprocess.run([sys.executable, str(PROBE), "--windows", str(windows), "--mode", mode], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=600)
    match = SUMMARY.search(proc.stdout)
    return proc, (None if match is None else {"windows": int(match.group(2)), "alive": int(match.group(3)),
                                              "widgets": int(match.group(4))})


def _locked_pyside() -> str:
    text = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
    match = re.search(r"^PySide6==([0-9.]+)", text, re.MULTILINE)
    assert match, "requirements-lock.txt does not pin PySide6"
    return match.group(1)


def test_the_lock_pin_and_the_retain_policy_agree_while_the_owner_decision_is_pending():
    """Changing the pin (M325) must be a deliberate, owner-approved act that also updates the D63/D74 register."""
    locked = _locked_pyside()
    policy = lt.window_release_policy(locked, env={})
    if lt._version_tuple(locked) < lt.FIXED_PYSIDE:
        assert policy["release"] is False and "use-after-free" in policy["reason"]
    else:   # pragma: no cover - only after an approved M325 pin change
        pytest.fail(f"PySide6 is pinned to {locked}: record the owner approval and close D63/D74 in the register, "
                    f"then replace this guard with the release-path lifecycle test.")


def test_product_policy_closes_real_windows_without_a_crash_and_retains_them_on_the_pinned_pyside():
    import PySide6

    # three windows: on 6.8.1.1 the freed-window crash fires while the THIRD window is built (M307: 4 / 5 runs), so a
    # policy that wrongly released windows on the pinned PySide6 fails here with rc 139 most of the time; the
    # deterministic guard against that mistake is the lock-pin test above.
    proc, summary = _probe("product", windows=3)
    assert proc.returncode == 0, f"rc={proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    assert summary is not None, proc.stdout[-2000:]
    release = lt.window_release_policy(PySide6.__version__, env={})["release"]
    assert summary["alive"] == (0 if release else summary["windows"])     # retained on 6.8.1.1, freed on >= 6.8.2
    assert f"'release': {release}" in proc.stdout                          # the policy the window actually applied


def test_the_operator_can_force_retention_of_real_windows():
    proc, summary = _probe("product", **{lt.RETAIN_ENV: "1"})
    assert proc.returncode == 0, f"rc={proc.returncode}\n{proc.stdout[-2000:]}"
    assert summary is not None and summary["alive"] == summary["windows"] == 2
    assert f"{lt.RETAIN_ENV}=1" in proc.stdout


def test_retained_windows_cost_is_bounded_and_stated():
    """Retention is not free: every retained window keeps its widget tree. The cost per window must stay constant
    (no growth from window to window), so a long session degrades linearly and visibly, never explosively."""
    proc1, one = _probe("retain", windows=1)
    proc3, three = _probe("retain", windows=3)
    assert proc1.returncode == proc3.returncode == 0
    assert one["alive"] == 1 and three["alive"] == 3
    per_window = one["widgets"]
    assert per_window > 0
    assert three["widgets"] <= 3 * per_window * 1.05, (one, three)          # linear, within 5 %
