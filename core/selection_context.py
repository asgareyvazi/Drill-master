"""M102: resolve a selection snapshot through the database relations (read-only).

``SelectionManager`` holds ids; this module turns a ``ContextSnapshot`` into
labels using only relations that exist in the data model:

    Company <- Project <- Well <- Wellbore / Section <- DailyReport

* The rig is the well's ``rig_name`` attribute; there is no rig entity, so a
  rig is never selected or inferred from another table.
* A child whose stored parent differs from the selected parent (a stale id)
  is reported in ``conflicts`` and its label is withheld. It is never shown as
  if it belonged.
* Missing values stay ``None``. Nothing is invented.

Runs a handful of primary-key lookups; callers on the GUI thread pass the
snapshot they already have, and nothing ORM leaves this module.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

PATH_ORDER = ("company", "project", "well", "wellbore", "section", "report")


def resolve(db, snapshot) -> Dict[str, Any]:
    """Labels for every level of ``snapshot`` ({} when nothing is selected or there is no database)."""
    out: Dict[str, Any] = {"conflicts": []}
    if snapshot is None or db is None or not callable(getattr(db, "session_scope", None)):
        return out
    from core.database import Company, DailyReport, Project, Section, Well, Wellbore

    with db.session_scope() as session:
        well = session.get(Well, int(snapshot.well_id)) if snapshot.well_id else None
        if well is not None:
            out["well"] = {"id": well.id, "name": well.name, "code": well.code}
            out["rig"] = {"name": well.rig_name, "source": "well attribute rig_name"} if well.rig_name else None
            project = session.get(Project, well.project_id) if well.project_id else None
            if project is not None:
                out["project"] = {"id": project.id, "name": project.name}
                company = session.get(Company, project.company_id) if project.company_id else None
                if company is not None:
                    out["company"] = {"id": company.id, "name": company.name}
        elif snapshot.well_id:
            out["conflicts"].append(f"well {snapshot.well_id} does not exist")
        if snapshot.wellbore_id:
            bore = session.get(Wellbore, int(snapshot.wellbore_id))
            if bore is None or well is None or bore.well_id != well.id:
                out["conflicts"].append(f"wellbore {snapshot.wellbore_id} is not a wellbore of the selected well")
            else:
                out["wellbore"] = {"id": bore.id, "name": bore.name}
        if snapshot.section_id:
            section = session.get(Section, int(snapshot.section_id))
            if section is None or well is None or section.well_id != well.id:
                out["conflicts"].append(f"section {snapshot.section_id} is not a section of the selected well")
            else:
                out["section"] = {"id": section.id, "name": section.name}
        if snapshot.report_id:
            report = session.get(DailyReport, int(snapshot.report_id))
            if report is None or well is None or report.well_id != well.id:
                out["conflicts"].append(f"report {snapshot.report_id} is not a report of the selected well")
            else:
                out["report"] = {"id": report.id, "number": report.report_number,
                                 "date": report.report_date.isoformat() if report.report_date else None}
    if snapshot.period_from or snapshot.period_to:
        out["period"] = {"from": snapshot.period_from, "to": snapshot.period_to}
    return out


def path_text(resolved: Dict[str, Any], *, empty: str = "No well selected") -> str:
    """One-line context path for status bars: Company › Project › Well (rig) › Wellbore › Section › Report."""
    parts = []
    for level in PATH_ORDER:
        item: Optional[dict] = resolved.get(level)
        if not item:
            continue
        if level == "well":
            rig = resolved.get("rig")
            parts.append(f"{item['name']}" + (f" (rig {rig['name']})" if rig else ""))
        elif level == "report":
            number = item.get("number")
            parts.append(f"Report {'#' + str(number) if number is not None else 'id ' + str(item['id'])}"
                         + (f" {item['date']}" if item.get("date") else ""))
        else:
            parts.append(str(item["name"]))
    if not parts:
        return empty
    text = " › ".join(parts)
    period = resolved.get("period")
    if period:
        text += f"  |  period {period['from'] or '…'} – {period['to'] or '…'}"
    if resolved.get("conflicts"):
        text += "  |  context conflict: " + "; ".join(resolved["conflicts"])
    return text
