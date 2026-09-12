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
        wellbore_changed(int, object) - wellbore_id, wellbore_data
        section_changed(int, object)  - section_id, section_data
        report_changed(int, object)   - report_id, report_data
        selection_cleared()           - everything cleared

    Cascade (Schema v3 hierarchy Well → Wellbore → Section → Report):
        select_well     -> clears wellbore, section, report
        select_wellbore -> clears section, report
        select_section  -> clears report
        select_report   -> clears nothing below it
    """

    well_changed = Signal(int, object)
    wellbore_changed = Signal(int, object)
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
        self._wellbore_id = None
        self._section_id = None
        self._report_id = None
        self._well_data = None
        self._wellbore_data = None
        self._section_data = None
        self._report_data = None
        self._initialized = True

    # ==================== Properties ====================

    @property
    def current_well_id(self) -> int:
        return self._well_id

    @property
    def current_wellbore_id(self) -> int:
        return self._wellbore_id

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
    def current_wellbore_data(self) -> dict:
        return self._wellbore_data

    @property
    def current_section_data(self) -> dict:
        return self._section_data

    @property
    def current_report_data(self) -> dict:
        return self._report_data

    # ==================== Selection Methods ====================

    def _ownership_conflict(self, child_data, child_kind: str) -> bool:
        """Detect a child selection that belongs to a different well.

        A selection context like ``well = A, section = B`` where B belongs to
        well C is incoherent. When the child payload carries an explicit
        ``well_id`` that contradicts the currently selected well, the
        selection is rejected (logged) instead of silently accepted.
        Payloads without ``well_id`` cannot be checked and pass through —
        the guard is defensive, not a new API requirement.
        """
        if not isinstance(child_data, dict):
            return False
        if self._well_id is not None:
            child_well = child_data.get("well_id")
            if child_well is not None and child_well != self._well_id:
                logger.warning(
                    "Rejected %s selection %s: belongs to well %s, but well %s "
                    "is selected",
                    child_kind,
                    child_data.get("id"),
                    child_well,
                    self._well_id,
                )
                return True
        # A wellbore, once selected, is also an ownership boundary: a section
        # or report explicitly tagged with a different wellbore is incoherent.
        if self._wellbore_id is not None:
            child_wellbore = child_data.get("wellbore_id")
            if child_wellbore is not None and child_wellbore != self._wellbore_id:
                logger.warning(
                    "Rejected %s selection %s: belongs to wellbore %s, but "
                    "wellbore %s is selected",
                    child_kind,
                    child_data.get("id"),
                    child_wellbore,
                    self._wellbore_id,
                )
                return True
        return False

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
            # Well changed -> clear wellbore, section and report
            if changed:
                self._wellbore_id = None
                self._wellbore_data = None
                self._section_id = None
                self._section_data = None
                self._report_id = None
                self._report_data = None

            self.well_changed.emit(well_id, self._well_data)
            logger.debug(f"Selection: well → {well_id}")

    def select_wellbore(
        self, wellbore_id: int, wellbore_data: dict = None, force: bool = False
    ):
        """
        Select a wellbore and notify all listeners.

        A wellbore belongs to the currently selected well. Selecting a
        different wellbore clears the section and report below it. A wellbore
        payload whose ``well_id`` contradicts the selected well is rejected.

        Args:
            wellbore_id: Wellbore ID
            wellbore_data: Wellbore data dict (optional)
            force: Force emit even if same ID
        """
        if self._ownership_conflict(wellbore_data, "wellbore"):
            return
        changed = wellbore_id != self._wellbore_id
        data_changed = (
            wellbore_data is not None and wellbore_data != self._wellbore_data
        )
        self._wellbore_id = wellbore_id
        if wellbore_data is not None:
            self._wellbore_data = wellbore_data
        elif self._wellbore_data is None:
            self._wellbore_data = {}

        if changed or data_changed or force:
            # Wellbore changed -> clear section and report
            if changed:
                self._section_id = None
                self._section_data = None
                self._report_id = None
                self._report_data = None

            self.wellbore_changed.emit(wellbore_id, self._wellbore_data)
            logger.debug(f"Selection: wellbore → {wellbore_id}")

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
        if self._ownership_conflict(section_data, "section"):
            return
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
        if self._ownership_conflict(report_data, "report"):
            return
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
        wellbore_id: int = None,
        wellbore_data: dict = None,
    ):
        """
        Select well + wellbore + section + report in one call.
        Useful after import to set everything at once.
        Emits signals in correct order: well → wellbore → section → report

        ``wellbore_id`` is keyword-only-by-position optional so existing
        callers that pass (well, section, report) keep working unchanged.
        """
        self.select_well(well_id, well_data, force=True)
        if wellbore_id:
            self.select_wellbore(wellbore_id, wellbore_data, force=True)
        if section_id:
            self.select_section(section_id, section_data, force=True)
        if report_id:
            self.select_report(report_id, report_data, force=True)

    def clear(self):
        """Clear all selections and notify listeners."""
        self._well_id = None
        self._wellbore_id = None
        self._section_id = None
        self._report_id = None
        self._well_data = None
        self._wellbore_data = None
        self._section_data = None
        self._report_data = None
        self.selection_cleared.emit()
        logger.debug("Selection: cleared")

    # ==================== Query Methods ====================

    def has_well(self) -> bool:
        return self._well_id is not None

    def has_wellbore(self) -> bool:
        return self._wellbore_id is not None

    def has_section(self) -> bool:
        return self._section_id is not None

    def has_report(self) -> bool:
        return self._report_id is not None

    def get_full_context(self) -> dict:
        """Get complete selection state as dict."""
        return {
            "well_id": self._well_id,
            "well_data": self._well_data,
            "wellbore_id": self._wellbore_id,
            "wellbore_data": self._wellbore_data,
            "section_id": self._section_id,
            "section_data": self._section_data,
            "report_id": self._report_id,
            "report_data": self._report_data,
        }

    def __repr__(self) -> str:
        return (
            f"SelectionManager("
            f"well={self._well_id}, "
            f"wellbore={self._wellbore_id}, "
            f"section={self._section_id}, "
            f"report={self._report_id})"
        )