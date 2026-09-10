"""Phase 1 P0 regressions (2026-09-09 session).

Each test pins a defect confirmed by the forensic audit:

1. ``CodeResolver`` was referenced at ``core/profile_import_engine.py`` (time-log
   extraction) without any import in scope: the resulting NameError was swallowed
   by ``except Exception`` and every NPT row silently lost its contractor.
2. Several profile-engine readers indexed the sheet cache with flat tuple keys
   while the only cache builder produces ``{row: {col: value}}`` — the workbook
   code catalog and embedded mud-chemical extraction were dead code.
3. ``core.validators.ImportValidator`` claimed to delegate to
   ``core.import_quality.ImportValidator`` but implemented an incompatible
   signature. It now really delegates.
4. ``object.__new__(ExcelImportDialog)`` raises TypeError under real (shiboken)
   Qt classes; construction must use ``ExcelImportDialog.__new__``.
"""

import os
import sys

import pytest


def _qt_gui_importable() -> bool:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import PySide6.QtWidgets  # noqa: F401

        return True
    except Exception:
        return False


def _row_cache_time_logs():
    from core.profile_import_engine import ProfileImportEngine

    engine = ProfileImportEngine(None)
    engine.cell_cache = {
        "Time Logs": {
            1: {1: "From", 2: "To", 3: "Hrs", 4: "Main Phase", 5: "Code",
                6: "Sub", 7: "Status", 8: "NPT", 9: "Rig Activity"},
            2: {1: "00:00", 2: "06:00", 3: 6, 4: "Drilling", 5: 1, 6: "1.1",
                7: "PLN", 9: "Drill ahead"},
            3: {1: "06:00", 2: "08:00", 3: 2, 4: "Repair", 5: 2, 6: "2.1",
                7: "ACT", 8: "RR", 9: "Rig repair"},
        },
    }
    return engine


class TestCodeResolverContractorRegression:
    def test_npt_row_resolves_contractor(self):
        """An NPT row must get its contractor from CodeResolver.

        Before the fix this raised NameError inside a bare except and
        silently stored ``contractor: ""``.
        """
        if not _qt_gui_importable():
            pytest.skip("PySide6 GUI modules cannot load in this environment")
        engine = _row_cache_time_logs()
        logs = engine._extract_time_logs("Time Logs")
        assert len(logs) == 2
        assert logs[0]["is_npt"] is False
        assert logs[0]["contractor"] == ""
        npt = logs[1]
        assert npt["is_npt"] is True
        assert npt["contractor"] == "Rig Contractor", (
            "NPT contractor was silently dropped (swallowed NameError)"
        )

    def test_extraction_survives_unavailable_code_resolver(self, monkeypatch):
        """Without the Qt dialog layer the engine must degrade explicitly.

        The row must still be extracted (no crash, no lost data) and the
        contractor stays empty *because the resolver is unavailable*, never
        because of a swallowed NameError.
        """
        monkeypatch.setitem(sys.modules, "dialogs.smart_template_dialog", None)
        engine = _row_cache_time_logs()
        logs = engine._extract_time_logs("Time Logs")
        assert len(logs) == 2
        assert logs[1]["is_npt"] is True
        assert logs[1]["contractor"] == ""


class TestProfileEngineCacheShapeRegression:
    """The sheet cache is {row: {col: value}}; every reader must honor it."""

    def test_workbook_code_catalog_configured_from_row_cache(self):
        """_configure_workbook_code_catalog was dead code (tuple-key reads)."""
        if not _qt_gui_importable():
            pytest.skip("PySide6 GUI modules cannot load in this environment")
        from core.profile_import_engine import ProfileImportEngine

        engine = ProfileImportEngine(None)
        engine.cell_cache = {
            "Activity Codes": {
                2: {1: 1, 2: "1.1", 3: "Drilling"},
                3: {1: 2, 2: "2.1", 3: "Circulate"},
            },
        }
        try:
            engine._configure_workbook_code_catalog()
            from dialogs.smart_template_dialog import MAIN_CODE_MAP, SUB_CODE_MAP

            assert MAIN_CODE_MAP.get("1") == "Drilling"
            assert SUB_CODE_MAP.get("1.1") == "Drilling"
            assert SUB_CODE_MAP.get("2.1") == "Circulate"
        finally:
            # configure_catalog mutates process-global maps; restore defaults.
            from dialogs.smart_template_dialog import CodeResolver

            CodeResolver.configure_catalog({}, {})

    def test_embedded_mud_chemicals_extracted_from_row_cache(self):
        """_extract_embedded_mud_chemicals was dead code (tuple-key reads)."""
        from core.profile_import_engine import ProfileImportEngine

        engine = ProfileImportEngine(None)
        engine.cell_cache = {
            "DDR Data": {
                5: {2: "Mud Chemical"},
                6: {1: "Product Type", 2: "Used", 3: "Received", 4: "On Hand", 5: "Unit"},
                7: {1: "Bentonite", 2: 10, 3: 5, 4: 100, 5: "kg"},
            },
        }
        result = {"bulk_materials": []}
        engine._extract_embedded_mud_chemicals(result)
        assert result["bulk_materials"], "embedded mud chemicals were silently dropped"
        row = result["bulk_materials"][0]
        assert row["material_name"] == "Bentonite"
        assert row["initial_stock"] == 100
        assert row["used"] == 10
        assert row["received"] == 5
        assert row["current_stock"] == pytest.approx(95.0)


class TestImportValidatorSingleContract:
    def test_validators_alias_delegates_to_canonical(self):
        from core.import_quality import ImportValidator as Canonical
        from core.validators import ImportValidator as Legacy

        assert Legacy is not Canonical
        assert issubclass(Legacy, Canonical), (
            "core.validators.ImportValidator must delegate to "
            "core.import_quality.ImportValidator (documented deprecated alias)"
        )

    def test_alias_behaves_identically(self):
        from core.import_quality import ImportValidator as Canonical
        from core.validators import ImportValidator as Legacy

        rows = [{"report_date": ""}, {"report_date": "2024-01-01"}]
        a = Legacy.validate_rows(list(rows), "daily_report", "SheetA")
        b = Canonical.validate_rows(list(rows), "daily_report", "SheetA")
        assert a.total == b.total == 2
        assert a.failed == b.failed
        assert [str(i) for i in a.issues] == [str(i) for i in b.issues]


class TestDialogConstructionSafety:
    def test_new_construction_is_safe_under_real_qt(self):
        """ExcelImportDialog.__new__(cls) must work with real shiboken types.

        ``object.__new__(ExcelImportDialog)`` raises TypeError once the class
        derives from a real QDialog — the construction pattern used by the
        golden import tests must therefore be ``cls.__new__(cls)``.
        """
        if not _qt_gui_importable():
            pytest.skip("PySide6 GUI modules cannot load in this environment")
        from dialogs.excel_import_dialog import ExcelImportDialog

        dialog = ExcelImportDialog.__new__(ExcelImportDialog)

        class CaptureDB:
            def __init__(self):
                self.payload = None

            def save_drilling_parameters(self, payload, session=None):
                self.payload = payload
                return True

        dialog.well_id = 17
        dialog.db = CaptureDB()
        from datetime import date

        dialog._save_drilling_params(
            {"nozzle1_no": None, "nozzle1_size": "18/32"},
            report_id=23,
            report_date=date(2025, 10, 27),
        )
        assert dialog.db.payload["well_id"] == 17
        assert dialog.db.payload["report_id"] == 23


class TestCodeResolverImportGuardNarrowed:
    """The lazy ``CodeResolver`` import must degrade only on ImportError.

    A missing Qt/dialog module legitimately degrades to "resolver
    unavailable" (headless runs). A broken dialog module — e.g. one raising
    ``SyntaxError`` — must propagate instead of being silently masked as
    "unavailable", which would silently drop NPT contractor resolution.
    """

    def _engine_with_empty_cache(self):
        from core.profile_import_engine import ProfileImportEngine

        engine = ProfileImportEngine(None)
        # A sheet without a recognizable header: extraction stops right
        # after the lazy import guard, so we exercise the guard in isolation.
        engine.cell_cache = {"Time Logs": {1: {1: "no", 2: "header", 3: "here"}}}
        return engine

    def test_syntax_error_in_dialog_module_propagates(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def _raise_syntax(name, *args, **kwargs):
            if "smart_template_dialog" in name:
                raise SyntaxError("broken dialog module")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _raise_syntax)
        engine = self._engine_with_empty_cache()
        with pytest.raises(SyntaxError):
            engine._extract_time_logs("Time Logs")

    def test_import_error_still_degrades_to_unavailable(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def _raise_import(name, *args, **kwargs):
            if "smart_template_dialog" in name:
                raise ImportError("no Qt in this environment")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _raise_import)
        engine = self._engine_with_empty_cache()
        assert engine._extract_time_logs("Time Logs") == []
