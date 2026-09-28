"""Forensic regression contracts: no currency conversion, no unknown -> zero."""

from datetime import date, time
from types import SimpleNamespace

import pytest

from core.actual_vs_plan import compare, ActualVsPlanEngine, compare_plan_activities
from core.cost_semantics import summarize_costs
from core.safety_semantics import safety_kpis
from test_cost_truth_boundary import memory_manager


@pytest.mark.parametrize(
    "planned,actual",
    [(None, None), (None, 0), (0, None), (0, 0), (100, None), (None, 100), (100, 0), (0, 100), (100, 100)],
)
def test_scalar_and_canonical_null_zero_matrix(planned, actual):
    scalar = compare("Hours", planned, actual)
    canonical = ActualVsPlanEngine.compare_metrics({"hours": planned}, {"hours": actual})
    metric = canonical.values.get("hours") or canonical.metadata["unavailable_metrics"]["hours"]
    assert scalar.planned == metric["planned"] == planned
    assert scalar.actual == metric["actual"] == actual
    assert scalar.status == metric["status"]
    if planned is None or actual is None:
        assert scalar.variance is scalar.variance_pct is None
        assert scalar.status == "unavailable"
        assert not canonical.success
    else:
        assert scalar.variance == actual - planned
        assert canonical.success
        if planned == 0 and actual != 0:
            assert scalar.variance_pct is None and scalar.status == "unavailable"
        elif planned == actual:
            assert scalar.variance_pct == 0 and scalar.status == "on-track"
        else:
            assert scalar.variance_pct == -100


@pytest.mark.parametrize(
    "planned,actual",
    [(None, None), (None, 0), (0, None), (0, 0), (100, None), (None, 100), (100, 0), (0, 100), (100, 100)],
)
def test_activity_null_zero_matrix(planned, actual):
    metrics = compare_plan_activities(
        [{"planned_duration_hours": planned, "planned_depth_to": planned}], actual, actual
    )
    for metric in metrics:
        assert metric.planned == planned and metric.actual == actual
        assert metric.status == compare(metric.metric, planned, actual).status
    assert compare_plan_activities([], actual, actual)[0].planned is None


@pytest.mark.parametrize(
    "currencies,status,total",
    [
        (["USD", "EUR"], "multi-currency", None),
        (["USD", None], "unknown-currency", None),
        ([None, None], "unknown-currency", None),
        ([" usd ", "USD"], "single-currency", 200),
    ],
)
def test_currency_grouping_never_uses_project_default(currencies, status, total):
    costs = summarize_costs([dict(category="Rig", currency=c, planned_cost=100, actual_cost=100) for c in currencies])
    assert costs["status"] == status
    assert costs["total_actual"] == total
    assert len(costs["groups"]) == len(set(c.strip().upper() if c else None for c in currencies))


def test_partial_amounts_invalidate_only_missing_side():
    costs = summarize_costs(
        [
            dict(category="Rig", currency="USD", planned_cost=100, actual_cost=0),
            dict(category="Rig", currency="USD", planned_cost=None, actual_cost=0),
        ]
    )
    assert costs["total_planned"] is costs["variance"] is None
    assert costs["total_actual"] == 0


def test_safety_absence_zero_incomplete_and_latest_not_maximum():
    assert all(value is None for value in safety_kpis([]).values())
    old = SimpleNamespace(report_date=date(2026, 1, 1), days_without_lti=120, lti_count=0, near_miss_count=0)
    latest = SimpleNamespace(report_date=date(2026, 1, 2), days_without_lti=0, lti_count=1, near_miss_count=None)
    assert safety_kpis([old])["total_lti"] == 0
    assert safety_kpis([old, latest]) == dict(days_without_lti=0, total_lti=1, total_near_miss=None)
    assert safety_kpis([old, latest, latest])["days_without_lti"] is None


@pytest.fixture
def env():
    manager, wid = memory_manager()
    yield manager, wid
    manager.close()


def test_db_null_defaults_no_invented_safety_or_cost(env):
    from core.database import CostRecord, SafetyReport

    db, wid = env
    with db.session_scope() as session:
        cost = CostRecord(well_id=wid, category="Rig")
        safety = SafetyReport(well_id=wid, report_date=date(2026, 1, 1))
        session.add_all([cost, safety])
        session.flush()
        assert cost.planned_cost is cost.actual_cost is cost.currency is None
        for field in ("days_without_lti", "lti_count", "near_miss_count", "test_pressure", "waste_ph", "oil_content"):
            assert getattr(safety, field) is None


def test_db_zero_plan_and_known_actual_survive_missing_counterpart(env):
    from core.database import WellPlan, DailyReport, TimeLog24H

    db, wid = env
    with db.session_scope() as session:
        session.add(
            WellPlan(well_id=wid, plan_name="Zero", planned_total_days=0, planned_final_depth=0, is_active=True)
        )
        report = DailyReport(well_id=wid, report_date=date(2026, 1, 1), rop_meter=0, depth_2400=0)
        session.add(report)
        session.flush()
        session.add(TimeLog24H(report_id=report.id, time_from=time(0), time_to=time(0), duration=0, is_npt=False))
    assert db.get_planned_total_days(wid) == 0
    result = db.get_actual_vs_plan(wid)
    assert result["hours"]["planned"] == result["hours"]["actual"] == 0
    assert result["rop"]["actual"] == 0 and result["rop"]["planned"] is None


def test_currency_roundtrip_metadata_and_consumers(env, tmp_path):
    from core.database import DailyReport
    from core.operations_intelligence import OperationsIntelligenceService
    from core.report_engine import CostReportEngine, NPTReportEngine, EOWRReportEngine
    from core.cost_semantics import cost_records_to_afe_rows

    db, wid = env
    with db.session_scope() as session:
        session.add(DailyReport(well_id=wid, report_date=date(2026, 1, 1), depth_2400=100))
    db.save_afe_worksheet(
        wid,
        [
            dict(category="Rig", planned_cost=None, actual_cost=100, currency="EUR", vendor="Original", afe_number="A"),
            dict(category="Rig", planned_cost=0, actual_cost=100, currency="USD", afe_number="B"),
        ],
    )
    rows = cost_records_to_afe_rows(db.get_cost_records(wid))
    db.save_afe_worksheet(wid, rows, currency="GBP")
    assert {r["currency"] for r in db.get_cost_records(wid)} == {"USD", "EUR"}
    assert {r["afe_number"] for r in db.get_cost_records(wid)} == {"A", "B"}
    assert next(r for r in db.get_cost_records(wid) if r["currency"] == "EUR")["vendor"] == "Original"
    assert db.get_cost_totals(wid)["total_actual"] is None
    assert db.get_actual_vs_plan(wid)["cost"]["actual"] is None
    kpis = OperationsIntelligenceService(db).analyze_well(wid)["kpis"]
    assert kpis["total_cost"] is None
    assert all(v is None for v in kpis["safety_kpi"].values())
    engine = CostReportEngine(db)
    data = engine._collect_data(wid)
    assert data["total_cost"] is None and len(data["categories"]) == 2
    html = engine._build_html(data)
    assert "EUR 100.00" in html and "USD 100.00" in html and "$" not in html
    assert engine._save_excel(data, str(tmp_path / "mixed.xlsx"))
    assert NPTReportEngine(db)._collect_data(wid)["npt_cost"] is None
    eowr = EOWRReportEngine(db)._collect_data(wid)
    assert eowr["summary"]["total_cost"] is None


def test_zero_projection_is_explicit_and_separate(env):
    from core.database import DailyReport
    from core.report_engine import CostReportEngine

    db, wid = env
    with db.session_scope() as session:
        session.add(DailyReport(well_id=wid, report_date=date(2026, 1, 1)))
    engine = CostReportEngine(db)
    data = engine._collect_data(wid, 0, 0, "EUR")
    assert data["projected_total_cost"] == 0
    assert data["total_cost"] is None
    assert engine._collect_data(wid, 100, 100)["projected_total_cost"] is None


def test_permission_exceptions_fail_closed(monkeypatch):
    from core.permissions import permissions
    from core.base_tab import DrillTabBase
    from core.hierarchy_operations import check_delete_permission

    def broken():
        raise RuntimeError("permission subsystem failed")

    monkeypatch.setattr(permissions, "is_viewer", broken)
    tab = SimpleNamespace(show_warning=lambda message: None)
    assert DrillTabBase.save_data(tab) is False
    assert DrillTabBase.check_permission(tab, "can_edit_reports") is False
    assert check_delete_permission() is False


def test_failed_backup_preserves_previous_destination(env, tmp_path, monkeypatch):
    import sqlite3

    db, _ = env
    live = tmp_path / "live.db"
    with sqlite3.connect(live) as connection:
        connection.execute("CREATE TABLE sentinel (value INTEGER)")
    destination = tmp_path / "prior.db"
    destination.write_bytes(b"previous known-good backup")
    db.db_path = str(live)

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("injected backup failure")

    monkeypatch.setattr(sqlite3, "connect", broken)
    assert db.backup_to(destination) is None
    assert destination.read_bytes() == b"previous known-good backup"
    assert not list(tmp_path.glob(".drillmaster-backup-*"))


def test_w8_w16_empty_state_zero_currency_and_export_subprocess(tmp_path):
    import subprocess
    import sys
    import os

    script = r"""
from datetime import date
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import QDate
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database import Base, DatabaseManager, Company, Project, Well, DailyReport
from core.permissions import permissions
from tabs.w8_Safety_Widget import SafetyBOPTab, WasteManagementTab
from tabs.w16_Cost_Management import CostManagementWidget
app = QApplication([])
for method in ('information', 'warning', 'critical'):
    setattr(QMessageBox, method, staticmethod(lambda *a, **kw: None))
db = DatabaseManager()
db.engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(db.engine)
db.Session = sessionmaker(bind=db.engine, expire_on_commit=False)
with db.session_scope() as s:
    c=Company(name='C',code='C');s.add(c);s.flush()
    p=Project(name='P',code='P',company_id=c.id);s.add(p);s.flush()
    w=Well(name='W',code='W',project_id=p.id);s.add(w);s.flush()
    r=DailyReport(well_id=w.id,report_date=date(2026,1,1));s.add(r);s.flush()
permissions.set_user({'id': None,'role':'engineer'})
parent=SimpleNamespace(db=db,current_well_id=w.id,current_report_id=r.id,show_message=lambda msg: None)
bop=SafetyBOPTab(parent)
waste=WasteManagementTab(parent)
assert bop.days_no_lti.value()==-1 and bop.test_pressure.value()==-1
assert bop.last_fire_drill.date()==bop.last_fire_drill.minimumDate()
assert waste.waste_ph.value()==-1 and waste.hardness.text()==''
assert waste.waste_type.currentIndex()==-1
assert bop.save_to_database(w.id,r.id)
assert waste.save_to_database(w.id,r.id)
row=db.get_safety_report(w.id,report_id=r.id)
assert row['days_without_lti'] is row['test_pressure'] is row['waste_ph'] is None
bop.days_no_lti.setValue(0)
waste.waste_ph.setValue(0)
assert bop.save_to_database(w.id,r.id)
assert waste.save_to_database(w.id,r.id)
row=db.get_safety_report(w.id,report_id=r.id)
assert row['days_without_lti']==row['waste_ph']==0
permissions.set_user({'role':'viewer'})
bop.days_no_lti.setValue(99)
assert bop.save_to_database(w.id,r.id) is False
assert db.get_safety_report(w.id,report_id=r.id)['days_without_lti']==0
permissions.set_user({'id':None,'role':'engineer'})
assert bop.load_from_database(w.id,report_id=999)
assert waste.load_from_database(w.id,report_id=999)
assert bop.days_no_lti.value()==waste.waste_ph.value()==-1
bop.add_bop_row()
assert all(bop.bop_stack_table.item(0,col).text()=='' for col in range(8))
waste.clear_waste_form()
waste.add_waste_row()
assert waste.waste_table.item(0,2).text()==waste.waste_table.item(0,3).text()==''
permissions.set_user({'id': None,'role':'engineer'})
db.save_afe_worksheet(w.id,[dict(category='A',currency='USD',planned_cost=None,actual_cost=0),dict(category='B',currency='EUR',planned_cost=0,actual_cost=100)])
tab=CostManagementWidget(db_manager=db)
tab.on_well_changed(w.id,{})
tab.afe_currency.setCurrentText('GBP')
assert tab.save_data()
rows=db.get_cost_records(w.id)
assert {r['currency'] for r in rows}=={'USD','EUR'}
assert next(r for r in rows if r['category']=='A')['planned_cost'] is None
assert '100' not in tab.card_total.value_label.text()
import os,csv
csv_path=os.environ['M28_CSV']
QFileDialog.getSaveFileName=staticmethod(lambda *a,**kw:(csv_path,'CSV'))
tab._export_cost()
with open(csv_path) as f: exported=list(csv.reader(f))
assert exported[0][-1]=='Currency'
assert {r[-1] for r in exported[1:]}=={'USD','EUR'}
assert 'Not supplied' in exported[1]
# Unknown -> explicit zero is editable, unlike the old minimum=0 NULL display.
tab.afe_table.cellWidget(0,1).setValue(0)
assert tab.save_data()
assert next(r for r in db.get_cost_records(w.id) if r['category']=='A')['planned_cost']==0
# Empty context must not carry the former well's source facts.
tab.on_well_changed(None,{})
assert tab.afe_table.rowCount()==0
assert tab.card_total.value_label.text()=='Unknown'
print('M28_UI_OK')
"""
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", M28_CSV=str(tmp_path / "cost.csv"))
    result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "M28_UI_OK" in result.stdout


def test_cost_orm_writers_cannot_persist_stale_variance(env):
    from core.database import CostRecord
    db, wid = env
    with db.session_scope() as session:
        row = CostRecord(well_id=wid, category="Rig", planned_cost=100, actual_cost=130,
                         currency=" eur ", variance=999)
        session.add(row)
        session.flush()
        assert row.variance == -30 and row.currency == "EUR"
        row.actual_cost = None
        session.flush()
        assert row.variance is None
