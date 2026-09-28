"""Adversarial M30 contracts: real database/service paths, no in-process Qt widgets."""
from datetime import date, time
from types import SimpleNamespace

import pytest

from core.database import DailyReport, Section, TimeLog24H, BulkMaterials
from core.scope_attribution import ScopeAttributionService, INVALID
from test_scope_attribution import _mgr, _base, _well, _wellbore, _section, _report, _get_report


@pytest.fixture
def env():
    db = _mgr()
    project = _base(db)
    a, b = _well(db, project, "Needle_A"), _well(db, project, "Needle_B")
    ba, bb = _wellbore(db, a, "Same"), _wellbore(db, b, "Same")
    sa, sb = _section(db, a, "Same", wellbore_id=ba), _section(db, b, "Same", wellbore_id=bb)
    ra, rb = _report(db, a, 1, wellbore_id=ba, section_id=sa), _report(db, b, 1, wellbore_id=bb, section_id=sb)
    with db.session_scope() as s:
        for rid in (ra, rb):
            s.get(DailyReport, rid).summary = "needle operations"
            s.add(TimeLog24H(report_id=rid, time_from=time(0), time_to=time(1), duration=1,
                             activity_description="needle log", is_npt=False))
    yield db, dict(a=a, b=b, ba=ba, bb=bb, sa=sa, sb=sb, ra=ra, rb=rb)
    db.close()


def test_search_honors_well_scope_for_every_entity_and_ai(env):
    from core.rag_search import HistoricalDDRSearch
    db, x = env
    hits = db.search_all("needle", well_id=x["a"])
    assert len(hits) == 3
    assert {h["well_id"] for h in hits} == {x["a"]}
    assert db.search_all("needle", well_id=0) == []
    result = HistoricalDDRSearch(db).rag_query("needle", x["a"])
    assert result["status"] == "matched" and result["confidence"] is None
    assert all(e["confidence"] is None for e in result["evidence"])
    assert next(e for e in result["evidence"] if e["type"] == "well")["source_report"] is None
    assert next(e for e in result["evidence"] if e["type"] == "timelog")["source_report"] == x["ra"]


def test_search_literal_wildcards_are_not_pattern_syntax(env):
    db, x = env
    with db.session_scope() as s:
        s.get(DailyReport, x["ra"]).summary = "100%_literal"
    hits = db.search_all("%_", well_id=x["a"])
    assert [(h["type"], h["id"]) for h in hits] == [("report", x["ra"])]


def test_failed_retrieval_is_not_empty_success():
    from core.rag_search import HistoricalDDRSearch
    def fail(*args, **kwargs):
        raise RuntimeError("locked database")
    service = HistoricalDDRSearch(SimpleNamespace(search_all=fail))
    with pytest.raises(RuntimeError):
        service.search("needle")
    result = service.rag_query("needle")
    assert result["status"] == "failed" and result["confidence"] is None
    assert result["evidence"] == []
    assert "No relevant" not in result["answer"]


def test_scope_coverage_distinguishes_persisted_from_possible(env):
    db, x = env
    r = _report(db, x["a"], 2)
    service = ScopeAttributionService(db)
    before = service.coverage(x["a"])
    assert before["wellbore_coverage_pct"] == 50
    assert before["wellbore_attributable_pct"] == 100
    assert _get_report(db, r) == (None, None)
    service.resolve(x["a"])
    assert service.coverage(x["a"])["wellbore_coverage_pct"] == 100
    assert service.resolve(x["a"]).applied == 0


def test_scope_rejects_invalid_unassigned_candidates_without_mutation(env):
    db, x = env
    # Two bores avoid a unique-bore fallback; the sole section is now malformed.
    _wellbore(db, x["a"], "Second")
    r = _report(db, x["a"], 2)
    with db.engine.begin() as c:
        c.execute(Section.__table__.update().where(Section.id == x["sa"]).values(wellbore_id=x["bb"]))
    service = ScopeAttributionService(db)
    for well_filter in (x["a"], None):
        outcomes = [o for o in service.analyze(well_filter).outcomes if o.report_id == r]
        assert len(outcomes) == 2 and all(o.status == INVALID for o in outcomes)
        assert service.resolve(well_filter).applied == 0
    assert _get_report(db, r) == (None, None)


def test_attribution_serialization_does_not_alias_outcomes(env):
    db, x = env
    report = ScopeAttributionService(db).analyze(x["a"])
    payload = report.as_dict()
    original = report.outcomes[0].target_id
    payload["outcomes"][0]["target_id"] = -999
    assert report.outcomes[0].target_id == original


@pytest.mark.parametrize("bad", ["not-a-number", True, float("nan"), float("inf")])
def test_invalid_inventory_movement_rolls_back_prior_worksheet(env, bad):
    from core.engineering.result import EngineeringError
    db, x = env
    original = dict(item_name="Gloves", unit="pcs", opening_stock=10, received=0, used=0)
    db.save_inventory_items(x["a"], x["ra"], [original], report_date=date(2026, 1, 1))
    before = db.get_inventory_items(well_id=x["a"], report_id=x["ra"])
    with pytest.raises(EngineeringError):
        db.save_inventory_items(x["a"], x["ra"], [dict(original, received=bad)])
    assert db.get_inventory_items(well_id=x["a"], report_id=x["ra"]) == before


def test_carry_forward_requires_same_unit_and_unique_latest_date(env):
    db, x = env
    db.save_inventory_items(x["a"], x["ra"], [dict(item_name="Chemical", unit="kg", opening_stock=100)], report_date=date(2026, 1, 1))
    next_report = _report(db, x["a"], 2, wellbore_id=x["ba"], section_id=x["sa"])
    db.save_inventory_items(x["a"], next_report, [dict(item_name="Chemical", unit="ton")], report_date=date(2026, 1, 2))
    assert db.get_inventory_items(report_id=next_report)[0]["opening_stock"] is None
    # Distinct report, same latest day and unit: neither closing proves an owner.
    sec = _section(db, x["a"], "Other", wellbore_id=x["ba"])
    duplicate_day = _report(db, x["a"], 1, wellbore_id=x["ba"], section_id=sec)
    db.save_inventory_items(x["a"], duplicate_day, [dict(item_name="Chemical", unit="kg", opening_stock=999)], report_date=date(2026, 1, 1))
    db.save_inventory_items(x["a"], next_report, [dict(item_name="Chemical", unit="kg")], report_date=date(2026, 1, 2))
    assert db.get_inventory_items(report_id=next_report)[0]["opening_stock"] is None


def test_bulk_same_name_different_unit_does_not_overwrite(env):
    db, x = env
    payload = dict(well_id=x["a"], report_id=x["ra"], report_date=date(2026, 1, 1), material_name="Chemical", initial_stock=10)
    kg = db.save_bulk_material(dict(payload, unit="kg"))
    ton = db.save_bulk_material(dict(payload, unit="ton", initial_stock=20))
    assert kg and ton and kg != ton
    with db.session_scope() as s:
        rows = s.query(BulkMaterials).filter_by(report_id=x["ra"]).all()
        assert {(r.unit, r.initial_stock) for r in rows} == {("kg", 10), ("ton", 20)}
    # Wrong well on an otherwise valid report must not mutate its existing row.
    assert not db.save_bulk_material(dict(payload, well_id=x["b"], unit="kg", initial_stock=999))
    with db.session_scope() as s:
        assert s.get(BulkMaterials, kg).initial_stock == 10


@pytest.mark.parametrize("bad", ["broken", True, float("nan"), float("inf"), -1])
def test_invalid_recorded_time_does_not_produce_factual_totals(bad):
    from core.operational_time import summarize_time_logs
    result = summarize_time_logs([SimpleNamespace(duration=bad, is_npt=True)])
    assert result["total_hours"] is None and result["npt_hours"] is None
    assert result["unknown_duration_count"] == 1


def test_nonboolean_npt_classification_is_unknown():
    from core.operational_time import summarize_time_logs
    result = summarize_time_logs([SimpleNamespace(duration=1, is_npt="False")])
    assert result["total_hours"] == 1 and result["npt_hours"] is None


def test_comparison_formula_matches_negative_plan_denominator():
    from core.actual_vs_plan import ActualVsPlanEngine
    result = ActualVsPlanEngine.compare_metrics({"cost": -100}, {"cost": -80})
    assert result.values["cost"]["variance_pct"] == 20
    assert "abs(planned)" in result.formula



def test_backup_source_disappearing_does_not_create_empty_success(tmp_path, monkeypatch):
    import sqlite3
    from core.database import DatabaseManager
    source, destination = tmp_path / "source.db", tmp_path / "previous.db"
    with sqlite3.connect(source) as c:
        c.execute("CREATE TABLE witness (value INTEGER)")
    destination.write_bytes(b"previous backup")
    db = DatabaseManager.__new__(DatabaseManager)
    db.db_path = str(source)
    real_connect = sqlite3.connect
    first = True
    def disappear(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            source.unlink()
        return real_connect(*args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", disappear)
    assert db.backup_to(destination) is None
    assert destination.read_bytes() == b"previous backup"
    assert not source.exists()
    assert not list(tmp_path.glob(".drillmaster-backup-*"))


@pytest.mark.parametrize("inputs", [(1, 1, 1, 1, 1e-200), (1, 1, 1, 1, 1e200),
                                    (1, 1e308, 1e308, 1, 8.5)])
def test_mse_never_reports_nonfinite_or_underflowed_calculation_as_success(inputs):
    from core.engineering.engines.mse import MSEEngine
    result = MSEEngine.calculate(*inputs)
    assert result.success is False and result.validation_status == "error"


def test_search_database_exception_reaches_ui_failed_state(env, monkeypatch):
    from main_window import MainWindow
    messages = []
    def fail(*args, **kwargs):
        raise RuntimeError("locked DB")
    db, x = env
    closed = []
    monkeypatch.setattr(db, "create_session", lambda: SimpleNamespace(
        query=fail, close=lambda: closed.append(True)))
    stub = SimpleNamespace(search_input=SimpleNamespace(text=lambda: "needle"),
                           sel_manager=SimpleNamespace(current_well_id=1),
                           db_manager=db,
                           status_manager=SimpleNamespace(show_message=lambda *args: messages.append(args)))
    assert MainWindow._global_search(stub) is False
    assert "FAILED" in messages[0][1]
    assert closed == [True]


def test_bulk_duplicate_identity_is_not_first_match_mutation(env):
    db, x = env
    payload = dict(well_id=x["a"], report_id=x["ra"], report_date=date(2026, 1, 1),
                   material_name="Chemical", unit="kg", initial_stock=10)
    with db.session_scope() as s:
        s.add_all([BulkMaterials(**payload), BulkMaterials(**payload)])
    assert not db.save_bulk_material(dict(payload, initial_stock=999))
    with db.session_scope() as s:
        assert [r.initial_stock for r in s.query(BulkMaterials).filter_by(report_id=x["ra"])] == [10, 10]


def test_inventory_ui_invalid_calculation_and_unattached_saves_in_subprocess():
    import os
    import subprocess
    import sys
    script = """
from PySide6.QtWidgets import QApplication, QMessageBox
from tabs.w5_Equipment_Widget import InventoryTab, RigEquipmentTab, DrillPipeTab, SolidControlTab
app = QApplication([])
successes, errors = [], []
QMessageBox.information = lambda *a: successes.append(a)
QMessageBox.warning = lambda *a: errors.append(a)
for cls in (InventoryTab, RigEquipmentTab, DrillPipeTab, SolidControlTab):
    widget = cls()
    assert widget.save_data() is False, cls.__name__
assert len(errors) == 4 and not successes
tab = InventoryTab()
tab.load_table_data([["Gloves", "PPE", "100", "0", "0", "", "pcs", "", ""]])
tab.calculate_inventory()
assert tab.table.item(0, 5).text() == "100.00"
tab.table.item(0, 3).setText("broken")
assert tab.calculate_inventory() is False
assert tab.table.item(0, 5).text() == "INVALID"
print("M30_UI_OK")
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            env=dict(os.environ, QT_QPA_PLATFORM="offscreen"), timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "M30_UI_OK" in result.stdout



@pytest.mark.parametrize("operation", ["total", "variance", "percentage", "plan"])
def test_finite_financial_inputs_must_not_emit_infinite_facts(operation):
    from core.cost_semantics import complete_total, canonical_variance, percent_used
    from core.actual_vs_plan import compare
    from core.engineering.result import EngineeringError
    calls = {"total": lambda: complete_total([1e308, 1e308]),
             "variance": lambda: canonical_variance(1e308, -1e308),
             "percentage": lambda: percent_used(1e-308, 1e308),
             "plan": lambda: compare("Cost", 1e308, -1e308)}
    with pytest.raises(EngineeringError):
        calls[operation]()



@pytest.mark.parametrize("bad", ["bad", True, False, float("nan"), float("inf")])
def test_bad_bulk_movement_preserves_previous_row(env, bad):
    db, x = env
    payload = dict(well_id=x["a"], report_id=x["ra"], report_date=date(2026, 1, 1),
                   material_name="Chemical", unit="kg", initial_stock=10)
    identity = db.save_bulk_material(payload)
    assert not db.save_bulk_material(dict(payload, received=bad))
    with db.session_scope() as s:
        row = s.get(BulkMaterials, identity)
        assert row.current_stock == 10 and row.received == 0



@pytest.mark.parametrize("parser", ["require_number", "optional_number"])
def test_unrepresentable_integer_uses_engineering_error_contract(parser):
    import core.engineering.result as result
    with pytest.raises(result.EngineeringError):
        getattr(result, parser)(10 ** 500, "measurement")



def test_read_only_legacy_inventory_decoder_handles_huge_integer():
    from core.inventory_semantics import to_float_or_none
    assert to_float_or_none(10 ** 500) is None



@pytest.mark.parametrize("currency", ["unknown", "N/A", "not recorded", "—"])
def test_explicit_unknown_currency_markers_do_not_authorize_money_totals(currency):
    from core.cost_semantics import summarize_costs, normalize_currency
    rows = [dict(currency=currency, category="OPEX", planned_cost=10, actual_cost=8)] * 2
    assert normalize_currency(currency) is None
    result = summarize_costs(rows)
    assert result["status"] == "unknown-currency"
    assert result["total_actual"] is None and result["total_planned"] is None
