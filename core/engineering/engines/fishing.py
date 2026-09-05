"""Fishing / stuck-pipe screening calculations.

Canonical home for the free-point, string-stretch, adjusted pipe weight,
back-off, jar-range and overshot-fit helpers previously living inside the
W13 tab engine.

Scope: SCREENING — the constants below are the legacy handbook-style
approximations that the application has always used (free-point charts,
constant-stretch method). They are centralized here so the UI holds no
formulas, and their approximate nature is declared in every result.

Governing approximations:
- Adjusted (plain-end) pipe weight:  W_ppf = 2.67 × (OD² − ID²)
  (steel density ≈ 490 lb/ft³: π/4 × 490/144 = 2.672)
- Free point under a pull:
      FP_ft = 735294 × ΔL_in × W_ppf / P_lbf
  derived from L = A·E·ΔL/P with E = 30×10⁶ psi and A ≈ W_ppf/3.4:
      E/(3.4 × 12) = 735 294
- String stretch (buoyed pipe, own weight):
      ΔL_in = L_ft / 96 250 000 × (65.44 − 1.44 × MW_ppg)
- Back-off depth uses the same constant-stretch relation:
      L_ft = ΔL_in × E × A / (W_ppf × 12),  A ≈ W_ppf / 3.4
- Jar range: buoyed weight ± overpull; recommended jar setting 80 % of
  the upward force (legacy rule of thumb).
- Overshot fit: clearance = overshot ID − fish OD, compatible when
  0 < clearance < 0.5 in (legacy band).

None of these replace a proper fishing/back-off engineering study; they
are screening aids only.
"""
from __future__ import annotations

from typing import Dict

from ..result import (
    EngineeringResult,
    MissingInputError,
    EngineeringError,
    ok,
    missing,
    failed,
    require_number,
)

METHOD = "Legacy free-point/stretch chart approximations — SCREENING"
SCOPE = "PARTIAL / SCREENING"

# Plain-end weight constant for steel: π/4 × 490 lb/ft³ / 144 in²/ft²
STEEL_WEIGHT_CONST = 2.67
# Free-point constant: E/(3.4 × 12) with E = 30e6 psi (A ≈ W/3.4)
FREE_POINT_CONST = 735294.0
# String-stretch approximation constants (buoyed pipe, own weight)
STRETCH_DENOM = 96250000.0
STRETCH_A = 65.44
STRETCH_B = 1.44
# Steel density used by the legacy stretch formula (ppg)
STEEL_STRETCH_PPG = STRETCH_A


class FishingEngine:
    """Fishing / stuck-pipe screening calculations (single source)."""

    METHOD = METHOD
    SCOPE = SCOPE

    # ------------------------------------------------------------------
    # Pipe properties
    # ------------------------------------------------------------------
    @classmethod
    def adjusted_weight(cls, od_in, id_in) -> EngineeringResult:
        """Adjusted (plain-end) pipe weight in lb/ft.

        W = 2.67 × (OD² − ID²)  — steel body, no tool joints.
        """
        try:
            od = require_number(od_in, "od_in")
            id_ = require_number(id_in, "id_in")
            if od <= 0 or id_ < 0:
                raise EngineeringError("OD must be > 0 and ID ≥ 0")
            if id_ >= od:
                raise EngineeringError("ID must be < OD")
            w = STEEL_WEIGHT_CONST * (od ** 2 - id_ ** 2)
            return ok(
                round(w, 2),
                values={"adjusted_weight_ppf": round(w, 2), "od_in": od, "id_in": id_},
                unit="lb/ft",
                formula="W = 2.67 × (OD² − ID²)",
                method=cls.METHOD,
                assumptions=["Plain-end steel body (no tool joints)", "Steel ≈ 490 lb/ft³"],
                metadata={"units": {"diameter": "in", "weight": "lb/ft"}},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    # ------------------------------------------------------------------
    # Free point / stretch
    # ------------------------------------------------------------------
    @classmethod
    def free_point(cls, stretch_in, pipe_weight_ppf, pull_lbf) -> EngineeringResult:
        """Free point (ft) from stretch measured under a known pull.

        FP = 735294 × ΔL × W_ppf / P  (E = 30e6 psi, A ≈ W_ppf/3.4).
        """
        try:
            dl = require_number(stretch_in, "stretch_in")
            w = require_number(pipe_weight_ppf, "pipe_weight_ppf")
            pull = require_number(pull_lbf, "pull_lbf")
            if pull <= 0:
                raise EngineeringError("pull_lbf must be > 0 (stretch under pull)")
            if w <= 0:
                raise EngineeringError("pipe_weight_ppf must be > 0")
            if dl < 0:
                raise EngineeringError("stretch_in cannot be negative")
            fp = FREE_POINT_CONST * dl * w / pull
            return ok(
                round(fp, 1),
                values={
                    "free_point_ft": round(fp, 1),
                    "stretch_in": dl,
                    "pipe_weight_ppf": w,
                    "pull_lbf": pull,
                },
                unit="ft",
                formula="FP = 735294 × ΔL × W / P",
                method=cls.METHOD,
                assumptions=[
                    "Stretch measured with the string free and under the given pull",
                    "Constant stretch approximation (E = 30e6 psi, A ≈ W/3.4)",
                ],
                metadata={"units": {"stretch": "in", "pull": "lbf", "length": "ft"}},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def string_stretch(cls, length_ft, mw_ppg) -> EngineeringResult:
        """Estimated stretch (in) of a free string hanging in mud.

        ΔL = L/96 250 000 × (65.44 − 1.44 × MW_ppg)
        """
        try:
            length = require_number(length_ft, "length_ft")
            mw = require_number(mw_ppg, "mw_ppg")
            if length <= 0:
                raise EngineeringError("length_ft must be > 0")
            if mw < 0 or mw >= STEEL_STRETCH_PPG / STRETCH_B:
                raise EngineeringError(
                    "mw_ppg out of range for the stretch approximation")
            stretch = length / STRETCH_DENOM * (STRETCH_A - STRETCH_B * mw)
            return ok(
                round(stretch, 2),
                values={"string_stretch_in": round(stretch, 2), "length_ft": length, "mw_ppg": mw},
                unit="in",
                formula="ΔL = L/96250000 × (65.44 − 1.44 × MW)",
                method=cls.METHOD,
                assumptions=["Free string hanging under its own buoyed weight"],
                metadata={"units": {"length": "ft", "mw": "ppg", "stretch": "in"}},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def backoff_depth(cls, stretch_in, pipe_weight_ppf,
                      modulus_psi=30.0e6) -> EngineeringResult:
        """Free point (ft) from stretch for a back-off shot.

        L = ΔL × E × A / (W_ppf × 12),  with A ≈ W_ppf/3.4.

        NOTE: legacy approximation — the pipe weight cancels in the formula
        (A ≈ W/3.4), so the result depends only on stretch, E and the 3.4
        area approximation. Screening use only.
        """
        try:
            dl = require_number(stretch_in, "stretch_in")
            w = require_number(pipe_weight_ppf, "pipe_weight_ppf")
            mod = require_number(modulus_psi, "modulus_psi")
            if dl < 0:
                raise EngineeringError("stretch_in cannot be negative")
            if w <= 0:
                raise EngineeringError("pipe_weight_ppf must be > 0")
            area = w / 3.4  # legacy area approximation (in²)
            fp = dl * mod * area / (w * 12)
            return ok(
                round(fp, 1),
                values={"backoff_depth_ft": round(fp, 1), "stretch_in": dl,
                        "pipe_weight_ppf": w, "modulus_psi": mod},
                unit="ft",
                formula="L = ΔL·E·A/(W·12), A ≈ W/3.4",
                method=cls.METHOD,
                assumptions=[
                    "Legacy constant-stretch approximation (screening only)",
                    "No pull force input — result is stretch/E based; verify against "
                    "a proper free-point determination before shooting",
                ],
                metadata={"units": {"stretch": "in", "length": "ft"}},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    # ------------------------------------------------------------------
    # Jar / overshot rules
    # ------------------------------------------------------------------
    @classmethod
    def jar_operating_range(cls, string_weight_lbs, buoyancy_factor,
                            overpull_lbs) -> EngineeringResult:
        """Jar operating forces from buoyed string weight and overpull.

        Down = buoyed weight; Up = buoyed weight + overpull.
        Recommended jar setting = 80 % of the upward force (legacy rule).
        """
        try:
            w = require_number(string_weight_lbs, "string_weight_lbs")
            bf = require_number(buoyancy_factor, "buoyancy_factor")
            op = require_number(overpull_lbs, "overpull_lbs")
            if w < 0:
                raise EngineeringError("string_weight_lbs cannot be negative")
            if op < 0:
                raise EngineeringError("overpull_lbs cannot be negative")
            buoyed = w * bf
            up = buoyed + op
            down = buoyed
            values = {
                "buoyant_weight_lbs": round(buoyed, 0),
                "upward_force_lbs": round(up, 0),
                "downward_force_lbs": round(down, 0),
                "recommended_jar_setting_lbs": round(up * 0.8, 0),
            }
            return ok(
                round(up, 0),
                values=values,
                unit="lbf",
                formula="F_down = W×BF; F_up = W×BF + overpull; jar setting ≈ 0.8×F_up",
                method=cls.METHOD,
                assumptions=[
                    "Buoyancy factor supplied by the caller (single-source BF)",
                    "80 % jar-setting factor is a legacy field rule of thumb",
                ],
                metadata={"units": {"force": "lbf"}},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))

    @classmethod
    def overshot_fit(cls, fish_od_in, overshot_id_in) -> EngineeringResult:
        """Overshot sizing check: clearance = overshot ID − fish OD.

        Compatible when 0 < clearance < 0.5 in (legacy band).
        """
        try:
            fish = require_number(fish_od_in, "fish_od_in")
            os_id = require_number(overshot_id_in, "overshot_id_in")
            if fish <= 0 or os_id <= 0:
                raise EngineeringError("Diameters must be > 0")
            clearance = os_id - fish
            compatible = 0.0 < clearance < 0.5
            values = {
                "clearance_in": round(clearance, 3),
                "compatible": compatible,
                "recommendation": "OK" if compatible else "Check sizing",
                "fish_od_in": fish,
                "overshot_id_in": os_id,
            }
            return ok(
                round(clearance, 3),
                values=values,
                unit="in",
                formula="Clearance = Overshot ID − Fish OD; 0 < clearance < 0.5 in",
                method=cls.METHOD,
                assumptions=["Legacy 0.5 in clearance band for grapple sizing"],
                metadata={"units": {"diameter": "in", "clearance": "in"}},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))


# ----------------------------------------------------------------------
# Plain helpers (used by W13 legacy wrapper and tests)
# ----------------------------------------------------------------------
def calculate_free_point(stretch_in: float, pipe_weight_ppf: float,
                         pull_lbf: float) -> float:
    """Plain-return free point (ft), 0 on invalid input (legacy behaviour)."""
    if pull_lbf <= 0:
        return 0.0
    r = FishingEngine.free_point(stretch_in, pipe_weight_ppf, pull_lbf)
    return r.value if r.success else 0.0


def calculate_string_stretch(length_ft: float, mw_ppg: float) -> float:
    """Plain-return string stretch (in), 0 on invalid input."""
    r = FishingEngine.string_stretch(length_ft, mw_ppg)
    return r.value if r.success else 0.0


def calculate_backoff_depth(stretch_in: float, pipe_weight_ppf: float) -> float:
    """Plain-return back-off free point (ft), 0 on invalid input."""
    if pipe_weight_ppf <= 0:
        return 0.0
    r = FishingEngine.backoff_depth(stretch_in, pipe_weight_ppf)
    return r.value if r.success else 0.0
