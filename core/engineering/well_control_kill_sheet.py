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

This module keeps the boundary deterministic while distinguishing supplied
measurements from absent geometry. It provides:

* :class:`WellControlKillSheetInputs` — a frozen, Qt-free input object with
  canonical units and immutable drill-string segments.
* :func:`build_canonical_kill_sheet_inputs` — the owner of UI-to-engine unit
  conversion and missing/invalid-input provenance.
* :func:`compute_kill_sheet` — the composite kill-sheet computation. Pressure
  formulas delegate to :class:`WellControlEngine`; volume calculations require
  a complete pipe program and a measured casing-shoe MD before reporting totals.
  Kick-height output is explicitly screening-only when it uses a single local
  bottomhole annular capacity. Missing geometry does not receive a synthetic
  pipe OD or casing/open-hole interval.

The choke schedule remains a 10-interval linear interpolation. These results are
not presented as an API standards-compliance certification; the calculation
scope and geometry assumptions are returned with each result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.hydraulics_engine import AdvancedHydraulicsEngine
from core.engineering.engines.well_control import WellControlEngine

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
    except (TypeError, ValueError, OverflowError):
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
    # Optional casing-shoe measured depth; required for geometry-split annular
    # volume because shoe TVD alone cannot locate the interval on a deviated well.
    shoe_md_ft: Optional[float] = None
    # drill string program (immutable)
    pipes: Tuple[PipeSegment, ...] = ()
    # descriptive echoes of the source display units (NOT consumed by any
    # formula — kept only so a saved snapshot can render the original numbers).
    display: Mapping[str, Any] = field(default_factory=dict)

    # Absence provenance: raw inputs whose value was not recorded. The builder
    # has always substituted 0.0 for its float fields (historical arithmetic is
    # preserved), so without this the engine cannot tell "recorded zero" from
    # "never entered" and a kill sheet could be computed from missing SIDPP/SCR.
    missing_inputs: Tuple[str, ...] = ()
    invalid_inputs: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        d = {
            "tvd_ft": self.tvd_ft,
            "md_ft": self.md_ft,
            "shoe_tvd_ft": self.shoe_tvd_ft,
            "shoe_md_ft": self.shoe_md_ft,
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
            "missing_inputs": list(self.missing_inputs),
            "invalid_inputs": list(self.invalid_inputs),
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
            shoe_md_ft=(float(data["shoe_md_ft"]) if data.get("shoe_md_ft") is not None else None),
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
            missing_inputs=tuple(data.get("missing_inputs", ())),
            invalid_inputs=tuple(data.get("invalid_inputs", ())),
        )


def build_canonical_kill_sheet_inputs(
    *,
    tvd_m: float,
    md_m: float,
    shoe_tvd_m: float,
    shoe_md_m: Optional[float] = None,
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
    invalid_inputs: List[str] = []
    try:
        raw_pipes = tuple(pipes_m or ())
    except TypeError:
        raw_pipes = ()
        invalid_inputs.append("pipes_m must be a sequence of pipe records")
    for index, p in enumerate(raw_pipes):
        if not isinstance(p, Mapping):
            invalid_inputs.append(f"pipes_m[{index}] is not a pipe record")
            continue
        od = _num(p.get("od"))
        pid = _num(p.get("id"))
        length_m = _num(p.get("length"))
        if od is None or pid is None or length_m is None:
            invalid_inputs.append(
                f"pipes_m[{index}] requires finite OD, ID, and length"
            )
            continue
        if od <= 0 or pid <= 0 or length_m <= 0 or pid >= od:
            invalid_inputs.append(
                f"pipes_m[{index}] requires positive length and 0 < ID < OD"
            )
            continue
        seg.append(
            PipeSegment(
                type=str(p.get("type", "")),
                od_in=od,
                id_in=pid,
                length_ft=length_m * FT_PER_M,
            )
        )

    # Inputs the composite computation actually consumes. ``scr1_spm``/
    # ``scr2_spm`` are echo-only display metadata and are deliberately absent.
    required_raw = {
        "tvd_m": tvd_m,
        "md_m": md_m,
        "shoe_tvd_m": shoe_tvd_m,
        "hole_size_in": hole_size_in,
        # Consumed as the annulus in compute_kill_sheet (``csg_id =
        # inp.casing_id_in``, annular loop below): an unfilled casing-ID
        # field reaches this builder as None (the widget sentinel reads
        # back as None) and must refuse, not drop the annular volume.
        "casing_id_in": casing_id_in,
        "mw_pcf": mw_pcf,
        "frac_gradient_psi_ft": frac_gradient_psi_ft,
        "sidpp_psi": sidpp_psi,
        "sicp_psi": sicp_psi,
        "scr1_psi": scr1_psi,
        "pit_gain_bbl": pit_gain_bbl,
        "pump_output_bbl_stk": pump_output_bbl_stk,
    }
    missing_inputs = tuple(name for name, value in required_raw.items() if _num(value) is None)

    shoe_md = _num(shoe_md_m)
    if shoe_md is not None and (shoe_md < 0 or (_num(md_m) is not None and shoe_md > _num(md_m))):
        invalid_inputs.append("shoe_md_m must be between zero and measured depth")

    display = {
        "tvd_m": tvd_m,
        "md_m": md_m,
        "shoe_tvd_m": shoe_tvd_m,
        "shoe_md_m": shoe_md_m,
        "mw_pcf": mw_pcf,
        "casing_od_in": casing_od_in,
        "casing_id_in": casing_id_in,
        "pipes_m": [
            dict(p) if isinstance(p, Mapping) else {"invalid_record": repr(p)}
            for p in raw_pipes
        ],
    }

    return WellControlKillSheetInputs(
        missing_inputs=missing_inputs,
        invalid_inputs=tuple(invalid_inputs),
        tvd_ft=(_num(tvd_m) or 0.0) * FT_PER_M,
        md_ft=(_num(md_m) or 0.0) * FT_PER_M,
        shoe_tvd_ft=(_num(shoe_tvd_m) or 0.0) * FT_PER_M,
        shoe_md_ft=shoe_md * FT_PER_M if shoe_md is not None else None,
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
    total_string_vol_bbl: Optional[float] = None
    total_ann_vol_bbl: Optional[float] = None
    total_well_vol_bbl: Optional[float] = None
    string_detail: List[Tuple[str, float, float]] = field(default_factory=list)
    ann_detail: List[Tuple[str, float, float]] = field(default_factory=list)
    # strokes
    stk_to_bit: Optional[float] = None
    stk_annular: Optional[float] = None
    stk_total: Optional[float] = None
    # kick geometry
    kick_type: str = "n/a (enter pit gain + drill string)"
    kick_height_ft: Optional[float] = None
    kick_note: str = ""
    # schedule: list of (strokes, pressure_psi, pct_complete)
    choke_schedule: List[Tuple[int, float, int]] = field(default_factory=list)
    # provenance
    method: str = ""
    engine_method: str = WellControlEngine.METHOD
    warnings: List[str] = field(default_factory=list)
    scope: str = "NOT_ASSESSED"
    geometry_assumption_used: bool = False
    assumptions: List[str] = field(default_factory=list)

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
            "scope": self.scope,
            "geometry_assumption_used": self.geometry_assumption_used,
            "assumptions": list(self.assumptions),
        }

    # Correctness-relevant projection of the WHOLE result (mission §12/§13/§14).
    # This is what a persisted historical claim stores and what whole-result
    # verification compares. It deliberately EXCLUDES presentation/diagnostic
    # metadata (success/error/method/engine_method/warnings/kick_note, and the
    # human-facing kick_type label) so the shared engine-agnostic
    # ``deep_numeric_diff`` sees exactly the numeric/structural engineering
    # answer. Every scalar, both nested detail lists and the choke schedule are
    # included, so a single changed correctness value cannot hide behind a
    # summary-only MATCH (the T&D false-MATCH lesson).
    _CORRECTNESS_KEYS = (
        "kill_mw_ppg", "kill_mw_pcf", "mw_ppg", "mw_pcf",
        "mw_increase_ppg", "mw_increase_pcf",
        "icp_psi", "fcp_psi", "maasp_psi",
        "total_string_vol_bbl", "total_ann_vol_bbl", "total_well_vol_bbl",
        "string_detail", "ann_detail",
        "stk_to_bit", "stk_annular", "stk_total",
        "kick_height_ft", "choke_schedule",
    )

    @property
    def values(self) -> Dict[str, Any]:
        """Whole correctness-relevant result (verification-core protocol).

        Named ``values`` and paired with ``success``/``error`` so a
        :class:`KillSheetResult` satisfies the exact duck-typed protocol the
        shared ``classify_verification`` consumes — enabling reuse of the generic
        verifier with NO Well-Control-specific branches (mission §47).
        """
        d = self.as_dict()
        return {k: d[k] for k in self._CORRECTNESS_KEYS}


# error sentinels so a caller (or a snapshot) can classify failure without
# string-matching (mission §26)
KILL_INPUT_INVALID = "INPUT_INVALID"
KILL_ENGINE_FAILED = "ENGINE_FAILED"


def compute_kill_sheet(inp: WellControlKillSheetInputs) -> KillSheetResult:
    """Composite kill-sheet computation over canonical, provenance-aware inputs.

    The kill-weight, ICP/FCP, MAASP, kick classification, and schedule logic
    delegate to the existing well-control engine or its documented screening
    interpolation. Geometry-dependent totals require an MD-positioned pipe and
    casing/open-hole program; unsupported totals remain ``None``.
    """
    A = AdvancedHydraulicsEngine
    WC = WellControlEngine

    if inp.missing_inputs:
        # A kill sheet computed from absent kick data looks plausible and is
        # wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.
        return KillSheetResult(
            success=False,
            error=(f"{KILL_INPUT_INVALID}: missing required kill-sheet inputs: "
                   + ", ".join(inp.missing_inputs)),
        )
    if inp.invalid_inputs:
        return KillSheetResult(
            success=False,
            error=(f"{KILL_INPUT_INVALID}: invalid kill-sheet inputs: "
                   + ", ".join(inp.invalid_inputs)),
        )
    canonical_values = {
        "tvd_ft": inp.tvd_ft,
        "md_ft": inp.md_ft,
        "shoe_tvd_ft": inp.shoe_tvd_ft,
        "hole_size_in": inp.hole_size_in,
        "casing_id_in": inp.casing_id_in,
        "mw_ppg": inp.mw_ppg,
        "frac_gradient_psi_ft": inp.frac_gradient_psi_ft,
        "sidpp_psi": inp.sidpp_psi,
        "sicp_psi": inp.sicp_psi,
        "pit_gain_bbl": inp.pit_gain_bbl,
        "scr1_psi": inp.scr1_psi,
        "pump_output_bbl_stk": inp.pump_output_bbl_stk,
    }
    bad_values = [name for name, value in canonical_values.items()
                  if _num(value) is None]
    for index, pipe in enumerate(inp.pipes):
        if (
            _num(pipe.od_in) is None or _num(pipe.id_in) is None
            or _num(pipe.length_ft) is None or pipe.od_in <= 0
            or pipe.id_in <= 0 or pipe.id_in >= pipe.od_in
            or pipe.length_ft <= 0
        ):
            bad_values.append(f"pipes[{index}] geometry")
    if bad_values:
        return KillSheetResult(
            success=False,
            error=(f"{KILL_INPUT_INVALID}: invalid canonical values: "
                   + ", ".join(bad_values)),
        )
    negative_values = [
        name for name, value in {
            "sidpp_psi": inp.sidpp_psi,
            "sicp_psi": inp.sicp_psi,
            "pit_gain_bbl": inp.pit_gain_bbl,
            "scr1_psi": inp.scr1_psi,
            "pump_output_bbl_stk": inp.pump_output_bbl_stk,
        }.items()
        if value < 0
    ]
    if negative_values:
        return KillSheetResult(
            success=False,
            error=(f"{KILL_INPUT_INVALID}: values cannot be negative: "
                   + ", ".join(negative_values)),
        )

    mw_ppg = inp.mw_ppg
    mw_pcf = mw_ppg * PCF_PER_PPG
    sidpp = inp.sidpp_psi
    sicp = inp.sicp_psi
    frac_grad = inp.frac_gradient_psi_ft
    pit_gain = inp.pit_gain_bbl
    scr1 = inp.scr1_psi
    pump_output = inp.pump_output_bbl_stk
    # --- string + annular volumes (canonical bbl/ft x ft) ------------------
    total_string_vol = 0.0
    total_ann_vol = 0.0
    string_detail: List[Tuple[str, float, float]] = []
    ann_detail: List[Tuple[str, float, float]] = []

    annulus_assessable = bool(inp.pipes)
    for p in inp.pipes:
        capacity = A.calc_pipe_capacity_bbl_ft(p.id_in) * p.length_ft
        total_string_vol += capacity
        string_detail.append((p.type, p.length_ft / FT_PER_M, capacity))

    pipe_program_ft = sum(p.length_ft for p in inp.pipes)
    pipe_geometry_available = bool(inp.pipes) and abs(pipe_program_ft - inp.md_ft) <= 1.0
    annulus_assessable = (
        pipe_geometry_available
        and inp.shoe_md_ft is not None
        and 0 <= inp.shoe_md_ft <= inp.md_ft
        and inp.hole_size_in > 0
        and inp.casing_id_in > 0
    )
    if annulus_assessable:
        depth_top_ft = 0.0
        for p in inp.pipes:
            depth_bottom_ft = depth_top_ft + p.length_ft
            cased_length = max(0.0, min(depth_bottom_ft, inp.shoe_md_ft) - depth_top_ft)
            open_length = max(0.0, depth_bottom_ft - max(depth_top_ft, inp.shoe_md_ft))
            for zone_name, ann_id, zone_length in (
                ("CSG", inp.casing_id_in, cased_length),
                ("Open hole", inp.hole_size_in, open_length),
            ):
                if zone_length <= 0:
                    continue
                if ann_id <= p.od_in:
                    annulus_assessable = False
                    break
                volume = A.calc_annular_capacity_bbl_ft(ann_id, p.od_in) * zone_length
                total_ann_vol += volume
                ann_detail.append((f"{p.type} in {zone_name}", zone_length / FT_PER_M, volume))
            if not annulus_assessable:
                break
            depth_top_ft = depth_bottom_ft

    # --- kill weight (engine) ---------------------------------------------
    kmw_r = WC.kill_mw(mw_ppg, sidpp, inp.tvd_ft)
    if not kmw_r.success:
        return KillSheetResult(success=False, error=f"{KILL_ENGINE_FAILED}: {kmw_r.error}")
    kmw_ppg = kmw_r.value
    kmw_pcf = kmw_ppg * PCF_PER_PPG

    # ICP / FCP — single-owner formulas (WellControlEngine), same values as the
    # historical inline arithmetic (icp = scr1 + sidpp; fcp = scr1·kmw/mw).
    icp = WC.calculate_icp(scr1, sidpp)
    if mw_ppg <= 0:
        return KillSheetResult(
            success=False, error=f"{KILL_INPUT_INVALID}: positive mud weight"
        )
    fcp = WC.calculate_fcp(scr1, kmw_ppg, mw_ppg)

    # --- MAASP (engine) ----------------------------------------------------
    maasp_r = WC.maasp(
        max_allowable_mw_ppg=frac_grad / PSI_PER_PPG_FT if frac_grad else None,
        current_mw_ppg=mw_ppg,
        shoe_tvd_ft=inp.shoe_tvd_ft,
    )
    if not maasp_r.success:
        return KillSheetResult(success=False, error=f"{KILL_ENGINE_FAILED}: {maasp_r.error}")
    maasp = maasp_r.value

    # Volumes are totals only when the entered pipe program reaches MD and the
    # annular geometry is located by an explicitly supplied shoe MD. TVD cannot
    # substitute for shoe MD in a directional/horizontal well.
    string_volume = total_string_vol if pipe_geometry_available else None
    annular_volume = total_ann_vol if annulus_assessable else None
    well_volume = (
        total_string_vol + total_ann_vol
        if pipe_geometry_available and annulus_assessable else None
    )

    warnings: List[str] = []
    if not inp.pipes:
        warnings.append(
            "Drill-string geometry is missing; string/annular volumes and "
            "pipe-dependent strokes are not assessed."
        )
    elif not pipe_geometry_available:
        warnings.append(
            "Pipe program length does not match measured depth; total string "
            "volume and pipe-dependent strokes are not assessed."
        )
    if pipe_geometry_available and not annulus_assessable:
        warnings.append(
            "Total annular volume is not assessed: a valid shoe measured depth, "
            "casing ID, hole size, and positive clearance for every interval are required."
        )

    # --- strokes -----------------------------------------------------------
    stk_to_bit = string_volume / pump_output if string_volume is not None and pump_output > 0 else None
    stk_annular = annular_volume / pump_output if annular_volume is not None and pump_output > 0 else None
    stk_total = stk_to_bit + stk_annular if stk_to_bit is not None and stk_annular is not None else None
    if pump_output <= 0:
        warnings.append("Pump output must be positive; pump strokes are not assessed.")

    # --- kick height / type (engine kick_volume) ---------------------------
    kick_type = "NOT ASSESSED" if pit_gain > 0 else "n/a (no positive pit gain)"
    kick_height = 0.0 if pit_gain == 0 else None
    kick_note = ""
    geometry_assumption_used = False
    assumptions: List[str] = []
    if pit_gain > 0 and pipe_geometry_available and annulus_assessable:
        bottom_pipe = inp.pipes[-1]
        bottom_annulus_id = inp.hole_size_in if inp.md_ft > inp.shoe_md_ft else inp.casing_id_in
        ann_cap_ft = A.calc_annular_capacity_bbl_ft(bottom_annulus_id, bottom_pipe.od_in)
        if ann_cap_ft > 0:
            kv = WC.kick_volume(
                pit_gain_bbl=pit_gain,
                annular_capacity_bbl_ft=ann_cap_ft,
                mw_ppg=mw_ppg,
                sidpp_psi=sidpp,
                sicp_psi=sicp,
            )
            if kv.success and kv.values.get("kick_height_ft") is not None:
                kick_height = kv.values["kick_height_ft"]
                kind = kv.values.get("kick_type")
                kick_type = {
                    "gas": "Gas Kick",
                    "oil": "Oil Kick",
                    "oil_or_condensate": "Oil Kick",
                    "salt_water": "Salt Water Kick",
                    "saltwater": "Salt Water Kick",
                }.get(kind, "Unknown")
                geometry_assumption_used = True
                assumption = (
                    "Kick-height screening uses the supplied bottommost pipe and "
                    "annular interval as a uniform local capacity; influx spanning "
                    "multiple intervals is not modeled."
                )
                assumptions.append(assumption)
                kick_note = f" ⚠ SCREENING: {assumption}"
                warnings.append(assumption)
                if kv.warnings:
                    warnings.extend(kv.warnings)
            else:
                warning = (
                    "Kick-height/type calculation was not successful: "
                    f"{getattr(kv, 'error', '') or 'no finite height returned'}."
                )
                warnings.append(warning)
                kick_note = f" ⚠ {warning}"
        else:
            warnings.append("Kick height/type is not assessed because bottomhole clearance is nonpositive.")
    elif pit_gain > 0:
        warning = (
            "Kick height/type is not assessed because complete drill-string and "
            "casing-shoe measured-depth geometry was not supplied."
        )
        warnings.append(warning)
        kick_note = f" ⚠ {warning}"

    # --- choke schedule (linear ICP -> FCP) --------------------------------
    schedule: List[Tuple[int, float, int]] = []
    intervals = CHOKE_SCHEDULE_INTERVALS
    if stk_to_bit is not None and stk_to_bit > 0:
        step = stk_to_bit / intervals
        dp = (icp - fcp) / intervals
        for i in range(intervals + 1):
            strokes = round(i * step)
            pressure = round(icp - i * dp, 1)
            schedule.append((strokes, pressure, round(i / intervals * 100)))

    scope = (
        "SCREENING" if geometry_assumption_used
        else "PARTIAL" if warnings else "COMPLETE"
    )
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
        total_string_vol_bbl=string_volume,
        total_ann_vol_bbl=annular_volume,
        total_well_vol_bbl=well_volume,
        string_detail=string_detail if pipe_geometry_available else [],
        ann_detail=ann_detail if annulus_assessable else [],
        stk_to_bit=stk_to_bit,
        stk_annular=stk_annular,
        stk_total=stk_total,
        kick_type=kick_type,
        kick_height_ft=kick_height,
        kick_note=kick_note,
        choke_schedule=schedule,
        method=inp.method,
        warnings=warnings,
        scope=scope,
        geometry_assumption_used=geometry_assumption_used,
        assumptions=assumptions,
    )
