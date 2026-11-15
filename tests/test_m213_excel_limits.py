"""M213: generic Excel workbook limits (size, uncompressed size, sheets, used range), tightened per report profile
and configured in the real ``ReportProfileDialog``. Synthetic workbooks only; the source file is never modified.
"""
from __future__ import annotations

import hashlib
import shutil
import warnings
import zipfile
from pathlib import Path

import pytest

from core import ddr_import_pipeline as pipe
from core import workbook_io as wio
from core.ddr_report_profiles import ReportProfile, get_profile, validate_profile

FIXTURES = Path(__file__).parent / "fixtures"


def _profile(limits=None, **extra):
    rules = {"stop_markers": []}
    if limits is not None:
        rules["excel_limits"] = limits
    return ReportProfile(key="syn-limits", version=3, name="Synthetic limits", report_format="xlsx",
                         table_rules=rules, **extra)


@pytest.fixture(scope="module")
def service():
    from PySide6.QtWidgets import QApplication
    from core.ddr_import_service import DDRImportService
    QApplication.instance() or QApplication([])
    return DDRImportService()


def test_limits_rule_validation_only_allows_tightening():
    assert wio.validate_limits_rule({"max_sheets": 10, "max_bytes": 1024}) == []
    assert "above the built-in limit" in wio.validate_limits_rule({"max_sheets": 10**6})[0]
    assert "positive whole number" in wio.validate_limits_rule({"max_sheets": 0})[0]
    assert "positive whole number" in wio.validate_limits_rule({"max_sheets": True})[0]
    assert "Unknown Excel limit" in wio.validate_limits_rule({"max_rows": 5})[0]
    assert "must be a mapping" in wio.validate_limits_rule([1])[0]
    assert any("above the built-in limit" in e for e in validate_profile(_profile({"max_cells_total": 10**12})))
    assert validate_profile(_profile({"max_sheets": 4})) == []


def test_profile_limits_tighten_and_an_invalid_rule_falls_back_to_the_built_in_limits():
    limits = wio.limits_from_profile(_profile({"max_sheets": 4, "max_bytes": 2048}))
    assert (limits.max_sheets, limits.max_bytes, limits.source) == (4, 2048, "profile syn-limits v3")
    assert limits.max_cells_per_sheet == wio.HARD_LIMITS.max_cells_per_sheet
    assert wio.limits_from_profile(_profile({"max_sheets": 10**6})) == wio.HARD_LIMITS
    assert wio.limits_from_profile(None) == wio.HARD_LIMITS
    assert wio.HARD_LIMITS.as_dict()["source"] == "built-in"


def test_file_size_and_zip_bomb_are_refused_before_reading(tmp_path):
    small = tmp_path / "small.xlsx"
    shutil.copyfile(FIXTURES / "normal_ddr.xlsx", small)
    info = wio.check_workbook_file(small)
    assert info["bytes"] == small.stat().st_size and info["uncompressed_bytes"] > 0
    with pytest.raises(wio.WorkbookLimitError, match="exceeds the Excel import limit of 100 bytes"):
        wio.check_workbook_file(small, wio.WorkbookLimits(max_bytes=100, source="test"))
    bomb = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"\0" * (3 * 1024 * 1024))
    assert bomb.stat().st_size < 64 * 1024
    with pytest.raises(wio.WorkbookLimitError, match="uncompressed exceeds"):
        wio.check_workbook_file(bomb, wio.WorkbookLimits(max_uncompressed_bytes=1024 * 1024))


def test_sheet_count_and_used_range_are_refused():
    from openpyxl import Workbook
    workbook = Workbook()
    workbook.active.cell(row=300, column=40, value="x")                      # 12 000 cells
    for index in range(3):
        workbook.create_sheet(f"S{index}")
    assert wio.check_workbook_shape(workbook) == {"sheets": 4, "cells": 12000 + 3}
    with pytest.raises(wio.WorkbookLimitError, match="4 sheets exceed"):
        wio.check_workbook_shape(workbook, wio.WorkbookLimits(max_sheets=3))
    with pytest.raises(wio.WorkbookLimitError, match="12000 cells"):
        wio.check_workbook_shape(workbook, wio.WorkbookLimits(max_cells_per_sheet=10000))
    with pytest.raises(wio.WorkbookLimitError, match="above the limit of 11000"):
        wio.check_workbook_shape(workbook, wio.WorkbookLimits(max_cells_total=11000))


def test_the_ddr_service_and_pipeline_refuse_an_oversized_workbook_and_leave_it_unchanged(service, tmp_path):
    from core.import_router import route_file
    from dialogs.excel_import_dialog import has_meaningful_canonical_data
    path = tmp_path / "ddr.xlsx"
    shutil.copyfile(FIXTURES / "synthetic_ddr_golden_a.xlsx", path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(wio.WorkbookLimitError):
        service.extract_file(str(path), limits=wio.WorkbookLimits(max_bytes=10))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        refused = pipe.prepare_import(str(path), profile=_profile({"max_bytes": 10}), route=route_file,
                                      template_matcher=service._auto_match_template,
                                      extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
        accepted = pipe.prepare_import(str(path), profile=_profile(), route=route_file,
                                       template_matcher=service._auto_match_template,
                                       extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    assert isinstance(refused.error, wio.WorkbookLimitError) and refused.extracted is None
    assert "profile syn-limits v3" in str(refused.error)
    assert accepted.error is None and accepted.extracted
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_the_profile_shape_limits_reach_the_extractor_and_legacy_extractors_still_work(service, tmp_path):
    """The pipeline used to check only the file-size limits of the profile; sheets / cells fell back to the
    built-in limits inside the extractor (M213 residual)."""
    from core import isolated_parse
    from core.import_router import route_file
    from dialogs.excel_import_dialog import has_meaningful_canonical_data
    path = tmp_path / "ddr.xlsx"
    shutil.copyfile(FIXTURES / "synthetic_ddr_golden_a.xlsx", path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    kwargs = dict(route=route_file, template_matcher=service._auto_match_template,
                  extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for rule, text in (({"max_sheets": 1}, "sheets exceed"), ({"max_cells_per_sheet": 10}, "cells), above"),
                           ({"max_cells_total": 10}, "above the limit of 10")):
            refused = pipe.prepare_import(str(path), profile=_profile(rule), **kwargs)
            assert isinstance(refused.error, wio.WorkbookLimitError), (rule, refused.error)
            assert text in str(refused.error) and "profile syn-limits v3" in str(refused.error)
            assert refused.extracted is None
        # the profile crosses the isolated-parser boundary with its limits
        dto = isolated_parse.profile_from_dto(isolated_parse.profile_to_dto(_profile({"max_sheets": 1})))
        assert wio.limits_from_profile(dto).max_sheets == 1
        # an injected extractor without ``limits`` keeps working when no profile tightens anything
        calls = []

        def legacy_extract(p):
            calls.append(p)
            return service.extract_file(p)

        accepted = pipe.prepare_import(str(path), profile=_profile(), **dict(kwargs, extract_file=legacy_extract))
    assert accepted.error is None and accepted.extracted and calls == [str(path)]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.fixture
def db():
    import tempfile
    from synthetic_operations import make_file_database
    manager = make_file_database(Path(tempfile.mkdtemp(prefix="m213-")) / "profiles.db")
    yield manager
    manager.engine.dispose()


def test_the_profile_dialog_configures_reloads_and_refuses_limits(db):
    from PySide6.QtWidgets import QApplication
    from core.permissions import permissions
    from dialogs.ddr_profile_dialog import ReportProfileDialog
    QApplication.instance() or QApplication([])
    permissions.set_user({"id": 1, "username": "m213-synthetic", "role": "engineer"})   # conftest restores
    dialog = ReportProfileDialog(db)
    try:
        dialog.key_edit.setText("syn-xlsx")
        dialog.name_edit.setText("Synthetic XLSX")
        assert dialog.max_sheets_spin.value() == 0 and "built-in" in dialog.max_sheets_spin.specialValueText()
        assert "excel_limits" not in dialog.collect_profile().table_rules
        dialog.max_sheets_spin.setValue(12)
        dialog.max_mb_spin.setValue(5)
        stored = dialog.save_version()
        assert stored is not None
        assert stored.table_rules["excel_limits"] == {"max_sheets": 12, "max_bytes": 5 * 1024 * 1024}
        reread = get_profile(db, "syn-xlsx")
        assert wio.limits_from_profile(reread).max_sheets == 12
        dialog.load_profile(None)
        dialog.load_profile(reread)
        assert (dialog.max_sheets_spin.value(), dialog.max_mb_spin.value(), dialog.max_cells_spin.value()) == (12, 5, 0)
        assert dialog.max_sheets_spin.maximum() == wio.HARD_LIMITS.max_sheets   # the UI cannot raise a limit
    finally:
        dialog.deleteLater()
