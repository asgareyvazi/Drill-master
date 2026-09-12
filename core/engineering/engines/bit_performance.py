"""Bit / section performance from Daily Report drilling parameters.

Does NOT create a parallel performance system. It turns already-imported
daily-report / bit-record fields into footage, hours, ROP and (when the
inputs exist) MSE, using the canonical engines.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Dict, Iterable, List, Optional

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
            if d_in < 0 or d_out < 0:
                raise EngineeringError("depth_in and depth_out cannot be negative")
            if size is not None and size <= 0:
                raise EngineeringError("bit_size_in must be > 0 when supplied")
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
            for name, value in (("wob_klbf", wob), ("rpm", n), ("torque_ft_lbf", tq)):
                if value is not None and value < 0:
                    raise EngineeringError(f"{name} cannot be negative")
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
        if not isinstance(params, dict):
            return failed("drilling_params must be a mapping")
        wob = params.get("wob_max", params.get("wob"))
        rpm = params.get("rpm_max", params.get("rpm"))
        tq = params.get("torque_max", params.get("torque"))
        # Torque in the database is commonly klb.ft; reject malformed source
        # tokens here so the canonical result contract is never bypassed.
        try:
            tq_n = optional_number(tq, "torque")
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))
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

    # ------------------------------------------------------------------
    # Canonical paired footage / weighted ROP
    # ------------------------------------------------------------------
    VALID_PAIR_RULE = (
        "depth_in, depth_out, hours_on_bottom all non-null AND "
        "depth_out >= depth_in AND hours_on_bottom > 0"
    )

    @staticmethod
    def paired_observation(row: Any):
        """Return (footage, hours) for ONE drilling observation iff it forms a
        complete, valid paired ROP observation; otherwise return None.

        A valid pair requires ALL of:
            depth_in is not None AND depth_out is not None
            AND hours_on_bottom is not None
            AND depth_out >= depth_in
            AND hours_on_bottom > 0

        An invalid row contributes NEITHER footage NOR hours — never a partial
        contribution. Explicit zero footage (depth_in == depth_out with
        hours > 0) is a real recorded zero and DOES form a valid pair
        (footage = 0, hours > 0).

        ``row`` may be a mapping (dict / import record) or any object exposing
        ``depth_in`` / ``depth_out`` / ``hours_on_bottom`` attributes (e.g. a
        DrillingParameters ORM row).
        """
        def _get(key):
            if isinstance(row, Mapping):
                return row.get(key)
            return getattr(row, key, None)

        try:
            d_in = optional_number(_get("depth_in"), "depth_in")
            d_out = optional_number(_get("depth_out"), "depth_out")
            hours = optional_number(_get("hours_on_bottom"), "hours_on_bottom")
        except EngineeringError:
            # Malformed / non-numeric source token → not a valid pair.
            return None
        if d_in is None or d_out is None or hours is None:
            return None
        if d_out < d_in:
            return None
        if hours <= 0:
            return None
        return (d_out - d_in, hours)

    @classmethod
    def weighted_rop(cls, runs: Iterable[Any]) -> EngineeringResult:
        """Footage-weighted ROP over a set of drilling observations.

            weighted_rop = Σ(valid-pair footage) / Σ(valid-pair hours)

        Footage and hours are summed from the SAME valid pairs (see
        :meth:`paired_observation`); rows failing the validity gate contribute
        nothing. Returns value ``None`` (never 0) when there are no valid pairs
        or the total valid hours are not positive.

        This is deliberately DISTINCT from:
          * a mean of per-row ROPs (a mean of ratios, statistically wrong), and
          * the naive ``Σ(footage)/Σ(hours)`` taken across independently
            nullable columns, which mispairs footage with unrelated hours.
        """
        rows = list(runs or [])
        total_footage = 0.0
        total_hours = 0.0
        valid = 0
        for row in rows:
            pair = cls.paired_observation(row)
            if pair is None:
                continue
            footage, hours = pair
            total_footage += footage
            total_hours += hours
            valid += 1
        considered = len(rows)
        excluded = considered - valid
        base_values = {
            "weighted_rop": None,
            "total_footage": round(total_footage, 3),
            "total_hours": round(total_hours, 3),
            "valid_pairs": valid,
            "excluded_rows": excluded,
            "observations_considered": considered,
        }
        assumptions = [
            "Depths in metres, hours in hours → ROP in m/hr",
            "Only complete valid pairs contribute; invalid rows excluded whole",
            f"Valid pair: {cls.VALID_PAIR_RULE}",
        ]
        if valid == 0 or total_hours <= 0:
            return ok(
                None,
                values=base_values,
                unit="m/hr",
                formula="weighted_rop = Σ(valid-pair footage) / Σ(valid-pair hours)",
                method=cls.METHOD,
                assumptions=assumptions,
                warnings=[
                    "No valid paired footage/hours observations — "
                    "weighted ROP undefined"
                ],
            )
        wr = total_footage / total_hours
        base_values["weighted_rop"] = round(wr, 3)
        warnings = []
        if excluded:
            warnings.append(
                f"{excluded} of {considered} observation(s) excluded "
                "(incomplete or invalid pair)"
            )
        return ok(
            round(wr, 3),
            values=base_values,
            unit="m/hr",
            formula="weighted_rop = Σ(valid-pair footage) / Σ(valid-pair hours)",
            method=cls.METHOD,
            assumptions=assumptions,
            warnings=warnings,
        )

    @classmethod
    def rollup(cls, runs: List[Dict[str, Any]]) -> EngineeringResult:
        if not runs:
            return missing("bit_runs")
        results = [cls.from_daily_params(r) for r in runs]
        # Aggregate footage and hours from the SAME valid pairs so a row with
        # footage but no/zero hours (or vice-versa) never leaks into only one
        # sum — the classic mispairing that inflates or deflates ROP.
        footage = 0.0
        hours = 0.0
        for r in runs:
            pair = cls.paired_observation(r)
            if pair is None:
                continue
            f, h = pair
            footage += f
            hours += h
        avg_rop = footage / hours if hours else None
        return ok(
            avg_rop,
            values={
                "runs": len(results),
                "total_footage": round(footage, 3),
                "total_hours": round(hours, 3),
                "avg_rop": None if avg_rop is None else round(avg_rop, 3),
                "weighted_rop": None if avg_rop is None else round(avg_rop, 3),
                "details": [r.values if r.success else {"error": r.error} for r in results],
            },
            unit="m/hr",
            formula="weighted_rop = Σ(valid-pair footage) / Σ(valid-pair hours)",
            method=cls.METHOD,
        )

    # ------------------------------------------------------------------
    # d-exponent (pore-pressure detection) — Rehm & McClendon (1971)
    # ------------------------------------------------------------------
    @classmethod
    def d_exponent(
        cls,
        rop_ft_hr,
        rpm,
        wob_lbf,
        bit_size_in,
    ) -> EngineeringResult:
        """d-exponent (Rehm & McClendon, 1971; IADC).

            d = log10( ROP / (60 × RPM) ) / log10( 12 × WOB / (1,000,000 × D) )

        ROP in ft/hr, RPM in rev/min, WOB in lbf, bit size in inches
        (Jorden & Shirley, 1966; equivalent form with WOB in klbf:
        log10(12·WOB_klbf / (1000 × D))).
        d rises with normal compaction; a decreasing d at constant depth
        indicates overpressure (abnormal pore pressure).
        """
        try:
            rop = require_number(rop_ft_hr, "rop_ft_hr")
            r = require_number(rpm, "rpm")
            wob = require_number(wob_lbf, "wob_lbf")
            d = require_number(bit_size_in, "bit_size_in")
            if rop <= 0 or r <= 0 or wob <= 0 or d <= 0:
                raise EngineeringError(
                    "ROP, RPM, WOB and bit size must all be > 0"
                )
            numerator = math.log10(rop / (60.0 * r))
            denominator = math.log10((12.0 * wob) / (1000000.0 * d))
            if abs(denominator) < 1e-9:
                raise EngineeringError(
                    "12×WOB/(10⁶×D) = 1 → log(1) = 0; d-exponent undefined"
                )
            d_exp = numerator / denominator
            return ok(
                round(d_exp, 4),
                values={
                    "d_exponent": round(d_exp, 4),
                    "numerator_log10": round(numerator, 6),
                    "denominator_log10": round(denominator, 6),
                },
                unit="dimensionless",
                formula="d = log10(ROP/(60·RPM)) / log10(12·WOB/(10⁶·D))",
                method="Rehm & McClendon (1971)",
                assumptions=[
                    "ROP in ft/hr, WOB in lbf, bit size in inches",
                    "Jorden & Shirley (1966) form: denominator 12·WOB/(10⁶·D)",
                    "Normal-compaction baseline: d increases with depth",
                    "Decreasing d at constant depth → abnormal pressure",
                ],
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def d_exponent_corrected(
        cls,
        rop_ft_hr,
        rpm,
        wob_lbf,
        bit_size_in,
        mw_ppg,
        normal_mw_ppg=8.6,
    ) -> EngineeringResult:
        """Mud-weight-corrected d-exponent (dc).

            dc = d × (MW_normal / MW_actual)

        The correction removes the drilling-fluid-density effect so pore
        pressure trends can be read from dc directly.
        """
        try:
            base = cls.d_exponent(rop_ft_hr, rpm, wob_lbf, bit_size_in)
            if not base.success:
                return base
            mw = require_number(mw_ppg, "mw_ppg")
            normal = require_number(normal_mw_ppg, "normal_mw_ppg")
            if mw <= 0 or normal <= 0:
                raise EngineeringError("mw_ppg and normal_mw_ppg must be > 0")
            dc = base.values["d_exponent"] * (normal / mw)
            return ok(
                round(dc, 4),
                values={
                    "d_exponent_corrected": round(dc, 4),
                    "d_exponent": base.values["d_exponent"],
                    "mw_ppg": mw,
                    "normal_mw_ppg": normal,
                },
                unit="dimensionless",
                formula="dc = d × (MW_normal / MW_actual)",
                method="Rehm & McClendon (1971), mud-weight corrected",
                assumptions=[
                    "Normal mud weight baseline 8.6 ppg unless provided",
                    "Same units as d_exponent (ROP ft/hr, WOB lbf, D in)",
                ],
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def cost_per_foot(
        cls,
        rig_cost_per_day,
        trip_hours,
        bit_cost,
        footage,
        rotating_hours=None,
    ) -> EngineeringResult:
        """Drilling cost per foot (Bourgoyne, Applied Drilling Engineering).

            C/ft = (C_rig × T_trip + C_bit) / footage

        C_rig in $/day → $/hr via /24; T_trip in hours; C_bit in $;
        footage in ft. If rotating_hours is given, rig cost uses the full
        cycle: C_rig × (T_trip + T_rotating) + C_bit.
        """
        try:
            rig_day = require_number(rig_cost_per_day, "rig_cost_per_day")
            trip = require_number(trip_hours, "trip_hours")
            bit = require_number(bit_cost, "bit_cost")
            ft = require_number(footage, "footage")
            if rig_day < 0 or trip < 0 or bit < 0:
                raise EngineeringError("Costs and hours cannot be negative")
            if ft <= 0:
                raise EngineeringError("Footage must be > 0")
            rig_hour = rig_day / 24.0
            rot = None
            if rotating_hours is not None:
                rot = require_number(rotating_hours, "rotating_hours")
                if rot < 0:
                    raise EngineeringError("rotating_hours cannot be negative")
                total_cost = rig_hour * (trip + rot) + bit
            else:
                total_cost = rig_hour * trip + bit
            cft = total_cost / ft
            return ok(
                round(cft, 2),
                values={
                    "cost_per_ft": round(cft, 2),
                    "total_cost": round(total_cost, 2),
                    "rig_cost_per_hr": round(rig_hour, 2),
                    "trip_hours": trip,
                    "rotating_hours": rot,
                    "footage": ft,
                },
                unit="$/ft",
                formula="C/ft = (C_rig×T_trip + C_bit) / footage",
                method="Bourgoyne et al., Applied Drilling Engineering",
                assumptions=[
                    "Rig cost in $/day, trip time in hours, bit cost in $",
                    "Bit cost includes dull-grading / handling if applicable",
                    "Full-cycle variant adds rotating hours to trip hours",
                ],
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))
