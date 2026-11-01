"""M54: generic (non-form) PDF table reconstruction for the PyMuPDF tier.

Fixes the M52 limits of the tier-2 fallback:

* ruled tables that are not one of the known DDR form sections no longer emit
  their header row as data (header-row detection, ``header_detected`` flag);
* text-only (unruled) tables are rebuilt from word positions: the header line
  defines column anchors and every following word is assigned to a column;
  a wrapped cell (a lone fragment under a later column) is appended to the
  row above instead of creating a fake row;
* repeated page headers/footers (same text in the top/bottom margin band on
  two or more pages, digits normalised so "Page 1 of 3" matches "Page 2 of 3")
  are excluded before table detection;
* a table that continues on the next page (same column headers repeated, or a
  header-less table with the same column count at the top of the next page) is
  joined, with per-row page provenance;
* pages without a text layer are reported as scanned; OCR status is explicit
  (``available``/``unavailable``) and nothing is invented for those pages;
* non-tabular text is still returned as ``page_text`` line records so a
  text-only PDF never fails with "no tables or text".

Pure functions over word tuples ``(x0, y0, x1, y1, text)``; PyMuPDF is only
needed by :func:`page_words`. Deterministic; no network, no models.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

GENERIC_TABLES_VERSION = "M54 generic PDF tables v1"
MARGIN_FRACTION = 0.08        # top/bottom band (fraction of page height) checked for repeats
LINE_TOLERANCE = 3.0          # points: words whose vertical centres differ less share a line
CELL_GAP = 7.0                # points: a horizontal gap at least this wide separates cells
MIN_TEXT_CHARS = 40           # same threshold as core.ddr_pdf_split for "has a text layer"

Word = Tuple[float, float, float, float, str]

_NUMERIC = re.compile(r"^[-+]?(\d+([.,]\d+)?|\.\d+)(%|m|ft|h|hrs?)?$", re.IGNORECASE)
_TIME = re.compile(r"^([01]?\d|2[0-4])[:.][0-5]\d$")
_DATE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")
_PAGE_MARK = re.compile(r"^(page\s*)?\d+\s*(of|/)\s*\d+$", re.IGNORECASE)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\\n", " ")).strip()


def is_value_token(text: str) -> bool:
    """True for a number, time, or date token (a typical data cell)."""
    token = _clean(text)
    return bool(token) and bool(_NUMERIC.match(token) or _TIME.match(token) or _DATE.match(token))


def is_header_cell(text: str) -> bool:
    token = _clean(text)
    return bool(token) and not is_value_token(token) and any(ch.isalpha() for ch in token)


def unique_headers(raw: Sequence[Any]) -> List[str]:
    headers: List[str] = []
    for index, value in enumerate(raw):
        name = _clean(value) or f"Column {index + 1}"
        base, n = name, 2
        while name in headers:
            name = f"{base} ({n})"
            n += 1
        headers.append(name)
    return headers


# ---------------------------------------------------------------------------
# Ruled tables (PyMuPDF find_tables matrices)
# ---------------------------------------------------------------------------
def detect_header_row(matrix: Sequence[Sequence[Any]]) -> Optional[int]:
    """Index of the header row of a ruled table, or ``None`` if there is none.

    A header row has at least two non-empty cells, all of them label-like
    (contain letters, not numbers/times/dates), and is followed by at least
    one row that contains a value token. Only the first three rows are
    considered (titles may precede the header).
    """
    rows = [[_clean(c) for c in row] for row in matrix]
    for index, row in enumerate(rows[:3]):
        filled = [c for c in row if c]
        if len(filled) < 2 or not all(is_header_cell(c) for c in filled):
            continue
        if any(is_value_token(c) for later in rows[index + 1:] for c in later):
            return index
    return None


def ruled_table_payload(matrix: Sequence[Sequence[Any]], page_no: int, report: Dict[str, Any]) -> Dict[str, Any]:
    """Records for a non-form ruled table with header-row detection."""
    rows = [[_clean(c) for c in row] for row in matrix if any(_clean(c) for c in row)]
    width = max((len(r) for r in rows), default=0)
    header_index = detect_header_row(rows)
    if header_index is None:
        headers = [f"Column {i + 1}" for i in range(width)]
        body = rows
    else:
        headers = unique_headers(list(rows[header_index]) + [""] * (width - len(rows[header_index])))
        body = rows[header_index + 1:]
    records = [dict(zip(headers, list(r) + [""] * (width - len(r)))) for r in body]
    return {
        "data": records,
        "page": page_no,
        "report": {
            **report,
            "method": "find_tables-generic",
            "header_detected": header_index is not None,
            "header_row": None if header_index is None else header_index + 1,
            "row_pages": [page_no] * len(records),
            "version": GENERIC_TABLES_VERSION,
        },
    }


# ---------------------------------------------------------------------------
# Unruled text: lines, cells, margins
# ---------------------------------------------------------------------------
def group_lines(words: Iterable[Word]) -> List[Tuple[float, List[Word]]]:
    """Group words into visual lines by vertical centre; each line sorted by x."""
    lines: List[Tuple[float, List[Word]]] = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        if not _clean(word[4]):
            continue
        centre = (word[1] + word[3]) / 2
        if lines and abs(lines[-1][0] - centre) <= LINE_TOLERANCE:
            lines[-1][1].append(word)
        else:
            lines.append((centre, [word]))
    return [(y, sorted(ws, key=lambda w: w[0])) for y, ws in lines]


def line_cells(line_words: Sequence[Word]) -> List[Tuple[float, float, str]]:
    """Merge adjacent words into cells; a gap >= CELL_GAP starts a new cell."""
    cells: List[List[Any]] = []
    for x0, _y0, x1, _y1, text in line_words:
        if cells and x0 - cells[-1][1] < CELL_GAP:
            cells[-1][1] = x1
            cells[-1][2] += " " + _clean(text)
        else:
            cells.append([x0, x1, _clean(text)])
    return [(c[0], c[1], c[2]) for c in cells]


def _margin_key(text: str) -> str:
    return re.sub(r"\d+", "#", _clean(text).lower())


def repeated_margin_lines(pages: Sequence[Tuple[float, List[Tuple[float, List[Word]]]]]) -> set:
    """Normalised texts of lines repeated in the top/bottom band of >= 2 pages.

    ``pages`` is a list of ``(page_height, lines)``. Page-number marks
    ("Page 2 of 5", "2/5") in a margin band are always treated as furniture.
    """
    seen: Dict[str, set] = {}
    for page_index, (height, lines) in enumerate(pages):
        band = height * MARGIN_FRACTION
        for y, words in lines:
            if y <= band or y >= height - band:
                key = _margin_key(" ".join(w[4] for w in words))
                seen.setdefault(key, set()).add(page_index)
    repeated = {key for key, idx in seen.items() if len(idx) >= 2}
    repeated |= {key for key in seen if _PAGE_MARK.match(key.replace("#", "1"))}
    return repeated


def strip_margins(height: float, lines: List[Tuple[float, List[Word]]], repeated: set) -> Tuple[list, int]:
    band = height * MARGIN_FRACTION
    kept, dropped = [], 0
    for y, words in lines:
        in_band = y <= band or y >= height - band
        if in_band and _margin_key(" ".join(w[4] for w in words)) in repeated:
            dropped += 1
            continue
        kept.append((y, words))
    return kept, dropped


def _column_for(cell: Tuple[float, float, str], anchors: List[Tuple[float, float]]) -> int:
    """Column whose header span overlaps the cell most; else the nearest centre."""
    x0, x1, _ = cell
    best, best_overlap = None, 0.0
    for index, (a0, a1) in enumerate(anchors):
        overlap = min(x1, a1) - max(x0, a0)
        if overlap > best_overlap:
            best, best_overlap = index, overlap
    if best is not None:
        return best
    centre = (x0 + x1) / 2
    return min(range(len(anchors)), key=lambda i: abs((anchors[i][0] + anchors[i][1]) / 2 - centre))


def _consume_rows(cells_by_line, index, anchors, width):
    """Assign lines to columns from ``index``; returns ``(rows, next_index)``."""
    rows: List[List[str]] = []
    while index < len(cells_by_line):
        row_cells = cells_by_line[index]
        if len(row_cells) >= 2:
            row = [""] * width
            for cell in row_cells:
                col = _column_for(cell, anchors)
                row[col] = (row[col] + " " + cell[2]).strip()
            rows.append(row)
            index += 1
            continue
        if len(row_cells) == 1 and rows:
            col = _column_for(row_cells[0], anchors)
            if col > 0:
                rows[-1][col] = (rows[-1][col] + " " + row_cells[0][2]).strip()
                index += 1
                continue
        break
    return rows, index


def text_tables(lines: List[Tuple[float, List[Word]]], carry: Optional[Dict[str, Any]] = None):
    """Rebuild unruled tables from lines.

    Returns ``(tables, leftover_text_lines, ends_at_bottom)``. ``carry`` is the
    previous page's last table when it ran to the bottom of that page: value
    rows at the top of this page are then a header-less continuation and are
    assigned with the carried column anchors (``continuation_of_previous``).

    Each table is ``{"headers", "rows", "anchors"}``. A header line has >= 3
    label-like cells and the next line has >= 2 cells including a value token.
    Rows continue while lines have >= 2 cells; a single cell that sits under a
    non-first column is a wrapped continuation of the row above.
    """
    cells_by_line = [line_cells(words) for _y, words in lines]
    tables: List[Dict[str, Any]] = []
    leftover: List[str] = []
    index = 0
    ends_at_bottom = False
    if carry is not None and cells_by_line:
        first = cells_by_line[0]
        if len(first) >= 2 and any(is_value_token(c[2]) for c in first) and not all(
            is_header_cell(c[2]) for c in first
        ):
            rows, index = _consume_rows(cells_by_line, 0, carry["anchors"], len(carry["headers"]))
            tables.append({"headers": list(carry["headers"]), "rows": rows, "anchors": carry["anchors"],
                           "continuation_of_previous": True})
            ends_at_bottom = index >= len(cells_by_line)
    while index < len(cells_by_line):
        cells = cells_by_line[index]
        nxt = cells_by_line[index + 1] if index + 1 < len(cells_by_line) else []
        is_header = (
            len(cells) >= 3
            and all(is_header_cell(c[2]) for c in cells)
            and len(nxt) >= 2
            and any(is_value_token(c[2]) for c in nxt)
        )
        if not is_header:
            leftover.append(" ".join(c[2] for c in cells))
            index += 1
            continue
        anchors = [(c[0], c[1]) for c in cells]
        headers = unique_headers([c[2] for c in cells])
        rows, index = _consume_rows(cells_by_line, index + 1, anchors, len(headers))
        tables.append({"headers": headers, "rows": rows, "anchors": anchors})
        ends_at_bottom = index >= len(cells_by_line)
    return tables, leftover, ends_at_bottom


# ---------------------------------------------------------------------------
# Multi-page assembly
# ---------------------------------------------------------------------------
def join_continuations(
    page_tables: Sequence[Tuple[int, List[Dict[str, Any]], bool]], join: bool = True
) -> List[Dict[str, Any]]:
    """Join tables continued across pages.

    ``page_tables`` is ``[(page_no, tables, starts_at_top)]`` where
    ``starts_at_top`` tells whether the page's first table is the first
    content on that page. A first table on page N+1 continues the last table
    of page N when its headers equal the previous headers (a repeated header).
    """
    joined: List[Dict[str, Any]] = []
    previous_page = None
    for page_no, tables, starts_at_top in page_tables:
        for position, table in enumerate(tables):
            table = {**table, "pages": [page_no], "row_pages": [page_no] * len(table["rows"])}
            last = joined[-1] if joined else None
            if (
                join
                and position == 0
                and (starts_at_top or table.get("continuation_of_previous"))
                and last is not None
                and previous_page == page_no - 1
                and last["headers"] == table["headers"]
            ):
                last["rows"].extend(table["rows"])
                last["row_pages"].extend(table["row_pages"])
                last["pages"].append(page_no)
                last["continued"] = True
                continue
            joined.append(table)
        previous_page = page_no
    return joined


def ocr_status() -> str:
    """``available`` only if a local OCR engine is already installed."""
    has_binding = importlib.util.find_spec("pytesseract") is not None
    has_binary = shutil.which("tesseract") is not None
    return "available" if has_binding and has_binary else "unavailable"


def page_words(page) -> List[Word]:
    """PyMuPDF words as ``(x0, y0, x1, y1, text)``."""
    return [(w[0], w[1], w[2], w[3], str(w[4])) for w in page.get_text("words")]


def generic_document_tables(
    pages: Sequence[Tuple[int, float, List[Word], bool]], continuation: bool = True
) -> Dict[str, Any]:
    """Generic extraction for pages without form sections.

    ``pages`` is ``[(page_no, page_height, words, has_images)]``. Returns
    ``{"tables": [...payloads...], "scanned_pages", "ocr", "margin_lines_removed"}``
    where payloads use the ``{"data", "page", "report"}`` shape consumed by
    ``parse_pdf_native_fallback``.
    """
    grouped = [(height, group_lines(words)) for _no, height, words, _img in pages]
    repeated = repeated_margin_lines(grouped)
    scanned: List[int] = []
    removed = 0
    per_page: List[Tuple[int, List[Dict[str, Any]], bool]] = []
    text_payloads: List[Dict[str, Any]] = []
    carry: Optional[Dict[str, Any]] = None
    carry_page: Optional[int] = None
    for (page_no, height, words, has_images), (_h, lines) in zip(pages, grouped):
        if sum(len(_clean(w[4])) for w in words) < MIN_TEXT_CHARS:
            if has_images or not words:
                scanned.append(page_no)
            if not words:
                continue
        kept, dropped = strip_margins(height, lines, repeated)
        removed += dropped
        tables, leftover, ends_at_bottom = text_tables(
            kept, carry if continuation and carry_page is not None and carry_page == page_no - 1 else None
        )
        carry = tables[-1] if tables and ends_at_bottom else None
        carry_page = page_no if carry is not None else None
        first_cells = line_cells(kept[0][1]) if kept else []
        starts_at_top = bool(tables) and bool(kept) and [c[2] for c in first_cells] == [
            h for h in tables[0]["headers"]
        ]
        per_page.append((page_no, tables, starts_at_top))
        leftover = [line for line in leftover if line]
        if leftover:
            text_payloads.append({
                "data": [{"text": line} for line in leftover],
                "page": page_no,
                "report": {"page": page_no, "section": "page_text", "method": "pymupdf-text-lines",
                           "version": GENERIC_TABLES_VERSION},
            })
    payloads: List[Dict[str, Any]] = []
    for table in join_continuations(per_page, join=continuation):
        records = [dict(zip(table["headers"], row)) for row in table["rows"]]
        if not records:
            continue
        payloads.append({
            "data": records,
            "page": table["pages"][0],
            "report": {
                "page": table["pages"][0],
                "pages": table["pages"],
                "row_pages": table["row_pages"],
                "continued": bool(table.get("continued")),
                "method": "pymupdf-text-columns",
                "header_detected": True,
                "version": GENERIC_TABLES_VERSION,
            },
        })
    return {
        "tables": payloads + text_payloads,
        "scanned_pages": scanned,
        "ocr": ocr_status(),
        "margin_lines_removed": removed,
        "continuation": bool(continuation),
        "version": GENERIC_TABLES_VERSION,
    }


def join_ruled_continuations(payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Join generic ruled tables continued on the next page.

    A generic ``find_tables`` table on page N+1 continues the last generic
    table of page N when it is the first generic table on its page and either
    repeats the same headers, or has no detected header and the same column
    count (rows are then re-keyed to the previous headers).
    """
    out: List[Dict[str, Any]] = []
    first_on_page: set = set()
    for payload in payloads:
        report = payload.get("report", {})
        if report.get("method") != "find_tables-generic":
            out.append(payload)
            continue
        page = payload.get("page")
        is_first = page not in first_on_page
        first_on_page.add(page)
        previous = next((p for p in reversed(out) if p.get("report", {}).get("method") == "find_tables-generic"), None)
        if is_first and previous is not None and previous["report"].get("pages", [previous.get("page")])[-1] == (page or 0) - 1:
            prev_headers = list(previous["data"][0].keys()) if previous["data"] else []
            headers = list(payload["data"][0].keys()) if payload["data"] else []
            same = report.get("header_detected") and headers == prev_headers
            headerless = (not report.get("header_detected")) and len(headers) == len(prev_headers) and prev_headers
            if same or headerless:
                rows = payload["data"] if same else [dict(zip(prev_headers, r.values())) for r in payload["data"]]
                previous["data"].extend(rows)
                previous["report"].setdefault("pages", [previous.get("page")]).append(page)
                previous["report"]["row_pages"] = list(previous["report"].get("row_pages", [])) + [page] * len(rows)
                previous["report"]["continued"] = True
                continue
        out.append(payload)
    return out
