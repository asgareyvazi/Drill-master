"""M192: the 7.48 / 7.48052 pcf->ppg constants are inventoried; any silent change anywhere is noticed.

No global change is made (owner decision, M196). The difference is 0.007 %, far below the input resolution of a
mud balance (0.1 pcf / 0.01 ppg) - but two modules that convert the same weight differently must be visible.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "mission-reports" / "m171-m200-evidence" / "density_constants_m192.json"


def _tool():
    spec = importlib.util.spec_from_file_location("dci", ROOT / "tools" / "quality" / "density_constant_inventory_m192.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_inventory_matches_the_committed_evidence():
    stored = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert _tool().inventory()["by_file"] == stored["by_file"], (
        "a 7.48 / 7.48052 use was added, removed or changed: review it against the M196 owner decision and "
        "re-write the inventory with --write")


def test_the_difference_is_quantified_and_both_constants_are_in_use():
    data = _tool().inventory()
    assert data["relative_difference"] == pytest.approx(6.95e-5, rel=1e-2)
    assert data["totals"]["7.48"] > 0 and data["totals"]["7.48052"] > 0
    assert 75.0 / 7.48 == pytest.approx(10.0267, abs=1e-4) and 75.0 / 7.48052 == pytest.approx(10.0260, abs=1e-4)


@pytest.mark.parametrize("text, expected", [("x / 7.48\n", {"7.48": 1}), ("x * 7.48052\n", {"7.48052": 1}),
                                            ("42.0 / 7.4805\n", {"7.4805": 1}), ("17.481\n", {}), ("27.48\n", {})])
def test_the_patterns_count_each_constant_exactly(text, expected):
    tool = _tool()
    found = {name: len(p.findall(text)) for name, p in tool.PATTERNS.items() if p.findall(text)}
    assert found == expected
