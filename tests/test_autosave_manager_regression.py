"""Regression coverage for the shared widget-manager autosave setup."""

from __future__ import annotations

import pytest


try:
    from PySide6.QtCore import QCoreApplication, QObject
except Exception as exc:  # pragma: no cover - environment-dependent Qt import
    pytest.skip(f"Qt is unavailable: {exc}", allow_module_level=True)

try:
    from core.managers import setup_widget_with_managers
except Exception as exc:  # pragma: no cover - environment-dependent Qt import
    pytest.skip(f"manager dependencies are unavailable: {exc}", allow_module_level=True)


class _SaveWidget(QObject):
    def __init__(self):
        super().__init__()
        self.save_count = 0

    def save_data(self):
        self.save_count += 1


def test_setup_widget_with_managers_uses_minute_api_and_is_idempotent():
    """The helper must use AutoSaveManager's interval_minutes API."""
    app = QCoreApplication.instance() or QCoreApplication([])
    widget = _SaveWidget()

    setup_widget_with_managers(
        widget,
        "RegressionWidget",
        enable_autosave=True,
        autosave_interval=7,
        setup_shortcuts=False,
    )

    manager = widget.autosave_timer
    assert len(manager._timers) == 1
    timer = manager._timers["RegressionWidget"]
    assert timer.interval() == 7 * 60 * 1000
    assert timer.isActive()

    # The callback still targets the widget's existing save_data API.
    timer.timeout.emit()
    assert widget.save_count == 1

    # Repeated helper setup is a no-op and cannot add a duplicate timer.
    setup_widget_with_managers(
        widget,
        "RegressionWidget",
        enable_autosave=True,
        autosave_interval=7,
        setup_shortcuts=False,
    )
    assert widget.autosave_timer is manager
    assert len(manager._timers) == 1
    assert manager._timers["RegressionWidget"] is timer

    # A direct re-enable replaces the named timer while preserving minute
    # semantics, rather than leaving two active timers behind.
    replacement = manager.enable_for_widget(
        "RegressionWidget", widget, interval_minutes=3
    )
    assert replacement is manager._timers["RegressionWidget"]
    assert replacement.interval() == 3 * 60 * 1000
    assert len(manager._timers) == 1

    app.processEvents()
