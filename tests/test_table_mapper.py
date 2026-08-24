import unittest
from core.table_record_mapper import map_table

class TableMapperTests(unittest.TestCase):
    def test_creates_one_record_per_row(self):
        cells = {(1,1): "MD", (1,2): "Inclination", (1,3): "Azimuth", (2,1): 1000, (2,2): 5, (2,3): 90, (3,1): 1100, (3,2): 6, (3,3): 91}
        region = {"sheet": "Survey", "min_row": 1, "max_row": 3, "min_col": 1, "max_col": 3, "headers": ["MD", "Inclination", "Azimuth"], "columns": [{"column": 1}, {"column": 2}, {"column": 3}]}
        result = map_table(cells, region, "survey")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["source_row"], 3)
        self.assertEqual(result[0]["md"], 1000)

if __name__ == "__main__":
    unittest.main()
