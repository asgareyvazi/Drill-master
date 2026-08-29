"""Tests for Canonical Activity Mapper — company/template-aware code mapping."""

import pytest
from core.activity_mapper import (
    ActivityMapper, CANONICAL_ACTIVITIES, KNOWN_CODE_PATTERNS,
    ActivityMappingResult,
)


@pytest.fixture
def mapper():
    return ActivityMapper()


class TestCanonicalActivities:
    def test_all_activities_have_required_fields(self):
        for act_id, act in CANONICAL_ACTIVITIES.items():
            assert act.canonical_id == act_id
            assert act.name
            assert act.category

    def test_drilling_exists(self):
        assert "DRILLING" in CANONICAL_ACTIVITIES
        assert CANONICAL_ACTIVITIES["DRILLING"].category == "Operations"

    def test_npt_activities_flagged(self):
        assert CANONICAL_ACTIVITIES["RIG_REPAIR"].is_npt is True
        assert CANONICAL_ACTIVITIES["WAIT_ON_WEATHER"].is_npt is True
        assert CANONICAL_ACTIVITIES["DRILLING"].is_npt is False


class TestThreeCompanyMapping:
    """Test: Three companies with different codes all map to DRILLING."""

    def test_numeric_code_2_drilling(self, mapper):
        """Company A: code 2 → DRILLING"""
        result = mapper.map_activity("2", "Drilling ahead", company="CompanyA")
        assert result.canonical_id == "DRILLING"
        assert result.confidence >= 0.85
        assert result.source_code == "2"

    def test_alpha_code_drl_drilling(self, mapper):
        """Company B: code DRL → DRILLING"""
        result = mapper.map_activity("DRL", "Drilling", company="CompanyB")
        assert result.canonical_id == "DRILLING"
        assert result.confidence >= 0.85
        assert result.source_code == "DRL"

    def test_custom_code_d01_drilling(self, mapper):
        """Company C: code D01 → DRILLING (via description)"""
        result = mapper.map_activity("D01", "Drilling 12.25in hole", company="CompanyC")
        assert result.canonical_id == "DRILLING"
        assert result.confidence >= 0.70


class TestCirculationMapping:
    """Test: Different codes mapping to CIRCULATION."""

    def test_numeric_5_circulation(self, mapper):
        result = mapper.map_activity("5", "Circulate & Condition", company="CompanyA")
        assert result.canonical_id == "CIRCULATION"

    def test_alpha_cir_circulation(self, mapper):
        result = mapper.map_activity("CIR", "Circulation", company="CompanyB")
        assert result.canonical_id == "CIRCULATION"

    def test_description_circulate(self, mapper):
        result = mapper.map_activity("X1", "Circulate hole clean", company="CompanyC")
        assert result.canonical_id == "CIRCULATION"


class TestTrippingMapping:
    """Test: Different codes mapping to TRIPPING."""

    def test_numeric_6_tripping(self, mapper):
        result = mapper.map_activity("6", "Trips", company="CompanyA")
        assert result.canonical_id in ("TRIPPING_IN", "TRIPPING_OUT")

    def test_pooh_tripping_out(self, mapper):
        result = mapper.map_activity("POOH", "Pull out of hole", company="CompanyB")
        assert result.canonical_id == "TRIPPING_OUT"

    def test_rih_tripping_in(self, mapper):
        result = mapper.map_activity("RIH", "Run in hole", company="CompanyB")
        assert result.canonical_id == "TRIPPING_IN"

    def test_subcode_6_6_tripping_out(self, mapper):
        result = mapper.map_activity("6-6", "Pull Out Of Hole", company="CompanyA")
        assert result.canonical_id == "TRIPPING_OUT"


class TestAmbiguousCodeResolution:
    """Test: Ambiguous code resolved using description."""

    def test_code_c_connection(self, mapper):
        """Code C with description 'Connection' → CONNECTION"""
        result = mapper.map_activity("C", "Connection", company="Test")
        # Should resolve to CONNECTION via description
        assert result.canonical_id in ("CONNECTION", "CIRCULATION")
        # If description says "Connection", should be CONNECTION
        if "connection" in result.source_description.lower():
            assert result.canonical_id == "CONNECTION"

    def test_code_c_circulation(self, mapper):
        """Code C with description 'Circulating' → CIRCULATION"""
        result = mapper.map_activity("C", "Circulating mud", company="Test")
        assert result.canonical_id == "CIRCULATION"

    def test_description_drilling_params(self, mapper):
        """Description with drilling parameters should still map to DRILLING"""
        result = mapper.map_activity(
            "2", "Cont. Drlg 17-1/2\" HS f/ 155 to 165m; WOB: 10-25klb",
            company="OEOC"
        )
        assert result.canonical_id == "DRILLING"


class TestUnknownCode:
    """Test: Unknown code → UNRESOLVED, never silent mapping."""

    def test_unknown_code_unresolved(self, mapper):
        result = mapper.map_activity("ZZZZ", "", company="Unknown")
        assert result.method == "unresolved"
        assert result.confidence == 0.0

    def test_unknown_with_description(self, mapper):
        result = mapper.map_activity("XX", "Some unknown activity", company="Test")
        # Should either match via description or be unresolved
        if result.method == "unresolved":
            assert result.confidence == 0.0

    def test_empty_code_unresolved(self, mapper):
        result = mapper.map_activity("", "", company="Test")
        assert result.method == "unresolved"
        assert result.confidence == 0.0


class TestLearnedMapping:
    """Test: User-approved mapping persists."""

    def test_learn_and_retrieve(self, mapper):
        mapper.learn_mapping("CUSTOM1", "DRILLING", company="MyCompany")
        result = mapper.map_activity("CUSTOM1", "Drilling", company="MyCompany")
        assert result.canonical_id == "DRILLING"
        assert result.method == "learned"
        assert result.confidence >= 0.95

    def test_learned_company_specific(self, mapper):
        mapper.learn_mapping("X", "DRILLING", company="CompanyA")
        # Different company with same code should NOT use learned mapping
        result = mapper.map_activity("X", "Something else", company="CompanyB")
        assert result.method != "learned"


class TestProvenance:
    """Test: Original company code is preserved."""

    def test_source_code_preserved(self, mapper):
        result = mapper.map_activity("DRL", "Drilling", company="Test")
        assert result.source_code == "DRL"
        assert result.source_description == "Drilling"

    def test_result_has_all_fields(self, mapper):
        result = mapper.map_activity("2", "Drilling", company="Test")
        d = result.to_dict()
        assert "source_code" in d
        assert "source_description" in d
        assert "canonical_id" in d
        assert "canonical_name" in d
        assert "category" in d
        assert "is_npt" in d
        assert "confidence" in d
        assert "method" in d
        assert "reason" in d


class TestNPTClassification:
    """Test: NPT activities are correctly classified."""

    def test_rig_repair_is_npt(self, mapper):
        result = mapper.map_activity("8", "Repair Rig", company="Test")
        assert result.is_npt is True
        assert result.npt_category != ""

    def test_drilling_not_npt(self, mapper):
        result = mapper.map_activity("2", "Drilling", company="Test")
        assert result.is_npt is False

    def test_wait_on_weather_is_npt(self, mapper):
        result = mapper.map_activity("20-5", "Waiting on Weather", company="Test")
        assert result.is_npt is True

    def test_well_control_is_npt(self, mapper):
        result = mapper.map_activity("27", "Well Control", company="Test")
        assert result.is_npt is True


class TestTimeLogValidationUnchanged:
    """Test: Existing 24h Time Log validation remains unchanged."""

    def test_time_log_validator_still_works(self):
        from core.import_quality import TimeLogValidator
        logs = [
            {"time_from": "00:00", "time_to": "06:00", "duration": 6, "main_code": "2"},
            {"time_from": "06:00", "time_to": "12:00", "duration": 6, "main_code": "2"},
            {"time_from": "12:00", "time_to": "18:00", "duration": 6, "main_code": "6"},
            {"time_from": "18:00", "time_to": "24:00", "duration": 6, "main_code": "2"},
        ]
        report = TimeLogValidator.validate_logs(logs, sheet="Test")
        assert report.total == 4
        # Should not crash, should produce valid report
        assert report is not None
