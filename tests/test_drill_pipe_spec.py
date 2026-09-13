"""Canonical DrillPipeSpec — master-data foundation and engine handoff.

Proves the first canonical Engineering Master Data vertical slice:

* vendor row -> canonical spec normalization (units explicit, unknown preserved,
  no fabrication, unmapped columns retained for audit);
* stable domain identity (never a row index);
* duplicate/conflict classification (never silent merge);
* provenance preservation;
* the canonical calculation handoff: DrillPipeSpec -> component -> the existing
  Torque & Drag / weight-card engine -> EngineeringResult, checked against the
  repository's own buoyed-weight ground truth.
"""
from __future__ import annotations

import math

from core.engineering.drill_pipe import (
    AMBIGUOUS,
    CONFLICTING,
    DUPLICATE,
    IDENTICAL,
    DrillPipeSpec,
    Provenance,
    classify_duplicate,
)
from core.engineering.engines.torque_drag import TorqueDragEngine


# ----------------------------------------------------------------------
# 1. Vendor row -> canonical spec
# ----------------------------------------------------------------------
class TestVendorNormalization:
    def test_basic_mapping_inches_and_ppf(self):
        spec = DrillPipeSpec.from_vendor_row(
            {
                "Manufacturer": "NOV",
                "Product": "5 DP",
                "OD (in)": 5.0,
                "ID (in)": 4.276,
                "Weight (ppf)": 19.5,
                "Grade": "S-135",
                "Connection": "NC50",
            }
        )
        assert spec.manufacturer == "NOV"
        assert spec.model == "5 DP"
        assert spec.nominal_od_in == 5.0
        assert spec.nominal_id_in == 4.276
        assert spec.nominal_weight_ppf == 19.5
        assert spec.grade == "S-135"
        assert spec.connection == "NC50"

    def test_mm_diameter_converted_to_inches(self):
        # 127 mm == 5 in via the existing UnitManager.
        spec = DrillPipeSpec.from_vendor_row({"od": 127.0, "weight": 19.5}, od_unit="mm")
        assert math.isclose(spec.nominal_od_in, 5.0, rel_tol=1e-9)

    def test_ppf_is_not_unit_converted(self):
        # ppf is a linear weight; it must stay numeric, matching the T&D engine.
        spec = DrillPipeSpec.from_vendor_row({"od": 5.0, "ppf": 19.5})
        assert spec.nominal_weight_ppf == 19.5

    def test_missing_values_stay_unknown_never_zero(self):
        spec = DrillPipeSpec.from_vendor_row({"OD (in)": 5.0, "Weight (ppf)": 19.5})
        assert spec.nominal_id_in is None
        assert spec.grade is None
        assert spec.connection is None
        assert spec.tensile_rating_klbf is None

    def test_blank_and_nan_cells_are_absent(self):
        spec = DrillPipeSpec.from_vendor_row(
            {"OD (in)": 5.0, "Weight (ppf)": 19.5, "Grade": "  ", "ID (in)": float("nan"),
             "Connection": "n/a"}
        )
        assert spec.grade is None
        assert spec.nominal_id_in is None
        assert spec.connection is None

    def test_unmapped_columns_preserved_in_extra(self):
        spec = DrillPipeSpec.from_vendor_row(
            {"OD (in)": 5.0, "Weight (ppf)": 19.5, "Vendor Note": "premium", "Lot #": 42}
        )
        assert spec.extra.get("Vendor Note") == "premium"
        assert spec.extra.get("Lot #") == 42

    def test_nothing_inferred_from_another_field(self):
        # A row with only OD must not gain a weight, id, or grade.
        spec = DrillPipeSpec.from_vendor_row({"OD (in)": 5.0})
        assert spec.nominal_weight_ppf is None
        assert spec.nominal_id_in is None
        assert not spec.has_identity  # OD alone is not identifiable


# ----------------------------------------------------------------------
# 2. Identity
# ----------------------------------------------------------------------
class TestIdentity:
    def test_identity_is_domain_key_not_row_index(self):
        a = DrillPipeSpec.from_vendor_row(
            {"Manufacturer": "NOV", "Product": "5DP", "OD (in)": 5.0,
             "Weight (ppf)": 19.5, "Grade": "S-135", "Connection": "NC50"}
        )
        b = DrillPipeSpec.from_vendor_row(
            {"manufacturer": "nov", "model": "5dp", "od": 5.0,
             "weight": 19.5, "grade": "s-135", "connection": "nc50"}
        )
        # Same domain identity despite case/spacing/header differences.
        assert a.identity_key == b.identity_key

    def test_has_identity_requires_od_and_weight(self):
        assert DrillPipeSpec(nominal_od_in=5.0, nominal_weight_ppf=19.5).has_identity
        assert not DrillPipeSpec(nominal_od_in=5.0).has_identity
        assert not DrillPipeSpec(nominal_weight_ppf=19.5).has_identity

    def test_different_weight_is_different_identity(self):
        a = DrillPipeSpec(nominal_od_in=5.0, nominal_weight_ppf=19.5)
        b = DrillPipeSpec(nominal_od_in=5.0, nominal_weight_ppf=25.6)
        assert a.identity_key != b.identity_key


# ----------------------------------------------------------------------
# 3. Duplicate / conflict classification (never silent merge)
# ----------------------------------------------------------------------
class TestDuplicateClassification:
    def _spec(self, **kw):
        base = dict(nominal_od_in=5.0, nominal_weight_ppf=19.5, grade="S-135",
                    connection="NC50")
        base.update(kw)
        return DrillPipeSpec(**base)

    def test_identical(self):
        a = self._spec(nominal_id_in=4.276, tensile_rating_klbf=550.0)
        b = self._spec(nominal_id_in=4.276, tensile_rating_klbf=550.0)
        assert classify_duplicate(a, b) == IDENTICAL

    def test_duplicate_when_one_side_missing(self):
        a = self._spec(nominal_id_in=4.276)
        b = self._spec()  # same identity, no descriptive detail
        assert classify_duplicate(a, b) == DUPLICATE

    def test_conflicting_engineering_values(self):
        a = self._spec(nominal_id_in=4.276)
        b = self._spec(nominal_id_in=3.640)
        assert classify_duplicate(a, b) == CONFLICTING

    def test_ambiguous_without_identity(self):
        a = self._spec()
        b = DrillPipeSpec(nominal_od_in=5.0)  # no weight -> no identity
        assert classify_duplicate(a, b) == AMBIGUOUS

    def test_different_identity_is_ambiguous_not_merged(self):
        a = self._spec()
        b = self._spec(nominal_weight_ppf=25.6)
        assert classify_duplicate(a, b) == AMBIGUOUS


# ----------------------------------------------------------------------
# 4. Provenance
# ----------------------------------------------------------------------
class TestProvenance:
    def test_provenance_preserved(self):
        prov = Provenance(source="vendor Excel", source_revision="2024-Q3",
                          status="unverified", notes="sheet Aa")
        spec = DrillPipeSpec.from_vendor_row(
            {"OD (in)": 5.0, "Weight (ppf)": 19.5}, provenance=prov
        )
        assert spec.provenance.source == "vendor Excel"
        assert spec.provenance.source_revision == "2024-Q3"
        assert spec.provenance.status == "unverified"
        assert spec.as_dict()["provenance"]["notes"] == "sheet Aa"

    def test_default_provenance_is_unverified(self):
        spec = DrillPipeSpec.from_vendor_row({"OD (in)": 5.0, "Weight (ppf)": 19.5})
        assert spec.provenance.status == "unverified"
        assert spec.provenance.source == ""


# ----------------------------------------------------------------------
# 5. Canonical calculation handoff — the whole point of the slice
# ----------------------------------------------------------------------
class TestEngineHandoff:
    def test_to_component_matches_engine_contract(self):
        spec = DrillPipeSpec(nominal_od_in=5.0, nominal_id_in=4.276,
                             nominal_weight_ppf=19.5)
        comp = spec.to_component(length_m=3048.0)
        assert comp == {"length": 3048.0, "weight": 19.5, "od": 5.0, "id": 4.276}

    def test_missing_spec_fields_are_omitted_not_defaulted(self):
        spec = DrillPipeSpec(nominal_od_in=5.0, nominal_weight_ppf=19.5)  # no id
        comp = spec.to_component(length_m=100.0)
        assert "id" not in comp  # engine keeps authority over missing inputs
        assert comp["weight"] == 19.5

    def test_spec_drives_buoyed_weight_ground_truth(self):
        """DrillPipeSpec -> component -> T&D engine reproduces the repo's own
        vertical buoyed-weight ground truth (165.23 klbf).

        Reference (tests/test_engineering_ground_truth.py::test_vertical_buoyed_weight):
        10000 ft of 19.5 ppf, MW 10 ppg, vertical -> BF ~= 0.8473 -> ~165.23 klbf.
        """
        spec = DrillPipeSpec(nominal_od_in=5.0, nominal_weight_ppf=19.5)
        comp = spec.to_component(length_m=3048.0)  # 3048 m == 10000 ft
        result = TorqueDragEngine.calculate(
            survey=[{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}],
            bha=[comp],
            mud_density_ppg=10.0,
            friction_factor=0.3,
        )
        assert result.success, result.error
        bf = 1.0 - 10.0 / 65.5
        expected = 10000.0 * 19.5 * bf / 1000.0
        assert math.isclose(result.values["total_buoyed_weight"], expected, abs_tol=0.1)
        assert math.isclose(result.values["total_buoyed_weight"], 165.23, abs_tol=0.02)

    def test_missing_weight_spec_yields_engine_missing_input(self):
        """A spec without a weight must let the engine report MISSING_INPUT,
        never silently compute with a fabricated 0 weight."""
        spec = DrillPipeSpec(nominal_od_in=5.0)  # no weight
        comp = spec.to_component(length_m=3048.0)
        assert "weight" not in comp
        result = TorqueDragEngine.calculate(
            survey=[{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}],
            bha=[comp],
            mud_density_ppg=10.0,
            friction_factor=0.3,
        )
        assert not result.success
        assert result.validation_status in {"missing_input", "error"}
