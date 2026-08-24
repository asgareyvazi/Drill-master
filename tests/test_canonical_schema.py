import unittest
from core.canonical_schema import FIELD_SPECS, CANONICAL_FIELDS

class CanonicalSchemaTests(unittest.TestCase):
    def test_registry_is_unique_and_typed(self):
        self.assertEqual(len(FIELD_SPECS), len(CANONICAL_FIELDS))
        self.assertEqual(FIELD_SPECS["mud_report.mw"].unit, "ppg")
        self.assertTrue(FIELD_SPECS["daily_report.depth_2400"].critical)

if __name__ == "__main__":
    unittest.main()
