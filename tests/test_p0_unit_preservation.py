"""P0: Unit Preservation Tests"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.unit_manager import UnitManager


class UnitPreservationTests(unittest.TestCase):
    def test_sg_to_ppg(self):
        # 1.50 SG → 12.52 ppg
        record = UnitManager.create_record("mud_report.mw", "density", "sg", 1.5, "ppg")
        self.assertAlmostEqual(record.normalized_value, 12.518, places=2)
        self.assertEqual(record.original_value, 1.5)
        self.assertEqual(record.source_unit, "sg")
        self.assertEqual(record.canonical_unit, "ppg")
        self.assertIn("SG", record.conversion_rule)

    def test_ft_to_m(self):
        record = UnitManager.create_record("survey.md", "depth", "ft", 1000, "m")
        self.assertAlmostEqual(record.normalized_value, 304.8, places=1)

    def test_detect_unit(self):
        val, unit = UnitManager.detect_unit("1.50 SG")
        self.assertEqual(val, 1.5)
        self.assertEqual(unit, "SG")

        val, unit = UnitManager.detect_unit("12.5 ppg")
        self.assertEqual(val, 12.5)
        self.assertEqual(unit, "ppg")

        val, unit = UnitManager.detect_unit("3500 m")
        self.assertEqual(val, 3500)
        self.assertEqual(unit, "m")

    def test_missing_preservation(self):
        # Missing should preserve None, not fake 0
        record = UnitManager.create_record("daily_report.depth_2400", "depth", "m", None, "m")
        self.assertIsNone(record.normalized_value)
        self.assertEqual(record.confidence, 0.0)

    def test_no_fake_defaults_in_convert(self):
        self.assertIsNone(UnitManager.convert(None, "length", "ft", "m"))
        self.assertIsNone(UnitManager.convert("", "length", "ft", "m"))

    def test_all_required_quantities_exist(self):
        required = ["length", "diameter", "depth", "pressure", "flow_rate", "volume", "density", "temperature", "torque", "force", "weight", "rop", "rpm", "viscosity", "yield_point", "ecd", "dls", "azimuth", "inclination"]
        for qty in required:
            units = UnitManager.units_for(qty)
            self.assertTrue(len(units) > 0, f"Quantity {qty} should have units")

    def test_canonical_units(self):
        self.assertEqual(UnitManager.canonical_for("depth"), "m")
        self.assertEqual(UnitManager.canonical_for("density"), "ppg")
        self.assertEqual(UnitManager.canonical_for("pressure"), "psi")
        self.assertEqual(UnitManager.canonical_for("rop"), "m/hr")

    def test_normalize_row_preserves_none(self):
        row = {"depth_2400": None, "mw": 12.5}
        unit_map = {"depth_2400": ("depth", "ft", "m"), "mw": ("density", "ppg", "ppg")}
        result = UnitManager.normalize_row(row, unit_map)
        self.assertIsNone(result["depth_2400"])
        self.assertEqual(result["mw"], 12.5)


if __name__ == "__main__":
    unittest.main()
