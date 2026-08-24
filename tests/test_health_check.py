import unittest
from core.health_check import check_dependencies

class HealthCheckTests(unittest.TestCase):
    def test_health_report_shape(self):
        report = check_dependencies()
        self.assertIn("python", report)
        self.assertIn("core", report)
        self.assertIn("optional", report)
        self.assertIn("openpyxl", report["core"])

if __name__ == "__main__":
    unittest.main()
