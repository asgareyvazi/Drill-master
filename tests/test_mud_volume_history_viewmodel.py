"""Qt-free test of the Mud Volume history dialog's view-model builder.

Only the pure ``build_history_rows`` projection is tested here (no widgets), so
it runs in the shared pytest interpreter without a Qt display.
"""
from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

from dialogs.mud_volume_history_dialog import build_history_rows


def _saved(**kw):
    base = dict(
        id=7, label="Mud Volume Balance", method="M",
        input_snapshot={"parameters": {"active_volume_bbl": 800.0,
                                        "additions_bbl": 50.0,
                                        "losses_bbl": 20.0}},
        summary={"active_volume_bbl": 800.0, "final_volume_bbl": 855.0,
                 "net_change_bbl": 55.0},
        well_id=None, created_at=datetime(2026, 9, 19, 9, 30),
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
    assert r["active"] == 800.0
    assert r["final"] == 855.0
    assert r["net"] == 55.0
    assert r["when"] == "2026-09-19 09:30"


def test_build_history_rows_handles_empty_and_missing():
    assert build_history_rows([]) == []
    sparse = _saved(summary={}, input_snapshot={"parameters": {}})
    sparse.input_parameters = {}
    rows = build_history_rows([sparse])
    assert rows[0]["active"] is None
    assert rows[0]["final"] is None
    assert rows[0]["net"] is None
