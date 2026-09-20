"""M23 Track D — Wellbore / sidetrack scope in the read & display path.

These are Qt-free domain tests: they exercise the database read helpers and the
schematic builder directly against an in-memory SQLite database. They prove:

* ``get_full_hierarchy`` groups sections UNDER their owning wellbore, so an
  original hole and a sidetrack that reuse the same section name stay distinct.
* ``get_sections_by_well`` carries ``wellbore_id`` so a caller can tell which
  bore a section belongs to (NULL = unknown, never silently the original).
* ``SchematicAutoBuilder.build_from_well`` can be scoped to a single wellbore
  and then isolates that bore's casing / formation / completion — combining
  bores only happens in the explicit whole-well view.
* A previously silent defect (completion appended to a non-existent attribute)
  is fixed: completion data now actually reaches the schematic.

Nothing here fabricates data: unknown bores stay NULL and are never claimed by
a specific wellbore.
"""

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base,
    DatabaseManager,
    Company,
    Project,
    Well,
    Wellbore,
    Section,
    DailyReport,
    CasingReport,
    FormationReport,
    DownholeEquipment,
)
from core.wellbore_schematic_engine import SchematicAutoBuilder


@pytest.fixture()
def db():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    m.create_session()
    return m


@pytest.fixture()
def two_bore_well(db):
    """A well with an original bore and a sidetrack.

    Both bores drill a section with the SAME name ('12-1/4"') and each carries
    its own casing, formation and completion so cross-bore mixing is
    observable. A third, legacy section has an unknown (NULL) bore.
    """
    s = db.create_session()
    c = Company(name="OP", code="OP")
    s.add(c)
    s.flush()
    p = Project(name="PR", code="PR", company_id=c.id)
    s.add(p)
    s.flush()
    w = Well(name="W1", code="W1", project_id=p.id)
    s.add(w)
    s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original")
    s.add(orig)
    s.flush()
    st1 = Wellbore(
        well_id=w.id,
        name="ST-1",
        wellbore_type="sidetrack",
        parent_wellbore_id=orig.id,
        kickoff_md=2500.0,
    )
    s.add(st1)
    s.flush()
    sec_o = Section(name='12-1/4"', well_id=w.id, wellbore_id=orig.id, depth_from=1000)
    sec_s = Section(name='12-1/4"', well_id=w.id, wellbore_id=st1.id, depth_from=2500)
    sec_legacy = Section(name='17-1/2"', well_id=w.id, wellbore_id=None, depth_from=0)
    s.add_all([sec_o, sec_s, sec_legacy])
    s.flush()
    r_o = DailyReport(
        well_id=w.id, section_id=sec_o.id, wellbore_id=orig.id,
        report_number=1, report_date=date(2026, 1, 1), depth_2400=1200,
    )
    r_s = DailyReport(
        well_id=w.id, section_id=sec_s.id, wellbore_id=st1.id,
        report_number=2, report_date=date(2026, 1, 5), depth_2400=2800,
    )
    s.add_all([r_o, r_s])
    s.flush()
    s.add_all([
        CasingReport(
            well_id=w.id, section_id=sec_o.id, report_id=r_o.id,
            report_date=date(2026, 1, 1),
            casing_json=json.dumps([
                {"type": "Surface", "od": 13.375, "from": 0, "to": 1000}]),
        ),
        CasingReport(
            well_id=w.id, section_id=sec_s.id, report_id=r_s.id,
            report_date=date(2026, 1, 5),
            casing_json=json.dumps([
                {"type": "Production", "od": 9.625, "from": 2500, "to": 3200}]),
        ),
        FormationReport(
            well_id=w.id, report_id=r_o.id, report_name="F-O",
            formations_json=[{"name": "Asmari", "top": 900, "base": 1100}],
        ),
        FormationReport(
            well_id=w.id, report_id=r_s.id, report_name="F-S",
            formations_json=[{"name": "Sarvak", "top": 2600, "base": 3000}],
        ),
        DownholeEquipment(
            well_id=w.id, report_id=r_o.id,
            equipment_data_json=[{
                "name": "Packer-O", "type": "packer",
                "depth": 950, "od_inch": 7.0, "length_m": 2.0}],
        ),
        DownholeEquipment(
            well_id=w.id, report_id=r_s.id,
            equipment_data_json=[{
                "name": "Packer-S", "type": "packer",
                "depth": 2900, "od_inch": 5.5, "length_m": 2.0}],
        ),
    ])
    s.commit()
    ids = {
        "well": w.id, "orig": orig.id, "st1": st1.id,
        "sec_o": sec_o.id, "sec_s": sec_s.id, "sec_legacy": sec_legacy.id,
    }
    s.close()
    return ids


# ---------------------------------------------------------------------------
# get_full_hierarchy — bore grouping
# ---------------------------------------------------------------------------

def test_hierarchy_groups_sections_under_wellbore(db, two_bore_well):
    h = db.get_full_hierarchy()
    well = h[0]["projects"][0]["wells"][0]
    bores = {wb["name"]: wb for wb in well["wellbores"]}
    assert set(bores) == {"Original", "ST-1"}
    # Same section name, but each stays under its own bore.
    assert [s["name"] for s in bores["Original"]["sections"]] == ['12-1/4"']
    assert [s["name"] for s in bores["ST-1"]["sections"]] == ['12-1/4"']
    assert bores["Original"]["sections"][0]["id"] != bores["ST-1"]["sections"][0]["id"]


def test_hierarchy_preserves_sidetrack_lineage(db, two_bore_well):
    well = db.get_full_hierarchy()[0]["projects"][0]["wells"][0]
    bores = {wb["name"]: wb for wb in well["wellbores"]}
    assert bores["Original"]["wellbore_type"] == "original"
    assert bores["Original"]["parent_wellbore_id"] is None
    assert bores["ST-1"]["wellbore_type"] == "sidetrack"
    assert bores["ST-1"]["parent_wellbore_id"] == bores["Original"]["id"]
    assert bores["ST-1"]["kickoff_md"] == 2500.0


def test_hierarchy_keeps_unknown_bore_section_visible(db, two_bore_well):
    """A legacy NULL-bore section is shown as unassigned, never reattached."""
    well = db.get_full_hierarchy()[0]["projects"][0]["wells"][0]
    assert [s["name"] for s in well["unassigned_sections"]] == ['17-1/2"']
    for wb in well["wellbores"]:
        assert '17-1/2"' not in [s["name"] for s in wb["sections"]]


def test_hierarchy_flat_section_list_backward_compatible(db, two_bore_well):
    """The legacy flat ``sections`` list is retained (with wellbore_id added)."""
    well = db.get_full_hierarchy()[0]["projects"][0]["wells"][0]
    names = sorted(s["name"] for s in well["sections"])
    assert names == ['12-1/4"', '12-1/4"', '17-1/2"']
    # every flat section still exposes its bore (or None)
    assert all("wellbore_id" in s for s in well["sections"])


def test_hierarchy_reports_carry_wellbore_id(db, two_bore_well):
    well = db.get_full_hierarchy()[0]["projects"][0]["wells"][0]
    bores = {wb["name"]: wb for wb in well["wellbores"]}
    orig_report = bores["Original"]["sections"][0]["reports"][0]
    st_report = bores["ST-1"]["sections"][0]["reports"][0]
    assert orig_report["wellbore_id"] == bores["Original"]["id"]
    assert st_report["wellbore_id"] == bores["ST-1"]["id"]


def test_hierarchy_single_bore_well_still_works(db):
    """A well with no wellbore rows keeps a flat, empty-wellbores structure."""
    s = db.create_session()
    c = Company(name="C", code="C")
    s.add(c)
    s.flush()
    p = Project(name="P", code="P", company_id=c.id)
    s.add(p)
    s.flush()
    w = Well(name="Solo", code="S", project_id=p.id)
    s.add(w)
    s.flush()
    s.add(Section(name='8-1/2"', well_id=w.id, wellbore_id=None, depth_from=0))
    s.commit()
    s.close()
    well = db.get_full_hierarchy()[0]["projects"][0]["wells"][0]
    assert well["wellbores"] == []
    assert [s["name"] for s in well["sections"]] == ['8-1/2"']
    assert [s["name"] for s in well["unassigned_sections"]] == ['8-1/2"']


# ---------------------------------------------------------------------------
# get_sections_by_well — wellbore_id exposure
# ---------------------------------------------------------------------------

def test_sections_by_well_exposes_wellbore_id(db, two_bore_well):
    sections = db.get_sections_by_well(two_bore_well["well"])
    by_id = {s["id"]: s for s in sections}
    assert by_id[two_bore_well["sec_o"]]["wellbore_id"] == two_bore_well["orig"]
    assert by_id[two_bore_well["sec_s"]]["wellbore_id"] == two_bore_well["st1"]
    assert by_id[two_bore_well["sec_legacy"]]["wellbore_id"] is None


# ---------------------------------------------------------------------------
# SchematicAutoBuilder — bore-scoped schematic
# ---------------------------------------------------------------------------

def test_schematic_isolates_casing_per_bore(db, two_bore_well):
    eng = SchematicAutoBuilder(db)
    so = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["orig"])
    ss = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["st1"])
    assert [c.od_inch for c in so.casings] == [13.375]
    assert [c.od_inch for c in ss.casings] == [9.625]


def test_schematic_isolates_formation_per_bore(db, two_bore_well):
    eng = SchematicAutoBuilder(db)
    so = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["orig"])
    ss = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["st1"])
    assert [f.name for f in so.formations] == ["Asmari"]
    assert [f.name for f in ss.formations] == ["Sarvak"]


def test_schematic_isolates_completion_per_bore(db, two_bore_well):
    eng = SchematicAutoBuilder(db)
    so = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["orig"])
    ss = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["st1"])
    assert [c.label for c in so.completion] == ["Packer-O"]
    assert [c.label for c in ss.completion] == ["Packer-S"]


def test_schematic_scoped_carries_wellbore_name(db, two_bore_well):
    eng = SchematicAutoBuilder(db)
    so = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["orig"])
    assert so.wellbore_name == "Original"
    # Whole-well view does not fabricate a bore name.
    whole = eng.build_from_well(two_bore_well["well"])
    assert whole.wellbore_name == ""


def test_schematic_completion_reaches_schematic(db, two_bore_well):
    """Regression: completion used to be appended to a non-existent attribute
    (schematic.completions) and silently lost. It must now be present."""
    eng = SchematicAutoBuilder(db)
    whole = eng.build_from_well(two_bore_well["well"])
    labels = sorted(c.label for c in whole.completion)
    assert labels == ["Packer-O", "Packer-S"]


def test_schematic_scoped_excludes_unknown_bore(db, two_bore_well):
    """A bore-scoped schematic never picks up records with an unknown bore."""
    # add a NULL-bore casing report; it must not appear in either bore view
    s = db.create_session()
    legacy_rep = DailyReport(
        well_id=two_bore_well["well"], section_id=two_bore_well["sec_legacy"],
        wellbore_id=None, report_number=9, report_date=date(2026, 2, 1),
    )
    s.add(legacy_rep)
    s.flush()
    s.add(CasingReport(
        well_id=two_bore_well["well"], section_id=two_bore_well["sec_legacy"],
        report_id=legacy_rep.id, report_date=date(2026, 2, 1),
        casing_json=json.dumps([
            {"type": "Conductor", "od": 30.0, "from": 0, "to": 100}]),
    ))
    s.commit()
    s.close()
    eng = SchematicAutoBuilder(db)
    so = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["orig"])
    ss = eng.build_from_well(two_bore_well["well"], wellbore_id=two_bore_well["st1"])
    assert 30.0 not in [c.od_inch for c in so.casings]
    assert 30.0 not in [c.od_inch for c in ss.casings]
