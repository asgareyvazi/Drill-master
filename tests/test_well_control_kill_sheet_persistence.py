"""Qt-free tests for Well Control kill-sheet persistence + reproducibility.

DrillMaster's FOURTH persistent engineering calculation — and the first
*composite* one (three sub-engine calls + derived arithmetic + choke schedule).
Mirrors the T&D/Casing/Cement coverage against the composite: snapshot
round-trip and input completeness, repository CRUD across a real persistence
boundary, historical reproducibility, whole-result verification (including
nested detail-list and schedule-row drift), corruption states, historical-row
immutability, determinism, current-vs-historical independence, and a
composite-executed ground truth (never hard-coded).
"""
from __future__ import annotations

import json

import pytest

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core.database import (  # noqa: E402
    Base,
    DatabaseManager,
    WellControlKillSheetCalculationRecord,
)
from core.engineering.calculation_verification import (  # noqa: E402
    VERIFY_DIFFERENT,
    VERIFY_MATCH,
    VERIFY_NOT_REPRODUCIBLE,
    VERIFY_UNREADABLE,
)
from core.engineering.engines.well_control import WellControlEngine  # noqa: E402
from core.engineering.well_control_kill_sheet import (  # noqa: E402
    build_canonical_kill_sheet_inputs,
    compute_kill_sheet,
)
from core.engineering.well_control_kill_sheet_persistence import (  # noqa: E402
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    result_summary,
    snapshot_to_inputs,
)
from core.repositories.well_control_kill_sheet_repository import (  # noqa: E402
    WellControlKillSheetRepository,
)

RAW = dict(
    tvd_m=3000, md_m=3200, shoe_tvd_m=2000, hole_size_in=8.5,
    casing_id_in=8.835, casing_od_in=9.625, mw_pcf=90.0,
    frac_gradient_psi_ft=0.8, sidpp_psi=500, sicp_psi=700, pit_gain_bbl=10,
    scr1_psi=800, scr1_spm=30, scr2_psi=600, scr2_spm=25,
    pump_output_bbl_stk=0.09, method="Wait & Weight", well_type="Vertical",
    pipes_m=[
        {"type": "DP", "od": 5.0, "id": 4.276, "length": 2800.0},
        {"type": "HWDP", "od": 5.0, "id": 3.0, "length": 200.0},
        {"type": "DC", "od": 6.5, "id": 2.8125, "length": 150.0},
    ],
)

RAW2 = dict(
    tvd_m=4200, md_m=4800, shoe_tvd_m=3500, hole_size_in=12.25,
    casing_id_in=12.415, casing_od_in=13.375, mw_pcf=112.0,
    frac_gradient_psi_ft=0.95, sidpp_psi=820, sicp_psi=1100, pit_gain_bbl=32,
    scr1_psi=1200, scr1_spm=40, scr2_psi=900, scr2_spm=32,
    pump_output_bbl_stk=0.117, method="Driller's", well_type="Deviated",
    pipes_m=[
        {"type": "DP", "od": 5.5, "id": 4.778, "length": 4400.0},
        {"type": "DC", "od": 8.0, "id": 3.0, "length": 220.0},
    ],
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


def _inputs(raw=None):
    return build_canonical_kill_sheet_inputs(**(raw or RAW))


def _save(repo, raw=None, label="run"):
    inp = _inputs(raw)
    res = compute_kill_sheet(inp)
    snap = build_snapshot(inputs=inp, method=WellControlEngine.METHOD)
    # The historical claim is the WHOLE correctness-relevant result (res.values),
    # not the diagnostic-carrying as_dict() (which includes success/method/etc.).
    cid = repo.save_run(
        snapshot=snap, result=res.values,
        method=WellControlEngine.METHOD, label=label)
    return cid, res


# --------------------------------------------------------------------------
# Snapshot / reconstruction
# --------------------------------------------------------------------------
def test_snapshot_is_json_serializable_and_versioned():
    snap = build_snapshot(inputs=_inputs(), method=WellControlEngine.METHOD)
    back = json.loads(json.dumps(snap))
    assert back["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert back["method"] == WellControlEngine.METHOD
    assert "canonical_inputs" in back
    # canonical inputs are already in canonical units (ft), not raw metres
    assert back["canonical_inputs"]["tvd_ft"] == pytest.approx(3000 * 3.28084)


def test_snapshot_reconstructs_inputs_without_display():
    snap = build_snapshot(inputs=_inputs(), method=WellControlEngine.METHOD)
    # display (raw UI echo) must NOT live inside the reproducible identity payload
    assert "display" not in snap["canonical_inputs"]
    rebuilt = snapshot_to_inputs(snap)
    fresh = _inputs()
    # canonical fields reconstruct exactly (ignoring the presentation display map)
    a = fresh.as_dict(); a.pop("display")
    b = rebuilt.as_dict(); b.pop("display")
    assert a == b


def test_reconstruction_reproduces_whole_result():
    inp = _inputs()
    original = compute_kill_sheet(inp)
    snap = build_snapshot(inputs=inp, method=WellControlEngine.METHOD)
    recalc = recalculate_from_snapshot(snap)
    assert recalc.values == original.values


# --------------------------------------------------------------------------
# Repository CRUD + reproducibility
# --------------------------------------------------------------------------
def test_save_and_load_roundtrip():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, res = _save(repo, label="sheet-A")
    loaded = repo.get(cid)
    assert loaded is not None
    assert loaded.label == "sheet-A"
    assert loaded.method == WellControlEngine.METHOD
    assert loaded.result["kill_mw_ppg"] == pytest.approx(res.kill_mw_ppg)
    assert loaded.summary["maasp_psi"] == pytest.approx(res.maasp_psi)


def test_each_save_is_a_distinct_run():
    repo = WellControlKillSheetRepository(_mem_db())
    _save(repo); _save(repo); _save(repo)
    assert repo.count() == 3  # never deduplicated


def test_all_is_deterministic_newest_first():
    repo = WellControlKillSheetRepository(_mem_db())
    ids = [_save(repo, label=f"r{i}")[0] for i in range(4)]
    listed = [s.id for s in repo.all()]
    assert listed == sorted(ids, reverse=True)


def test_verify_match_on_clean_reload():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    outcome = repo.get(cid).verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == VERIFY_MATCH
    assert outcome.method_matches
    assert outcome.all_differences == []


# --------------------------------------------------------------------------
# Whole-result verification catches drift (T&D false-MATCH lesson)
# --------------------------------------------------------------------------
def test_scalar_drift_prevents_match():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result["maasp_psi"] = saved.result["maasp_psi"] + 5.0
    outcome = saved.verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any("maasp_psi" in d["path"] for d in outcome.all_differences)


def test_nested_detail_list_drift_prevents_match():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    saved = repo.get(cid)
    # perturb a numeric value deep inside the string_detail list of lists
    saved.result["string_detail"][0][2] += 0.01
    outcome = saved.verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any("string_detail" in d["path"] for d in outcome.all_differences)


def test_choke_schedule_row_drift_prevents_match():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result["choke_schedule"][3][1] += 1.0  # perturb a pressure
    outcome = saved.verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT
    assert any("choke_schedule" in d["path"] for d in outcome.all_differences)


def test_schedule_length_change_is_detected():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result["choke_schedule"].pop()  # structural change
    outcome = saved.verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == VERIFY_DIFFERENT


# --------------------------------------------------------------------------
# Corruption states
# --------------------------------------------------------------------------
def test_unreadable_when_result_missing():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.result = {}  # simulate corrupt/empty stored result
    outcome = saved.verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == VERIFY_UNREADABLE


def test_unreadable_when_snapshot_structurally_invalid():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    saved = repo.get(cid)
    saved.input_snapshot = {"schema_version": 1, "method": "x",
                            "canonical_inputs": {"tvd_ft": "not-a-number"}}
    outcome = saved.verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == VERIFY_UNREADABLE


def test_not_reproducible_when_snapshot_forces_engine_failure():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    saved = repo.get(cid)
    # zero mud weight -> kill_mw engine rejects it -> composite cannot run
    saved.input_snapshot["canonical_inputs"]["mw_ppg"] = 0.0
    outcome = saved.verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == VERIFY_NOT_REPRODUCIBLE


# --------------------------------------------------------------------------
# Historical immutability + current-vs-historical independence
# --------------------------------------------------------------------------
def test_verify_does_not_mutate_stored_record():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    before = json.dumps(repo.get(cid).result, sort_keys=True)
    repo.get(cid).verify(current_method=WellControlEngine.METHOD)
    after = json.dumps(repo.get(cid).result, sort_keys=True)
    assert before == after


def test_two_runs_are_independent_history():
    repo = WellControlKillSheetRepository(_mem_db())
    cid_a, res_a = _save(repo, raw=RAW, label="A")
    cid_b, res_b = _save(repo, raw=RAW2, label="B")
    a = repo.get(cid_a)
    b = repo.get(cid_b)
    assert a.result["kill_mw_ppg"] == pytest.approx(res_a.kill_mw_ppg)
    assert b.result["kill_mw_ppg"] == pytest.approx(res_b.kill_mw_ppg)
    assert a.result["kill_mw_ppg"] != b.result["kill_mw_ppg"]
    # A still verifies MATCH after B was saved (no cross-contamination)
    assert a.verify(current_method=WellControlEngine.METHOD).status == VERIFY_MATCH


def test_method_change_flagged_even_if_numbers_match():
    repo = WellControlKillSheetRepository(_mem_db())
    cid, _ = _save(repo)
    outcome = repo.get(cid).verify(current_method="SOME OTHER METHOD v2")
    assert outcome.status == VERIFY_MATCH  # numbers still reproduce
    assert outcome.method_matches is False  # but algorithm identity changed


# --------------------------------------------------------------------------
# Summary columns match the promoted headline claims
# --------------------------------------------------------------------------
def test_summary_columns_persisted():
    m = _mem_db()
    repo = WellControlKillSheetRepository(m)
    cid, res = _save(repo)
    with m.session_scope() as s:
        row = s.get(WellControlKillSheetCalculationRecord, cid)
        assert row.kill_mw_ppg == pytest.approx(res.kill_mw_ppg)
        assert row.maasp_psi == pytest.approx(res.maasp_psi)
        assert row.icp_psi == pytest.approx(res.icp_psi)
        assert row.total_well_vol_bbl == pytest.approx(res.total_well_vol_bbl)


def test_result_summary_keys():
    res = compute_kill_sheet(_inputs())
    summ = result_summary(res.as_dict())
    assert set(summ.keys()) == {
        "kill_mw_ppg", "icp_psi", "fcp_psi", "maasp_psi",
        "total_well_vol_bbl", "stk_total", "kick_height_ft"}
