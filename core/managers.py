"""Managers - StatusBar, AutoSave, Shortcut, plus new Architecture Managers for Intelligence Platform

P0: Existing managers kept
P1/P2 Future: NavigationManager, TabRegistry, ContextManager, MenuManager, ExportCoordinator, ImportCoordinator, WindowStateManager
"""

import logging
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel

logger = logging.getLogger(__name__)


class StatusBarManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._main_window = None
            cls._instance._widgets = {}
        return cls._instance

    def register_main_window(self, main_window):
        self._main_window = main_window

    def register_widget(self, name, widget):
        self._widgets[name] = widget

    def show_message(self, source, message, timeout=3000):
        try:
            if self._main_window and hasattr(self._main_window, 'status_label'):
                self._main_window.status_label.setText(message)
                if timeout:
                    QTimer.singleShot(timeout, lambda: self._main_window.status_label.setText("✅ Ready"))
        except Exception:
            logger.info(f"{source}: {message}")

    def show_success(self, source, message):
        self.show_message(source, f"✅ {message}", 3000)

    def show_error(self, source, message):
        self.show_message(source, f"❌ {message}", 5000)

    def show_warning(self, source, message):
        self.show_message(source, f"⚠️ {message}", 4000)

    def show_progress(self, source, message):
        self.show_message(source, f"⏳ {message}", 2000)


class AutoSaveManager:
    def __init__(self):
        self._timers = {}
        self._enabled = True

    def enable_for_widget(self, name, widget, interval_minutes=5):
        if not self._enabled:
            return
        timer = QTimer(widget)
        timer.timeout.connect(lambda: widget.save_data() if hasattr(widget, 'save_data') else None)
        timer.start(int(interval_minutes * 60 * 1000))
        self._timers[name] = timer

    def set_enabled(self, enabled):
        self._enabled = enabled
        for timer in self._timers.values():
            if enabled:
                timer.start()
            else:
                timer.stop()


class TableManager:
    """Manages QTableWidget operations: add/delete rows, alternating colors, export."""

    def __init__(self, table, parent=None):
        self.table = table
        self.parent = parent

    def set_alternating_row_colors(self, enabled: bool):
        self.table.setAlternatingRowColors(enabled)

    def add_row(self, data=None):
        row = self.table.rowCount()
        self.table.insertRow(row)
        if data:
            for col, value in enumerate(data):
                if col < self.table.columnCount():
                    from PySide6.QtWidgets import QTableWidgetItem
                    self.table.setItem(row, col, QTableWidgetItem(str(value) if value is not None else ""))
        return row

    def delete_row(self):
        current = self.table.currentRow()
        if current >= 0:
            self.table.removeRow(current)
            return True
        return False

    def clear(self):
        self.table.setRowCount(0)

    def get_row_data(self, row: int) -> list:
        data = []
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            data.append(item.text() if item else "")
        return data

    def set_row_data(self, row: int, data: list):
        from PySide6.QtWidgets import QTableWidgetItem
        for col, value in enumerate(data):
            if col < self.table.columnCount():
                self.table.setItem(row, col, QTableWidgetItem(str(value) if value is not None else ""))


class TableButtonManager:
    def __init__(self, table):
        self.table = table


class ExportManager:
    def __init__(self, parent=None):
        self.parent = parent

    def export_table_with_dialog(self, table, default_name):
        try:
            from PySide6.QtWidgets import QFileDialog
            import csv
            path, _ = QFileDialog.getSaveFileName(None, "Export", f"{default_name}.csv", "CSV (*.csv)")
            if not path:
                return
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                headers = [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else f"Col {c}" for c in range(table.columnCount())]
                writer.writerow(headers)
                for r in range(table.rowCount()):
                    row = []
                    for c in range(table.columnCount()):
                        item = table.item(r, c)
                        widget = table.cellWidget(r, c)
                        if item:
                            row.append(item.text())
                        elif widget:
                            # Try to get text from widget
                            if hasattr(widget, 'text'):
                                row.append(widget.text())
                            elif hasattr(widget, 'currentText'):
                                row.append(widget.currentText())
                            else:
                                row.append("")
                        else:
                            row.append("")
                    writer.writerow(row)
        except Exception as e:
            logger.error(f"Export error: {e}")


class ShortcutManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self._shortcuts = {}

    def setup_default_shortcuts(self):
        pass

    def add_shortcut_with_feedback(self, key, slot, desc):
        try:
            from PySide6.QtGui import QShortcut, QKeySequence
            sc = QShortcut(QKeySequence(key), self.main_window)
            sc.activated.connect(slot)
            self._shortcuts[key] = sc
        except Exception as e:
            logger.debug(f"Shortcut {key} failed: {e}")


# ==================== New Architecture Managers (P1/P2 skeleton) ====================

class NavigationManager:
    """Manages navigation between wells/sections/reports/tabs."""

    def __init__(self, tab_widget, selection_manager):
        self.tab_widget = tab_widget
        self.sel_manager = selection_manager

    def navigate_to_well(self, well_id: int):
        self.sel_manager.select_well(well_id, {})

    def navigate_to_report(self, report_id: int):
        self.sel_manager.select_report(report_id, {})


class TabRegistry:
    """Registry of all tabs with ownership (software/well/section/report)."""

    def __init__(self):
        self._tabs = {}

    def register(self, name: str, widget, ownership: str):
        """ownership: software, well, section, report"""
        self._tabs[name] = {"widget": widget, "ownership": ownership}

    def get_by_ownership(self, ownership: str):
        return [info for info in self._tabs.values() if info["ownership"] == ownership]


class ContextManager:
    """Manages current context: Company/Project/Well/Section/Report."""

    def __init__(self, selection_manager):
        self.sel_manager = selection_manager

    def get_full_context(self) -> dict:
        return {
            "well_id": self.sel_manager.current_well_id,
            "section_id": self.sel_manager.current_section_id,
            "report_id": self.sel_manager.current_report_id,
            "well_data": self.sel_manager.current_well_data,
            "section_data": self.sel_manager.current_section_data,
            "report_data": self.sel_manager.current_report_data,
        }


class MenuManager:
    """Manages menus and permission-based enabling."""

    def __init__(self, main_window):
        self.main_window = main_window

    def apply_permissions(self):
        try:
            from core.permissions import permissions
            is_viewer = permissions.is_viewer()
            # Disable sensitive actions for viewer
            if hasattr(self.main_window, 'auto_save_action'):
                self.main_window.auto_save_action.setEnabled(not is_viewer)
        except Exception:
            pass


class ExportCoordinator:
    """Coordinates professional export with full metadata."""

    def __init__(self, db_manager):
        self.db = db_manager

    def get_export_metadata(self, well_id: int, report_id: int = None) -> dict:
        """Professional export metadata as per spec."""
        from datetime import datetime, timezone
        well = self.db.get_well_by_id(well_id) or {}
        report = self.db.get_daily_report_by_id(report_id) if report_id else {}

        return {
            "company": well.get("client", "") or well.get("operator", ""),
            "project": well.get("project_name", ""),
            "field": well.get("field_name", ""),
            "well": well.get("name", ""),
            "section": well.get("section_name", ""),
            "report_number": report.get("report_number", ""),
            "report_date": str(report.get("report_date", "")),
            "revision": "Rev 0",
            "status": report.get("status", "Draft"),
            "prepared_by": well.get("supervisor_day", ""),
            "checked_by": well.get("supervisor_night", ""),
            "approved_by": well.get("operation_manager", ""),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "timezone": "UTC",
            "units": "Metric (m, ppg, psi, gpm)",
            "data_quality": "Validated",
            "audit_id": f"AUDIT-{well_id}-{report_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }


class ImportCoordinator:
    """Coordinates atomic import with preview and validation."""

    def __init__(self, db_manager):
        self.db = db_manager

    def import_file(self, file_path: str, well_id: int = None) -> dict:
        """Atomic import flow as per spec."""
        # This is coordinated in ExcelImportDialog._unified_import
        # Here is the logical flow:
        # Begin Transaction
        #   Well (universal alias resolution)
        #   Project
        #   Section (name + depth range)
        #   Daily Report (well_id + section_id + report_date unique, no fake defaults)
        #   Mud, Drilling Parameters, Time Logs (24h validation), Bit, BHA, Survey, Equipment, Logistics, Safety, Services, Cost
        # Commit / Rollback All
        # Batch report successful/failed
        return {"status": "coordinated in dialog"}


class WindowStateManager:
    """Manages window state persistence."""

    def __init__(self, settings):
        self.settings = settings

    def save(self, main_window):
        try:
            self.settings.setValue("window/geometry", main_window.saveGeometry())
            self.settings.setValue("window/state", main_window.saveState())
        except Exception:
            pass

    def restore(self, main_window):
        try:
            geom = self.settings.value("window/geometry")
            state = self.settings.value("window/state")
            if geom:
                main_window.restoreGeometry(geom)
            if state:
                main_window.restoreState(state)
        except Exception:
            pass


class DrillingManager:
    """Utility class for common drilling calculations used by UI tabs."""

    @staticmethod
    def calculate_tfa(nozzles: list) -> float:
        """Calculate Total Flow Area from nozzle sizes (in 32nds of inch).

        TFA = sum( pi/4 * (d/32)^2 ) for each nozzle
        """
        import math
        tfa = 0.0
        for n in (nozzles or []):
            size = n.get("size") if isinstance(n, dict) else n
            qty = n.get("quantity", 1) if isinstance(n, dict) else 1
            try:
                d = float(size) / 32.0
                tfa += qty * math.pi / 4 * d * d
            except (TypeError, ValueError):
                continue
        return round(tfa, 4)

    @staticmethod
    def calculate_rop(depth_in: float, depth_out: float, hours: float) -> float:
        """Calculate Rate of Penetration: (depth_out - depth_in) / hours."""
        if not hours or hours <= 0:
            return 0.0
        return round((depth_out - depth_in) / hours, 2)

    @staticmethod
    def calculate_hsi(pump_pressure: float, flow_rate: float, bit_size: float) -> float:
        """Calculate Hydraulic Horsepower per Square Inch.

        HHP = Q * dP / 1714
        HSI = HHP / (pi/4 * D^2)
        """
        import math
        if not bit_size or bit_size <= 0:
            return 0.0
        bit_area = math.pi / 4 * bit_size * bit_size
        hhp = (flow_rate or 0) * (pump_pressure or 0) / 1714
        return round(hhp / bit_area, 2) if bit_area > 0 else 0.0

    @staticmethod
    def calculate_annular_velocity(flow_rate: float, hole_size: float, pipe_od: float) -> dict:
        """Calculate annular velocity.

        AV = 24.51 * Q / (Dh^2 - Dp^2) in ft/min
        Returns dict with ft_min key for compatibility.
        """
        denom = (hole_size or 0) ** 2 - (pipe_od or 0) ** 2
        if denom <= 0:
            return {"ft_min": 0.0}
        av = 24.51 * (flow_rate or 0) / denom
        return {"ft_min": round(av, 2)}

    @staticmethod
    def calculate_bit_revolution(rpm: float, hours: float) -> float:
        """Calculate total bit revolutions: RPM * hours * 60."""
        return round((rpm or 0) * (hours or 0) * 60, 0)


def setup_widget_with_managers(widget, widget_name: str = "",
                                enable_autosave: bool = False,
                                autosave_interval: int = 5,
                                setup_shortcuts: bool = False):
    """Convenience function to wire up common managers for a tab widget.

    Registers the widget with StatusBarManager and optionally enables auto-save.
    """
    try:
        status_mgr = StatusBarManager()
        status_mgr.register_widget(widget_name or widget.__class__.__name__, widget)
    except Exception:
        pass

    if enable_autosave and hasattr(widget, 'save_data'):
        try:
            auto_mgr = AutoSaveManager()
            auto_mgr.enable_for_widget(
                widget_name or widget.__class__.__name__,
                widget,
                interval_minutes=autosave_interval
            )
        except Exception:
            pass
