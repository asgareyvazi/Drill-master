"""Qt-free tests for Cement job-volume calculation persistence + reproducibility.

DrillMaster's THIRD persistent engineering calculation. Mirrors the T&D/Casing
coverage against a different engine/input class AND a richer result shape (nested
lead/tail legs + a stacked_hydrostatic layer list): snapshot round-trip and input
completeness, repository CRUD across a real persistence boundary, historical
reproducibility, whole-result verification (including nested/list drift),
corruption states, historical-row immutability, determinism, and an
engine-executed ground truth (never hard-coded).
"""
from __future__ import annotations

import inspect
import json

import pytest

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core.database import Base, CementCalculationRecord, DatabaseManager  # noqa: E402
from core.engineering.calculation_verification import (  # noqa: E402
    VERIFY_DIFFERENT,
    VERIFY_MATCH,
    VERIFY_NOT_REPRODUCIBLE,
    VERIFY_UNREADABLE,
)
from core.engineering.engines.cement import CementEngine  # noqa: E402
from core.engineering.cement_persistence import (  # noqa: E402
    _ENGINE_PARAMS,
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    snapshot_to_engine_args,
)
from core.repositories.cement_repository import (  # noqa: E402
    CementCalculationRepository,
)

INPUTS = dict(
    hole_size_in=12.25, casing_od_in=9.625, open_hole_length_ft=2000.0,
    excess_pct=30.0, casing_id_in=8.681, shoe_track_ft=80.0,
    slurry_density_ppg=15.8, yield_ft3_sk=1.15,
    mud_tvd_ft=1000.0, mud_density_ppg=9.5,
    spacer_tvd_ft=500.0, spacer_density_ppg=10.5, spacer_length_ft=500.0,
    lead_tvd_ft=1500.0, lead_density_ppg=13.5, lead_length_ft=1500.0,
    tail_tvd_ft=500.0, tail_density_ppg=15.8, tail_length_ft=500.0,
    shoe_tvd_ft=8000.0, pump_rate_bbl_min=8.0,
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
    return CementEngine.job_volumes(**INPUTS)


def _save(repo, inputs=None, label="run"):
    ins = inputs or INPUTS
    r = CementEngine.job_volumes(**ins)
    cid = repo.save_run(inputs=ins, result_values=r.values,
                        method=CementEngine.METHOD, label=label)
    return cid, r


# --------------------------------------------------------------------------
# Input contract completeness — no engine input silently omitted
# --------------------------------------------------------------------------
def test_snapshot_params_exactly_match_engine_signature():
    sig = set(inspect.signature(CementEngine.job_volumes).parameters) - {"cls"}
    persisted = set(_ENGINE_PARAMS)
    assert persisted <= sig                     # nothing persisted the engine ignores
    assert sig - persisted == set()             # nothing the engine needs is dropped


def test_snapshot_is_json_serializable_and_versioned():
    snap = build_snapshot(inputs=INPUTS, method=CementEngine.METHOD)
    back = json.loads(json.dumps(snap))
    assert back["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert back["method"] == CementEngine.METHOD
    assert back["parameters"]["hole_size_in"] == 12.25
    assert back["parameters"]["excess_pct"] == 30.0


def test_snapshot_preserves_units_without_conversion():
    snap = build_snapshot(inputs=INPUTS, method=CementEngine.METHOD)
    p = snap["parameters"]
    assert p["hole_size_in"] == 12.25 and p["casing_od_in"] == 9.625  # inches
    assert p["open_hole_length_ft"] == 2000.0                          # ft
    assert p["slurry_density_ppg"] == 15.8                             # ppg


def test_snapshot_preserves_optional_none():
    ins = dict(hole_size_in=12.25, casing_od_in=9.625,
               open_hole_length_ft=2000.0, excess_pct=30.0)  # minimal
    snap = build_snapshot(inputs=ins, method=CementEngine.METHOD)
    args = snapshot_to_engine_args(snap)
    assert args["slurry_density_ppg"] is None
    assert args["yield_ft3_sk"] is None
    assert recalculate_from_snapshot(snap).success


def test_recalculate_from_snapshot_matches_direct_engine():
    direct = _direct()
    snap = build_snapshot(inputs=INPUTS, method=CementEngine.METHOD)
    recalc = recalculate_from_snapshot(json.loads(json.dumps(snap)))
    assert recalc.success
    assert recalc.values["slurry_volume_bbl"] == direct.values["slurry_volume_bbl"]
    assert recalc.values["total_pump_bbl"] == direct.values["total_pump_bbl"]
    # nested structures reproduce too
    assert recalc.values["lead"] == direct.values["lead"]
    assert recalc.values["stacked_hydrostatic"] == direct.values["stacked_hydrostatic"]


# --------------------------------------------------------------------------
# Ground truth (engine-executed, not hard-coded)
# --------------------------------------------------------------------------
def test_ground_truth_annulus_capacity():
    # Independent hand value: annulus bbl/ft = (Dh² − OD²)/1029.4, × length,
    # × (1 + excess). No shoe track effect on the annulus-with-excess figure.
    dh, od, L, ex = 12.25, 9.625, 2000.0, 30.0
    expected = (dh * dh - od * od) / 1029.4 * L * (1 + ex / 100.0)
    r = _direct()
    assert r.success
    assert r.values["annular_with_excess_bbl"] == pytest.approx(expected, abs=0.02)


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
def test_engine_deterministic_and_no_input_mutation():
    before = dict(INPUTS)
    snap = build_snapshot(inputs=INPUTS, method=CementEngine.METHOD)
    first = json.dumps(recalculate_from_snapshot(snap).values, sort_keys=True,
                       default=str)
    for _ in range(5):
        CementEngine.job_volumes(hole_size_in=17.5, casing_od_in=13.375,
                                 open_hole_length_ft=1000, excess_pct=50)
    second = json.dumps(recalculate_from_snapshot(snap).values, sort_keys=True,
                        default=str)
    assert first == second
    assert INPUTS == before


# --------------------------------------------------------------------------
# Repository CRUD + reproducibility across the persistence boundary
# --------------------------------------------------------------------------
def test_save_reload_reconstruct_recalculate():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    cid, direct = _save(repo, label="gt")
    assert isinstance(cid, int) and repo.count() == 1

    saved = repo.get(cid)
    assert saved.label == "gt"
    assert saved.method == CementEngine.METHOD
    assert saved.summary["slurry_volume_bbl"] == pytest.approx(
        direct.values["slurry_volume_bbl"], abs=0.01)

    recalc = saved.recalculate()   # crosses persistence boundary
    assert recalc.values["slurry_volume_bbl"] == direct.values["slurry_volume_bbl"]


def test_each_save_is_distinct_run_not_deduplicated():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    a, _ = _save(repo)
    b, _ = _save(repo)
    assert a != b and repo.count() == 2


def test_all_returns_newest_first():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    first, _ = _save(repo, label="first")
    second, _ = _save(repo, label="second")
    ids = [s.id for s in repo.all()]
    assert ids[0] == second and second > first


def test_promoted_columns_queryable():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    _save(repo)
    with m.session_scope() as session:
        row = session.query(CementCalculationRecord).one()
        assert row.slurry_volume_bbl is not None
        assert row.method == CementEngine.METHOD
        assert row.input_snapshot_json is not None


# --------------------------------------------------------------------------
# Whole-result verification (MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE)
# --------------------------------------------------------------------------
def test_verify_match_on_full_result():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    cid, _ = _save(repo)
    outcome = repo.get(cid).verify(current_method=CementEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert outcome.all_differences == []
    assert outcome.method_matches is True


def test_verify_nested_leg_drift_is_different():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result["lead"]["slurry_bbl"] = 1.0     # nested dict, not a summary col
    outcome = saved.verify(current_method=CementEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any(d["path"] == "lead.slurry_bbl" for d in outcome.all_differences)


def test_verify_stacked_layer_drift_is_different():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result["stacked_hydrostatic"]["layers"][0]["psi"] = 1.0  # list of dicts
    outcome = saved.verify(current_method=CementEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any(d["path"].startswith("stacked_hydrostatic.layers[0]")
               for d in outcome.all_differences)


def test_verify_method_drift_flagged_honestly():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    cid, _ = _save(repo)
    outcome = repo.get(cid).verify(current_method="DIFFERENT ALGORITHM v2")
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches is False


def test_verify_missing_result_is_unreadable():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result = {}
    outcome = saved.verify(current_method=CementEngine.METHOD)
    assert outcome.status == VERIFY_UNREADABLE


def test_verify_broken_snapshot_not_reproducible():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    cid, _ = _save(repo)
    saved = repo.get(cid)
    # hole <= casing OD violates an engine precondition -> engine fails cleanly
    saved.input_snapshot = {"parameters": {"hole_size_in": 5.0,
                                           "casing_od_in": 9.625,
                                           "open_hole_length_ft": 2000.0,
                                           "excess_pct": 30.0},
                            "method": CementEngine.METHOD}
    outcome = saved.verify(current_method=CementEngine.METHOD)
    assert outcome.status == VERIFY_NOT_REPRODUCIBLE
    assert outcome.detail


# --------------------------------------------------------------------------
# Historical-row immutability during verification
# --------------------------------------------------------------------------
def _row_fingerprint(m, cid):
    with m.session_scope() as session:
        row = session.get(CementCalculationRecord, cid)
        return json.dumps({
            "input": row.input_snapshot_json, "result": row.result_json,
            "slurry": row.slurry_volume_bbl, "method": row.method,
            "created_at": str(row.created_at), "updated_at": str(row.updated_at),
        }, sort_keys=True)


def test_verify_and_recalculate_never_mutate_persisted_row():
    m = _mem_db()
    repo = CementCalculationRepository(m)
    cid, _ = _save(repo)
    before = _row_fingerprint(m, cid)
    for _ in range(3):
        saved = repo.get(cid)
        saved.verify(current_method=CementEngine.METHOD)
        saved.recalculate()
        saved.result["slurry_volume_bbl"] = 0.0           # tamper detached copy
        saved.input_snapshot["parameters"]["hole_size_in"] = 1.0
    assert _row_fingerprint(m, cid) == before


# --------------------------------------------------------------------------
# Failure safety: a mid-transaction error leaves no partial row
# --------------------------------------------------------------------------
def test_persistence_failure_leaves_no_partial_row(monkeypatch):
    import contextlib
    m = _mem_db()
    repo = CementCalculationRepository(m)
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
                      method=CementEngine.METHOD)
    monkeypatch.undo()
    assert repo.count() == 0
