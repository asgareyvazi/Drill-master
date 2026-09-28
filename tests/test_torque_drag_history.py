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
    _deep_numeric_diff,
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


# --------------------------------------------------------------------------
# Deep whole-result verification (mission §11/§12): a summary-only MATCH must
# not hide drift in non-summary fields or in the numeric profile arrays.
# --------------------------------------------------------------------------
DEVIATED_SURVEY = [
    {"md": 0, "inc": 0, "azi": 0},
    {"md": 1500, "inc": 30, "azi": 45},
    {"md": 3048.0, "inc": 60, "azi": 90},
]


def _save_deviated(repo):
    r = TorqueDragEngine.calculate(DEVIATED_SURVEY, [COMPONENT],
                                   mud_density_ppg=10.0, friction_factor=0.3,
                                   wob_klbf=5.0, wellbore_id_in=8.5)
    cid = repo.save_run(survey=DEVIATED_SURVEY, components=[COMPONENT],
                        mud_density_ppg=10.0, friction_factor=0.3, wob_klbf=5.0,
                        wellbore_id_in=8.5, result_values=r.values,
                        method=TorqueDragEngine.METHOD)
    return cid, r


def test_clean_run_matches_on_full_result_not_just_summary():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_deviated(repo)
    outcome = repo.get(cid).verify(current_method=TorqueDragEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert outcome.all_differences == []  # entire numeric result reproduced


def test_non_summary_field_drift_is_reported_different():
    # neutral_point_md_m is NOT one of the 5 promoted summary keys; drift there
    # must still be caught (previously would have been a false MATCH).
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_deviated(repo)
    saved = repo.get(cid)
    saved.result["neutral_point_md_m"] = 1234.5
    outcome = saved.verify(current_method=TorqueDragEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert outcome.differences == []  # the 5-key summary is unchanged
    assert any("neutral_point" in d["path"] for d in outcome.all_differences)


def test_profile_array_leaf_drift_is_reported_different():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_deviated(repo)
    saved = repo.get(cid)
    leaf = saved.result["tension_profile"][0]
    key = next(k for k, v in leaf.items()
               if isinstance(v, (int, float)) and not isinstance(v, bool))
    leaf[key] = leaf[key] + 9999.0
    outcome = saved.verify(current_method=TorqueDragEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any("tension_profile[0]" in d["path"] for d in outcome.all_differences)


def test_buckling_boolean_flag_drift_is_reported_different():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_deviated(repo)
    saved = repo.get(cid)
    saved.result["buckling"]["any"] = not saved.result["buckling"]["any"]
    outcome = saved.verify(current_method=TorqueDragEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any(d["path"] == "buckling.any" for d in outcome.all_differences)


def test_deep_diff_ignores_textual_metadata():
    # method/scope/warnings differences must NOT create numeric differences
    # (method drift is reported separately via method_matches).
    a = {"x": 1.0, "method": "OLD", "warnings": ["a"], "scope": "PARTIAL"}
    b = {"x": 1.0, "method": "NEW v2", "warnings": ["b", "c"], "scope": "FULL"}
    assert _deep_numeric_diff(a, b) == []


def test_deep_diff_flags_array_length_mismatch():
    a = {"profile": [{"v": 1.0}, {"v": 2.0}]}
    b = {"profile": [{"v": 1.0}]}
    diffs = _deep_numeric_diff(a, b)
    assert any("profile" in d["path"] for d in diffs)


# --------------------------------------------------------------------------
# Corruption matrix (mission §20): explicit failure states, never a crash and
# never a false MATCH, never a fallback to live catalog.
# --------------------------------------------------------------------------
def test_corrupt_missing_result_is_unreadable():
    outcome = verify_saved_calculation(
        {"survey": SURVEY, "components": [COMPONENT],
         "parameters": {"mud_density_ppg": 10.0, "friction_factor": 0.3},
         "method": TorqueDragEngine.METHOD},
        {},  # no stored result to verify against
        current_method=TorqueDragEngine.METHOD,
    )
    assert outcome.status == VERIFY_UNREADABLE


def test_corrupt_wrong_type_snapshot_is_unreadable_or_not_reproducible():
    outcome = verify_saved_calculation(
        {"survey": "garbage", "components": [COMPONENT], "parameters": {}},
        {"total_buoyed_weight": 1.0},
        current_method=TorqueDragEngine.METHOD,
    )
    assert outcome.status in (VERIFY_UNREADABLE, VERIFY_NOT_REPRODUCIBLE)


def test_corrupt_missing_required_component_field_not_reproducible():
    # component with no weight -> engine raises MISSING_INPUT -> explicit state.
    outcome = verify_saved_calculation(
        {"survey": SURVEY,
         "components": [{"od": 5.0, "id": 4.276, "length": 3048.0}],
         "parameters": {"mud_density_ppg": 10.0, "friction_factor": 0.3},
         "method": TorqueDragEngine.METHOD},
        {"total_buoyed_weight": 165.23},
        current_method=TorqueDragEngine.METHOD,
    )
    assert outcome.status == VERIFY_NOT_REPRODUCIBLE


def test_corrupt_invalid_numeric_in_stored_result_does_not_crash():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_deviated(repo)
    saved = repo.get(cid)
    saved.result["total_buoyed_weight"] = float("nan")
    outcome = saved.verify(current_method=TorqueDragEngine.METHOD)
    # NaN stored vs finite recalculated -> a difference, reported not crashed.
    assert outcome.status == VERIFY_DIFFERENT


# --------------------------------------------------------------------------
# Persisted-row immutability during verification (mission §21). The DB row's
# every persisted field must be byte-identical before and after verify/recalc.
# --------------------------------------------------------------------------
def _snapshot_row(m, calc_id):
    from core.database import TorqueDragCalculationRecord
    import json
    with m.session_scope() as session:
        row = session.get(TorqueDragCalculationRecord, calc_id)
        return {
            "label": row.label, "method": row.method,
            "schema": row.snapshot_schema_version,
            "input": json.dumps(row.input_snapshot_json, sort_keys=True),
            "result": json.dumps(row.result_json, sort_keys=True),
            "refs": json.dumps(row.reference_fingerprints_json, sort_keys=True),
            "buoyed": row.total_buoyed_weight_klbf,
            "created_at": row.created_at, "updated_at": row.updated_at,
            "created_by": row.created_by, "well_id": row.well_id,
        }


def test_verify_and_recalculate_never_mutate_persisted_row():
    m = _mem_db()
    repo = TorqueDragCalculationRepository(m)
    cid, _ = _save_deviated(repo)
    before = _snapshot_row(m, cid)

    # Perform verification and recalculation repeatedly, including on detached
    # copies whose in-memory dicts we tamper (must not reach the DB).
    for _ in range(3):
        saved = repo.get(cid)
        saved.verify(current_method=TorqueDragEngine.METHOD)
        saved.recalculate()
        saved.result["total_buoyed_weight"] = 0.0  # tamper the detached copy
        saved.input_snapshot["components"][0]["weight"] = 1.0

    after = _snapshot_row(m, cid)
    assert after == before  # every persisted field unchanged


# --------------------------------------------------------------------------
# Reference unavailability (mission §15): reconstruction must not require the
# live catalog — the snapshot alone must recompute the engineering numbers.
# --------------------------------------------------------------------------
def test_reconstruction_does_not_require_live_catalog():
    m = _mem_db()
    ref = _seed_catalog(m)
    repo = TorqueDragCalculationRepository(m)
    spec = ref.all()[0]
    comp = dict(COMPONENT, reference_fingerprint=spec.identity_fingerprint())
    cid, direct = _save_gt_run(repo, components=[comp])

    # Simulate the catalog no longer being able to provide the reference by
    # deleting every reference row (no lifecycle feature added — direct DB del).
    from core.database import DrillPipeSpecRecord
    with m.session_scope() as session:
        session.query(DrillPipeSpecRecord).delete()
    assert ref.all() == []  # catalog is now empty

    # Historical run must STILL recalculate from its frozen snapshot alone.
    saved = repo.get(cid)
    assert saved.reference_fingerprints == [spec.identity_fingerprint()]
    recalc = saved.recalculate()
    assert recalc.values["total_buoyed_weight"] == direct.values["total_buoyed_weight"]
    assert saved.verify(current_method=TorqueDragEngine.METHOD).status == VERIFY_MATCH
