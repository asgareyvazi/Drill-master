"""Reusable dashboard components (M53): theme, KPI card, panel, chart, trajectory preview.

English-only, left-to-right widgets for the Home / Operations dashboard.
Everything is painted with QPainter from plain Python data (no matplotlib on
the GUI thread, no web view).  A chart without data paints an explicit
"unavailable" message with the reason, never zero lines or invented points.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QToolTip, QVBoxLayout, QWidget

DARK = dict(name="dark", bg="#0b1220", panel="#111a2e", panel2="#16213a", border="#22304d", text="#e6edf7",
            muted="#8b9bb4", cyan="#22d3ee", blue="#3b82f6", teal="#14b8a6", amber="#f59e0b", red="#ef4444",
            green="#22c55e", grid="#1c2742", selection="#1e3a5f")
LIGHT = dict(name="light", bg="#eef2f8", panel="#ffffff", panel2="#f6f8fc", border="#d5dce8", text="#0f1b2d",
             muted="#5b6b82", cyan="#0891b2", blue="#2563eb", teal="#0d9488", amber="#b45309", red="#dc2626",
             green="#15803d", grid="#e6ebf3", selection="#dbeafe")
THEMES = {"dark": DARK, "light": LIGHT}
SERIES_KEYS = ("cyan", "blue", "teal", "amber", "red", "green")


def state_color(theme: dict, state: str) -> str:
    return {"ok": theme["cyan"], "warning": theme["amber"], "error": theme["red"],
            "no_data": theme["muted"]}.get(state, theme["muted"])


def severity_color(theme: dict, severity: Optional[str]) -> str:
    return {"error": theme["red"], "warning": theme["amber"], "info": theme["blue"]}.get(severity, theme["green"])


def stylesheet(t: dict) -> str:
    """Qt style sheet for everything under the dashboard root (objectName dashboardRoot)."""
    return f"""
#dashboardRoot, #dashboardRoot QScrollArea, #dashboardRoot QWidget#dashboardCanvas {{ background: {t['bg']}; }}
#dashboardRoot QLabel {{ color: {t['text']}; background: transparent; }}
#dashboardRoot QLabel#dashTitle {{ font-size: 20px; font-weight: 700; }}
#dashboardRoot QLabel#dashSubtitle, #dashboardRoot QLabel#dashState, #dashboardRoot QLabel#muted {{
    color: {t['muted']}; }}
#dashboardRoot QLabel#sectionTitle {{ color: {t['muted']}; font-size: 11px; font-weight: 700;
    letter-spacing: 1px; }}
#dashboardRoot QFrame#panel {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 8px; }}
#dashboardRoot QLabel#panelTitle {{ font-weight: 600; font-size: 13px; }}
#dashboardRoot QFrame#kpiCard {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 8px; }}
#dashboardRoot QFrame#kpiCard:hover {{ border-color: {t['cyan']}; }}
#dashboardRoot QLabel#kpiTitle {{ color: {t['muted']}; font-size: 11px; }}
#dashboardRoot QLabel#kpiValue {{ font-size: 21px; font-weight: 700; }}
#dashboardRoot QLabel#kpiNote, #dashboardRoot QLabel#kpiFoot {{ color: {t['muted']}; font-size: 10px; }}
#dashboardRoot QFrame#filterBar {{ background: {t['panel']}; border: 1px solid {t['border']};
    border-radius: 8px; }}
#dashboardRoot QComboBox {{ background: {t['panel2']}; color: {t['text']}; border: 1px solid {t['border']};
    border-radius: 5px; padding: 3px 8px; min-width: 110px; }}
#dashboardRoot QComboBox QAbstractItemView {{ background: {t['panel']}; color: {t['text']};
    selection-background-color: {t['selection']}; }}
#dashboardRoot QPushButton {{ background: {t['panel2']}; color: {t['text']}; border: 1px solid {t['border']};
    border-radius: 5px; padding: 5px 12px; }}
#dashboardRoot QPushButton:hover {{ border-color: {t['cyan']}; }}
#dashboardRoot QPushButton:disabled {{ color: {t['muted']}; }}
#dashboardRoot QPushButton#primary {{ background: {t['blue']}; color: #ffffff; border-color: {t['blue']}; }}
#dashboardRoot QTableWidget {{ background: {t['panel']}; alternate-background-color: {t['panel2']};
    color: {t['text']}; gridline-color: {t['grid']}; border: none;
    selection-background-color: {t['selection']}; selection-color: {t['text']}; }}
#dashboardRoot QHeaderView::section {{ background: {t['panel2']}; color: {t['muted']}; border: none;
    border-bottom: 1px solid {t['border']}; padding: 5px 6px; font-weight: 600; }}
#dashboardRoot QListWidget {{ background: {t['panel']}; color: {t['text']}; border: none; }}
#dashboardRoot QListWidget::item {{ padding: 6px 4px; border-bottom: 1px solid {t['grid']}; }}
#dashboardRoot QListWidget::item:selected {{ background: {t['selection']}; color: {t['text']}; }}
#dashboardRoot QSplitter::handle {{ background: {t['bg']}; }}
#dashboardRoot QScrollBar:vertical, #dashboardRoot QScrollBar:horizontal {{ background: {t['panel']};
    border: none; width: 10px; height: 10px; }}
#dashboardRoot QScrollBar::handle {{ background: {t['border']}; border-radius: 4px; min-height: 24px;
    min-width: 24px; }}
#dashboardRoot QScrollBar::handle:hover {{ background: {t['muted']}; }}
#dashboardRoot QScrollBar::add-line, #dashboardRoot QScrollBar::sub-line {{ width: 0; height: 0; }}
#dashboardRoot QScrollBar::add-page, #dashboardRoot QScrollBar::sub-page {{ background: transparent; }}
#dashboardRoot QAbstractScrollArea::corner {{ background: {t['panel']}; }}
#dashboardRoot QToolTip {{ color: {t['text']}; background: {t['panel2']}; border: 1px solid {t['border']}; }}
"""


def format_number(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return f"{value:,}"
    if abs(value) >= 10_000:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}"


class Panel(QFrame):
    """Titled card container used for charts, lists and tables."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(6)
        self.title = QLabel(title)
        self.title.setObjectName("panelTitle")
        self._layout.addWidget(self.title)

    def body(self) -> QVBoxLayout:
        return self._layout


class KpiCard(QFrame):
    """One KPI: title, value, unit, note and source/freshness; clicking drills down."""

    clicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 9, 12, 9)
        layout.setSpacing(1)
        self.title = QLabel("—")
        self.title.setObjectName("kpiTitle")
        self.value = QLabel("…")
        self.value.setObjectName("kpiValue")
        self.note = QLabel("")
        self.note.setObjectName("kpiNote")
        self.foot = QLabel("")
        self.foot.setObjectName("kpiFoot")
        for label in (self.title, self.value, self.note, self.foot):
            layout.addWidget(label)
        self.kpi = None
        self.theme = DARK

    def set_kpi(self, kpi, theme: Optional[dict] = None):
        from tabs.home_tab import format_kpi_value
        self.kpi = kpi
        self.theme = theme or self.theme
        self.title.setText(kpi.label.upper())
        self.value.setText(format_kpi_value(kpi))
        color = state_color(self.theme, kpi.state)
        self.value.setStyleSheet(f"color: {color};")
        self.setStyleSheet(f"QFrame#kpiCard {{ border-left: 3px solid {color}; }}")
        self.note.setText(kpi.note or " ")
        as_of = kpi.as_of.isoformat() if isinstance(kpi.as_of, (date, datetime)) else "—"
        self.foot.setText(f"{kpi.source} · as of {as_of}" if kpi.source else " ")
        unit = kpi.unit or "count / none"
        self.setToolTip(f"{kpi.definition}\n\nUnit: {unit}\nSource: {kpi.source or '—'}\nData as of: {as_of}"
                        + (f"\nNote: {kpi.note}" if kpi.note else "")
                        + ("\n\nClick to drill down." if kpi.drilldown else ""))

    def mousePressEvent(self, event):       # noqa: N802 (Qt override)
        if event.button() == Qt.LeftButton and self.kpi is not None:
            self.clicked.emit(self.kpi)
        super().mousePressEvent(event)


def _as_number(x):
    if isinstance(x, datetime):
        return x.timestamp() / 86400.0
    if isinstance(x, date):
        return float(x.toordinal())
    return float(x)


def _x_label(x) -> str:
    if isinstance(x, datetime):
        return x.strftime("%m-%d %H:%M")
    if isinstance(x, date):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, (int, float)):
        return format_number(x)
    return str(x)            # bar categories (bit numbers, cost categories)


def _nice_ticks(lo: float, hi: float, count: int = 4) -> list:
    if hi == lo:
        hi = lo + (abs(lo) or 1.0)
    raw = (hi - lo) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = min((m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw), default=raw)
    start = math.floor(lo / step) * step
    ticks = []
    value = start
    while value <= hi + step * 0.5 and len(ticks) < 12:
        ticks.append(value)
        value += step
    return ticks


class MiniChart(QWidget):
    """Line, bar or horizontal-bar chart painted from plain data.

    ``set_data(kind, series, unit, unavailable=reason)``: ``series`` is a list
    of ``(label, points, theme colour key)``; points are ``(x, y)`` tuples
    (dates, datetimes, numbers or category strings for bars).
    """

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setMinimumSize(QSize(260, 170))
        self.setMouseTracking(True)
        self.setLayoutDirection(Qt.LeftToRight)
        self.title = title
        self.kind = "line"
        self.series = []
        self.unit = ""
        self.x_unit = ""
        self.unavailable = "No data"
        self.invert_y = False
        self.theme = DARK
        self._hits = []          # (QPointF, tooltip text)

    def set_theme(self, theme: dict):
        self.theme = theme
        self.update()

    def set_data(self, kind: str, series: list, unit: str = "", unavailable: str = "No data",
                 invert_y: bool = False, x_unit: str = ""):
        self.kind, self.unit, self.unavailable, self.invert_y, self.x_unit = kind, unit, unavailable, invert_y, x_unit
        self.series = [(label, list(points), color) for label, points, color in series if points]
        self.update()

    @property
    def has_data(self) -> bool:
        return bool(self.series)

    # ------------------------------------------------------------ painting
    def paintEvent(self, _event):            # noqa: N802 (Qt override)
        t = self.theme
        painter = QPainter(self)
        # A QPainter left active by an exception crashes Qt natively; always end it
        # (the exception itself still propagates and is reported by PySide).
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            painter.fillRect(rect, QColor(t["panel"]))
            self._hits = []
            if not self.series:
                painter.setPen(QColor(t["muted"]))
                painter.drawText(rect.adjusted(12, 12, -12, -12), Qt.AlignCenter | Qt.TextWordWrap,
                                 f"Unavailable\n{self.unavailable}")
            elif self.kind == "hbar":
                self._paint_hbar(painter, rect)
            elif self.kind == "bar":
                self._paint_bar(painter, rect)
            else:
                self._paint_line(painter, rect)
        finally:
            painter.end()

    def _small_font(self, painter):
        font = QFont(painter.font())
        font.setPointSizeF(7.5)
        painter.setFont(font)
        return font

    def _paint_axes(self, painter, plot, y_ticks, y_lo, y_hi):
        t = self.theme
        self._small_font(painter)
        for tick in y_ticks:
            if tick < y_lo - 1e-9 or tick > y_hi + 1e-9:
                continue
            y = self._map_y(tick, plot, y_lo, y_hi)
            painter.setPen(QPen(QColor(t["grid"]), 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(t["muted"]))
            painter.drawText(QRectF(0, y - 8, plot.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter,
                             format_number(tick, 1 if abs(y_hi - y_lo) < 20 else 0))
        painter.setPen(QColor(t["muted"]))
        if self.unit:
            painter.drawText(QRectF(4, 2, plot.left() + 80, 14), Qt.AlignLeft | Qt.AlignVCenter, self.unit)

    def _map_y(self, value, plot, lo, hi):
        frac = 0.0 if hi == lo else (value - lo) / (hi - lo)
        if self.invert_y:
            return plot.top() + frac * plot.height()
        return plot.bottom() - frac * plot.height()

    def _paint_line(self, painter, rect):
        t = self.theme
        xs = [_as_number(x) for _l, pts, _c in self.series for x, _y in pts]
        ys = [float(y) for _l, pts, _c in self.series for _x, y in pts]
        x_lo, x_hi = min(xs), max(xs)
        if x_hi == x_lo:
            x_lo, x_hi = x_lo - 1, x_hi + 1
        ticks = _nice_ticks(min(ys), max(ys))
        y_lo, y_hi = min(ticks[0], min(ys)), max(ticks[-1], max(ys))
        plot = rect.adjusted(52, 24, -14, -30)
        self._paint_axes(painter, plot, ticks, y_lo, y_hi)
        first = min((pts[0][0] for _l, pts, _c in self.series), key=_as_number)
        last = max((pts[-1][0] for _l, pts, _c in self.series), key=_as_number)
        painter.setPen(QColor(t["muted"]))
        painter.drawText(QRectF(plot.left(), plot.bottom() + 6, 140, 14), Qt.AlignLeft, _x_label(first))
        painter.drawText(QRectF(plot.right() - 140, plot.bottom() + 6, 140, 14), Qt.AlignRight, _x_label(last))
        if self.x_unit:
            painter.drawText(QRectF(plot.left(), plot.bottom() + 6, plot.width(), 14), Qt.AlignHCenter,
                             self.x_unit)
        legend_x = plot.left() + 70
        for label, points, color_key in self.series:
            color = QColor(t[color_key])
            path = QPainterPath()
            for index, (x, y) in enumerate(points):
                px = plot.left() + (_as_number(x) - x_lo) / (x_hi - x_lo) * plot.width()
                py = self._map_y(float(y), plot, y_lo, y_hi)
                if index == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
                self._hits.append((QPointF(px, py), f"{label}\n{_x_label(x)}: {format_number(float(y), 2)} "
                                                    f"{self.unit}".strip()))
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            painter.setBrush(color)
            if len(points) <= 60:
                for point, _text in self._hits[-len(points):]:
                    painter.drawEllipse(point, 2.6, 2.6)
            if len(self.series) > 1:
                painter.setPen(color)
                painter.drawText(QRectF(legend_x, 2, 120, 14), Qt.AlignLeft | Qt.AlignVCenter, f"■ {label}")
                legend_x += 110

    def _paint_bar(self, painter, rect):
        t = self.theme
        categories = []
        for _l, pts, _c in self.series:
            for x, _y in pts:
                if x not in categories:
                    categories.append(x)
        values = [float(y) for _l, pts, _c in self.series for _x, y in pts]
        ticks = _nice_ticks(min(0.0, min(values)), max(values))
        y_lo, y_hi = min(ticks[0], 0.0), max(ticks[-1], max(values))
        plot = rect.adjusted(52, 24, -10, -34)
        self._paint_axes(painter, plot, ticks, y_lo, y_hi)
        group_w = plot.width() / max(1, len(categories))
        bar_w = max(3.0, group_w * 0.7 / len(self.series))
        zero = self._map_y(0.0, plot, y_lo, y_hi)
        for s_index, (label, points, color_key) in enumerate(self.series):
            color = QColor(t[color_key])
            lookup = dict(points)
            for c_index, category in enumerate(categories):
                if category not in lookup:
                    continue
                value = float(lookup[category])
                x = plot.left() + c_index * group_w + group_w * 0.15 + s_index * bar_w
                y = self._map_y(value, plot, y_lo, y_hi)
                bar = QRectF(x, min(y, zero), bar_w - 1, abs(zero - y))
                painter.fillRect(bar, color)
                self._hits.append((bar.center(), f"{label} · {category}: {format_number(value, 2)} {self.unit}"))
        painter.setPen(QColor(t["muted"]))
        step = max(1, math.ceil(len(categories) / max(1, int(plot.width() // 60))))
        for c_index, category in enumerate(categories):
            if c_index % step:
                continue
            x = plot.left() + c_index * group_w
            painter.drawText(QRectF(x, plot.bottom() + 4, max(group_w * step, 40), 14),
                             Qt.AlignHCenter | Qt.AlignTop, _x_label(category)[:14])
        if len(self.series) > 1:
            legend_x = plot.left() + 70
            for label, _points, color_key in self.series:
                painter.setPen(QColor(t[color_key]))
                painter.drawText(QRectF(legend_x, 2, 120, 14), Qt.AlignLeft | Qt.AlignVCenter, f"■ {label}")
                legend_x += 110

    def _paint_hbar(self, painter, rect):
        t = self.theme
        label, points, color_key = self.series[0]
        points = points[:8]
        total = sum(float(y) for _x, y in points) or 1.0
        top = rect.top() + 18
        row_h = min(26.0, (rect.height() - 24) / max(1, len(points)))
        name_w = min(150.0, rect.width() * 0.38)
        maximum = max(float(y) for _x, y in points) or 1.0
        self._small_font(painter)
        painter.setPen(QColor(t["muted"]))
        if self.unit:
            painter.drawText(QRectF(rect.left() + 4, rect.top() + 2, 200, 14), Qt.AlignLeft, self.unit)
        for index, (name, value) in enumerate(points):
            y = top + index * row_h
            painter.setPen(QColor(t["text"]))
            painter.drawText(QRectF(rect.left() + 4, y, name_w - 8, row_h), Qt.AlignRight | Qt.AlignVCenter,
                             str(name)[:22])
            width = (rect.width() - name_w - 70) * float(value) / maximum
            bar = QRectF(rect.left() + name_w, y + row_h * 0.2, max(2.0, width), row_h * 0.6)
            painter.fillRect(bar, QColor(t[SERIES_KEYS[index % len(SERIES_KEYS)]] if color_key == "multi"
                                         else t[color_key]))
            painter.setPen(QColor(t["muted"]))
            painter.drawText(QRectF(bar.right() + 6, y, 64, row_h), Qt.AlignLeft | Qt.AlignVCenter,
                             f"{format_number(float(value))} ({100 * float(value) / total:.0f}%)")
            self._hits.append((bar.center(), f"{name}: {format_number(float(value), 2)} {self.unit}"))

    def mouseMoveEvent(self, event):         # noqa: N802 (Qt override)
        if not self._hits:
            return
        pos = event.position()
        point, text = min(self._hits, key=lambda hit: (hit[0] - pos).manhattanLength())
        if (point - pos).manhattanLength() < 28:
            QToolTip.showText(event.globalPosition().toPoint(), text, self)
        else:
            QToolTip.hideText()


class TrajectoryPreview(QWidget):
    """Plan view (east/north) and section view (VS/TVD) of composed survey stations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(QSize(320, 190))
        self.setLayoutDirection(Qt.LeftToRight)
        self.stations = []
        self.message = "Select a well to preview its trajectory"
        self.theme = DARK

    def set_theme(self, theme: dict):
        self.theme = theme
        self.update()

    def set_stations(self, stations: list, message: str = ""):
        """``stations``: [(md, tvd, north, east, vs, dls)] from stored surveys only."""
        self.stations = list(stations)
        self.message = message
        self.update()

    def paintEvent(self, _event):            # noqa: N802 (Qt override)
        t = self.theme
        painter = QPainter(self)
        try:                                  # always end the painter (see MiniChart.paintEvent)
            painter.setRenderHint(QPainter.Antialiasing)
            rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            painter.fillRect(rect, QColor(t["panel"]))
            if len(self.stations) < 2:
                painter.setPen(QColor(t["muted"]))
                painter.drawText(rect.adjusted(10, 10, -10, -10), Qt.AlignCenter | Qt.TextWordWrap,
                                 f"Unavailable\n{self.message or 'Fewer than two valid survey stations'}")
            else:
                half = rect.width() / 2
                self._view(painter, QRectF(rect.left(), rect.top(), half - 4, rect.height()),
                           "PLAN  (E / N, m)", [(s[3], s[2]) for s in self.stations], False, equal=True)
                self._view(painter, QRectF(rect.left() + half + 4, rect.top(), half - 4, rect.height()),
                           "SECTION  (VS / TVD, m)", [(s[4], s[1]) for s in self.stations], True)
        finally:
            painter.end()

    def _view(self, painter, area, title, points, invert, equal=False):
        t = self.theme
        font = QFont(painter.font())
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.setPen(QColor(t["muted"]))
        painter.drawText(QRectF(area.left() + 4, area.top() + 2, area.width(), 14), Qt.AlignLeft, title)
        plot = area.adjusted(40, 20, -8, -18)
        painter.setPen(QPen(QColor(t["border"]), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(plot)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        x_lo, x_hi, y_lo, y_hi = min(xs), max(xs), min(ys), max(ys)
        span_x, span_y = (x_hi - x_lo) or 1.0, (y_hi - y_lo) or 1.0
        if equal:
            span = max(span_x, span_y)
            x_lo -= (span - span_x) / 2
            y_lo -= (span - span_y) / 2
            span_x = span_y = span
        painter.drawText(QRectF(area.left(), plot.top() - 2, 36, 12), Qt.AlignRight,
                         format_number(y_lo if invert else y_lo + span_y, 0))
        painter.drawText(QRectF(area.left(), plot.bottom() - 10, 36, 12), Qt.AlignRight,
                         format_number(y_lo + span_y if invert else y_lo, 0))
        painter.drawText(QRectF(plot.left(), plot.bottom() + 2, 60, 12), Qt.AlignLeft, format_number(x_lo, 0))
        painter.drawText(QRectF(plot.right() - 60, plot.bottom() + 2, 60, 12), Qt.AlignRight,
                         format_number(x_lo + span_x, 0))

        def map_point(x, y):
            px = plot.left() + 6 + (x - x_lo) / span_x * (plot.width() - 12)
            frac = (y - y_lo) / span_y
            py = plot.top() + 6 + (frac if invert else 1 - frac) * (plot.height() - 12)
            return QPointF(px, py)
        path = QPainterPath(map_point(*points[0]))
        for point in points[1:]:
            path.lineTo(map_point(*point))
        painter.setPen(QPen(QColor(t["cyan"]), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setBrush(QColor(t["green"]))
        painter.drawEllipse(map_point(*points[0]), 3.5, 3.5)
        painter.setBrush(QColor(t["amber"]))
        painter.drawEllipse(map_point(*points[-1]), 3.5, 3.5)
