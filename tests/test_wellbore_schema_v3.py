"""Wellbore / Schema v3 foundation acceptance tests.

These tests establish the canonical hierarchy

    Company → Field/Project → Well → Wellbore → Section → DailyReport

and enforce the standing rules of the phase:

* A ``Wellbore`` is the drilling-path identity between a Well and a Section.
  It has an immutable integer PK and a stable ``well_id`` FK; it never changes
  identity because a rig, a display name, or a report source changed.
* A **sidetrack** is a *distinct* wellbore under the *same* well, carrying
  lineage to its parent (``parent_wellbore_id``). It is never auto-merged into
  the original bore, and never promoted to a new Well.
* Migration is **non-destructive**: an existing v2 database upgrades to v3 with
  the ``wellbores`` table and the two nullable ``wellbore_id`` columns added,
  and every pre-existing row preserved.
* Attribution is **deterministic-only**: an ambiguous historical record keeps
  ``wellbore_id = NULL`` ("unknown"). Uncertainty is preserved, never
  fabricated into a wellbore.

The tests reuse the real production database + import path against isolated
in-memory / temp-file databases (mirroring ``memory_manager`` from
``test_well_centric_acceptance``), with no Qt dependency.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine
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
from core.ddr_import_service import DDRImportService


RIG = "OEOC-208"


def memory_manager():
    """Canonical isolated in-memory manager seeded with Company + Project.

    Mirrors ``tests/test_well_centric_acceptance.memory_manager`` so the two
    suites build identical fixtures.
    """
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
    company = Company(name="OEOC", code="OEOC")
    session.add(company)
    session.flush()
    project = Project(name="Bid Boland", code="BB", company_id=company.id)
    session.add(project)
    session.commit()
    session.close()
    return manager


def seed_well(manager, name="AZNS 12", code="W1"):
    session = manager.create_session()
    try:
        project = session.query(Project).first()
        well = Well(project_id=project.id, name=name, code=code, rig_name=RIG)
        session.add(well)
        session.commit()
        return well.id
    finally:
        session.close()


def ddr_payload(well_name, report_date, *, section='12-1/4"', depth=2500, **extra):
    payload = {
        "well_info": {"name": well_name, "rig_name": RIG, "operator": "OEOC"},
        "daily_report": {
            "report_date": report_date,
            "section_name": section,
            "depth_0000": depth - 120,
            "depth_0600": depth - 60,
            "depth_2400": depth,
        },
        "time_logs_24h": [
            {"time_from": "00:00", "time_to": "12:00", "duration": 12,
             "main_phase": "Drilling", "status": "PLN"},
        ],
    }
    payload.update(extra)
    return payload


def import_ddr(manager, payload, well_id=None):
    service = DDRImportService(manager, well_id)
    return service.import_records(payload)


@pytest.fixture()
def manager():
    return memory_manager()


# --------------------------------------------------------------------------
# 1. Canonical model + identity
# --------------------------------------------------------------------------
class TestWellboreModel:
    def test_wellbore_sits_between_well_and_section(self, manager):
        well_id = seed_well(manager)
        wb_id = manager.get_or_create_wellbore(well_id, "Original")
        assert wb_id is not None

        session = manager.create_session()
        try:
            wb = session.get(Wellbore, wb_id)
            # Immutable identity keys.
            assert wb.id == wb_id
            assert wb.well_id == well_id
            assert wb.wellbore_type == "original"
            # Relationship both ways.
            well = session.get(Well, well_id)
            assert [w.id for w in well.wellbores] == [wb_id]
        finally:
            session.close()

    def test_get_or_create_is_idempotent_per_well_and_name(self, manager):
        well_id = seed_well(manager)
        first = manager.get_or_create_wellbore(well_id, "Original")
        again = manager.get_or_create_wellbore(well_id, "Original")
        assert first == again

        session = manager.create_session()
        try:
            assert session.query(Wellbore).filter_by(well_id=well_id).count() == 1
        finally:
            session.close()

    def test_same_name_under_different_wells_are_distinct(self, manager):
        well_a = seed_well(manager, "AZNS 12", "W1")
        well_b = seed_well(manager, "AZNS 15", "W2")
        wb_a = manager.get_or_create_wellbore(well_a, "Original")
        wb_b = manager.get_or_create_wellbore(well_b, "Original")
        assert wb_a != wb_b, "wellbores never merge across wells"


# --------------------------------------------------------------------------
# 2. Rig is not a wellbore identity
# --------------------------------------------------------------------------
class TestRigIsNotWellboreIdentity:
    def test_rig_change_does_not_fork_wellbore(self, manager):
        well_id = seed_well(manager)
        wb_id = manager.get_or_create_wellbore(well_id, "Original")

        # Change the rig on the well — a pure attribute update.
        session = manager.create_session()
        try:
            well = session.get(Well, well_id)
            well.rig_name = "OEOC-209"
            session.commit()
        finally:
            session.close()

        # Re-resolving the same wellbore name returns the SAME identity.
        again = manager.get_or_create_wellbore(well_id, "Original")
        assert again == wb_id

        session = manager.create_session()
        try:
            assert session.query(Wellbore).count() == 1
        finally:
            session.close()


# --------------------------------------------------------------------------
# 3. Sidetrack lineage — never auto-merge
# --------------------------------------------------------------------------
class TestSidetrackLineage:
    def test_sidetrack_is_distinct_wellbore_with_parent(self, manager):
        well_id = seed_well(manager, "AZNS 12")
        original = manager.get_or_create_wellbore(well_id, "Original")
        st = manager.get_or_create_wellbore(
            well_id,
            "ST #1",
            wellbore_type="sidetrack",
            parent_wellbore_id=original,
            kickoff_md=1850.0,
        )
        assert st != original

        session = manager.create_session()
        try:
            wb = session.get(Wellbore, st)
            assert wb.wellbore_type == "sidetrack"
            assert wb.parent_wellbore_id == original
            assert wb.kickoff_md == 1850.0
            assert wb.parent.id == original
            parent = session.get(Wellbore, original)
            assert [s.id for s in parent.sidetracks] == [st]
            # Both bores live under ONE well — sidetrack is not a new well.
            assert session.query(Well).count() == 1
            assert session.query(Wellbore).filter_by(well_id=well_id).count() == 2
        finally:
            session.close()

    def test_sidetrack_and_original_never_share_identity(self, manager):
        well_id = seed_well(manager, "AZNS 12")
        original = manager.get_or_create_wellbore(well_id, "AZNS 12")
        st = manager.get_or_create_wellbore(well_id, "AZNS 12 ST #1")
        assert original != st

    def test_unknown_kickoff_stays_null_not_zero(self, manager):
        well_id = seed_well(manager)
        wb_id = manager.get_or_create_wellbore(
            well_id, "ST #2", wellbore_type="sidetrack"
        )
        session = manager.create_session()
        try:
            wb = session.get(Wellbore, wb_id)
            assert wb.kickoff_md is None, "unknown kickoff is NULL, never 0"
        finally:
            session.close()


# --------------------------------------------------------------------------
# 4. Deterministic-only attribution via the real import path
# --------------------------------------------------------------------------
class TestImportAttribution:
    def test_import_without_wellbore_leaves_null(self, manager):
        """A DDR that does not name a wellbore must not fabricate one."""
        result = import_ddr(manager, ddr_payload("AZNS 12", "2024-10-21"))
        assert result.get("wellbore_id") in (None, 0) or "wellbore_id" not in result

        session = manager.create_session()
        try:
            assert session.query(Wellbore).count() == 0, "no fabricated wellbore"
            section = session.query(Section).one()
            assert section.wellbore_id is None
            report = session.query(DailyReport).one()
            assert report.wellbore_id is None
        finally:
            session.close()

    def test_import_with_named_wellbore_attributes_deterministically(self, manager):
        payload = ddr_payload("AZNS 12", "2024-10-21")
        payload["well_info"]["wellbore_name"] = "Original Hole"
        result = import_ddr(manager, payload)
        assert result.get("wellbore_id") is not None

        session = manager.create_session()
        try:
            wb = session.query(Wellbore).one()
            assert wb.name == "Original Hole"
            assert wb.wellbore_type == "original"
            section = session.query(Section).one()
            assert section.wellbore_id == wb.id
            report = session.query(DailyReport).one()
            assert report.wellbore_id == wb.id
        finally:
            session.close()

    def test_import_sidetrack_wellbore_marked_as_sidetrack(self, manager):
        payload = ddr_payload("AZNS 12", "2024-11-05")
        payload["well_info"]["wellbore_name"] = "AZNS 12 ST #1"
        payload["well_info"]["wellbore_type"] = "sidetrack"
        import_ddr(manager, payload)

        session = manager.create_session()
        try:
            wb = session.query(Wellbore).one()
            assert wb.wellbore_type == "sidetrack"
        finally:
            session.close()

    def test_two_wellbores_one_well_from_import(self, manager):
        """Original + sidetrack DDRs on one well → two wellbores, one well."""
        p1 = ddr_payload("AZNS 12", "2024-10-21")
        p1["well_info"]["wellbore_name"] = "Original"
        p2 = ddr_payload("AZNS 12", "2024-11-05", section='8-1/2"', depth=3200)
        p2["well_info"]["wellbore_name"] = "ST #1"
        p2["well_info"]["wellbore_type"] = "sidetrack"
        r1 = import_ddr(manager, p1)
        r2 = import_ddr(manager, p2)
        assert r1["well_id"] == r2["well_id"], "same well"

        session = manager.create_session()
        try:
            assert session.query(Well).count() == 1
            wbs = session.query(Wellbore).order_by(Wellbore.id).all()
            assert len(wbs) == 2
            assert {w.name for w in wbs} == {"Original", "ST #1"}
        finally:
            session.close()


# --------------------------------------------------------------------------
# 5. Non-destructive migration v2 → v3
# --------------------------------------------------------------------------
def _build_v2_database(dbp):
    """Create a faithful pre-v3 database: no wellbores table, no wellbore_id
    columns, schema_version marked 2, with real seed rows."""
    from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
    from sqlalchemy.schema import CreateTable

    def split_top(body):
        out, depth, start = [], 0, 0
        for i, ch in enumerate(body):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append(body[start:i])
                start = i + 1
        out.append(body[start:])
        return out

    con = sqlite3.connect(dbp)
    con.execute("PRAGMA foreign_keys=OFF")
    for table in Base.metadata.sorted_tables:
        if table.name == "wellbores":
            continue
        sql = str(CreateTable(table).compile(dialect=sqlite_dialect()))
        if table.name in ("sections", "daily_reports"):
            op, cl = sql.index("("), sql.rindex(")")
            head, body, tail = sql[:op], sql[op + 1 : cl], sql[cl + 1 :]
            clauses = [c for c in split_top(body) if "wellbore_id" not in c]
            sql = head + "(" + ",".join(clauses) + ")" + tail
        con.execute(sql)
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER NOT NULL, applied_at DATETIME NOT NULL)"
    )
    con.execute("INSERT INTO schema_version(version, applied_at) VALUES (2, CURRENT_TIMESTAMP)")
    con.execute("INSERT INTO companies (name, code) VALUES ('OEOC','OEOC')")
    cid = con.execute("SELECT id FROM companies").fetchone()[0]
    con.execute(
        "INSERT INTO projects (company_id, name, code) VALUES (?,?,?)",
        (cid, "Bid Boland", "BB"),
    )
    pid = con.execute("SELECT id FROM projects").fetchone()[0]
    con.execute(
        "INSERT INTO wells (project_id, name, code) VALUES (?,?,?)",
        (pid, "AZNS 12", "W1"),
    )
    wid = con.execute("SELECT id FROM wells").fetchone()[0]
    con.execute("INSERT INTO sections (well_id, name) VALUES (?,?)", (wid, '12-1/4"'))
    sid = con.execute("SELECT id FROM sections").fetchone()[0]
    con.execute(
        "INSERT INTO daily_reports (well_id, section_id, report_date, report_number) "
        "VALUES (?,?,?,?)",
        (wid, sid, "2024-10-22", 1),
    )
    con.commit()
    con.close()


class TestNonDestructiveMigration:
    def test_v2_upgrades_to_v3_without_data_loss(self, tmp_path, monkeypatch):
        dbp = str(tmp_path / "v2.sqlite")
        monkeypatch.setenv("DRILLMASTER_ENV", "test")
        monkeypatch.setenv("DRILLMASTER_DB_PATH", dbp)
        monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path))

        _build_v2_database(dbp)

        # Precondition: genuinely a v2 shape.
        con = sqlite3.connect(dbp)
        pre_cols = [r[1] for r in con.execute("PRAGMA table_info(sections)").fetchall()]
        assert "wellbore_id" not in pre_cols
        assert con.execute(
            "SELECT name FROM sqlite_master WHERE name='wellbores'"
        ).fetchone() is None
        assert con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 2
        con.close()

        manager = DatabaseManager()
        assert manager.initialize() is True, manager.last_diagnostic

        con = sqlite3.connect(dbp)
        try:
            # Version advanced.
            assert con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 3
            # New table + columns exist.
            assert con.execute(
                "SELECT name FROM sqlite_master WHERE name='wellbores'"
            ).fetchone() is not None
            sec_cols = [r[1] for r in con.execute("PRAGMA table_info(sections)").fetchall()]
            dr_cols = [r[1] for r in con.execute("PRAGMA table_info(daily_reports)").fetchall()]
            assert "wellbore_id" in sec_cols
            assert "wellbore_id" in dr_cols
            # No data loss.
            assert con.execute("SELECT name FROM wells").fetchone()[0] == "AZNS 12"
            assert con.execute("SELECT COUNT(*) FROM daily_reports").fetchone()[0] == 1
            # No fabricated attribution on legacy rows.
            assert con.execute("SELECT wellbore_id FROM sections").fetchone()[0] is None
            assert con.execute("SELECT wellbore_id FROM daily_reports").fetchone()[0] is None
        finally:
            con.close()

    def test_v2_upgrade_is_idempotent(self, tmp_path, monkeypatch):
        dbp = str(tmp_path / "v2b.sqlite")
        monkeypatch.setenv("DRILLMASTER_ENV", "test")
        monkeypatch.setenv("DRILLMASTER_DB_PATH", dbp)
        monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path))
        _build_v2_database(dbp)

        first = DatabaseManager()
        assert first.initialize() is True
        first.close()

        # Re-initialise: must stay at v3, no error, no duplication.
        second = DatabaseManager()
        assert second.initialize() is True
        second.close()

        con = sqlite3.connect(dbp)
        try:
            versions = [r[0] for r in con.execute("SELECT version FROM schema_version").fetchall()]
            assert max(versions) == 3
        finally:
            con.close()


# --------------------------------------------------------------------------
# 6. Fresh v3 schema shape
# --------------------------------------------------------------------------
class TestFreshSchema:
    def test_fresh_database_is_v3(self, tmp_path, monkeypatch):
        dbp = str(tmp_path / "fresh.sqlite")
        monkeypatch.setenv("DRILLMASTER_ENV", "test")
        monkeypatch.setenv("DRILLMASTER_DB_PATH", dbp)
        monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path))

        manager = DatabaseManager()
        assert manager.initialize() is True

        con = sqlite3.connect(dbp)
        try:
            assert con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 3
            assert con.execute(
                "SELECT name FROM sqlite_master WHERE name='wellbores'"
            ).fetchone() is not None
        finally:
            con.close()

    def test_wellbore_id_columns_are_nullable(self, manager):
        assert Section.__table__.columns["wellbore_id"].nullable is True
        assert DailyReport.__table__.columns["wellbore_id"].nullable is True
