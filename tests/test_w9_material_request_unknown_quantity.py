"""W9 must keep an unentered material-request quantity NULL, not zero."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("PySide6")


_CHILD = textwrap.dedent(
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from datetime import date
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import Base, DatabaseManager, Company, Project, Well

    db = DatabaseManager()
    db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db.engine)
    db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    s = db.create_session()
    company = Company(name="C", code="C"); s.add(company); s.flush()
    project = Project(name="P", company_id=company.id); s.add(project); s.flush()
    well = Well(name="W", project_id=project.id); s.add(well); s.commit()
    well_id = well.id
    s.close()

    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    from tabs.w9_Services_Widget import MaterialHandlingTab
    tab = MaterialHandlingTab(db)
    tab.current_well_id = well_id
    tab.requested_items_input.setPlainText("Casing centralizers")

    # Untouched quantity is unknown by the MaterialRequest DB contract.
    tab.save_material_request()
    rows = db.get_material_requests(well_id=well_id)
    assert len(rows) == 1 and rows[0]["requested_quantity"] is None

    # An explicitly entered zero is still a reported zero, not the unknown sentinel.
    tab.requested_items_input.setPlainText("No quantity needed")
    tab.requested_qty_input.setValue(0)
    tab.save_material_request()
    rows = db.get_material_requests(well_id=well_id)
    quantities = [row["requested_quantity"] for row in rows]
    assert len(rows) == 2 and None in quantities and 0.0 in quantities

    tab.clear_request_form()
    assert tab.requested_qty_input.value() == -1.0
    print("W9_UNKNOWN_QUANTITY_UI_OK")
    """
)


def test_w9_unentered_quantity_round_trips_as_null_and_explicit_zero_survives():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-c", _CHILD], cwd=repo_root, env=env,
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0 or "W9_UNKNOWN_QUANTITY_UI_OK" not in result.stdout:
        pytest.fail(f"W9 quantity UI regression failed\n{result.stdout}\n{result.stderr}")
