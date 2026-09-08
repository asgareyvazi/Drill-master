"""PDF table extraction with 3-tier professional fallback: Camelot → PyMuPDF → OCR

Implements:
- Text PDF table extraction via Camelot
- Coordinate-preserving text via PyMuPDF
- Scanned PDF OCR via pytesseract (Qwen-VL future placeholder)
- Metrics preserved for Review Matrix and Data Quality Score
"""

import logging
from typing import Dict, Any, List
from pathlib import Path
import re

logger = logging.getLogger(__name__)


def _cell_text(value: Any) -> str:
    return str(value or "").replace("\\n", " ").replace("\n", " ").strip()


def _pymupdf_structured_tables(page, page_no: int) -> List[Dict[str, Any]]:
    """Convert PyMuPDF's geometric table model into semantic table payloads.

    The PDF report is a merged-cell form, not a conventional one-header table.
    ``get_text('blocks')`` destroys that structure.  ``find_tables`` retains
    row/column boundaries; this adapter then emits the report's actual sections
    with canonical headers while preserving page and bounding-box provenance.
    """
    finder = getattr(page, "find_tables", None)
    if not callable(finder):
        return []
    found = finder()
    detected = list(getattr(found, "tables", []) or [])
    outputs: List[Dict[str, Any]] = []
    for table_index, detected_table in enumerate(detected, 1):
        matrix = [[_cell_text(value) for value in row] for row in (detected_table.extract() or [])]
        matrix = [[value if value != "None" else "" for value in row] for row in matrix]
        if not matrix:
            continue
        bbox = tuple(getattr(detected_table, "bbox", ()) or ()) or None
        report = {"page": page_no, "method": "pymupdf-find-tables", "bbox": bbox, "detected_table": table_index}

        # The primary form table contains two semantically independent time
        # logs.  Locate headers by labels instead of hard-coding row numbers.
        for start, section, end_section in (
            ("24h", "time_log", "time_log_morning"),
            ("morning", "time_log_morning", None),
        ):
            header_index = next(
                (i for i, row in enumerate(matrix)
                 if "From" in row and "To" in row and "Code" in row and "Rig Activity" in row
                 and ((start == "24h" and i < len(matrix) // 2) or (start == "morning" and i >= len(matrix) // 2))),
                None,
            )
            if header_index is None:
                continue
            header = matrix[header_index]
            positions = {
                "From": header.index("From"),
                "To": header.index("To"),
                "hrs": next((i for i, value in enumerate(header) if value in {"hrs", "hrs."}), 3),
                "Main Phase": next((i for i, value in enumerate(header) if value.replace(" ", "") == "MainPhase"), 5),
                "Code": header.index("Code"),
                "Sub Code": next((i for i, value in enumerate(header) if value.replace(" ", "") == "SubCode"), 9),
                "Status": header.index("Status"),
                "NPT/ Unplan Attributed": next((i for i, value in enumerate(header) if value.startswith("NPT/")), 11),
                "Rig Activity": header.index("Rig Activity"),
            }
            records = []
            for row in matrix[header_index + 1:]:
                if row and str(row[0]).strip().casefold() == "from":
                    break
                values = [row[index] if index < len(row) else "" for index in positions.values()]
                if not any(str(value).strip() for value in values):
                    continue
                if str(row[0]).strip().casefold() == "total":
                    continue
                record = dict(zip(positions, values))
                if section == "time_log_morning":
                    record = {f"Morning {key}": value for key, value in record.items()}
                records.append(record)
            if records:
                outputs.append({
                    "data": records,
                    "page": page_no,
                    "report": {**report, "section": section, "header_row": header_index + 1},
                })

        # Scalar report anchors in the merged form are converted into a
        # semantic header table.  This keeps the real report date, depth, and
        # mud-weight source unit available to the common normalizer.
        if len(matrix) >= 8 and len(matrix[3]) > 12:
            report_header = {
                "Report Year": matrix[3][4], "Report Month": matrix[3][6], "Report Day": matrix[3][8],
                "MD (m)@ 0:00": matrix[1][12], "MD (m)@ 24:00": matrix[2][12],
                "MD (m)@ 6:00": matrix[3][12], "MW (PCF)": matrix[6][8],
                "RT - WH (m)": matrix[6][12], "Section Start Depth": matrix[7][12],
            }
            outputs.append({"data": [report_header], "page": page_no,
                            "report": {**report, "section": "daily_report_header"}})

        # Summary and forecast are merged full-width rows between metadata and
        # the first time log.  Preserve the exact source text as two fields.
        summary_index = next((i for i, row in enumerate(matrix) if row and row[0].startswith("Summary of Activities")), None)
        forecast_index = next((i for i, row in enumerate(matrix) if row and row[0].startswith("Operation Forecast")), None)
        if summary_index is not None or forecast_index is not None:
            summary = matrix[summary_index + 1][0] if summary_index is not None and summary_index + 1 < len(matrix) else ""
            forecast = matrix[forecast_index + 1][0] if forecast_index is not None and forecast_index + 1 < len(matrix) else ""
            outputs.append({"data": [{"Summary": summary, "Forecast": forecast}], "page": page_no,
                            "report": {**report, "section": "daily_report_text"}})

        # Casing header starts at the Previous Casing Information column.  It
        # is intentionally a separate table so the canonical casing mapper
        # sees its real field names rather than generic Column N labels.
        casing_header_index = 2 if len(matrix) > 2 and "Size (in)" in matrix[2] else None
        if casing_header_index is not None:
            casing_names = (
                "Size (in)", "From (m)", "To (m)", "Grade", "Weight (#)", "Thread",
                "Shoe (TVD)m", "Burst (psi)", "Collapse (psi)"
            )
            casing_positions = {name: matrix[casing_header_index].index(name) for name in casing_names if name in matrix[casing_header_index]}
            casing_records = []
            for row in matrix[casing_header_index + 1:]:
                if row and (row[0].startswith("Summary") or row[0].startswith("From")):
                    break
                if len(row) <= max(casing_positions.values(), default=-1):
                    continue
                values = [row[index] for index in casing_positions.values()]
                if any(values):
                    casing_records.append(dict(zip((name.replace("\n", " ") for name in casing_positions), values)))
            if casing_records:
                outputs.append({"data": casing_records, "page": page_no,
                                "report": {**report, "section": "casing"}})
        # If this is a non-form table (the compact metadata table), retain its
        # key/value pairs as a single record with semantic headers.
        if len(matrix[0]) <= 10 and any("Well Name:" in row for row in matrix):
            record: Dict[str, str] = {}
            for row in matrix:
                for index in range(0, len(row) - 1, 2):
                    label, value = row[index].rstrip(": "), row[index + 1]
                    if label and value and label.endswith(":") is False:
                        record[label] = value
            if record:
                outputs.append({"data": [record], "page": page_no, "report": {**report, "section": "report_metadata"}})

        # Keep an auditable raw section when no semantic section was detected.
        if not any(item.get("report", {}).get("detected_table") == table_index for item in outputs):
            headers = [f"Column {index + 1}" for index in range(max(len(row) for row in matrix))]
            outputs.append({"data": [dict(zip(headers, row)) for row in matrix], "page": page_no, "report": report})
    return outputs


def extract_tables(path, pages="all") -> Dict[str, Any]:
    """Return tables plus parser metrics; never silently discard failures.

    3-tier extraction for professional platform.
    """
    metrics: List[Dict[str, Any]] = []

    # Tier 1: Camelot
    try:
        import camelot
        tables = camelot.read_pdf(str(path), pages=pages, flavor="stream")
        result = []
        for table in tables:
            result.append(
                {
                    "data": table.df.to_dict(orient="records"),
                    "report": getattr(table, "parsing_report", {}),
                    "shape": table.df.shape,
                    "page": getattr(table, "page", None),
                }
            )
        if result:
            return {
                "tables": result,
                "engine": "camelot",
                "tier": 1,
                "table_count": len(result),
                "error": None,
                "metrics": [{"tier": 1, "engine": "camelot", "tables": len(result)}],
            }
        metrics.append({"tier": 1, "engine": "camelot", "info": "No tables found"})
    except ImportError:
        metrics.append({"tier": 1, "engine": "camelot", "error": "Install camelot-py for text PDF tables - pip install camelot-py[cv]"})
    except Exception as exc:
        logger.error("PDF Tier1 Camelot failed: %s", exc, exc_info=True)
        metrics.append({"tier": 1, "engine": "camelot", "error": str(exc)})

    # Tier 2: PyMuPDF
    try:
        import fitz

        doc = fitz.open(str(path))
        tables = []
        try:
            structured_available = False
            for page_no, page in enumerate(doc, 1):
                structured = _pymupdf_structured_tables(page, page_no)
                if structured:
                    tables.extend(structured)
                    structured_available = True
                    continue
                blocks = page.get_text("blocks")
                grouped = {}
                for block in blocks:
                    x0, y0, _x1, _y1, text = block[:5]
                    for line in str(text).splitlines():
                        line = line.strip()
                        if line:
                            grouped.setdefault(round(y0, 1), []).append((x0, line))

                page_rows = []
                for _y, cells in sorted(grouped.items()):
                    cells.sort(key=lambda v: v[0])
                    text = " | ".join(v for _x, v in cells)
                    parts = [p.strip() for p in re.split(r"\s*\|\s*|\t|\s{2,}", text) if p.strip()]
                    if parts:
                        page_rows.append(parts)

                if page_rows:
                    # Convert to dict records
                    if len(page_rows) >= 2:
                        headers = page_rows[0]
                        for row in page_rows[1:]:
                            record = {}
                            for i, h in enumerate(headers):
                                if i < len(row):
                                    record[h] = row[i]
                            if record:
                                tables.append({"data": record, "page": page_no, "report": {"page": page_no, "method": "pymupdf"}})

            if structured_available:
                return {
                    "tables": tables,
                    "engine": "pymupdf",
                    "tier": 2,
                    "table_count": len(tables),
                    "error": None,
                    "metrics": metrics + [{"tier": 2, "engine": "pymupdf", "tables": len(tables), "method": "find_tables"}],
                }
            if tables:
                return {
                    "tables": [{"data": tables, "report": {"engine": "pymupdf"}}],
                    "engine": "pymupdf",
                    "tier": 2,
                    "table_count": len(tables),
                    "error": None,
                    "metrics": metrics + [{"tier": 2, "engine": "pymupdf", "rows": len(tables)}],
                }
        finally:
            doc.close()

        metrics.append({"tier": 2, "engine": "pymupdf", "info": "No tables extracted"})

    except ImportError:
        metrics.append({"tier": 2, "engine": "pymupdf", "error": "Install PyMuPDF - pip install PyMuPDF"})
    except Exception as exc:
        logger.error("PDF Tier2 PyMuPDF failed: %s", exc, exc_info=True)
        metrics.append({"tier": 2, "engine": "pymupdf", "error": str(exc)})

    # Tier 3: OCR
    try:
        import pytesseract
        from pdf2image import convert_from_path

        images = convert_from_path(str(path), first_page=1, last_page=3)
        ocr_tables = []

        for page_no, image in enumerate(images, 1):
            text = pytesseract.image_to_string(image)
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines:
                ocr_tables.append(
                    {
                        "data": [{"text": line} for line in lines],
                        "report": {"page": page_no, "engine": "pytesseract", "method": "ocr"},
                    }
                )

        if ocr_tables:
            return {
                "tables": ocr_tables,
                "engine": "pytesseract-ocr",
                "tier": 3,
                "table_count": len(ocr_tables),
                "error": None,
                "metrics": metrics + [{"tier": 3, "engine": "pytesseract", "pages": len(images)}],
                "warning": "OCR extraction - verify data, confidence may be lower",
            }

        metrics.append({"tier": 3, "engine": "pytesseract", "info": "OCR produced no data"})

    except ImportError as exc:
        metrics.append({"tier": 3, "engine": "pytesseract", "error": f"Install pytesseract pdf2image Pillow: {exc}"})
    except Exception as exc:
        logger.error("PDF Tier3 OCR failed: %s", exc, exc_info=True)
        metrics.append({"tier": 3, "engine": "pytesseract", "error": str(exc)})

    # All tiers failed
    return {
        "tables": [],
        "engine": "unavailable",
        "tier": None,
        "table_count": 0,
        "error": f"All 3 PDF extraction tiers failed for {path}",
        "metrics": metrics,
        "help": "Install: pip install camelot-py[cv] PyMuPDF pytesseract pdf2image Pillow",
    }


def extract_with_qwen_vl_placeholder(path: str) -> Dict[str, Any]:
    """Placeholder for Qwen-VL → PDF تصویری as per spec future.

    Current implementation uses pytesseract, future will use Qwen-VL vision model.

    Architecture:
    - Qwen → Mapping عمومی
    - Gemma → مقایسه و Review
    - Qwen-VL → PDF تصویری (this placeholder)
    - Table Transformer → ساختار جدول

    Execution of multiple models only for ambiguous cases to preserve speed.
    """
    result = extract_tables(path)

    # Add future model placeholders
    result["future_models"] = {
        "qwen": "General mapping - currently using deterministic + Ollama",
        "gemma": "Comparison and Review - future",
        "qwen_vl": "Scanned PDF vision - currently pytesseract, future Qwen-VL",
        "table_transformer": "Table structure - future",
    }

    result["ai_escalation_policy"] = "Multi-model execution only for ambiguous cases with confidence <0.70 to preserve speed"

    return result
