"""M546-M550 (U4): citation record v2 — document content SHA-256, page hash, passage id / offsets, verification
state; v1 stays readable; symbolic links and directory file names are refused; the Documents tab writes a v2 copy.

SYNTHETIC M50 corpus; real Documents tab (Linux offscreen Qt, not desktop acceptance).
"""
from __future__ import annotations

import json
import os

import pytest

from core import citation_passage as cp
from core import citation_record as cr
from core import citation_record_v2 as cr2
from test_m50_citation_navigation import QUESTION, _ask, _edit_page, _selected, app, world  # noqa: F401

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "docs", "engineering", "schemas",
                      "citation_record_v2.schema.json")


def _v1_file(tmp_path, app, panel, name="answer.citations.json"):  # noqa: F811
    _ask(app, panel, QUESTION)
    path = str(tmp_path / name)
    assert panel.export_citations(path)
    return path


def _v2(db, path):
    record = cp.read_record(path)
    return cr2.upgrade(db, record, cp.verify(db, record))


def _write(tmp_path, name, record) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(record), encoding="utf-8")
    return str(path)


def _library_hash(db, document_id):
    from core.database import Document

    with db.session_scope() as session:
        return session.get(Document, document_id).sha256


def test_upgrade_copies_the_library_content_hash_only_for_exact_citations(tmp_path, app, world):  # noqa: F811
    _tab, panel, _ids, db = world
    v2 = _v2(db, _v1_file(tmp_path, app, panel))
    assert v2["record_version"] == cr2.RECORD_VERSION and v2["upgraded_from"] == cr.RECORD_VERSION
    for c in v2["citations"]:
        assert c["document_sha256"] == _library_hash(db, c["document_id"])
        assert c["verification_state"] == cr2.VERIFIED_EXACT and c["state_reason"] == ""
        assert c["page_text_sha256"] == c["text_version"] and c["quote_sha256"] == cr2.sha256_text(c["quote"])
        assert c["passage_id"] == cr2.passage_id(c["document_sha256"], c["page_no"], c["start"], c["end"],
                                                 c["quote_sha256"])
        assert c["offset_unit"] == cr2.OFFSET_UNIT
    path = _write(tmp_path, "v2.citations.json", v2)
    _record, results, targets = cp.open_record(db, path)
    assert all(r["status"] == cr.EXACT for r in results) and all(t["openable"] for t in targets)
    assert all(r["verification_state"] == cr2.VERIFIED_EXACT for r in results)


def test_changed_page_at_upgrade_gives_no_hash_and_not_verified(tmp_path, app, world):  # noqa: F811
    _tab, panel, _ids, db = world
    path = _v1_file(tmp_path, app, panel)
    first = cr.load(path)["citations"][0]
    _edit_page(db, first["page_id"], lambda text: "SYN inserted. " + text)
    v2 = _v2(db, path)
    c = v2["citations"][0]
    assert c["document_sha256"] is None and c["verification_state"] == cr2.NOT_VERIFIED
    assert c["state_reason"].startswith(cr.PAGE_CHANGED)
    results = cp.verify(db, v2)
    assert results[0]["status"] == cr.PAGE_CHANGED and "content hash not recorded" in results[0]["reason"]


def test_library_file_content_changed_is_document_changed_and_not_openable(tmp_path, app, world):  # noqa: F811
    from core.database import Document

    _tab, panel, _ids, db = world
    v2 = _v2(db, _v1_file(tmp_path, app, panel))
    doc_id = v2["citations"][0]["document_id"]
    with db.session_scope() as session:
        session.get(Document, doc_id).sha256 = "e" * 64          # another file version stored under the same id
    _record, results, targets = cp.open_record(db, _write(tmp_path, "v2.citations.json", v2))
    changed = [r for r, c in zip(results, v2["citations"]) if c["document_id"] == doc_id]
    assert changed and all(r["status"] == cr2.DOCUMENT_CHANGED for r in changed)
    assert not any(t["openable"] for t, c in zip(targets, v2["citations"]) if c["document_id"] == doc_id)


@pytest.mark.parametrize("edit,needle", [
    (lambda c: c.update(start=c["start"] + 1, quote=c["quote"][1:], quote_sha256=cr2.sha256_text(c["quote"][1:])),
     "passage_id"),
    (lambda c: c.update(quote=c["quote"] + "x"), "quote_sha256"),
    (lambda c: c.update(document_sha256="0" * 64), "passage_id"),
    (lambda c: c.update(page_text_sha256="1" * 64), "page_text_sha256"),
    (lambda c: c.update(verification_state="TRUSTED"), "verification_state"),
    (lambda c: c.update(offset_unit="bytes"), "offset_unit"),
    (lambda c: c.update(document_sha256="ABC"), "document_sha256"),
    (lambda c: c.update(passage_id="zz"), "passage_id is not a SHA-256"),
    (lambda c: c.update(file_name="../../etc/SYN.txt"), "bare file name"),
    (lambda c: c.update(file_name="C:SYN.txt"), "bare file name"),
])
def test_edited_v2_citations_are_unreadable_and_never_opened(tmp_path, app, world, edit, needle):  # noqa: F811
    _tab, panel, _ids, db = world
    v2 = _v2(db, _v1_file(tmp_path, app, panel))
    edit(v2["citations"][0])
    results = cp.verify(db, v2)
    assert results[0]["status"] == cr.UNREADABLE and needle in results[0]["reason"]
    assert cr.navigation(v2, results)[0]["openable"] is False


def test_verified_state_without_a_hash_is_refused(tmp_path, app, world):  # noqa: F811
    _tab, panel, _ids, db = world
    v2 = _v2(db, _v1_file(tmp_path, app, panel))
    c = v2["citations"][0]
    c["document_sha256"] = None
    c["passage_id"] = cr2.passage_id(None, c["page_no"], c["start"], c["end"], c["quote_sha256"])
    assert cp.verify(db, v2)[0]["status"] == cr.UNREADABLE


def test_symbolic_links_are_refused_for_v1_and_v2(tmp_path, app, world):  # noqa: F811
    _tab, panel, _ids, db = world
    v1 = _v1_file(tmp_path, app, panel)
    v2 = _write(tmp_path, "v2.citations.json", _v2(db, v1))
    for target in (v1, v2):
        link = tmp_path / ("link-" + os.path.basename(target))
        link.symlink_to(target)
        with pytest.raises(cp.PassageError, match="symbolic link"):
            cp.read_record(str(link))
    with pytest.raises(cp.PassageError, match="not a regular file"):
        cp.read_record(str(tmp_path))


def test_v1_records_stay_readable_and_unchanged(tmp_path, app, world):  # noqa: F811
    _tab, panel, _ids, db = world
    path = _v1_file(tmp_path, app, panel)
    before = open(path, encoding="utf-8").read()
    record, results, _targets = cp.open_record(db, path)
    assert record["record_version"] == cr.RECORD_VERSION and all(r["status"] == cr.EXACT for r in results)
    assert "passage_id" not in results[0]                   # v1 results carry no v2 fields
    cr2.upgrade(db, record, results)
    assert open(path, encoding="utf-8").read() == before    # upgrading never rewrites the v1 file
    with pytest.raises(cr.CitationRecordError):
        cr2.upgrade(db, {**record, "record_version": cr2.RECORD_VERSION}, results)
    with pytest.raises(cr.CitationRecordError):
        cr2.upgrade(db, record, results[:-1] if len(results) > 1 else [])


def test_unreadable_v1_citations_are_not_carried_into_v2(tmp_path, app, world):  # noqa: F811
    _tab, panel, _ids, db = world
    record = cr.load(_v1_file(tmp_path, app, panel))
    record["citations"].append({**record["citations"][0], "label": "<bad>"})
    results = cp.verify(db, record)
    v2 = cr2.upgrade(db, record, results)
    assert len(v2["citations"]) == len(record["citations"]) - 1
    assert all(c["label"] != "<bad>" for c in v2["citations"])


def test_documents_tab_saves_a_v2_copy_and_opens_it(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, db = world
    path = _v1_file(tmp_path, app, panel)
    assert not tab.save_citation_v2_button.isEnabled()
    tab.open_citation_file(path)
    assert tab.save_citation_v2_button.isEnabled() and cr.RECORD_VERSION in tab.citation_file_status.text()
    out = tab.save_citation_file_v2(str(tmp_path / "saved-v2"))
    assert out.endswith(".citations.json") and "carry a verified document content hash" in \
        tab.citation_file_status.text()
    results = tab.open_citation_file(out)
    assert all(r["status"] == cr.EXACT for r in results)
    assert cr2.RECORD_VERSION in tab.citation_file_status.text() and not tab.save_citation_v2_button.isEnabled()
    tab.open_citation_passage_button.click()
    first = json.load(open(out, encoding="utf-8"))["citations"][0]
    assert _selected(tab) == [first["quote"]]


def test_refused_file_disables_the_v2_save(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, _db = world
    tab.open_citation_file(_v1_file(tmp_path, app, panel))
    bad = tmp_path / "bad.citations.json"
    bad.write_text("{}", encoding="utf-8")
    assert tab.open_citation_file(str(bad)) is None
    assert not tab.save_citation_v2_button.isEnabled() and tab.save_citation_file_v2(str(tmp_path / "x")) is None


def test_schema_v2_matches_the_code():
    schema = json.load(open(SCHEMA, encoding="utf-8"))
    assert schema["properties"]["record_version"]["const"] == cr2.RECORD_VERSION
    item = schema["properties"]["citations"]["items"]
    assert set(cr2.V2_FIELDS) <= set(item["required"]) and set(cr.REQUIRED) <= set(item["required"])
    assert item["properties"]["offset_unit"]["const"] == cr2.OFFSET_UNIT
    assert set(item["properties"]["verification_state"]["enum"]) == {cr2.VERIFIED_EXACT, cr2.NOT_VERIFIED}
    assert cr2.DOCUMENT_CHANGED in schema["x-drillmaster"]["statuses"]
    assert schema["x-drillmaster"]["max_file_bytes"] == cp.MAX_FILE_BYTES
