"""M286: workbench actions on calculation-history records - clone, archive and restore.

The workbench already compares (``calculation_history.full_field_compare``), re-runs with MATCH / DIFFERENT /
NOT_REPRODUCIBLE / UNREADABLE (``recalculate_entry``) and stores a re-run as a linked case
(``save_recalculation``). This module adds the two remaining actions for **every** history source:

* **Clone** stores a NEW calculation case with the record's exact inputs and stored results, linked
  ``clone_of``. The clone keeps the original's method and version, because nothing was recalculated. It is
  labelled as a copy, and the original is never written. A case delegates to the existing M87 ``clone_case``.
* **Archive / restore** are append-only events (``calculation_archive_marks``). Each needs a reason and writes a
  mandatory audit record in the same transaction. Archiving hides a record from the default list only; it
  stays readable, comparable, re-runnable and citable, and nothing is deleted.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ARCHIVE, RESTORE = "ARCHIVE", "RESTORE"
ARCHIVED, ACTIVE = "ARCHIVED", "ACTIVE"
CLONE_STATUS = "CLONE"


class WorkbenchError(ValueError):
    """A workbench action was refused; the message says why. Nothing was written."""


def archived_ids(session, tables: Optional[Iterable[str]] = None) -> Dict[str, Set[int]]:
    """``{table: {record ids}}`` of the records whose LATEST mark is ARCHIVE (inside the caller's session).

    A mark counts only while its source row exists with the ``created_at`` it had when it was marked: SQLite can
    reuse the id of a deleted row, and a new record must not inherit the old record's archive state.
    """
    from core.database import CalculationArchiveMark as Mark

    query = (session.query(Mark.source_table, Mark.source_id, Mark.source_created_at, Mark.action)
             .order_by(Mark.id.asc()))
    if tables is not None:
        query = query.filter(Mark.source_table.in_(list(tables)))
    marks = query.all()
    born: Dict[Tuple[str, int], Any] = {}
    for table in {m.source_table for m in marks}:
        ids = {m.source_id for m in marks if m.source_table == table}
        born.update({(table, record_id): created for record_id, created in _created_at(session, table, ids)})
    latest: Dict[Tuple[str, int], str] = {}
    for table, record_id, snapshot, action in marks:
        key = (table, record_id)
        if key in born and born[key] == snapshot:      # the same row that was marked (not a reused id)
            latest[key] = action                       # ordered by id: the last mark wins
    out: Dict[str, Set[int]] = {}
    for (table, record_id), action in latest.items():
        if action == ARCHIVE:
            out.setdefault(table, set()).add(record_id)
    return out


def _created_at(session, table: str, ids) -> List[Tuple[int, Any]]:
    """``(id, created_at)`` of the existing rows of ``table`` among ``ids`` (None when it has no created_at)."""
    from core.database import Base

    model = {mapper.class_.__tablename__: mapper.class_ for mapper in Base.registry.mappers}.get(table)
    if model is None:
        return []
    created = getattr(model, "created_at", None)
    if created is None:
        return [(row_id, None) for (row_id,) in session.query(model.id).filter(model.id.in_(list(ids)))]
    return [(row_id, stamp) for row_id, stamp in session.query(model.id, created).filter(model.id.in_(list(ids)))]


def state(db, entry) -> str:
    """ARCHIVED or ACTIVE for one history entry."""
    with db.session_scope() as session:
        return ARCHIVED if entry.record_id in archived_ids(session, [entry.table]).get(entry.table, set()) \
            else ACTIVE


def history_of(db, entry) -> list:
    """Every archive / restore mark of an entry, oldest first (the audit trail shown in the workbench)."""
    from core.database import CalculationArchiveMark as Mark

    with db.session_scope() as session:
        rows = (session.query(Mark).filter(Mark.source_table == entry.table, Mark.source_id == entry.record_id)
                .order_by(Mark.id.asc()).all())
        return [{"id": r.id, "action": r.action, "reason": r.reason, "created_by": r.created_by,
                 "created_at": r.created_at} for r in rows]


def _mark(db, entry, action: str, reason: str, *, user_id: Optional[int]) -> Dict[str, Any]:
    from core.calculation_cases import _source_row
    from core.database import CalculationArchiveMark as Mark

    reason = str(reason or "").strip()
    if not reason:
        raise WorkbenchError(f"A reason is required to {action.lower()} a calculation record.")
    with db.session_scope() as session:
        source = _source_row(session, entry.table, entry.record_id)
        if source is None:
            raise WorkbenchError(f"{entry.table}:{entry.record_id} does not exist.")
        current = ARCHIVED if entry.record_id in archived_ids(session, [entry.table]).get(entry.table, set()) \
            else ACTIVE
        if action == ARCHIVE and current == ARCHIVED:
            raise WorkbenchError(f"{entry.table}:{entry.record_id} is already archived.")
        if action == RESTORE and current == ACTIVE:
            raise WorkbenchError(f"{entry.table}:{entry.record_id} is not archived.")
        row = Mark(source_table=entry.table, source_id=entry.record_id,
                   source_created_at=getattr(source, "created_at", None), well_id=getattr(source, "well_id", None),
                   action=action, reason=reason, created_by=user_id)
        session.add(row)
        session.flush()
        db._add_mandatory_audit(session, f"CALCULATION_{action}", entry.table, entry.record_id,
                                entry.name, f"{action.lower()} {entry.table}:{entry.record_id}: {reason}")
        return {"id": row.id, "action": action, "state": ARCHIVED if action == ARCHIVE else ACTIVE,
                "source_table": entry.table, "source_id": entry.record_id, "reason": reason}


def archive(db, entry, reason: str, *, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Archive one record: hidden from the default list, nothing deleted or changed. Needs a reason."""
    return _mark(db, entry, ARCHIVE, reason, user_id=user_id)


def restore(db, entry, reason: str, *, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Restore an archived record to the default list. Needs a reason."""
    return _mark(db, entry, RESTORE, reason, user_id=user_id)


def clone(db, entry, name: Optional[str] = None, *, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store a NEW case with the record's exact inputs and stored results, linked ``clone_of``.

    The original's method and version are kept and the copy is labelled as not recalculated. A record whose
    inputs cannot be read is refused rather than cloned empty.
    """
    from core import calculation_cases as cc

    name = str(name or "").strip() or f"{entry.name} (clone)"
    if not isinstance(entry.inputs, dict) or not entry.inputs:
        raise WorkbenchError(f"{entry.key} has no readable inputs; it cannot be cloned.")
    if entry.table == "calculation_cases":
        return cc.clone_case(db, cc.get_case(db, entry.record_id), name, user_id=user_id)
    results = entry.full_results or entry.results or {}
    return cc.save_case(
        db, calculator=f"{entry.source} (clone)", name=name, inputs=entry.inputs, results=results,
        method=entry.method or entry.source, method_version=entry.version, well_id=entry.well_id,
        wellbore_id=entry.wellbore_id, user_id=user_id,
        note=f"Clone of {entry.key} ({entry.version}): inputs and stored results copied unchanged, not recalculated",
        source_link={"link_type": "clone_of", "source_table": entry.table, "source_id": entry.record_id,
                     "source_method": entry.method, "source_method_version": entry.version,
                     "verification_status": CLONE_STATUS, "method_changed": False})
