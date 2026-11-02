"""M67: unified calculation history (read-only adapters, no migration).

Every stored engineering calculation is exposed through one view model,
``HistoryEntry``, built by a per-table adapter. The source tables are never
modified here: the adapters only read. Sources:

* the six engine snapshot tables (T&D, casing, cement, MSE, mud volume,
  kill sheet) sharing ``label / method / snapshot_schema_version /
  input_snapshot_json / result_json``;
* ``trajectory_calculations`` (``parameters_json`` / ``results_json``);
* ``calculation_cases`` (M63) and ``directional_plan_revisions`` (M62);
* M88: ``survey_revisions`` (M72/M85) and ``well_architecture_revisions``
  (M74). Their recalculation re-runs minimum curvature / the architecture
  validator from the stored stations / components after the SHA-256 check;
  a failed check is UNREADABLE, never recomputed from tampered data.

``lineage`` follows the structured case links, the revision parent chains
(survey, architecture, plan, case) and the architecture -> survey revision
link in both directions.

The Engineering Report Center renders one entry, or a comparison of two, to
self-contained HTML with the method, version, inputs, results, scope and the
UNSIGNED / not-validated statement.
"""

from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

HISTORY_VERSION = 1
REPORT_TEMPLATE_VERSION = 1

# table -> (display source, scope statement)
SNAPSHOT_SOURCES = {
    "torque_drag_calculations": ("Torque & drag", "SCREENING (soft-string)"),
    "casing_calculations": ("Casing design", "SCREENING (API TR 5C3 subset)"),
    "cement_calculations": ("Cement volumes", "WORKSHEET"),
    "mse_calculations": ("MSE", "SCREENING"),
    "mud_volume_calculations": ("Mud volume", "WORKSHEET"),
    "well_control_kill_sheet_calculations": ("Kill sheet", "TRAINING AID"),
}
REVISION_SOURCES = {"survey_revisions": "Survey revision", "well_architecture_revisions": "Well architecture"}
SOURCES = (tuple(v[0] for v in SNAPSHOT_SOURCES.values()) + ("Trajectory", "Calculation case", "Directional plan")
           + tuple(REVISION_SOURCES.values()))


@dataclass
class HistoryEntry:
    source: str
    table: str
    record_id: int
    well_id: Optional[int]
    name: str
    method: str
    version: str
    created_at: Optional[datetime]
    scope: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    parent: str = ""
    full_results: Dict[str, Any] = field(default_factory=dict)   # complete stored result (verification)
    wellbore_id: Optional[int] = None

    @property
    def key(self) -> str:
        return f"{self.table}:{self.record_id}"

    def to_row(self) -> Dict[str, Any]:
        return {"source": self.source, "id": self.record_id, "well_id": self.well_id, "name": self.name,
                "method": self.method, "version": self.version,
                "created_at": self.created_at.isoformat(sep=" ", timespec="seconds") if self.created_at else "",
                "scope": self.scope, "parent": self.parent}


def _json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:  # silent-ok: unparseable legacy JSON is shown as raw text, never dropped
            return {"raw": value}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {}


def _adapters():
    from core import database as d

    def snapshot(model, table):
        source, scope = SNAPSHOT_SOURCES[table]

        def adapt(row):
            return HistoryEntry(source, table, row.id, row.well_id, row.label or f"{source} #{row.id}",
                                row.method or "", f"snapshot schema v{row.snapshot_schema_version}",
                                row.created_at, scope, _json(row.input_snapshot_json), _json(row.result_json))
        return model, adapt

    by_table = {mapper.class_.__tablename__: mapper.class_ for mapper in d.Base.registry.mappers}
    missing = [table for table in SNAPSHOT_SOURCES if table not in by_table]
    if missing:   # a renamed model must not silently drop a history source
        raise LookupError(f"Calculation history source table(s) without a model: {', '.join(missing)}")
    adapters = [snapshot(by_table[table], table) for table in SNAPSHOT_SOURCES]

    def trajectory(row):
        return HistoryEntry("Trajectory", "trajectory_calculations", row.id, row.well_id,
                            row.description or f"Trajectory #{row.id}", row.method or "", "unversioned (legacy)",
                            row.created_at, "CALCULATION", _json(row.parameters_json), _json(row.results_json))

    def case(row):
        return HistoryEntry("Calculation case", "calculation_cases", row.id, row.well_id, row.name,
                            row.method, row.method_version, row.created_at, "W13 CALCULATOR",
                            row.inputs or {}, row.results or {}, f"case #{row.parent_id}" if row.parent_id else "")

    def plan(row):
        results = row.results or {}
        stations = results.get("stations") or []
        headline = {"stations": len(stations), "targets": results.get("targets", []),
                    "warnings": results.get("warnings", [])}
        if stations:
            headline.update(td_md=stations[-1]["md"], td_tvd=stations[-1]["tvd"],
                            max_dls=max(s.get("dls", 0.0) for s in stations))
        return HistoryEntry("Directional plan", "directional_plan_revisions", row.id, row.well_id,
                            f"{row.name} rev {row.revision} ({row.status})", row.method, row.method_version,
                            row.created_at, "PLANNING AID", row.inputs or {}, headline,
                            f"revision id {row.parent_id}" if row.parent_id else "", full_results=results,
                            wellbore_id=row.wellbore_id)

    def survey(row):
        from core.survey_revisions import stations_sha256

        stations = json.loads(row.stations_json or "[]")
        positions = json.loads(row.results_json or "[]")
        integrity = "VERIFIED" if stations_sha256(stations) == row.stations_sha256 else "HASH MISMATCH"
        headline: Dict[str, Any] = {"stations": row.station_count, "integrity": integrity,
                                    "azimuth_reference": row.azimuth_reference, "depth_datum": row.depth_datum}
        if positions:
            last = positions[-1]
            headline.update({f"td_{k}": last[k] for k in ("md", "tvd", "north", "east") if k in last})
        inputs = {"stations": stations, "source_unit": row.source_unit, "source_type": row.source_type,
                  "azimuth_reference": row.azimuth_reference, "depth_datum": row.depth_datum,
                  "mode": row.mode, "stations_sha256": row.stations_sha256}
        return HistoryEntry("Survey revision", "survey_revisions", row.id, row.well_id,
                            f"Survey rev {row.revision} ({row.mode}, {row.source_type})", row.method,
                            row.method_version, row.created_at, "SURVEY (minimum curvature)", inputs, headline,
                            f"revision id {row.parent_id}" if row.parent_id else "",
                            full_results={"positions": positions}, wellbore_id=row.wellbore_id)

    def architecture(row):
        from core.well_architecture import components_sha256

        components = json.loads(row.components_json or "[]")
        validation = _json(row.validation_json)
        integrity = "VERIFIED" if components_sha256(components) == row.components_sha256 else "HASH MISMATCH"
        headline = {"components": row.component_count, "integrity": integrity,
                    "errors": len(validation.get("errors", [])), "warnings": len(validation.get("warnings", [])),
                    "survey_revision_id": row.survey_revision_id}
        inputs = {"components": components, "survey_revision_id": row.survey_revision_id,
                  "components_sha256": row.components_sha256}
        return HistoryEntry("Well architecture", "well_architecture_revisions", row.id, row.well_id,
                            f"Architecture rev {row.revision}" + (f" - {row.note}" if row.note else ""),
                            "well architecture validation", row.schema_version, row.created_at,
                            "ARCHITECTURE (validation only)", inputs, headline,
                            f"revision id {row.parent_id}" if row.parent_id else "",
                            full_results=validation, wellbore_id=row.wellbore_id)

    adapters += [(d.TrajectoryCalculation, trajectory), (d.CalculationCase, case), (d.DirectionalPlanRevision, plan),
                 (d.SurveyRevision, survey), (d.WellArchitectureRevision, architecture)]
    return adapters


_NAME_COLUMN = {"trajectory_calculations": "description", "calculation_cases": "name",
                "directional_plan_revisions": "name", "survey_revisions": "source_type",
                "well_architecture_revisions": "note"}
_METHOD_COLUMN = {"well_architecture_revisions": "schema_version"}


def _source_of(model, adapt) -> str:
    table = model.__tablename__
    if table in SNAPSHOT_SOURCES:
        return SNAPSHOT_SOURCES[table][0]
    if table in REVISION_SOURCES:
        return REVISION_SOURCES[table]
    return {"trajectory_calculations": "Trajectory", "calculation_cases": "Calculation case",
            "directional_plan_revisions": "Directional plan"}[table]


def _filtered(session, model, *, well_id, since, until, needle):
    """M73: the well, period and text filters run in the database (indexed well_id, created_at)."""
    from sqlalchemy import func, or_

    query = session.query(model)
    if well_id is not None:
        query = query.filter(model.well_id == well_id)
    if since is not None:
        query = query.filter(model.created_at >= since)
    if until is not None:
        query = query.filter(model.created_at <= until)
    if needle:
        name = getattr(model, _NAME_COLUMN.get(model.__tablename__, "label"))
        pattern = f"%{needle}%"
        method = getattr(model, _METHOD_COLUMN.get(model.__tablename__, "method"))
        query = query.filter(or_(func.lower(name).like(pattern), func.lower(method).like(pattern)))
    return query


def load_history(db, *, well_id: Optional[int] = None, sources: Optional[Iterable[str]] = None, text: str = "",
                 since: Optional[datetime] = None, until: Optional[datetime] = None,
                 limit: Optional[int] = None, offset: int = 0) -> List[HistoryEntry]:
    """Matching entries, newest first. Read-only; sessions stay inside.

    Filters run in the database; sources that are not wanted are not queried.
    The text filter matches the record name and method (case-insensitive).
    With ``limit`` only one page is returned: each source is asked for its
    newest ``offset + limit`` rows, the pages are merged by time and sliced.
    """
    wanted = set(sources) if sources else None
    needle = text.strip().lower()
    out: List[HistoryEntry] = []
    window = None if limit is None else max(0, int(offset)) + max(0, int(limit))
    with db.session_scope() as session:
        for model, adapt in _adapters():
            if wanted is not None and _source_of(model, adapt) not in wanted:
                continue
            query = _filtered(session, model, well_id=well_id, since=since, until=until, needle=needle)
            query = query.order_by(model.created_at.desc(), model.id.desc())
            if window is not None:
                query = query.limit(window)
            out.extend(adapt(row) for row in query.all())
    out.sort(key=lambda e: (e.created_at or datetime.min, e.record_id), reverse=True)
    if limit is not None:
        return out[max(0, int(offset)):window]
    return out


def count_history(db, *, well_id: Optional[int] = None, sources: Optional[Iterable[str]] = None, text: str = "",
                  since: Optional[datetime] = None, until: Optional[datetime] = None) -> int:
    """Number of matching entries (COUNT in the database), for the page indicator."""
    wanted = set(sources) if sources else None
    needle = text.strip().lower()
    total = 0
    with db.session_scope() as session:
        for model, adapt in _adapters():
            if wanted is not None and _source_of(model, adapt) not in wanted:
                continue
            total += _filtered(session, model, well_id=well_id, since=since, until=until, needle=needle).count()
    return total


def entry_status(entry: HistoryEntry) -> Dict[str, str]:
    """M73: three separate answers instead of one label.

    * readable - the stored inputs and results could be read as data;
    * comparable - the results hold at least one numeric value to compare;
    * reproducible - a recalculation path exists for this record and method
      version (plans, engine snapshots, contract calculators); otherwise NOT
      REPRODUCIBLE with the reason. ``recalculate_entry`` gives the verdict.
    """
    from core import calculator_contracts as contracts

    readable = isinstance(entry.inputs, dict) and isinstance(entry.results, dict) and bool(entry.inputs)
    numbers = [v for v in flatten(entry.results).values() if _number(v) is not None]
    if entry.table in PERSISTENCE_MODULES or entry.table == "directional_plan_revisions" \
            or entry.table in REVISION_SOURCES:
        reproducible, why = "REPRODUCIBLE", "a recalculation adapter exists"
    elif entry.table == "calculation_cases":
        reproducible, why = contracts.reproducibility(entry.method, entry.version)
    else:
        reproducible, why = "NOT REPRODUCIBLE", f"no recalculation adapter for {entry.source}"
    return {"readable": "READABLE" if readable else "UNREADABLE",
            "comparable": "COMPARABLE" if numbers else "NOT COMPARABLE",
            "reproducible": reproducible, "reproducible_reason": why}


def _number(value) -> Optional[float]:
    """Leading number of a stored value ("0.05828 bbl/m | ..." -> 0.05828); None when there is none."""
    import re

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.match(r"\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", str(value or ""))
    return float(match.group(1)) if match else None


def _unit(entry_value) -> str:
    if isinstance(entry_value, dict):
        return str(entry_value.get("unit") or "")
    return ""


def numeric_differences(a: HistoryEntry, b: HistoryEntry) -> Dict[str, List[Dict[str, Any]]]:
    """Unit-safe numeric differences, inputs and results separately.

    Values are compared only when both are numeric and carry the same unit
    (an explicit unit or none on both); a unit mismatch is listed as
    ``UNIT MISMATCH`` and never converted silently.
    """
    def side(left: Dict[str, Any], right: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for key in sorted(set(left) | set(right)):
            la, lb = left.get(key), right.get(key)
            va = la.get("value") if isinstance(la, dict) and "value" in la else la
            vb = lb.get("value") if isinstance(lb, dict) and "value" in lb else lb
            na, nb = _number(va), _number(vb)
            if na is None or nb is None:
                continue
            ua, ub = _unit(la), _unit(lb)
            if ua != ub:
                out.append({"key": key, "status": "UNIT MISMATCH", "a": va, "b": vb, "unit_a": ua, "unit_b": ub})
                continue
            if na != nb:
                out.append({"key": key, "status": "DIFFERENT", "a": na, "b": nb, "unit": ua,
                            "delta": nb - na, "relative": (nb - na) / abs(na) if na else None})
        return out

    return {"inputs": side(a.inputs, b.inputs), "results": side(a.results, b.results)}


def flatten(data: Any, prefix: str = "") -> Dict[str, Any]:
    """Nested dict/list -> dotted keys (lists of scalars stay as values)."""
    out: Dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            out.update(flatten(value, f"{prefix}{key}."))
    elif isinstance(data, list) and any(isinstance(v, (dict, list)) for v in data):
        for index, value in enumerate(data):
            out.update(flatten(value, f"{prefix}{index}."))
    else:
        out[prefix.rstrip(".")] = data
    return out


def compare_entries(a: HistoryEntry, b: HistoryEntry) -> Dict[str, Any]:
    def diff(left, right) -> List[Tuple[str, Any, Any]]:
        fa, fb = flatten(left), flatten(right)
        return [(k, fa.get(k), fb.get(k)) for k in sorted(set(fa) | set(fb)) if fa.get(k) != fb.get(k)]

    return {"a": a, "b": b, "same_source": a.source == b.source, "same_version": a.version == b.version,
            "inputs": diff(a.inputs, b.inputs), "results": diff(a.results, b.results)}


def export_history_csv(entries: Iterable[HistoryEntry], path: str) -> int:
    rows = [e.to_row() for e in entries]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source", "id", "well_id", "name", "method", "version",
                                                    "created_at", "scope", "parent"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


# -- Engineering Report Center ---------------------------------------------------------------------
_STYLE = ("body{font-family:sans-serif;font-size:10pt;color:#111}h1{font-size:15pt}h2{font-size:12pt;"
          "border-bottom:1px solid #999}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:2px 6px;"
          "text-align:left}.note{color:#7a4b00}"
          # M78: printed reports keep rows whole and headings with their tables
          "tr{page-break-inside:avoid}h1,h2{page-break-after:avoid}table{page-break-inside:auto}")


def _table(pairs: Iterable[Tuple[Any, ...]], headers: Tuple[str, ...]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in pairs)
    return f"<table><tr>{head}</tr>{body or '<tr><td colspan=9>none</td></tr>'}</table>"


def _footer(well_label: str) -> str:
    return (f"<p class='note'>Well: {html.escape(well_label or 'not linked')}. Generated "
            f"{datetime.now().isoformat(sep=' ', timespec='seconds')} by DrillMaster Report Center template "
            f"v{REPORT_TEMPLATE_VERSION}. UNSIGNED. Engineering aid only: not validated, not an approval, "
            "not a substitute for an engineer's review.</p>")


def well_label(db, well_id: Optional[int]) -> str:
    """Label of the record's OWN well (never the current selection); explicit when unknown."""
    if well_id is None:
        return "no well (software-level calculation)"
    from core.database import Well

    with db.session_scope() as session:
        well = session.get(Well, well_id)
        return f"{well.name} (id {well_id})" if well is not None else f"well id {well_id} (deleted)"


def render_entry_report(entry: HistoryEntry, *, well_label: str = "") -> str:
    meta = [("Source", entry.source), ("Record", entry.key), ("Name", entry.name), ("Method", entry.method),
            ("Method version", entry.version), ("Created", entry.to_row()["created_at"]), ("Scope", entry.scope),
            ("Derived from", entry.parent or "—")]
    state = entry_status(entry)          # M73/M78: the three statuses travel with the report
    meta += [("Readable", state["readable"]), ("Comparable", state["comparable"]),
             ("Reproducible", f"{state['reproducible']} ({state['reproducible_reason']})")]
    return (f"<html><head><meta charset='utf-8'><style>{_STYLE}</style></head><body>"
            f"<h1>Engineering calculation report — {html.escape(entry.name)}</h1>"
            f"{_table(meta, ('Field', 'Value'))}"
            f"<h2>Inputs</h2>{_table(flatten(entry.inputs).items(), ('Input', 'Value'))}"
            f"<h2>Results</h2>{_table(flatten(entry.results).items(), ('Result', 'Value'))}"
            f"{_footer(well_label)}</body></html>")


def render_comparison_report(a: HistoryEntry, b: HistoryEntry, *, well_label: str = "") -> str:
    report = compare_entries(a, b)
    warn = "" if report["same_version"] else (
        f"<p class='note'>Method versions differ ({html.escape(a.version)} vs {html.escape(b.version)}); "
        "differences can come from the method change.</p>")
    return (f"<html><head><meta charset='utf-8'><style>{_STYLE}</style></head><body>"
            f"<h1>Calculation comparison</h1><p>A: {html.escape(a.source)} — {html.escape(a.name)} ({a.key})<br>"
            f"B: {html.escape(b.source)} — {html.escape(b.name)} ({b.key})</p>{warn}"
            f"<h2>Inputs that differ</h2>{_table(report['inputs'], ('Input', 'A', 'B'))}"
            f"<h2>Results that differ</h2>{_table(report['results'], ('Result', 'A', 'B'))}"
            f"{_footer(well_label)}</body></html>")


# -- recalculation (original never modified) -------------------------------------------------------
PERSISTENCE_MODULES = {
    "torque_drag_calculations": "core.engineering.torque_drag_persistence",
    "casing_calculations": "core.engineering.casing_persistence",
    "cement_calculations": "core.engineering.cement_persistence",
    "mse_calculations": "core.engineering.mse_persistence",
    "mud_volume_calculations": "core.engineering.mud_volume_persistence",
    "well_control_kill_sheet_calculations": "core.engineering.well_control_kill_sheet_persistence",
}


def recalculate_entry(entry: HistoryEntry) -> Dict[str, Any]:
    """Re-run an entry with the CURRENT method and classify it against the stored result.

    Engine snapshots reuse each engine's ``recalculate_from_snapshot`` and the
    shared ``classify_verification``; directional plans re-run the designer.
    Nothing is written; see ``save_recalculation``.
    """
    import importlib

    if entry.table in PERSISTENCE_MODULES:
        from core.engineering.calculation_verification import classify_verification

        module = importlib.import_module(PERSISTENCE_MODULES[entry.table])
        try:
            recalc = module.recalculate_from_snapshot(entry.inputs)
        except Exception as exc:  # silent-ok: reported to the user as UNREADABLE with the reason
            return {"status": "UNREADABLE", "method_matches": None, "current_method": "",
                    "detail": f"snapshot could not be reconstructed: {exc}", "values": {}}
        outcome = classify_verification(entry.results, recalc, snapshot_method=entry.inputs.get("method"),
                                        current_method=getattr(recalc, "method", None))
        return {"status": outcome.status, "method_matches": outcome.method_matches,
                "current_method": getattr(recalc, "method", "") or "", "detail": outcome.detail or "",
                "values": dict(recalc.values) if getattr(recalc, "success", False) else {}}
    if entry.table == "directional_plan_revisions":
        from core.directional_plans import verify_plan_record

        return verify_plan_record(entry.inputs, entry.full_results, entry.version)
    if entry.table == "calculation_cases":
        from core import calculator_contracts as contracts

        return contracts.verify_case(entry.method, entry.version, entry.inputs, entry.results)
    if entry.table == "survey_revisions":
        return _verify_survey(entry)
    if entry.table == "well_architecture_revisions":
        return _verify_architecture(entry)
    return {"status": "NOT_REPRODUCIBLE", "method_matches": None, "current_method": "",
            "detail": f"No recalculation adapter for {entry.source}; reopen it in its calculator instead.",
            "values": {}}


def _verify_survey(entry: HistoryEntry) -> Dict[str, Any]:
    """M88: minimum curvature again from the stored stations, after the SHA-256 check."""
    from core import survey_revisions as sr

    stations = entry.inputs.get("stations") or []
    if sr.stations_sha256(stations) != entry.inputs.get("stations_sha256"):
        return {"status": "UNREADABLE", "method_matches": None, "current_method": sr.SURVEY_METHOD,
                "detail": "The stored stations fail their SHA-256 check; nothing was recomputed.", "values": {}}
    stored = entry.full_results.get("positions") or []
    check = sr.verify_results({"stations": stations, "results": stored})
    fresh = sr.compute(stations)
    values: Dict[str, Any] = {}
    if fresh:
        values = {f"td_{k}": fresh[-1][k] for k in ("md", "tvd", "north", "east") if k in fresh[-1]}
        values["max_position_difference_m"] = check.get("max_position_difference_m")
    detail = check.get("detail") or f"largest position difference {check.get('max_position_difference_m', 0.0):.3g} m"
    return {"status": check["status"], "method_matches": entry.method == sr.SURVEY_METHOD,
            "current_method": sr.SURVEY_METHOD, "detail": detail, "values": values}


def _verify_architecture(entry: HistoryEntry) -> Dict[str, Any]:
    """M88: the current validator again on the stored components, after the SHA-256 check."""
    from core import well_architecture as wa

    components = entry.inputs.get("components") or []
    if wa.components_sha256(components) != entry.inputs.get("components_sha256"):
        return {"status": "UNREADABLE", "method_matches": None, "current_method": wa.ARCHITECTURE_VERSION,
                "detail": "The stored components fail their SHA-256 check; nothing was re-validated.", "values": {}}
    fresh = wa.validate(components)
    stored = entry.full_results
    same = all(sorted(fresh.get(k, [])) == sorted(stored.get(k, [])) for k in ("errors", "warnings"))
    return {"status": "MATCH" if same else "DIFFERENT", "method_matches": entry.version == wa.ARCHITECTURE_VERSION,
            "current_method": wa.ARCHITECTURE_VERSION,
            "detail": "validation messages identical" if same else
            f"stored {len(stored.get('errors', []))} error(s)/{len(stored.get('warnings', []))} warning(s), "
            f"now {len(fresh.get('errors', []))}/{len(fresh.get('warnings', []))}",
            "values": {"components": len(components), "errors": len(fresh.get("errors", [])),
                       "warnings": len(fresh.get("warnings", []))}}


# table -> label of the record kind (every table here has a ``parent_id`` column)
_PARENT_CHAINS = {"survey_revisions": "Survey revision", "well_architecture_revisions": "Architecture revision",
                  "directional_plan_revisions": "Plan revision", "calculation_cases": "Case"}


def _revision_links(db, entry: HistoryEntry) -> List[Dict[str, Any]]:
    """M88: parent / child revisions of the same kind and the architecture <-> survey link."""
    from core import database as d

    models = {"survey_revisions": d.SurveyRevision, "well_architecture_revisions": d.WellArchitectureRevision,
              "directional_plan_revisions": d.DirectionalPlanRevision, "calculation_cases": d.CalculationCase}
    items: List[Dict[str, Any]] = []
    model = models.get(entry.table)
    if model is None:
        return items
    kind = _PARENT_CHAINS[entry.table]
    with db.session_scope() as session:
        row = session.get(model, entry.record_id)
        if row is None:
            return items
        if row.parent_id:
            items.append({"direction": "parent", "key": f"{entry.table}:{row.parent_id}",
                          "label": f"Parent: {kind.lower()} id {row.parent_id}"})
        for child in session.query(model.id).filter(model.parent_id == row.id).order_by(model.id):
            items.append({"direction": "child", "key": f"{entry.table}:{child.id}",
                          "label": f"Child: {kind.lower()} id {child.id}"})
        if entry.table == "well_architecture_revisions" and row.survey_revision_id:
            items.append({"direction": "uses", "key": f"survey_revisions:{row.survey_revision_id}",
                          "label": f"Uses: survey revision id {row.survey_revision_id}"})
        if entry.table == "survey_revisions":
            arch = d.WellArchitectureRevision
            for used in session.query(arch.id).filter(arch.survey_revision_id == row.id).order_by(arch.id):
                items.append({"direction": "used_by", "key": f"well_architecture_revisions:{used.id}",
                              "label": f"Used by: architecture revision id {used.id}"})
    return items


def lineage(db, entry: HistoryEntry) -> List[Dict[str, Any]]:
    """Structured lineage of an entry.

    Each item: ``direction`` (source / derived for case links; parent / child /
    uses / used_by for revisions, M88), ``key`` (``table:id`` of the other
    record), ``label`` and, for case links, the link fields.
    """
    from core.calculation_cases import derived_cases, source_links

    items: List[Dict[str, Any]] = []
    if entry.table == "calculation_cases":
        for link in source_links(db, entry.record_id):
            changed = "; METHOD CHANGED" if link["method_changed"] else ""
            items.append(dict(link, direction="source", key=f"{link['source_table']}:{link['source_id']}",
                              label=f"Source: {link['source_table']} #{link['source_id']} "
                                    f"({link['link_type']}, {link['verification_status']}{changed})"))
    for link in derived_cases(db, entry.table, entry.record_id):
        changed = "; METHOD CHANGED" if link["method_changed"] else ""
        items.append(dict(link, direction="derived", key=f"calculation_cases:{link['case_id']}",
                          label=f"Derived: case #{link['case_id']} ({link['link_type']}, "
                                f"{link['verification_status']}{changed})"))
    return items + _revision_links(db, entry)


def page_of(db, key: str, *, page_size: int, **filters) -> Optional[int]:
    """M88: the 0-based page holding ``key`` under ``filters`` (``load_history`` order), or None."""
    total = count_history(db, **filters)
    for page in range(max(1, -(-total // page_size))):
        if any(e.key == key for e in load_history(db, limit=page_size, offset=page * page_size, **filters)):
            return page
    return None


def save_recalculation(db, entry: HistoryEntry, outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Store a recalculation as a NEW calculation case with structured lineage to the original.

    The case and its ``calculation_source_links`` row are written in one
    transaction; the source must still exist and belong to the same well. The
    original record is never written.
    """
    from core.calculation_cases import save_case

    if not outcome.get("values"):
        raise ValueError(f"Nothing to store: recalculation status {outcome.get('status')}.")
    method_changed = outcome.get("method_matches") is False
    note = (f"Recalculated from {entry.key} ({entry.version}); verification {outcome['status']}"
            + ("; METHOD CHANGED since the original" if method_changed else ""))
    current = outcome.get("current_method") or entry.method
    return save_case(
        db, calculator=f"{entry.source} recalculation", name=f"{entry.name} (recalc)", inputs=entry.inputs,
        results=outcome["values"], method=current, method_version=outcome.get("current_method") or entry.version,
        well_id=entry.well_id, wellbore_id=entry.wellbore_id, note=note,
        source_link={"link_type": "recalculation_of", "source_table": entry.table, "source_id": entry.record_id,
                     "source_method": entry.method, "source_method_version": entry.version,
                     "recalc_method": current, "recalc_method_version": outcome.get("current_method") or "",
                     "verification_status": outcome["status"], "method_changed": method_changed})
