"""M80: backup/restore keeps the M72/M74 revisions and their guards; the new modules stay offline.

SYNTHETIC database under a temporary data directory (never a user database).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import text

from core import db_maintenance as dm
from core import survey_revisions as sr
from core import well_architecture as wa
from tests.test_db_restore_service import ADMIN, env  # noqa: F401  (fixture reused)
from tests.test_m74_well_architecture import ARCH

ROOT = Path(__file__).resolve().parents[1]
NEW_MODULES = ("core/survey_revisions.py", "core/well_architecture.py", "core/calculator_contracts.py",
               "core/specialist_methods.py", "core/calculation_history.py", "core/ddr_import_pipeline.py",
               "tabs/survey_revision_panel.py", "tabs/well_architecture_panel.py")
NETWORK = {"socket", "urllib", "requests", "http", "httpx", "aiohttp", "ftplib", "smtplib"}


def _well(manager):
    with manager.session_scope() as session:
        return session.execute(text("SELECT id FROM wells WHERE code='SNAP-W1'")).scalar()


def test_restore_brings_back_revisions_with_their_immutability_guards(env):  # noqa: F811
    manager, backups, restore, _initial = env
    well = _well(manager)
    survey = sr.save_revision(manager, well, [{"md": 0, "inc": 0, "azi": 0}, {"md": 300, "inc": 0, "azi": 0}],
                              depth_datum="RKB", azimuth_reference="true")
    first = wa.save_revision(manager, well, ARCH, survey_revision_id=survey["id"])
    snapshot = backups.create_backup(ADMIN)
    assert snapshot.ok
    wa.save_revision(manager, well, ARCH, parent_id=first["id"])            # written after the backup
    result = restore.restore(Path(snapshot.path), ADMIN, confirmed=True)
    assert result.ok and result.stage == "complete", result
    assert [r["revision"] for r in wa.list_revisions(manager, well)] == [1]
    assert wa.get_revision(manager, first["id"])["components_sha256"] == first["components_sha256"]
    with manager.session_scope() as session:
        triggers = set(session.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'")).scalars())
    assert {"trg_survey_revision_immutable_v1", "trg_well_architecture_immutable_v1"} <= triggers
    with pytest.raises(Exception, match="immutable"):
        with manager.session_scope() as session:
            session.execute(text("UPDATE well_architecture_revisions SET note='x' WHERE id=:i"), {"i": first["id"]})
    assert dm.BackupService(manager, Path(snapshot.path).parent).create_backup(ADMIN).ok


def test_new_modules_import_no_network_library():
    for module in NEW_MODULES:
        tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        assert not imported & NETWORK, (module, imported & NETWORK)
