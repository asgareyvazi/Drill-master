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
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ==================== Data Classes ====================

@dataclass
class PipeSegment:
    """یک بخش از رشته حفاری"""
    name: str = ""           # e.g., "5\" DP", "6.5\" DC", "MWD"
    pipe_type: str = "DP"    # DP, HWDP, DC, MWD, Motor, Stabilizer, Sub
    od: float = 5.0          # inch
    id: float = 4.276        # inch
    length: float = 0.0      # meters
    weight_ppf: float = 19.5 # lb/ft
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
    od: float = 9.625        # inch (OD of casing / hole size)
    id: float = 8.835        # inch (ID of casing / hole size for OH)
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
    size_32nds: int = 16     # اندازه به 1/32 اینچ
    quantity: int = 1
    
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
    mw_pcf: float = 75.0     # وزن گل (pcf)
    pv: float = 15.0         # ویسکوزیته پلاستیک (cp)
    yp: float = 11.0         # نقطه تسلیم (lb/100ft²)
    theta600: float = 45.0   # قرائت 600
    theta300: float = 25.0   # قرائت 300
    theta200: float = 18.0   # قرائت 200
    theta100: float = 12.0   # قرائت 100
    theta6: float = 4.0      # قرائت 6
    theta3: float = 3.0      # قرائت 3
    gel_10s: float = 5.0     # ژل 10 ثانیه
    gel_10m: float = 12.0    # ژل 10 دقیقه
    
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
        """consistency index - Power Law"""
        n = self.n_power_law
        if n <= 0:
            return 1.0
        return 511 * self.theta300 / (511 ** n)
    
    @property
    def tau_y_hb(self) -> float:
        """Yield stress for Herschel-Bulkley (approximate)"""
        return max(0, 2 * self.theta3 - self.theta6)


@dataclass
class SurfaceEquipment:
    """تجهیزات سطحی"""
    standpipe_length_m: float = 50.0
    standpipe_id_inch: float = 3.5
    hose_length_m: float = 30.0
    hose_id_inch: float = 4.0
    swivel_id_inch: float = 2.5
    kelly_length_m: float = 12.0
    kelly_id_inch: float = 3.0
    
    # یا استفاده از ثابت API
    use_api_constant: bool = False
    api_surface_loss_constant: float = 0.0  # E factor


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
    build_rate: float = 2.0      # °/30m
    
    # Survey points for complex wells: [(md, inc, azi), ...]
    survey_points: list = field(default_factory=list)
    
    def get_tvd_at_md(self, md: float) -> float:
        """محاسبه TVD در یک عمق MD مشخص"""
        if self.well_type == "vertical":
            return md
        
        if self.survey_points:
            return self._interpolate_tvd(md)
        
        # محاسبه ساده بر اساس KOP
        if md <= self.kop_md:
            return md  # بخش عمودی
        
        if self.eob_md > 0 and md <= self.eob_md:
            # بخش build
            arc_length = md - self.kop_md
            radius = 30 / math.radians(self.build_rate) if self.build_rate > 0 else 10000
            inc_rad = arc_length / radius
            tvd = self.kop_tvd + radius * math.sin(inc_rad)
            return tvd
        
        # بخش tangent
        if self.eob_md > 0:
            remaining = md - self.eob_md
            tvd = self.eob_tvd + remaining * math.cos(math.radians(self.eob_inc))
            return tvd
        
        return md
    
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
        """درون‌یابی TVD از survey points"""
        if not self.survey_points:
            return md
        
        # پیدا کردن دو نقطه نزدیک
        for i in range(len(self.survey_points) - 1):
            md1 = self.survey_points[i][0]
            md2 = self.survey_points[i + 1][0]
            
            if md1 <= md <= md2:
                # درون‌یابی خطی ساده
                fraction = (md - md1) / (md2 - md1) if md2 != md1 else 0
                tvd1 = self.survey_points[i][3] if len(self.survey_points[i]) > 3 else md1
                tvd2 = self.survey_points[i+1][3] if len(self.survey_points[i+1]) > 3 else md2
                return tvd1 + fraction * (tvd2 - tvd1)
        
        return md


@dataclass
class HydraulicsResult:
    """نتایج محاسبات هیدرولیک"""
    # فشارها
    surface_loss_psi: float = 0.0
    pipe_losses: list = field(default_factory=list)   # [(segment_name, loss_psi), ...]
    annulus_losses: list = field(default_factory=list) # [(segment_name, loss_psi), ...]
    bit_loss_psi: float = 0.0
    total_loss_psi: float = 0.0
    
    # ECD
    ecd_at_bit_ppg: float = 0.0
    ecd_at_shoe_ppg: float = 0.0
    ecd_profile: list = field(default_factory=list)  # [(depth_m, ecd_ppg), ...]
    
    # Bit hydraulics
    tfa_in2: float = 0.0
    bit_hhp: float = 0.0
    hsi: float = 0.0
    jet_velocity_fps: float = 0.0
    impact_force_lbs: float = 0.0
    percent_bit_hp: float = 0.0
    
    # Flow regime
    flow_regimes_pipe: list = field(default_factory=list)    # [(segment, "Laminar"/"Turbulent"), ...]
    flow_regimes_annulus: list = field(default_factory=list)
    
    # Velocities
    annular_velocities: list = field(default_factory=list)  # [(segment, av_fpm), ...]
    pipe_velocities: list = field(default_factory=list)
    
    # Critical flow rate (annular, deepest section)
    critical_flow_rate_gpm: float = 0.0
    critical_velocity_ft_min: float = 0.0
    critical_section: str = ""

    # سایر
    pump_output_bbl_stroke: float = 0.0
    flow_rate_gpm: float = 0.0
    
    # خطاها
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# ==================== Main Engine ====================

class AdvancedHydraulicsEngine:
    """
    موتور محاسبات هیدرولیک پیشرفته
    مرجع: Applied Drilling Engineering (Bourgoyne et al.)
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
        self.flow_rate_gpm: float = 250.0
        self.bit_depth_m: float = 3000.0
        self.model: str = "bingham"  # bingham, power_law, herschel_bulkley
    
    def calculate(self) -> HydraulicsResult:
        """محاسبه کامل هیدرولیک"""
        result = HydraulicsResult()
        result.flow_rate_gpm = self.flow_rate_gpm
        
        try:
            # 1. Surface losses
            result.surface_loss_psi = self._calc_surface_losses()
            
            # 2. Build drill string depth map
            segments_with_depth = self._build_depth_map()
            
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
                bit_od = (max(seg.od for seg in self.pipe_segments)
                          if self.pipe_segments else 8.5)
                bh = self.calc_bit_hydraulics(
                    self.flow_rate_gpm, self.mud.mw_ppg, tfa, bit_od
                )
                result.bit_loss_psi = bh["bit_pressure_drop_psi"]
                result.bit_hhp = bh["bit_hhp"]
                result.hsi = bh["hsi"]
                result.jet_velocity_fps = bh["jet_velocity_fps"]
                result.impact_force_lbs = bh["impact_force_lbs"]
            
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
            
        except Exception as e:
            logger.error(f"Hydraulics calculation error: {e}")
            result.errors.append(str(e))
        
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
        
        # Swivel
        if se.swivel_id_inch > 0:
            total += self._calc_pipe_pressure_loss(
                se.swivel_id_inch, 5.0, self.flow_rate_gpm  # ~5 ft effective
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
    
    def _bingham_pipe_loss(self, v: float, d: float, L: float, 
                            mw: float, pv: float, yp: float) -> float:
        """Bingham Plastic Model - Pipe"""
        if d <= 0 or mw <= 0:
            return 0.0
        
        # Critical velocity
        vc = (1.08 * pv + 1.08 * math.sqrt(pv**2 + 12.34 * d**2 * yp * mw)) / (mw * d)
        
        if v >= vc:
            # Turbulent
            return mw**0.75 * v**1.75 * pv**0.25 * L / (1800 * d**1.25)
        else:
            # Laminar
            return (pv * v * L) / (1000 * d**2) + (yp * L) / (225 * d)
    
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
            # Turbulent (API RP 13D)
            return 3.6033e-4 * mw**0.8 * v**1.8 * pv**0.2 * L / (d**1.2)
        else:
            # Laminar
            gamma = (96.0 * v / d) * (3.0 * n + 1.0) / (4.0 * n)
            return (gamma ** n) * (k * L / (300.0 * d))
    
    def _hb_pipe_loss(self, v: float, d: float, L: float, mw: float) -> float:
        """Herschel-Bulkley Model - Pipe (approximate)"""
        n = self.mud.n_power_law
        k = self.mud.k_power_law
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
        """Bingham Model - Annulus"""
        if gap <= 0 or mw <= 0:
            return 0.0
        
        vc_a = (1.08 * pv + 1.08 * math.sqrt(pv**2 + 9.26 * gap**2 * yp * mw)) / (mw * gap)
        
        if v >= vc_a:
            return mw**0.75 * v**1.75 * pv**0.25 * L / (1396 * gap**1.25)
        else:
            return (pv * v * L) / (1000 * gap**2) + (yp * L) / (200 * gap)
    
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
    
    def _calc_velocity(self, gpm: float, id_inch: float) -> float:
        """سرعت سیال (ft/s)"""
        if id_inch <= 0:
            return 0.0
        return gpm / (2.448 * id_inch**2)
    
    def _calc_annular_velocity(self, gpm: float, hole_id: float, pipe_od: float) -> float:
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
            
            # اگر بخشی خارج از همه کیسینگ‌ها هست (open hole)
            covered_ft = sum(ov[1] for ov in overlaps)
            remaining = (seg_bot - seg_top) - covered_ft
            
            if remaining > 1:
                # ساخت open hole section مجازی
                oh = CasingSection(
                    name="Open Hole",
                    section_type="open_hole",
                    id=max(s.od for s in self.pipe_segments) + 2.0 if self.pipe_segments else 8.5,
                    od=0,
                    top_md=0,
                    bottom_md=self.bit_depth_m,
                )
                # استفاده از hole size واقعی اگه موجوده
                for csg in self.casing_sections:
                    if csg.section_type == "open_hole":
                        oh = csg
                        break
                
                overlaps.append((oh, remaining))
            
            segments_info.append({
                'segment': seg,
                'top_ft': seg_top,
                'bot_ft': seg_bot,
                'overlaps': overlaps,
            })
            
            current_depth_ft = seg_bot
        
        return segments_info

    # ==================== ECD Profile ====================
    
    def _calc_ecd_profile(self, result: HydraulicsResult) -> list:
        """محاسبه ECD vs Depth"""
        profile = []
        bit_depth_m = self.bit_depth_m
        
        if bit_depth_m <= 0:
            return profile
        
        # Total annular pressure loss
        total_ann_loss = sum(loss for _, loss in result.annulus_losses)
        
        # Calculate ECD at intervals
        intervals = 20
        step = bit_depth_m / intervals
        
        cumulative_ann_loss = 0.0
        
        for i in range(intervals + 1):
            depth_m = i * step
            tvd_m = self.well_profile.get_tvd_at_md(depth_m)
            tvd_ft = tvd_m * 3.28084
            
            if tvd_ft <= 0:
                profile.append((round(depth_m, 1), self.mud.mw_ppg))
                continue
            
            # Proportional annular loss
            fraction = depth_m / bit_depth_m if bit_depth_m > 0 else 0
            ann_loss_at_depth = total_ann_loss * fraction
            
            # ECD = MW + APL / (0.052 × TVD)
            ecd = self.mud.mw_ppg + ann_loss_at_depth / (0.052 * tvd_ft)
            
            profile.append((round(depth_m, 1), round(ecd, 3)))
        
        return profile

    # ==================== Surge/Swab ====================
    
    def calc_surge_swab(self, trip_speed_fpm: float = 90, 
                         operation: str = "POOH",
                         pipe_open: bool = True) -> Dict:
        """
        محاسبه Surge/Swab پیشرفته
        - برای هر ترکیب لوله
        - با توجه به well profile
        """
        bit_depth_ft = self.bit_depth_m * 3.28084
        mw = self.mud.mw_ppg
        n = self.mud.n_bingham
        k = self.mud.k_bingham
        
        total_pressure = 0.0
        segment_results = []
        
        for seg in self.pipe_segments:
            seg_len_ft = seg.length_ft
            
            # Find the hole/casing ID this segment is in
            hole_id = 8.5  # default
            for csg in self.casing_sections:
                csg_top_ft = csg.top_md * 3.28084
                csg_bot_ft = csg.bottom_md * 3.28084
                if csg_top_ft <= bit_depth_ft - seg_len_ft <= csg_bot_ft:
                    hole_id = csg.id
                    break
            
            hs = hole_id
            od = seg.od
            id_ = seg.id
            
            if hs <= od:
                continue
            
            # Clinging constant
            if pipe_open:
                K_c = 0.45 + (od**2 - id_**2) / (hs**2 - od**2 + id_**2)
            else:
                K_c = 0.45 + od**2 / (hs**2 - od**2)
            
            v_pipe = K_c * trip_speed_fpm / 60  # ft/s
            v_max = 1.5 * v_pipe
            
            # Pressure loss
            gap = hs - od
            if gap <= 0:
                continue
            
            gamma = (2.4 * v_max / gap) * ((2 * n + 1) / (3 * n))
            
            if gamma > 0 and n > 0:
                P_seg = (gamma ** n) * (k * seg_len_ft / (300 * gap))
            else:
                P_seg = 0
            
            total_pressure += P_seg
            segment_results.append({
                "segment": seg.name,
                "pressure_psi": round(P_seg, 2),
                "velocity_fps": round(v_max, 2),
            })
        
        # TVD at bit
        tvd_ft = self.well_profile.get_tvd_at_md(self.bit_depth_m) * 3.28084
        
        if operation == "RIH":
            equiv_mw = mw + total_pressure / (0.052 * tvd_ft) if tvd_ft > 0 else mw
            label = "Surge"
        else:
            equiv_mw = mw - total_pressure / (0.052 * tvd_ft) if tvd_ft > 0 else mw
            label = "Swab"
        
        return {
            "type": label,
            "total_pressure_psi": round(total_pressure, 1),
            "equiv_mw_ppg": round(equiv_mw, 3),
            "equiv_mw_pcf": round(equiv_mw * 7.48, 2),
            "segments": segment_results,
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
    def calc_bit_pressure_drop(gpm: float, mw_ppg: float, tfa_in2: float) -> float:
        """Bit nozzle pressure drop (psi).

            ΔP = Q² × MW / (10858 × TFA²)      (Q in gpm, MW in ppg, TFA in in²)
        """
        if tfa_in2 <= 0:
            raise ValueError("TFA must be > 0")
        return gpm**2 * mw_ppg / (10858.0 * tfa_in2**2)

    @staticmethod
    def calc_tfa_from_pressure_drop(gpm: float, mw_ppg: float,
                                    delta_p_psi: float) -> float:
        """Required TFA (in²) to achieve a target bit pressure drop.

            TFA = √(Q² × MW / (10858 × ΔP))
        """
        if delta_p_psi <= 0:
            raise ValueError("delta_p_psi must be > 0")
        return math.sqrt(gpm**2 * mw_ppg / (10858.0 * delta_p_psi))

    @staticmethod
    def calc_bit_hhp(gpm: float, pressure_drop_psi: float) -> float:
        """Bit hydraulic horsepower.

            HHP = Q × ΔP / 1714
        """
        return gpm * pressure_drop_psi / 1714.0

    @staticmethod
    def calc_hsi(bit_hhp: float, bit_od_in: float) -> float:
        """Hydraulic horsepower per square inch of bit area."""
        area = math.pi / 4.0 * bit_od_in**2
        return bit_hhp / area if area > 0 else 0.0

    @staticmethod
    def calc_jet_velocity(gpm: float, tfa_in2: float) -> float:
        """Nozzle jet velocity (ft/s)."""
        if tfa_in2 <= 0:
            raise ValueError("TFA must be > 0")
        return gpm / (3.117 * tfa_in2)

    @staticmethod
    def calc_impact_force(mw_ppg: float, gpm: float,
                          jet_velocity_fps: float) -> float:
        """Hydraulic impact force (lbf).

            F = MW × Q × v / 1930
        """
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
        non-positive exponent) n = 1.0 is used as the documented fallback.
        Nozzle combination search is over standard 1/32-inch sizes.
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
        if (fr2 > 0 and fr1 > 0 and spp1 > 0 and spp2 > 0
                and abs(fr1 - fr2) > 1e-9 and spp1 != spp2):
            try:
                cand = (math.log10(spp1 / spp2) / math.log10(fr1 / fr2))
                if cand > 0:
                    n = cand
            except (ValueError, ZeroDivisionError):
                n = 1.0

        if model == "HP":
            dpf_max = max_press / (n + 1.0) if n != -1.0 else 0.0
        else:
            dpf_max = 2.0 * max_press / (n + 2.0)

        # Parasitic friction at the pump-test point (SPP minus bit loss).
        dpf_1 = 0.0
        if prev_tfa > 0:
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
        gap = hole_size_in - pipe_od_in
        if gap <= 0:
            raise ValueError("Hole size must be > pipe OD")
        if mw_ppg <= 0 or pv_cp <= 0:
            raise ValueError("MW and PV must be > 0")
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
        """حجم آنولوس (bbl)"""
        return (hole_id**2 - pipe_od**2) / 1029.4 * length_ft

    @staticmethod
    def calc_pipe_capacity_bbl(pipe_id: float, length_ft: float) -> float:
        """ظرفیت لوله (bbl)"""
        return pipe_id**2 / 1029.4 * length_ft

    @staticmethod
    def calc_annular_capacity_bbl_ft(hole_id: float, pipe_od: float) -> float:
        """Annular capacity (bbl/ft) — canonical (Dh² − Dp²)/1029.4."""
        return (hole_id**2 - pipe_od**2) / 1029.4

    @staticmethod
    def calc_pipe_capacity_bbl_ft(pipe_id: float) -> float:
        """Pipe capacity (bbl/ft) — canonical ID²/1029.4."""
        return pipe_id**2 / 1029.4

    @staticmethod
    def calc_pipe_displacement_bbl_ft(pipe_od: float, pipe_id: float) -> float:
        """Pipe metal displacement (bbl/ft) — canonical (OD² − ID²)/1029.4."""
        return (pipe_od**2 - pipe_id**2) / 1029.4

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