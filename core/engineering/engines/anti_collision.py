"""Deterministic well-to-well anti-collision screening.

This engine provides a transparent centerline screening model. It does not
implement an ISCWSA error model, magnetic reference model, or survey-tool
uncertainty propagation. Those requirements remain explicitly unsupported
unless a validated error model is supplied by a future integration.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..result import (
    EngineeringError,
    EngineeringResult,
    MissingInputError,
    failed,
    missing,
    ok,
    optional_number,
    require_number,
)


class AntiCollisionEngine:
    """Well-to-well separation and clearance screening.

    Input coordinates must use one consistent linear unit for both wells.
    Each point requires ``md``, ``tvd``, ``north`` and ``east``. Optional
    point fields are ``wellbore_radius`` and 1-sigma ``sigma_north``,
    ``sigma_east`` and ``sigma_tvd``. The uncertainty result is a transparent
    3D RSS screening metric, not an ISCWSA separation factor.
    """

    REQUIRED_INPUTS = {
        "reference_trajectory": "List of {md, tvd, north, east}",
        "offset_trajectory": "List of {md, tvd, north, east}",
        "coordinates_unit": "Same linear unit for both trajectories",
    }
    METHOD = "Linear-interpolated 3D centerline separation screening"
    SCOPE = "PARTIAL / SCREENING"
    OUTPUTS = {
        "separation_vs_md": "Interpolated centerline separation by common MD",
        "closest_approach": "Minimum separation on the common-MD scan",
        "clearance_vs_md": "Centerline separation minus supplied radii",
        "separation_factor": "Distance / combined supplied 3D 1-sigma RSS",
        "collision_scan": "Threshold scan when collision_threshold is supplied",
    }
    _COORDINATES = ("md", "tvd", "north", "east")
    _SIGMA_AXES = ("north", "east", "tvd")
    _LINEAR_UNITS = frozenset({
        "input", "m", "meter", "meters", "mm", "cm",
        "ft", "foot", "feet", "in", "inch", "inches",
    })

    @staticmethod
    def _euclidean_distance(p1: Dict, p2: Dict) -> float:
        """Basic 3D distance retained for legacy callers."""
        try:
            dx = require_number(p1.get("north"), "north") - require_number(p2.get("north"), "north")
            dy = require_number(p1.get("east"), "east") - require_number(p2.get("east"), "east")
            dz = require_number(p1.get("tvd"), "tvd") - require_number(p2.get("tvd"), "tvd")
        except (MissingInputError, EngineeringError):
            return float("inf")
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @classmethod
    def _validate_trajectory(cls, name: str, points: Sequence[Dict]) -> List[Dict[str, float]]:
        if not points:
            raise MissingInputError(name)
        if not isinstance(points, (list, tuple)):
            raise EngineeringError(f"{name} must be a list of survey points")

        validated: List[Dict[str, float]] = []
        previous_md = None
        for index, point in enumerate(points):
            if not isinstance(point, dict):
                raise EngineeringError(f"{name}[{index}] must be a mapping")
            values = {}
            for field in cls._COORDINATES:
                values[field] = require_number(point.get(field), f"{name}[{index}].{field}")
            if values["md"] < 0:
                raise EngineeringError(f"{name}[{index}].md cannot be negative")
            if previous_md is not None and values["md"] <= previous_md:
                raise EngineeringError(f"{name} MD values must be strictly increasing")
            previous_md = values["md"]

            for axis in cls._SIGMA_AXES:
                sigma = cls._point_sigma(point, axis)
                if sigma is not None:
                    if sigma < 0:
                        raise EngineeringError(f"{name}[{index}].sigma_{axis} cannot be negative")
                    values[f"sigma_{axis}"] = sigma
            radius = cls._point_radius(point)
            if radius is not None:
                if radius < 0:
                    raise EngineeringError(f"{name}[{index}].wellbore_radius cannot be negative")
                values["wellbore_radius"] = radius
            validated.append(values)
        return validated

    @staticmethod
    def _point_sigma(point: Dict, axis: str) -> Optional[float]:
        direct = point.get(f"sigma_{axis}")
        if direct not in (None, ""):
            return require_number(direct, f"sigma_{axis}")
        uncertainty = point.get("uncertainty") or point.get("error_ellipse")
        if isinstance(uncertainty, dict):
            for key in (f"sigma_{axis}", axis, f"{axis}_sigma"):
                if uncertainty.get(key) not in (None, ""):
                    return require_number(uncertainty[key], f"uncertainty.{key}")
        return None

    @staticmethod
    def _point_radius(point: Dict) -> Optional[float]:
        for key in ("wellbore_radius", "radius"):
            if point.get(key) not in (None, ""):
                return require_number(point[key], key)
        return None

    @staticmethod
    def _interpolate(points: Sequence[Dict[str, float]], md: float) -> Dict[str, float]:
        if md <= points[0]["md"]:
            return dict(points[0])
        if md >= points[-1]["md"]:
            return dict(points[-1])
        for left, right in zip(points, points[1:]):
            if left["md"] <= md <= right["md"]:
                span = right["md"] - left["md"]
                fraction = (md - left["md"]) / span
                result = {
                    field: left[field] + (right[field] - left[field]) * fraction
                    for field in AntiCollisionEngine._COORDINATES
                }
                for field in set(left).intersection(right) - set(AntiCollisionEngine._COORDINATES):
                    result[field] = left[field] + (right[field] - left[field]) * fraction
                return result
        return dict(points[-1])

    @classmethod
    def _common_md_grid(cls, reference: Sequence[Dict], offset: Sequence[Dict]) -> List[float]:
        start = max(reference[0]["md"], offset[0]["md"])
        end = min(reference[-1]["md"], offset[-1]["md"])
        if end < start:
            raise EngineeringError("reference and offset trajectories have no overlapping MD interval")
        grid = {start, end}
        grid.update(point["md"] for point in reference if start <= point["md"] <= end)
        grid.update(point["md"] for point in offset if start <= point["md"] <= end)
        return sorted(grid)

    @staticmethod
    def _combined_sigma(reference: Dict, offset: Dict) -> Optional[Dict[str, float]]:
        if not all(f"sigma_{axis}" in reference and f"sigma_{axis}" in offset for axis in AntiCollisionEngine._SIGMA_AXES):
            return None
        combined = {
            axis: math.sqrt(reference[f"sigma_{axis}"] ** 2 + offset[f"sigma_{axis}"] ** 2)
            for axis in AntiCollisionEngine._SIGMA_AXES
        }
        combined["rss_3d"] = math.sqrt(sum(value * value for value in combined.values()))
        return combined

    @staticmethod
    def _metrics(reference: Dict, offset: Dict, md: float) -> Dict[str, Any]:
        dn = reference["north"] - offset["north"]
        de = reference["east"] - offset["east"]
        dtvd = reference["tvd"] - offset["tvd"]
        distance = math.sqrt(dn * dn + de * de + dtvd * dtvd)
        radii = None
        clearance = None
        if "wellbore_radius" in reference and "wellbore_radius" in offset:
            radii = reference["wellbore_radius"] + offset["wellbore_radius"]
            clearance = distance - radii
        sigma = AntiCollisionEngine._combined_sigma(reference, offset)
        separation_factor = None
        clearance_factor = None
        if sigma and sigma["rss_3d"] > 0:
            separation_factor = distance / sigma["rss_3d"]
            if clearance is not None:
                clearance_factor = clearance / sigma["rss_3d"]
        return {
            "md": round(md, 6),
            "ref_md": round(md, 6),
            "offset_md": round(md, 6),
            "ref_tvd": round(reference["tvd"], 6),
            "offset_tvd": round(offset["tvd"], 6),
            "north_separation": round(dn, 6),
            "east_separation": round(de, 6),
            "vertical_separation": round(dtvd, 6),
            "lateral_separation": round(math.sqrt(dn * dn + de * de), 6),
            "distance": round(distance, 6),
            "centerline_distance": round(distance, 6),
            "radii_sum": None if radii is None else round(radii, 6),
            "clearance": None if clearance is None else round(clearance, 6),
            "combined_sigma": None if sigma is None else round(sigma["rss_3d"], 6),
            "sigma_north": None if sigma is None else round(sigma["north"], 6),
            "sigma_east": None if sigma is None else round(sigma["east"], 6),
            "sigma_tvd": None if sigma is None else round(sigma["tvd"], 6),
            "separation_factor": None if separation_factor is None else round(separation_factor, 6),
            "clearance_factor": None if clearance_factor is None else round(clearance_factor, 6),
        }

    @classmethod
    def _continuous_closest_approach(
        cls,
        reference: Sequence[Dict],
        offset: Sequence[Dict],
        grid: Sequence[float],
    ) -> Dict[str, Any]:
        candidates: List[Tuple[float, Dict[str, Any]]] = []
        for md in grid:
            ref = cls._interpolate(reference, md)
            off = cls._interpolate(offset, md)
            candidates.append((md, cls._metrics(ref, off, md)))

        for left_md, right_md in zip(grid, grid[1:]):
            left_ref = cls._interpolate(reference, left_md)
            right_ref = cls._interpolate(reference, right_md)
            left_off = cls._interpolate(offset, left_md)
            right_off = cls._interpolate(offset, right_md)
            relative_start = [left_ref[axis] - left_off[axis] for axis in ("north", "east", "tvd")]
            relative_delta = [
                (right_ref[axis] - right_off[axis]) - relative_start[i]
                for i, axis in enumerate(("north", "east", "tvd"))
            ]
            denominator = sum(value * value for value in relative_delta)
            fraction = 0.0 if denominator == 0 else -sum(
                relative_start[i] * relative_delta[i] for i in range(3)
            ) / denominator
            fraction = max(0.0, min(1.0, fraction))
            md = left_md + fraction * (right_md - left_md)
            candidates.append((md, cls._metrics(
                cls._interpolate(reference, md),
                cls._interpolate(offset, md),
                md,
            )))
        return min(candidates, key=lambda item: item[1]["distance"])[1]

    @classmethod
    def screen_clearance(
        cls,
        reference: List[Dict],
        offset: List[Dict],
        *,
        collision_threshold=None,
        coordinates_unit: str = "input",
    ) -> EngineeringResult:
        """Calculate common-MD separation and closest-approach screening."""
        try:
            ref = cls._validate_trajectory("reference_trajectory", reference)
            off = cls._validate_trajectory("offset_trajectory", offset)
            if not isinstance(coordinates_unit, str) or not coordinates_unit.strip():
                raise MissingInputError("coordinates_unit")
            coordinates_unit = coordinates_unit.strip().lower()
            if coordinates_unit not in cls._LINEAR_UNITS:
                raise EngineeringError(
                    f"Unsupported coordinates_unit {coordinates_unit!r}; "
                    f"expected a linear unit such as m, ft, mm, cm, in or input"
                )
            grid = cls._common_md_grid(ref, off)
            threshold = optional_number(collision_threshold, "collision_threshold")
            if threshold is not None and threshold <= 0:
                raise EngineeringError("collision_threshold must be > 0")

            rows = []
            for md in grid:
                row = cls._metrics(cls._interpolate(ref, md), cls._interpolate(off, md), md)
                if rows:
                    delta_md = row["md"] - rows[-1]["md"]
                    delta_distance = row["distance"] - rows[-1]["distance"]
                    row["distance_change"] = round(delta_distance, 6)
                    row["separation_rate_per_md"] = (
                        None if delta_md <= 0 else round(delta_distance / delta_md, 9)
                    )
                    tolerance = max(1e-9, abs(row["distance"]) * 1e-9)
                    row["convergence"] = (
                        "converging" if delta_distance < -tolerance
                        else "diverging" if delta_distance > tolerance
                        else "stable"
                    )
                else:
                    row["distance_change"] = None
                    row["separation_rate_per_md"] = None
                    row["convergence"] = "initial"
                rows.append(row)

            closest = cls._continuous_closest_approach(ref, off, grid)
            uncertainty_available = closest["combined_sigma"] is not None
            clearance_available = closest["clearance"] is not None
            warnings = [
                "Screening model only: ISCWSA error model, tool-error model and covariance propagation are not applied",
            ]
            if not uncertainty_available:
                warnings.append("Positional uncertainty is incomplete; separation factor is not computed")
            if not clearance_available:
                warnings.append("Wellbore radii were not supplied; centerline clearance is not computed")

            collision_scan = {
                "performed": threshold is not None,
                "threshold": threshold,
                "metric": "clearance" if clearance_available else "centerline_distance",
                "events": [],
                "minimum_margin": None,
            }
            if threshold is None:
                warnings.append("Collision scan not performed because collision_threshold was not supplied")
            else:
                event_rows = []
                margins = []
                for row in rows:
                    metric = row["clearance"] if row["clearance"] is not None else row["distance"]
                    margin = metric - threshold
                    margins.append(margin)
                    if margin <= 0:
                        event_rows.append({
                            "md": row["md"],
                            "metric": round(metric, 6),
                            "margin": round(margin, 6),
                            "status": "below_threshold",
                        })
                collision_scan["events"] = event_rows
                collision_scan["minimum_margin"] = round(min(margins), 6) if margins else None
                collision_scan["status"] = "alert" if event_rows else "clear"

            values = {
                "separation_vs_md": rows,
                "distances": rows,
                "closest_approach": closest,
                "minimum_separation": closest["distance"],
                "min_distance": closest["distance"],
                "min_distance_md": closest["md"],
                # Legacy names retained for existing exports and AI callers.
                "min_distance_ref_md": closest["ref_md"],
                "min_distance_offset_md": closest["offset_md"],
                "clearance_vs_md": [
                    {"md": row["md"], "clearance": row["clearance"]}
                    for row in rows
                ],
                "collision_scan": collision_scan,
                "uncertainty": {
                    "available": uncertainty_available,
                    "model": "combined supplied 3D 1-sigma RSS",
                    "iscwsa_applied": False,
                },
                "coordinates_unit": coordinates_unit,
                "reference_md_range": (ref[0]["md"], ref[-1]["md"]),
                "offset_md_range": (off[0]["md"], off[-1]["md"]),
            }
            return ok(
                closest["distance"],
                values=values,
                unit=coordinates_unit,
                formula="d = sqrt(ΔN² + ΔE² + ΔTVD²); linear common-MD interpolation",
                method=cls.METHOD,
                assumptions=[
                    "Both trajectories use the same coordinate reference and linear unit",
                    "Positions are linearly interpolated between supplied survey stations",
                    "Closest approach is minimized on the common-MD piecewise-linear scan",
                    "No ISCWSA model, covariance matrix, magnetic model or tool-error model is applied",
                ],
                warnings=warnings,
                metadata={
                    "iscwsa_compliant": False,
                    "screening_model": True,
                    "uncertainty_model": None if not uncertainty_available else "supplied-axis-rss",
                    "clearance_uses_supplied_radii": clearance_available,
                },
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def _legacy_values(cls, result: EngineeringResult) -> Dict[str, Any]:
        if not result.success:
            return {"error": result.error}
        values = dict(result.values)
        values.update({
            "method": result.method,
            "warnings": list(result.warnings),
            "scope": result.scope,
        })
        return values

    @classmethod
    def calculate_clearance(cls, reference: List[Dict], offset: List[Dict]) -> Dict:
        """Backward-compatible dict facade for the screening result."""
        return cls._legacy_values(cls.screen_clearance(reference, offset))

    @classmethod
    def calculate_with_welleng(cls, reference: List[Dict], offset: List[Dict]) -> Optional[Dict]:
        """Return internal screening plus optional package availability metadata."""
        result = cls.screen_clearance(reference, offset)
        values = cls._legacy_values(result)
        try:
            from ..adapters.welleng_adapter import WellengAdapter
            values["welleng_available"] = WellengAdapter.available()
        except Exception as exc:
            values["welleng_available"] = False
            values["welleng_error"] = str(exc)
        if result.success and values.get("welleng_available"):
            values.setdefault("warnings", []).append(
                "welleng is installed but no validated ISCWSA anti-collision benchmark is wired"
            )
        return values

    @classmethod
    def get_contract(cls) -> Dict:
        return {
            "required_inputs": cls.REQUIRED_INPUTS,
            "outputs": cls.OUTPUTS,
            "units": {"distance": "coordinates_unit", "separation_factor": "dimensionless"},
            "assumptions": [
                "Linear interpolation in common MD and Euclidean centerline distance",
                "Supplied axis uncertainties use independent 1-sigma RSS screening only",
                "Full ISCWSA is unsupported without a validated error/covariance model",
            ],
            "validation": [
                "Both trajectories non-empty",
                "Required coordinates present",
                "MD strictly increasing within each trajectory",
            ],
            "error_conditions": [
                "MISSING_INPUT for missing trajectories or coordinates",
                "UNSUPPORTED/failed result for no overlapping MD interval",
            ],
        }
