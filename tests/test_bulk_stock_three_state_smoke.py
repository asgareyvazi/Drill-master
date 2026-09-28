"""Subprocess-isolated UI regression for W7 live bulk stock ("Current Stock").

``FuelWaterTab.update_bulk_stock_for_row`` recomputes the Current Stock cell from
the Initial/Received/Used cells. It must obey the SAME three-state contract the
same widget already implements on both boundaries it is flanked by:

* persistence -- ``_cell_float`` in ``save_bulk_materials_to_db``: "an EMPTY cell
  is 'not reported' (None) -- carry-forward/unknown downstream. A typed 0 is an
  explicit zero and is preserved exactly."
* loading -- ``_fmt_stock`` in ``load_bulk_materials_from_db``: "Unknown stock
  displays as an em dash, never as 0.0."

The original implementation did neither: it evaluated ``float(text or 0)``, so a
blank cell became a fabricated 0 and a fabricated 0-based Current Stock was
displayed (and, for the em dash that the loader itself writes, the float
conversion raised and the recomputation silently produced nothing).

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

    from PySide6.QtWidgets import QApplication, QTableWidgetItem
    app = QApplication.instance() or QApplication([])

    from tabs.w7_logistics_Widget import FuelWaterTab

    tab = FuelWaterTab()          # no DB manager, no well -> pure UI computation
    t = tab.bulk_table

    # Column contract: 1=Material, 2=Unit, 3=Initial, 4=Received, 5=Used,
    # 6=Current Stock. The em dash is what load_bulk_materials_from_db writes
    # for an unreported value.
    rows = [
        ("Barite", "kg", "100", "20", "10"),   # fully known -> 110.0
        ("Bentonite", "kg", "", "5", "0"),     # blank opening -> UNKNOWN
        ("CMC", "kg", "0", "0", "0"),          # explicit zeros are facts -> 0.0
        ("Caustic", "kg", "\\u2014", "1", "2"),  # em dash from the loader -> UNKNOWN
        ("Polymer", "kg", "", "", ""),         # nothing reported -> UNKNOWN
    ]
    for r, (name, unit, initial, received, used) in enumerate(rows):
        t.insertRow(r)
        for col, value in ((1, name), (2, unit), (3, initial), (4, received), (5, used)):
            t.setItem(r, col, QTableWidgetItem(value))

    # Drive the real user-edit path (cellChanged -> on_bulk_cell_changed) over
    # every quantity column of every row.
    for r in range(len(rows)):
        for col in (3, 4, 5):
            tab.on_bulk_cell_changed(r, col)

    def cell(r, c):
        it = t.item(r, c)
        return None if it is None else it.text()

    assert cell(0, 6) == "110.0", ("known stock", cell(0, 6))
    assert cell(2, 6) == "0.0", ("explicit zeros are a real fact", cell(2, 6))

    # The defect: a blank opening must NOT be turned into a 0-based balance.
    assert cell(1, 6) == "\\u2014", (
        "blank opening must leave the computed stock UNKNOWN, not fabricated",
        cell(1, 6),
    )
    assert cell(3, 6) == "\\u2014", (
        "em dash from the loader must stay UNKNOWN (and not raise)", cell(3, 6),
    )
    assert cell(4, 6) == "\\u2014", ("nothing reported -> UNKNOWN", cell(4, 6))

    # No fabricated numeric balance may appear for any unknown row.
    for r in (1, 3, 4):
        assert cell(r, 6) not in ("5.0", "0.0", "-1.0", "-2.0"), (
            "fabricated balance for unknown row", r, cell(r, 6),
        )

    print("W7_BULK_STOCK_THREE_STATE_OK")
    """
)


def test_w7_bulk_stock_three_state_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "W7_BULK_STOCK_THREE_STATE_OK" not in proc.stdout:
        pytest.fail(
            "W7 bulk stock three-state smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
