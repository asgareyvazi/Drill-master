"""Persistence + import + integration tests for the drill-pipe reference repo.

These use synthetic specs only (the mission forbids fabricating a production
dataset); the point is to prove the persistence *contract*, not to ship data.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, DatabaseManager, DrillPipeSpecRecord
from core.engineering.drill_pipe import DrillPipeSpec, Provenance
from core.engineering.engines.torque_drag import TorqueDragEngine
from core.repositories.drill_pipe_reference_repository import (
    CONFLICT,
    ENRICHED,
    INVALID,
    NEW,
    UNCHANGED,
    DrillPipeReferenceRepository,
)


@pytest.fixture()
def repo():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    return DrillPipeReferenceRepository(m)


def _spec(**over):
    row = {
        "Manufacturer": "NOV",
        "Product": "5DP",
        "OD (in)": 5.0,
        "Weight (ppf)": 19.5,
        "Grade": "S-135",
        "Connection": "NC50",
    }
    row.update(over)
    return DrillPipeSpec.from_vendor_row(row, provenance=Provenance(source="unit-test"))


# ---------------------------------------------------------------- persistence
def test_table_autocreates_on_real_initialize(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_MODE", "development")
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(tmp_path / "t.db"))
    db = DatabaseManager()
    db.initialize()  # credential step may block; table creation precedes it
    import sqlite3

    con = sqlite3.connect(str(tmp_path / "t.db"))
    try:
        found = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='drill_pipe_specs'"
        ).fetchone()
    finally:
        con.close()
    assert found is not None


def test_insert_then_get_roundtrips_losslessly(repo):
    s = _spec(**{"ID (in)": 4.276})
    assert repo.upsert(s).outcome == NEW
    got = repo.get_spec(s)
    assert got is not None
    assert got.nominal_od_in == 5.0
    assert got.nominal_weight_ppf == 19.5
    assert got.nominal_id_in == 4.276
    assert got.manufacturer == "NOV"
    assert got.provenance.source == "unit-test"
    assert got.identity_fingerprint() == s.identity_fingerprint()


def test_identity_fingerprint_stable_across_float_spelling(repo):
    a = _spec(**{"OD (in)": 5.0, "Weight (ppf)": 19.5})
    b = _spec(**{"OD (in)": 5.000, "Weight (ppf)": 19.50})
    assert a.identity_fingerprint() == b.identity_fingerprint()
    assert repo.upsert(a).outcome == NEW
    # same identity via different spelling -> not a second row
    assert repo.upsert(b).outcome == UNCHANGED
    assert repo.count() == 1


def test_unique_constraint_is_the_fingerprint(repo):
    assert any(
        c.name == "identity_fingerprint" and c.unique
        for c in DrillPipeSpecRecord.__table__.columns
    )


# --------------------------------------------------------------------- import
def test_identical_reimport_is_unchanged(repo):
    s = _spec()
    assert repo.upsert(s).outcome == NEW
    assert repo.upsert(_spec()).outcome == UNCHANGED
    assert repo.count() == 1


def test_duplicate_fills_gaps_without_overwriting(repo):
    assert repo.upsert(_spec()).outcome == NEW
    enriched = _spec(tensile=550.0)
    assert repo.upsert(enriched).outcome == ENRICHED
    got = repo.get_spec(_spec())
    assert got.tensile_rating_klbf == 550.0
    assert repo.count() == 1


def test_enrich_never_changes_existing_value(repo):
    repo.upsert(_spec(**{"ID (in)": 4.276}))
    # incoming has a *different* ID -> that is a conflict, not enrichment
    res = repo.upsert(_spec(**{"ID (in)": 3.5}))
    assert res.outcome == CONFLICT
    got = repo.get_spec(_spec())
    assert got.nominal_id_in == 4.276  # stored value untouched


def test_conflicting_reimport_is_rejected_and_not_written(repo):
    repo.upsert(_spec(**{"ID (in)": 4.276}))
    before = repo.get_spec(_spec()).nominal_id_in
    assert repo.upsert(_spec(**{"ID (in)": 3.0})).outcome == CONFLICT
    assert repo.get_spec(_spec()).nominal_id_in == before
    assert repo.count() == 1


def test_spec_without_identity_is_invalid(repo):
    s = DrillPipeSpec.from_vendor_row({"OD (in)": 5.0})  # no weight -> no identity
    assert repo.upsert(s).outcome == INVALID
    assert repo.count() == 0


def test_import_specs_summary_counts(repo):
    specs = [
        _spec(),                       # NEW
        _spec(),                       # UNCHANGED
        _spec(tensile=550.0),          # ENRICHED
        _spec(**{"ID (in)": 4.0}),     # ENRICHED (fills id)
        _spec(**{"ID (in)": 3.0}),     # CONFLICT (id now differs)
        DrillPipeSpec.from_vendor_row({"OD (in)": 5.0}),  # INVALID
    ]
    summary = repo.import_specs(specs)
    d = summary.as_dict()
    assert d["rows_seen"] == 6
    assert d["inserted"] == 1
    assert d["unchanged"] == 1
    assert d["enriched"] == 2
    assert d["conflicting"] == 1
    assert d["invalid"] == 1
    assert len(d["rows"]) == 6


def test_import_is_row_isolated_bad_row_keeps_good_rows(repo):
    specs = [
        _spec(**{"Product": "5DP"}),
        DrillPipeSpec.from_vendor_row({"OD (in)": 5.0}),  # invalid, must not abort
        _spec(**{"Product": "5.5DP", "OD (in)": 5.5, "Weight (ppf)": 21.9}),
    ]
    summary = repo.import_specs(specs)
    assert summary.inserted == 2
    assert summary.invalid == 1
    assert repo.count() == 2


# ---------------------------------------------------------------- integration
def test_stored_spec_drives_engine_calculation(repo):
    repo.upsert(_spec(**{"ID (in)": 4.276}))
    got = repo.get_spec(_spec())
    comp = got.to_component(length_m=3048.0)
    result = TorqueDragEngine.calculate(
        survey=[{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}],
        bha=[comp],
        mud_density_ppg=10.0,
        friction_factor=0.3,
    )
    # Vertical hole: buoyed hanging weight, ground-truth 165.23 klbf.
    assert result.values["total_buoyed_weight"] == pytest.approx(165.23, abs=0.1)
