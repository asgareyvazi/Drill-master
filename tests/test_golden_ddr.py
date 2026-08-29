"""Golden regression test for real DDR workbook.

Uses actual expected values from: 08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx

This test verifies that the import engine extracts CORRECT values,
not just non-null values.
"""

import pytest
import json
from pathlib import Path

DDR_PATH = Path(__file__).parent.parent / "08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx"
DDR_AVAILABLE = DDR_PATH.exists()


@pytest.fixture(scope="module")
def ddr_report():
    if not DDR_AVAILABLE:
        pytest.skip("Real DDR not in repo")
    import openpyxl
    from core.excel_intelligence import ExcelIntelligence

    wb = openpyxl.load_workbook(str(DDR_PATH), data_only=True)
    tmpl_path = Path(__file__).parent.parent / "templates" / "OEOC_DDR_v3.json"
    template = {}
    if tmpl_path.exists():
        with open(tmpl_path) as f:
            template = json.load(f)
    ei = ExcelIntelligence(wb, template)
    report = ei.extract()
    wb.close()
    return report


def _get(report, section, key):
    return report.canonical_json.get(section, {}).get(key)


# ==================== GOLDEN VALUES — EXACT MATCHES ====================

@pytest.mark.skipif(not DDR_AVAILABLE, reason="DDR not in repo")
class TestGoldenValues:
    """Verify EXACT expected values from the real DDR workbook."""

    def test_well_name(self, ddr_report):
        assert _get(ddr_report, "well_info", "name") == "AZNS-207"

    def test_rig_name(self, ddr_report):
        assert _get(ddr_report, "well_info", "rig_name") == "OEOC 208"

    def test_client(self, ddr_report):
        """PPL — not '225' (depth value from adjacent row)."""
        assert _get(ddr_report, "well_info", "client") == "PPL"

    def test_operator(self, ddr_report):
        """MSA — not '310' (depth value from adjacent row)."""
        assert _get(ddr_report, "well_info", "operator") == "MSA"

    def test_field_name(self, ddr_report):
        """AZNS — not '3.95' (GLE-MSL from adjacent row)."""
        assert _get(ddr_report, "well_info", "field_name") == "AZNS"

    def test_section_name(self, ddr_report):
        assert _get(ddr_report, "well_info", "section_name") == '17-1/2"'

    def test_target_depth(self, ddr_report):
        assert float(str(_get(ddr_report, "well_info", "target_depth"))) == 4180

    def test_gle_msl(self, ddr_report):
        assert float(str(_get(ddr_report, "well_info", "gle_msl"))) == pytest.approx(3.95, abs=0.01)

    def test_rte_msl(self, ddr_report):
        assert float(str(_get(ddr_report, "well_info", "rte_msl"))) == pytest.approx(14.45, abs=0.01)

    def test_gle_rte(self, ddr_report):
        assert float(str(_get(ddr_report, "well_info", "gle_rte"))) == pytest.approx(10.5, abs=0.01)

    def test_depth_0000(self, ddr_report):
        assert float(str(_get(ddr_report, "daily_report", "depth_0000"))) == 155.0

    def test_depth_2400(self, ddr_report):
        assert float(str(_get(ddr_report, "daily_report", "depth_2400"))) == 225.0

    def test_depth_0600(self, ddr_report):
        assert float(str(_get(ddr_report, "daily_report", "depth_0600"))) == 310.0

    def test_drilled_24hrs(self, ddr_report):
        """70m — not 310 (MD@0600 from adjacent row)."""
        assert float(str(_get(ddr_report, "daily_report", "drilled_24hrs"))) == 70.0

    def test_avg_rop(self, ddr_report):
        assert float(str(_get(ddr_report, "daily_report", "avg_rop_remark"))) == pytest.approx(4.67, abs=0.1)

    def test_ph(self, ddr_report):
        assert float(str(_get(ddr_report, "mud_report", "ph"))) == 10.5

    def test_chloride(self, ddr_report):
        assert float(str(_get(ddr_report, "mud_report", "chloride"))) == 7400.0

    def test_days_without_lti(self, ddr_report):
        assert int(float(str(_get(ddr_report, "safety", "days_without_lti")))) == 468

    def test_pob_total(self, ddr_report):
        assert int(float(str(_get(ddr_report, "logistics", "pob_total")))) == 130

    def test_lta_day(self, ddr_report):
        assert int(float(str(_get(ddr_report, "daily_report", "lta_day")))) == 468

    def test_actual_rig_days(self, ddr_report):
        assert float(str(_get(ddr_report, "daily_report", "actual_rig_days"))) == pytest.approx(7.25, abs=0.01)


# ==================== WRONG MAPPING DETECTION ====================

@pytest.mark.skipif(not DDR_AVAILABLE, reason="DDR not in repo")
class TestWrongMappingDetection:
    """Verify that values are NOT swapped between fields."""

    def test_well_name_not_rig_name(self, ddr_report):
        well_name = str(_get(ddr_report, "well_info", "name") or "")
        assert "OEOC" not in well_name.upper() or "AZNS" in well_name.upper()

    def test_rig_name_not_well_name(self, ddr_report):
        rig = str(_get(ddr_report, "well_info", "rig_name") or "")
        assert "AZNS" not in rig.upper() or "OEOC" in rig.upper()

    def test_client_not_depth(self, ddr_report):
        """Client=PPL must NOT be a depth value like 225."""
        client = str(_get(ddr_report, "well_info", "client") or "")
        assert client != "225"
        assert client != "310"

    def test_operator_not_depth(self, ddr_report):
        """Operator=MSA must NOT be a depth value."""
        operator = str(_get(ddr_report, "well_info", "operator") or "")
        assert operator != "225"
        assert operator != "310"

    def test_mud_weight_not_label(self, ddr_report):
        """MW must be numeric, not a label like 'Mud Weight'."""
        mw = _get(ddr_report, "mud_report", "mw")
        if mw is not None:
            try:
                float(str(mw).replace(",", ""))
            except ValueError:
                pytest.fail(f"MW is not numeric: {mw}")


# ==================== INVALID ENGINEERING DATA ====================

@pytest.mark.skipif(not DDR_AVAILABLE, reason="DDR not in repo")
class TestInvalidEngineeringData:
    """Verify that invalid engineering values are rejected."""

    def test_negative_md_rejected(self):
        from core.excel_intelligence import FieldExtractor, LabelDetector
        cells = {(1, 1): -100}
        merge = type('M', (), {'get_value': lambda s, r, c: (None, False), 'is_merged': lambda s, r, c: False})()
        ext = FieldExtractor(cells, merge, LabelDetector(cells))
        result = ext.extract({"row": 1, "col": 1}, "survey.md")
        assert result.validation != "valid"

    def test_inc_over_180_rejected(self):
        from core.excel_intelligence import FieldExtractor, LabelDetector
        cells = {(1, 1): 200}
        merge = type('M', (), {'get_value': lambda s, r, c: (None, False), 'is_merged': lambda s, r, c: False})()
        ext = FieldExtractor(cells, merge, LabelDetector(cells))
        result = ext.extract({"row": 1, "col": 1}, "survey.inc")
        assert result.validation != "valid"

    def test_negative_mw_rejected(self):
        from core.excel_intelligence import FieldExtractor, LabelDetector
        cells = {(1, 1): -10}
        merge = type('M', (), {'get_value': lambda s, r, c: (None, False), 'is_merged': lambda s, r, c: False})()
        ext = FieldExtractor(cells, merge, LabelDetector(cells))
        result = ext.extract({"row": 1, "col": 1}, "mud_report.mw")
        assert result.validation != "valid"

    def test_azi_over_360_rejected(self):
        from core.excel_intelligence import FieldExtractor, LabelDetector
        cells = {(1, 1): 500}
        merge = type('M', (), {'get_value': lambda s, r, c: (None, False), 'is_merged': lambda s, r, c: False})()
        ext = FieldExtractor(cells, merge, LabelDetector(cells))
        result = ext.extract({"row": 1, "col": 1}, "survey.azi")
        assert result.validation != "valid"


# ==================== CANONICAL NAMESPACE ====================

class TestCanonicalNamespace:
    """Verify canonical paths are preserved."""

    def test_one_mapping_registry(self):
        from core.canonical_schema import lookup_alias, FIELD_SPECS
        assert lookup_alias("mud weight") == "mud_report.mw"
        assert lookup_alias("well name") == "well_info.name"
        assert lookup_alias("bit size") == "drilling_params.bit_size"
        assert lookup_alias("md") == "survey.md"
        assert lookup_alias("inclination") == "survey.inc"

    def test_no_independent_alias_dicts(self):
        from core.excel_intelligence import FieldExtractor
        aliases = FieldExtractor._get_aliases("mud_report.mw")
        assert "mud weight" in aliases or "mw" in aliases


# ==================== TIME LOG GOLDEN VALUES ====================

@pytest.mark.skipif(not DDR_AVAILABLE, reason="DDR not in repo")
class TestTimeLogGoldenValues:
    """Verify exact time log values from the real DDR."""

    def _get_logs(self, report):
        return report.canonical_json.get("time_logs_24h", [])

    def test_time_log_count(self, ddr_report):
        logs = self._get_logs(ddr_report)
        assert len(logs) >= 6

    def test_first_entry_time_from(self, ddr_report):
        logs = self._get_logs(ddr_report)
        assert len(logs) > 0
        first = logs[0]
        tf = first.get("time_from") or first.get("time_log.time_from")
        assert tf is not None
        assert str(tf) in ("00:00:00", "00:00", "datetime.time(0, 0)")

    def test_first_entry_main_code(self, ddr_report):
        logs = self._get_logs(ddr_report)
        assert len(logs) > 0
        first = logs[0]
        mc = first.get("main_code") or first.get("time_log.main_code")
        assert mc is not None
        assert str(mc).strip() in ("2", "2 - Drilling", "2.0")

    def test_first_entry_sub_code(self, ddr_report):
        logs = self._get_logs(ddr_report)
        assert len(logs) > 0
        first = logs[0]
        sc = first.get("sub_code") or first.get("time_log.sub_code")
        assert sc is not None
        assert str(sc).strip() in ("1", "1.0")

    def test_first_entry_duration(self, ddr_report):
        logs = self._get_logs(ddr_report)
        assert len(logs) > 0
        first = logs[0]
        dur = first.get("duration") or first.get("time_log.duration")
        assert dur is not None
        assert float(str(dur)) == pytest.approx(6.0, abs=0.1)

    def test_total_duration_24h(self, ddr_report):
        logs = self._get_logs(ddr_report)
        total = 0
        for log in logs:
            dur = log.get("duration") or log.get("time_log.duration")
            if dur is not None:
                total += float(str(dur))
        assert total == pytest.approx(24.0, abs=1.0)

    def test_source_code_preserved(self, ddr_report):
        logs = self._get_logs(ddr_report)
        for log in logs:
            mc = log.get("main_code") or log.get("time_log.main_code")
            if mc is not None:
                code_str = str(mc).strip()
                assert any(c.isdigit() for c in code_str), \
                    f"Original code lost: got '{code_str}'"

    def test_morning_not_duplicated(self, ddr_report):
        """Morning logs must NOT appear in 24H logs."""
        tl24 = ddr_report.canonical_json.get("time_logs_24h", [])
        tl_m = ddr_report.canonical_json.get("time_logs_morning", [])
        # They should be separate lists
        assert tl24 is not tl_m
        # Morning logs should have different content
        if tl_m:
            first_morning = str(tl_m[0])
            for log in tl24:
                if str(log) == first_morning:
                    pytest.fail("Morning log duplicated in 24H log")


# ==================== TABLE EXTRACTION ====================

@pytest.mark.skipif(not DDR_AVAILABLE, reason="DDR not in repo")
class TestTableExtraction:
    """Verify table extraction from real DDR."""

    def test_time_logs_24h(self, ddr_report):
        tl = ddr_report.canonical_json.get("time_logs_24h", [])
        assert len(tl) >= 6

    def test_time_logs_morning(self, ddr_report):
        tl = ddr_report.canonical_json.get("time_logs_morning", [])
        assert len(tl) >= 3

    def test_surveys(self, ddr_report):
        assert len(ddr_report.canonical_json.get("surveys", [])) >= 2

    def test_bulk_materials(self, ddr_report):
        assert len(ddr_report.canonical_json.get("bulk_materials", [])) >= 5

    def test_bha_components(self, ddr_report):
        assert len(ddr_report.canonical_json.get("bha_components", [])) >= 3

    def test_downhole_equipment(self, ddr_report):
        assert len(ddr_report.canonical_json.get("downhole_equipment", [])) >= 2

    def test_bop_components(self, ddr_report):
        assert len(ddr_report.canonical_json.get("bop_components", [])) >= 3

    def test_cement_additives(self, ddr_report):
        assert len(ddr_report.canonical_json.get("cement_additives", [])) >= 3

    def test_solid_control(self, ddr_report):
        assert len(ddr_report.canonical_json.get("solid_control", [])) >= 3

    def test_formation_data(self, ddr_report):
        assert len(ddr_report.canonical_json.get("formation_data", [])) >= 1

    def test_scr_data(self, ddr_report):
        assert len(ddr_report.canonical_json.get("scr_data", [])) >= 2

    def test_drilling_params_table(self, ddr_report):
        assert len(ddr_report.canonical_json.get("drilling_params_table", [])) >= 5


# ==================== ACTIVITY MAPPER ====================

@pytest.mark.skipif(not DDR_AVAILABLE, reason="DDR not in repo")
class TestActivityMapperIntegration:
    """Verify ActivityMapper resolves OEOC codes correctly."""

    def test_code_2_drilling(self):
        from core.activity_mapper import ActivityMapper
        mapper = ActivityMapper()
        result = mapper.map_activity("2", "Drilling 17-1/2\" HS")
        assert result.canonical_id == "DRILLING"
        assert result.source_code == "2"
        assert result.confidence >= 0.85

    def test_code_6_trips(self):
        from core.activity_mapper import ActivityMapper
        mapper = ActivityMapper()
        result = mapper.map_activity("6", "Trips")
        assert result.canonical_id in ("TRIPPING_IN", "TRIPPING_OUT")
        assert result.source_code == "6"

    def test_code_3_reaming(self):
        from core.activity_mapper import ActivityMapper
        mapper = ActivityMapper()
        result = mapper.map_activity("3", "Reaming")
        assert result.canonical_id == "REAMING"

    def test_unknown_code_unresolved(self):
        from core.activity_mapper import ActivityMapper
        mapper = ActivityMapper()
        result = mapper.map_activity("ZZZ", "Unknown activity")
        assert result.method == "unresolved"
        assert result.confidence == 0.0
