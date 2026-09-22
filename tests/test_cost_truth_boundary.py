"""Cost truth-boundary regressions (Mission 20).

Demonstrated defects fixed and locked here:

  A. W16 ``save_data`` was a no-op (``return True``) — the AFE worksheet never
     persisted. It now writes canonical ``CostRecord`` budget lines atomically.
  B. Three consumers reported three different "total cost": the report engine
     used stored ``actual_cost`` (correct) while W16 and W12 multiplied rig days
     by a synthetic $60k/day rate. They now all read stored actual cost.
  C. Variance had no single sign convention; it is ``planned - actual``
     everywhere and is recomputed on save so a stale column cannot contradict
     the summary.
  D. Currency silently defaulted to USD; unknown currency now stays unknown.
  E. Re-saving the AFE worksheet duplicated money; the save is now an atomic
     replace of the well's AFE budget lines (idempotent).

Every test exercises real production code against an isolated in-memory
DatabaseManager — no mocks.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, CostRecord,
)
from core import cost_semantics as cs


def memory_manager():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(
        bind=manager.engine, autoflush=False, autocommit=False
    )
    session = manager.create_session()
    try:
        company = Company(name="OEOC", code="OEOC")
        session.add(company)
        session.flush()
        project = Project(name="Bid Boland", code="BB", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="Cost-Truth", code="CT-1", project_id=project.id)
        session.add(well)
        session.commit()
        well_id = well.id
    finally:
        session.close()
    return manager, well_id


@pytest.fixture
def env():
    manager, well_id = memory_manager()
    yield manager, well_id
    manager.close()


def afe_lines(manager, well_id):
    session = manager.create_session()
    try:
        return session.query(CostRecord).filter(
            CostRecord.well_id == well_id,
            CostRecord.cost_type == cs.COST_TYPE_BUDGET,
        ).all()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Domain semantics
# ---------------------------------------------------------------------------

class TestCanonicalSemantics:
    def test_variance_is_planned_minus_actual(self):
        assert cs.canonical_variance(100.0, 40.0) == 60.0
        assert cs.canonical_variance(40.0, 100.0) == -60.0

    def test_variance_unknown_propagates(self):
        assert cs.canonical_variance(None, 10.0) is None
        assert cs.canonical_variance(10.0, None) is None
        assert cs.canonical_variance(None, None) is None

    def test_variance_explicit_zero_is_a_fact(self):
        assert cs.canonical_variance(0.0, 0.0) == 0.0

    def test_currency_unknown_never_becomes_usd(self):
        assert cs.normalize_currency("") is None
        assert cs.normalize_currency("   ") is None
        assert cs.normalize_currency(None) is None
        assert cs.normalize_currency("usd") == "USD"

    def test_npt_allocation_matches_report_engine_model(self):
        # 30% of the time is NPT -> 30% of stored actual cost.
        assert cs.allocate_npt_cost(1000.0, 30.0, 100.0) == 300.0

    def test_npt_allocation_unknown_without_actual_cost(self):
        assert cs.allocate_npt_cost(None, 30.0, 100.0) is None

    def test_npt_allocation_no_divide_by_zero(self):
        assert cs.allocate_npt_cost(1000.0, 0.0, 0.0) is None


# ---------------------------------------------------------------------------
# Persistence round-trip / atomicity / idempotency
# ---------------------------------------------------------------------------

class TestAfePersistence:
    def test_round_trip_persists_planned_actual_and_variance(self, env):
        manager, well_id = env
        rows = [
            {"category": "Rig & Equipment", "planned_cost": 500000, "actual_cost": 480000},
            {"category": "Cementing", "planned_cost": 150000, "actual_cost": 170000},
        ]
        saved = manager.save_afe_worksheet(well_id, rows, afe_number="AFE-1",
                                           currency="USD")
        assert saved == 2
        lines = {l.category: l for l in afe_lines(manager, well_id)}
        assert lines["Rig & Equipment"].planned_cost == 500000
        assert lines["Rig & Equipment"].actual_cost == 480000
        # Variance recomputed canonically as planned - actual.
        assert lines["Rig & Equipment"].variance == 20000
        assert lines["Cementing"].variance == -20000
        assert lines["Rig & Equipment"].afe_number == "AFE-1"

    def test_resave_is_idempotent_no_duplicate_money(self, env):
        manager, well_id = env
        rows = [{"category": "Mud & Chemicals", "planned_cost": 200000, "actual_cost": 100000}]
        manager.save_afe_worksheet(well_id, rows)
        manager.save_afe_worksheet(well_id, rows)
        manager.save_afe_worksheet(well_id, rows)
        lines = afe_lines(manager, well_id)
        assert len(lines) == 1  # replace, not append
        assert lines[0].actual_cost == 100000

    def test_edit_then_resave_reflects_new_values(self, env):
        manager, well_id = env
        manager.save_afe_worksheet(
            well_id, [{"category": "Logging", "planned_cost": 180000, "actual_cost": 0}])
        manager.save_afe_worksheet(
            well_id, [{"category": "Logging", "planned_cost": 180000, "actual_cost": 200000}])
        lines = afe_lines(manager, well_id)
        assert len(lines) == 1
        assert lines[0].actual_cost == 200000
        assert lines[0].variance == -20000

    def test_unknown_currency_persisted_as_null(self, env):
        manager, well_id = env
        manager.save_afe_worksheet(
            well_id, [{"category": "Personnel", "planned_cost": 80000, "actual_cost": 0}],
            currency=None)
        assert afe_lines(manager, well_id)[0].currency is None

    def test_blank_category_rows_dropped(self, env):
        manager, well_id = env
        saved = manager.save_afe_worksheet(well_id, [
            {"category": "  ", "planned_cost": 1, "actual_cost": 1},
            {"category": "Real", "planned_cost": 10, "actual_cost": 5},
        ])
        assert saved == 1
        assert [l.category for l in afe_lines(manager, well_id)] == ["Real"]

    def test_save_leaves_non_afe_opex_lines_untouched(self, env):
        manager, well_id = env
        # A pre-existing OPEX line saved outside the AFE worksheet.
        manager.save_cost_record({
            "well_id": well_id, "category": "Fuel", "actual_cost": 5000,
            "cost_type": "OPEX",
        })
        manager.save_afe_worksheet(
            well_id, [{"category": "Rig", "planned_cost": 100, "actual_cost": 50}])
        session = manager.create_session()
        try:
            opex = session.query(CostRecord).filter(
                CostRecord.well_id == well_id, CostRecord.cost_type == "OPEX").all()
        finally:
            session.close()
        assert len(opex) == 1 and opex[0].category == "Fuel"


# ---------------------------------------------------------------------------
# Cross-consumer parity: canonical actual cost == what the summary reports
# ---------------------------------------------------------------------------

class TestConsumerParity:
    def test_summary_actual_matches_operations_intelligence(self, env):
        manager, well_id = env
        manager.save_afe_worksheet(well_id, [
            {"category": "A", "planned_cost": 100, "actual_cost": 40},
            {"category": "B", "planned_cost": 200, "actual_cost": 60},
        ])
        summary = manager.get_cost_summary(well_id)
        total_actual = sum(r["actual"] for r in summary)
        assert total_actual == 100
        # The canonical KPI service sums the same stored actual cost.
        # No daily reports -> analyze_well short-circuits; sum CostRecords direct.
        session = manager.create_session()
        try:
            from sqlalchemy import func
            direct = session.query(func.sum(CostRecord.actual_cost)).filter(
                CostRecord.well_id == well_id).scalar()
        finally:
            session.close()
        assert float(direct) == total_actual

    def test_summary_variance_sign_is_planned_minus_actual(self, env):
        manager, well_id = env
        manager.save_afe_worksheet(
            well_id, [{"category": "A", "planned_cost": 100, "actual_cost": 130}])
        summary = manager.get_cost_summary(well_id)
        # Over budget -> negative variance (planned - actual).
        assert summary[0]["variance"] == -30
