"""Input adapters for the Universal Import entry point."""
from pathlib import Path
import csv, re


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
    for encoding in ("utf-8-sig", "utf-8", "cp1256"):
        try:
            with open(csv_path, newline="", encoding=encoding) as stream:
                return _write_rows(list(csv.reader(stream)), output_path, Path(csv_path).stem)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV encoding is not supported")


def pdf_to_xlsx(pdf_path, output_path):
    """Convert PDF tables to XLSX, preferring Camelot and falling back to
    coordinate-preserving text extraction. Returned metrics are kept for the
    Import Review Matrix.
    """
    metrics = []
    try:
        import camelot
        tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="stream")
        rows = []
        for index, table in enumerate(tables, 1):
            report = getattr(table, "parsing_report", {})
            metrics.append({"table": index, **report})
            rows.append([f"[Table {index} | Page {report.get('page', '')}]"])
            rows.extend(table.df.fillna("").astype(str).values.tolist())
        if rows:
            result = _write_rows(rows, output_path, "PDF Tables")
            result["engine"] = "camelot"
            result["metrics"] = metrics
            return result
    except ImportError:
        metrics.append({"engine": "camelot", "error": "not installed"})
    except Exception as exc:
        metrics.append({"engine": "camelot", "error": str(exc)})

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF import requires camelot-py or PyMuPDF") from exc
    rows = []
    document = fitz.open(str(pdf_path))
    try:
        for page_no, page in enumerate(document, 1):
            blocks = page.get_text("blocks")
            grouped = {}
            for block in blocks:
                x0, y0, _x1, _y1, text = block[:5]
                for line in str(text).splitlines():
                    line = line.strip()
                    if line:
                        grouped.setdefault(round(y0, 1), []).append((x0, line))
            rows.append([f"[Page {page_no}]"])
            for _y, cells in sorted(grouped.items()):
                cells.sort(key=lambda value: value[0])
                text = " | ".join(value for _x, value in cells)
                parts = [part.strip() for part in re.split(r"\s*\|\s*|\t|\s{2,}", text) if part.strip()]
                if parts:
                    rows.append(parts)
    finally:
        document.close()
    result = _write_rows(rows, output_path, "PDF Text")
    result["engine"] = "pymupdf-coordinate-fallback"
    result["metrics"] = metrics
    return result
