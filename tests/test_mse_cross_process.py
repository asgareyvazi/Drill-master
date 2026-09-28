"""Cross-process reproducibility + schema-migration for MSE calculations.

These tests spawn a *fresh Python interpreter* to reconstruct a saved MSE run,
proving reproducibility comes from the persisted snapshot on disk and not from
any in-memory engine state (mission §29/§30/§59). They also prove the
``mse_calculations`` table is auto-provisioned on a pre-existing database by
``_apply_safe_schema_upgrades`` (§35-37/§60) without an Alembic migration, and
that the four prior calculation tables survive the upgrade.
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
    db = tmp_path / "mse.db"

    save = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.mse import MSEEngine
        from core.repositories.mse_repository import MSECalculationRepository
        m = DatabaseManager.__new__(DatabaseManager)
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = MSECalculationRepository(m)
        ins = dict(wob_lbf=25000.0, rpm=120.0, torque_ft_lbf=8000.0,
                   rop_ft_hr=30.0, bit_diameter_in=8.5)
        r = MSEEngine.calculate(**ins)
        cid = repo.save_run(inputs=ins, result_values=r.values,
                            method=MSEEngine.METHOD, label="xp")
        import json
        print(json.dumps({{"id": cid, "mse": r.values["mse_psi"],
                           "axial": r.values["axial_term_psi"],
                           "rotary": r.values["rotary_term_psi"]}}))
    """
    saved = json.loads(_run(save, root))

    verify = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.mse import MSEEngine
        from core.repositories.mse_repository import MSECalculationRepository
        m = DatabaseManager.__new__(DatabaseManager)
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = MSECalculationRepository(m)
        saved = repo.get({saved['id']})
        o = saved.verify(current_method=MSEEngine.METHOD)
        recalc = saved.recalculate()
        import json
        print(json.dumps({{"status": o.status,
                           "mse": recalc.values["mse_psi"],
                           "axial": recalc.values["axial_term_psi"],
                           "rotary": recalc.values["rotary_term_psi"]}}))
    """
    got = json.loads(_run(verify, root))
    assert got["status"] == "MATCH"
    assert got["mse"] == saved["mse"]
    assert got["axial"] == saved["axial"]
    assert got["rotary"] == saved["rotary"]


def test_migration_provisions_table_on_existing_db(tmp_path):
    db = tmp_path / "legacy.db"
    code = f"""
        from sqlalchemy import create_engine, inspect, text
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        m = DatabaseManager.__new__(DatabaseManager)
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine)
        m.schema_version = 3
        with m.engine.begin() as c:
            c.execute(text("DROP TABLE mse_calculations"))
        present_before = "mse_calculations" in inspect(m.engine).get_table_names()
        m._apply_safe_schema_upgrades()
        insp = inspect(m.engine)
        cols = len(insp.get_columns("mse_calculations"))
        import json
        print(json.dumps({{"before": present_before,
                           "after": "mse_calculations" in insp.get_table_names(),
                           "cols": cols,
                           "td": "torque_drag_calculations" in insp.get_table_names(),
                           "casing": "casing_calculations" in insp.get_table_names(),
                           "cement": "cement_calculations" in insp.get_table_names(),
                           "wc": "well_control_kill_sheet_calculations" in insp.get_table_names()}}))
    """
    out = json.loads(_run(code, "."))
    assert out["before"] is False
    assert out["after"] is True
    assert out["cols"] == 14
    assert out["td"] is True
    assert out["casing"] is True
    assert out["cement"] is True
    assert out["wc"] is True
