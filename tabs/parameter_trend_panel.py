"""M131: Drilling-parameter trends (W12 Analysis › Parameter trends).

One parameter against one explicitly chosen axis (report date or depth out); markers for values and vertical
bars for recorded min-max ranges - no line joins two records, so nothing is interpolated. Saved MSE runs are a
second, discrete plot. Missing, invalid and not-placed rows are listed with their source; the view exports to
CSV.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import parameter_trends as pt
from core.context_jobs import CANCELLED, ERROR, STALE, ContextJobRunner, check_cancel

logger = logging.getLogger(__name__)

try:
    import pyqtgraph as pg
    PYQTGRAPH = True
except ImportError:  # silent-ok: the panel shows the tables and says the charts need pyqtgraph
    pg = None
    PYQTGRAPH = False

GAP_COLUMNS = ("Series", "State", "Date", "Reason", "Source")


def _epoch(day) -> float:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()


def _load_trends_job(db, params, cancel_event):
    """Worker side: plain ids in, a plain ``TrendResult`` DTO out."""
    check_cancel(cancel_event)
    return pt.load(db, params["well"], params["axis"], params["wellbore"])


class ParameterTrendPanel(QWidget):
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.well_id: Optional[int] = None
        self.wellbore_id: Optional[int] = None
        self.result: Optional[pt.TrendResult] = None
        self.jobs = ContextJobRunner(None, "parameter trends", parent=self)   # M103 runner (M51: no GUI-thread SQL)
        self.jobs.result_ready.connect(self._show_result)
        self.jobs.state_changed.connect(self._job_state)

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.axis_combo = QComboBox()
        for key, label in pt.AXIS_LABELS.items():
            self.axis_combo.addItem(label, key)
        self.parameter_combo = QComboBox()
        for key, label, unit, _lo, _hi in pt.PARAMETERS:
            self.parameter_combo.addItem(f"{label} ({unit})", key)
        self.axis_combo.currentIndexChanged.connect(self.reload)
        self.parameter_combo.currentIndexChanged.connect(self._draw)
        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._export_dialog)
        for widget in (QLabel("Axis:"), self.axis_combo, QLabel("Parameter:"), self.parameter_combo,
                       self.export_btn):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)
        self.scope_label = QLabel("NOT ASSESSED: select a well")
        self.scope_label.setWordWrap(True)
        layout.addWidget(self.scope_label)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.plot = self.mse_plot = None
        if PYQTGRAPH:
            self.plot = pg.PlotWidget()
            self.mse_plot = pg.PlotWidget()
            for widget in (self.plot, self.mse_plot):
                widget.setMinimumHeight(220)
                layout.addWidget(widget)
        else:
            layout.addWidget(QLabel("Charts need pyqtgraph; the tables below list every value."))
        self.gap_table = QTableWidget(0, len(GAP_COLUMNS))
        self.gap_table.setHorizontalHeaderLabels(GAP_COLUMNS)
        self.gap_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(QLabel("Missing, invalid and not-placed records"))
        layout.addWidget(self.gap_table)
        self.export_btn.setEnabled(False)

    def axis(self) -> str:
        return self.axis_combo.currentData()

    def parameter(self) -> str:
        return self.parameter_combo.currentData()

    def set_scope(self, well_id: Optional[int], wellbore_id: Optional[int] = None) -> None:
        self.well_id, self.wellbore_id = well_id, wellbore_id
        self.reload()

    def reload(self) -> Optional[int]:
        """Read the trends of the current scope and axis in a background job (M103 runner: worker session on
        a file database, stale and superseded results rejected); returns the job id, None when nothing runs."""
        self.result = None
        if self.well_id is None or self.db is None:
            self.jobs.invalidate()
            self.scope_label.setText("NOT ASSESSED: select a well")
            self._draw()
            return None
        self.scope_label.setText("Loading drilling-parameter trends…")
        self._draw()
        self.jobs.db_manager = self.db
        return self.jobs.start(_load_trends_job, {"well": self.well_id, "axis": self.axis(),
                                                  "wellbore": self.wellbore_id})

    def wait(self, timeout_ms: int = 30000) -> bool:
        return self.jobs.wait(timeout_ms)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        return self.jobs.shutdown(timeout_ms)

    def _job_state(self, state: str, message: str) -> None:
        if state in (ERROR, STALE, CANCELLED):
            self.result = None
            self.scope_label.setText(message)          # the runner's message names the state / error type
            self._draw()

    def _show_result(self, _job_id: int, result) -> None:
        self.result = result
        self.scope_label.setText(f"{result.scope_label} — {result.rows} DDR row(s); axis {result.axis_label}. "
                                 f"{pt.TREND_METHOD}.")
        self._draw()

    def _x(self, value) -> float:
        return _epoch(value) if self.axis() == pt.AXIS_TIME else float(value)

    def _draw_series(self, widget, series: pt.Series) -> None:
        widget.clear()
        time_axis = self.axis() == pt.AXIS_TIME              # dates on a date axis, metres on a numeric axis
        widget.getPlotItem().setAxisItems({"bottom": pg.DateAxisItem(orientation="bottom") if time_axis
                                           else pg.AxisItem(orientation="bottom")})
        widget.setLabel("left", f"{series.label} ({series.unit})")
        widget.setLabel("bottom", self.result.axis_label)
        xs = [self._x(p.x) for p in series.points]
        ys = [p.high if p.high is not None else p.low for p in series.points]
        if xs:
            widget.plot(xs, ys, pen=None, symbol="o", symbolSize=6, name=series.label)
        bars_x, bars_y = [], []
        for p in series.points:
            if p.low is not None and p.high is not None and p.low != p.high:
                bars_x += [self._x(p.x)] * 2
                bars_y += [p.low, p.high]
        if bars_x:                    # each pair is one record's min-max; pairs are never joined to each other
            widget.plot(bars_x, bars_y, pen=pg.mkPen(width=2), connect="pairs", name="recorded range")
        widget.setTitle(series.summary() if xs else f"{series.summary()} — nothing to place on this axis")

    def _draw(self) -> None:
        self.gap_table.setRowCount(0)
        self.export_btn.setEnabled(self.result is not None)
        if self.result is None:
            self.summary_label.setText("")
            for widget in (self.plot, self.mse_plot):
                if widget is not None:
                    widget.clear()
            return
        series = self.result.series[self.parameter()]
        self.summary_label.setText(f"{series.summary()}. {self.result.mse.summary()}.")
        if self.plot is not None:
            self._draw_series(self.plot, series)
            self._draw_series(self.mse_plot, self.result.mse)
        rows = []
        for s in (series, self.result.mse):
            rows += [(s.label, "missing", day, "value not recorded", src) for day, src in s.missing]
            rows += [(s.label, "INVALID", day, why, src) for day, src, why in s.invalid]
            rows += [(s.label, "not placed", day, why, src) for day, src, why in s.not_placed]
        rows += [(self.result.mse.label, "excluded (scope)", day, why, src)
                 for day, src, why in self.result.excluded_mse]
        self.gap_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                self.gap_table.setItem(i, j, QTableWidgetItem("—" if value is None else str(value)))

    def export_to(self, path: str) -> int:
        return pt.export_csv(path, self.result) if self.result is not None else 0

    def _export_dialog(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Export trends", "parameter_trends.csv", "CSV (*.csv)")
        if path:
            self.summary_label.setText(f"Exported {self.export_to(path)} placed point(s) to {path}.")
