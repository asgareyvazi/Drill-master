"""Qt-free test of the cement history dialog's view-model builder.

Only the pure ``build_history_rows`` projection is tested here (no widgets), so
it runs in the shared pytest interpreter without a Qt display.
"""
from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

from dialogs.cement_history_dialog import build_history_rows


def _saved(**kw):
    base = dict(
        id=9, label="Cement Job Volume", method="M",
        input_snapshot={"parameters": {"hole_size_in": 12.25,
                                        "casing_od_in": 9.625,
                                        "open_hole_length_ft": 2000.0}},
        summary={"slurry_volume_bbl": 151.0, "total_pump_bbl": 320.0,
                 "sacks": 740.0},
        well_id=None, created_at=datetime(2026, 9, 14, 8, 15),
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
    assert r["hole"] == 12.25
    assert r["csg_od"] == 9.625
    assert r["slurry"] == 151.0
    assert r["sacks"] == 740.0
    assert r["when"] == "2026-09-14 08:15"


def test_build_history_rows_handles_empty_and_missing():
    assert build_history_rows([]) == []
    sparse = _saved(summary={}, input_snapshot={"parameters": {}})
    sparse.input_parameters = {}
    rows = build_history_rows([sparse])
    assert rows[0]["hole"] is None
    assert rows[0]["slurry"] is None
    assert rows[0]["sacks"] is None
