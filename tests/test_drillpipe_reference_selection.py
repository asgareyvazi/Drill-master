"""Production integration: persisted DrillPipe reference -> Quick-Select choice
-> engineering component -> TorqueDragEngine.

The reference-selection LOGIC lives in Qt-free helpers in
``dialogs.engineering_dialogs`` (build_reference_choices / reference_spec_label /
reference_component_fields); the AddPipeDialog is a thin view over them. These
tests exercise that real production logic end-to-end through a temporary DB and
the real repository, without constructing a Qt widget (which is environmentally
fragile in the shared headless test process). No fabricated production data ships.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, DatabaseManager
from core.engineering.drill_pipe import DrillPipeSpec, Provenance
from core.engineering.engines.torque_drag import TorqueDragEngine
from core.repositories.drill_pipe_reference_repository import (
    DrillPipeReferenceRepository,
)
from dialogs.engineering_dialogs import (
    REFERENCE_LABEL_PREFIX,
    build_reference_choices,
    reference_component_fields,
    reference_spec_label,
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
    row = {"Manufacturer": "NOV", "Product": "5DP", "OD (in)": 5.0, "Weight (ppf)": 19.5}
    row.update(over)
    return DrillPipeSpec.from_vendor_row(row, provenance=Provenance(source="test"))


# ------------------------------------------------------- label / choice logic
def test_empty_catalog_yields_no_choices(repo):
    assert build_reference_choices(repo.all()) == {}


def test_label_shows_engineering_identity_not_pk(repo):
    repo.upsert(_spec(Manufacturer="Vallourec", Product="VAM"))
    choices = build_reference_choices(repo.all())
    assert len(choices) == 1
    label = next(iter(choices))
    assert label.startswith(REFERENCE_LABEL_PREFIX)
    assert "Vallourec" in label and "5" in label and "19.5" in label
    assert "id 1" not in label.lower()


def test_only_offerable_specs_have_usable_od_and_weight(repo):
    repo.upsert(_spec())
    for spec in build_reference_choices(repo.all()).values():
        assert spec.nominal_od_in is not None
        assert spec.nominal_weight_ppf is not None


def test_unbranded_spec_still_labelled(repo):
    repo.upsert(DrillPipeSpec.from_vendor_row({"OD (in)": 5.0, "Weight (ppf)": 19.5}))
    label = reference_spec_label(next(iter(build_reference_choices(repo.all()).values())))
    assert "(unbranded)" in label


def test_distinct_identities_are_not_collapsed(repo):
    # Different weights => different identity => different label => two choices.
    repo.upsert(_spec(**{"Weight (ppf)": 19.5}))
    repo.upsert(_spec(**{"Weight (ppf)": 25.6, "ID (in)": 4.0}))
    choices = build_reference_choices(repo.all())
    assert len(choices) == 2  # no silent collapse of distinct engineering specs


def test_reference_fields_omit_none_no_fabrication():
    spec = _spec()  # ID is None (not provided)
    fields = reference_component_fields(spec)
    assert "id" not in fields  # never fabricates an ID default
    assert fields["od"] == 5.0
    assert fields["weight"] == 19.5


# ----------------------------------------------------- end-to-end into engine
def test_reference_selection_flows_into_torque_drag(repo):
    repo.upsert(_spec(**{"ID (in)": 4.276}))
    choices = build_reference_choices(repo.all())
    spec = next(iter(choices.values()))
    fields = reference_component_fields(spec)
    # assemble the component exactly as the dialog would (manual length added)
    comp = {
        "type": "Drill Pipe",
        "od": fields["od"],
        "id": fields["id"],
        "weight": fields["weight"],
        "length": 3048.0,
    }
    result = TorqueDragEngine.calculate(
        survey=[{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}],
        bha=[comp],
        mud_density_ppg=10.0,
        friction_factor=0.3,
    )
    assert result.success
    assert result.values["total_buoyed_weight"] == pytest.approx(165.23, abs=0.1)


def test_selected_reference_matches_stored_canonical_exactly(repo):
    seed = _spec(**{"ID (in)": 4.276, "Grade": "S-135", "Connection": "NC50"})
    repo.upsert(seed)
    stored = repo.get_spec(seed)
    assert stored is not None
    fields = reference_component_fields(next(iter(build_reference_choices(repo.all()).values())))
    assert fields["od"] == stored.nominal_od_in
    assert fields["id"] == stored.nominal_id_in
    assert fields["weight"] == stored.nominal_weight_ppf
    assert fields["grade"] == stored.grade
    assert fields["connection"] == stored.connection
