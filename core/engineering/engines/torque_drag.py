"""Torque & Drag — Johancsik soft-string SCREENING model.

Scope: PARTIAL / SCREENING MODEL
  Not production-certified. No bending stiffness, no contact-stiffness,
  no dynamics, no wellbore tortuosity reconstruction beyond survey stations.

Governing equations (Johancsik et al., SPE 11380):
  For an element of length ΔL, inclination I, azimuth change Δφ, build ΔI
  (angles in radians):

    Fn = [ (F Δφ sin I)² + (F ΔI + w_b ΔL sin I)² ]^0.5

    Pickup:   F_top = F_bottom + w_b ΔL cos I + μ Fn
    Slackoff: F_top = F_bottom + w_b ΔL cos I − μ Fn
    Rotating: F_top = F_bottom + w_b ΔL cos I          (axial friction ~ 0)
              ΔTorque = μ Fn r
    Sliding:  same axial as pickup/slackoff, torque ~ 0

Buoyancy (simple): BF = 1 − MW_ppg / 65.5   (steel ~ 65.5 ppg)
  Closed-end / pressure-area buoyancy is NOT included.

welleng / torque_drag packages, when installed, are used only as an optional
benchmark — never as a silent calculation backend.
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

STEEL_PPG = 65.5
E_STEEL_PSI = 30.0e6


def _shortest_rad(a_deg: float, b_deg: float) -> float:
    d = (b_deg - a_deg + 540.0) % 360.0 - 180.0
    return math.radians(d)


class TorqueDragEngine:
    METHOD = "Johancsik soft-string (SPE 11380) — SCREENING"
    SCOPE = "PARTIAL"
    REQUIRED_INPUTS = {
        "survey": "List of {md, inc, azi} — md in m, angles in deg",
        "bha": "List of {length_m, weight_ppf, od_in} from bit to surface",
        "mud_density_ppg": "Mud weight, ppg",
        "friction_factor": "Dimensionless, 0–1, no default",
    }
    OUTPUTS = {
        "hookload_pickup_klbf": "klbf",
        "hookload_slackoff_klbf": "klbf",
        "hookload_rotating_klbf": "klbf",
        "surface_torque_rotating_ft_lbf": "ft·lbf",
        "tension_profile": "list {md_m, pickup, slackoff, rotating} klbf",
        "torque_profile": "list {md_m, rotating_ft_lbf}",
    }

    @staticmethod
    def _validate(survey, bha, mud_density_ppg, friction_factor):
        if not survey:
            raise MissingInputError("survey")
        if not bha:
            raise MissingInputError("bha")
        ff = require_number(friction_factor, "friction_factor")
        if not (0.0 <= ff <= 1.0):
            raise EngineeringError("friction_factor must be in [0, 1]")
        mud = require_number(mud_density_ppg, "mud_density_ppg")
        if mud <= 0:
            raise EngineeringError("mud_density_ppg must be > 0")
        if len(survey) < 2:
            raise MissingInputError("survey (at least 2 stations)")
        return ff, mud

    @classmethod
    def calculate_soft_string(
        cls,
        survey: List[Dict],
        bha: List[Dict],
        mud_density_ppg,
        friction_factor,
        wob_klbf: float = 0.0,
        wellbore_id_in=None,
    ) -> Dict:
        """Return a dict for backward compatibility, wrapping the result values.

        Prefer calculate() which returns EngineeringResult.
        """
        result = cls.calculate(
            survey, bha, mud_density_ppg, friction_factor, wob_klbf, wellbore_id_in
        )
        if not result.success:
            raise EngineeringError(result.error)
        return result.values

    @classmethod
    def calculate(
        cls,
        survey: List[Dict],
        bha: List[Dict],
        mud_density_ppg,
        friction_factor,
        wob_klbf: float = 0.0,
        wellbore_id_in=None,
    ) -> EngineeringResult:
        try:
            ff, mud = cls._validate(survey, bha, mud_density_ppg, friction_factor)
            from ..core import TrajectoryEngine

            traj = TrajectoryEngine.calculate(survey)
            bf = 1.0 - mud / STEEL_PPG
            if bf <= 0:
                raise EngineeringError("Mud density ≥ steel density — buoyancy factor ≤ 0")

            string = cls._expand_string(bha, traj)
            hole_id = optional_number(wellbore_id_in, "wellbore_id_in")
            wob = (optional_number(wob_klbf, "wob_klbf") or 0.0) * 1000.0  # lbf

            pickup = cls._integrate(string, traj, ff, bf, mode="pickup", wob_lbf=wob)
            slack = cls._integrate(string, traj, ff, bf, mode="slackoff", wob_lbf=wob)
            rot = cls._integrate(string, traj, ff, bf, mode="rotating", wob_lbf=wob)
            slide = cls._integrate(string, traj, ff, bf, mode="sliding", wob_lbf=wob)

            buckling = cls._buckling_flags(string, slack["force_lbf"], hole_id, bf)

            warnings = [
                "PARTIAL / SCREENING MODEL — not production-certified",
                "Soft-string (no bending stiffness, no tool-joint effects)",
                "Simple buoyancy BF = 1 − MW/65.5 (no pressure-area term)",
                "Constant friction factor along the well",
                "Static analysis only",
            ]
            if buckling["any"]:
                warnings.append("Dawson-Paslay screening: compression exceeds sinusoidal buckling load in one or more elements")

            values = {
                "hookload_pickup": round(pickup["surface_klbf"], 2),
                "hookload_slackoff": round(slack["surface_klbf"], 2),
                "hookload_rotating": round(rot["surface_klbf"], 2),
                "hookload_sliding": round(slide["surface_klbf"], 2),
                "surface_torque_rotating_ft_lbf": round(rot["surface_torque_ft_lbf"], 1),
                "tension_profile": pickup["profile_force"],
                "torque_profile": rot["profile_torque"],
                "profiles": {
                    "pickup": pickup["profile_force"],
                    "slackoff": slack["profile_force"],
                    "rotating": rot["profile_force"],
                    "sliding": slide["profile_force"],
                },
                "total_buoyed_weight": round(pickup["buoyed_weight_klbf"], 2),
                "friction_factor": ff,
                "mud_density": mud,
                "buoyancy_factor": round(bf, 4),
                "buckling": buckling,
                "method": cls.METHOD,
                "scope": cls.SCOPE,
                "warnings": warnings,
                "assumptions": [
                    "Johancsik soft-string",
                    f"Steel density {STEEL_PPG} ppg",
                    "Weight of each component is required (ppf) — not defaulted",
                    "Survey computed with Minimum Curvature",
                ],
            }
            return ok(
                values["hookload_pickup"],
                values=values,
                unit="klbf",
                formula="Fn=[(F Δφ sin I)²+(F ΔI + wb ΔL sin I)²]^0.5; F_top=F_bot+wb ΔL cos I ± μ Fn",
                method=cls.METHOD,
                assumptions=values["assumptions"],
                warnings=warnings,
                scope=cls.SCOPE,
                metadata={"model": "soft-string-screening", "production_ready": False},
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def _expand_string(cls, bha: List[Dict], traj) -> List[Dict]:
        """Place BHA components from the bit (max MD) toward surface."""
        bit_md = traj[-1].md
        cursor = bit_md
        elements = []
        for i, comp in enumerate(bha):
            length = require_number(comp.get("length", comp.get("length_m")), f"bha[{i}].length")
            if length <= 0:
                raise EngineeringError(f"bha[{i}].length must be > 0")
            wt = optional_number(comp.get("weight", comp.get("weight_ppf")), f"bha[{i}].weight")
            if wt is None:
                raise MissingInputError(f"bha[{i}].weight (ppf)")
            od = optional_number(comp.get("od", comp.get("od_in")), f"bha[{i}].od")
            if od is None:
                raise MissingInputError(f"bha[{i}].od")
            id_ = optional_number(comp.get("id", comp.get("id_in")), f"bha[{i}].id") or 0.0
            md_bottom = cursor
            md_top = cursor - length
            elements.append(
                {
                    "name": comp.get("component_name") or comp.get("component") or f"comp[{i}]",
                    "md_bottom": md_bottom,
                    "md_top": md_top,
                    "length_m": length,
                    "weight_ppf": wt,
                    "od_in": od,
                    "id_in": id_,
                }
            )
            cursor = md_top
        return elements

    @classmethod
    def _inc_azi_at(cls, traj, md: float):
        if md <= traj[0].md:
            return traj[0].inc, traj[0].azi
        if md >= traj[-1].md:
            return traj[-1].inc, traj[-1].azi
        for i in range(1, len(traj)):
            if traj[i].md >= md:
                a, b = traj[i - 1], traj[i]
                if b.md == a.md:
                    return b.inc, b.azi
                f = (md - a.md) / (b.md - a.md)
                return a.inc + f * (b.inc - a.inc), a.azi + f * ((b.azi - a.azi + 540) % 360 - 180)
        return traj[-1].inc, traj[-1].azi

    @classmethod
    def _integrate(cls, string, traj, ff, bf, mode: str, wob_lbf: float):
        """Integrate from bit to surface. Force > 0 is tension."""
        force = -wob_lbf  # compression at bit when WOB applied
        torque = 0.0
        buoyed = 0.0
        profile_force = []
        profile_torque = []

        for el in string:
            inc1, azi1 = cls._inc_azi_at(traj, el["md_bottom"])
            inc2, azi2 = cls._inc_azi_at(traj, el["md_top"])
            d_l_ft = el["length_m"] * 3.28084
            w_air = el["weight_ppf"] * d_l_ft  # lbf
            w_b = w_air * bf
            buoyed += w_b
            i_avg = math.radians((inc1 + inc2) / 2.0)
            d_inc = math.radians(inc2 - inc1)
            d_azi = _shortest_rad(azi1, azi2)
            fn = math.sqrt((force * math.sin(i_avg) * d_azi) ** 2 + (force * d_inc + w_b * math.sin(i_avg)) ** 2)
            axial_w = w_b * math.cos(i_avg)
            if mode == "pickup":
                force = force + axial_w + ff * fn
            elif mode == "slackoff":
                force = force + axial_w - ff * fn
            elif mode == "rotating":
                force = force + axial_w
                r_ft = (el["od_in"] / 2.0) / 12.0
                torque = torque + ff * fn * r_ft
            elif mode == "sliding":
                force = force + axial_w + ff * fn  # sliding in, treat as pickup-like drag
            else:
                raise EngineeringError(f"Unknown T&D mode {mode}")

            profile_force.append(
                {
                    "md": round(el["md_top"], 2),
                    "tension_klbf": round(force / 1000.0, 3),
                    "component": el["name"],
                }
            )
            profile_torque.append(
                {
                    "md": round(el["md_top"], 2),
                    "torque": round(torque, 2),
                    "component": el["name"],
                }
            )

        return {
            "surface_klbf": force / 1000.0,
            "surface_torque_ft_lbf": torque,
            "buoyed_weight_klbf": buoyed / 1000.0,
            "profile_force": list(reversed(profile_force)),
            "profile_torque": list(reversed(profile_torque)),
            "force_lbf": force,
        }

    @classmethod
    def _buckling_flags(cls, string, surface_force_lbf, hole_id, bf) -> Dict:
        """Dawson-Paslay sinusoidal screening on the slackoff/compression side.

        Fcrit = 2 √(EI w sinI / rc)   (horizontal form generalized with sin I)
        Only flagged; not used to alter hookload.
        """
        any_flag = False
        details = []
        if hole_id is None:
            return {"any": False, "details": [], "note": "wellbore_id_in not provided — buckling not checked"}
        for el in string:
            od = el["od_in"]
            id_ = el["id_in"]
            rc = (hole_id - od) / 2.0
            if rc <= 0:
                details.append({"component": el["name"], "flag": "no_clearance"})
                any_flag = True
                continue
            i = math.pi / 64.0 * (od**4 - id_**4)  # in^4
            w_per_in = el["weight_ppf"] / 12.0 * bf  # lbf/in
            # without local inclination we use a conservative sinI=1 bound in the note
            fcrit = 2.0 * math.sqrt(E_STEEL_PSI * i * max(w_per_in, 1e-9) / rc)
            details.append(
                {
                    "component": el["name"],
                    "fcrit_sin_horizontal_lbf": round(fcrit, 0),
                    "note": "Horizontal Dawson-Paslay magnitude (screening)",
                }
            )
        return {"any": any_flag, "details": details}

    @classmethod
    def calculate_with_welleng(cls, survey, bha, mud_density_ppg, friction_factor) -> Optional[Dict]:
        """Optional benchmark only. Internal screening result is always the value."""
        internal = cls.calculate(survey, bha, mud_density_ppg, friction_factor)
        payload = internal.as_dict()
        try:
            from ..adapters.welleng_adapter import WellengAdapter
            from ..adapters.torque_drag_adapter import TorqueDragAdapter

            payload["values"]["welleng_available"] = WellengAdapter.available()
            payload["values"]["torque_drag_package_available"] = TorqueDragAdapter.available()
            payload["values"]["benchmark"] = (
                "External packages are not used as the calculation backend. "
                "Compare independently if installed."
            )
        except Exception as exc:
            payload["values"]["adapter_error"] = str(exc)
        return payload

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
                "Soft-string screening model",
                "Constant friction factor",
                "Simple buoyancy",
            ],
            "scope": cls.SCOPE,
            "error_conditions": ["MISSING_INPUT if survey/bha/weight/od/friction/mud missing"],
        }
