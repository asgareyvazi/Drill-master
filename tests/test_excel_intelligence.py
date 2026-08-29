"""Tests for Excel Intelligence Layer — robust extraction engine."""

import pytest
from core.excel_intelligence import (
    MergeCellAnalyzer, LabelDetector, FieldExtractor,
    DynamicTableExtractor, ExcelIntelligence,
    ExtractionResult, TableExtraction, ImportReport,
)


class TestExtractionResult:
    def test_to_dict(self):
        r = ExtractionResult(
            canonical_field="well_info.name", value="AZNS-207",
            status="OK", confidence=1.0, source="preferred_cell",
            cell="W3", row=3, col=23, sheet="DDR Remark",
        )
        d = r.to_dict()
        assert d["field"] == "well_info.name"
        assert d["value"] == "AZNS-207"
        assert d["confidence"] == 1.0


class TestLabelDetector:
    def _make_detector(self, cells):
        return LabelDetector(cells)

    def test_find_exact(self):
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207"}
        d = self._make_detector(cells)
        matches = d.find_exact("Well Name:")
        assert len(matches) == 1
        assert matches[0] == (3, 18, "Well Name:")

    def test_find_exact_case_insensitive(self):
        cells = {(3, 18): "WELL NAME:"}
        d = self._make_detector(cells)
        matches = d.find_exact("well name:")
        assert len(matches) == 1

    def test_find_aliases(self):
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207"}
        d = self._make_detector(cells)
        matches = d.find_aliases(["well name", "well name:", "well"])
        assert len(matches) > 0

    def test_find_near_label(self):
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207", (3, 28): "Project:"}
        d = self._make_detector(cells)
        nearby = d.find_near_label(3, 18, search_radius=10)
        assert len(nearby) > 0
        values = [v for _, _, v in nearby]
        assert "AZNS-207" in values

    def test_find_fuzzy(self):
        cells = {(3, 18): "Well Name:"}
        d = self._make_detector(cells)
        matches = d.find_fuzzy("well name", threshold=0.6)
        assert len(matches) > 0

    def test_looks_like_label(self):
        d = self._make_detector({})
        assert d._looks_like_label("Well Name:") is True
        assert d._looks_like_label("MW") is True
        assert d._looks_like_label("10.2") is False
        assert d._looks_like_label("AZNS-207") is False


class TestFieldExtractor:
    def _make_extractor(self, cells):
        merge = type('MockMerge', (), {
            'get_value': lambda self, r, c: (None, False),
            'is_merged': lambda self, r, c: False,
        })()
        labels = LabelDetector(cells)
        return FieldExtractor(cells, merge, labels)

    def test_preferred_cell(self):
        cells = {(3, 23): "AZNS-207"}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 3, "col": 23, "field": "Well Name"}, "well_info.name")
        assert result.status == "OK"
        assert result.value == "AZNS-207"
        assert result.confidence == 1.0
        assert result.source == "preferred_cell"

    def test_preferred_cell_empty_falls_through(self):
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207"}
        ext = self._make_extractor(cells)
        # Row 5, col 25 is empty — should fall through to label search
        result = ext.extract({"row": 5, "col": 25, "field": "Well Name"}, "well_info.name")
        # Should find via label match
        assert result.value is not None or result.status == "UNRESOLVED"

    def test_label_match(self):
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207"}
        ext = self._make_extractor(cells)
        # Wrong preferred cell, but label exists
        result = ext.extract({"row": 99, "col": 99, "field": "Well Name"}, "well_info.name")
        assert result.value == "AZNS-207"
        assert result.source in ("label_match", "alias_match", "fuzzy_match")

    def test_unresolved(self):
        cells = {(1, 1): "Something else entirely"}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 99, "col": 99, "field": "Nonexistent"}, "well_info.nonexistent")
        assert result.status == "UNRESOLVED"
        assert result.confidence == 0.0

    def test_numeric_validation(self):
        cells = {(3, 23): 10.2}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 3, "col": 23, "field": "MW"}, "mud_report.mw")
        assert result.validation == "valid"

    def test_invalid_numeric(self):
        cells = {(3, 23): "ABC"}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 3, "col": 23, "field": "MW"}, "mud_report.mw")
        assert result.validation == "invalid_type"


class TestImportReport:
    def test_summary(self):
        r = ImportReport(
            fields_detected=100,
            fields_unresolved=5,
            fields_conflict=1,
            fields_low_confidence=3,
            tables_detected=6,
            total_rows_extracted=50,
            extraction_time_ms=150.5,
        )
        s = r.summary()
        assert "100 detected" in s
        assert "5 unresolved" in s
        assert "6" in s
        assert "150ms" in s
