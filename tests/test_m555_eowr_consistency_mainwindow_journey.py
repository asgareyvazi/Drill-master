"""M555 (U5): real MainWindow journey — the W11 EOWR export of the selected well carries the data-consistency review
(a SYNTHETIC time log whose duration contradicts its interval is listed with its source record) and the stored row is
unchanged afterwards. Linux offscreen Qt (not Windows or desktop acceptance).
"""
from __future__ import annotations

from datetime import time

from test_m70_selection_audit import _pump, window  # noqa: F401  (module fixture reused)
from test_m467_eowr_mainwindow_journey import _export  # noqa: F401


def test_w11_eowr_lists_a_contradiction_without_changing_the_row(window, monkeypatch, tmp_path):  # noqa: F811
    from core.database import TimeLog24H

    win, db, ids = window
    with db.session_scope() as s:
        row = TimeLog24H(report_id=ids["report_1"], time_from=time(6, 0), time_to=time(12, 0), duration=4.5,
                         activity_description="SYN-M555 contradicting log")
        s.add(row)
        s.flush()
        row_id = row.id
    try:
        win.navigate_to({"type": "well", "id": ids["alpha"]})
        _pump(0.4)
        text = _export(win, monkeypatch, tmp_path / "alpha-consistency.html")
        assert "Data consistency review" in text
        assert f"time log {row_id}: 06:00:00-12:00:00 is 6 h but the stored duration is 4.5 h" in text
        assert f"time_logs_24h id {row_id} duration=4.5" in text
        assert "<td><b>consistency.time_log_interval</b></td><td>INCONSISTENT" in text
        with db.session_scope() as s:
            stored = s.get(TimeLog24H, row_id)
            assert stored.duration == 4.5 and stored.time_from == time(6, 0)

        win.navigate_to({"type": "well", "id": ids["twin_1"]})
        _pump(0.4)
        twin = _export(win, monkeypatch, tmp_path / "twin-consistency.html")
        assert "SYN-M555" not in twin and f"time log {row_id}:" not in twin
    finally:
        with db.session_scope() as s:
            obj = s.get(TimeLog24H, row_id)
            if obj is not None:
                s.delete(obj)
