"""W3 drilling editor NULL/zero source-value regression (Qt subprocess)."""
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
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    class FakeDB:
        saved = None
        def save_drilling_parameters(self, data):
            self.saved = dict(data)
            return 1

    from tabs.w3_drilling_report import DrillingParametersTab, _optional_input_value
    db = FakeDB()
    tab = DrillingParametersTab(db)
    tab.set_current_well(1)
    source_fields = (
        "bit_size", "depth_in", "depth_out", "cum_drilled", "hours_on_bottom",
        "cum_hours", "wob_min", "wob_max", "rpm_min", "rpm_max",
        "torque_min", "torque_max", "pump_pressure_min", "pump_pressure_max",
        "pump_output_min", "pump_output_max", "pump1_spm", "pump1_spp",
        "pump2_spm", "pump2_spp",
    )
    assert all(_optional_input_value(getattr(tab, key)) is None for key in source_fields)
    assert tab.bit_type.currentIndex() == -1
    initial = tab.collect_data()
    assert all(initial[key] is None for key in source_fields), initial
    assert initial["bit_drilled"] is None
    assert initial["tfa"] is None and initial["avg_rop"] is None and initial["hsi"] is None
    assert initial["annular_velocity"] is None and initial["bit_revolution"] is None

    # Explicit zeros survive while unknown source fields remain NULL.
    for key in ("bit_size", "depth_in", "depth_out", "cum_drilled", "wob_min"):
        getattr(tab, key).setValue(0)
    assert tab.collect_data()["depth_in"] == 0
    assert tab.collect_data()["depth_out"] == 0
    assert tab.collect_data()["bit_drilled"] == 0
    assert tab.save_data_for_report(7)
    assert all(db.saved[key] == 0 for key in ("bit_size", "depth_in", "depth_out", "cum_drilled", "wob_min"))
    assert all(db.saved[key] is None for key in ("hours_on_bottom", "rpm_min", "torque_min", "pump_pressure_min"))

    # SQL NULL loads without passing None into Qt's numeric setter; save again
    # preserves both the explicit zeros and the unrecorded fields.
    tab.load_from_dict({key: None for key in source_fields})
    persisted = dict(db.saved)
    tab.load_from_dict(persisted)
    assert tab.collect_data()["bit_size"] == 0
    assert tab.collect_data()["depth_in"] == 0
    assert tab.collect_data()["depth_out"] == 0
    assert tab.collect_data()["rpm_min"] is None
    assert tab.save_data_for_report(7)
    assert db.saved["bit_size"] == 0 and db.saved["depth_in"] == 0 and db.saved["depth_out"] == 0
    assert db.saved["rpm_min"] is None and db.saved["pump_pressure_min"] is None
    try:
        tab.load_from_dict({"bit_size": float("nan")})
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("non-finite bit size was silently treated as unknown")
    print("W3_DRILLING_NULL_ZERO_OK")
    """
)


def test_w3_drilling_null_and_zero_roundtrip_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD], cwd=repo_root, env=env,
        capture_output=True, text=True, timeout=180,
    )
    if "libGL.so.1" in proc.stderr and proc.returncode != 0:
        pytest.skip("Qt widget smoke is environment-blocked: libGL.so.1 is unavailable")
    if proc.returncode != 0 or "W3_DRILLING_NULL_ZERO_OK" not in proc.stdout:
        pytest.fail(
            "W3 drilling NULL/zero round-trip failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
