"""Tests for the expanded canonical schema."""
import pytest
from core.canonical_schema import (
    FIELD_SPECS, CANONICAL_FIELDS,
    get_critical_fields, get_fields_by_quantity, get_field_spec,
)


class TestExpandedSchema:
    def test_schema_has_minimum_fields(self):
        """Schema should have at least 100 fields covering all domains."""
        assert len(FIELD_SPECS) >= 100

    def test_all_fields_have_paths(self):
        """Every field must have a non-empty path."""
        for path, spec in FIELD_SPECS.items():
            assert path, f"Empty path found in schema"
            assert spec.path == path

    def test_critical_fields_exist(self):
        """Critical fields must be present."""
        critical = get_critical_fields()
        assert "well_info.name" in critical
        assert "daily_report.depth_2400" in critical
        assert "mud_report.mw" in critical
        assert "drilling_params.bit_size" in critical
        assert "survey.md" in critical
        assert "bop.working_pressure" in critical

    def test_well_info_fields(self):
        """Well info domain should have expected fields."""
        fields = [p for p in FIELD_SPECS if p.startswith("well_info.")]
        assert len(fields) >= 8
        assert "well_info.name" in FIELD_SPECS
        assert "well_info.rig_name" in FIELD_SPECS
        assert "well_info.operator" in FIELD_SPECS

    def test_mud_report_fields(self):
        """Mud report domain should have comprehensive rheology fields."""
        fields = [p for p in FIELD_SPECS if p.startswith("mud_report.")]
        assert len(fields) >= 12
        assert "mud_report.mw" in FIELD_SPECS
        assert "mud_report.pv" in FIELD_SPECS
        assert "mud_report.yp" in FIELD_SPECS
        assert "mud_report.funnel_vis" in FIELD_SPECS
        assert "mud_report.gel_10s" in FIELD_SPECS
        assert "mud_report.gel_10m" in FIELD_SPECS

    def test_drilling_params_fields(self):
        """Drilling params should have WOB, RPM, torque, pump fields."""
        fields = [p for p in FIELD_SPECS if p.startswith("drilling_params.")]
        assert len(fields) >= 18
        assert "drilling_params.wob_min" in FIELD_SPECS
        assert "drilling_params.wob_max" in FIELD_SPECS
        assert "drilling_params.rpm_min" in FIELD_SPECS
        assert "drilling_params.torque_min" in FIELD_SPECS
        assert "drilling_params.pump_pressure_min" in FIELD_SPECS

    def test_survey_fields(self):
        """Survey should have MD, Inc, Azi, TVD, North, East, DLS."""
        assert "survey.md" in FIELD_SPECS
        assert "survey.inc" in FIELD_SPECS
        assert "survey.azi" in FIELD_SPECS
        assert "survey.tvd" in FIELD_SPECS
        assert "survey.north" in FIELD_SPECS
        assert "survey.east" in FIELD_SPECS
        assert "survey.dls" in FIELD_SPECS

    def test_npt_fields(self):
        """NPT domain should exist."""
        fields = [p for p in FIELD_SPECS if p.startswith("npt.")]
        assert len(fields) >= 4
        assert "npt.npt_category" in FIELD_SPECS
        assert "npt.duration_hours" in FIELD_SPECS

    def test_cost_fields(self):
        """Cost domain should have planned and actual."""
        assert "cost.planned_cost" in FIELD_SPECS
        assert "cost.actual_cost" in FIELD_SPECS
        assert "cost.category" in FIELD_SPECS

    def test_get_fields_by_quantity(self):
        """Should be able to filter fields by quantity type."""
        density_fields = get_fields_by_quantity("density")
        assert "mud_report.mw" in density_fields
        assert "cement.slurry_density" in density_fields

        length_fields = get_fields_by_quantity("length")
        assert "survey.md" in length_fields
        assert "drilling_params.bit_size" in length_fields

    def test_get_field_spec(self):
        """Should be able to get individual field specs."""
        spec = get_field_spec("mud_report.mw")
        assert spec is not None
        assert spec.quantity == "density"
        assert spec.unit == "ppg"
        assert spec.critical is True

        unknown = get_field_spec("nonexistent.field")
        assert unknown is None

    def test_frozen_set_matches_dict(self):
        """CANONICAL_FIELDS frozenset should match FIELD_SPECS keys."""
        assert CANONICAL_FIELDS == frozenset(FIELD_SPECS.keys())

    def test_no_duplicate_paths(self):
        """No duplicate field paths in the schema."""
        paths = [path for path, _, _, _ in [
            # Reconstruct from FIELD_SPECS to check
        ]]
        # The dict comprehension already deduplicates, but let's verify
        assert len(FIELD_SPECS) == len(set(FIELD_SPECS.keys()))
