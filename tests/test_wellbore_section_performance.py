"""Regression tests for Wellbore- and Section-scoped Engineering Performance
rollups (OperationsIntelligenceService.analyze_wellbore / analyze_section).

These lock the scope-identity and canonical-math contract:

* Scope is resolved through the ownership chain
  (DrillingParameters.report_id / TimeLog24H.report_id → DailyReport.wellbore_id
  / section_id) using canonical integer identity, never display names.
* Weighted ROP reuses the canonical paired-observation semantics
  (Σ valid-pair footage / Σ valid-pair hours); it is NOT a mean of per-day
  rates and NOT a naive Σ(footage)/Σ(hours).
* Foreign wells, foreign wellbores and foreign sections never contribute.
* Reports with NULL wellbore_id / section_id ("unknown") are not attributed to
  any scope.
* Join multiplicity (BHA/Bit/etc.) cannot inflate hours: time is aggregated
  from time logs only.
* Missing rate/percentage data → None (never a fabricated 0); a real zero stays
  zero.
"""

from __future__ import annotations

from datetime import date, time as dtime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base,
    BHAReport,
    BitReport,
    Company,
    DailyReport,
    DatabaseManager,
    DrillingParameters,
    Project,
    Section,
    TimeLog24H,
    Well,
    Wellbore,
)
from core.operations_intelligence import OperationsIntelligenceService


def _build():
    """Well A (wellbore A1 → sections A1-1, A1-2 ; wellbore A2), Well B (B1)."""
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(m.engine, "connect")
    def _fk(dbapi, _rec):  # pragma: no cover - trivial
        dbapi.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    co = Company(name="C", code="C")
    s.add(co)
    s.flush()
    pr = Project(name="P", code="P", company_id=co.id)
    s.add(pr)
    s.flush()
    wa = Well(name="A", code="A", project_id=pr.id)
    wb = Well(name="B", code="B", project_id=pr.id)
    s.add_all([wa, wb])
    s.flush()
    a1 = Wellbore(well_id=wa.id, name="A1", wellbore_type="original")
    a2 = Wellbore(well_id=wa.id, name="A2", wellbore_type="sidetrack")
    b1 = Wellbore(well_id=wb.id, name="B1", wellbore_type="original")
    s.add_all([a1, a2, b1])
    s.flush()
    s11 = Section(well_id=wa.id, wellbore_id=a1.id, name="A1-1")
    s12 = Section(well_id=wa.id, wellbore_id=a1.id, name="A1-2")
    s.add_all([s11, s12])
    s.flush()
    ids = {
        "m": m,
        "wa": wa.id,
        "wb": wb.id,
        "a1": a1.id,
        "a2": a2.id,
        "b1": b1.id,
        "s11": s11.id,
        "s12": s12.id,
    }
    s.commit()
    s.close()
    return ids


def _ddr(m, well_id, wellbore_id, section_id, day, di, do, h,
         npt_h=0.0, prod_h=None):
    s = m.create_session()
    try:
        dr = DailyReport(
            well_id=well_id,
            wellbore_id=wellbore_id,
            section_id=section_id,
            report_date=date(2026, 1, day),
            depth_2400=do if do is not None else 0,
        )
        s.add(dr)
        s.flush()
        rid = dr.id
        s.add(DrillingParameters(
            well_id=well_id, report_id=rid, report_date=date(2026, 1, day),
            depth_in=di, depth_out=do, hours_on_bottom=h,
        ))
        worked = prod_h if prod_h is not None else (h or 0)
        if worked:
            s.add(TimeLog24H(
                report_id=rid, time_from=dtime(0, 0), time_to=dtime(12, 0),
                duration=worked, is_npt=False,
            ))
        if npt_h:
            s.add(TimeLog24H(
                report_id=rid, time_from=dtime(12, 0), time_to=dtime(13, 0),
                duration=npt_h, is_npt=True,
            ))
        s.commit()
        return rid
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Wellbore scope
# ---------------------------------------------------------------------------


def test_wellbore_weighted_rop_sums_valid_pairs_across_sections():
    ids = _build()
    m = ids["m"]
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 1, 1000, 1100, 5)   # 100/5
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 2, 1100, 1400, 5)   # 300/5
    _ddr(m, ids["wa"], ids["a1"], ids["s12"], 3, 1400, 1600, 4)   # 200/4
    k = OperationsIntelligenceService(m).analyze_wellbore(ids["a1"])["kpis"]
    assert abs(k["weighted_rop"] - 600 / 14) < 1e-3
    assert k["weighted_rop_footage"] == 600.0
    assert k["weighted_rop_hours"] == 14.0
    assert k["weighted_rop_valid_pairs"] == 3


def test_wellbore_isolation_excludes_sibling_wellbore_and_foreign_well():
    ids = _build()
    m = ids["m"]
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 1, 1000, 1100, 5)      # A1: 20
    _ddr(m, ids["wa"], ids["a2"], None, 2, 0, 100000, 0.1)           # A2 absurd
    _ddr(m, ids["wb"], ids["b1"], None, 3, 0, 50000, 0.05)          # B1 absurd
    k = OperationsIntelligenceService(m).analyze_wellbore(ids["a1"])["kpis"]
    assert k["weighted_rop"] == 20.0
    assert k["weighted_rop_valid_pairs"] == 1


def test_wellbore_null_scope_reports_not_attributed():
    ids = _build()
    m = ids["m"]
    # report with NULL wellbore_id ("unknown") must not attach to any wellbore
    _ddr(m, ids["wa"], None, None, 1, 1000, 1100, 5)
    res = OperationsIntelligenceService(m).analyze_wellbore(ids["a1"])
    assert res["kpis"] == {"reports": 0}


def test_wellbore_time_and_npt_rollup():
    ids = _build()
    m = ids["m"]
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 1, 1000, 1100, 5, npt_h=1, prod_h=5)
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 2, 1100, 1400, 5, npt_h=1, prod_h=5)
    k = OperationsIntelligenceService(m).analyze_wellbore(ids["a1"])["kpis"]
    assert k["total_hours"] == 12.0   # 5+5 prod + 1+1 npt
    assert k["npt_hours"] == 2.0
    assert k["npt_percent"] == round(2 / 12 * 100, 2)
    assert k["productive_hours"] == 10.0


def test_wellbore_multiplicity_does_not_inflate():
    ids = _build()
    m = ids["m"]
    rid = _ddr(m, ids["wa"], ids["a1"], ids["s11"], 1, 1000, 1100, 5, npt_h=0, prod_h=5)
    svc = OperationsIntelligenceService(m)
    before = svc.analyze_wellbore(ids["a1"])["kpis"]
    s = m.create_session()
    for i in range(2):
        s.add(BHAReport(well_id=ids["wa"], report_id=rid, bha_name=f"BHA{i}",
                        bha_data_json="{}"))
        s.add(BitReport(well_id=ids["wa"], report_id=rid,
                        report_date=date(2026, 1, 1), report_name=f"Bit{i}",
                        bit_records_json="[]"))
    s.commit()
    s.close()
    after = svc.analyze_wellbore(ids["a1"])["kpis"]
    assert before["weighted_rop"] == after["weighted_rop"] == 20.0
    assert before["total_hours"] == after["total_hours"] == 5.0


# ---------------------------------------------------------------------------
# Section scope
# ---------------------------------------------------------------------------


def test_section_grouping_and_foreign_section_exclusion():
    ids = _build()
    m = ids["m"]
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 1, 1000, 1100, 5)   # A1-1: 100/5
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 2, 1100, 1400, 5)   # A1-1: 300/5
    _ddr(m, ids["wa"], ids["a1"], ids["s12"], 3, 1400, 1600, 4)   # A1-2: 200/4
    svc = OperationsIntelligenceService(m)
    k11 = svc.analyze_section(ids["s11"])["kpis"]
    k12 = svc.analyze_section(ids["s12"])["kpis"]
    assert k11["weighted_rop"] == 40.0          # 400/10
    assert k11["weighted_rop_valid_pairs"] == 2
    assert k12["weighted_rop"] == 50.0          # 200/4
    assert k12["weighted_rop_valid_pairs"] == 1


def test_section_null_scope_not_attributed():
    ids = _build()
    m = ids["m"]
    _ddr(m, ids["wa"], ids["a1"], None, 1, 1000, 1100, 5)  # NULL section
    res = OperationsIntelligenceService(m).analyze_section(ids["s11"])
    assert res["kpis"] == {"reports": 0}


def test_section_mixed_valid_invalid_rows():
    ids = _build()
    m = ids["m"]
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 1, 1000, 1100, 5)    # valid 100/5
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 2, None, 1400, 6)    # null footage
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 3, 1500, 1400, 5)    # neg footage
    k = OperationsIntelligenceService(m).analyze_section(ids["s11"])["kpis"]
    assert k["weighted_rop"] == 20.0     # only the first row; 6h must not count
    assert k["weighted_rop_hours"] == 5.0
    assert k["weighted_rop_valid_pairs"] == 1


def test_section_no_valid_pairs_returns_none():
    ids = _build()
    m = ids["m"]
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 1, None, 1100, 5)
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 2, 1500, 1400, 5)
    k = OperationsIntelligenceService(m).analyze_section(ids["s11"])["kpis"]
    assert k["weighted_rop"] is None


def test_section_explicit_zero_footage_is_real_zero():
    ids = _build()
    m = ids["m"]
    _ddr(m, ids["wa"], ids["a1"], ids["s11"], 1, 1000, 1000, 5)  # 0 m in 5 h
    k = OperationsIntelligenceService(m).analyze_section(ids["s11"])["kpis"]
    assert k["weighted_rop"] == 0.0
    assert k["weighted_rop_valid_pairs"] == 1


def test_nonexistent_scope_returns_empty():
    ids = _build()
    m = ids["m"]
    assert OperationsIntelligenceService(m).analyze_wellbore(99999)["kpis"] == {"reports": 0}
    assert OperationsIntelligenceService(m).analyze_section(99999)["kpis"] == {"reports": 0}


# ---------------------------------------------------------------------------
# EOWR report exposure of footage-weighted ROP
# ---------------------------------------------------------------------------


def test_eowr_exposes_footage_weighted_rop(tmp_path, monkeypatch):
    """The EOWR executive summary must show a distinct Footage-Weighted ROP KPI
    computed from the canonical engine, and render '—' (not 0) when unknown."""
    import secrets

    from core.database import DatabaseManager
    from core.report_engine import EOWRReportEngine

    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path))
    db = DatabaseManager(bootstrap_passwords={"admin": secrets.token_urlsafe(24)})
    db.db_path = str(tmp_path / "eowr.db")
    assert db.initialize()
    company = db.generic_save(Company, {"name": "Op", "code": "OP"})
    project = db.generic_save(Project, {"name": "Pr", "code": "PR", "company_id": company})
    well = db.generic_save(Well, {"name": "W1", "code": "W1", "project_id": project})
    section = db.generic_save(Section, {"name": "S1", "well_id": well})
    rep = db.save_daily_report({
        "well_id": well, "section_id": section, "report_number": 1,
        "report_date": date(2026, 1, 1), "depth_2400": 1100,
    })
    rid = rep["id"]
    # Two valid pairs (100/5 + 300/5) → weighted 40.0
    db.save_drilling_parameters({
        "well_id": well, "report_id": rid, "report_date": date(2026, 1, 1),
        "depth_in": 1000, "depth_out": 1100, "hours_on_bottom": 5,
    })
    rep2 = db.save_daily_report({
        "well_id": well, "section_id": section, "report_number": 2,
        "report_date": date(2026, 1, 2), "depth_2400": 1400,
    })
    db.save_drilling_parameters({
        "well_id": well, "report_id": rep2["id"], "report_date": date(2026, 1, 2),
        "depth_in": 1100, "depth_out": 1400, "hours_on_bottom": 5,
    })
    out = tmp_path / "eowr.html"
    assert EOWRReportEngine(db).generate(well, str(out), format="html")
    html = out.read_text()
    assert "Footage-Weighted ROP (m/hr)" in html
    assert "40.0" in html
    db.close()
