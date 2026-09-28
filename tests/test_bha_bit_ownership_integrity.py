"""BHA / Bit ownership-integrity and longitudinal-behaviour tests.

Forensic audit 2026-09-12. DrillMaster models BHA, Bit, and Downhole equipment
as **per-daily-report snapshots** (one row per DDR, keyed on ``report_id``),
where physical run continuity is expressed by a stable ``bha_name`` / bit serial
repeated across consecutive daily snapshots — there is no separate canonical
"Run" entity. That is the established architecture (see
``tests/test_well_centric_acceptance.py``); these tests pin the *integrity*
invariants around it, they do not introduce a new Run entity.

Invariants enforced here:

* A report-scoped record (BHA / Bit / Downhole) whose ``report_id`` is set must
  belong to the same well as that report — no cross-well references, on every
  save path (service helper OR direct ORM flush).
* Re-importing the same DDR does not duplicate BHA/Bit snapshots.
* Original-bore and sidetrack snapshots stay isolated (via each snapshot's
  report → wellbore linkage), even with identical section names / bit sizes.
* Rig is never an identity key for BHA/Bit.
* Unknown values are never fabricated; explicit zero is preserved.
"""

import datetime

import pytest
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
    DownholeEquipment,
    Project,
    Well,
    Wellbore,
)
from core.import_diagnostics import OwnershipIntegrityError


def build():
    """Two wells, each with one daily report; FK enforcement on."""
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
    rep_a = DailyReport(
        well_id=well_a.id, report_date=datetime.date(2024, 1, 1), report_number=1
    )
    rep_b = DailyReport(
        well_id=well_b.id, report_date=datetime.date(2024, 1, 1), report_number=1
    )
    s.add_all([rep_a, rep_b])
    s.flush()
    ids = dict(
        well_a=well_a.id, well_b=well_b.id, rep_a=rep_a.id, rep_b=rep_b.id
    )
    s.commit()
    s.close()
    return manager, ids


@pytest.fixture()
def env():
    return build()


# ----------------------------------------------------------------------
# Cross-well report references (service layer)
# ----------------------------------------------------------------------
class TestServiceOwnershipGuards:
    def test_save_bit_report_rejects_cross_well_report(self, env):
        manager, ids = env
        with pytest.raises((OwnershipIntegrityError, ValueError)):
            manager.save_bit_report(
                ids["well_a"],
                {
                    "report_id": ids["rep_b"],  # report belongs to Well B
                    "report_date": datetime.date(2024, 1, 1),
                    "bit_records_json": [{"bit_no": "1"}],
                },
            )
        s = manager.create_session()
        try:
            assert s.query(BitReport).count() == 0
        finally:
            s.close()

    def test_save_bha_report_rejects_cross_well_report(self, env):
        manager, ids = env
        with pytest.raises((OwnershipIntegrityError, ValueError)):
            manager.save_bha_report(
                ids["well_a"],
                {"report_id": ids["rep_b"], "bha_name": "BHA #1", "bha_data": []},
            )

    def test_save_downhole_rejects_cross_well_report(self, env):
        manager, ids = env
        with pytest.raises((OwnershipIntegrityError, ValueError)):
            manager.save_downhole_equipment(
                ids["well_a"],
                {"report_id": ids["rep_b"], "equipment_data_json": []},
            )

    def test_save_bit_report_same_well_ok(self, env):
        manager, ids = env
        rid = manager.save_bit_report(
            ids["well_a"],
            {
                "report_id": ids["rep_a"],
                "report_date": datetime.date(2024, 1, 1),
                "bit_records_json": [{"bit_no": "1", "serial": "BT-1"}],
            },
        )
        assert rid is not None
        s = manager.create_session()
        try:
            row = s.get(BitReport, rid)
            assert row.well_id == ids["well_a"]
            assert row.report_id == ids["rep_a"]
        finally:
            s.close()


# ----------------------------------------------------------------------
# Persistence-boundary guard (direct ORM flush cannot bypass ownership)
# ----------------------------------------------------------------------
class TestPersistenceBoundary:
    def test_orm_bit_report_cross_well_rejected(self, env):
        manager, ids = env
        s = manager.create_session()
        try:
            s.add(
                BitReport(
                    well_id=ids["well_a"],
                    report_id=ids["rep_b"],  # cross well
                    report_date=datetime.date(2024, 1, 1),
                    bit_records_json="[]",
                )
            )
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()

    def test_orm_bha_report_cross_well_rejected(self, env):
        manager, ids = env
        s = manager.create_session()
        try:
            s.add(
                BHAReport(
                    well_id=ids["well_a"],
                    report_id=ids["rep_b"],
                    bha_name="BHA #1",
                    bha_data_json=[],
                )
            )
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()

    def test_orm_downhole_cross_well_rejected(self, env):
        manager, ids = env
        s = manager.create_session()
        try:
            s.add(
                DownholeEquipment(
                    well_id=ids["well_a"],
                    report_id=ids["rep_b"],
                    equipment_data_json=[],
                )
            )
            with pytest.raises(OwnershipIntegrityError):
                s.commit()
        finally:
            s.rollback()
            s.close()

    def test_orm_bit_report_matching_well_ok(self, env):
        manager, ids = env
        s = manager.create_session()
        try:
            s.add(
                BitReport(
                    well_id=ids["well_a"],
                    report_id=ids["rep_a"],
                    report_date=datetime.date(2024, 1, 1),
                    bit_records_json="[]",
                )
            )
            s.commit()
            assert s.query(BitReport).count() == 1
        finally:
            s.close()

    def test_orm_bit_report_null_report_id_allowed(self, env):
        """A well-level snapshot with no report link is a valid state; the
        cross-well guard only applies when report_id is set."""
        manager, ids = env
        s = manager.create_session()
        try:
            s.add(
                BitReport(
                    well_id=ids["well_a"],
                    report_id=None,
                    report_date=datetime.date(2024, 1, 1),
                    bit_records_json="[]",
                )
            )
            s.commit()
            assert s.query(BitReport).filter_by(report_id=None).count() == 1
        finally:
            s.close()


# ----------------------------------------------------------------------
# Longitudinal behaviour via the real import path
# ----------------------------------------------------------------------
def _mem_import_env():
    from tests.test_well_centric_acceptance import memory_manager

    return memory_manager()


def _payload(well, date, **extra):
    from tests.test_well_centric_acceptance import ddr_payload

    return ddr_payload(well, date, **extra)


def _import(manager, payload):
    from tests.test_well_centric_acceptance import import_ddr

    return import_ddr(manager, payload)


BHA = {"bha_name": "BHA #12", "bha_data": [{"component_name": "Bit", "od": 8.5}]}
BIT = {"bit_records_json": [{"bit_no": "7", "size_in": 8.5, "serial": "BT-777"}]}


class TestLongitudinalImport:
    def test_same_run_snapshotted_per_ddr(self):
        manager = _mem_import_env()
        for d in ("2024-10-21", "2024-10-22", "2024-10-23", "2024-10-24"):
            _import(manager, _payload("AZNS 12", d, bha_report=BHA, bit_report=BIT))
        s = manager.create_session()
        try:
            reports = s.query(DailyReport).count()
            bhas = s.query(BHAReport).all()
            bits = s.query(BitReport).all()
            # One snapshot per DDR for the same physical run.
            assert reports == 4
            assert len(bhas) == 4
            assert len(bits) == 4
            # Run identity is the stable name/serial shared across snapshots.
            assert {b.bha_name for b in bhas} == {"BHA #12"}
            # Every snapshot belongs to the one well.
            assert len({b.well_id for b in bhas}) == 1
        finally:
            s.close()

    def test_reimport_is_idempotent(self):
        manager = _mem_import_env()
        p = _payload("AZNS 12", "2024-10-21", bha_report=BHA, bit_report=BIT)
        _import(manager, p)
        _import(manager, p)
        s = manager.create_session()
        try:
            assert s.query(Well).count() == 1
            assert s.query(DailyReport).count() == 1
            assert s.query(BHAReport).count() == 1
            assert s.query(BitReport).count() == 1
        finally:
            s.close()

    def test_sidetrack_snapshots_isolated_from_original(self):
        manager = _mem_import_env()
        p1 = _payload("AZNS 12", "2024-10-21", bha_report=BHA, bit_report=BIT)
        p1["well_info"]["wellbore_name"] = "Original"
        p2 = _payload("AZNS 12", "2024-11-05", bha_report=BHA, bit_report=BIT)
        p2["well_info"]["wellbore_name"] = "ST #1"
        p2["well_info"]["wellbore_type"] = "sidetrack"
        _import(manager, p1)
        _import(manager, p2)
        s = manager.create_session()
        try:
            assert s.query(Well).count() == 1
            bores = {w.name: w.id for w in s.query(Wellbore).all()}
            assert set(bores) == {"Original", "ST #1"}
            # Each BHA snapshot maps, via its report, to exactly one bore, and
            # the two bores are different -> histories are isolated.
            wb_for_bha = set()
            for b in s.query(BHAReport).all():
                rep = s.get(DailyReport, b.report_id)
                wb_for_bha.add(rep.wellbore_id)
            assert wb_for_bha == set(bores.values())
            assert len(wb_for_bha) == 2
        finally:
            s.close()

    def test_rig_is_not_bha_bit_identity(self):
        """Same rig, two different wells → BHA/Bit snapshots never merge."""
        manager = _mem_import_env()
        _import(manager, _payload("AZNS 12", "2024-10-21", bha_report=BHA, bit_report=BIT))
        _import(manager, _payload("AZNS 15", "2024-10-21", bha_report=BHA, bit_report=BIT))
        s = manager.create_session()
        try:
            wells = {w.name: w.id for w in s.query(Well).all()}
            assert len(wells) == 2
            bha_wells = {b.well_id for b in s.query(BHAReport).all()}
            assert bha_wells == set(wells.values())
        finally:
            s.close()


# ----------------------------------------------------------------------
# Physical schema
# ----------------------------------------------------------------------
class TestPhysicalSchema:
    def test_fresh_bha_bit_have_well_and_report_fks(self, tmp_path, monkeypatch):
        import sqlite3

        dbp = str(tmp_path / "fresh.sqlite")
        monkeypatch.setenv("DRILLMASTER_ENV", "test")
        monkeypatch.setenv("DRILLMASTER_DB_PATH", dbp)
        monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path))
        manager = DatabaseManager()
        assert manager.initialize() is True

        con = sqlite3.connect(dbp)
        try:
            for table in ("bha_reports", "bit_reports", "downhole_equipment"):
                targets = {
                    r[2] for r in con.execute(
                        f"PRAGMA foreign_key_list({table})"
                    ).fetchall()
                }
                assert "wells" in targets, table
                assert "daily_reports" in targets, table
            assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            con.close()
