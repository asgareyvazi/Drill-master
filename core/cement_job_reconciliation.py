"""M317 (M280): reconcile a recorded cement job with a frozen well-architecture revision (WORKSHEET).

The recorded job is one ``cement_reports`` row: sacks, slurry yield, recorded top and bottom of cement (m) and
recorded displacement (bbl). The geometry is one immutable ``well_architecture_revisions`` row and one cemented
string in it. The reconciliation answers three questions and never more:

1. Pumped slurry volume = sacks × yield converted to bbl/sk through the declared yield unit (``YIELD_UNITS``,
   M331). The yield unit is not stored on the report, so the caller must declare one of the registered units.
   Without a declaration (or with an unregistered unit) the volume stays None / the request is refused.
2. Gauge annulus volume between the **recorded** TOC and BOC, with the existing worksheet
   (``well_architecture.cement_annulus``: cased intervals use the outer string's ID, open hole uses the declared
   caliper, the entered open-hole size or the recorded hole size, otherwise unknown). The implied excess is
   (pumped − gauge) ÷ gauge. It is an implied figure, not a washout measurement.
3. Displacement capacity of the string from its top to its shoe (``CementEngine.displacement``). The shoe track is
   not recorded, so the capacity is the upper bound to the shoe. The recorded displacement is compared with it:
   above the bound it is EXCEEDS_CAPACITY; at or below it is WITHIN_UPPER_BOUND, which is NOT a statement that the
   displacement was right (under-displacement cannot be judged without the shoe track; M323 A-3).
   For a liner, displacement runs through the running string, so this check is NOT_APPLICABLE.

Never inferred: TOC, BOC, yield unit, shoe track, hole size. A missing TOC or BOC leaves the gauge volume None. The
architecture's own cement interval is shown next to the recorded one, but it never replaces it. Nothing is
written to the report or to the architecture.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

CONTRACT = "cement-job-reconciliation-v1"
METHOD_ID = "m317.cement_job_reconciliation"
METHOD_VERSION = "M317 v2 (yield-unit registry; well_architecture.cement_annulus + CementEngine.displacement)"
SUPPORTED_VERSIONS = ("M317 v1 (well_architecture.cement_annulus + CementEngine.displacement)", METHOD_VERSION)
LABEL = "WORKSHEET — RECORDED CEMENT JOB VS ARCHITECTURE — NOT A CEMENT EVALUATION"
# M331: controlled yield-unit registry. Each entry converts the declared yield to bbl per sack with an explicit,
# documented factor. An unregistered unit is refused, never inferred.
#   ft3/sk : ÷ 5.6146 ft³/bbl  (CementEngine.BBL_PER_CUFT, the value every existing cement worksheet uses)
#   gal/sk : ÷ 42 gal/bbl      (US gallon; exact by definition)
#   bbl/sk : × 1
#   L/sk   : ÷ 158.987294928 L/bbl (exact: 1 bbl = 0.158987294928 m³)
#   m3/sk  : ÷ 0.158987294928 m³/bbl
YIELD_UNITS = {"ft3/sk": "BBL_PER_CUFT", "gal/sk": 42.0, "bbl/sk": 1.0, "L/sk": 158.987294928,
               "m3/sk": 0.158987294928}
YIELD_BASIS = {"ft3/sk": "÷ 5.6146 ft³/bbl (cement engine constant)", "gal/sk": "÷ 42 US gal/bbl (exact)",
               "bbl/sk": "× 1", "L/sk": "÷ 158.987294928 L/bbl (exact)", "m3/sk": "÷ 0.158987294928 m³/bbl (exact)"}
M_TO_FT = 3.28084
DISPLACEMENT_TOLERANCE = 0.02            # relative, display tolerance for rounding in recorded reports
WITHIN, OVER_CAPACITY, NOT_CHECKED, NOT_APPLICABLE = ("WITHIN_UPPER_BOUND", "EXCEEDS_CAPACITY", "NOT_CHECKED",
                                                     "NOT_APPLICABLE")


class ReconciliationError(ValueError):
    """A request that cannot be reconciled at all (wrong well, unknown string, bad declaration)."""


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):  # silent-ok: an unparseable recorded value is missing (None), stated as unknown in the result
        return None
    return number if math.isfinite(number) and number > 0 else None


def _depth(value: Any) -> Optional[float]:
    """Recorded depths: 0 is a real surface depth for TOC, so only None / non-finite / negative are missing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):  # silent-ok: an unparseable recorded depth is missing (None); TOC/BOC are never inferred
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _recorded_zero(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):  # silent-ok: not a number at all, so not a recorded zero
        return False


def bbl_per_sack(yield_value: float, unit: str) -> float:
    """Declared yield → bbl per sack through the registry (M331). Raises for an unregistered unit."""
    from core.engineering.engines.cement import BBL_PER_CUFT

    if unit not in YIELD_UNITS:
        raise ReconciliationError(f"Yield unit {unit!r} is not supported; declare one of {sorted(YIELD_UNITS)}.")
    divisor = BBL_PER_CUFT if YIELD_UNITS[unit] == "BBL_PER_CUFT" else YIELD_UNITS[unit]
    return yield_value / divisor


def recorded_job(db, cement_report_id: int) -> Dict[str, Any]:
    from core.database import CementReport

    with db.session_scope() as session:
        row = session.get(CementReport, cement_report_id)
        if row is None:
            raise LookupError(f"Cement report {cement_report_id} does not exist.")
        return {"id": row.id, "well_id": row.well_id, "report_id": row.report_id, "name": row.report_name or "",
                "job_type": row.job_type or "", "sacks": _num(row.cement_volume), "yield": _num(row.slurry_yield),
                "slurry_density_pcf": _num(row.slurry_density), "toc_m": _depth(row.top_of_cement),
                "boc_m": _depth(row.bottom_of_cement), "displacement_bbl": _num(row.displacement_volume),
                "recorded_zero": [k for k, v in (("sacks", row.cement_volume), ("yield", row.slurry_yield),
                                                 ("displacement", row.displacement_volume)) if _recorded_zero(v)]}


def list_jobs(db, well_id: int) -> List[Dict[str, Any]]:
    from core.database import CementReport

    with db.session_scope() as session:
        ids = [r.id for r in session.query(CementReport.id).filter_by(well_id=well_id).order_by(CementReport.id)]
    return [recorded_job(db, i) for i in ids]


def reconcile(db, cement_report_id: int, architecture_revision_id: int, string_name: str, *,
              yield_unit: Optional[str] = None, open_hole_in: Optional[float] = None,
              caliper_in: Optional[float] = None) -> Dict[str, Any]:
    from core import well_architecture as wa

    return compute(recorded_job(db, cement_report_id), wa.get_revision(db, architecture_revision_id), string_name,
                   yield_unit=yield_unit, open_hole_in=open_hole_in, caliper_in=caliper_in)


def compute(job: Dict[str, Any], revision: Dict[str, Any], string_name: str, *, yield_unit: Optional[str] = None,
            open_hole_in: Optional[float] = None, caliper_in: Optional[float] = None) -> Dict[str, Any]:
    """The reconciliation of one recorded job (a dict, live or frozen) against one verified revision."""
    from core import well_architecture as wa
    from core.engineering.engines.cement import CementEngine

    if revision["well_id"] != job["well_id"]:
        raise ReconciliationError(f"Architecture revision {revision['revision']} belongs to well {revision['well_id']},"
                                  f" the cement report to well {job['well_id']}.")
    if yield_unit is not None and yield_unit not in YIELD_UNITS:
        raise ReconciliationError(f"Yield unit {yield_unit!r} is not supported; declare one of {sorted(YIELD_UNITS)}.")
    items = wa.normalize(revision["components"])[0]
    string = next((i for i in items if i["kind"] in wa.STRINGS and i["name"] == string_name), None)
    cement = next((i for i in items if i["kind"] == "cement" and i["name"] == string_name), None)
    if string is None:
        raise ReconciliationError(f"'{string_name}' is not a string in architecture revision {revision['revision']}.")
    notes: List[str] = []

    # 1. pumped slurry volume
    pumped = None
    zeros = [k for k in ("sacks", "yield") if k in (job.get("recorded_zero") or [])]
    if zeros:
        notes.append(f"pumped volume not computed: {' and '.join(zeros)} recorded as 0 (no slurry volume can be "
                     f"derived from a zero)")
    elif job["sacks"] is None or job["yield"] is None:
        notes.append("pumped volume not computed: sacks and slurry yield must both be recorded")
    elif yield_unit is None:
        notes.append("pumped volume not computed: the yield unit is not stored on the report and was not declared")
    else:
        pumped = job["sacks"] * bbl_per_sack(job["yield"], yield_unit)

    # 2. gauge annulus between the recorded TOC and BOC
    toc, boc = job["toc_m"], job["boc_m"]
    gauge, intervals, interval_note = None, [], ""
    if toc is None or boc is None:
        interval_note = "recorded TOC and BOC are both needed; neither is inferred"
    elif boc <= toc:
        interval_note = f"recorded BOC {boc:g} m is not below recorded TOC {toc:g} m"
    elif cement is None:
        interval_note = f"'{string_name}' has no cement record in this architecture revision"
    else:
        recorded = [dict(c, top_md=toc, bottom_md=boc) if c.get("kind") == "cement" and c.get("name") == string_name
                    else c for c in revision["components"]]
        try:
            annulus = wa.cement_annulus(recorded, string_name, open_hole_in=open_hole_in, caliper_in=caliper_in)
        except (wa.ArchitectureError, ValueError) as exc:
            interval_note = f"annulus not derived: {exc}"
        else:
            gauge, intervals = annulus["base_total_bbl"], annulus["intervals"]
            if gauge is None:
                interval_note = "an interval has no known outer size; the gauge volume stays unknown"
    if interval_note:
        notes.append(interval_note)
    excess = (pumped - gauge) / gauge * 100.0 if pumped is not None and gauge else None
    architecture_interval = ({"top_md": cement["top_md"], "bottom_md": cement["bottom_md"]} if cement else None)
    toc_difference = (toc - cement["top_md"]) if cement and toc is not None and cement["top_md"] is not None else None

    # 3. displacement capacity to the shoe
    displacement = {"status": NOT_CHECKED, "capacity_to_shoe_bbl": None, "reason": ""}
    if string["kind"] == "liner":
        displacement.update(status=NOT_APPLICABLE, reason="a liner is displaced through the running string, "
                                                          "which is not part of the architecture")
    elif string["id_in"] is None or string["top_md"] is None or string["bottom_md"] is None:
        displacement["reason"] = "the string has no recorded ID, top or bottom"
    else:
        result = CementEngine.displacement(string["id_in"], (string["bottom_md"] - string["top_md"]) * M_TO_FT, 0)
        capacity = result.values.get("displacement_volume_bbl") if result.success else None
        displacement["capacity_to_shoe_bbl"] = capacity
        if capacity is None:
            displacement["reason"] = f"capacity not computed: {result.error}"
        elif job["displacement_bbl"] is None:
            displacement["reason"] = "no displacement recorded on the report"
        else:
            over = job["displacement_bbl"] > capacity * (1 + DISPLACEMENT_TOLERANCE)
            displacement.update(
                status=OVER_CAPACITY if over else WITHIN,
                reason=(f"recorded {job['displacement_bbl']:g} bbl vs {capacity:g} bbl string capacity to the shoe "
                        f"(upper bound: the shoe track is not recorded"
                        + ("" if over else "; under-displacement cannot be judged") + ")"))
    return {"contract": CONTRACT, "method": METHOD_ID, "method_version": METHOD_VERSION, "label": LABEL,
            "well_id": job["well_id"], "job": job, "architecture_revision_id": revision["id"],
            "architecture_revision": revision["revision"], "components_sha256": revision["components_sha256"],
            "string": string_name, "string_kind": string["kind"], "yield_unit": yield_unit,
            "open_hole_in": open_hole_in, "caliper_in": caliper_in, "pumped_bbl": pumped, "gauge_bbl": gauge,
            "implied_excess_pct": excess, "intervals": intervals, "architecture_interval": architecture_interval,
            "toc_difference_m": toc_difference, "displacement": displacement, "notes": notes,
            "status": "COMPUTED" if (gauge is not None or pumped is not None
                                     or displacement["capacity_to_shoe_bbl"] is not None) else "NOT_COMPUTED"}


def summary_lines(result: Dict[str, Any]) -> List[str]:
    job = result["job"]

    def show(value, unit, digits=2):
        return "unknown" if value is None else f"{value:.{digits}f} {unit}"

    lines = [f"{result['label']}.",
             f"Cement report #{job['id']} vs architecture rev {result['architecture_revision']}, string "
             f"{result['string']} ({result['string_kind']}).",
             f"Pumped slurry: {show(result['pumped_bbl'], 'bbl')}"
             + (f" ({job['sacks']:g} sk × {job['yield']:g} {result['yield_unit']})" if result["pumped_bbl"] is not None else "")
             + ".",
             f"Recorded interval: TOC {show(job['toc_m'], 'm', 1)}, BOC {show(job['boc_m'], 'm', 1)}; gauge annulus "
             f"{show(result['gauge_bbl'], 'bbl')}; implied excess {show(result['implied_excess_pct'], '%', 1)}."]
    if result["architecture_interval"]:
        arch = result["architecture_interval"]
        lines.append(f"Architecture cement record: {arch['top_md']:g}–{arch['bottom_md']:g} m"
                     + ("" if result["toc_difference_m"] is None else
                        " (recorded TOC equals the architecture record)" if result["toc_difference_m"] == 0 else
                        f" (recorded TOC differs by {result['toc_difference_m']:+.1f} m)") + ".")
    d = result["displacement"]
    lines.append(f"Displacement: {d['status']}" + (f" – {d['reason']}" if d["reason"] else "") + ".")
    lines += [f"Note: {n}." for n in result["notes"]]
    return lines


def save_case(db, result: Dict[str, Any], *, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store a computed reconciliation as an immutable case linked to the cement report."""
    from core import calculation_cases as cc

    if result.get("status") != "COMPUTED":
        raise ValueError("Nothing was computed; there is no reconciliation to store.")
    job = result["job"]
    inputs, results = case_payload(result)
    return cc.save_case(db, calculator="Cement job reconciliation",
                        name=f"Cement job #{job['id']} vs arch rev {result['architecture_revision']} ({result['string']})",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=result["well_id"], user_id=user_id, note=LABEL,
                        source_link={"link_type": "recalculation_of", "source_table": "cement_reports",
                                     "source_id": job["id"], "verification_status": result["displacement"]["status"],
                                     "recalc_method": METHOD_ID, "recalc_method_version": METHOD_VERSION})


def case_payload(result: Dict[str, Any]):
    """(inputs, results) of a reconciliation case: one builder for save and M328 replay."""
    job = result["job"]
    inputs = {
        "cement_report_id": {"value": job["id"], "unit": "", "label": "cement report id", "source": "RECORDED"},
        "architecture_revision_id": {"value": result["architecture_revision_id"], "unit": "",
                                     "label": f"architecture rev {result['architecture_revision']} "
                                              f"({result['components_sha256'][:12]})", "source": "RECORDED"},
        "string": {"value": result["string"], "unit": "", "label": "cemented string", "source": "SELECTED"},
        "yield_unit": {"value": result["yield_unit"], "unit": "", "label": "declared yield unit",
                       "source": "DECLARED" if result["yield_unit"] else "NOT_DECLARED"},
        "open_hole_in": {"value": result["open_hole_in"], "unit": "in", "label": "open hole entered",
                         "source": "DECLARED" if result["open_hole_in"] else "NOT_DECLARED"},
        "caliper_in": {"value": result["caliper_in"], "unit": "in", "label": "average caliper",
                       "source": "DECLARED" if result["caliper_in"] else "NOT_DECLARED"},
        **{f"recorded_{k}": {"value": job[k], "unit": u, "label": f"recorded {k}", "source": "RECORDED"}
           for k, u in (("sacks", "sk"), ("yield", result["yield_unit"] or "undeclared"), ("toc_m", "m"),
                        ("boc_m", "m"), ("displacement_bbl", "bbl"))},
        "components_sha256": {"value": result["components_sha256"], "unit": "", "label": "architecture SHA-256",
                              "source": "RECORDED"},
        # M328: the recorded job exactly as reconciled; a replay never re-reads the (mutable) cement report
        "job_snapshot": {"value": dict(job), "unit": "", "label": "frozen recorded job (M328 replay)",
                         "source": "SNAPSHOT"},
    }
    results = {"pumped_bbl": {"value": result["pumped_bbl"], "label": "pumped slurry (bbl)"},
               "gauge_bbl": {"value": result["gauge_bbl"], "label": "gauge annulus, recorded TOC-BOC (bbl)"},
               "implied_excess_pct": {"value": result["implied_excess_pct"], "label": "implied excess (%)"},
               "capacity_to_shoe_bbl": {"value": result["displacement"]["capacity_to_shoe_bbl"],
                                        "label": "string capacity to shoe (bbl, upper bound)"},
               "displacement_check": {"value": result["displacement"]["status"],
                                      "label": result["displacement"]["reason"]}}
    return inputs, results
