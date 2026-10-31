"""M52 balanced plug (CementEngine.balanced_plug).

References are independent of the implementation's constant and formula
wording: capacities from circle geometry (pi/4 x (D/12)^2 ft^2 / 5.6146 ft^3
per bbl), and the physical balance conditions - equal cement height inside and
outside, equal spacer heights, displacement = pipe volume above the spacer.
Synthetic example values only.
"""
from __future__ import annotations

import math

import pytest

from core.engineering.engines.cement import CementEngine


def geometric_capacity(d_in):
    return math.pi / 4 * (d_in / 12) ** 2 / 5.6146


CASE = dict(hole_size_in=8.75, pipe_od_in=3.5, pipe_id_in=2.764, plug_length_ft=500, plug_bottom_md_ft=9000,
            excess_pct=20, spacer_ahead_bbl=10)


def test_hand_reference_from_geometry_and_balance_conditions():
    result = CementEngine.balanced_plug(**CASE)
    assert result.success, result.error
    v = result.values
    ch, cp = geometric_capacity(8.75), geometric_capacity(2.764)
    ca = ch - geometric_capacity(3.5)
    volume = 500 * ch * 1.2
    assert v["slurry_volume_bbl"] == pytest.approx(volume, rel=1e-4)
    h = v["column_height_pipe_in_ft"]
    assert h * ca + h * cp == pytest.approx(volume, rel=1e-4)              # same height inside and outside
    assert v["spacer_behind_bbl"] / cp == pytest.approx(10 / ca, rel=1e-4)   # equal spacer heights
    pipe_above_spacer = cp * (9000 - h - v["spacer_height_ft"])
    assert v["displacement_bbl"] == pytest.approx(pipe_above_spacer, rel=1e-4)
    assert v["top_after_pull_gauge_md_ft"] == pytest.approx(9000 - volume / ch, abs=0.05)
    assert result.method == "M52 balanced plug v1" and result.scope == "SCREENING"
    assert any("Static volumetrics" in a for a in result.assumptions)


def test_no_excess_plug_top_lands_on_the_design_top_after_pulling():
    result = CementEngine.balanced_plug(**{**CASE, "excess_pct": 0})
    assert result.values["top_after_pull_gauge_md_ft"] == pytest.approx(8500.0, abs=0.01)


def test_sacks_are_rounded_up_and_only_with_a_yield():
    with_yield = CementEngine.balanced_plug(**CASE, slurry_yield_ft3_sk=1.06)
    ft3 = with_yield.values["slurry_volume_ft3"]
    assert with_yield.values["sacks"] == math.ceil(ft3 / 1.06 - 1e-6)
    assert "sacks" not in CementEngine.balanced_plug(**CASE).values


def test_under_displacement_reduces_displacement_and_warns():
    base = CementEngine.balanced_plug(**CASE).values["displacement_bbl"]
    under = CementEngine.balanced_plug(**CASE, underdisplacement_bbl=2)
    assert under.values["displacement_bbl"] == pytest.approx(base - 2, abs=0.002)
    assert under.warnings and "not exactly balanced" in under.warnings[0]


@pytest.mark.parametrize("change, message", [
    ({"pipe_id_in": 3.6}, "Pipe ID must be smaller"),
    ({"pipe_od_in": 9.0}, "smaller than the hole"),
    ({"plug_length_ft": 0}, "Plug length"),
    ({"plug_bottom_md_ft": 400}, "deeper than the plug length"),
    ({"excess_pct": -1}, "Excess"),
    ({"spacer_ahead_bbl": -1}, "cannot be negative"),
    ({"plug_bottom_md_ft": 600, "spacer_ahead_bbl": 50}, "above surface"),
    ({"hole_size_in": 0}, "must be > 0"),
])
def test_invalid_inputs_fail_with_the_reason(change, message):
    result = CementEngine.balanced_plug(**{**CASE, **change})
    assert not result.success and message in result.error


def test_missing_and_non_numeric_inputs_are_missing_not_zero():
    for change in ({"pipe_id_in": None}, {"plug_length_ft": "abc"}):
        result = CementEngine.balanced_plug(**{**CASE, **change})
        assert not result.success and not result.values and result.value is None, change


def test_displacement_that_would_be_negative_is_refused():
    result = CementEngine.balanced_plug(**CASE, underdisplacement_bbl=10_000)
    assert not result.success and "Displacement" in result.error


# ---- history persistence (Qt-free) and the W13 tab (isolated subprocess) ---------------------------
def test_a_saved_plug_run_reconstructs_and_verifies_from_its_snapshot():
    from core.engineering.cement_persistence import build_snapshot, recalculate_from_snapshot, result_summary
    inputs = {**CASE, "underdisplacement_bbl": 1.0, "slurry_yield_ft3_sk": 1.06}
    result = CementEngine.balanced_plug(**inputs)
    snapshot = build_snapshot(inputs=inputs, method=result.method)
    assert set(snapshot["parameters"]) == set(inputs)              # exactly the plug engine's arguments
    again = recalculate_from_snapshot(snapshot)
    assert again.success and again.values == result.values
    assert result_summary(result.values)["displacement_volume_bbl"] == result.values["displacement_bbl"]
    job_snapshot = build_snapshot(inputs={"hole_size_in": 12.25}, method=CementEngine.METHOD)
    assert "plug_length_ft" not in job_snapshot["parameters"]      # job-volume snapshots are unchanged


_PLUG_CHILD = '''
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from core.database import DatabaseManager, Base
from core.engineering.engines.cement import CementEngine

m = DatabaseManager()
m.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(m.engine)
m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)
from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
tab = EngineeringCalculatorTab(m)
assert tab._plug_save_calculation() is None and tab._cement_repo().count() == 0
tab.plug_pipe_id.setValue(4.0)                    # ID > OD: refused, nothing cached
assert not tab._plug_calculate().success and "NOT CALCULATED" in tab.plug_result.toPlainText()
assert tab._plug_last_run is None
tab.plug_pipe_id.setValue(2.764)
tab.plug_yield.setValue(1.06)
result = tab._plug_calculate()
text = tab.plug_result.toPlainText()
assert result.success and "SCREENING" in text and "cement-calc" in text and "Displacement" in text
first, second = tab._plug_save_calculation(), tab._plug_save_calculation()
assert first and second and first != second
saved = tab._cement_repo().get(first)
assert saved.label == "Balanced Plug" and saved.method == CementEngine.BALANCED_PLUG_VERSION
outcome = saved.verify(current_method=CementEngine.BALANCED_PLUG_VERSION)
assert outcome.status == "MATCH", outcome.status
print("PLUG_TAB_OK")
'''


def test_w13_balanced_plug_tab_calculates_and_saves_in_subprocess():
    import os
    import subprocess
    import sys
    pytest.importorskip("PySide6")
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, "-c", _PLUG_CHILD], cwd=root, env=env, capture_output=True,
                          text=True, timeout=180)
    assert proc.returncode == 0 and "PLUG_TAB_OK" in proc.stdout, (proc.returncode, proc.stdout[-2000:],
                                                                    proc.stderr[-3000:])
