"""Report provenance (M93): scope, sources, revisions, methods and the UNSIGNED label on every report.

``build(db, kind, target_id)`` reads what a report of ``kind`` (ddr / eowr / npt / cost / plan) is based on:

* **scope** - well, wellbore (a DDR's own wellbore; otherwise "all wellbores of the well"), report or period;
* **sources** - the tables the report engine reads, with the number of daily reports and their date range;
* **revisions** - the latest report revision (DDR), survey, well-architecture and directional-plan revisions
  of the scope with their SHA-256 where stored; "none recorded" when there is none (never invented);
* **methods** - catalogue IDs with the version read from the running code (``core.method_catalogue``);
* **label** - UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED, generation time and template version.

``attach(html, prov)`` puts a label banner at the top and the provenance block at the end of the HTML and
sets the text direction (``ltr`` default, ``rtl`` on request) - Qt's rich-text PDF writer honours the same
``dir`` attribute, so HTML and PDF agree. ``add_sheet`` adds a "Provenance" sheet to an Excel export and
``save_csv`` writes one CSV per Excel sheet with the provenance as leading ``#`` rows. No PyMuPDF.
"""
from __future__ import annotations

import csv
import html as _html
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

PROVENANCE_VERSION = "M93 report provenance v1"
LABEL = "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"
DIRECTIONS = ("ltr", "rtl")
KINDS = ("ddr", "eowr", "npt", "cost", "plan")
TITLES = {"ddr": "Daily drilling report", "eowr": "End-of-well report", "npt": "NPT report", "cost": "Cost report",
          "plan": "Well plan report"}
# Tables each report engine reads (core/report_engine.py), named by their database tables.
SOURCES = {
    "ddr": ("daily_reports", "time_logs_24h", "time_logs_morning", "DDR child collections (report snapshot)"),
    "eowr": ("daily_reports", "time_logs_24h", "time_logs_morning", "drilling_parameters", "bit_reports",
             "bha_reports", "mud_reports", "casing_reports", "cement_reports", "survey_points", "cost_records",
             "safety_reports", "equipment_logs", "material_requests", "logistics_personnel", "transport_logs",
             "service_companies"),
    "npt": ("daily_reports", "time_logs_24h", "cost_records"),
    "cost": ("daily_reports", "time_logs_24h", "cost_records"),
    "plan": ("well_plans", "planned_activities"),
}
# Catalogue method IDs each report applies (versions come from the catalogue, i.e. from the code).
METHODS = {
    "ddr": ("analysis.time_log_summary",),
    "eowr": ("analysis.time_log_summary", "analysis.cost_per_currency", "engine.bit_performance",
             "directional.minimum_curvature"),
    "npt": ("analysis.time_log_summary", "analysis.cost_per_currency"),
    "cost": ("analysis.time_log_summary", "analysis.cost_per_currency"),
    "plan": (),
}


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else ("" if value is None else str(value))


def _latest(session, model, **filters):
    query = session.query(model)
    for name, value in filters.items():
        query = query.filter(getattr(model, name) == value)
    order = getattr(model, "revision", None) or getattr(model, "revision_no")
    return query.order_by(order.desc(), model.id.desc()).first()


def build(db, kind: str, target_id: int, *, direction: str = "ltr") -> Dict[str, Any]:
    from core import method_catalogue as mc
    from core.database import (DailyReport, DirectionalPlanRevision, ReportRevision, SurveyRevision, Well,
                               WellArchitectureRevision, Wellbore)

    if kind not in KINDS:
        raise ValueError(f"unknown report kind {kind!r}")
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown text direction {direction!r}")
    with db.session_scope() as session:
        report = session.get(DailyReport, target_id) if kind == "ddr" else None
        well_id = report.well_id if report is not None else target_id
        well = session.get(Well, well_id)
        bore_id = report.wellbore_id if report is not None else None
        bore = session.get(Wellbore, bore_id) if bore_id else None
        reports = session.query(DailyReport).filter(DailyReport.well_id == well_id)
        if report is not None:
            reports = reports.filter(DailyReport.id == report.id)
        dates = sorted(r.report_date for r in reports if r.report_date is not None)
        count = reports.count()
        scope = {
            "kind": kind, "title": TITLES[kind],
            "well": f"{well.name} (id {well.id})" if well is not None else f"unknown well (id {well_id})",
            "wellbore": (f"{bore.name} (id {bore.id})" if bore is not None
                         else "not recorded on the report" if report is not None else "all wellbores of the well"),
            "report": (f"#{report.report_number or '—'} of {_iso(report.report_date) or 'unknown date'} (id {report.id})"
                       if report is not None else "all daily reports of the well"),
            "period": (f"{_iso(dates[0])} – {_iso(dates[-1])}" if dates else "no dated daily report"),
        }
        bore_filter = {"well_id": well_id, **({"wellbore_id": bore_id} if bore_id else {})}
        revisions: List[str] = []
        if report is not None:
            rev = _latest(session, ReportRevision, report_id=report.id)
            revisions.append(f"Report revision {rev.revision_no} ({rev.status}, {_iso(rev.created_at)})"
                             if rev is not None else "Report revision: none recorded")
        survey = _latest(session, SurveyRevision, **bore_filter)
        revisions.append(f"Survey revision {survey.revision} (id {survey.id}, stations SHA-256 "
                         f"{survey.stations_sha256[:12]}…)" if survey is not None else "Survey revision: none recorded")
        arch = _latest(session, WellArchitectureRevision, **bore_filter)
        revisions.append(f"Well architecture revision {arch.revision} (id {arch.id}, SHA-256 "
                         f"{arch.components_sha256[:12]}…)" if arch is not None
                         else "Well architecture revision: none recorded")
        if kind in ("plan", "eowr"):
            plan = _latest(session, DirectionalPlanRevision, **bore_filter)
            revisions.append(f"Directional plan '{plan.name}' revision {plan.revision} ({plan.status})"
                             if plan is not None else "Directional plan revision: none recorded")
    catalogue = {e.method_id: e for e in mc.catalogue()}
    methods = [f"{mid} — {catalogue[mid].version} ({catalogue[mid].label or 'no product label'}; "
               f"{catalogue[mid].approval})" for mid in METHODS[kind]]
    methods.append(f"report template core/report_engine.py ({kind}); {PROVENANCE_VERSION}")
    return {"scope": scope, "sources": list(SOURCES[kind]) + [f"{count} daily report(s) in scope"],
            "revisions": revisions, "methods": methods, "label": LABEL, "direction": direction,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "version": PROVENANCE_VERSION}


def rows(prov: Dict[str, Any]) -> List[List[str]]:
    """Provenance as (field, value) rows for CSV and Excel."""
    out = [["status", prov["label"]], ["generated_at", prov["generated_at"]], ["provenance", prov["version"]],
           ["direction", prov["direction"]]]
    out += [[f"scope.{key}", value] for key, value in prov["scope"].items()]
    out += [["source", value] for value in prov["sources"]]
    out += [["revision", value] for value in prov["revisions"]]
    out += [["method", value] for value in prov["methods"]]
    return out


def block_html(prov: Dict[str, Any]) -> str:
    e = _html.escape
    items = "".join(f"<tr><td><b>{e(k)}</b></td><td>{e(str(v))}</td></tr>" for k, v in rows(prov))
    return (f'<div dir="{prov["direction"]}" class="dm-provenance"><h3>Provenance</h3>'
            f'<table border="1" cellspacing="0" cellpadding="3">{items}</table></div>')


def attach(html: str, prov: Dict[str, Any]) -> str:
    """Label banner first, provenance block last, the whole body in the requested direction."""
    direction = prov["direction"]
    banner = (f'<div dir="{direction}" class="dm-label" style="border:2px solid #b00;padding:4px;'
              f'font-weight:bold">{_html.escape(prov["label"])} — {_html.escape(prov["scope"]["title"])}</div>')
    lower = html.lower()
    start = lower.find("<body")
    if start >= 0:
        open_end = html.index(">", start) + 1
        close = lower.rfind("</body>")
        close = close if close >= open_end else len(html)
        body = html[open_end:close]
        out = (html[:open_end] + f'<div dir="{direction}">' + banner + body + block_html(prov) + "</div>"
               + html[close:])
    else:
        out = f'<div dir="{direction}">{banner}{html}{block_html(prov)}</div>'
    head = out.lower().find("<html")
    if head >= 0 and "dir=" not in out[head:out.index(">", head)].lower():
        out = out[:head + 5] + f' dir="{direction}"' + out[head + 5:]
    return out


def add_sheet(path: str, prov: Dict[str, Any]) -> bool:
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    sheet = workbook.create_sheet("Provenance", 0)
    for row in rows(prov):
        sheet.append(row)
    if prov["direction"] == "rtl":
        for ws in workbook.worksheets:
            ws.sheet_view.rightToLeft = True
    workbook.save(path)
    return True


def save_csv(engine, data, path: str, prov: Dict[str, Any], **excel_kwargs) -> List[str]:
    """One CSV per sheet of the engine's own Excel export, provenance rows first. Returns the files written."""
    from openpyxl import load_workbook

    with tempfile.TemporaryDirectory() as tmp:
        xlsx = os.path.join(tmp, "report.xlsx")
        if not engine._save_excel(data, xlsx, **excel_kwargs):
            return []
        workbook = load_workbook(xlsx, read_only=True, data_only=True)
        sheets = [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in workbook.worksheets]
        workbook.close()
    stem, _ext = os.path.splitext(path)
    written = []
    for index, (title, values) in enumerate(sheets):
        target = path if index == 0 else f"{stem}_{_safe(title)}.csv"
        with open(target, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            for key, value in rows(prov):
                writer.writerow([f"# {key}", value])
            writer.writerow(["# sheet", title])
            for row in values:
                writer.writerow(["" if v is None else v for v in row])
        written.append(target)
    return written


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40] or "sheet"


def emit(engine, kind: str, target_id: int, data, html: str, path: str, fmt: str,
         excel_kwargs: Optional[Dict[str, Any]] = None) -> bool:
    """The one output step of every report engine: provenance in every format."""
    excel_kwargs = excel_kwargs or {}
    prov = build(engine.db, kind, target_id, direction=getattr(engine, "direction", "ltr"))
    engine.last_provenance = prov
    if fmt == "pdf":
        return engine._save_pdf(attach(html, prov), path)
    if fmt == "html":
        return engine._save_html(attach(html, prov), path)
    if fmt == "excel":
        return bool(engine._save_excel(data, path, **excel_kwargs)) and add_sheet(path, prov)
    if fmt == "csv":
        return bool(save_csv(engine, data, path, prov, **excel_kwargs))
    return False
