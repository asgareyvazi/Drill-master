# core/selection_manager.py
"""
Central Selection Manager
=========================
Keeps track of current well, section, report
and notifies all registered tabs via Qt signals.

Usage:
    sel = SelectionManager()
    sel.well_changed.connect(my_tab.on_well_changed)
    sel.select_well(well_id, well_data)
"""

from PySide6.QtCore import QObject, Signal
import logging
from threading import Lock

logger = logging.getLogger(__name__)
# Module-level lock avoids fragile class-attribute edits and protects the
# singleton during concurrent widget construction.
_SELECTION_INSTANCE_LOCK = Lock()


class SelectionManager(QObject):
    """
    Central Selection Manager (Singleton)

    Signals:
        well_changed(int, object)     - well_id, well_data
        section_changed(int, object)  - section_id, section_data
        report_changed(int, object)   - report_id, report_data
        selection_cleared()           - everything cleared
    """

    well_changed = Signal(int, object)
    section_changed = Signal(int, object)
    report_changed = Signal(int, object)
    selection_cleared = Signal()

    _instance = None
    _instance_lock = Lock()

    def __new__(cls, *args, **kwargs):
        # QObject singletons must only be constructed once.  In particular,
        # calling SelectionManager(parent) a second time must not attempt to
        # re-parent an already constructed QObject.
        with _SELECTION_INSTANCE_LOCK:
            if getattr(cls, "_instance", None) is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, parent=None):
        if getattr(self, '_initialized', False):
            return
        super().__init__(parent)
        self._well_id = None
        self._section_id = None
        self._report_id = None
        self._well_data = None
        self._section_data = None
        self._report_data = None
        self._initialized = True

    # ==================== Properties ====================

    @property
    def current_well_id(self) -> int:
        return self._well_id

    @property
    def current_section_id(self) -> int:
        return self._section_id

    @property
    def current_report_id(self) -> int:
        return self._report_id

    @property
    def current_well_data(self) -> dict:
        return self._well_data

    @property
    def current_section_data(self) -> dict:
        return self._section_data

    @property
    def current_report_data(self) -> dict:
        return self._report_data

    # ==================== Selection Methods ====================

    def select_well(
        self, well_id: int, well_data: dict = None, force: bool = False
    ):
        """
        Select a well and notify all listeners.

        Args:
            well_id: Well ID
            well_data: Well data dict (optional)
            force: Force emit even if same ID
        """
        changed = well_id != self._well_id
        data_changed = well_data is not None and well_data != self._well_data
        self._well_id = well_id
        if well_data is not None:
            self._well_data = well_data
        elif self._well_data is None:
            self._well_data = {}

        # A refresh with the same id is still a meaningful update (notably
        # after Excel import), and an explicit None must not suppress it.
        if changed or data_changed or force:
            # Well changed -> clear section and report
            if changed:
                self._section_id = None
                self._section_data = None
                self._report_id = None
                self._report_data = None

            self.well_changed.emit(well_id, self._well_data)
            logger.debug(f"Selection: well → {well_id}")

    def select_section(
        self, section_id: int, section_data: dict = None, force: bool = False
    ):
        """
        Select a section and notify all listeners.

        Args:
            section_id: Section ID
            section_data: Section data dict (optional)
            force: Force emit even if same ID
        """
        changed = section_id != self._section_id
        data_changed = section_data is not None and section_data != self._section_data
        self._section_id = section_id
        if section_data is not None:
            self._section_data = section_data
        elif self._section_data is None:
            self._section_data = {}

        if changed or data_changed or force:
            # Section changed -> clear report
            if changed:
                self._report_id = None
                self._report_data = None

            self.section_changed.emit(section_id, self._section_data)
            logger.debug(f"Selection: section → {section_id}")

    def select_report(
        self, report_id: int, report_data: dict = None, force: bool = False
    ):
        """
        Select a report and notify all listeners.

        Args:
            report_id: Report ID
            report_data: Report data dict (optional)
            force: Force emit even if same ID
        """
        changed = report_id != self._report_id
        data_changed = report_data is not None and report_data != self._report_data
        self._report_id = report_id
        if report_data is not None:
            self._report_data = report_data
        elif self._report_data is None:
            self._report_data = {}

        if changed or data_changed or force:
            self.report_changed.emit(report_id, self._report_data)
            logger.debug(f"Selection: report → {report_id}")

    def select_full_context(
        self,
        well_id: int,
        section_id: int,
        report_id: int,
        well_data: dict = None,
        section_data: dict = None,
        report_data: dict = None,
    ):
        """
        Select well + section + report in one call.
        Useful after import to set everything at once.
        Emits signals in correct order: well → section → report
        """
        self.select_well(well_id, well_data, force=True)
        if section_id:
            self.select_section(section_id, section_data, force=True)
        if report_id:
            self.select_report(report_id, report_data, force=True)

    def clear(self):
        """Clear all selections and notify listeners."""
        self._well_id = None
        self._section_id = None
        self._report_id = None
        self._well_data = None
        self._section_data = None
        self._report_data = None
        self.selection_cleared.emit()
        logger.debug("Selection: cleared")

    # ==================== Query Methods ====================

    def has_well(self) -> bool:
        return self._well_id is not None

    def has_section(self) -> bool:
        return self._section_id is not None

    def has_report(self) -> bool:
        return self._report_id is not None

    def get_full_context(self) -> dict:
        """Get complete selection state as dict."""
        return {
            "well_id": self._well_id,
            "well_data": self._well_data,
            "section_id": self._section_id,
            "section_data": self._section_data,
            "report_id": self._report_id,
            "report_data": self._report_data,
        }

    def __repr__(self) -> str:
        return (
            f"SelectionManager("
            f"well={self._well_id}, "
            f"section={self._section_id}, "
            f"report={self._report_id})"
        )