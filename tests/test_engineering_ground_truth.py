"""Ground-truth engineering tests (numbers, not 'result > 0')."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.core import TrajectoryEngine, TrajectoryPoint, HydraulicsEngine, BitEngine
from core.engineering.engines.well_control import WellControlEngine
from core.engineering.engines.casing import CasingEngine
from core.engineering.engines.mse import MSEEngine
from core.engineering.engines.mud_volume import MudVolumeEngine
from core.engineering.engines.torque_drag import TorqueDragEngine
from core.engineering.engines.cement import CementEngine
from core.engineering.engines.bit_performance import BitPerformanceEngine
from core.company_mapping import CompanyMappingService
from core.ai_tools import AIToolRegistry


class KickToleranceGroundTruth(unittest.TestCase):
    """drillingformulas / IWCF worked example."""

    def test_iwcf_gas_kick_tolerance_bbl(self):
        r = WellControlEngine.kick_tolerance(
            mw_ppg=14.5,
            shoe_tvd_ft=6000,
            current_tvd_ft=10000,
            frac_mw_ppg=16.0,
            influx_gradient_psi_ft=0.1,
            annular_capacity_bbl_ft=0.0459,
            bha_annular_capacity_bbl_ft=0.0226,
            formation_emw_ppg=15.0,
        )
        self.assertTrue(r.success, r.error)
        self.assertAlmostEqual(r.values["maasp_psi"], 468.0, places=1)
        self.assertAlmostEqual(r.values["kick_intensity_ppg"], 0.5, places=4)
        self.assertAlmostEqual(r.values["remaining_pressure_psi"], 208.0, places=1)
        self.assertAlmostEqual(r.values["max_kick_height_ft"], 318.0, delta=1.0)
        self.assertAlmostEqual(r.values["volume_at_bha_bbl"], 7.2, delta=0.05)
        self.assertAlmostEqual(r.values["volume_at_shoe_bbl"], 14.6, delta=0.05)
        self.assertAlmostEqual(r.values["volume_at_bottom_bbl"], 9.34, delta=0.05)
        self.assertAlmostEqual(r.values["kick_tolerance_bbl"], 7.2, delta=0.05)

    def test_kick_tolerance_requires_influx_gradient(self):
        r = WellControlEngine.kick_tolerance(
            mw_ppg=14.5,
            shoe_tvd_ft=6000,
            current_tvd_ft=10000,
            frac_mw_ppg=16.0,
        )
        self.assertFalse(r.success)
        self.assertIn("MISSING_INPUT", r.error)
        self.assertIn("influx", r.error.lower())


class TripMarginGroundTruth(unittest.TestCase):
    def test_trip_margin_ppg_and_psi(self):
        r = WellControlEngine.trip_margin(mw_ppg=12.0, formation_emw_ppg=11.5, tvd_ft=10000)
        self.assertTrue(r.success, r.error)
        self.assertAlmostEqual(r.values["trip_margin_ppg"], 0.5, places=4)
        self.assertAlmostEqual(r.values["trip_margin_psi"], 260.0, places=1)


class TrajectoryGroundTruth(unittest.TestCase):
    def test_first_station_md_zero(self):
        pts = TrajectoryEngine.calculate([{"md": 0, "inc": 0, "azi": 0}])
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0].tvd, 0.0, places=6)
        self.assertAlmostEqual(pts[0].north, 0.0, places=6)
        self.assertAlmostEqual(pts[0].east, 0.0, places=6)

    def test_first_station_tvd_from_inc(self):
        pts = TrajectoryEngine.calculate([{"md": 100, "inc": 0, "azi": 45}])
        self.assertAlmostEqual(pts[0].tvd, 100.0, places=6)
        self.assertAlmostEqual(pts[0].north, 0.0, places=6)
        self.assertAlmostEqual(pts[0].east, 0.0, places=6)

    def test_tie_on_overrides_origin(self):
        pts = TrajectoryEngine.calculate(
            [{"md": 1500, "inc": 10, "azi": 30}],
            tie_on={"tvd": 1400, "north": 50, "east": -20},
        )
        self.assertAlmostEqual(pts[0].tvd, 1400.0, places=4)
        self.assertAlmostEqual(pts[0].north, 50.0, places=4)
        self.assertAlmostEqual(pts[0].east, -20.0, places=4)

    def test_vs_from_north_east(self):
        pts = TrajectoryEngine.calculate(
            [{"md": 0, "inc": 90, "azi": 0}, {"md": 100, "inc": 90, "azi": 0}],
            vs_azimuth=0.0,
        )
        self.assertAlmostEqual(pts[-1].tvd, 0.0, delta=0.05)
        self.assertAlmostEqual(pts[-1].north, 100.0, delta=0.05)
        self.assertAlmostEqual(pts[-1].vs, pts[-1].north, places=4)
        pts_e = TrajectoryEngine.calculate(
            [{"md": 0, "inc": 90, "azi": 0}, {"md": 100, "inc": 90, "azi": 0}],
            vs_azimuth=90.0,
        )
        self.assertAlmostEqual(pts_e[-1].vs, pts_e[-1].east, places=4)

    def test_project_ahead_recomputes_vs(self):
        last = TrajectoryPoint(md=0, inc=90, azi=0, tvd=0, north=0, east=0, vs=999.0, hd=0)
        nxt = TrajectoryEngine.project_ahead(last, md_target=100, inc=90, azi=0, vs_azimuth=0)
        self.assertAlmostEqual(nxt.north, 100.0, delta=0.2)
        self.assertAlmostEqual(nxt.vs, nxt.north, places=3)
        self.assertNotAlmostEqual(nxt.vs, 999.0, places=0)


class CasingGroundTruth(unittest.TestCase):
    def test_barlow_burst_9_625_n80(self):
        r = CasingEngine.burst(9.625, 0.472, 80000)
        self.assertTrue(r.success, r.error)
        expected = 0.875 * 2.0 * 80000 * 0.472 / 9.625
        self.assertAlmostEqual(r.value, expected, places=0)
        self.assertAlmostEqual(r.value, 6866, delta=3)
        self.assertEqual(r.scope, "PARTIAL")

    def test_collapse_four_regime_returns_regime(self):
        r = CasingEngine.collapse(9.625, 0.472, 80000)
        self.assertTrue(r.success, r.error)
        self.assertIn(r.values["regime"], ("yield", "plastic", "transition", "elastic"))
        self.assertGreater(r.value, 2000)
        self.assertLess(r.value, 15000)

    def test_fyax_tension_z_half(self):
        yp, z = 80000.0, 0.5
        expected = (math.sqrt(1.0 - 0.75 * z * z) - 0.5 * z) * yp
        self.assertAlmostEqual(CasingEngine.fyax(yp, z * yp), expected, places=1)
        self.assertAlmostEqual(expected / yp, 0.6513878, places=5)

    def test_collapse_combined_pi_correction(self):
        pc = CasingEngine.collapse(9.625, 0.472, 80000)
        self.assertTrue(pc.success, pc.error)
        pi = 1000.0
        r = CasingEngine.collapse_combined(9.625, 0.472, 80000, axial_tension_lbf=0, internal_pressure_psi=pi)
        self.assertTrue(r.success, r.error)
        expected = pc.value + pi * (1.0 - 2.0 * 0.472 / 9.625)
        self.assertAlmostEqual(r.value, expected, places=0)

    def test_vme_inner_wall_internal_only(self):
        od, id_, yp, pi = 9.625, 8.681, 80000.0, 3000.0
        r = CasingEngine.triaxial_vme(od, id_, yp, pi, 0.0, 0.0, include_capped_end=True)
        self.assertTrue(r.success, r.error)
        ro, ri = od / 2.0, id_ / 2.0
        denom = ro**2 - ri**2
        sigma_r = -pi
        sigma_h = (pi * (ri**2 + ro**2)) / denom
        area = math.pi * denom
        capped = (pi * ri**2) / area
        vme = math.sqrt(0.5 * ((sigma_h - capped) ** 2 + (capped - sigma_r) ** 2 + (sigma_r - sigma_h) ** 2))
        self.assertAlmostEqual(r.value, vme, places=0)

    def test_connection_governs_when_supplied(self):
        r = CasingEngine.evaluate(
            od_in=9.625, wall_in=0.472, id_in=8.681, yield_psi=80000, connection_burst_psi=5000
        )
        self.assertTrue(r.success, r.error)
        self.assertAlmostEqual(r.values["governing_burst_psi"], 5000, places=0)


class MSEGroundTruth(unittest.TestCase):
    def test_teale_120pi(self):
        wob, rpm, tq, rop, d = 25000.0, 120.0, 8000.0, 30.0, 8.5
        ab = math.pi / 4.0 * d * d
        expected = wob / ab + (120.0 * math.pi * rpm * tq) / (ab * rop)
        r = MSEEngine.calculate(wob, rpm, tq, rop, d)
        self.assertTrue(r.success, r.error)
        self.assertAlmostEqual(r.value, expected, places=0)

    def test_zero_rop_is_error_not_invented(self):
        r = MSEEngine.calculate(25000, 120, 8000, 0, 8.5)
        self.assertFalse(r.success)


class MudVolumeGroundTruth(unittest.TestCase):
    def test_balance(self):
        r = MudVolumeEngine.balance(
            active_volume_bbl=800, additions_bbl=50, losses_bbl=20, dilution_bbl=10, dumped_bbl=5
        )
        self.assertTrue(r.success, r.error)
        self.assertAlmostEqual(r.value, 835.0, places=3)

    def test_weight_up_requires_density(self):
        r = MudVolumeEngine.weight_up(80, 90, 500, None)
        self.assertFalse(r.success)
        self.assertIn("MISSING_INPUT", r.error)


class TorqueDragGroundTruth(unittest.TestCase):
    def test_vertical_buoyed_weight(self):
        survey = [{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}]
        bha = [{"length": 3048.0, "weight": 19.5, "od": 5.0}]
        r = TorqueDragEngine.calculate(survey, bha, mud_density_ppg=10.0, friction_factor=0.2)
        self.assertTrue(r.success, r.error)
        self.assertEqual(r.scope, "PARTIAL")
        self.assertFalse(r.metadata.get("production_ready"))
        bf = 1.0 - 10.0 / 65.5
        expected = 10000.0 * 19.5 * bf / 1000.0
        self.assertAlmostEqual(r.values["total_buoyed_weight"], expected, places=1)
        self.assertAlmostEqual(expected, 165.23, places=2)
        self.assertAlmostEqual(r.values["hookload_rotating"], expected, places=1)
        self.assertIn("stretch_rotating_in", r.values)
        self.assertIn("side_force_profile", r.values)

    def test_neutral_point_with_wob(self):
        survey = [{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}]
        bha = [{"length": 3048.0, "weight": 19.5, "od": 5.0, "id": 4.276}]
        r = TorqueDragEngine.calculate(
            survey, bha, mud_density_ppg=10.0, friction_factor=0.2, wob_klbf=20.0
        )
        self.assertTrue(r.success, r.error)
        self.assertIsNotNone(r.values["neutral_point_md_m"])
        self.assertGreater(r.values["neutral_point_md_m"], 0)
        self.assertLess(r.values["neutral_point_md_m"], 3048.0)
        self.assertGreater(r.values["stretch_rotating_in"], 0)

    def test_buckling_uses_local_compression(self):
        survey = [{"md": 0, "inc": 90, "azi": 0}, {"md": 300, "inc": 90, "azi": 0}]
        bha = [{"length": 300, "weight": 19.5, "od": 5.0, "id": 4.276}]
        r = TorqueDragEngine.calculate(
            survey, bha, 10.0, 0.25, wob_klbf=40.0, wellbore_id_in=8.5
        )
        self.assertTrue(r.success, r.error)
        det = r.values["buckling"]["details"]
        self.assertTrue(det)
        self.assertIn("f_sin_lbf", det[0])
        self.assertIn("compression_lbf", det[0])

    def test_friction_not_defaulted(self):
        survey = [{"md": 0, "inc": 0, "azi": 0}, {"md": 100, "inc": 0, "azi": 0}]
        bha = [{"length": 100, "weight": 19.5, "od": 5.0}]
        r = TorqueDragEngine.calculate(survey, bha, 10.0, None)
        self.assertFalse(r.success)
        self.assertIn("MISSING_INPUT", r.error)


class CementHonesty(unittest.TestCase):
    def test_volume_scope_complete_worksheet(self):
        r = CementEngine.job_volumes(12.25, 9.625, 1000, 0)
        self.assertTrue(r.success, r.error)
        self.assertEqual(r.scope, "COMPLETE")
        expected_ann = (12.25**2 - 9.625**2) / 1029.4 * 1000
        self.assertAlmostEqual(r.values["annular_volume_bbl"], expected_ann, places=2)
        self.assertTrue(any("laboratory" in w.lower() or "UCA" in w for w in r.warnings))

    def test_hydrostatic_stack(self):
        r = CementEngine.hydrostatic_column(
            [
                {"name": "mud", "tvd_ft": 2000, "density_ppg": 10.0},
                {"name": "tail", "tvd_ft": 1000, "density_ppg": 16.0},
            ],
            pore_emw_ppg=9.0,
            shoe_tvd_ft=3000,
        )
        self.assertTrue(r.success, r.error)
        expected = 0.052 * 10 * 2000 + 0.052 * 16 * 1000
        self.assertAlmostEqual(r.value, expected, places=1)
        self.assertAlmostEqual(r.values["overbalance_psi"], expected - 0.052 * 9 * 3000, places=1)

    def test_sacks_from_yield_not_invented(self):
        r = CementEngine.job_volumes(12.25, 9.625, 1000, 0)
        self.assertIsNone(r.values["sacks"])
        r2 = CementEngine.job_volumes(12.25, 9.625, 1000, 0, yield_ft3_sk=1.18)
        self.assertTrue(r2.success, r2.error)
        slurry_cuft = r2.values["slurry_volume_cuft"]
        self.assertAlmostEqual(r2.values["sacks"], slurry_cuft / 1.18, places=1)


class HydraulicsGroundTruth(unittest.TestCase):
    def test_av_and_ecd(self):
        av = HydraulicsEngine.calculate_annular_velocity(250, 12.25, 5)
        self.assertAlmostEqual(av, 24.51 * 250 / (12.25**2 - 5**2), places=4)
        ecd = HydraulicsEngine.calculate_ecd(12, 200, 10000)
        self.assertAlmostEqual(ecd, 12 + 200 / (0.052 * 10000), places=4)


class BitHsiGroundTruth(unittest.TestCase):
    def test_hsi_is_hhp_over_area(self):
        hsi = BitEngine.calculate_hsi(400, 800, 8.5)
        ab = math.pi / 4 * 8.5 * 8.5
        self.assertAlmostEqual(hsi, (400 * 800 / 1714) / ab, places=4)


class BitPerformanceFromDdr(unittest.TestCase):
    def test_rop_from_run(self):
        r = BitPerformanceEngine.from_run(depth_in=1000, depth_out=1120, hours_on_bottom=12, bit_size_in=8.5)
        self.assertTrue(r.success, r.error)
        self.assertAlmostEqual(r.values["footage"], 120.0, places=3)
        self.assertAlmostEqual(r.values["rop"], 10.0, places=3)


class CompanyTemplateMapping(unittest.TestCase):
    def test_oeoc_template_maps_activity_and_field(self):
        svc = CompanyMappingService()
        self.assertIn("oeoc", svc.list_companies())
        rec = svc.map_activity(original_code="1.1", source_company="OEOC")
        self.assertEqual(rec.canonical_code, "1.1")
        self.assertGreaterEqual(rec.mapping_confidence, 1.0)
        self.assertEqual(svc.map_field("OEOC", "Mud Weight"), "mud_report.mw")

    def test_unknown_company_passthrough(self):
        svc = CompanyMappingService()
        rec = svc.map_activity(original_code="ZZ", source_company="NoSuchCo")
        self.assertEqual(rec.canonical_code, "ZZ")
        self.assertEqual(rec.mapping_confidence, 0.0)


class AIToolsCallEngines(unittest.TestCase):
    def test_kick_tolerance_tool(self):
        reg = AIToolRegistry()
        out = reg.call_tool(
            "calculate_kick_tolerance",
            mw_ppg=14.5,
            shoe_tvd_ft=6000,
            current_tvd_ft=10000,
            frac_mw_ppg=16.0,
            influx_gradient_psi_ft=0.1,
            annular_capacity_bbl_ft=0.0459,
            bha_annular_capacity_bbl_ft=0.0226,
            formation_emw_ppg=15.0,
        )
        self.assertTrue(out["success"], out.get("error"))
        self.assertAlmostEqual(out["values"]["kick_tolerance_bbl"], 7.2, delta=0.05)

    def test_td_no_silent_friction(self):
        reg = AIToolRegistry()
        out = reg.call_tool(
            "calculate_torque_drag",
            survey=[{"md": 0, "inc": 0, "azi": 0}, {"md": 100, "inc": 0, "azi": 0}],
            bha=[{"length": 100, "weight": 19.5, "od": 5}],
            mud_density_ppg=10,
        )
        self.assertFalse(out["success"])
        self.assertIn("MISSING_INPUT", out["error"])


if __name__ == "__main__":
    unittest.main()
