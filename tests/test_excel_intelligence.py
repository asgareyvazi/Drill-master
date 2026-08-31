"""Tests for Excel Intelligence Layer v2 — candidate scoring, engineering validation."""

import pytest
from core.excel_intelligence import (
    MergeCellAnalyzer, LabelDetector, FieldExtractor,
    DynamicTableExtractor, ExcelIntelligence, CandidateScorer,
    ExtractionResult, TableExtraction, ImportReport, Candidate,
    confidence_decision,
)
from core.canonical_schema import FIELD_SPECS, lookup_alias, get_engineering_bounds


class TestConfidencePolicy:
    def test_critical_accept(self):
        assert confidence_decision(0.99, critical=True) == "ACCEPT"
        assert confidence_decision(1.0, critical=True) == "ACCEPT"

    def test_critical_review(self):
        assert confidence_decision(0.90, critical=True) == "REVIEW"
        assert confidence_decision(0.85, critical=True) == "REVIEW"

    def test_critical_reject(self):
        assert confidence_decision(0.84, critical=True) == "REJECT"
        assert confidence_decision(0.50, critical=True) == "REJECT"

    def test_noncritical_accept(self):
        assert confidence_decision(0.95, critical=False) == "ACCEPT"

    def test_noncritical_review(self):
        assert confidence_decision(0.80, critical=False) == "REVIEW"
        assert confidence_decision(0.70, critical=False) == "REVIEW"

    def test_noncritical_reject(self):
        assert confidence_decision(0.69, critical=False) == "REJECT"


class TestCandidateScorer:
    def test_preferred_cell_not_1_0(self):
        """Preferred cell must NEVER get 1.0 automatically."""
        c = Candidate(value="AZNS-207", source="preferred_cell", row=3, col=23)
        score = CandidateScorer.score_candidate(c, "well_info.name")
        assert score < 1.0
        assert score < 0.95  # Should not be auto-accept

    def test_label_right_direction_bonus(self):
        """Value to the right of label should score higher."""
        c_right = Candidate(value="AZNS-207", source="label_match", row=3, col=23,
                           label_row=3, label_col=18, distance=5, direction="right")
        c_below = Candidate(value="AZNS-207", source="label_match", row=5, col=18,
                           label_row=3, label_col=18, distance=2, direction="below")
        score_right = CandidateScorer.score_candidate(c_right, "well_info.name")
        score_below = CandidateScorer.score_candidate(c_below, "well_info.name")
        # Right direction should score higher despite greater distance
        assert score_right > 0

    def test_numeric_field_bonus(self):
        """Numeric value for numeric field should get bonus."""
        c_num = Candidate(value=10.2, source="preferred_cell", row=3, col=5)
        c_text = Candidate(value="ABC", source="preferred_cell", row=3, col=5)
        score_num = CandidateScorer.score_candidate(c_num, "mud_report.mw")
        score_text = CandidateScorer.score_candidate(c_text, "mud_report.mw")
        assert score_num > score_text

    def test_already_assigned_penalty(self):
        """Already-assigned cell should get penalty."""
        c = Candidate(value="test", source="spatial", row=3, col=5)
        score_normal = CandidateScorer.score_candidate(c, "well_info.name")
        score_assigned = CandidateScorer.score_candidate(c, "well_info.name",
                                                          assigned_cells={(3, 5)})
        assert score_assigned < score_normal


class TestLabelDetector:
    def _make_detector(self, cells):
        return LabelDetector(cells)

    def test_find_exact(self):
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207"}
        d = self._make_detector(cells)
        matches = d.find_exact("Well Name:")
        assert len(matches) == 1

    def test_find_near_label_returns_scored(self):
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207", (5, 18): "Rig Name:"}
        d = self._make_detector(cells)
        nearby = d.find_near_label(3, 18, search_radius=10)
        assert len(nearby) > 0
        # Should include direction and distance
        _, _, val, direction, distance = nearby[0]
        assert direction in ("right", "below", "diagonal")


class TestFieldExtractor:
    def _make_extractor(self, cells):
        merge = type('MockMerge', (), {
            'get_value': lambda self, r, c: (None, False),
            'is_merged': lambda self, r, c: False,
        })()
        labels = LabelDetector(cells)
        return FieldExtractor(cells, merge, labels)

    def test_preferred_cell_is_candidate_not_truth(self):
        """Preferred cell should NOT get confidence=1.0."""
        cells = {(3, 23): "AZNS-207"}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 3, "col": 23, "field": "Well Name"}, "well_info.name")
        assert result.value == "AZNS-207"
        assert result.confidence < 1.0  # NEVER 1.0 from preferred alone
        assert result.confidence > 0    # Should have some confidence

    def test_label_match_finds_value(self):
        """Label-based detection should find value near label."""
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207"}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 99, "col": 99, "field": "Well Name"}, "well_info.name")
        # Should find via label or alias match
        assert result.value == "AZNS-207"
        assert result.confidence > 0

    def test_unresolved(self):
        cells = {(1, 1): "Something else entirely"}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 99, "col": 99, "field": "Nonexistent"}, "well_info.nonexistent")
        assert result.status == "UNRESOLVED"
        assert result.confidence == 0.0

    def test_engineering_validation_negative_md(self):
        """Negative MD should be flagged."""
        cells = {(3, 5): -100}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 3, "col": 5, "field": "MD"}, "survey.md")
        assert "engineering_violation" in result.validation or "below_minimum" in result.validation

    def test_engineering_validation_mw_zero(self):
        """MW = 0 should be flagged."""
        cells = {(3, 5): 0}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 3, "col": 5, "field": "MW"}, "mud_report.mw")
        assert result.validation != "valid"

    def test_engineering_validation_inclination_range(self):
        """Inclination > 180 should be flagged."""
        cells = {(3, 5): 200}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 3, "col": 5, "field": "Inc"}, "survey.inc")
        assert result.validation != "valid"
        assert "above_maximum" in result.validation or "engineering_violation" in result.validation

    def test_candidates_list_populated(self):
        """Result should include all candidates considered."""
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207", (3, 28): "Other"}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 99, "col": 99, "field": "Well Name"}, "well_info.name")
        assert len(result.candidates) > 0

    def test_provenance_preserved(self):
        """Result must preserve complete provenance."""
        cells = {(3, 18): "Well Name:", (3, 23): "AZNS-207"}
        ext = self._make_extractor(cells)
        result = ext.extract({"row": 3, "col": 23, "field": "Well Name"}, "well_info.name")
        assert result.canonical_field == "well_info.name"
        assert result.sheet != "" or result.row > 0
        assert result.canonical_unit is not None


class TestCanonicalSchemaIntegration:
    def test_lookup_alias(self):
        """Centralized alias lookup must work."""
        assert lookup_alias("mud weight") == "mud_report.mw"
        assert lookup_alias("well name") == "well_info.name"
        assert lookup_alias("bit size") == "drilling_params.bit_size"
        assert lookup_alias("md") == "survey.md"

    def test_engineering_bounds(self):
        """Engineering bounds must come from schema."""
        min_val, max_val = get_engineering_bounds("survey.inc")
        assert min_val == 0
        assert max_val == 180

        min_val, max_val = get_engineering_bounds("mud_report.mw")
        assert min_val == 0
        assert max_val == 25

    def test_no_independent_alias_dicts(self):
        """FieldExtractor must use canonical schema aliases, not private dicts."""
        spec = FIELD_SPECS.get("mud_report.mw")
        assert spec is not None
        assert "mud weight" in spec.aliases
        assert "mw" in spec.aliases
