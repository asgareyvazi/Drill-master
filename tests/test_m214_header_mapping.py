"""M214: header-mapping re-audit - no broad fuzzy matching anywhere a header or label becomes a fact.

* Smart-template tables (``core.table_record_mapper``, D66): a header maps to ONE field, by the same name or by
  whole words; "Total Depth" is not "To"; "Code" is not four code fields; ties are left to the operator.
* Scalar labels (``core.excel_intelligence``): a fuzzy-label or purely spatial candidate is a review proposal,
  never an accepted value, whatever its score.
* The DDR table-header path (``canonical_mapper`` / ``semantic_tables``) and the time-log description rule (M174)
  were already exact; they are re-checked here.
"""
from __future__ import annotations

import pytest

from core import excel_intelligence as ei
from core import table_record_mapper as trm


def _map(record_type, headers):
    cells = {(1, i + 1): h for i, h in enumerate(headers)}
    cells.update({(2, i + 1): f"col{i + 1}" for i in range(len(headers))})
    region = {"sheet": "S", "min_row": 1, "max_row": 2, "min_col": 1, "headers": list(headers),
              "columns": [{"column": i + 1} for i in range(len(headers))]}
    records = trm.map_table(cells, region, record_type)
    fields = {k: v for k, v in (records[0] if records else {}).items()
              if k not in ("source_sheet", "source_row", "record_type", "source_cell")}
    return fields, region["ambiguous_headers"]


@pytest.mark.parametrize("record_type, headers, expected", [
    # every case below mapped one column to several fields before the fix (evidence file d66_*)
    ("time_log", ["From", "To", "Hrs", "Code", "Activity Description"],
     {"time_from": "col1", "time_to": "col2", "duration": "col3", "main_code": "col4",
      "activity_description": "col5"}),
    ("time_log", ["Activity Code", "Depth"], {"main_code": "col1"}),
    ("time_log", ["Total Depth"], {}),
    ("survey", ["MD (m)", "Inc (deg)", "Azimuth", "TVD (m)", "DLS (deg/30m)"],
     {"md": "col1", "inc": "col2", "azi": "col3", "tvd": "col4", "dls": "col5"}),
    ("bha", ["Component", "OD (in)", "ID (in)", "Length (m)", "Weight", "S/N"],
     {"component_name": "col1", "od": "col2", "id": "col3", "length": "col4", "weight": "col5", "serial": "col6"}),
])
def test_one_header_maps_to_at_most_one_field(record_type, headers, expected):
    fields, ambiguous = _map(record_type, headers)
    assert fields == expected and ambiguous == []
    assert len(set(fields.values())) == len(fields)


def test_an_equally_good_match_for_two_fields_is_left_to_the_operator():
    fields, ambiguous = _map("bit", ["Bit Size Code", "Bit No"])
    assert fields == {"bit_no": "col2"}
    assert ambiguous == [{"header": "Bit Size Code", "index": 0, "fields": ["bit_size", "iadc_code"]}]


def test_scores_are_exact_or_whole_word_never_partial():
    assert trm._score("MD (m)", "md") == trm.EXACT
    assert trm._score("Activity Description", "description") == trm.PHRASE
    assert trm._score("Total Depth", "to") == 0                  # inside a word
    assert trm._score("Depth", "h") == 0                         # a 1-letter alias is exact-only
    assert trm._score("To", "attributed to") == 0                # never "header inside the alias"
    assert trm._score("Hrs", "hrs") == trm.EXACT and trm._score("", "x") == 0


def _extractor(cells_by_ref):
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    for ref, value in cells_by_ref.items():
        sheet[ref] = value
    cells = {(c.row, c.column): c.value for row in sheet.iter_rows() for c in row if c.value is not None}
    return ei.FieldExtractor(cells, ei.MergeCellAnalyzer(sheet), ei.LabelDetector(cells))


def test_a_fuzzy_label_value_is_never_accepted_even_if_the_score_policy_would(monkeypatch):
    extractor = _extractor({"D4": "Mud Weigth", "E4": 10.5})          # misspelt label: fuzzy only
    result = extractor.extract({"field": "mud weight", "row": 20, "col": 20}, "mud_report.mw", sheet="S")
    assert (result.source, result.status, result.certainty) == ("fuzzy_match", "REVIEW_REQUIRED", "LOW")
    monkeypatch.setattr(ei, "confidence_decision", lambda confidence, critical=False: "ACCEPT")
    forced = extractor.extract({"field": "mud weight", "row": 20, "col": 20}, "mud_report.mw", sheet="S")
    assert forced.status == "REVIEW_REQUIRED"
    assert ei.NEVER_ACCEPTED_SOURCES == {"fuzzy_match", "spatial"}
    anchored = extractor.extract({"field": "mud weight", "row": 4, "col": 5}, "mud_report.mw", sheet="S")
    assert anchored.source == "preferred_cell" and anchored.status == "OK"   # a template anchor is unchanged


def test_the_ddr_header_path_is_exact():
    from core.canonical_mapper import resolve_canonical_field
    from core.ddr_header_aliases import resolve_description_headers
    assert resolve_canonical_field("Mud Weigth") is None
    assert resolve_canonical_field("mud weight") == "mud_report.mw"
    fields, outcome = resolve_description_headers(["Activity Code", "Operation Hours"], [None, None])
    assert outcome["state"] != "MAPPED"
