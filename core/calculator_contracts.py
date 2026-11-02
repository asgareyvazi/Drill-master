"""Structured calculator contracts (M73).

A contract gives one calculator a stable identity and a data contract:

* ``stable_id`` and ``schema_version`` - what a stored case was captured with;
* ``method_id`` / ``method_version`` - the method that produced the results;
* field IDs with canonical units for inputs and results, bound to the
  calculator's form labels (the generic W13 capture keeps working);
* ``recalculate`` - the CURRENT method, reusing the existing engine.

A stored case is reproducible only when its method version is still available
here. Cases captured before M73 carry ``calculation_cases.W13_UNVERSIONED`` and stay NOT
REPRODUCIBLE: nothing records which method produced them. Stored results are
display text, so comparisons use the documented display rounding of each
field (half a unit in the last displayed decimal) as the tolerance.

M87: every W13 leaf calculator has a status in ``CALCULATOR_STATUS`` - a
CONTRACT (re-runnable) or NOT_SUPPORTED with the reason. M87 contracts bind
fields by the widget object name ``w13:<attribute>`` (labels can repeat, e.g.
two "Length" fields on Quick Calc), may carry non-widget state (``ExtraSpec``,
e.g. the nozzle program) and store the adapter's own full-precision results
(``source: contract``) next to the captured display text. Those are compared
with a relative tolerance of 1e-9; display text is never parsed for them.
Each adapter calls the same canonical engines as its W13 handler; parity
tests compare adapter and on-screen values.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

CONTRACT_REGISTRY_VERSION = "M87 calculator contracts v2"
OBJECT_PREFIX = "w13:"
STRUCTURED_REL_TOL = 1e-9


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    label: str            # the form label the generic capture records
    unit: str             # canonical unit of the stored value
    decimals: Optional[int] = None   # displayed decimals (results): tolerance = 0.5 * 10**-decimals
    attr: str = ""        # M87: W13 widget attribute; bound by object name "w13:<attr>"
    required: bool = True


@dataclass(frozen=True)
class ExtraSpec:
    """Non-widget calculator state stored with a case (e.g. the nozzle program)."""
    field_id: str
    attr: str             # attribute on the W13 tab
    unit: str
    description: str
    refresh: str = ""     # tab method to call after restoring the value


@dataclass(frozen=True)
class Contract:
    stable_id: str
    calculator: str       # the W13 finder path
    schema_version: int
    method_id: str
    method_version: str
    inputs: Tuple[FieldSpec, ...]
    results: Tuple[FieldSpec, ...]
    recalculate: Callable[[Dict[str, Any]], Dict[str, Optional[float]]] = field(compare=False)
    reference: str = ""
    extras: Tuple[ExtraSpec, ...] = ()
    structured: bool = False      # M87: results stored from the adapter at full precision
    limits: str = ""


def _quick_calc(values: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Pipe capacity/displacement; the same engine calls as W13 ``_vol_update_quick``."""
    from core.hydraulics_engine import AdvancedHydraulicsEngine as engine

    od, inner, length = values["od"], values["id"], values["length"]
    if not od > inner > 0:
        raise ValueError("OD must be greater than ID and ID greater than zero")
    capacity = engine.calc_pipe_capacity_bbl_ft(inner) * 3.28084
    displacement = engine.calc_pipe_displacement_bbl_ft(od, inner) * 3.28084
    return {"capacity": capacity, "displacement": displacement,
            "volume": capacity * length if length > 0 else None,
            "metal_volume": displacement * length if length > 0 else None}


QUICK_CALC_V1 = Contract(
    stable_id="w13.volume.quick_calc", calculator="Volume › Quick Calc", schema_version=1,
    method_id="w13.volume.pipe_capacity", method_version="M73 pipe capacity v1",
    inputs=(FieldSpec("od", "OD", "in"), FieldSpec("id", "ID", "in"), FieldSpec("length", "Length", "m")),
    results=(FieldSpec("capacity", "Capacity", "bbl/m", 5), FieldSpec("displacement", "Displacement", "bbl/m", 5),
             FieldSpec("volume", "Volume", "bbl", 2), FieldSpec("metal_volume", "Metal Volume", "bbl", 2)),
    recalculate=_quick_calc,
    reference="capacity = ID^2 / 1029.4 bbl/ft (oilfield units); displacement = (OD^2 - ID^2) / 1029.4 bbl/ft",
)



# ---- M87 contracts (structured adapter results) ---------------------------------------------
def _positive(values: Dict[str, Any], *names: str) -> None:
    for name in names:
        if not (values.get(name) is not None and values[name] > 0):
            raise ValueError(f"{name} must be greater than zero")


def _quick_calc_v2(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Pipe and annulus parts of Quick Calc (W13 ``_vol_update_quick`` / ``_vol_update_annular``)."""
    from core.hydraulics_engine import AdvancedHydraulicsEngine as engine

    out: Dict[str, Optional[float]] = dict.fromkeys(
        ("capacity", "displacement", "volume", "metal_volume", "annular_capacity", "annular_volume"))
    od, inner, length = values["od"], values["id"], values["length"]
    if od > inner > 0:
        out["capacity"] = engine.calc_pipe_capacity_bbl_ft(inner) * 3.28084
        out["displacement"] = engine.calc_pipe_displacement_bbl_ft(od, inner) * 3.28084
        if length > 0:
            out["volume"], out["metal_volume"] = out["capacity"] * length, out["displacement"] * length
    hole, pipe, ann_length = values["hole"], values["pipe_od"], values["annular_length"]
    if hole > pipe > 0:
        out["annular_capacity"] = engine.calc_annular_capacity_bbl_ft(hole, pipe) * 3.28084
        if ann_length > 0:
            out["annular_volume"] = out["annular_capacity"] * ann_length
    if all(v is None for v in out.values()):
        raise ValueError("neither OD > ID > 0 nor hole > pipe OD > 0")
    return out


QUICK_CALC = Contract(
    stable_id="w13.volume.quick_calc", calculator="Volume › Quick Calc", schema_version=2,
    method_id="w13.volume.quick_calc", method_version="M87 volume quick calc v2",
    inputs=(FieldSpec("od", "OD", "in", attr="v_od"), FieldSpec("id", "ID", "in", attr="v_id"),
            FieldSpec("length", "Length", "m", attr="v_length"),
            FieldSpec("hole", "Hole/CSG ID", "in", attr="v_hole"),
            FieldSpec("pipe_od", "Pipe OD", "in", attr="v_pipe_od"),
            FieldSpec("annular_length", "Length", "m", attr="v_ann_len")),
    results=(FieldSpec("capacity", "Capacity", "bbl/m"), FieldSpec("displacement", "Displacement", "bbl/m"),
             FieldSpec("volume", "Volume", "bbl"), FieldSpec("metal_volume", "Metal Volume", "bbl"),
             FieldSpec("annular_capacity", "Ann. Capacity", "bbl/m"), FieldSpec("annular_volume", "Ann. Volume", "bbl")),
    recalculate=_quick_calc_v2, structured=True,
    reference="capacity = ID^2/1029.4, displacement = (OD^2-ID^2)/1029.4, annulus = (Dh^2-Dp^2)/1029.4 bbl/ft; x3.28084 per m",
    limits="Nominal geometry; no tool joints, no washout.",
)


def _bit_page(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Bit hydraulics, MSE (Teale) and cost per foot (W13 ``_bit_calculate`` / ``_mse_calculate`` /
    ``_bit_cost_per_foot``). Each part is computed only from its own inputs; a part whose inputs are
    not usable stays None (never zero)."""
    import math as _math

    from core.engineering.core import BitEngine
    from core.engineering.engines.bit_performance import BitPerformanceEngine
    from core.engineering.engines.mse import MSEEngine
    from core.hydraulics_engine import AdvancedHydraulicsEngine

    out: Dict[str, Optional[float]] = dict.fromkeys(
        ("bit_dp", "bit_hhp", "hsi", "jet_velocity", "impact_force", "tfa", "mse", "cost_per_ft"))
    gpm, mw_pcf, bit_od = values["gpm"], values["mw"], values["bit_od"]
    nozzles = values.get("nozzles") or []
    sizes = []
    valid_nozzles = bool(nozzles)
    for nozzle in nozzles:
        size, qty = (nozzle or {}).get("size"), (nozzle or {}).get("qty")
        if (not isinstance(size, (int, float)) or isinstance(size, bool) or not _math.isfinite(size) or size <= 0
                or not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0):
            valid_nozzles = False
            break
        sizes.extend([size] * qty)
    if gpm > 0 and mw_pcf > 0 and bit_od > 0 and valid_nozzles:
        tfa = BitEngine.calculate_tfa(sizes)
        bh = AdvancedHydraulicsEngine.calc_bit_hydraulics(gpm, mw_pcf / 7.48052, tfa, bit_od)
        out.update(bit_dp=bh["bit_pressure_drop_psi"], bit_hhp=bh["bit_hhp"], hsi=bh["hsi"],
                   jet_velocity=bh["jet_velocity_fps"], impact_force=bh["impact_force_lbs"], tfa=tfa)
    mse = MSEEngine.calculate(wob_lbf=values["wob"] * 1000.0, rpm=values["rpm"], torque_ft_lbf=values["torque"],
                              rop_ft_hr=values["rop"], bit_diameter_in=bit_od)
    if mse.success:
        out["mse"] = mse.value
    cost = BitPerformanceEngine.cost_per_foot(rig_cost_per_day=values["rig_day"], trip_hours=values["trip_h"],
                                              bit_cost=values["bit_cost"], footage=values["footage"],
                                              rotating_hours=values["rot_h"])
    if cost.success:
        out["cost_per_ft"] = cost.values["cost_per_ft"]
    if all(v is None for v in out.values()):
        raise ValueError("no part of the page can be computed from these inputs")
    return out


BIT_HYDRAULICS = Contract(
    stable_id="w13.bit.hydraulics_page", calculator="Bit Hydraulics › Bit Hydraulics", schema_version=1,
    method_id="w13.bit.hydraulics_mse_cost", method_version="M87 bit hydraulics / MSE / cost per foot v1",
    inputs=(FieldSpec("gpm", "Flow Rate", "gpm", attr="bit_gpm"), FieldSpec("mw", "Mud Weight", "pcf", attr="bit_mw"),
            FieldSpec("bit_od", "Bit Size", "in", attr="bit_od"), FieldSpec("wob", "WOB", "klbf", attr="bit_wob"),
            FieldSpec("rpm", "RPM", "rpm", attr="bit_rpm"), FieldSpec("torque", "Torque", "ft-lbf", attr="bit_tq"),
            FieldSpec("rop", "ROP", "ft/hr", attr="bit_rop"),
            FieldSpec("rig_day", "Rig cost", "currency/day (unit as labelled; currency not recorded)",
                      attr="bit_rig_day"),
            FieldSpec("trip_h", "Trip time", "hr", attr="bit_trip_h"),
            FieldSpec("rot_h", "Rotating time", "hr", attr="bit_rot_h"),
            FieldSpec("bit_cost", "Bit cost", "currency (not recorded)", attr="bit_cost"),
            FieldSpec("footage", "Footage", "ft", attr="bit_footage")),
    results=(FieldSpec("bit_dp", "Bit ΔP", "psi"), FieldSpec("bit_hhp", "Bit HHP", "hp"),
             FieldSpec("hsi", "HSI", "hp/in²"), FieldSpec("jet_velocity", "Jet Velocity", "ft/s"),
             FieldSpec("impact_force", "Impact Force", "lbf"), FieldSpec("tfa", "TFA", "in²"),
             FieldSpec("mse", "MSE (Teale)", "psi"),
             FieldSpec("cost_per_ft", "Cost per foot", "currency/ft (not recorded)")),
    recalculate=_bit_page, structured=True,
    extras=(ExtraSpec("nozzles", "bit_nozzles", "1/32 in x count", "Nozzle program", refresh="_bit_refresh_nozzles"),),
    reference="Bit ΔP = MW·Q²/(10858·TFA²) (12032·Cd², Cd 0.95); TFA = Σ π/4·(d/32)²; MSE Teale (1965); "
              "cost/ft from BitPerformanceEngine.cost_per_foot",
    limits="Nozzle program required for hydraulics; currency is not recorded (owner-gated money model).",
)


def _tfa(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core.hydraulics_engine import AdvancedHydraulicsEngine

    _positive(values, "gpm", "mw", "bit_dp")
    return {"tfa": AdvancedHydraulicsEngine.calc_tfa_from_pressure_drop(values["gpm"], values["mw"], values["bit_dp"])}


TFA = Contract(
    stable_id="w13.bit.tfa_from_dp", calculator="Bit Hydraulics › TFA Calculator", schema_version=1,
    method_id="w13.bit.tfa_from_dp", method_version="M87 TFA from bit pressure drop v1",
    inputs=(FieldSpec("gpm", "Flow Rate", "gpm", attr="tfa_gpm"), FieldSpec("mw", "Mud Weight", "ppg", attr="tfa_mw"),
            FieldSpec("bit_dp", "Bit ΔP", "psi", attr="tfa_dp")),
    results=(FieldSpec("tfa", "Required TFA", "in²"),),
    recalculate=_tfa, structured=True, reference="TFA = sqrt(MW·Q²/(10858·ΔP)) (inverse of the bit ΔP relation, Cd 0.95)",
)


def _hydrostatic(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core.engineering.engines.well_control import WellControlEngine

    _positive(values, "mw", "tvd")
    r = WellControlEngine.formation_pressure(mw_ppg=values["mw"] / 7.48, tvd_ft=values["tvd"] * 3.28084,
                                             sidpp_psi=values["sidpp"])
    if not r.success:
        raise ValueError(r.error)
    v = r.values
    return {"hydrostatic": v["hydrostatic_psi"], "formation_pressure": v["formation_pressure_psi"],
            "gradient": v["pressure_gradient_psi_ft"], "emw": v["equivalent_mw_ppg"]}


HYDROSTATIC = Contract(
    stable_id="w13.well_control.hydrostatic_fp", calculator="Well Control › HP  FP", schema_version=1,
    method_id="w13.well_control.hydrostatic_fp", method_version="M87 hydrostatic and formation pressure v1",
    inputs=(FieldSpec("mw", "Mud Weight", "pcf", attr="hp_mw"), FieldSpec("tvd", "TVD", "m", attr="hp_tvd"),
            FieldSpec("sidpp", "SIDPP", "psi", attr="hp_sidpp")),
    results=(FieldSpec("hydrostatic", "Hydrostatic Pressure", "psi"),
             FieldSpec("formation_pressure", "Formation Pressure", "psi"),
             FieldSpec("gradient", "Pressure Gradient", "psi/ft"), FieldSpec("emw", "Equivalent MW", "ppg")),
    recalculate=_hydrostatic, structured=True,
    reference="P = 0.052·MW(ppg)·TVD(ft); PF = P + SIDPP (pcf→ppg uses 7.48 as the W13 handler does)",
)


def _cement(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core.engineering.engines.cement import CementEngine

    opt = {k: (values[k] or None) for k in ("yield", "density", "spacer_len", "spacer_mw", "lead_len", "lead_mw",
                                           "tail_len", "tail_mw", "shoe_tvd", "pump", "pore")}
    r = CementEngine.job_volumes(
        hole_size_in=values["hole"], casing_od_in=values["casing_od"], open_hole_length_ft=values["length"],
        excess_pct=values["excess"], casing_id_in=values["casing_id"] or None, shoe_track_ft=values["shoe_track"],
        slurry_density_ppg=opt["density"], yield_ft3_sk=opt["yield"], spacer_length_ft=opt["spacer_len"],
        spacer_density_ppg=opt["spacer_mw"], lead_length_ft=opt["lead_len"], lead_density_ppg=opt["lead_mw"],
        tail_length_ft=opt["tail_len"], tail_density_ppg=opt["tail_mw"], tvd_column_ft=opt["shoe_tvd"],
        shoe_tvd_ft=opt["shoe_tvd"], tail_tvd_ft=opt["shoe_tvd"] if opt["tail_mw"] else None,
        pump_rate_bbl_min=opt["pump"], pore_emw_ppg=opt["pore"])
    if not r.success:
        raise ValueError(r.error)
    v = r.values
    return {"annular_volume": v["annular_volume_bbl"], "annular_with_excess": v["annular_with_excess_bbl"],
            "shoe_track_volume": v["shoe_track_volume_bbl"], "spacer_volume": v["spacer_volume_bbl"],
            "slurry_volume": v["slurry_volume_bbl"], "sacks": v.get("sacks"),
            "displacement_volume": v.get("displacement_volume_bbl"), "total_pump": v["total_pump_bbl"],
            "pump_time": v.get("pump_time_min"), "hydrostatic": v.get("hydrostatic_psi")}


_CMT = (("hole", "Hole Size", "in", "cmt_hole"), ("casing_od", "Casing OD", "in", "cmt_csg"),
        ("length", "Cement Length", "ft", "cmt_len"), ("excess", "Excess %", "%", "cmt_excess"),
        ("casing_id", "Casing ID", "in", "cmt_csg_id"), ("shoe_track", "Shoe Track", "ft", "cmt_shoe_track"),
        ("yield", "Slurry yield (0=omit sacks)", "ft³/sk", "cmt_yield"), ("density", "Slurry density", "ppg", "cmt_dens"),
        ("spacer_len", "Spacer length", "ft", "cmt_spacer_len"), ("spacer_mw", "Spacer MW", "ppg", "cmt_spacer_mw"),
        ("lead_len", "Lead length", "ft", "cmt_lead_len"), ("lead_mw", "Lead MW", "ppg", "cmt_lead_mw"),
        ("tail_len", "Tail length", "ft", "cmt_tail_len"), ("tail_mw", "Tail MW", "ppg", "cmt_tail_mw"),
        ("shoe_tvd", "Shoe TVD (hydrostatic)", "ft", "cmt_shoe_tvd"), ("pump", "Pump rate", "bbl/min", "cmt_pump"),
        ("pore", "Pore EMW", "ppg", "cmt_pore"))

CEMENT_VOLUME = Contract(
    stable_id="w13.cement.job_volumes", calculator="CSG/CMT › Cement Volume", schema_version=1,
    method_id="w13.cement.job_volumes", method_version="M87 cement job volume worksheet v1",
    inputs=tuple(FieldSpec(fid, label, unit, attr=attr) for fid, label, unit, attr in _CMT),
    results=(FieldSpec("annular_volume", "Annulus", "bbl"), FieldSpec("annular_with_excess", "With excess", "bbl"),
             FieldSpec("shoe_track_volume", "Shoe track", "bbl"), FieldSpec("spacer_volume", "Spacer", "bbl"),
             FieldSpec("slurry_volume", "Slurry", "bbl"), FieldSpec("sacks", "Sacks", "sk"),
             FieldSpec("displacement_volume", "Displacement", "bbl"), FieldSpec("total_pump", "Total pump", "bbl"),
             FieldSpec("pump_time", "Pump time", "min"), FieldSpec("hydrostatic", "Hydrostatic", "psi")),
    recalculate=_cement, structured=True,
    reference="Annulus (Dh²−Dp²)/1029.4 bbl/ft; CementEngine.job_volumes",
    limits="WORKSHEET - not laboratory cement design; 0 in an optional field means omitted.",
)


def _owr(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core.engineering.extended import MudEngineering

    try:
        r = MudEngineering.oil_water_ratio(values["oil"], values["water"])
    except Exception as exc:  # the engine raises its own error type for invalid fractions
        raise ValueError(str(exc)) from exc
    return {"oil_ratio": float(r["oil_percent"]), "water_ratio": float(r["water_percent"])}


OWR = Contract(
    stable_id="w13.mud.owr", calculator="Mud › OWR", schema_version=1,
    method_id="w13.mud.owr", method_version="M87 oil-water ratio v1",
    inputs=(FieldSpec("oil", "Oil %", "% retort", attr="mud_oil"), FieldSpec("water", "Water %", "% retort",
                                                                            attr="mud_water")),
    results=(FieldSpec("oil_ratio", "Oil ratio", "%"), FieldSpec("water_ratio", "Water ratio", "%")),
    recalculate=_owr, structured=True, reference="OWR = oil/(oil+water) : water/(oil+water) x 100",
)


def _build_turn(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core.engineering.core import TrajectoryEngine
    from core.well_plan_designer import dogleg_deg

    _positive(values, "interval")
    md = values["interval"]
    return {"build_rate": TrajectoryEngine.calculate_build_rate(values["inc1"], values["inc2"], md),
            "turn_rate": TrajectoryEngine.calculate_turn_rate(values["azi1"], values["azi2"], md),
            "dls": dogleg_deg(values["inc1"], values["azi1"], values["inc2"], values["azi2"]) * 30.0 / md}


BUILD_TURN = Contract(
    stable_id="w13.directional.build_turn_dls", calculator="Directional › Build/Turn Rate", schema_version=1,
    method_id="w13.directional.build_turn_dls", method_version="M87 build/turn rate and dogleg severity v1",
    inputs=(FieldSpec("inc1", "Initial Inc", "deg", attr="dd_init_inc"),
            FieldSpec("inc2", "Final Inc", "deg", attr="dd_final_inc"),
            FieldSpec("azi1", "Initial Azi", "deg", attr="dd_init_azi"),
            FieldSpec("azi2", "Final Azi", "deg", attr="dd_final_azi"),
            FieldSpec("interval", "MD Interval", "m", attr="dd_interval")),
    results=(FieldSpec("build_rate", "Build Rate", "deg/30 m"), FieldSpec("turn_rate", "Turn Rate", "deg/30 m"),
             FieldSpec("dls", "Dogleg severity", "deg/30 m")),
    recalculate=_build_turn, structured=True,
    reference="DLS from the dogleg angle cos(b) = cos I1 cos I2 + sin I1 sin I2 cos(dA) (minimum curvature)",
)

CONTRACTS: Dict[str, Contract] = {c.calculator: c for c in (QUICK_CALC, BIT_HYDRAULICS, TFA, HYDROSTATIC,
                                                            CEMENT_VOLUME, OWR, BUILD_TURN)}
LEGACY_CONTRACTS: Tuple[Contract, ...] = (QUICK_CALC_V1,)
# method_id -> versions this build can still run. A version removed from here
# makes its stored cases NOT REPRODUCIBLE (never silently re-run with another method).
AVAILABLE_METHODS: Dict[str, Tuple[str, ...]] = {c.method_id: (c.method_version,) for c in CONTRACTS.values()}
AVAILABLE_METHODS[QUICK_CALC_V1.method_id] = (QUICK_CALC_V1.method_version,)

_TABLE = "depends on table/dialog state the generic case capture does not record"
# Every W13 leaf calculator (finder path) and whether it has a re-runnable contract.
NOT_SUPPORTED: Dict[str, str] = {
    "Volume › Well Volumes": f"string and hole sections {_TABLE}",
    "Hydraulics": f"drill-string and annulus sections {_TABLE}; saved hydraulics runs are verified in Calc History",
    "Bit Hydraulics › Nozzle Optimization": "two-point pump curve optimisation is not yet contracted",
    "Weight": f"drill-string components {_TABLE}",
    "Stuck Pipe": "free-point and stretch results are not yet contracted",
    "Mud › Weight/Dilution/Mix": "three calculators share one page; not yet contracted",
    "Mud › Volume Balance": "not yet contracted",
    "Mud › Rheology": "rheology runs are verified in Calc History (mud engine snapshots); no page contract",
    "Mud › Mud Lab": "several independent lab calculators on one page; not yet contracted",
    "CSG/CMT › Casing Strength": "casing runs are verified in Calc History (casing engine snapshots); no page contract",
    "CSG/CMT › Balanced Plug": "not yet contracted",
    "CSG/CMT › Buoyancy": "not yet contracted",
    "Well Control › Kill Sheet": "TRAINING AID (owner decision pending); not re-runnable as a case",
    "Well Control › Choke Schedule": "schedule table output; not yet contracted",
    "Well Control › Kick Tolerance": "not yet contracted",
    "Well Control › Pore Press  FG": "not yet contracted",
    "Directional › Multi-Survey": f"survey table {_TABLE}; use Survey revisions",
    "Directional › Anti-Collision": f"offset trajectories {_TABLE}; SCREENING only",
    "Fishing": "several independent sizing calculators on one page; not yet contracted",
    "DP Database": "reference catalogue, not a calculator",
}


def calculator_status(calculator: Optional[str]) -> Tuple[str, str]:
    """(CONTRACT | NOT_SUPPORTED | UNKNOWN, explanation) for a W13 finder path."""
    contract = contract_for(calculator)
    if contract is not None:
        return "CONTRACT", f"{contract.stable_id} — {contract.method_version}; cases are re-runnable"
    reason = NOT_SUPPORTED.get(str(calculator or ""))
    if reason is not None:
        return "NOT_SUPPORTED", f"{reason}. Cases are stored as captured and are NOT REPRODUCIBLE"
    return "UNKNOWN", "no contract status recorded for this calculator; cases are NOT REPRODUCIBLE"


def contract_for(calculator: Optional[str]) -> Optional[Contract]:
    return CONTRACTS.get(str(calculator or ""))


def _by_method(method_id: str, method_version: str = "") -> Optional[Contract]:
    candidates = [c for c in (*CONTRACTS.values(), *LEGACY_CONTRACTS) if c.method_id == method_id]
    exact = [c for c in candidates if c.method_version == method_version]
    return (exact or candidates or [None])[0]


def _norm(label: str) -> str:
    return re.sub(r"[\s:]+$", "", str(label or "")).strip().lower()


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", str(value or ""))       # thousands separators
    match = re.match(r"\s*\$?\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", text)
    return float(match.group(1)) if match else None


def annotate(contract: Contract, inputs: Dict[str, Any],
             results: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Add ``field_id``/``unit`` to captured entries.

    M87 fields (``attr``) bind by the widget object name; older fields by
    their label, and a label that appears more than once is ambiguous and
    reported missing rather than guessed. Returns copies plus the contract
    fields that were not found (the case is still stored; never invented).
    Structured contracts bind inputs only; their results come from
    ``structured_results``.
    """
    def bind(entries: Dict[str, Any], specs: Tuple[FieldSpec, ...]) -> Tuple[Dict[str, Any], List[str]]:
        out = {key: dict(value) if isinstance(value, dict) else {"value": value} for key, value in entries.items()}
        by_object = {v.get("object"): key for key, v in out.items() if v.get("object")}
        labels: Dict[str, List[str]] = {}
        for key, v in out.items():
            labels.setdefault(_norm(v.get("label", "")), []).append(key)
        missing = []
        for spec in specs:
            if spec.attr:
                key = by_object.get(OBJECT_PREFIX + spec.attr)
            else:
                keys = labels.get(_norm(spec.label), [])
                key = keys[0] if len(keys) == 1 else None
            if key is None:
                if spec.required:
                    missing.append(spec.field_id)
                continue
            out[key].update(field_id=spec.field_id, unit=spec.unit)
        return out, missing

    new_inputs, missing_inputs = bind(inputs, contract.inputs)
    if contract.structured:
        return new_inputs, {key: dict(v) if isinstance(v, dict) else {"value": v} for key, v in results.items()}, \
            missing_inputs
    new_results, _missing_results = bind(results, contract.results)   # results may legitimately be blank
    return new_inputs, new_results, missing_inputs


def extra_entries(contract: Contract, owner: Any) -> Dict[str, Any]:
    """Case entries for the contract's non-widget state, read from the W13 tab."""
    import copy

    out = {}
    for spec in contract.extras:
        value = copy.deepcopy(getattr(owner, spec.attr, None))
        out[f"extra:{spec.field_id}"] = {"label": spec.description, "value": value, "field_id": spec.field_id,
                                         "unit": spec.unit, "extra": True}
    return out


def input_values(contract: Contract, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Numeric inputs by field id (plus extras as stored); raises ValueError when one is unusable."""
    stored = _field_values(inputs)
    values: Dict[str, Any] = {}
    for spec in contract.inputs:
        number = _number(stored.get(spec.field_id))
        if number is None and spec.required:
            raise ValueError(f"input {spec.field_id} is missing or not a number")
        values[spec.field_id] = number
    for spec in contract.extras:
        values[spec.field_id] = stored.get(spec.field_id)
    return values


def structured_results(contract: Contract, values: Dict[str, Any]) -> Dict[str, Any]:
    """The adapter's results at full precision as case entries (``source: contract``)."""
    current = contract.recalculate(values)
    return {f"contract:{spec.field_id}": {"label": spec.label, "field_id": spec.field_id, "unit": spec.unit,
                                          "value": current.get(spec.field_id), "source": "contract"}
            for spec in contract.results}


def _field_values(entries: Dict[str, Any]) -> Dict[str, Any]:
    return {v["field_id"]: v.get("value") for v in entries.values() if isinstance(v, dict) and v.get("field_id")}


def reproducibility(method_id: str, method_version: str) -> Tuple[str, str]:
    from core.calculation_cases import W13_UNVERSIONED

    if not method_version or method_version == W13_UNVERSIONED:
        return "NOT REPRODUCIBLE", "captured without a method version (before M73)"
    if _by_method(method_id, method_version) is None:
        return "NOT REPRODUCIBLE", f"no contract for method {method_id!r}"
    if method_version not in AVAILABLE_METHODS.get(method_id, ()):
        return "NOT REPRODUCIBLE", f"method version {method_version!r} is no longer available"
    return "REPRODUCIBLE", "contract method available"


def verify_case(method_id: str, method_version: str, inputs: Dict[str, Any],
                results: Dict[str, Any]) -> Dict[str, Any]:
    """Re-run a contract case with the current method and classify it.

    MATCH / DIFFERENT per the display-rounding tolerance (a result the case
    never stored is listed in ``not_compared``); NOT_REPRODUCIBLE when
    the method or version is unavailable; UNREADABLE when inputs are missing.
    """
    status, why = reproducibility(method_id, method_version)
    blank = {"method_matches": None, "current_method": "", "values": {}, "differences": [], "not_compared": []}
    if status != "REPRODUCIBLE":
        return {**blank, "status": "NOT_REPRODUCIBLE", "detail": f"{why}; reopen it in its calculator instead."}
    contract = _by_method(method_id, method_version)
    if not any(spec.attr for spec in contract.inputs):
        labels = [_norm(v.get("label", "")) for v in inputs.values() if isinstance(v, dict)]
        ambiguous = [spec.field_id for spec in contract.inputs if labels.count(_norm(spec.label)) > 1]
        if ambiguous:
            return {**blank, "status": "UNREADABLE",
                    "detail": f"inputs bound by an ambiguous label ({', '.join(ambiguous)}); captured before M87, "
                              "the stored binding cannot be trusted"}
    try:
        values = input_values(contract, inputs)
    except ValueError as exc:
        return {**blank, "status": "UNREADABLE", "detail": str(exc)}
    try:
        current = contract.recalculate(values)
    except ValueError as exc:
        return {**blank, "status": "UNREADABLE", "detail": f"inputs rejected by the method: {exc}"}
    stored = _field_values(results)
    differences, not_compared = [], []
    for spec in contract.results:
        new, old = current.get(spec.field_id), _number(stored.get(spec.field_id))
        if new is None and old is None:
            continue
        if old is None and not contract.structured:   # never stored with the case: named, not judged
            not_compared.append(spec.field_id)
            continue
        if contract.structured:
            tolerance = max(STRUCTURED_REL_TOL * abs(old if old is not None else 0.0), 1e-12)
        else:
            tolerance = 0.5 * 10 ** -(spec.decimals if spec.decimals is not None else 9)
        if new is None or old is None or abs(new - old) > tolerance:
            differences.append({"field_id": spec.field_id, "unit": spec.unit, "stored": old, "current": new,
                                "tolerance": tolerance})
    basis = "relative tolerance 1e-9" if contract.structured else "display rounding"
    return {"status": "DIFFERENT" if differences else "MATCH", "method_matches": True,
            "current_method": f"{contract.method_id} {contract.method_version}",
            "detail": (f"{len(differences)} result(s) outside {basis}" if differences
                       else f"stored results within {basis}")
                      + (f"; not stored, not compared: {', '.join(not_compared)}" if not_compared else ""),
            "values": {k: v for k, v in current.items() if v is not None}, "differences": differences,
            "not_compared": not_compared}
