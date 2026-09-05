"""Format-aware routing for the standard DrillMaster import pipeline.

This module only decides which engine should receive a file.  It does not
parse documents or write to SQLite.  Known structured workbooks stay on the
existing deterministic Excel path; document-style inputs can use the external
MinerU adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from core.mineru_engine import IMAGE_SUFFIXES, SUPPORTED_SUFFIXES


@dataclass(frozen=True)
class ImportRoute:
    source_file: str
    engine: str
    reason: str
    fallback_engine: Optional[str] = None


def route_file(
    source_file: str,
    *,
    template_matcher: Optional[Callable[[list[str]], object]] = None,
) -> ImportRoute:
    """Return a route without invoking any external process.

    ``template_matcher`` is the existing Excel template matcher supplied by
    the UI layer.  If it is unavailable, an XLSX is conservatively considered
    unknown and may use MinerU rather than being silently treated as a known
    structured workbook.
    """
    path = Path(source_file)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        if template_matcher is not None:
            sheet_names = _sheet_names(path)
            try:
                matched = template_matcher(sheet_names)
            except Exception:
                matched = None
            if matched:
                return ImportRoute(str(path), "excel_intelligence", "known structured workbook")
        return ImportRoute(
            str(path),
            "mineru",
            "unknown or document-style workbook",
            fallback_engine="excel_intelligence",
        )
    if suffix == ".csv":
        return ImportRoute(str(path), "csv", "CSV remains on the existing deterministic converter")
    if suffix == ".pdf":
        return ImportRoute(str(path), "mineru", "PDF document intelligence", fallback_engine="pdf_fallback")
    if suffix in {".docx", ".pptx"} or suffix in IMAGE_SUFFIXES:
        return ImportRoute(str(path), "mineru", f"MinerU primary parser for {suffix[1:].upper()}")
    if suffix == ".xls":
        return ImportRoute(str(path), "unsupported", "legacy XLS requires conversion to XLSX")
    if suffix not in SUPPORTED_SUFFIXES:
        return ImportRoute(str(path), "unsupported", f"unsupported import format: {suffix or '<none>'}")
    return ImportRoute(str(path), "unsupported", f"unsupported import format: {suffix}")


def _sheet_names(path: Path) -> list[str]:
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            return [sheet.title for sheet in workbook.worksheets]
        finally:
            workbook.close()
    except Exception:
        return []
