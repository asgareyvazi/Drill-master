"""W13 ECD chart keeps a Qt-widget Agg fallback and clears stale profiles."""

import pytest


def test_w13_ecd_chart_falls_back_to_agg_and_replaces_stale_output(monkeypatch):
    try:
        from PySide6.QtWidgets import QApplication, QLabel, QWidget
        from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    except ImportError as exc:  # pragma: no cover - host Qt runtime dependent
        pytest.skip(f"Qt runtime unavailable: {exc}")

    from core.matplotlib_widgets import AggFigureCanvasWidget

    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    tab = EngineeringCalculatorTab(None, parent=parent)

    class FailingQtCanvas:
        def __init__(self, _figure):
            raise RuntimeError("injected Qt canvas initialization failure")

    monkeypatch.setattr(
        "core.matplotlib_widgets.select_figure_canvas",
        lambda: (FailingQtCanvas, True),
    )
    tab._draw_ecd([(100.0, 10.1), (200.0, 10.2)])
    layout = tab.hy_ecd_w.layout()
    canvas = layout.itemAt(0).widget()
    assert isinstance(canvas, AggFigureCanvasWidget)
    assert not canvas._image.isNull()

    # Missing results replace, rather than silently retaining, the old profile.
    tab._draw_ecd([])
    status = tab.hy_ecd_w.layout().itemAt(0).widget()
    assert isinstance(status, QLabel)
    assert status.text() == "ECD profile unavailable"

    parent.close()
    app.processEvents()
