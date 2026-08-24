import unittest
from core.actual_vs_plan import compare
from core.import_profiler import ImportProfiler

class OperationsTests(unittest.TestCase):
    def test_plan_variance(self):
        result = compare("Depth", 1000, 900)
        self.assertEqual(result.status, "behind")
        self.assertAlmostEqual(result.variance_pct, -10.0)

    def test_zero_plan_is_safe(self):
        result = compare("Hours", 0, 0)
        self.assertEqual(result.variance_pct, 0.0)
        self.assertEqual(result.status, "on-track")

    def test_import_profiler(self):
        profiler = ImportProfiler()
        with profiler.measure("test"):
            pass
        self.assertIn("test", profiler.as_dict())
        self.assertGreaterEqual(profiler.total(), 0)

if __name__ == "__main__":
    unittest.main()
