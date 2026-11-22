"""M314 (M277): recorded vs recomputed bit hydraulics for one daily report (SCREENING).

Takes only values recorded on the report: bit size and TFA / nozzles and pump output from
``drilling_parameters``, and mud weight from ``mud_reports``. It recomputes bit hydraulics with the existing
engine (``AdvancedHydraulicsEngine.calc_bit_hydraulics``: ΔP = Q²·MW / (10858·TFA²), HHP = Q·ΔP / 1714,
HSI = HHP / (π/4·D²), v = Q / (3.117·TFA), IF = MW·Q·v / 1930) and compares the result with the recorded HSI.

Rules:
* No formula or constant is new. Mud weight is converted pcf → ppg by the hydraulics engine's own
  ``MudProperties.mw_ppg`` (÷ 7.48052, as every hydraulics calculation already does). The P8 owner decision
  (short vs long pcf divisor in mud volumes) is unaffected.
* Nothing is invented. A missing input is listed and the dependent result is None. TFA is derived from the
  nozzles only when every nozzle row has an explicit size and count. Several different mud weights on one report
  make the check NOT_CHECKED instead of picking one.
* The recorded HSI is compared with the HSI range over the recorded pump outputs (min..max). The comparison
  tolerance ``HSI_TOLERANCE`` is a display tolerance for rounding in reports, not an engineering limit.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

CONTRACT = "ddr-hydraulics-check-v1"
METHOD_ID = "m314.ddr_bit_hydraulics_check"
METHOD_VERSION = "M314 v1 (AdvancedHydraulicsEngine.calc_bit_hydraulics)"
SCOPE = "SCREENING — recorded vs recomputed bit hydraulics (not a hydraulics programme)"
HSI_TOLERANCE = 0.05            # relative; rounding in recorded reports, documented as a display tolerance
TFA_TOLERANCE = 0.01            # relative; recorded TFA vs TFA from the recorded nozzles
AGREES, DIFFERS, NOT_CHECKED = "AGREES", "DIFFERS", "NOT_CHECKED"


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):  # silent-ok: an unparseable recorded value is MISSING (None) and named in the result
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> Optional[float]:
    number = _num(value)
    return number if number is not None and number > 0 else None


def _input(value, unit, source, status="RECORDED", note=""):
    return {"value": value, "unit": unit, "source": source, "status": status, "note": note}


def tfa_from_nozzles(nozzles_json: Any) -> Dict[str, Any]:
    """TFA (in²) from the recorded nozzle rows, or None with the reason. Never fills a missing size or count."""
    from core.engineering.core import BitEngine

    if nozzles_json in (None, "", "[]"):
        return {"value": None, "reason": "no nozzle rows recorded"}
    try:
        rows = json.loads(nozzles_json) if isinstance(nozzles_json, str) else nozzles_json
    except ValueError:
        return {"value": None, "reason": "nozzle rows are unreadable"}
    if not isinstance(rows, list) or not rows:
        return {"value": None, "reason": "no nozzle rows recorded"}
    program = []
    for row in rows:
        size = _positive((row or {}).get("size_32nd")) if isinstance(row, dict) else None
        qty = (row or {}).get("quantity") if isinstance(row, dict) else None
        if size is None or not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            text = (row or {}).get("text") if isinstance(row, dict) else row
            return {"value": None, "reason": f"nozzle row {row.get('row') if isinstance(row, dict) else '?'} has "
                                             f"no explicit size and count ({text!r})"}
        program.append((size, qty))
    return {"value": BitEngine.calculate_tfa_program(program), "reason": "",
            "program": [{"size_32nd": s, "quantity": q} for s, q in program]}


def gather(db, report_id: int) -> Dict[str, Any]:
    """The recorded inputs of one report with their provenance (read-only)."""
    from core.database import DailyReport, DrillingParameters, MudReport
    from core.hydraulics_engine import MudProperties

    with db.session_scope() as session:
        report = session.get(DailyReport, report_id)
        if report is None:
            raise LookupError(f"Daily report {report_id} does not exist.")
        dp = session.query(DrillingParameters).filter_by(report_id=report_id).order_by(DrillingParameters.id).all()
        muds = session.query(MudReport).filter_by(report_id=report_id).order_by(MudReport.id).all()
        well_id = report.well_id
        dp_rows = [{c: getattr(r, c) for c in ("id", "bit_no", "bit_size", "tfa", "nozzles_json", "pump_output_min",
                                                "pump_output_max", "hsi", "pump_pressure_max")} for r in dp]
        mud_rows = [{"id": m.id, "mw": m.mw, "sample_time": m.sample_time} for m in muds]
    inputs: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    if len(dp_rows) > 1:
        problems.append(f"{len(dp_rows)} drilling-parameter records on this report; the check needs exactly one")
    row = dp_rows[0] if len(dp_rows) == 1 else {}
    src = f"drilling_parameters#{row['id']}" if row else "drilling_parameters (none)"
    inputs["bit_size_in"] = _input(_positive(row.get("bit_size")), "in", f"{src}.bit_size")
    inputs["tfa_recorded_in2"] = _input(_positive(row.get("tfa")), "in2", f"{src}.tfa")
    nozzle = tfa_from_nozzles(row.get("nozzles_json"))
    inputs["tfa_nozzles_in2"] = _input(nozzle["value"], "in2", f"{src}.nozzles_json", "DERIVED", nozzle["reason"])
    inputs["flow_min_gpm"] = _input(_positive(row.get("pump_output_min")), "gpm", f"{src}.pump_output_min")
    inputs["flow_max_gpm"] = _input(_positive(row.get("pump_output_max")), "gpm", f"{src}.pump_output_max")
    inputs["hsi_recorded"] = _input(_positive(row.get("hsi")), "hp/in2", f"{src}.hsi")
    weights = sorted({w for w in (_positive(m["mw"]) for m in mud_rows) if w is not None})
    if len(weights) > 1:
        problems.append(f"{len(weights)} different mud weights recorded on this report "
                        f"({', '.join(f'{w:g}' for w in weights)} pcf); none is chosen")
        mw_pcf = None
    else:
        mw_pcf = weights[0] if weights else None
    inputs["mw_pcf"] = _input(mw_pcf, "pcf", "mud_reports.mw")
    inputs["mw_ppg"] = _input(MudProperties(mw_pcf=mw_pcf).mw_ppg if mw_pcf else None, "ppg", "mud_reports.mw",
                              "DERIVED", "pcf -> ppg by MudProperties.mw_ppg (÷ 7.48052, hydraulics engine)")
    for name, entry in inputs.items():
        if entry["value"] is None and entry["status"] == "RECORDED":
            entry["status"] = "MISSING"
    return {"report_id": report_id, "well_id": well_id, "inputs": inputs, "problems": problems,
            "drilling_parameters_id": row.get("id")}


def check(db, report_id: int) -> Dict[str, Any]:
    """Recompute bit hydraulics from the recorded inputs and compare with the recorded HSI."""
    return evaluate(gather(db, report_id))


def evaluate(data: Dict[str, Any]) -> Dict[str, Any]:
    """The check on gathered inputs: live (``gather``) or frozen in a saved case (M328 replay). Pure; reads nothing."""
    from core.hydraulics_engine import AdvancedHydraulicsEngine as H

    inputs = data["inputs"]
    report_id = data["report_id"]
    recorded_tfa, nozzle_tfa = inputs["tfa_recorded_in2"]["value"], inputs["tfa_nozzles_in2"]["value"]
    tfa_check = {"status": NOT_CHECKED, "reason": "needs both the recorded TFA and complete nozzle rows"}
    if recorded_tfa and nozzle_tfa:
        same = abs(recorded_tfa - nozzle_tfa) <= TFA_TOLERANCE * nozzle_tfa
        tfa_check = {"status": AGREES if same else DIFFERS,
                     "reason": f"recorded {recorded_tfa:.4f} in² vs nozzles {nozzle_tfa:.4f} in²"}
    tfa, tfa_basis = (recorded_tfa, "recorded TFA") if recorded_tfa else \
        (nozzle_tfa, "TFA from the recorded nozzles") if nozzle_tfa else (None, "")
    missing = [name for name, value in (("bit size", inputs["bit_size_in"]["value"]), ("TFA or nozzles", tfa),
                                        ("mud weight", inputs["mw_ppg"]["value"]))
               if value is None]
    flows = [(label, inputs[key]["value"]) for label, key in (("min", "flow_min_gpm"), ("max", "flow_max_gpm"))
             if inputs[key]["value"] is not None]
    if not flows:
        missing.append("pump output")
    computed: Dict[str, Dict[str, float]] = {}
    if not missing and not data["problems"]:
        for label, gpm in flows:
            computed[label] = {"flow_gpm": gpm, **H.calc_bit_hydraulics(gpm, inputs["mw_ppg"]["value"], tfa,
                                                                        inputs["bit_size_in"]["value"])}
    recorded_hsi = inputs["hsi_recorded"]["value"]
    if not computed:
        reasons = data["problems"] + ([f"missing: {', '.join(missing)}"] if missing else [])
        hsi_check = {"status": NOT_CHECKED, "reason": "; ".join(reasons) or "nothing to compute"}
    elif recorded_hsi is None:
        hsi_check = {"status": NOT_CHECKED, "reason": "no HSI recorded on this report"}
    else:
        low = min(c["hsi"] for c in computed.values())
        high = max(c["hsi"] for c in computed.values())
        inside = low * (1 - HSI_TOLERANCE) <= recorded_hsi <= high * (1 + HSI_TOLERANCE)
        hsi_check = {"status": AGREES if inside else DIFFERS,
                     "reason": (f"recorded {recorded_hsi:g} hp/in² vs recomputed {low:g}"
                                + (f"–{high:g}" if high != low else "") + f" hp/in² (±{HSI_TOLERANCE:.0%})")}
    return {"contract": CONTRACT, "method": METHOD_ID, "method_version": METHOD_VERSION, "scope": SCOPE,
            "report_id": report_id, "well_id": data["well_id"],
            "drilling_parameters_id": data["drilling_parameters_id"], "inputs": inputs, "problems": data["problems"],
            "missing": missing, "tfa_used": tfa, "tfa_basis": tfa_basis, "tfa_check": tfa_check,
            "computed": computed, "hsi_check": hsi_check, "status": "COMPUTED" if computed else "NOT_COMPUTED"}


def save_check(db, result: Dict[str, Any], *, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store a COMPUTED check as an immutable calculation case (visible in Calculation history)."""
    from core import calculation_cases as cc

    if result.get("status") != "COMPUTED":
        raise ValueError("Only a computed hydraulics check can be stored; nothing was computed for this report.")
    inputs = {name: {"value": e["value"], "unit": e["unit"], "label": f"{name} ({e['source']})",
                     "source": e["status"]} for name, e in result["inputs"].items()}
    inputs["report_id"] = {"value": result["report_id"], "unit": "", "label": "daily report id", "source": "RECORDED"}
    # M328: the exact gathered inputs (value, unit, source path, status, note), so a replay never reads the DDR
    inputs["snapshot"] = {"value": {"inputs": result["inputs"], "problems": list(result["problems"]),
                                    "report_id": result["report_id"],
                                    "well_id": result["well_id"],
                                    "drilling_parameters_id": result["drilling_parameters_id"]},
                          "unit": "", "label": "frozen gathered inputs (M328 replay)", "source": "SNAPSHOT"}
    results = case_results(result)
    return cc.save_case(db, calculator="DDR hydraulics check", name=f"Hydraulics check report #{result['report_id']}",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=result["well_id"], user_id=user_id,
                        note=f"{SCOPE}; TFA basis: {result['tfa_basis']}",
                        source_link={"link_type": "recalculation_of", "source_table": "drilling_parameters",
                                     "source_id": result["drilling_parameters_id"],
                                     "verification_status": result["hsi_check"]["status"],
                                     "recalc_method": METHOD_ID, "recalc_method_version": METHOD_VERSION})


def case_results(result: Dict[str, Any]) -> Dict[str, Any]:
    """The stored result fields of a check (one builder for save and replay)."""
    results: Dict[str, Any] = {}
    for label, values in result["computed"].items():
        for key, value in values.items():
            results[f"{label}_{key}"] = {"value": value, "label": f"{key} at {label} pump output"}
    results["hsi_check"] = {"value": result["hsi_check"]["status"], "label": result["hsi_check"]["reason"]}
    results["tfa_check"] = {"value": result["tfa_check"]["status"], "label": result["tfa_check"]["reason"]}
    return results


def summary_lines(result: Dict[str, Any]) -> List[str]:
    lines = [f"{SCOPE}.", f"Status: {result['status']}."]
    if result["missing"]:
        lines.append("Missing: " + ", ".join(result["missing"]) + ".")
    lines += [f"Problem: {p}." for p in result["problems"]]
    for label, values in result["computed"].items():
        lines.append(f"At {label} pump output {values['flow_gpm']:g} gpm: bit ΔP {values['bit_pressure_drop_psi']:g} psi, "
                     f"HHP {values['bit_hhp']:g}, HSI {values['hsi']:g} hp/in², jet {values['jet_velocity_fps']:g} ft/s, "
                     f"impact {values['impact_force_lbs']:g} lbf.")
    lines.append(f"HSI check: {result['hsi_check']['status']} – {result['hsi_check']['reason']}.")
    lines.append(f"TFA check: {result['tfa_check']['status']} – {result['tfa_check']['reason']}.")
    return lines
