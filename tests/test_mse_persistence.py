"""Qt-free tests for MSE (Teale) calculation persistence + reproducibility.

DrillMaster's FIFTH persistent engineering calculation. Mirrors the
T&D/Casing/Cement/Kill-Sheet coverage against a different engine and a flat
scalar-decomposition result: snapshot round-trip and input completeness,
repository CRUD across a real persistence boundary, historical reproducibility,
whole-result verification (including a deliberately corrupted stored field so a
false MATCH is impossible), corruption/failure states, historical-row
immutability, determinism, and an INDEPENDENTLY computed Teale ground truth
(never copied from the engine output).
"""
from __future__ import annotations

import inspect
import json
import math

import pytest

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core.database import Base, DatabaseManager  # noqa: E402
from core.engineering.calculation_verification import (  # noqa: E402
    VERIFY_DIFFERENT,
    VERIFY_MATCH,
    VERIFY_NOT_REPRODUCIBLE,
    VERIFY_UNREADABLE,
)
from core.engineering.engines.mse import MSEEngine, TEALE_120_PI  # noqa: E402
from core.engineering.mse_persistence import (  # noqa: E402
    _ENGINE_PARAMS,
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    result_summary,
    snapshot_to_engine_args,
)
from core.repositories.mse_repository import (  # noqa: E402
    MSECalculationRepository,
    SavedMSECalculation,
)

# Canonical engine units (WOB already in lbf, not klbf).
INPUTS = dict(
    wob_lbf=25000.0,
    rpm=120.0,
    torque_ft_lbf=8000.0,
    rop_ft_hr=30.0,
    bit_diameter_in=8.5,
)


# --------------------------------------------------------------------------
# Fixtures: an isolated in-memory DB with a real DatabaseManager session.
# --------------------------------------------------------------------------
@pytest.fixture()
def db():
    manager = DatabaseManager.__new__(DatabaseManager)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    manager.engine = engine
    manager.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return manager


@pytest.fixture()
def repo(db):
    return MSECalculationRepository(db)


# --------------------------------------------------------------------------
# Engine signature <-> snapshot contract (catches a drifting input set).
# --------------------------------------------------------------------------
def test_snapshot_params_match_engine_signature():
    sig = inspect.signature(MSEEngine.calculate)
    engine_kwargs = [p for p in sig.parameters if p != "cls"]
    assert set(_ENGINE_PARAMS) == set(engine_kwargs)


# --------------------------------------------------------------------------
# Independent numerical ground truth: compute Teale by hand, not from engine.
# --------------------------------------------------------------------------
def test_independent_teale_ground_truth():
    d = INPUTS["bit_diameter_in"]
    ab = math.pi / 4.0 * d * d
    axial = INPUTS["wob_lbf"] / ab
    rotary = (120.0 * math.pi * INPUTS["rpm"] * INPUTS["torque_ft_lbf"]) / (ab * INPUTS["rop_ft_hr"])
    expected = axial + rotary

    r = MSEEngine.calculate(**INPUTS)
    assert r.success, r.error
    # Engine rounds to 1 dp; compare against the independently computed value.
    assert r.values["mse_psi"] == pytest.approx(expected, abs=0.05)
    assert r.values["axial_term_psi"] == pytest.approx(axial, abs=0.05)
    assert r.values["rotary_term_psi"] == pytest.approx(rotary, abs=0.05)
    assert r.values["bit_area_in2"] == pytest.approx(ab, abs=1e-4)
    # The engine must use 120π, NOT the 480 spreadsheet constant.
    assert TEALE_120_PI == pytest.approx(376.99, abs=0.01)


# --------------------------------------------------------------------------
# Snapshot round-trip.
# --------------------------------------------------------------------------
def test_snapshot_roundtrip_reconstructs_inputs():
    snap = build_snapshot(inputs=INPUTS, method=MSEEngine.METHOD)
    assert snap["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snap["method"] == MSEEngine.METHOD
    # JSON-serializable and self-contained.
    snap2 = json.loads(json.dumps(snap))
    args = snapshot_to_engine_args(snap2)
    assert args == INPUTS
    r = recalculate_from_snapshot(snap2)
    assert r.success
    assert r.values["mse_psi"] == MSEEngine.calculate(**INPUTS).values["mse_psi"]


def test_clean_number_rejects_bool_and_nonfinite():
    bad = dict(INPUTS)
    bad["wob_lbf"] = True  # bool must NOT become 1.0
    bad["rpm"] = float("nan")
    snap = build_snapshot(inputs=bad, method=MSEEngine.METHOD)
    assert snap["parameters"]["wob_lbf"] is None
    assert snap["parameters"]["rpm"] is None


# --------------------------------------------------------------------------
# Repository CRUD across a real persistence boundary.
# --------------------------------------------------------------------------
def test_save_and_reload(repo):
    r = MSEEngine.calculate(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values,
                        method=MSEEngine.METHOD, label="unit")
    assert isinstance(cid, int)
    assert repo.count() == 1

    saved = repo.get(cid)
    assert isinstance(saved, SavedMSECalculation)
    assert saved.method == MSEEngine.METHOD
    assert saved.label == "unit"
    assert saved.summary["mse_psi"] == r.values["mse_psi"]
    assert saved.input_parameters == INPUTS


def test_each_save_is_a_distinct_run(repo):
    r = MSEEngine.calculate(**INPUTS)
    a = repo.save_run(inputs=INPUTS, result_values=r.values, method=MSEEngine.METHOD)
    b = repo.save_run(inputs=INPUTS, result_values=r.values, method=MSEEngine.METHOD)
    assert a != b
    assert repo.count() == 2  # identical content is NOT deduplicated


def test_all_is_deterministically_ordered(repo):
    r = MSEEngine.calculate(**INPUTS)
    ids = [repo.save_run(inputs=INPUTS, result_values=r.values,
                         method=MSEEngine.METHOD) for _ in range(3)]
    got = [s.id for s in repo.all()]
    # newest first (created_at desc, id desc) — highest id first here.
    assert got == sorted(ids, reverse=True)


# --------------------------------------------------------------------------
# Whole-result verification.
# --------------------------------------------------------------------------
def test_verify_match(repo):
    r = MSEEngine.calculate(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MSEEngine.METHOD)
    outcome = repo.get(cid).verify(current_method=MSEEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches is True
    assert outcome.all_differences == []


def test_verify_detects_tampered_secondary_field(repo):
    # A false-MATCH guard: corrupt a NON-headline result field and prove the
    # whole-result diff still catches it (mission §20/§57).
    r = MSEEngine.calculate(**INPUTS)
    tampered = dict(r.values)
    tampered["rotary_term_psi"] = tampered["rotary_term_psi"] + 500.0
    cid = repo.save_run(inputs=INPUTS, result_values=tampered, method=MSEEngine.METHOD)
    outcome = repo.get(cid).verify(current_method=MSEEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    paths = {d["path"] for d in outcome.all_differences}
    assert "rotary_term_psi" in paths


def test_verify_method_drift_flag(repo):
    r = MSEEngine.calculate(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MSEEngine.METHOD)
    outcome = repo.get(cid).verify(current_method="Some Other Method v2")
    # Numbers still reproduce, but the method changed → not exact-algo repro.
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches is False


def test_verify_not_reproducible_on_invalid_snapshot(repo):
    # rop=0 makes MSE undefined → engine fails → NOT_REPRODUCIBLE, not MATCH.
    r = MSEEngine.calculate(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MSEEngine.METHOD)
    saved = repo.get(cid)
    # Corrupt the frozen snapshot's rop to an engine-invalid value.
    saved.input_snapshot["parameters"]["rop_ft_hr"] = 0.0
    outcome = saved.verify(current_method=MSEEngine.METHOD)
    assert outcome.status == VERIFY_NOT_REPRODUCIBLE


def test_verify_unreadable_when_no_stored_result(repo):
    r = MSEEngine.calculate(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MSEEngine.METHOD)
    saved = repo.get(cid)
    saved.result = {}  # simulate a record with no stored result
    outcome = saved.verify(current_method=MSEEngine.METHOD)
    assert outcome.status == VERIFY_UNREADABLE


def test_verify_unreadable_on_missing_snapshot_field(repo):
    r = MSEEngine.calculate(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MSEEngine.METHOD)
    saved = repo.get(cid)
    # Missing required input → engine raises MISSING_INPUT during reconstruct.
    del saved.input_snapshot["parameters"]["wob_lbf"]
    outcome = saved.verify(current_method=MSEEngine.METHOD)
    # snapshot_to_engine_args fills missing keys with None → engine returns
    # missing() (success=False) → NOT_REPRODUCIBLE (not a crash/UNREADABLE).
    assert outcome.status == VERIFY_NOT_REPRODUCIBLE


# --------------------------------------------------------------------------
# Historical-row immutability under verification.
# --------------------------------------------------------------------------
def test_verify_does_not_mutate_stored_row(repo):
    r = MSEEngine.calculate(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MSEEngine.METHOD)
    before = json.dumps(repo.get(cid).result, sort_keys=True)
    for _ in range(3):
        repo.get(cid).verify(current_method=MSEEngine.METHOD)
    after = json.dumps(repo.get(cid).result, sort_keys=True)
    assert before == after


# --------------------------------------------------------------------------
# Reference independence: a saved run must NOT depend on current widget/UI
# state. We change the "current" inputs and prove the old run is unchanged.
# --------------------------------------------------------------------------
def test_saved_run_is_independent_of_later_inputs(repo):
    r1 = MSEEngine.calculate(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r1.values, method=MSEEngine.METHOD)
    stored_mse = repo.get(cid).summary["mse_psi"]

    # A completely different "current" run happens later.
    other = dict(INPUTS, wob_lbf=60000.0, rop_ft_hr=10.0)
    r2 = MSEEngine.calculate(**other)
    assert r2.values["mse_psi"] != stored_mse

    # The historical run still recomputes to its original value.
    outcome = repo.get(cid).verify(current_method=MSEEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert repo.get(cid).summary["mse_psi"] == stored_mse


# --------------------------------------------------------------------------
# Determinism (same-process, interleaved, serialization round trip).
# --------------------------------------------------------------------------
def test_determinism_repeated_and_serialized():
    v1 = MSEEngine.calculate(**INPUTS).values["mse_psi"]
    # An unrelated calculation runs in between.
    MSEEngine.calculate(wob_lbf=1000.0, rpm=50.0, torque_ft_lbf=2000.0,
                        rop_ft_hr=5.0, bit_diameter_in=6.0)
    v2 = MSEEngine.calculate(**INPUTS).values["mse_psi"]
    snap = json.loads(json.dumps(build_snapshot(inputs=INPUTS, method=MSEEngine.METHOD)))
    v3 = recalculate_from_snapshot(snap).values["mse_psi"]
    assert v1 == v2 == v3


def test_engine_does_not_mutate_input_mapping():
    original = dict(INPUTS)
    MSEEngine.calculate(**INPUTS)
    assert INPUTS == original


def test_result_summary_only_headline_keys():
    r = MSEEngine.calculate(**INPUTS)
    summary = result_summary(r.values)
    assert set(summary) == {"mse_psi", "axial_term_psi", "rotary_term_psi", "bit_area_in2"}
