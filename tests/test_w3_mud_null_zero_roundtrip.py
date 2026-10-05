"""Subprocess-isolated W3 mud editor NULL/zero save-load regression."""
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
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    class FakeDB:
        saved = None
        def get_daily_report_by_id(self, report_id):
            return {"id": report_id, "report_date": date(2026, 10, 1)}
        def save_mud_report(self, data):
            self.saved = dict(data)
            return {"id": 1}

    from tabs.w3_drilling_report import MudReportTab, _optional_input_value
    db = FakeDB()
    tab = MudReportTab(db)
    tab.set_current_well(1)
    tab.clear_form()
    source_fields = (
        "mw", "pv", "yp", "funnel_vis", "gel_10s", "gel_10m",
        "cake_thickness", "ph", "temperature", "solid_percent", "oil_percent",
        "water_percent", "chloride", "calcium", "kcl", "mbt", "pf_mf",
        "total_hardness", "flowline_temp", "volume_hole", "total_circulated",
        "loss_downhole", "loss_surface",
    )
    assert all(_optional_input_value(getattr(tab, key)) is None for key in source_fields)
    assert all(getattr(tab, key).value() == getattr(tab, key).minimum() for key in source_fields)
    assert all(getattr(tab, key).specialValueText() == "Not recorded" for key in source_fields)
    assert tab.save_data_for_report(1)
    assert all(db.saved[key] is None for key in source_fields), db.saved
    assert db.saved["fl"] is None

    # An explicitly entered zero is a measurement, distinct from the untouched
    # Not recorded sentinel; it must persist through save, reload, and save.
    for key in ("mw", "pv", "ph", "temperature", "solid_percent", "oil_percent", "water_percent"):
        getattr(tab, key).setValue(0.0)
    tab.fl_nc.setChecked(False)
    tab.fl.setValue(0.0)
    assert tab.save_data_for_report(1)
    assert all(db.saved[key] == 0.0 for key in ("mw", "pv", "ph", "temperature", "solid_percent", "oil_percent", "water_percent", "fl"))

    persisted = dict(db.saved)
    tab.load_from_dict(persisted)
    assert tab.save_data_for_report(1)
    assert all(db.saved[key] == 0.0 for key in ("mw", "pv", "ph", "temperature", "solid_percent", "oil_percent", "water_percent", "fl"))
    assert all(db.saved[key] is None for key in ("yp", "funnel_vis", "gel_10s", "gel_10m", "cake_thickness", "chloride", "calcium", "kcl", "mbt", "pf_mf", "total_hardness", "flowline_temp", "volume_hole", "total_circulated", "loss_downhole", "loss_surface"))

    # Clearing a real value explicitly returns it to unknown; an unchanged
    # loaded zero never gets rewritten as NULL.
    tab.mw.setValue(tab.mw.minimum())
    assert tab.save_data_for_report(1)
    assert db.saved["mw"] is None and db.saved["pv"] == 0.0

    # Corrupt/non-finite persisted values are rejected, not converted into the
    # same UI state used for an actual SQL NULL.
    try:
        tab.load_from_dict({"mw": float("nan")})
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("non-finite persisted MW was silently treated as unknown")
    print("W3_MUD_NULL_ZERO_OK")
    """
)


def test_w3_mud_null_and_zero_roundtrip_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD], cwd=repo_root, env=env,
        capture_output=True, text=True, timeout=180,
    )
    if "libGL.so.1" in proc.stderr and proc.returncode != 0:
        pytest.skip("Qt widget smoke is environment-blocked: libGL.so.1 is unavailable")
    if proc.returncode != 0 or "W3_MUD_NULL_ZERO_OK" not in proc.stdout:
        pytest.fail(
            "W3 mud NULL/zero round-trip failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
