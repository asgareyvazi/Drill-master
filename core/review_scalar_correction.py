"""M173: correct a deferred scalar DDR review item directly from the persisted review queue.

Contract ``ddr-scalar-correction-v1``:

* Only an explicit allowlist of canonical targets is correctable: the report itself (``daily_report.*``), the
  report's single mud / drilling-parameter / safety record and the well master record (``well_info.*``).  A target
  that cannot be associated with exactly one existing record (no record, several records, a multi-row table, an
  unknown or protected column) stays unresolved with the reason - a correction never creates a record.
* The operator's value is parsed strictly against the canonical :class:`core.canonical_schema.FieldSpec` *and* the
  column type: no booleans for numbers, no NaN / infinity / overflow, no thousands separators, no empty value,
  engineering bounds enforced, a declared unit converted with :class:`core.unit_manager.UnitManager` or refused.
* Optimistic concurrency: the canonical field must still hold the value it had when the review item was created
  (``payload.target_at_creation``; for older items without that snapshot a deferred proposal was never canonical, so
  the field must still be empty) or, after an earlier correction, the value that correction wrote.  The preview
  returns a token of the current value; applying with a different current value is refused.
* Apply is one transaction: canonical update, item state ``ACCEPTED``, decision history (append-only) and a
  mandatory audit record commit or roll back together.  The original extracted text is never changed.
* A decided item can be reopened (history kept, canonical data unchanged); an attached continuation cannot.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

CORRECTION_CONTRACT = "ddr-scalar-correction-v1"

# entity -> (model name, locator)
TARGETS = {
    "daily_report": ("DailyReport", "report"),
    "mud_report": ("MudReport", "report_child"),
    "drilling_params": ("DrillingParameters", "report_child"),
    "safety": ("SafetyReport", "report_child"),
    "well_info": ("Well", "well"),
}
NOT_CORRECTABLE = {
    "bulk_material": "bulk materials are a multi-row table; correct the row in the Material tab",
    "time_log": "time-log rows are corrected in the Daily Report time log, never from a scalar review",
    "time_log_morning": "time-log rows are corrected in the Daily Report time log, never from a scalar review",
}
# Fields the import persists on another record than their canonical prefix says (same rule as the import:
# ``DDRImportService._save_mud_report`` stores the header "mud lost downhole" as ``MudReport.loss_downhole``).
STORED_AS = {"daily_report.mud_lost_downhole": "mud_report.loss_downhole"}
PROTECTED_COLUMNS = {"id", "well_id", "report_id", "project_id", "section_id", "wellbore_id", "created_at",
                     "updated_at", "name", "code", "report_date", "report_number"}
MAX_MAGNITUDE = 1e15


class CorrectionRefused(ValueError):
    """The correction is not applied; the message says why (the item stays unresolved)."""


@dataclass
class Target:
    entity: str
    model: Any
    record: Any
    column: str
    sql_type: str
    length: Optional[int]

    def describe(self) -> Dict[str, Any]:
        return {"entity": self.entity, "model": self.model.__name__, "record_id": self.record.id,
                "column": self.column, "type": self.sql_type, "length": self.length}


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def value_token(value: Any) -> str:
    return hashlib.sha256(json.dumps(_json_value(value), default=str).encode("utf-8")).hexdigest()[:16]


def field_spec(target_field: str):
    from core.canonical_schema import FIELD_SPECS
    return FIELD_SPECS.get(target_field or "")


def _column_kind(column) -> Tuple[str, Optional[int]]:
    from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, Time
    kind = column.type
    if isinstance(kind, Boolean):
        return "boolean", None
    if isinstance(kind, Integer):
        return "integer", None
    if isinstance(kind, (Float, Numeric)):
        return "number", None
    if isinstance(kind, DateTime):
        return "datetime", None
    if isinstance(kind, Date):
        return "date", None
    if isinstance(kind, Time):
        return "time", None
    if isinstance(kind, (String, Text)):
        return "text", getattr(kind, "length", None)
    return type(kind).__name__.lower(), None


def resolve_target(session, item) -> Target:
    """The one existing canonical record and column an item corrects, or :class:`CorrectionRefused`."""
    from core import database as models
    field = str(item.target_field or "")
    entity, _, column = STORED_AS.get(field, field).partition(".")
    if item.review_type == "continuation":
        raise CorrectionRefused("A continuation is attached, rejected or ignored - it has no scalar value")
    if entity in NOT_CORRECTABLE:
        raise CorrectionRefused(f"{field}: {NOT_CORRECTABLE[entity]}")
    if entity not in TARGETS or not column:
        raise CorrectionRefused(f"{field or '(no target field)'} is not a correctable canonical field; "
                                "the item stays unresolved")
    if column in PROTECTED_COLUMNS:
        raise CorrectionRefused(f"{field} is an identity column and is never corrected from a review item")
    report = session.get(models.DailyReport, item.report_id)
    if report is None or report.well_id != item.well_id:
        raise CorrectionRefused("The report of this item no longer belongs to its well; nothing was changed")
    model_name, locator = TARGETS[entity]
    model = getattr(models, model_name)
    table_column = model.__table__.columns.get(column)
    if table_column is None:
        raise CorrectionRefused(f"{field}: {model.__tablename__} has no column {column!r}; the item stays "
                                "unresolved")
    if locator == "report":
        record = report
    elif locator == "well":
        record = session.get(models.Well, item.well_id)
    else:
        rows = session.query(model).filter(model.report_id == item.report_id).all()
        if not rows:
            raise CorrectionRefused(f"{field}: this report has no {model.__tablename__} record; a correction never "
                                    "creates a record (enter the section in its tab)")
        if len(rows) > 1:
            raise CorrectionRefused(f"{field}: this report has {len(rows)} {model.__tablename__} records; the "
                                    "target is ambiguous")
        record = rows[0]
        if hasattr(record, "well_id") and record.well_id not in (None, item.well_id):
            raise CorrectionRefused("The target record belongs to another well; nothing was changed")
    if record is None:
        raise CorrectionRefused(f"{field}: the target record does not exist")
    kind, length = _column_kind(table_column)
    return Target(entity, model, record, column, kind, length)


_INT = re.compile(r"[+-]?\d+")
_NUM = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")


def parse_value(raw: Any, target_field: str, target: Target, unit: Optional[str] = None) -> Tuple[Any, Dict]:
    """Strictly parse an operator value for ``target``; returns ``(value, conversion)``."""
    spec = field_spec(target_field)
    canonical_unit = spec.unit if spec else ""
    conversion: Dict[str, Any] = {"entered_unit": unit or canonical_unit, "canonical_unit": canonical_unit}
    if isinstance(raw, bool) and target.sql_type != "boolean":
        raise CorrectionRefused("A yes/no value is not a valid value for this field")
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise CorrectionRefused("An empty correction is not a value; reject or ignore the item instead")
    kind = target.sql_type
    if kind == "text":
        if target.length and len(text) > target.length:
            raise CorrectionRefused(f"The value is longer than the field allows ({target.length} characters)")
        return text, conversion
    if kind == "date":
        try:
            return date.fromisoformat(text), conversion
        except ValueError:
            raise CorrectionRefused("Enter the date as YYYY-MM-DD") from None
    if kind == "integer":
        if not _INT.fullmatch(text):
            raise CorrectionRefused("Enter a whole number (no separators, no unit text)")
        value: Any = int(text)
        if abs(value) > MAX_MAGNITUDE:
            raise CorrectionRefused("The number is out of range")
    elif kind == "number":
        if not _NUM.fullmatch(text):
            raise CorrectionRefused("Enter a plain number (decimal point, no thousands separator, no unit text)")
        value = float(text)
        if not math.isfinite(value) or abs(value) > MAX_MAGNITUDE:
            raise CorrectionRefused("The number is not finite or out of range")
    else:
        raise CorrectionRefused(f"Fields of type {kind} are not corrected from the review queue")
    if unit and canonical_unit and unit.strip() != canonical_unit:
        from core.unit_manager import UnitManager
        try:
            converted = UnitManager.convert(value, spec.quantity, unit, canonical_unit)
        except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
            raise CorrectionRefused(f"Cannot convert {unit!r} to {canonical_unit!r} for {spec.quantity}: {exc}") \
                from None
        if converted is None or not math.isfinite(float(converted)):
            raise CorrectionRefused("The unit conversion did not give a finite value")
        conversion.update(entered_value=value, factor_applied=True)
        value = float(converted) if kind == "number" else converted
        if kind == "integer":
            if float(value) != int(float(value)):
                raise CorrectionRefused("The converted value is not a whole number")
            value = int(float(value))
    elif unit and not canonical_unit:
        raise CorrectionRefused(f"{target_field} has no canonical unit; enter the value without a unit")
    if canonical_unit == "%" and not 0 <= value <= 100:
        raise CorrectionRefused(f"{value} % is not a percentage between 0 and 100")
    if spec is not None:
        if spec.min_val is not None and value < spec.min_val:
            raise CorrectionRefused(f"{value} {canonical_unit} is below the plausible minimum {spec.min_val}")
        if spec.max_val is not None and value > spec.max_val:
            raise CorrectionRefused(f"{value} {canonical_unit} is above the plausible maximum {spec.max_val}")
    return value, conversion


def history(item) -> List[Dict[str, Any]]:
    try:
        data = json.loads(item.decision_history_json) if item.decision_history_json else []
    except ValueError:
        data = [{"action": "UNREADABLE_HISTORY", "raw": item.decision_history_json}]
    return data if isinstance(data, list) else []


def append_history(item, entry: Dict[str, Any]) -> None:
    entries = history(item)
    entries.append({**entry, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    item.decision_history_json = json.dumps(entries, ensure_ascii=False, default=str)


def expected_current(item) -> Tuple[Any, str]:
    """The value the canonical field must still hold, and where that expectation comes from."""
    for entry in reversed(history(item)):
        if entry.get("action") == "CORRECTED":
            return entry.get("new"), "the last correction of this item"
    payload = json.loads(item.payload_json) if item.payload_json else {}
    snapshot = payload.get("target_at_creation") if isinstance(payload, dict) else None
    if isinstance(snapshot, dict) and "value" in snapshot:
        return snapshot.get("value"), "the value when the review item was created"
    return None, "empty (a deferred proposal is never canonical)"


def snapshot_target(session, item) -> Dict[str, Any]:
    """Recorded on new queue items: the target and its value at creation (or why there is none)."""
    try:
        target = resolve_target(session, item)
    except CorrectionRefused as exc:
        return {"correctable": False, "reason": str(exc)}
    return {"correctable": True, **target.describe(),
            "value": _json_value(getattr(target.record, target.column))}


def _item(session, item_id: int, well_id: int):
    from core.database import ImportReviewItem
    item = session.get(ImportReviewItem, item_id)
    if item is None or item.well_id != well_id:
        raise CorrectionRefused("The review item is not an item of the selected well; nothing was changed")
    return item


def _source_units(item) -> Dict[str, Any]:
    payload = json.loads(item.payload_json) if item.payload_json else {}
    return {"source_unit": payload.get("original_unit") or payload.get("unit") or "",
            "proposed_value": payload.get("normalized_value", payload.get("proposed_value")),
            "source_cell": payload.get("source_cell") or (payload.get("source_location") or {}).get("cell")}


def preview_correction(db, item_id: int, well_id: int, raw: Any, unit: Optional[str] = None) -> Dict[str, Any]:
    """Validate an edit without writing; returns what would change and the concurrency token."""
    from core.ddr_continuation import DEFERRED_UNRESOLVED, VALIDATION_ERROR
    with db.session_scope() as session:
        item = _item(session, item_id, well_id)
        if item.state not in (DEFERRED_UNRESOLVED, VALIDATION_ERROR):
            raise CorrectionRefused(f"The review item is already decided ({item.state}); reopen it first")
        target = resolve_target(session, item)
        spec = field_spec(item.target_field)
        value, conversion = parse_value(raw, item.target_field, target, unit)
        current = _json_value(getattr(target.record, target.column))
        expected, basis = expected_current(item)
        return {"contract": CORRECTION_CONTRACT, "item_id": item.id, "review_id": item.review_id,
                "target_field": item.target_field, "target": target.describe(),
                "quantity": spec.quantity if spec else target.sql_type, **_source_units(item), **conversion,
                "original_text": item.original_text, "current_value": current, "expected_value": expected,
                "expected_basis": basis, "conflict": current != expected,
                "new_value": _json_value(value), "token": value_token(current)}


def apply_correction(db, item_id: int, well_id: int, raw: Any, *, reason: str, token: str, confirmed: bool,
                     unit: Optional[str] = None) -> Dict[str, Any]:
    """Write a previewed correction atomically (canonical value, item, history, audit)."""
    from core.ddr_continuation import ACCEPTED, DEFERRED_UNRESOLVED, VALIDATION_ERROR
    if not confirmed:
        raise CorrectionRefused("The correction was not confirmed; nothing was changed")
    if not str(reason or "").strip():
        raise CorrectionRefused("A reason is required for a correction; nothing was changed")
    with db.session_scope() as session:
        item = _item(session, item_id, well_id)
        if item.state not in (DEFERRED_UNRESOLVED, VALIDATION_ERROR):
            raise CorrectionRefused(f"The review item is already decided ({item.state}); nothing was changed")
        target = resolve_target(session, item)
        value, conversion = parse_value(raw, item.target_field, target, unit)
        current = _json_value(getattr(target.record, target.column))
        expected, basis = expected_current(item)
        if current != expected:
            raise CorrectionRefused(f"NOT SAVED: {item.target_field} changed since {basis} (expected "
                                    f"{expected!r}, found {current!r}); review the current value first")
        if value_token(current) != token:
            raise CorrectionRefused("NOT SAVED: the target changed since the preview; preview again")
        setattr(target.record, target.column, value)
        before_state = item.state
        actor = (db._audit_actor()[1] or "")[:100] or None
        item.state = ACCEPTED
        item.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        item.resolved_by = actor
        item.resolution_note = f"Corrected by operator: {str(reason).strip()}"[:1000]
        append_history(item, {"action": "CORRECTED", "contract": CORRECTION_CONTRACT, "before_state": before_state,
                              "after_state": ACCEPTED, "old": current, "new": _json_value(value), "raw": str(raw),
                              **conversion, "reason": str(reason).strip(), "by": actor,
                              "target": target.describe()})
        session.flush()
        db._add_mandatory_audit(session, "ddr_review_correction", "import_review_item", item.id, item.review_id,
                                json.dumps({"contract": CORRECTION_CONTRACT, "report_id": item.report_id,
                                            "field": item.target_field, "record": target.describe()["record_id"],
                                            "old": current, "new": _json_value(value),
                                            "unit": conversion.get("entered_unit"),
                                            "reason": str(reason).strip()[:160]}, default=str))
        return {"id": item.id, "state": item.state, "old": current, "new": _json_value(value),
                "target": target.describe()}


def reopen_item(db, item_id: int, well_id: int, reason: str) -> Dict[str, Any]:
    """Reopen a decided item for another decision; history is kept and canonical data is not changed."""
    from core.ddr_continuation import ACCEPTED, DEFERRED_UNRESOLVED, IGNORED, REJECTED
    if not str(reason or "").strip():
        raise CorrectionRefused("A reason is required to reopen a review item")
    with db.session_scope() as session:
        item = _item(session, item_id, well_id)
        if item.state not in (ACCEPTED, REJECTED, IGNORED):
            raise CorrectionRefused(f"Only an accepted, rejected or ignored item can be reopened ({item.state})")
        before = item.state
        actor = (db._audit_actor()[1] or "")[:100] or None
        append_history(item, {"action": "REOPENED", "before_state": before, "after_state": DEFERRED_UNRESOLVED,
                              "reason": str(reason).strip(), "by": actor,
                              "previous_resolution": item.resolution_note,
                              "previous_resolved_by": item.resolved_by,
                              "previous_resolved_at": _json_value(item.resolved_at)})
        item.state = DEFERRED_UNRESOLVED
        item.resolved_at = item.resolved_by = item.resolution_note = None
        session.flush()
        db._add_mandatory_audit(session, "ddr_review_reopened", "import_review_item", item.id, item.review_id,
                                json.dumps({"before": before, "reason": str(reason).strip()[:200]}))
        return {"id": item.id, "state": item.state}
