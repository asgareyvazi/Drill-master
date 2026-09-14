"""Qt-free test of the kill-sheet history dialog's view-model builder.

Only the pure ``build_history_rows`` projection is tested here (no widgets), so
it runs in the shared pytest interpreter without a Qt display.
"""
from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

from dialogs.well_control_kill_sheet_history_dialog import build_history_rows


def _saved(**kw):
    base = dict(
        id=7, label="Well Control Kill Sheet", method="IWCF",
        input_snapshot={"method": "IWCF",
                        "canonical_inputs": {"method": "Wait & Weight",
                                             "tvd_ft": 9842.5}},
        summary={"kill_mw_ppg": 13.01, "maasp_psi": 1143.9, "stk_total": 7306.0},
        well_id=None, created_at=datetime(2026, 9, 14, 11, 30),
    )
    base.update(kw)
    obj = SimpleNamespace(**base)
    obj.canonical_inputs = dict(base["input_snapshot"]["canonical_inputs"])
    return obj


def test_build_history_rows_projects_fields():
    rows = build_history_rows([_saved()])
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == 7
    assert r["method"] == "Wait & Weight"
    assert r["kill_mw"] == 13.01
    assert r["maasp"] == 1143.9
    assert r["stk_total"] == 7306.0
    assert r["when"] == "2026-09-14 11:30"


def test_build_history_rows_handles_missing_created_at():
    rows = build_history_rows([_saved(created_at=None)])
    assert rows[0]["when"] == "—"


def test_build_history_rows_falls_back_to_record_method():
    s = _saved(input_snapshot={"method": "IWCF", "canonical_inputs": {}})
    s.canonical_inputs = {}
    rows = build_history_rows([s])
    assert rows[0]["method"] == "IWCF"
