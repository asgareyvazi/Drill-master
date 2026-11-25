"""M320-D (M287): section manifest of a report — no section is omitted silently.

Every section that a DDR, EOWR, NPT, Cost or Plan template knows about (M333 added the last three) is listed with
one status:

* ``INCLUDED``       – rendered with its rows (the row count is given);
* ``NOT_RECORDED``   – rendered as an explicit "Not recorded" statement (never as a zero or a blank heading);
* ``SUMMARISED``     – rendered as counts only (the rows are not reproduced in the report body);
* ``QUERY_FAILED``   – the data could not be read; totals are not assessed;
* ``NOT_RENDERED``   – data was collected for the scope but is not rendered: the template does not render it (Plan:
  inactive versions) or a stored payload cannot be read as records (EOWR, M464). It is named, with its row count
  and the unreadable source IDs, so nothing disappears unannounced.

``manifest(kind, data)`` builds the list from the engine's collected data; ``report_provenance.emit`` adds it to the
provenance, so it appears in HTML, PDF, Excel and CSV alike. Kinds without a manifest are stated as such.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MANIFEST_VERSION = "M320-D report section manifest v3"          # v2 (M333): + npt, cost, plan; v3 (M464): EOWR
#                                                                  source-data sections rendered
INCLUDED, NOT_RECORDED, SUMMARISED, QUERY_FAILED, NOT_RENDERED = (
    "INCLUDED", "NOT_RECORDED", "SUMMARISED", "QUERY_FAILED", "NOT_RENDERED")
MANIFEST_KINDS = ("ddr", "eowr", "npt", "cost", "plan")


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
    # M464: the six source-data sections are rendered (core/eowr_sections.py); their status comes from the same
    # analysis the report body uses, so the manifest cannot claim rows the body does not show.
    from core import eowr_sections

    for res in eowr_sections.analyse(data):
        entries.append(_entry(res.title, res.status, None if res.status == QUERY_FAILED else len(res.rows),
                              res.detail))
    period = data.get("period")
    excluded = {k: v for k, v in (data.get("period_excluded_undated") or {}).items() if v}
    entries.insert(0, _entry("Scope", INCLUDED, None, eowr_sections.period_label(period) + (
        "; undated records excluded: " + ", ".join(f"{k} {v}" for k, v in sorted(excluded.items()))
        if excluded else "")))
    return entries


def _size(value: Any) -> int:
    """Rows of an aggregation (one per group / line); a scalar counts like ``_count``."""
    return len(value) if isinstance(value, (dict, list, tuple)) else _count(value)


def _listed(title: str, value: Any, detail_empty: str) -> Dict[str, Any]:
    n = _size(value)
    return _entry(title, INCLUDED if n else NOT_RECORDED, n, "" if n else detail_empty)


def _known(title: str, value: Any, detail_unknown: str) -> Dict[str, Any]:
    """A computed figure: INCLUDED when known; NOT_RECORDED with the reason when it is unknown (never shown as 0)."""
    return _entry(title, INCLUDED if value is not None else NOT_RECORDED, None,
                  "" if value is not None else detail_unknown)


def npt_manifest(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """M333 (A-7): the NPT report template (``NPTReportEngine._build_html``)."""
    windowed = data.get("from_date") not in (None, "Start") or data.get("to_date") not in (None, "End")
    sub = _size(data.get("by_sub_code"))
    no_npt = "no NPT time logs in this scope" if data.get("total_hours") else "no time logged in this scope"
    if data.get("npt_cost") is not None:
        cost = _entry("NPT cost (allocated)", INCLUDED, None, "")
    elif windowed:
        cost = _entry("NPT cost (allocated)", NOT_RECORDED, None,
                      "not allocated for a date window: whole-well cost lines have no date attribution")
    else:
        cost = _entry("NPT cost (allocated)", NOT_RECORDED, None,
                      "needs recorded actual cost in one currency and logged time; not a zero cost")
    return [
        _entry("Header and period", INCLUDED, 1),
        _known("NPT share of logged time", data.get("npt_pct"),
               "no time logged: the NPT share is unknown, not 0 %"),
        _listed("NPT by main code", data.get("by_main_code"), no_npt),
        _entry("NPT by sub code", SUMMARISED if sub > 15 else (INCLUDED if sub else NOT_RECORDED), sub,
               f"top 15 of {sub} sub codes shown" if sub > 15 else ("" if sub else no_npt)),
        _listed("NPT by contractor", data.get("by_contractor"), no_npt),
        _listed("NPT by phase", data.get("by_phase"), no_npt),
        _listed("NPT daily trend", data.get("by_date"), no_npt),
        _listed("NPT event details", data.get("entries"), no_npt),
        cost,
    ]


def cost_manifest(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """M333 (A-7): the Cost report template (``CostReportEngine._build_html``)."""
    no_rate = "no rig day rate, spread rate and projection currency declared: projections are not computed"
    return [
        _entry("Header", INCLUDED, 1),
        _known("Total actual cost", data.get("total_cost"),
               f"no complete actual cost total ({data.get('currency_status') or 'no cost lines'}); not a zero cost"),
        _known("Cost per metre / foot", data.get("cost_per_meter"),
               "needs a known actual total and a recorded depth"),
        _known("Projection (rate × days)", data.get("projected_total_cost"), no_rate),
        _known("NPT / productive cost (projection)", data.get("npt_cost"),
               no_rate if data.get("total_daily_cost") is None else "no time logged: NPT days unknown"),
        _listed("Cost by category", data.get("categories"), "no cost records: not a reported zero"),
        _listed("Source cost lines (unaggregated)", data.get("records"), "no cost records: not a reported zero"),
        _listed("Cumulative cost vs depth", data.get("cumulative"), no_rate),
    ]


def plan_manifest(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """M333 (A-7): the Plan report template (``PlanReportEngine._build_html``); only the active plan is rendered."""
    plan = data.get("plan")
    name = f"{getattr(plan, 'plan_name', '') or '?'} v{getattr(plan, 'plan_version', '') or '?'}" if plan else ""
    others = max(_size(data.get("all_plans")) - 1, 0)
    return [
        _entry("Plan information", INCLUDED if plan is not None else NOT_RECORDED, 1 if plan is not None else 0,
               f"active plan {name}" if plan is not None else "no active plan"),
        _known("Planned totals (days / hours)", data.get("total_hrs"),
               "at least one activity has no planned duration: the total is unknown, not partial"),
        _known("Planned final depth", data.get("max_depth"), "no activity has a planned depth"),
        _listed("Hours by phase", data.get("by_phase"), "no planned activities"),
        _listed("Activity schedule", data.get("activities"), "no planned activities"),
        _entry("Other plan versions", NOT_RENDERED if others else INCLUDED, others,
               f"{others} inactive plan version(s) collected but not rendered" if others else "no other versions"),
    ]


def manifest(kind: str, data: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(data, dict):
        return None
    if kind == "ddr":
        return ddr_manifest(data)
    if kind == "eowr":
        return eowr_manifest(data)
    builder = {"npt": npt_manifest, "cost": cost_manifest, "plan": plan_manifest}.get(kind)
    return builder(data) if builder else None


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
