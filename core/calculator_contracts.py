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

M107: eleven more contracts (18 of the 27 leaf calculators); the other nine are
NOT_SUPPORTED with the exact reason (which table or state is not captured, or
the owner gate). Fields may be text (a list entry) or bool (a check / radio
button) as well as numbers. Kill-sheet-style inputs keep "Not recorded" (-1) as
None, never zero. The weight-up sack count was corrected (D26) in the engine.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

CONTRACT_REGISTRY_VERSION = "M129 calculator contracts v7"
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
    kind: str = "number"  # M107: "number", "text" (combo entry) or "bool" (check / radio button)


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
    # M126: per-component rows (e.g. each string / annulus interval) stored with the case and compared on re-run
    components: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = field(default=None, compare=False)


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
    limits="WORKSHEET — NOT A CEMENT DESIGN APPROVAL: not laboratory cement design; yield and sacks are entered, "
           "never inferred from a class or grade; 0 in an optional field means omitted.",
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

# ---- M107 contracts (the remaining single-form W13 calculators) -----------------------------
# Kill-sheet-style inputs (``_make_wc_spin``) store -1 for "Not recorded"; the W13 handler reads
# them through ``_wc_value`` and the adapters do the same, so an unrecorded input is None, never 0.
WC_NOT_RECORDED = -1.0
STEEL_DENSITY_PCF = 490.0          # W13 buoyancy card default (``calc_buoyancy_factor_result``)
# Weight-up additives offered by W13 (pcf). M107: barite was listed as "1470 pcf" - the ppg field
# constant 42 x 35 used as a density (D26); 4.20 SG x 62.428 lb/ft3 = 262.2 pcf.
WEIGHT_UP_ADDITIVES: Tuple[Tuple[str, float], ...] = (("Barite (4.20 SG, 262.2 pcf)", 262.2),
                                                      ("Calcium Carbonate (170 pcf)", 170.0),
                                                      ("Hematite (320 pcf)", 320.0))


def additive_density_pcf(text: Any) -> Optional[float]:
    """Density of a W13 weight-up additive by its exact list text; unknown text is None (never a default)."""
    return dict(WEIGHT_UP_ADDITIVES).get(str(text or ""))


def _recorded(value: Any) -> Optional[float]:
    """A kill-sheet-style spin value, or None when it holds the "Not recorded" sentinel."""
    if value is None or value <= WC_NOT_RECORDED:
        return None
    return float(value)


def _or_none(value: Any) -> Optional[float]:
    """W13 "0 = omit" fields."""
    return float(value) if value else None


def _all_none(out: Dict[str, Optional[float]], what: str) -> Dict[str, Optional[float]]:
    if all(v is None for v in out.values()):
        raise ValueError(f"no part of the page can be computed from these inputs ({what})")
    return out


def _buoyancy(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Buoyancy factor and casing landing load (W13 ``_csg_calc_landing``)."""
    from core.engineering.engines.torque_drag import TorqueDragEngine
    from core.engineering.result import EngineeringError
    from core.unit_manager import UnitManager

    mw = _recorded(values["mw"])
    if mw is None:
        raise ValueError("mud weight not recorded")
    try:
        bf = round(TorqueDragEngine.buoyancy_factor(UnitManager.convert(mw, "density", "pcf", "ppg"),
                                                    UnitManager.convert(STEEL_DENSITY_PCF, "density", "pcf", "ppg")), 4)
    except EngineeringError as exc:
        raise ValueError(str(exc)) from exc
    out: Dict[str, Optional[float]] = {"buoyancy_factor": bf, "air_weight": None, "buoyed_weight": None,
                                       "hook_load": None}
    load = TorqueDragEngine.casing_landing_load(_recorded(values["casing_weight"]), _recorded(values["casing_length"]),
                                                bf, _recorded(values["friction"]))
    if load.success:
        v = load.values
        out.update(air_weight=v["total_air_weight_lbs"], buoyed_weight=v["buoyed_weight_lbs"],
                   hook_load=v["hook_load_lbs"])
    return out


BUOYANCY = Contract(
    stable_id="w13.casing.buoyancy_landing", calculator="CSG/CMT › Buoyancy", schema_version=1,
    method_id="w13.casing.buoyancy_landing", method_version="M107 buoyancy factor and casing landing load v1",
    inputs=(FieldSpec("mw", "Mud Weight", "pcf (-1 = not recorded)", attr="bf_mw"),
            FieldSpec("casing_weight", "Casing Weight", "ppf (-1 = not recorded)", attr="bf_csg_wt"),
            FieldSpec("casing_length", "Casing Length", "ft (-1 = not recorded)", attr="bf_csg_len"),
            FieldSpec("friction", "Friction Factor", "- (-1 = not recorded)", attr="bf_friction")),
    results=(FieldSpec("buoyancy_factor", "Buoyancy factor", "-"), FieldSpec("air_weight", "Air weight", "lbf"),
             FieldSpec("buoyed_weight", "Buoyant weight", "lbf"), FieldSpec("hook_load", "Hook load", "lbf")),
    recalculate=_buoyancy, structured=True,
    reference="BF = 1 - mud density / steel density (490 pcf, rounded to 4 decimals as on screen); "
              "TorqueDragEngine.casing_landing_load",
    limits="SCREENING: density ratio only, no pressure-area term.",
)


def _balanced_plug(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Balanced cement plug volumetrics (W13 ``_plug_calculate``)."""
    from core.engineering.engines.cement import CementEngine

    r = CementEngine.balanced_plug(
        hole_size_in=values["hole"], pipe_od_in=values["pipe_od"], pipe_id_in=values["pipe_id"],
        plug_length_ft=values["length"], plug_bottom_md_ft=values["bottom"], excess_pct=values["excess"],
        spacer_ahead_bbl=values["spacer"], underdisplacement_bbl=values["under"],
        slurry_yield_ft3_sk=values["yield"] if values["yield"] and values["yield"] > 0 else None)
    if not r.success:
        raise ValueError(r.error or r.validation_status)
    v = r.values
    return {"slurry_volume": v["slurry_volume_bbl"], "sacks": v.get("sacks"),
            "column_height": v["column_height_pipe_in_ft"], "top_pipe_in": v["top_pipe_in_md_ft"],
            "top_after_pull": v["top_after_pull_gauge_md_ft"], "spacer_behind": v["spacer_behind_bbl"],
            "displacement": v["displacement_bbl"]}


BALANCED_PLUG = Contract(
    stable_id="w13.cement.balanced_plug", calculator="CSG/CMT › Balanced Plug", schema_version=1,
    method_id="w13.cement.balanced_plug", method_version="M107 balanced plug volumetrics v1",
    inputs=(FieldSpec("hole", "Hole size / casing ID", "in", attr="plug_hole"),
            FieldSpec("pipe_od", "Pipe OD", "in", attr="plug_pipe_od"),
            FieldSpec("pipe_id", "Pipe ID", "in", attr="plug_pipe_id"),
            FieldSpec("length", "Plug length", "ft", attr="plug_length"),
            FieldSpec("bottom", "Plug bottom (pipe end)", "ft MD", attr="plug_bottom"),
            FieldSpec("excess", "Excess", "%", attr="plug_excess"),
            FieldSpec("spacer", "Spacer ahead", "bbl", attr="plug_spacer"),
            FieldSpec("under", "Under-displacement", "bbl", attr="plug_under"),
            FieldSpec("yield", "Slurry yield (0 = no sacks)", "ft³/sk", attr="plug_yield")),
    results=(FieldSpec("slurry_volume", "Slurry volume", "bbl"), FieldSpec("sacks", "Sacks", "sk"),
             FieldSpec("column_height", "Column height, pipe in", "ft"),
             FieldSpec("top_pipe_in", "Top of cement, pipe in", "ft MD"),
             FieldSpec("top_after_pull", "Top after pull (gauge)", "ft MD"),
             FieldSpec("spacer_behind", "Spacer behind", "bbl"), FieldSpec("displacement", "Displacement", "bbl")),
    recalculate=_balanced_plug, structured=True, reference="CementEngine.balanced_plug (static volumetrics)",
    limits="WORKSHEET - static volumetrics, not a placement simulation or a cement design approval.",
)


def _kick_page(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Kick tolerance and trip margin (W13 ``_wc_calc_kt`` / ``_wc_calc_trip_margin``)."""
    from core.engineering.engines.well_control import WellControlEngine

    out: Dict[str, Optional[float]] = dict.fromkeys(("maasp", "kick_intensity", "max_kick_height", "kick_tolerance",
                                                     "trip_margin", "trip_margin_psi"))
    kt = WellControlEngine.kick_tolerance(
        mw_ppg=values["kt_mw"], shoe_tvd_ft=values["kt_shoe"], current_tvd_ft=values["kt_tvd"],
        frac_mw_ppg=values["kt_frac"], influx_gradient_psi_ft=values["kt_influx"], annular_vol_bbl=None,
        annular_capacity_bbl_ft=_or_none(values["kt_cap"]), formation_emw_ppg=_or_none(values["kt_form"]))
    if kt.success:
        v = kt.values
        out.update(maasp=v.get("maasp_psi"), kick_intensity=v.get("kick_intensity_ppg"),
                   max_kick_height=v.get("max_kick_height_ft"), kick_tolerance=v.get("kick_tolerance_bbl"))
    tm = WellControlEngine.trip_margin(mw_ppg=values["tm_mw"], formation_emw_ppg=values["tm_form"],
                                       tvd_ft=values["tm_tvd"], swab_pressure_psi=_or_none(values["tm_swab"]))
    if tm.success:
        out.update(trip_margin=tm.values["trip_margin_ppg"], trip_margin_psi=tm.values.get("trip_margin_psi"))
    return _all_none(out, "kick tolerance and trip margin both rejected")


KICK_TOLERANCE = Contract(
    stable_id="w13.well_control.kick_tolerance", calculator="Well Control › Kick Tolerance", schema_version=1,
    method_id="w13.well_control.kick_tolerance_trip_margin",
    method_version="M107 kick tolerance and trip margin v1",
    inputs=(FieldSpec("kt_frac", "Frac MW", "ppg", attr="kt_frac"),
            FieldSpec("kt_mw", "Current MW", "ppg", attr="kt_mw"),
            FieldSpec("kt_tvd", "TVD", "ft", attr="kt_tvd"), FieldSpec("kt_shoe", "Shoe TVD", "ft", attr="kt_shoe"),
            FieldSpec("kt_influx", "Influx gradient", "psi/ft", attr="kt_influx_g"),
            FieldSpec("kt_cap", "Ann. cap DP/OH", "bbl/ft (0 = omit)", attr="kt_ann_cap"),
            FieldSpec("kt_form", "Formation EMW (0=omit)", "ppg", attr="kt_form_emw"),
            FieldSpec("tm_mw", "Current MW", "ppg", attr="tm_mw"), FieldSpec("tm_form", "Pore EMW", "ppg", attr="tm_form"),
            FieldSpec("tm_tvd", "TVD", "ft", attr="tm_tvd"),
            FieldSpec("tm_swab", "Swab pressure (opt)", "psi (0 = omit)", attr="tm_swab")),
    results=(FieldSpec("maasp", "MAASP", "psi"), FieldSpec("kick_intensity", "Kick intensity", "ppg"),
             FieldSpec("max_kick_height", "Max height", "ft"), FieldSpec("kick_tolerance", "Kick tolerance", "bbl"),
             FieldSpec("trip_margin", "Trip margin", "ppg"), FieldSpec("trip_margin_psi", "Trip margin", "psi")),
    recalculate=_kick_page, structured=True,
    reference="WellControlEngine.kick_tolerance (no invented influx gradient or capacity) and trip_margin",
    limits="SCREENING well-control aid; not an approved well-control calculation.",
)


def _pore_fg(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Eaton fracture gradient, influx type and corrected d-exponent (W13 ``_wc_calc_eaton`` /
    ``_wc_calc_influx_type`` / ``_wc_calc_d_exp``). The influx category is text and is not a result field."""
    from core.engineering.engines.bit_performance import BitPerformanceEngine
    from core.engineering.engines.well_control import WellControlEngine

    out: Dict[str, Optional[float]] = dict.fromkeys(("fracture_gradient", "fracture_emw", "influx_gradient",
                                                     "influx_height", "d_exponent", "dc_exponent"))
    eaton = WellControlEngine.eaton_fracture_gradient(values["obg"], values["pore_gradient"], values["poisson"])
    if eaton.success:
        fg = eaton.values["fracture_gradient_psi_ft"]
        out.update(fracture_gradient=fg, fracture_emw=fg / 0.052)
    influx = WellControlEngine.influx_type(values["sicp"], values["sidpp"], values["annular_capacity"],
                                           values["pit_gain"])
    if influx.success:
        out.update(influx_gradient=influx.values["influx_gradient_psi_ft"],
                   influx_height=influx.values["influx_height_ft"])
    dexp = BitPerformanceEngine.d_exponent_corrected(values["rop"], values["rpm"], values["wob"], values["bit"],
                                                     mw_ppg=values["mw"], normal_mw_ppg=values["normal_mw"])
    if dexp.success:
        out.update(d_exponent=dexp.values["d_exponent"], dc_exponent=dexp.values["d_exponent_corrected"])
    return _all_none(out, "Eaton, influx and d-exponent all rejected")


PORE_FG = Contract(
    stable_id="w13.well_control.pore_fg", calculator="Well Control › Pore Press  FG", schema_version=1,
    method_id="w13.well_control.eaton_influx_dexp", method_version="M107 Eaton FG / influx type / dc-exponent v1",
    inputs=(FieldSpec("obg", "Overburden gradient", "psi/ft", attr="pp_obg"),
            FieldSpec("pore_gradient", "Pore pressure gradient", "psi/ft", attr="pp_ppg_grad"),
            FieldSpec("poisson", "Poisson's ratio", "-", attr="pp_nu"),
            FieldSpec("sicp", "SICP", "psi", attr="pp_sicp"), FieldSpec("sidpp", "SIDPP", "psi", attr="pp_sidpp"),
            FieldSpec("annular_capacity", "Annular capacity (open hole)", "bbl/ft", attr="pp_ann_cap"),
            FieldSpec("pit_gain", "Pit gain", "bbl", attr="pp_gain"),
            FieldSpec("rop", "ROP", "ft/hr", attr="pp_rop"), FieldSpec("rpm", "RPM", "rpm", attr="pp_rpm"),
            FieldSpec("wob", "WOB", "lbf", attr="pp_wob"), FieldSpec("bit", "Bit size", "in", attr="pp_bit"),
            FieldSpec("mw", "Actual MW", "ppg", attr="pp_mw"), FieldSpec("normal_mw", "Normal MW", "ppg", attr="pp_mw_n")),
    results=(FieldSpec("fracture_gradient", "Fracture gradient", "psi/ft"),
             FieldSpec("fracture_emw", "Fracture gradient EMW", "ppg"),
             FieldSpec("influx_gradient", "Influx gradient", "psi/ft"), FieldSpec("influx_height", "Influx height", "ft"),
             FieldSpec("d_exponent", "d", "-"), FieldSpec("dc_exponent", "dc", "-")),
    recalculate=_pore_fg, structured=True,
    reference="Eaton (1969) FG; influx gradient = SIDPP-SICP balance over the influx height; "
              "Jorden-Shirley d-exponent with Rehm-McClendon correction (BitPerformanceEngine)",
    limits="SCREENING; EMW uses 0.052 psi/ft per ppg; the influx category text is shown, not compared.",
)


def _stuck_pipe(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Free point, string stretch and adjusted weight (W13 ``_update_stuck``)."""
    from core.engineering.engines.fishing import FishingEngine
    from core.unit_manager import UnitManager

    out: Dict[str, Optional[float]] = dict.fromkeys(("free_point", "string_stretch", "adjusted_weight"))
    fp = FishingEngine.free_point(_recorded(values["stretch"]), _recorded(values["pipe_weight"]),
                                  _recorded(values["pull"]))
    if fp.success and fp.value is not None:
        out["free_point"] = fp.value
    length, mw = _recorded(values["length"]), _recorded(values["mw"])
    if length is not None and mw is not None and mw > 0:
        st = FishingEngine.string_stretch(UnitManager.convert(length, "length", "m", "ft"),
                                          UnitManager.convert(mw, "density", "pcf", "ppg"))
        if st.success and st.value is not None:
            out["string_stretch"] = st.value
    adj = FishingEngine.adjusted_weight(_recorded(values["od"]), _recorded(values["id"]))
    if adj.success and adj.value is not None:
        out["adjusted_weight"] = adj.value
    return _all_none(out, "no measured inputs")


STUCK_PIPE = Contract(
    stable_id="w13.fishing.stuck_pipe", calculator="Stuck Pipe", schema_version=1,
    method_id="w13.fishing.free_point_stretch_weight", method_version="M107 free point / stretch / adjusted weight v1",
    inputs=(FieldSpec("stretch", "Measured Stretch", "in (-1 = not recorded)", attr="stk_stretch_in"),
            FieldSpec("pipe_weight", "Pipe Weight", "lb/ft (-1 = not recorded)", attr="stk_wt"),
            FieldSpec("pull", "Pull Force", "lbf (-1 = not recorded)", attr="stk_pull"),
            FieldSpec("length", "String Length", "m (-1 = not recorded)", attr="stk_len_m"),
            FieldSpec("mw", "Mud Weight", "pcf (-1 = not recorded)", attr="stk_mw_pcf"),
            FieldSpec("od", "Pipe OD", "in (-1 = not recorded)", attr="stk_pipe_od"),
            FieldSpec("id", "Pipe ID", "in (-1 = not recorded)", attr="stk_pipe_id")),
    results=(FieldSpec("free_point", "Free point", "ft"), FieldSpec("string_stretch", "String stretch", "in"),
             FieldSpec("adjusted_weight", "Adjusted weight", "lb/ft")),
    recalculate=_stuck_pipe, structured=True, reference="FishingEngine.free_point / string_stretch / adjusted_weight",
    limits="SCREENING estimates; an unrecorded input is not assessed, never zero.",
)


def _mud_wdm(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Weight-up, dilution and mixing (W13 ``_mud_wu`` / ``_mud_dil`` / ``_mud_mix``)."""
    from core.engineering.engines.mud_volume import MudVolumeEngine

    out: Dict[str, Optional[float]] = dict.fromkeys(("sacks", "volume_increase", "weight_up_final_volume",
                                                     "water_required", "dilution_final_volume", "mix_mw",
                                                     "mix_volume"))
    wu = MudVolumeEngine.weight_up(values["wu_current"], values["wu_target"], values["wu_volume"],
                                   additive_density_pcf(values["additive"]))
    if wu.success:
        out.update(sacks=wu.values["sacks"], volume_increase=wu.values["volume_increase_bbl"],
                   weight_up_final_volume=wu.values["final_volume_bbl"])
    dil = MudVolumeEngine.dilution(values["dil_current"], values["dil_target"], values["dil_volume"],
                                   _or_none(values["dilutant"]))
    if dil.success:
        out.update(water_required=dil.values["water_required_bbl"], dilution_final_volume=dil.values["final_volume_bbl"])
    mix = MudVolumeEngine.mix(values["mud1_mw"], values["mud1_volume"], values["mud2_mw"], values["mud2_volume"])
    if mix.success:
        out.update(mix_mw=mix.values["final_mw"], mix_volume=mix.values["total_volume"])
    return _all_none(out, "weight-up, dilution and mix all rejected")


MUD_WDM = Contract(
    stable_id="w13.mud.weight_dilution_mix", calculator="Mud › Weight/Dilution/Mix", schema_version=1,
    method_id="w13.mud.weight_dilution_mix", method_version="M107 weight-up v2 / dilution / mixing v1",
    inputs=(FieldSpec("wu_current", "Current MW", "pcf", attr="mud_wu_cur"),
            FieldSpec("wu_target", "Target MW", "pcf", attr="mud_wu_tar"),
            FieldSpec("wu_volume", "System Volume", "bbl", attr="mud_wu_vol"),
            FieldSpec("additive", "Additive", "text (list entry)", attr="mud_wu_additive", kind="text"),
            FieldSpec("dil_current", "Current MW", "pcf", attr="mud_dil_cur"),
            FieldSpec("dil_target", "Target MW", "pcf", attr="mud_dil_tar"),
            FieldSpec("dil_volume", "System Volume", "bbl", attr="mud_dil_vol"),
            FieldSpec("dilutant", "Dilutant MW (required)", "pcf (0 = not entered)", attr="mud_dilant_mw"),
            FieldSpec("mud1_mw", "Mud 1 MW", "pcf", attr="mud_m1_mw"),
            FieldSpec("mud1_volume", "Mud 1 Vol", "bbl", attr="mud_m1_vol"),
            FieldSpec("mud2_mw", "Mud 2 MW", "pcf", attr="mud_m2_mw"),
            FieldSpec("mud2_volume", "Mud 2 Vol", "bbl", attr="mud_m2_vol")),
    results=(FieldSpec("sacks", "Additive", "100-lb sacks"), FieldSpec("volume_increase", "Volume Increase", "bbl"),
             FieldSpec("weight_up_final_volume", "Final Volume (weight-up)", "bbl"),
             FieldSpec("water_required", "Water Required", "bbl"),
             FieldSpec("dilution_final_volume", "Final Volume (dilution)", "bbl"),
             FieldSpec("mix_mw", "Final MW", "pcf"), FieldSpec("mix_volume", "Total Volume", "bbl")),
    recalculate=_mud_wdm, structured=True,
    reference="sacks = V(bbl) x 5.6146 ft³/bbl x rho_add x (MW2-MW1)/(rho_add-MW2)/100 (pcf); "
              "dilution V(MW1-MW2)/(MW2-MWd); mix volume-weighted",
    limits="Ideal volume additivity; additive densities as listed in the calculator.",
)


def _mud_balance(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core.engineering.engines.mud_volume import MudVolumeEngine

    r = MudVolumeEngine.balance(active_volume_bbl=values["active"], additions_bbl=values["additions"],
                                losses_bbl=values["losses"], transfers_in_bbl=values["transfers_in"],
                                transfers_out_bbl=values["transfers_out"], returns_bbl=values["returns"],
                                dilution_bbl=values["dilution"], dumped_bbl=values["dumped"])
    if not r.success:
        raise ValueError(r.error)
    return {"final_volume": r.values["final_volume_bbl"], "net_change": r.values["net_change_bbl"]}


MUD_BALANCE = Contract(
    stable_id="w13.mud.volume_balance", calculator="Mud › Volume Balance", schema_version=1,
    method_id="w13.mud.volume_balance", method_version="M107 mud volume balance v1",
    inputs=tuple(FieldSpec(fid, label, "bbl", attr=attr) for fid, label, attr in (
        ("active", "Active volume", "mud_bal_active"), ("additions", "Additions", "mud_bal_add"),
        ("losses", "Losses", "mud_bal_loss"), ("transfers_in", "Transfers in", "mud_bal_tin"),
        ("transfers_out", "Transfers out", "mud_bal_tout"), ("returns", "Returns", "mud_bal_ret"),
        ("dilution", "Dilution (water)", "mud_bal_dil"), ("dumped", "Dumped", "mud_bal_dump"))),
    results=(FieldSpec("final_volume", "Final volume", "bbl"), FieldSpec("net_change", "Net change", "bbl")),
    recalculate=_mud_balance, structured=True,
    reference="final = active + additions + transfers in + returns + dilution - losses - transfers out - dumped",
    limits="WORKSHEET - bookkeeping of the entered volumes; no engineering model (M125 classification).",
)


def _mud_lab(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """MBT, LSRYP, excess lime, slug and corrosion (W13 ``_mud_lab*``); each part from its own inputs."""
    from core.engineering.extended import MudEngineering

    out: Dict[str, Optional[float]] = dict.fromkeys(("mbt", "lsryp", "excess_lime", "dry_pipe_length",
                                                     "hydrostatic_gain", "corrosion_mpy", "corrosion_lb_ft2_yr"))
    parts = (
        (lambda: MudEngineering.mbt_bentonite_equiv(values["mb_ml"], values["sample_ml"]),
         {"mbt": "mbt_lb_per_bbl"}),
        (lambda: MudEngineering.lsryp(values["theta3"], values["theta6"]), {"lsryp": "lsryp_lb_per_100ft2"}),
        (lambda: MudEngineering.excess_lime_obm(values["pom"]), {"excess_lime": "excess_lime_lb_per_bbl"}),
        (lambda: MudEngineering.slug_dry_length(values["slug_volume"], values["slug_mw"], values["mud_mw"],
                                                values["pipe_capacity"]),
         {"dry_pipe_length": "dry_pipe_length_ft", "hydrostatic_gain": "hydrostatic_gain_psi"}),
        (lambda: MudEngineering.corrosion_rate(values["coupon_loss"], values["coupon_area"], values["exposure"],
                                               values["coupon_density"]),
         {"corrosion_mpy": "corrosion_rate_mpy", "corrosion_lb_ft2_yr": "corrosion_rate_lb_ft2_yr"}),
    )
    for compute, keys in parts:
        try:
            res = compute()
        except Exception:  # silent-ok: the engine's own error type; that part stays None (W13 shows the message)
            continue
        for field_id, key in keys.items():
            out[field_id] = float(res[key]) if res.get(key) is not None else None
    return _all_none(out, "every lab calculator rejected its inputs")


MUD_LAB = Contract(
    stable_id="w13.mud.lab", calculator="Mud › Mud Lab", schema_version=1,
    method_id="w13.mud.lab", method_version="M107 mud lab (MBT, LSRYP, lime, slug, corrosion) v1",
    inputs=(FieldSpec("mb_ml", "Methylene blue used", "mL", attr="ml_mb_ml"),
            FieldSpec("sample_ml", "Mud sample volume", "mL", attr="ml_sample_ml"),
            FieldSpec("theta3", "θ3 reading", "dial", attr="ml_th3"), FieldSpec("theta6", "θ6 reading", "dial", attr="ml_th6"),
            FieldSpec("pom", "POM (mL 0.1N H₂SO₄)", "mL", attr="ml_pom"),
            FieldSpec("slug_volume", "Slug volume", "bbl", attr="ml_slug_vol"),
            FieldSpec("slug_mw", "Slug MW", "ppg", attr="ml_slug_mw"), FieldSpec("mud_mw", "Mud MW", "ppg", attr="ml_mud_mw"),
            FieldSpec("pipe_capacity", "Pipe capacity", "bbl/ft", attr="ml_pipe_cap"),
            FieldSpec("coupon_loss", "Coupon weight loss", "mg", attr="ml_cr_w"),
            FieldSpec("coupon_area", "Coupon area", "in²", attr="ml_cr_a"),
            FieldSpec("exposure", "Exposure time", "hr", attr="ml_cr_t"),
            FieldSpec("coupon_density", "Coupon density", "g/cm³", attr="ml_cr_d")),
    results=(FieldSpec("mbt", "Bentonite equiv", "lb/bbl"), FieldSpec("lsryp", "LSRYP", "lbf/100 ft²"),
             FieldSpec("excess_lime", "Excess lime", "lb/bbl"), FieldSpec("dry_pipe_length", "Dry pipe", "ft"),
             FieldSpec("hydrostatic_gain", "ΔP gain", "psi"), FieldSpec("corrosion_mpy", "Corrosion rate", "mpy"),
             FieldSpec("corrosion_lb_ft2_yr", "Corrosion rate", "lb/ft²/yr")),
    recalculate=_mud_lab, structured=True,
    reference="MBT = 5 V_MB/V_sample; LSRYP = 2θ3 - θ6; excess lime = 1.295 POM; "
              "L_dry = V_slug(ρs-ρm)/(cap ρm); mpy = 534 W/(A T D)",
    limits="The corrosion severity text is shown, not compared.",
)


def _fishing(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Overshot fit, jar range and back-off depth (W13 ``_calc_fish_sizing`` / ``_calc_jar_range`` /
    ``_calc_backoff``). A rejected overshot fit is None here; the legacy screen shows 0.000 for it."""
    from core.engineering.engines.fishing import FishingEngine

    out: Dict[str, Optional[float]] = dict.fromkeys(("clearance", "compatible", "buoyant_weight", "upward_force",
                                                     "jar_setting", "backoff_depth"))
    fit = FishingEngine.overshot_fit(values["fish_od"], values["overshot_id"])
    if fit.success:
        out.update(clearance=fit.values["clearance_in"], compatible=1.0 if fit.values["compatible"] else 0.0)
    jar = FishingEngine.jar_operating_range(values["string_weight"], values["bf"], values["overpull"])
    if jar.success:
        out.update(buoyant_weight=jar.values["buoyant_weight_lbs"], upward_force=jar.values["upward_force_lbs"],
                   jar_setting=jar.values["recommended_jar_setting_lbs"])
    bo = FishingEngine.backoff_depth(_recorded(values["bo_stretch"]), _recorded(values["bo_weight"]), 30.0e6)
    if bo.success and bo.value is not None:
        out["backoff_depth"] = bo.value
    return _all_none(out, "overshot, jar and back-off all rejected")


FISHING = Contract(
    stable_id="w13.fishing.sizing", calculator="Fishing", schema_version=1,
    method_id="w13.fishing.overshot_jar_backoff", method_version="M107 overshot fit / jar range / back-off v1",
    inputs=(FieldSpec("fish_od", "Fish OD", "in", attr="fish_od"),
            FieldSpec("overshot_id", "Overshot Catch ID", "in", attr="fish_os_id"),
            FieldSpec("string_weight", "String Weight", "lbf", attr="jar_string_wt"),
            FieldSpec("bf", "Buoyancy Factor", "-", attr="jar_bf"),
            FieldSpec("overpull", "Overpull", "lbf", attr="jar_overpull"),
            FieldSpec("bo_stretch", "Measured Stretch", "in (-1 = not recorded)", attr="bo_stretch"),
            FieldSpec("bo_weight", "Pipe Weight", "ppf (-1 = not recorded)", attr="bo_pipe_wt")),
    results=(FieldSpec("clearance", "Clearance", "in"), FieldSpec("compatible", "Compatible", "flag (1 = yes)"),
             FieldSpec("buoyant_weight", "Buoyant Wt", "lbf"), FieldSpec("upward_force", "Upward Force", "lbf"),
             FieldSpec("jar_setting", "Recommended Jar", "lbf"), FieldSpec("backoff_depth", "Back-off depth", "ft")),
    recalculate=_fishing, structured=True,
    reference="FishingEngine.overshot_fit / jar_operating_range / backoff_depth (E = 30e6 psi)",
    limits="SCREENING sizing rules.",
)


def _rheology(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Fann rheology (W13 ``_mud_rheo``); θ200/θ100 are displayed but not used by the engine."""
    from core.hydraulics_engine import MudProperties

    try:
        r = MudProperties.calculate_fann_rheology(theta600=values["t600"], theta300=values["t300"],
                                                  theta3=values["t3"], theta6=values["t6"])
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    pv, yp = r["pv_cp"], r["yp_lbf100ft2"]
    return {"pv": float(pv), "yp": float(yp), "n": r["power_law_n"], "k": r["power_law_k_cp_s_nminus1"],
            "tau_y": r["hb_yield_estimate_lbf100ft2"], "indicator": r["screening_effective_viscosity_indicator_cp"],
            "pv_yp": pv / yp if yp > 0 else None,
            "gel_ratio": values["gel10m"] / values["gel10s"] if values["gel10s"] > 0 else None,
            "mw_ppg": MudProperties(mw_pcf=values["mw"]).mw_ppg}


RHEOLOGY = Contract(
    stable_id="w13.mud.rheology", calculator="Mud › Rheology", schema_version=1,
    method_id="w13.mud.fann_rheology", method_version="M107 Fann rheology (Bingham / power law / HB estimate) v1",
    inputs=tuple(FieldSpec(fid, label, unit, attr=attr) for fid, label, unit, attr in (
        ("t600", "θ600", "dial", "rh_t600"), ("t300", "θ300", "dial", "rh_t300"), ("t200", "θ200", "dial", "rh_t200"),
        ("t100", "θ100", "dial", "rh_t100"), ("t6", "θ6", "dial", "rh_t6"), ("t3", "θ3", "dial", "rh_t3"),
        ("gel10s", "Gel 10s", "lbf/100 ft²", "rh_gel10s"), ("gel10m", "Gel 10m", "lbf/100 ft²", "rh_gel10m"),
        ("mw", "MW", "pcf", "rh_mw"))),
    results=(FieldSpec("pv", "PV", "cP"), FieldSpec("yp", "YP", "lbf/100 ft²"), FieldSpec("n", "n", "-"),
             FieldSpec("k", "K", "cP·s^(n-1)"), FieldSpec("tau_y", "τ0 estimate", "lbf/100 ft²"),
             FieldSpec("indicator", "PV + 5YP indicator", "cP"), FieldSpec("pv_yp", "PV/YP Ratio", "-"),
             FieldSpec("gel_ratio", "Gel 10m/10s", "-"), FieldSpec("mw_ppg", "Mud Weight", "ppg")),
    recalculate=_rheology, structured=True,
    reference="MudProperties.calculate_fann_rheology: PV = θ600-θ300, YP = θ300-PV, n = 3.32 log(θ600/θ300), "
              "K = 510 θ300/511^n, τ0 = 2θ3-θ6",
    limits="SCREENING; θ200 and θ100 are recorded but not used by the method; not a full HB fit.",
)

NOZZLE_SLOTS = 8          # the W13 nozzle-count spin allows 1..8


def _nozzle_optimization(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Two-point pump-test nozzle optimisation (W13 ``_bit_optimize``). The engine's zero fallbacks are
    rejected here: without available HHP, a pump-pressure limit and a mud weight there is no result (with
    all three positive the bit pressure drop and the optimum area are positive)."""
    from core.hydraulics_engine import AdvancedHydraulicsEngine

    _positive(values, "hhp", "max_press", "mw")
    count = values["n_nozzles"]
    if count is None or count != int(count) or not 1 <= int(count) <= NOZZLE_SLOTS:
        raise ValueError(f"nozzle count must be a whole number from 1 to {NOZZLE_SLOTS}")
    r = AdvancedHydraulicsEngine.optimize_nozzles(
        hhp=values["hhp"], max_press=values["max_press"], fr1=values["fr1"], spp1=values["spp1"],
        fr2=values["fr2"], spp2=values["spp2"], prev_tfa=values["prev_tfa"], mw_ppg=values["mw"],
        n_nozzles=int(count), model="HP" if values["model_hp"] else "IF")
    out: Dict[str, Optional[float]] = {
        "max_flow_rate": r["max_flow_rate_gpm"], "optimal_flow_rate": r["optimal_flow_rate_gpm"],
        "friction_exponent": r["friction_exponent"],
        "friction_exponent_assumed": 1.0 if r["friction_exponent_source"] == "assumed_fallback" else 0.0,
        "optimal_tfa": r["optimal_tfa_in2"], "actual_tfa": r["actual_tfa_in2"], "tfa_error": r["tfa_error"]}
    sizes = list(r["selected_nozzles"])
    for slot in range(NOZZLE_SLOTS):
        out[f"nozzle_{slot + 1}"] = float(sizes[slot]) if slot < len(sizes) else None
    return out


NOZZLE_OPTIMIZATION = Contract(
    stable_id="w13.bit.nozzle_optimization", calculator="Bit Hydraulics › Nozzle Optimization", schema_version=1,
    method_id="w13.bit.nozzle_optimization", method_version="M107 two-point nozzle optimisation v1",
    inputs=(FieldSpec("hhp", "Available HHP", "hp", attr="opt_hhp"),
            FieldSpec("max_press", "Max Pump Press", "psi", attr="opt_max_press"),
            FieldSpec("fr1", "Flow Rate #1", "gpm", attr="opt_fr1"), FieldSpec("spp1", "SPP #1", "psi", attr="opt_spp1"),
            FieldSpec("fr2", "Flow Rate #2", "gpm", attr="opt_fr2"), FieldSpec("spp2", "SPP #2", "psi", attr="opt_spp2"),
            FieldSpec("prev_tfa", "Current TFA", "in²", attr="opt_tfa"), FieldSpec("mw", "Mud Weight", "ppg", attr="opt_mw"),
            FieldSpec("n_nozzles", "No. of Nozzles", "count", attr="opt_n_nzl"),
            FieldSpec("model_hp", "Model", "bool (checked = max bit HP, else max impact force)", attr="opt_hp_model",
                      kind="bool")),
    results=(FieldSpec("max_flow_rate", "Max Flow Rate", "gpm"), FieldSpec("optimal_flow_rate", "Optimal Flow Rate", "gpm"),
             FieldSpec("friction_exponent", "Friction exponent", "-"),
             FieldSpec("friction_exponent_assumed", "Friction exponent assumed", "flag (1 = n = 1 fallback)"),
             FieldSpec("optimal_tfa", "Target TFA", "in²"), FieldSpec("actual_tfa", "Actual TFA", "in²"),
             FieldSpec("tfa_error", "TFA Error", "in²"),
             *(FieldSpec(f"nozzle_{slot}", f"Nozzle {slot}", "1/32 in") for slot in range(1, NOZZLE_SLOTS + 1))),
    recalculate=_nozzle_optimization, structured=True,
    reference="Q_max = HHP·1714/P_max; n from log(SPP1/SPP2)/log(Q1/Q2) (fallback n = 1, flagged); "
              "ΔPf_opt = P/(n+1) (HP) or 2P/(n+2) (IF); best real 1/32-in combination",
    limits="SCREENING; the parasitic-loss model is a single power law from two pump-test points.",
)


# ---- M126: table-driven pages (Well Volumes; Hydraulics) ---------------------------------------------
def _well_volumes_assessment(values: Dict[str, Any]) -> Dict[str, Any]:
    from core import well_volumes

    out = well_volumes.assess(values.get("pumps") or [], values.get("pipes") or [], values.get("casings") or [],
                              values.get("bit_depth"))
    if out["status"] != "ASSESSED":
        raise ValueError("NOT ASSESSED: " + "; ".join(out["reasons"]))
    return out


def _well_volumes(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    return dict(_well_volumes_assessment(values)["results"])


def _well_volume_rows(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _well_volumes_assessment(values)["components"]


WELL_VOLUMES = Contract(
    stable_id="w13.volume.well_volumes", calculator="Volume › Well Volumes", schema_version=1,
    method_id="w13.volume.well_volumes", method_version="M126 well volumes v1",
    inputs=(FieldSpec("bit_depth", "Bit Depth", "m", attr="vol_depth"),),
    results=(FieldSpec("string_length_m", "String length", "m"),
             FieldSpec("string_volume_bbl", "String volume", "bbl"),
             FieldSpec("annular_volume_bbl", "Annular volume", "bbl"),
             FieldSpec("circulating_volume_bbl", "Circulating volume (string + annulus)", "bbl"),
             FieldSpec("flow_rate_gpm", "Flow rate", "gpm"),
             FieldSpec("surface_to_bit_min", "Surface to bit", "min"),
             FieldSpec("lag_time_min", "Lag time (bottoms up)", "min"),
             FieldSpec("circulation_time_min", "Full circulation", "min"),
             FieldSpec("bottoms_up_strokes", "Bottoms-up strokes per pump", "stk")),
    recalculate=_well_volumes, structured=True, components=_well_volume_rows,
    extras=(ExtraSpec("pumps", "vol_pumps", "bbl/stk, spm", "Mud pumps", refresh="_vol_refresh_pump_table"),
            ExtraSpec("pipes", "vol_pipes", "in, m (surface down)", "Drill string", refresh="_vol_refresh_pipe_table"),
            ExtraSpec("casings", "vol_casings", "in, m MD", "Casing / open hole", refresh="_vol_refresh_csg_table")),
    reference="String placed from the surface down to the bit; pipe capacity ID^2/1029.4 bbl/ft, annulus "
              "(Dh^2 - OD^2)/1029.4 bbl/ft per placed interval; times from sum(output x SPM) (core.well_volumes)",
    limits="Calculation of the entered geometry, not a measured volume; surface lines, pits and the hole below the "
           "bit are excluded; gaps, overlaps or a string that does not reach the bit are NOT ASSESSED.",
)


def _hydraulics_run(values: Dict[str, Any]):
    from core import w13_hydraulics

    if values.get("confirmed") is not True:
        raise ValueError("NOT ASSESSED: the display-seeded hydraulics inputs were not confirmed")
    result = w13_hydraulics.run(dict(values, bit_diameter=_recorded(values.get("bit_diameter"))))
    if result.errors:
        raise ValueError("; ".join(result.errors))
    return result


def _hydraulics(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core import w13_hydraulics

    return w13_hydraulics.scalar_results(_hydraulics_run(values))


def _hydraulics_rows(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    from core import w13_hydraulics

    return w13_hydraulics.component_rows(_hydraulics_run(values))


HYDRAULICS = Contract(
    stable_id="w13.hydraulics.page", calculator="Hydraulics", schema_version=1,
    method_id="w13.hydraulics.circulating_system", method_version="M126 circulating-system hydraulics v1",
    inputs=(FieldSpec("model", "Model", "model name", attr="hy_model", kind="text"),
            FieldSpec("confirmed", "Confirm", "bool (checked = displayed values confirmed)", attr="hy_confirm_defaults",
                      kind="bool"),
            FieldSpec("mw", "MW (pcf)", "pcf", attr="hy_mw"), FieldSpec("pv", "PV (cp)", "cP", attr="hy_pv"),
            FieldSpec("yp", "YP", "lbf/100 ft²", attr="hy_yp"),
            FieldSpec("t600", "θ600", "dial", attr="hy_t600"), FieldSpec("t300", "θ300", "dial", attr="hy_t300"),
            FieldSpec("t6", "θ6", "dial", attr="hy_t6"), FieldSpec("t3", "θ3", "dial", attr="hy_t3"),
            FieldSpec("standpipe_length", "Standpipe Len", "m", attr="hy_sp_l"),
            FieldSpec("standpipe_id", "Standpipe ID", "in", attr="hy_sp_id"),
            FieldSpec("hose_length", "Hose Len", "m", attr="hy_hose_l"),
            FieldSpec("hose_id", "Hose ID", "in", attr="hy_hose_id"),
            FieldSpec("bit_diameter", "Bit diameter for HSI", "in", attr="hy_bit_diameter", required=False),
            FieldSpec("well_type", "Well Type", "profile name", attr="hy_wt", kind="text"),
            FieldSpec("kop", "KOP", "m", attr="hy_kop"), FieldSpec("eob", "EOB", "m", attr="hy_eob"),
            FieldSpec("max_inc", "Max Inc", "deg", attr="hy_inc"),
            FieldSpec("build_rate", "Build Rate", "deg/30 m", attr="hy_br"),
            FieldSpec("bit_depth", "Bit Depth", "m", attr="hy_bit_dep")),
    results=(FieldSpec("flow_rate_gpm", "Flow rate", "gpm"), FieldSpec("surface_loss_psi", "Surface loss", "psi"),
             FieldSpec("string_loss_psi", "Drill-string loss (sum of rows)", "psi"),
             FieldSpec("bit_loss_psi", "Bit ΔP", "psi"),
             FieldSpec("annular_loss_psi", "Annular loss (sum of rows)", "psi"),
             FieldSpec("total_loss_psi", "Total (SPP)", "psi"),
             FieldSpec("ecd_at_bit_ppg", "ECD at bit", "ppg"), FieldSpec("ecd_at_shoe_ppg", "ECD at shoe", "ppg"),
             FieldSpec("tfa_in2", "TFA", "in²"), FieldSpec("bit_hhp", "Bit HHP", "hp"),
             FieldSpec("hsi", "HSI", "hp/in²"), FieldSpec("jet_velocity_fps", "Jet velocity", "ft/s"),
             FieldSpec("impact_force_lbs", "Impact force", "lbf"), FieldSpec("percent_bit_hp", "Bit HP", "%"),
             FieldSpec("critical_flow_rate_gpm", "Critical flow rate (deepest annulus)", "gpm")),
    recalculate=_hydraulics, structured=True, components=_hydraulics_rows,
    extras=(ExtraSpec("pumps", "hy_pumps", "bbl/stk, spm", "Mud pumps", refresh="_hy_refresh_pump_table"),
            ExtraSpec("pipes", "hy_pipe_rows", "in, m, ppf (surface down)", "Drill string",
                      refresh="_hy_invalidate_results"),
            ExtraSpec("casings", "hy_csg_rows", "in, m MD", "Casing / open hole", refresh="_hy_invalidate_results"),
            ExtraSpec("nozzles", "hy_nzl_rows", "1/32 in x count", "Bit nozzles", refresh="_hy_update_tfa")),
    reference="AdvancedHydraulicsEngine (Bingham: Guo & Liu 2011 Eqs. 2.58-2.59 laminar, Blasius-type turbulent; "
              "Power Law); bit ΔP from TFA; ECD = MW + annular loss / (0.052 TVD) with TVD = MD (vertical only) "
              "(core.w13_hydraulics)",
    limits="SCREENING - simplified correlations, not an approved hydraulics design; Herschel-Bulkley refused; a "
           "non-vertical profile is NOT ASSESSED (no measured survey TVD on this page).",
)


def _weight(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core import w13_weight

    try:
        return w13_weight.results(values)
    except w13_weight.SurveyPinError as exc:
        raise ValueError(f"NOT REPRODUCIBLE: {exc}") from exc


WEIGHT = Contract(
    stable_id="w13.weight.page", calculator="Weight", schema_version=1,
    method_id="w13.weight.torque_drag", method_version="M127 weight card and soft-string T&D v1",
    inputs=(FieldSpec("tds", "TDS/Block Wt", "klbf", attr="wt_tds"),
            FieldSpec("mw", "Mud Weight", "pcf", attr="wt_mw"),
            FieldSpec("inclination", "Inclination", "deg (weight card only)", attr="wt_inc"),
            FieldSpec("friction", "Friction Factor", "dimensionless", attr="wt_friction"),
            FieldSpec("hole_id", "Hole ID (T&D buckling)", "in (0 = not recorded)", attr="wt_hole", required=False),
            FieldSpec("wob", "WOB (T&D)", "klbf", attr="wt_wob")),
    results=(FieldSpec("air_weight_klbf", "Air weight", "klbf"),
             FieldSpec("axial_air_weight_klbf", "Axial air weight (weight card inclination)", "klbf"),
             FieldSpec("buoyancy_factor", "Buoyancy factor", "dimensionless"),
             FieldSpec("buoyed_weight_klbf", "Buoyed weight", "klbf"),
             FieldSpec("hook_load_klbf", "Hook load (with TDS/block)", "klbf"),
             FieldSpec("pickup_klbf", "Pickup (weight card)", "klbf"),
             FieldSpec("slackoff_klbf", "Slack-off (weight card)", "klbf"),
             FieldSpec("td_pickup_klbf", "T&D pickup hook load", "klbf"),
             FieldSpec("td_slackoff_klbf", "T&D slack-off hook load", "klbf"),
             FieldSpec("td_rotating_klbf", "T&D rotating hook load", "klbf"),
             FieldSpec("td_sliding_klbf", "T&D sliding hook load", "klbf"),
             FieldSpec("td_surface_torque_ft_lbf", "T&D surface torque (rotating)", "ft-lbf"),
             FieldSpec("td_buoyed_weight_klbf", "T&D buoyed string weight", "klbf"),
             FieldSpec("td_neutral_point_md_m", "T&D neutral point (slack-off)", "m MD"),
             FieldSpec("td_buckling_flag", "T&D buckling screening flag", "1 = flagged, 0 = not flagged")),
    recalculate=_weight, structured=True,
    extras=(ExtraSpec("pipes", "wt_pipes", "in, m, ppf", "Drill-string components", refresh="_wt_refresh_table"),
            ExtraSpec("survey", "wt_survey_pin", "survey revision pin (MD m, deg, station SHA-256)",
                      "Survey revision (pinned)", refresh="_wt_survey_pin_restored")),
    reference="TorqueDragEngine: weight card W_axial = W_air cos I, BF = 1 - MW/65.5, drag = W_b mu sin I; "
              "Johancsik soft-string (SPE 11380) along the pinned survey revision (core.w13_weight)",
    limits="SCREENING - soft-string (no stiffness, contact or dynamics), constant friction factor, simple "
           "buoyancy; T&D only on a pinned, hash-verified survey revision of the well, otherwise UNKNOWN.",
)


_CASING_REQUIRED = ("od_in", "id_in", "wall_in", "yield_psi")
CASING_ORIGINS = ("architecture", "derived", "preset", "reference", "user", "unknown")   # M188: + reference (additive)


def _casing_strength(values: Dict[str, Any]) -> Dict[str, Optional[float]]:
    from core.engineering.engines.casing import CasingEngine

    provenance = values.get("provenance") if isinstance(values.get("provenance"), dict) else {}
    fields = provenance.get("fields") if isinstance(provenance.get("fields"), dict) else {}
    if not fields:
        raise ValueError("NOT REPRODUCIBLE: the per-field provenance was not recorded")
    odd = sorted(k for k, v in fields.items() if v not in CASING_ORIGINS)
    if odd:
        raise ValueError(f"NOT REPRODUCIBLE: unknown provenance class for {', '.join(odd)}")
    unknown = [key for key in _CASING_REQUIRED if fields.get(key) in (None, "unknown")]
    if unknown:
        raise ValueError(f"NOT ASSESSED: {', '.join(unknown)} unknown in the source - enter the value(s)")
    r = CasingEngine.evaluate(
        od_in=values["od"], id_in=values["id"], wall_in=values["wall"], yield_psi=values["yield_psi"],
        internal_pressure_psi=values.get("pi") or None, external_pressure_psi=values.get("pe") or None,
        axial_tension_lbf=values.get("axial") or None,
        connection_burst_psi=values.get("conn_burst") or None,
        connection_collapse_psi=values.get("conn_collapse") or None,
        connection_tension_lbf=values.get("conn_tension") or None)
    if not r.success:
        raise ValueError(r.error or "casing evaluation failed")
    v = r.values
    keys = ("burst_rating_psi", "collapse_rating_psi", "d_over_t", "pipe_body_yield_lbf", "collapse_combined_psi",
            "fyax_psi", "vme_psi", "vme_utilization", "governing_burst_psi", "governing_collapse_psi",
            "governing_tension_lbf", "burst_sf", "collapse_sf", "tension_sf")
    return {key: v.get(key) for key in keys}


CASING_STRENGTH = Contract(
    stable_id="w13.casing.strength", calculator="CSG/CMT › Casing Strength", schema_version=1,
    method_id="w13.casing.strength", method_version="M127 casing pipe-body strength v1",
    inputs=(FieldSpec("od", "OD", "in", attr="csg_od"),
            FieldSpec("weight", "Weight", "ppf (recorded, not used by the ratings)", attr="csg_wt_ppf",
                      required=False),
            FieldSpec("id", "ID", "in", attr="csg_id_calc"),
            FieldSpec("yield_psi", "Yield Strength", "psi", attr="csg_yield"),
            FieldSpec("wall", "Wall Thickness", "in", attr="csg_wall"),
            FieldSpec("axial", "Axial tension (opt)", "lbf (0 = not supplied)", attr="csg_axial", required=False),
            FieldSpec("pi", "Internal P (opt)", "psi (0 = not supplied)", attr="csg_pi", required=False),
            FieldSpec("pe", "External P (opt)", "psi (0 = not supplied)", attr="csg_pe", required=False),
            FieldSpec("conn_burst", "Connection burst (0=omit)", "psi (0 = not entered)", attr="csg_conn_burst",
                      required=False),
            FieldSpec("conn_collapse", "Connection collapse (0=omit)", "psi (0 = not entered)",
                      attr="csg_conn_coll", required=False),
            FieldSpec("conn_tension", "Connection tension (0=omit)", "lbf (0 = not entered)",
                      attr="csg_conn_tens", required=False)),
    results=(FieldSpec("burst_rating_psi", "Burst rating (pipe body)", "psi"),
             FieldSpec("collapse_rating_psi", "Collapse rating (pipe body)", "psi"),
             FieldSpec("d_over_t", "D/t", "dimensionless"),
             FieldSpec("pipe_body_yield_lbf", "Pipe-body yield", "lbf"),
             FieldSpec("collapse_combined_psi", "Collapse with axial / internal pressure", "psi"),
             FieldSpec("fyax_psi", "Axial-stress equivalent yield (fyax)", "psi"),
             FieldSpec("vme_psi", "VME stress (inner wall)", "psi"),
             FieldSpec("vme_utilization", "VME utilisation", "fraction of yield"),
             FieldSpec("governing_burst_psi", "Governing burst (pipe body / connection)", "psi"),
             FieldSpec("governing_collapse_psi", "Governing collapse (pipe body / connection)", "psi"),
             FieldSpec("governing_tension_lbf", "Governing tension (pipe body / connection)", "lbf"),
             FieldSpec("burst_sf", "Burst SF (governing / internal P)", "ratio"),
             FieldSpec("collapse_sf", "Collapse SF (governing / external P)", "ratio"),
             FieldSpec("tension_sf", "Tension SF (governing / axial)", "ratio")),
    recalculate=_casing_strength, structured=True,
    extras=(ExtraSpec("provenance", "csg_case_provenance", "origin per field (architecture / derived / preset / "
                      "reference / user / unknown) and the architecture revision pin or library snapshot", "Input provenance",
                      refresh="_csg_case_provenance_restored"),),
    reference="CasingEngine (API TR 5C3 pipe-body subset: Barlow burst with 87.5 % wall, four-regime collapse, "
              "pipe-body yield, fyax and internal-pressure correction, inner-wall VME; capped-end)",
    limits="SCREENING - API TR 5C3 pipe-body subset only, not a complete rating, casing design or compliance "
           "statement; connection ratings only as entered; yield never inferred from the grade; a required "
           "value unknown in the source is NOT ASSESSED; 0 in an optional load means not supplied.",
)


def _dp_schedule_run(values: Dict[str, Any]) -> Dict[str, Any]:
    from core import dp_schedule

    return dp_schedule.schedule(values.get("icp"), values.get("fcp"), values.get("strokes"),
                                values.get("intervals"), values.get("pump_output") or None)


CHOKE_SCHEDULE = Contract(
    stable_id="w13.well_control.dp_schedule", calculator="Well Control › Choke Schedule", schema_version=1,
    method_id="w13.well_control.dp_pressure_schedule", method_version="M128 drill-pipe pressure schedule v1",
    inputs=(FieldSpec("icp", "ICP", "psi", attr="cs_icp"), FieldSpec("fcp", "FCP", "psi", attr="cs_fcp"),
            FieldSpec("strokes", "Strokes to Bit", "stk", attr="cs_strokes"),
            FieldSpec("intervals", "Intervals", "count", attr="cs_intervals"),
            FieldSpec("pump_output", "Pump output (volume column)", "bbl/stk (0 = not entered)",
                      attr="cs_pump_output", required=False)),
    results=(FieldSpec("initial_dp_psi", "Initial drill-pipe pressure (ICP)", "psi"),
             FieldSpec("final_dp_psi", "Final drill-pipe pressure (FCP)", "psi"),
             FieldSpec("strokes_per_step", "Strokes per step", "stk"),
             FieldSpec("pressure_step_psi", "Pressure drop per step", "psi"),
             FieldSpec("psi_per_100_strokes", "Pressure drop per 100 strokes", "psi"),
             FieldSpec("kill_mud_to_bit_bbl", "Kill mud pumped to the bit", "bbl")),
    recalculate=lambda values: dict(_dp_schedule_run(values)["results"]), structured=True,
    components=lambda values: _dp_schedule_run(values)["rows"],
    reference="Linear drill-pipe circulating pressure from ICP at 0 strokes to FCP at strokes to bit in equal "
              "stroke steps (Wait and Weight); cumulative volume = strokes x entered pump output (core.dp_schedule)",
    limits="WORKSHEET - arithmetic of the entered ICP, FCP and strokes (never seeded or derived here); drill-pipe "
           "pressures the choke is adjusted to hold, not choke pressures; not a kill procedure or an approved "
           "well-control document.",
)


CONTRACTS: Dict[str, Contract] = {c.calculator: c for c in (
    QUICK_CALC, BIT_HYDRAULICS, TFA, HYDROSTATIC, CEMENT_VOLUME, OWR, BUILD_TURN,                    # M73 / M87
    BUOYANCY, BALANCED_PLUG, KICK_TOLERANCE, PORE_FG, STUCK_PIPE, MUD_WDM, MUD_BALANCE, MUD_LAB,    # M107
    FISHING, RHEOLOGY, NOZZLE_OPTIMIZATION,
    WELL_VOLUMES, HYDRAULICS,                                                                          # M126
    WEIGHT, CASING_STRENGTH,                                                                           # M127
    CHOKE_SCHEDULE)}                                                                                   # M128
LEGACY_CONTRACTS: Tuple[Contract, ...] = (QUICK_CALC_V1,)
# method_id -> versions this build can still run. A version removed from here
# makes its stored cases NOT REPRODUCIBLE (never silently re-run with another method).
AVAILABLE_METHODS: Dict[str, Tuple[str, ...]] = {c.method_id: (c.method_version,) for c in CONTRACTS.values()}
AVAILABLE_METHODS[QUICK_CALC_V1.method_id] = (QUICK_CALC_V1.method_version,)

# Every W13 leaf calculator (finder path) without a re-runnable contract, with the exact reason (M107).
NOT_SUPPORTED: Dict[str, str] = {
    "Well Control › Kill Sheet": "TRAINING AID (owner decision pending) and the drill-string geometry table (wc_pipes) "
                                 "is not captured; kill-sheet runs are saved in Calc History as TRAINING AID",
    "Directional › Multi-Survey": "no W13 case: the table is a draft that no other page reads; it is kept by "
                                  "saving it as a survey revision (immutable, verified, method-versioned, "
                                  "declared azimuth reference and datum)",
    "Directional › Anti-Collision": "no W13 case: each run is saved as a trajectory comparison record (survey "
                                    "revisions of both wells, re-run in History); SCREENING - NO ISCWSA "
                                    "UNCERTAINTY - NO SEPARATION FACTOR - NOT APPROVED",
    "DP Database": "reference catalogue, not a calculator: nothing is computed, so there is nothing to re-run",
}


# ---- M125: what each W13 leaf IS (separate from whether its cases can be re-run) ----------------------
LEAF_CLASSIFICATION_VERSION = "M125 W13 leaf classification v1"
CLASS_CONTRACT = "CONTRACT"
CLASS_SCREENING = "SCREENING CONTRACT"
CLASS_WORKSHEET = "WORKSHEET"
CLASS_TRAINING = "TRAINING AID"
CLASS_REFERENCE = "REFERENCE-ONLY"
CLASS_NOT_SUPPORTED = "NOT_SUPPORTED"
# M129: leaves whose work is kept as another immutable record - a W13 case would only duplicate it, so none
# is saved (the case bar names the record instead)
RECORDED_ELSEWHERE: Dict[str, str] = {
    "Directional › Multi-Survey": "a survey revision (Save as survey revision on this page)",
    "Directional › Anti-Collision": "a trajectory comparison record (Save on this page; re-run in History)",
}

LEAF_CLASS_MEANING: Dict[str, str] = {
    CLASS_CONTRACT: "a documented calculation with captured inputs, units and method version; cases are re-run and "
                    "verified",
    CLASS_SCREENING: "a simplified screening estimate with a re-runnable contract; not a design value and not an "
                     "approved calculation",
    CLASS_WORKSHEET: "arithmetic on entered values with a re-runnable contract; no engineering model and not a design "
                     "approval",
    CLASS_TRAINING: "a training aid; not an operational well-control procedure (owner decision pending)",
    CLASS_REFERENCE: "a reference catalogue; nothing is computed, so no case can be saved",
    CLASS_NOT_SUPPORTED: "no re-runnable contract yet; cases are stored as captured and are NOT REPRODUCIBLE",
}
# Source-backed: SCREENING / WORKSHEET follow the contract's own ``limits``; TRAINING AID / REFERENCE-ONLY /
# NOT_SUPPORTED are the leaves without a contract (see NOT_SUPPORTED for the exact reasons).
LEAF_CLASSES: Dict[str, str] = {
    "Volume › Quick Calc": CLASS_CONTRACT,
    "Bit Hydraulics › Bit Hydraulics": CLASS_CONTRACT,
    "Bit Hydraulics › TFA Calculator": CLASS_CONTRACT,
    "Well Control › HP  FP": CLASS_CONTRACT,
    "Mud › OWR": CLASS_CONTRACT,
    "Directional › Build/Turn Rate": CLASS_CONTRACT,
    "Mud › Weight/Dilution/Mix": CLASS_CONTRACT,
    "Mud › Mud Lab": CLASS_CONTRACT,
    "CSG/CMT › Cement Volume": CLASS_WORKSHEET,
    "CSG/CMT › Balanced Plug": CLASS_WORKSHEET,
    "Mud › Volume Balance": CLASS_WORKSHEET,
    "CSG/CMT › Buoyancy": CLASS_SCREENING,
    "Well Control › Kick Tolerance": CLASS_SCREENING,
    "Well Control › Pore Press  FG": CLASS_SCREENING,
    "Stuck Pipe": CLASS_SCREENING,
    "Fishing": CLASS_SCREENING,
    "Mud › Rheology": CLASS_SCREENING,
    "Bit Hydraulics › Nozzle Optimization": CLASS_SCREENING,
    "Well Control › Kill Sheet": CLASS_TRAINING,
    "DP Database": CLASS_REFERENCE,
    "Volume › Well Volumes": CLASS_CONTRACT,          # M126
    "Hydraulics": CLASS_SCREENING,                   # M126
    "Weight": CLASS_SCREENING,                       # M127
    "CSG/CMT › Casing Strength": CLASS_SCREENING,    # M127
    "Well Control › Choke Schedule": CLASS_WORKSHEET,     # M128
    "Directional › Multi-Survey": CLASS_NOT_SUPPORTED,
    "Directional › Anti-Collision": CLASS_NOT_SUPPORTED,
}
_CONTRACT_CLASSES = (CLASS_CONTRACT, CLASS_SCREENING, CLASS_WORKSHEET)


def leaf_class(calculator: Optional[str]) -> Tuple[str, str]:
    """(class, meaning) of a W13 leaf; ("UNKNOWN", ...) for a path that is not a classified leaf."""
    cls = LEAF_CLASSES.get(str(calculator or ""))
    if cls is None:
        return "UNKNOWN", "not a classified W13 calculator"
    return cls, LEAF_CLASS_MEANING[cls]


def classification_violations() -> List[str]:
    """Contradictions between the classification and the contract registry (empty when consistent)."""
    out = []
    for calculator, cls in LEAF_CLASSES.items():
        contract = CONTRACTS.get(calculator)
        if (cls in _CONTRACT_CLASSES) != (contract is not None):
            out.append(f"{calculator}: {cls} but {'a' if contract else 'no'} contract")
            continue
        limits = (contract.limits if contract else "").upper()
        if cls == CLASS_SCREENING and "SCREENING" not in limits:
            out.append(f"{calculator}: SCREENING CONTRACT but its limits do not say SCREENING")
        if cls == CLASS_WORKSHEET and "WORKSHEET" not in limits:
            out.append(f"{calculator}: WORKSHEET but its limits do not say WORKSHEET")
        if cls == CLASS_CONTRACT and ("SCREENING" in limits or "WORKSHEET" in limits):
            out.append(f"{calculator}: CONTRACT but its limits say SCREENING/WORKSHEET")
        if cls == CLASS_TRAINING and "TRAINING AID" not in NOT_SUPPORTED.get(calculator, ""):
            out.append(f"{calculator}: TRAINING AID without that reason")
    missing = (set(CONTRACTS) | set(NOT_SUPPORTED)) ^ set(LEAF_CLASSES)
    out += [f"{calculator}: not classified or not a leaf" for calculator in sorted(missing)]
    return out


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
    """Inputs by field id - numbers, M107 text and bool fields, plus extras as stored; raises ValueError
    when one is unusable."""
    stored = _field_values(inputs)
    values: Dict[str, Any] = {}
    for spec in contract.inputs:
        if spec.kind == "text":                       # M107: a list entry, stored as its exact text
            text = stored.get(spec.field_id)
            if not (isinstance(text, str) and text.strip()) and spec.required:
                raise ValueError(f"input {spec.field_id} is missing or empty")
            values[spec.field_id] = text if isinstance(text, str) else None
            continue
        if spec.kind == "bool":                       # M107: a check or radio button state
            flag = stored.get(spec.field_id)
            if not isinstance(flag, bool):
                raise ValueError(f"input {spec.field_id} is missing or not a true/false state")
            values[spec.field_id] = flag
            continue
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
    out = {f"contract:{spec.field_id}": {"label": spec.label, "field_id": spec.field_id, "unit": spec.unit,
                                         "value": current.get(spec.field_id), "source": "contract"}
           for spec in contract.results}
    if contract.components is not None:      # M126: the per-component rows behind the totals
        out["contract:components"] = {"label": "Components", "field_id": "components", "unit": "rows",
                                      "value": contract.components(values), "source": "contract"}
    return out


def _rows_differ(stored: Any, current: List[Dict[str, Any]]) -> str:
    """'' when the stored component rows equal the re-run rows (texts exactly, numbers within 1e-9 relative)."""
    if not isinstance(stored, list) or len(stored) != len(current):
        return f"{len(stored) if isinstance(stored, list) else 'no'} stored row(s) vs {len(current)} re-run"
    for n, (old, new) in enumerate(zip(stored, current), 1):
        if not isinstance(old, dict) or set(old) != set(new):
            return f"row {n}: different fields"
        for key, value in new.items():
            a, b = _number(old.get(key)), _number(value)
            if a is not None and b is not None and not isinstance(value, str):
                if abs(a - b) > max(STRUCTURED_REL_TOL * abs(a), 1e-12):
                    return f"row {n} {key}: {a} stored vs {b} re-run"
            elif old.get(key) != value:
                return f"row {n} {key}: {old.get(key)!r} stored vs {value!r} re-run"
    return ""


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
    if contract.components is not None:      # M126
        stored_rows = stored.get("components")
        if stored_rows is None:
            not_compared.append("components")
        else:
            why = _rows_differ(stored_rows, contract.components(values))
            if why:
                differences.append({"field_id": "components", "unit": "rows", "stored": None, "current": None,
                                    "tolerance": STRUCTURED_REL_TOL, "detail": why})
    basis = "relative tolerance 1e-9" if contract.structured else "display rounding"
    return {"status": "DIFFERENT" if differences else "MATCH", "method_matches": True,
            "current_method": f"{contract.method_id} {contract.method_version}",
            "detail": (f"{len(differences)} result(s) outside {basis}" if differences
                       else f"stored results within {basis}")
                      + (f"; not stored, not compared: {', '.join(not_compared)}" if not_compared else ""),
            "values": {k: v for k, v in current.items() if v is not None}, "differences": differences,
            "not_compared": not_compared}
