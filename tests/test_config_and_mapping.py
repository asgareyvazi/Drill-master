import unittest
from core.standards import bop_test_interval_days
from core.mapping_store import MappingStore

class ConfigAndMappingTests(unittest.TestCase):
    def test_bop_interval_is_positive(self):
        self.assertGreater(bop_test_interval_days(), 0)

    def test_mapping_fingerprint_is_stable(self):
        snapshot = {"tables": [{"headers": ["WOB", "RPM"]}]}
        self.assertEqual(MappingStore.fingerprint(snapshot), MappingStore.fingerprint(snapshot))

if __name__ == "__main__":
    unittest.main()
