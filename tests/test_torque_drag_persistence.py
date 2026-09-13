"""Qt-free tests for Torque & Drag calculation persistence + reproducibility.

Covers the mission testing matrix without constructing any Qt widget:
domain snapshot / round-trip / reconstruction, repository CRUD across a real
persistence boundary, historical reproducibility, reference-mutation isolation,
engineering ground truth, and failure paths.

All engineering values are synthetic test fixtures (ACME / a documented API 5DP
5" 19.5# case), and the ground-truth number is produced by executing the REAL
engine, never hard-coded into the computation.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

pytest.importorskip("openpyxl")

from openpyxl import Workbook  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core.database import Base, DatabaseManager, TorqueDragCalculationRecord  # noqa: E402
from core.engineering.drill_pipe_import import import_workbook  # noqa: E402
from core.engineering.engines.torque_drag import TorqueDragEngine  # noqa: E402
from core.engineering.torque_drag_persistence import (  # noqa: E402
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    reference_fingerprints,
    snapshot_to_engine_args,
)
from core.repositories.drill_pipe_reference_repository import (  # noqa: E402
    DrillPipeReferenceRepository,
)
from core.repositories.torque_drag_repository import (  # noqa: E402
    TorqueDragCalculationRepository,
)

SURVEY = [{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}]
GT_COMPONENT = {
    "type": "Drill Pipe", "od": 5.0, "id": 4.276, "length": 3048.0,
    "weight": 19.5, "grade": "S-135", "connection": "NC50",
}


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


def _ground_truth_klbf():
    r = TorqueDragEngine.calculate(SURVEY, [GT_COMPONENT],
                                   mud_density_ppg=10.0, friction_factor=0.3)
    return r


# --------------------------------------------------------------------------
# A. Domain: snapshot / serialization / reconstruction
# --------------------------------------------------------------------------
def test_snapshot_is_json_serializable_and_versioned():
    snap = build_snapshot(survey=SURVEY, components=[GT_COMPONENT],
                          mud_density_ppg=10.0, friction_factor=0.3,
                          method=TorqueDragEngine.METHOD)
    blob = json.dumps(snap)  # must not raise
    back = json.loads(blob)
    assert back["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert back["method"] == TorqueDragEngine.METHOD
    assert len(back["components"]) == 1
    assert back["parameters"]["friction_factor"] == 0.3


def test_snapshot_freezes_ppf_and_diameters_without_conversion():
    snap = build_snapshot(survey=SURVEY, components=[GT_COMPONENT],
                          mud_density_ppg=10.0, friction_factor=0.3,
                          method=TorqueDragEngine.METHOD)
    comp = snap["components"][0]
    assert comp["weight"] == 19.5    # ppf preserved exactly, no mass conversion
    assert comp["od"] == 5.0
    assert comp["id"] == 4.276


def test_reconstruct_engine_args_strips_non_engine_metadata():
    comp = dict(GT_COMPONENT, reference_fingerprint="fp-123")
    snap = build_snapshot(survey=SURVEY, components=[comp],
                          mud_density_ppg=10.0, friction_factor=0.3,
                          method=TorqueDragEngine.METHOD)
    args = snapshot_to_engine_args(snap)
    assert "reference_fingerprint" not in args["bha"][0]
    assert args["mud_density_ppg"] == 10.0
    assert reference_fingerprints(snap) == ["fp-123"]


def test_recalculate_from_snapshot_matches_direct_engine():
    direct = _ground_truth_klbf()
    snap = build_snapshot(survey=SURVEY, components=[GT_COMPONENT],
                          mud_density_ppg=10.0, friction_factor=0.3,
                          method=TorqueDragEngine.METHOD)
    recalc = recalculate_from_snapshot(json.loads(json.dumps(snap)))
    assert recalc.success
    assert (recalc.values["total_buoyed_weight"]
            == direct.values["total_buoyed_weight"])


def test_engine_is_deterministic_and_does_not_mutate_inputs():
    # Same snapshot recomputed repeatedly (with unrelated calcs interleaved)
    # must give a byte-identical numeric result, and the engine must not mutate
    # the caller's input structures — both are prerequisites for reproducibility.
    survey = [{"md": 0, "inc": 0, "azi": 0}, {"md": 1500, "inc": 30, "azi": 45},
              {"md": 3048.0, "inc": 60, "azi": 90}]
    comp = {"type": "DP", "od": 5.0, "id": 4.276, "length": 3048.0,
            "weight": 19.5}
    snap = build_snapshot(survey=survey, components=[comp], mud_density_ppg=10.0,
                          friction_factor=0.3, wob_klbf=5.0, wellbore_id_in=8.5,
                          method=TorqueDragEngine.METHOD)
    frozen = json.dumps(snap, sort_keys=True)

    first = json.dumps(recalculate_from_snapshot(snap).values,
                       sort_keys=True, default=str)
    for _ in range(5):  # unrelated calculations between the two runs
        TorqueDragEngine.calculate(survey, [dict(comp, weight=25.6)],
                                   mud_density_ppg=12.0, friction_factor=0.4)
    second = json.dumps(recalculate_from_snapshot(snap).values,
                        sort_keys=True, default=str)

    assert first == second                    # deterministic
    assert json.dumps(snap, sort_keys=True) == frozen  # snapshot not mutated


# --------------------------------------------------------------------------
# F. Engineering ground truth (engine-executed, not hard-coded)
# --------------------------------------------------------------------------
def test_ground_truth_5in_19_5ppf():
    r = _ground_truth_klbf()
    assert r.success
    assert r.values["total_buoyed_weight"] == pytest.approx(165.23, abs=0.01)


# --------------------------------------------------------------------------
# B/D. Repository: save -> reload -> reconstruct -> recalculate
# --------------------------------------------------------------------------
def test_save_reload_reconstruct_recalculate():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    direct = _ground_truth_klbf()
    cid = repo.save_run(
        survey=SURVEY, components=[GT_COMPONENT], mud_density_ppg=10.0,
        friction_factor=0.3, result_values=direct.values,
        method=TorqueDragEngine.METHOD, label="gt",
    )
    assert isinstance(cid, int) and repo.count() == 1

    saved = repo.get(cid)
    assert saved is not None
    assert saved.label == "gt"
    assert saved.method == TorqueDragEngine.METHOD
    assert saved.summary["total_buoyed_weight"] == pytest.approx(165.23, abs=0.01)

    recalc = saved.recalculate()  # crosses persistence boundary
    assert recalc.values["total_buoyed_weight"] == direct.values["total_buoyed_weight"]


def test_each_save_is_a_distinct_run_not_deduplicated():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    direct = _ground_truth_klbf()
    kw = dict(survey=SURVEY, components=[GT_COMPONENT], mud_density_ppg=10.0,
              friction_factor=0.3, result_values=direct.values,
              method=TorqueDragEngine.METHOD)
    a = repo.save_run(**kw)
    b = repo.save_run(**kw)
    assert a != b
    assert repo.count() == 2


def test_all_returns_newest_first():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    direct = _ground_truth_klbf()
    kw = dict(survey=SURVEY, components=[GT_COMPONENT], mud_density_ppg=10.0,
              friction_factor=0.3, result_values=direct.values,
              method=TorqueDragEngine.METHOD)
    first = repo.save_run(label="first", **kw)
    second = repo.save_run(label="second", **kw)
    ids = [s.id for s in repo.all()]
    assert ids[0] == second and second > first


# --------------------------------------------------------------------------
# E. Reference mutation isolation
# --------------------------------------------------------------------------
def _seed_catalog(m):
    ref = DrillPipeReferenceRepository(m)
    wb = Workbook()
    ws = wb.active
    ws.title = "Aa"
    ws.append(["Manufacturer", "Product", "OD (in)", "ID (in)",
               "Weight (ppf)", "Grade", "Connection"])
    ws.append(["ACME", "5DP", "5.000", "4.276", "19.5", "S-135", "NC50"])
    p = tempfile.mktemp(suffix=".xlsx")
    wb.save(p)
    try:
        import_workbook(ref, p, sheet="Aa")
    finally:
        os.remove(p)
    return ref


def test_history_survives_catalog_enrichment():
    m = _mem_db()
    ref = _seed_catalog(m)
    repo = TorqueDragCalculationRepository(m)
    spec = ref.all()[0]
    comp = dict(GT_COMPONENT, reference_fingerprint=spec.identity_fingerprint())
    direct = TorqueDragEngine.calculate(SURVEY, [comp],
                                        mud_density_ppg=10.0, friction_factor=0.3)
    cid = repo.save_run(survey=SURVEY, components=[comp], mud_density_ppg=10.0,
                        friction_factor=0.3, result_values=direct.values,
                        method=TorqueDragEngine.METHOD)

    # Legitimate enrichment of the master reference (adds a previously-missing
    # tool-joint OD; same identity) — a supported, non-conflicting mutation.
    wb = Workbook()
    ws = wb.active
    ws.title = "Aa"
    ws.append(["Manufacturer", "Product", "OD (in)", "ID (in)", "Weight (ppf)",
               "Grade", "Connection", "Tool Joint OD"])
    ws.append(["ACME", "5DP", "5.000", "4.276", "19.5", "S-135", "NC50", "6.625"])
    p = tempfile.mktemp(suffix=".xlsx")
    wb.save(p)
    try:
        summary = import_workbook(ref, p, sheet="Aa")
    finally:
        os.remove(p)
    assert summary.as_dict()["enriched"] == 1  # master reference DID change

    # Historical run must be unchanged and still reproduce the original result.
    saved = repo.get(cid)
    assert saved.reference_fingerprints == [spec.identity_fingerprint()]
    assert saved.input_snapshot["components"][0]["id"] == 4.276
    recalc = saved.recalculate()
    assert recalc.values["total_buoyed_weight"] == direct.values["total_buoyed_weight"]


# --------------------------------------------------------------------------
# G. Failure paths
# --------------------------------------------------------------------------
def test_invalid_snapshot_yields_failed_result_not_crash():
    bad = build_snapshot(survey=[], components=[],
                         mud_density_ppg=10.0, friction_factor=0.3,
                         method=TorqueDragEngine.METHOD)
    r = recalculate_from_snapshot(bad)
    assert not r.success  # engine reports MISSING_INPUT, no exception


def test_persistence_failure_leaves_no_partial_row(monkeypatch):
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    direct = _ground_truth_klbf()

    # Force a failure inside the unit of work AFTER add/flush would occur.
    real_scope = m.session_scope

    class Boom(RuntimeError):
        pass

    import contextlib

    @contextlib.contextmanager
    def exploding_scope():
        with real_scope() as session:
            yield session
            raise Boom("commit boom")

    monkeypatch.setattr(m, "session_scope", exploding_scope)
    with pytest.raises(Boom):
        repo.save_run(survey=SURVEY, components=[GT_COMPONENT],
                      mud_density_ppg=10.0, friction_factor=0.3,
                      result_values=direct.values, method=TorqueDragEngine.METHOD)
    monkeypatch.undo()
    assert repo.count() == 0  # rolled back; no partial row survived


def test_record_columns_are_promoted_for_query():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    direct = _ground_truth_klbf()
    repo.save_run(survey=SURVEY, components=[GT_COMPONENT], mud_density_ppg=10.0,
                  friction_factor=0.3, result_values=direct.values,
                  method=TorqueDragEngine.METHOD)
    with m.session_scope() as session:
        row = session.query(TorqueDragCalculationRecord).one()
        assert row.total_buoyed_weight_klbf == pytest.approx(165.23, abs=0.01)
        assert row.method == TorqueDragEngine.METHOD
        assert row.input_snapshot_json is not None
