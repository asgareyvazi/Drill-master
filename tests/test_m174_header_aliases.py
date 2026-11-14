"""M174: profile-driven description-header aliases for MinerU/native-PDF time logs; ambiguity -> operator."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import ddr_import_pipeline as pipe
from core.ddr_header_aliases import (
    DEFAULT_DESCRIPTION_HEADERS, RULE_KEY, normalize_header, resolve_description_headers, time_log_section,
)
from core.ddr_report_profiles import ReportProfile, map_headers, profile_from_dict, validate_profile
from core.mineru_engine import PROFILE_RULES_VERSION, DocumentTable, MinerUDocument, Provenance

ROWS = [["00:00", "06:00", "6", "Drill ahead"], ["06:00", "08:00", "2", "POOH"]]


def _profile(rules=None, aliases=None, version=3):
    return ReportProfile(key="syn-m174", version=version, name="Synthetic", report_format="pdf",
                         aliases=aliases or {}, units={}, date_formats=(), table_rules=rules or {})


def _extract(headers, rows, profile=None, name="24 hrs time log"):
    document = MinerUDocument(source_file="synthetic.pdf", backend="pdf-native-fallback", method="pymupdf", tables=[
        DocumentTable(headers=headers, rows=rows, name=name,
                      provenance=Provenance("synthetic.pdf", source_page=4, bounding_box=[10.0, 20.0, 300.0, 400.0]))])
    parsed = SimpleNamespace(document=document, success=True, diagnostics={}, error=None)
    return pipe.mineru_extracted("synthetic.pdf", parsed, profile=profile)


def _descriptions(extracted, key="time_logs_24h"):
    return [row.get("activity_description") for row in extracted.get(key, [])]


@pytest.mark.parametrize("header", ["Activity", "DESCRIPTION", " operation ", "Details:", "Operations",
                                    "شرح عملیات", "شرح عمليات", "توضیحات", "فعالیت"])
def test_each_listed_english_and_persian_header_maps_in_a_time_log(header):
    extracted = _extract(["From", "To", "Hrs", header], ROWS)
    assert _descriptions(extracted) == ["Drill ahead", "POOH"]
    [outcome] = extracted["metadata"]["header_aliases"]
    assert outcome["state"] == "MAPPED" and outcome["header"] == header and outcome["column"] == 4
    assert outcome["source"]["source_page"] == 4 and outcome["source"]["bounding_box"] == [10.0, 20.0, 300.0, 400.0]
    assert outcome["method"] == "default description header" and outcome["rules_version"] == 1
    cells = extracted["time_logs_24h"][0]["_source_cells"]["time_log.activity_description"]
    assert cells == {"page": 4, "row": 1, "column": 4}
    assert extracted["metadata"]["profile_rules_version"] == PROFILE_RULES_VERSION == 2


@pytest.mark.parametrize("header", ["Activity Code", "Operation Hours", "Descr", "Detail", "Activty", "Remarks",
                                    "Description 2", "شرح کد"])
def test_no_fuzzy_partial_or_misspelled_match(header):
    extracted = _extract(["From", "To", "Hrs", header], ROWS)
    assert _descriptions(extracted) == [None, None]
    assert extracted["metadata"]["header_aliases"] == []
    assert any(header in w["message"] for w in extracted["metadata"]["warnings"])


def test_generic_words_outside_a_time_log_are_not_mapped():
    # A mud/BHA table with "Description" has no from/to anchor; nothing is guessed.
    fields, outcome = resolve_description_headers(["Item", "Description", "OD"], [None, None, None])
    assert fields == [None, None, None] and outcome["state"] == "NOT_TIME_LOG"
    # Only "From" without "To" is no anchor either; mixed 24h/morning anchors are refused too.
    assert time_log_section(["time_log.time_from", None]) is None
    assert time_log_section(["time_log.time_from", "time_log.time_to",
                             "time_log_morning.time_from", "time_log_morning.time_to"]) is None


def test_two_candidates_are_ambiguous_and_require_an_operator_decision():
    rows = [r + ["full returns"] for r in ROWS]
    extracted = _extract(["From", "To", "Hrs", "Activity", "Details"], rows)
    assert _descriptions(extracted) == [None, None]
    [outcome] = extracted["metadata"]["header_aliases"]
    assert outcome["state"] == "AMBIGUOUS" and [c["header"] for c in outcome["candidates"]] == ["Activity", "Details"]
    review = [r for r in extracted["metadata"]["review_matrix"] if "Operator decision required" in r["reason"]]
    assert {r["original_value"] for r in review} == {"Activity", "Details"}
    assert {r["column"] for r in review} == {4, 5} and all(r["page"] == 4 for r in review)
    # Original cells stay in the raw source payload under their own header.
    assert extracted["time_logs_24h"][0]["_source_cells"]["Details"]["column"] == 5
    # The operator decides with an explicit profile alias; the other header stays unmapped.
    decided = _extract(["From", "To", "Hrs", "Activity", "Details"], rows,
                       profile=_profile(aliases={"Details": "time_log.activity_description"}))
    assert _descriptions(decided) == ["full returns", "full returns"]
    assert decided["metadata"]["header_aliases"] == []          # rule not needed: explicit mapping wins
    assert decided["metadata"]["profile"]["mappings"][-1]["label"] == "Details"


def test_explicit_mapping_already_present_is_not_overridden():
    extracted = _extract(["From", "To", "Hrs", "Rig Activity", "Details"], [r + ["x"] for r in ROWS])
    assert _descriptions(extracted) == ["Drill ahead", "POOH"] and extracted["metadata"]["header_aliases"] == []


def test_profile_override_replaces_or_disables_the_list_and_is_recorded():
    custom = _profile({RULE_KEY: ["Ops Narrative"]})
    extracted = _extract(["From", "To", "Hrs", "Ops Narrative"], ROWS, profile=custom)
    assert _descriptions(extracted) == ["Drill ahead", "POOH"]
    [outcome] = extracted["metadata"]["header_aliases"]
    assert outcome["method"] == "profile syn-m174 v3 description header"
    assert outcome["label_source"] == "profile syn-m174 v3"
    mapping = extracted["metadata"]["profile"]["mappings"][-1]
    assert mapping["label"] == "Ops Narrative" and mapping["column"] == 4 and mapping["rules_version"] == 2
    assert _descriptions(_extract(["From", "To", "Hrs", "Activity"], ROWS, profile=custom)) == [None, None]
    assert _descriptions(_extract(["From", "To", "Hrs", "Activity"], ROWS, profile=_profile({RULE_KEY: []}))) == \
        [None, None]


def test_morning_time_log_maps_to_the_morning_section():
    fields, outcome = resolve_description_headers(
        ["From", "To", "Operation"], ["time_log_morning.time_from", "time_log_morning.time_to", None])
    assert fields[2] == "time_log_morning.activity_description" and outcome["state"] == "MAPPED"


def test_profile_validation_and_old_profile_versions_stay_readable():
    assert validate_profile(_profile({RULE_KEY: ["Activity", "شرح"]})) == []
    assert validate_profile(_profile({RULE_KEY: "Activity"}))
    assert any("twice" in e for e in validate_profile(_profile({RULE_KEY: ["Activity", " activity "]})))
    assert any("empty" in e for e in validate_profile(_profile({RULE_KEY: ["  "]})))
    # A v1-era profile payload (no description_headers key) loads and uses the built-in list.
    old = profile_from_dict({"key": "old", "version": 1, "name": "Old",
                             "payload": {"aliases": {}, "table_rules": {"stop_markers": ["Total"]}}})
    assert RULE_KEY not in old.table_rules and validate_profile(old) == []
    assert _descriptions(_extract(["From", "To", "Hrs", "Activity"], ROWS, profile=old)) == ["Drill ahead", "POOH"]


def test_header_preview_uses_the_same_rule():
    rows = map_headers(None, ["From", "To", "Activity"])
    assert rows[2]["field"] == "time_log.activity_description" and rows[2]["method"] == "default description header"
    rows = map_headers(None, ["From", "To", "Activity", "Details"])
    assert rows[2]["field"] == "" and "operator decision" in rows[3]["method"]


def test_normalisation_is_exact_not_fuzzy():
    assert normalize_header("  Operation  Details: ") == "operation details"
    assert normalize_header("شرح\u200cعملیات") == normalize_header("شرح عملیات")
    assert normalize_header("Activities") != normalize_header("Activity")
    assert len({normalize_header(h) for h in DEFAULT_DESCRIPTION_HEADERS}) == len(DEFAULT_DESCRIPTION_HEADERS)


def test_profile_dialog_round_trips_the_override(tmp_path):
    from PySide6.QtWidgets import QApplication
    from dialogs.ddr_profile_dialog import ReportProfileDialog
    from core.database import DatabaseManager

    QApplication.instance() or QApplication([])
    db = DatabaseManager()
    db.db_path = str(tmp_path / "m174.db")
    assert db.initialize()
    dialog = ReportProfileDialog(db)
    dialog.load_profile(_profile({RULE_KEY: ["Ops Narrative", "شرح"]}))
    assert dialog.description_override_check.isChecked() and dialog.description_headers_edit.isEnabled()
    assert dialog.collect_profile().table_rules[RULE_KEY] == ["Ops Narrative", "شرح"]
    dialog.load_profile(_profile({}))
    assert not dialog.description_headers_edit.isEnabled() and RULE_KEY not in dialog.collect_profile().table_rules
    dialog.description_override_check.setChecked(True)
    assert dialog.collect_profile().table_rules[RULE_KEY] == []      # explicit: rule off
    dialog.deleteLater()
    db.close()
