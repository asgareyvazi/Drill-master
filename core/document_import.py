"""Document adapters used by the single Universal Import entry point."""
from pathlib import Path
import re


def pdf_to_xlsx(pdf_path, output_path):
    """Convert text-based PDF blocks to a reviewable XLSX.

    Coordinates are used to rebuild rows; the semantic importer then applies
    the same table detection and review rules as a native workbook.
    """
    try:
        import fitz
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("PDF import requires PyMuPDF and openpyxl") from exc
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
                    if not line:
                        continue
                    key = round(y0, 1)
                    grouped.setdefault(key, []).append((x0, line))
            rows.append([f"[Page {page_no}]"])
            for _y, cells in sorted(grouped.items()):
                cells.sort(key=lambda value: value[0])
                text = " | ".join(value for _x, value in cells)
                parts = [part.strip() for part in re.split(r"\s*\|\s*|\t|\s{2,}", text) if part.strip()]
                if parts:
                    rows.append(parts)
    finally:
        document.close()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PDF Import"
    for row in rows:
        sheet.append(row)
    workbook.save(output_path)
    workbook.close()
    return {"rows": len(rows), "path": str(output_path)}
