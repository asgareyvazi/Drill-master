"""Cross-process reproducibility + schema-migration for Mud Volume calculations.

These tests spawn a *fresh Python interpreter* to reconstruct a saved balance
run, proving reproducibility comes from the persisted snapshot on disk and not
from any in-memory state (mission §24/§48). They also prove the
``mud_volume_calculations`` table is auto-provisioned on a pre-existing database
by ``_apply_safe_schema_upgrades`` (§27-29) without an Alembic migration, and
that the five prior calculation tables survive the upgrade.
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
    db = tmp_path / "mudvol.db"

    save = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.mud_volume import MudVolumeEngine
        from core.repositories.mud_volume_repository import MudVolumeCalculationRepository
        m = DatabaseManager.__new__(DatabaseManager)
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = MudVolumeCalculationRepository(m)
        ins = dict(active_volume_bbl=800.0, additions_bbl=50.0, losses_bbl=20.0,
                   transfers_in_bbl=10.0, transfers_out_bbl=5.0, returns_bbl=15.0,
                   dilution_bbl=8.0, dumped_bbl=3.0)
        r = MudVolumeEngine.balance(**ins)
        cid = repo.save_run(inputs=ins, result_values=r.values,
                            method=MudVolumeEngine.METHOD, label="xp")
        import json
        print(json.dumps({{"id": cid, "final": r.values["final_volume_bbl"],
                           "net": r.values["net_change_bbl"]}}))
    """
    saved = json.loads(_run(save, root))

    verify = f"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from core.database import Base, DatabaseManager
        from core.engineering.engines.mud_volume import MudVolumeEngine
        from core.repositories.mud_volume_repository import MudVolumeCalculationRepository
        m = DatabaseManager.__new__(DatabaseManager)
        m.engine = create_engine("sqlite:///{db.as_posix()}")
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        repo = MudVolumeCalculationRepository(m)
        saved = repo.get({saved['id']})
        o = saved.verify(current_method=MudVolumeEngine.METHOD)
        recalc = saved.recalculate()
        import json
        print(json.dumps({{"status": o.status,
                           "final": recalc.values["final_volume_bbl"],
                           "net": recalc.values["net_change_bbl"]}}))
    """
    got = json.loads(_run(verify, root))
    assert got["status"] == "MATCH"
    assert got["final"] == saved["final"]
    assert got["net"] == saved["net"]


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
            c.execute(text("DROP TABLE mud_volume_calculations"))
        present_before = "mud_volume_calculations" in inspect(m.engine).get_table_names()
        m._apply_safe_schema_upgrades()
        insp = inspect(m.engine)
        cols = len(insp.get_columns("mud_volume_calculations"))
        import json
        print(json.dumps({{"before": present_before,
                           "after": "mud_volume_calculations" in insp.get_table_names(),
                           "cols": cols,
                           "td": "torque_drag_calculations" in insp.get_table_names(),
                           "casing": "casing_calculations" in insp.get_table_names(),
                           "cement": "cement_calculations" in insp.get_table_names(),
                           "wc": "well_control_kill_sheet_calculations" in insp.get_table_names(),
                           "mse": "mse_calculations" in insp.get_table_names()}}))
    """
    out = json.loads(_run(code, "."))
    assert out["before"] is False
    assert out["after"] is True
    assert out["cols"] == 13
    assert out["td"] is True
    assert out["casing"] is True
    assert out["cement"] is True
    assert out["wc"] is True
    assert out["mse"] is True
