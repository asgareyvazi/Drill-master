"""P0/P1: Engineering Core deterministic tests"""

import unittest
import sys
from pathlib import Path
import math

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.core import (
    TrajectoryEngine,
    BitEngine,
    BHAEngine,
    HydraulicsEngine,
    WellControlEngine,
    MudLedgerEngine,
    ChemicalLedgerEntry,
    MissingInputError,
)


class TrajectoryEngineTests(unittest.TestCase):
    def test_minimum_curvature_vertical(self):
        surveys = [
            {"md": 0, "inc": 0, "azi": 0},
            {"md": 100, "inc": 0, "azi": 0},
            {"md": 200, "inc": 0, "azi": 0},
        ]
        result = TrajectoryEngine.calculate(surveys)
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[-1].tvd, 200, places=1)
        self.assertAlmostEqual(result[-1].north, 0, places=1)

    def test_minimum_curvature_build(self):
        surveys = [
            {"md": 0, "inc": 0, "azi": 0},
            {"md": 100, "inc": 10, "azi": 0},
        ]
        result = TrajectoryEngine.calculate(surveys)
        self.assertEqual(len(result), 2)
        # TVD should be less than MD due to inclination
        self.assertLess(result[-1].tvd, 100)
        self.assertGreater(result[-1].north, 0)

    def test_duplicate_md_detection(self):
        surveys = [
            {"md": 100, "inc": 0, "azi": 0},
            {"md": 100, "inc": 5, "azi": 45},
        ]
        with self.assertRaises(Exception) as ctx:
            TrajectoryEngine.calculate(surveys)
        self.assertIn("Duplicate", str(ctx.exception))

    def test_non_monotonic_md_detection(self):
        surveys = [
            {"md": 200, "inc": 0, "azi": 0},
            {"md": 100, "inc": 5, "azi": 45},
        ]
        with self.assertRaises(Exception) as ctx:
            TrajectoryEngine.calculate(surveys)
        self.assertIn("Non-monotonic", str(ctx.exception))

    def test_missing_input(self):
        with self.assertRaises(MissingInputError):
            TrajectoryEngine.calculate([])

    def test_dls_calculation(self):
        surveys = [
            {"md": 0, "inc": 0, "azi": 0},
            {"md": 30, "inc": 2, "azi": 0},
        ]
        result = TrajectoryEngine.calculate(surveys, dls_unit="deg/30m")
        self.assertAlmostEqual(result[-1].dls, 2.0, places=1)


class BitEngineTests(unittest.TestCase):
    def test_tfa(self):
        # 3 nozzles of 12/32"
        tfa = BitEngine.calculate_tfa([12, 12, 12])
        # area per nozzle = pi/4 * (12/32)^2 = pi/4 * 0.140625 = 0.1104
        # total ~0.3313
        self.assertAlmostEqual(tfa, 0.3313, places=3)

    def test_missing_bit_size(self):
        with self.assertRaises(MissingInputError):
            BitEngine.validate({})

    def test_missing_nozzle(self):
        with self.assertRaises(MissingInputError):
            BitEngine.calculate_tfa([])


class BHAEngineTests(unittest.TestCase):
    def test_cumulative_length(self):
        comps = [
            {"component_name": "Bit", "length": 0.3},
            {"component_name": "Motor", "length": 7.5},
            {"component_name": "DC", "length": 20},
        ]
        total_len, total_weight, enriched = BHAEngine.calculate_cumulative(comps)
        self.assertAlmostEqual(total_len, 27.8, places=1)
        self.assertEqual(enriched[-1]["cumulative_length"], 27.8)

    def test_invalid_bha_length(self):
        comps = [{"component_name": "Bit", "length": -5}]
        with self.assertRaises(Exception):
            BHAEngine.calculate_cumulative(comps)


class HydraulicsEngineTests(unittest.TestCase):
    def test_annular_velocity(self):
        # Q=250 gpm, Dh=12.25", Dp=5"
        av = HydraulicsEngine.calculate_annular_velocity(250, 12.25, 5)
        # AV = 24.51*250 / (150.0625 -25) = 6127.5 /125.0625 ≈ 48.99 ft/min
        self.assertAlmostEqual(av, 48.99, places=1)

    def test_ecd(self):
        # MW=12 ppg, APL=200 psi, TVD=5000 ft
        ecd = HydraulicsEngine.calculate_ecd(12, 200, 5000)
        # ECD = 12 + 200/(0.052*5000)=12+200/260=12+0.769=12.769
        self.assertAlmostEqual(ecd, 12.769, places=2)

    def test_pv_yp(self):
        pv, yp = HydraulicsEngine.calculate_pv_yp(60, 35)
        self.assertEqual(pv, 25)
        self.assertEqual(yp, 10)


class WellControlEngineTests(unittest.TestCase):
    def test_kill_mw(self):
        # Original 12 ppg, SIDPP 500 psi, TVD 5000 ft
        kill = WellControlEngine.calculate_kill_mw(12, 500, 5000)
        # 12 + 500/(0.052*5000)=12+1.923=13.923
        self.assertAlmostEqual(kill, 13.923, places=2)

    def test_maasp(self):
        maasp = WellControlEngine.calculate_maasp(14, 12, 2000)
        # (14-12)*0.052*2000=2*104=208 psi
        self.assertAlmostEqual(maasp, 208, places=0)


class MudLedgerEngineTests(unittest.TestCase):
    def test_closing_formula(self):
        # Closing = Opening + Received + Adjusted - Used - Returned
        entry = ChemicalLedgerEntry(
            product="Bentonite",
            opening_stock=100,
            received=50,
            used=30,
            returned=10,
            adjusted=5,
            unit="kg",
        )
        self.assertEqual(entry.closing_stock, 100+50+5-30-10)

    def test_negative_stock_alert(self):
        entry = ChemicalLedgerEntry(product="Barite", opening_stock=10, used=20, unit="kg")
        alerts = entry.alerts()
        self.assertTrue(any("Negative" in a for a in alerts))

    def test_next_day_opening(self):
        self.assertEqual(MudLedgerEngine.next_day_opening(125.5), 125.5)

    def test_history(self):
        daily = [
            {"date": "2026-01-01", "product": "Bentonite", "used": 10, "closing": 90, "received": 0},
            {"date": "2026-01-02", "product": "Bentonite", "used": 15, "closing": 75, "received": 0},
            {"date": "2026-01-03", "product": "Bentonite", "used": 20, "closing": 55, "received": 0},
        ]
        history = MudLedgerEngine.build_history(daily)
        self.assertIn("Bentonite", history)
        self.assertEqual(history["Bentonite"]["consumption_rate"], 15.0)


if __name__ == "__main__":
    unittest.main()
