import pytest


def test_agg_fallback_is_a_real_qt_widget_and_paints_a_figure():
    try:
        from matplotlib.figure import Figure
        from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
    except ImportError as exc:  # pragma: no cover - host Qt runtime dependent
        pytest.skip(f"Qt runtime unavailable: {exc}")
    from core.matplotlib_widgets import (
        AggFigureCanvasWidget,
        select_figure_canvas,
    )

    app = QApplication.instance() or QApplication([])

    def unavailable_qt_canvas():
        raise ImportError("injected missing Matplotlib Qt backend")

    canvas_type, qt_available = select_figure_canvas(unavailable_qt_canvas)
    assert qt_available is False
    assert canvas_type is AggFigureCanvasWidget

    figure = Figure(figsize=(3, 2), dpi=80)
    axes = figure.subplots()
    axes.plot([0, 1, 2], [0, 1, 0])
    widget = canvas_type(figure)
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.addWidget(widget)
    host.resize(320, 220)
    host.show()
    app.processEvents()

    assert widget.parentWidget() is host
    assert widget.sizeHint().width() >= 120
    assert not widget._image.isNull()
    rendered = widget.grab().toImage()
    assert not rendered.isNull()
    host.close()
