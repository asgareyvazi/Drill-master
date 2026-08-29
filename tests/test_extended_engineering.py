"""Tests for extended drilling engineering calculations."""

import pytest
import math
from core.engineering.extended import (
    MudEngineering, HydraulicsExtended, WellControlExtended,
    CasingDesign, DirectionalExtended, CementingEngine, ROPModels,
    ExtendedEngineeringError,
)


class TestMudEngineering:
    def test_mud_weighting(self):
        result = MudEngineering.mud_weighting(
            start_volume_m3=100, start_density_sg=1.2,
            target_density_sg=1.5, weighting_density_sg=4.2
        )
        assert result["weight_kg"] > 0
        assert result["final_volume_m3"] > 100
        assert "formula" in result

    def test_mud_weighting_invalid(self):
        with pytest.raises(ExtendedEngineeringError):
            MudEngineering.mud_weighting(100, 1.5, 1.2, 4.2)  # target < start

    def test_mix_two_muds(self):
        result = MudEngineering.mix_two_muds(50, 1.2, 50, 1.5)
        assert abs(result["mixed_density_sg"] - 1.35) < 0.01

    def test_oil_water_ratio(self):
        result = MudEngineering.oil_water_ratio(30, 70)
        assert result["oil_percent"] == 30.0
        assert result["water_percent"] == 70.0
        assert result["owr"] == "30:70"

    def test_solids_content(self):
        result = MudEngineering.solids_content(10, 70, 12.0)
        assert result["total_solids_pct"] == 20.0

    def test_funnel_viscosity(self):
        result = MudEngineering.funnel_viscosity_to_pv_yp(40, 10.0)
        assert result["estimated_pv_cp"] > 0


class TestHydraulicsExtended:
    def test_annular_pressure_loss(self):
        result = HydraulicsExtended.pressure_loss_annular(
            mw_ppg=10.0, pv_cp=15, yp_lbf100ft2=10,
            flow_rate_gpm=500, hole_id_in=12.25,
            pipe_od_in=5.0, length_ft=5000
        )
        assert result["pressure_loss_psi"] > 0
        assert result["annular_velocity_ftmin"] > 0

    def test_pipe_pressure_loss(self):
        result = HydraulicsExtended.pressure_loss_pipe(
            mw_ppg=10.0, pv_cp=15, yp_lbf100ft2=10,
            flow_rate_gpm=500, pipe_id_in=4.276, length_ft=5000
        )
        assert result["pressure_loss_psi"] > 0

    def test_bit_nozzle_pressure_drop(self):
        result = HydraulicsExtended.bit_nozzle_pressure_drop(
            flow_rate_gpm=500, mw_ppg=10.0, tfa_in2=1.0
        )
        assert result["nozzle_pressure_drop_psi"] > 0

    def test_jet_velocity(self):
        result = HydraulicsExtended.jet_velocity(500, 1.0)
        assert result["jet_velocity_fps"] > 0

    def test_impact_force(self):
        result = HydraulicsExtended.impact_force(500, 10.0, 2000)
        assert result["impact_force_lbf"] > 0


class TestWellControlExtended:
    def test_kick_tolerance(self):
        result = WellControlExtended.kick_tolerance(
            mw_ppg=10.0, tvd_ft=10000, shoe_tvd_ft=5000,
            lot_pressure_psi=4000
        )
        assert result["kick_tolerance_ppg"] > 0
        assert result["fracture_pressure_ppg"] > 10.0

    def test_wait_weight(self):
        result = WellControlExtended.wait_weight_method(
            original_mw_ppg=10.0, sidpp_psi=500,
            tvd_ft=10000, circ_pressure_psi=800
        )
        assert result["kill_mud_weight_ppg"] > 10.0
        assert result["initial_circulating_pressure_psi"] == 1300
        assert result["final_circulating_pressure_psi"] > 800

    def test_formation_pressure(self):
        result = WellControlExtended.formation_pressure(
            mw_ppg=10.0, sidpp_psi=500, tvd_ft=10000
        )
        assert result["formation_pressure_psi"] > 5200  # 0.052*10*10000


class TestCasingDesign:
    def test_hydrostatic_pressure(self):
        result = CasingDesign.hydrostatic_pressure(10.0, 10000)
        assert abs(result["hydrostatic_pressure_psi"] - 5200) < 1

    def test_burst_pressure(self):
        result = CasingDesign.burst_pressure(5000, safety_factor=1.1)
        assert result["required_burst_rating_psi"] == 5500

    def test_collapse_pressure(self):
        result = CasingDesign.collapse_pressure(3000, safety_factor=1.125)
        assert result["required_collapse_rating_psi"] == 3375


class TestDirectionalExtended:
    def test_deviation(self):
        result = DirectionalExtended.deviation_from_vertical(100, 100)
        assert abs(result["deviation_m"] - 141.42) < 0.1

    def test_slide_rotor(self):
        result = DirectionalExtended.slide_rotor_ratio(30, 70)
        assert abs(result["slide_percent"] - 30.0) < 0.1

    def test_tool_face_offset(self):
        result = DirectionalExtended.tool_face_offset(100, 200, 500)
        assert result["offset_degrees"] > 0

    def test_inclination_from_accelerometers(self):
        # Vertical: Gx=0, Gy=0, Gz=1
        result = DirectionalExtended.inclination_from_accelerometers(0, 0, 1)
        assert abs(result["inclination_deg"]) < 0.1

    def test_azimuth_from_magnetometers(self):
        result = DirectionalExtended.azimuth_from_magnetometers(0, 0, 1, 1, 0, 0)
        assert 0 <= result["azimuth_deg"] <= 360


class TestCementingEngine:
    def test_annular_volume(self):
        result = CementingEngine.cement_volume_annular(
            outer_diameter_in=12.25, inner_diameter_in=9.625, length_ft=1000
        )
        assert result["volume_bbl"] > 0

    def test_pipe_volume(self):
        result = CementingEngine.cement_volume_pipe(
            inner_diameter_in=8.5, length_ft=1000
        )
        assert result["volume_bbl"] > 0

    def test_slurry_density(self):
        result = CementingEngine.slurry_density(
            cement_weight_kg=1000, water_volume_l=500
        )
        assert result["slurry_density_sg"] > 1.0
        assert result["slurry_density_ppg"] > 8.0


class TestROPModels:
    def test_bourgoyne_young(self):
        result = ROPModels.bourgoyne_young_rop(
            depth_ft=5000, wob_klbf=20, rpm=120, mw_ppg=10.0
        )
        assert result["predicted_rop_ft_hr"] > 0
        assert result["predicted_rop_m_hr"] > 0

    def test_bourgoyne_young_invalid(self):
        with pytest.raises(ExtendedEngineeringError):
            ROPModels.bourgoyne_young_rop(0, 20, 120, 10.0)
