"""Regression coverage for Operations Intelligence model/schema alignment."""

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
    Section,
    Well,
)
from core.operations_intelligence import OperationsIntelligenceService


def _manager_with_report():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)

    session = manager.create_session()
    company = Company(name="OI Regression Company", code="OI-CO")
    session.add(company)
    session.flush()
    project = Project(name="OI Regression Project", code="OI-PR", company_id=company.id)
    session.add(project)
    session.flush()
    well = Well(name="OI Regression Well", code="OI-WELL", project_id=project.id)
    session.add(well)
    session.flush()
    section = Section(name="12-1/4 in", well_id=well.id)
    session.add(section)
    session.flush()
    report = DailyReport(
        well_id=well.id,
        section_id=section.id,
        report_number=1,
        report_date=date(2025, 10, 27),
        depth_2400=1000.0,
    )
    session.add(report)
    session.flush()
    session.add(
        DrillingParameters(
            well_id=well.id,
            report_id=report.id,
            report_date=report.report_date,
            wob_min=10.0,
            wob_max=20.0,
            torque_min=100.0,
            torque_max=140.0,
            rpm_min=80.0,
            rpm_max=100.0,
            avg_rop=12.5,
        )
    )
    session.commit()
    well_id = well.id
    session.close()
    return manager, well_id


def test_operations_intelligence_uses_current_drilling_parameters_schema():
    manager, well_id = _manager_with_report()
    result = OperationsIntelligenceService(manager).analyze_well(well_id)

    assert "error" not in result["kpis"]
    assert result["kpis"]["wob_trend"] == [15.0]
    assert result["kpis"]["torque_trend"] == [120.0]
    assert result["kpis"]["rpm_trend"] == [90.0]


from datetime import time as _time

from core.database import DailyReport as _DailyReport, TimeLog24H, Well as _Well


def _manager_empty_well():
    """A well with one daily report but no time logs and no drilling params.

    ROP, NPT% and productive time are therefore genuinely unknown.
    """
    manager, existing_well_id = _manager_with_report()
    session = manager.create_session()
    try:
        project_id = session.get(_Well, existing_well_id).project_id
        well = _Well(name="Unknown Metrics Well", code="OI-EMPTY", project_id=project_id)
        session.add(well)
        session.flush()
        session.add(
            _DailyReport(
                well_id=well.id,
                report_number=1,
                report_date=date(2025, 10, 28),
                depth_2400=500.0,
            )
        )
        session.commit()
        well_id = well.id
    finally:
        session.close()
    return manager, well_id


def test_unknown_rop_and_npt_are_none_not_fabricated_zero():
    """KPI-01 regression: absent source data yields None (unknown), not 0.0.

    Reporting 0.0 m/hr ROP or 0% NPT for a well with no time logs / no
    drilling parameters asserts a false fact. Unknown must stay unknown, the
    same no-fabrication contract already applied to cost_per_meter.
    """
    manager, well_id = _manager_empty_well()
    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]

    assert kpis["average_rop"] is None
    assert kpis["npt_percent"] is None
    assert kpis["productive_hours"] is None
    # Unknown NPT must not fabricate an NPT insight, and analysis must not crash.
    assert "error" not in kpis
    # cost stays None too (no cost records) — unchanged behaviour.
    assert kpis["cost_per_meter"] is None


def test_known_rop_and_npt_are_computed():
    """With time logs and ROP present, real values are still reported."""
    manager, existing_well_id = _manager_with_report()
    session = manager.create_session()
    try:
        project_id = session.get(_Well, existing_well_id).project_id
        well = _Well(name="Known Metrics Well", code="OI-KNOWN", project_id=project_id)
        session.add(well)
        session.flush()
        report = _DailyReport(
            well_id=well.id, report_number=1,
            report_date=date(2025, 10, 29), depth_2400=800.0,
        )
        session.add(report)
        session.flush()
        session.add(TimeLog24H(
            report_id=report.id, time_from=_time(0), time_to=_time(18),
            duration=18.0, is_npt=False,
        ))
        session.add(TimeLog24H(
            report_id=report.id, time_from=_time(18), time_to=_time(23, 59),
            duration=6.0, is_npt=True,
        ))
        session.add(DrillingParameters(
            well_id=well.id, report_id=report.id,
            report_date=report.report_date, avg_rop=15.0,
        ))
        session.commit()
        well_id = well.id
    finally:
        session.close()

    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]
    assert kpis["average_rop"] == 15.0
    assert kpis["npt_percent"] == 25.0  # 6 of 24 hours
    assert kpis["productive_hours"] == 18.0


from core.database import (
    BHAReport as _BHAReport,
    BitReport as _BitReport,
    CostRecord as _CostRecord,
    Section as _Section,
    Wellbore as _Wellbore,
)


def test_canonical_kpis_do_not_multiply_across_one_to_many_children():
    """Multiplicity guard (coverage audit §16/§21).

    A single DailyReport that carries two BHA snapshots, two Bit snapshots,
    three NPT time logs and two cost records must NOT have its NPT / ROP / cost
    KPIs multiplied by a Cartesian join. Canonical analysis reads each
    one-to-many child in its own query, so the numbers stay singular.
    """
    manager, existing_well_id = _manager_with_report()
    session = manager.create_session()
    try:
        project_id = session.get(_Well, existing_well_id).project_id
        well = _Well(name="Multiplicity Well", code="OI-MULT", project_id=project_id)
        session.add(well)
        session.flush()
        report = _DailyReport(
            well_id=well.id, report_number=1,
            report_date=date(2026, 1, 1), depth_2400=1000.0,
        )
        session.add(report)
        session.flush()
        # 24 h total, 6 h NPT across three separate NPT rows.
        session.add(TimeLog24H(report_id=report.id, time_from=_time(0), time_to=_time(18),
                               duration=18.0, is_npt=False))
        session.add(TimeLog24H(report_id=report.id, time_from=_time(18), time_to=_time(20),
                               duration=2.0, is_npt=True))
        session.add(TimeLog24H(report_id=report.id, time_from=_time(20), time_to=_time(22),
                               duration=2.0, is_npt=True))
        session.add(TimeLog24H(report_id=report.id, time_from=_time(22), time_to=_time(23, 59),
                               duration=2.0, is_npt=True))
        session.add(DrillingParameters(well_id=well.id, report_id=report.id,
                                       report_date=report.report_date, avg_rop=25.0))
        # Two BHA + two Bit report-scoped snapshots on the SAME report.
        session.add(_BHAReport(well_id=well.id, report_id=report.id, bha_name="BHA-1", bha_data_json=[]))
        session.add(_BHAReport(well_id=well.id, report_id=report.id, bha_name="BHA-2", bha_data_json=[]))
        session.add(_BitReport(well_id=well.id, report_id=report.id, report_date=report.report_date,
                               report_name="Bit-1", bit_records_json=[]))
        session.add(_BitReport(well_id=well.id, report_id=report.id, report_date=report.report_date,
                               report_name="Bit-2", bit_records_json=[]))
        session.add(_CostRecord(well_id=well.id, category="Rig", actual_cost=100000.0))
        session.add(_CostRecord(well_id=well.id, category="Mud", actual_cost=50000.0))
        session.commit()
        well_id = well.id
    finally:
        session.close()

    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]
    assert kpis["reports"] == 1
    assert kpis["npt_hours"] == 6.0            # not 6 × (2 BHA) × (2 Bit)
    assert kpis["npt_percent"] == 25.0         # 6 / 24
    assert kpis["productive_hours"] == 18.0
    assert kpis["average_rop"] == 25.0         # single parameter row, not ×4
    assert kpis["total_cost"] == 150000.0      # two records summed once, not ×4


def test_canonical_well_kpis_span_wellbores_without_cross_well_contamination():
    """Scope guard (coverage audit §14/§15).

    Well-level KPIs aggregate every wellbore of the Well (original + sidetrack)
    but must never absorb another Well's records. Identity is by id, never by
    rig or free-text name.
    """
    manager, existing_well_id = _manager_with_report()
    session = manager.create_session()
    try:
        project_id = session.get(_Well, existing_well_id).project_id
        # Target well with an original + a sidetrack wellbore.
        well = _Well(name="Sidetrack Well", code="OI-ST", project_id=project_id)
        session.add(well)
        session.flush()
        orig = _Wellbore(well_id=well.id, name="OH", wellbore_type="original")
        session.add(orig)
        session.flush()
        st = _Wellbore(well_id=well.id, name="ST1", wellbore_type="sidetrack",
                       parent_wellbore_id=orig.id)
        session.add(st)
        session.flush()
        sec_o = _Section(well_id=well.id, wellbore_id=orig.id, name="OH-S1")
        sec_s = _Section(well_id=well.id, wellbore_id=st.id, name="ST-S1")
        session.add_all([sec_o, sec_s])
        session.flush()
        r_o = _DailyReport(well_id=well.id, wellbore_id=orig.id, section_id=sec_o.id,
                           report_number=1, report_date=date(2026, 1, 1), depth_2400=1000.0)
        r_s = _DailyReport(well_id=well.id, wellbore_id=st.id, section_id=sec_s.id,
                           report_number=2, report_date=date(2026, 1, 2), depth_2400=1500.0)
        session.add_all([r_o, r_s])
        session.flush()
        session.add(TimeLog24H(report_id=r_o.id, time_from=_time(0), time_to=_time(12),
                               duration=12.0, is_npt=False))
        session.add(TimeLog24H(report_id=r_o.id, time_from=_time(12), time_to=_time(18),
                               duration=6.0, is_npt=True))
        session.add(TimeLog24H(report_id=r_s.id, time_from=_time(0), time_to=_time(6),
                               duration=6.0, is_npt=True))
        session.add(DrillingParameters(well_id=well.id, report_id=r_o.id,
                                       report_date=r_o.report_date, avg_rop=20.0))
        session.add(DrillingParameters(well_id=well.id, report_id=r_s.id,
                                       report_date=r_s.report_date, avg_rop=10.0))

        # A DIFFERENT well in the same project that must never leak in.
        other = _Well(name="Other Well", code="OI-OTHER", project_id=project_id)
        session.add(other)
        session.flush()
        r_x = _DailyReport(well_id=other.id, report_number=1,
                           report_date=date(2026, 1, 1), depth_2400=9999.0)
        session.add(r_x)
        session.flush()
        session.add(TimeLog24H(report_id=r_x.id, time_from=_time(0), time_to=_time(23, 59),
                               duration=24.0, is_npt=True))
        session.add(DrillingParameters(well_id=other.id, report_id=r_x.id,
                                       report_date=r_x.report_date, avg_rop=999.0))
        session.commit()
        well_id = well.id
    finally:
        session.close()

    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]
    assert kpis["reports"] == 2                     # both wellbores, not the other well
    assert kpis["current_depth"] == 1500.0
    assert kpis["npt_hours"] == 12.0                # 6 + 6, other well's 24 excluded
    assert kpis["npt_percent"] == 50.0             # 12 / 24
    assert kpis["average_rop"] == 15.0             # mean(20, 10); 999 excluded
