"""Annular velocity must use explicit pipe OD from the active daily report."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest


def test_annular_velocity_refuses_fallback_and_uses_active_report_pipe_od(monkeypatch):
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - requires host Qt libraries
        pytest.skip(f"Qt runtime unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    from core.database import DownholeEquipment
    from core.managers import DrillingManager
    from tabs.w3_drilling_report import DrillingParametersTab
    from test_scope_attribution import _base, _mgr, _well

    db = _mgr()
    tab = None
    try:
        project_id = _base(db)
        well_id = _well(db, project_id, "AV-scope")
        other_report = db.save_daily_report({
            "well_id": well_id,
            "report_number": 1,
            "report_date": date(2026, 9, 1),
        })
        current_report = db.save_daily_report({
            "well_id": well_id,
            "report_number": 2,
            "report_date": date(2026, 9, 2),
        })

        # Geometry from a different report is not valid input for this report.
        session = db.create_session()
        session.add(DownholeEquipment(
            well_id=well_id,
            report_id=other_report["id"],
            equipment_data_json=[{"type": "Drill Pipe", "od_inch": 8.0}],
        ))
        session.commit()
        session.close()

        tab = DrillingParametersTab(db_manager=db)
        tab.parent = SimpleNamespace(
            current_well=well_id,
            current_report_id=current_report["id"],
        )
        tab.pump_output_min.setValue(400)
        tab.pump_output_max.setValue(400)
        tab.bit_size.setValue(12.25)
        tab.calculate_annular_velocity()

        assert tab.annular_velocity.value() == tab.annular_velocity.minimum()
        assert tab.get_form_data()["annular_velocity"] is None
        assert "NOT ASSESSED" in tab.annular_velocity.toolTip()
        assert "current report" in tab.annular_velocity.toolTip().lower()

        # Add explicit pipe OD for the active report; the result uses that OD,
        # not the old first-row or 5-inch fallback.
        session = db.create_session()
        session.add(DownholeEquipment(
            well_id=well_id,
            report_id=current_report["id"],
            equipment_data_json=[{"type": "Drill Pipe", "od_inch": 6.5}],
        ))
        session.commit()
        session.close()

        tab.calculate_annular_velocity()
        expected = 24.51 * 400 / (12.25**2 - 6.5**2)
        assert tab.annular_velocity.value() == pytest.approx(round(expected, 1))
        assert "SCREENING" in tab.annular_velocity.toolTip()
        assert "6.5 in" in tab.annular_velocity.toolTip()
        assert tab.get_form_data()["annular_velocity"] == pytest.approx(round(expected, 1))

        # A calculation wrapper failure contains a compatibility zero, but the
        # UI must not persist or show that zero as a valid engineering result.
        monkeypatch.setattr(
            DrillingManager,
            "calculate_annular_velocity",
            staticmethod(lambda *_args: {"ft_min": 0, "m_min": 0, "status": "invalid geometry"}),
        )
        tab.calculate_annular_velocity()
        assert tab.annular_velocity.value() == tab.annular_velocity.minimum()
        assert tab.get_form_data()["annular_velocity"] is None
        assert "NOT ASSESSED" in tab.annular_velocity.toolTip()
    finally:
        if tab is not None:
            tab.close()
            tab.deleteLater()
        db.close()
        app.processEvents()
