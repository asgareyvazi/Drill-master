"""Canonical casing strength — API TR 5C3 *pipe-body* subset.

Implemented:
  - Internal yield (burst): Barlow with 0.875 wall tolerance
  - Collapse: four API 5C3 regimes (yield / plastic / transition / elastic)
  - Pipe-body yield tension: Yp × area
  - Combined-load collapse (fyax biaxial reduction, API 5C3)
  - Internal-pressure collapse adjustment  Pc' = Pc + Pi (1 − 2 t/D)
  - Von Mises equivalent (Lamé inner-wall + axial), utilization vs Yp
  - Optional user-supplied connection ratings (never invented)

NOT implemented (do not claim full API TR 5C3):
  - Published connection tables (BTC / premium)
  - Temperature-yield tables (pass yield_at_temp_psi if already derated)
  - Wear, bending moment, triaxial *design envelope* software
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
    METHOD = "API TR 5C3 pipe-body subset (Barlow + four-regime + fyax + VME)"
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
    def _collapse_uncorrected(cls, od: float, t: float, yp: float):
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
        return max(0.0, rating), regime, dt, dt_yp, dt_pt, dt_te

    @staticmethod
    def fyax(yield_psi: float, axial_stress_psi: float) -> float:
        """API 5C3 reduced yield for collapse under axial stress.

        Tension (sa > 0):  fyax = [√(1 − 0.75 z²) − 0.5 z] Yp
        Compression (sa < 0): sign of the 0.5 z term flips.
        """
        if yield_psi <= 0:
            return 0.0
        z = axial_stress_psi / yield_psi
        if abs(z) >= 1.0:
            return 0.0
        root = math.sqrt(max(0.0, 1.0 - 0.75 * z * z))
        return max(0.0, (root - 0.5 * z) * yield_psi)

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
            if df is not None and df <= 0:
                raise EngineeringError("design_factor must be > 0 when supplied")
            working = rating / df if df is not None else None
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
                    "No temperature derating unless yield_psi is already derated",
                ],
                warnings=["Pipe-body Barlow only — connection burst is not looked up"],
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
            if t >= od / 2:
                raise EngineeringError("Wall thickness must be < OD/2")
            rating, regime, dt, dt_yp, dt_pt, dt_te = cls._collapse_uncorrected(od, t, yp)
            df = optional_number(design_factor, "design_factor")
            if df is not None and df <= 0:
                raise EngineeringError("design_factor must be > 0 when supplied")
            working = rating / df if df is not None else None
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
                ],
                warnings=[],
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def collapse_combined(
        cls,
        od_in,
        wall_in,
        yield_psi,
        axial_tension_lbf=None,
        id_in=None,
        internal_pressure_psi=None,
        design_factor=None,
    ) -> EngineeringResult:
        """Four-regime collapse with fyax and internal-pressure correction."""
        try:
            od = require_number(od_in, "od_in")
            t = require_number(wall_in, "wall_in")
            yp = require_number(yield_psi, "yield_psi")
            if od <= 0 or t <= 0 or yp <= 0:
                raise EngineeringError("OD, wall and yield must be > 0")
            id_ = optional_number(id_in, "id_in")
            if id_ is None:
                id_ = od - 2.0 * t
            if id_ <= 0 or id_ >= od:
                raise EngineeringError("ID must be > 0 and < OD")
            fax = optional_number(axial_tension_lbf, "axial_tension_lbf") or 0.0
            pi = optional_number(internal_pressure_psi, "internal_pressure_psi") or 0.0
            if pi < 0:
                raise EngineeringError("internal_pressure_psi cannot be negative")
            area = math.pi / 4.0 * (od**2 - id_**2)
            if area <= 0:
                raise EngineeringError("Cross-section area must be > 0")
            sa = fax / area
            yp_ax = cls.fyax(yp, sa)
            pc0, regime0, dt, *_ = cls._collapse_uncorrected(od, t, yp)
            pc_ax, regime, *_rest = cls._collapse_uncorrected(od, t, yp_ax if yp_ax > 0 else yp)
            if yp_ax <= 0:
                pc_ax, regime = 0.0, "yield_exhausted"
            pc_corr = pc_ax + pi * (1.0 - 2.0 * t / od)
            pc_corr = max(0.0, pc_corr)
            df = optional_number(design_factor, "design_factor")
            working = pc_corr / df if df and df > 0 else None
            values = {
                "collapse_uncorrected_psi": round(pc0, 1),
                "fyax_psi": round(yp_ax, 1),
                "axial_stress_psi": round(sa, 1),
                "collapse_fyax_psi": round(pc_ax, 1),
                "collapse_combined_psi": round(pc_corr, 1),
                "internal_pressure_psi": pi,
                "regime": regime,
                "d_over_t": round(dt, 4),
                "working_pressure_psi": None if working is None else round(working, 1),
            }
            return ok(
                round(pc_corr, 1),
                values=values,
                unit="psi",
                formula="fyax=[√(1−0.75z²)−0.5z]Yp; Pc'=Pc(fyax)+Pi(1−2t/D)",
                method=cls.METHOD,
                assumptions=[
                    "API 5C3 biaxial fyax (tension positive)",
                    "Internal-pressure addendum Pc' = Pc + Pi (1 − 2t/D)",
                ],
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def triaxial_vme(
        cls,
        od_in,
        id_in,
        yield_psi,
        internal_pressure_psi,
        external_pressure_psi,
        axial_tension_lbf,
        include_capped_end=True,
    ) -> EngineeringResult:
        """Inner-wall von Mises equivalent (Lamé) vs specified minimum yield."""
        try:
            od = require_number(od_in, "od_in")
            id_ = require_number(id_in, "id_in")
            yp = require_number(yield_psi, "yield_psi")
            pi = require_number(internal_pressure_psi, "internal_pressure_psi")
            pe = require_number(external_pressure_psi, "external_pressure_psi")
            fax = require_number(axial_tension_lbf, "axial_tension_lbf")
            if od <= id_ or id_ <= 0 or yp <= 0:
                raise EngineeringError("Need OD > ID > 0 and yield > 0")
            if pi < 0 or pe < 0:
                raise EngineeringError("Internal and external pressures cannot be negative")
            ro, ri = od / 2.0, id_ / 2.0
            area = math.pi * (ro**2 - ri**2)
            # Lamé at inner wall
            denom = ro**2 - ri**2
            sigma_r = -pi
            sigma_h = (pi * (ri**2 + ro**2) - 2.0 * pe * ro**2) / denom
            capped = 0.0
            if include_capped_end:
                capped = (pi * ri**2 - pe * ro**2) / area
            sigma_a = fax / area + capped
            vme = math.sqrt(0.5 * ((sigma_h - sigma_a) ** 2 + (sigma_a - sigma_r) ** 2 + (sigma_r - sigma_h) ** 2))
            util = vme / yp
            values = {
                "sigma_hoop_psi": round(sigma_h, 1),
                "sigma_radial_psi": round(sigma_r, 1),
                "sigma_axial_psi": round(sigma_a, 1),
                "capped_end_psi": round(capped, 1),
                "vme_psi": round(vme, 1),
                "utilization": round(util, 4),
                "yield_psi": yp,
            }
            warnings = []
            if util > 1.0:
                warnings.append(f"VME utilization {util:.3f} > 1.0 (exceeds specified minimum yield)")
            return ok(
                round(vme, 1),
                values=values,
                unit="psi",
                formula="VME=√½[(σh−σa)²+(σa−σr)²+(σr−σh)²]; Lamé inner wall",
                method=cls.METHOD,
                assumptions=[
                    "Elastic Lamé thick-wall at inner surface",
                    "Capped-end axial from Pi, Pe included when include_capped_end=True",
                    "Not a full ISO 10400 design envelope (no temperature, wear, or connection VME)",
                ],
                warnings=warnings,
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
                    "Pipe-body yield only — connections often govern",
                    "No joint strength unless connection_tension_lbf is supplied",
                ],
                warnings=["Pipe-body yield only — API connection ratings are not tabulated here"],
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
        yield_at_temp_psi=None,
        connection_burst_psi=None,
        connection_collapse_psi=None,
        connection_tension_lbf=None,
    ) -> EngineeringResult:
        """Pipe-body ratings, combined collapse, optional VME and connection mins."""
        try:
            od = require_number(od_in, "od_in")
            yp_nom = require_number(yield_psi, "yield_psi")
            yp_t = optional_number(yield_at_temp_psi, "yield_at_temp_psi")
            yp = yp_t if yp_t is not None else yp_nom
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
            return failed(b.error or c.error or t.error)

        comb = cls.collapse_combined(
            od, wall, yp,
            axial_tension_lbf=axial_tension_lbf,
            id_in=id_,
            internal_pressure_psi=internal_pressure_psi,
            design_factor=collapse_design_factor,
        )

        warnings: List[str] = list(b.warnings) + list(c.warnings) + list(t.warnings)
        if yp_t is None:
            warnings.append("Temperature derating not applied — pass yield_at_temp_psi if Yp is reduced")
        else:
            warnings.append(f"Using yield_at_temp_psi={yp_t:g} (not a built-in temperature table)")

        conn_b = optional_number(connection_burst_psi, "connection_burst_psi")
        conn_c = optional_number(connection_collapse_psi, "connection_collapse_psi")
        conn_t = optional_number(connection_tension_lbf, "connection_tension_lbf")
        for name, value in (("connection_burst_psi", conn_b),
                            ("connection_collapse_psi", conn_c),
                            ("connection_tension_lbf", conn_t)):
            if value is not None and value < 0:
                return failed(f"{name} cannot be negative")
        burst_gov = b.value if conn_b is None else min(b.value, conn_b)
        coll_gov = (comb.value if comb.success else c.value)
        if conn_c is not None:
            coll_gov = min(coll_gov, conn_c)
        tens_gov = t.value if conn_t is None else min(t.value, conn_t)
        if conn_b is None and conn_c is None and conn_t is None:
            warnings.append("Connection ratings not supplied — pipe body governs (PARTIAL)")

        loads: Dict[str, Optional[float]] = {}
        pi = optional_number(internal_pressure_psi, "internal_pressure_psi")
        pe = optional_number(external_pressure_psi, "external_pressure_psi")
        fax = optional_number(axial_tension_lbf, "axial_tension_lbf")
        if pi is not None and pi < 0:
            return failed("internal_pressure_psi cannot be negative")
        if pe is not None and pe < 0:
            return failed("external_pressure_psi cannot be negative")
        if pi is not None and pi > 0:
            loads["burst_sf"] = round(burst_gov / pi, 3)
            dfb = optional_number(burst_design_factor, "burst_design_factor")
            if dfb and loads["burst_sf"] < dfb:
                warnings.append(f"Burst SF {loads['burst_sf']:.2f} < design factor {dfb}")
        if pe is not None and pe > 0:
            loads["collapse_sf"] = round(coll_gov / pe, 3)
            dfc = optional_number(collapse_design_factor, "collapse_design_factor")
            if dfc and loads["collapse_sf"] < dfc:
                warnings.append(f"Collapse SF {loads['collapse_sf']:.2f} < design factor {dfc}")
        if fax is not None and fax > 0:
            loads["tension_sf"] = round(tens_gov / fax, 3)
            dft = optional_number(tension_design_factor, "tension_design_factor")
            if dft and loads["tension_sf"] < dft:
                warnings.append(f"Tension SF {loads['tension_sf']:.2f} < design factor {dft}")

        vme_vals = {}
        if pi is not None and pe is not None and fax is not None:
            vm = cls.triaxial_vme(od, id_, yp, pi, pe, fax)
            if vm.success:
                vme_vals = {f"vme_{k}": v for k, v in vm.values.items()}
                vme_vals["vme_psi"] = vm.value
                warnings.extend(vm.warnings)

        values = {
            **b.values,
            **c.values,
            **t.values,
            **(comb.values if comb.success else {}),
            **loads,
            **vme_vals,
            "governing_burst_psi": round(burst_gov, 1),
            "governing_collapse_psi": round(coll_gov, 1),
            "governing_tension_lbf": round(tens_gov, 0),
            "connection_burst_psi": conn_b,
            "connection_collapse_psi": conn_c,
            "connection_tension_lbf": conn_t,
            "grade": grade,
            "weight_ppf": optional_number(weight_ppf, "weight_ppf"),
            "scope": cls.SCOPE,
        }
        return ok(
            {
                "burst_psi": b.value,
                "collapse_psi": c.value,
                "collapse_combined_psi": comb.value if comb.success else c.value,
                "tensile_lbf": t.value,
                "governing_burst_psi": burst_gov,
                "governing_collapse_psi": coll_gov,
                "governing_tension_lbf": tens_gov,
            },
            values=values,
            unit="psi / lbf",
            formula="Barlow + API 5C3 four-regime + fyax + Pi correction + inner-wall VME",
            method=cls.METHOD,
            assumptions=b.assumptions + c.assumptions + t.assumptions,
            warnings=warnings,
            scope=cls.SCOPE,
            metadata={"api_tr_5c3_complete": False, "pipe_body_combined_loads": True},
        )
