"""A W3c well switch must not carry prior-well section forms into the new scope."""
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
    app = QApplication.instance() or QApplication([])

    from tabs.w3c_section_data import SectionDataWidget
    widget = SectionDataWidget()
    assert widget._tabs_ready
    widget.current_well_id = 1
    widget.current_section_id = 101
    widget.cement_tab.report_name.setText("Prior well cement report")
    widget.casing_tab.report_name.setText("Prior well casing report")
    widget.casing_tally_tab.tally_table.setRowCount(2)
    widget.casing_tally_tab.summary_text.setPlainText("Prior well tally")
    widget.bit_tab.bit_table.setRowCount(3)

    widget.on_well_changed(2, {"name": "New well"})

    assert widget.current_well_id == 2
    assert widget.current_section_id is None
    assert widget.cement_tab.report_name.text() == ""
    assert widget.casing_tab.report_name.text() == ""
    assert widget.casing_tally_tab.tally_table.rowCount() == 0
    assert widget.casing_tally_tab.summary_text.toPlainText() == ""
    assert widget.bit_tab.bit_table.rowCount() == 0
    print("W3C_WELL_SWITCH_SCOPE_OK")
    """
)


def test_w3c_well_switch_clears_prior_scope_in_isolated_qt_process():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-c", _CHILD], cwd=repo_root, env=env,
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0 or "W3C_WELL_SWITCH_SCOPE_OK" not in result.stdout:
        pytest.fail(f"W3c well-switch scope regression failed\n{result.stdout}\n{result.stderr}")
