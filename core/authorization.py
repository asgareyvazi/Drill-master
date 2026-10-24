"""Data-layer authorization for every ORM mutation (M43).

UI slots are guarded by ``core.permissions.require_permission``; this module
enforces the same role model where the data is written, so a missed UI guard,
a direct service call or a new code path cannot mutate data the signed-in
principal is not allowed to change.

How it works
------------
* ``DatabaseManager.enforce_authorization(principal)`` turns enforcement on for
  that manager (the application does this right after login). The principal is
  any object with ``has_permission(name)`` and ``user_id``/``username`` - in
  the application the ``core.permissions.permissions`` singleton.
* A ``before_flush`` hook checks every inserted, updated and deleted mapped
  object against :data:`TABLE_POLICY`; a ``do_orm_execute`` hook checks ORM
  bulk ``update()``/``delete()`` statements and rejects textual DML.
  Raw DBAPI writes bypass both hooks; ``tests/test_data_layer_authorization.py``
  fails if one appears outside the reviewed system modules.
* Operations whose own code already authorizes a narrower action declare it
  with :func:`operation_scope` (report lifecycle, import) and system
  bookkeeping runs in :func:`system_scope` (bootstrap, login throttling,
  default-content seeding). Scopes are per thread/task (``contextvars``).
* Unknown tables are denied: every mapped table must have a policy entry
  (enforced by a completeness test), so adding a model without deciding who
  may write it fails the suite.
* Denials raise :class:`AuthorizationError` (a ``PermissionError``) with a
  generic message and are written to ``audit_logs`` after the failed
  transaction ends.

A manager without ``enforce_authorization`` (library use, tests, maintenance
scripts with direct file access) is not restricted: whoever can run Python
against the SQLite file can already modify it. See ``docs/SECURITY_MODEL.md``.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
import threading
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

EDIT = "can_edit_reports"
DELETE_REPORTS = "can_delete_reports"
CREATE_WELL = "can_create_well"
DELETE_WELL = "can_delete_well"
MANAGE_USERS = "can_manage_users"
IMPORT = "can_import"
APPROVE = "can_approve_reports"

ANY_PRINCIPAL = "<authenticated>"
NOBODY = "<denied>"


@dataclass(frozen=True)
class TablePolicy:
    """Permissions (any one suffices) required per kind of change."""
    write: tuple[str, ...]
    delete: tuple[str, ...]
    insert: Optional[tuple[str, ...]] = None  # defaults to ``write``

    def required(self, operation: str) -> tuple[str, ...]:
        if operation == "delete":
            return self.delete
        if operation == "insert" and self.insert is not None:
            return self.insert
        return self.write


# Report-scoped operational data: edited with can_edit_reports (the UI's
# DrillTabBase.save_data / require_permission contract), deleted with
# can_delete_reports; can_delete_well also covers rows removed when a whole
# well (and everything under it) is deleted.
_REPORT_DATA = TablePolicy(write=(EDIT,), delete=(DELETE_REPORTS, DELETE_WELL))
# Company/project/well/wellbore: created with can_create_well (New*Dialog),
# deleted with can_delete_well (core.hierarchy_operations).
_HIERARCHY = TablePolicy(write=(CREATE_WELL,), delete=(DELETE_WELL,))

_REPORT_TABLES = (
    "activity_codes", "bha_reports", "bit_reports", "bop_components", "bulk_materials",
    "casing_calculations", "casing_reports", "cement_calculations", "cement_reports",
    "cost_records", "daily_reports", "downhole_equipment", "drilling_parameters",
    "equipment_logs", "export_templates", "formation_reports", "fuel_water_inventory",
    "inventory_items", "logistics_personnel", "material_requests", "mse_calculations",
    "mud_reports", "mud_volume_calculations", "npt_reports", "operational_procedures",
    "pjsm_records", "planned_activities", "procedure_approvals", "procedure_checklists",
    "procedure_steps", "procedure_templates", "rop_analysis", "safety_incidents",
    "safety_reports", "sections", "service_companies", "service_company_pob",
    "service_notes", "seven_days_lookahead", "survey_points", "time_depth_data",
    "time_logs_24h", "time_logs_morning", "torque_drag_calculations",
    "trajectory_calculations", "trajectory_plots", "transport_logs", "transport_notes",
    "trip_sheet_entries", "waste_records", "well_control_kill_sheet_calculations",
    "well_plans", "wellbore_schematics",
)

TABLE_POLICY: dict[str, TablePolicy] = {
    **{name: _REPORT_DATA for name in _REPORT_TABLES},
    **{name: _HIERARCHY for name in ("companies", "projects", "wells", "wellbores")},
    "users": TablePolicy(write=(MANAGE_USERS,), delete=(MANAGE_USERS,)),
    # Reference catalog rows are only written by the catalog import.
    "drill_pipe_specs": TablePolicy(write=(IMPORT,), delete=(MANAGE_USERS,)),
    # Audit records are append-only for every signed-in principal.
    "audit_logs": TablePolicy(write=(NOBODY,), delete=(NOBODY,), insert=(ANY_PRINCIPAL,)),
    # Lifecycle records are written by transition_report (operation scope);
    # they leave only with their report.
    "approval_actions": TablePolicy(write=(NOBODY,), delete=(DELETE_REPORTS, DELETE_WELL), insert=(NOBODY,)),
    "report_revisions": TablePolicy(write=(NOBODY,), delete=(DELETE_REPORTS, DELETE_WELL), insert=(NOBODY,)),
    # Document library (M44): written only by the reviewed document import.
    "documents": TablePolicy(write=(IMPORT,), delete=(IMPORT,)),
    "document_pages": TablePolicy(write=(IMPORT,), delete=(IMPORT,)),
    # Login throttling state is system bookkeeping only.
    "login_throttle": TablePolicy(write=(NOBODY,), delete=(NOBODY,)),
}


class AuthorizationError(PermissionError):
    """A mutation was refused by the data-layer policy (generic message)."""

    def __init__(self, table: str, operation: str, required: Iterable[str]):
        self.table, self.operation, self.required = table, operation, tuple(required)
        super().__init__("You do not have permission to perform this action.")


@dataclass(frozen=True)
class OperationScope:
    """An operation that authorizes itself; ``tables`` may be written in it.

    ``permission`` must be held by the principal (``None`` = system).
    ``columns`` restricts updates per table (``None`` = any column).
    """
    name: str
    permission: Optional[str]
    tables: dict[str, Optional[frozenset[str]]]
    operations: frozenset[str] = frozenset({"insert", "update", "delete"})


SYSTEM = OperationScope("system", None, {})
_current_scope: contextvars.ContextVar[Optional[OperationScope]] = contextvars.ContextVar(
    "drillmaster_authorization_scope", default=None)

REPORT_LIFECYCLE = OperationScope(
    "report_lifecycle", None,  # transition_report checks the action-specific permission itself
    {"daily_reports": frozenset({"status", "updated_at"}),
     "report_revisions": None, "approval_actions": None},
    frozenset({"insert", "update"}),
)
IMPORT_SCOPE = OperationScope(
    "import", IMPORT,
    {name: None for name in (*_REPORT_TABLES, "audit_logs", "wells", "wellbores")},
    frozenset({"insert", "update", "delete"}),
)


@contextlib.contextmanager
def operation_scope(scope: OperationScope):
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)


def system_scope():
    return operation_scope(SYSTEM)


def current_scope() -> Optional[OperationScope]:
    return _current_scope.get()


@dataclass
class AuthorizationState:
    """Per-DatabaseManager enforcement switch, principal and denial queue."""
    principal: object = None
    enforced: bool = False
    audit_writer: object = None  # callable(list[dict]) supplied by DatabaseManager
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allows(self, permission: str) -> bool:
        if permission == NOBODY:
            return False
        principal = self.principal
        if principal is None:
            return False
        if permission == ANY_PRINCIPAL:
            return getattr(principal, "user_id", None) is not None or bool(getattr(principal, "user", None))
        try:
            return bool(principal.has_permission(permission))
        except Exception:
            logger.exception("Permission resolution failed; access denied (%s)", permission)
            return False


def _principal_label(state: AuthorizationState) -> tuple[Optional[int], str]:
    principal = state.principal
    try:
        return getattr(principal, "user_id", None), str(getattr(principal, "username", "") or "")
    except Exception:  # silent-ok: labels are best-effort context for the audit record
        return None, ""


def authorize_change(state: AuthorizationState, table: str, operation: str,
                     columns: Optional[set[str]] = None) -> None:
    """Raise :class:`AuthorizationError` unless the change is allowed."""
    if not state.enforced:
        return
    scope = current_scope()
    if scope is SYSTEM:
        return
    if scope is not None and table in scope.tables and operation in scope.operations:
        allowed_columns = scope.tables[table]
        column_ok = operation != "update" or allowed_columns is None or (columns or set()) <= allowed_columns
        if column_ok and (scope.permission is None or state.allows(scope.permission)):
            return
    policy = TABLE_POLICY.get(table)
    required = policy.required(operation) if policy else (NOBODY,)
    if any(state.allows(permission) for permission in required):
        return
    raise AuthorizationError(table, operation, required)


def _changed_columns(obj) -> set[str]:
    from sqlalchemy import inspect

    state = inspect(obj)
    return {attr.key for attr in state.attrs if attr.history.has_changes()}


def _denied(session, state: AuthorizationState, error: AuthorizationError):
    user_id, username = _principal_label(state)
    session.info.setdefault("_authz_denials", []).append({
        "table": error.table, "operation": error.operation,
        "required": list(error.required), "user_id": user_id, "username": username,
        "scope": getattr(current_scope(), "name", None),
    })
    logger.warning("Authorization denied: %s %s (user_id=%s)", error.operation, error.table, user_id)


def before_flush(session, flush_context, instances):
    state = session.info.get("authorization")
    if state is None or not state.enforced:
        return
    for operation, objects in (("insert", session.new), ("update", session.dirty), ("delete", session.deleted)):
        for obj in list(objects):
            table = getattr(getattr(obj, "__table__", None), "name", None)
            if table is None:
                continue
            columns = None
            if operation == "update":
                if not session.is_modified(obj, include_collections=False):
                    continue
                columns = _changed_columns(obj)
            try:
                authorize_change(state, table, operation, columns)
            except AuthorizationError as error:
                _denied(session, state, error)
                raise


def do_orm_execute(orm_execute_state):
    session = orm_execute_state.session
    state = session.info.get("authorization")
    if state is None or not state.enforced:
        return
    statement = orm_execute_state.statement
    if orm_execute_state.is_update or orm_execute_state.is_delete or orm_execute_state.is_insert:
        operation = "update" if orm_execute_state.is_update else "delete" if orm_execute_state.is_delete else "insert"
        table = getattr(getattr(statement, "table", None), "name", None)
        columns = None
        if operation == "update":
            columns = {getattr(key, "key", str(key)) for key in (getattr(statement, "_values", None) or {})}
        try:
            authorize_change(state, table or "<unknown>", operation, columns)
        except AuthorizationError as error:
            _denied(session, state, error)
            raise
        return
    text = str(getattr(statement, "text", "") or "").lstrip().upper()
    if text.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE", "DROP", "ALTER", "CREATE")):
        error = AuthorizationError("<textual-sql>", "execute", (NOBODY,))
        if current_scope() is SYSTEM:
            return
        _denied(session, state, error)
        raise error


def after_transaction_end(session, transaction):
    if transaction.parent is not None:
        return
    denials = session.info.pop("_authz_denials", None)
    state = session.info.get("authorization")
    if denials and state is not None and callable(state.audit_writer):
        try:
            state.audit_writer(denials)
        except Exception:
            logger.exception("Could not record %d authorization denial(s) in the audit log", len(denials))


def install(session_class) -> None:
    """Register the hooks on a Session class once."""
    from sqlalchemy import event

    if getattr(session_class, "_drillmaster_authz_installed", False):
        return
    event.listen(session_class, "before_flush", before_flush)
    event.listen(session_class, "do_orm_execute", do_orm_execute)
    event.listen(session_class, "after_transaction_end", after_transaction_end)
    session_class._drillmaster_authz_installed = True
