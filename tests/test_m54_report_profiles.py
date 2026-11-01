"""M54 versioned DDR report profiles: validation, immutable versions, mapping use, editor.

Temporary SQLite databases with synthetic data; editor tests use offscreen Qt
(not Windows desktop testing).
"""
from __future__ import annotations

from datetime import date

import pytest

from core.ddr_report_profiles import (
    ReportProfile,
    get_profile,
    list_latest_profiles,
    map_headers,
    profile_history,
    save_profile_version,
    validate_profile,
)
from core.mineru_engine import DocumentNormalizer, DocumentTable, MinerUDocument, Provenance


def _profile(**overrides):
    base = dict(key="syn-operator-pdf", version=0, name="Synthetic operator PDF", operator="SYN OPERATOR",
                report_format="pdf", aliases={"Fluid Density": "mud_report.mw", "Hole Depth": "daily_report.depth_2400"},
                units={"mud_report.mw": "ppg"}, date_formats=("%d/%m/%Y",),
                table_rules={"stop_markers": ["Total"]}, continuation=True, confidence_threshold=0.85)
    base.update(overrides)
    return ReportProfile(**base)


@pytest.fixture
def db():
    from synthetic_operations import make_file_database
    import tempfile
    from pathlib import Path
    directory = tempfile.mkdtemp(prefix="m54-profiles-")
    manager = make_file_database(Path(directory) / "profiles.db")
    yield manager
    manager.engine.dispose()


# ---- validation -----------------------------------------------------------------------------------
def test_a_well_formed_profile_validates():
    assert validate_profile(_profile()) == []


@pytest.mark.parametrize("overrides, message", [
    ({"key": " "}, "Profile key is required."),
    ({"name": ""}, "Profile name is required."),
    ({"report_format": "docx"}, "Report format must be one of pdf, xlsx, any."),
    ({"aliases": {"Fluid Density": "mud_report.not_a_field"}}, "targets unknown canonical field"),
    ({"aliases": {"": "mud_report.mw"}}, "empty source label"),
    ({"aliases": {"MW ": "mud_report.mw", "mw": "daily_report.depth_2400"}}, "mapped to two different fields"),
    ({"units": {"mud_report.mw": "furlongs"}}, "is not a known source unit"),
    ({"date_formats": ("dd/mm/yyyy",)}, "is not a valid strftime pattern"),
    ({"confidence_threshold": 1.5}, "between 0 and 1"),
    ({"table_rules": {"stop_markers": "Total"}}, "must be a list of text values"),
])
def test_invalid_profiles_are_rejected_with_a_clear_reason(overrides, message):
    errors = validate_profile(_profile(**overrides))
    assert any(message in error for error in errors), errors


# ---- immutable versions ------------------------------------------------------------------------------
def test_each_save_creates_a_new_version_and_keeps_the_old_one(db):
    first = save_profile_version(db, _profile(), note="initial")
    assert (first.key, first.version) == ("syn-operator-pdf", 1)
    second = save_profile_version(db, _profile(aliases={"Fluid Density": "mud_report.mw"}), note="drop depth alias")
    assert second.version == 2
    assert get_profile(db, "syn-operator-pdf", 1).aliases == _profile().aliases      # v1 unchanged
    assert get_profile(db, "syn-operator-pdf").version == 2                           # latest
    assert [(h["version"], h["note"], h["aliases"]) for h in profile_history(db, "syn-operator-pdf")] == [
        (1, "initial", 2), (2, "drop depth alias", 1)]
    assert [p.version for p in list_latest_profiles(db)] == [2]


def test_an_invalid_profile_writes_nothing(db):
    with pytest.raises(ValueError, match="unknown canonical field"):
        save_profile_version(db, _profile(aliases={"X": "nope.field"}))
    assert list_latest_profiles(db) == []


def test_profile_versions_are_insert_only_in_the_data_layer_policy():
    from core.authorization import IMPORT, NOBODY, TABLE_POLICY
    policy = TABLE_POLICY["ddr_report_profiles"]
    assert policy.required("insert") == (IMPORT,)
    assert policy.required("update") == (NOBODY,) and policy.required("delete") == (NOBODY,)


# ---- application -------------------------------------------------------------------------------------
def test_profile_resolution_dates_and_review_threshold():
    profile = _profile()
    assert profile.resolve("  fluid density: ") == "mud_report.mw"
    assert profile.resolve("Unknown") is None
    assert profile.parse_date("15/01/2026") == date(2026, 1, 15)
    assert profile.parse_date("2026-01-15") is None                    # not guessed
    assert profile.needs_review(0.84) and not profile.needs_review(0.9) and profile.needs_review(None)


def test_header_preview_names_the_rule_that_mapped_each_column():
    rows = map_headers(_profile(), ["Fluid Density", "Bit Number", "Mystery"])
    assert rows[0] == {"header": "Fluid Density", "field": "mud_report.mw",
                       "method": "profile syn-operator-pdf v0", "unit": "ppg"}
    assert rows[1]["field"] == "drilling_params.bit_no" and rows[1]["method"] == "canonical alias"
    assert rows[2] == {"header": "Mystery", "field": "", "method": "unmapped — review", "unit": ""}


def _document():
    return MinerUDocument(source_file="synthetic.pdf", backend="pdf-native-fallback", method="pymupdf", tables=[
        DocumentTable(headers=["Fluid Density"], rows=[["10.2"]],
                      provenance=Provenance("synthetic.pdf", source_page=1), name="mud report")])


def test_without_a_profile_the_unknown_column_stays_unmapped():
    normalized = DocumentNormalizer().normalize(_document())
    assert normalized.canonical_data.get("mud_report", {}).get("mw") is None
    assert any("No unambiguous canonical field for table column 'Fluid Density'" in w.get("message", "")
               for w in normalized.warnings)


def test_a_profile_alias_and_declared_unit_map_and_convert_the_value():
    normalizer = DocumentNormalizer(profile=_profile(version=3))
    normalized = normalizer.normalize(_document())
    assert normalized.canonical_data["mud_report"]["mw"] == pytest.approx(10.2 / 0.133680556)
    assert normalizer.profile_mappings == [
        {"label": "Fluid Density", "field": "mud_report.mw", "profile": "syn-operator-pdf", "version": 3}]


def test_a_header_unit_wins_over_the_profile_unit():
    document = _document()
    document.tables[0].headers[0] = "Fluid Density (pcf)"
    normalizer = DocumentNormalizer(profile=_profile())
    normalized = normalizer.normalize(document)
    assert normalized.canonical_data["mud_report"]["mw"] == pytest.approx(10.2)


# ---- editor (offscreen Qt) --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_the_editor_saves_versions_previews_mapping_and_blocks_invalid_input(app, db):
    from core.permissions import permissions
    from dialogs.ddr_profile_dialog import ReportProfileDialog
    permissions.set_user({"id": 1, "username": "m54-synthetic", "role": "engineer"})   # conftest restores
    dialog = ReportProfileDialog(db)
    assert dialog.message_label.text() == "No report profiles yet. Create one with New profile."
    dialog.key_edit.setText("syn-ui")
    dialog.name_edit.setText("Synthetic UI profile")
    dialog.add_alias_row("Fluid Density", "mud_report.mw")
    dialog.add_unit_row("mud_report.mw", "ppg")
    dialog.add_alias_row("Bad", "not.a.field")
    assert dialog.save_version() is None
    assert "targets unknown canonical field 'not.a.field'" in dialog.message_label.text()
    dialog.alias_table.removeRow(1)
    stored = dialog.save_version()
    assert stored is not None and stored.version == 1 and stored.units == {"mud_report.mw": "ppg"}
    assert dialog.profile_list.count() == 1 and dialog.key_edit.isReadOnly()
    dialog.headers_edit.setText("Fluid Density | Mystery")
    rows = dialog.preview_mapping()
    assert [r["method"] for r in rows] == ["profile syn-ui v0", "unmapped — review"]
    dialog.note_edit.setText("second")
    assert dialog.save_version().version == 2
    assert "v1, v2 (second)" in dialog.history_label.text()
    dialog.deleteLater()


def test_a_viewer_cannot_save_a_profile(app, db):
    from core.permissions import permissions
    from dialogs.ddr_profile_dialog import ReportProfileDialog
    permissions.set_user({"id": 2, "username": "m54-viewer", "role": "viewer"})
    dialog = ReportProfileDialog(db)
    dialog.key_edit.setText("syn-view")
    dialog.name_edit.setText("Viewer attempt")
    assert dialog.save_version() is False
    assert dialog.message_label.text().startswith("Not saved:")
    assert list_latest_profiles(db) == []
    dialog.deleteLater()


def test_the_preview_field_detail_shows_full_provenance(app):
    from dialogs.excel_import_dialog import ImportPreviewDialog
    payload = {"sheet": "synthetic.pdf", "page": 2, "source_cell": "R3C1", "original_value": "10.2",
               "normalized_value": 76.3, "unit": "pcf", "target_field": "mud_report.mw", "confidence": 0.9,
               "review_reason": "Converted from ppg", "decision": "REVIEW"}
    text = ImportPreviewDialog.field_detail_text(
        payload, {"mappings": [{"field": "mud_report.mw", "profile": "syn", "version": 2, "label": "Fluid Density"}]})
    assert "Source: synthetic.pdf, page 2, cell R3C1" in text
    assert "Mapped by: report profile syn v2 (label 'Fluid Density')" in text
    assert "Confidence: 90%" in text and "Warning: Converted from ppg" in text and "Decision: REVIEW" in text
    assert ImportPreviewDialog.profile_summary(None) == "Report profile: none — canonical aliases only."
