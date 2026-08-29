"""
Trajectory Calculator - deterministic Minimum Curvature with full contracts

Based on welleng knowledge (not copied, reimplemented with NNNNN architecture)

Governing Equations:
- Minimum Curvature Method is industry standard (SPE, Bourgoyne)
- DLS = arccos(cosI1*cosI2 + sinI1*sinI2*cos(A2-A1)) * (30 / dMD) for deg/30m
- TVD increment uses ratio factor RF

References:
- Bourgoyne et al. Applied Drilling Engineering
- ISCWSA error models (for future)
- welleng repository (jonnymaserati/welleng) - as knowledge source, not copy
"""

from ..core import TrajectoryEngine, TrajectoryPoint
from typing import List, Dict


class TrajectoryCalculator:
    """Wrapper with explicit contract for UI/services."""

    # Contract definition
    REQUIRED_INPUTS = {
        "surveys": "List of {md, inc, azi} sorted by MD",
        "vs_azimuth": "Vertical section azimuth, deg (optional, default 0)",
        "dls_unit": "deg/30m or deg/100ft (optional)",
    }

    OUTPUTS = {
        "tvd": "True Vertical Depth",
        "north": "Northing",
        "east": "Easting",
        "vs": "Vertical Section",
        "hd": "Horizontal Displacement",
        "dls": "Dogleg Severity",
        "build_rate": "Build Rate deg/30m",
        "turn_rate": "Turn Rate deg/30m",
    }

    UNITS = {
        "md": "m (canonical), ft supported at boundary",
        "inc": "deg",
        "azi": "deg",
        "tvd": "same as md",
        "dls": "deg/30m (canonical) or deg/100ft",
    }

    ASSUMPTIONS = [
        "Minimum Curvature Method (MCM) is used - industry standard",
        "Earth is locally flat for North/East (no convergence)",
        "First survey at origin (0,0,0) unless specified",
        "VS azimuth default 0 (North)",
    ]

    @classmethod
    def calculate(cls, surveys: List[Dict], vs_azimuth: float = 0.0, dls_unit: str = "deg/30m") -> List[Dict]:
        points = TrajectoryEngine.calculate(surveys, vs_azimuth=vs_azimuth, dls_unit=dls_unit)
        return [
            {
                "md": p.md,
                "inc": p.inc,
                "azi": p.azi,
                "tvd": p.tvd,
                "north": p.north,
                "east": p.east,
                "vs": p.vs,
                "hd": p.hd,
                "dls": p.dls,
                "build_rate": p.build_rate,
                "turn_rate": p.turn_rate,
            }
            for p in points
        ]

    @classmethod
    def get_contract(cls) -> Dict:
        return {
            "required_inputs": cls.REQUIRED_INPUTS,
            "outputs": cls.OUTPUTS,
            "units": cls.UNITS,
            "assumptions": cls.ASSUMPTIONS,
            "validation": [
                "MD monotonic increasing",
                "Duplicate MD detection",
                "Non-monotonic MD detection",
                "Inc in [0,180], Azi normalized to [0,360)",
            ],
            "error_conditions": ["MISSING_INPUT if surveys empty", "Duplicate MD", "Non-monotonic MD"],
        }
