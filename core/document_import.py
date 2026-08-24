"""Input adapters for the Universal Import entry point.

Professional Features:
- CSV to XLSX with encoding detection (utf-8-sig, utf-8, cp1256 for Persian)
- PDF to XLSX with 3-tier extraction:
  1. Camelot (text PDF tables) - preferred
  2. PyMuPDF coordinate-preserving text extraction - fallback
  3. OCR via pytesseract + pdf2image for scanned PDFs - final fallback
- Metrics preserved for Review Matrix and Data Quality Score
- Atomic transaction ready
"""

from pathlib import Path
import csv
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def _write_rows(rows, output_path, sheet_name="Imported"):
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name[:31] or "Imported"
    for row in rows:
        sheet.append(list(row))
    workbook.save(output_path)
    workbook.close()
    return {"rows": len(rows), "path": str(output_path)}


def csv_to_xlsx(csv_path, output_path):
    """CSV to XLSX with Persian encoding support."""
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "windows-1256", "iso-8859-6"):
        try:
            with open(csv_path, newline="", encoding=encoding) as stream:
                reader = csv.reader(stream)
                rows = list(reader)
                if rows:
                    result = _write_rows(rows, output_path, Path(csv_path).stem)
                    result["encoding"] = encoding
                    result["engine"] = "csv"
                    return result
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            logger.debug(f"CSV read with {encoding} failed: {exc}")
            continue
    raise ValueError("CSV encoding is not supported - tried utf-8-sig, utf-8, cp1256, windows-1256")


def pdf_to_xlsx(pdf_path, output_path):
    """Convert PDF tables to XLSX with 3-tier extraction.

    Tier 1: Camelot (text PDF tables) - best for bordered tables
    Tier 2: PyMuPDF coordinate-preserving text - good for text PDFs without borders
    Tier 3: OCR via pytesseract - for scanned PDFs (Qwen-VL future, pytesseract now)

    Returned metrics are kept for Import Review Matrix and Data Quality.
    """
    metrics: List[Dict[str, Any]] = []
    rows: List[List[str]] = []

    # Tier 1: Camelot
    try:
        import camelot
        tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="stream")
        tier1_rows = []
        for index, table in enumerate(tables, 1):
            report = getattr(table, "parsing_report", {})
            metrics.append({"tier": 1, "table": index, "engine": "camelot", **report})
            tier1_rows.append([f"[Table {index} | Page {report.get('page', '')} | Accuracy {report.get('accuracy', '')}]"])
            tier1_rows.extend(table.df.fillna("").astype(str).values.tolist())
        if tier1_rows:
            result = _write_rows(tier1_rows, output_path, "PDF Tables - Camelot")
            result["engine"] = "camelot"
            result["tier"] = 1
            result["metrics"] = metrics
            result["table_count"] = len(tables)
            logger.info(f"PDF Tier1 Camelot: {len(tables)} tables from {pdf_path}")
            return result
        else:
            metrics.append({"tier": 1, "engine": "camelot", "info": "No tables found"})
    except ImportError:
        metrics.append({"tier": 1, "engine": "camelot", "error": "not installed - pip install camelot-py[cv]"})
    except Exception as exc:
        metrics.append({"tier": 1, "engine": "camelot", "error": str(exc)})
        logger.debug(f"Camelot failed: {exc}")

    # Tier 2: PyMuPDF text extraction with coordinate grouping
    try:
        import fitz  # PyMuPDF

        document = fitz.open(str(pdf_path))
        tier2_rows = []
        try:
            for page_no, page in enumerate(document, 1):
                blocks = page.get_text("blocks")
                grouped: Dict[float, List[tuple]] = {}
                for block in blocks:
                    x0, y0, _x1, _y1, text = block[:5]
                    for line in str(text).splitlines():
                        line = line.strip()
                        if line:
                            grouped.setdefault(round(y0, 1), []).append((x0, line))

                tier2_rows.append([f"[Page {page_no} - PyMuPDF Text]"])
                for _y, cells in sorted(grouped.items()):
                    cells.sort(key=lambda value: value[0])
                    text = " | ".join(value for _x, value in cells)
                    parts = [part.strip() for part in re.split(r"\s*\|\s*|\t|\s{2,}", text) if part.strip()]
                    if parts:
                        tier2_rows.append(parts)

            if tier2_rows and len(tier2_rows) > len(document):  # More than just page headers
                result = _write_rows(tier2_rows, output_path, "PDF Text - PyMuPDF")
                result["engine"] = "pymupdf-coordinate-fallback"
                result["tier"] = 2
                result["metrics"] = metrics
                result["page_count"] = len(document)
                logger.info(f"PDF Tier2 PyMuPDF: {len(tier2_rows)} rows from {pdf_path}")
                return result
            else:
                metrics.append({"tier": 2, "engine": "pymupdf", "info": "No meaningful text extracted, trying OCR"})

        finally:
            document.close()

    except ImportError as exc:
        metrics.append({"tier": 2, "engine": "pymupdf", "error": f"not installed: {exc}"})
    except Exception as exc:
        metrics.append({"tier": 2, "engine": "pymupdf", "error": str(exc)})
        logger.debug(f"PyMuPDF failed: {exc}")

    # Tier 3: OCR for scanned PDFs
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image

        # Convert PDF pages to images
        images = convert_from_path(str(pdf_path), first_page=1, last_page=5)  # limit to 5 pages for performance
        tier3_rows = []

        for page_no, image in enumerate(images, 1):
            tier3_rows.append([f"[Page {page_no} - OCR]"])
            # OCR with table awareness
            ocr_text = pytesseract.image_to_string(image)

            for line in ocr_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Split by multiple spaces or tabs as table columns
                parts = [p.strip() for p in re.split(r"\t|\s{2,}| \| ", line) if p.strip()]
                if parts:
                    tier3_rows.append(parts)

            # Also try to get data with TSV for better structure
            try:
                tsv_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DATAFRAME)
                # Group by block/line
                if not tsv_data.empty:
                    # Filter confident text
                    confident = tsv_data[tsv_data.conf > 60]
                    if not confident.empty:
                        metrics.append(
                            {
                                "tier": 3,
                                "page": page_no,
                                "engine": "pytesseract",
                                "confident_words": len(confident),
                                "avg_conf": float(confident.conf.mean()),
                            }
                        )
            except Exception:
                pass

        if tier3_rows and len(tier3_rows) > len(images):
            result = _write_rows(tier3_rows, output_path, "PDF OCR - Tesseract")
            result["engine"] = "pytesseract-ocr"
            result["tier"] = 3
            result["metrics"] = metrics
            result["page_count"] = len(images)
            logger.info(f"PDF Tier3 OCR: {len(tier3_rows)} rows from {pdf_path}")
            return result
        else:
            metrics.append({"tier": 3, "engine": "pytesseract", "info": "OCR produced no data"})

    except ImportError as exc:
        metrics.append({"tier": 3, "engine": "pytesseract", "error": f"not installed: {exc} - pip install pytesseract pdf2image Pillow"})
    except Exception as exc:
        metrics.append({"tier": 3, "engine": "pytesseract", "error": str(exc)})
        logger.debug(f"OCR failed: {exc}")

    # If all tiers failed but we have some rows from any tier, return what we have
    if rows:
        result = _write_rows(rows, output_path, "PDF Fallback")
        result["engine"] = "fallback"
        result["metrics"] = metrics
        return result

    # Complete failure - return metrics for Review Matrix
    raise RuntimeError(
        f"PDF import failed for {pdf_path} - All 3 tiers failed:\n"
        f"Tier1 Camelot: {metrics[0] if len(metrics)>0 else 'no attempt'}\n"
        f"Tier2 PyMuPDF: {metrics[1] if len(metrics)>1 else 'no attempt'}\n"
        f"Tier3 OCR: {metrics[2] if len(metrics)>2 else 'no attempt'}\n"
        f"Install: pip install camelot-py[cv] PyMuPDF pytesseract pdf2image Pillow"
    )


def extract_pdf_with_ocr_preview(pdf_path: str) -> Dict[str, Any]:
    """Extract PDF with preview of which tier will be used, for Import Preview dialog.

    Returns dict with tier, engine, table count, sample rows, metrics.
    No file writing - just analysis.
    """
    metrics = []
    preview = {"file": str(pdf_path), "tier": None, "engine": None, "table_count": 0, "sample_rows": [], "metrics": []}

    # Tier1 check
    try:
        import camelot
        tables = camelot.read_pdf(str(pdf_path), pages="1", flavor="stream")
        if tables and len(tables) > 0:
            preview["tier"] = 1
            preview["engine"] = "camelot"
            preview["table_count"] = len(tables)
            preview["sample_rows"] = tables[0].df.head(3).astype(str).values.tolist() if hasattr(tables[0], 'df') else []
            preview["metrics"] = [{"tier": 1, "engine": "camelot", "tables": len(tables)}]
            return preview
    except Exception as exc:
        metrics.append({"tier": 1, "error": str(exc)})

    # Tier2 check
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        text = doc[0].get_text() if len(doc) > 0 else ""
        doc.close()
        if text and len(text.strip()) > 100:
            preview["tier"] = 2
            preview["engine"] = "pymupdf"
            preview["sample_rows"] = [line.split() for line in text.splitlines()[:3] if line.strip()]
            preview["metrics"] = metrics + [{"tier": 2, "engine": "pymupdf", "text_length": len(text)}]
            return preview
    except Exception as exc:
        metrics.append({"tier": 2, "error": str(exc)})

    # Tier3 - scanned
    preview["tier"] = 3
    preview["engine"] = "pytesseract (scanned PDF suspected)"
    preview["metrics"] = metrics + [{"tier": 3, "info": "Scanned PDF - OCR required"}]
    return preview
