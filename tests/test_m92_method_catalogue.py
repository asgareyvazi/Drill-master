"""M92: Method Catalogue over every method source; read-only UI (Help menu); no self-approval.

Synthetic data only. Offscreen Qt (real MainWindow from the M70 module fixture).
"""
from __future__ import annotations

import ast
import csv
import dataclasses
import os
from pathlib import Path
from types import MappingProxyType

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QAbstractItemView, QPushButton  # noqa: E402

from core import calculation_cases as cases  # noqa: E402
from core import calculator_contracts as contracts  # noqa: E402
from core import method_catalogue as mc  # noqa: E402
from core import specialist_methods as sm  # noqa: E402
from core import well_plan_designer as wpd  # noqa: E402
from test_m70_selection_audit import _pump, window  # noqa: E402,F401  (module fixture reused)

ROOT = Path(__file__).resolve().parents[1]


def _engine_methods():
    """Engine classes with a METHOD attribute, discovered from the source independently of the catalogue."""
    found = {}
    for path in sorted((ROOT / "core" / "engineering" / "engines").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and any(
                    isinstance(s, ast.Assign) and any(getattr(t, "id", "") == "METHOD" for t in s.targets)
                    for s in node.body):
                found[node.name] = f"core/engineering/engines/{path.name}"
    return found


def test_every_registry_is_in_the_catalogue_with_versions_from_the_code():
    entries = mc.catalogue()
    by_id = {e.method_id: e for e in entries}
    assert mc.violations(entries) == []
    assert {e.module for e in entries if e.source == "engine"} >= set(_engine_methods().values())
    for contract in contracts.CONTRACTS.values():
        assert by_id[contract.method_id].version == contract.method_version
    assert by_id[contracts.QUICK_CALC_V1.method_id + " (legacy)"].version == contracts.QUICK_CALC_V1.method_version
    unsupported = {e.title for e in entries if e.status == "NOT SUPPORTED"}
    assert unsupported == set(contracts.NOT_SUPPORTED)
    for method in sm.METHODS:
        assert by_id[method.method_id].status == method.status and by_id[method.method_id].licence == method.licence
    from core.engineering.engines.casing import CasingEngine
    assert by_id["engine.casing"].version == CasingEngine.METHOD
    assert by_id["directional.target_solver"].version == wpd.SOLVER_VERSION
    assert by_id["engine.anti_collision"].label == "SCREENING"
    assert "NO ISCWSA UNCERTAINTY" in by_id["directional.plan_vs_actual"].limits


def test_no_self_approval():
    entries = mc.catalogue()
    assert all(e.approval == mc.NOT_APPROVED and "owner engineering approval" in e.blockers for e in entries)
    with pytest.raises(TypeError):
        mc.OWNER_APPROVALS["engine.mse"] = "self"                       # immutable at runtime
    assert not hasattr(mc, "approve") and not hasattr(mc.CatalogueEntry, "approve")


def test_owner_record_is_the_only_approval_path(monkeypatch):
    monkeypatch.setattr(mc, "OWNER_APPROVALS", MappingProxyType({"engine.mse": "owner record 2026-11 (example)",
                                                                  "no.such.method": "x"}))
    entries = mc.catalogue()
    mse = next(e for e in entries if e.method_id == "engine.mse")
    assert mse.approval.startswith("APPROVED — owner record") and "owner engineering approval" not in mse.blockers
    assert mc.violations(entries) == ["no.such.method: approval for an unknown method"]


def test_violations_catch_misleading_entries():
    good = next(e for e in mc.catalogue() if e.method_id == "engine.mse")
    bad = [good, good,
           dataclasses.replace(good, method_id="a", reference=""),
           dataclasses.replace(good, method_id="b", status="VALIDATED"),
           dataclasses.replace(good, method_id="c", status="NOT IMPLEMENTED", blocker=""),
           dataclasses.replace(good, method_id="d", label="FIELD READY"),
           dataclasses.replace(good, method_id="e", version="")]
    found = mc.violations(bad)
    assert found == ["engine.mse: duplicate id", "a: implemented without a reference statement",
                     "b: unknown status 'VALIDATED'", "b: not implemented without a recorded blocker", "c: not implemented without a recorded blocker",
                     "d: unknown label 'FIELD READY'", "e: implemented without version, limits or module"]


def test_usage_counts_and_export(window, tmp_path):  # noqa: F811
    _win, db, ids = window
    qc = contracts.QUICK_CALC
    key = (qc.method_id, qc.method_version)
    before_all, before_alpha = mc.usage(db).get(key, 0), mc.usage(db, ids["alpha"]).get(key, 0)
    for well in (ids["alpha"], ids["alpha"], ids["twin_1"]):
        cases.save_case(db, calculator=qc.calculator, name="m92", inputs={"a": 1}, results={"r": 1},
                        method=qc.method_id, method_version=qc.method_version, well_id=well)
    entry = next(e for e in mc.catalogue() if e.method_id == qc.method_id)
    assert mc.usage_for(entry, mc.usage(db)) == before_all + 3
    assert mc.usage_for(entry, mc.usage(db, ids["alpha"])) == before_alpha + 2      # per well, not the total
    assert mc.usage_for(next(e for e in mc.catalogue() if e.method_id == "engine.mse"), mc.usage(db)) is None
    path = tmp_path / "catalogue.csv"
    assert mc.export_csv(str(path)) == len(mc.catalogue())
    rows = list(csv.reader(open(path, encoding="utf-8")))
    assert rows[1] == ["# status", "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"]
    assert rows[2] == list(mc.COLUMNS) and len(rows) == 3 + len(mc.catalogue())


def test_help_menu_opens_a_read_only_catalogue(window, tmp_path):  # noqa: F811
    win, db, ids = window
    action = next(a for menu in win.menuBar().actions() if menu.menu() is not None
                  for a in menu.menu().actions() if a.text() == "📐 Method Catalogue")
    action.trigger()
    _pump(0.2)
    dialog = win._method_catalogue
    try:
        assert dialog.isVisible() and dialog.table.rowCount() == len(mc.catalogue())
        assert dialog.table.editTriggers() == QAbstractItemView.NoEditTriggers
        assert not [b.text() for b in dialog.findChildren(QPushButton) if "approv" in b.text().lower()]
        dialog.status.setCurrentText("NOT SUPPORTED")
        assert dialog.table.rowCount() == len(contracts.NOT_SUPPORTED)
        dialog.status.setCurrentText("All")
        dialog.search.setText("Teale")
        assert {e.method_id for e in dialog.shown} >= {"engine.mse"}
        dialog.search.setText(contracts.QUICK_CALC.method_id)
        dialog.table.selectRow([e.method_id for e in dialog.shown].index(contracts.QUICK_CALC.method_id))
        text = dialog.details.toPlainText()
        assert "Approval: NOT APPROVED — OWNER REVIEW REQUIRED" in text and "stored case(s) in this database" in text
        assert dialog.export(str(tmp_path / "shown.csv")) == len(dialog.shown) == 1
    finally:
        dialog.close()
        _pump(0.1)
    from dialogs.method_catalogue_dialog import MethodCatalogueDialog
    scoped = MethodCatalogueDialog(db, ids["alpha"])
    entry = next(e for e in scoped.entries if e.method_id == contracts.QUICK_CALC.method_id)
    assert "for the selected well" in scoped.usage_text(entry)
    assert MethodCatalogueDialog(None).usage_text(entry) == "no database open"
    scoped.deleteLater()
