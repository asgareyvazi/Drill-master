"""M123 - D6: MSE lineage v2 (explicit MD, input units), the audited lineage repair workflow, the legacy
label, and the lineage classes in Operational Analysis, MSE History and Calculation History.

Synthetic data only.  Rules under test:
* MD is recorded only when entered, only with the wellbore it was measured in; never derived.
* A repair fills ONE unknown field from named evidence, with a reason and an identified confirming user;
  recorded lineage and earlier repairs are never overwritten; the MSE record is never written.
* Repairs are append-only in storage; a report delete only unlinks them (D33); a well delete removes them.
* OA separates whole-well / wellbore / depth / unscoped legacy and filters a wellbore by EFFECTIVE lineage.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import analysis_evidence as ev  # noqa: E402
from core import calculation_history as ch  # noqa: E402
from core import operational_analysis as oa  # noqa: E402
from core.authorization import AuthorizationError  # noqa: E402
from core.database import AuditLog, DailyReport, MSECalculationRecord, MSELineageRepair, Wellbore  # noqa: E402
from core.repositories import mse_repository as mr  # noqa: E402
from tests.test_data_layer_authorization import Principal  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

MSE_IN = {"wob_lbf": 25000.0, "rpm": 120.0, "torque_ft_lbf": 8000.0, "rop_ft_hr": 50.0, "bit_diameter_in": 8.5}
MSE_OUT = {"mse_psi": 127997.67, "axial_term_psi": 440.6, "rotary_term_psi": 127557.07, "bit_area_in2": 56.745}


def _admin(path):
    return dict(sqlite3.connect(path).execute("SELECT username, id FROM users").fetchall())["admin"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m123.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    out = {"well": well, "bore": bore, "other_well": ids["B"][0], "path": path}
    with manager.session_scope() as s:
        st = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        foreign = Wellbore(well_id=out["other_well"], name="SYN-B OH2", wellbore_type="original")
        s.add_all([st, foreign])
        s.flush()
        out["sidetrack"], out["foreign_bore"] = st.id, foreign.id
        r1 = DailyReport(well_id=well, wellbore_id=bore, report_date=datetime(2026, 2, 1).date(), report_number=1)
        r2 = DailyReport(well_id=well, wellbore_id=st.id, report_date=datetime(2026, 2, 2).date(), report_number=2)
        rf = DailyReport(well_id=out["other_well"], report_date=datetime(2026, 2, 1).date(), report_number=1)
        s.add_all([r1, r2, rf])
        s.flush()
        out["r_bore"], out["r_st"], out["r_foreign"] = r1.id, r2.id, rf.id
        legacy = MSECalculationRecord(well_id=well, label="SYN legacy", method="Teale", snapshot_schema_version=1,
                                      input_snapshot_json={"parameters": MSE_IN}, result_json=MSE_OUT,
                                      mse_psi=127997.67, created_at=datetime(2026, 2, 1, 9, 0))
        standalone = MSECalculationRecord(well_id=None, label="SYN standalone", method="Teale",
                                          snapshot_schema_version=1, input_snapshot_json={"parameters": MSE_IN},
                                          mse_psi=1.0, created_at=datetime(2026, 2, 1, 9, 30))
        s.add_all([legacy, standalone])
        s.flush()
        out["legacy"], out["standalone"] = legacy.id, standalone.id
    repo = mr.MSECalculationRepository(manager)
    out["whole"] = repo.save_run(inputs=MSE_IN, result_values=MSE_OUT, method="Teale", label="SYN whole", well_id=well)
    out["bore_run"] = repo.save_run(inputs=MSE_IN, result_values=MSE_OUT, method="Teale", label="SYN bore",
                                    well_id=well, wellbore_id=bore, report_id=out["r_bore"])
    out["depth_run"] = repo.save_run(inputs=MSE_IN, result_values=MSE_OUT, method="Teale", label="SYN depth",
                                     well_id=well, wellbore_id=bore, md_value=1000.0, md_unit="ft")
    yield manager, repo, out
    manager.close()


def _as_admin(manager, path):
    manager.enforce_authorization(Principal("admin", _admin(path), "admin"))


def _raw(path, sql, *args):
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        rows = con.execute(sql, args).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


# ------------------------------------------------------------------ dashboard (whole-well trend)
def test_dashboard_mse_is_a_whole_well_save_time_trend_with_legacy_kept_apart(env):
    from core.operations_dashboard import build_well_detail
    manager, _repo, out = env
    detail = build_well_detail(manager, out["well"])
    assert len(detail.mse) == 4                       # legacy + whole-well + wellbore + depth runs, all scopes
    assert len(detail.mse_legacy) == 1 and len(detail.mse_recorded) == 3
    assert sorted(detail.mse_legacy + detail.mse_recorded) == sorted(detail.mse)
    assert detail.mse_legacy[0][0] == datetime(2026, 2, 1, 9, 0)


def test_points_chart_never_joins_discrete_runs():
    from PySide6.QtWidgets import QApplication
    from tabs.dashboard_widgets import MiniChart
    _app = QApplication.instance() or QApplication([])
    pts = [(datetime(2026, 2, 1, h), 1000.0 * h) for h in (8, 9, 10)]
    drawn = {}
    for kind in ("points", "line"):
        chart = MiniChart()
        chart.resize(360, 220)
        chart.set_data(kind, [("a", pts, "cyan")], "MSE (psi), whole-well", x_unit="saved at (not depth)")
        calls = []
        original = chart._paint_line

        def spy(painter, rect, _orig=original, _calls=calls):
            real = painter.drawPath
            painter.drawPath = lambda path, _r=real: (_calls.append(path.elementCount()), _r(path))
            return _orig(painter, rect)

        chart._paint_line = spy
        assert not chart.grab().isNull() and len(chart._hits) == 3
        drawn[kind] = calls
    assert drawn["points"] == [] and drawn["line"] == [3]


# ------------------------------------------------------------------ save path (lineage v2)
def test_new_runs_record_v2_lineage_with_explicit_md_and_units(env):
    _manager, repo, out = env
    depth = repo.get(out["depth_run"])
    assert depth.lineage_version == mr.LINEAGE_VERSION == 2
    assert depth.md_entered_value == 1000.0 and depth.md_entered_unit == "ft"
    assert math.isclose(depth.md_m, 304.8, rel_tol=0, abs_tol=1e-9)     # 1000 ft x 0.3048 m/ft (unit_manager)
    assert depth.input_units == mr.INPUT_UNITS and depth.input_units["wob_lbf"] == "lbf"
    assert depth.lineage_class == mr.CLASS_DEPTH
    whole = repo.get(out["whole"])
    assert whole.md_m is None and whole.md_entered_value is None and whole.lineage_class == mr.CLASS_WELL
    assert repo.get(out["bore_run"]).lineage_class == mr.CLASS_WELLBORE
    legacy = repo.get(out["legacy"])
    assert legacy.is_legacy and legacy.lineage_class == mr.CLASS_LEGACY and legacy.input_units is None
    assert repo.get(out["standalone"]).lineage_class == mr.CLASS_NO_WELL


@pytest.mark.parametrize("kwargs,message", [
    ({"md_value": 100.0, "md_unit": "m"}, "with the wellbore"),                       # no wellbore
    ({"wellbore_id": "B", "md_value": 0.0, "md_unit": "m"}, "positive"),
    ({"wellbore_id": "B", "md_value": -5.0, "md_unit": "m"}, "positive"),
    ({"wellbore_id": "B", "md_value": float("nan"), "md_unit": "m"}, "finite"),
    ({"wellbore_id": "B", "md_value": 100.0, "md_unit": "km"}, "unit"),
    ({"wellbore_id": "B", "md_value": None, "md_unit": "m"}, "number"),
    ({"wellbore_id": "F", "md_value": 100.0, "md_unit": "m"}, "is not a wellbore of well"),
])
def test_an_unusable_or_unanchored_md_is_refused_and_nothing_is_saved(env, kwargs, message):
    _manager, repo, out = env
    kwargs = dict(kwargs)
    if kwargs.get("wellbore_id") == "B":
        kwargs["wellbore_id"] = out["bore"]
    elif kwargs.get("wellbore_id") == "F":
        kwargs["wellbore_id"] = out["foreign_bore"]
    before = repo.count()
    with pytest.raises(ValueError, match=message):
        repo.save_run(inputs=MSE_IN, result_values=MSE_OUT, method="Teale", well_id=out["well"], **kwargs)
    assert repo.count() == before


# ------------------------------------------------------------------ audited repair
def test_a_legacy_run_gets_an_audited_wellbore_repair_and_the_record_is_not_written(env):
    manager, repo, out = env
    _as_admin(manager, out["path"])
    raw_before = _raw(out["path"], "SELECT * FROM mse_calculations WHERE id=?", out["legacy"])
    rid = repo.repair_lineage(out["legacy"], "wellbore_id", wellbore_id=out["bore"],
                              evidence="SYN DDR #1 page 2: bit run on OH", reason="lineage reconstruction")
    assert _raw(out["path"], "SELECT * FROM mse_calculations WHERE id=?", out["legacy"]) == raw_before
    saved = repo.get(out["legacy"])
    assert saved.wellbore_id is None and saved.effective_wellbore_id == out["bore"]      # recorded stays unknown
    assert saved.lineage_class == f"{mr.CLASS_WELLBORE} (repaired: wellbore_id)" and saved.is_legacy
    (repair,) = saved.repairs
    assert (repair.id, repair.field, repair.confirmer, repair.method_version) == (
        rid, "wellbore_id", "admin", mr.REPAIR_METHOD_VERSION)
    assert repair.before_value.startswith("unknown (legacy run") and "SYN-A" in repair.value_label
    assert repair.evidence == "SYN DDR #1 page 2: bit run on OH" and repair.confirmed_at is not None
    with manager.session_scope() as s:
        audit = s.query(AuditLog).filter(AuditLog.action == "lineage_repair").one()
        details = json.loads(audit.details)
        assert (audit.entity_type, audit.entity_id, details["field"], details["repair_id"]) == (
            "mse_calculation", out["legacy"], "wellbore_id", rid)
    # then MD can be repaired (the wellbore is now known), and the run becomes depth-class
    repo.repair_lineage(out["legacy"], "md_m", md_value=2450.0, md_unit="m", evidence="SYN tally", reason="r")
    saved = repo.get(out["legacy"])
    assert saved.effective_md_m == 2450.0 and saved.lineage_class.startswith(mr.CLASS_DEPTH)


def _refusal_cases(out):
    return [
        ("legacy", "wellbore_id", {"wellbore_id": out["bore"], "evidence": " ", "reason": "r"}, "evidence"),
        ("legacy", "wellbore_id", {"wellbore_id": out["bore"], "evidence": "e", "reason": ""}, "reason"),
        ("bore_run", "wellbore_id", {"wellbore_id": out["bore"], "evidence": "e", "reason": "r"}, "recorded"),
        ("bore_run", "report_id", {"report_id": out["r_bore"], "evidence": "e", "reason": "r"}, "recorded"),
        ("legacy", "wellbore_id", {"wellbore_id": out["foreign_bore"], "evidence": "e", "reason": "r"},
         "not a wellbore of well"),
        ("legacy", "report_id", {"report_id": out["r_foreign"], "evidence": "e", "reason": "r"},
         "not a report of well"),
        ("legacy", "md_m", {"md_value": 100.0, "md_unit": "m", "evidence": "e", "reason": "r"}, "wellbore"),
        ("standalone", "wellbore_id", {"wellbore_id": out["bore"], "evidence": "e", "reason": "r"},
         "without a well"),
        ("legacy", "wellbore_id", {"wellbore_id": out["bore"], "report_id": out["r_bore"], "evidence": "e",
                                   "reason": "r"}, "exactly"),
        ("legacy", "label", {"evidence": "e", "reason": "r"}, "Only"),
        ("bore_run", "report_id", {"report_id": out["r_st"], "evidence": "e", "reason": "r"}, "recorded"),
        ("whole", "md_m", {"md_value": 10.0, "md_unit": "m", "evidence": "e", "reason": "r"}, "wellbore"),
    ]


def test_every_unsafe_repair_is_refused_and_nothing_is_written(env):
    manager, repo, out = env
    _as_admin(manager, out["path"])
    for run, name, kwargs, message in _refusal_cases(out):
        with pytest.raises(ValueError, match=message):
            repo.repair_lineage(out[run], name, **kwargs)
    # a report of the sidetrack cannot repair a run whose (recorded) wellbore is the original hole
    repo2 = mr.MSECalculationRepository(manager)
    run = repo2.save_run(inputs=MSE_IN, result_values=MSE_OUT, method="Teale", well_id=out["well"],
                         wellbore_id=out["bore"])
    with pytest.raises(ValueError, match="another wellbore"):
        repo2.repair_lineage(run, "report_id", report_id=out["r_st"], evidence="e", reason="r")
    assert _raw(out["path"], "SELECT COUNT(*) FROM mse_lineage_repairs")[0][0] == 0
    # one repair per field: a second one is refused, the first is never overwritten
    repo.repair_lineage(out["legacy"], "wellbore_id", wellbore_id=out["bore"], evidence="e1", reason="r1")
    with pytest.raises(ValueError, match="already repaired"):
        repo.repair_lineage(out["legacy"], "wellbore_id", wellbore_id=out["sidetrack"], evidence="e2", reason="r2")
    assert [r.evidence for r in repo.get(out["legacy"]).repairs] == ["e1"]


def test_a_repair_needs_an_identified_and_authorized_user(env, monkeypatch):
    manager, repo, out = env
    from core.database import DatabaseManager
    monkeypatch.setattr(DatabaseManager, "_get_current_user_info",
                        property(lambda self: {"user_id": None, "username": "system"}))
    with pytest.raises(ValueError, match="identified user"):
        repo.repair_lineage(out["legacy"], "wellbore_id", wellbore_id=out["bore"], evidence="e", reason="r")
    manager.enforce_authorization(Principal("viewer", _admin(out["path"]), "admin"))
    with pytest.raises(AuthorizationError):
        repo.repair_lineage(out["legacy"], "wellbore_id", wellbore_id=out["bore"], evidence="e", reason="r")
    assert _raw(out["path"], "SELECT COUNT(*) FROM mse_lineage_repairs")[0][0] == 0
    assert _raw(out["path"], "SELECT COUNT(*) FROM audit_logs WHERE action='lineage_repair'")[0][0] == 0


def test_a_stored_repair_is_append_only_in_storage(env):
    manager, repo, out = env
    _as_admin(manager, out["path"])
    rid = repo.repair_lineage(out["legacy"], "report_id", report_id=out["r_bore"], evidence="SYN", reason="r")
    for sql in ("UPDATE mse_lineage_repairs SET evidence='forged' WHERE id=?",
                "UPDATE mse_lineage_repairs SET value_label='Report #9' WHERE id=?",
                "UPDATE mse_lineage_repairs SET confirmed_by=NULL WHERE id=?",
                "DELETE FROM mse_lineage_repairs WHERE id=?"):
        with pytest.raises(sqlite3.DatabaseError):
            _raw(out["path"], sql, rid)
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):        # never re-pointed to another report
        _raw(out["path"], "UPDATE mse_lineage_repairs SET report_id=? WHERE id=?", out["r_st"], rid)
    assert _raw(out["path"], "SELECT evidence, report_id FROM mse_lineage_repairs WHERE id=?", rid) == [
        ("SYN", out["r_bore"])]


def test_report_delete_unlinks_the_repair_keeps_its_evidence_and_allows_a_new_repair(env):
    manager, repo, out = env
    _as_admin(manager, out["path"])
    rid = repo.repair_lineage(out["legacy"], "report_id", report_id=out["r_bore"], evidence="SYN", reason="r")
    assert manager.delete_daily_report(out["r_bore"]) is True
    row = _raw(out["path"], "SELECT report_id, value_label, evidence FROM mse_lineage_repairs WHERE id=?", rid)[0]
    assert row[0] is None and row[1].startswith("Report #1") and row[2] == "SYN"
    saved = repo.get(out["legacy"])
    assert saved.repairs[0].unlinked and saved.effective_report_id is None           # unknown again, not guessed
    assert repo.get(out["bore_run"]).report_id is None                                # D33 for the record itself
    repo.repair_lineage(out["legacy"], "report_id", report_id=out["r_st"], evidence="SYN 2", reason="r")
    assert repo.get(out["legacy"]).effective_report_id == out["r_st"]
    assert _raw(out["path"], "PRAGMA foreign_key_check") == []


def test_well_delete_removes_runs_and_repairs_together(env):
    manager, repo, out = env
    _as_admin(manager, out["path"])
    repo.repair_lineage(out["legacy"], "wellbore_id", wellbore_id=out["bore"], evidence="SYN", reason="r")
    assert manager.delete_well(out["well"]) is True
    assert _raw(out["path"], "SELECT COUNT(*) FROM mse_lineage_repairs")[0][0] == 0
    assert _raw(out["path"], "SELECT COUNT(*) FROM mse_calculations WHERE well_id=?", out["well"])[0][0] == 0
    assert _raw(out["path"], "SELECT COUNT(*) FROM mse_calculations WHERE id=?", out["standalone"])[0][0] == 1
    assert _raw(out["path"], "PRAGMA foreign_key_check") == []


# ------------------------------------------------------------------ Operational Analysis
def _mse_table(manager, out, bore=None):
    result = oa.analyze(manager, ev.AnalysisScope(well_id=out["well"], wellbore_id=bore))
    return {r[1]: dict(zip(oa.COLUMNS["mse"], r)) for r in result.tables["mse"][1]}, result


def test_oa_separates_lineage_classes_and_labels_legacy(env):
    manager, _repo, out = env
    rows, result = _mse_table(manager, out)
    assert rows["SYN legacy"]["Lineage class"] == mr.CLASS_LEGACY
    assert rows["SYN legacy"]["Wellbore"] == rows["SYN legacy"]["Input source"] == mr.LEGACY_LABEL
    assert mr.LEGACY_LABEL == "LEGACY — LINEAGE UNKNOWN — NOT DEPTH-REPRODUCIBLE"
    assert rows["SYN whole"]["Lineage class"] == mr.CLASS_WELL and rows["SYN whole"]["MD (m)"] is None
    assert rows["SYN bore"]["Lineage class"] == mr.CLASS_WELLBORE
    assert rows["SYN depth"]["Lineage class"] == mr.CLASS_DEPTH
    assert math.isclose(rows["SYN depth"]["MD (m)"], 304.8, abs_tol=1e-9)
    assert "SYN standalone" not in rows                                     # no well: never in a well's analysis
    note = next(n for n in result.notes if n.startswith("MSE lineage:"))
    for part in (f"{mr.CLASS_LEGACY} 1", f"{mr.CLASS_WELL} 1", f"{mr.CLASS_WELLBORE} 1", f"{mr.CLASS_DEPTH} 1"):
        assert part in note


def test_oa_wellbore_scope_uses_the_repaired_lineage_and_shows_the_repair(env):
    manager, repo, out = env
    rows, _ = _mse_table(manager, out, bore=out["bore"])
    assert set(rows) == {"SYN bore", "SYN depth"}                           # legacy/whole-well not attributed
    _as_admin(manager, out["path"])
    repo.repair_lineage(out["legacy"], "wellbore_id", wellbore_id=out["bore"], evidence="SYN DDR", reason="r")
    rows, _ = _mse_table(manager, out, bore=out["bore"])
    assert set(rows) == {"SYN bore", "SYN depth", "SYN legacy"}
    legacy = rows["SYN legacy"]
    assert legacy["Lineage class"] == f"{mr.CLASS_WELLBORE} (repaired: wellbore_id)"
    assert "repair #" in legacy["Lineage repairs"] and "evidence: SYN DDR" in legacy["Lineage repairs"]
    assert legacy["Input source"] == mr.LEGACY_LABEL                       # the original stays legacy
    rows, _ = _mse_table(manager, out, bore=out["sidetrack"])
    assert "SYN legacy" not in rows


# ------------------------------------------------------------------ Calculation History
def test_calculation_history_carries_the_recorded_wellbore_into_a_rerun_case(env):
    manager, _repo, out = env
    entries = {e.name: e for e in ch.load_history(manager, well_id=out["well"]) if e.table == "mse_calculations"}
    assert entries["SYN bore"].wellbore_id == out["bore"]
    assert entries["SYN legacy"].wellbore_id is None and entries["SYN whole"].wellbore_id is None
    entry = entries["SYN bore"]
    outcome = {"values": MSE_OUT, "status": "MATCH", "method_matches": True, "current_method": "Teale"}
    case = ch.save_recalculation(manager, entry, outcome)
    with manager.session_scope() as s:
        from core.database import CalculationCase
        assert s.get(CalculationCase, case["id"]).wellbore_id == out["bore"]


# ------------------------------------------------------------------ MSE History dialog (real widgets)
def test_history_dialog_shows_lineage_and_records_a_repair_through_its_widgets(env):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from dialogs.mse_history_dialog import MSEHistoryDialog, RepairLineageDialog
    QApplication.instance() or QApplication([])
    manager, repo, out = env
    _as_admin(manager, out["path"])
    dlg = MSEHistoryDialog(repo, current_method="Teale", well_id=out["well"], well_label="SYN-A")
    labels = {dlg.table.item(r, 0).data(0x0100): dlg.table.item(r, 4).text() for r in range(dlg.table.rowCount())}
    assert mr.LEGACY_LABEL in labels.values() and mr.CLASS_DEPTH in labels.values()
    row = next(r for r in range(dlg.table.rowCount()) if dlg.table.item(r, 4).text() == mr.LEGACY_LABEL)
    dlg.table.selectRow(row)
    assert mr.LEGACY_LABEL in dlg.details.toPlainText() and dlg.repair_btn.isEnabled()
    saved = dlg._saved[dlg._selected_index()]
    rep = RepairLineageDialog(repo, saved)
    assert [rep.field_combo.itemData(i) for i in range(rep.field_combo.count())] == ["wellbore_id", "report_id",
                                                                                      "md_m"]
    assert rep.confirmer_label.text() == "admin"
    assert rep.wellbore_combo.findData(out["foreign_bore"]) == -1          # only the run's own well is offered
    rep.wellbore_combo.setCurrentIndex(rep.wellbore_combo.findData(out["bore"]))
    assert rep.submit() is False and "evidence" in rep.error_label.text()  # refused, nothing written
    assert _raw(out["path"], "SELECT COUNT(*) FROM mse_lineage_repairs")[0][0] == 0
    rep.evidence_edit.setPlainText("SYN DDR #1 p.2")
    rep.reason_edit.setText("reconstruction")
    assert rep.submit() is True and rep.repair_id is not None
    dlg.reload()
    row = next(r for r in range(dlg.table.rowCount()) if "repaired" in dlg.table.item(r, 4).text())
    dlg.table.clearSelection()
    dlg.table.selectRow(row)
    text = dlg.details.toPlainText()
    assert "AUDITED REPAIR" in text and "SYN DDR #1 p.2" in text and "Confirmed by    : admin" in text
    dlg.close()


# ------------------------------------------------------------------ W13 (subprocess, like the M-series smoke)
_W13 = textwrap.dedent("""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import DatabaseManager, Base
    m = DatabaseManager.__new__(DatabaseManager)
    m.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    with m.engine.begin() as c:
        c.execute(text("INSERT INTO companies(id, name, code) VALUES (1, 'SYN', 'S')"))
        c.execute(text("INSERT INTO projects(id, company_id, name, code) VALUES (1, 1, 'SYN', 'P')"))
        c.execute(text("INSERT INTO wells(id, project_id, name, code) VALUES (1, 1, 'SYN-W', 'W')"))
        c.execute(text("INSERT INTO wellbores(id, well_id, name, wellbore_type) VALUES (5, 1, 'OH', 'original')"))
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    shown = []
    QMessageBox.information = staticmethod(lambda *a, **k: shown.append(("info", a[2])))
    QMessageBox.warning = staticmethod(lambda *a, **k: shown.append(("warning", a[2])))
    QMessageBox.critical = staticmethod(lambda *a, **k: shown.append(("error", a[2])))
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab(m)
    tab.current_well_id, tab.current_wellbore_id, tab.current_context = 1, None, None
    for w, v in ((tab.bit_od, 8.5), (tab.bit_wob, 25.0), (tab.bit_rpm, 120.0), (tab.bit_tq, 8000.0),
                 (tab.bit_rop, 30.0)):
        w.setValue(v)
    tab._mse_calculate()
    assert not tab.mse_md_value.isEnabled()
    tab.mse_md_check.setChecked(True)
    assert tab.mse_md_value.isEnabled() and tab.mse_md_unit.isEnabled()
    tab.mse_md_value.setValue(2500.0)
    tab.mse_md_unit.setCurrentText("ft")
    tab._mse_save_calculation()                      # no wellbore selected: refused, nothing saved
    # the UI explains it before saving (guidance, not a failed save); the repository refuses as well
    assert tab._mse_repo().count() == 0 and shown[-1][0] == "info", shown
    assert "wellbore it was measured in" in shown[-1][1] and "Select the wellbore" in shown[-1][1], shown
    tab.current_wellbore_id = 5
    tab._mse_save_calculation()
    run = tab._mse_repo().all()[0]
    assert (run.wellbore_id, run.md_entered_value, run.md_entered_unit) == (5, 2500.0, "ft"), run
    assert abs(run.md_m - 762.0) < 1e-9 and run.lineage_class.startswith("depth"), run.md_m
    tab.mse_md_check.setChecked(False)
    tab._mse_save_calculation()
    assert tab._mse_repo().all()[0].md_m is None     # unchecked: MD not recorded, never carried over
    print("W13_MD_OK")
""")


def test_w13_records_md_only_when_entered_and_only_with_a_wellbore():
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(root))
    proc = subprocess.run([sys.executable, "-c", _W13], cwd=root, env=env, capture_output=True, text=True,
                          timeout=240)
    assert proc.returncode == 0 and "W13_MD_OK" in proc.stdout, proc.stdout[-2000:] + proc.stderr[-3000:]


def test_an_old_database_gains_the_repair_table_and_its_guards(env):
    """An old database (no repair table) gains it, with its guard triggers, on the next start."""
    manager, _repo, out = env
    manager.close()
    with sqlite3.connect(out["path"]) as con:
        con.execute("DROP TABLE mse_lineage_repairs")
    assert manager.initialize(), manager.last_diagnostic
    with sqlite3.connect(out["path"]) as con:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert {"trg_mse_lineage_repair_immutable_v1", "trg_mse_lineage_repair_nodelete_v1",
            "trg_mse_lineage_repair_noreplace_v1"} <= names
    with manager.session_scope() as s:
        assert s.query(MSELineageRepair).count() == 0
