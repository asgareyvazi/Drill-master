"""M464-M466: EOWR source-data sections — bit records, BHA, time logs, material requests, equipment logs.

Until M464 the EOWR collected these six record sets but did not render them (manifest status NOT_RENDERED,
"see the professional workbook export"). This module turns the collected ORM rows into report rows that the HTML,
PDF, Excel and CSV outputs all use, so the report body and the section manifest describe the same thing.

Rules (no fabrication, nothing silent):

* **Source data only.** Every rendered row is a stored record of the selected well; every row names its source
  (table, primary key and, where recorded, the daily report it belongs to). Nothing is derived, summed, deduplicated
  or converted: values are reproduced as stored, with the unit of the column they were entered in.
* **Chronology.** Rows are ordered by their own date (daily-report date for time logs and BHA, report date for bit
  records, request date, service date), then by time of day, then by primary key. Undated rows sort last.
* **States.** A section is ``INCLUDED`` with its row count, ``NOT_RECORDED`` when the scope has no row (stored
  records with an empty payload are counted and named, never shown as zero), ``QUERY_FAILED`` when the table could
  not be read (never shown as "none recorded"), and ``NOT_RENDERED`` when a stored payload exists but cannot be read
  as records (malformed JSON) — the unreadable source IDs are named.
* **Period.** With a period (``parse_period``) only records dated inside it are reported; records without a date
  cannot be placed in a period, so they are excluded and counted, never silently included or dropped.
* **Unknown fields.** A bit/BHA payload key that is not a known column is shown in an "Other fields" column, so a
  stored value never disappears from the report.

SYNTHETIC tests only; no field data is embedded here.
"""
from __future__ import annotations

import html as _html
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

SECTIONS_VERSION = "M464 EOWR source-data sections v1"

AVAILABLE, QUERY_FAILED_STATUS = "available", "query-failed"

# (data key, manifest/report title, Excel sheet name)
SECTION_SPECS: Tuple[Tuple[str, str, str], ...] = (
    ("bit_reports", "12. Bit records", "BitRecords"),
    ("bha_reports", "13. BHA components", "BHAComponents"),
    ("time_logs_24h", "14. 24-hour time logs", "TimeLog24H"),
    ("time_logs_morning", "15. Morning tour time logs", "TimeLogMorning"),
    ("requests", "16. Material requests", "MaterialRequests"),
    ("equipment_logs", "17. Equipment logs", "EquipmentLogs"),
)
SECTION_KEYS = tuple(key for key, _title, _sheet in SECTION_SPECS)

# Columns of the W3c bit table (tabs/w3c_section_data.py) with the payload keys that mean the same field. Keys are
# compared after ``_norm`` (lower case, "_" -> " ", single spaces).
BIT_COLUMNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Bit No", ("bit no", "bit number", "bit #", "bit")),
    ("Size (in)", ("size (in)", "size", "bit size")),
    ("Manufacturer", ("manufacture", "manufacturer")),
    ("Type", ("type", "bit type")),
    ("IADC", ("iadc code", "iadc")),
    ("Serial No", ("serial no", "serial number", "serial")),
    ("Depth In (m)", ("depth in (m)", "depth in")),
    ("Depth Out (m)", ("depth out (m)", "depth out")),
    ("Metres Drilled", ("metres drilled", "meters drilled", "bit drilled")),
    ("Hours", ("hours", "bit hours")),
    ("ROP (m/hr)", ("rop (m/hr)", "rop", "avg rop")),
    ("Dull Grade", ("dull grade",)),
    ("Reason Pulled", ("reason pulled",)),
)
# Columns of the W4 BHA table (tabs/w4_Downhole_Widget.py).
BHA_COLUMNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Component Name", ("component name", "component")),
    ("Tool Type", ("tool type",)),
    ("OD (in)", ("od (in)", "od")),
    ("ID (in)", ("id (in)", "id")),
    ("Length (m)", ("length (m)", "length")),
    ("Serial No", ("serial no", "serial number", "serial")),
    ("Connection Type", ("connection type", "connection")),
    ("Remarks", ("remarks",)),
)
# Fields of the W3c/W4 tables that the EOWR deliberately leaves to the workbook are still reproduced, in "Other".
TIME_LOG_COLUMNS = ("Date", "DDR #", "From", "To", "Duration (h)", "Phase", "Main code", "Sub code", "Status", "NPT",
                    "NPT category", "Activity", "Contractor", "Source")
REQUEST_COLUMNS = ("Request date", "Requested items", "Requested qty", "Unit (requested)", "Outstanding items",
                   "Outstanding qty", "Received items", "Received qty", "Received date", "Backload items",
                   "Backload qty", "Backload date", "Status", "Remarks", "Source")
EQUIPMENT_COLUMNS = ("Service date", "Type", "Name", "Equipment ID", "Manufacturer", "Serial No", "Service type",
                     "Service provider", "Hours worked (h)", "Status", "Notes", "Source")
COLUMNS: Dict[str, Tuple[str, ...]] = {
    "bit_reports": ("Report date",) + tuple(c for c, _a in BIT_COLUMNS) + ("Other fields", "Source"),
    "bha_reports": ("DDR date", "BHA", "#") + tuple(c for c, _a in BHA_COLUMNS) + ("Other fields", "Source"),
    "time_logs_24h": TIME_LOG_COLUMNS,
    "time_logs_morning": TIME_LOG_COLUMNS,
    "requests": REQUEST_COLUMNS,
    "equipment_logs": EQUIPMENT_COLUMNS,
}
NOTES: Dict[str, str] = {
    "bit_reports": ("Each stored bit report is a snapshot of the bit table; a bit listed in several snapshots appears "
                    "once per snapshot (no identity rule is assumed, nothing is deduplicated). Values are reproduced "
                    "as stored in the W3c bit table units."),
    "bha_reports": ("Components are listed in their stored order; no string length or weight is derived. Legacy "
                    "named BHA configurations are listed under their configuration name."),
    "time_logs_24h": "Ordered by daily-report date and start time. Durations are the stored values (hours).",
    "time_logs_morning": "Ordered by daily-report date and start time. Durations are the stored values (hours).",
    "requests": ("Quantities are reproduced as stored. Only the requested quantity carries a unit field; outstanding, "
                 "received and backload quantities are stored without their own unit."),
    "equipment_logs": "Ordered by service date; equipment without a service date is listed last.",
}


@dataclass
class SectionResult:
    key: str
    title: str
    status: str                       # INCLUDED / NOT_RECORDED / QUERY_FAILED / NOT_RENDERED (report_sections)
    rows: List[Dict[str, str]] = field(default_factory=list)
    sources: int = 0                  # stored records read for the scope (after the period filter)
    empty_sources: List[str] = field(default_factory=list)
    unreadable: List[str] = field(default_factory=list)
    excluded_undated: int = 0
    detail: str = ""


# ------------------------------------------------------------------------------------------------------- helpers
def _norm(key: Any) -> str:
    return " ".join(str(key).replace("_", " ").lower().split())


def _text(value: Any) -> str:
    """Stored value as display text; an absent value is "—" (never 0, never blank)."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "strftime"):                      # datetime.time
        return value.strftime("%H:%M")
    text = str(value).strip()
    return text if text else "—"


def _date_of(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def parse_period(period: Any) -> Optional[Tuple[date, date]]:
    """``None`` (whole well) or an inclusive (from, to) pair of dates / ISO strings. Anything else is refused."""
    if period is None:
        return None
    if not isinstance(period, (tuple, list)) or len(period) != 2:
        raise ValueError("EOWR period must be a (from, to) pair")
    out = []
    for value in period:
        if isinstance(value, str):
            value = date.fromisoformat(value.strip())
        value = _date_of(value)
        if value is None:
            raise ValueError("EOWR period bounds must be dates")
        out.append(value)
    if out[0] > out[1]:
        raise ValueError(f"EOWR period starts after it ends ({out[0]} > {out[1]})")
    return out[0], out[1]


def period_label(period: Optional[Tuple[date, date]]) -> str:
    if period is None:
        return "Whole-Well Aggregate"
    return (f"Period {period[0].isoformat()} to {period[1].isoformat()} (dated records only; sections, surveys, "
            f"personnel, services and transport are undated and stay whole-well)")


def within(value: Any, period: Optional[Tuple[date, date]]) -> bool:
    if period is None:
        return True
    d = _date_of(value)
    return d is not None and period[0] <= d <= period[1]


def filter_period(rows: Optional[Sequence[Any]], period, date_of: Callable[[Any], Any]):
    """(kept rows, number of undated rows excluded). ``None`` (query failed) stays ``None``."""
    if rows is None or period is None:
        return rows, 0
    kept = [r for r in rows if within(date_of(r), period)]
    undated = sum(1 for r in rows if _date_of(date_of(r)) is None)
    return kept, undated


def _payload_records(value: Any) -> Tuple[Optional[List[Tuple[str, Dict[str, Any]]]], str]:
    """Stored JSON payload -> [(configuration name, record)], or (None, reason) when it is not readable as records."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return [], ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            return None, f"malformed JSON ({exc.msg})"
    if value is None:
        return [], ""
    if isinstance(value, list):
        if not all(isinstance(r, dict) for r in value):
            return None, "not a list of records"
        return [("", r) for r in value], ""
    if isinstance(value, dict):                          # legacy named configurations {name: [records]}
        out: List[Tuple[str, Dict[str, Any]]] = []
        for name, rows in value.items():
            if isinstance(rows, str):
                try:
                    rows = json.loads(rows)
                except ValueError as exc:
                    return None, f"configuration {name!r}: malformed JSON ({exc.msg})"
            if rows is None:
                continue
            if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                return None, f"configuration {name!r} is not a list of records"
            out.extend((str(name), r) for r in rows)
        return out, ""
    return None, f"unexpected payload type {type(value).__name__}"


def _map_columns(record: Dict[str, Any], columns) -> Dict[str, str]:
    by_norm = {}
    for key, value in record.items():
        by_norm.setdefault(_norm(key), (key, value))
    used = set()
    out: Dict[str, str] = {}
    for column, aliases in columns:
        hit = next((a for a in (_norm(column),) + aliases if a in by_norm), None)
        if hit is None:
            out[column] = "—"
        else:
            used.add(hit)
            out[column] = _text(by_norm[hit][1])
    other = [f"{key}={_text(value)}" for norm, (key, value) in by_norm.items()
             if norm not in used and value not in (None, "")]
    out["Other fields"] = "; ".join(other) if other else "—"
    return out


def _sort_key(d: Any, *rest: Any) -> Tuple:
    d = _date_of(d)
    return (d is None, d or date.min) + tuple((x is None, x if x is not None else 0) for x in rest)


def _report_index(daily_reports: Iterable[Any]) -> Dict[Any, Tuple[Optional[date], Any]]:
    return {getattr(r, "id", None): (_date_of(getattr(r, "report_date", None)), getattr(r, "report_number", None))
            for r in daily_reports or ()}


def _ddr_ref(report_id: Any, index) -> str:
    if report_id is None:
        return "no daily report"
    d, number = index.get(report_id, (None, None))
    return f"DDR id {report_id}" + (f" #{number}" if number not in (None, "") else "") + (f" {d}" if d else "")


# ---------------------------------------------------------------------------------------------- section builders
def _bit_rows(records, index):
    rows, empty, unreadable, sources = [], [], [], 0
    for rep in sorted(records, key=lambda r: _sort_key(r.report_date, r.id)):
        sources += 1
        src = f"bit_reports id {rep.id} ({_ddr_ref(rep.report_id, index)})"
        payload, reason = _payload_records(rep.bit_records_json)
        if payload is None:
            unreadable.append(f"{src}: {reason}")
            continue
        if not payload:
            empty.append(src)
            continue
        for n, (_cfg, rec) in enumerate(payload, 1):
            row = {"Report date": _text(rep.report_date)}
            row.update(_map_columns(rec, BIT_COLUMNS))
            row["Source"] = f"{src}, record {n}"
            rows.append(row)
    return rows, sources, empty, unreadable


def _bha_rows(records, index):
    rows, empty, unreadable, sources = [], [], [], 0

    def key(r):
        return _sort_key(index.get(r.report_id, (None, None))[0], r.id)

    for rep in sorted(records, key=key):
        sources += 1
        src = f"bha_reports id {rep.id} ({_ddr_ref(rep.report_id, index)})"
        payload, reason = _payload_records(rep.bha_data_json)
        if payload is None:
            unreadable.append(f"{src}: {reason}")
            continue
        if not payload:
            empty.append(src)
            continue
        for n, (cfg, rec) in enumerate(payload, 1):
            row = {"DDR date": _text(index.get(rep.report_id, (None, None))[0]),
                   "BHA": _text(rep.bha_name) + (f" / {cfg} (legacy configuration)" if cfg else ""), "#": str(n)}
            row.update(_map_columns(rec, BHA_COLUMNS))
            row["Source"] = f"{src}, component {n}"
            rows.append(row)
    return rows, sources, empty, unreadable


def _time_rows(records, index, table):
    rows = []

    def key(r):
        return _sort_key(index.get(r.report_id, (None, None))[0], r.time_from, r.id)

    for log in sorted(records, key=key):
        d, number = index.get(log.report_id, (None, None))
        rows.append({
            "Date": _text(d), "DDR #": _text(number), "From": _text(log.time_from), "To": _text(log.time_to),
            "Duration (h)": _text(log.duration), "Phase": _text(log.main_phase), "Main code": _text(log.main_code),
            "Sub code": _text(log.sub_code), "Status": _text(log.status),
            "NPT": "Yes" if log.is_npt else ("No" if log.is_npt is not None else "—"),
            "NPT category": _text(log.npt_category), "Activity": _text(log.activity_description),
            "Contractor": _text(log.contractor), "Source": f"{table} id {log.id} ({_ddr_ref(log.report_id, index)})",
        })
    return rows, len(records), [], []


def _request_rows(records, index):
    rows = []
    for r in sorted(records, key=lambda r: _sort_key(r.request_date, r.id)):
        rows.append({
            "Request date": _text(r.request_date), "Requested items": _text(r.requested_items),
            "Requested qty": _text(r.requested_quantity), "Unit (requested)": _text(r.requested_unit),
            "Outstanding items": _text(r.outstanding_items), "Outstanding qty": _text(r.outstanding_quantity),
            "Received items": _text(r.received_items), "Received qty": _text(r.received_quantity),
            "Received date": _text(r.received_date), "Backload items": _text(r.backload_items),
            "Backload qty": _text(r.backload_quantity), "Backload date": _text(r.backload_date),
            "Status": _text(r.status), "Remarks": _text(r.remarks),
            "Source": f"material_requests id {r.id} ({_ddr_ref(r.report_id, index)})",
        })
    return rows, len(records), [], []


def _equipment_rows(records, index):
    rows = []
    for e in sorted(records, key=lambda e: _sort_key(e.service_date, e.id)):
        rows.append({
            "Service date": _text(e.service_date), "Type": _text(e.equipment_type), "Name": _text(e.equipment_name),
            "Equipment ID": _text(e.equipment_id), "Manufacturer": _text(e.manufacturer),
            "Serial No": _text(e.serial_number), "Service type": _text(e.service_type),
            "Service provider": _text(e.service_provider), "Hours worked (h)": _text(e.hours_worked),
            "Status": _text(e.status), "Notes": _text(e.notes),
            "Source": f"equipment_logs id {e.id} ({_ddr_ref(e.report_id, index)})",
        })
    return rows, len(records), [], []


_BUILDERS = {
    "bit_reports": _bit_rows,
    "bha_reports": _bha_rows,
    "time_logs_24h": lambda recs, idx: _time_rows(recs, idx, "time_logs_24h"),
    "time_logs_morning": lambda recs, idx: _time_rows(recs, idx, "time_logs_morning"),
    "requests": _request_rows,
    "equipment_logs": _equipment_rows,
}


def analyse(data: Dict[str, Any]) -> List[SectionResult]:
    """The six source-data sections of an EOWR from its collected data (pure; the same for every format)."""
    from core.report_sections import INCLUDED, NOT_RECORDED, NOT_RENDERED, QUERY_FAILED

    index = _report_index(data.get("daily_reports") or ())
    status = data.get("source_query_status") or {}
    excluded = data.get("period_excluded_undated") or {}
    out = []
    for key, title, _sheet in SECTION_SPECS:
        records = data.get(key)
        undated = int(excluded.get(key) or 0)
        undated_text = (f"; {undated} undated record(s) excluded from the period" if undated else "")
        if records is None or status.get(key) == QUERY_FAILED_STATUS:
            out.append(SectionResult(key, title, QUERY_FAILED, excluded_undated=undated,
                                     detail=f"{key} query failed; this section is not assessed (not 'none recorded')"))
            continue
        rows, sources, empty, unreadable = _BUILDERS[key](list(records), index)
        if unreadable:
            state = NOT_RENDERED
            detail = (f"{len(unreadable)} of {sources} stored record(s) unreadable and not rendered: "
                      f"{'; '.join(unreadable)}; {len(rows)} row(s) rendered from the others")
        elif rows:
            state, detail = INCLUDED, f"{len(rows)} row(s) from {sources} stored record(s)"
        else:
            state = NOT_RECORDED
            detail = (f"{len(empty)} stored record(s) with no rows ({'; '.join(empty)}); not a reported zero"
                      if empty else "none recorded for this scope; not a reported zero")
        out.append(SectionResult(key, title, state, rows, sources, empty, unreadable, undated, detail + undated_text))
    return out


# ------------------------------------------------------------------------------------------------------- output
def html_sections(results: Sequence[SectionResult]) -> str:
    """Escaped HTML for the six sections (every stored text is escaped: payloads are user/import data)."""
    from core.report_sections import NOT_RECORDED, QUERY_FAILED

    e = _html.escape
    parts = []
    for res in results:
        parts.append(f"<h1>{e(res.title)}</h1>")
        parts.append(f'<p style="font-size:7pt;color:#666">{e(NOTES[res.key])}</p>')
        if res.status == QUERY_FAILED:
            parts.append(f'<p class="note">Data unavailable — the {e(res.key)} query failed; this section is not '
                         f'assessed and is not a statement that nothing was recorded.</p>')
            continue
        if res.status == NOT_RECORDED:
            parts.append(f'<p class="note">Not recorded: {e(res.detail)}.</p>')
        if res.unreadable:
            parts.append('<p class="note"><b>Unreadable stored records (not rendered):</b> '
                         + e("; ".join(res.unreadable)) + "</p>")
        if res.excluded_undated:
            parts.append(f'<p class="note">{res.excluded_undated} undated record(s) cannot be placed in the period '
                         f'and are excluded.</p>')
        if res.rows:
            cols = COLUMNS[res.key]
            parts.append('<table class="table"><tr>' + "".join(f"<th>{e(c)}</th>" for c in cols) + "</tr>")
            for row in res.rows:
                parts.append("<tr>" + "".join(f"<td>{e(row.get(c, '—'))}</td>" for c in cols) + "</tr>")
            parts.append("</table>")
    return "".join(parts)


def sheet_records(res: SectionResult) -> List[Dict[str, str]]:
    """Rows for the Excel/CSV sheet of a section; a section without rows gets one explicit status row."""
    if res.rows:
        return [{c: row.get(c, "—") for c in COLUMNS[res.key]} for row in res.rows]
    return [{"Status": res.status, "Detail": res.detail}]
