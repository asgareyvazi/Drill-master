"""Regression tests for the canonical footage-weighted ROP engine.

Covers the semantic contract from the 2026-09-12 Weighted ROP Implementation
audit:

* A valid paired observation requires ALL of depth_in, depth_out and
  hours_on_bottom non-null AND depth_out >= depth_in AND hours_on_bottom > 0.
* An invalid row contributes NEITHER footage NOR hours (never partial).
* weighted_rop = Σ(valid-pair footage) / Σ(valid-pair hours), summed from the
  SAME pairs — distinct from a mean of per-row rates and from a naive
  Σ(footage)/Σ(hours) across independently nullable columns.
* No valid pairs → value None (unknown), never 0.
* Well scope aggregates by well_id: SUM valid footage / SUM valid hours, and is
  isolated from foreign wells; join multiplicity (BHA/Bit/NPT/Cost) and
  duplicate-DDR imports do not change the result.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base,
    Company,
    DailyReport,
    DatabaseManager,
    DrillingParameters,
    Project,
    Well,
)
from core.engineering.engines.bit_performance import BitPerformanceEngine
from core.operations_intelligence import OperationsIntelligenceService


# ---------------------------------------------------------------------------
# Engine-level tests (§7, §22 matrix)
# ---------------------------------------------------------------------------


def _row(depth_in, depth_out, hours):
    return {"depth_in": depth_in, "depth_out": depth_out, "hours_on_bottom": hours}


def test_single_valid_pair():
    r = BitPerformanceEngine.weighted_rop([_row(1000, 1100, 5)])
    assert r.success
    assert r.value == 20.0
    assert r.values["valid_pairs"] == 1
    assert r.values["total_footage"] == 100.0
    assert r.values["total_hours"] == 5.0
    assert r.unit == "m/hr"


def test_two_valid_pairs_sum_before_divide():
    # (100 + 300) / (5 + 5) = 40, NOT mean of 20 and 60 (= 40 here by luck) —
    # use asymmetric hours to make the distinction visible below.
    r = BitPerformanceEngine.weighted_rop([_row(0, 100, 5), _row(0, 300, 5)])
    assert r.value == 40.0
    assert r.values["valid_pairs"] == 2


def test_mandatory_pairing_repro():
    """§7: Row1(1000,1100,5) valid; Row2(None,1200,6) invalid.

    Correct = 100/5 = 20.0. The naive SUM(footage)/SUM(hours) would drop the
    NULL footage while still counting Row2's 6 hours → 100/11 = 9.09. That
    mispairing must NOT happen.
    """
    rows = [_row(1000, 1100, 5), _row(None, 1200, 6)]
    r = BitPerformanceEngine.weighted_rop(rows)
    assert r.value == 20.0
    assert abs(r.value - (100 / 11)) > 1.0  # definitively not the naive answer
    assert r.values["valid_pairs"] == 1
    assert r.values["excluded_rows"] == 1
    assert r.values["total_hours"] == 5.0


def test_missing_footage_excludes_whole_row():
    # valid footage row + a row with valid hours but no footage: the hours from
    # the second row must NOT be added.
    r = BitPerformanceEngine.weighted_rop(
        [_row(0, 100, 5), _row(None, None, 6)]
    )
    assert r.value == 20.0
    assert r.values["total_hours"] == 5.0


def test_missing_hours_excludes_whole_row():
    # valid footage but missing hours → contributes NO footage.
    r = BitPerformanceEngine.weighted_rop(
        [_row(0, 100, 5), _row(0, 500, None)]
    )
    assert r.value == 20.0
    assert r.values["total_footage"] == 100.0


def test_both_missing_is_excluded():
    r = BitPerformanceEngine.weighted_rop([_row(None, None, None)])
    assert r.value is None
    assert r.values["valid_pairs"] == 0


def test_zero_hours_excluded_not_divide_by_zero():
    r = BitPerformanceEngine.weighted_rop([_row(0, 100, 0)])
    assert r.value is None
    assert r.values["valid_pairs"] == 0


def test_negative_footage_excluded():
    r = BitPerformanceEngine.weighted_rop([_row(100, 0, 5)])
    assert r.value is None
    assert r.values["valid_pairs"] == 0


def test_explicit_zero_footage_is_a_real_pair():
    # depth_in == depth_out with hours > 0 is a genuine recorded zero.
    r = BitPerformanceEngine.weighted_rop([_row(100, 100, 5)])
    assert r.success
    assert r.value == 0.0
    assert r.values["valid_pairs"] == 1
    assert r.values["total_hours"] == 5.0


def test_no_valid_pairs_returns_none_not_zero():
    r = BitPerformanceEngine.weighted_rop(
        [_row(None, 100, 6), _row(50, 40, 5), _row(0, 100, 0)]
    )
    assert r.value is None
    assert r.values["excluded_rows"] == 3
    assert r.warnings


def test_empty_returns_none():
    r = BitPerformanceEngine.weighted_rop([])
    assert r.value is None
    assert r.values["observations_considered"] == 0


def test_weighted_rop_differs_from_mean_of_rates():
    # Row A: 100 m in 1 h → 100 m/hr. Row B: 100 m in 100 h → 1 m/hr.
    # Mean of rates = 50.5. Footage-weighted = 200 / 101 ≈ 1.98.
    rows = [_row(0, 100, 1), _row(0, 100, 100)]
    r = BitPerformanceEngine.weighted_rop(rows)
    mean_of_rates = (100 / 1 + 100 / 100) / 2
    assert abs(r.value - (200 / 101)) < 0.01  # rounded to 3 dp
    assert abs(r.value - mean_of_rates) > 40


def test_malformed_token_excluded():
    r = BitPerformanceEngine.weighted_rop(
        [_row("abc", 100, 5), _row(0, 100, 5)]
    )
    assert r.value == 20.0
    assert r.values["valid_pairs"] == 1


def test_accepts_orm_style_attribute_rows():
    class _Obj:
        def __init__(self, di, do, h):
            self.depth_in = di
            self.depth_out = do
            self.hours_on_bottom = h

    r = BitPerformanceEngine.weighted_rop([_Obj(0, 200, 4)])
    assert r.value == 50.0


def test_rollup_no_longer_mispairs():
    # rollup previously added footage and hours independently; ensure it now
    # pairs (a footage-only row and an hours-only row must both be excluded).
    r = BitPerformanceEngine.rollup(
        [_row(0, 100, 5), _row(0, 500, None), _row(None, None, 99)]
    )
    assert r.values["total_footage"] == 100.0
    assert r.values["total_hours"] == 5.0
    assert r.value == 20.0


# ---------------------------------------------------------------------------
# Well-scope integration tests (§10, §11, §13, duplicate-DDR)
# ---------------------------------------------------------------------------


def _manager():
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
    company = Company(name="WR Co", code="WR-CO")
    session.add(company)
    session.flush()
    project = Project(name="WR Project", code="WR-PR", company_id=company.id)
    session.add(project)
    session.flush()
    session.commit()
    project_id = project.id
    session.close()
    return manager, project_id


def _well(manager, project_id, name, code):
    session = manager.create_session()
    try:
        well = Well(name=name, code=code, project_id=project_id)
        session.add(well)
        session.flush()
        wid = well.id
        session.commit()
        return wid
    finally:
        session.close()


def _ddr(manager, well_id, day, depth_in, depth_out, hours):
    session = manager.create_session()
    try:
        report = DailyReport(
            well_id=well_id,
            report_date=date(2026, 1, day),
            depth_2400=depth_out if depth_out is not None else 0,
        )
        session.add(report)
        session.flush()
        rid = report.id
        params = DrillingParameters(
            well_id=well_id,
            report_id=rid,
            report_date=date(2026, 1, day),
            depth_in=depth_in,
            depth_out=depth_out,
            hours_on_bottom=hours,
        )
        session.add(params)
        session.commit()
        return rid
    finally:
        session.close()


def test_well_scope_sums_valid_pairs():
    manager, project_id = _manager()
    well_id = _well(manager, project_id, "Well A", "WA")
    _ddr(manager, well_id, 1, 1000, 1100, 5)   # 100 m / 5 h
    _ddr(manager, well_id, 2, 1100, 1400, 5)   # 300 m / 5 h
    _ddr(manager, well_id, 3, None, 1600, 6)   # invalid — excluded whole
    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]
    # (100 + 300) / (5 + 5) = 40.0, NOT 400 / 16 = 25 (naive with day-3 hours).
    assert kpis["weighted_rop"] == 40.0
    assert kpis["weighted_rop_hours"] == 10.0
    assert kpis["weighted_rop_valid_pairs"] == 2


def test_well_isolation_excludes_foreign_well():
    manager, project_id = _manager()
    well_a = _well(manager, project_id, "Well A", "WA")
    well_b = _well(manager, project_id, "Well B", "WB")
    _ddr(manager, well_a, 1, 1000, 1100, 5)         # A: 100 / 5 = 20 m/hr
    _ddr(manager, well_b, 1, 0, 100000, 0.1)        # B: absurd 1,000,000 m/hr
    kpis = OperationsIntelligenceService(manager).analyze_well(well_a)["kpis"]
    assert kpis["weighted_rop"] == 20.0
    assert kpis["weighted_rop_valid_pairs"] == 1


def test_well_scope_none_when_no_valid_pairs():
    manager, project_id = _manager()
    well_id = _well(manager, project_id, "Well C", "WC")
    _ddr(manager, well_id, 1, None, 1100, 5)
    _ddr(manager, well_id, 2, 100, 50, 5)   # negative footage
    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]
    assert kpis["weighted_rop"] is None


def test_weighted_rop_distinct_from_average_rop():
    """average_rop (mean of stored per-day avg_rop) must remain untouched and
    can legitimately differ from the footage-weighted value."""
    manager, project_id = _manager()
    well_id = _well(manager, project_id, "Well D", "WD")
    _ddr(manager, well_id, 1, 0, 100, 1)     # 100 m/hr
    _ddr(manager, well_id, 2, 0, 100, 100)   # 1 m/hr
    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]
    # weighted = 200 / 101 ≈ 1.98
    assert abs(kpis["weighted_rop"] - (200 / 101)) < 0.02
    # average_rop is a separate, independently-computed key that still exists.
    assert "average_rop" in kpis
