# core/base_tab.py
"""
Base class for all tabs in DrillMaster.

Usage:
    class MyTab(DrillTabBase):
        def __init__(self, db_manager, parent=None):
            super().__init__("MyTab", db_manager, parent)

        def on_well_changed(self, well_id, well_data):
            self.load_data_for_well(well_id)

        def on_report_changed(self, report_id, report_data):
            self.load_data_for_report(report_id)

        def save_data(self) -> bool:
            ...
            return True
"""

import logging
from PySide6.QtWidgets import QWidget, QMessageBox
from PySide6.QtCore import QTimer

from core.managers import StatusBarManager
from core.selection_manager import SelectionManager

logger = logging.getLogger(__name__)


class DrillTabBase(QWidget):
    """
    Common base for all DrillMaster tabs.

    Features:
    - Auto-connects to SelectionManager signals
    - Lazy loading: only loads when tab is visible
    - Pending updates: queued while tab is hidden
    - Status bar integration
    - Common require_* guards
    """

    def __init__(
        self,
        widget_name: str,
        db_manager=None,
        parent=None,
    ):
        super().__init__(parent)  # ✅ pass parent to Qt directly

        self.widget_name = widget_name
        self.db = db_manager
        self.status_manager = StatusBarManager()
        self.sel_manager = SelectionManager()

        # Current state - synced from SelectionManager
        self.current_well_id = self.sel_manager.current_well_id
        self.current_section_id = self.sel_manager.current_section_id
        self.current_report_id = self.sel_manager.current_report_id
        self.current_well_data = self.sel_manager.current_well_data or {}
        self.current_section_data = self.sel_manager.current_section_data or {}
        self.current_report_data = self.sel_manager.current_report_data or {}

        # ✅ Pending updates - initialized upfront
        self._pending_well = None       # (well_id, well_data)
        self._pending_section = None    # (section_id, section_data)
        self._pending_report = None     # (report_id, report_data)

        # ✅ Track last loaded IDs to avoid duplicate loads
        self._loaded_well_id = None
        self._loaded_section_id = None
        self._loaded_report_id = None

        # Connect to SelectionManager
        self.sel_manager.well_changed.connect(
            self._on_well_changed_internal
        )
        self.sel_manager.section_changed.connect(
            self._on_section_changed_internal
        )
        self.sel_manager.report_changed.connect(
            self._on_report_changed_internal
        )
        self.sel_manager.selection_cleared.connect(
            self._on_selection_cleared_internal
        )

        # Register in StatusManager
        try:
            self.status_manager.register_widget(widget_name, self)
        except Exception:
            pass

    # ================================================================
    # Internal Signal Handlers
    # ================================================================

    def _on_well_changed_internal(self, well_id, well_data):
        """Handle well change signal."""
        self.current_well_id = well_id
        self.current_well_data = well_data or {}

        # ✅ Reset section/report when well changes
        self.current_section_id = None
        self.current_section_data = {}
        self.current_report_id = None
        self.current_report_data = {}

        if self.isVisible():
            self._loaded_well_id = well_id
            self._pending_well = None
            try:
                self.on_well_changed(well_id, self.current_well_data)
            except Exception as e:
                logger.error(
                    f"{self.widget_name}.on_well_changed error: {e}",
                    exc_info=True,
                )
        else:
            # Queue for when tab becomes visible
            self._pending_well = (well_id, self.current_well_data)
            # Clear downstream pending too
            self._pending_section = None
            self._pending_report = None

    def _on_section_changed_internal(self, section_id, section_data):
        """Handle section change signal."""
        self.current_section_id = section_id
        self.current_section_data = section_data or {}

        # Reset report when section changes
        self.current_report_id = None
        self.current_report_data = {}

        if self.isVisible():
            self._loaded_section_id = section_id
            self._pending_section = None
            try:
                self.on_section_changed(
                    section_id, self.current_section_data
                )
            except Exception as e:
                logger.error(
                    f"{self.widget_name}.on_section_changed error: {e}",
                    exc_info=True,
                )
        else:
            self._pending_section = (section_id, self.current_section_data)
            self._pending_report = None

    def _on_report_changed_internal(self, report_id, report_data):
        """Handle report change signal."""
        self.current_report_id = report_id
        self.current_report_data = report_data or {}

        if self.isVisible():
            self._loaded_report_id = report_id
            self._pending_report = None
            try:
                self.on_report_changed(
                    report_id, self.current_report_data
                )
            except Exception as e:
                logger.error(
                    f"{self.widget_name}.on_report_changed error: {e}",
                    exc_info=True,
                )
        else:
            self._pending_report = (report_id, self.current_report_data)

    def _on_selection_cleared_internal(self):
        """Handle full clear signal."""
        self.current_well_id = None
        self.current_section_id = None
        self.current_report_id = None
        self.current_well_data = {}
        self.current_section_data = {}
        self.current_report_data = {}
        self._pending_well = None
        self._pending_section = None
        self._pending_report = None
        self._loaded_well_id = None
        self._loaded_section_id = None
        self._loaded_report_id = None
        try:
            self.on_selection_cleared()
        except Exception as e:
            logger.error(
                f"{self.widget_name}.on_selection_cleared error: {e}"
            )

    # ================================================================
    # showEvent - Process pending updates
    # ================================================================

    def showEvent(self, event):
        """Process pending updates when tab becomes visible."""
        super().showEvent(event)

        # A tab can be created after the selection was made.  In that case
        # there is no queued signal, so bootstrap it from the manager state.
        if self._pending_well is None and self.current_well_id is not None and self._loaded_well_id != self.current_well_id:
            self._pending_well = (self.current_well_id, self.current_well_data)
        if self._pending_section is None and self.current_section_id is not None and self._loaded_section_id != self.current_section_id:
            self._pending_section = (self.current_section_id, self.current_section_data)
        if self._pending_report is None and self.current_report_id is not None and self._loaded_report_id != self.current_report_id:
            self._pending_report = (self.current_report_id, self.current_report_data)

        # Process in order: well -> section -> report
        if self._pending_well is not None:
            well_id, well_data = self._pending_well
            self._pending_well = None
            self._loaded_well_id = well_id
            try:
                self.on_well_changed(well_id, well_data)
            except Exception as e:
                logger.error(
                    f"{self.widget_name}.on_well_changed (pending): {e}"
                )

        if self._pending_section is not None:
            section_id, section_data = self._pending_section
            self._pending_section = None
            self._loaded_section_id = section_id
            try:
                self.on_section_changed(section_id, section_data)
            except Exception as e:
                logger.error(
                    f"{self.widget_name}.on_section_changed (pending): {e}"
                )

        if self._pending_report is not None:
            report_id, report_data = self._pending_report
            self._pending_report = None
            self._loaded_report_id = report_id
            try:
                self.on_report_changed(report_id, report_data)
            except Exception as e:
                logger.error(
                    f"{self.widget_name}.on_report_changed (pending): {e}"
                )

    # ================================================================
    # Override These in Subclasses
    # ================================================================

    def on_well_changed(self, well_id: int, well_data: dict):
        """Called when well selection changes. Override in subclass."""
        pass

    def on_section_changed(self, section_id: int, section_data: dict):
        """Called when section selection changes. Override in subclass."""
        pass

    def on_report_changed(self, report_id: int, report_data: dict):
        """Called when report selection changes. Override in subclass."""
        pass

    def on_selection_cleared(self):
        """Called when all selections are cleared. Override in subclass."""
        pass

    def save_data(self) -> bool:
        """Save current tab data. Override in subclass."""
        return True

    def load_data(self):
        """Load data for current state. Override in subclass."""
        pass

    def refresh(self):
        """Refresh current view. Default: reload data."""
        self.load_data()

    def force_refresh(self):
        """Reload the current context and notify this tab immediately."""
        if self.current_well_id is not None:
            self._loaded_well_id = None
            self._on_well_changed_internal(self.current_well_id, self.current_well_data)
        if self.current_section_id is not None:
            self._loaded_section_id = None
            self._on_section_changed_internal(self.current_section_id, self.current_section_data)
        if self.current_report_id is not None:
            self._loaded_report_id = None
            self._on_report_changed_internal(self.current_report_id, self.current_report_data)
        if self.current_well_id is None:
            self.load_data()

    def cleanup(self):
        """Cleanup on close. Override in subclass."""
        pass

    # ================================================================
    # Guards
    # ================================================================

    def require_well(self) -> bool:
        """
        Check if a well is selected.
        Shows error message if not.
        Returns True if well is selected.
        """
        if not self.current_well_id:
            self.show_error("Please select a well first.")
            return False
        return True

    def require_section(self) -> bool:
        """
        Check if a section is selected.
        Returns True if section is selected.
        """
        if not self.current_section_id:
            self.show_error("Please select a section first.")
            return False
        return True

    def require_report(self) -> bool:
        """
        Check if a report is selected.
        Returns True if report is selected.
        """
        if not self.current_report_id:
            self.show_error("Please select a daily report first.")
            return False
        return True

    # ================================================================
    # Status Messages
    # ================================================================

    def show_error(self, message: str):
        """Show error in MessageBox."""
        QMessageBox.warning(self, "Error", message)

    def show_info(self, message: str):
        """Show info in MessageBox."""
        QMessageBox.information(self, "Info", message)

    def show_message(self, message: str, timeout: int = 3000):
        """Show message in Status Bar."""
        try:
            self.status_manager.show_message(
                self.widget_name, message, timeout
            )
        except Exception:
            logger.info(f"{self.widget_name}: {message}")

    def show_success(self, message: str):
        """Show success message in Status Bar."""
        try:
            self.status_manager.show_success(
                self.widget_name, message
            )
        except Exception:
            logger.info(f"{self.widget_name}: ✅ {message}")

    def show_warning(self, message: str):
        """Show warning in Status Bar."""
        try:
            self.status_manager.show_message(
                self.widget_name, f"⚠️ {message}", 4000
            )
        except Exception:
            logger.warning(f"{self.widget_name}: ⚠️ {message}")

    def show_progress(self, message: str):
        """Show progress message."""
        try:
            self.status_manager.show_progress(
                self.widget_name, message
            )
        except Exception:
            logger.info(f"{self.widget_name}: ⏳ {message}")

    # ================================================================
    # Utilities
    # ================================================================

    def get_well_name(self) -> str:
        """Get current well name - uses cached data first."""
        # ✅ Use cached data, avoid DB query
        if self.current_well_data:
            name = self.current_well_data.get("name")
            if name:
                return name

        # Fallback to DB
        if self.db and self.current_well_id:
            try:
                well = self.db.get_well_by_id(self.current_well_id)
                if well:
                    self.current_well_data = well
                    return well.get("name", "Unknown")
            except Exception:
                pass

        return "No well selected"

    def get_context(self) -> dict:
        """Get current selection context as dict."""
        return {
            "well_id": self.current_well_id,
            "section_id": self.current_section_id,
            "report_id": self.current_report_id,
            "well_data": self.current_well_data,
            "section_data": self.current_section_data,
            "report_data": self.current_report_data,
        }

    def force_refresh(self):
        """
        Force reload regardless of visible state.
        Useful after import.
        """
        ctx = self.sel_manager.get_full_context()
        wid = ctx.get("well_id")
        sid = ctx.get("section_id")
        rid = ctx.get("report_id")

        if wid and wid != self._loaded_well_id:
            self.on_well_changed(wid, ctx.get("well_data") or {})
            self._loaded_well_id = wid

        if sid and sid != self._loaded_section_id:
            self.on_section_changed(sid, ctx.get("section_data") or {})
            self._loaded_section_id = sid

        if rid and rid != self._loaded_report_id:
            self.on_report_changed(rid, ctx.get("report_data") or {})
            self._loaded_report_id = rid