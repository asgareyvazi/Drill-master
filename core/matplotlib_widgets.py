"""Qt-safe Matplotlib canvas selection used by chart-bearing DrillMaster tabs."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget


class AggFigureCanvasWidget(QWidget):
    """Raster Agg canvas presented through a real Qt QWidget.

    This fallback is intentionally static (no Matplotlib mouse callbacks), but
    it preserves plot rendering when the Qt Matplotlib backend cannot import.
    The raw Agg canvas is never inserted into a Qt layout.
    """

    def __init__(self, figure, parent=None):
        super().__init__(parent)
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        self.figure = figure
        self._agg_canvas = FigureCanvasAgg(figure)
        self._image = QImage()
        self.setMinimumSize(120, 90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.draw()

    def sizeHint(self):
        size = self.figure.get_size_inches() * self.figure.get_dpi()
        return QSize(max(120, int(size[0])), max(90, int(size[1])))

    def draw(self):
        self._agg_canvas.draw()
        rgba = self._agg_canvas.buffer_rgba()
        width, height = self._agg_canvas.get_width_height()
        self._image = QImage(
            rgba, width, height, width * 4, QImage.Format_RGBA8888
        ).copy()
        self.update()

    def draw_idle(self):
        self.draw()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)
        if not self._image.isNull():
            painter.drawImage(self.rect(), self._image)
        painter.end()


def select_figure_canvas(qt_canvas_loader=None):
    """Use a Qt canvas when importable, otherwise use the QWidget Agg adapter."""
    if qt_canvas_loader is None:
        def qt_canvas_loader():
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
            return FigureCanvasQTAgg
    try:
        return qt_canvas_loader(), True
    except ImportError:
        try:
            from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: F401
            return AggFigureCanvasWidget, False
        except ImportError:
            return None, False
