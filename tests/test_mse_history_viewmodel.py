"""Qt-free test of the MSE history dialog's view-model builder.

Only the pure ``build_history_rows`` projection is tested here (no widgets), so
it runs in the shared pytest interpreter without a Qt display.
"""
from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

from dialogs.mse_history_dialog import build_history_rows


def _saved(**kw):
    base = dict(
        id=9, label="MSE (Teale)", method="M",
        input_snapshot={"parameters": {"wob_lbf": 25000.0,
                                        "rpm": 120.0,
                                        "torque_ft_lbf": 8000.0,
                                        "rop_ft_hr": 30.0,
                                        "bit_diameter_in": 8.5}},
        summary={"mse_psi": 41234.0, "axial_term_psi": 440.0,
                 "rotary_term_psi": 40794.0, "bit_area_in2": 56.7},
        well_id=None, created_at=datetime(2026, 9, 19, 8, 15),
    )
    base.update(kw)
    obj = SimpleNamespace(**base)
    obj.input_parameters = dict(base["input_snapshot"]["parameters"])
    return obj


def test_build_history_rows_projects_fields():
    rows = build_history_rows([_saved()])
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == 9
    assert r["wob"] == 25000.0
    assert r["rpm"] == 120.0
    assert r["rop"] == 30.0
    assert r["bit"] == 8.5
    assert r["mse"] == 41234.0
    assert r["when"] == "2026-09-19 08:15"


def test_build_history_rows_handles_empty_and_missing():
    assert build_history_rows([]) == []
    sparse = _saved(summary={}, input_snapshot={"parameters": {}})
    sparse.input_parameters = {}
    rows = build_history_rows([sparse])
    assert rows[0]["wob"] is None
    assert rows[0]["mse"] is None
    assert rows[0]["bit"] is None
