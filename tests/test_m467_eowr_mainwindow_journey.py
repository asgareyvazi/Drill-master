"""M467: real MainWindow journey — the W11 "End of Well" tab exports an EOWR whose bit / time-log / request /
equipment sections come from the selected well's stored rows, whole-well and with the M465 period option.

SYNTHETIC data only; Linux offscreen Qt (this is not Windows acceptance).
"""
from __future__ import annotations

import json
import time as _time
from datetime import date, time

import pytest

from test_m70_selection_audit import _pump, window  # noqa: F401  (module fixture reused)


def _tab(win, name):
    for i in range(win.tab_widget.count()):
        widget = win.tab_widget.widget(i)
        if type(widget).__name__ == name:
            win.tab_widget.setCurrentWidget(widget)
            _pump(0.3)
            return widget
    raise LookupError(name)


def _export(win, monkeypatch, path, period=None):
    import tabs.w11_Export as w11
    from PySide6.QtCore import QDate
    tab = _tab(win, "ExportWidget")
    monkeypatch.setattr(w11.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(path), "")))
    tab.eowr_fmt.setCurrentText("HTML")
    tab.eowr_period.setChecked(period is not None)
    if period is not None:
        tab.eowr_from.setDate(QDate(period[0].year, period[0].month, period[0].day))
        tab.eowr_to.setDate(QDate(period[1].year, period[1].month, period[1].day))
    tab._export_eowr()
    end = _time.monotonic() + 30
    while tab.export_running() and _time.monotonic() < end:
        _pump(0.05)
    assert not tab.export_running() and path.exists(), tab.eowr_status.text()
    return path.read_text(encoding="utf-8")


@pytest.fixture
def seeded(window):  # noqa: F811
    win, db, ids = window
    from core.database import BitReport, EquipmentLog, MaterialRequest, TimeLog24H
    added = []
    with db.session_scope() as s:
        rows = [
            BitReport(well_id=ids["alpha"], report_id=ids["report_1"], report_date=date(2026, 1, 2),
                      report_name="SYN M467", bit_records_json=json.dumps([{"Bit No": "SYN-M467-BIT"}])),
            TimeLog24H(report_id=ids["report_2"], time_from=time(0, 0), time_to=time(6, 0), duration=6.0,
                       activity_description="SYN-M467 day-2 log"),
            TimeLog24H(report_id=ids["report_1"], time_from=time(0, 0), time_to=time(6, 0), duration=6.0,
                       activity_description="SYN-M467 day-1 log"),
            MaterialRequest(well_id=ids["alpha"], request_date=date(2026, 1, 3), requested_items="SYN-M467 item"),
            EquipmentLog(well_id=ids["twin_1"], equipment_name="SYN-M467-TWIN equipment"),
        ]
        s.add_all(rows)
        s.flush()
        added = [(type(r), r.id) for r in rows]
    yield win, db, ids
    with db.session_scope() as s:
        for model, pk in added:
            obj = s.get(model, pk)
            if obj is not None:
                s.delete(obj)


def test_w11_eowr_renders_source_sections_for_the_selected_well(seeded, monkeypatch, tmp_path):
    from core import report_sections as rs
    win, _db, ids = seeded
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _pump(0.4)
    text = _export(win, monkeypatch, tmp_path / "alpha.html")
    for title in ("12. Bit records", "14. 24-hour time logs", "16. Material requests", "17. Equipment logs"):
        assert f"<h1>{title}</h1>" in text
    assert "SYN-M467-BIT" in text and "SYN-M467 item" in text and "SYN-M467-TWIN" not in text
    assert text.index("SYN-M467 day-1 log") < text.index("SYN-M467 day-2 log")
    assert f"12. Bit records: {rs.INCLUDED}, 1 row(s)" in text           # manifest in the provenance block
    assert "17. Equipment logs: NOT_RECORDED" in text
    assert "not rendered by the EOWR template" not in text

    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    _pump(0.4)
    twin = _export(win, monkeypatch, tmp_path / "twin.html")
    assert "SYN-M467-TWIN equipment" in twin and "SYN-M467-BIT" not in twin


def test_w11_eowr_period_option_limits_dated_rows(seeded, monkeypatch, tmp_path):
    win, _db, ids = seeded
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _pump(0.4)
    text = _export(win, monkeypatch, tmp_path / "period.html", period=(date(2026, 1, 3), date(2026, 1, 3)))
    assert "Period 2026-01-03 to 2026-01-03" in text
    assert "SYN-M467 day-2 log" in text and "SYN-M467 day-1 log" not in text and "SYN-M467-BIT" not in text
    tab = _tab(win, "ExportWidget")
    tab.eowr_period.setChecked(False)
    assert not tab.eowr_from.isEnabled() and not tab.eowr_to.isEnabled()


def test_w11_eowr_refuses_an_inverted_period(window, monkeypatch, tmp_path):  # noqa: F811
    import tabs.w11_Export as w11
    from PySide6.QtCore import QDate
    win, _db, ids = window
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _pump(0.4)
    tab = _tab(win, "ExportWidget")
    warnings, dialogs = [], []
    monkeypatch.setattr(w11.QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2])))
    monkeypatch.setattr(w11.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: dialogs.append(1) or ("", "")))
    tab.eowr_period.setChecked(True)
    tab.eowr_from.setDate(QDate(2026, 1, 5))
    tab.eowr_to.setDate(QDate(2026, 1, 1))
    tab._export_eowr()
    tab.eowr_period.setChecked(False)
    assert warnings == ["The EOWR period starts after it ends."] and dialogs == []
