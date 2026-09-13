"""Qt-free tests for the Torque & Drag calculation-HISTORY slice.

Covers historical verification semantics (MATCH / DIFFERENT / NOT_REPRODUCIBLE
/ UNREADABLE), the observational guarantee that verification never rewrites a
stored result, the current-vs-historical separation invariant, the history
list view-model, and empty/failure states — all without constructing Qt.

The ground-truth number is always produced by executing the real engine.
"""
from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("openpyxl")

from openpyxl import Workbook  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core.database import Base, DatabaseManager  # noqa: E402
from core.engineering.drill_pipe_import import import_workbook  # noqa: E402
from core.engineering.engines.torque_drag import TorqueDragEngine  # noqa: E402
from core.engineering.torque_drag_persistence import (  # noqa: E402
    VERIFY_DIFFERENT,
    VERIFY_MATCH,
    VERIFY_NOT_REPRODUCIBLE,
    VERIFY_UNREADABLE,
    verify_saved_calculation,
)
from core.repositories.drill_pipe_reference_repository import (  # noqa: E402
    DrillPipeReferenceRepository,
)
from core.repositories.torque_drag_repository import (  # noqa: E402
    TorqueDragCalculationRepository,
)

SURVEY = [{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}]
COMPONENT = {
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


def _save_gt_run(repo, components=None, label="run"):
    comps = components or [COMPONENT]
    direct = TorqueDragEngine.calculate(SURVEY, comps, mud_density_ppg=10.0,
                                        friction_factor=0.3)
    cid = repo.save_run(survey=SURVEY, components=comps, mud_density_ppg=10.0,
                        friction_factor=0.3, result_values=direct.values,
                        method=TorqueDragEngine.METHOD, label=label)
    return cid, direct


# --------------------------------------------------------------------------
# Verification states
# --------------------------------------------------------------------------
def test_verify_match_for_untouched_run():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_gt_run(repo)
    outcome = repo.get(cid).verify(current_method=TorqueDragEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches is True
    assert outcome.differences == []


def test_verify_reports_different_when_stored_result_diverges():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_gt_run(repo)
    saved = repo.get(cid)
    saved.result["total_buoyed_weight"] = 999.0  # simulate a divergent record
    outcome = saved.verify(current_method=TorqueDragEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any(d["key"] == "total_buoyed_weight" for d in outcome.differences)


def test_verify_reports_not_reproducible_for_empty_snapshot():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_gt_run(repo)
    saved = repo.get(cid)
    saved.input_snapshot = {"survey": [], "components": [], "parameters": {},
                            "method": TorqueDragEngine.METHOD}
    outcome = saved.verify(current_method=TorqueDragEngine.METHOD)
    assert outcome.status == VERIFY_NOT_REPRODUCIBLE
    assert outcome.detail  # carries the engine's reason


def test_verify_reports_unreadable_for_corrupt_snapshot():
    # A snapshot whose survey rows are not mappings cannot be reconstructed.
    outcome = verify_saved_calculation(
        {"survey": "not-a-list-of-rows", "components": [], "parameters": {}},
        {"total_buoyed_weight": 1.0},
        current_method=TorqueDragEngine.METHOD,
    )
    assert outcome.status in (VERIFY_UNREADABLE, VERIFY_NOT_REPRODUCIBLE)


def test_verify_flags_algorithm_method_drift_honestly():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_gt_run(repo)
    # Numbers still match, but the current engine method differs -> the outcome
    # must NOT claim an exact-algorithm reproduction.
    outcome = repo.get(cid).verify(current_method="DIFFERENT ALGORITHM v2")
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches is False


def test_verification_never_mutates_stored_result():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, direct = _save_gt_run(repo)
    before = dict(repo.get(cid).result)
    # Verify multiple times, including after tampering an in-memory copy.
    saved = repo.get(cid)
    saved.verify(current_method=TorqueDragEngine.METHOD)
    saved.result["total_buoyed_weight"] = 1.0
    saved.verify(current_method=TorqueDragEngine.METHOD)
    # The persisted record is unchanged (verification is observational).
    after = dict(repo.get(cid).result)
    assert after == before
    assert after["total_buoyed_weight"] == direct.values["total_buoyed_weight"]


# --------------------------------------------------------------------------
# Current-vs-historical separation (mission §19, stronger than enrichment)
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


def test_historical_run_a_stays_distinct_from_current_run_b():
    m = _mem_db()
    ref = _seed_catalog(m)
    repo = TorqueDragCalculationRepository(m)
    spec = ref.all()[0]

    # Run A: catalog reference A, persisted.
    comp_a = dict(COMPONENT, id=4.276,
                  reference_fingerprint=spec.identity_fingerprint())
    id_a, direct_a = _save_gt_run(repo, components=[comp_a], label="A")

    # Enrich master catalog legitimately (adds tool-joint OD; identity same).
    wb = Workbook()
    ws = wb.active
    ws.title = "Aa"
    ws.append(["Manufacturer", "Product", "OD (in)", "ID (in)", "Weight (ppf)",
               "Grade", "Connection", "Tool Joint OD"])
    ws.append(["ACME", "5DP", "5.000", "4.276", "19.5", "S-135", "NC50", "6.625"])
    p = tempfile.mktemp(suffix=".xlsx")
    wb.save(p)
    try:
        import_workbook(ref, p, sheet="Aa")
    finally:
        os.remove(p)

    # Run B: a genuinely DIFFERENT current calculation (heavier/longer string)
    # so its result differs from Run A's frozen historical result.
    comp_b = dict(COMPONENT, weight=25.6, length=4000.0)
    id_b, direct_b = _save_gt_run(repo, components=[comp_b], label="B")
    assert id_a != id_b
    assert direct_a.values["total_buoyed_weight"] != direct_b.values["total_buoyed_weight"]

    # Reload + recalculate Run A: must equal Run A, never silently become Run B.
    saved_a = repo.get(id_a)
    assert saved_a.input_snapshot["components"][0]["weight"] == 19.5
    assert saved_a.input_snapshot["components"][0]["length"] == 3048.0
    recalc_a = saved_a.recalculate()
    assert recalc_a.values["total_buoyed_weight"] == direct_a.values["total_buoyed_weight"]
    assert recalc_a.values["total_buoyed_weight"] != direct_b.values["total_buoyed_weight"]
    assert saved_a.verify(current_method=TorqueDragEngine.METHOD).status == VERIFY_MATCH


# --------------------------------------------------------------------------
# History list view-model + empty state
# --------------------------------------------------------------------------
def test_history_rows_projection_and_ordering():
    from dialogs.torque_drag_history_dialog import build_history_rows

    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    _save_gt_run(repo, label="first")
    _save_gt_run(repo, components=[COMPONENT, dict(COMPONENT, id=3.5)],
                 label="second")
    rows = build_history_rows(repo.all())
    assert len(rows) == 2
    # newest first
    assert rows[0]["components"] == 2
    assert rows[1]["components"] == 1
    for r in rows:
        assert r["method"] == TorqueDragEngine.METHOD
        assert r["pickup"] is not None
        assert "id" in r  # storage handle present but never shown as identity


def test_history_rows_empty_when_no_runs():
    from dialogs.torque_drag_history_dialog import build_history_rows

    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    assert build_history_rows(repo.all()) == []


def test_manual_component_carries_no_reference_fingerprint():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_gt_run(repo, components=[COMPONENT])  # no fingerprint set
    saved = repo.get(cid)
    assert saved.reference_fingerprints == []
    assert "reference_fingerprint" not in saved.input_snapshot["components"][0]
