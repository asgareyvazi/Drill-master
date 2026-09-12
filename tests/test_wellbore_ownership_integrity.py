"""Wellbore ownership-integrity invariants (forensic audit 2026-09-12).

A foreign key only proves the referenced row exists; it does NOT prove the
referenced row belongs to the same Well/Wellbore. These tests pin the
persistence-boundary invariants that keep the

    Well → Wellbore → Section → DailyReport

ownership chain internally consistent, so contradictory states can never be
committed regardless of which save path is used (ORM helper, import service, or
direct session). They complement — and must never weaken — the no-fabrication
rule (unknown stays NULL; a NULL wellbore_id on legacy/ambiguous rows is
always allowed).
"""

import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base,
    Company,
    DailyReport,
    DatabaseManager,
    Project,
    Section,
    Well,
    Wellbore,
)
from core.import_diagnostics import OwnershipIntegrityError


def build():
    """Two wells, each with one original wellbore; FK enforcement on."""
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(manager.engine, "connect")
    def _fk(dbapi, _rec):  # pragma: no cover - trivial
        dbapi.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(
        bind=manager.engine, autoflush=False, autocommit=False
    )
    s = manager.create_session()
    company = Company(name="OEOC", code="OEOC")
    s.add(company)
    s.flush()
    project = Project(name="BB", code="BB", company_id=company.id)
    s.add(project)
    s.flush()
    well_a = Well(project_id=project.id, name="Well A", code="A")
    well_b = Well(project_id=project.id, name="Well B", code="B")
    s.add_all([well_a, well_b])
    s.flush()
    bore_a = Wellbore(well_id=well_a.id, name="Original A", wellbore_type="original")
    bore_b = Wellbore(well_id=well_b.id, name="Original B", wellbore_type="original")
    s.add_all([bore_a, bore_b])
    s.commit()
    ids = dict(
        well_a=well_a.id, well_b=well_b.id, bore_a=bore_a.id, bore_b=bore_b.id
    )
    s.close()
    return manager, ids


@pytest.fixture()
def env():
    return build()


# ----------------------------------------------------------------------
# Cross-Well parent lineage (Gate C)
# ----------------------------------------------------------------------
class TestParentLineage:
    def test_cross_well_parent_rejected_orm(self, env):
        manager, ids = env
        s = manager.create_session()
        try:
            st = Wellbore(
                well_id=ids["well_a"],
                name="ST cross",
                wellbore_type="sidetrack",
                parent_wellbore_id=ids["bore_b"],  # parent belongs to Well B
            )
            s.add(st)
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()

    def test_cross_well_parent_rejected_helper(self, env):
        manager, ids = env
        with pytest.raises(OwnershipIntegrityError):
            manager.get_or_create_wellbore(
                ids["well_a"],
                "ST via helper",
                wellbore_type="sidetrack",
                parent_wellbore_id=ids["bore_b"],
            )
        # Nothing was persisted.
        s = manager.create_session()
        try:
            assert s.query(Wellbore).filter_by(name="ST via helper").count() == 0
        finally:
            s.close()

    def test_same_well_parent_allowed(self, env):
        manager, ids = env
        st = manager.get_or_create_wellbore(
            ids["well_a"],
            "ST #1",
            wellbore_type="sidetrack",
            parent_wellbore_id=ids["bore_a"],  # same well
        )
        assert st is not None
        s = manager.create_session()
        try:
            row = s.get(Wellbore, st)
            assert row.parent_wellbore_id == ids["bore_a"]
            assert row.well_id == ids["well_a"]
        finally:
            s.close()

    def test_wellbore_cannot_be_its_own_parent(self, env):
        manager, ids = env
        s = manager.create_session()
        try:
            wb = s.get(Wellbore, ids["bore_a"])
            wb.parent_wellbore_id = wb.id
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()


# ----------------------------------------------------------------------
# Wellbore type / structural invariants (Gate D)
# ----------------------------------------------------------------------
class TestWellboreType:
    def test_invalid_type_rejected(self, env):
        manager, ids = env
        with pytest.raises(OwnershipIntegrityError):
            manager.get_or_create_wellbore(
                ids["well_a"], "weird", wellbore_type="banana"
            )

    def test_original_with_parent_rejected(self, env):
        manager, ids = env
        with pytest.raises(OwnershipIntegrityError):
            manager.get_or_create_wellbore(
                ids["well_a"],
                "orig-with-parent",
                wellbore_type="original",
                parent_wellbore_id=ids["bore_a"],
            )

    def test_original_and_sidetrack_are_valid(self, env):
        manager, ids = env
        a = manager.get_or_create_wellbore(ids["well_a"], "O2", wellbore_type="original")
        b = manager.get_or_create_wellbore(
            ids["well_a"], "S2", wellbore_type="sidetrack",
            parent_wellbore_id=ids["bore_a"],
        )
        assert a is not None and b is not None


# ----------------------------------------------------------------------
# Section ownership consistency (Gate E)
# ----------------------------------------------------------------------
class TestSectionOwnership:
    def test_section_wellbore_must_match_well(self, env):
        manager, ids = env
        s = manager.create_session()
        try:
            sec = Section(
                well_id=ids["well_a"],
                wellbore_id=ids["bore_b"],  # B's bore under A's well
                name="cross-sec",
            )
            s.add(sec)
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()

    def test_section_with_matching_wellbore_ok(self, env):
        manager, ids = env
        s = manager.create_session()
        try:
            sec = Section(
                well_id=ids["well_a"], wellbore_id=ids["bore_a"], name="ok-sec"
            )
            s.add(sec)
            s.commit()
            assert sec.id is not None
        finally:
            s.close()

    def test_section_null_wellbore_is_allowed(self, env):
        """Legacy / ambiguous sections keep wellbore_id NULL — never fabricated."""
        manager, ids = env
        s = manager.create_session()
        try:
            sec = Section(well_id=ids["well_a"], wellbore_id=None, name="legacy")
            s.add(sec)
            s.commit()
            assert sec.wellbore_id is None
        finally:
            s.close()


# ----------------------------------------------------------------------
# DailyReport ownership consistency (Gate F + §9)
# ----------------------------------------------------------------------
class TestDailyReportOwnership:
    def _section(self, manager, well_id, wellbore_id, name):
        s = manager.create_session()
        try:
            sec = Section(well_id=well_id, wellbore_id=wellbore_id, name=name)
            s.add(sec)
            s.commit()
            return sec.id
        finally:
            s.close()

    def test_report_wellbore_must_match_well(self, env):
        manager, ids = env
        sec = self._section(manager, ids["well_a"], ids["bore_a"], "secA")
        s = manager.create_session()
        try:
            dr = DailyReport(
                well_id=ids["well_a"],
                section_id=sec,
                wellbore_id=ids["bore_b"],  # B's bore
                report_date=datetime.date(2024, 1, 1),
                report_number=1,
            )
            s.add(dr)
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()

    def test_report_wellbore_must_match_section(self, env):
        manager, ids = env
        # Section under bore_a; report claims well A but a *different* bore
        # that also belongs to A -> still contradicts the section.
        other_a = manager.get_or_create_wellbore(ids["well_a"], "A-second")
        sec = self._section(manager, ids["well_a"], ids["bore_a"], "secA2")
        s = manager.create_session()
        try:
            dr = DailyReport(
                well_id=ids["well_a"],
                section_id=sec,
                wellbore_id=other_a,  # same well, different bore than the section
                report_date=datetime.date(2024, 1, 2),
                report_number=1,
            )
            s.add(dr)
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()

    def test_report_section_must_match_well(self, env):
        manager, ids = env
        sec_b = self._section(manager, ids["well_b"], ids["bore_b"], "secB")
        s = manager.create_session()
        try:
            dr = DailyReport(
                well_id=ids["well_a"],
                section_id=sec_b,  # section belongs to well B
                report_date=datetime.date(2024, 1, 3),
                report_number=1,
            )
            s.add(dr)
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()

    def test_consistent_report_ok(self, env):
        manager, ids = env
        sec = self._section(manager, ids["well_a"], ids["bore_a"], "secOK")
        s = manager.create_session()
        try:
            dr = DailyReport(
                well_id=ids["well_a"],
                section_id=sec,
                wellbore_id=ids["bore_a"],
                report_date=datetime.date(2024, 1, 4),
                report_number=1,
            )
            s.add(dr)
            s.commit()
            assert dr.id is not None
        finally:
            s.close()

    def test_legacy_null_wellbore_report_ok(self, env):
        """A report with section + NULL wellbore is a valid transitional state."""
        manager, ids = env
        sec = self._section(manager, ids["well_a"], None, "legacy-sec")
        s = manager.create_session()
        try:
            dr = DailyReport(
                well_id=ids["well_a"],
                section_id=sec,
                wellbore_id=None,
                report_date=datetime.date(2024, 1, 5),
                report_number=1,
            )
            s.add(dr)
            s.commit()
            assert dr.wellbore_id is None
        finally:
            s.close()


# ----------------------------------------------------------------------
# Identity immutability via save_wellbore (Gate B / §20)
# ----------------------------------------------------------------------
class TestIdentityImmutability:
    def test_save_wellbore_cannot_move_bore_to_another_well(self, env):
        manager, ids = env
        # Attempt to reparent Well A's bore to Well B.
        with pytest.raises(OwnershipIntegrityError):
            manager.save_wellbore({"id": ids["bore_a"], "well_id": ids["well_b"]})
        s = manager.create_session()
        try:
            row = s.get(Wellbore, ids["bore_a"])
            assert row.well_id == ids["well_a"], "well_id must be immutable"
        finally:
            s.close()

    def test_save_wellbore_can_update_non_identity_fields(self, env):
        manager, ids = env
        result = manager.save_wellbore(
            {"id": ids["bore_a"], "status": "Suspended", "code": "OA-1"}
        )
        assert result == ids["bore_a"]
        s = manager.create_session()
        try:
            row = s.get(Wellbore, ids["bore_a"])
            assert row.status == "Suspended"
            assert row.code == "OA-1"
            assert row.well_id == ids["well_a"]
        finally:
            s.close()
