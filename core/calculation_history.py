"""M67: unified calculation history (read-only adapters, no migration).

Every stored engineering calculation is exposed through one view model,
``HistoryEntry``, built by a per-table adapter. The source tables are never
modified here: the adapters only read. Sources:

* the six engine snapshot tables (T&D, casing, cement, MSE, mud volume,
  kill sheet) sharing ``label / method / snapshot_schema_version /
  input_snapshot_json / result_json``;
* ``trajectory_calculations`` (``parameters_json`` / ``results_json``);
* ``calculation_cases`` (M63) and ``directional_plan_revisions`` (M62).

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
SOURCES = tuple(v[0] for v in SNAPSHOT_SOURCES.values()) + ("Trajectory", "Calculation case", "Directional plan")


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

    adapters += [(d.TrajectoryCalculation, trajectory), (d.CalculationCase, case), (d.DirectionalPlanRevision, plan)]
    return adapters


def load_history(db, *, well_id: Optional[int] = None, sources: Optional[Iterable[str]] = None, text: str = "",
                 since: Optional[datetime] = None, until: Optional[datetime] = None) -> List[HistoryEntry]:
    """Every matching entry, newest first. Read-only; sessions stay inside."""
    wanted = set(sources) if sources else None
    needle = text.strip().lower()
    out: List[HistoryEntry] = []
    with db.session_scope() as session:
        for model, adapt in _adapters():
            query = session.query(model)
            if well_id is not None:
                query = query.filter(model.well_id == well_id)
            for row in query.all():
                entry = adapt(row)
                if wanted is not None and entry.source not in wanted:
                    continue
                if since is not None and (entry.created_at is None or entry.created_at < since):
                    continue
                if until is not None and (entry.created_at is None or entry.created_at > until):
                    continue
                if needle and needle not in " ".join(
                        [entry.name, entry.method, entry.source, " ".join(map(str, entry.inputs))]).lower():
                    continue
                out.append(entry)
    out.sort(key=lambda e: (e.created_at or datetime.min, e.record_id), reverse=True)
    return out


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
          "text-align:left}.note{color:#7a4b00}")


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
    return {"status": "NOT_REPRODUCIBLE", "method_matches": None, "current_method": "",
            "detail": f"No recalculation adapter for {entry.source}; reopen it in its calculator instead.",
            "values": {}}


def lineage(db, entry: HistoryEntry) -> List[Dict[str, Any]]:
    """Structured lineage of an entry: its source (for a case) and the cases derived from it.

    Each item: ``direction`` (source/derived), ``key`` (``table:id`` of the other
    record), ``label`` and the link fields.
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
    return items


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
