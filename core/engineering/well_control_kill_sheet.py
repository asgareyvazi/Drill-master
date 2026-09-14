"""Canonical, Qt-free input boundary + composite computation for the Well
Control **kill sheet** (mission 7).

Why this module exists
----------------------
Unlike Torque & Drag, Casing and Cement — each of which is a *single* engine
call whose ``EngineeringResult`` already is the complete answer — the kill sheet
is a **composite** calculation. The historical W13 handler
``_wc_calc_kill`` did four things that a snapshot-ready boundary must not leave
buried inside a Qt widget method (mission §5/§6/§8):

1. **Unit conversions** performed inline before any engine call
   (m → ft ``× 3.28084``; pcf → ppg ``÷ 7.48``; fracture gradient
   ``psi/ft`` → max-allowable MW ``÷ 0.052``).
2. **Drill-string / annular volume** aggregation over a *mutable* pipe list,
   using the canonical hydraulics capacity formulas.
3. **Derived kill parameters that have no engine home** — ICP
   (``SCR + SIDPP``), FCP (``SCR × KillMW / MW``) and pump strokes
   (``volume ÷ pump output``).
4. A **choke pressure schedule** (linear ICP → FCP interpolation).

Only ``kill_mw``, ``maasp`` and ``kick_volume`` were actual
``WellControlEngine`` calls. Everything else was engineering logic living in the
UI layer, i.e. the *real* input boundary was the handler, not the engine.

This module makes the boundary honest and deterministic **without changing a
single formula, constant, unit factor or safety cut-off** (mission primary
directive). It provides:

* :class:`WellControlKillSheetInputs` — a frozen, Qt-free canonical-unit input
  object (mission §11). It captures the *exact* values consumed by the
  computation, already in canonical oilfield units, plus the immutable pipe
  program as a tuple of plain :class:`PipeSegment` records.
* :func:`build_canonical_kill_sheet_inputs` — the **single owner** of every
  raw→canonical unit conversion (mission §9). Handlers hand it raw UI numbers in
  their native display units; nothing else in the stack converts units.
* :func:`compute_kill_sheet` — the relocated composite computation. It reproduces
  the handler's arithmetic byte-for-byte (verified by regression tests) and
  returns a complete, serializable :class:`KillSheetResult`.

The formulas, the "simplified annulus" assumption (annulus always uses the last
casing ID), the linear 10-interval choke schedule and every numeric constant are
preserved verbatim from the original handler. This module deliberately does NOT
"fix" the simplified annulus or any other pre-existing modelling choice; doing so
would change results and violate the mission's no-formula-change rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.hydraulics_engine import AdvancedHydraulicsEngine
from core.engineering.engines.well_control import WellControlEngine
from core.engineering.result import EngineeringResult

# --- canonical unit conversion constants (single source, mission §9) --------
# These are the EXACT factors the historical handler used inline. They live here
# now so there is one and only one place that converts UI units to canonical
# oilfield units. Changing any of these changes results, so they are frozen.
FT_PER_M = 3.28084          # metres  -> feet
PCF_PER_PPG = 7.48          # ppg = pcf / 7.48   (pounds/ft^3 -> lb/gal)
PSI_PER_PPG_FT = 0.052      # oilfield hydrostatic constant

DRILLERS_METHOD = "Driller's"
WAIT_AND_WEIGHT_METHOD = "Wait & Weight"

CHOKE_SCHEDULE_INTERVALS = 10  # historical fixed granularity


def _num(value: Any) -> Optional[float]:
    """Coerce to a finite, non-bool float or ``None`` (never raises)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


# ---------------------------------------------------------------------------
# Canonical input contract (mission §11 / §12)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PipeSegment:
    """One drill-string segment, canonical units (inches + feet).

    ``length_ft`` is stored in feet — the canonical length the volume formula
    consumes — even though the UI collects metres. Conversion happens once, in
    :func:`build_canonical_kill_sheet_inputs`.
    """

    type: str
    od_in: float
    id_in: float
    length_ft: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "od_in": self.od_in,
            "id_in": self.id_in,
            "length_ft": self.length_ft,
        }


@dataclass(frozen=True)
class WellControlKillSheetInputs:
    """Frozen, Qt-free, canonical-unit inputs for the kill sheet.

    Every field is already in canonical oilfield units (ft, in, ppg, psi, psi/ft,
    bbl, bbl/stroke). There are no widget references and no mutable containers:
    ``pipes`` is a tuple of frozen :class:`PipeSegment`. This is the object a
    snapshot would freeze and a reconstruction would rebuild (mission §11/§17).
    """

    # geometry (canonical: feet / inches)
    tvd_ft: float
    md_ft: float
    shoe_tvd_ft: float
    hole_size_in: float
    casing_id_in: float
    # mud / kick state (canonical: ppg / psi / psi/ft / bbl)
    mw_ppg: float
    frac_gradient_psi_ft: float
    sidpp_psi: float
    sicp_psi: float
    pit_gain_bbl: float
    # pump data
    scr1_psi: float
    scr1_spm: float
    scr2_psi: float
    scr2_spm: float
    pump_output_bbl_stk: float
    # method + descriptive
    method: str
    well_type: str
    # drill string program (immutable)
    pipes: Tuple[PipeSegment, ...] = ()
    # descriptive echoes of the source display units (NOT consumed by any
    # formula — kept only so a saved snapshot can render the original numbers).
    display: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        d = {
            "tvd_ft": self.tvd_ft,
            "md_ft": self.md_ft,
            "shoe_tvd_ft": self.shoe_tvd_ft,
            "hole_size_in": self.hole_size_in,
            "casing_id_in": self.casing_id_in,
            "mw_ppg": self.mw_ppg,
            "frac_gradient_psi_ft": self.frac_gradient_psi_ft,
            "sidpp_psi": self.sidpp_psi,
            "sicp_psi": self.sicp_psi,
            "pit_gain_bbl": self.pit_gain_bbl,
            "scr1_psi": self.scr1_psi,
            "scr1_spm": self.scr1_spm,
            "scr2_psi": self.scr2_psi,
            "scr2_spm": self.scr2_spm,
            "pump_output_bbl_stk": self.pump_output_bbl_stk,
            "method": self.method,
            "well_type": self.well_type,
            "pipes": [p.as_dict() for p in self.pipes],
            "display": dict(self.display),
        }
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WellControlKillSheetInputs":
        pipes = tuple(
            PipeSegment(
                type=str(p.get("type", "")),
                od_in=float(p.get("od_in", 0.0)),
                id_in=float(p.get("id_in", 0.0)),
                length_ft=float(p.get("length_ft", 0.0)),
            )
            for p in data.get("pipes", [])
        )
        return cls(
            tvd_ft=float(data["tvd_ft"]),
            md_ft=float(data["md_ft"]),
            shoe_tvd_ft=float(data["shoe_tvd_ft"]),
            hole_size_in=float(data["hole_size_in"]),
            casing_id_in=float(data["casing_id_in"]),
            mw_ppg=float(data["mw_ppg"]),
            frac_gradient_psi_ft=float(data["frac_gradient_psi_ft"]),
            sidpp_psi=float(data["sidpp_psi"]),
            sicp_psi=float(data["sicp_psi"]),
            pit_gain_bbl=float(data["pit_gain_bbl"]),
            scr1_psi=float(data["scr1_psi"]),
            scr1_spm=float(data["scr1_spm"]),
            scr2_psi=float(data["scr2_psi"]),
            scr2_spm=float(data["scr2_spm"]),
            pump_output_bbl_stk=float(data["pump_output_bbl_stk"]),
            method=str(data["method"]),
            well_type=str(data["well_type"]),
            pipes=pipes,
            display=dict(data.get("display", {})),
        )


def build_canonical_kill_sheet_inputs(
    *,
    tvd_m: float,
    md_m: float,
    shoe_tvd_m: float,
    hole_size_in: float,
    casing_id_in: float,
    casing_od_in: Optional[float] = None,
    mw_pcf: float,
    frac_gradient_psi_ft: float,
    sidpp_psi: float,
    sicp_psi: float,
    pit_gain_bbl: float,
    scr1_psi: float,
    scr1_spm: float,
    scr2_psi: float,
    scr2_spm: float,
    pump_output_bbl_stk: float,
    method: str,
    well_type: str,
    pipes_m: Any = (),
) -> WellControlKillSheetInputs:
    """The **single owner** of raw→canonical unit conversion (mission §9).

    Callers pass raw UI numbers in their native display units:
    depths in metres, mud weight in pounds/ft^3 (pcf), pipe lengths in metres.
    This function applies the exact historical conversion factors ONCE and
    returns a canonical-unit :class:`WellControlKillSheetInputs`. No other layer
    performs unit conversion afterwards.

    ``pipes_m`` accepts the historical mutable pipe dicts (keys ``od``/``id``/
    ``length``/``type`` with length in metres) and freezes them into
    canonical-foot :class:`PipeSegment` records.
    """
    seg: List[PipeSegment] = []
    for p in pipes_m or ():
        od = _num(p.get("od")) or 0.0
        pid = _num(p.get("id")) or 0.0
        length_m = _num(p.get("length")) or 0.0
        seg.append(
            PipeSegment(
                type=str(p.get("type", "")),
                od_in=od,
                id_in=pid,
                length_ft=length_m * FT_PER_M,
            )
        )

    display = {
        "tvd_m": tvd_m,
        "md_m": md_m,
        "shoe_tvd_m": shoe_tvd_m,
        "mw_pcf": mw_pcf,
        "casing_od_in": casing_od_in,
        "pipes_m": [dict(p) for p in (pipes_m or ())],
    }

    return WellControlKillSheetInputs(
        tvd_ft=(_num(tvd_m) or 0.0) * FT_PER_M,
        md_ft=(_num(md_m) or 0.0) * FT_PER_M,
        shoe_tvd_ft=(_num(shoe_tvd_m) or 0.0) * FT_PER_M,
        hole_size_in=_num(hole_size_in) or 0.0,
        casing_id_in=_num(casing_id_in) or 0.0,
        mw_ppg=(_num(mw_pcf) or 0.0) / PCF_PER_PPG,
        frac_gradient_psi_ft=_num(frac_gradient_psi_ft) or 0.0,
        sidpp_psi=_num(sidpp_psi) or 0.0,
        sicp_psi=_num(sicp_psi) or 0.0,
        pit_gain_bbl=_num(pit_gain_bbl) or 0.0,
        scr1_psi=_num(scr1_psi) or 0.0,
        scr1_spm=_num(scr1_spm) or 0.0,
        scr2_psi=_num(scr2_psi) or 0.0,
        scr2_spm=_num(scr2_spm) or 0.0,
        pump_output_bbl_stk=_num(pump_output_bbl_stk) or 0.0,
        method=str(method),
        well_type=str(well_type),
        pipes=tuple(seg),
        display=display,
    )


# ---------------------------------------------------------------------------
# Composite result contract (mission §14)
# ---------------------------------------------------------------------------
@dataclass
class KillSheetResult:
    """Complete, serializable kill-sheet result.

    Classification of members (mission §14):

    * CORRECTNESS  — kill_mw, icp, fcp, maasp, volumes, strokes, kick geometry,
      choke schedule: the engineering answer.
    * DIAGNOSTIC   — ``warnings`` and ``engine`` sub-result echoes.
    * UI-ONLY      — none here; ASCII rendering stays in the handler.
    """

    success: bool
    error: str = ""
    # kill weights
    kill_mw_ppg: float = 0.0
    kill_mw_pcf: float = 0.0
    mw_ppg: float = 0.0
    mw_pcf: float = 0.0
    mw_increase_ppg: float = 0.0
    mw_increase_pcf: float = 0.0
    # pressures
    icp_psi: float = 0.0
    fcp_psi: float = 0.0
    maasp_psi: float = 0.0
    # volumes
    total_string_vol_bbl: float = 0.0
    total_ann_vol_bbl: float = 0.0
    total_well_vol_bbl: float = 0.0
    string_detail: List[Tuple[str, float, float]] = field(default_factory=list)
    ann_detail: List[Tuple[str, float, float]] = field(default_factory=list)
    # strokes
    stk_to_bit: float = 0.0
    stk_annular: float = 0.0
    stk_total: float = 0.0
    # kick geometry
    kick_type: str = "n/a (enter pit gain + drill string)"
    kick_height_ft: float = 0.0
    kick_note: str = ""
    # schedule: list of (strokes, pressure_psi, pct_complete)
    choke_schedule: List[Tuple[int, float, int]] = field(default_factory=list)
    # provenance
    method: str = ""
    engine_method: str = WellControlEngine.METHOD
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "error": self.error,
            "kill_mw_ppg": self.kill_mw_ppg,
            "kill_mw_pcf": self.kill_mw_pcf,
            "mw_ppg": self.mw_ppg,
            "mw_pcf": self.mw_pcf,
            "mw_increase_ppg": self.mw_increase_ppg,
            "mw_increase_pcf": self.mw_increase_pcf,
            "icp_psi": self.icp_psi,
            "fcp_psi": self.fcp_psi,
            "maasp_psi": self.maasp_psi,
            "total_string_vol_bbl": self.total_string_vol_bbl,
            "total_ann_vol_bbl": self.total_ann_vol_bbl,
            "total_well_vol_bbl": self.total_well_vol_bbl,
            "string_detail": [list(x) for x in self.string_detail],
            "ann_detail": [list(x) for x in self.ann_detail],
            "stk_to_bit": self.stk_to_bit,
            "stk_annular": self.stk_annular,
            "stk_total": self.stk_total,
            "kick_type": self.kick_type,
            "kick_height_ft": self.kick_height_ft,
            "kick_note": self.kick_note,
            "choke_schedule": [list(x) for x in self.choke_schedule],
            "method": self.method,
            "engine_method": self.engine_method,
            "warnings": list(self.warnings),
        }


# error sentinels so a caller (or a snapshot) can classify failure without
# string-matching (mission §26)
KILL_INPUT_INVALID = "INPUT_INVALID"
KILL_ENGINE_FAILED = "ENGINE_FAILED"


def compute_kill_sheet(inp: WellControlKillSheetInputs) -> KillSheetResult:
    """Composite kill-sheet computation, relocated verbatim from the handler.

    The arithmetic below is byte-for-byte identical to the historical
    ``_wc_calc_kill`` handler (a regression test asserts equal engine outputs).
    Only its *location* changed: it now consumes a canonical, Qt-free input
    object instead of reading widgets and converting units inline.
    """
    A = AdvancedHydraulicsEngine
    WC = WellControlEngine

    mw_ppg = inp.mw_ppg
    mw_pcf = mw_ppg * PCF_PER_PPG
    sidpp = inp.sidpp_psi
    sicp = inp.sicp_psi
    frac_grad = inp.frac_gradient_psi_ft
    pit_gain = inp.pit_gain_bbl
    scr1 = inp.scr1_psi
    pump_output = inp.pump_output_bbl_stk
    hole = inp.hole_size_in
    csg_id = inp.casing_id_in

    # --- string + annular volumes (canonical bbl/ft x ft) ------------------
    total_string_vol = 0.0
    total_ann_vol = 0.0
    string_detail: List[Tuple[str, float, float]] = []
    ann_detail: List[Tuple[str, float, float]] = []

    for p in inp.pipes:
        od = p.od_in
        id_ = p.id_in
        L_ft = p.length_ft
        ptype = p.type

        cap = A.calc_pipe_capacity_bbl_ft(id_) * L_ft
        total_string_vol += cap
        # detail lengths reported in metres to match the original kill sheet
        string_detail.append((ptype, L_ft / FT_PER_M, cap))

        # Annular (simplified: last casing ID for the whole string) — preserved
        if L_ft > 0:
            ann_id_val = csg_id
            if ann_id_val > od:
                ann = A.calc_annular_capacity_bbl_ft(ann_id_val, od) * L_ft
                total_ann_vol += ann
                ann_detail.append((f"{ptype} in CSG", L_ft / FT_PER_M, ann))

    # --- kill weight (engine) ---------------------------------------------
    kmw_r = WC.kill_mw(mw_ppg, sidpp, inp.tvd_ft)
    if not kmw_r.success:
        return KillSheetResult(success=False, error=f"{KILL_ENGINE_FAILED}: {kmw_r.error}")
    kmw_ppg = kmw_r.value
    kmw_pcf = kmw_ppg * PCF_PER_PPG

    icp = scr1 + sidpp
    if mw_ppg <= 0:
        return KillSheetResult(
            success=False, error=f"{KILL_INPUT_INVALID}: positive mud weight"
        )
    fcp = scr1 * (kmw_ppg / mw_ppg)

    # --- MAASP (engine) ----------------------------------------------------
    maasp_r = WC.maasp(
        max_allowable_mw_ppg=frac_grad / PSI_PER_PPG_FT if frac_grad else None,
        current_mw_ppg=mw_ppg,
        shoe_tvd_ft=inp.shoe_tvd_ft,
    )
    if not maasp_r.success:
        return KillSheetResult(success=False, error=f"{KILL_ENGINE_FAILED}: {maasp_r.error}")
    maasp = maasp_r.value

    # --- strokes -----------------------------------------------------------
    stk_to_bit = total_string_vol / pump_output if pump_output > 0 else 0
    stk_annular = total_ann_vol / pump_output if pump_output > 0 else 0
    stk_total = stk_to_bit + stk_annular

    # --- kick height / type (engine kick_volume) ---------------------------
    kick_type = "n/a (enter pit gain + drill string)"
    kick_height = 0.0
    kick_note = ""
    warnings: List[str] = []
    last_pipe_od = inp.pipes[-1].od_in if inp.pipes else 5
    ann_cap_ft = A.calc_annular_capacity_bbl_ft(hole, last_pipe_od)
    if pit_gain > 0 and ann_cap_ft > 0:
        kv = WC.kick_volume(
            pit_gain_bbl=pit_gain,
            annular_capacity_bbl_ft=ann_cap_ft,
            mw_ppg=mw_ppg,
            sidpp_psi=sidpp,
            sicp_psi=sicp,
        )
        if kv.success:
            kick_height = kv.values.get("kick_height_ft") or 0.0
            kind = kv.values.get("kick_type")
            kick_type = {
                "gas": "Gas Kick",
                "oil": "Oil Kick",
                "oil_or_condensate": "Oil Kick",
                "salt_water": "Salt Water Kick",
                "saltwater": "Salt Water Kick",
            }.get(kind, "Unknown")
            if kv.warnings:
                kick_note = " \u26a0 " + "; ".join(kv.warnings)[:80]
                warnings.extend(kv.warnings)

    # --- choke schedule (linear ICP -> FCP) --------------------------------
    schedule: List[Tuple[int, float, int]] = []
    intervals = CHOKE_SCHEDULE_INTERVALS
    if stk_to_bit > 0:
        step = stk_to_bit / intervals
        dp = (icp - fcp) / intervals
        for i in range(intervals + 1):
            strokes = round(i * step)
            pressure = round(icp - i * dp, 1)
            schedule.append((strokes, pressure, round(i / intervals * 100)))

    return KillSheetResult(
        success=True,
        kill_mw_ppg=kmw_ppg,
        kill_mw_pcf=kmw_pcf,
        mw_ppg=mw_ppg,
        mw_pcf=mw_pcf,
        mw_increase_ppg=kmw_ppg - mw_ppg,
        mw_increase_pcf=kmw_pcf - mw_pcf,
        icp_psi=icp,
        fcp_psi=fcp,
        maasp_psi=maasp,
        total_string_vol_bbl=total_string_vol,
        total_ann_vol_bbl=total_ann_vol,
        total_well_vol_bbl=total_string_vol + total_ann_vol,
        string_detail=string_detail,
        ann_detail=ann_detail,
        stk_to_bit=stk_to_bit,
        stk_annular=stk_annular,
        stk_total=stk_total,
        kick_type=kick_type,
        kick_height_ft=kick_height,
        kick_note=kick_note,
        choke_schedule=schedule,
        method=inp.method,
        warnings=warnings,
    )
