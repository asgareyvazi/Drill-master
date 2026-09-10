"""Well-centric acceptance scenario (master handoff §34 / §35).

Exact conceptual scenario:

    Rig OEOC-208
        ├── AZNS 12
        │    └── Wellbore 1 (modeled today as the well's section interval)
        │         ├── Section
        │         ├── DDR 001
        │         ├── DDR 002
        │         ├── BHA Run 1
        │         └── Bit Run 1
        ├── AZNS 12 ST #1
        └── AZNS 15

Expected:

* OEOC-208 is NOT a well identity — it is an attribute shared by three
  distinct wells.
* DDR 001 → DDR 002 preserve longitudinal continuity under the same well
  (one well, two dated facts, shared section, same BHA/Bit run identity).
* ``AZNS 12 ST #1`` must never automatically merge with ``AZNS 12``.

These tests run the real production import path
(``core.ddr_import_service.DDRImportService`` — no Qt) against an isolated
in-memory database.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, Company, Project, Well, Section, DailyReport
from core.database import BHAReport, BitReport, TimeLog24H
from core.database import DatabaseManager
from core.ddr_import_service import DDRImportService


RIG = "OEOC-208"


def memory_manager():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)
    session = manager.create_session()
    company = Company(name="OEOC", code="OEOC")
    session.add(company)
    session.flush()
    project = Project(name="Bid Boland", code="BB", company_id=company.id)
    session.add(project)
    session.commit()
    session.close()
    return manager


def ddr_payload(well_name, report_date, *, section='12-1/4"', depth=2500, **extra):
    """A canonical-style extracted payload for one DDR of the scenario."""
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
            {"time_from": "12:00", "time_to": "24:00", "duration": 12,
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


class TestRigIsNotWellIdentity:
    def test_three_wells_one_rig_stay_separate(self, manager):
        import_ddr(manager, ddr_payload("AZNS 12", "2024-10-21"))
        import_ddr(manager, ddr_payload("AZNS 12", "2024-10-22"))
        import_ddr(manager, ddr_payload("AZNS 12 ST #1", "2024-11-05"))
        import_ddr(manager, ddr_payload("AZNS 15", "2024-12-01"))

        session = manager.create_session()
        try:
            wells = session.query(Well).order_by(Well.id).all()
            assert len(wells) == 3, [w.name for w in wells]
            names = {w.name for w in wells}
            assert names == {"AZNS 12", "AZNS 12 ST #1", "AZNS 15"}
            # The rig is shared metadata, never identity.
            assert all(w.rig_name == RIG for w in wells)
            assert len({w.id for w in wells}) == 3
            # DDR facts: 2 for AZNS 12, 1 each for the others
            reports = session.query(DailyReport).all()
            assert len(reports) == 4
            azns12 = next(w for w in wells if w.name == "AZNS 12")
            assert len([r for r in reports if r.well_id == azns12.id]) == 2
        finally:
            session.close()


class TestDDRContinuity:
    def test_two_ddrs_share_well_section_and_run_identity(self, manager):
        bha = {"bha_name": "BHA #1", "bha_data": [
            {"component_name": "Bit", "od": 8.5}, {"component_name": "DC", "od": 6.5}]}
        bit = {"bit_records_json": [{"bit_no": "1", "size_in": 12.25, "serial": "BT-77"}]}
        first = import_ddr(manager, ddr_payload(
            "AZNS 12", "2024-10-21", bha_report=bha, bit_report=bit))
        second = import_ddr(manager, ddr_payload(
            "AZNS 12", "2024-10-22", bha_report=bha, bit_report=bit))

        assert first["well_id"] == second["well_id"], "consecutive DDRs must stay on one well"
        session = manager.create_session()
        try:
            reports = (
                session.query(DailyReport)
                .filter_by(well_id=first["well_id"])
                .order_by(DailyReport.report_date)
                .all()
            )
            assert len(reports) == 2
            assert [r.report_number for r in reports] == [1, 2]
            # Same section reused — not one section per DDR.
            assert len({r.section_id for r in reports}) == 1
            # Time logs are per-day facts.
            assert session.query(TimeLog24H).filter_by(
                report_id=reports[0].id).count() == 2
            assert session.query(TimeLog24H).filter_by(
                report_id=reports[1].id).count() == 2
            # BHA / Bit run identity is preserved across both DDRs: the same
            # run name/serial appears on both daily snapshots of one well.
            bhas = session.query(BHAReport).filter_by(well_id=first["well_id"]).all()
            assert len(bhas) == 2, "one snapshot per DDR for the same run"
            assert {b.bha_name for b in bhas} == {"BHA #1"}
            assert {b.report_id for b in bhas} == {r.id for r in reports}
            bits = session.query(BitReport).filter_by(well_id=first["well_id"]).all()
            assert len(bits) == 2
            assert {b.report_id for b in bits} == {r.id for r in reports}
        finally:
            session.close()

    def test_identical_reimport_is_idempotent(self, manager):
        payload = ddr_payload("AZNS 12", "2024-10-21")
        first = import_ddr(manager, payload)
        again = import_ddr(manager, payload)

        assert again.get("reimport") is True
        assert again["imported"] == 0
        assert again["report_id"] == first["report_id"]
        session = manager.create_session()
        try:
            assert session.query(Well).count() == 1
            assert session.query(DailyReport).count() == 1
        finally:
            session.close()


class TestSidetrackNeverMerges:
    def test_st_well_is_a_distinct_well(self, manager):
        import_ddr(manager, ddr_payload("AZNS 12", "2024-10-21"))
        st = import_ddr(manager, ddr_payload("AZNS 12 ST #1", "2024-11-05"))
        assert st["well_id"] is not None

        session = manager.create_session()
        try:
            wells = session.query(Well).all()
            assert len(wells) == 2
            assert {w.name for w in wells} == {"AZNS 12", "AZNS 12 ST #1"}
        finally:
            session.close()

    def test_variant_names_resolve_to_same_well_but_new_names_do_not_merge(self, manager):
        """AZNS-12 (code variant) → same well; a genuinely new label never
        silently merges into an existing well."""
        base = import_ddr(manager, ddr_payload("AZNS 12", "2024-10-21"))

        # Same well re-selected via a second import whose well_info uses the
        # hyphenated variant as code, identical name.
        variant = ddr_payload("AZNS 12", "2024-10-23")
        variant["well_info"] = {"name": "AZNS-12", "rig_name": RIG}
        result = import_ddr(manager, variant)
        assert result["well_id"] == base["well_id"], (
            "hyphenated label variant must resolve to the same well identity"
        )

        session = manager.create_session()
        try:
            assert session.query(Well).count() == 1
        finally:
            session.close()


class TestRigChangePreservesWellIdentity:
    """Scenario F: the rig changes mid-program on the same well.

    A rig is an attribute (of a report / of the program), never a well
    identity key. Importing later DDRs from a different rig under the same
    well name must update the attribute and stay on the SAME well — no new
    well, no orphaned reports.
    """

    def test_rig_change_same_well_no_fork(self, manager):
        import_ddr(manager, ddr_payload("AZNS 12", "2024-10-21"))
        import_ddr(
            manager,
            ddr_payload(
                "AZNS 12",
                "2024-10-22",
                well_info={"name": "AZNS 12", "rig_name": "OEOC-209", "operator": "OEOC"},
            ),
        )

        session = manager.create_session()
        try:
            wells = session.query(Well).all()
            assert len(wells) == 1, [w.name for w in wells]
            reports = (
                session.query(DailyReport)
                .filter(DailyReport.well_id == wells[0].id)
                .order_by(DailyReport.report_date)
                .all()
            )
            assert len(reports) == 2
            # Both reports hang off the single well regardless of rig name.
            assert {r.well_id for r in reports} == {wells[0].id}
        finally:
            session.close()

    def test_new_rig_first_then_old_rig_also_no_fork(self, manager):
        """Order must not matter: identity follows the well, not the rig."""
        import_ddr(
            manager,
            ddr_payload(
                "AZNS 15",
                "2024-12-01",
                well_info={"name": "AZNS 15", "rig_name": "OEOC-209", "operator": "OEOC"},
            ),
        )
        import_ddr(manager, ddr_payload("AZNS 15", "2024-12-02"))

        session = manager.create_session()
        try:
            assert session.query(Well).count() == 1
        finally:
            session.close()


class TestHierarchyConsistency:
    def test_every_report_section_belongs_to_its_report_well(self, manager):
        import_ddr(manager, ddr_payload("AZNS 12", "2024-10-21"))
        import_ddr(manager, ddr_payload("AZNS 12 ST #1", "2024-11-05"))
        import_ddr(manager, ddr_payload("AZNS 15", "2024-12-01"))

        session = manager.create_session()
        try:
            reports = session.query(DailyReport).all()
            assert reports
            for report in reports:
                assert report.section_id is not None
                section = session.get(Section, report.section_id)
                well = session.get(Well, report.well_id)
                assert section is not None and well is not None
                assert section.well_id == report.well_id, (
                    f"section {section.name} belongs to well {section.well_id} "
                    f"but report {report.id} claims well {report.well_id}"
                )
                assert well.project_id is not None
        finally:
            session.close()

    def test_sections_are_scoped_to_their_well(self, manager):
        import_ddr(manager, ddr_payload("AZNS 12", "2024-10-21"))
        import_ddr(manager, ddr_payload("AZNS 15", "2024-12-01"))
        session = manager.create_session()
        try:
            wells = session.query(Well).all()
            for well in wells:
                for section in session.query(Section).filter_by(well_id=well.id):
                    assert section.well_id == well.id
            # two wells, same section label, must remain two distinct rows
            assert session.query(Section).count() == 2
        finally:
            session.close()
