# core/hydraulics_engine.py
"""
Advanced Drilling Hydraulics Engine
موتور محاسبات هیدرولیک پیشرفته حفاری
- پشتیبانی از تعداد نامحدود لوله/کیسینگ
- سه مدل رئولوژی: Bingham, Power Law, Herschel-Bulkley
- محاسبه ECD vs Depth
- Surge/Swab برای هر ترکیب
- پشتیبانی از چاه عمودی/دایرکشنال/افقی
"""
import math
import logging
from typing import List, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ==================== Data Classes ====================

@dataclass
class PipeSegment:
    """یک بخش از رشته حفاری"""
    name: str = ""           # e.g., "5\" DP", "6.5\" DC", "MWD"
    pipe_type: str = "DP"    # DP, HWDP, DC, MWD, Motor, Stabilizer, Sub
    # Zero dimensions/length mark unprovided geometry; callers must supply them.
    od: float = 0.0          # inch
    id: float = 0.0          # inch
    length: float = 0.0      # meters
    weight_ppf: float = 0.0  # lb/ft
    tj_od: float = 0.0       # Tool Joint OD (inch) - for surge/swab
    
    @property
    def length_ft(self) -> float:
        return self.length * 3.28084
    
    @property
    def area_pipe(self) -> float:
        """سطح مقطع داخلی لوله (in²)"""
        return math.pi / 4 * self.id ** 2
    
    @property
    def displacement(self) -> float:
        """جابجایی (bbl/ft)"""
        return (self.od**2 - self.id**2) / 1029.4
    
    @property
    def capacity(self) -> float:
        """ظرفیت (bbl/ft)"""
        return self.id**2 / 1029.4


@dataclass
class CasingSection:
    """یک بخش از کیسینگ/چاه باز"""
    name: str = ""           # e.g., "13-3/8 CSG", "Open Hole"
    section_type: str = "casing"  # casing, liner, open_hole
    # Zero dimensions mark unprovided casing/open-hole geometry.
    od: float = 0.0          # inch (OD of casing / hole size)
    id: float = 0.0          # inch (ID of casing / hole size for OH)
    top_md: float = 0.0      # meters
    bottom_md: float = 0.0   # meters
    top_tvd: float = 0.0     # meters (for directional)
    bottom_tvd: float = 0.0  # meters
    
    @property
    def length_m(self) -> float:
        return self.bottom_md - self.top_md
    
    @property
    def length_ft(self) -> float:
        return self.length_m * 3.28084


@dataclass
class BitNozzle:
    """نازل بیت"""
    size_32nds: int = 0      # 1/32 in; zero means no supplied nozzle size
    quantity: int = 0        # zero means no supplied nozzle count
    
    @property
    def diameter_inch(self) -> float:
        return self.size_32nds / 32.0
    
    @property
    def area(self) -> float:
        """مساحت یک نازل (in²)"""
        return math.pi / 4 * self.diameter_inch ** 2
    
    @property
    def total_area(self) -> float:
        """مساحت کل (in²)"""
        return self.area * self.quantity


@dataclass
class MudProperties:
    """خواص گل حفاری"""
    # Zero marks unprovided data; no plausible rheology is silently seeded.
    mw_pcf: float = 0.0      # density (lb/ft³)
    pv: float = 0.0          # plastic viscosity (cP)
    yp: float | None = None   # yield point (lbf/100 ft²); None means not supplied
    theta600: float = 0.0    # viscometer dial reading
    theta300: float = 0.0
    theta200: float = 0.0
    theta100: float = 0.0
    theta6: float | None = None
    theta3: float | None = None
    gel_10s: float = 0.0
    gel_10m: float = 0.0
    
    @property
    def mw_ppg(self) -> float:
        return self.mw_pcf / 7.48052
    
    @property
    def n_bingham(self) -> float:
        """flow behavior index - Bingham"""
        if self.theta300 <= 0:
            return 1.0
        return 3.32 * math.log10(self.theta600 / self.theta300)
    
    @property
    def k_bingham(self) -> float:
        """consistency index - Bingham"""
        n = self.n_bingham
        return self.theta300 / (511 ** n)
    
    @property
    def n_power_law(self) -> float:
        """flow behavior index - Power Law"""
        if self.theta300 <= 0:
            return 1.0
        return 3.32 * math.log10(self.theta600 / self.theta300)
    
    @property
    def k_power_law(self) -> float:
        """Field-unit power-law consistency index from the Fann reading.

        Guo and Liu, Eq. (2.11), use ``K = 510·theta300 / 511**n`` for
        theta300 in dial units and the 300-rpm shear rate convention. The
        leading factor is a field-unit conversion, not an extra shear-rate
        multiplier. This implementation keeps the published 510 coefficient.
        """
        n = self.n_power_law
        if n <= 0 or self.theta300 <= 0:
            return 0.0
        return 510.0 * self.theta300 / (511 ** n)
    
    @property
    def tau_y_hb(self) -> float | None:
        """Approximate HB yield stress from explicit 3/6-rpm readings, if supplied."""
        if self.theta3 is None or self.theta6 is None:
            return None
        return max(0.0, 2.0 * self.theta3 - self.theta6)

    @staticmethod
    def calculate_fann_rheology(*, theta600: float, theta300: float,
                                theta3: float | None = None,
                                theta6: float | None = None) -> Dict:
        """Canonical Fann-derived Bingham, Power Law, and screening HB values.

        Readings are dial units at the named rpm. Power-law K is the
        field-unit ``equivalent cP`` convention (510 theta300 / 511**n), not
        the dimensional SI consistency index. The HB yield estimate and
        ``PV + 5*YP`` display indicator are explicitly screening-only.
        """
        readings = {"theta600": theta600, "theta300": theta300}
        if theta3 is not None:
            readings["theta3"] = theta3
        if theta6 is not None:
            readings["theta6"] = theta6
        for name, value in readings.items():
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be a finite nonnegative dial reading")
        if theta600 <= theta300 or theta300 <= 0:
            raise ValueError("theta600 must exceed positive theta300")
        pv = theta600 - theta300
        yp = theta300 - pv
        if yp < 0:
            raise ValueError("Fann readings imply negative Bingham yield point")
        n = 3.32 * math.log10(theta600 / theta300)
        k = 510.0 * theta300 / (511.0 ** n) if n > 0 else None
        tau_y = None
        if theta3 is not None and theta6 is not None:
            tau_y = max(0.0, 2.0 * theta3 - theta6)
        return {
            "theta600": theta600,
            "theta300": theta300,
            "theta3": theta3,
            "theta6": theta6,
            "pv_cp": pv,
            "yp_lbf100ft2": yp,
            "power_law_n": n,
            "power_law_k_equivalent_cp": k,
            "hb_yield_estimate_lbf100ft2": tau_y,
            "screening_effective_viscosity_indicator_cp": pv + 5.0 * yp,
            "units": {
                "dial_readings": "Fann dial units at stated rpm",
                "pv": "cP",
                "yp": "lbf/100 ft^2",
                "power_law_n": "dimensionless",
                "power_law_k": "equivalent cP at the 511 s^-1 convention",
                "hb_yield_estimate": "lbf/100 ft^2",
                "effective_viscosity_indicator": "cP (heuristic, not constitutive viscosity)",
            },
            "formula": {
                "pv": "theta600 - theta300",
                "yp": "theta300 - PV",
                "power_law_n": "3.32 log10(theta600/theta300)",
                "power_law_k": "510 theta300 / 511^n",
                "hb_yield_estimate": "max(0, 2 theta3 - theta6)",
                "effective_viscosity_indicator": "PV + 5 YP (heuristic only)",
            },
            "scope": "SCREENING",
            "assumptions": [
                "Power-law K follows the stated equivalent-cP field convention.",
                "HB yield and PV+5YP indicator are screening estimates, not full rheological solutions.",
            ],
        }


@dataclass
class SurfaceEquipment:
    """تجهیزات سطحی"""
    # Zero-valued dimensions indicate missing/unprovided geometry.
    standpipe_length_m: float = 0.0
    standpipe_id_inch: float = 0.0
    hose_length_m: float = 0.0
    hose_id_inch: float = 0.0
    swivel_id_inch: float = 0.0
    kelly_length_m: float = 0.0
    kelly_id_inch: float = 0.0
    
    # Legacy field names retained for compatibility. A user-entered empirical
    # E factor is not evidence of API-standard provenance or compliance.
    use_api_constant: bool = False
    api_surface_loss_constant: float = 0.0
    swivel_length_m: float = 0.0


@dataclass 
class WellProfile:
    """پروفایل چاه"""
    well_type: str = "vertical"  # vertical, directional, horizontal, s_shape, j_shape
    kop_md: float = 0.0          # Kick Off Point (m)
    kop_tvd: float = 0.0
    eob_md: float = 0.0          # End of Build (m)
    eob_tvd: float = 0.0
    eob_inc: float = 0.0         # Inclination at EOB (degrees)
    target_md: float = 0.0
    target_tvd: float = 0.0
    target_inc: float = 0.0
    build_rate: float = 0.0      # °/30m; required for an explicit build-section profile
    
    # Survey points for complex wells: [(md, inc, azi), ...]
    survey_points: list = field(default_factory=list)
    
    def get_tvd_at_md(self, md: float) -> float:
        """محاسبه TVD در یک عمق MD مشخص"""
        if not isinstance(md, (int, float)) or isinstance(md, bool) or not math.isfinite(md) or md < 0:
            raise ValueError("measured depth must be finite and nonnegative")
        if self.well_type == "vertical":
            return md
        if self.survey_points:
            return self._interpolate_tvd(md)
        raise ValueError("directional TVD is unsupported without measured survey TVD points")
    
    def get_inc_at_md(self, md: float) -> float:
        """محاسبه Inclination در یک عمق MD"""
        if self.well_type == "vertical":
            return 0.0
        
        if md <= self.kop_md:
            return 0.0
        
        if self.eob_md > 0 and md <= self.eob_md:
            arc_length = md - self.kop_md
            inc = self.build_rate * arc_length / 30
            return min(inc, self.eob_inc)
        
        return self.eob_inc if self.eob_inc > 0 else self.target_inc
    
    def _interpolate_tvd(self, md: float) -> float:
        """Linearly interpolate explicitly recorded survey TVD between stations."""
        if len(self.survey_points) < 2:
            raise ValueError("at least two survey stations with TVD are required")
        normalized = []
        for index, point in enumerate(self.survey_points):
            if len(point) < 4:
                raise ValueError(f"survey station {index + 1} is missing measured TVD")
            station_md, station_tvd = point[0], point[3]
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in (station_md, station_tvd)
            ) or station_md < 0 or station_tvd < 0:
                raise ValueError(f"survey station {index + 1} has invalid MD/TVD")
            normalized.append((station_md, station_tvd))
        if any(current[0] <= previous[0] for previous, current in zip(normalized, normalized[1:])):
            raise ValueError("survey measured depths must be strictly increasing")
        if md < normalized[0][0] or md > normalized[-1][0]:
            raise ValueError("survey TVD does not cover requested measured depth")
        for (md1, tvd1), (md2, tvd2) in zip(normalized, normalized[1:]):
            if md1 <= md <= md2:
                fraction = (md - md1) / (md2 - md1)
                return tvd1 + fraction * (tvd2 - tvd1)
        return normalized[-1][1]


@dataclass
class HydraulicsResult:
    """نتایج محاسبات هیدرولیک"""
    # Unassessed calculations keep engineering outputs unknown (None); assessed
    # outputs are SCREENING and carry explicit assumptions/warnings.
    scope: str = "NOT_ASSESSED"
    assumptions: list = field(default_factory=list)

    # Unsupported calculations carry unknown outputs, never numeric zero answers.
    surface_loss_psi: float | None = None
    pipe_losses: list = field(default_factory=list)   # [(segment_name, loss_psi), ...]
    annulus_losses: list = field(default_factory=list) # [(segment_name, loss_psi), ...]
    bit_loss_psi: float | None = None
    total_loss_psi: float | None = None
    
    # ECD
    ecd_at_bit_ppg: float | None = None
    ecd_at_shoe_ppg: float | None = None
    ecd_profile: list = field(default_factory=list)  # [(depth_m, ecd_ppg), ...]
    
    # Bit hydraulics
    tfa_in2: float | None = None
    bit_hhp: float | None = None
    hsi: float | None = None
    jet_velocity_fps: float | None = None
    impact_force_lbs: float | None = None
    percent_bit_hp: float | None = None
    
    # Flow regime
    flow_regimes_pipe: list = field(default_factory=list)    # [(segment, "Laminar"/"Turbulent"), ...]
    flow_regimes_annulus: list = field(default_factory=list)
    
    # Velocities
    annular_velocities: list = field(default_factory=list)  # [(segment, av_fpm), ...]
    pipe_velocities: list = field(default_factory=list)
    
    # Critical flow rate (annular, deepest section)
    critical_flow_rate_gpm: float | None = None
    critical_velocity_ft_min: float | None = None
    critical_section: str = ""

    # سایر
    pump_output_bbl_stroke: float = 0.0
    flow_rate_gpm: float = 0.0
    
    # خطاها
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# ==================== Main Engine ====================

class AdvancedHydraulicsEngine:
    """Simplified drilling-hydraulics correlations with explicit unit conventions.

    The laminar Bingham equations follow Guo and Liu, “Mud Hydraulics
    Fundamentals,” Applied Drilling Circulation Systems (2011), Chapter 2,
    pp. 19–59, Eqs. 2.58–2.59, in US field units. Other branches are estimates;
    this class does not claim API standards compliance.
    """
    
    # ثابت‌ها
    STEEL_ROUGHNESS = 0.00015  # ft (roughness for steel pipe)
    WATER_DENSITY_PPG = 8.33
    
    def __init__(self):
        self.pipe_segments: List[PipeSegment] = []
        self.casing_sections: List[CasingSection] = []
        self.nozzles: List[BitNozzle] = []
        self.mud = MudProperties()
        self.surface_equipment = SurfaceEquipment()
        self.well_profile = WellProfile()
        self.flow_rate_gpm: float = 0.0
        self.bit_depth_m: float = 0.0
        self.bit_diameter_in: float | None = None
        self.model: str = "bingham"  # bingham, power_law, herschel_bulkley
    
    def calculate(self) -> HydraulicsResult:
        """Calculate a hydraulics profile only when operating/geometry inputs exist."""
        result = HydraulicsResult()
        result.flow_rate_gpm = self.flow_rate_gpm
        missing = []
        invalid = []

        def finite_number(value):
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )

        def require_positive(value, label):
            if value is None:
                missing.append(label)
            elif not finite_number(value):
                invalid.append(f"{label} must be a finite number")
            elif value <= 0:
                (missing if value == 0 else invalid).append(label)

        require_positive(self.flow_rate_gpm, "positive pump flow rate")
        require_positive(self.bit_depth_m, "positive bit measured depth")
        require_positive(self.mud.mw_pcf, "positive mud density")
        require_positive(self.mud.pv, "positive plastic viscosity")
        if self.mud.yp is None:
            missing.append("yield point")
        elif not finite_number(self.mud.yp) or self.mud.yp < 0:
            invalid.append("yield point must be finite and nonnegative")
        if not self.pipe_segments:
            missing.append("drill-string geometry")
        for index, segment in enumerate(self.pipe_segments):
            label = f"pipe segment {index + 1} OD/ID/length"
            for value, part in ((segment.od, "OD"), (segment.id, "ID"), (segment.length, "length")):
                require_positive(value, f"{label} {part}")
            if finite_number(segment.od) and finite_number(segment.id) and segment.id >= segment.od:
                invalid.append(f"{label} requires ID smaller than OD")

        if not self.casing_sections:
            missing.append("casing/open-hole interval geometry")
        for index, section in enumerate(self.casing_sections):
            label = f"bore section {index + 1} ID/top MD/bottom MD"
            for value, part in ((section.id, "ID"), (section.top_md, "top MD"), (section.bottom_md, "bottom MD")):
                if not finite_number(value):
                    invalid.append(f"{label} {part} must be finite")
                elif part == "ID" and value <= 0:
                    (missing if value == 0 else invalid).append(f"{label} {part}")
            if finite_number(section.top_md) and finite_number(section.bottom_md) and section.bottom_md <= section.top_md:
                invalid.append(f"{label} must have positive interval length")

        if not self.nozzles:
            missing.append("bit nozzle geometry")
        for index, nozzle in enumerate(self.nozzles):
            if not finite_number(nozzle.size_32nds) or nozzle.size_32nds <= 0:
                (missing if finite_number(nozzle.size_32nds) and nozzle.size_32nds == 0 else invalid).append(
                    f"bit nozzle {index + 1} size must be positive and finite"
                )
            if not finite_number(nozzle.quantity) or nozzle.quantity <= 0:
                (missing if finite_number(nozzle.quantity) and nozzle.quantity == 0 else invalid).append(
                    f"bit nozzle {index + 1} quantity must be positive and finite"
                )
        if self.bit_diameter_in is not None:
            require_positive(self.bit_diameter_in, "positive bit diameter")

        if self.model not in {"bingham", "power_law", "herschel_bulkley"}:
            invalid.append("unsupported rheology model")
        if self.model in {"power_law", "herschel_bulkley"}:
            require_positive(self.mud.theta300, "positive theta300")
            require_positive(self.mud.theta600, "positive theta600")
            if finite_number(self.mud.theta600) and finite_number(self.mud.theta300) and self.mud.theta600 <= self.mud.theta300:
                invalid.append("theta600 must exceed theta300")
        if self.model == "herschel_bulkley":
            for value, label in ((self.mud.theta3, "theta3"), (self.mud.theta6, "theta6")):
                if value is None:
                    missing.append(label)
                elif not finite_number(value) or value < 0:
                    invalid.append(f"{label} must be finite and nonnegative")

        surface = self.surface_equipment
        surface_pairs = (
            (surface.standpipe_length_m, surface.standpipe_id_inch, "standpipe"),
            (surface.hose_length_m, surface.hose_id_inch, "hose"),
            (surface.swivel_length_m, surface.swivel_id_inch, "swivel"),
            (surface.kelly_length_m, surface.kelly_id_inch, "kelly"),
        )
        for length, diameter, name in surface_pairs:
            for value in (length, diameter):
                if not finite_number(value) or value < 0:
                    invalid.append(f"{name} geometry must be finite and nonnegative")
            if finite_number(length) and finite_number(diameter) and (length > 0) != (diameter > 0):
                invalid.append(f"{name} requires both explicit length and ID")
        factor = surface.api_surface_loss_constant
        if not isinstance(surface.use_api_constant, bool):
            invalid.append("empirical surface-factor selection must be boolean")
        if not finite_number(factor) or factor < 0:
            invalid.append("empirical surface factor must be finite and nonnegative")
        if finite_number(factor) and factor > 0 and not surface.use_api_constant:
            invalid.append("empirical surface factor requires explicit selection")
        has_surface_geometry = any(
            finite_number(length) and length > 0 and finite_number(diameter) and diameter > 0
            for length, diameter, _ in surface_pairs
        )
        has_surface_factor = surface.use_api_constant and finite_number(factor) and factor > 0
        if not has_surface_geometry and not has_surface_factor:
            missing.append("surface-equipment geometry or an explicitly selected empirical factor")

        profile = self.well_profile
        if profile.well_type != "vertical" and not profile.survey_points:
            missing.append("directional measured survey TVD")
        if invalid:
            result.errors.append("Hydraulics not assessed: invalid " + "; ".join(dict.fromkeys(invalid)) + ".")
        if missing:
            result.errors.append("Hydraulics not assessed: missing " + ", ".join(dict.fromkeys(missing)) + ".")
        if result.errors:
            return result
        
        try:
            # 1. Build drill-string depth map from supplied pipe and bore geometry.
            segments_with_depth = self._build_depth_map()
            bit_depth_ft = self.bit_depth_m * 3.28084
            uncovered = [item for item in segments_with_depth if item["uncovered_ft"] > 0.5]
            if not segments_with_depth or abs(segments_with_depth[-1]["bot_ft"] - bit_depth_ft) > 0.5:
                result.errors.append(
                    "Hydraulics not assessed: supplied drill-string lengths do not reach the bit depth."
                )
                return result
            if uncovered:
                result.errors.append(
                    "Hydraulics not assessed: casing/open-hole geometry does not cover the full drill-string interval."
                )
                return result
            invalid_clearance = [
                f"{item['segment'].name} in {csg.name}"
                for item in segments_with_depth
                for csg, _length in item["overlaps"]
                if csg.id <= item["segment"].od
            ]
            if invalid_clearance:
                result.errors.append(
                    "Hydraulics not assessed: nonpositive annular clearance at "
                    + ", ".join(invalid_clearance) + "."
                )
                return result
            ordered_bores = sorted(self.casing_sections, key=lambda section: section.top_md)
            if any(
                current.top_md < previous.bottom_md - 1e-6
                for previous, current in zip(ordered_bores, ordered_bores[1:])
            ):
                result.errors.append("Hydraulics not assessed: overlapping bore-section intervals are ambiguous.")
                return result
            supplied_string_ft = sum(segment.length_ft for segment in self.pipe_segments)
            if supplied_string_ft > bit_depth_ft + 0.5:
                result.errors.append(
                    "Hydraulics not assessed: supplied drill-string length exceeds measured bit depth."
                )
                return result

            # 2. Surface losses, after minimum required inputs were validated.
            result.surface_loss_psi = self._calc_surface_losses()
            
            # 3. Pipe & Annulus losses for each segment
            total_pipe_loss = 0.0
            total_ann_loss = 0.0
            
            for seg_info in segments_with_depth:
                seg = seg_info['segment']
                overlaps = seg_info['overlaps']  # [(casing_section, overlap_length_ft), ...]
                
                for csg, overlap_ft in overlaps:
                    if overlap_ft <= 0:
                        continue
                    
                    # Pipe pressure loss
                    pipe_loss = self._calc_pipe_pressure_loss(
                        seg.id, overlap_ft, self.flow_rate_gpm
                    )
                    total_pipe_loss += pipe_loss
                    result.pipe_losses.append((
                        f"{seg.name} in {csg.name}",
                        round(pipe_loss, 2)
                    ))
                    
                    # Pipe velocity & regime
                    v_pipe = self._calc_velocity(self.flow_rate_gpm, seg.id)
                    regime_pipe = self._determine_flow_regime(v_pipe, seg.id, is_annular=False)
                    result.pipe_velocities.append((seg.name, round(v_pipe * 60, 1)))  # ft/min
                    result.flow_regimes_pipe.append((seg.name, regime_pipe))
                    
                    # Annular pressure loss
                    gap = csg.id - seg.od
                    if gap > 0:
                        ann_loss = self._calc_annular_pressure_loss(
                            csg.id, seg.od, overlap_ft, self.flow_rate_gpm
                        )
                        total_ann_loss += ann_loss
                        result.annulus_losses.append((
                            f"{seg.name} vs {csg.name}",
                            round(ann_loss, 2)
                        ))
                        
                        # Annular velocity
                        v_ann = self._calc_annular_velocity(self.flow_rate_gpm, csg.id, seg.od)
                        regime_ann = self._determine_flow_regime(v_ann, gap, is_annular=True)
                        result.annular_velocities.append((
                            f"{seg.name} in {csg.name}",
                            round(v_ann * 60, 1)
                        ))
                        result.flow_regimes_annulus.append((
                            f"{seg.name} vs {csg.name}",
                            regime_ann
                        ))
                        
                        # Check minimum AV
                        av_fpm = v_ann * 60
                        if av_fpm < 100:
                            result.warnings.append(
                                f"Low AV ({av_fpm:.0f} ft/min) in {seg.name} vs {csg.name}. "
                                f"Min recommended: 100 ft/min"
                            )

                        # Critical (laminar→turbulent) flow rate for this
                        # annulus — same correlation as _determine_flow_regime.
                        # Overwritten per section so the deepest one (at the
                        # bit) is reported.
                        try:
                            qc = self.calc_critical_flow_rate(
                                self.mud.mw_ppg, self.mud.pv, self.mud.yp,
                                csg.id, seg.od
                            )
                            result.critical_flow_rate_gpm = qc["critical_flow_rate_gpm"]
                            result.critical_velocity_ft_min = qc["critical_velocity_ft_min"]
                            result.critical_section = f"{seg.name} vs {csg.name}"
                        except ValueError:
                            pass
            
            # 4. Bit pressure loss
            tfa = sum(n.total_area for n in self.nozzles)
            result.tfa_in2 = round(tfa, 4)
            
            if tfa > 0:
                result.bit_loss_psi = self.calc_bit_pressure_drop(
                    self.flow_rate_gpm, self.mud.mw_ppg, tfa
                )
                result.bit_hhp = self.calc_bit_hhp(self.flow_rate_gpm, result.bit_loss_psi)
                result.jet_velocity_fps = self.calc_jet_velocity(self.flow_rate_gpm, tfa)
                result.impact_force_lbs = self.calc_impact_force(
                    self.mud.mw_ppg, self.flow_rate_gpm, result.jet_velocity_fps
                )
                if self.bit_diameter_in is not None and self.bit_diameter_in > 0:
                    result.hsi = self.calc_hsi(result.bit_hhp, self.bit_diameter_in)
                else:
                    result.warnings.append(
                        "HSI not assessed: bit diameter was not supplied."
                    )
            
            # 5. Total
            result.total_loss_psi = round(
                result.surface_loss_psi + total_pipe_loss + total_ann_loss + result.bit_loss_psi, 1
            )
            
            # Percent bit HP
            if result.total_loss_psi > 0:
                result.percent_bit_hp = round(
                    result.bit_loss_psi / result.total_loss_psi * 100, 1
                )
            
            # 6. ECD Profile
            result.ecd_profile = self._calc_ecd_profile(result)
            if result.ecd_profile:
                result.ecd_at_bit_ppg = result.ecd_profile[-1][1]
                
                # ECD at shoe
                shoe_depth = max((c.bottom_md for c in self.casing_sections
                                  if c.section_type == "casing"), default=0)
                for depth, ecd in result.ecd_profile:
                    if depth >= shoe_depth:
                        result.ecd_at_shoe_ppg = ecd
                        break
            result.scope = "SCREENING"
            result.assumptions.extend((
                "Simplified drilling-hydraulics correlations; not a standards-compliance certification.",
                "Surface loss includes only explicitly supplied component dimensions or a selected empirical factor.",
            ))
            result.warnings.extend(result.assumptions)
            if self.model == "herschel_bulkley":
                result.warnings.append(
                    "Herschel-Bulkley pressure loss is a Power Law plus yield-stress screening approximation, not a full HB solver."
                )
            if not result.ecd_profile:
                result.warnings.append("ECD profile not assessed because supplied geometry is incomplete.")
            
        except Exception as e:
            logger.error(f"Hydraulics calculation error: {e}")
            result.errors.append(str(e))
            result.scope = "NOT_ASSESSED"
            for name in (
                "surface_loss_psi", "bit_loss_psi", "total_loss_psi",
                "ecd_at_bit_ppg", "ecd_at_shoe_ppg", "tfa_in2", "bit_hhp",
                "hsi", "jet_velocity_fps", "impact_force_lbs", "percent_bit_hp",
                "critical_flow_rate_gpm", "critical_velocity_ft_min",
            ):
                setattr(result, name, None)
            result.pipe_losses.clear()
            result.annulus_losses.clear()
            result.ecd_profile.clear()
            result.pipe_velocities.clear()
            result.annular_velocities.clear()
            result.flow_regimes_pipe.clear()
            result.flow_regimes_annulus.clear()
        
        return result

    # ==================== Surface Losses ====================
    
    def _calc_surface_losses(self) -> float:
        """محاسبه افت فشار سطحی"""
        se = self.surface_equipment
        
        if se.use_api_constant and se.api_surface_loss_constant > 0:
            return se.api_surface_loss_constant * self.mud.mw_ppg * self.flow_rate_gpm**1.86 / 1e6
        
        total = 0.0
        
        # Standpipe
        if se.standpipe_id_inch > 0 and se.standpipe_length_m > 0:
            total += self._calc_pipe_pressure_loss(
                se.standpipe_id_inch, se.standpipe_length_m * 3.28084, self.flow_rate_gpm
            )
        
        # Hose
        if se.hose_id_inch > 0 and se.hose_length_m > 0:
            total += self._calc_pipe_pressure_loss(
                se.hose_id_inch, se.hose_length_m * 3.28084, self.flow_rate_gpm
            )
        
        # Swivel: require an explicit length; never substitute an assumed 5 ft.
        if se.swivel_id_inch > 0 and se.swivel_length_m > 0:
            total += self._calc_pipe_pressure_loss(
                se.swivel_id_inch, se.swivel_length_m * 3.28084, self.flow_rate_gpm
            )
        
        # Kelly
        if se.kelly_id_inch > 0 and se.kelly_length_m > 0:
            total += self._calc_pipe_pressure_loss(
                se.kelly_id_inch, se.kelly_length_m * 3.28084, self.flow_rate_gpm
            )
        
        return round(total, 2)

    # ==================== Pipe Pressure Loss ====================
    
    def _calc_pipe_pressure_loss(self, id_inch: float, length_ft: float, 
                                  gpm: float) -> float:
        """افت فشار در لوله"""
        if id_inch <= 0 or length_ft <= 0 or gpm <= 0:
            return 0.0
        
        mw = self.mud.mw_ppg
        pv = self.mud.pv
        yp = self.mud.yp
        
        # Velocity (ft/s)
        v = gpm / (2.448 * id_inch**2)
        
        if self.model == "bingham":
            return self._bingham_pipe_loss(v, id_inch, length_ft, mw, pv, yp)
        elif self.model == "power_law":
            return self._power_law_pipe_loss(v, id_inch, length_ft, mw)
        elif self.model == "herschel_bulkley":
            return self._hb_pipe_loss(v, id_inch, length_ft, mw)
        
        return 0.0
    
    @staticmethod
    def bingham_laminar_pipe_loss_components(pv_cp: float, yp_lbf100ft2: float,
                                            velocity_fps: float, diameter_in: float,
                                            length_ft: float) -> Dict[str, float]:
        """Simplified Bingham laminar pipe loss in psi (US field units).

        Inputs: PV [cP], YP [lbf/100 ft²], mean velocity [ft/s],
        inside diameter [in], and length [ft].  This drilling-hydraulics
        correlation uses 1500 for the viscous term and 225 for the yield term;
        it is an approximate model, not a general non-Newtonian pipe solver.
        """
        values = (pv_cp, yp_lbf100ft2, velocity_fps, diameter_in, length_ft)
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("Bingham inputs must be finite real numbers")
        if diameter_in <= 0 or length_ft < 0 or min(pv_cp, yp_lbf100ft2, velocity_fps) < 0:
            raise ValueError("Bingham inputs must be nonnegative and diameter positive")
        return {
            "viscous_psi": pv_cp * velocity_fps * length_ft / (1500.0 * diameter_in**2),
            "yield_psi": yp_lbf100ft2 * length_ft / (225.0 * diameter_in),
        }

    @staticmethod
    def bingham_laminar_pipe_loss(pv_cp: float, yp_lbf100ft2: float,
                                  velocity_fps: float, diameter_in: float,
                                  length_ft: float) -> float:
        """Total of the canonical Bingham laminar pipe components in psi."""
        return sum(AdvancedHydraulicsEngine.bingham_laminar_pipe_loss_components(
            pv_cp, yp_lbf100ft2, velocity_fps, diameter_in, length_ft
        ).values())

    @staticmethod
    def bingham_laminar_annular_loss_components(pv_cp: float, yp_lbf100ft2: float,
                                     velocity_fps: float, gap_in: float,
                                     length_ft: float) -> float:
        """Simplified concentric-annulus Bingham loss in psi (US field units).

        The model uses radial clearance ``Dh-Dp`` [in], mean annular velocity
        [ft/s], and the drilling correlation constants 1000 and 200.  This
        approximation does not represent eccentricity, rotation, or local
        restrictions.
        """
        values = (pv_cp, yp_lbf100ft2, velocity_fps, gap_in, length_ft)
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("Bingham inputs must be finite real numbers")
        if gap_in <= 0 or length_ft < 0 or min(pv_cp, yp_lbf100ft2, velocity_fps) < 0:
            raise ValueError("Bingham inputs must be nonnegative and gap positive")
        return {
            "viscous_psi": pv_cp * velocity_fps * length_ft / (1000.0 * gap_in**2),
            "yield_psi": yp_lbf100ft2 * length_ft / (200.0 * gap_in),
        }

    @staticmethod
    def bingham_laminar_annular_loss(pv_cp: float, yp_lbf100ft2: float,
                                     velocity_fps: float, gap_in: float,
                                     length_ft: float) -> float:
        """Total of the canonical Bingham laminar annular components in psi."""
        return sum(AdvancedHydraulicsEngine.bingham_laminar_annular_loss_components(
            pv_cp, yp_lbf100ft2, velocity_fps, gap_in, length_ft
        ).values())

    def _bingham_pipe_loss(self, v: float, d: float, L: float,
                            mw: float, pv: float, yp: float) -> float:
        """Simplified Bingham pipe estimate with laminar/turbulent branches."""
        values = (v, d, L, mw, pv, yp)
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("Bingham pipe inputs must be finite real numbers")
        if d <= 0 or mw <= 0 or L < 0 or v < 0 or pv <= 0 or yp < 0:
            raise ValueError("Bingham pipe inputs require positive ID, MW and PV; other inputs must be nonnegative")
        
        # Critical velocity
        vc = (1.08 * pv + 1.08 * math.sqrt(pv**2 + 12.34 * d**2 * yp * mw)) / (mw * d)
        
        if v >= vc:
            # Turbulent
            return mw**0.75 * v**1.75 * pv**0.25 * L / (1800 * d**1.25)
        else:
            # Laminar. At YP=0 this reduces to the Newtonian pipe equation;
            # the field-unit coefficient 1500 is consistent with Poiseuille's
            # exact 1496.3 conversion for these input units.
            return self.bingham_laminar_pipe_loss(pv, yp, v, d, L)
    
    def _power_law_pipe_loss(self, v: float, d: float, L: float, mw: float) -> float:
        """Power Law Model - Pipe"""
        n = self.mud.n_power_law
        k = self.mud.k_power_law
        pv = self.mud.pv
        
        if d <= 0 or mw <= 0:
            return 0.0
        
        # Critical velocity
        if (2 - n) != 0:
            vc = ((58200.0 * k / mw) ** (1.0 / (2.0 - n))) / 60.0 * \
                 ((1.6 / d) * ((3.0 * n + 1.0) / (4.0 * n))) ** (n / (2.0 - n))
        else:
            vc = 999
        
        if v >= vc:
            # Empirical turbulent branch; no API-compliance claim is made.
            return 3.6033e-4 * mw**0.8 * v**1.8 * pv**0.2 * L / (d**1.2)
        else:
            # Laminar
            gamma = (96.0 * v / d) * (3.0 * n + 1.0) / (4.0 * n)
            return (gamma ** n) * (k * L / (300.0 * d))
    
    def _hb_pipe_loss(self, v: float, d: float, L: float, mw: float) -> float:
        """Herschel-Bulkley Model - Pipe (approximate)"""
        tau_y = self.mud.tau_y_hb
        
        if d <= 0:
            return 0.0
        
        # Approximate: HB ≈ Power Law + Yield stress contribution
        pl_loss = self._power_law_pipe_loss(v, d, L, mw)
        yield_contrib = tau_y * L / (225 * d)
        
        return pl_loss + yield_contrib

    # ==================== Annular Pressure Loss ====================
    
    def _calc_annular_pressure_loss(self, hole_id: float, pipe_od: float,
                                      length_ft: float, gpm: float) -> float:
        """افت فشار در آنولوس"""
        gap = hole_id - pipe_od
        if gap <= 0 or length_ft <= 0 or gpm <= 0:
            return 0.0
        
        mw = self.mud.mw_ppg
        pv = self.mud.pv
        yp = self.mud.yp
        
        # Annular velocity (ft/s)
        v_ann = gpm / (2.448 * (hole_id**2 - pipe_od**2))
        
        if self.model == "bingham":
            return self._bingham_annular_loss(v_ann, gap, hole_id, pipe_od, length_ft, mw, pv, yp)
        elif self.model == "power_law":
            return self._power_law_annular_loss(v_ann, gap, hole_id, pipe_od, length_ft, mw, gpm)
        elif self.model == "herschel_bulkley":
            return self._hb_annular_loss(v_ann, gap, hole_id, pipe_od, length_ft, mw, gpm)
        
        return 0.0
    
    def _bingham_annular_loss(self, v: float, gap: float, d_h: float, d_p: float,
                                L: float, mw: float, pv: float, yp: float) -> float:
        """Simplified Bingham annulus estimate with laminar/turbulent branches."""
        values = (v, gap, d_h, d_p, L, mw, pv, yp)
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("Bingham annular inputs must be finite real numbers")
        if gap <= 0 or d_h <= d_p or d_p <= 0 or L < 0 or v < 0 or mw <= 0 or pv <= 0 or yp < 0:
            raise ValueError("Bingham annular inputs have invalid dimensions or rheology")
        
        vc_a = (1.08 * pv + 1.08 * math.sqrt(pv**2 + 9.26 * gap**2 * yp * mw)) / (mw * gap)
        
        if v >= vc_a:
            return mw**0.75 * v**1.75 * pv**0.25 * L / (1396 * gap**1.25)
        else:
            return self.bingham_laminar_annular_loss(pv, yp, v, gap, L)
    
    def _power_law_annular_loss(self, v: float, gap: float, d_h: float, d_p: float,
                                  L: float, mw: float, gpm: float) -> float:
        """Power Law Model - Annulus"""
        n = self.mud.n_power_law
        k = self.mud.k_power_law
        pv = self.mud.pv
        
        if gap <= 0 or mw <= 0:
            return 0.0
        
        if (2 - n) != 0:
            vc_a = ((38780.0 * k / mw) ** (1.0 / (2.0 - n))) / 60.0 * \
                   ((2.4 / gap) * ((2.0 * n + 1.0) / (3.0 * n))) ** (n / (2.0 - n))
        else:
            vc_a = 999
        
        if v >= vc_a:
            return 7.7e-5 * mw**0.8 * gpm**1.8 * pv**0.2 * L / \
                   (gap**3 * (d_h + d_p)**1.8)
        else:
            gamma = (144.0 * v / gap) * (2.0 * n + 1.0) / (3.0 * n)
            return (gamma ** n) * (k * L / (300.0 * gap))
    
    def _hb_annular_loss(self, v: float, gap: float, d_h: float, d_p: float,
                           L: float, mw: float, gpm: float) -> float:
        """Herschel-Bulkley - Annulus (approximate)"""
        tau_y = self.mud.tau_y_hb
        pl_loss = self._power_law_annular_loss(v, gap, d_h, d_p, L, mw, gpm)
        yield_contrib = tau_y * L / (200 * gap) if gap > 0 else 0
        return pl_loss + yield_contrib

    # ==================== Helper Methods ====================
    
    @staticmethod
    def _calc_velocity(gpm: float, id_inch: float) -> float:
        """سرعت سیال (ft/s)"""
        if id_inch <= 0:
            return 0.0
        return gpm / (2.448 * id_inch**2)
    
    @staticmethod
    def _calc_annular_velocity(gpm: float, hole_id: float, pipe_od: float) -> float:
        """سرعت آنولوس (ft/s)"""
        area = hole_id**2 - pipe_od**2
        if area <= 0:
            return 0.0
        return gpm / (2.448 * area)
    
    def _determine_flow_regime(self, velocity_fps: float, hydraulic_diameter: float,
                                is_annular: bool = False) -> str:
        """تعیین رژیم جریان"""
        if hydraulic_diameter <= 0:
            return "Unknown"
        
        mw = self.mud.mw_ppg
        pv = self.mud.pv
        yp = self.mud.yp
        
        if is_annular:
            vc = (1.08 * pv + 1.08 * math.sqrt(pv**2 + 9.26 * hydraulic_diameter**2 * yp * mw)) / \
                 (mw * hydraulic_diameter) if mw * hydraulic_diameter > 0 else 0
        else:
            vc = (1.08 * pv + 1.08 * math.sqrt(pv**2 + 12.34 * hydraulic_diameter**2 * yp * mw)) / \
                 (mw * hydraulic_diameter) if mw * hydraulic_diameter > 0 else 0
        
        if velocity_fps >= vc:
            return "Turbulent"
        elif velocity_fps >= vc * 0.8:
            return "Transitional"
        else:
            return "Laminar"
    
    def _build_depth_map(self) -> list:
        """ساخت نقشه عمقی لوله‌ها با overlap کیسینگ"""
        bit_depth_ft = self.bit_depth_m * 3.28084
        
        # ساخت لیست segments با عمق
        segments_info = []
        current_depth_ft = 0.0
        
        for seg in self.pipe_segments:
            seg_length_ft = seg.length_ft
            seg_top = current_depth_ft
            seg_bot = min(current_depth_ft + seg_length_ft, bit_depth_ft)
            
            if seg_bot <= seg_top:
                continue
            
            # پیدا کردن overlaps با casing sections
            overlaps = []
            for csg in self.casing_sections:
                csg_top_ft = csg.top_md * 3.28084
                csg_bot_ft = csg.bottom_md * 3.28084
                
                ov_top = max(seg_top, csg_top_ft)
                ov_bot = min(seg_bot, csg_bot_ft)
                ov_len = ov_bot - ov_top
                
                if ov_len > 0:
                    overlaps.append((csg, ov_len))
            
            # Unmapped depth remains unknown: never synthesize an open-hole ID
            # from the largest pipe OD or another display/calculation default.
            covered_ft = sum(ov[1] for ov in overlaps)
            remaining_ft = max(0.0, (seg_bot - seg_top) - covered_ft)
            
            segments_info.append({
                'segment': seg,
                'top_ft': seg_top,
                'bot_ft': seg_bot,
                'overlaps': overlaps,
                'uncovered_ft': remaining_ft,
            })
            
            current_depth_ft = seg_bot
        
        return segments_info

    # ==================== ECD Profile ====================
    
    def _calc_ecd_profile(self, result: HydraulicsResult) -> list:
        """Return geometry-weighted ECD at MD stations (US field units).

        Cumulative annular friction is integrated over the explicitly supplied
        pipe/casing intervals above each station. It is not distributed as a
        linear fraction of total loss by measured depth. The denominator uses
        trajectory TVD from the selected well profile.
        """
        profile = []
        bit_depth_m = self.bit_depth_m
        if bit_depth_m <= 0:
            return profile

        segments = self._build_depth_map()
        if (
            not segments
            or abs(segments[-1]["bot_ft"] - bit_depth_m * 3.28084) > 0.5
            or any(item["uncovered_ft"] > 0.5 for item in segments)
        ):
            return profile

        intervals = 20
        step = bit_depth_m / intervals
        for i in range(intervals + 1):
            depth_m = i * step
            depth_ft = depth_m * 3.28084
            tvd_m = self.well_profile.get_tvd_at_md(depth_m)
            tvd_ft = tvd_m * 3.28084
            if tvd_ft <= 0:
                profile.append((round(depth_m, 1), self.mud.mw_ppg))
                continue

            cumulative_ann_loss = 0.0
            for item in segments:
                seg = item["segment"]
                for csg, _overlap_ft in item["overlaps"]:
                    csg_top_ft = csg.top_md * 3.28084
                    csg_bottom_ft = csg.bottom_md * 3.28084
                    interval_top = max(item["top_ft"], csg_top_ft)
                    interval_bottom = min(item["bot_ft"], csg_bottom_ft, depth_ft)
                    interval_length = interval_bottom - interval_top
                    if interval_length > 0:
                        cumulative_ann_loss += self._calc_annular_pressure_loss(
                            csg.id, seg.od, interval_length, self.flow_rate_gpm
                        )

            ecd = self.mud.mw_ppg + cumulative_ann_loss / (0.052 * tvd_ft)
            profile.append((round(depth_m, 1), round(ecd, 3)))
        return profile

    # ==================== Surge/Swab ====================
    
    def calc_surge_swab(self, trip_speed_fpm: float | None = None,
                         operation: str | None = None,
                         pipe_open: bool | None = None) -> Dict:
        """Return a geometry-aware surge/swab *screening* calculation.

        Trip and induced annular velocities are first expressed in ft/min using
        the Moore-style displacement ratio and the 1.5 maximum-velocity factor.
        They are converted to ft/s only when delegated to this engine's
        canonical annular pressure-loss model. No separate shear-rate/pressure
        equation or synthetic hole diameter is used.
        """
        warnings = [
            "Screening approximation: concentric annulus, 0.45 clinging factor, "
            "1.5 maximum-velocity factor, and selected simplified rheology; not an operational guarantee."
        ]
        operation_label = {"RIH": "Surge", "POOH": "Swab"}.get(operation, "Not selected")
        invalid = []
        missing = []

        def finite(value):
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )

        if trip_speed_fpm is None or trip_speed_fpm == 0:
            missing.append("positive trip speed")
        elif not finite(trip_speed_fpm) or trip_speed_fpm < 0:
            invalid.append("trip speed must be finite and positive")
        if operation is None:
            missing.append("operation (RIH or POOH)")
        elif operation not in {"RIH", "POOH"}:
            invalid.append("operation must be RIH or POOH")
        if pipe_open is None:
            missing.append("open/closed pipe selection")
        elif not isinstance(pipe_open, bool):
            invalid.append("open/closed pipe selection must be boolean")

        for value, label in (
            (self.bit_depth_m, "positive bit measured depth"),
            (self.mud.mw_pcf, "positive mud density"),
        ):
            if value is None or value == 0:
                missing.append(label)
            elif not finite(value) or value < 0:
                invalid.append(f"{label} must be finite and positive")
        if self.model not in {"bingham", "power_law", "herschel_bulkley"}:
            invalid.append("unsupported rheology model")
        if self.model == "bingham":
            if not finite(self.mud.pv) or self.mud.pv <= 0:
                (missing if finite(self.mud.pv) and self.mud.pv == 0 else invalid).append(
                    "positive plastic viscosity"
                )
            if self.mud.yp is None:
                missing.append("yield point")
            elif not finite(self.mud.yp) or self.mud.yp < 0:
                invalid.append("yield point must be finite and nonnegative")
        else:
            for value, label in ((self.mud.theta300, "theta300"), (self.mud.theta600, "theta600")):
                if not finite(value) or value <= 0:
                    (missing if finite(value) and value == 0 else invalid).append(f"positive {label}")
            if finite(self.mud.theta300) and finite(self.mud.theta600) and self.mud.theta600 <= self.mud.theta300:
                invalid.append("theta600 must exceed theta300")
            if self.model == "herschel_bulkley":
                for value, label in ((self.mud.theta3, "theta3"), (self.mud.theta6, "theta6")):
                    if not finite(value) or value < 0:
                        (missing if value is None or (finite(value) and value == 0) else invalid).append(
                            f"nonnegative {label} reading"
                        )

        if not self.pipe_segments:
            missing.append("drill-string geometry")
        if not self.casing_sections:
            missing.append("casing/open-hole interval geometry")
        for index, segment in enumerate(self.pipe_segments):
            for value, label in ((segment.od, "OD"), (segment.length, "length")):
                if not finite(value) or value <= 0:
                    (missing if finite(value) and value == 0 else invalid).append(
                        f"pipe segment {index + 1} positive finite {label}"
                    )
            if pipe_open is True and (not finite(segment.id) or segment.id <= 0):
                (missing if finite(segment.id) and segment.id == 0 else invalid).append(
                    f"pipe segment {index + 1} ID for open-pipe displacement"
                )
            if pipe_open is True and finite(segment.id) and finite(segment.od) and segment.id >= segment.od:
                invalid.append(f"pipe segment {index + 1} ID must be smaller than OD")
        for index, section in enumerate(self.casing_sections):
            for value, label in ((section.id, "ID"), (section.top_md, "top MD"), (section.bottom_md, "bottom MD")):
                if not finite(value):
                    invalid.append(f"bore section {index + 1} {label} must be finite")
                elif label == "ID" and value <= 0:
                    (missing if value == 0 else invalid).append(f"bore section {index + 1} positive ID")
            if finite(section.top_md) and finite(section.bottom_md) and section.bottom_md <= section.top_md:
                invalid.append(f"bore section {index + 1} must have positive interval length")
        ordered_sections = sorted(self.casing_sections, key=lambda section: section.top_md if finite(section.top_md) else 0)
        if any(
            finite(previous.bottom_md) and finite(current.top_md)
            and current.top_md < previous.bottom_md - 1e-6
            for previous, current in zip(ordered_sections, ordered_sections[1:])
        ):
            invalid.append("bore-section intervals overlap")

        profile = self.well_profile
        if profile.well_type != "vertical" and not profile.survey_points:
            missing.append("directional measured survey TVD")

        if not invalid and not missing:
            bit_depth_ft = self.bit_depth_m * 3.28084
            supplied_length_ft = sum(segment.length_ft for segment in self.pipe_segments)
            if supplied_length_ft < bit_depth_ft - 0.5:
                missing.append("pipe program does not reach bit depth")
            elif supplied_length_ft > bit_depth_ft + 0.5:
                invalid.append("pipe program exceeds bit depth")
            depth_map = self._build_depth_map()
            if not depth_map or abs(depth_map[-1]["bot_ft"] - bit_depth_ft) > 0.5:
                missing.append("pipe program does not reach bit depth")
            if any(item["uncovered_ft"] > 0.5 for item in depth_map):
                missing.append("casing/open-hole geometry does not cover the pipe interval")
            for item in depth_map:
                if any(section.id <= item["segment"].od for section, _length in item["overlaps"]):
                    invalid.append(f"nonpositive annular clearance in {item['segment'].name or 'pipe segment'}")

        if invalid or missing:
            warnings.extend(f"Invalid: {item}." for item in dict.fromkeys(invalid))
            warnings.extend(f"Missing: {item}." for item in dict.fromkeys(missing))
            return {
                "type": operation_label,
                "scope": "NOT_ASSESSED",
                "total_pressure_psi": None,
                "equiv_mw_ppg": None,
                "equiv_mw_pcf": None,
                "segments": [],
                "unassessed_segments": list(dict.fromkeys(invalid + missing)),
                "warnings": warnings,
                "trip_speed_fpm": trip_speed_fpm,
                "pipe_status": "Open" if pipe_open is True else "Closed" if pipe_open is False else "Not selected",
            }

        total_pressure = 0.0
        segment_results = []
        for item in depth_map:
            segment = item["segment"]
            for section, overlap_ft in item["overlaps"]:
                hole_id = section.id
                pipe_od = segment.od
                annular_area_factor = hole_id**2 - pipe_od**2
                if pipe_open:
                    displacement_area_factor = pipe_od**2 - segment.id**2
                    displacement_flow_area_factor = annular_area_factor + segment.id**2
                else:
                    displacement_area_factor = pipe_od**2
                    displacement_flow_area_factor = annular_area_factor
                if displacement_flow_area_factor <= 0 or annular_area_factor <= 0:
                    warnings.append(f"Invalid annular area in {segment.name or 'pipe segment'} vs {section.name}.")
                    return {
                        "type": operation_label,
                        "scope": "NOT_ASSESSED", "total_pressure_psi": None,
                        "equiv_mw_ppg": None, "equiv_mw_pcf": None,
                        "segments": [], "unassessed_segments": ["nonpositive annular area"],
                        "warnings": warnings, "trip_speed_fpm": trip_speed_fpm,
                        "pipe_status": "Open" if pipe_open else "Closed",
                    }
                induced_velocity_fpm = (
                    0.45 + displacement_area_factor / displacement_flow_area_factor
                ) * trip_speed_fpm
                maximum_velocity_fpm = 1.5 * induced_velocity_fpm
                maximum_velocity_fps = maximum_velocity_fpm / 60.0
                equivalent_flow_gpm = maximum_velocity_fps * 2.448 * annular_area_factor
                pressure = self._calc_annular_pressure_loss(
                    hole_id, pipe_od, overlap_ft, equivalent_flow_gpm
                )
                total_pressure += pressure
                segment_results.append({
                    "segment": f"{segment.name} in {section.name}",
                    "pressure_psi": round(pressure, 2),
                    "fluid_velocity_ft_min": round(induced_velocity_fpm, 2),
                    "maximum_velocity_ft_min": round(maximum_velocity_fpm, 2),
                })

        try:
            tvd_ft = self.well_profile.get_tvd_at_md(self.bit_depth_m) * 3.28084
        except (TypeError, ValueError, OverflowError):
            tvd_ft = 0.0
        if not finite(tvd_ft) or tvd_ft <= 0:
            return {
                "type": operation_label,
                "scope": "NOT_ASSESSED", "total_pressure_psi": None,
                "equiv_mw_ppg": None, "equiv_mw_pcf": None,
                "segments": [], "unassessed_segments": ["positive finite TVD is required"],
                "warnings": warnings + ["Missing: positive finite TVD."],
                "trip_speed_fpm": trip_speed_fpm,
                "pipe_status": "Open" if pipe_open else "Closed",
            }
        sign = 1.0 if operation == "RIH" else -1.0
        equiv_mw = self.mud.mw_ppg + sign * total_pressure / (0.052 * tvd_ft)
        return {
            "type": operation_label,
            "scope": "SCREENING",
            "total_pressure_psi": round(total_pressure, 1),
            "equiv_mw_ppg": round(equiv_mw, 3),
            "equiv_mw_pcf": round(equiv_mw * 7.48052, 2),
            "segments": segment_results,
            "unassessed_segments": [],
            "warnings": warnings,
            "trip_speed_fpm": trip_speed_fpm,
            "pipe_status": "Open" if pipe_open else "Closed",
        }

    # ==================== Static Utility Methods ====================
    
    # ------------------------------------------------------------------
    # Bit hydraulics — single canonical source for ΔP, HHP, HSI, jet
    # velocity and impact force (used by calculate() and all UI tabs).
    # Constants: 10858 (ΔP), 1714 (HHP), 3.117 (jet velocity), 1930 (IF).
    # ------------------------------------------------------------------
    @staticmethod
    def _require_finite_engineering_inputs(**values) -> None:
        for name, value in values.items():
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite real number")

    @staticmethod
    def calc_bit_pressure_drop(gpm: float, mw_ppg: float, tfa_in2: float) -> float:
        """Bit nozzle pressure drop (psi).

            ΔP = Q² × MW / (10858 × TFA²)      (Q in gpm, MW in ppg, TFA in in²)
        """
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(gpm=gpm, mw_ppg=mw_ppg, tfa_in2=tfa_in2)
        if gpm <= 0:
            raise ValueError("gpm must be > 0")
        if mw_ppg <= 0:
            raise ValueError("mw_ppg must be > 0")
        if tfa_in2 <= 0:
            raise ValueError("TFA must be > 0")
        return gpm**2 * mw_ppg / (10858.0 * tfa_in2**2)

    @staticmethod
    def calc_tfa_from_pressure_drop(gpm: float, mw_ppg: float,
                                    delta_p_psi: float) -> float:
        """Required TFA (in²) to achieve a target bit pressure drop.

            TFA = √(Q² × MW / (10858 × ΔP))
        """
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(
            gpm=gpm, mw_ppg=mw_ppg, delta_p_psi=delta_p_psi
        )
        if gpm <= 0:
            raise ValueError("gpm must be > 0")
        if mw_ppg <= 0:
            raise ValueError("mw_ppg must be > 0")
        if delta_p_psi <= 0:
            raise ValueError("delta_p_psi must be > 0")
        return math.sqrt(gpm**2 * mw_ppg / (10858.0 * delta_p_psi))

    @staticmethod
    def calc_bit_hhp(gpm: float, pressure_drop_psi: float) -> float:
        """Bit hydraulic horsepower.

            HHP = Q × ΔP / 1714
        """
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(
            gpm=gpm, pressure_drop_psi=pressure_drop_psi
        )
        if gpm <= 0 or pressure_drop_psi <= 0:
            raise ValueError("Flow and pressure drop must be positive")
        return gpm * pressure_drop_psi / 1714.0

    @staticmethod
    def calc_hsi(bit_hhp: float, bit_od_in: float) -> float:
        """Hydraulic horsepower per square inch of bit area."""
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(bit_hhp=bit_hhp, bit_od_in=bit_od_in)
        if bit_hhp <= 0:
            raise ValueError("bit_hhp must be > 0")
        if bit_od_in <= 0:
            raise ValueError("bit_od_in must be > 0")
        area = math.pi / 4.0 * bit_od_in**2
        return bit_hhp / area

    @staticmethod
    def calc_jet_velocity(gpm: float, tfa_in2: float) -> float:
        """Nozzle jet velocity (ft/s)."""
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(gpm=gpm, tfa_in2=tfa_in2)
        if gpm <= 0:
            raise ValueError("gpm must be > 0")
        if tfa_in2 <= 0:
            raise ValueError("TFA must be > 0")
        return gpm / (3.117 * tfa_in2)

    @staticmethod
    def calc_impact_force(mw_ppg: float, gpm: float,
                          jet_velocity_fps: float) -> float:
        """Hydraulic impact force (lbf).

            F = MW × Q × v / 1930
        """
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(
            mw_ppg=mw_ppg, gpm=gpm, jet_velocity_fps=jet_velocity_fps
        )
        if mw_ppg <= 0 or gpm <= 0 or jet_velocity_fps <= 0:
            raise ValueError("MW, flow and jet velocity must be positive")
        return mw_ppg * gpm * jet_velocity_fps / 1930.0

    @staticmethod
    def calc_bit_hydraulics(gpm: float, mw_ppg: float, tfa_in2: float,
                            bit_od_in: float) -> dict:
        """Complete bit hydraulics set (ΔP, HHP, HSI, jet velocity, IF)."""
        dp = AdvancedHydraulicsEngine.calc_bit_pressure_drop(gpm, mw_ppg, tfa_in2)
        hhp = AdvancedHydraulicsEngine.calc_bit_hhp(gpm, dp)
        jv = AdvancedHydraulicsEngine.calc_jet_velocity(gpm, tfa_in2)
        return {
            "bit_pressure_drop_psi": round(dp, 1),
            "bit_hhp": round(hhp, 2),
            "hsi": round(AdvancedHydraulicsEngine.calc_hsi(hhp, bit_od_in), 2),
            "jet_velocity_fps": round(jv, 1),
            "impact_force_lbs": round(
                AdvancedHydraulicsEngine.calc_impact_force(mw_ppg, gpm, jv), 1),
        }

    @staticmethod
    def optimize_nozzles(
        hhp: float,
        max_press: float,
        fr1: float,
        spp1: float,
        fr2: float,
        spp2: float,
        prev_tfa: float,
        mw_ppg: float,
        n_nozzles: int,
        model: str = "HP",
    ) -> dict:
        """Canonical bit-nozzle optimization (max-HHP or max-impact criterion).

        Single authoritative implementation. All bit pressure-drop / TFA
        values come from calc_bit_pressure_drop() and
        calc_tfa_from_pressure_drop() (ΔP = Q²·MW/(10858·TFA²)) so the
        optimizer can never disagree with the canonical bit hydraulics.

        Method (Bourgoyne et al., Applied Drilling Engineering):
        1. Parasitic-loss exponent n from a two-point pump test:
               n = log10(SPP₁/SPP₂) / log10(Q₁/Q₂)
        2. Optimum parasitic-loss split:
               max HHP:      ΔP_par = P_max / (n + 1)
               max impact:   ΔP_par = 2·P_max / (n + 2)
        3. Optimum flow Q_opt from the two-point friction law
           ΔP_par = a·Q^n, then required TFA from the canonical formula.

        When the two-point test is invalid (missing/zero readings, or a
        non-positive exponent) n = 1.0 is used as the documented fallback;
        the returned ``friction_exponent_source`` distinguishes that assumption
        from an exponent derived from the two-point test. Nozzle combination
        search is over standard 1/32-inch sizes.
        """
        import itertools

        nzl_sizes = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20,
                     22, 24, 26, 28, 30)

        def nozzle_area(size32: float) -> float:
            d = size32 / 32.0
            return math.pi * (d / 2) ** 2

        # Maximum pump-limited flow: HHP = Q·ΔP/1714  →  Q = HHP·1714/ΔP
        q_max = hhp * 1714.0 / max_press if max_press > 0 else 0.0

        # Parasitic-loss exponent from a two-point pump test.
        n = 1.0  # documented fallback
        friction_exponent_source = "assumed_fallback"
        if (fr2 > 0 and fr1 > 0 and spp1 > 0 and spp2 > 0
                and abs(fr1 - fr2) > 1e-9 and spp1 != spp2):
            try:
                cand = (math.log10(spp1 / spp2) / math.log10(fr1 / fr2))
                if cand > 0:
                    n = cand
                    friction_exponent_source = "two_point_pump_test"
            except (ValueError, ZeroDivisionError):
                n = 1.0

        if model == "HP":
            dpf_max = max_press / (n + 1.0) if n != -1.0 else 0.0
        else:
            dpf_max = 2.0 * max_press / (n + 2.0)

        # Parasitic friction at the pump-test point (SPP minus bit loss).
        dpf_1 = 0.0
        if prev_tfa > 0 and fr1 > 0 and spp1 > 0 and mw_ppg > 0:
            dpf_1 = spp1 - AdvancedHydraulicsEngine.calc_bit_pressure_drop(
                fr1, mw_ppg, prev_tfa)
        a = dpf_1 / (fr1 ** n) if fr1 > 0 else 0.0

        if a > 0 and n != 0:
            q_opt = (dpf_max / a) ** (1.0 / n)
        else:
            q_opt = q_max

        dp_bit = max_press - dpf_max
        if dp_bit > 0 and q_opt > 0 and mw_ppg > 0:
            opt_tfa = AdvancedHydraulicsEngine.calc_tfa_from_pressure_drop(
                q_opt, mw_ppg, dp_bit)
        else:
            opt_tfa = 0.0

        # Best real nozzle combination (1/32-in sizes).
        best_combo = None
        best_error = 1e9
        for combo in itertools.combinations_with_replacement(
                nzl_sizes, max(0, int(n_nozzles))):
            total_area = sum(nozzle_area(s) for s in combo)
            error = abs(opt_tfa - total_area)
            if error < best_error:
                best_error = error
                best_combo = combo

        return {
            "max_flow_rate_gpm": round(q_max, 1),
            "optimal_flow_rate_gpm": round(q_opt, 1),
            "optimal_tfa_in2": round(opt_tfa, 4),
            "friction_exponent": round(n, 4),
            "friction_exponent_source": friction_exponent_source,
            "selected_nozzles": list(best_combo) if best_combo else [],
            "actual_tfa_in2": round(
                sum(nozzle_area(s) for s in best_combo), 4) if best_combo else 0,
            "tfa_error": round(best_error, 4),
        }

    @staticmethod
    def calc_pump_output(liner_size_inch: float, stroke_length_inch: float,
                          efficiency: float = 0.95) -> float:
        """Triplex pump output (bbl/stroke).

        Canonical triplex formula (single source of truth for the UI):
            output = 0.000243 × liner² × stroke × efficiency
        (0.000243 = π/4 ÷ 231 in³/gal ÷ 42 gal/bbl × 12³ in³/ft³.)
        """
        if liner_size_inch <= 0 or stroke_length_inch <= 0:
            raise ValueError("Liner size and stroke length must be > 0")
        if not 0 < efficiency <= 1:
            raise ValueError("Pump efficiency must be in (0, 1]")
        return 0.000243 * liner_size_inch**2 * stroke_length_inch * efficiency

    @staticmethod
    def calc_pump_output_duplex(liner_size_inch: float, rod_size_inch: float,
                                stroke_length_inch: float,
                                efficiency: float = 0.95) -> float:
        """Duplex (double-acting) pump output (bbl/stroke).

        Canonical duplex formula (single source of truth for the UI):
            output = 0.000162 × stroke × (2 × liner² − rod²) × efficiency

        A duplex pump displaces on both strokes (hence ×2); the piston-rod
        diameter reduces displacement on one side (hence − rod²).
        0.000162 is the duplex geometry constant (bbl/stroke for inches).
        """
        if liner_size_inch <= 0 or stroke_length_inch <= 0:
            raise ValueError("Liner size and stroke length must be > 0")
        if rod_size_inch < 0 or rod_size_inch >= liner_size_inch:
            raise ValueError("Rod size must be ≥ 0 and smaller than liner size")
        if not 0 < efficiency <= 1:
            raise ValueError("Pump efficiency must be in (0, 1]")
        return 0.000162 * stroke_length_inch * (
            2.0 * liner_size_inch**2 - rod_size_inch**2
        ) * efficiency

    @staticmethod
    def calc_critical_flow_rate(mw_ppg: float, pv_cp: float, yp_lbf100ft2: float,
                                hole_size_in: float, pipe_od_in: float) -> dict:
        """Annular critical (laminar→turbulent) velocity and flow rate.

        Uses the SAME Bingham critical-velocity correlation as the engine's
        flow-regime classification (_determine_flow_regime, annular branch):

            Vc (ft/sec) = (1.08·PV + 1.08·√(PV² + 9.26·(Dh−Dp)²·YP·MW)) / (MW·(Dh−Dp))

        Qc (gpm) = Vc × A_annulus(ft²) × 60 × 7.4805.

        Below Qc the annulus is laminar (cuttings-bed risk); above Qc
        turbulent (better hole cleaning, higher ECD).
        """
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(
            mw_ppg=mw_ppg, pv_cp=pv_cp, yp_lbf100ft2=yp_lbf100ft2,
            hole_size_in=hole_size_in, pipe_od_in=pipe_od_in,
        )
        gap = hole_size_in - pipe_od_in
        if hole_size_in <= 0 or pipe_od_in <= 0:
            raise ValueError("Hole size and pipe OD must be > 0")
        if gap <= 0:
            raise ValueError("Hole size must be > pipe OD")
        if mw_ppg <= 0 or pv_cp <= 0:
            raise ValueError("MW and PV must be > 0")
        if yp_lbf100ft2 < 0:
            raise ValueError("Yield point cannot be negative")
        vc_fps = (1.08 * pv_cp + 1.08 * math.sqrt(
            pv_cp**2 + 9.26 * gap**2 * yp_lbf100ft2 * mw_ppg
        )) / (mw_ppg * gap)
        area_ft2 = math.pi / 4.0 * (
            (hole_size_in / 12.0) ** 2 - (pipe_od_in / 12.0) ** 2
        )
        qc_gpm = vc_fps * 60.0 * area_ft2 * 7.4805
        return {
            "critical_velocity_ft_min": round(vc_fps * 60.0, 1),
            "critical_flow_rate_gpm": round(qc_gpm, 1),
            "annular_gap_in": round(gap, 3),
        }

    @staticmethod
    def calc_annular_volume(hole_id: float, pipe_od: float, length_ft: float) -> float:
        """Annular volume (bbl), with positive dimensions and interval length."""
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(
            hole_id=hole_id, pipe_od=pipe_od, length_ft=length_ft
        )
        if hole_id <= pipe_od or pipe_od <= 0 or length_ft <= 0:
            raise ValueError("Annular volume requires hole ID > positive pipe OD and positive length")
        return (hole_id**2 - pipe_od**2) / 1029.4 * length_ft

    @staticmethod
    def calc_pipe_capacity_bbl(pipe_id: float, length_ft: float) -> float:
        """Pipe volume (bbl), with positive ID and interval length."""
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(pipe_id=pipe_id, length_ft=length_ft)
        if pipe_id <= 0 or length_ft <= 0:
            raise ValueError("Pipe capacity requires positive ID and length")
        return pipe_id**2 / 1029.4 * length_ft

    @staticmethod
    def calc_annular_capacity_bbl_ft(hole_id: float, pipe_od: float) -> float:
        """Annular capacity (bbl/ft) — canonical (Dh² − Dp²)/1029.4."""
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(hole_id=hole_id, pipe_od=pipe_od)
        if pipe_od <= 0 or hole_id <= pipe_od:
            raise ValueError("Annular capacity requires hole ID > positive pipe OD")
        return (hole_id**2 - pipe_od**2) / 1029.4

    @staticmethod
    def calc_pipe_capacity_bbl_ft(pipe_id: float) -> float:
        """Pipe capacity (bbl/ft) — canonical ID²/1029.4."""
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(pipe_id=pipe_id)
        if pipe_id <= 0:
            raise ValueError("Pipe ID must be positive")
        return pipe_id**2 / 1029.4

    @staticmethod
    def calc_pipe_displacement_bbl_ft(pipe_od: float, pipe_id: float) -> float:
        """Pipe metal displacement (bbl/ft) — canonical (OD² − ID²)/1029.4."""
        AdvancedHydraulicsEngine._require_finite_engineering_inputs(pipe_od=pipe_od, pipe_id=pipe_id)
        if pipe_id <= 0 or pipe_od <= pipe_id:
            raise ValueError("Pipe displacement requires OD > positive ID")
        return (pipe_od**2 - pipe_id**2) / 1029.4

    @staticmethod
    def calc_bottoms_up_strokes(annular_volume_bbl: float,
                                pump_output_bbl_stroke: float) -> float:
        """Strokes of pump output needed to pump the annulus around (stk)."""
        if pump_output_bbl_stroke <= 0:
            return 0.0
        return annular_volume_bbl / pump_output_bbl_stroke

    @staticmethod
    def calc_bottoms_up_time(annular_volume_bbl: float, pump_output_bbl_stroke: float,
                              spm: float) -> float:
        """زمان Bottoms Up (دقیقه)"""
        if pump_output_bbl_stroke <= 0 or spm <= 0:
            return 0.0
        flow_rate_bbl_min = pump_output_bbl_stroke * spm
        return annular_volume_bbl / flow_rate_bbl_min if flow_rate_bbl_min > 0 else 0

    @staticmethod
    def calc_lag_time(annular_volume_bbl: float, flow_rate_gpm: float) -> float:
        """محاسبه Lag Time (دقیقه)"""
        if flow_rate_gpm <= 0:
            return 0.0
        flow_rate_bbl_min = flow_rate_gpm / 42.0
        return annular_volume_bbl / flow_rate_bbl_min if flow_rate_bbl_min > 0 else 0