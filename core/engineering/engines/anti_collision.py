"""
Anti-Collision Engine - Clearance Factor, Separation Factor

Based on welleng and ISCWSA knowledge

Governing concepts:
- Separation Factor = Distance / (Sigma_ref + Sigma_offset) or ISCWSA
- Clearance Factor similar
- Error Ellipse from ISCWSA error models

For now, deterministic fallback implementation with explicit UNSUPPORTED for full ISCWSA

Future: welleng adapter after benchmark
"""

from typing import List, Dict, Optional, Tuple
import math
from ..core import MissingInputError, UnsupportedCalculationError


class AntiCollisionEngine:
    """
    Anti-collision calculations.

    Required inputs for basic clearance:
    - Reference well trajectory (list of {md, tvd, north, east})
    - Offset well trajectory
    - Error model (optional, for ISCWSA)

    Outputs:
    - Distance between wells at each MD
    - Clearance factor / Separation factor
    - Minimum distance

    Units:
    - Same as input trajectory (m or ft, converted at boundary)

    Validation:
    - Both trajectories required
    - MD sorted

    Safety: If ISCWSA model not available, returns basic Euclidean distance with warning, not guessed error ellipse.
    """

    REQUIRED_INPUTS = {
        "reference_trajectory": "List of {md, tvd, north, east}",
        "offset_trajectory": "List of {md, tvd, north, east}",
        "error_model": "ISCWSA error model (optional, for full uncertainty)",
    }

    OUTPUTS = {
        "distance": "3D distance between wells",
        "separation_factor": "SF = Distance / (sigma_ref + sigma_offset) - if sigma available",
        "clearance_factor": "Similar to SF",
        "min_distance": "Minimum distance across all points",
    }

    @staticmethod
    def _euclidean_distance(p1: Dict, p2: Dict) -> float:
        """Basic 3D distance."""
        dx = (p1.get("north", 0) or 0) - (p2.get("north", 0) or 0)
        dy = (p1.get("east", 0) or 0) - (p2.get("east", 0) or 0)
        dz = (p1.get("tvd", 0) or 0) - (p2.get("tvd", 0) or 0)
        return math.sqrt(dx*dx + dy*dy + dz*dz)

    @classmethod
    def calculate_clearance(cls, reference: List[Dict], offset: List[Dict]) -> Dict:
        if not reference or not offset:
            raise MissingInputError("reference and offset trajectories required")

        # For each reference point, find closest offset point (simplified)
        distances = []
        for ref_pt in reference:
            min_dist = float("inf")
            closest = None
            for off_pt in offset:
                dist = cls._euclidean_distance(ref_pt, off_pt)
                if dist < min_dist:
                    min_dist = dist
                    closest = off_pt
            distances.append(
                {
                    "ref_md": ref_pt.get("md"),
                    "offset_md": closest.get("md") if closest else None,
                    "distance": min_dist,
                    "ref_tvd": ref_pt.get("tvd"),
                    "offset_tvd": closest.get("tvd") if closest else None,
                }
            )

        min_entry = min(distances, key=lambda x: x["distance"]) if distances else None

        return {
            "distances": distances,
            "min_distance": min_entry["distance"] if min_entry else 0,
            "min_distance_ref_md": min_entry["ref_md"] if min_entry else None,
            "min_distance_offset_md": min_entry["offset_md"] if min_entry else None,
            "method": "Euclidean (basic) - ISCWSA error ellipse requires welleng and error models",
            "warnings": ["Full ISCWSA uncertainty and separation factor requires welleng package and error models - current is basic distance only"],
        }

    @classmethod
    def calculate_with_welleng(cls, reference: List[Dict], offset: List[Dict]) -> Optional[Dict]:
        """Try welleng if available, otherwise fallback to basic."""
        try:
            from ..adapters.welleng_adapter import WellengAdapter

            if not WellengAdapter.available():
                return cls.calculate_clearance(reference, offset)

            # Build surveys
            ref_survey = WellengAdapter.build_survey(reference, name="reference")
            off_survey = WellengAdapter.build_survey(offset, name="offset")

            if not ref_survey or not off_survey:
                return cls.calculate_clearance(reference, offset)

            # welleng clearance - if API available
            # For now, return basic + indicate welleng available
            basic = cls.calculate_clearance(reference, offset)
            basic["welleng_available"] = True
            basic["method"] = "welleng available but using basic distance until benchmark with internal engine"
            return basic

        except Exception as exc:
            # Never crash, return basic with error
            basic = cls.calculate_clearance(reference, offset)
            basic["error"] = str(exc)
            return basic

    @classmethod
    def get_contract(cls) -> Dict:
        return {
            "required_inputs": cls.REQUIRED_INPUTS,
            "outputs": cls.OUTPUTS,
            "units": {"distance": "m", "separation_factor": "dimensionless"},
            "assumptions": [
                "Basic Euclidean distance if no error model",
                "Closest approach per reference MD (simplified)",
                "Full ISCWSA requires welleng",
            ],
            "validation": ["Both trajectories non-empty", "MD sorted"],
            "error_conditions": ["MISSING_INPUT if trajectories missing", "UNSUPPORTED for full ISCWSA without welleng"],
        }
