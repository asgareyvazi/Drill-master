"""M138: user-visible states of the six M130-M135 workbench panels, measured on the real widgets.

``tools/quality/ux_states_m138.py`` drives every panel through its public API (the 3D layer panel inside the
trajectory viewer) in a left-to-right and a right-to-left run: no well, a well without records, a well with
records, a failing background job and its Retry. Offscreen Linux, SYNTHETIC data - NOT Windows desktop evidence;
no timing threshold is asserted (the numbers go to ``docs/mission-reports/m140-evidence/ux_m138.json``).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))

import ux_states_m138 as ux  # noqa: E402

from tests.test_m70_integrity import _open  # noqa: E402
from tests.test_m123_mse_lineage import _as_admin  # noqa: E402

EVIDENCE = ROOT / "docs" / "mission-reports" / "m140-evidence" / "ux_m138.json"
PANELS = [cls.name for cls in ux.ADAPTERS]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    folder = tmp_path_factory.mktemp("m138")
    with pytest.MonkeyPatch.context() as mp:
        path = folder / "m138.sqlite"
        manager = _open(path, folder, mp)
        world = ux.build_world(manager)
        _as_admin(manager, path)
        try:
            result = {rtl: {p["panel"]: p for p in ux.measure(manager, world, rtl=rtl, out_dir=folder / "out")["panels"]}
                      for rtl in (False, True)}
        finally:
            manager.close()
    assert app is not None
    return result


def _each(runs):
    for rtl, panels in runs.items():
        for name in PANELS:
            yield rtl, name, panels[name]


def test_every_panel_was_measured_in_both_directions(runs):
    for rtl in (False, True):
        assert sorted(runs[rtl]) == sorted(PANELS)


def test_no_well_is_an_explicit_not_assessed_never_a_blank(runs):
    for _rtl, name, entry in _each(runs):
        text = entry["none"]["text"]
        assert "NOT ASSESSED: select a well" in text or "select a well" in text, (name, text)


EMPTY_MESSAGES = {
    "BitRunWorkbench": "No DDR row records a bit number.",
    "ParameterTrendPanel": "No drilling-parameter row is recorded in this scope; nothing is drawn.",
    "TrajectoryLayersPanel": "NO DATA | no DDR survey point is recorded",
    "MudEvaluationPanel": "No mud report is recorded in this scope.",
    "NptReconciliationPanel": "No NPT register event or NPT time-log row is recorded in this scope.",
    "WellPackagePanel": "EMPTY",
}


def test_a_well_without_records_says_so(runs):
    for _rtl, name, entry in _each(runs):
        empty = entry["empty"]
        assert empty["delivered"], name
        assert EMPTY_MESSAGES[name] in empty["text"], (name, empty["text"])


def test_the_layer_panel_never_claims_a_drawn_working_survey_without_stations(runs):
    for rtl in (False, True):
        layers = runs[rtl]["TrajectoryLayersPanel"]
        assert "Working survey | DDR survey points | DRAWN" not in layers["empty"]["text"]
        assert "Working survey | DDR survey points | DRAWN | 4 station(s)" in layers["data"]["text"]


DATA_MESSAGES = {
    "BitRunWorkbench": "1 run(s)",
    "ParameterTrendPanel": "2 DDR row(s)",
    "TrajectoryLayersPanel": "DRAWN",
    "MudEvaluationPanel": "1 mud report(s)",
    "NptReconciliationPanel": "2 group(s)",
    "WellPackagePanel": "manifest SHA-256",
}


def test_a_well_with_records_shows_them(runs):
    for _rtl, name, entry in _each(runs):
        data = entry["data"]
        assert data["delivered"] and data["ms"] >= 0, name
        assert DATA_MESSAGES[name] in data["text"], (name, data["text"])
        assert "NOT ASSESSED" not in data["text"].split(" || ")[0], (name, data["text"])
    for rtl in (False, True):
        layers = runs[rtl]["TrajectoryLayersPanel"]["data"]
        assert layers["layers_ok"] and "Survey revision 1" in layers["layers_text"]


def test_a_failed_read_names_the_error_offers_retry_and_retry_recovers(runs):
    for _rtl, name, entry in _each(runs):
        error = entry["error"]
        assert "failed (RuntimeError); nothing is shown. Press Retry." in error["text"], (name, error["text"])
        assert ux.INJECTED not in error["text"]                    # the type is named, the message is not shown
        assert error["retry_visible"], name
        assert error["retry_hidden_after"] and "failed (" not in error["after_retry_text"], (name, error)
    for rtl in (False, True):
        build = runs[rtl]["WellPackagePanel"]["data"]["build_error_text"]
        assert "failed (RuntimeError)" in build and "Build the package again to retry." in build
        assert "Press Retry" not in build                           # the panel has no Retry for a build


def test_every_panel_and_child_follows_the_layout_direction(runs):
    for _rtl, name, entry in _each(runs):
        direction = entry["direction"]
        assert direction["panel"] and direction["children"] > 0, name
        assert direction["not_following"] == [], (name, direction)


def test_trend_axes_carry_their_units(runs):
    for rtl in (False, True):
        axes = runs[rtl]["ParameterTrendPanel"]["data"]["axes"]
        for key in ("parameter", "mse"):
            assert axes[key] is not None, key
            left, bottom = axes[key]["left"], axes[key]["bottom"]
            assert left.endswith(")") and "(" in left, (key, left)
            assert bottom, key
        # MSE is drawn as discrete saved runs (M131), in psi, on the same axis as the parameter view
        assert axes["mse"]["left"] == "MSE — discrete saved runs, not a continuous log (psi)"
        assert axes["parameter"]["left"] == "ROP (average) (m/h)"
        assert axes["mse"]["bottom"] == axes["parameter"]["bottom"] == "Report date (DDR)"


def test_the_committed_evidence_is_labelled_and_complete():
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert data["environment"]["note"] == ux.NOTE
    assert [run["direction"] for run in data["runs"]] == ["ltr", "rtl"]
    for run in data["runs"]:
        assert [p["panel"] for p in run["panels"]] == PANELS
        assert all(p["error"]["retry_visible"] and p["error"]["retry_hidden_after"] for p in run["panels"])


class _MovedSelection:
    """The selection changed while the job ran: its result must be discarded as STALE."""

    @staticmethod
    def context_token():
        return "the selection when the job started"

    @staticmethod
    def is_current(_token):
        return False


def _no_rows(_db, _params, _cancel):
    return []


def test_a_stale_result_names_the_button_the_panels_have(runs):
    from core.context_jobs import STALE, ContextJobRunner
    from tabs.bit_run_panel import BitRunWorkbench
    from tabs.job_retry import REFRESH_HINT
    from tabs.mud_engineering_panel import MudEvaluationPanel
    from tabs.npt_reconciliation_panel import NptReconciliationPanel
    from tabs.parameter_trend_panel import ParameterTrendPanel
    from tabs.trajectory_layers_panel import TrajectoryLayersPanel
    from tabs.well_package_panel import WellPackagePanel

    runner = ContextJobRunner(None, "bit runs", selection=_MovedSelection(), refresh_hint=REFRESH_HINT)
    runner.start(_no_rows, {})                      # no database: the runner computes synchronously
    assert runner.state == STALE and runner.message.endswith(REFRESH_HINT) and "Refresh" not in runner.message
    panels = [cls(None) for cls in (BitRunWorkbench, ParameterTrendPanel, TrajectoryLayersPanel, MudEvaluationPanel,
                                    NptReconciliationPanel)]
    package = WellPackagePanel(None)
    try:
        assert all(p.jobs.refresh_hint == REFRESH_HINT for p in panels)
        assert package.bore_jobs.refresh_hint == REFRESH_HINT
        assert package.jobs.retry_hint == "Build the package again to retry."
        assert package.verify_jobs.retry_hint == "Verify the folder again to retry."
    finally:
        for widget in panels + [package]:
            widget.deleteLater()
