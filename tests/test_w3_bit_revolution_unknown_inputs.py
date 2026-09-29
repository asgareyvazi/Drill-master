"""W3 bit revolutions preserve missing RPM/time through UI and persistence."""
import pytest

from core.engineering.engines.bit_performance import BitPerformanceEngine
from core.managers import DrillingManager
from test_scope_attribution import _base, _mgr, _report, _well


@pytest.mark.parametrize(
    "rpm_min,rpm_max,hours,expected",
    [
        (None, 120, 2, None),
        (100, None, 2, None),
        (100, 120, None, None),
        (0, 0, 0, 0.0),
        (100, 120, 2, 13.2),
    ],
)
def test_engine_distinguishes_missing_from_explicit_zero_and_positive_values(
    rpm_min, rpm_max, hours, expected
):
    result = BitPerformanceEngine.bit_revolutions(rpm_min, rpm_max, hours)
    if expected is None:
        assert result.success is False
        assert result.validation_status == "missing_input"
        assert result.value is None
    else:
        assert result.success is True
        assert result.value == pytest.approx(expected)
        assert result.unit == "k.rev"


def test_w3_unknown_zero_positive_and_failed_recomputation_round_trip(monkeypatch):
    try:
        from PySide6.QtWidgets import QApplication, QWidget
    except ImportError as exc:  # pragma: no cover - host Qt runtime dependent
        pytest.skip(f"Qt runtime unavailable: {exc}")
    from core.engineering.result import failed
    from tabs.w3_drilling_report import DrillingParametersTab

    app = QApplication.instance() or QApplication([])
    db = _mgr()
    host = QWidget()
    try:
        well_id = _well(db, _base(db), "Bit-revolution")
        report_id = _report(db, well_id, 1, depth=100)
        tab = DrillingParametersTab(db, parent=host)
        tab.current_well = well_id

        assert tab.collect_data()["hours_on_bottom"] is None
        assert tab.collect_data()["rpm_min"] is None
        assert tab.collect_data()["rpm_max"] is None
        assert tab.collect_data()["bit_revolution"] is None
        assert tab.bit_revolution.value() == tab.bit_revolution.minimum()
        assert tab.save_data_for_report(report_id)
        stored = db.get_drilling_parameters(report_id=report_id)
        assert stored["hours_on_bottom"] is None
        assert stored["rpm_min"] is None
        assert stored["rpm_max"] is None
        assert stored["bit_revolution"] is None

        # Explicit zeros remain numeric, including a valid measured zero result.
        tab.hours_on_bottom.setValue(0)
        tab.rpm_min.setValue(0)
        tab.rpm_max.setValue(0)
        assert tab.collect_data()["bit_revolution"] == 0
        assert tab.save_data_for_report(report_id)
        tab.load_for_report(report_id)
        explicit_zero = tab.collect_data()
        assert explicit_zero["hours_on_bottom"] == 0
        assert explicit_zero["rpm_min"] == 0
        assert explicit_zero["rpm_max"] == 0
        assert explicit_zero["bit_revolution"] == 0

        tab.hours_on_bottom.setValue(2)
        tab.rpm_min.setValue(100)
        tab.rpm_max.setValue(120)
        assert tab.collect_data()["bit_revolution"] == pytest.approx(13.2)
        assert tab.save_data_for_report(report_id)
        tab.load_for_report(report_id)
        assert tab.collect_data()["bit_revolution"] == pytest.approx(13.2)

        # Inject a failed engine result; the read-only display and payload must
        # clear instead of retaining the previous successful 13.2 k.rev.
        monkeypatch.setattr(
            DrillingManager,
            "calculate_bit_revolution_result",
            staticmethod(lambda *_args: failed("injected calculation failure")),
        )
        tab.calculate_bit_revolution()
        assert tab.collect_data()["bit_revolution"] is None
        assert tab.bit_revolution.value() == tab.bit_revolution.minimum()
    finally:
        host.close()
        host.deleteLater()
        db.close()
        app.processEvents()
