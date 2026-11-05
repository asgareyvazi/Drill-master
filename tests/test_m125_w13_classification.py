"""M125: every W13 leaf is classified - CONTRACT / SCREENING CONTRACT / WORKSHEET / TRAINING AID /
REFERENCE-ONLY / NOT_SUPPORTED - separately from whether its cases can be re-run.

The classification is source-backed (a SCREENING or WORKSHEET class only where the contract's own limits
say so; TRAINING AID / REFERENCE-ONLY / NOT_SUPPORTED only for leaves without a contract) and reaches the
user through the real W13 case bar, Calc History and the Method Catalogue. Offscreen Qt, synthetic DB.
"""
from __future__ import annotations

import os
from collections import Counter

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from core import calculation_cases as cc  # noqa: E402
from core import calculation_history as ch  # noqa: E402
from core import calculator_contracts as contracts  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def w13(app, db):  # noqa: F811
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab(db)
    yield tab
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _leaves(w13):
    from tabs.calculator_finder import build_index
    paths = [e.path for e in build_index(w13.tabs)]
    return [p for p in paths if not any(o != p and o.startswith(p + " › ") for o in paths)]


def test_all_27_real_leaves_are_classified_consistently_with_the_registry(w13):
    leaves = _leaves(w13)
    assert len(leaves) == 27 and set(contracts.LEAF_CLASSES) == set(leaves)
    assert contracts.classification_violations() == []
    assert Counter(contracts.LEAF_CLASSES.values()) == {
        contracts.CLASS_CONTRACT: 9, contracts.CLASS_SCREENING: 10, contracts.CLASS_WORKSHEET: 3,  # M126 +2, M127 +2
        contracts.CLASS_TRAINING: 1, contracts.CLASS_REFERENCE: 1, contracts.CLASS_NOT_SUPPORTED: 3}
    assert contracts.leaf_class("DP Database")[0] == contracts.CLASS_REFERENCE
    assert contracts.leaf_class("Well Control › Kill Sheet")[0] == contracts.CLASS_TRAINING
    assert contracts.leaf_class("Directional › Anti-Collision")[0] == contracts.CLASS_NOT_SUPPORTED
    assert contracts.leaf_class("Volume › Nothing")[0] == "UNKNOWN"
    for cls, meaning in contracts.LEAF_CLASS_MEANING.items():
        assert len(meaning) > 30, cls
    assert "not a design value" in contracts.LEAF_CLASS_MEANING[contracts.CLASS_SCREENING]
    assert "NOT REPRODUCIBLE" in contracts.LEAF_CLASS_MEANING[contracts.CLASS_NOT_SUPPORTED]


def test_a_relabelled_screening_contract_is_a_violation(monkeypatch):
    """The guard is real: calling a SCREENING contract a CONTRACT (or a missing leaf) is reported."""
    changed = dict(contracts.LEAF_CLASSES, **{"Mud › Rheology": contracts.CLASS_CONTRACT})
    monkeypatch.setattr(contracts, "LEAF_CLASSES", changed)
    assert any("Mud › Rheology" in v for v in contracts.classification_violations())
    changed = dict(contracts.LEAF_CLASSES)
    changed.pop("Hydraulics")
    monkeypatch.setattr(contracts, "LEAF_CLASSES", changed)
    assert any("Hydraulics" in v for v in contracts.classification_violations())
    changed = dict(contracts.LEAF_CLASSES, **{"Volume › Quick Calc": contracts.CLASS_SCREENING})
    monkeypatch.setattr(contracts, "LEAF_CLASSES", changed)
    assert any("Quick Calc" in v and "do not say SCREENING" in v for v in contracts.classification_violations())
    changed = dict(contracts.LEAF_CLASSES, **{"Mud › OWR": contracts.CLASS_WORKSHEET})
    monkeypatch.setattr(contracts, "LEAF_CLASSES", changed)
    assert any("OWR" in v and "do not say WORKSHEET" in v for v in contracts.classification_violations())
    changed = dict(contracts.LEAF_CLASSES, **{"Directional › Multi-Survey": contracts.CLASS_SCREENING})
    monkeypatch.setattr(contracts, "LEAF_CLASSES", changed)       # M127: Weight is contracted; Multi-Survey is not
    assert any("Multi-Survey" in v and "no contract" in v for v in contracts.classification_violations())


def test_the_case_bar_shows_the_class_and_dp_database_saves_nothing(w13):
    assert w13.calculator_finder.open_path("Mud › Rheology")
    w13.case_bar.refresh()
    assert "Class: SCREENING CONTRACT" in w13.case_bar.contract_label.text()
    assert "Contract status: CONTRACT" in w13.case_bar.contract_label.text()
    assert w13.case_bar.save_btn.isEnabled()
    assert w13.calculator_finder.open_path("DP Database")
    w13.case_bar.refresh()
    assert "Class: REFERENCE-ONLY" in w13.case_bar.contract_label.text()
    assert not w13.case_bar.save_btn.isEnabled()
    before = len(cc.list_cases(w13.db))
    assert w13.case_bar.save_case("SYN dp") is None
    assert "REFERENCE-ONLY" in w13.case_bar.status.text() and len(cc.list_cases(w13.db)) == before
    assert w13.calculator_finder.open_path("Well Control › Kill Sheet")
    w13.case_bar.refresh()
    assert "Class: TRAINING AID" in w13.case_bar.contract_label.text()


def test_a_saved_screening_case_carries_its_class_into_calc_history(w13):
    assert w13.calculator_finder.open_path("Stuck Pipe")
    w13.stk_stretch_in.setValue(20.0)
    w13.stk_wt.setValue(19.5)
    w13.stk_pull.setValue(50000.0)
    w13._update_stuck()
    case = w13.case_bar.save_case("SYN stuck")
    entry = next(e for e in ch.load_history(w13.db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert entry.scope == "W13 CALCULATOR — SCREENING CONTRACT"
    assert ch.recalculate_entry(entry)["status"] == "MATCH"


def test_the_method_catalogue_labels_follow_the_classification():
    from core import method_catalogue as mc
    entries = {e.title: e for e in mc.catalogue() if e.family == "W13 calculator"}
    assert entries["DP Database"].label == "REFERENCE-ONLY"
    assert entries["Well Control › Kill Sheet"].label == "TRAINING AID"
    assert entries["Mud › Volume Balance"].label == "WORKSHEET"
    assert entries["Mud › Rheology"].label == "SCREENING"
    assert entries["Volume › Quick Calc"].label == ""
    assert mc.violations(list(mc.catalogue())) == []
