import unittest
from core.import_quality import ImportValidator, find_duplicates, decision_for_confidence
from core.unit_manager import UnitManager

class ImportCoreTests(unittest.TestCase):
    def test_duplicate_time_logs(self):
        rows = [{"report_id": 1, "time_from": "08:00", "time_to": "09:00"}, {"report_id": 1, "time_from": "08:00", "time_to": "09:00"}]
        self.assertEqual(find_duplicates(rows, "time_log"), [1])

    def test_confidence_policy(self):
        self.assertEqual(decision_for_confidence(.99), "ACCEPT")
        self.assertEqual(decision_for_confidence(.80), "REVIEW")
        self.assertEqual(decision_for_confidence(.50), "REJECT")

    def test_units(self):
        self.assertAlmostEqual(UnitManager.convert(1, "length", "ft", "m"), .3048, places=5)
        self.assertAlmostEqual(UnitManager.convert(1.5, "density", "sg", "ppg"), 12.5181, places=3)

    def test_row_validation(self):
        report = ImportValidator.validate_rows([{"report_date": "2026-01-01"}], "daily_report")
        self.assertTrue(report.success)
        self.assertEqual(report.total, 1)

if __name__ == "__main__":
    unittest.main()
