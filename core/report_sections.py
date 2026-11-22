"""M320-D (M287): section manifest of a report — no section is omitted silently.

Every section that a DDR or EOWR template knows about is listed with one status:

* ``INCLUDED``       – rendered with its rows (the row count is given);
* ``NOT_RECORDED``   – rendered as an explicit "Not recorded" statement (never as a zero or a blank heading);
* ``SUMMARISED``     – rendered as counts only (the rows are not reproduced in the report body);
* ``QUERY_FAILED``   – the data could not be read; totals are not assessed;
* ``NOT_RENDERED``   – data was collected for the scope but this template does not render it. It is named, with
  its row count and the export where it does appear, so nothing disappears unannounced.

``manifest(kind, data)`` builds the list from the engine's collected data; ``report_provenance.emit`` adds it to the
provenance, so it appears in HTML, PDF, Excel and CSV alike. Kinds without a manifest are stated as such.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MANIFEST_VERSION = "M320-D report section manifest v1"
INCLUDED, NOT_RECORDED, SUMMARISED, QUERY_FAILED, NOT_RENDERED = (
    "INCLUDED", "NOT_RECORDED", "SUMMARISED", "QUERY_FAILED", "NOT_RENDERED")
MANIFEST_KINDS = ("ddr", "eowr")


def _count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        return 1 if any(v not in (None, "", [], {}) for v in value.values()) else 0
    if isinstance(value, (list, tuple)):
        return len(value)
    return 1 if value else 0


def _entry(title: str, status: str, rows: Optional[int] = None, detail: str = "") -> Dict[str, Any]:
    return {"section": title, "status": status, "rows": rows, "detail": detail}


def _presence(title: str, value: Any, detail_empty: str = "") -> Dict[str, Any]:
    n = _count(value)
    return _entry(title, INCLUDED if n else NOT_RECORDED, n, "" if n else (detail_empty or "no rows for this scope"))


def ddr_manifest(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    total = data.get("total_hrs")
    summary = (data.get("report") or {}).get("summary") or (data.get("snapshot") or {}).get("summary")
    return [
        _entry("Header and depth summary", INCLUDED, 1),
        _presence("Drilling parameters", data.get("params")),
        _presence("Mud properties", data.get("mud")),
        _presence("24-hour operations", data.get("logs_24h")),
        _presence("Morning tour", data.get("logs_morning")),
        _entry("Time analysis", INCLUDED if total else NOT_RECORDED, None,
               "" if total else "no time logged: percentages are unknown, not 100 % productive"),
        _presence("Operations summary", summary, "no summary text on the report"),
    ]


def eowr_manifest(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    cost = data.get("cost_records")
    if cost is None or data.get("cost_query_status") == "query-failed":
        cost_entry = _entry("11. Cost summary", QUERY_FAILED, None, "cost-record query failed; totals not assessed")
    else:
        cost_entry = _presence("11. Cost summary", cost, "no cost records: not a reported zero")
    entries = [
        _entry("1–2. Well information and key personnel", INCLUDED, 1),
        _presence("3. Section summary", data.get("sections")),
        _presence("4. Daily reports summary", data.get("daily_reports")),
        _presence("5. Drilling performance", data.get("drilling_params")),
        _presence("6. Mud summary", data.get("mud_reports")),
        _entry("7. Casing and cementing", SUMMARISED, _count(data.get("cement_reports")) +
               _count(data.get("casing_reports")),
               f"counts only: {_count(data.get('cement_reports'))} cement, {_count(data.get('casing_reports'))} casing "
               f"report(s); rows are in the W3c section pages"),
        _presence("8. Trajectory / survey", data.get("surveys")),
        _presence("9. Safety summary", data.get("safety_reports")),
        _entry("10. Logistics and services", SUMMARISED, _count(data.get("personnel")) + _count(data.get("services"))
               + _count(data.get("transport")),
               f"counts only: {_count(data.get('personnel'))} personnel, {_count(data.get('services'))} services, "
               f"{_count(data.get('transport'))} transport"),
        cost_entry,
    ]
    for key, title in (("bit_reports", "Bit reports"), ("bha_reports", "BHA reports"),
                       ("time_logs_24h", "24-hour time logs"), ("time_logs_morning", "Morning time logs"),
                       ("requests", "Material requests"), ("equipment_logs", "Equipment logs")):
        n = _count(data.get(key))
        entries.append(_entry(title, NOT_RENDERED, n,
                              f"collected ({n} row(s)) but not rendered by the EOWR template; see the professional "
                              f"workbook export" if n else "not rendered by the EOWR template; none recorded"))
    return entries


def manifest(kind: str, data: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(data, dict):
        return None
    if kind == "ddr":
        return ddr_manifest(data)
    if kind == "eowr":
        return eowr_manifest(data)
    return None


def rows(entries: Optional[List[Dict[str, Any]]], kind: str) -> List[List[str]]:
    if entries is None:
        return [["section manifest", f"not available for report kind {kind!r} ({MANIFEST_VERSION} covers "
                                     f"{', '.join(MANIFEST_KINDS)})"]]
    out = [["section manifest", MANIFEST_VERSION]]
    for e in entries:
        rows_text = f", {e['rows']} row(s)" if e["rows"] is not None else ""
        out.append(["section", f"{e['section']}: {e['status']}{rows_text}" + (f" – {e['detail']}" if e["detail"]
                                                                             else "")])
    return out
