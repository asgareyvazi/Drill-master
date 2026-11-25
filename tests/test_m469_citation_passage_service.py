"""M469-M471 (U2): open a ``.citations.json`` passage from the Documents tab, through the secure passage service.

Uses the SYNTHETIC M50 corpus and the real Documents tab (offscreen Qt). The tests cover:
* EXACT passages open with the quote highlighted;
* a changed page opens without a highlight;
* hostile or malformed files are refused as a whole, and the previous passages are cleared;
* malformed entries are UNREADABLE and never opened;
* a record from another library (same id, other file) is IDENTITY_MISMATCH;
* record text is never rendered as rich text.
"""
from __future__ import annotations

import json
import os

import pytest

from core import citation_passage as cp
from core import citation_record as cr
from test_m50_citation_navigation import QUESTION, _ask, _edit_page, _selected, app, world  # noqa: F401

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "docs", "engineering", "schemas",
                      "citation_record_v1.schema.json")


def _record_file(tmp_path, app, panel, name="answer.citations.json"):  # noqa: F811
    _ask(app, panel, QUESTION)
    path = str(tmp_path / name)
    assert panel.export_citations(path)
    return path


def _write(tmp_path, name, payload) -> str:
    path = tmp_path / name
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------------------------------- Documents tab UI
def test_library_page_opens_an_exact_passage_from_a_record_file(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, _db = world
    path = _record_file(tmp_path, app, panel)
    tab.sections.setCurrentIndex(1)                           # the user is on the assistant; the record is opened
    assert tab.citation_file_navigation.isHidden()            # from the library page
    results = tab.open_citation_file(path)
    assert results and all(r["status"] == cr.EXACT for r in results)
    assert not tab.citation_file_navigation.isHidden()
    assert tab.citation_file_combo.count() == len(results)
    assert tab.open_citation_passage_button.isEnabled()
    assert "ALL EXACT" in tab.citation_file_status.text() and "Not semantically verified" in \
        tab.citation_file_status.text()
    tab.open_citation_passage_button.click()
    first = cr.load(path)["citations"][0]
    assert tab.sections.currentIndex() == 0
    assert _selected(tab) == [first["quote"]]
    assert tab.cited_span == (first["document_id"], first["page_no"], first["start"], first["end"])


def test_library_page_changed_page_opens_without_highlight(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, db = world
    path = _record_file(tmp_path, app, panel)
    first = cr.load(path)["citations"][0]
    _edit_page(db, first["page_id"], lambda text: "SYN inserted. " + text)
    results = tab.open_citation_file(path)
    assert results[0]["status"] == cr.PAGE_CHANGED and tab.open_citation_passage_button.isEnabled()
    tab.open_citation_target(0)
    assert tab.cited_span is None and _selected(tab) == []
    assert "has changed" in tab.viewer_title.text()


def test_refused_file_clears_previous_passages_and_nothing_opens(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, _db = world
    path = _record_file(tmp_path, app, panel)
    tab.open_citation_file(path)
    assert tab.citation_file_targets
    bad = _write(tmp_path, "dup.citations.json", '{"record_version": "x", "record_version": "y"}')
    assert tab.open_citation_file(bad) is None
    assert tab.citation_file_targets == [] and tab.citation_file_navigation.isHidden()
    assert "repeats the key 'record_version'" in tab.citation_file_status.text()
    assert tab.open_citation_target(0) is False


def test_untrusted_record_text_is_plain_text_and_unopenable_entries_say_why(tmp_path, app, world):  # noqa: F811
    from PySide6.QtCore import Qt
    tab, panel, _ids, _db = world
    record = cr.load(_record_file(tmp_path, app, panel))
    record["citations"][0]["label"] = "<img src=x>"
    path = _write(tmp_path, "html.citations.json", record)
    results = tab.open_citation_file(path)
    assert results[0]["status"] == cr.UNREADABLE and "label" in results[0]["reason"]
    assert tab.citation_file_status.textFormat() == Qt.PlainText
    assert panel.citation_status.textFormat() == Qt.PlainText
    tab.citation_file_combo.setCurrentIndex(0)
    assert not tab.open_citation_passage_button.isEnabled()
    assert "Not openable" in tab.open_citation_passage_button.toolTip()
    assert tab.open_citation_target(0) is False and "not opened – UNREADABLE" in tab.citation_file_status.text()


def test_record_from_another_library_is_an_identity_mismatch(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, _db = world
    record = cr.load(_record_file(tmp_path, app, panel))
    record["citations"][0]["file_name"] = "SYN other library.pdf"
    path = _write(tmp_path, "foreign.citations.json", record)
    results = tab.open_citation_file(path)
    assert results[0]["status"] == cp.IDENTITY_MISMATCH and "a different document with the same id" in \
        results[0]["reason"]
    assert tab.open_citation_target(0) is False and getattr(tab, "cited_span", None) is None


def test_assistant_verify_uses_the_same_service(tmp_path, app, world):  # noqa: F811
    _tab, panel, _ids, _db = world
    record = cr.load(_record_file(tmp_path, app, panel))
    record["citations"][0]["start"] = True                   # a boolean is not an offset
    path = _write(tmp_path, "bool.citations.json", record)
    results = panel.verify_citation_file(path)
    assert results[0]["status"] == cr.UNREADABLE and "start is not a non-negative integer" in results[0]["reason"]
    assert panel.open_record_citation(0) is False


# ------------------------------------------------------------------------------------------- service (no Qt UI)
@pytest.mark.parametrize("payload, reason", [
    ("{\"record_version\": \"M320-E citation record v1\", \"citations\": [NaN]}", "NaN"),
    ("[" * 100000 + "]" * 100000, "nested too deeply"),
    ("{\"record_version\": \"M320-E citation record v1\"}", "no citations list"),
    ("{\"record_version\": \"M320-E citation record v1\", \"citations\": []}", "no citations list"),
    ("{\"record_version\": \"other\", \"citations\": [{}]}", "not a DrillMaster citation record"),
    ("{\"record_version\": \"M320-E citation record v1\", \"citations\": [{}], \"answer\": 5}", "'answer' is not text"),
    ("not json", "not valid JSON"),
])
def test_hostile_files_are_refused_as_a_whole(tmp_path, payload, reason):
    path = _write(tmp_path, "x.json", payload)
    with pytest.raises(cp.PassageError, match=reason):
        cp.read_record(path)


def test_size_type_and_encoding_limits(tmp_path, monkeypatch):
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (cp.MAX_FILE_BYTES + 1))
    with pytest.raises(cp.PassageError, match="byte limit"):
        cp.read_record(str(big))
    with pytest.raises(cp.PassageError, match="not a regular file"):
        cp.read_record(str(tmp_path))
    latin = tmp_path / "latin.json"
    latin.write_bytes("{\"q\": \"\xe9\"}".encode("latin-1"))
    with pytest.raises(cp.PassageError, match="not UTF-8"):
        cp.read_record(str(latin))
    with pytest.raises(cp.PassageError, match="cannot be read"):
        cp.read_record(str(tmp_path / "missing.json"))
    many = {"record_version": cr.RECORD_VERSION, "citations": [{}] * (cp.MAX_CITATIONS + 1)}
    with pytest.raises(cp.PassageError, match="more than"):
        cp.validate_record(many)


def _entry(**changes):
    entry = {"label": "S1", "document_id": 1, "page_id": 2, "page_no": 1, "start": 0, "end": 4,
             "text_version": "a" * 64, "quote": "SYN.", "file_name": "syn.txt"}
    entry.update(changes)
    return entry


@pytest.mark.parametrize("changes, reason", [
    ({"document_id": "1"}, "document_id is not a non-negative integer"),
    ({"page_no": -1}, "page_no is not a non-negative integer"),
    ({"end": 2 ** 40}, "end is not a non-negative integer"),
    ({"start": 1.0}, "start is not a non-negative integer"),
    ({"start": 4, "end": 4}, "start is not before end"),
    ({"end": cp.MAX_QUOTE_CHARS + 1}, "span is longer"),
    ({"text_version": "A" * 64}, "SHA-256"),
    ({"text_version": "a" * 63}, "SHA-256"),
    ({"label": "x" * 40}, "label"),
    ({"label": ""}, "label is not a short plain token"),
    ({"label": None}, "missing label"),
    ({"quote": 7}, "quote is not text"),
    ({"file_name": "a\nb"}, "single-line"),
    ({"file_name": "x" * 261}, "single-line"),
])
def test_citation_entry_schema(changes, reason):
    assert reason in (cp.citation_problem(_entry(**changes)) or "<valid>")


def test_valid_entry_and_unicode_file_name_pass():
    assert cp.citation_problem(_entry()) == ""
    assert cp.citation_problem(_entry(file_name="گزارش روزانه.pdf", label="S12")) == ""
    assert cp.citation_problem("x") == "the entry is not an object"


def test_published_schema_matches_the_service_limits():
    with open(SCHEMA, encoding="utf-8") as handle:
        schema = json.load(handle)
    assert schema["properties"]["record_version"]["const"] == cr.RECORD_VERSION
    citations = schema["properties"]["citations"]
    assert citations["minItems"] == 1 and citations["maxItems"] == cp.MAX_CITATIONS
    item = citations["items"]
    assert sorted(item["required"]) == sorted(cr.REQUIRED)
    for key in cp.INT_FIELDS:
        assert item["properties"][key] == {"type": "integer", "minimum": 0, "maximum": cp.MAX_ID}, key
    assert item["properties"]["text_version"]["pattern"] == "^" + cp.SHA_PATTERN.pattern + "$"
    assert item["properties"]["label"]["pattern"] == "^" + cp.LABEL_PATTERN.pattern + "$"
    assert item["properties"]["quote"]["maxLength"] == cp.MAX_QUOTE_CHARS
    assert schema["x-drillmaster"]["max_file_bytes"] == cp.MAX_FILE_BYTES
