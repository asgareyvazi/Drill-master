"""M126: the W13 ``Hydraulics`` page as a re-runnable SCREENING contract.

One function configures ``AdvancedHydraulicsEngine`` from the page values - used by the page itself
(``_hy_collect``) and by the case contract - so a saved case re-runs exactly what was on screen. Rows are the
page tables as entered (pumps: name/output_bbl_stk/spm; pipes from the surface down: type/od/id/length/weight;
bore: type/od/id/from/to; nozzles: size (1/32 in)/qty). An unreadable row is kept as an invalid row so the
engine refuses the program instead of calculating with the rest.

The engine is SCREENING (Bingham / Power Law; Herschel-Bulkley refused). ECD is reported only when the engine
assessed it: a non-vertical profile needs measured survey TVD, which this page does not supply, so ECD (and
the whole run) is NOT ASSESSED there - no TVD is derived from KOP / build rate.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

METHOD_ID = "w13.hydraulics.circulating_system"
METHOD_VERSION = "M126 circulating-system hydraulics v1"
GAL_PER_BBL = 42.0
MODELS = {"Bingham Plastic": "bingham", "Power Law": "power_law", "Herschel-Bulkley (unsupported)": "herschel_bulkley"}
PROFILES = {"Vertical": "vertical", "Directional": "directional", "Horizontal": "horizontal", "S-Shape": "s_shape"}
RESULT_FIELDS = ("flow_rate_gpm", "surface_loss_psi", "string_loss_psi", "bit_loss_psi", "annular_loss_psi",
                 "total_loss_psi", "ecd_at_bit_ppg", "ecd_at_shoe_ppg", "tfa_in2", "bit_hhp", "hsi",
                 "jet_velocity_fps", "impact_force_lbs", "percent_bit_hp", "critical_flow_rate_gpm")


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def flow_rate_gpm(pumps: List[Dict[str, Any]]) -> float:
    """Sum of output x SPM x 42 over the pump rows (the page's ``_hy_get_total_gpm``)."""
    return sum((_num(p.get("output_bbl_stk")) or 0.0) * (_num(p.get("spm")) or 0.0) * GAL_PER_BBL
               for p in pumps or ())


def configure(engine, values: Dict[str, Any]) -> None:
    """Load the page values into ``engine`` (an ``AdvancedHydraulicsEngine``)."""
    from core.hydraulics_engine import (BitNozzle, CasingSection, MudProperties, PipeSegment, SurfaceEquipment,
                                        WellProfile)

    engine.flow_rate_gpm = flow_rate_gpm(values.get("pumps") or [])
    engine.bit_depth_m = values.get("bit_depth")
    engine.bit_diameter_in = values.get("bit_diameter")
    engine.model = MODELS.get(str(values.get("model") or ""), f"unsupported:{values.get('model')}")
    engine.mud = MudProperties(mw_pcf=values.get("mw"), pv=values.get("pv"), yp=values.get("yp"),
                               theta600=values.get("t600"), theta300=values.get("t300"),
                               theta6=values.get("t6"), theta3=values.get("t3"))
    engine.surface_equipment = SurfaceEquipment(
        standpipe_length_m=values.get("standpipe_length"), standpipe_id_inch=values.get("standpipe_id"),
        hose_length_m=values.get("hose_length"), hose_id_inch=values.get("hose_id"))
    engine.pipe_segments = []
    for n, row in enumerate(values.get("pipes") or [], 1):
        od, inner, length = _num(row.get("od")), _num(row.get("id")), _num(row.get("length"))
        if od is None or inner is None or length is None:
            engine.pipe_segments.append(PipeSegment(name=f"Unparsed pipe row {n}"))
            continue
        engine.pipe_segments.append(PipeSegment(
            name=f"{row.get('type', '')} ({od:.3f}\\\")", pipe_type=str(row.get("type", "")), od=od, id=inner,
            length=length, weight_ppf=_num(row.get("weight")) or 0.0))
    engine.casing_sections = []
    for n, row in enumerate(values.get("casings") or [], 1):
        od, inner = _num(row.get("od")), _num(row.get("id"))
        top, bottom = _num(row.get("from")), _num(row.get("to"))
        if None in (od, inner, top, bottom):
            engine.casing_sections.append(CasingSection(name=f"Unparsed bore row {n}"))
            continue
        kind = "open_hole" if "Open" in str(row.get("type", "")) else "casing"
        engine.casing_sections.append(CasingSection(name=str(row.get("type", "")), section_type=kind, od=od,
                                                    id=inner, top_md=top, bottom_md=bottom))
    engine.nozzles = []
    for row in values.get("nozzles") or []:
        size, qty = row.get("size"), row.get("qty")
        if isinstance(size, int) and not isinstance(size, bool) and isinstance(qty, int) and not isinstance(qty, bool):
            engine.nozzles.append(BitNozzle(size_32nds=size, quantity=qty))
        else:
            engine.nozzles.append(BitNozzle())
    engine.well_profile = WellProfile(
        well_type=PROFILES.get(str(values.get("well_type") or ""), f"unsupported:{values.get('well_type')}"),
        kop_md=values.get("kop") or 0.0, eob_md=values.get("eob") or 0.0, eob_inc=values.get("max_inc") or 0.0,
        build_rate=values.get("build_rate") or 0.0)


def run(values: Dict[str, Any]):
    """Configure a fresh engine and calculate; returns the ``HydraulicsResult``."""
    from core.hydraulics_engine import AdvancedHydraulicsEngine

    engine = AdvancedHydraulicsEngine()
    configure(engine, values)
    return engine.calculate()


def scalar_results(result) -> Dict[str, Optional[float]]:
    """The headline numbers of an assessed run (component sums from the engine's own rows)."""
    pipe = [loss for _name, loss in result.pipe_losses]
    annulus = [loss for _name, loss in result.annulus_losses]
    return {"flow_rate_gpm": result.flow_rate_gpm, "surface_loss_psi": result.surface_loss_psi,
            "string_loss_psi": sum(pipe) if pipe else None, "bit_loss_psi": result.bit_loss_psi,
            "annular_loss_psi": sum(annulus) if annulus else None, "total_loss_psi": result.total_loss_psi,
            "ecd_at_bit_ppg": result.ecd_at_bit_ppg, "ecd_at_shoe_ppg": result.ecd_at_shoe_ppg,
            "tfa_in2": result.tfa_in2, "bit_hhp": result.bit_hhp, "hsi": result.hsi,
            "jet_velocity_fps": result.jet_velocity_fps, "impact_force_lbs": result.impact_force_lbs,
            "percent_bit_hp": result.percent_bit_hp, "critical_flow_rate_gpm": result.critical_flow_rate_gpm}


def component_rows(result) -> List[Dict[str, Any]]:
    """Per-component pressure losses with velocity and flow regime, in engine order.

    The engine appends loss, velocity and regime for each (component, bore) overlap together but names
    them differently, so the rows are paired by position, never by name."""
    rows = [{"kind": "pipe", "name": name, "loss_psi": loss, "velocity_ft_min": velocity, "regime": regime}
            for (name, loss), (_v, velocity), (_r, regime)
            in zip(result.pipe_losses, result.pipe_velocities, result.flow_regimes_pipe, strict=True)]
    rows += [{"kind": "annulus", "name": name, "loss_psi": loss, "velocity_ft_min": velocity, "regime": regime}
             for (name, loss), (_v, velocity), (_r, regime)
             in zip(result.annulus_losses, result.annular_velocities, result.flow_regimes_annulus, strict=True)]
    if result.surface_loss_psi is not None:
        rows.insert(0, {"kind": "surface", "name": result.surface_loss_method or "surface", "loss_psi":
                        result.surface_loss_psi, "velocity_ft_min": None, "regime": None})
    if result.bit_loss_psi is not None:
        rows.append({"kind": "bit", "name": "bit nozzles", "loss_psi": result.bit_loss_psi, "velocity_ft_min":
                     result.jet_velocity_fps, "regime": None})
    return rows
