"""Subprocess-isolated smoke test: AddPipeDialog stamps reference traceability.

Proves that selecting a persisted catalog reference in Quick Select stamps the
component with that reference's engineering fingerprint (§8), and that editing
the component away from the reference honestly DROPS the fingerprint (no
misleading traceability). Runs in an isolated subprocess to avoid the shared
pytest process's native Qt abort with real dialogs.
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
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from openpyxl import Workbook
    from core.database import DatabaseManager, Base
    from core.repositories.drill_pipe_reference_repository import (
        DrillPipeReferenceRepository)
    from core.engineering.drill_pipe_import import import_workbook

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    ref = DrillPipeReferenceRepository(m)
    wb = Workbook(); ws = wb.active; ws.title = "Aa"
    ws.append(["Manufacturer","Product","OD (in)","ID (in)","Weight (ppf)",
               "Grade","Connection"])
    ws.append(["ACME","5DP","5.000","4.276","19.5","S-135","NC50"])
    p = tempfile.mktemp(suffix=".xlsx"); wb.save(p)
    try:
        import_workbook(ref, p, sheet="Aa")
    finally:
        os.remove(p)
    spec = ref.all()[0]

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from dialogs.engineering_dialogs import AddPipeDialog, reference_spec_label

    # Select the reference, keep values, save -> fingerprint stamped.
    d1 = AddPipeDialog(reference_repo=ref)
    d1._on_quick_selected(reference_spec_label(spec))
    d1.length.setValue(1000.0)
    d1._save()
    assert (d1.result or {}).get("reference_fingerprint") == spec.identity_fingerprint()

    # Select then edit OD away -> fingerprint dropped (honest traceability).
    d2 = AddPipeDialog(reference_repo=ref)
    d2._on_quick_selected(reference_spec_label(spec))
    d2.length.setValue(1000.0)
    d2.od.setValue(5.5); d2.id_.setValue(4.0)
    d2._save()
    assert (d2.result or {}).get("reference_fingerprint") is None

    print("ADDPIPE_FP_SMOKE_OK")
    """
)


def test_addpipe_reference_fingerprint_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "ADDPIPE_FP_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "AddPipe reference fingerprint smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
