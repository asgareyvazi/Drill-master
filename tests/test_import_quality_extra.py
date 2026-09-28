import unittest
from core.import_quality import ImportReport, ImportReviewMatrix, decision_for_confidence

class ImportQualityExtraTests(unittest.TestCase):
    def test_multiple_errors_same_row_count_once(self):
        report = ImportReport()
        report.error("DDR", 7, "missing", "date")
        report.error("DDR", 7, "missing", "well")
        self.assertEqual(report.failed, 1)
        self.assertEqual(len(report.errors), 2)

    def test_review_matrix_preserves_provenance(self):
        matrix = ImportReviewMatrix()
        matrix.add(sheet="DDR Data", row=9, column="L", source_value="83", normalized_value=83, unit="pcf", canonical_field="mud_report.mw", confidence=.99, decision="ACCEPT")
        self.assertEqual(matrix.as_rows()[0]["source_sheet" if "source_sheet" in matrix.as_rows()[0] else "sheet"], "DDR Data")

    def test_critical_confidence_is_strict(self):
        self.assertEqual(decision_for_confidence(.98, critical=True), "REVIEW")
        self.assertEqual(decision_for_confidence(.99, critical=True), "ACCEPT")

    def test_review_item_normalizes_row_level_provenance_and_entity(self):
        from core.import_quality import ReviewItem

        item = ReviewItem.from_dict({
            "file": "report.xlsx",
            "source_cells": {"survey.md": "R58C10", "survey.azi": "R58C12"},
            "source_row": 58,
            "field": "survey_points.inc/azi",
            "original_value": {"inc": 0.25, "azi": None},
            "reason": "Survey station persisted with NULL angle for review",
            "classification": "survey-ambiguity",
        })
        assert item.entity == "survey_points"
        assert item.source_cell == "R58C10; R58C12"
        assert item.source_location["file"] == "report.xlsx"
        assert item.source_location["row"] == 58
        assert item.mapping_method == "source-validation"
        assert item.expected_type == "canonical value"
        assert item.classification == "survey-ambiguity"

if __name__ == "__main__":
    unittest.main()
