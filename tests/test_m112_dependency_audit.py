"""M112: dependency and licence audit - every pinned package with its declared licence, every third-party
import declared or guarded, no GPL Qt binding in a PySide6 product (D30), copyleft as owner gates, the
catalogue evidence count, and the owner decision packs.

Read-only: nothing is installed or downloaded.  Synthetic workbook only for the D30 behaviour test.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dependency_audit", ROOT / "tools" / "quality" / "dependency_audit.py")
da = importlib.util.module_from_spec(spec)
spec.loader.exec_module(da)
COMMITTED = json.loads(da.OUT.read_text(encoding="utf-8"))
PACKS = (ROOT / "docs" / "engineering" / "M112_OWNER_DECISION_PACKS.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def audit():
    return da.build()


def test_the_committed_audit_is_current_and_has_no_failure(audit):
    for key in ("version", "declared", "lock", "optional_imports", "imports", "findings"):
        assert audit[key] == COMMITTED[key], key
    assert audit["catalogue"]["entries"] == COMMITTED["catalogue"]["entries"]
    assert [f for f in audit["findings"] if f["level"] == "FAIL"] == []


def test_every_pinned_package_has_a_licence_class_and_copyleft_is_an_owner_gate(audit):
    rows = {r["distribution"]: r for r in audit["lock"]}
    assert set(rows) == {name for name, _v in da._lock()} and len(rows) == 26
    assert all(r["class"] != "unknown" and r["licence"] for r in rows.values())
    assert rows["PyMuPDF"]["class"] == "strong copyleft (AGPL)" and rows["PyMuPDF"]["owner_gate"]
    for name in ("PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6"):
        assert rows[name]["class"] == "weak copyleft (LGPL)" and rows[name]["owner_gate"]
    assert all(not r["owner_gate"] for r in rows.values() if r["class"] == "permissive")
    assert "PyMuPDF" in audit["declared"]                     # pre-existing mandatory dependency, not removed


def test_optional_imports_are_guarded_and_gated_and_never_installed(audit):
    modules = {i["module"] for i in audit["imports"]}
    assert modules - set(da.DECLARED_IMPORTS) <= set(da.OPTIONAL_IMPORTS)
    assert all(i["guarded"] for i in audit["imports"] if i["module"] in da.OPTIONAL_IMPORTS)
    optional = {o["module"]: o for o in audit["optional_imports"]}
    assert optional["torque_drag"]["class"] == "weak copyleft (LGPL)"
    assert optional["qtribbon"]["class"] == "unknown"
    for module in ("rapidocr", "pytesseract", "camelot", "torch", "welleng", "torque_drag"):
        assert importlib.util.find_spec(module) is None, module      # owner gates: not installed here


def test_the_guard_detector_flags_an_unguarded_or_forbidden_import(tmp_path):
    (tmp_path / "core").mkdir()
    sample = tmp_path / "core" / "sample.py"
    sample.write_text("import rapidocr\ntry:\n    import welleng\nexcept ImportError:\n    welleng = None\n"
                      "def f():\n    from PyQt5.QtWidgets import QInputDialog\n    import mysterylib\n",
                      encoding="utf-8")
    imports = da.scan_imports(tmp_path, [sample])
    assert {(i["module"], i["guarded"]) for i in imports} == {
        ("rapidocr", False), ("welleng", True), ("PyQt5", False), ("mysterylib", False)}
    findings = sorted(f["finding"] for f in da.findings_for(imports))
    assert all(f["level"] == "FAIL" for f in da.findings_for(imports)) and len(findings) == 3
    assert findings[0].startswith("PyQt5: GPL-3.0")                          # forbidden binding
    assert findings[1] == "optional rapidocr is imported without an ImportError guard"
    assert findings[2] == "undeclared third-party import mysterylib"


def test_no_pyqt_import_anywhere_in_the_product():
    for path in da.product_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        assert not [n for n in names if n.split(".")[0] in ("PyQt5", "PyQt6")], path


def test_d30_the_vendor_workbook_sheet_is_chosen_with_the_pyside6_dialog(tmp_path, monkeypatch):
    from openpyxl import Workbook
    from PySide6 import QtWidgets

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import tabs.w13_Engineering_Calculator as w13
    import core.engineering.drill_pipe_import as dpi

    book = Workbook()
    book.active.title = "Cover"
    book.create_sheet("Aa")
    path = tmp_path / "SYN_vendor.xlsx"
    book.save(path)
    asked, imported, shown = [], [], []
    monkeypatch.setattr(w13.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))
    monkeypatch.setattr(w13.QInputDialog, "getItem",
                        staticmethod(lambda parent, title, label, items, current, editable:
                                     asked.append((list(items), current)) or ("Aa", True)))
    monkeypatch.setattr(w13.QMessageBox, "information", staticmethod(lambda *a: shown.append(a[2])))
    monkeypatch.setattr(w13.QMessageBox, "critical", staticmethod(lambda *a: shown.append(a[2])))
    result = SimpleNamespace(as_dict=lambda: {"parse": {"source": "SYN", "sheet": "Aa", "data_rows": 0},
                                              "blank_rows": 0, "inserted": 0, "unchanged": 0, "enriched": 0,
                                              "conflicting": 0, "invalid": 0})
    monkeypatch.setattr(dpi, "import_workbook", lambda repo, p, sheet=None: imported.append(sheet) or result)
    stub = SimpleNamespace(_drill_pipe_reference_repo=lambda: object(), _refresh_reference_catalog_view=lambda: None)
    w13.EngineeringCalculatorTab._wt_import_reference_catalog(stub)
    assert asked == [(["Cover", "Aa"], 1)]                    # the user is asked; "Aa" preselected
    assert imported == ["Aa"] and "sheet 'Aa'" in shown[0]
    assert w13.QInputDialog.__module__.startswith("PySide6")


def test_the_lgpl_adapter_returns_nothing_without_the_package():
    from core.engineering.adapters.torque_drag_adapter import TorqueDragAdapter

    assert TorqueDragAdapter.available() is False and TorqueDragAdapter.calculate(1, 2) is None


def test_catalogue_evidence_is_counted_per_method(audit):
    from core import method_catalogue as mc

    rows = audit["catalogue"]["rows"]
    assert [r["method_id"] for r in rows] == [e.method_id for e in mc.catalogue()]
    assert audit["catalogue"]["entries"] == len(rows) == 54 and audit["catalogue"]["approved"] == 0
    assert all(r["approval"] == "NOT APPROVED — OWNER REVIEW REQUIRED" for r in rows)
    missing = audit["catalogue"]["without_test_evidence"]
    assert missing == [r["method_id"] for r in rows if r["evidence_tests"] == 0]
    assert all(next(e for e in mc.catalogue() if e.method_id == m).status != "IMPLEMENTED" for m in missing)


def test_owner_packs_cover_every_gate_and_offer_no_approval():
    for title in ("ISCWSA / welleng", "pwptemp", "torque_drag", "PyMuPDF", "OCR", "Kill sheet", "Cost / currency",
                  "Hydraulics", "7.48", "Datum / CRS", "Qt for Python", "qtribbon"):
        assert f"## Pack — {title}" in PACKS or title in PACKS, title
    assert PACKS.count("**Decision needed:**") >= 10 and "No approval is recorded by this document" in PACKS
    from core import method_catalogue as mc
    assert not hasattr(mc, "approve") and not hasattr(mc, "set_approval")
