"""Cross-process reproducibility + schema-migration for casing calculations.

These tests deliberately spawn a *fresh Python interpreter* to reconstruct a
saved run, proving reproducibility comes from the persisted snapshot on disk and
not from any in-memory engine state (mission §23). They also prove the
``casing_calculations`` table is auto-provisioned on a pre-existing database by
``_apply_safe_schema_upgrades`` (§29-30) without an Alembic migration.
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
    db = tmp_path / "casing.db"

    save = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.casing import CasingEngine
        from core.repositories.casing_repository import CasingCalculationRepository
        m = DatabaseManager()
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = CasingCalculationRepository(m)
        ins = dict(od_in=9.625, id_in=8.681, yield_psi=80000.0,
                   internal_pressure_psi=8000.0, external_pressure_psi=6000.0,
                   axial_tension_lbf=200000.0, grade="N-80", weight_ppf=47.0)
        r = CasingEngine.evaluate(**ins)
        cid = repo.save_run(inputs=ins, result_values=r.values,
                            method=CasingEngine.METHOD, label="xp")
        import json
        print(json.dumps({{"id": cid, "burst": r.values["burst_rating_psi"],
                           "vme": r.values["vme_psi"]}}))
    """
    saved = json.loads(_run(save, root))

    verify = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.casing import CasingEngine
        from core.repositories.casing_repository import CasingCalculationRepository
        m = DatabaseManager()
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = CasingCalculationRepository(m)
        saved = repo.get({saved['id']})
        o = saved.verify(current_method=CasingEngine.METHOD)
        recalc = saved.recalculate()
        import json
        print(json.dumps({{"status": o.status,
                           "burst": recalc.values["burst_rating_psi"],
                           "vme": recalc.values["vme_psi"]}}))
    """
    got = json.loads(_run(verify, root))
    assert got["status"] == "MATCH"
    assert got["burst"] == saved["burst"]
    assert got["vme"] == saved["vme"]


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
            c.execute(text("DROP TABLE casing_calculations"))
        present_before = "casing_calculations" in inspect(m.engine).get_table_names()
        m._apply_safe_schema_upgrades()
        insp = inspect(m.engine)
        cols = len(insp.get_columns("casing_calculations"))
        import json
        print(json.dumps({{"before": present_before,
                           "after": "casing_calculations" in insp.get_table_names(),
                           "cols": cols,
                           "td": "torque_drag_calculations" in insp.get_table_names()}}))
    """
    out = json.loads(_run(code, "."))
    assert out["before"] is False
    assert out["after"] is True
    assert out["cols"] == 16
    assert out["td"] is True
