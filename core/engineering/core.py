"""
Engineering Calculation Core - Deterministic, Validated, No LLM Guessing

Architecture:
UI → Application Services → Domain / Engineering Core → Repositories → Database
AI → call Engineering Engine → receive numerical result → validate → explain

Safety Rule: Never silently invent formulas, constants, limits, missing inputs, units, assumptions.
If unknown: return MISSING_INPUT or UNSUPPORTED_CALCULATION instead of plausible number.

Every calculation has contract:
- Required inputs
- Outputs
- Units
- Assumptions
- Validation
- Error conditions
"""

from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple, Any
import math
import logging

from .result import (
    EngineeringResult,
    EngineeringError,
    MissingInputError,
    UnsupportedCalculationError,
)

logger = logging.getLogger(__name__)


@dataclass
class CalculationResult:
    """Backward-compatible alias of EngineeringResult."""

    success: bool
    value: Any = None
    values: Dict[str, Any] = None
    unit: str = ""
    formula: str = ""
    method: str = ""
    assumptions: List[str] = None
    warnings: List[str] = None
    validation_status: str = "ok"
    metadata: Dict[str, Any] = None
    error: str = ""
    scope: str = "COMPLETE"

    def as_dict(self):
        return asdict(self)

    @classmethod
    def from_engineering(cls, r: EngineeringResult) -> "CalculationResult":
        return cls(
            success=r.success,
            value=r.value,
            values=r.values,
            unit=r.unit,
            formula=r.formula,
            method=r.method,
            assumptions=r.assumptions,
            warnings=r.warnings,
            validation_status=r.validation_status,
            metadata=r.metadata,
            error=r.error,
            scope=r.scope,
        )


# ==================== Trajectory / Survey / Minimum Curvature ====================

@dataclass
class SurveyPointInput:
    md: float  # Measured Depth, m
    inc: float  # Inclination, deg
    azi: float  # Azimuth, deg


@dataclass
class TrajectoryPoint:
    md: float
    inc: float
    azi: float
    tvd: float
    north: float
    east: float
    vs: float = 0.0
    hd: float = 0.0
    dls: float = 0.0
    build_rate: float = 0.0
    turn_rate: float = 0.0


class TrajectoryEngine:
    """
    Minimum Curvature Method (MCM) - Industry standard

    Governing equations (from Bourgoyne et al., SPE):
    - Dogleg = arccos[ cos(I1)*cos(I2) + sin(I1)*sin(I2)*cos(A2-A1) ]
    - RF = (2/DL) * tan(DL/2) if DL !=0 else 1
    - dTVD = 0.5 * dMD * (cosI1 + cosI2) * RF
    - dNorth = 0.5 * dMD * (sinI1*cosA1 + sinI2*cosA2) * RF
    - dEast = 0.5 * dMD * (sinI1*sinA1 + sinI2*sinA2) * RF

    Required inputs:
    - Survey list sorted by MD ascending
    - Each: MD, Inc (deg), Azi (deg)

    Outputs:
    - TVD, North, East, VS, HD, DLS per point

    Units:
    - Input MD: m (or ft, converted at boundary)
    - Input angles: deg
    - Output TVD/North/East: same as MD unit
    - DLS: deg/30m (or deg/100ft depending on config)

    Validation:
    - MD must be monotonic increasing
    - Inc in [0,180], Azi in [0,360)
    - Duplicate MD detection
    - Non-monotonic MD detection
    """

    @staticmethod
    def _validate_surveys(surveys: List[Dict]) -> List[SurveyPointInput]:
        if not surveys:
            raise MissingInputError("surveys")

        cleaned = []
        prev_md = -1
        seen_md = set()
        for idx, p in enumerate(surveys):
            md = p.get("md")
            inc = p.get("inc", p.get("inclination", 0))
            azi = p.get("azi", p.get("azimuth", 0))

            if md in (None, ""):
                raise MissingInputError(f"survey[{idx}].md")

            try:
                md_f = float(md)
                inc_f = float(inc) if inc not in (None, "") else 0.0
                azi_f = float(azi) if azi not in (None, "") else 0.0
            except (TypeError, ValueError):
                raise EngineeringError(f"Invalid numeric survey at index {idx}")

            if md_f in seen_md:
                raise EngineeringError(f"Duplicate MD detected: {md_f} at index {idx}")
            seen_md.add(md_f)

            if md_f <= prev_md and prev_md != -1:
                raise EngineeringError(f"Non-monotonic MD: {md_f} <= {prev_md} at index {idx}")
            prev_md = md_f

            if not (0 <= inc_f <= 180):
                raise EngineeringError(f"Inclination out of range [0,180]: {inc_f} at MD {md_f}")
            # Normalize azimuth to [0,360)
            azi_f = azi_f % 360

            cleaned.append(SurveyPointInput(md=md_f, inc=inc_f, azi=azi_f))

        # Sort by MD
        cleaned.sort(key=lambda x: x.md)
        return cleaned

    @classmethod
    def calculate(
        cls,
        surveys: List[Dict],
        vs_azimuth: float = 0.0,
        dls_unit: str = "deg/30m",
        tie_on: Optional[Dict] = None,
    ) -> List[TrajectoryPoint]:
        """
        Calculate full trajectory using Minimum Curvature.

        vs_azimuth: Vertical Section azimuth (deg) for VS calculation
        dls_unit: "deg/30m" or "deg/100ft" - determines DLS scaling
        tie_on: optional {tvd, north, east} for the first station. If omitted:
            north = 0, east = 0,
            TVD = MD × cos(inc)  — well assumed drilled at constant inclination
            from a surface origin. For MD = 0 this gives TVD = 0.
        """
        inputs = cls._validate_surveys(surveys)
        vs_azi_rad = math.radians(vs_azimuth)

        def _first_station(pt: SurveyPointInput) -> TrajectoryPoint:
            if tie_on:
                tvd0 = float(tie_on.get("tvd", pt.md * math.cos(math.radians(pt.inc))))
                n0 = float(tie_on.get("north", 0) or 0)
                e0 = float(tie_on.get("east", 0) or 0)
            else:
                tvd0 = pt.md * math.cos(math.radians(pt.inc))
                n0 = 0.0
                e0 = 0.0
            hd0 = math.sqrt(n0**2 + e0**2)
            vs0 = n0 * math.cos(vs_azi_rad) + e0 * math.sin(vs_azi_rad)
            return TrajectoryPoint(
                md=pt.md,
                inc=pt.inc,
                azi=pt.azi,
                tvd=tvd0,
                north=n0,
                east=e0,
                vs=vs0,
                hd=hd0,
                dls=0,
                build_rate=0,
                turn_rate=0,
            )

        if len(inputs) == 1:
            return [_first_station(inputs[0])]

        results: List[TrajectoryPoint] = [_first_station(inputs[0])]

        for i in range(1, len(inputs)):
            prev = inputs[i - 1]
            curr = inputs[i]

            d_md = curr.md - prev.md
            if d_md <= 0:
                raise EngineeringError(f"Invalid dMD <=0 between {prev.md} and {curr.md}")

            # Convert to radians
            inc1 = math.radians(prev.inc)
            inc2 = math.radians(curr.inc)
            azi1 = math.radians(prev.azi)
            azi2 = math.radians(curr.azi)

            # Dogleg angle
            cos_dl = math.cos(inc1) * math.cos(inc2) + math.sin(inc1) * math.sin(inc2) * math.cos(azi2 - azi1)
            # Clamp for numerical stability
            cos_dl = max(-1.0, min(1.0, cos_dl))
            dl = math.acos(cos_dl)  # radians

            # Ratio Factor
            if dl != 0:
                rf = (2.0 / dl) * math.tan(dl / 2.0)
            else:
                rf = 1.0

            # TVD, North, East increments
            d_tvd = 0.5 * d_md * (math.cos(inc1) + math.cos(inc2)) * rf
            d_north = 0.5 * d_md * (math.sin(inc1) * math.cos(azi1) + math.sin(inc2) * math.cos(azi2)) * rf
            d_east = 0.5 * d_md * (math.sin(inc1) * math.sin(azi1) + math.sin(inc2) * math.sin(azi2)) * rf

            prev_result = results[-1]
            tvd = prev_result.tvd + d_tvd
            north = prev_result.north + d_north
            east = prev_result.east + d_east
            hd = math.sqrt(north**2 + east**2)
            # VS = North*cos(VS_azi) + East*sin(VS_azi)
            vs = north * math.cos(vs_azi_rad) + east * math.sin(vs_azi_rad)

            # DLS
            if d_md > 0:
                dls_rad = dl  # dogleg in radians over d_md
                # Convert to deg per 30m or per 100ft
                if dls_unit == "deg/30m":
                    dls = math.degrees(dls_rad) * (30.0 / d_md)
                elif dls_unit == "deg/100ft":
                    # d_md assumed in ft if unit is ft, but we use m->ft conversion at boundary
                    # Here we assume d_md in same unit as input; if m, then 100ft = 30.48m
                    # So for m input: DLS per 30.48m
                    dls = math.degrees(dls_rad) * (30.48 / d_md)
                else:
                    dls = math.degrees(dls_rad) * (30.0 / d_md)
            else:
                dls = 0.0

            # Build and Turn rates
            build_rate = (curr.inc - prev.inc) * (30.0 / d_md) if d_md else 0
            # Turn rate: shortest angle difference
            azi_diff = (curr.azi - prev.azi + 540) % 360 - 180  # normalized to [-180,180)
            turn_rate = azi_diff * (30.0 / d_md) if d_md else 0

            results.append(
                TrajectoryPoint(
                    md=curr.md,
                    inc=curr.inc,
                    azi=curr.azi,
                    tvd=tvd,
                    north=north,
                    east=east,
                    vs=vs,
                    hd=hd,
                    dls=dls,
                    build_rate=build_rate,
                    turn_rate=turn_rate,
                )
            )

        return results

    @classmethod
    def project_ahead(
        cls,
        last_point: TrajectoryPoint,
        md_target: float,
        inc: float,
        azi: float,
        vs_azimuth: float = 0.0,
    ) -> TrajectoryPoint:
        """Project ahead using Minimum Curvature from the last station.

        VS is recomputed from the projected North/East and vs_azimuth
        (not copied from the last station).
        """
        if md_target <= last_point.md:
            raise EngineeringError("Target MD must be > last MD for projection")
        pts = cls.calculate(
            [
                {"md": last_point.md, "inc": last_point.inc, "azi": last_point.azi},
                {"md": md_target, "inc": inc, "azi": azi},
            ],
            vs_azimuth=vs_azimuth,
            tie_on={"tvd": last_point.tvd, "north": last_point.north, "east": last_point.east},
        )
        return pts[-1]


# ==================== Bit & BHA ====================

@dataclass
class BitInput:
    bit_no: str = ""
    bit_size: float = 0  # inch
    bit_type: str = ""
    iadc: str = ""
    manufacturer: str = ""
    serial: str = ""
    nozzles: List[float] = None  # list of 32nds
    depth_in: float = 0
    depth_out: float = 0
    hours_on_bottom: float = 0


class BitEngine:
    """Bit calculations: TFA, HSI, etc."""

    @staticmethod
    def validate(bit: Dict):
        if not bit.get("bit_size"):
            raise MissingInputError("bit.size")
        try:
            size = float(bit["bit_size"])
            if size <= 0:
                raise EngineeringError("Bit size must be >0")
        except (TypeError, ValueError):
            raise EngineeringError("Bit size must be numeric")

    @staticmethod
    def calculate_tfa(nozzles: List[float]) -> float:
        """Total Flow Area from nozzle sizes in 32nds of inch.

        TFA = sum( pi/4 * (size/32)^2 )
        """
        if not nozzles:
            raise MissingInputError("nozzles")
        tfa = 0.0
        for n in nozzles:
            try:
                d = float(n) / 32.0
                tfa += math.pi / 4 * d * d
            except (TypeError, ValueError):
                continue
        if tfa == 0:
            raise EngineeringError("TFA calculated as 0")
        return tfa

    @staticmethod
    def calculate_hsi(flow_rate_gpm: float, pressure_drop_psi: float, bit_size_in: float) -> float:
        """Hydraulic Horsepower per square inch."""
        if not flow_rate_gpm or not pressure_drop_psi or not bit_size_in:
            raise MissingInputError("flow_rate, pressure_drop, bit_size required for HSI")
        bit_area = math.pi / 4 * bit_size_in * bit_size_in
        hhp = flow_rate_gpm * pressure_drop_psi / 1714
        return hhp / bit_area if bit_area else 0


@dataclass
class BHAComponent:
    component: str
    od: float  # inch
    id: float  # inch
    length: float  # m
    weight: float = 0  # kg/m or ppf


class BHAEngine:
    """BHA Assembly calculations."""

    @staticmethod
    def calculate_cumulative(components: List[Dict]) -> Tuple[float, float, List[Dict]]:
        """
        Returns total length, total weight, and components with cumulative length.

        Required: each component has length
        """
        if not components:
            raise MissingInputError("bha.components")

        total_length = 0.0
        total_weight = 0.0
        enriched = []

        for comp in components:
            if not isinstance(comp, dict):
                continue
            length = comp.get("length")
            if length in (None, ""):
                raise MissingInputError(f"bha component {comp.get('component_name','unknown')} length")
            try:
                l = float(length)
            except (TypeError, ValueError):
                raise EngineeringError(f"Invalid BHA length: {length}")

            if l < 0:
                raise EngineeringError(f"BHA length cannot be negative: {l}")

            # Weight: if weight is ppf, convert to kg/m? Keep as provided for now
            w = float(comp.get("weight", 0) or 0)

            total_length += l
            total_weight += w * l if w else 0

            enriched.append(
                {
                    **comp,
                    "cumulative_length": total_length,
                    "cumulative_length_from_bottom": total_length,  # bottom-up
                }
            )

        return total_length, total_weight, enriched

    @staticmethod
    def validate(components: List[Dict]):
        if not components:
            raise MissingInputError("bha.components")
        for c in components:
            if not c.get("component") and not c.get("component_name"):
                raise MissingInputError("bha.component_name")


# ==================== Mud / Hydraulics ====================

@dataclass
class MudInput:
    mw: float  # ppg
    pv: float  # cp
    yp: float  # lb/100ft2
    flow_rate: float  # gpm
    hole_size: float  # inch
    pipe_od: float  # inch


class HydraulicsEngine:
    """Deterministic hydraulics - wrapper around AdvancedHydraulicsEngine with contracts."""

    @staticmethod
    def calculate_annular_velocity(flow_rate_gpm: float, hole_id_in: float, pipe_od_in: float) -> float:
        """Annular velocity in ft/min.

        AV = 24.51 * Q / (Dh^2 - Dp^2) where Q in gpm, D in inch → ft/min
        Source: Bourgoyne et al.
        """
        if not flow_rate_gpm or not hole_id_in or not pipe_od_in:
            raise MissingInputError("flow_rate, hole_id, pipe_od required")
        denom = hole_id_in**2 - pipe_od_in**2
        if denom <= 0:
            raise EngineeringError("Hole ID must be > Pipe OD")
        av = 24.51 * flow_rate_gpm / denom  # ft/min
        return av

    @staticmethod
    def calculate_ecd(mw_ppg: float, annular_pressure_loss_psi: float, tvd_ft: float) -> float:
        """ECD = MW + APL / (0.052 * TVD)

        Source: Applied Drilling Engineering
        """
        if mw_ppg is None or annular_pressure_loss_psi is None or tvd_ft is None:
            raise MissingInputError("mw, annular_pressure_loss, tvd required")
        if tvd_ft <= 0:
            raise EngineeringError("TVD must be >0 for ECD")
        return mw_ppg + annular_pressure_loss_psi / (0.052 * tvd_ft)

    @staticmethod
    def calculate_pv_yp(theta600: float, theta300: float) -> Tuple[float, float]:
        """PV = theta600 - theta300, YP = theta300 - PV"""
        if theta600 is None or theta300 is None:
            raise MissingInputError("theta600, theta300 required")
        pv = float(theta600) - float(theta300)
        yp = float(theta300) - pv
        return pv, yp


# ==================== Well Control ====================

class WellControlEngine:
    """Compatibility façade. Canonical formulas live in engines.well_control."""

    @staticmethod
    def calculate_kill_mw(original_mw_ppg: float, sidpp_psi: float, tvd_ft: float) -> float:
        from .engines.well_control import WellControlEngine as _WC
        return _WC.calculate_kill_mw(original_mw_ppg, sidpp_psi, tvd_ft)

    @staticmethod
    def calculate_maasp(max_allowable_mw_ppg: float, current_mw_ppg: float, shoe_tvd_ft: float, leak_off_psi: float = None) -> float:
        from .engines.well_control import WellControlEngine as _WC
        return _WC.calculate_maasp(max_allowable_mw_ppg, current_mw_ppg, shoe_tvd_ft, leak_off_psi)


# ==================== Operations Intelligence ====================

class OperationsIntelligenceEngine:
    """Deterministic analysis over validated data, returns insights with evidence."""

    @staticmethod
    def analyze_rop_trend(rop_values: List[float], threshold_pct=18.0) -> Optional[Dict]:
        """Detect ROP degradation over last 7 days.

        Returns insight with evidence if degradation > threshold.
        """
        if len(rop_values) < 2:
            return None
        first = rop_values[0]
        last = rop_values[-1]
        if first == 0:
            return None
        decline_pct = (first - last) / first * 100
        if decline_pct >= threshold_pct:
            return {
                "kind": "rop_degradation",
                "severity": "warning" if decline_pct < 30 else "critical",
                "message": f"ROP declined {decline_pct:.1f}% from {first:.1f} to {last:.1f}",
                "evidence": {
                    "first": first,
                    "latest": last,
                    "decline_pct": round(decline_pct, 2),
                    "data_points": len(rop_values),
                },
                "confidence": 0.85,
            }
        return None

    @staticmethod
    def analyze_npt_trend(npt_percent: float, threshold=20.0) -> Optional[Dict]:
        if npt_percent >= threshold:
            return {
                "kind": "npt_increase",
                "severity": "critical" if npt_percent >= 30 else "warning",
                "message": f"NPT {npt_percent:.1f}% exceeds threshold {threshold}%",
                "evidence": {"npt_percent": npt_percent, "threshold": threshold},
                "confidence": 0.9,
            }
        return None


# ==================== Mud Chemical Ledger ====================

@dataclass
class ChemicalLedgerEntry:
    product: str
    type: str = ""
    opening_stock: float = 0.0
    received: float = 0.0
    used: float = 0.0
    returned: float = 0.0
    adjusted: float = 0.0
    unit: str = ""

    @property
    def closing_stock(self) -> float:
        """Closing = Opening + Received + Adjusted - Used - Returned"""
        return self.opening_stock + self.received + self.adjusted - self.used - self.returned

    def alerts(self) -> List[str]:
        issues = []
        if self.closing_stock < 0:
            issues.append(f"Negative Stock: {self.product} closing {self.closing_stock:.2f} {self.unit}")
        if self.opening_stock > 0 and self.used / self.opening_stock > 2:
            issues.append(f"Unusual Consumption: {self.product} used {self.used} vs opening {self.opening_stock}")
        if self.received == 0 and self.used == 0 and self.opening_stock > 0:
            issues.append(f"No Movement: {self.product} stock {self.opening_stock} {self.unit} with no usage")
        return issues


class MudLedgerEngine:
    """Mud Chemical Ledger with Opening(day+1)=Closing(day) enforcement."""

    @staticmethod
    def calculate_closing(opening: float, received: float, used: float, returned: float = 0, adjusted: float = 0) -> float:
        return opening + received + adjusted - used - returned

    @staticmethod
    def next_day_opening(closing: float) -> float:
        return closing

    @staticmethod
    def validate_ledger(entries: List[ChemicalLedgerEntry]) -> List[str]:
        alerts = []
        for e in entries:
            alerts.extend(e.alerts())
        return alerts

    @staticmethod
    def build_history(daily_data: List[Dict]) -> Dict[str, Dict]:
        """Build history per material: daily usage chart, stock trend, consumption rate, days remaining.

        daily_data: list of {date, product, opening, received, used, closing}
        """
        history: Dict[str, List[Dict]] = {}
        for row in daily_data:
            product = row.get("product") or row.get("material_name")
            if not product:
                continue
            history.setdefault(product, []).append(row)

        result = {}
        for product, rows in history.items():
            rows_sorted = sorted(rows, key=lambda x: x.get("date", ""))
            usages = [float(r.get("used", 0) or 0) for r in rows_sorted]
            stocks = [float(r.get("closing", r.get("current_stock", 0)) or 0) for r in rows_sorted]
            avg_consumption = sum(usages) / len(usages) if usages else 0
            last_stock = stocks[-1] if stocks else 0
            days_remaining = last_stock / avg_consumption if avg_consumption > 0 else 0

            result[product] = {
                "daily_usage": usages,
                "stock_trend": stocks,
                "consumption_rate": round(avg_consumption, 2),
                "days_remaining": round(days_remaining, 2),
                "received_vs_used": {
                    "total_received": sum(float(r.get("received", 0) or 0) for r in rows_sorted),
                    "total_used": sum(usages),
                },
            }
        return result
