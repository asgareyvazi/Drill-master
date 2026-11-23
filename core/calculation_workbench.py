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
    reuse the id of a deleted row, and a new record must not inherit the old record's archive state. M365 (D87):
    a mark that carries a content fingerprint also needs the row's current fingerprint to be equal, which closes
    the equal-timestamp and NULL-timestamp cases. Pre-M365 marks (no fingerprint) keep the timestamp rule.
    """
    from core.database import CalculationArchiveMark as Mark

    query = (session.query(Mark.source_table, Mark.source_id, Mark.source_created_at, Mark.action,
                           Mark.source_fingerprint).order_by(Mark.id.asc()))
    if tables is not None:
        query = query.filter(Mark.source_table.in_(list(tables)))
    marks = query.all()
    born: Dict[Tuple[str, int], Any] = {}
    prints: Dict[Tuple[str, int], Optional[str]] = {}
    for table in {m.source_table for m in marks}:
        ids = {m.source_id for m in marks if m.source_table == table}
        for record_id, created, fp in _identity(session, table, ids):
            born[(table, record_id)] = created
            prints[(table, record_id)] = fp
    latest: Dict[Tuple[str, int], str] = {}
    for table, record_id, snapshot, action, stored_fp in marks:
        key = (table, record_id)
        if key not in born or born[key] != snapshot:     # deleted, or a reused id with another timestamp
            continue
        if stored_fp is not None and prints.get(key) != stored_fp:
            continue                                     # M365: same id and timestamp, different record
        latest[key] = action                             # ordered by id: the last mark wins
    out: Dict[str, Set[int]] = {}
    for (table, record_id), action in latest.items():
        if action == ARCHIVE:
            out.setdefault(table, set()).add(record_id)
    return out


def _identity(session, table: str, ids) -> List[Tuple[int, Any, Optional[str]]]:
    """``(id, created_at, fingerprint)`` of the existing rows of ``table`` among ``ids``."""
    from core import record_identity
    from core.database import Base

    model = {mapper.class_.__tablename__: mapper.class_ for mapper in Base.registry.mappers}.get(table)
    if model is None:
        return []
    rows = session.query(model).filter(model.id.in_(list(ids))).all()
    return [(row.id, getattr(row, "created_at", None), record_identity.fingerprint(table, row)) for row in rows]


def _created_at(session, table: str, ids) -> List[Tuple[int, Any]]:
    """``(id, created_at)`` of the existing rows of ``table`` among ``ids`` (None when it has no created_at)."""
    return [(record_id, created) for record_id, created, _fp in _identity(session, table, ids)]


def identity_basis(table: str, source) -> Optional[str]:
    """How a new mark would pin ``source``: CONTENT_PINNED, TIMESTAMP_ONLY, or None when it cannot be pinned."""
    from core import record_identity

    if record_identity.fingerprint(table, source) is not None:
        return record_identity.CONTENT_PINNED
    if hasattr(type(source), "created_at") and getattr(source, "created_at", None) is None:
        return None
    return record_identity.TIMESTAMP_ONLY


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
    from core import record_identity
    from core.calculation_cases import _source_row
    from core.database import CalculationArchiveMark as Mark

    reason = str(reason or "").strip()
    if not reason:
        raise WorkbenchError(f"A reason is required to {action.lower()} a calculation record.")
    auth = getattr(db, "_authorization", None)        # M365: refuse before reading (the data layer also refuses)
    if auth is not None:
        from core.authorization import authorize_change

        authorize_change(auth, "calculation_archive_marks", "insert")     # raises AuthorizationError
    with db.session_scope() as session:
        source = _source_row(session, entry.table, entry.record_id)
        if source is None:
            raise WorkbenchError(f"{entry.table}:{entry.record_id} does not exist.")
        current = ARCHIVED if entry.record_id in archived_ids(session, [entry.table]).get(entry.table, set()) \
            else ACTIVE
        if action == ARCHIVE and identity_basis(entry.table, source) is None:
            # M304 (D87 review): without a creation time and without a content fingerprint contract a later record
            # that reuses the id would inherit the archive state, so the mark is refused instead of being weak.
            # M365: a table with a fingerprint contract is pinned by content, so a NULL created_at is allowed.
            raise WorkbenchError(f"{entry.table}:{entry.record_id} has no creation time, so its identity cannot "
                                 f"be pinned against id reuse; archiving it is refused.")
        if action == ARCHIVE and current == ARCHIVED:
            raise WorkbenchError(f"{entry.table}:{entry.record_id} is already archived.")
        if action == RESTORE and current == ACTIVE:
            raise WorkbenchError(f"{entry.table}:{entry.record_id} is not archived.")
        row = Mark(source_table=entry.table, source_id=entry.record_id,
                   source_created_at=getattr(source, "created_at", None), well_id=getattr(source, "well_id", None),
                   source_fingerprint=record_identity.fingerprint(entry.table, source),
                   action=action, reason=reason, created_by=user_id)
        session.add(row)
        session.flush()
        db._add_mandatory_audit(session, f"CALCULATION_{action}", entry.table, entry.record_id,
                                entry.name, f"{action.lower()} {entry.table}:{entry.record_id}: {reason}")
        return {"id": row.id, "action": action, "state": ARCHIVED if action == ARCHIVE else ACTIVE,
                "source_table": entry.table, "source_id": entry.record_id, "reason": reason,
                "identity": identity_basis(entry.table, source)}


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
    from core.calculation_clone_contract import clone_check

    name = str(name or "").strip() or f"{entry.name} (clone)"
    allowed, reason = clone_check(entry, db)          # M303: the adapter matrix refuses an invalid clone
    if not allowed:
        raise WorkbenchError(reason)
    if entry.table == "calculation_cases":
        return cc.clone_case(db, cc.get_case(db, entry.record_id), name, user_id=user_id)
    results = entry.full_results or entry.results or {}
    return cc.save_case(
        db, calculator=f"{entry.source} (clone)", name=name, inputs=entry.inputs, results=results,
        method=entry.method or entry.source, method_version=entry.version, well_id=entry.well_id,
        wellbore_id=entry.wellbore_id, user_id=user_id,
        note=(f"Clone of {entry.key} ({entry.version}; scope {entry.scope}): inputs and stored results copied "
              f"unchanged, not recalculated, not approved"),
        source_link={"link_type": "clone_of", "source_table": entry.table, "source_id": entry.record_id,
                     "source_method": entry.method, "source_method_version": entry.version,
                     "verification_status": CLONE_STATUS, "method_changed": False})


# -- M305: bulk archive / restore ---------------------------------------------------------------------------
BULK_CONTRACT = "PER_ROW"   # each row is its own transaction (mark + mandatory audit); refused rows write nothing
WILL, SKIP, REFUSE = "WILL", "SKIP", "REFUSE"
DONE, SKIPPED, REFUSED, FAILED = "DONE", "SKIPPED", "REFUSED", "FAILED"


def _authorized(db) -> Optional[str]:
    """None when the current principal may insert archive marks, else the refusal text (nothing is written)."""
    from core.authorization import AuthorizationError, authorize_change

    state = getattr(db, "_authorization", None)
    if state is None:
        return None
    try:
        authorize_change(state, "calculation_archive_marks", "insert")
    except AuthorizationError as exc:
        return f"not authorized: {exc}"
    return None


def bulk_preview(db, entries: Iterable[Any], action: str) -> Dict[str, Any]:
    """What a bulk ARCHIVE or RESTORE would do, row by row, without writing anything.

    Each row is ``WILL`` (it will be marked), ``SKIP`` (already in the requested state) or ``REFUSE`` (with the
    reason, e.g. no creation time or the record no longer exists). An unauthorized user gets every row refused.
    """
    from core.calculation_cases import _source_row

    if action not in (ARCHIVE, RESTORE):
        raise WorkbenchError(f"Unknown bulk action {action!r}.")
    entries = list(entries)
    denied = _authorized(db)
    rows: List[Dict[str, Any]] = []
    with db.session_scope() as session:
        archived = archived_ids(session, {e.table for e in entries}) if entries else {}
        for entry in entries:
            row = {"key": entry.key, "name": entry.name, "table": entry.table, "record_id": entry.record_id}
            current = ARCHIVED if entry.record_id in archived.get(entry.table, set()) else ACTIVE
            row["current"] = current
            source = _source_row(session, entry.table, entry.record_id)
            if denied:
                row.update(plan=REFUSE, reason=denied)
            elif source is None:
                row.update(plan=REFUSE, reason="the record no longer exists")
            elif (action == ARCHIVE and current == ARCHIVED) or (action == RESTORE and current == ACTIVE):
                row.update(plan=SKIP, reason=f"already {current.lower()}")
            elif action == ARCHIVE and identity_basis(entry.table, source) is None:
                row.update(plan=REFUSE, reason="no creation time: identity cannot be pinned against id reuse")
            else:
                row.update(plan=WILL, reason="", identity=identity_basis(entry.table, source))
            rows.append(row)
    seen: Set[str] = set()
    for row in rows:                                   # the same record twice in one batch is marked once
        if row["key"] in seen and row["plan"] == WILL:
            row.update(plan=SKIP, reason="listed twice in this batch")
        seen.add(row["key"])
    counts = {plan: sum(1 for r in rows if r["plan"] == plan) for plan in (WILL, SKIP, REFUSE)}
    return {"action": action, "contract": BULK_CONTRACT, "rows": rows, "counts": counts,
            "authorized": denied is None}


def bulk_apply(db, entries: Iterable[Any], action: str, reason: str, *,
               user_id: Optional[int] = None) -> Dict[str, Any]:
    """Apply a bulk ARCHIVE or RESTORE with one reason. PER_ROW: each WILL row gets its own mark + audit
    transaction; a row that fails is reported (FAILED) and the others keep their result. ``partial`` is True
    whenever at least one requested row did not end DONE or SKIPPED."""
    reason = str(reason or "").strip()
    if not reason:
        raise WorkbenchError(f"A reason is required to {action.lower()} calculation records.")
    entries = list(entries)
    preview = bulk_preview(db, entries, action)
    if not preview["authorized"]:
        raise WorkbenchError(f"Bulk {action.lower()} refused: {preview['rows'][0]['reason'] if preview['rows'] else ''}")
    by_key = {e.key: e for e in entries}
    results: List[Dict[str, Any]] = []
    for row in preview["rows"]:
        out = {k: row[k] for k in ("key", "name", "table", "record_id")}
        if row["plan"] == SKIP:
            out.update(status=SKIPPED, detail=row["reason"])
        elif row["plan"] == REFUSE:
            out.update(status=REFUSED, detail=row["reason"])
        else:
            try:
                mark = _mark(db, by_key[row["key"]], action, reason, user_id=user_id)
                out.update(status=DONE, detail=f"mark #{mark['id']}")
            except WorkbenchError as exc:
                out.update(status=REFUSED, detail=str(exc))
            except Exception as exc:  # silent-ok: reported per row as FAILED; that row's transaction rolled back
                out.update(status=FAILED, detail=f"{type(exc).__name__}: {exc}")
        results.append(out)
    counts = {s: sum(1 for r in results if r["status"] == s) for s in (DONE, SKIPPED, REFUSED, FAILED)}
    partial = bool(counts[REFUSED] or counts[FAILED]) and bool(counts[DONE])
    return {"action": action, "contract": BULK_CONTRACT, "reason": reason, "rows": results, "counts": counts,
            "partial": partial, "message": bulk_message(action, counts, partial)}


def bulk_message(action: str, counts: Dict[str, int], partial: bool) -> str:
    verb = "Archived" if action == ARCHIVE else "Restored"
    text = f"{verb} {counts[DONE]} record(s)"
    extras = [f"{counts[SKIPPED]} skipped"] if counts[SKIPPED] else []
    if counts[REFUSED]:
        extras.append(f"{counts[REFUSED]} refused")
    if counts[FAILED]:
        extras.append(f"{counts[FAILED]} NOT SAVED (storage error)")
    text += (" (" + ", ".join(extras) + ")" if extras else "") + "."
    if partial:
        text = "PARTIAL: " + text + " Rows that were done stay done; see the per-row status."
    return text + " Nothing was deleted or changed."
