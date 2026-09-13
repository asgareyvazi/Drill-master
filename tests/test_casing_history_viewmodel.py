"""Qt-free test of the casing history dialog's view-model builder.

Only the pure ``build_history_rows`` projection is tested here (no widgets), so
it runs in the shared pytest interpreter without a Qt display.
"""
from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

from dialogs.casing_history_dialog import build_history_rows


def _saved(**kw):
    base = dict(
        id=7, label="Casing Strength", method="M",
        input_snapshot={"parameters": {"od_in": 9.625, "grade": "N-80",
                                        "yield_psi": 80000.0}},
        summary={"burst_rating_psi": 6865.5, "collapse_rating_psi": 4754.0,
                 "pipe_body_yield_lbf": 1085789.0},
        well_id=None, created_at=datetime(2026, 9, 13, 10, 30),
    )
    base.update(kw)
    obj = SimpleNamespace(**base)
    obj.input_parameters = dict(base["input_snapshot"]["parameters"])
    return obj


def test_build_history_rows_projects_fields():
    rows = build_history_rows([_saved()])
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == 7
    assert r["od"] == 9.625
    assert r["grade"] == "N-80"
    assert r["burst"] == 6865.5
    assert r["when"] == "2026-09-13 10:30"


def test_build_history_rows_handles_empty_and_missing():
    assert build_history_rows([]) == []
    sparse = _saved(summary={}, input_snapshot={"parameters": {}})
    sparse.input_parameters = {}
    rows = build_history_rows([sparse])
    assert rows[0]["od"] is None
    assert rows[0]["grade"] == "—"
    assert rows[0]["burst"] is None
