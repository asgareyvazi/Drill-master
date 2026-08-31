"""Bit / section performance from Daily Report drilling parameters.

Does NOT create a parallel performance system. It turns already-imported
daily-report / bit-record fields into footage, hours, ROP and (when the
inputs exist) MSE, using the canonical engines.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..result import (
    EngineeringResult,
    MissingInputError,
    EngineeringError,
    ok,
    missing,
    failed,
    optional_number,
    require_number,
)
from .mse import MSEEngine


class BitPerformanceEngine:
    METHOD = "Daily Report bit run roll-up"
    SCOPE = "COMPLETE"

    @classmethod
    def from_run(
        cls,
        bit_size_in=None,
        depth_in=None,
        depth_out=None,
        hours_on_bottom=None,
        wob_klbf=None,
        rpm=None,
        torque_ft_lbf=None,
        bit_no=None,
        serial=None,
        dull=None,
        formation=None,
        section=None,
    ) -> EngineeringResult:
        try:
            d_in = optional_number(depth_in, "depth_in")
            d_out = optional_number(depth_out, "depth_out")
            hours = optional_number(hours_on_bottom, "hours_on_bottom")
            size = optional_number(bit_size_in, "bit_size_in")
            if d_in is None or d_out is None:
                raise MissingInputError("depth_in and depth_out")
            footage = d_out - d_in
            if footage < 0:
                raise EngineeringError("depth_out must be ≥ depth_in")
            rop = None
            if hours is not None:
                if hours < 0:
                    raise EngineeringError("hours_on_bottom cannot be negative")
                if hours == 0:
                    rop = None
                else:
                    rop = footage / hours  # m/hr if depths in m

            mse_res = None
            wob = optional_number(wob_klbf, "wob_klbf")
            n = optional_number(rpm, "rpm")
            tq = optional_number(torque_ft_lbf, "torque_ft_lbf")
            if (
                wob is not None
                and n is not None
                and tq is not None
                and size is not None
                and rop is not None
                and rop > 0
            ):
                # depths assumed metres → ROP m/hr → ft/hr
                mse_res = MSEEngine.calculate(
                    wob_lbf=wob * 1000.0,
                    rpm=n,
                    torque_ft_lbf=tq,
                    rop_ft_hr=rop * 3.28084,
                    bit_diameter_in=size,
                )

            values = {
                "bit_no": bit_no,
                "serial": serial,
                "bit_size_in": size,
                "depth_in": d_in,
                "depth_out": d_out,
                "footage": round(footage, 3),
                "hours_on_bottom": hours,
                "rop": None if rop is None else round(rop, 3),
                "wob_klbf": wob,
                "rpm": n,
                "torque_ft_lbf": tq,
                "mse_psi": None if mse_res is None or not mse_res.success else mse_res.value,
                "dull": dull,
                "formation": formation,
                "section": section,
            }
            warnings = []
            if hours is None:
                warnings.append("Hours on bottom missing — ROP not computed")
            if mse_res is not None and not mse_res.success:
                warnings.append(f"MSE not computed: {mse_res.error}")
            return ok(
                values["rop"],
                values=values,
                unit="m/hr" if rop is not None else "",
                formula="footage = depth_out − depth_in; ROP = footage / hours; MSE via Teale",
                method=cls.METHOD,
                assumptions=["Depths in metres, ROP in m/hr, WOB in klbf"],
                warnings=warnings,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def from_daily_params(cls, params: Dict[str, Any], section: str = None) -> EngineeringResult:
        """Map a drilling_params dict (DB / import) onto from_run."""
        if not params:
            return missing("drilling_params")
        wob = params.get("wob_max", params.get("wob"))
        rpm = params.get("rpm_max", params.get("rpm"))
        tq = params.get("torque_max", params.get("torque"))
        # torque in DB is often klb.ft
        tq_n = optional_number(tq, "torque")
        tq_ft_lbf = None if tq_n is None else tq_n * 1000.0
        return cls.from_run(
            bit_size_in=params.get("bit_size"),
            depth_in=params.get("depth_in"),
            depth_out=params.get("depth_out"),
            hours_on_bottom=params.get("hours_on_bottom"),
            wob_klbf=wob,
            rpm=rpm,
            torque_ft_lbf=tq_ft_lbf,
            bit_no=params.get("bit_no"),
            serial=params.get("serial") or params.get("bit_serial"),
            dull=params.get("dull") or params.get("dull_grade"),
            formation=params.get("formation"),
            section=section,
        )

    @classmethod
    def rollup(cls, runs: List[Dict[str, Any]]) -> EngineeringResult:
        if not runs:
            return missing("bit_runs")
        results = [cls.from_daily_params(r) for r in runs]
        footage = 0.0
        hours = 0.0
        for r in results:
            if r.success:
                footage += r.values.get("footage") or 0
                hours += r.values.get("hours_on_bottom") or 0
        avg_rop = footage / hours if hours else None
        return ok(
            avg_rop,
            values={
                "runs": len(results),
                "total_footage": round(footage, 3),
                "total_hours": round(hours, 3),
                "avg_rop": None if avg_rop is None else round(avg_rop, 3),
                "details": [r.values if r.success else {"error": r.error} for r in results],
            },
            unit="m/hr",
            formula="Σ footage / Σ hours",
            method=cls.METHOD,
        )
