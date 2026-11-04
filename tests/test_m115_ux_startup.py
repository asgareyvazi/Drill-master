"""M115: measured start-up breakdown and the right-to-left / left-to-right check on the real MainWindow.

Each direction runs ``tools/quality/ux_startup_m115.py`` in its own process (one MainWindow per process).
Offscreen Linux, SYNTHETIC data: NOT a Windows desktop measurement. No timing threshold is asserted (the
numbers are recorded in the capability matrix); the test pins what must hold on every machine.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "quality" / "ux_startup_m115.py"
#: English-only panels pinned left-to-right by design (M53 dashboard test; calculation history tables)
LTR_PINNED_TABS = {"HomeTab", "CalculationHistoryTab"}


def _run(tmp_path, rtl):
    out = tmp_path / ("rtl.json" if rtl else "ltr.json")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run([sys.executable, str(TOOL), "--json", str(out)] + (["--rtl"] if rtl else []),
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, f"exit status {proc.returncode} (negative = signal); stderr tail: {proc.stderr[-2500:]}"
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("m115")
    return {"ltr": _run(folder, False), "rtl": _run(folder, True)}


def test_the_startup_breakdown_accounts_for_every_tab(runs):
    for direction, result in runs.items():
        assert result["direction"] == direction
        assert result["tab_count"] == len(result["tabs"]) == len(result["visits"]) >= 20
        assert [t["class"] for t in result["tabs"]] == [v["class"] for v in result["visits"]]
        total = sum(t["ms"] for t in result["tabs"])
        assert abs(total - result["create_tabs_ms"]) <= 0.05 * result["create_tabs_ms"] + 5
        assert 0 < result["create_tabs_ms"] <= result["startup_ms"] + 300
        assert "not a Windows desktop measurement" in result["environment"]["note"]


def test_every_tab_opens_in_both_directions(runs):
    for result in runs.values():
        failures = [(v["tab"], v.get("error")) for v in result["visits"] if "error" in v or not v.get("visible")]
        assert failures == []


def test_every_tab_inherits_right_to_left_except_the_documented_english_only_panels(runs):
    assert {v["direction"] for v in runs["ltr"]["visits"]} == {"ltr"}
    pinned = {v["class"] for v in runs["rtl"]["visits"] if v["direction"] == "ltr"}
    assert pinned == LTR_PINNED_TABS
