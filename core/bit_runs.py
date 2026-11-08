"""M130: bit run workbench - runs from DDR drilling parameters, lifecycle, comparison, cost per length.

One aggregation (``aggregate``) turns DDR ``DrillingParameters`` rows into bit runs; Operational Analysis
and the workbench both use it, so a run's footage, hours and ROP are the same everywhere.

* **Run** = the DDR rows that record the same bit number and rerun. Footage is the sum of the daily drilled
  lengths, else depth out - depth in; an incomplete sum is not a total (unknown, never 0).
* **Lifecycle** is what the DDRs show, nothing more: SUPERSEDED when a later DDR row records another bit
  (that bit and date are named), otherwise OPEN - "last reported <date>; no later DDR records another
  bit". Nothing is inferred about pulling, dull grade or reason (the DDR rows do not carry them).
* **Incomplete** runs stay in every table with what is missing; they are never costed or ranked.
* **Cost per length** is a SCENARIO: bit cost, rig rate and trip time are typed by the user in ONE
  explicitly entered currency (no default, no conversion, no currency mixing); the canonical Bourgoyne
  engine (``BitPerformanceEngine.cost_per_foot``) is used with lengths in metres, so the result is
  currency per metre. It is not recorded cost and not an approval.
* **Comparison** ranks only complete runs of the same bit size (different hole sizes are not
  like-for-like).
* A scenario is saved as an immutable case (``calculation_cases``, method ``m130.bit_run_cost``) with the
  frozen run figures and the DDR rows they came from; a re-run repeats the cost from the frozen figures and
  reports when the DDR rows have changed since.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

RUN_METHOD = "M130 bit run roll-up v1"
COST_METHOD = "m130.bit_run_cost"
COST_VERSION = "M130 bit run cost per length v1"
COST_CALCULATOR = "Bit run cost per length"
COST_LABEL = "SCENARIO — USER-ENTERED COSTS — NOT RECORDED COST — NOT AN APPROVAL"
CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")        # a code the user types (e.g. USD); never looked up or converted
COST_TOLERANCE = 0.01                             # the engine rounds money to 2 decimals

OPEN, SUPERSEDED = "OPEN", "SUPERSEDED"
COMPLETE, INCOMPLETE = "COMPLETE", "INCOMPLETE"
ASSESSED, NOT_ASSESSED = "ASSESSED", "NOT ASSESSED"

RUN_COLUMNS = ("Bit #", "Rerun", "Size (in)", "Type", "Manufacturer", "IADC", "Depth in (m)", "Depth out (m)",
               "Footage (m)", "Footage basis", "Hours on bottom", "ROP (m/h)", "ROP basis", "First DDR", "Last DDR",
               "DDR rows", "Lifecycle", "Data", "Missing", "Source")


@dataclass(frozen=True)
class BitRun:
    bit_no: str
    rerun: Any
    size: Optional[float]
    bit_type: str
    manufacturer: str
    iadc: str
    depth_in: Optional[float]
    depth_out: Optional[float]
    footage: Optional[float]
    footage_basis: str
    hours: Optional[float]
    rop: Optional[float]
    rop_basis: str
    details: Tuple[Dict[str, Any], ...]
    wellbores: Tuple[Any, ...] = ()
    lifecycle: str = OPEN
    lifecycle_detail: str = ""
    missing: Tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.bit_no} / rerun {self.rerun}"

    @property
    def rows(self) -> Tuple[int, ...]:
        return tuple(d["row"] for d in self.details)

    @property
    def reports(self) -> Tuple[Any, ...]:
        return tuple(d["report"] for d in self.details)

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def first_date(self):
        return self.details[0]["date"] if self.details else None

    @property
    def last_date(self):
        return self.details[-1]["date"] if self.details else None

    def source(self) -> str:
        return "drilling_parameters #" + ", #".join(str(i) for i in self.rows)

    def table_row(self) -> List[Any]:
        return [self.bit_no, self.rerun, self.size, self.bit_type, self.manufacturer, self.iadc, self.depth_in,
                self.depth_out, self.footage, self.footage_basis, self.hours, self.rop, self.rop_basis,
                self.first_date, self.last_date, len(self.details), f"{self.lifecycle}: {self.lifecycle_detail}",
                COMPLETE if self.complete else INCOMPLETE, "; ".join(self.missing), self.source()]

    def figures(self) -> Dict[str, Any]:
        """What a cost scenario freezes: identity, figures and the DDR rows they came from."""
        return {"bit_no": self.bit_no, "rerun": self.rerun, "size_in": self.size, "footage_m": self.footage,
                "footage_basis": self.footage_basis, "hours_on_bottom": self.hours, "rows": list(self.rows),
                "reports": [r for r in self.reports if r is not None], "rows_sha256": rows_sha256(self.details)}


def rows_sha256(details: Iterable[Dict[str, Any]]) -> str:
    """Fingerprint of the DDR values a run was built from (row, date, depths, drilled, hours)."""
    payload = [[d["row"], str(d["date"]), d["in"], d["out"], d["drilled"], d["hours"]] for d in details]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _missing(footage, basis, hours, size, depth_in, depth_out) -> Tuple[str, ...]:
    missing = []
    if basis.startswith("INVALID"):
        missing.append(basis)
    elif footage is None:
        missing.append("footage (daily drilled incomplete and depth in / out not both recorded)")
    if hours is None:
        missing.append("hours on bottom (not recorded on every DDR row)")
    elif hours == 0:
        missing.append("hours on bottom (0 recorded: no ROP)")
    if size is None:
        missing.append("bit size")
    if depth_in is None:
        missing.append("depth in")
    if depth_out is None:
        missing.append("depth out")
    return tuple(missing)


def aggregate(params: Sequence[Any]) -> List[BitRun]:
    """Bit runs from DDR drilling-parameter rows ordered by (report date, id); rows without a bit number skipped.

    ``params`` items need ``id, report_id, report_date, bit_no, bit_rerun, bit_size, bit_type, depth_in,
    depth_out, bit_drilled, hours_on_bottom`` and optionally ``manufacturer, iadc_code, wellbore_id``.
    """
    from core.operational_analysis import _num, _rop_basis, _sum

    grouped: Dict[Tuple[str, Any], Dict[str, Any]] = {}
    order: List[Tuple[str, Any]] = []
    for p in params:
        bit_no = (getattr(p, "bit_no", None) or "").strip()
        if not bit_no:
            continue
        key = (bit_no, getattr(p, "bit_rerun", None))
        if key not in grouped:
            order.append(key)
            grouped[key] = {"size": getattr(p, "bit_size", None), "type": getattr(p, "bit_type", None) or "",
                            "manufacturer": getattr(p, "manufacturer", None) or "",
                            "iadc": getattr(p, "iadc_code", None) or "", "details": [], "wellbores": []}
        run = grouped[key]
        run["details"].append({"date": p.report_date, "report": p.report_id, "row": p.id,
                               "in": _num(p.depth_in), "out": _num(p.depth_out), "drilled": _num(p.bit_drilled),
                               "hours": _num(p.hours_on_bottom)})
        wellbore = getattr(p, "wellbore_id", None)
        if wellbore not in run["wellbores"]:
            run["wellbores"].append(wellbore)

    runs: List[BitRun] = []
    for key in order:
        run = grouped[key]
        details = run["details"]
        depth_in = min((d["in"] for d in details if d["in"] is not None), default=None)
        depth_out = max((d["out"] for d in details if d["out"] is not None), default=None)
        footage, basis = _sum([d["drilled"] for d in details]), "sum of daily drilled"
        if footage is None and depth_in is not None and depth_out is not None and depth_out >= depth_in:
            footage, basis = depth_out - depth_in, "depth out - depth in"
        elif footage is None and depth_in is not None and depth_out is not None:
            basis = f"INVALID: depth out {depth_out:g} m is shallower than depth in {depth_in:g} m"
        elif footage is None:
            basis = "not assessed (drilled and depths incomplete)"
        hours = _sum([d["hours"] for d in details])
        rop = footage / hours if footage is not None and hours else None
        runs.append(BitRun(key[0], key[1], run["size"], run["type"], run["manufacturer"], run["iadc"], depth_in,
                           depth_out, footage, basis, hours, rop, _rop_basis(footage, hours), tuple(details),
                           tuple(run["wellbores"]),
                           missing=_missing(footage, basis, hours, run["size"], depth_in, depth_out)))
    return _with_lifecycle(runs)


def _with_lifecycle(runs: List[BitRun]) -> List[BitRun]:
    """SUPERSEDED when a later DDR row (date, row id) records another bit; otherwise OPEN."""
    from dataclasses import replace

    def position(detail):
        return (detail["date"], detail["row"])

    out = []
    for run in runs:
        last = position(run.details[-1])
        later = [(position(d), other) for other in runs if other is not run for d in other.details
                 if position(d) > last]
        if later:
            (day, _row), other = min(later, key=lambda item: item[0])
            out.append(replace(run, lifecycle=SUPERSEDED,
                               lifecycle_detail=f"bit {other.bit_no} (rerun {other.rerun}) is recorded from {day}"))
        else:
            out.append(replace(run, lifecycle=OPEN, lifecycle_detail=f"last reported {run.last_date}; no later "
                                                                        "DDR records another bit"))
    return out


def load_runs(db, well_id: int, wellbore_id: Optional[int] = None) -> List[BitRun]:
    """Runs of one well (or only the DDRs of one wellbore); legacy duplicate parameter rows excluded."""
    from types import SimpleNamespace

    from core.database import DailyReport, DrillingParameters
    from core.operations_intelligence import canonical_params_clause

    with db.session_scope() as session:
        wellbore_of = dict(session.query(DailyReport.id, DailyReport.wellbore_id)
                           .filter(DailyReport.well_id == well_id).all())
        query = session.query(DrillingParameters).filter(DrillingParameters.well_id == well_id)
        if wellbore_id:
            ids = [rid for rid, bore in wellbore_of.items() if bore == wellbore_id]
            query = query.filter(DrillingParameters.report_id.in_(ids or [-1]))
        else:
            query = query.filter(canonical_params_clause(DrillingParameters))
        rows = [SimpleNamespace(id=p.id, report_id=p.report_id, report_date=p.report_date, bit_no=p.bit_no,
                                bit_rerun=p.bit_rerun, bit_size=p.bit_size, bit_type=p.bit_type,
                                manufacturer=p.manufacturer, iadc_code=p.iadc_code, depth_in=p.depth_in,
                                depth_out=p.depth_out, bit_drilled=p.bit_drilled, hours_on_bottom=p.hours_on_bottom,
                                wellbore_id=wellbore_of.get(p.report_id))
                for p in query.order_by(DrillingParameters.report_date, DrillingParameters.id).all()]
    return aggregate(rows)


# ---- cost per length (SCENARIO) --------------------------------------------------------------------------
@dataclass
class CostOutcome:
    status: str
    run_key: str
    reasons: List[str] = field(default_factory=list)
    currency: str = ""
    total_cost: Optional[float] = None
    cost_per_m: Optional[float] = None
    inputs: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "run": self.run_key, "reasons": list(self.reasons), "currency": self.currency,
                "total_cost": self.total_cost, "cost_per_m": self.cost_per_m, "inputs": dict(self.inputs)}


def scenario_problems(currency: str, bit_cost, rig_rate_per_day, trip_hours) -> List[str]:
    problems = []
    if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):   # M140: "USD\n" is not USD
        problems.append("currency not entered (type its 3-letter code, e.g. USD; nothing is converted)")
    for name, value in (("bit cost", bit_cost), ("rig rate per day", rig_rate_per_day), ("trip time", trip_hours)):
        if value is None:
            problems.append(f"{name} not entered")
        elif value < 0:
            problems.append(f"{name} cannot be negative")
    return problems


def cost_per_length(figures: Dict[str, Any], *, currency: str, bit_cost: Optional[float],
                    rig_rate_per_day: Optional[float], trip_hours: Optional[float],
                    missing: Sequence[str] = ()) -> CostOutcome:
    """(bit cost + rig rate / 24 x (trip + on-bottom hours)) / footage, in ``currency`` per metre."""
    from core.engineering.engines.bit_performance import BitPerformanceEngine

    key = f"{figures.get('bit_no')} / rerun {figures.get('rerun')}"
    inputs = {"currency": currency, "bit_cost": bit_cost, "rig_rate_per_day": rig_rate_per_day,
              "trip_hours": trip_hours}
    reasons = scenario_problems(currency, bit_cost, rig_rate_per_day, trip_hours)
    reasons += [f"run incomplete: {m}" for m in missing]
    footage, hours = figures.get("footage_m"), figures.get("hours_on_bottom")
    if not missing and (footage is None or footage <= 0):
        reasons.append("run footage is not a positive length")
    if not missing and hours is None:
        reasons.append("run hours on bottom unknown")
    if reasons:
        return CostOutcome(NOT_ASSESSED, key, reasons, currency, inputs=inputs)
    result = BitPerformanceEngine.cost_per_foot(rig_cost_per_day=rig_rate_per_day, trip_hours=trip_hours,
                                                bit_cost=bit_cost, footage=footage, rotating_hours=hours)
    if not result.success:
        return CostOutcome(NOT_ASSESSED, key, [str(getattr(result, "error", "") or "not computed")], currency,
                           inputs=inputs)
    # the engine's "cost_per_ft" is cost per unit of the length passed in - metres here
    return CostOutcome(ASSESSED, key, [], currency, result.values["total_cost"], result.values["cost_per_ft"],
                       inputs)


def compare(runs: Sequence[BitRun], outcomes: Dict[str, CostOutcome]) -> List[Dict[str, Any]]:
    """Side-by-side rows; "best" (lowest cost per metre, highest ROP) only among complete runs of one size."""
    rows = []
    for run in runs:
        outcome = outcomes.get(run.key)
        rows.append({"run": run.key, "size_in": run.size, "footage_m": run.footage, "hours": run.hours,
                     "rop_m_h": run.rop, "lifecycle": run.lifecycle, "data": COMPLETE if run.complete else INCOMPLETE,
                     "missing": list(run.missing), "cost_per_m": outcome.cost_per_m if outcome else None,
                     "currency": outcome.currency if outcome and outcome.status == ASSESSED else "",
                     "cost_status": outcome.status if outcome else NOT_ASSESSED,
                     "cost_reasons": list(outcome.reasons) if outcome else ["no scenario entered"],
                     "best_cost": False, "best_rop": False})
    sizes = {r["size_in"] for r in rows if r["size_in"] is not None}
    for size in sizes:
        group = [r for r in rows if r["size_in"] == size and r["data"] == COMPLETE]
        if len(group) < 2:
            continue                                     # a single run of a size is not a comparison
        costed = [r for r in group if r["cost_status"] == ASSESSED]
        if len(costed) >= 2 and len({r["currency"] for r in costed}) == 1:
            low = min(r["cost_per_m"] for r in costed)
            for r in costed:
                r["best_cost"] = abs(r["cost_per_m"] - low) < 1e-9
        rated = [r for r in group if r["rop_m_h"] is not None]
        if len(rated) >= 2:
            high = max(r["rop_m_h"] for r in rated)
            for r in rated:
                r["best_rop"] = abs(r["rop_m_h"] - high) < 1e-9
    return rows


# ---- persistence (immutable case) and re-run -------------------------------------------------------------
def save_scenario(db, run: BitRun, outcome: CostOutcome, *, well_id: int, wellbore_id: Optional[int] = None,
                  name: str = "", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store an ASSESSED scenario as a new immutable case; the wellbore only when the caller scoped one."""
    from core import calculation_cases as cc

    if outcome.status != ASSESSED:
        raise ValueError("Only an assessed cost scenario can be saved: " + "; ".join(outcome.reasons))
    if outcome.run_key != run.key:
        raise ValueError(f"The outcome is for {outcome.run_key}, not for {run.key}.")
    inputs = {**outcome.inputs, "run": run.figures(), "run_method": RUN_METHOD, "well_id": well_id,
              "wellbore_id": wellbore_id}
    results = _results(outcome.total_cost, outcome.cost_per_m, outcome.currency)
    return cc.save_case(db, calculator=COST_CALCULATOR, name=name or f"Bit {run.key} cost per metre",
                        inputs=inputs, results=results, method=COST_METHOD, method_version=COST_VERSION,
                        well_id=well_id, wellbore_id=wellbore_id, user_id=user_id, note=COST_LABEL)


def _results(total_cost: float, cost_per_m: float, currency: str) -> Dict[str, Any]:
    return {"total_cost": {"value": total_cost, "unit": currency},
            "cost_per_m": {"value": cost_per_m, "unit": f"{currency}/m"},
            "label": {"value": COST_LABEL, "unit": ""}}


def save_rerun(db, source_case_id: int, inputs: Dict[str, Any], outcome: Dict[str, Any], *,
               well_id: Optional[int], wellbore_id: Optional[int], name: str,
               user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store a verified re-run as a NEW scenario case linked ``rerun_of`` the original (same frozen inputs)."""
    from core import calculation_cases as cc

    values = outcome.get("values") or {}
    if outcome.get("status") not in ("MATCH", "DIFFERENT") or not values:
        raise ValueError(f"Nothing to store: re-run status {outcome.get('status')}.")
    return cc.save_case(
        db, calculator=COST_CALCULATOR, name=f"{name} (re-run)", inputs=inputs,
        results=_results(values["total_cost"], values["cost_per_m"], inputs.get("currency", "")),
        method=COST_METHOD, method_version=COST_VERSION, well_id=well_id, wellbore_id=wellbore_id, user_id=user_id,
        note=f"{COST_LABEL}; re-run of case #{source_case_id}: {outcome['status']}; {outcome.get('ddr_source', '')}",
        source_link={"link_type": "rerun_of", "source_table": "calculation_cases", "source_id": source_case_id,
                     "source_method": COST_METHOD, "source_method_version": COST_VERSION,
                     "recalc_method": COST_METHOD, "recalc_method_version": COST_VERSION,
                     "verification_status": outcome["status"], "method_changed": False})


def verify_case(db, inputs: Dict[str, Any], results: Dict[str, Any], version: str) -> Dict[str, Any]:
    """Repeat the cost from the frozen figures; report a DDR change since saving (never silently re-based)."""
    blank = {"method_matches": None, "current_method": f"{COST_METHOD} {COST_VERSION}", "values": {},
             "differences": [], "not_compared": []}
    if version != COST_VERSION:
        return {**blank, "status": "NOT_REPRODUCIBLE",
                "detail": f"method version {version!r} is not available in this build"}
    run = inputs.get("run") if isinstance(inputs, dict) else None
    if not isinstance(run, dict) or not isinstance(results, dict):
        return {**blank, "status": "UNREADABLE", "detail": "the stored scenario is not a bit run cost payload"}
    fresh = cost_per_length(run, currency=inputs.get("currency", ""), bit_cost=inputs.get("bit_cost"),
                            rig_rate_per_day=inputs.get("rig_rate_per_day"), trip_hours=inputs.get("trip_hours"))
    if fresh.status != ASSESSED:
        return {**blank, "status": "UNREADABLE", "detail": "; ".join(fresh.reasons)}
    differences = []
    for key, value in (("total_cost", fresh.total_cost), ("cost_per_m", fresh.cost_per_m)):
        stored = (results.get(key) or {}).get("value")
        if not isinstance(stored, (int, float)) or abs(stored - value) > COST_TOLERANCE:
            differences.append({"field_id": key, "stored": stored, "current": value})
    detail = f"{len(differences)} field(s) differ" if differences else "cost repeated from the frozen run figures"
    source = ddr_source_status(db, inputs)
    return {"status": "DIFFERENT" if differences else "MATCH", "method_matches": True,
            "current_method": f"{COST_METHOD} {COST_VERSION}", "detail": f"{detail}; {source}. {COST_LABEL}.",
            "values": {"total_cost": fresh.total_cost, "cost_per_m": fresh.cost_per_m},
            "differences": differences, "not_compared": [], "ddr_source": source}


def ddr_source_status(db, inputs: Dict[str, Any]) -> str:
    """Whether the run's DDR rows still hold the values the scenario froze."""
    run = inputs.get("run") or {}
    if db is None or not inputs.get("well_id"):
        return "DDR rows not re-read here"
    current = {r.key: r for r in load_runs(db, inputs["well_id"], inputs.get("wellbore_id"))}
    match = current.get(f"{run.get('bit_no')} / rerun {run.get('rerun')}")
    if match is None:
        return "DDR SOURCE CHANGED: the run is no longer in the DDRs"
    if rows_sha256(match.details) != run.get("rows_sha256"):
        return (f"DDR SOURCE CHANGED: the run's DDR rows differ now (footage {run.get('footage_m')} → "
                f"{match.footage} m, hours {run.get('hours_on_bottom')} → {match.hours})")
    return "DDR rows unchanged since saving"


# ---- export ------------------------------------------------------------------------------------------------
def export_csv(path: str, runs: Sequence[BitRun], comparison: Sequence[Dict[str, Any]], *, well_label: str,
               scope_label: str, scenario: Optional[Dict[str, Any]] = None) -> int:
    """Runs and comparison with their provenance; returns the number of run rows written."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        out = csv.writer(handle)
        out.writerow(["Bit run workbench", RUN_METHOD])
        out.writerow(["Well", well_label])
        out.writerow(["Scope", scope_label])
        out.writerow(["Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")])
        out.writerow(["Source", "DDR drilling parameters (legacy duplicate rows excluded); unknown values are empty"])
        out.writerow([])
        out.writerow(RUN_COLUMNS)
        for run in runs:
            out.writerow(["" if v is None else v for v in run.table_row()])
        out.writerow([])
        if scenario:
            out.writerow(["Cost scenario", COST_LABEL, COST_VERSION])
            out.writerow(["Currency", scenario.get("currency", ""), "Bit cost", scenario.get("bit_cost"),
                          "Rig rate per day", scenario.get("rig_rate_per_day"), "Trip hours",
                          scenario.get("trip_hours")])
        out.writerow(["Run", "Size (in)", "Footage (m)", "Hours", "ROP (m/h)", "Lifecycle", "Data", "Cost status",
                      "Cost per m", "Currency", "Lowest cost per m (same size)", "Highest ROP (same size)",
                      "Reasons"])
        for row in comparison:
            out.writerow([row["run"], _blank(row["size_in"]), _blank(row["footage_m"]), _blank(row["hours"]),
                          _blank(row["rop_m_h"]), row["lifecycle"], row["data"], row["cost_status"],
                          _blank(row["cost_per_m"]), row["currency"], "yes" if row["best_cost"] else "",
                          "yes" if row["best_rop"] else "", "; ".join(row["cost_reasons"] + row["missing"])])
    return len(runs)


def _blank(value):
    return "" if value is None else value
