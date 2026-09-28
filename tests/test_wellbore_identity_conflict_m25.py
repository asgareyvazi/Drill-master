"""Mission 25 — §22/§23: get_or_create_wellbore identity conflict matrix.

Locks the import-identity safety contract for reconciling an incoming wellbore
against a stored one that shares ``(well_id, name)``:

  Case A  same metadata            -> IDEMPOTENT (same id, unchanged)
  Case B  type original vs sidetrack (explicit) -> CONFLICT (raise)
  Case C  same parent              -> IDEMPOTENT
  Case D  different parent         -> CONFLICT (raise)
  Case E  stored kickoff NULL, incoming explicit -> SAFE ENRICHMENT

Authoritative identity metadata (type, parent) is never silently mutated; only
a stored NULL is enriched from an explicit incoming value.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, Wellbore,
)
from core.import_diagnostics import OwnershipIntegrityError


@pytest.fixture()
def db():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    m.create_session()
    return m


@pytest.fixture()
def well(db):
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original")
    s.add(orig); s.flush()
    ids = {"well": w.id, "orig": orig.id}
    s.commit(); s.close()
    return ids


def _get(db, wb_id):
    s = db.create_session()
    try:
        return s.get(Wellbore, wb_id)
    finally:
        s.close()


# --- Case A: idempotent same metadata --------------------------------------

def test_case_a_idempotent_same_metadata(db, well):
    first = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"], kickoff_md=2500)
    second = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"], kickoff_md=2500)
    assert first == second
    wb = _get(db, first)
    assert wb.wellbore_type == "sidetrack"
    assert wb.parent_wellbore_id == well["orig"]
    assert wb.kickoff_md == 2500


def test_case_a_plain_get_no_type_is_idempotent(db, well):
    """A plain get with the default 'original' fallback must not conflict with a
    stored sidetrack."""
    st = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"])
    again = db.get_or_create_wellbore(well["well"], "ST-1")  # default 'original'
    assert again == st
    assert _get(db, st).wellbore_type == "sidetrack"  # not flipped


# --- Case B: conflicting type ----------------------------------------------

def test_case_b_conflicting_type_raises(db, well):
    # Existing 'Original' (original). Incoming explicitly 'sidetrack'.
    with pytest.raises(OwnershipIntegrityError):
        db.get_or_create_wellbore(
            well["well"], "Original", wellbore_type="sidetrack")
    # Stored type unchanged.
    assert _get(db, well["orig"]).wellbore_type == "original"


# --- Case C: same parent idempotent ----------------------------------------

def test_case_c_same_parent_idempotent(db, well):
    st = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"])
    again = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"])
    assert st == again
    assert _get(db, st).parent_wellbore_id == well["orig"]


# --- Case D: conflicting parent --------------------------------------------

def test_case_d_conflicting_parent_raises(db, well):
    s = db.create_session()
    other = Wellbore(well_id=well["well"], name="Other", wellbore_type="original")
    s.add(other); s.flush(); other_id = other.id; s.commit(); s.close()

    st = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"])
    with pytest.raises(OwnershipIntegrityError):
        db.get_or_create_wellbore(
            well["well"], "ST-1", wellbore_type="sidetrack",
            parent_wellbore_id=other_id)
    # Lineage unchanged.
    assert _get(db, st).parent_wellbore_id == well["orig"]


# --- Case E: kickoff enrichment --------------------------------------------

def test_case_e_kickoff_null_enriched(db, well):
    st = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"])   # kickoff unknown (None)
    assert _get(db, st).kickoff_md is None
    again = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"], kickoff_md=2500)
    assert again == st
    assert _get(db, st).kickoff_md == 2500   # safely enriched


def test_case_e_known_kickoff_not_overwritten(db, well):
    st = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"], kickoff_md=2500)
    # A different incoming kickoff does NOT silently overwrite a known value.
    db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"], kickoff_md=9999)
    assert _get(db, st).kickoff_md == 2500


# --- Parent enrichment from NULL -------------------------------------------

def test_parent_null_enriched(db, well):
    # Create ST-1 with no parent, then supply the parent later.
    st = db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack")
    assert _get(db, st).parent_wellbore_id is None
    db.get_or_create_wellbore(
        well["well"], "ST-1", wellbore_type="sidetrack",
        parent_wellbore_id=well["orig"])
    assert _get(db, st).parent_wellbore_id == well["orig"]
