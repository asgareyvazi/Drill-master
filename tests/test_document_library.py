"""M44: reviewable document extraction, atomic import, local search.

All files are generated here (SYNTHETIC text only).  OCR is exercised with a
fake engine object implementing ``recognize(image_bytes) -> (text, score)``;
the real RapidOCR adapter is optional and is tested only for graceful absence
(``rapidocr`` is not installed in the test environment).
"""
import json
import sqlite3

import fitz
import pytest

from core import document_library as dl
from core.document_library import (
    CANCELLED, CORRUPT, EMPTY, ENCRYPTED, FAILED, NEEDS_REVIEW, NO_TEXT, PARTIAL, READY, TOO_LARGE, UNSUPPORTED,
    DocumentLibrary, PageDecision, default_decisions, detect_kind, extract_batch, extract_document,
)
from core.permissions import permissions, session_user
from synthetic_operations import make_file_database
from test_scope_attribution import _mgr

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fe"
    "a7d6a4170000000049454e44ae426082")


class FakeOcr:
    def __init__(self, text="SYNTHETIC scanned casing report shoe depth 1250 m", score=0.95, fail=False):
        self.text, self.score, self.fail, self.calls = text, score, fail, []

    def recognize(self, image_bytes):
        self.calls.append(image_bytes[:8])
        if self.fail:
            raise RuntimeError("synthetic OCR failure")
        return self.text, self.score


def _pdf(path, pages):
    document = fitz.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.save(str(path))
    return path


@pytest.fixture
def files(tmp_path):
    return {
        "report": _pdf(tmp_path / "syn_report.pdf", [
            "SYNTHETIC casing tally: 9 5/8 in shoe set at 1250 m. Cement returns observed.",
            "",
            "SYNTHETIC mud weight increased to 1.25 sg after a gas peak."]),
        "text_only": _pdf(tmp_path / "syn_text.pdf", ["SYNTHETIC bit run summary: PDC bit pulled at 1800 m."]),
        "scanned": _pdf(tmp_path / "syn_scan.pdf", [""]),
    }


@pytest.fixture(autouse=True)
def _reset_ocr_state():
    dl._OCR_STATE.clear()
    yield
    dl._OCR_STATE.clear()


# ---------------------------------------------------------------- detection
@pytest.mark.parametrize("head, kind", [
    (b"%PDF-1.7\n...", "pdf"), (PNG_1PX, "png"), (b"\xff\xd8\xff\xe0JFIF", "jpeg"), (b"II*\x00rest", "tiff"),
    (b"MM\x00*rest", "tiff"), (b"BM" + b"\x00" * 20, "bmp"), (b"plain SYNTHETIC text\n", "text"),
    ("فشار پمپ".encode("utf-8"), "text"), (bytes(range(256)), "unknown"), (b"", "unknown"),
])
def test_detect_kind_uses_magic_bytes(head, kind):
    assert detect_kind(head) == kind


def test_decode_text_order():
    assert dl.decode_text("\ufeffSYN".encode("utf-8")) == ("SYN", "utf-8-sig")
    assert dl.decode_text("پمپ".encode("utf-8"))[1] == "utf-8-sig"          # BOM-less utf-8 also decodes
    text, encoding = dl.decode_text("گزارش مصنوعي".encode("cp1256"))
    assert encoding == "cp1256" and text == "گزارش مصنوعي"


# --------------------------------------------------------------- extraction
def test_text_pdf_with_blank_page_is_partial(files):
    x = extract_document(files["report"])
    assert x.kind == "pdf" and x.page_count == 3 and x.status == PARTIAL and x.importable
    assert [(p.page_no, p.status, p.location, p.method) for p in x.pages] == [
        (1, "ok", "page 1", "pdf-text"), (2, "no_text", "page 2", "pdf-text"), (3, "ok", "page 3", "pdf-text")]
    assert "No text layer" in x.pages[1].note and "OCR" in x.pages[1].note
    assert len(x.sha256) == 64 and x.size_bytes > 0
    assert extract_document(files["text_only"]).status == READY


def test_scanned_pdf_without_ocr_is_no_text_with_reason(files):
    x = extract_document(files["scanned"])
    assert x.status == NO_TEXT and not x.importable
    assert "OCR engine not installed" in x.pages[0].note


def test_scanned_pdf_with_ocr_needs_review(files):
    engine = FakeOcr()
    x = extract_document(files["scanned"], ocr_engine=engine)
    assert x.status == NEEDS_REVIEW and x.importable
    page = x.pages[0]
    assert page.method == "ocr" and page.status == "needs_review" and page.confidence == 0.95
    assert engine.calls == [b"\x89PNG\r\n\x1a\n"]                            # rendered page image
    assert default_decisions(x) == {1: PageDecision(approved=False)}          # never pre-approved


def test_ocr_empty_or_failing_page(files, tmp_path):
    assert extract_document(files["scanned"], ocr_engine=FakeOcr(text="  ")).status == NO_TEXT
    failed = extract_document(files["scanned"], ocr_engine=FakeOcr(fail=True))
    assert failed.pages[0].status == "error" and "RuntimeError" in failed.pages[0].note
    assert failed.status == NO_TEXT and not failed.importable


def test_image_with_and_without_ocr(tmp_path):
    image = tmp_path / "syn_photo.png"
    image.write_bytes(PNG_1PX)
    without = extract_document(image)
    assert without.kind == "png" and without.status == NO_TEXT and without.pages[0].location == "image"
    with_ocr = extract_document(image, ocr_engine=FakeOcr())
    assert with_ocr.status == NEEDS_REVIEW and with_ocr.pages[0].method == "ocr"


@pytest.mark.parametrize("content, status", [
    (b"%PDF-1.7\n this is not a real pdf \x00\x01", CORRUPT),
    (bytes(range(256)) * 4, UNSUPPORTED),
    (b"", EMPTY),
])
def test_bad_files_get_terminal_status_and_no_pages(tmp_path, content, status):
    path = tmp_path / "syn_bad.bin"
    path.write_bytes(content)
    x = extract_document(path)
    assert x.status == status and x.pages == [] and not x.importable and x.messages


def test_encrypted_missing_oversized_and_cancelled(tmp_path, files, monkeypatch):
    locked = tmp_path / "syn_locked.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "SYNTHETIC locked")
    document.save(str(locked), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    assert extract_document(locked).status == ENCRYPTED
    missing = extract_document(tmp_path / "does-not-exist.pdf")
    assert missing.status == FAILED and "FileNotFoundError" in missing.messages[0]
    monkeypatch.setattr(dl, "MAX_FILE_BYTES", 100)
    assert extract_document(files["report"]).status == TOO_LARGE
    monkeypatch.setattr(dl, "MAX_FILE_BYTES", 50 * 1024 * 1024)
    cancelled = extract_document(files["report"], cancel=lambda: True)
    assert cancelled.status == CANCELLED and cancelled.pages == [] and not cancelled.importable


def test_text_files_are_split_into_line_sections(tmp_path):
    path = tmp_path / "syn_log.txt"
    path.write_bytes("\n".join(f"SYNTHETIC line {n:03d} گزارش" for n in range(1, 201)).encode("cp1256"))
    x = extract_document(path)
    assert x.kind == "text" and x.encoding == "cp1256" and x.status == READY and x.page_count == 3
    assert [p.location for p in x.pages] == ["lines 1-80", "lines 81-160", "lines 161-200"]
    assert x.pages[2].text.startswith("SYNTHETIC line 161")


def test_batch_isolates_failures(tmp_path, files):
    bad = tmp_path / "syn_broken.pdf"
    bad.write_bytes(b"%PDF-1.4 broken")
    progress = []
    results = extract_batch([bad, files["text_only"], tmp_path / "missing.txt"],
                            progress=lambda done, total: progress.append((done, total)))
    assert [r.status for r in results] == [CORRUPT, READY, FAILED]
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert extract_batch([files["text_only"]], cancel=lambda: True) == []


def test_extraction_crash_inside_a_file_is_contained(files, monkeypatch):
    def explode(*_args, **_kwargs):
        raise MemoryError("synthetic")
    monkeypatch.setattr(dl, "_extract_pdf", explode)
    x = extract_document(files["report"])
    assert x.status == FAILED and x.pages == [] and "MemoryError" in x.messages[0]


# ------------------------------------------------------------------- import
def _rows(db, sql):
    session = db.create_session()
    try:
        from sqlalchemy import text
        return session.execute(text(sql)).fetchall()
    finally:
        session.close()


def test_import_stores_approved_pages_with_audit(files):
    db = _mgr()
    library = DocumentLibrary(db)
    outcome = library.import_reviewed(extract_document(files["report"]))
    assert outcome.status == "imported" and outcome.stored_pages == 2
    assert outcome.skipped_pages == [{"page": 2, "reason": "no_text"}]
    pages = library.pages(outcome.document_id)
    assert [(p["page_no"], p["location"], p["method"], p["review_status"]) for p in pages] == [
        (1, "page 1", "pdf-text", "extracted"), (3, "page 3", "pdf-text", "extracted")]
    (audit,) = _rows(db, "SELECT action, entity_type, entity_id, entity_name, details FROM audit_logs "
                         "WHERE action='document_import'")
    assert audit[1:4] == ("document", outcome.document_id, "syn_report.pdf")
    details = json.loads(audit[4])
    assert details["stored_pages"] == [1, 3] and details["skipped"] == [{"page": 2, "reason": "no_text"}]
    assert details["extraction_status"] == PARTIAL and details["source_pages"] == 3
    docs = library.list_documents()
    assert docs[0]["stored_pages"] == 2 and docs[0]["page_count"] == 3 and docs[0]["status"] == PARTIAL


def test_ocr_text_is_stored_only_after_explicit_approval(files):
    db = _mgr()
    library = DocumentLibrary(db)
    x = extract_document(files["scanned"], ocr_engine=FakeOcr())
    first = library.import_reviewed(x)                                        # default decisions
    assert first.status == "nothing_approved" and first.skipped_pages == [{"page": 1, "reason": "not approved"}]
    assert _rows(db, "SELECT COUNT(*) FROM documents")[0][0] == 0
    approved = library.import_reviewed(x, {1: PageDecision(approved=True)})
    assert approved.status == "imported"
    (page,) = library.pages(approved.document_id)
    assert page["review_status"] == "approved" and page["method"] == "ocr" and page["confidence"] == 0.95
    details = json.loads(_rows(db, "SELECT details FROM audit_logs WHERE action='document_import'")[0][0])
    assert details["ocr_pages_approved"] == [1]


def test_edited_and_emptied_pages(files):
    db = _mgr()
    library = DocumentLibrary(db)
    x = extract_document(files["report"])
    outcome = library.import_reviewed(x, {1: PageDecision(True, "SYNTHETIC corrected casing shoe at 1251 m"),
                                          3: PageDecision(True, "   ")})
    assert outcome.status == "imported" and outcome.stored_pages == 1
    assert {"page": 3, "reason": "empty after review"} in outcome.skipped_pages
    (page,) = library.pages(outcome.document_id)
    assert page["review_status"] == "edited" and "1251 m" in page["text"]
    details = json.loads(_rows(db, "SELECT details FROM audit_logs WHERE action='document_import'")[0][0])
    assert details["edited_pages"] == [1]


def test_duplicate_content_is_refused_even_under_another_name(files, tmp_path):
    db = _mgr()
    library = DocumentLibrary(db)
    assert library.import_reviewed(extract_document(files["text_only"])).status == "imported"
    copy = tmp_path / "renamed_copy.pdf"
    copy.write_bytes(files["text_only"].read_bytes())
    again = library.import_reviewed(extract_document(copy))
    assert again.status == "duplicate" and "syn_text.pdf" in again.message
    assert _rows(db, "SELECT COUNT(*) FROM documents")[0][0] == 1
    assert _rows(db, "SELECT COUNT(*) FROM audit_logs WHERE action='document_import'")[0][0] == 1


def test_not_importable_files_store_nothing(tmp_path):
    db = _mgr()
    bad = tmp_path / "syn_broken.pdf"
    bad.write_bytes(b"%PDF-1.4 broken")
    outcome = DocumentLibrary(db).import_reviewed(extract_document(bad))
    assert outcome.status == "not_importable" and "Not a readable PDF" in outcome.message
    assert _rows(db, "SELECT COUNT(*) FROM documents")[0][0] == 0


def test_failure_mid_import_rolls_back_document_pages_and_audit(files, monkeypatch):
    import core.database as database
    db = _mgr()
    library = DocumentLibrary(db)

    class BrokenAudit(database.AuditLog):
        __abstract__ = True

        def __init__(self, **_kwargs):
            raise RuntimeError("synthetic audit failure")
    monkeypatch.setattr(database, "AuditLog", BrokenAudit)
    outcome = library.import_reviewed(extract_document(files["report"]))
    assert outcome.status == "failed" and "rolled back" in outcome.message
    monkeypatch.undo()
    assert _rows(db, "SELECT COUNT(*) FROM documents")[0][0] == 0
    assert _rows(db, "SELECT COUNT(*) FROM document_pages")[0][0] == 0
    assert _rows(db, "SELECT COUNT(*) FROM audit_logs WHERE action='document_import'")[0][0] == 0
    assert library.import_reviewed(extract_document(files["report"])).status == "imported"   # retry works


def test_data_layer_enforces_import_permission(files, tmp_path):
    db = make_file_database(tmp_path / "auth.db")
    previous = permissions.user
    try:
        permissions.set_user(session_user(db.authenticate_user("viewer", "Synthetic-View-1!")))
        db.enforce_authorization(permissions)
        denied = DocumentLibrary(db).import_reviewed(extract_document(files["text_only"]))
        assert denied.status == "denied"
        assert _rows(db, "SELECT COUNT(*) FROM documents")[0][0] == 0
        permissions.set_user(session_user(db.authenticate_user("engineer", "Synthetic-Eng-1!")))
        allowed = DocumentLibrary(db).import_reviewed(extract_document(files["text_only"]))
        assert allowed.status == "imported"
        (row,) = _rows(db, "SELECT imported_by FROM documents")
        assert row[0] == "engineer"
        (audit,) = _rows(db, "SELECT username FROM audit_logs WHERE action='document_import'")
        assert audit[0] == "engineer"
    finally:
        permissions.set_user(previous)
        db.engine.dispose()


def test_delete_document_removes_pages_and_is_audited(files):
    db = _mgr()
    library = DocumentLibrary(db)
    outcome = library.import_reviewed(extract_document(files["report"]))
    assert library.delete_document(outcome.document_id) is True
    assert _rows(db, "SELECT COUNT(*) FROM document_pages")[0][0] == 0
    assert _rows(db, "SELECT COUNT(*) FROM audit_logs WHERE action='document_delete'")[0][0] == 1
    assert library.delete_document(outcome.document_id) is False


# ------------------------------------------------------------------- search
def _library_with_content(files, tmp_path):
    db = _mgr()
    library = DocumentLibrary(db)
    library.import_reviewed(extract_document(files["report"]))
    persian = tmp_path / "syn_fa.txt"
    persian.write_bytes("گزارش مصنوعي حفاري: فشار پمپ 2500 psi".encode("cp1256"))
    library.import_reviewed(extract_document(persian))
    scanned = extract_document(files["scanned"], ocr_engine=FakeOcr(text="SYNTHETIC unapproved ocr wording"))
    library.import_reviewed(scanned)                                     # not approved -> not stored
    return db, library


def test_fts_search_returns_file_page_and_snippet(files, tmp_path):
    _db, library = _library_with_content(files, tmp_path)
    result = library.search("casing shoe")
    assert result["status"] == "matched" and result["method"].startswith("SQLite FTS5")
    (hit,) = result["hits"]
    assert hit["file_name"] == "syn_report.pdf" and hit["page_no"] == 1 and hit["location"] == "page 1"
    assert "[casing]" in hit["snippet"] and "[shoe]" in hit["snippet"]
    assert library.search("cem")["hits"][0]["location"] == "page 1"           # prefix match
    assert library.search("mud weight")["hits"][0]["location"] == "page 3"
    fa = library.search("پمپ")["hits"]
    assert fa[0]["file_name"] == "syn_fa.txt" and fa[0]["location"] == "lines 1-1"


def test_unreviewed_and_textless_content_is_not_searchable(files, tmp_path):
    _db, library = _library_with_content(files, tmp_path)
    result = library.search("unapproved wording")
    assert result["status"] == "no_matches" and result["hits"] == []
    assert "unapproved OCR are not indexed" in result["message"]
    assert library.search("x")["status"] == "invalid_query"
    assert library.search("  ")["status"] == "invalid_query"


def test_index_follows_imports_and_deletes(files, tmp_path):
    _db, library = _library_with_content(files, tmp_path)
    assert library.search("PDC bit")["hits"] == []
    outcome = library.import_reviewed(extract_document(files["text_only"]))
    assert library.search("PDC bit")["hits"][0]["document_id"] == outcome.document_id
    library.delete_document(outcome.document_id)
    assert library.search("PDC bit")["hits"] == []


def test_search_falls_back_to_substring_scan_without_fts5(files, tmp_path, monkeypatch):
    _db, library = _library_with_content(files, tmp_path)

    class NoFts:
        OperationalError = sqlite3.OperationalError

        @staticmethod
        def connect(_path):
            connection = sqlite3.connect(":memory:")

            class Wrapper:
                def execute(self, sql, *args):
                    if "fts5" in sql:
                        raise sqlite3.OperationalError("no such module: fts5")
                    return connection.execute(sql, *args)

                def close(self):
                    connection.close()
            return Wrapper()
    monkeypatch.setattr(dl, "sqlite3", NoFts)
    result = library.search("casing shoe")
    assert result["method"].startswith("Substring scan") and library.fts_available is False
    (hit,) = result["hits"]
    assert hit["location"] == "page 1" and "[casing]" in hit["snippet"]
    assert library.search("unapproved")["hits"] == []


# ---------------------------------------------------------------------- OCR
def test_ocr_status_reports_absence_and_opt_out(monkeypatch):
    status = dl.ocr_status()
    assert status["available"] is False and "requirements-optional.txt" in status["reason"]
    assert dl.default_ocr_engine() is None
    dl._OCR_STATE.clear()
    monkeypatch.setenv("DRILLMASTER_OCR", "0")
    assert dl.ocr_status()["reason"].startswith("OCR disabled")


def test_rapidocr_adapter_raises_clear_error_when_missing():
    with pytest.raises(dl.OcrUnavailable, match="not installed"):
        dl.RapidOcrEngine()


def test_rapidocr_adapter_rebuilds_lines_from_boxes(monkeypatch):
    class Output:
        txts = ("SYNTHETIC CASING", "9 5/8", "SHOE 1250 m")
        scores = (0.9, 1.0, 0.8)
        boxes = [[(10, 10), (200, 10), (200, 30), (10, 30)], [(220, 12), (300, 12), (300, 32), (220, 32)],
                 [(10, 60), (200, 60), (200, 80), (10, 80)]]
    engine = object.__new__(dl.RapidOcrEngine)
    engine._engine = lambda _image: Output()
    text, score = engine.recognize(b"png")
    assert text == "SYNTHETIC CASING 9 5/8\nSHOE 1250 m" and score == pytest.approx(0.9)
    engine._engine = lambda _image: type("Empty", (), {"txts": None})()
    assert engine.recognize(b"png") == ("", None)
