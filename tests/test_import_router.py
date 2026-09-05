"""Routing tests for deterministic Excel and external document paths."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from core.import_router import route_file


def _workbook(path: Path, sheets: list[str]) -> None:
    workbook = Workbook()
    workbook.active.title = sheets[0]
    for name in sheets[1:]:
        workbook.create_sheet(name)
    workbook.save(path)
    workbook.close()


def test_pdf_docx_pptx_and_images_route_to_mineru(tmp_path):
    for suffix in (".pdf", ".docx", ".pptx", ".png"):
        path = tmp_path / f"input{suffix}"
        path.write_bytes(b"fixture")
        route = route_file(str(path))
        assert route.engine == "mineru"


def test_known_structured_excel_stays_on_excel_intelligence(tmp_path):
    path = tmp_path / "known.xlsx"
    _workbook(path, ["DDR Remark", "DDR Data"])

    route = route_file(str(path), template_matcher=lambda sheets: {"name": "known"})
    assert route.engine == "excel_intelligence"
    assert route.fallback_engine is None


def test_unknown_excel_can_route_to_mineru_with_excel_fallback(tmp_path):
    path = tmp_path / "unknown.xlsx"
    _workbook(path, ["Document", "Tables"])

    route = route_file(str(path), template_matcher=lambda sheets: None)
    assert route.engine == "mineru"
    assert route.fallback_engine == "excel_intelligence"


def test_csv_and_legacy_xls_preserve_existing_rules(tmp_path):
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    assert route_file(str(csv_path)).engine == "csv"

    xls_path = tmp_path / "input.xls"
    xls_path.write_bytes(b"legacy")
    assert route_file(str(xls_path)).engine == "unsupported"
