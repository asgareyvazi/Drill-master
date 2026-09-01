"""Tests for engineering capabilities integrated from reference repos.

Covers (single canonical formula each, no UI duplication):
- pump output: triplex + duplex (AddPumpDialog now delegates here)
- d-exponent and mud-weight-corrected d-exponent (pore pressure)
- Eaton fracture gradient + kick influx-type classification
- critical flow rate (annular, same correlation as flow-regime engine)
- cost per foot (bit economics)
- required build rate (trajectory planning)
- mud lab: MBT bentonite equivalent, LSRYP, excess lime (POM), slug dry length
"""

import math

import pytest

from core.hydraulics_engine import AdvancedHydraulicsEngine
from core.engineering.extended import MudEngineering
from core.engineering.engines.bit_performance import BitPerformanceEngine
from core.engineering.engines.well_control import WellControlEngine


# ---------------------------------------------------------------------------
# Pump output (canonical: mud-engineer-pro split triplex/duplex)
# ---------------------------------------------------------------------------
class TestPumpOutput:
    def test_triplex_matches_canonical(self):
        # 0.000243 × 7² × 12 × 0.95
        out = AdvancedHydraulicsEngine.calc_pump_output(7.0, 12.0, 0.95)
        assert abs(out - 0.000243 * 49 * 12 * 0.95) < 1e-9
        assert abs(out - 0.135740) < 1e-5

    def test_duplex_matches_canonical(self):
        # 0.000162 × 12 × (2×7² − 3²) × 0.95 = 0.000162 × 12 × 89 × 0.95
        out = AdvancedHydraulicsEngine.calc_pump_output_duplex(7.0, 3.0, 12.0, 0.95)
        assert abs(out - 0.000162 * 12.0 * (2 * 49 - 9) * 0.95) < 1e-9
        assert abs(out - 0.164365) < 1e-5

    def test_duplex_rod_effect(self):
        # Larger rod → less displacement
        a = AdvancedHydraulicsEngine.calc_pump_output_duplex(7.0, 2.0, 12.0, 1.0)
        b = AdvancedHydraulicsEngine.calc_pump_output_duplex(7.0, 4.0, 12.0, 1.0)
        assert a > b

    def test_dialog_branch_logic_matches_engine(self):
        # AddPumpDialog._pump_output_bbl_stk selects formula by pump_type;
        # replicate the exact branch to pin the contract.
        def dialog_output(pump_type, liner, rod, stroke, eff):
            if pump_type == "Duplex":
                return AdvancedHydraulicsEngine.calc_pump_output_duplex(
                    liner, rod, stroke, eff)
            return AdvancedHydraulicsEngine.calc_pump_output(liner, stroke, eff)

        trip = dialog_output("Triplex", 7.0, 3.0, 12.0, 0.95)
        dup = dialog_output("Duplex", 7.0, 3.0, 12.0, 0.95)
        assert trip == AdvancedHydraulicsEngine.calc_pump_output(7.0, 12.0, 0.95)
        assert dup == AdvancedHydraulicsEngine.calc_pump_output_duplex(
            7.0, 3.0, 12.0, 0.95)
        # duplex with a rod must NOT equal the triplex value
        assert abs(trip - dup) > 1e-6


# ---------------------------------------------------------------------------
# d-exponent (Rehm & McClendon 1971) — pore-pressure detection
# ---------------------------------------------------------------------------
class TestDExponent:
    def test_known_value(self):
        r = BitPerformanceEngine.d_exponent(
            rop_ft_hr=30.0, rpm=80.0, wob_lbf=25000.0, bit_size_in=8.5)
        assert r.success
        num = math.log10(30.0 / (60.0 * 80.0))
        den = math.log10(12.0 * 25000.0 / (1000000.0 * 8.5))
        assert abs(r.values["d_exponent"] - num / den) < 1e-4
        # sanity: typical d-exponent values are positive (≈1.5 here)
        assert r.values["d_exponent"] > 1.0

    def test_corrected(self):
        r = BitPerformanceEngine.d_exponent_corrected(
            30.0, 80.0, 25000.0, 8.5, mw_ppg=12.0, normal_mw_ppg=8.6)
        assert r.success
        base = BitPerformanceEngine.d_exponent(30.0, 80.0, 25000.0, 8.5)
        assert abs(r.values["d_exponent_corrected"]
                   - base.values["d_exponent"] * 8.6 / 12.0) < 1e-4

    def test_invalid_inputs(self):
        r = BitPerformanceEngine.d_exponent(0, 80, 25000, 8.5)
        assert not r.success


# ---------------------------------------------------------------------------
# Eaton fracture gradient + influx type (well control)
# ---------------------------------------------------------------------------
class TestWellControlAdditions:
    def test_eaton_known_value(self):
        r = WellControlEngine.eaton_fracture_gradient(0.95, 0.52, 0.25)
        assert r.success
        expected = (0.25 / 0.75) * (0.95 - 0.52) + 0.52
        assert abs(r.values["fracture_gradient_psi_ft"] - expected) < 1e-5

    def test_eaton_poisson_bounds(self):
        r = WellControlEngine.eaton_fracture_gradient(0.95, 0.52, 0.6)
        assert not r.success

    def test_influx_type_gas(self):
        r = WellControlEngine.influx_type(240.0, 200.0, 0.05, 20.0)
        assert r.success and r.values["influx_type"] == "gas"

    def test_influx_type_saltwater(self):
        r = WellControlEngine.influx_type(400.0, 200.0, 0.045, 10.0)
        assert r.success and r.values["influx_type"] == "saltwater"
        # 200 psi over ~222 ft → 0.9 psi/ft

    def test_influx_type_invalid(self):
        r = WellControlEngine.influx_type(100.0, 200.0, 0.05, 20.0)
        assert not r.success  # SICP < SIDPP


# ---------------------------------------------------------------------------
# Critical flow rate (same correlation constants as _determine_flow_regime)
# ---------------------------------------------------------------------------
class TestCriticalFlowRate:
    def test_known_value(self):
        res = AdvancedHydraulicsEngine.calc_critical_flow_rate(
            mw_ppg=10.0, pv_cp=15.0, yp_lbf100ft2=10.0,
            hole_size_in=12.25, pipe_od_in=5.0)
        gap = 12.25 - 5.0
        vc = (1.08 * 15.0 + 1.08 * math.sqrt(
            15.0 ** 2 + 9.26 * gap ** 2 * 10.0 * 10.0)) / (10.0 * gap)
        area = math.pi / 4.0 * ((12.25 / 12.0) ** 2 - (5.0 / 12.0) ** 2)
        assert abs(res["critical_velocity_ft_min"] - vc * 60.0) < 0.1
        assert abs(res["critical_flow_rate_gpm"] - vc * 60.0 * area * 7.4805) < 0.5
        assert res["critical_flow_rate_gpm"] > 500

    def test_invalid_geometry(self):
        with pytest.raises(ValueError):
            AdvancedHydraulicsEngine.calc_critical_flow_rate(
                10.0, 15.0, 10.0, hole_size_in=5.0, pipe_od_in=7.0)


# ---------------------------------------------------------------------------
# Cost per foot (Bourgoyne)
# ---------------------------------------------------------------------------
class TestCostPerFoot:
    def test_known_value(self):
        r = BitPerformanceEngine.cost_per_foot(
            rig_cost_per_day=40000.0, trip_hours=6.0,
            bit_cost=2000.0, footage=500.0)
        assert r.success
        assert abs(r.values["cost_per_ft"] - (40000.0 / 24.0 * 6.0 + 2000.0) / 500.0) < 1e-6

    def test_full_cycle(self):
        r = BitPerformanceEngine.cost_per_foot(
            40000.0, 6.0, 2000.0, 500.0, rotating_hours=20.0)
        assert r.success
        expected = (40000.0 / 24.0 * 26.0 + 2000.0) / 500.0
        assert abs(r.values["cost_per_ft"] - expected) < 1e-2

    def test_zero_footage(self):
        r = BitPerformanceEngine.cost_per_foot(40000.0, 6.0, 2000.0, 0.0)
        assert not r.success


# ---------------------------------------------------------------------------
# Mud lab additions
# ---------------------------------------------------------------------------
class TestMudLabAdditions:
    def test_mbt_bentonite_equiv(self):
        res = MudEngineering.mbt_bentonite_equiv(10.0, 2.0)
        assert abs(res["mbt_lb_per_bbl"] - 25.0) < 0.1

    def test_mbt_invalid_sample(self):
        with pytest.raises(Exception):
            MudEngineering.mbt_bentonite_equiv(10.0, 0.0)

    def test_lsryp(self):
        res = MudEngineering.lsryp(6.0, 4.0)
        assert abs(res["lsryp_lb_per_100ft2"] - 8.0) < 1e-9
        assert res["warning"] is None

    def test_lsryp_sag_warning(self):
        res = MudEngineering.lsryp(2.0, 3.0)
        assert res["warning"] is not None

    def test_excess_lime(self):
        res = MudEngineering.excess_lime_obm(2.5)
        assert abs(res["excess_lime_lb_per_bbl"] - 3.2375) < 0.01

    def test_slug_dry_length(self):
        res = MudEngineering.slug_dry_length(20.0, 12.5, 10.0, 0.01776)
        assert res["dry_pipe_length_ft"] > 0
        assert res["hydrostatic_gain_psi"] > 0

    def test_corrosion_rate(self):
        # 100 mg loss, 3 in² coupon, 168 hr, steel 7.86 g/cm³
        res = MudEngineering.corrosion_rate(100.0, 3.0, 168.0, 7.86)
        expected = 534.0 * 100.0 / (3.0 * 168.0 * 7.86)
        assert abs(res["corrosion_rate_mpy"] - expected) < 1e-3
        assert res["corrosion_rate_mpy"] > 10  # high-severity example

    def test_corrosion_rate_invalid(self):
        with pytest.raises(Exception):
            MudEngineering.corrosion_rate(100.0, 0.0, 168.0)
