"""Tests for data lineage tracking."""
import pytest
from core.lineage import LineageRecord, LineageTracker, get_import_lineage, reset_import_lineage


class TestLineageRecord:
    def test_create_minimal(self):
        r = LineageRecord(canonical_field="mud_report.mw", value=10.2)
        assert r.canonical_field == "mud_report.mw"
        assert r.value == 10.2
        assert r.source_file == ""
        assert r.confidence == 0.0

    def test_create_full(self):
        r = LineageRecord(
            canonical_field="mud_report.mw",
            value=12.52,
            source_file="DDR_2026_08_20.xlsx",
            source_sheet="Daily Report",
            source_cell="H17",
            source_row=17,
            source_column=8,
            original_label="Mud Wt.",
            original_value=1.50,
            original_unit="SG",
            normalized_value=12.52,
            normalized_unit="ppg",
            conversion_rule="1.50 SG * 8.3454 = 12.52 ppg",
            mapping_method="ai",
            confidence=0.96,
            validation_status="valid",
        )
        assert r.source_file == "DDR_2026_08_20.xlsx"
        assert r.confidence == 0.96
        assert r.mapping_method == "ai"

    def test_as_dict(self):
        r = LineageRecord(canonical_field="survey.md", value=1500.0)
        d = r.as_dict()
        assert isinstance(d, dict)
        assert d["canonical_field"] == "survey.md"
        assert d["value"] == 1500.0

    def test_summary(self):
        r = LineageRecord(
            canonical_field="mud_report.mw",
            value=12.52,
            source_file="DDR.xlsx",
            source_sheet="Mud",
            source_cell="B5",
            original_label="MW",
            normalized_unit="ppg",
            mapping_method="deterministic",
            confidence=0.95,
        )
        summary = r.summary()
        assert "mud_report.mw" in summary
        assert "12.52" in summary
        assert "DDR.xlsx" in summary
        assert "95%" in summary


class TestLineageTracker:
    def test_track_record(self):
        tracker = LineageTracker()
        r = LineageRecord(canonical_field="mud_report.mw", value=10.2)
        tracker.track(r)
        assert tracker.count == 1
        assert tracker.records[0].canonical_field == "mud_report.mw"

    def test_track_value_convenience(self):
        tracker = LineageTracker()
        tracker.track_value(
            canonical_field="survey.md",
            value=1500.0,
            source_file="DDR.xlsx",
            source_sheet="Survey",
            source_cell="A3",
            original_label="MD",
            mapping_method="deterministic",
            confidence=1.0,
        )
        assert tracker.count == 1
        r = tracker.records[0]
        assert r.source_file == "DDR.xlsx"
        assert r.confidence == 1.0

    def test_get_by_field(self):
        tracker = LineageTracker()
        tracker.track_value(canonical_field="mud_report.mw", value=10.2)
        tracker.track_value(canonical_field="mud_report.pv", value=15.0)
        tracker.track_value(canonical_field="mud_report.mw", value=10.5)
        
        mw_records = tracker.get_by_field("mud_report.mw")
        assert len(mw_records) == 2
        
        pv_records = tracker.get_by_field("mud_report.pv")
        assert len(pv_records) == 1

    def test_get_by_source(self):
        tracker = LineageTracker()
        tracker.track_value(canonical_field="mud_report.mw", value=10.2, source_file="DDR1.xlsx")
        tracker.track_value(canonical_field="mud_report.pv", value=15.0, source_file="DDR2.xlsx")
        tracker.track_value(canonical_field="survey.md", value=1500.0, source_file="DDR1.xlsx", source_sheet="Survey")
        
        ddr1 = tracker.get_by_source("DDR1.xlsx")
        assert len(ddr1) == 2
        
        survey = tracker.get_by_source("DDR1.xlsx", "Survey")
        assert len(survey) == 1

    def test_get_low_confidence(self):
        tracker = LineageTracker()
        tracker.track_value(canonical_field="mud_report.mw", value=10.2, confidence=0.95)
        tracker.track_value(canonical_field="mud_report.pv", value=15.0, confidence=0.5)
        tracker.track_value(canonical_field="survey.md", value=1500.0, confidence=0.0)
        
        low = tracker.get_low_confidence(0.7)
        assert len(low) == 1
        assert low[0].canonical_field == "mud_report.pv"

    def test_get_errors(self):
        tracker = LineageTracker()
        tracker.track_value(canonical_field="mud_report.mw", value=10.2, validation_status="valid")
        tracker.track_value(canonical_field="mud_report.pv", value=-5.0, validation_status="error")
        
        errors = tracker.get_errors()
        assert len(errors) == 1
        assert errors[0].canonical_field == "mud_report.pv"

    def test_to_json(self):
        tracker = LineageTracker()
        tracker.track_value(canonical_field="mud_report.mw", value=10.2)
        
        json_str = tracker.to_json()
        assert "mud_report.mw" in json_str
        assert "10.2" in json_str

    def test_summary_table(self):
        tracker = LineageTracker()
        tracker.track_value(
            canonical_field="mud_report.mw",
            value=10.2,
            source_sheet="Mud",
            source_cell="B5",
            original_label="MW",
            normalized_unit="ppg",
            mapping_method="deterministic",
            confidence=0.95,
        )
        
        table = tracker.summary_table()
        assert len(table) == 1
        assert table[0]["field"] == "mud_report.mw"
        assert table[0]["confidence"] == "95%"

    def test_clear(self):
        tracker = LineageTracker()
        tracker.track_value(canonical_field="mud_report.mw", value=10.2)
        assert tracker.count == 1
        
        tracker.clear()
        assert tracker.count == 0

    def test_imported_at_auto_set(self):
        tracker = LineageTracker()
        r = LineageRecord(canonical_field="mud_report.mw", value=10.2)
        assert r.imported_at == ""
        tracker.track(r)
        assert r.imported_at != ""


class TestGlobalLineage:
    def test_singleton(self):
        reset_import_lineage()
        tracker = get_import_lineage()
        tracker.track_value(canonical_field="test.field", value=42)
        
        # Same instance
        tracker2 = get_import_lineage()
        assert tracker2.count == 1
        
        reset_import_lineage()
        assert get_import_lineage().count == 0
