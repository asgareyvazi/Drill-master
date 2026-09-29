"""Loaded cement SQL NULLs stay unknown unless the operator edits the field."""
from __future__ import annotations

from datetime import date

import pytest

from test_scope_attribution import _base, _mgr, _section, _well


def test_untouched_null_restores_source_but_explicit_zero_remains_value():
    from core.mud_records import preserve_widget_values

    source = {"slurry_density": None, "slurry_yield": 1.18}
    displayed = {"slurry_density": 120.0, "slurry_yield": 1.18}
    submitted = {"slurry_density": 120.0, "slurry_yield": 1.18}
    assert preserve_widget_values(source, displayed, submitted) == {
        "slurry_density": None, "slurry_yield": 1.18,
    }
    edited = {**submitted, "slurry_density": 0.0}
    assert preserve_widget_values(source, displayed, edited, {"slurry_density"}) == {
        "slurry_density": 0.0, "slurry_yield": 1.18,
    }


def test_unchanged_cement_nulls_round_trip_and_explicit_zero_is_saved():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - depends on host Qt libraries
        pytest.skip(f"Qt runtime unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    db = _mgr()
    section_widget = None
    try:
        project_id = _base(db)
        well_id = _well(db, project_id, "Cement-null")
        section_id = _section(db, well_id, "Null-values")
        db.save_cement_report({
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date(2026, 9, 1),
            "slurry_density": None,
            "slurry_yield": None,
            "mix_water": None,
            "thickening_time": None,
            "compressive_strength": None,
            "fluid_loss": None,
            "cement_volume": None,
            "displacement_volume": None,
            "top_of_cement": None,
            "bottom_of_cement": None,
            "summary": None,
        })

        # Exercise the same real QWidget parent/container used by the
        # application; the tabs' constructors receive QWidget parents here.
        from tabs.w3c_section_data import SectionDataWidget

        section_widget = SectionDataWidget(db)
        section_widget.on_well_changed(well_id, {})
        section_widget.on_section_changed(section_id, {})
        tab = section_widget.cement_tab

        assert tab.slurry_density.value() == 120  # visual placeholder, not source data
        assert "Slurry density" in tab.cement_source_status.text()
        assert not tab.cement_source_status.isHidden()
        assert "Source database value is NULL" in tab.slurry_density.toolTip()
        assert tab.save_data()

        saved = db.get_cement_report(section_id=section_id)
        for key in (
            "slurry_density", "slurry_yield", "mix_water", "thickening_time",
            "compressive_strength", "fluid_loss", "cement_volume",
            "displacement_volume", "top_of_cement", "bottom_of_cement", "summary",
        ):
            assert saved[key] is None, key

        # A deliberate operator entry of numeric zero must remain a real value.
        tab.slurry_density.setValue(0)
        assert "Slurry density" not in tab.cement_source_status.text()
        assert tab.save_data()
        saved = db.get_cement_report(section_id=section_id)
        assert saved["slurry_density"] == 0
        assert saved["slurry_yield"] is None

        # Imported/stored inventory and daily movement are separate facts.
        # Editing movement inputs must not overwrite the stored inventory value.
        tab.add_material_row(
            material="Imported additive", received=10, consumed=4,
            backload=2, inventory=25, unit="kg",
        )
        assert tab.materials_table.columnCount() == 8
        assert tab.materials_table.cellWidget(0, 5).value() == 25
        assert tab.materials_table.cellWidget(0, 6).text() == "6"
        tab.materials_table.cellWidget(0, 2).setValue(11)
        assert tab.materials_table.cellWidget(0, 5).value() == 25
        assert tab.materials_table.cellWidget(0, 6).text() == "7"
        assert tab.save_data()
        saved_materials = db.get_cement_report(section_id=section_id)["materials_json"]
        import json
        material = json.loads(saved_materials)[0]
        assert material["inventory"] == 25
        assert material["net_movement"] == 7
        assert material["backload"] == 2

        db.save_casing_report({
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date(2026, 9, 1),
            "burst_pressure": None,
            "collapse_pressure": None,
            "tensile_strength": None,
            "makeup_torque": None,
            "drift_diameter": None,
            "internal_yield": None,
            "running_speed": None,
            "fillup_frequency": None,
            "centralizer_spacing": None,
            "scratcher_spacing": None,
            "summary": None,
        })

        casing = section_widget.casing_tab
        section_widget._load_section_data(section_id)
        assert "Burst pressure" in casing.casing_source_status.text()
        assert "Source database value is NULL" in casing.burst_pressure.toolTip()
        assert casing.save_data()
        saved_casing = db.get_casing_report(section_id=section_id)
        for key in (
            "burst_pressure", "collapse_pressure", "tensile_strength", "makeup_torque",
            "drift_diameter", "internal_yield", "running_speed", "fillup_frequency",
            "centralizer_spacing", "scratcher_spacing", "summary",
        ):
            assert saved_casing[key] is None, key

        casing.burst_pressure.setValue(1)
        casing.burst_pressure.setValue(0)
        assert "Burst pressure" not in casing.casing_source_status.text()
        assert casing.save_data()
        saved_casing = db.get_casing_report(section_id=section_id)
        assert saved_casing["burst_pressure"] == 0
        assert saved_casing["collapse_pressure"] is None
    finally:
        if section_widget is not None:
            section_widget.close()
            section_widget.deleteLater()
        db.close()
        app.processEvents()
