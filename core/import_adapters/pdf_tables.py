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
            for page_no, page in enumerate(doc, 1):
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
