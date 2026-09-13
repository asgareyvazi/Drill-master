"""Minimal UI smoke test for the w15 DrillPipe catalog view.

Constructing the full ``ReferenceTablesWidget`` (12 heavy reference tabs) in the
*shared* pytest interpreter is environmentally fragile — mixed with other Qt
tests it can trigger a native ``Fatal Python error: Aborted``. So this smoke
test runs the widget construction and assertions in an **isolated subprocess**;
the shared process only checks the subprocess's exit status. The heavy catalog
logic is covered Qt-free in ``test_drill_pipe_catalog_view.py``.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("openpyxl")
pytest.importorskip("PySide6")


_CHILD = textwrap.dedent(
    """
    import os, tempfile
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from openpyxl import Workbook
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import Base, DatabaseManager
    from core.engineering.drill_pipe_import import import_workbook
    from core.repositories.drill_pipe_reference_repository import (
        DrillPipeReferenceRepository,
    )

    def mem_db():
        m = DatabaseManager()
        m.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(m.engine)
        m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
        return m

    def seed(m):
        repo = DrillPipeReferenceRepository(m)
        wb = Workbook(); ws = wb.active; ws.title = "Aa"
        ws.append(["Manufacturer","Product","OD (in)","ID (in)",
                   "Weight (ppf)","Grade","Connection"])
        ws.append(["ACME","5DP","5.0","4.276","19.5","S-135","NC50"])
        ws.append(["Vallourec","VAM","5.875","5.153","23.4","S-135","5-1/2 FH"])
        p = tempfile.mktemp(suffix=".xlsx"); wb.save(p)
        try:
            import_workbook(repo, p, sheet="Aa")
        finally:
            os.remove(p)

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from tabs.w15_Reference_Tables import ReferenceTablesWidget

    # populated catalog -> loads + filters
    m = mem_db(); seed(m)
    w = ReferenceTablesWidget(m)
    assert len(w._dp_catalog_all_rows) == 2, "expected 2 loaded rows"
    assert w._dp_catalog_table.rowCount() == 2
    w._dp_catalog_filter("vallourec")
    assert w._dp_catalog_table.rowCount() == 1, "filter should narrow to 1"
    w._dp_catalog_filter("")
    assert w._dp_catalog_table.rowCount() == 2, "clearing filter restores rows"

    # empty catalog -> empty state message
    w2 = ReferenceTablesWidget(mem_db())
    assert w2._dp_catalog_table.rowCount() == 0
    assert "Import" in w2._dp_catalog_status.text()

    # reload reflects newly imported specs
    m3 = mem_db(); w3 = ReferenceTablesWidget(m3)
    assert w3._dp_catalog_table.rowCount() == 0
    seed(m3); w3._dp_catalog_reload()
    assert w3._dp_catalog_table.rowCount() == 2, "reload should show imports"

    print("CATALOG_WIDGET_SMOKE_OK")
    """
)


def test_catalog_widget_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "CATALOG_WIDGET_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "catalog widget smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
