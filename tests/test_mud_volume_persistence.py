"""Qt-free tests for Mud Volume balance calculation persistence + reproducibility.

DrillMaster's SIXTH persistent engineering calculation. Mirrors the
T&D/Casing/Cement/Kill-Sheet/MSE coverage against a different engine and a flat
eight-input balance result: snapshot round-trip and input completeness,
repository CRUD across a real persistence boundary, historical reproducibility,
whole-result verification (with a deliberately corrupted stored field so a false
MATCH is impossible), corruption/failure states, historical-row immutability,
determinism, and an INDEPENDENTLY computed balance ground truth (never copied
from the engine output).
"""
from __future__ import annotations

import inspect
import json

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
from core.engineering.engines.mud_volume import MudVolumeEngine  # noqa: E402
from core.engineering.mud_volume_persistence import (  # noqa: E402
    _ENGINE_PARAMS,
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    result_summary,
    snapshot_to_engine_args,
)
from core.repositories.mud_volume_repository import (  # noqa: E402
    MudVolumeCalculationRepository,
    SavedMudVolumeCalculation,
)

INPUTS = dict(
    active_volume_bbl=800.0,
    additions_bbl=50.0,
    losses_bbl=20.0,
    transfers_in_bbl=10.0,
    transfers_out_bbl=5.0,
    returns_bbl=15.0,
    dilution_bbl=8.0,
    dumped_bbl=3.0,
)


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
    return MudVolumeCalculationRepository(db)


# --------------------------------------------------------------------------
# Engine signature <-> snapshot contract.
# --------------------------------------------------------------------------
def test_snapshot_params_match_engine_signature():
    sig = inspect.signature(MudVolumeEngine.balance)
    engine_kwargs = [p for p in sig.parameters if p != "cls"]
    assert set(_ENGINE_PARAMS) == set(engine_kwargs)


# --------------------------------------------------------------------------
# Independent numerical ground truth (computed by hand, not from the engine).
# --------------------------------------------------------------------------
def test_independent_balance_ground_truth():
    expected_final = (INPUTS["active_volume_bbl"] + INPUTS["additions_bbl"]
                      + INPUTS["transfers_in_bbl"] + INPUTS["returns_bbl"]
                      + INPUTS["dilution_bbl"] - INPUTS["losses_bbl"]
                      - INPUTS["transfers_out_bbl"] - INPUTS["dumped_bbl"])
    r = MudVolumeEngine.balance(**INPUTS)
    assert r.success, r.error
    assert r.values["final_volume_bbl"] == pytest.approx(expected_final, abs=1e-9)
    assert r.values["net_change_bbl"] == pytest.approx(
        expected_final - INPUTS["active_volume_bbl"], abs=1e-9)


# --------------------------------------------------------------------------
# Snapshot round-trip.
# --------------------------------------------------------------------------
def test_snapshot_roundtrip_reconstructs_inputs():
    snap = build_snapshot(inputs=INPUTS, method=MudVolumeEngine.METHOD)
    assert snap["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snap["method"] == MudVolumeEngine.METHOD
    snap2 = json.loads(json.dumps(snap))
    args = snapshot_to_engine_args(snap2)
    assert args == INPUTS
    r = recalculate_from_snapshot(snap2)
    assert r.success
    assert r.values["final_volume_bbl"] == MudVolumeEngine.balance(**INPUTS).values["final_volume_bbl"]


def test_old_partial_snapshot_defaults_optionals_to_zero():
    # An older snapshot with only the required field must reconstruct exactly
    # (the seven optional terms default to 0.0, matching the engine contract).
    snap = {"schema_version": 1, "method": MudVolumeEngine.METHOD,
            "parameters": {"active_volume_bbl": 500.0}}
    args = snapshot_to_engine_args(snap)
    assert args["active_volume_bbl"] == 500.0
    assert all(args[k] == 0.0 for k in _ENGINE_PARAMS if k != "active_volume_bbl")
    r = recalculate_from_snapshot(snap)
    assert r.success
    assert r.values["final_volume_bbl"] == 500.0


def test_clean_number_rejects_bool_and_nonfinite():
    bad = dict(INPUTS)
    bad["active_volume_bbl"] = True
    bad["additions_bbl"] = float("inf")
    snap = build_snapshot(inputs=bad, method=MudVolumeEngine.METHOD)
    assert snap["parameters"]["active_volume_bbl"] is None
    assert snap["parameters"]["additions_bbl"] is None


# --------------------------------------------------------------------------
# Repository CRUD.
# --------------------------------------------------------------------------
def test_save_and_reload(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values,
                        method=MudVolumeEngine.METHOD, label="unit")
    assert isinstance(cid, int)
    assert repo.count() == 1
    saved = repo.get(cid)
    assert isinstance(saved, SavedMudVolumeCalculation)
    assert saved.method == MudVolumeEngine.METHOD
    assert saved.summary["final_volume_bbl"] == r.values["final_volume_bbl"]
    assert saved.input_parameters == INPUTS


def test_each_save_is_a_distinct_run(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    a = repo.save_run(inputs=INPUTS, result_values=r.values, method=MudVolumeEngine.METHOD)
    b = repo.save_run(inputs=INPUTS, result_values=r.values, method=MudVolumeEngine.METHOD)
    assert a != b
    assert repo.count() == 2


def test_all_is_deterministically_ordered(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    ids = [repo.save_run(inputs=INPUTS, result_values=r.values,
                         method=MudVolumeEngine.METHOD) for _ in range(3)]
    got = [s.id for s in repo.all()]
    assert got == sorted(ids, reverse=True)


# --------------------------------------------------------------------------
# Whole-result verification.
# --------------------------------------------------------------------------
def test_verify_match(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MudVolumeEngine.METHOD)
    outcome = repo.get(cid).verify(current_method=MudVolumeEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches is True
    assert outcome.all_differences == []


def test_verify_detects_tampered_secondary_field(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    tampered = dict(r.values)
    tampered["net_change_bbl"] = tampered["net_change_bbl"] + 10.0
    cid = repo.save_run(inputs=INPUTS, result_values=tampered, method=MudVolumeEngine.METHOD)
    outcome = repo.get(cid).verify(current_method=MudVolumeEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    paths = {d["path"] for d in outcome.all_differences}
    assert "net_change_bbl" in paths


def test_verify_method_drift_flag(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MudVolumeEngine.METHOD)
    outcome = repo.get(cid).verify(current_method="Some Other Method v2")
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches is False


def test_verify_not_reproducible_on_missing_required_input(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MudVolumeEngine.METHOD)
    saved = repo.get(cid)
    # Drop the required field → engine returns missing() → NOT_REPRODUCIBLE.
    saved.input_snapshot["parameters"]["active_volume_bbl"] = None
    outcome = saved.verify(current_method=MudVolumeEngine.METHOD)
    assert outcome.status == VERIFY_NOT_REPRODUCIBLE


def test_verify_unreadable_when_no_stored_result(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MudVolumeEngine.METHOD)
    saved = repo.get(cid)
    saved.result = {}
    outcome = saved.verify(current_method=MudVolumeEngine.METHOD)
    assert outcome.status == VERIFY_UNREADABLE


# --------------------------------------------------------------------------
# Historical-row immutability + reference independence.
# --------------------------------------------------------------------------
def test_verify_does_not_mutate_stored_row(repo):
    r = MudVolumeEngine.balance(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r.values, method=MudVolumeEngine.METHOD)
    before = json.dumps(repo.get(cid).result, sort_keys=True)
    for _ in range(3):
        repo.get(cid).verify(current_method=MudVolumeEngine.METHOD)
    after = json.dumps(repo.get(cid).result, sort_keys=True)
    assert before == after


def test_saved_run_is_independent_of_later_inputs(repo):
    r1 = MudVolumeEngine.balance(**INPUTS)
    cid = repo.save_run(inputs=INPUTS, result_values=r1.values, method=MudVolumeEngine.METHOD)
    stored_final = repo.get(cid).summary["final_volume_bbl"]

    other = dict(INPUTS, active_volume_bbl=2000.0, losses_bbl=500.0)
    r2 = MudVolumeEngine.balance(**other)
    assert r2.values["final_volume_bbl"] != stored_final

    outcome = repo.get(cid).verify(current_method=MudVolumeEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert repo.get(cid).summary["final_volume_bbl"] == stored_final


# --------------------------------------------------------------------------
# Determinism + immutability.
# --------------------------------------------------------------------------
def test_determinism_repeated_and_serialized():
    v1 = MudVolumeEngine.balance(**INPUTS).values["final_volume_bbl"]
    MudVolumeEngine.balance(active_volume_bbl=1.0)  # unrelated call
    v2 = MudVolumeEngine.balance(**INPUTS).values["final_volume_bbl"]
    snap = json.loads(json.dumps(build_snapshot(inputs=INPUTS, method=MudVolumeEngine.METHOD)))
    v3 = recalculate_from_snapshot(snap).values["final_volume_bbl"]
    assert v1 == v2 == v3


def test_engine_does_not_mutate_input_mapping():
    original = dict(INPUTS)
    MudVolumeEngine.balance(**INPUTS)
    assert INPUTS == original


def test_result_summary_only_headline_keys():
    r = MudVolumeEngine.balance(**INPUTS)
    summary = result_summary(r.values)
    assert set(summary) == {"active_volume_bbl", "final_volume_bbl", "net_change_bbl"}
