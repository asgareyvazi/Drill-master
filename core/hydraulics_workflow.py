"""M366 — circulating-system hydraulics workflow on top of the W13 engine (SCREENING).

The W13 hydraulics page (``core/w13_hydraulics.py`` → ``core/hydraulics_engine.AdvancedHydraulicsEngine``) computes
one operating point. This module adds the engineering workflow around that one point without a second hydraulics
model:

* **pressure budget**: surface, drill pipe, HWDP, BHA, unclassified string, bit and annulus losses with their share
  of the predicted standpipe pressure; the component sum is checked against the engine total;
* **pump limits**: the predicted standpipe pressure against each pump's ENTERED maximum pressure, and the required
  hydraulic horsepower of each pump's share of the flow against its ENTERED rated horsepower (mechanical efficiency
  is never assumed, so passing this check is necessary, not sufficient);
* **flow-rate sensitivity**: the same frozen inputs re-run at declared flow rates;
* **nozzle sensitivity**: the same frozen inputs re-run with declared alternative nozzle sets;
* **plan vs actual**: an OBSERVED standpipe pressure against the prediction, classified only against a tolerance the
  user declares (no default band).

Every run uses the same frozen page values (``values``) and stores their SHA-256, so a saved case is replayed by
``core.history_replay`` from the snapshot, never from the widgets.

Rules kept from the engine: ECD is reported only when the engine assessed it (complete annular geometry); a missing
value stays ``None``; an un-entered pump limit (0 on the page) is NOT ENTERED, never a limit of 0 psi. Mud density
enters in pcf and is converted with the P8 density divisor inside the engine; every density output is ppg.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

CONTRACT = "hydraulics-workflow-v1"
METHOD_ID = "m366.hydraulics_workflow"
METHOD_VERSION = "M366 v1 (W13 circulating-system engine; budget, pump limits, flow/nozzle sensitivity, plan vs actual)"
LABEL = "SCREENING — PRESSURE BUDGET AND SENSITIVITY — NOT FIELD-CALIBRATED"
CALCULATOR = "Hydraulics workflow"
MAX_FLOW_POINTS = 12
MAX_NOZZLE_SETS = 8
HHP_DIVISOR = 1714.0          # hydraulic hp = psi × gpm / 1714 (field units)
GAL_PER_BBL = 42.0

DRILL_PIPE_TYPES = ("Drill Pipe",)
HWDP_TYPES = ("HWDP",)
BHA_TYPES = ("Drill Collar", "MWD/LWD", "Motor", "Stabilizer", "Sub", "Jar", "X-Over")
GROUPS = ("surface", "drill_pipe", "hwdp", "bha", "unclassified_string", "bit", "annulus")
GROUP_LABELS = {"surface": "Surface equipment", "drill_pipe": "Drill pipe bore", "hwdp": "HWDP bore",
                "bha": "BHA bore (collars, MWD/LWD, motor, stabilisers, subs, jars, X-overs)",
                "unclassified_string": "String bore, component type not classified", "bit": "Bit nozzles",
                "annulus": "Annulus (all intervals)"}


class WorkflowError(ValueError):
    """Declared workflow options are malformed (nothing is computed)."""


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


# ---- parsing of declared options --------------------------------------------------------------------------
def parse_flow_rates(text: str) -> List[float]:
    """``"400, 450 500"`` → ``[400.0, 450.0, 500.0]``; every value positive and finite, no duplicates."""
    items = [t for t in (text or "").replace(";", ",").replace(" ", ",").split(",") if t.strip()]
    rates: List[float] = []
    for item in items:
        try:
            value = float(item)
        except ValueError as exc:
            raise WorkflowError(f"flow rate {item!r} is not a number") from exc
        if not math.isfinite(value) or value <= 0:
            raise WorkflowError(f"flow rate {item!r} must be positive and finite")
        if value not in rates:
            rates.append(value)
    if len(rates) > MAX_FLOW_POINTS:
        raise WorkflowError(f"at most {MAX_FLOW_POINTS} flow rates per sweep")
    return rates


def parse_nozzle_sets(text: str) -> List[List[Tuple[int, int]]]:
    """``"3x12+1x13; 4x12"`` → ``[[(12, 3), (13, 1)], [(12, 4)]]`` as (size in 32nds, quantity)."""
    sets: List[List[Tuple[int, int]]] = []
    for chunk in [c.strip() for c in (text or "").split(";") if c.strip()]:
        nozzles: List[Tuple[int, int]] = []
        for part in [p.strip().lower() for p in chunk.split("+") if p.strip()]:
            if "x" not in part:
                raise WorkflowError(f"nozzle group {part!r} must be written quantity x size (e.g. 3x12)")
            qty_text, size_text = (s.strip() for s in part.split("x", 1))
            try:
                qty, size = int(qty_text), int(size_text)
            except ValueError as exc:
                raise WorkflowError(f"nozzle group {part!r} needs whole numbers") from exc
            if qty <= 0 or size <= 0:
                raise WorkflowError(f"nozzle group {part!r} needs a positive quantity and size")
            nozzles.append((size, qty))
        if nozzles:
            sets.append(nozzles)
    if len(sets) > MAX_NOZZLE_SETS:
        raise WorkflowError(f"at most {MAX_NOZZLE_SETS} nozzle sets per sweep")
    return sets


def nozzle_set_label(nozzles: Sequence[Sequence[int]]) -> str:
    return " + ".join(f"{qty}x{size}/32" for size, qty in nozzles)


# ---- frozen inputs ----------------------------------------------------------------------------------------
def freeze(values: Mapping[str, Any]) -> Dict[str, Any]:
    """A JSON round-trip copy of the page values (the immutable record of what was computed)."""
    try:
        return json.loads(json.dumps(dict(values), sort_keys=True, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise WorkflowError(f"the hydraulics inputs cannot be frozen: {exc}") from exc


def values_sha256(values: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(values), sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


def classify_component(type_text: str) -> str:
    text = (type_text or "").strip()
    if text in DRILL_PIPE_TYPES:
        return "drill_pipe"
    if text in HWDP_TYPES:
        return "hwdp"
    if text in BHA_TYPES:
        return "bha"
    return "unclassified_string"


def _engine_run(values: Mapping[str, Any], *, flow_gpm: Optional[float] = None,
                nozzles: Optional[Sequence[Sequence[int]]] = None):
    from core import w13_hydraulics
    from core.hydraulics_engine import AdvancedHydraulicsEngine, BitNozzle

    engine = AdvancedHydraulicsEngine()
    w13_hydraulics.configure(engine, dict(values))
    if flow_gpm is not None:
        engine.flow_rate_gpm = float(flow_gpm)
    if nozzles is not None:
        engine.nozzles = [BitNozzle(size_32nds=int(size), quantity=int(qty)) for size, qty in nozzles]
    return engine, engine.calculate()


# ---- pressure budget --------------------------------------------------------------------------------------
def pressure_budget(engine, result) -> Dict[str, Any]:
    """Losses by group with their share of the predicted standpipe pressure (engine rows only)."""
    sums = {group: None for group in GROUPS}

    def add(group: str, value: Optional[float]) -> None:
        if value is not None:
            sums[group] = (sums[group] or 0.0) + value

    add("surface", _num(result.surface_loss_psi))
    segments = list(getattr(engine, "pipe_segments", []) or [])
    for name, loss in result.pipe_losses:
        owner = next((seg for seg in segments if str(name).startswith(f"{seg.name} in ")), None)
        add(classify_component(owner.pipe_type if owner is not None else ""), _num(loss))
    add("bit", _num(result.bit_loss_psi))
    for _name, loss in result.annulus_losses:
        add("annulus", _num(loss))
    total = _num(result.total_loss_psi)
    rows = []
    for group in GROUPS:
        value = sums[group]
        share = (value / total * 100.0) if (value is not None and total) else None
        rows.append({"group": group, "label": GROUP_LABELS[group], "loss_psi": value, "share_pct": share})
    component_sum = sum(v for v in sums.values() if v is not None)
    # the engine rounds each component to 0.01 psi, so the closure tolerance scales with the row count
    rounding = 0.01 * (len(result.pipe_losses) + len(result.annulus_losses) + 2)
    closes = total is not None and abs(component_sum - total) <= max(rounding, 1e-6)
    return {"rows": rows, "predicted_spp_psi": total, "component_sum_psi": component_sum, "closes": closes,
            "closure_note": ("component sum equals the engine total within row rounding" if closes else
                             "component sum does not equal the engine total; the budget is not consistent")}


# ---- pump limits ------------------------------------------------------------------------------------------
def pump_limits(values: Mapping[str, Any], spp_psi: Optional[float],
                total_flow_gpm: Optional[float] = None) -> List[Dict[str, Any]]:
    """Each pump against its ENTERED maximum pressure and rated horsepower (0 on the page = NOT ENTERED)."""
    pumps = list(values.get("pumps") or [])
    page_flows = [(_num(p.get("output_bbl_stk")) or 0.0) * (_num(p.get("spm")) or 0.0) * GAL_PER_BBL for p in pumps]
    page_total = sum(page_flows)
    rows = []
    for n, (pump, page_q) in enumerate(zip(pumps, page_flows, strict=True), 1):
        # a sensitivity flow is shared in the same proportion as the page flows (same SPM ratio)
        if total_flow_gpm is not None and page_total > 0:
            q = total_flow_gpm * page_q / page_total
        else:
            q = page_q
        max_p = _num(pump.get("max_pressure"))
        rated_hp = _num(pump.get("hp"))
        row: Dict[str, Any] = {"pump": str(pump.get("name") or f"Pump {n}"), "flow_gpm": q,
                               "max_pressure_psi": max_p if max_p and max_p > 0 else None,
                               "rated_hp": rated_hp if rated_hp and rated_hp > 0 else None}
        if spp_psi is None:
            row["pressure_status"], row["hp_status"] = "NOT ASSESSED", "NOT ASSESSED"
            row["required_hhp"], row["pressure_margin_psi"] = None, None
            rows.append(row)
            continue
        required = spp_psi * q / HHP_DIVISOR
        row["required_hhp"] = required
        if row["max_pressure_psi"] is None:
            row["pressure_status"], row["pressure_margin_psi"] = "NOT ENTERED", None
        else:
            row["pressure_margin_psi"] = row["max_pressure_psi"] - spp_psi
            row["pressure_status"] = "WITHIN" if row["pressure_margin_psi"] >= 0 else "EXCEEDED"
        if row["rated_hp"] is None:
            row["hp_status"] = "NOT ENTERED"
        else:
            row["hp_status"] = ("WITHIN RATED HP (mechanical efficiency not applied)" if required <= row["rated_hp"]
                                else "EXCEEDS RATED HP")
        rows.append(row)
    return rows


def _pump_summary(rows: Iterable[Mapping[str, Any]]) -> str:
    states = [r["pressure_status"] for r in rows]
    if not states:
        return "NO PUMPS"
    if "EXCEEDED" in states:
        return "EXCEEDED"
    if "NOT ASSESSED" in states:
        return "NOT ASSESSED"
    if "NOT ENTERED" in states:
        return "WITHIN (some limits not entered)" if "WITHIN" in states else "NOT ENTERED"
    return "WITHIN"


# ---- one operating point ----------------------------------------------------------------------------------
def _min_av(result) -> Optional[float]:
    values = [_num(v) for _n, v in result.annular_velocities]
    values = [v for v in values if v is not None]
    return min(values) if values else None


# ---- M370 hole cleaning ------------------------------------------------------------------------------------
CCI_MAX_INCLINATION_DEG = 35.0


def hole_cleaning(values: Mapping[str, Any], min_av_ft_min: Optional[float], mw_ppg: Optional[float]) -> Dict[str, Any]:
    """Carrying capacity index (Robinson and Morgan, 2004) — SCREENING, vertical / near-vertical hole only.

    CCI = K · AV · MW / 400 000 with K = 511^(1 − n) · (PV + YP) (equivalent cP), n = 3.32 log10(θ600 / θ300),
    AV the LOWEST annular velocity (ft/min), MW in ppg (the engine's MudProperties.mw_ppg, P8). CCI ≥ 1 GOOD, ≤ 0.5 POOR, between
    MARGINAL. Above 35° inclination the index does not apply (cuttings beds); un-entered rheology is never guessed.
    """
    out: Dict[str, Any] = {"method": "Robinson-Morgan carrying capacity index (SCREENING)", "cci": None, "n": None,
                           "k_equiv_cp": None, "status": "NOT ASSESSED", "reason": ""}
    well_type = str(values.get("well_type") or "").strip()
    max_inc = _num(values.get("max_inc"))
    if well_type != "Vertical":
        if max_inc is None or max_inc <= 0:
            out["reason"] = "maximum inclination not entered for a non-vertical well"
            return out
        if max_inc > CCI_MAX_INCLINATION_DEG:
            out.update(status="NOT APPLICABLE",
                       reason=f"maximum inclination {max_inc:g}° > {CCI_MAX_INCLINATION_DEG:g}°: the CCI is a "
                              f"vertical / near-vertical index; deviated hole cleaning is not modelled")
            return out
    t600, t300 = _num(values.get("t600")), _num(values.get("t300"))
    pv, yp = _num(values.get("pv")), _num(values.get("yp"))
    if t600 and t300 and t600 > 0 and t300 > 0:
        source = "Fann 600/300 readings"
    elif pv and pv > 0 and yp is not None and yp >= 0:
        t600, t300, source = 2.0 * pv + yp, pv + yp, "PV/YP (θ600 = 2PV + YP, θ300 = PV + YP)"
    else:
        out["reason"] = "rheology not entered (Fann 600/300 or PV and YP)"
        return out
    if t600 <= t300:
        out["reason"] = "θ600 must exceed θ300"
        return out
    mw_ppg = _num(mw_ppg)
    if mw_ppg is None or mw_ppg <= 0:
        out["reason"] = "mud density not entered"
        return out
    if min_av_ft_min is None or min_av_ft_min <= 0:
        out["reason"] = "no annular velocity (incomplete annular geometry)"
        return out
    n = 3.32 * math.log10(t600 / t300)
    k = 511.0 ** (1.0 - n) * t300                      # t300 = PV + YP for a Bingham fit
    cci = k * min_av_ft_min * mw_ppg / 400000.0
    status = "GOOD (CCI ≥ 1)" if cci >= 1.0 else "POOR (CCI ≤ 0.5)" if cci <= 0.5 else "MARGINAL (0.5 < CCI < 1)"
    out.update(cci=cci, n=n, k_equiv_cp=k, status=status, rheology_source=source, av_ft_min=min_av_ft_min,
               mw_ppg=mw_ppg, reason="lowest annular velocity used")
    return out


def _ecd_state(result) -> Tuple[Optional[float], str]:
    if result.ecd_at_bit_ppg is not None:
        return result.ecd_at_bit_ppg, "ASSESSED (complete annular geometry, P8 density divisor)"
    notes = [w for w in result.warnings if "ECD" in w]
    return None, "NOT ASSESSED: " + (notes[0] if notes else "the engine produced no ECD profile")


def _point(values, *, flow_gpm=None, nozzles=None) -> Dict[str, Any]:
    engine, result = _engine_run(values, flow_gpm=flow_gpm, nozzles=nozzles)
    if result.errors:
        return {"status": "NOT_ASSESSED", "reason": "; ".join(result.errors), "flow_gpm": flow_gpm,
                "nozzles": [list(n) for n in nozzles] if nozzles is not None else None}
    budget = pressure_budget(engine, result)
    ecd, ecd_note = _ecd_state(result)
    spp = budget["predicted_spp_psi"]
    pumps = pump_limits(values, spp, result.flow_rate_gpm if flow_gpm is not None else None)
    q = result.flow_rate_gpm
    regime = None
    if q is not None and result.critical_flow_rate_gpm is not None:
        regime = "ABOVE critical flow (deepest annulus)" if q > result.critical_flow_rate_gpm \
            else "AT/BELOW critical flow (deepest annulus)"
    return {"status": "OK", "reason": "", "flow_gpm": q, "spp_psi": spp,
            "surface_loss_psi": result.surface_loss_psi,
            "string_loss_psi": sum(v for _n, v in result.pipe_losses) if result.pipe_losses else None,
            "bit_loss_psi": result.bit_loss_psi,
            "annular_loss_psi": sum(v for _n, v in result.annulus_losses) if result.annulus_losses else None,
            "tfa_in2": result.tfa_in2, "bit_hhp": result.bit_hhp, "hsi": result.hsi,
            "jet_velocity_fps": result.jet_velocity_fps, "impact_force_lbf": result.impact_force_lbs,
            "percent_bit_hp": result.percent_bit_hp, "ecd_at_bit_ppg": ecd, "ecd_at_shoe_ppg": result.ecd_at_shoe_ppg,
            "ecd_state": ecd_note, "min_annular_velocity_ft_min": _min_av(result),
            "hole_cleaning": hole_cleaning(values, _min_av(result), getattr(engine.mud, "mw_ppg", None)),
            "critical_flow_gpm": result.critical_flow_rate_gpm, "regime_note": regime,
            "pump_status": _pump_summary(pumps), "pumps": pumps, "budget": budget,
            "nozzles": [list(n) for n in nozzles] if nozzles is not None else None,
            "warnings": list(result.warnings)}


# ---- plan vs actual ---------------------------------------------------------------------------------------
def plan_vs_actual(predicted_psi: Optional[float], observed_psi: Optional[float],
                   tolerance_psi: Optional[float]) -> Dict[str, Any]:
    observed, tolerance = _num(observed_psi), _num(tolerance_psi)
    if observed_psi is not None and (observed is None or observed <= 0):
        return {"status": "REFUSED", "reason": "observed standpipe pressure must be positive and finite",
                "difference_psi": None, "difference_pct": None}
    if tolerance_psi is not None and (tolerance is None or tolerance < 0):
        return {"status": "REFUSED", "reason": "declared tolerance must be finite and nonnegative",
                "difference_psi": None, "difference_pct": None}
    if observed is None:
        return {"status": "NOT ENTERED", "reason": "no observed standpipe pressure", "difference_psi": None,
                "difference_pct": None}
    if predicted_psi is None:
        return {"status": "NOT ASSESSED", "reason": "no predicted standpipe pressure", "difference_psi": None,
                "difference_pct": None}
    diff = observed - predicted_psi
    pct = diff / predicted_psi * 100.0 if predicted_psi else None
    if tolerance is None:
        return {"status": "NOT CLASSIFIED", "reason": "no tolerance declared; the difference is reported only",
                "difference_psi": diff, "difference_pct": pct}
    within = abs(diff) <= tolerance
    return {"status": "WITHIN DECLARED TOLERANCE" if within else "OUTSIDE DECLARED TOLERANCE",
            "reason": f"|observed − predicted| = {abs(diff):.1f} psi vs declared ±{tolerance:g} psi",
            "difference_psi": diff, "difference_pct": pct}


# ---- the workflow -----------------------------------------------------------------------------------------
def evaluate(values: Mapping[str, Any], *, flow_rates: Iterable[Any] = (), nozzle_sets: Iterable[Any] = (),
             observed_spp_psi: Optional[float] = None, spp_tolerance_psi: Optional[float] = None) -> Dict[str, Any]:
    """Base point, budget, pump limits, flow and nozzle sensitivity, plan vs actual — from frozen values."""
    frozen = freeze(values)
    rates = [float(q) for q in flow_rates]
    sets = [[(int(s), int(q)) for s, q in nset] for nset in nozzle_sets]
    if len(rates) > MAX_FLOW_POINTS or len(sets) > MAX_NOZZLE_SETS:
        raise WorkflowError("too many sensitivity points")
    if any(not math.isfinite(q) or q <= 0 for q in rates):
        raise WorkflowError("every flow rate must be positive and finite")
    options = {"flow_rates": rates, "nozzle_sets": [[list(n) for n in s] for s in sets],
               "observed_spp_psi": observed_spp_psi, "spp_tolerance_psi": spp_tolerance_psi}
    out: Dict[str, Any] = {"contract": CONTRACT, "method_id": METHOD_ID, "method_version": METHOD_VERSION,
                           "label": LABEL, "values_sha256": values_sha256(frozen),
                           "snapshot": {"values": frozen, "options": options}}
    if not frozen.get("confirmed"):
        out.update(status="NOT_ASSESSED", reason="the displayed hydraulics inputs are not confirmed", base=None,
                   flow_sweep=[], nozzle_sweep=[], plan_vs_actual=plan_vs_actual(None, None, None))
        return out
    base = _point(frozen)
    out["base"] = base
    if base["status"] != "OK":
        out.update(status="NOT_ASSESSED", reason=base["reason"], flow_sweep=[], nozzle_sweep=[],
                   plan_vs_actual=plan_vs_actual(None, observed_spp_psi, spp_tolerance_psi))
        return out
    out["flow_sweep"] = [_point(frozen, flow_gpm=q) for q in rates]
    out["nozzle_sweep"] = [_point(frozen, nozzles=s) for s in sets]
    out["plan_vs_actual"] = plan_vs_actual(base["spp_psi"], observed_spp_psi, spp_tolerance_psi)
    out.update(status="COMPUTED", reason="")
    return out


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    def show(value, digits=1, unit=""):
        return "—" if value is None else f"{value:.{digits}f}{(' ' + unit) if unit else ''}"

    lines = [result["label"], f"Inputs SHA-256 {result['values_sha256'][:16]}…"]
    if result["status"] != "COMPUTED":
        return lines + [f"Not assessed: {result['reason']}"]
    base = result["base"]
    lines.append(f"Predicted SPP {show(base['spp_psi'], 0, 'psi')} at {show(base['flow_gpm'], 0, 'gpm')}; "
                 f"pumps {base['pump_status']}")
    lines.append(f"ECD at bit {show(base['ecd_at_bit_ppg'], 2, 'ppg')} — {base['ecd_state']}")
    lines.append(f"Bit: TFA {show(base['tfa_in2'], 3, 'in²')}, ΔP {show(base['bit_loss_psi'], 0, 'psi')}, "
                 f"HSI {show(base['hsi'], 2, 'hp/in²')}, jet {show(base['jet_velocity_fps'], 0, 'ft/s')}, "
                 f"impact {show(base['impact_force_lbf'], 0, 'lbf')}")
    hc = base.get("hole_cleaning") or {}
    lines.append(f"Hole cleaning (CCI, SCREENING): {hc.get('status', 'NOT ASSESSED')}"
                 + (f" — CCI {hc['cci']:.2f}" if hc.get("cci") is not None else f" — {hc.get('reason', '')}"))
    pva = result["plan_vs_actual"]
    lines.append(f"Plan vs actual: {pva['status']} — {pva['reason']}")
    if not base["budget"]["closes"]:
        lines.append("Budget: " + base["budget"]["closure_note"])
    return lines


# ---- persistence ------------------------------------------------------------------------------------------
_POINT_FIELDS = (("spp_psi", "psi"), ("bit_loss_psi", "psi"), ("annular_loss_psi", "psi"), ("tfa_in2", "in²"),
                 ("hsi", "hp/in²"), ("jet_velocity_fps", "ft/s"), ("impact_force_lbf", "lbf"),
                 ("percent_bit_hp", "%"), ("ecd_at_bit_ppg", "ppg"), ("min_annular_velocity_ft_min", "ft/min"))
# M370: the carrying capacity index of the base point is stored with the case (None when not assessed)


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(inputs, results) of a saved workflow case: one builder for save and M328-style replay."""
    snap = result["snapshot"]
    inputs = {"snapshot": {"value": snap, "unit": "", "label": "frozen W13 hydraulics inputs and workflow options",
                           "source": "SNAPSHOT"},
              "values_sha256": {"value": result["values_sha256"], "unit": "", "label": "inputs SHA-256"},
              "observed_spp_psi": {"value": snap["options"]["observed_spp_psi"], "unit": "psi",
                                   "label": "observed standpipe pressure",
                                   "source": "OBSERVED" if snap["options"]["observed_spp_psi"] is not None
                                   else "NOT_ENTERED"},
              "spp_tolerance_psi": {"value": snap["options"]["spp_tolerance_psi"], "unit": "psi",
                                    "label": "declared plan-vs-actual tolerance",
                                    "source": "DECLARED" if snap["options"]["spp_tolerance_psi"] is not None
                                    else "NOT_DECLARED"}}
    results: Dict[str, Any] = {"status": {"value": result["status"], "label": result.get("reason") or LABEL}}
    base = result.get("base")
    if result["status"] == "COMPUTED" and base:
        for key, unit in _POINT_FIELDS:
            results[f"base_{key}"] = {"value": base[key], "unit": unit, "label": f"base {key}"}
        for row in base["budget"]["rows"]:
            results[f"budget_{row['group']}_psi"] = {"value": row["loss_psi"], "unit": "psi", "label": row["label"]}
        results["base_pump_status"] = {"value": base["pump_status"], "label": "pump limit summary"}
        results["base_ecd_state"] = {"value": base["ecd_state"], "label": "ECD state"}
        hc = base.get("hole_cleaning") or {}
        results["base_cci"] = {"value": hc.get("cci"), "unit": "", "label": "carrying capacity index (SCREENING)"}
        results["base_hole_cleaning_status"] = {"value": hc.get("status"), "label": hc.get("reason") or ""}
        for point in result["flow_sweep"]:
            tag = f"flow_{point['flow_gpm']:g}"
            results[f"{tag}_status"] = {"value": point["status"], "label": point["reason"] or "OK"}
            if point["status"] == "OK":
                for key, unit in _POINT_FIELDS:
                    results[f"{tag}_{key}"] = {"value": point[key], "unit": unit, "label": f"{tag} {key}"}
                results[f"{tag}_pump_status"] = {"value": point["pump_status"], "label": "pump limit summary"}
        for n, point in enumerate(result["nozzle_sweep"], 1):
            tag = f"nozzles_{n}"
            results[f"{tag}_set"] = {"value": nozzle_set_label(point["nozzles"] or []), "label": "nozzle set"}
            results[f"{tag}_status"] = {"value": point["status"], "label": point["reason"] or "OK"}
            if point["status"] == "OK":
                for key, unit in _POINT_FIELDS:
                    results[f"{tag}_{key}"] = {"value": point[key], "unit": unit, "label": f"{tag} {key}"}
        pva = result["plan_vs_actual"]
        results["pva_status"] = {"value": pva["status"], "label": pva["reason"]}
        results["pva_difference_psi"] = {"value": pva["difference_psi"], "unit": "psi", "label": "observed − predicted"}
    return inputs, results


def unit_of(key: str) -> str:
    """Unit of a stored result field (from the field-name suffix, never guessed)."""
    for field, unit in _POINT_FIELDS:
        if key.endswith(field):
            return unit
    if key.endswith("_psi"):
        return "psi"
    return ""


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != "COMPUTED":
        raise ValueError(f"Nothing to store: the workflow was not computed ({result.get('reason')}).")
    inputs, results = case_payload(result)
    base = result["base"]
    return cc.save_case(db, calculator=CALCULATOR, name=f"Hydraulics budget at {base['flow_gpm']:g} gpm",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; inputs SHA-256 {result['values_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    """Re-run a saved case from its frozen snapshot after the SHA-256 check (raises ValueError if it fails)."""
    snap = inputs["snapshot"]["value"] if isinstance(inputs.get("snapshot"), dict) else None
    if not isinstance(snap, dict) or not isinstance(snap.get("values"), dict):
        raise ValueError("the case holds no frozen hydraulics snapshot")
    stored_sha = inputs.get("values_sha256", {}).get("value")
    if values_sha256(snap["values"]) != stored_sha:
        raise IntegrityError("the frozen hydraulics inputs fail their SHA-256 check")
    options = snap.get("options") or {}
    result = evaluate(snap["values"], flow_rates=options.get("flow_rates") or [],
                      nozzle_sets=options.get("nozzle_sets") or [],
                      observed_spp_psi=options.get("observed_spp_psi"),
                      spp_tolerance_psi=options.get("spp_tolerance_psi"))
    return case_payload(result)[1]


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""
