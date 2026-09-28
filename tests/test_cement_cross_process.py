"""Cross-process reproducibility + schema-migration for cement calculations.

These tests spawn a *fresh Python interpreter* to reconstruct a saved run,
proving reproducibility comes from the persisted snapshot on disk and not from
any in-memory engine state (mission §22/§44). They also prove the
``cement_calculations`` table is auto-provisioned on a pre-existing database by
``_apply_safe_schema_upgrades`` (§28-29) without an Alembic migration.
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
    db = tmp_path / "cement.db"

    save = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.cement import CementEngine
        from core.repositories.cement_repository import CementCalculationRepository
        m = DatabaseManager()
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = CementCalculationRepository(m)
        ins = dict(hole_size_in=12.25, casing_od_in=9.625, open_hole_length_ft=2000.0,
                   excess_pct=30.0, casing_id_in=8.681, shoe_track_ft=80.0,
                   slurry_density_ppg=15.8, yield_ft3_sk=1.15, tvd_column_ft=8000.0,
                   lead_tvd_ft=1500.0, lead_density_ppg=13.5, lead_length_ft=1500.0,
                   tail_tvd_ft=500.0, tail_density_ppg=15.8, tail_length_ft=500.0,
                   shoe_tvd_ft=8000.0, pump_rate_bbl_min=8.0)
        r = CementEngine.job_volumes(**ins)
        cid = repo.save_run(inputs=ins, result_values=r.values,
                            method=CementEngine.METHOD, label="xp")
        import json
        print(json.dumps({{"id": cid, "slurry": r.values["slurry_volume_bbl"],
                           "pump": r.values["total_pump_bbl"],
                           "lead": r.values["lead"]["slurry_bbl"]}}))
    """
    saved = json.loads(_run(save, root))

    verify = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.cement import CementEngine
        from core.repositories.cement_repository import CementCalculationRepository
        m = DatabaseManager()
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = CementCalculationRepository(m)
        saved = repo.get({saved['id']})
        o = saved.verify(current_method=CementEngine.METHOD)
        recalc = saved.recalculate()
        import json
        print(json.dumps({{"status": o.status,
                           "slurry": recalc.values["slurry_volume_bbl"],
                           "pump": recalc.values["total_pump_bbl"],
                           "lead": recalc.values["lead"]["slurry_bbl"]}}))
    """
    got = json.loads(_run(verify, root))
    assert got["status"] == "MATCH"
    assert got["slurry"] == saved["slurry"]
    assert got["pump"] == saved["pump"]
    assert got["lead"] == saved["lead"]


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
        with m.engine.begin() as c:
            c.execute(text("DROP TABLE cement_calculations"))
        present_before = "cement_calculations" in inspect(m.engine).get_table_names()
        m._apply_safe_schema_upgrades()
        insp = inspect(m.engine)
        cols = len(insp.get_columns("cement_calculations"))
        import json
        print(json.dumps({{"before": present_before,
                           "after": "cement_calculations" in insp.get_table_names(),
                           "cols": cols,
                           "casing": "casing_calculations" in insp.get_table_names(),
                           "td": "torque_drag_calculations" in insp.get_table_names()}}))
    """
    out = json.loads(_run(code, "."))
    assert out["before"] is False
    assert out["after"] is True
    assert out["cols"] == 16
    assert out["casing"] is True
    assert out["td"] is True
