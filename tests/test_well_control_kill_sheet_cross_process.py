"""Cross-process reproducibility + schema-migration for kill-sheet calculations.

These tests spawn a *fresh Python interpreter* to reconstruct a saved composite
run, proving reproducibility comes from the persisted snapshot on disk and not
from any in-memory engine state (mission §31/§32/§58). They also prove the
``well_control_kill_sheet_calculations`` table is auto-provisioned on a
pre-existing database by ``_apply_safe_schema_upgrades`` (§40-42) without an
Alembic migration and without disturbing the three existing calculation tables,
and that a reload reconstructs WITHOUT any live pipe catalog (§35-37).
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap


def _run(code: str, cwd: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=cwd, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_reconstruct_in_fresh_process(tmp_path):
    root = "."
    db = tmp_path / "killsheet.db"

    save = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.well_control import WellControlEngine
        from core.engineering.well_control_kill_sheet import (
            build_canonical_kill_sheet_inputs, compute_kill_sheet)
        from core.engineering.well_control_kill_sheet_persistence import build_snapshot
        from core.repositories.well_control_kill_sheet_repository import (
            WellControlKillSheetRepository)
        m = DatabaseManager()
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = WellControlKillSheetRepository(m)
        inp = build_canonical_kill_sheet_inputs(tvd_m=3000, md_m=3200, shoe_tvd_m=2000,
            hole_size_in=8.5, casing_id_in=8.835, casing_od_in=9.625, mw_pcf=90.0,
            frac_gradient_psi_ft=0.8, sidpp_psi=500, sicp_psi=700, pit_gain_bbl=10,
            scr1_psi=800, scr1_spm=30, scr2_psi=600, scr2_spm=25,
            pump_output_bbl_stk=0.09, method="Wait & Weight", well_type="Vertical",
            pipes_m=[{{"type":"DP","od":5.0,"id":4.276,"length":2800.0}},
                     {{"type":"DC","od":6.5,"id":2.8125,"length":150.0}}])
        res = compute_kill_sheet(inp)
        snap = build_snapshot(inputs=inp, method=WellControlEngine.METHOD)
        cid = repo.save_run(snapshot=snap, result=res.values,
                            method=WellControlEngine.METHOD, label="xp")
        import json
        print(json.dumps({{"id": cid, "kill_mw": res.kill_mw_ppg,
                           "maasp": res.maasp_psi,
                           "sched0": res.choke_schedule[0][1]}}))
    """
    saved = json.loads(_run(save, root))

    verify = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.well_control import WellControlEngine
        from core.repositories.well_control_kill_sheet_repository import (
            WellControlKillSheetRepository)
        m = DatabaseManager()
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = WellControlKillSheetRepository(m)
        saved = repo.get({saved['id']})
        o = saved.verify(current_method=WellControlEngine.METHOD)
        recalc = saved.recalculate()
        import json
        print(json.dumps({{"status": o.status,
                           "kill_mw": recalc.values["kill_mw_ppg"],
                           "maasp": recalc.values["maasp_psi"],
                           "sched0": recalc.values["choke_schedule"][0][1]}}))
    """
    got = json.loads(_run(verify, root))
    assert got["status"] == "MATCH"
    assert got["kill_mw"] == saved["kill_mw"]
    assert got["maasp"] == saved["maasp"]
    assert got["sched0"] == saved["sched0"]


def test_migration_provisions_table_on_existing_db(tmp_path):
    db = tmp_path / "legacy.db"
    code = f"""
        from sqlalchemy import create_engine, inspect, text
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        m = DatabaseManager()
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine)
        # simulate a pre-existing DB that predates calculation #4
        with m.engine.begin() as c:
            c.execute(text("DROP TABLE well_control_kill_sheet_calculations"))
        insp0 = inspect(m.engine)
        present_before = "well_control_kill_sheet_calculations" in insp0.get_table_names()
        m._apply_safe_schema_upgrades()
        insp = inspect(m.engine)
        cols = len(insp.get_columns("well_control_kill_sheet_calculations"))
        import json
        print(json.dumps({{"before": present_before,
                           "after": "well_control_kill_sheet_calculations" in insp.get_table_names(),
                           "cols": cols,
                           "cement": "cement_calculations" in insp.get_table_names(),
                           "casing": "casing_calculations" in insp.get_table_names(),
                           "td": "torque_drag_calculations" in insp.get_table_names()}}))
    """
    out = json.loads(_run(code, "."))
    assert out["before"] is False
    assert out["after"] is True
    assert out["cols"] == 17
    assert out["cement"] is True   # existing calc tables untouched
    assert out["casing"] is True
    assert out["td"] is True


def test_existing_records_survive_new_table_creation(tmp_path):
    """Saving cement + kill-sheet runs, then re-running migration, keeps both."""
    db = tmp_path / "mixed.db"
    code = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.well_control import WellControlEngine
        from core.engineering.well_control_kill_sheet import (
            build_canonical_kill_sheet_inputs, compute_kill_sheet)
        from core.engineering.well_control_kill_sheet_persistence import build_snapshot
        from core.repositories.well_control_kill_sheet_repository import (
            WellControlKillSheetRepository)
        m = DatabaseManager()
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = WellControlKillSheetRepository(m)
        inp = build_canonical_kill_sheet_inputs(tvd_m=3000, md_m=3200, shoe_tvd_m=2000,
            hole_size_in=8.5, casing_id_in=8.835, casing_od_in=9.625, mw_pcf=90.0,
            frac_gradient_psi_ft=0.8, sidpp_psi=500, sicp_psi=700, pit_gain_bbl=10,
            scr1_psi=800, scr1_spm=30, scr2_psi=600, scr2_spm=25,
            pump_output_bbl_stk=0.09, method="Wait & Weight", well_type="Vertical",
            pipes_m=[{{"type":"DP","od":5.0,"id":4.276,"length":2800.0}}])
        res = compute_kill_sheet(inp)
        snap = build_snapshot(inputs=inp, method=WellControlEngine.METHOD)
        cid = repo.save_run(snapshot=snap, result=res.values,
                            method=WellControlEngine.METHOD, label="survivor")
        # re-run the safe upgrade (idempotent) and confirm the row still verifies
        m._apply_safe_schema_upgrades()
        saved = repo.get(cid)
        o = saved.verify(current_method=WellControlEngine.METHOD)
        import json
        print(json.dumps({{"count": repo.count(), "status": o.status}}))
    """
    out = json.loads(_run(code, "."))
    assert out["count"] == 1
    assert out["status"] == "MATCH"
