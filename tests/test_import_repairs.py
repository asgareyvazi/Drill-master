"""Permanent regressions for production DDR import boundaries."""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from core.import_quality import ImportReviewMatrix
from core.mineru_engine import DocumentNormalizer, parse_mineru_output
from core.value_normalizer import ValueNormalizer


class ImportRepairRegressionTests(unittest.TestCase):
    def test_review_item_accepts_legacy_value_and_new_metadata_contract(self):
        matrix = ImportReviewMatrix()
        item = matrix.add(
            file="report.xlsx",
            sheet="DDR Data",
            row=12,
            column=4,
            value="Drilling Data",
            original_value="Drilling Data",
            target_field="drilling_params.wob_max",
            expected_type="number",
            status="REVIEW_REQUIRED",
            reason="numeric conversion was unsafe",
            confidence=0.0,
        )
        self.assertEqual(item.value, "Drilling Data")
        self.assertEqual(item.proposed_value, "Drilling Data")
        self.assertEqual(item.normalized_value, "Drilling Data")
        self.assertEqual(item.validation_state, "REVIEW_REQUIRED")
        self.assertEqual(item.source_cell, "D12")

    def test_mineru_drilling_data_title_or_token_never_reaches_numeric_value(self):
        with tempfile.TemporaryDirectory(prefix="drillmaster-mineru-regression-") as directory:
            root = Path(directory)
            (root / "report.md").write_text(
                "# Drilling Data\n"
                "| WOB | RPM |\n"
                "| --- | --- |\n"
                "| Drilling Data | 120 |\n"
                "| 10 | 90 |\n",
                encoding="utf-8",
            )
            document = parse_mineru_output(root, source_file="reported-ddr.pdf")
            normalized = DocumentNormalizer().normalize(document)

        records = normalized.canonical_data["drilling_params"]
        self.assertEqual(records[0]["wob_max"], None)
        self.assertEqual(records[0]["rpm_max"], 120.0)
        self.assertEqual(records[1]["wob_max"], 10.0)
        self.assertTrue(any(item.get("value") == "Drilling Data" for item in normalized.warnings))
        self.assertTrue(any(item.get("expected_type") in {"number", "force"} for item in normalized.warnings))

    def test_malformed_numeric_is_reviewable_and_not_zero(self):
        result = ValueNormalizer.normalize("Drilling Data", "pressure")
        self.assertFalse(result.ok)
        self.assertTrue(result.needs_review)
        self.assertIsNone(result.value)
        self.assertIsNone(ValueNormalizer.to_float("Drilling Data"))
        self.assertEqual(ValueNormalizer.to_float("0"), 0.0)

    def test_to_int_preserves_missing_and_rejects_invalid_tokens(self):
        for value in (None, "", "   "):
            self.assertIsNone(ValueNormalizer.to_int(value))
        self.assertEqual(ValueNormalizer.to_int("12"), 12)
        self.assertIsNone(ValueNormalizer.to_int("not-a-number"))

    def test_missing_nozzle_number_reaches_db_as_null_without_crashing(self):
        import json
        from datetime import date
        try:
            from dialogs.excel_import_dialog import ExcelImportDialog
        except ImportError as exc:
            if "libGL" in str(exc):
                self.skipTest(f"Qt unavailable in this headless environment: {exc}")
            raise

        class CaptureDB:
            def __init__(self):
                self.payload = None

            def save_drilling_parameters(self, payload, session=None):
                # Production contract (core/database.py: save_drilling_parameters(
                # data, session=None)) — the capture double must accept the
                # caller-owned session keyword.
                self.payload = payload
                return True

        dialog = ExcelImportDialog.__new__(ExcelImportDialog)
        dialog.well_id = 17
        dialog.db = CaptureDB()
        dialog._save_drilling_params(
            {"nozzle1_no": None, "nozzle1_size": "18/32", "nozzle2_no": "   "},
            report_id=23,
            report_date=date(2025, 10, 27),
        )
        nozzle_rows = json.loads(dialog.db.payload["nozzles_json"])
        self.assertIsNone(nozzle_rows[0]["quantity"])
        self.assertEqual(nozzle_rows[0]["size_32nd"], 18.0)
        self.assertEqual(nozzle_rows[0]["diameter_inch"], 0.5625)

    def test_shared_normalizer_covers_typed_import_values(self):
        self.assertEqual(ValueNormalizer.to_int("12"), 12)
        self.assertEqual(ValueNormalizer.to_decimal("12.50"), ValueNormalizer.to_decimal("12.5"))
        self.assertEqual(ValueNormalizer.to_date("22-Oct-2024").isoformat(), "2024-10-22")
        self.assertEqual(ValueNormalizer.to_time("23:30").hour, 23)
        self.assertEqual(ValueNormalizer.to_duration("01:30").total_seconds(), 5400)
        self.assertIs(ValueNormalizer.to_bool("yes"), True)
        self.assertEqual(ValueNormalizer.to_float("3K"), 3000.0)
        self.assertEqual(ValueNormalizer.to_float("17-1/2\""), 17.5)


if __name__ == "__main__":
    unittest.main()
