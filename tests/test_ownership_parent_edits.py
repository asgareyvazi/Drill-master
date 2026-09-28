"""Ownership checks must run in both directions, not only on edited children."""
from datetime import date

import pytest

from core.database import DailyReport, DrillingParameters, Section, Wellbore
from core.import_diagnostics import OwnershipIntegrityError
from test_scope_attribution import _mgr, _base, _well, _wellbore, _section, _report


@pytest.mark.parametrize("parent", ["report", "section", "bore"])
def test_parent_reassignment_cannot_strand_unchanged_children(parent):
    m = _mgr()
    p = _base(m)
    a, b = _well(m, p, "A"), _well(m, p, "B")
    ba = _wellbore(m, a, "A")
    other = _wellbore(m, a, "Other")
    sec = _section(m, a, "S", wellbore_id=ba)
    rid = _report(m, a, 1, wellbore_id=ba, section_id=sec)
    with m.create_session() as s:
        s.add(DrillingParameters(well_id=a, report_id=rid, report_date=date(2026, 1, 1)))
        s.commit()
    with m.create_session() as s:
        if parent == "report":
            r = s.get(DailyReport, rid)
            r.well_id, r.wellbore_id, r.section_id = b, None, None
        elif parent == "section":
            s.get(Section, sec).wellbore_id = other
        else:
            s.get(Wellbore, ba).well_id = b
        with pytest.raises(OwnershipIntegrityError):
            s.commit()
        s.rollback()
    with m.create_session() as s:
        assert s.get(DailyReport, rid).well_id == a
        assert s.get(Section, sec).wellbore_id == ba
        assert s.get(Wellbore, ba).well_id == a


def test_consistent_parent_and_child_edit_is_allowed():
    m = _mgr()
    a = _well(m, _base(m), "A")
    ba, bb = _wellbore(m, a, "A"), _wellbore(m, a, "B")
    sec = _section(m, a, "S", wellbore_id=ba)
    rid = _report(m, a, 1, wellbore_id=ba, section_id=sec)
    with m.create_session() as s:
        s.get(Section, sec).wellbore_id = bb
        s.get(DailyReport, rid).wellbore_id = bb
        s.commit()


@pytest.mark.parametrize("new", [True, False])
def test_relationship_assignment_cannot_bypass_owner_guard(new):
    from core.database import SafetyReport
    m = _mgr()
    p = _base(m)
    a, b = _well(m, p, "A"), _well(m, p, "B")
    ra, rb = _report(m, a, 1), _report(m, b, 1)
    with m.create_session() as s:
        row = SafetyReport(well_id=a, report_id=ra, report_date=date(2026, 1, 1))
        s.add(row)
        if not new:
            s.commit()
        row.report = s.get(DailyReport, rb)
        with pytest.raises(OwnershipIntegrityError):
            s.commit()
        s.rollback()
        assert s.query(SafetyReport).filter_by(report_id=rb).count() == 0


def test_coherent_relationship_and_scalar_owner_change():
    from core.database import SafetyReport, Well
    m = _mgr()
    p = _base(m)
    a, b = _well(m, p, "A"), _well(m, p, "B")
    ra = _report(m, a, 1)
    with m.create_session() as s:
        row = SafetyReport(well_id=a, report_id=ra, report_date=date(2026, 1, 1))
        s.add(row)
        s.commit()
        s.get(DailyReport, ra).well = s.get(Well, b)
        row.well_id = b
        s.commit()
        assert row.well_id == s.get(DailyReport, ra).well_id == b


def test_startup_rejects_external_owner_corruption_without_repair(tmp_path):
    from core.database import DatabaseManager
    m = DatabaseManager()
    m.db_path = str(tmp_path / "external.db")
    assert m.initialize()
    p = _base(m)
    a, b = _well(m, p, "A"), _well(m, p, "B")
    r = _report(m, b, 1)
    with m.engine.begin() as conn:
        # Direct SQL bypasses ORM events but still satisfies single-column FKs.
        conn.execute(DrillingParameters.__table__.insert().values(
            well_id=a, report_id=r, report_date=date(2026, 1, 1)))
    m.close()
    reopened = DatabaseManager()
    reopened.db_path = m.db_path
    try:
        assert not reopened.initialize()
        assert "ownership conflict" in reopened.last_diagnostic["message"].lower()
        with reopened.engine.connect() as conn:
            assert conn.execute(DrillingParameters.__table__.select()).one().well_id == a
    finally:
        reopened.close()
