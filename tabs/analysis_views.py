"""Qt views for prepared Analysis payloads (M52 §2.1).

``RowsTableView``: a read-only table backed by one immutable tuple of
preformatted rows.  Setting thousands of rows is one model reset instead of
one ``QTableWidgetItem`` per cell, and only the visible rows are painted.

``ChartImageView``: shows a ``core.analysis_payloads.ChartImage`` (an Agg
rendering made off the GUI thread).  It scales the image to its size at once
and, after resizing settles, re-renders at the new size on a worker thread
(``FunctionWorker``; a newer request or a new image wins; the thread is
released only after ``run()`` returns).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QTableView

logger = logging.getLogger(__name__)

RERENDER_DELAY_MS = 200
RERENDER_TOLERANCE = 0.10        # re-render only when the size changed by more than 10 %


class RowsTableModel(QAbstractTableModel):
    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self._headers = tuple(headers)
        self._rows = ()

    def set_rows(self, rows) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def rows(self) -> tuple:
        return self._rows

    def rowCount(self, parent=QModelIndex()):      # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):   # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if role in (Qt.DisplayRole, Qt.ToolTipRole) and index.isValid():
            row = self._rows[index.row()]
            return row[index.column()] if index.column() < len(row) else ""
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):   # noqa: N802 - Qt API
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self._headers):
            return self._headers[section]
        return super().headerData(section, orientation, role)


class RowsTableView(QTableView):
    """Read-only rows; ``rowCount()`` / ``cell_text()`` mirror the QTableWidget reads callers used."""

    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self._model = RowsTableModel(headers, self)
        self.setModel(self._model)
        self.setEditTriggers(QTableView.NoEditTriggers)
        self.verticalHeader().setDefaultSectionSize(24)

    def set_rows(self, rows) -> None:
        self._model.set_rows(rows)

    def clear_rows(self) -> None:
        self._model.set_rows(())

    def rows(self) -> tuple:
        return self._model.rows()

    def rowCount(self) -> int:          # noqa: N802 - mirrors QTableWidget.rowCount
        return self._model.rowCount()

    def columnCount(self) -> int:       # noqa: N802 - mirrors QTableWidget.columnCount
        return self._model.columnCount()

    def cell_text(self, row: int, column: int) -> str:
        return self._model.rows()[row][column]


class ChartImageView(QLabel):
    """A prepared chart image (or a message), kept at the view's size."""

    def __init__(self, parent=None, minimum=(320, 240)):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(*minimum)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background-color: #1e1e1e; color: #95a5a6;")
        self._image = None              # QImage of the current ChartImage
        self.chart = None               # the ChartImage shown (None: a message is shown)
        self._render = None             # size -> ChartImage, run on a worker after a resize
        self._token = 0
        self._worker = None
        self.rerenders = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(RERENDER_DELAY_MS)
        self._timer.timeout.connect(self._rerender)

    # ---- content ---------------------------------------------------------------------------------
    def show_image(self, chart, render=None) -> None:
        """Show ``chart``; ``render(size)`` re-renders it later at another size (worker thread)."""
        self._token += 1                # a late re-render of the previous chart is dropped
        self.chart, self._render = chart, render
        image = QImage(chart.rgba, chart.width, chart.height, chart.width * 4, QImage.Format_RGBA8888)
        self._image = image.copy()      # own the pixels: ``chart.rgba`` may be released
        self.setText("")
        self._fit()
        if self._needs_rerender():
            self._timer.start()

    def show_message(self, text: str) -> None:
        self._token += 1
        self._timer.stop()
        self.chart = self._image = self._render = None
        self.setPixmap(QPixmap())
        self.setText(text)

    def message(self) -> str:
        return self.text() if self.chart is None else ""

    # ---- size --------------------------------------------------------------------------------------
    def _fit(self) -> None:
        if self._image is None:
            return
        size = self.contentsRect().size()
        pixmap = QPixmap.fromImage(self._image)
        if size.width() > 0 and size.height() > 0 and (size.width(), size.height()) != (
                self._image.width(), self._image.height()):
            pixmap = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)

    def _needs_rerender(self) -> bool:
        if self.chart is None or self._render is None or not self.isVisible():
            return False
        size = self.contentsRect().size()
        if size.width() <= 0 or size.height() <= 0:
            return False
        return (abs(size.width() - self.chart.width) > RERENDER_TOLERANCE * self.chart.width
                or abs(size.height() - self.chart.height) > RERENDER_TOLERANCE * self.chart.height)

    def resizeEvent(self, event):       # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._fit()
        if self._needs_rerender():
            self._timer.start()

    def showEvent(self, event):         # noqa: N802 - Qt API
        super().showEvent(event)
        if self._needs_rerender():
            self._timer.start()

    def _rerender(self) -> None:
        if not self._needs_rerender() or self._worker is not None:
            if self._worker is not None:
                self._timer.start()     # one re-render at a time; retry after it returns
            return
        from core.async_workers import FunctionWorker, release_when_finished
        size = self.contentsRect().size()
        token = self._token
        worker = FunctionWorker(self._render, (size.width(), size.height()))
        self._worker = worker
        worker.result_ready.connect(lambda chart, t=token: self._rerendered(t, chart))
        worker.failed.connect(lambda message: logger.error("Chart re-render failed: %s", message))
        worker.finished.connect(self._worker_finished)
        worker.start()
        # After start(): a thread that is not running yet counts as finished and
        # would be deleted at once - while run() then starts (Qt aborts).
        release_when_finished(worker)

    def _worker_finished(self) -> None:
        self._worker = None

    def _rerendered(self, token, chart) -> None:
        if token != self._token or self.chart is None:
            return                      # a newer image or message replaced the one re-rendered
        self.rerenders += 1
        render = self._render
        self._token += 1
        self.chart = chart
        image = QImage(chart.rgba, chart.width, chart.height, chart.width * 4, QImage.Format_RGBA8888)
        self._image = image.copy()
        self._render = render
        self._fit()

    def cleanup(self, wait_ms: int = 5000) -> None:
        """Page disposal: stop the timer and join a re-render in flight."""
        self._timer.stop()
        self._token += 1
        worker = self._worker
        if worker is not None:
            worker.wait(wait_ms)
