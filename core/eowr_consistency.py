"""M551-M555 (U5): non-destructive EOWR data-consistency analyzer.

Input: the dictionary that ``EOWRReportEngine._collect_data`` returns (stored rows of one well, optionally limited to
a period). Output: one result per rule with a status, the findings and their lineage (table, record id, field,
stored value). The analyzer reads attributes only: it never writes, repairs, converts, infers or fills a value, and
it does not change what the EOWR reports elsewhere.

Statuses
* ``CONSISTENT``        — the rule was checked on at least one complete record set and nothing contradicts it;
* ``INCONSISTENT``      — at least one contradiction between stored values (each listed with its sources). It is a
                          review item, not a verdict on which value is wrong;
* ``NOT_ASSESSED``      — the source query failed (``source_query_status == query-failed``), so nothing is known;
* ``INSUFFICIENT_DATA`` — the source rows exist but lack the values the rule needs (none is assumed);
* ``NOT_APPLICABLE``    — the rule does not apply to this report scope (stated why).

Rules (depths are the stored metre columns of the canonical schema — daily_report.depth_* and survey md — compared
as stored, never converted; durations are the stored hours)
* R1 ``depth_continuity``      — per wellbore, a report's depth at 00:00 equals the previous report's depth at 24:00;
* R2 ``depth_within_day``      — depth at 24:00 is not below depth at 00:00 (a decrease may be a plug-back or a
                                 sidetrack; it is flagged for review, never assumed);
* R3 ``time_log_day_total``    — the 24 h time-log durations of one daily report sum to at most 24 h;
* R4 ``time_log_interval``     — each duration equals its from/to interval (24:00 wrap allowed) within one minute;
* R5 ``npt_summary``           — the EOWR summary NPT equals the NPT recomputed here from the same rows (known only
                                 when every row has an NPT flag and every NPT row a valid duration, the
                                 ``core.operational_time`` definition);
* R6 ``report_identity``       — no two daily reports of one wellbore share a date and report number;
* R7 ``bit_run_depths``        — a bit record's depth out is not above its depth in, and stated metres drilled equal
                                 out - in;
* R8 ``survey_within_depth``   — no survey station is deeper (MD) than the deepest reported daily depth (whole-well
                                 reports only: surveys are not period-filtered, so a period report is NOT_APPLICABLE).

SCREENING data-quality aid for review; not a signed or approved report.
"""
from __future__ import annotations

import html as _html
from datetime import datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ANALYZER_VERSION = "M551 EOWR consistency analyzer v1"
CONSISTENT, INCONSISTENT, NOT_ASSESSED, INSUFFICIENT_DATA, NOT_APPLICABLE = (
    "CONSISTENT", "INCONSISTENT", "NOT_ASSESSED", "INSUFFICIENT_DATA", "NOT_APPLICABLE")
STATUSES = (CONSISTENT, INCONSISTENT, NOT_ASSESSED, INSUFFICIENT_DATA, NOT_APPLICABLE)
DEPTH_TOL_M = 0.01
HOURS_TOL = 1e-6
INTERVAL_TOL_H = 1.0 / 60.0
NPT_TOL_H = 1e-6
QUERY_FAILED = "query-failed"

RULES: Tuple[Tuple[str, str], ...] = (
    ("depth_continuity", "Depth at 00:00 equals the previous report's depth at 24:00 (per wellbore)"),
    ("depth_within_day", "Depth at 24:00 is not below depth at 00:00"),
    ("time_log_day_total", "24 h time-log durations of one report sum to at most 24 h"),
    ("time_log_interval", "Each time-log duration equals its from/to interval (within 1 min)"),
    ("npt_summary", "Summary NPT equals the NPT recomputed from the time-log rows"),
    ("report_identity", "No two daily reports of one wellbore share a date and report number"),
    ("bit_run_depths", "Bit depth out is not above depth in; metres drilled equal out - in"),
    ("survey_within_depth", "No survey station is deeper than the deepest reported daily depth"),
)
RULE_KEYS = tuple(key for key, _title in RULES)


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text or text in ("—", "-"):
            return None
        value = text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None  # silent-ok: a non-numeric stored value counts as missing -> INSUFFICIENT_DATA, never 0
    return number if number == number and abs(number) != float("inf") else None


def _src(table: str, row: Any, field: str, value: Any) -> Dict[str, Any]:
    return {"table": table, "id": getattr(row, "id", None), "field": field, "value": value}


def _result(key: str, status: str, reason: str, findings=None, checked: int = 0, lineage=None) -> Dict[str, Any]:
    title = dict(RULES)[key]
    return {"rule": key, "title": title, "status": status, "reason": reason, "checked": checked,
            "findings": list(findings or []), "lineage": list(lineage or [])}


def _verdict(key: str, findings: List[Dict[str, Any]], checked: int, lineage, empty_reason: str) -> Dict[str, Any]:
    if findings:
        return _result(key, INCONSISTENT, f"{len(findings)} contradiction(s) in {checked} check(s)", findings,
                       checked, lineage)
    if checked:
        return _result(key, CONSISTENT, f"{checked} check(s), no contradiction", [], checked, lineage)
    return _result(key, INSUFFICIENT_DATA, empty_reason, [], 0, lineage)


def _failed(data: Dict[str, Any], source: str) -> bool:
    return (data.get("source_query_status") or {}).get(source) == QUERY_FAILED or data.get(source, []) is None


def _reports_by_bore(data) -> Dict[Any, List[Any]]:
    groups: Dict[Any, List[Any]] = {}
    for r in data.get("daily_reports") or []:
        groups.setdefault(getattr(r, "wellbore_id", None), []).append(r)
    for rows in groups.values():
        rows.sort(key=lambda r: (getattr(r, "report_date", None) is None, getattr(r, "report_date", None) or 0,
                                 getattr(r, "report_number", None) or 0, getattr(r, "id", 0) or 0))
    return groups


# ---- rules ---------------------------------------------------------------------------------------------------------
def _depth_continuity(data):
    findings, checked, lineage = [], 0, []
    for bore, rows in _reports_by_bore(data).items():
        for prev, cur in zip(rows, rows[1:]):
            end, start = _num(getattr(prev, "depth_2400", None)), _num(getattr(cur, "depth_0000", None))
            if end is None or start is None:
                continue
            checked += 1
            src = [_src("daily_reports", prev, "depth_2400", end), _src("daily_reports", cur, "depth_0000", start)]
            lineage.extend(src)
            if abs(end - start) > DEPTH_TOL_M:
                findings.append({"message": f"wellbore {bore}: report {getattr(cur, 'id', None)} starts at {start:g} m"
                                            f" but report {getattr(prev, 'id', None)} ended at {end:g} m",
                                 "sources": src})
    return _verdict("depth_continuity", findings, checked, lineage,
                    "fewer than two consecutive reports with both depths stored")


def _depth_within_day(data):
    findings, checked, lineage = [], 0, []
    for r in data.get("daily_reports") or []:
        start, end = _num(getattr(r, "depth_0000", None)), _num(getattr(r, "depth_2400", None))
        if start is None or end is None:
            continue
        checked += 1
        src = [_src("daily_reports", r, "depth_0000", start), _src("daily_reports", r, "depth_2400", end)]
        lineage.extend(src)
        if end < start - DEPTH_TOL_M:
            findings.append({"message": f"report {getattr(r, 'id', None)}: depth decreased {start:g} -> {end:g} m "
                                        "(plug-back / sidetrack? review; not assumed)", "sources": src})
    return _verdict("depth_within_day", findings, checked, lineage, "no report stores both depths")


def _logs_by_report(rows) -> Dict[Any, List[Any]]:
    groups: Dict[Any, List[Any]] = {}
    for row in rows or []:
        groups.setdefault(getattr(row, "report_id", None), []).append(row)
    return groups


def _time_log_day_total(data):
    if _failed(data, "time_logs_24h"):
        return _result("time_log_day_total", NOT_ASSESSED, "the 24 h time-log query failed")
    findings, checked, lineage = [], 0, []
    for report_id, rows in _logs_by_report(data.get("time_logs_24h")).items():
        durations = [_num(getattr(r, "duration", None)) for r in rows]
        if report_id is None or any(d is None for d in durations):
            continue
        checked += 1
        src = [_src("time_logs_24h", r, "duration", d) for r, d in zip(rows, durations)]
        lineage.extend(src)
        total = sum(durations)
        if total > 24.0 + HOURS_TOL:
            findings.append({"message": f"daily report {report_id}: time logs sum to {total:g} h (> 24 h)",
                             "sources": src})
    return _verdict("time_log_day_total", findings, checked, lineage,
                    "no daily report has a complete set of stored durations")


def _hours_between(t_from: Any, t_to: Any) -> Optional[float]:
    if not isinstance(t_from, time) or not isinstance(t_to, time):
        return None
    base = datetime(2000, 1, 1)
    a, b = datetime.combine(base, t_from), datetime.combine(base, t_to)
    if b <= a:
        b += timedelta(days=1)                       # 24:00 wrap (e.g. 18:00 -> 00:00)
    return (b - a).total_seconds() / 3600.0


def _time_log_interval(data):
    if _failed(data, "time_logs_24h"):
        return _result("time_log_interval", NOT_ASSESSED, "the 24 h time-log query failed")
    findings, checked, lineage = [], 0, []
    for r in data.get("time_logs_24h") or []:
        duration = _num(getattr(r, "duration", None))
        span = _hours_between(getattr(r, "time_from", None), getattr(r, "time_to", None))
        if duration is None or span is None:
            continue
        checked += 1
        src = [_src("time_logs_24h", r, "time_from", str(r.time_from)), _src("time_logs_24h", r, "time_to",
                                                                              str(r.time_to)),
               _src("time_logs_24h", r, "duration", duration)]
        lineage.extend(src)
        if abs(span - duration) > INTERVAL_TOL_H:
            findings.append({"message": f"time log {getattr(r, 'id', None)}: {r.time_from}-{r.time_to} is {span:g} h "
                                        f"but the stored duration is {duration:g} h", "sources": src})
    return _verdict("time_log_interval", findings, checked, lineage, "no time log stores from, to and duration")


def _npt_summary(data):
    if _failed(data, "time_logs_24h"):
        return _result("npt_summary", NOT_ASSESSED, "the 24 h time-log query failed")
    rows = list(data.get("time_logs_24h") or [])
    summary = (data.get("summary") or {}).get("total_npt")
    if not rows:
        return _result("npt_summary", INSUFFICIENT_DATA, "no 24 h time logs")
    npt, complete = 0.0, True
    for r in rows:
        d, flag = _num(getattr(r, "duration", None)), getattr(r, "is_npt", None)
        if flag is not True and flag is not False:
            complete = False                          # an unclassified row cannot be counted either way
        elif flag is True:
            if d is None or d < 0:
                complete = False
            else:
                npt += d
    lineage = [_src("time_logs_24h", r, "is_npt", getattr(r, "is_npt", None)) for r in rows]
    if not complete:
        if summary is None:
            return _result("npt_summary", INSUFFICIENT_DATA, "some rows lack an NPT flag or an NPT row lacks a "
                                                              "duration; the summary NPT is (correctly) unknown", [],
                           0, lineage)
        return _result("npt_summary", INCONSISTENT, "the summary states an NPT although rows lack an NPT flag or an "
                                                     "NPT duration", [{"message": f"summary NPT {summary} h from incomplete "
                                                                              "rows", "sources": lineage}], 1, lineage)
    s = _num(summary)
    if s is None or abs(s - npt) > NPT_TOL_H:
        return _result("npt_summary", INCONSISTENT, f"summary NPT {summary} h, rows give {npt:g} h",
                       [{"message": f"summary NPT {summary} h, rows give {npt:g} h", "sources": lineage}], 1,
                       lineage)
    return _result("npt_summary", CONSISTENT, f"summary NPT {npt:g} h equals the rows", [], 1, lineage)


def _report_identity(data):
    findings, checked, lineage = [], 0, []
    for bore, rows in _reports_by_bore(data).items():
        seen: Dict[Tuple[Any, Any], Any] = {}
        for r in rows:
            key = (getattr(r, "report_date", None), getattr(r, "report_number", None))
            if key[0] is None or key[1] is None:
                continue
            checked += 1
            src = _src("daily_reports", r, "report_date/report_number", f"{key[0]} #{key[1]}")
            lineage.append(src)
            if key in seen:
                findings.append({"message": f"wellbore {bore}: reports {seen[key]['id']} and {getattr(r, 'id', None)} "
                                            f"are both {key[0]} #{key[1]}", "sources": [seen[key], src]})
            else:
                seen[key] = src
    return _verdict("report_identity", findings, checked, lineage, "no report stores a date and number")


def _bit_run_depths(data):
    if _failed(data, "bit_reports"):
        return _result("bit_run_depths", NOT_ASSESSED, "the bit-report query failed")
    from core import eowr_sections as es

    findings, checked, lineage = [], 0, []
    for rep in data.get("bit_reports") or []:
        payload, _reason = es._payload_records(getattr(rep, "bit_records_json", None))
        for n, (_cfg, record) in enumerate(payload or [], 1):
            mapped = es._map_columns(record, es.BIT_COLUMNS)
            d_in, d_out = _num(mapped.get("Depth In (m)")), _num(mapped.get("Depth Out (m)"))
            if d_in is None or d_out is None:
                continue
            checked += 1
            drilled = _num(mapped.get("Metres Drilled"))
            src = [{"table": "bit_reports", "id": getattr(rep, "id", None), "field": f"record {n} depth in/out",
                    "value": f"{d_in:g} / {d_out:g}"}]
            if drilled is not None:
                src.append({"table": "bit_reports", "id": getattr(rep, "id", None),
                            "field": f"record {n} metres drilled", "value": drilled})
            lineage.extend(src)
            if d_out < d_in - DEPTH_TOL_M:
                findings.append({"message": f"bit report {getattr(rep, 'id', None)} record {n}: depth out {d_out:g} m "
                                            f"above depth in {d_in:g} m", "sources": src})
            elif drilled is not None and abs((d_out - d_in) - drilled) > DEPTH_TOL_M:
                findings.append({"message": f"bit report {getattr(rep, 'id', None)} record {n}: metres drilled "
                                            f"{drilled:g} != out - in {d_out - d_in:g}", "sources": src})
    return _verdict("bit_run_depths", findings, checked, lineage, "no bit record stores both depth in and depth out")


def _survey_within_depth(data):
    if data.get("period") is not None:
        return _result("survey_within_depth", NOT_APPLICABLE,
                       "period report: surveys are not period-filtered, so they cannot be compared with the "
                       "period's daily depths")
    depths = [(r, _num(getattr(r, "depth_2400", None))) for r in data.get("daily_reports") or []]
    depths = [(r, d) for r, d in depths if d is not None]
    stations = [s for s in data.get("surveys") or [] if _num(_get(s, "md")) is not None]
    if not depths or not stations:
        return _result("survey_within_depth", INSUFFICIENT_DATA, "needs stored daily depths and survey stations")
    deepest_row, deepest = max(depths, key=lambda item: item[1])
    station = max(stations, key=lambda s: _num(_get(s, "md")))
    md = _num(_get(station, "md"))
    src = [_src("daily_reports", deepest_row, "depth_2400", deepest),
           {"table": "survey_points", "id": _get(station, "id"), "field": "md", "value": md}]
    if md > deepest + DEPTH_TOL_M:
        return _result("survey_within_depth", INCONSISTENT, f"deepest survey MD {md:g} m > deepest daily depth "
                                                            f"{deepest:g} m",
                       [{"message": f"survey station at {md:g} m is deeper than any reported depth ({deepest:g} m)",
                         "sources": src}], 1, src)
    return _result("survey_within_depth", CONSISTENT, f"deepest survey MD {md:g} m <= deepest daily depth "
                                                      f"{deepest:g} m", [], 1, src)


def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


_RULE_FUNCS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "depth_continuity": _depth_continuity, "depth_within_day": _depth_within_day,
    "time_log_day_total": _time_log_day_total, "time_log_interval": _time_log_interval,
    "npt_summary": _npt_summary, "report_identity": _report_identity, "bit_run_depths": _bit_run_depths,
    "survey_within_depth": _survey_within_depth,
}


def analyze(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """All rules on the collected EOWR data; read-only. An empty / failed collection is NOT_ASSESSED throughout."""
    if not data:
        results = [_result(key, NOT_ASSESSED, "no EOWR data was collected") for key in RULE_KEYS]
    else:
        results = [_RULE_FUNCS[key](data) for key in RULE_KEYS]
    counts = {status: sum(1 for r in results if r["status"] == status) for status in STATUSES}
    return {"version": ANALYZER_VERSION, "results": results, "counts": counts,
            "label": "SCREENING data-consistency review aid — contradictions are review items, nothing was changed"}


def manifest_rows(analysis: Dict[str, Any]) -> List[List[str]]:
    rows = [["consistency.version", analysis["version"]]]
    rows += [[f"consistency.{r['rule']}", f"{r['status']} — {r['reason']}"] for r in analysis["results"]]
    return rows


def sheet_records(analysis: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for r in analysis["results"]:
        if not r["findings"]:
            out.append({"Rule": r["title"], "Status": r["status"], "Finding": r["reason"], "Sources": "—"})
        for f in r["findings"]:
            out.append({"Rule": r["title"], "Status": r["status"], "Finding": f["message"],
                        "Sources": "; ".join(f"{s['table']} id {s['id']} {s['field']}={s['value']}"
                                             for s in f["sources"])})
    return out


def html_section(analysis: Dict[str, Any]) -> str:
    e = _html.escape
    body = "".join(f"<tr><td>{e(row['Rule'])}</td><td><b>{e(row['Status'])}</b></td><td>{e(row['Finding'])}</td>"
                   f"<td>{e(row['Sources'])}</td></tr>" for row in sheet_records(analysis))
    return (f'<div class="dm-consistency"><h2>Data consistency review ({e(analysis["version"])})</h2>'
            f'<p>{e(analysis["label"])}</p><table border="1" cellspacing="0" cellpadding="3">'
            f"<tr><th>Rule</th><th>Status</th><th>Finding</th><th>Sources</th></tr>{body}</table></div>")


def statuses(analysis: Dict[str, Any]) -> Dict[str, str]:
    return {r["rule"]: r["status"] for r in analysis["results"]}


def rules_table() -> Sequence[Tuple[str, str]]:
    return RULES
