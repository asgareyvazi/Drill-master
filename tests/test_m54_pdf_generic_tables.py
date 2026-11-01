"""M54 generic PDF tables: text-only tables, header rows, multi-page, margins, scanned/OCR state.

Synthetic PDFs drawn with PyMuPDF in a temp dir (no real DDR content). Exercises
the real tier-2 path of ``extract_tables`` and the common-IR adapter.
"""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from core.import_adapters import pdf_generic_tables as g  # noqa: E402
from core.import_adapters.pdf_tables import extract_tables  # noqa: E402


COLS = [50, 110, 170, 220, 290]


def row(page, y, cells):
    for x, text in zip(COLS, cells):
        if text:
            page.insert_text((x, y), text, fontsize=9)


def furniture(page, n, total):
    page.insert_text((50, 30), "SYNTHETIC DRILLING REPORT - TEST ONLY", fontsize=8)
    page.insert_text((260, 820), f"Page {n} of {total}", fontsize=8)


def text_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    furniture(p, 1, 3)
    p.insert_text((50, 80), "Daily operations summary for synthetic well", fontsize=10)
    y = 120
    row(p, y, ["From", "To", "Hrs", "Code", "Activity"])
    for r in [
        ["00:00", "06:00", "6.0", "DRL", "Drill ahead synthetic"],
        ["06:00", "08:30", "2.5", "CIRC", "Circulate bottoms up"],
    ]:
        y += 14
        row(p, y, r)
    y += 14
    row(p, y, ["", "", "", "", "and flow check"])  # wrapped cell
    for r in [["08:30", "12:00", "3.5", "TRIP", "Trip out"]]:
        y += 14
        row(p, y, r)
    row(p, 780, ["12:00", "13:00", "1.0", "SVC", "Service rig"])  # last line of page 1
    p = doc.new_page()
    furniture(p, 2, 3)
    y = 80
    row(p, y, ["From", "To", "Hrs", "Code", "Activity"])
    for r in [["13:00", "18:00", "5.0", "DRL", "Drill ahead"]]:
        y += 14
        row(p, y, r)
    y = 790
    row(p, y, ["18:00", "20:00", "2.0", "SURV", "Survey"])
    p = doc.new_page()
    furniture(p, 3, 3)
    y = 80
    row(p, y, ["20:00", "24:00", "4.0", "DRL", "Drill to section TD"])
    doc.save(path)


def ruled_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((50, 60), "Synthetic bit record", fontsize=10)
    xs = [50, 130, 210, 290, 370]
    ys = [100 + 20 * i for i in range(5)]
    for x in xs:
        p.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys:
        p.draw_line((xs[0], y), (xs[-1], y))
    data = [
        ["Bit No", "Size in", "Depth In", "Depth Out"],
        ["1", "12.25", "500", "900"],
        ["2", "12.25", "900", "1400"],
        ["3", "8.5", "1400", "1800"],
    ]
    for r, vals in enumerate(data):
        for c, v in enumerate(vals):
            p.insert_text((xs[c] + 4, ys[r] + 14), v, fontsize=9)
    doc.save(path)


def scanned_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 60), False)
    pix.clear_with(200)
    p.insert_image(fitz.Rect(50, 50, 400, 400), pixmap=pix)
    doc.save(path)


def _tables(result, method):
    return [t for t in result["tables"] if t["report"].get("method") == method]


def test_a_text_only_table_is_rebuilt_with_its_header_as_headers(tmp_path):
    path = tmp_path / "text.pdf"
    text_pdf(str(path))
    result = extract_tables(str(path))
    assert result["engine"] == "pymupdf" and result["error"] is None
    (table,) = _tables(result, "pymupdf-text-columns")
    assert list(table["data"][0]) == ["From", "To", "Hrs", "Code", "Activity"]
    assert all(rec["From"] != "From" for rec in table["data"])  # header never a data row
    assert [rec["From"] for rec in table["data"]] == ["00:00", "06:00", "08:30", "12:00", "13:00", "18:00", "20:00"]


def test_a_wrapped_cell_joins_the_row_above(tmp_path):
    path = tmp_path / "text.pdf"
    text_pdf(str(path))
    (table,) = _tables(extract_tables(str(path)), "pymupdf-text-columns")
    assert table["data"][1]["Activity"] == "Circulate bottoms up and flow check"
    assert len(table["data"]) == 7


def test_a_table_continues_across_pages_with_row_page_provenance(tmp_path):
    path = tmp_path / "text.pdf"
    text_pdf(str(path))
    (table,) = _tables(extract_tables(str(path)), "pymupdf-text-columns")
    assert table["report"]["pages"] == [1, 2, 3] and table["report"]["continued"] is True
    assert table["report"]["row_pages"] == [1, 1, 1, 1, 2, 2, 3]
    assert table["data"][-1] == {
        "From": "20:00",
        "To": "24:00",
        "Hrs": "4.0",
        "Code": "DRL",
        "Activity": "Drill to section TD",
    }


def test_repeated_page_headers_and_footers_are_excluded(tmp_path):
    path = tmp_path / "text.pdf"
    text_pdf(str(path))
    result = extract_tables(str(path))
    assert result["margin_lines_removed"] == 6
    texts = [rec["text"] for t in result["tables"] if t["report"].get("section") == "page_text" for rec in t["data"]]
    assert texts == ["Daily operations summary for synthetic well"]
    flat = " ".join(str(v) for t in result["tables"] for rec in t["data"] for v in rec.values())
    assert "SYNTHETIC DRILLING REPORT" not in flat and "Page 2 of 3" not in flat


def test_a_ruled_table_header_row_is_not_read_as_data(tmp_path):
    path = tmp_path / "ruled.pdf"
    ruled_pdf(str(path))
    (table,) = _tables(extract_tables(str(path)), "find_tables-generic")
    assert table["report"]["header_detected"] is True and table["report"]["header_row"] == 1
    assert table["data"] == [
        {"Bit No": "1", "Size in": "12.25", "Depth In": "500", "Depth Out": "900"},
        {"Bit No": "2", "Size in": "12.25", "Depth In": "900", "Depth Out": "1400"},
        {"Bit No": "3", "Size in": "8.5", "Depth In": "1400", "Depth Out": "1800"},
    ]


def test_a_scanned_pdf_reports_ocr_unavailable_and_guesses_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ocr_status", lambda: "unavailable")
    path = tmp_path / "scanned.pdf"
    scanned_pdf(str(path))
    result = extract_tables(str(path))
    assert result["tables"] == [] and result["scanned_pages"] == [1] and result["ocr"] == "unavailable"
    assert result["error"].startswith("OCR unavailable: scanned page(s) [1] have no text layer")


def test_the_common_ir_adapter_gets_real_headers_and_text_pdfs_no_longer_fail(tmp_path, monkeypatch):
    from core.mineru_engine import MinerUOutputError, parse_pdf_native_fallback

    path = tmp_path / "text.pdf"
    text_pdf(str(path))
    document = parse_pdf_native_fallback(str(path))
    by_headers = {tuple(t.headers): t for t in document.tables}
    table = by_headers[("From", "To", "Hrs", "Code", "Activity")]
    assert len(table.rows) == 7 and table.provenance.source_page == 1
    assert ("text",) in by_headers
    scanned = tmp_path / "scanned.pdf"
    scanned_pdf(str(scanned))
    monkeypatch.setattr(g, "ocr_status", lambda: "unavailable")
    with pytest.raises(MinerUOutputError, match="OCR unavailable"):
        parse_pdf_native_fallback(str(scanned))


# ---- pure helpers ----------------------------------------------------------------------------------
def test_header_row_detection_rules():
    assert g.detect_header_row([["Bit", "Size"], ["1", "12.25"]]) == 0
    assert g.detect_header_row([["Synthetic title", ""], ["Bit", "Size"], ["1", "8.5"]]) == 1
    assert g.detect_header_row([["1", "12.25"], ["2", "8.5"]]) is None
    assert g.detect_header_row([["Remarks", "Notes"], ["text", "more text"]]) is None  # no value rows


def test_duplicate_header_names_are_kept_distinct():
    assert g.unique_headers(["Depth", "Depth", "", "Depth"]) == ["Depth", "Depth (2)", "Column 3", "Depth (3)"]


def test_value_tokens_cover_numbers_times_and_dates():
    for token in ("12.25", "-3", "06:00", "24:00", "2026-01-15", "15/01/2026", "85%"):
        assert g.is_value_token(token), token
    for token in ("Drill", "Bit No", "", "P/U"):
        assert not g.is_value_token(token), token


def test_a_header_less_ruled_continuation_is_rekeyed_to_the_previous_headers():
    first = g.ruled_table_payload([["Bit", "Size"], ["1", "12.25"]], 1, {"page": 1})
    second = g.ruled_table_payload([["2", "8.5"], ["3", "6.0"]], 2, {"page": 2})
    other = g.ruled_table_payload([["Bit", "Size"], ["9", "4.0"]], 4, {"page": 4})
    joined = g.join_ruled_continuations([first, second, other])
    assert len(joined) == 2
    assert joined[0]["data"] == [
        {"Bit": "1", "Size": "12.25"},
        {"Bit": "2", "Size": "8.5"},
        {"Bit": "3", "Size": "6.0"},
    ]
    assert joined[0]["report"]["pages"] == [1, 2] and joined[0]["report"]["row_pages"] == [1, 2, 2]
    assert joined[1]["page"] == 4  # page 3 gap: not a continuation


def test_the_import_preview_note_states_the_ocr_condition():
    from dialogs.excel_import_dialog import ImportPreviewDialog

    note = ImportPreviewDialog.pdf_extraction_note
    assert note({}) is None
    assert note({"fallback_diagnostics": {"fallback": {"scanned_pages": [], "ocr": "unavailable"}}}) is None
    unavailable = note({"fallback_diagnostics": {"fallback": {"scanned_pages": [2, 4], "ocr": "unavailable"}}})
    assert unavailable.startswith("OCR unavailable: page(s) 2, 4 are scanned images")
    assert "Nothing was guessed" in unavailable
    available = note({"fallback_diagnostics": {"fallback": {"scanned_pages": [1], "ocr": "available"}}})
    assert available.startswith("Scanned page(s) 1 detected: OCR text must be verified")
