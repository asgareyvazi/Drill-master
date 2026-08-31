"""Canonical casing strength — API TR 5C3 *subset*.

Supported scope (PARTIAL):
  - Internal yield (burst): Barlow with 0.875 wall tolerance  [API 5C3 / 5CT]
  - Collapse: four API 5C3 regimes (yield / plastic / transition / elastic)
    with published A,B,C,F,G coefficients from specified minimum yield
  - Pipe-body yield tension: Yp × cross-section area

NOT implemented (do not claim complete API TR 5C3):
  - Connection ratings (BTC, premium)
  - Axial-stress / combined-load equivalent yield (fyax) collapse derating
  - Internal-pressure collapse adjustment (Addendum)
  - Temperature derating, wear, bending, triaxial von Mises design
  - Load-case envelopes (burst/collapse/tension/compression with design factors
    applied as a full well-design workflow)

Design factors, if supplied, are applied as simple SF = rating / load.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

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


class CasingEngine:
    METHOD = "API TR 5C3 (historical four-regime collapse) + Barlow internal yield"
    SCOPE = "PARTIAL"

    @staticmethod
    def _abc(yp: float):
        """API 5C3 empirical coefficients. Yp in psi."""
        a = 2.8762 + 0.10679e-5 * yp + 0.21301e-10 * yp**2 - 0.53132e-16 * yp**3
        b = 0.026233 + 0.50609e-6 * yp
        c = -465.93 + 0.030867 * yp - 0.10483e-7 * yp**2 + 0.36989e-13 * yp**3
        ba = b / a
        denom = yp * (3.0 * ba - ba**3 - 1.0)
        if denom == 0:
            raise EngineeringError("API 5C3 coefficient denominator is 0 for this yield")
        f = 46.95e6 * ((3.0 * ba) / (2.0 + ba)) ** 3 / denom
        g = f * ba
        return a, b, c, f, g

    @classmethod
    def _dt_limits(cls, yp: float):
        a, b, c, f, g = cls._abc(yp)
        term = b + c / yp
        if term == 0:
            raise EngineeringError("API 5C3 D/t yield-limit denominator is 0")
        dt_yp = (math.sqrt((a - 2.0) ** 2 + 8.0 * term) + (a - 2.0)) / (2.0 * term)
        dt_pt = yp * (a - f) / (c + yp * (b - g))
        dt_te = (2.0 + b / a) / (3.0 * b / a)
        return dt_yp, dt_pt, dt_te, a, b, c, f, g

    @classmethod
    def burst(cls, od_in, wall_in, yield_psi, design_factor=None) -> EngineeringResult:
        try:
            od = require_number(od_in, "od_in")
            t = require_number(wall_in, "wall_in")
            yp = require_number(yield_psi, "yield_psi")
            if od <= 0 or t <= 0 or yp <= 0:
                raise EngineeringError("OD, wall and yield must be > 0")
            if t >= od / 2:
                raise EngineeringError("Wall thickness must be < OD/2")
            rating = 0.875 * 2.0 * yp * t / od
            df = optional_number(design_factor, "design_factor")
            working = rating / df if df and df > 0 else None
            values = {
                "burst_rating_psi": round(rating, 1),
                "working_pressure_psi": None if working is None else round(working, 1),
                "od_in": od,
                "wall_in": t,
                "yield_psi": yp,
                "wall_tolerance_factor": 0.875,
            }
            return ok(
                round(rating, 1),
                values=values,
                unit="psi",
                formula="P_burst = 0.875 × 2 × Yp × t / OD  (Barlow, API wall tolerance)",
                method=cls.METHOD,
                assumptions=[
                    "Thin-wall Barlow internal yield",
                    "API 5CT −12.5% wall tolerance (0.875 factor)",
                    "No temperature derating, no biaxial reduction",
                ],
                warnings=["PARTIAL: Barlow internal yield only — not a full API TR 5C3 burst design"],
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def collapse(cls, od_in, wall_in, yield_psi, design_factor=None) -> EngineeringResult:
        try:
            od = require_number(od_in, "od_in")
            t = require_number(wall_in, "wall_in")
            yp = require_number(yield_psi, "yield_psi")
            if od <= 0 or t <= 0 or yp <= 0:
                raise EngineeringError("OD, wall and yield must be > 0")
            dt = od / t
            dt_yp, dt_pt, dt_te, a, b, c, f, g = cls._dt_limits(yp)
            if dt <= dt_yp:
                regime = "yield"
                rating = 2.0 * yp * ((dt - 1.0) / dt**2)
            elif dt <= dt_pt:
                regime = "plastic"
                rating = yp * (a / dt - b) - c
            elif dt <= dt_te:
                regime = "transition"
                rating = yp * (f / dt - g)
            else:
                regime = "elastic"
                rating = 46.95e6 / (dt * (dt - 1.0) ** 2)
            rating = max(0.0, rating)
            df = optional_number(design_factor, "design_factor")
            working = rating / df if df and df > 0 else None
            values = {
                "collapse_rating_psi": round(rating, 1),
                "working_pressure_psi": None if working is None else round(working, 1),
                "d_over_t": round(dt, 4),
                "regime": regime,
                "dt_yield": round(dt_yp, 4),
                "dt_plastic_transition": round(dt_pt, 4),
                "dt_transition_elastic": round(dt_te, 4),
                "od_in": od,
                "wall_in": t,
                "yield_psi": yp,
            }
            return ok(
                round(rating, 1),
                values=values,
                unit="psi",
                formula=(
                    "Yield: 2Yp(D/t−1)/(D/t)^2; Plastic: Yp(A/(D/t)−B)−C; "
                    "Transition: Yp(F/(D/t)−G); Elastic: 46.95e6/[(D/t)(D/t−1)^2]"
                ),
                method=cls.METHOD,
                assumptions=[
                    "Zero axial load, zero internal pressure (uncorrected Pc)",
                    "Coefficients A,B,C,F,G from specified minimum yield (psi)",
                    "No combined-load fyax derating",
                ],
                warnings=[
                    "PARTIAL: API 5C3 four-regime collapse only — no axial/internal-pressure correction"
                ],
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def tensile(cls, od_in, id_in, yield_psi, design_factor=None) -> EngineeringResult:
        try:
            od = require_number(od_in, "od_in")
            id_ = require_number(id_in, "id_in")
            yp = require_number(yield_psi, "yield_psi")
            if od <= 0 or yp <= 0:
                raise EngineeringError("OD and yield must be > 0")
            if id_ <= 0:
                raise EngineeringError("ID must be > 0")
            if id_ >= od:
                raise EngineeringError("ID must be < OD")
            area = math.pi / 4.0 * (od**2 - id_**2)
            rating = area * yp  # lbf
            df = optional_number(design_factor, "design_factor")
            working = rating / df if df and df > 0 else None
            values = {
                "pipe_body_yield_lbf": round(rating, 0),
                "pipe_body_yield_klbf": round(rating / 1000.0, 2),
                "working_tension_lbf": None if working is None else round(working, 0),
                "cross_section_in2": round(area, 4),
                "od_in": od,
                "id_in": id_,
                "yield_psi": yp,
            }
            return ok(
                round(rating, 0),
                values=values,
                unit="lbf",
                formula="T_body = Yp × π/4 × (OD² − ID²)",
                method=cls.METHOD,
                assumptions=[
                    "Pipe-body yield only — connections often govern and are NOT rated here",
                    "No joint strength, no temperature derating",
                ],
                warnings=["PARTIAL: pipe-body yield only — API connection ratings not implemented"],
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def evaluate(
        cls,
        od_in,
        id_in=None,
        wall_in=None,
        yield_psi=None,
        internal_pressure_psi=None,
        external_pressure_psi=None,
        axial_tension_lbf=None,
        burst_design_factor=None,
        collapse_design_factor=None,
        tension_design_factor=None,
        grade: str = "",
        weight_ppf=None,
    ) -> EngineeringResult:
        """Compute burst, collapse and tension ratings and optional load checks."""
        try:
            od = require_number(od_in, "od_in")
            yp = require_number(yield_psi, "yield_psi")
            wall = optional_number(wall_in, "wall_in")
            id_ = optional_number(id_in, "id_in")
            if wall is None and id_ is not None:
                wall = (od - id_) / 2.0
            if id_ is None and wall is not None:
                id_ = od - 2.0 * wall
            if wall is None:
                raise MissingInputError("wall_in or id_in")
            if id_ is None:
                raise MissingInputError("id_in or wall_in")
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

        b = cls.burst(od, wall, yp, burst_design_factor)
        c = cls.collapse(od, wall, yp, collapse_design_factor)
        t = cls.tensile(od, id_, yp, tension_design_factor)
        if not (b.success and c.success and t.success):
            err = b.error or c.error or t.error
            return failed(err)

        warnings: List[str] = list(b.warnings) + list(c.warnings) + list(t.warnings)
        loads: Dict[str, Optional[float]] = {}
        pi = optional_number(internal_pressure_psi, "internal_pressure_psi")
        pe = optional_number(external_pressure_psi, "external_pressure_psi")
        fax = optional_number(axial_tension_lbf, "axial_tension_lbf")
        if pi is not None:
            sf_b = b.value / pi if pi > 0 else None
            loads["burst_sf"] = None if sf_b is None else round(sf_b, 3)
            dfb = optional_number(burst_design_factor, "burst_design_factor")
            if dfb and sf_b is not None and sf_b < dfb:
                warnings.append(f"Burst SF {sf_b:.2f} < design factor {dfb}")
        if pe is not None:
            sf_c = c.value / pe if pe > 0 else None
            loads["collapse_sf"] = None if sf_c is None else round(sf_c, 3)
            dfc = optional_number(collapse_design_factor, "collapse_design_factor")
            if dfc and sf_c is not None and sf_c < dfc:
                warnings.append(f"Collapse SF {sf_c:.2f} < design factor {dfc}")
        if fax is not None:
            sf_t = t.value / fax if fax > 0 else None
            loads["tension_sf"] = None if sf_t is None else round(sf_t, 3)
            dft = optional_number(tension_design_factor, "tension_design_factor")
            if dft and sf_t is not None and sf_t < dft:
                warnings.append(f"Tension SF {sf_t:.2f} < design factor {dft}")

        values = {
            **b.values,
            **c.values,
            **t.values,
            **loads,
            "grade": grade,
            "weight_ppf": optional_number(weight_ppf, "weight_ppf"),
            "scope": cls.SCOPE,
        }
        return ok(
            {
                "burst_psi": b.value,
                "collapse_psi": c.value,
                "tensile_lbf": t.value,
            },
            values=values,
            unit="psi / lbf",
            formula="Barlow burst + API 5C3 collapse + pipe-body yield",
            method=cls.METHOD,
            assumptions=b.assumptions + c.assumptions + t.assumptions,
            warnings=warnings,
            scope=cls.SCOPE,
            metadata={"api_tr_5c3_complete": False},
        )
