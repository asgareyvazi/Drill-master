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

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal
import logging
from threading import Lock

logger = logging.getLogger(__name__)
# Module-level lock avoids fragile class-attribute edits and protects the
# singleton during concurrent widget construction.
_SELECTION_INSTANCE_LOCK = Lock()


@dataclass(frozen=True)
class ContextSnapshot:
    """M102: one immutable view of the whole selection, emitted with ``context_changed``.

    Ids come from the selection itself; labels come from the payloads the
    selection was made with (``None`` when the payload did not carry them).
    Company and project are taken from the well payload when present; a
    consumer that needs them authoritative resolves them through the database
    relations (``core.selection_context.resolve``). The rig is an attribute of
    the well (``rig_name``); the data model has no rig entity, so there is no
    rig selection. ``period_from``/``period_to`` are an analysis filter that
    survives well switches.
    """

    generation: int = 0
    company_id: Optional[int] = None
    project_id: Optional[int] = None
    well_id: Optional[int] = None
    well_name: Optional[str] = None
    rig_name: Optional[str] = None
    wellbore_id: Optional[int] = None
    wellbore_name: Optional[str] = None
    section_id: Optional[int] = None
    section_name: Optional[str] = None
    report_id: Optional[int] = None
    report_number: Optional[Any] = None
    report_date: Optional[str] = None
    period_from: Optional[str] = None
    period_to: Optional[str] = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


# M124 (D7): the selection fields a consumer can depend on, in hierarchy order.
CONTEXT_FIELDS = ("well_id", "wellbore_id", "section_id", "report_id", "period_from", "period_to")


@dataclass(frozen=True)
class ContextTicket:
    """M124 (D7): the central selection identity a piece of background work was started for.

    ``snapshot`` is the immutable ``ContextSnapshot`` taken on the GUI thread when the work starts;
    ``fields`` names the parts of the selection the work depends on (a trajectory comparison depends
    on the well only, an analysis page on well, wellbore, section and report); ``local`` is the
    consumer's own supersede token (a newer request in the SAME context), kept for that separate
    purpose.  A result is shown only while BOTH are still current, so a result can no longer be
    accepted just because a tab-local counter was not bumped (a hidden tab defers its selection
    handlers; a queued result can arrive after the selection moved).
    """

    snapshot: ContextSnapshot
    fields: tuple = CONTEXT_FIELDS
    local: Any = None

    def identity(self) -> tuple:
        return tuple(getattr(self.snapshot, name) for name in self.fields)

    def stale_reason(self, selection, local: Any = None) -> Optional[str]:
        """``None`` while the work is current, else why its result must not be shown."""
        if local != self.local:
            return "superseded by a newer request"
        if selection is None:
            return None
        current = selection.snapshot()
        changed = [name for name in self.fields if getattr(current, name) != getattr(self.snapshot, name)]
        if changed:
            return "the selection changed (" + ", ".join(name.replace("_id", "").replace("_", " ")
                                                         for name in changed) + ")"
        return None

    def is_current(self, selection, local: Any = None) -> bool:
        return self.stale_reason(selection, local) is None


def _as_date(value, label: str) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):          # a datetime is a date subclass; the period is day-granular
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        raise ValueError(f"{label} must be a date (YYYY-MM-DD), not {value!r}") from None


def _label(data, *keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


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
    period_changed = Signal(object)        # M102: (date_from, date_to) ISO strings, or None
    context_changed = Signal(object)       # M102: ContextSnapshot after every selection change

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
        self._generation = 0   # M83: bumped before every selection signal
        self._period = None    # M102: (date, date) analysis filter, kept across well switches
        self._batch = 0        # M102: select_full_context emits one context_changed at the end
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
        if child_kind == "report" and self._section_id is not None:
            child_section = child_data.get("section_id")
            if child_section is not None and child_section != self._section_id:
                logger.warning("Rejected report from section %s; selected section is %s",
                               child_section, self._section_id)
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
        elif changed or self._well_data is None:
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

            self._generation += 1
            self.well_changed.emit(well_id, self._well_data)
            self._emit_context()
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
        elif changed or self._wellbore_data is None:
            self._wellbore_data = {}

        if changed or data_changed or force:
            # Wellbore changed -> clear section and report
            if changed:
                self._section_id = None
                self._section_data = None
                self._report_id = None
                self._report_data = None

            self._generation += 1
            self.wellbore_changed.emit(wellbore_id, self._wellbore_data)
            self._emit_context()
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
        elif changed or self._section_data is None:
            self._section_data = {}

        if changed or data_changed or force:
            # Section changed -> clear report
            if changed:
                self._report_id = None
                self._report_data = None

            self._generation += 1
            self.section_changed.emit(section_id, self._section_data)
            self._emit_context()
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
        elif changed or self._report_data is None:
            self._report_data = {}

        if changed or data_changed or force:
            self._generation += 1
            self.report_changed.emit(report_id, self._report_data)
            self._emit_context()
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
        self._batch += 1
        try:
            self.select_well(well_id, well_data, force=True)
            if wellbore_id:
                self.select_wellbore(wellbore_id, wellbore_data, force=True)
            if section_id:
                self.select_section(section_id, section_data, force=True)
            if report_id:
                self.select_report(report_id, report_data, force=True)
        finally:
            self._batch -= 1
        self._emit_context()

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
        self._generation += 1
        self.selection_cleared.emit()
        self._emit_context()
        logger.debug("Selection: cleared")

    # ==================== M102: period and context ====================
    def select_period(self, date_from=None, date_to=None) -> None:
        """Set (or with no dates clear) the analysis period; both ends are inclusive.

        A reversed period is refused (``ValueError``); nothing is changed then.
        """
        start, end = _as_date(date_from, "The period start"), _as_date(date_to, "The period end")
        if start and end and start > end:
            raise ValueError(f"The period starts {start} after it ends {end}.")
        period = (start, end) if (start or end) else None
        if period == self._period:
            return
        self._period = period
        self._generation += 1
        self.period_changed.emit(self.current_period)
        self._emit_context()

    @property
    def current_period(self):
        if not self._period:
            return None
        return tuple(d.isoformat() if d else None for d in self._period)

    def snapshot(self) -> ContextSnapshot:
        period = self.current_period or (None, None)
        well, report = self._well_data, self._report_data
        report_date = _label(report, "report_date", "date")
        return ContextSnapshot(
            generation=self._generation,
            company_id=_label(well, "company_id") if self._well_id else None,
            project_id=_label(well, "project_id") if self._well_id else None,
            well_id=self._well_id, well_name=_label(well, "name", "well_name") if self._well_id else None,
            rig_name=_label(well, "rig_name") if self._well_id else None,
            wellbore_id=self._wellbore_id or None,
            wellbore_name=_label(self._wellbore_data, "name") if self._wellbore_id else None,
            section_id=self._section_id or None,
            section_name=_label(self._section_data, "name", "section_name") if self._section_id else None,
            report_id=self._report_id or None,
            report_number=_label(report, "report_number", "report_no") if self._report_id else None,
            report_date=str(report_date)[:10] if self._report_id and report_date else None,
            period_from=period[0], period_to=period[1])

    def _emit_context(self) -> None:
        if self._batch:
            return
        self.context_changed.emit(self.snapshot())

    # ==================== Query Methods ====================
    def context_token(self) -> tuple:
        """M83 context contract for background work.

        Capture the token when a task starts and call ``is_current(token)``
        before showing its result: any selection change in between (another
        well, wellbore, section or report, or a clear) makes the result stale.
        """
        return (self._generation, self._well_id, self._wellbore_id)

    def is_current(self, token) -> bool:
        return tuple(token) == self.context_token()

    @property
    def generation(self) -> int:
        """Bumped before every selection signal (well, wellbore, section, report, clear, period)."""
        return self._generation

    def identity(self, fields=CONTEXT_FIELDS) -> tuple:
        """M124: the current values of ``fields`` (as in ``ContextSnapshot``), for a consumer's own key."""
        snapshot = self.snapshot()
        return tuple(getattr(snapshot, name) for name in fields)

    def ticket(self, fields=CONTEXT_FIELDS, local: Any = None) -> ContextTicket:
        """M124: capture the central identity for background work (see ``ContextTicket``)."""
        unknown = [name for name in fields if name not in CONTEXT_FIELDS]
        if unknown:
            raise ValueError(f"Unknown selection field(s): {', '.join(unknown)}")
        return ContextTicket(self.snapshot(), tuple(fields), local)

    def wellbore_for(self, well_id, db=None) -> Optional[int]:
        """The selected wellbore when it belongs to ``well_id`` (M70.7), else ``None``.

        Consumers that persist records (plans, calculation cases) use this so a
        stale wellbore of another well is never attached to a new record. With
        ``db`` the wellbore is also confirmed in the database being written.
        ``wellbore_changed`` carries ``0`` for "no wellbore"; that is ``None`` here.
        """
        if not well_id or self._well_id != well_id or not self._wellbore_id:
            return None
        owner = (self._wellbore_data or {}).get("well_id") if isinstance(self._wellbore_data, dict) else None
        if owner not in (None, well_id):
            return None
        if db is not None and callable(getattr(db, "session_scope", None)):
            # The record is written to ``db``: the wellbore must exist there, on this well.
            from core.database import Wellbore
            with db.session_scope() as session:
                row = session.get(Wellbore, int(self._wellbore_id))
                if row is None or row.well_id != well_id:
                    return None
        return self._wellbore_id


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