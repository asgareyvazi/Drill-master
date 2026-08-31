"""Canonical cement job-volume / hydrostatic worksheet.

COMPLETE as a volume + stacked-hydrostatic calculator.
NOT a laboratory cement design engine (no thickening time, UCA,
centralization FEM, or gas-migration modelling).
"""
from __future__ import annotations

from typing import List, Optional

from ..result import (
    EngineeringResult,
    MissingInputError,
    EngineeringError,
    ok,
    missing,
    failed,
    require_number,
    optional_number,
)

BBL_PER_CUFT = 5.6146
PSI_PER_PPG_FT = 0.052


def _ann_cap_bbl_ft(hole_in: float, pipe_od_in: float) -> float:
    return (hole_in**2 - pipe_od_in**2) / 1029.4


def _pipe_cap_bbl_ft(id_in: float) -> float:
    return id_in**2 / 1029.4


class CementEngine:
    METHOD = "Oilfield capacity (D²/1029.4) + stacked column hydrostatic"
    SCOPE = "COMPLETE"

    @classmethod
    def displacement(cls, casing_id_in, casing_length_ft, shoe_track_ft=0) -> EngineeringResult:
        try:
            cid = require_number(casing_id_in, "casing_id_in")
            length = require_number(casing_length_ft, "casing_length_ft")
            st = 0.0 if shoe_track_ft in (None, "") else require_number(shoe_track_ft, "shoe_track_ft")
            if cid <= 0 or length < 0:
                raise EngineeringError("Casing ID must be > 0 and length ≥ 0")
            if st < 0:
                raise EngineeringError("Shoe track cannot be negative")
            if st > length:
                raise EngineeringError("Shoe track longer than casing length")
            cap = _pipe_cap_bbl_ft(cid)
            shoe_bbl = cap * st
            disp_bbl = cap * (length - st)
            values = {
                "displacement_volume_bbl": round(disp_bbl, 3),
                "shoe_track_volume_bbl": round(shoe_bbl, 3),
                "total_pump_bbl": round(disp_bbl + shoe_bbl, 3),
            }
            return ok(
                round(disp_bbl, 3),
                values=values,
                unit="bbl",
                formula="Displacement = (ID²/1029.4) × (L − shoe track)",
                method=cls.METHOD,
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def toc_from_volume(
        cls,
        hole_size_in,
        casing_od_in,
        slurry_bbl,
        excess_pct,
        shoe_md_ft,
    ) -> EngineeringResult:
        """TOC MD from annular slurry volume (gauge hole + excess)."""
        try:
            hole = require_number(hole_size_in, "hole_size_in")
            od = require_number(casing_od_in, "casing_od_in")
            vol = require_number(slurry_bbl, "slurry_bbl")
            excess = require_number(excess_pct, "excess_pct")
            shoe = require_number(shoe_md_ft, "shoe_md_ft")
            cap = _ann_cap_bbl_ft(hole, od) * (1.0 + excess / 100.0)
            if cap <= 0:
                raise EngineeringError("Annular capacity must be > 0")
            height = vol / cap
            toc = shoe - height
            return ok(
                round(toc, 2),
                values={
                    "toc_md_ft": round(toc, 2),
                    "cement_height_ft": round(height, 2),
                    "annular_capacity_with_excess_bbl_ft": round(cap, 5),
                },
                unit="ft",
                formula="height = slurry_bbl / [(Dh²−OD²)/1029.4 × (1+excess)]; TOC = shoe − height",
                method=cls.METHOD,
                assumptions=["Gauge hole; excess accounts for washout"],
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def hydrostatic_column(
        cls,
        layers: list,
        *,
        pore_emw_ppg=None,
        shoe_tvd_ft=None,
    ) -> EngineeringResult:
        """Stacked hydrostatic. Each layer: {tvd_ft, density_ppg, name}.

        TVD thickness of each layer is required — MD is not substituted.
        """
        try:
            if not layers:
                raise MissingInputError("layers")
            total = 0.0
            detail = []
            for i, layer in enumerate(layers):
                tvd = require_number(layer.get("tvd_ft"), f"layers[{i}].tvd_ft")
                dens = require_number(layer.get("density_ppg"), f"layers[{i}].density_ppg")
                if tvd < 0 or dens <= 0:
                    raise EngineeringError(f"layers[{i}] TVD ≥ 0 and density > 0")
                dpsi = PSI_PER_PPG_FT * dens * tvd
                total += dpsi
                detail.append({
                    "name": layer.get("name") or f"layer[{i}]",
                    "tvd_ft": tvd,
                    "density_ppg": dens,
                    "psi": round(dpsi, 1),
                })
            overbalance = None
            pore = optional_number(pore_emw_ppg, "pore_emw_ppg")
            shoe_tvd = optional_number(shoe_tvd_ft, "shoe_tvd_ft")
            warnings: List[str] = []
            if pore is not None and shoe_tvd is not None:
                if shoe_tvd <= 0:
                    raise EngineeringError("shoe_tvd_ft must be > 0")
                pp = PSI_PER_PPG_FT * pore * shoe_tvd
                overbalance = total - pp
                if overbalance < 0:
                    warnings.append(f"Underbalance at shoe: hydrostatic {total:.0f} psi < pore {pp:.0f} psi")
            values = {
                "hydrostatic_psi": round(total, 1),
                "layers": detail,
                "overbalance_psi": None if overbalance is None else round(overbalance, 1),
                "pore_pressure_psi": None if (pore is None or shoe_tvd is None) else round(PSI_PER_PPG_FT * pore * shoe_tvd, 1),
            }
            return ok(
                round(total, 1),
                values=values,
                unit="psi",
                formula="Σ 0.052 × MW_i × TVD_i",
                method=cls.METHOD,
                warnings=warnings,
                assumptions=["Each layer TVD is required (MD is not used as TVD)"],
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def job_volumes(
        cls,
        hole_size_in,
        casing_od_in,
        open_hole_length_ft,
        excess_pct,
        casing_id_in=None,
        shoe_track_ft=None,
        toc_md_ft=None,
        shoe_md_ft=None,
        slurry_density_ppg=None,
        yield_ft3_sk=None,
        mix_water_gal_sk=None,
        lead_length_ft=None,
        lead_density_ppg=None,
        lead_yield_ft3_sk=None,
        lead_mix_water_gal_sk=None,
        tail_length_ft=None,
        tail_density_ppg=None,
        tail_yield_ft3_sk=None,
        tail_mix_water_gal_sk=None,
        tvd_column_ft=None,
        spacer_length_ft=None,
        spacer_density_ppg=None,
        mud_density_ppg=None,
        mud_tvd_ft=None,
        spacer_tvd_ft=None,
        lead_tvd_ft=None,
        tail_tvd_ft=None,
        shoe_tvd_ft=None,
        pore_emw_ppg=None,
        pump_rate_bbl_min=None,
    ) -> EngineeringResult:
        try:
            hole = require_number(hole_size_in, "hole_size_in")
            csg_od = require_number(casing_od_in, "casing_od_in")
            length = require_number(open_hole_length_ft, "open_hole_length_ft")
            excess = require_number(excess_pct, "excess_pct")
            if hole <= 0 or csg_od <= 0:
                raise EngineeringError("Hole size and casing OD must be > 0")
            if hole <= csg_od:
                raise EngineeringError("Hole size must be > casing OD")
            if length < 0:
                raise EngineeringError("Open-hole / cement length cannot be negative")
            if excess < 0:
                raise EngineeringError("Excess % cannot be negative")

            csg_id = optional_number(casing_id_in, "casing_id_in")
            shoe_track = optional_number(shoe_track_ft, "shoe_track_ft") or 0.0
            warnings: List[str] = []

            hole_vol_bbl = (hole**2 / 1029.4) * length
            annular_bbl = _ann_cap_bbl_ft(hole, csg_od) * length
            annular_cuft = annular_bbl * BBL_PER_CUFT
            annular_with_excess_bbl = annular_bbl * (1.0 + excess / 100.0)

            casing_cap_bbl = None
            steel_disp_bbl = None
            if csg_id is not None:
                if csg_id <= 0 or csg_id >= csg_od:
                    raise EngineeringError("Casing ID must be > 0 and < OD")
                casing_cap_bbl = _pipe_cap_bbl_ft(csg_id) * length
                steel_disp_bbl = ((csg_od**2 - csg_id**2) / 1029.4) * length

            shoe_track_bbl = 0.0
            if shoe_track > 0:
                if csg_id is None:
                    raise MissingInputError("casing_id_in (required for shoe-track volume)")
                shoe_track_bbl = _pipe_cap_bbl_ft(csg_id) * shoe_track

            spacer_len = optional_number(spacer_length_ft, "spacer_length_ft") or 0.0
            spacer_bbl = _ann_cap_bbl_ft(hole, csg_od) * spacer_len if spacer_len else 0.0

            slurry_bbl = annular_with_excess_bbl + shoe_track_bbl
            slurry_cuft = slurry_bbl * BBL_PER_CUFT

            displacement_bbl = None
            if csg_id is not None:
                disp_len = length - shoe_track
                if disp_len < 0:
                    raise EngineeringError("Shoe track longer than casing/cement length")
                displacement_bbl = _pipe_cap_bbl_ft(csg_id) * disp_len

            yield_v = optional_number(yield_ft3_sk, "yield_ft3_sk")
            mix_w = optional_number(mix_water_gal_sk, "mix_water_gal_sk")
            density = optional_number(slurry_density_ppg, "slurry_density_ppg")
            sacks = None
            mix_water_bbl = None
            if yield_v is not None:
                if yield_v <= 0:
                    raise EngineeringError("Slurry yield must be > 0")
                sacks = slurry_cuft / yield_v
                if mix_w is not None:
                    mix_water_bbl = sacks * mix_w / 42.0
            elif mix_w is not None:
                warnings.append("Mix water given without yield — sacks not computed")

            lead = _slurry_leg(
                "lead", lead_length_ft, hole, csg_od, excess,
                lead_density_ppg, lead_yield_ft3_sk, lead_mix_water_gal_sk,
            )
            tail = _slurry_leg(
                "tail", tail_length_ft, hole, csg_od, excess,
                tail_density_ppg, tail_yield_ft3_sk, tail_mix_water_gal_sk,
            )

            tvd = optional_number(tvd_column_ft, "tvd_column_ft")
            hydrostatic = None
            if density is not None and tvd is not None:
                if tvd <= 0:
                    raise EngineeringError("tvd_column_ft must be > 0")
                hydrostatic = PSI_PER_PPG_FT * density * tvd
            elif density is None and tvd is not None:
                warnings.append("Column TVD given without slurry density — single-fluid hydrostatic not computed")

            layers = []
            mud_tvd = optional_number(mud_tvd_ft, "mud_tvd_ft")
            mud_d = optional_number(mud_density_ppg, "mud_density_ppg")
            if mud_tvd is not None and mud_d is not None:
                layers.append({"name": "mud", "tvd_ft": mud_tvd, "density_ppg": mud_d})
            sp_tvd = optional_number(spacer_tvd_ft, "spacer_tvd_ft")
            sp_d = optional_number(spacer_density_ppg, "spacer_density_ppg")
            if sp_tvd is not None and sp_d is not None:
                layers.append({"name": "spacer", "tvd_ft": sp_tvd, "density_ppg": sp_d})
            ld_tvd = optional_number(lead_tvd_ft, "lead_tvd_ft")
            ld_d = optional_number(lead_density_ppg, "lead_density_ppg")
            if ld_tvd is not None and ld_d is not None:
                layers.append({"name": "lead", "tvd_ft": ld_tvd, "density_ppg": ld_d})
            tl_tvd = optional_number(tail_tvd_ft, "tail_tvd_ft")
            tl_d = optional_number(tail_density_ppg, "tail_density_ppg")
            if tl_tvd is not None and tl_d is not None:
                layers.append({"name": "tail", "tvd_ft": tl_tvd, "density_ppg": tl_d})

            stacked = None
            if layers:
                stacked = cls.hydrostatic_column(
                    layers,
                    pore_emw_ppg=pore_emw_ppg,
                    shoe_tvd_ft=shoe_tvd_ft,
                )
                if stacked.success:
                    hydrostatic = stacked.value
                    warnings.extend(stacked.warnings)
                else:
                    warnings.append(stacked.error)

            pump_rate = optional_number(pump_rate_bbl_min, "pump_rate_bbl_min")
            pump_time = None
            total_pump = slurry_bbl + spacer_bbl + (displacement_bbl or 0.0)
            if pump_rate is not None:
                if pump_rate <= 0:
                    raise EngineeringError("pump_rate_bbl_min must be > 0")
                pump_time = total_pump / pump_rate

            toc = optional_number(toc_md_ft, "toc_md_ft")
            shoe_md = optional_number(shoe_md_ft, "shoe_md_ft")

            values = {
                "hole_volume_bbl": round(hole_vol_bbl, 3),
                "annular_volume_bbl": round(annular_bbl, 3),
                "annular_volume_cuft": round(annular_cuft, 2),
                "annular_with_excess_bbl": round(annular_with_excess_bbl, 3),
                "excess_pct": excess,
                "casing_capacity_bbl": None if casing_cap_bbl is None else round(casing_cap_bbl, 3),
                "steel_displacement_bbl": None if steel_disp_bbl is None else round(steel_disp_bbl, 3),
                "shoe_track_volume_bbl": round(shoe_track_bbl, 3),
                "spacer_volume_bbl": round(spacer_bbl, 3),
                "slurry_volume_bbl": round(slurry_bbl, 3),
                "slurry_volume_cuft": round(slurry_cuft, 2),
                "sacks": None if sacks is None else round(sacks, 1),
                "mix_water_bbl": None if mix_water_bbl is None else round(mix_water_bbl, 3),
                "slurry_density_ppg": density,
                "yield_ft3_sk": yield_v,
                "displacement_volume_bbl": None if displacement_bbl is None else round(displacement_bbl, 3),
                "total_pump_bbl": round(total_pump, 3),
                "pump_time_min": None if pump_time is None else round(pump_time, 2),
                "hydrostatic_psi": None if hydrostatic is None else round(hydrostatic, 1),
                "stacked_hydrostatic": None if stacked is None or not stacked.success else stacked.values,
                "toc_md_ft": toc,
                "shoe_md_ft": shoe_md,
                "lead": lead,
                "tail": tail,
            }
            warnings.append(
                "Job-volume / hydrostatic worksheet — not a laboratory cement design (no UCA, thickening time, gas-migration model)"
            )
            return ok(
                round(slurry_bbl, 3),
                values=values,
                unit="bbl",
                formula="Annulus=(Dh²−OD²)/1029.4×L; slurry=annulus×(1+excess)+shoe track; H=Σ 0.052 MW TVD",
                method=cls.METHOD,
                assumptions=[
                    "Gauge hole (no washout other than the excess %)",
                    "Capacity factor D²/1029.4 bbl/ft",
                    "Yield and mix water must be laboratory / vendor values — not invented",
                    "Stacked hydrostatic uses layer TVD, never MD-as-TVD",
                ],
                warnings=warnings,
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))


def _slurry_leg(name, length_ft, hole, csg_od, excess, density, yield_v, mix_w):
    if length_ft in (None, ""):
        return None
    length = require_number(length_ft, f"{name}_length_ft")
    if length <= 0:
        return None
    vol = _ann_cap_bbl_ft(hole, csg_od) * length * (1.0 + excess / 100.0)
    out = {"length_ft": length, "slurry_bbl": round(vol, 3)}
    d = optional_number(density, f"{name}_density_ppg")
    y = optional_number(yield_v, f"{name}_yield_ft3_sk")
    m = optional_number(mix_w, f"{name}_mix_water_gal_sk")
    if d is not None:
        out["density_ppg"] = d
    if y is not None and y > 0:
        sacks = (vol * BBL_PER_CUFT) / y
        out["sacks"] = round(sacks, 1)
        if m is not None:
            out["mix_water_bbl"] = round(sacks * m / 42.0, 3)
    return out
