"""Complete Daily Drilling Report snapshot contract — domain-specific, Qt-free.

A ``ReportRevision.snapshot`` must be a *complete, self-contained* immutable
record of the operational report at a lifecycle event — not merely the
``DailyReport`` header row. This module builds that snapshot from the live
database rows at capture time, so that later edits to the current report and its
child tables can never mutate a historical revision.

Scope of "the DDR" is taken from the repository's own authoritative definition
of report-owned content (``tabs/w2_Daily_Report.py::_copy_all_report_data`` plus
the two time-log tables) — NOT every table that happens to carry a ``report_id``.
Derived analytics (trajectory calculations, time-depth, ROP analysis) and
engineering calculation histories are deliberately excluded: they are computed
or independently versioned elsewhere (missions 16/17).

This is intentionally a small, explicit contract for one record type. It is not
a generic serialization framework (mission §8/§51).
"""
from __future__ import annotations

from datetime import date, datetime, time as _time
from typing import Any, Dict, List

# Current snapshot schema version. Bump only on an incompatible structural
# change; readers must tolerate older versions.
SNAPSHOT_SCHEMA_VERSION = 1


def serialize_value(value: Any) -> Any:
    """Deterministically serialize a single column value to a JSON-safe form.

    Dates/times use ISO-8601. NULL / unknown stays ``None`` — never coerced to
    0, "", today or now (mission §12/§46). Native JSON scalars pass through.
    """
    if value is None:
        return None
    if isinstance(value, (datetime, date, _time)):
        return value.isoformat()
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, dict)):
        return value  # already-JSON columns (e.g. header_snapshot)
    # Fall back to a stable string only for genuinely unexpected types.
    return str(value)


def serialize_row(row) -> Dict[str, Any]:
    """Serialize one ORM row into an ordered, JSON-safe dict of its columns."""
    result: Dict[str, Any] = {}
    for column in row.__table__.columns:
        result[column.name] = serialize_value(getattr(row, column.name))
    return result


def _order_key(model_name: str):
    """Return a deterministic sort key function for a child collection.

    Ordering is derived from each entity's real domain semantics so that two
    snapshots of identical content serialize identically (mission §11).
    A stable id tiebreaker is always appended.
    """
    domain_order = {
        "TimeLog24H": ("time_from", "id"),
        "TimeLogMorning": ("time_from", "id"),
        "SurveyPoint": ("md", "id"),
        "BHAReport": ("bha_name", "id"),
        "DrillingParameters": ("depth_in", "id"),
    }
    fields = domain_order.get(model_name, ("id",))

    def key(item: Dict[str, Any]):
        out = []
        for f in fields:
            v = item.get(f)
            # None sorts first, then by (type-rank, value) to stay total-ordered
            out.append((v is not None, "" if v is None else str(v) if not isinstance(v, (int, float)) else v))
        return tuple(out)

    return key


# The authoritative report-owned child collections and their FK field.
# Mirrors tabs/w2_Daily_Report.py::_copy_all_report_data plus time logs.
CHILD_COLLECTIONS: List[tuple] = [
    ("time_logs_24h", "TimeLog24H", "report_id"),
    ("time_logs_morning", "TimeLogMorning", "report_id"),
    ("drilling_parameters", "DrillingParameters", "report_id"),
    ("mud_report", "MudReport", "report_id"),
    ("cement_report", "CementReport", "report_id"),
    ("casing_report", "CasingReport", "report_id"),
    ("bit_report", "BitReport", "report_id"),
    ("bha_report", "BHAReport", "report_id"),
    ("downhole_equipment", "DownholeEquipment", "report_id"),
    ("formation_report", "FormationReport", "report_id"),
    ("safety_report", "SafetyReport", "report_id"),
    ("wellbore_schematic", "WellboreSchematic", "report_id"),
    ("trip_sheet", "TripSheetEntry", "report_id"),
    ("survey", "SurveyPoint", "report_id"),
    ("logistics_personnel", "LogisticsPersonnel", "report_id"),
    ("service_company_pob", "ServiceCompanyPOB", "report_id"),
    ("fuel_water_inventory", "FuelWaterInventory", "report_id"),
    ("bulk_materials", "BulkMaterials", "report_id"),
    ("transport_log", "TransportLog", "report_id"),
    ("transport_notes", "TransportNotes", "report_id"),
    ("service_company", "ServiceCompany", "report_id"),
    ("service_note", "ServiceNote", "report_id"),
    ("material_request", "MaterialRequest", "report_id"),
    ("equipment_log", "EquipmentLog", "report_id"),
    ("seven_days_lookahead", "SevenDaysLookahead", "report_id"),
    ("npt_report", "NPTReport", "report_id"),
]


def build_report_snapshot(session, report, models: Dict[str, Any]) -> Dict[str, Any]:
    """Build the complete, self-contained snapshot of ``report``.

    Reads every report-owned collection from the live rows *now*, so the result
    is independent of any future change to those rows. ``models`` maps model
    class names to the ORM classes (supplied by the DB layer to avoid a hard
    import cycle and to keep this module Qt/ORM-agnostic).

    Ownership context (well_id / section_id / report_id) and the report's own
    ``header_snapshot`` (human-readable well identity captured at save time) are
    preserved so a revision never needs to re-read live master data (§10/§35).
    """
    report_dict = serialize_row(report)

    snapshot: Dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "captured_at": datetime.utcnow().isoformat(),
        "report_id": report.id,
        "well_id": report.well_id,
        "section_id": report.section_id,
        "report": report_dict,
        "children": {},
    }

    for key, model_name, fk_field in CHILD_COLLECTIONS:
        model = models.get(model_name)
        if model is None:
            continue
        rows = session.query(model).filter(getattr(model, fk_field) == report.id).all()
        serialized = [serialize_row(r) for r in rows]
        serialized.sort(key=_order_key(model_name))
        snapshot["children"][key] = serialized

    return snapshot


def snapshot_is_complete(snapshot: Dict[str, Any]) -> bool:
    """Cheap structural check that a dict is a v1 complete snapshot."""
    return (
        isinstance(snapshot, dict)
        and snapshot.get("schema_version") == SNAPSHOT_SCHEMA_VERSION
        and isinstance(snapshot.get("report"), dict)
        and isinstance(snapshot.get("children"), dict)
    )


def child_count(snapshot: Dict[str, Any], key: str) -> int:
    """Number of rows captured for a child collection (0 if absent)."""
    children = snapshot.get("children", {}) if isinstance(snapshot, dict) else {}
    rows = children.get(key)
    return len(rows) if isinstance(rows, list) else 0
