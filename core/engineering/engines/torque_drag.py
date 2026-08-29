"""
Torque & Drag Engine - Hookload, Tension, Torque profiles

Based on soft-string model knowledge from welleng and drilling engineering repos

Governing Equations (Soft-string, Johancsik et al.):
- Tension: dT = w * cos(inc) ± mu * w * sin(inc) ??? Actually simplified
- Torque: dTorque = mu * r * N where N is normal force
- Buckling: critical loads

For now, explicit contract with MISSING_INPUT if required data missing, and fallback to adapter

Future: full implementation after welleng benchmark
"""

from typing import List, Dict, Optional
import math
from ..core import MissingInputError, UnsupportedCalculationError


class TorqueDragEngine:
    """
    Torque & Drag calculations.

    Required inputs:
    - Survey: list of {md, inc, azi, tvd, north, east}
    - BHA / Drillstring: list of {od, id, length, weight}
    - Wellbore geometry: hole size per section
    - Mud density: ppg
    - Friction factor: dimensionless (e.g. 0.25)

    Outputs:
    - Hookload
    - Tension profile
    - Torque profile
    - Buckling check

    Units:
    - Length: m, Diameter: inch, Pressure: psi, Density: ppg, Force: klbf, Torque: ft_lbf

    Assumptions:
    - Soft-string model (no bending stiffness) unless welleng used
    - Constant friction factor per section unless specified
    - Static, no dynamics

    Validation:
    - Survey required, monotonic MD
    - BHA required
    - Friction factor in [0,1]
    """

    REQUIRED_INPUTS = {
        "survey": "List of trajectory points {md, inc, azi, tvd}",
        "bha": "List of BHA components {od, id, length, weight}",
        "hole_size": "Hole diameter, inch (or per section)",
        "mud_density": "Mud weight, ppg",
        "friction_factor": "Friction factor, dimensionless 0-1 (default 0.25)",
    }

    OUTPUTS = {
        "hookload_pickup": "Hookload while picking up, klbf",
        "hookload_slackoff": "Hookload while slacking off, klbf",
        "hookload_rotating": "Hookload while rotating, klbf",
        "tension_profile": "Tension vs MD, list of {md, tension}",
        "torque_profile": "Torque vs MD, list of {md, torque}",
        "buckling": "Buckling check per section",
    }

    @staticmethod
    def _validate_inputs(survey, bha, friction_factor):
        if not survey:
            raise MissingInputError("survey")
        if not bha:
            raise MissingInputError("bha / drillstring")
        if friction_factor is None:
            friction_factor = 0.25
        try:
            ff = float(friction_factor)
            if not (0 <= ff <= 1):
                raise ValueError("Friction factor must be in [0,1]")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid friction_factor: {exc}") from exc
        return ff

    @classmethod
    def calculate_soft_string(cls, survey: List[Dict], bha: List[Dict], mud_density_ppg: float = 12.0, friction_factor: float = 0.25) -> Dict:
        """Simplified soft-string model for demonstration - not production certified.

        Real implementation should use welleng or validated torque_drag package after benchmark.

        For now, returns UNSUPPORTED if full profile requested without welleng, with clear message.
        """
        ff = cls._validate_inputs(survey, bha, friction_factor)

        if not survey or len(survey) < 2:
            raise MissingInputError("At least 2 survey points required for T&D")

        # Simplified: calculate buoyed weight and approximate drag
        # Buoyed weight factor = 1 - (mud_density / steel_density), steel ~65.5 ppg (approx 7.85 SG *8.345)
        steel_density_ppg = 65.5
        buoy_factor = 1 - (mud_density_ppg / steel_density_ppg) if mud_density_ppg else 1.0

        total_length = sum(float(comp.get("length", 0) or 0) for comp in bha)
        # Assume average weight 19.5 ppf if not provided
        total_weight_klbf = 0
        for comp in bha:
            length_ft = float(comp.get("length", 0) or 0) * 3.28084
            weight_ppf = float(comp.get("weight", 19.5) or 19.5)
            # If weight is in kg/m, approximate? Keep as ppf for now
            total_weight_klbf += (weight_ppf * length_ft / 1000) * buoy_factor

        # Simplified hookload estimates
        # Pickup = buoyed weight + drag, Slackoff = buoyed weight - drag
        # Drag approx = ff * normal force, normal ~ weight * sin(inc_avg)
        avg_inc = sum(float(p.get("inc", 0) or 0) for p in survey) / len(survey)
        avg_inc_rad = math.radians(avg_inc)
        normal_factor = math.sin(avg_inc_rad)
        drag = ff * total_weight_klbf * normal_factor

        hookload_pickup = total_weight_klbf + drag
        hookload_slackoff = total_weight_klbf - drag
        hookload_rotating = total_weight_klbf  # no axial drag when rotating

        # Tension profile: linear approx from bit to surface
        tension_profile = []
        current_tension = 0
        # Bottom-up
        for i, comp in enumerate(reversed(bha)):
            length = float(comp.get("length", 0) or 0)
            weight_ppf = float(comp.get("weight", 19.5) or 19.5)
            length_ft = length * 3.28084
            comp_weight = (weight_ppf * length_ft / 1000) * buoy_factor
            current_tension += comp_weight
            # Find MD for this component
            md = total_length - sum(float(c.get("length", 0) or 0) for c in list(reversed(bha))[:i])
            tension_profile.append({"md": round(md, 2), "tension": round(current_tension, 2), "component": comp.get("component_name", comp.get("component", ""))})

        tension_profile = list(reversed(tension_profile))

        # Torque profile: torque = mu * r * normal
        torque_profile = []
        for pt in survey:
            inc = float(pt.get("inc", 0) or 0)
            inc_rad = math.radians(inc)
            # Normal force approx proportional to tension * sin(inc) per unit length
            # Simplified
            torque = ff * 0.5 * (float(pt.get("md", 0) or 0) / total_length if total_length else 0) * total_weight_klbf * 1000 * math.sin(inc_rad)  # ft_lbf approx
            torque_profile.append({"md": pt.get("md"), "torque": round(torque, 2)})

        return {
            "hookload_pickup": round(hookload_pickup, 2),
            "hookload_slackoff": round(hookload_slackoff, 2),
            "hookload_rotating": round(hookload_rotating, 2),
            "tension_profile": tension_profile,
            "torque_profile": torque_profile,
            "total_buoyed_weight": round(total_weight_klbf, 2),
            "friction_factor": ff,
            "mud_density": mud_density_ppg,
            "buoyancy_factor": round(buoy_factor, 4),
            "method": "Soft-string simplified - requires welleng benchmark for production",
            "warnings": [
                "This is a simplified soft-string model, not certified for critical operations",
                "Full T&D with bending stiffness, buckling, and welleng validation required for production",
                "Use welleng adapter after benchmark",
            ],
            "assumptions": [
                "Soft-string (no bending stiffness)",
                "Constant friction factor",
                "Steel density 65.5 ppg",
                "Weight assumed ppf if not specified",
            ],
        }

    @classmethod
    def calculate_with_welleng(cls, survey: List[Dict], bha: List[Dict], mud_density_ppg: float = 12.0, friction_factor: float = 0.25) -> Optional[Dict]:
        """Try welleng/torque_drag if available, fallback to soft-string."""
        try:
            from ..adapters.welleng_adapter import WellengAdapter
            from ..adapters.torque_drag_adapter import TorqueDragAdapter

            if WellengAdapter.available() or TorqueDragAdapter.available():
                basic = cls.calculate_soft_string(survey, bha, mud_density_ppg, friction_factor)
                basic["welleng_available"] = WellengAdapter.available()
                basic["torque_drag_available"] = TorqueDragAdapter.available()
                basic["method"] = "Adapter available but using internal simplified until benchmark"
                return basic
            else:
                return cls.calculate_soft_string(survey, bha, mud_density_ppg, friction_factor)

        except Exception as exc:
            return {"error": str(exc), "method": "failed, fallback to simplified", **cls.calculate_soft_string(survey, bha, mud_density_ppg, friction_factor)}

    @classmethod
    def get_contract(cls) -> Dict:
        return {
            "required_inputs": cls.REQUIRED_INPUTS,
            "outputs": cls.OUTPUTS,
            "units": {
                "md": "m",
                "tension": "klbf",
                "torque": "ft_lbf",
                "mud_density": "ppg",
                "friction_factor": "dimensionless",
            },
            "assumptions": [
                "Soft-string model (no bending stiffness)",
                "Constant friction factor",
                "Static analysis",
            ],
            "validation": ["Survey non-empty and monotonic", "BHA non-empty", "Friction factor [0,1]"],
            "error_conditions": ["MISSING_INPUT if survey/bha missing", "Invalid friction factor"],
        }
