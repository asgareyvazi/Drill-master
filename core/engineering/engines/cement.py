"""Canonical cement *volume / job-volume* calculator.

This is NOT a full cement job design engine (no thickening time, UCA,
centralization, gas-migration, or laboratory slurry design).

Supported (PARTIAL — volume calculator):
  hole volume, casing capacity, annular volume, excess, slurry volume,
  density, yield, mix water, lead/tail, TOC, shoe track, displacement,
  hydrostatic of a cement column.
"""
from __future__ import annotations

import math
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

BBL_PER_CUFT = 5.6146  # 1 bbl = 5.6146 ft³
PSI_PER_PPG_FT = 0.052


def _ann_cap_bbl_ft(hole_in: float, pipe_od_in: float) -> float:
    return (hole_in**2 - pipe_od_in**2) / 1029.4


def _pipe_cap_bbl_ft(id_in: float) -> float:
    return id_in**2 / 1029.4


class CementEngine:
    METHOD = "Standard oilfield capacity factors (D²/1029.4 bbl/ft)"
    SCOPE = "PARTIAL"

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

            slurry_bbl = annular_with_excess_bbl + shoe_track_bbl
            slurry_cuft = slurry_bbl * BBL_PER_CUFT

            # Displacement: casing capacity from surface to top of shoe track
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

            # Lead / tail optional split
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
                warnings.append("Column TVD given without slurry density — hydrostatic not computed")

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
                "slurry_volume_bbl": round(slurry_bbl, 3),
                "slurry_volume_cuft": round(slurry_cuft, 2),
                "sacks": None if sacks is None else round(sacks, 1),
                "mix_water_bbl": None if mix_water_bbl is None else round(mix_water_bbl, 3),
                "slurry_density_ppg": density,
                "yield_ft3_sk": yield_v,
                "displacement_volume_bbl": None if displacement_bbl is None else round(displacement_bbl, 3),
                "hydrostatic_psi": None if hydrostatic is None else round(hydrostatic, 1),
                "toc_md_ft": toc,
                "shoe_md_ft": shoe_md,
                "lead": lead,
                "tail": tail,
            }
            warnings.append(
                "PARTIAL: volume / job-volume calculator only — not a cement engineering design engine"
            )
            return ok(
                round(slurry_bbl, 3),
                values=values,
                unit="bbl",
                formula="Annulus=(Dh²−OD²)/1029.4×L; slurry=annulus×(1+excess)+shoe track; sacks=ft³/yield",
                method=cls.METHOD,
                assumptions=[
                    "Gauge hole (no washout other than the excess %)",
                    "Capacity factor D²/1029.4 bbl/ft",
                    "Yield and mix water must be laboratory / vendor values — not invented",
                    "Hydrostatic uses a single slurry density over TVD of the column",
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
