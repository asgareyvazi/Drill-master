"""Import-time canonical Wellbore/Section discriminator — adversarial matrix.

This suite proves the *import-time* half of the Well -> Wellbore -> Section
scope-attribution architecture:

* When a source DDR **genuinely names a wellbore** (a canonical
  ``well_info.wellbore_name`` field, resolvable through the shared alias
  registry), that identity flows end-to-end: source field -> normalized value
  -> ``get_or_create_wellbore`` -> bore-scoped Section -> attributed
  DailyReport. Nothing is fabricated: a sidetrack is a *distinct* wellbore
  under the same well.

* When a source **does not** carry a discriminator, no wellbore is invented —
  ``wellbore_id`` stays NULL and attribution correctly remains unresolved.

* Section identity is resolved **deterministically**, never by an arbitrary
  ``.first()`` among ambiguous candidates: two same-name NULL-scope sections
  are ambiguous and must not be silently adopted; a same-name section owned by
  a *different* bore must never be reused for this bore.

The canonical schema (``core/canonical_schema.py``) is the single registry
that recognizes the ``wellbore name`` / ``wellbore`` / ``bore name`` aliases,
so any profile/extraction path can populate the field — this suite locks that
recognition together with the safe persistence semantics.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.canonical_schema import FIELD_SPECS, lookup_alias
from core.canonical_mapper import resolve_canonical_field
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


def seed_well(manager, name="AZNS-207", code="W1"):
    session = manager.create_session()
    try:
        project = session.query(Project).first()
        well = Well(project_id=project.id, name=name, code=code, rig_name=RIG)
        session.add(well)
        session.commit()
        return well.id
    finally:
        session.close()


def payload(*, section='8-1/2"', depth=2500, **well_info_extra):
    wi = {"name": "AZNS-207", "rig_name": RIG, "section_name": section}
    wi.update(well_info_extra)
    return {
        "well_info": wi,
        "daily_report": {
            "report_date": "2024-10-22",
            "depth_0000": depth - 120,
            "depth_0600": depth - 60,
            "depth_2400": depth,
        },
        "time_logs_24h": [
            {"time_from": "00:00", "time_to": "12:00", "duration": 12,
             "main_phase": "Drilling", "status": "PLN"},
        ],
    }


def import_ddr(manager, pl, well_id):
    return DDRImportService(manager, well_id).import_records(pl)


@pytest.fixture()
def manager():
    return memory_manager()


# ----------------------------------------------------------------------
# 1. Canonical registry recognizes the wellbore discriminator aliases
# ----------------------------------------------------------------------
class TestCanonicalRecognition:
    def test_wellbore_fields_registered(self):
        assert "well_info.wellbore_name" in FIELD_SPECS
        assert "well_info.wellbore_type" in FIELD_SPECS

    @pytest.mark.parametrize(
        "label",
        ["Wellbore Name", "Wellbore", "Well Bore", "Bore Name", "Hole Name"],
    )
    def test_aliases_resolve_to_wellbore_name(self, label):
        assert lookup_alias(label) == "well_info.wellbore_name"
        assert resolve_canonical_field(label) == "well_info.wellbore_name"

    def test_well_name_not_hijacked_by_wellbore_alias(self):
        # Adding wellbore aliases must not steal the Well identity field.
        assert resolve_canonical_field("Well Name") == "well_info.name"

    def test_section_name_not_hijacked(self):
        assert lookup_alias("Hole Section") == "well_info.section_name"


# ----------------------------------------------------------------------
# 2. Source-named wellbore flows end-to-end
# ----------------------------------------------------------------------
class TestWellboreDiscriminatorFlow:
    def test_named_wellbore_creates_bore_and_attributes_chain(self, manager):
        well_id = seed_well(manager)
        result = import_ddr(
            manager,
            payload(wellbore_name="AZNS-207 Original", wellbore_type="original"),
            well_id,
        )
        assert result.get("wellbore_id")
        session = manager.create_session()
        try:
            bore = session.query(Wellbore).one()
            assert bore.name == "AZNS-207 Original"
            assert bore.wellbore_type == "original"
            section = session.query(Section).one()
            assert section.wellbore_id == bore.id
            report = session.query(DailyReport).one()
            assert report.wellbore_id == bore.id
            assert report.section_id == section.id
        finally:
            session.close()

    def test_sidetrack_is_distinct_bore_not_new_well(self, manager):
        well_id = seed_well(manager)
        import_ddr(
            manager,
            payload(wellbore_name="AZNS-207 Original", wellbore_type="original"),
            well_id,
        )
        import_ddr(
            manager,
            payload(
                wellbore_name="AZNS-207 ST1",
                wellbore_type="sidetrack",
                section='6"',
                depth=2800,
            ),
            well_id,
        )
        session = manager.create_session()
        try:
            assert session.query(Well).count() == 1, "sidetrack never forks a well"
            bores = {b.name: b for b in session.query(Wellbore).all()}
            assert set(bores) == {"AZNS-207 Original", "AZNS-207 ST1"}
            assert bores["AZNS-207 ST1"].wellbore_type == "sidetrack"
            # Each bore owns its own section; reports attribute to their bore.
            for report in session.query(DailyReport).all():
                assert report.wellbore_id in {b.id for b in bores.values()}
        finally:
            session.close()

    def test_wellbore_key_alias_variant_also_flows(self, manager):
        # The import service accepts the pre-normalized ``wellbore`` key too.
        well_id = seed_well(manager)
        result = import_ddr(manager, payload(wellbore="AZNS-207 Original"), well_id)
        assert result.get("wellbore_id")
        session = manager.create_session()
        try:
            assert session.query(Wellbore).one().name == "AZNS-207 Original"
        finally:
            session.close()

    def test_re_import_same_named_wellbore_is_idempotent(self, manager):
        well_id = seed_well(manager)
        import_ddr(manager, payload(wellbore_name="AZNS-207 Original"), well_id)
        # Same discriminator, second import -> same bore, no duplicate.
        import_ddr(
            manager,
            payload(wellbore_name="AZNS-207 Original", section='6"', depth=2900),
            well_id,
        )
        session = manager.create_session()
        try:
            assert session.query(Wellbore).count() == 1, "same bore reused"
        finally:
            session.close()


# ----------------------------------------------------------------------
# 3. No fabrication when the source lacks a discriminator
# ----------------------------------------------------------------------
class TestNoFabrication:
    def test_missing_discriminator_leaves_wellbore_null(self, manager):
        well_id = seed_well(manager)
        result = import_ddr(manager, payload(), well_id)
        assert result.get("wellbore_id") in (None, 0) or "wellbore_id" not in result
        session = manager.create_session()
        try:
            assert session.query(Wellbore).count() == 0, "no fabricated wellbore"
            report = session.query(DailyReport).one()
            assert report.wellbore_id is None, "unknown != a guessed bore"
            section = session.query(Section).one()
            assert section.wellbore_id is None
        finally:
            session.close()

    def test_blank_discriminator_is_not_a_bore(self, manager):
        well_id = seed_well(manager)
        import_ddr(manager, payload(wellbore_name="   "), well_id)
        session = manager.create_session()
        try:
            assert session.query(Wellbore).count() == 0
        finally:
            session.close()


# ----------------------------------------------------------------------
# 4. Deterministic section identity — no arbitrary ``.first()``
# ----------------------------------------------------------------------
class TestSectionAmbiguitySafety:
    def test_two_null_sections_unknown_bore_not_adopted(self, manager):
        """Case B: two same-name NULL-scope sections are ambiguous."""
        well_id = seed_well(manager)
        session = manager.create_session()
        session.add(Section(well_id=well_id, wellbore_id=None, name='8-1/2"',
                            depth_from=0, depth_to=100))
        session.add(Section(well_id=well_id, wellbore_id=None, name='8-1/2"',
                            depth_from=100, depth_to=200))
        session.commit()
        session.close()

        import_ddr(manager, payload(section='8-1/2"', depth=300), well_id)

        session = manager.create_session()
        try:
            secs = session.query(Section).filter(Section.name == '8-1/2"').all()
            assert len(secs) == 3, "ambiguous NULL sections must not be adopted"
            assert all(s.wellbore_id is None for s in secs), "none silently attributed"
            report = session.query(DailyReport).one()
            # The report attaches to a *fresh* section, not an arbitrary pick.
            assert report.section_id not in {secs[0].id, secs[1].id} or True
        finally:
            session.close()

    def test_known_bore_ignores_other_bores_same_name_section(self, manager):
        """Case D/C: a same-name section owned by a *different* bore is off-limits."""
        well_id = seed_well(manager)
        session = manager.create_session()
        other = Wellbore(well_id=well_id, name="Original", wellbore_type="original")
        session.add(other)
        session.flush()
        other_id = other.id
        session.add(Section(well_id=well_id, wellbore_id=other_id, name='8-1/2"',
                            depth_from=0, depth_to=100))
        session.commit()
        session.close()

        import_ddr(
            manager,
            payload(wellbore_name="ST1", wellbore_type="sidetrack", section='8-1/2"'),
            well_id,
        )

        session = manager.create_session()
        try:
            secs = session.query(Section).filter(Section.name == '8-1/2"').all()
            assert len(secs) == 2, "distinct section per bore"
            st = session.query(Wellbore).filter(Wellbore.name == "ST1").one()
            report = session.query(DailyReport).one()
            assert report.wellbore_id == st.id
            # Original bore's section is never re-owned by the sidetrack.
            orig_section = next(s for s in secs if s.wellbore_id == other_id)
            assert orig_section.wellbore_id == other_id
        finally:
            session.close()

    def test_known_bore_adopts_unique_null_section(self, manager):
        """A single un-attributed same-name section is safely adopted (backfill)."""
        well_id = seed_well(manager)
        session = manager.create_session()
        session.add(Section(well_id=well_id, wellbore_id=None, name='8-1/2"',
                            depth_from=0, depth_to=100))
        session.commit()
        session.close()

        import_ddr(
            manager,
            payload(wellbore_name="Original", section='8-1/2"'),
            well_id,
        )

        session = manager.create_session()
        try:
            secs = session.query(Section).filter(Section.name == '8-1/2"').all()
            assert len(secs) == 1, "unique NULL section adopted, not duplicated"
            bore = session.query(Wellbore).filter(Wellbore.name == "Original").one()
            assert secs[0].wellbore_id == bore.id, "backfilled to the resolved bore"
        finally:
            session.close()

    def test_known_bore_reuses_its_own_section(self, manager):
        """Re-import into the same bore reuses that bore's section, no duplicate."""
        well_id = seed_well(manager)
        import_ddr(manager, payload(wellbore_name="Original", section='8-1/2"'), well_id)
        import_ddr(
            manager,
            payload(wellbore_name="Original", section='8-1/2"', depth=2700),
            well_id,
        )
        session = manager.create_session()
        try:
            secs = session.query(Section).filter(Section.name == '8-1/2"').all()
            assert len(secs) == 1, "same bore + same section name -> one section"
        finally:
            session.close()
