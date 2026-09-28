"""Subprocess-isolated UI regression for W5 live inventory calculation (§2.1/§4).

The live "Remaining" cell computed by ``InventoryTab.calculate_inventory`` must
obey the SAME three-state contract as persistence: a MISSING opening yields an
UNKNOWN (blank) remaining rather than a fabricated 0-based number, and threshold
tinting only fires when the compared values are actually known. A freshly added
blank row (§4) must not assert reported zero quantities or fabricated
thresholds.

Runs the real widget in an isolated subprocess because native Qt aborts when
mixed with other Qt tests in the shared interpreter.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("PySide6")


_CHILD = textwrap.dedent(
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    app = QApplication.instance() or QApplication([])

    from tabs.w5_Equipment_Widget import InventoryTab

    tab = InventoryTab()
    t = tab.table

    # Row 0: fully known -> remaining computed (100 + 20 - 10 = 110), within
    #        min/max (10..500) -> green tint.
    # Row 1: blank opening -> remaining must stay UNKNOWN (blank), no tint.
    # Row 2: explicit 0 opening -> remaining is a real fact (0 + 0 - 0 = 0);
    #        below min (5) -> low tint.
    tab.load_table_data([
        ["Gloves", "PPE", "100", "20", "10", "", "pcs", "10", "500"],
        ["Rags",   "Cons", "",   "5",  "0",  "", "pcs", "",   ""],
        ["Bolts",  "Hw",   "0",  "0",  "0",  "", "pcs", "5",  "50"],
    ])

    tab.calculate_inventory()

    def cell(r, c):
        it = t.item(r, c)
        return "" if it is None else it.text()

    def bg_is_set(r, c):
        it = t.item(r, c)
        if it is None:
            return False
        b = it.background()
        return b is not None and b.style() != Qt.NoBrush

    assert cell(0, 5) == "110.00", ("known remaining", cell(0, 5))
    assert bg_is_set(0, 5), "known remaining within range should be tinted"

    assert cell(1, 5) == "", ("blank opening must stay unknown", cell(1, 5))
    assert not bg_is_set(1, 5), "unknown remaining must not be tinted"

    assert cell(2, 5) == "0.00", ("explicit zero opening is a fact", cell(2, 5))
    assert bg_is_set(2, 5), "known zero below min should be tinted low"

    # §4: a newly added default row must be blank in every quantity/threshold
    # column (unknown), never a reported zero or fabricated 10/100 thresholds.
    start = t.rowCount()
    tab.add_row()
    r = start
    for col in (2, 3, 4, 5, 7, 8):
        assert cell(r, col) == "", ("default row col not blank", col, cell(r, col))

    # Recalculating a table with the blank default row must not fabricate a
    # remaining value for it.
    tab.calculate_inventory()
    assert cell(r, 5) == "", ("default row remaining stays unknown", cell(r, 5))

    print("W5_LIVE_CALC_SMOKE_OK")
    """
)


def test_w5_live_calc_three_state_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "W5_LIVE_CALC_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W5 live calculate_inventory three-state smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
