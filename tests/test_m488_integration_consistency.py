"""M488-M492: integration consistency across the catalogue, replay adapters, well context and dialog text handling.

Static and service-level checks with SYNTHETIC inputs. These tests do not run a Windows desktop and are not a Windows
acceptance test.
"""
from __future__ import annotations

import importlib
import inspect
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import history_replay as hr  # noqa: E402
from core import method_catalogue as mc  # noqa: E402


def _case_entries():
    return [e for e in mc.catalogue() if e.source == "calculation case service"]


# ---- M488: catalogue <-> replay adapters --------------------------------------------------------------------------
def test_every_case_service_in_the_catalogue_has_a_replay_adapter_with_the_same_version():
    entries = _case_entries()
    assert entries
    for entry in entries:
        assert hr.handles(entry.method_id), entry.method_id
        current = hr.ADAPTERS[entry.method_id][2]()
        assert entry.version in current, (entry.method_id, entry.version, current)


def test_no_replay_adapter_is_missing_from_the_catalogue():
    ids = {e.method_id for e in mc.catalogue()}
    assert set(hr.ADAPTERS) - ids == set()


def test_catalogue_ids_unique_and_nothing_self_approved():
    entries = mc.catalogue()
    assert len({e.method_id for e in entries}) == len(entries)
    assert mc.violations(entries) == []
    assert mc.OWNER_APPROVALS == {}


@pytest.mark.parametrize("method", sorted(hr.SERVICE_MODULES))
def test_declared_input_services_share_one_contract(method):
    module = importlib.import_module(hr.SERVICE_MODULES[method][0])
    assert module.METHOD_ID == method
    for name in ("evaluate", "summary_lines", "case_payload", "save_case", "replay_results", "freeze",
                 "inputs_sha256", "LABEL", "METHOD_VERSION", "CALCULATOR"):
        assert hasattr(module, name), (method, name)
    assert issubclass(module.IntegrityError, ValueError)
    assert "APPROVED" not in module.LABEL.replace("NOT APPROVED", "")
    params = inspect.signature(module.save_case).parameters
    assert params["well_id"].kind is inspect.Parameter.KEYWORD_ONLY        # M489: the well is always explicit
    with pytest.raises(module.IntegrityError):
        module.replay_results({"inputs_sha256": {"value": "0" * 64}})


# ---- M489: well context in the W13 entry points ----------------------------------------------------------------------
@pytest.mark.parametrize("name", ["hy_hb_slot_dialog", "hy_surge_hb_dialog", "drilloff_fitted_dialog",
                                  "drilloff_robust_dialog", "dull_grade_dialog", "mse_drilloff_dialog"])
def test_w13_service_dialogs_take_the_selected_well(name):
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    src = inspect.getsource(getattr(EngineeringCalculatorTab, name))
    assert 'well_id=getattr(self, "current_well_id", None)' in src


# ---- M491: typed text is never rendered as rich text in the calculation dialogs -------------------------------------
def test_service_dialog_summaries_are_plain_text():
    from PySide6 import QtWidgets
    from PySide6.QtCore import QCoreApplication, QEvent, Qt

    from core import hydraulics_hb_slot as hb
    from dialogs.engineering_service_dialog import EngineeringServiceDialog, HB_LABELS
    from dialogs.mse_drilloff_dialog import MseDrillOffDialog
    from dialogs.well_control_volumetric_dialog import VolumetricMethodDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialogs = [EngineeringServiceDialog(hb, title="t", labels=HB_LABELS, choices={"transition_criterion": hb.CRITERIA}),
               MseDrillOffDialog({}), VolumetricMethodDialog({})]
    try:
        for dialog in dialogs:
            assert dialog.summary.textFormat() == Qt.PlainText, type(dialog).__name__
        first = dialogs[0]
        first.set_value("flow_rate_gpm", "<b>x</b><img src='file:///etc/passwd'>")
        assert first.run() is None
        assert "<b>x</b>" in first.summary.text()                       # shown literally, not interpreted
    finally:
        for dialog in dialogs:
            dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
