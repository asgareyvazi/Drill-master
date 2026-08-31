"""Canonical Mechanical Specific Energy (Teale).

MSE (psi) = WOB/Ab + (120π × RPM × T) / (Ab × ROP)

Oilfield units:
  WOB     lbf
  Ab      in²  = π/4 × D_bit²
  RPM     rev/min
  T       ft·lbf
  ROP     ft/hr
  MSE     psi

Reference: Teale (1965); Dupriest & Koederitz SPE 92194.
The theoretically consistent conversion of 2πNT/AR in these units is 120π ≈ 376.99,
NOT the rounded 480 that appears in some field spreadsheets (480 assumes different units).
"""
from __future__ import annotations

import math

from ..result import (
    EngineeringResult,
    MissingInputError,
    EngineeringError,
    ok,
    missing,
    failed,
    require_number,
)

TEALE_120_PI = 120.0 * math.pi  # 376.991118...


class MSEEngine:
    METHOD = "Teale (1965) Mechanical Specific Energy"
    SCOPE = "COMPLETE"

    @classmethod
    def calculate(
        cls,
        wob_lbf,
        rpm,
        torque_ft_lbf,
        rop_ft_hr,
        bit_diameter_in,
    ) -> EngineeringResult:
        try:
            wob = require_number(wob_lbf, "wob_lbf")
            n = require_number(rpm, "rpm")
            tq = require_number(torque_ft_lbf, "torque_ft_lbf")
            rop = require_number(rop_ft_hr, "rop_ft_hr")
            d = require_number(bit_diameter_in, "bit_diameter_in")
            if wob < 0 or n < 0 or tq < 0:
                raise EngineeringError("WOB, RPM and torque cannot be negative")
            if d <= 0:
                raise EngineeringError("bit_diameter_in must be > 0")
            if rop <= 0:
                raise EngineeringError("rop_ft_hr must be > 0 (zero ROP makes MSE undefined)")

            area = math.pi / 4.0 * d * d
            axial = wob / area
            rotary = (TEALE_120_PI * n * tq) / (area * rop)
            mse = axial + rotary
            values = {
                "mse_psi": round(mse, 1),
                "axial_term_psi": round(axial, 1),
                "rotary_term_psi": round(rotary, 1),
                "bit_area_in2": round(area, 4),
                "wob_lbf": wob,
                "rpm": n,
                "torque_ft_lbf": tq,
                "rop_ft_hr": rop,
                "bit_diameter_in": d,
            }
            return ok(
                round(mse, 1),
                values=values,
                unit="psi",
                formula="MSE = WOB/Ab + (120π × RPM × T) / (Ab × ROP)",
                method=cls.METHOD,
                assumptions=[
                    "Teale MSE in oilfield units (WOB lbf, T ft·lbf, ROP ft/hr, D in)",
                    "120π conversion (not the 480 spreadsheet constant)",
                    "Surface WOB and torque — no downhole correction, no MSE efficiency factor",
                ],
                metadata={"constant_120pi": TEALE_120_PI},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))
