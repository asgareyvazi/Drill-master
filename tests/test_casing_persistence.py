"""Qt-free tests for Casing-strength calculation persistence + reproducibility.

DrillMaster's second persistent engineering calculation. Mirrors the T&D test
coverage against a different engine/input class: snapshot round-trip and input
completeness, repository CRUD across a real persistence boundary, historical
reproducibility, whole-result verification, corruption states, historical-row
immutability, determinism, and an engine-executed ground truth (never
hard-coded).
"""
from __future__ import annotations

import inspect
import json

import pytest

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core.database import Base, CasingCalculationRecord, DatabaseManager  # noqa: E402
from core.engineering.calculation_verification import (  # noqa: E402
    VERIFY_DIFFERENT,
    VERIFY_MATCH,
    VERIFY_NOT_REPRODUCIBLE,
    VERIFY_UNREADABLE,
)
from core.engineering.engines.casing import CasingEngine  # noqa: E402
from core.engineering.casing_persistence import (  # noqa: E402
    _ENGINE_PARAMS,
    _ENGINE_TEXT_PARAMS,
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    snapshot_to_engine_args,
)
from core.repositories.casing_repository import (  # noqa: E402
    CasingCalculationRepository,
)

INPUTS = dict(
    od_in=9.625, id_in=8.681, wall_in=0.472, yield_psi=80000.0,
    internal_pressure_psi=8000.0, external_pressure_psi=6000.0,
    axial_tension_lbf=200000.0, grade="N-80", weight_ppf=47.0,
)


def _mem_db():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    return m


def _direct():
    return CasingEngine.evaluate(**INPUTS)


def _save(repo, inputs=None, label="run"):
    ins = inputs or INPUTS
    r = CasingEngine.evaluate(**ins)
    cid = repo.save_run(inputs=ins, result_values=r.values,
                        method=CasingEngine.METHOD, label=label)
    return cid, r


# --------------------------------------------------------------------------
# Input contract completeness (mission §16) — no engine input silently omitted
# --------------------------------------------------------------------------
def test_snapshot_params_exactly_match_engine_signature():
    sig = set(inspect.signature(CasingEngine.evaluate).parameters) - {"cls"}
    persisted = set(_ENGINE_PARAMS) | set(_ENGINE_TEXT_PARAMS)
    assert persisted <= sig                     # nothing persisted the engine ignores
    assert sig - persisted == set()             # nothing the engine needs is dropped


def test_snapshot_is_json_serializable_and_versioned():
    snap = build_snapshot(inputs=INPUTS, method=CasingEngine.METHOD)
    back = json.loads(json.dumps(snap))
    assert back["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert back["method"] == CasingEngine.METHOD
    assert back["parameters"]["od_in"] == 9.625
    assert back["parameters"]["yield_psi"] == 80000.0


def test_snapshot_preserves_units_without_conversion():
    snap = build_snapshot(inputs=INPUTS, method=CasingEngine.METHOD)
    p = snap["parameters"]
    assert p["od_in"] == 9.625 and p["wall_in"] == 0.472  # inches, exact
    assert p["yield_psi"] == 80000.0                       # psi, exact
    assert p["axial_tension_lbf"] == 200000.0              # lbf, exact


def test_snapshot_preserves_optional_none_loads():
    ins = dict(od_in=9.625, id_in=8.681, yield_psi=80000.0)  # no loads
    snap = build_snapshot(inputs=ins, method=CasingEngine.METHOD)
    args = snapshot_to_engine_args(snap)
    assert args["internal_pressure_psi"] is None
    assert args["axial_tension_lbf"] is None
    # reconstructs a valid engine call
    assert recalculate_from_snapshot(snap).success


def test_recalculate_from_snapshot_matches_direct_engine():
    direct = _direct()
    snap = build_snapshot(inputs=INPUTS, method=CasingEngine.METHOD)
    recalc = recalculate_from_snapshot(json.loads(json.dumps(snap)))
    assert recalc.success
    assert recalc.values["burst_rating_psi"] == direct.values["burst_rating_psi"]
    assert recalc.values["vme_psi"] == direct.values["vme_psi"]


# --------------------------------------------------------------------------
# Ground truth (engine-executed, not hard-coded)
# --------------------------------------------------------------------------
def test_ground_truth_burst_barlow():
    # Independent hand value: P_burst = 0.875 * 2 * Yp * t / OD.
    expected = 0.875 * 2 * 80000.0 * 0.472 / 9.625
    r = _direct()
    assert r.success
    assert r.values["burst_rating_psi"] == pytest.approx(expected, abs=0.05)


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
def test_engine_deterministic_and_no_input_mutation():
    before = dict(INPUTS)
    snap = build_snapshot(inputs=INPUTS, method=CasingEngine.METHOD)
    first = json.dumps(recalculate_from_snapshot(snap).values, sort_keys=True,
                       default=str)
    for _ in range(5):
        CasingEngine.evaluate(od_in=13.375, id_in=12.0, yield_psi=95000.0)
    second = json.dumps(recalculate_from_snapshot(snap).values, sort_keys=True,
                        default=str)
    assert first == second
    assert INPUTS == before


# --------------------------------------------------------------------------
# Repository CRUD + reproducibility across the persistence boundary
# --------------------------------------------------------------------------
def test_save_reload_reconstruct_recalculate():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    cid, direct = _save(repo, label="gt")
    assert isinstance(cid, int) and repo.count() == 1

    saved = repo.get(cid)
    assert saved.label == "gt"
    assert saved.method == CasingEngine.METHOD
    assert saved.summary["burst_rating_psi"] == pytest.approx(
        direct.values["burst_rating_psi"], abs=0.05)

    recalc = saved.recalculate()   # crosses persistence boundary
    assert recalc.values["burst_rating_psi"] == direct.values["burst_rating_psi"]


def test_each_save_is_distinct_run_not_deduplicated():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    a, _ = _save(repo)
    b, _ = _save(repo)
    assert a != b and repo.count() == 2


def test_all_returns_newest_first():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    first, _ = _save(repo, label="first")
    second, _ = _save(repo, label="second")
    ids = [s.id for s in repo.all()]
    assert ids[0] == second and second > first


def test_promoted_columns_queryable():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    _save(repo)
    with m.session_scope() as session:
        row = session.query(CasingCalculationRecord).one()
        assert row.burst_rating_psi is not None
        assert row.method == CasingEngine.METHOD
        assert row.input_snapshot_json is not None


# --------------------------------------------------------------------------
# Whole-result verification (MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE)
# --------------------------------------------------------------------------
def test_verify_match_on_full_result():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    cid, _ = _save(repo)
    outcome = repo.get(cid).verify(current_method=CasingEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert outcome.all_differences == []
    assert outcome.method_matches is True


def test_verify_non_summary_field_drift_is_different():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result["vme_psi"] = 1.0          # not a promoted summary column
    outcome = saved.verify(current_method=CasingEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any(d["path"] == "vme_psi" for d in outcome.all_differences)


def test_verify_method_drift_flagged_honestly():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    cid, _ = _save(repo)
    outcome = repo.get(cid).verify(current_method="DIFFERENT ALGORITHM v2")
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches is False


def test_verify_missing_result_is_unreadable():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result = {}
    outcome = saved.verify(current_method=CasingEngine.METHOD)
    assert outcome.status == VERIFY_UNREADABLE


def test_verify_broken_snapshot_not_reproducible():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.input_snapshot = {"parameters": {"od_in": 9.625},  # no yield -> engine fails
                            "method": CasingEngine.METHOD}
    outcome = saved.verify(current_method=CasingEngine.METHOD)
    assert outcome.status == VERIFY_NOT_REPRODUCIBLE
    assert outcome.detail


# --------------------------------------------------------------------------
# Historical-row immutability during verification (mission §21)
# --------------------------------------------------------------------------
def _row_fingerprint(m, cid):
    with m.session_scope() as session:
        row = session.get(CasingCalculationRecord, cid)
        return json.dumps({
            "input": row.input_snapshot_json, "result": row.result_json,
            "burst": row.burst_rating_psi, "method": row.method,
            "created_at": str(row.created_at), "updated_at": str(row.updated_at),
        }, sort_keys=True)


def test_verify_and_recalculate_never_mutate_persisted_row():
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    cid, _ = _save(repo)
    before = _row_fingerprint(m, cid)
    for _ in range(3):
        saved = repo.get(cid)
        saved.verify(current_method=CasingEngine.METHOD)
        saved.recalculate()
        saved.result["burst_rating_psi"] = 0.0            # tamper detached copy
        saved.input_snapshot["parameters"]["od_in"] = 1.0
    assert _row_fingerprint(m, cid) == before


# --------------------------------------------------------------------------
# Failure safety: a mid-transaction error leaves no partial row
# --------------------------------------------------------------------------
def test_persistence_failure_leaves_no_partial_row(monkeypatch):
    import contextlib
    m = _mem_db()
    repo = CasingCalculationRepository(m)
    direct = _direct()
    real_scope = m.session_scope

    class Boom(RuntimeError):
        pass

    @contextlib.contextmanager
    def exploding_scope():
        with real_scope() as session:
            yield session
            raise Boom("commit boom")

    monkeypatch.setattr(m, "session_scope", exploding_scope)
    with pytest.raises(Boom):
        repo.save_run(inputs=INPUTS, result_values=direct.values,
                      method=CasingEngine.METHOD)
    monkeypatch.undo()
    assert repo.count() == 0
