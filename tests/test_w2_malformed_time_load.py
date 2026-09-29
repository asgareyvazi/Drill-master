"""Malformed legacy DDR times remain visible and cannot be re-saved as facts."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("time_from", "time_to", "invalid_column"),
    [
        ("bad-start", "16:00", 0),
        ("08:00", "bad-end", 1),
        ("25:00", "16:00", 0),
        ("08:00", "16:75", 1),
        ("08:00:30", "16:00", 0),
        ("08:00", "16:00:30", 1),
    ],
)
def test_malformed_time_is_not_replaced_by_a_default_or_saved(time_from, time_to, invalid_column):
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - requires host Qt libraries
        pytest.skip(f"Qt runtime unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    from tabs.w2_Daily_Report import DailyReportWidget

    widget = DailyReportWidget(db_manager=None)
    try:
        widget.add_time_log_row(
            widget.time_24_table,
            SimpleNamespace(
                time_from=time_from,
                time_to=time_to,
                duration=0,
                main_phase="DRL",
                main_code="DRL-01",
                sub_code="",
                status="",
                is_npt=False,
                activity_description="Legacy activity",
                contractor="",
            ),
        )
        bad_widget = widget.time_24_table.cellWidget(0, invalid_column)
        duration = widget.time_24_table.cellWidget(0, 2)
        assert bad_widget.get_display_string() == (time_from if invalid_column == 0 else time_to)
        assert "NOT ASSESSED" == duration.text()
        with pytest.raises(ValueError, match="missing or invalid"):
            bad_widget.get_time()

        class MustNotDelete:
            called = False

            def query(self, *_args, **_kwargs):
                self.called = True
                raise AssertionError("invalid input must be rejected before deleting stored logs")

        session = MustNotDelete()
        with pytest.raises(ValueError, match="missing or invalid"):
            widget.save_time_logs_to_db(report_id=1, session=session)
        assert session.called is False

        # Replacing the malformed value with an explicit valid time restores a
        # computable duration; the invalid source itself was never normalized.
        bad_widget.set_time(9, 0)
        assert bad_widget.get_time() == (9, 0, False)
        assert duration.text() != "NOT ASSESSED"
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_blank_time_log_row_stays_unknown_until_times_are_entered():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - requires host Qt libraries
        pytest.skip(f"Qt runtime unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    from tabs.w2_Daily_Report import DailyReportWidget

    widget = DailyReportWidget(db_manager=None)
    try:
        row = widget.time_24_table.rowCount()
        widget.add_time_log_row(widget.time_24_table)
        start = widget.time_24_table.cellWidget(row, 0)
        end = widget.time_24_table.cellWidget(row, 1)
        duration = widget.time_24_table.cellWidget(row, 2)

        assert start.get_display_string() == ""
        assert end.get_display_string() == ""
        assert duration.text() == "NOT ASSESSED"
        with pytest.raises(ValueError, match="missing or invalid"):
            start.get_time()
        with pytest.raises(ValueError, match="missing or invalid"):
            end.get_time()

        class MustNotDelete:
            called = False

            def query(self, *_args, **_kwargs):
                self.called = True
                raise AssertionError("unknown times must be rejected before stored logs are deleted")

        session = MustNotDelete()
        with pytest.raises(ValueError, match="missing or invalid"):
            widget.save_time_logs_to_db(report_id=1, session=session)
        assert session.called is False
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
