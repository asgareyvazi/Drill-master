"""Completion OD unknown/invalid states survive real source and DB boundaries."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def test_auto_builder_and_schematic_save_preserve_od_status():
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on host Qt libraries
        pytest.skip(f"Qt runtime unavailable: {exc}")
    script = textwrap.dedent(
        r"""
        import json
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from PySide6.QtWidgets import QApplication, QWidget
        from core.database import (
            Base, Company, DatabaseManager, DownholeEquipment, Project, Well,
        )
        from core.wellbore_schematic_engine import (
            ElementType, SchematicAutoBuilder, WellboreSchematic as Schematic,
            completion_od_status,
        )

        app = QApplication.instance() or QApplication([])
        db = DatabaseManager()
        db.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(db.engine)
        db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
        session = db.create_session()
        try:
            company = Company(name="Owner", code="Owner")
            session.add(company)
            session.flush()
            project = Project(name="Project", company_id=company.id)
            session.add(project)
            session.flush()
            well = Well(name="W-1", project_id=project.id)
            session.add(well)
            session.flush()
            well_id = well.id
            session.add(DownholeEquipment(
                well_id=well_id,
                equipment_data_json=[
                    {"type": "Packer", "depth": 100, "od_inch": None},
                    {"type": "Packer", "depth": 200, "od_inch": 0},
                    {"type": "Packer", "depth": 300, "od_inch": "not-a-number"},
                    {"type": "Packer", "depth": 400, "od_inch": 4.5},
                    {"type": "Packer", "depth": 500, "od_inch": 10**1000},
                ],
            ))
            session.commit()
        finally:
            session.close()

        schematic = SchematicAutoBuilder(db).build_from_well(well_id)
        items = schematic.completion
        assert [item.depth_m for item in items] == [100, 200, 300, 400, 500]
        assert [completion_od_status(item.od_inch, item.od_source_status)
                for item in items] == [
                    "NOT_RECORDED", "INVALID", "INVALID", "RECORDED", "INVALID"
                ]
        assert items[0].od_inch is None
        assert items[2].od_inch is None and items[2].od_source_status == "INVALID_SOURCE"
        assert items[3].od_inch == 4.5
        assert items[4].od_inch is None and items[4].od_source_status == "INVALID_SOURCE"

        # The real tab gets a real QWidget parent; save_data persists the exact
        # unknown/invalid/known distinction into elements_json.
        from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab
        parent = QWidget()
        tab = WellboreSchematicTab(db, parent=parent)
        tab.current_well_id = well_id
        tab.schematic = schematic
        tab.show_success = lambda _message: None
        assert tab.save_data() is True

        saved_schematic = db.get_wellbore_schematic(well_id=well_id)
        assert saved_schematic is not None
        saved = json.loads(saved_schematic["elements_json"])["completion"]
        assert [item["od_status"] for item in saved] == [
            "NOT_RECORDED", "INVALID", "INVALID", "RECORDED", "INVALID"
        ]
        assert [item["od_inch"] for item in saved] == [None, None, None, 4.5, None]
        print("COMPLETION_OD_PERSISTENCE_OK")
        """
    )
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = str(Path(__file__).resolve().parent.parent)
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=repo_root, env=env,
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, (
        f"completion persistence subprocess failed\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr[-5000:]}"
    )
    assert "COMPLETION_OD_PERSISTENCE_OK" in proc.stdout
