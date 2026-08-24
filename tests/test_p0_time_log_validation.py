"""P0: Time Log 24h Validation Tests - Professional"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.import_quality import TimeLogValidator
from datetime import time


class TimeLogValidationTests(unittest.TestCase):
    def test_total_24h_valid(self):
        logs = [
            {"time_from": "00:00", "time_to": "06:00", "duration": 6.0, "main_code": "2 - Drilling"},
            {"time_from": "06:00", "time_to": "12:00", "duration": 6.0, "main_code": "2 - Drilling"},
            {"time_from": "12:00", "time_to": "18:00", "duration": 6.0, "main_code": "5 - Circulate"},
            {"time_from": "18:00", "time_to": "24:00", "duration": 6.0, "main_code": "6 - Trips"},
        ]
        report = TimeLogValidator.validate_logs(logs)
        # Should have no total warning
        total_warnings = [i for i in report.issues if "Total" in i.message]
        self.assertEqual(len(total_warnings), 0)

    def test_total_not_24h_warning(self):
        logs = [
            {"time_from": "00:00", "time_to": "06:00", "duration": 6.0},
            {"time_from": "06:00", "time_to": "12:00", "duration": 6.0},
            # Missing 12h
        ]
        report = TimeLogValidator.validate_logs(logs)
        self.assertTrue(any("24h" in i.message for i in report.issues))

    def test_overlap_detection(self):
        logs = [
            {"time_from": "00:00", "time_to": "08:00", "duration": 8.0},
            {"time_from": "07:00", "time_to": "12:00", "duration": 5.0},  # overlap 07-08
        ]
        report = TimeLogValidator.validate_logs(logs)
        self.assertTrue(any("overlap" in i.message.lower() for i in report.issues))

    def test_gap_detection(self):
        logs = [
            {"time_from": "00:00", "time_to": "06:00", "duration": 6.0},
            {"time_from": "08:00", "time_to": "12:00", "duration": 4.0},  # gap 06-08
        ]
        report = TimeLogValidator.validate_logs(logs)
        self.assertTrue(any("gap" in i.message.lower() for i in report.issues))

    def test_midnight_crossing(self):
        logs = [
            {"time_from": "22:00", "time_to": "24:00", "duration": 2.0},
            {"time_from": "00:00", "time_to": "06:00", "duration": 6.0},
        ]
        report = TimeLogValidator.validate_logs(logs)
        # Should handle midnight crossing without error for duration calc
        # But total will be 8h, so warning expected, not error
        self.assertTrue(len(report.issues) >= 1)

    def test_duration_mismatch_warning(self):
        logs = [
            {"time_from": "00:00", "time_to": "06:00", "duration": 5.0},  # mismatch: should be 6
        ]
        report = TimeLogValidator.validate_logs(logs)
        self.assertTrue(any("doesn't match" in i.message for i in report.issues))

    def test_duplicate_time_range(self):
        logs = [
            {"time_from": "00:00", "time_to": "06:00", "duration": 6.0},
            {"time_from": "00:00", "time_to": "06:00", "duration": 6.0},  # duplicate
        ]
        report = TimeLogValidator.validate_logs(logs)
        self.assertTrue(any("duplicate" in i.message.lower() for i in report.issues))

    def test_continuation_rows(self):
        logs = [
            {"time_from": "00:00", "time_to": "06:00", "duration": 6.0, "activity_description": "Drilling"},
            {"activity_description": "Continued drilling with same BHA"},  # continuation, no time
        ]
        report = TimeLogValidator.validate_logs(logs)
        # Should add review item for continuation, not error
        self.assertTrue(any("continuation" in str(item.get("target_field","")).lower() for item in report.review.as_rows()))

    def test_midnight_start_end_checks(self):
        logs = [
            {"time_from": "06:00", "time_to": "12:00", "duration": 6.0},
        ]
        report = TimeLogValidator.validate_logs(logs)
        self.assertTrue(any("00:00" in i.message for i in report.issues))
        self.assertTrue(any("24:00" in i.message for i in report.issues))

    def test_24_00_handling(self):
        # 24:00 should be parsed as 1440 minutes
        self.assertEqual(TimeLogValidator._to_minutes("24:00"), 24*60)
        self.assertEqual(TimeLogValidator._to_minutes("00:00"), 0)
        # Duration from 18:00 to 24:00 = 6h
        dur = TimeLogValidator._duration_from_times(18*60, 24*60)
        self.assertAlmostEqual(dur, 6.0)


if __name__ == "__main__":
    unittest.main()
