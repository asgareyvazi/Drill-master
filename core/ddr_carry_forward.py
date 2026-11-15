"""M217: day-by-day DDR authoring - carry-forward only with confirmation, and a state for every report section.

Contract ``ddr-carry-forward-v1``.

Before M217 both "copy previous day" routes (the Daily Report toolbar and the New Daily Report dialog) copied
every child table of yesterday's report into today's - mud properties, drilling parameters, survey stations, trip
sheet, NPT, bit runs, bulk-material movements - as if they had been measured today, without a marker. The toolbar
route also deleted whatever the target day already held, without asking.

Now:

* Only *state that persists from one day to the next* can be carried (the BHA in the hole, downhole equipment,
  the schematic, the BOP stack, personnel / POB / service companies, the look-ahead plan, the fuel / water opening
  balance, and yesterday's 00:00-06:00 morning log, which is the start of today's 24-hour log). Each section is
  chosen by the operator and the whole carry needs an explicit confirmation.
* A daily measurement or event is **never** carried (``NEVER_CARRIED`` lists why for each section).
* A section that already holds rows on the target day is never replaced; it is skipped and reported.
* The carry and its lineage (source report, sections, row counts, operator) are one transaction: the lineage is
  the ``ddr_carry_forward`` record in the audit store, next to the import lineage (``ddr_import``).
* A carried section stays **CARRIED** until the operator confirms it for the new day (``ddr_carry_confirm``).

``section_states`` reports, per section of a report, one of NEW / CARRIED / CONFIRMED / IMPORTED / DERIVED / MISSING.

Separate from this module and unchanged by M217 (recorded so it is not mistaken for a silent copy): the
inventory ledgers derive a **missing opening balance** from the latest earlier closing balance when the operator
saves a day's movements - ``Database.save_fuel_water_inventory`` (fuel / water opening stock),
``save_inventory_items`` and ``save_bulk_material`` (opening quantity). It is a DERIVED value under a stated rule
(opening = previous closing), applied only when the opening is None (an entered opening, including 0, is never
replaced) and only on an explicit save; the item and bulk ledgers leave it None when two earlier rows of the item
share the latest date (the fuel / water ledger takes the latest earlier row of the well). W7 shows
the projection under a "PREVIEW - carried forward ...; not yet saved" banner until the operator saves.
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional

CARRY_FORWARD_CONTRACT = "ddr-carry-forward-v1"
CARRY_ACTION = "ddr_carry_forward"
CONFIRM_ACTION = "ddr_carry_confirm"
IMPORT_ACTION = "ddr_import"

NEW, CARRIED, CONFIRMED, IMPORTED, DERIVED, MISSING = "NEW", "CARRIED", "CONFIRMED", "IMPORTED", "DERIVED", "MISSING"
STATES = (NEW, CARRIED, CONFIRMED, IMPORTED, DERIVED, MISSING)


class CarryForwardRefused(ValueError):
    """The carry-forward was not done; nothing was changed."""


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    model: str                  # the ORM class in core.database that holds the section's rows of a report
    source_model: str = ""      # a different source table (the morning log becomes today's 24-hour log)
    reason: str = ""            # why a section is never carried


CARRYABLE: Dict[str, Section] = {s.key: s for s in (
    Section("morning_log", "Morning log 00:00-06:00 -> today's 24-hour log", "TimeLog24H", "TimeLogMorning"),
    Section("bha", "BHA in the hole", "BHAReport"),
    Section("downhole_equipment", "Downhole equipment", "DownholeEquipment"),
    Section("wellbore_schematic", "Wellbore schematic", "WellboreSchematic"),
    Section("bop_components", "BOP stack components", "BOPComponent"),
    Section("personnel", "Personnel on board", "LogisticsPersonnel"),
    Section("service_pob", "Service company POB", "ServiceCompanyPOB"),
    Section("service_companies", "Service companies", "ServiceCompany"),
    Section("lookahead", "Seven-day look-ahead plan", "SevenDaysLookahead"),
    Section("fuel_water_opening", "Fuel / water opening balance (yesterday's remaining)", "FuelWaterInventory"),
)}

NEVER_CARRIED: Dict[str, Section] = {s.key: s for s in (
    Section("drilling_parameters", "Drilling parameters", "DrillingParameters",
            reason="measured for the day (WOB, RPM, flow, pressure)"),
    Section("mud", "Mud properties", "MudReport", reason="a mud check is a measurement of the day"),
    Section("cement", "Cement job", "CementReport", reason="an operation event of its own day"),
    Section("casing", "Casing job", "CasingReport", reason="an operation event of its own day"),
    Section("bit", "Bit run", "BitReport", reason="daily hours, footage and ROP are measurements"),
    Section("formation", "Formation tops", "FormationReport", reason="tops are observed on the day they are drilled"),
    Section("trip_sheet", "Trip sheet", "TripSheetEntry", reason="a trip is an event of its own day"),
    Section("surveys", "Survey stations", "SurveyPoint", reason="a station is measured once; a copy duplicates it"),
    Section("bulk_materials", "Bulk materials", "BulkMaterials",
            reason="daily receipts and usage; the opening is taken from the previous closing when the day is saved"),
    Section("transport_log", "Transport log", "TransportLog", reason="movements of the day"),
    Section("transport_notes", "Transport notes", "TransportNotes", reason="notes of the day"),
    Section("service_notes", "Service notes", "ServiceNote", reason="notes of the day"),
    Section("material_requests", "Material requests", "MaterialRequest", reason="a request is raised once"),
    Section("equipment_log", "Equipment log", "EquipmentLog", reason="equipment events of the day"),
    Section("waste", "Waste records", "WasteRecord", reason="waste generated on the day"),
    Section("npt", "NPT", "NPTReport", reason="a copied NPT event would be counted twice"),
    Section("safety", "Safety", "SafetyReport", reason="a previous observation is not a new assessment"),
)}

ALL_SECTIONS: Dict[str, Section] = {**CARRYABLE, **NEVER_CARRIED}
# Report-header values that a new day may derive from the previous report (recorded as DERIVED).
DERIVED_HEADER = {"depth_0000": "depth_2400", "rig_day": "rig_day"}
# A new report starts with these column defaults; an entered value is anything else and is never overwritten.
UNENTERED_HEADER = {"depth_0000": (None,), "rig_day": (None, 1)}


def _model(name):
    import core.database as database
    return getattr(database, name)


def _rows(session, model_name: str, report_id: int) -> int:
    model = _model(model_name)
    return session.query(model).filter(model.report_id == report_id).count()


def _reports(session, source_id: int, target_id: int):
    from core.report_lifecycle import is_editable
    DailyReport = _model("DailyReport")
    source, target = session.get(DailyReport, source_id), session.get(DailyReport, target_id)
    if source is None or target is None or source.id == target.id or source.well_id != target.well_id:
        raise CarryForwardRefused("Carry-forward needs two different reports of the same well; nothing was changed")
    if not is_editable(target.status):
        raise CarryForwardRefused("The target report is not editable; nothing was changed")
    if source.report_date and target.report_date and source.report_date >= target.report_date:
        raise CarryForwardRefused("Only an earlier report can be carried forward; nothing was changed")
    return source, target


def plan(session, source_id: int, target_id: int) -> Dict[str, Any]:
    """What a carry from ``source_id`` to ``target_id`` could do - read only."""
    source, target = _reports(session, source_id, target_id)
    carryable = []
    for section in CARRYABLE.values():
        available = _rows(session, section.source_model or section.model, source.id)
        existing = _rows(session, section.model, target.id)
        blocked = ("nothing to carry" if not available else
                   f"today already has {existing} row(s); they are never replaced" if existing else "")
        carryable.append({"key": section.key, "label": section.label, "rows": available, "target_rows": existing,
                          "blocked": blocked})
    never = [{"key": s.key, "label": s.label, "rows": _rows(session, s.model, source.id), "reason": s.reason}
             for s in NEVER_CARRIED.values()]
    derived = {field: getattr(source, origin) for field, origin in DERIVED_HEADER.items()}
    return {"contract": CARRY_FORWARD_CONTRACT, "source_report_id": source.id, "target_report_id": target.id,
            "source_date": str(source.report_date), "target_date": str(target.report_date),
            "carryable": carryable, "never_carried": never, "derived_header": derived}


def _copy_rows(session, section: Section, source, target) -> int:
    from sqlalchemy import null
    model = _model(section.model)
    if section.key == "morning_log":
        count = 0
        for log in session.query(_model("TimeLogMorning")).filter_by(report_id=source.id).all():
            session.add(model(report_id=target.id, time_from=log.time_from, time_to=log.time_to,
                              duration=log.duration, main_phase=log.main_phase, main_code=log.main_code,
                              sub_code=log.sub_code, status=log.status, is_npt=log.is_npt,
                              activity_description=log.activity_description, contractor=log.contractor))
            count += 1
        return count
    records = session.query(model).filter(model.report_id == source.id).order_by(model.id).all()
    for index, rec in enumerate(records):
        if section.key == "fuel_water_opening":
            # Opening = yesterday's remaining; today's movements are unknown until entered (None, never 0).
            session.add(model(well_id=rec.well_id, section_id=target.section_id, report_id=target.id,
                              report_date=target.report_date, fuel_type=rec.fuel_type,
                              fuel_stock=rec.fuel_remaining if rec.fuel_remaining is not None else null(),
                              water_stock=rec.water_remaining if rec.water_remaining is not None else null(),
                              fuel_remaining=rec.fuel_remaining if rec.fuel_remaining is not None else null(),
                              water_remaining=rec.water_remaining if rec.water_remaining is not None else null(),
                              fuel_consumed=null(), fuel_received=null(), water_consumed=null(),
                              water_received=null(), days_remaining_fuel=None, days_remaining_water=None,
                              created_by=rec.created_by))
            continue
        data = {c.name: deepcopy(getattr(rec, c.name)) for c in model.__table__.columns
                if c.name not in ("id", "report_id")}
        data["report_id"] = target.id
        if "section_id" in data:
            data["section_id"] = target.section_id
        if "report_date" in data:
            data["report_date"] = target.report_date
        if section.key == "lookahead":
            if index >= 7:
                break
            data.update(plan_date=target.report_date + timedelta(days=index), day_number=index + 1)
        session.add(model(**data))
    return min(len(records), 7) if section.key == "lookahead" else len(records)


def apply(session, source_id: int, target_id: int, sections: Iterable[str], *, confirmed: bool,
          derive_header: Iterable[str] = (), actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Carry the chosen ``sections`` (and derived header values) in ``session``'s transaction, with its lineage.

    Refuses (``CarryForwardRefused``, nothing changed) without confirmation, for an unknown or never-carried
    section, and when a chosen section already has rows on the target day.
    """
    if not confirmed:
        raise CarryForwardRefused("Carry-forward needs the operator's confirmation; nothing was changed")
    chosen = list(dict.fromkeys(str(k) for k in sections))
    derive = list(dict.fromkeys(str(k) for k in derive_header))
    if not chosen and not derive:
        raise CarryForwardRefused("No section was chosen; nothing was changed")
    for key in chosen:
        if key in NEVER_CARRIED:
            raise CarryForwardRefused(f"{NEVER_CARRIED[key].label} is never carried forward "
                                      f"({NEVER_CARRIED[key].reason}); nothing was changed")
        if key not in CARRYABLE:
            raise CarryForwardRefused(f"Unknown section {key!r}; nothing was changed")
    unknown = [f for f in derive if f not in DERIVED_HEADER]
    if unknown:
        raise CarryForwardRefused(f"Header value(s) {unknown} cannot be derived; nothing was changed")
    source, target = _reports(session, source_id, target_id)
    for key in chosen:
        existing = _rows(session, CARRYABLE[key].model, target.id)
        if existing:
            raise CarryForwardRefused(f"{CARRYABLE[key].label}: today already has {existing} row(s); they are "
                                      "never replaced - nothing was changed")
    copied = {key: _copy_rows(session, CARRYABLE[key], source, target) for key in chosen}
    derived = {}
    for field in derive:
        value = getattr(source, DERIVED_HEADER[field])
        if value is None:
            continue                                    # nothing known to derive from; stays missing
        value = value + 1 if field == "rig_day" else value
        if getattr(target, field) in UNENTERED_HEADER[field]:
            setattr(target, field, value)
            derived[field] = value
    record = {"contract": CARRY_FORWARD_CONTRACT, "source_report_id": source.id, "target_report_id": target.id,
              "sections": copied, "derived_header": derived, "confirmed": True}
    _audit(session, CARRY_ACTION, target.id, record, actor)
    session.flush()
    return record


def confirm(session, report_id: int, sections: Iterable[str], *, note: str = "",
            actor: Optional[Dict[str, Any]] = None) -> List[str]:
    """Confirm carried sections as valid for the new day (a new decision; the carry lineage stays)."""
    states = section_states(session, report_id)
    keys = [k for k in dict.fromkeys(sections) if states.get(k, {}).get("state") == CARRIED]
    if not keys:
        raise CarryForwardRefused("No carried section is waiting for confirmation; nothing was changed")
    _audit(session, CONFIRM_ACTION, report_id,
           {"contract": CARRY_FORWARD_CONTRACT, "sections": keys, "note": str(note or "")[:300]}, actor)
    session.flush()
    return keys


def _audit(session, action, report_id, details, actor):
    AuditLog = _model("AuditLog")
    from core.database import _now_utc
    actor = actor or {}
    session.add(AuditLog(action=action, entity_type="daily_report", entity_id=report_id,
                         user_id=actor.get("user_id"), username=actor.get("username"),
                         details=json.dumps(details, default=str, sort_keys=True), timestamp=_now_utc()))


def _records(session, report_id: int, action: str) -> List[Dict[str, Any]]:
    AuditLog = _model("AuditLog")
    rows = (session.query(AuditLog).filter_by(action=action, entity_type="daily_report", entity_id=report_id)
            .order_by(AuditLog.id).all())
    out = []
    for row in rows:
        try:
            data = json.loads(row.details or "{}")
        except ValueError:  # silent-ok: an unreadable lineage record is skipped (the section shows as NEW)
            continue
        out.append(dict(data, _audit_id=row.id))
    return out


def section_states(session, report_id: int) -> Dict[str, Dict[str, Any]]:
    """State of every section of a report (and of the derived header values)."""
    carries = _records(session, report_id, CARRY_ACTION)
    confirms = _records(session, report_id, CONFIRM_ACTION)
    imported = bool(_records(session, report_id, IMPORT_ACTION))
    states: Dict[str, Dict[str, Any]] = {}
    for key, section in ALL_SECTIONS.items():
        rows = _rows(session, section.model, report_id)
        carry = next((c for c in reversed(carries) if key in (c.get("sections") or {})), None)
        entry = {"label": section.label, "rows": rows, "state": MISSING if not rows else NEW}
        if rows and carry is not None:
            confirmed = any(c["_audit_id"] > carry["_audit_id"] and key in (c.get("sections") or [])
                            for c in confirms)
            entry.update(state=CONFIRMED if confirmed else CARRIED, source_report_id=carry.get("source_report_id"))
        elif rows and imported:
            entry["state"] = IMPORTED
        states[key] = entry
    DailyReport = _model("DailyReport")
    report = session.get(DailyReport, report_id)
    for field in DERIVED_HEADER:
        carry = next((c for c in reversed(carries) if field in (c.get("derived_header") or {})), None)
        value = getattr(report, field, None) if report is not None else None
        state = MISSING if value is None else DERIVED if carry is not None and \
            carry["derived_header"][field] == value else IMPORTED if imported else NEW
        states[f"header.{field}"] = {"label": field, "rows": int(value is not None), "state": state,
                                     **({"source_report_id": carry.get("source_report_id")} if carry else {})}
    return states
