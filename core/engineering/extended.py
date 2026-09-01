"""Extended Drilling Engineering Calculations.

Formulas sourced from industry references and open-source drilling engineering repos:
- welleng (jonnymaserati): trajectory, anti-collision, error models
- drilling-engineer-toolkit (juangjuang74): well control, hydraulics, casing, pore pressure
- mud-engineer-pro (Himageo2006): mud weighting, rheology, solids, OWR
- dasvan/engineering-calculations: mud mixing, annular velocity, directional
- 3D-directional-drilling-engine (ejbo2001): vectorized MCM, inclination/azimuth from sensors
- DrillingEngineeringOperations (BillyFrcs): ECD, pressure loss, hoisting

Every calculation has:
- Published formula reference
- Required inputs with units
- Output with unit
- Assumptions and limitations
- Error conditions
"""

import math
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class ExtendedEngineeringError(Exception):
    pass


# ==================== Mud Engineering ====================

class MudEngineering:
    """Mud weighting, mixing, rheology, and solids calculations.
    
    References:
    - API RP 13B-1/13B-2 (Drilling Fluids Testing)
    - M-I SWACO Drilling Fluids Handbook
    - Baroid Drilling Fluids Manual
    """

    @staticmethod
    def mud_weighting(start_volume_m3: float, start_density_sg: float,
                      target_density_sg: float, weighting_density_sg: float) -> Dict:
        """Calculate amount of weighting material needed.
        
        Formula: W = V_start * (ρ_target - ρ_start) / (ρ_weight - ρ_target)
        
        Args:
            start_volume_m3: Initial mud volume (m³)
            start_density_sg: Initial mud density (SG)
            target_density_sg: Target mud density (SG)
            weighting_density_sg: Weighting material density (SG), e.g. barite = 4.2
        
        Returns:
            Dict with weight_kg, final_volume_m3
        """
        if weighting_density_sg <= target_density_sg:
            raise ExtendedEngineeringError("Weighting density must be > target density")
        if target_density_sg < start_density_sg:
            raise ExtendedEngineeringError("Target density must be >= start density")
        
        weight_kg = start_volume_m3 * 1000 * (target_density_sg - start_density_sg) / (weighting_density_sg - target_density_sg)
        final_volume = start_volume_m3 + weight_kg / (weighting_density_sg * 1000)
        
        return {
            "weight_kg": round(weight_kg, 1),
            "final_volume_m3": round(final_volume, 3),
            "start_volume_m3": start_volume_m3,
            "start_density_sg": start_density_sg,
            "target_density_sg": target_density_sg,
            "formula": "W = V × (ρ_target - ρ_start) / (ρ_weight - ρ_target)",
        }

    @staticmethod
    def mix_two_muds(volume1_m3: float, density1_sg: float,
                     volume2_m3: float, density2_sg: float) -> Dict:
        """Calculate resulting density when mixing two mud systems.
        
        Formula: ρ_mix = (V1×ρ1 + V2×ρ2) / (V1 + V2)
        """
        total_volume = volume1_m3 + volume2_m3
        if total_volume <= 0:
            raise ExtendedEngineeringError("Total volume must be > 0")
        
        mixed_density = (volume1_m3 * density1_sg + volume2_m3 * density2_sg) / total_volume
        
        return {
            "mixed_density_sg": round(mixed_density, 4),
            "total_volume_m3": round(total_volume, 3),
            "formula": "ρ_mix = (V1×ρ1 + V2×ρ2) / (V1 + V2)",
        }

    @staticmethod
    def oil_water_ratio(oil_ml: float, water_ml: float) -> Dict:
        """Calculate Oil-Water Ratio (OWR).
        
        Formula: OWR = Oil% : Water% where Oil% = oil/(oil+water)*100
        """
        total = oil_ml + water_ml
        if total <= 0:
            raise ExtendedEngineeringError("Total volume must be > 0")
        
        oil_pct = oil_ml / total * 100
        water_pct = water_ml / total * 100
        
        return {
            "oil_percent": round(oil_pct, 1),
            "water_percent": round(water_pct, 1),
            "owr": f"{oil_pct:.0f}:{water_pct:.0f}",
            "formula": "OWR = Oil% : Water%",
        }

    @staticmethod
    def solids_content(retort_oil_pct: float, retort_water_pct: float,
                       mud_weight_ppg: float) -> Dict:
        """Calculate solids content from retort analysis.
        
        Formula: Solids% = 100 - Oil% - Water%
        Low gravity solids = (12.5 × MW - 62.5 × Water% - 35.4 × Oil%) / (12.5 - 8.33 × SG_lgs)
        High gravity solids from volume balance
        """
        solids_pct = 100 - retort_oil_pct - retort_water_pct
        
        # Approximate low gravity solids (SG ≈ 2.6)
        lgs_denom = 12.5 - 8.33 * 2.6
        if abs(lgs_denom) > 0.01:
            lgs_pct = (12.5 * mud_weight_ppg - 62.5 * retort_water_pct - 35.4 * retort_oil_pct) / lgs_denom
        else:
            lgs_pct = 0
        
        hgs_pct = max(0, solids_pct - max(0, lgs_pct))
        
        return {
            "total_solids_pct": round(solids_pct, 1),
            "low_gravity_solids_pct": round(max(0, lgs_pct), 1),
            "high_gravity_solids_pct": round(hgs_pct, 1),
            "formula": "Solids% = 100 - Oil% - Water%",
        }

    @staticmethod
    def funnel_viscosity_to_pv_yp(funnel_sec: float, mud_weight_ppg: float) -> Dict:
        """Estimate PV and YP from Marsh Funnel viscosity.
        
        Approximate: PV ≈ (funnel - 15) × MW / 40
                     YP ≈ (funnel - PV) × 0.5
        Note: These are rough estimates. Use viscometer for accurate values.
        """
        pv_approx = max(0, (funnel_sec - 15) * mud_weight_ppg / 40)
        yp_approx = max(0, (funnel_sec - pv_approx) * 0.5)
        
        return {
            "estimated_pv_cp": round(pv_approx, 1),
            "estimated_yp_lbf100ft2": round(yp_approx, 1),
            "note": "Approximate only. Use viscometer for accurate PV/YP.",
        }


    @staticmethod
    def corrosion_rate(weight_loss_mg: float, area_in2: float,
                       hours: float, density_g_cm3: float = 7.86) -> Dict:
        """Uniform corrosion rate from a weight-loss coupon (API RP 13B-1).

        Formula: rate (mpy) = 534 × W / (A × T × D)

        W = coupon weight loss (mg), A = coupon area (in²),
        T = exposure time (hours), D = coupon density (g/cm³, steel ≈ 7.86).
        Also returns lb/ft²/yr (= mpy / 24.6) for mud-system comparisons.
        """
        if area_in2 <= 0:
            raise ExtendedEngineeringError("Coupon area must be > 0")
        if hours <= 0:
            raise ExtendedEngineeringError("Exposure time must be > 0")
        if density_g_cm3 <= 0:
            raise ExtendedEngineeringError("Coupon density must be > 0")
        if weight_loss_mg < 0:
            raise ExtendedEngineeringError("Weight loss cannot be negative")
        mpy = 534.0 * weight_loss_mg / (area_in2 * hours * density_g_cm3)
        return {
            "corrosion_rate_mpy": round(mpy, 3),
            "corrosion_rate_lb_ft2_yr": round(mpy / 24.6, 4),
            "severity": (
                "low (< 5 mpy)" if mpy < 5 else
                "moderate (5–10 mpy)" if mpy < 10 else
                "high (> 10 mpy)"
            ),
            "formula": "mpy = 534 × W(mg) / (A(in²) × T(hr) × D(g/cm³))",
        }

    @staticmethod
    def mbt_bentonite_equiv(ml_methylene_blue: float, sample_ml: float) -> Dict:
        """Bentonite-equivalent from methylene-blue titration (API RP 13B-1).

        Formula: lb/bbl bentonite equiv = 5 × V_MB / V_sample

        Each mL of 0.01 N methylene blue titrated per mL of mud sample
        corresponds to ≈ 5 lb/bbl of reactive (bentonite) clay.
        """
        if sample_ml <= 0:
            raise ExtendedEngineeringError("Sample volume must be > 0")
        if ml_methylene_blue < 0:
            raise ExtendedEngineeringError("MBT volume cannot be negative")
        mbt = 5.0 * ml_methylene_blue / sample_ml
        return {
            "mbt_lb_per_bbl": round(mbt, 1),
            "formula": "MBT = 5 × V_MB / V_sample (lb/bbl bentonite equiv)",
        }

    @staticmethod
    def lsryp(r3: float, r6: float) -> Dict:
        """Low-Shear-Rate Yield Point (LSRYP) from 3/6 rpm dial readings.

        Formula: LSRYP = 2 × θ3 − θ6  (lb/100 ft²)

        LSRYP measures hole-cleaning / barite-sag tendency: values below
        ~3 lb/100 ft² at low shear are a sag warning sign.
        """
        lsryp_val = 2.0 * r3 - r6
        return {
            "lsryp_lb_per_100ft2": round(lsryp_val, 2),
            "warning": (
                "Low LSRYP (< 3 lb/100ft²) — barite sag risk"
                if lsryp_val < 3.0 else None
            ),
            "formula": "LSRYP = 2 × θ3 − θ6",
        }

    @staticmethod
    def excess_lime_obm(pom_ml: float) -> Dict:
        """Excess lime in oil/synthetic muds from POM alkalinity.

        Formula: Excess lime (lb/bbl) = 1.295 × POM (mL)

        POM is the whole-mud phenolphthalein alkalinity (mL of 0.1 N
        H₂SO₄ per mL of mud to pH 8.3, API RP 13B-2); 1.295 converts the
        titration to lb/bbl Ca(OH)₂ equivalent.
        """
        if pom_ml < 0:
            raise ExtendedEngineeringError("POM cannot be negative")
        lime = 1.295 * pom_ml
        return {
            "excess_lime_lb_per_bbl": round(lime, 2),
            "formula": "Excess lime = 1.295 × POM (lb/bbl)",
        }

    @staticmethod
    def slug_dry_length(slug_vol_bbl: float, slug_mw_ppg: float,
                        mud_mw_ppg: float, pipe_cap_bbl_ft: float) -> Dict:
        """Dry pipe length from a weighted slug.

        Formula: L_dry = V_slug × (ρ_slug − ρ_mud) / (pipe_cap × ρ_mud)

        Returns the dry-pipe length in ft and the hydrostatic gain
        (psi) of the slug over the same length:
            ΔP = 0.052 × (ρ_slug − ρ_mud) × L_slug
        """
        if pipe_cap_bbl_ft <= 0:
            raise ExtendedEngineeringError("Pipe capacity must be > 0")
        if mud_mw_ppg <= 0:
            raise ExtendedEngineeringError("Mud weight must be > 0")
        if slug_mw_ppg <= mud_mw_ppg:
            raise ExtendedEngineeringError("Slug MW must be > mud MW")
        if slug_vol_bbl <= 0:
            raise ExtendedEngineeringError("Slug volume must be > 0")
        dry_len = slug_vol_bbl * (slug_mw_ppg - mud_mw_ppg) / (
            pipe_cap_bbl_ft * mud_mw_ppg
        )
        hydro_gain = 0.052 * (slug_mw_ppg - mud_mw_ppg) * dry_len
        return {
            "dry_pipe_length_ft": round(dry_len, 1),
            "hydrostatic_gain_psi": round(hydro_gain, 1),
            "formula": "L_dry = V_slug × (ρ_slug − ρ_mud) / (cap × ρ_mud)",
        }


# ==================== Hydraulics Extended ====================

class HydraulicsExtended:
    """Extended hydraulics calculations.
    
    References:
    - Bourgoyne et al., Applied Drilling Engineering
    - API RP 13D (Rheology and Hydraulics)
    """

    @staticmethod
    def pressure_loss_annular(mw_ppg: float, pv_cp: float, yp_lbf100ft2: float,
                               flow_rate_gpm: float, hole_id_in: float,
                               pipe_od_in: float, length_ft: float) -> Dict:
        """Calculate annular pressure loss using Bingham Plastic model.
        
        Formula: ΔP = (YP × L) / (225 × (Dh - Dp)) + (PV × L × V) / (1000 × (Dh - Dp)²)
        where V = 24.51 × Q / (Dh² - Dp²)
        
        Returns pressure loss in psi.
        """
        dh = hole_id_in
        dp = pipe_od_in
        gap = dh - dp
        
        if gap <= 0:
            raise ExtendedEngineeringError("Hole ID must be > Pipe OD")
        
        # Annular velocity ft/min
        v_annular = 24.51 * flow_rate_gpm / (dh**2 - dp**2)
        
        # Bingham Plastic annular pressure loss
        p_yield = (yp_lbf100ft2 * length_ft) / (225 * gap)
        p_viscous = (pv_cp * length_ft * v_annular) / (1000 * gap**2)
        total_psi = p_yield + p_viscous
        
        return {
            "pressure_loss_psi": round(total_psi, 1),
            "annular_velocity_ftmin": round(v_annular, 1),
            "p_yield_component_psi": round(p_yield, 1),
            "p_viscous_component_psi": round(p_viscous, 1),
            "formula": "ΔP = YP×L/(225×(Dh-Dp)) + PV×L×V/(1000×(Dh-Dp)²)",
        }

    @staticmethod
    def pressure_loss_pipe(mw_ppg: float, pv_cp: float, yp_lbf100ft2: float,
                            flow_rate_gpm: float, pipe_id_in: float,
                            length_ft: float) -> Dict:
        """Calculate pipe (inside drillstring) pressure loss.
        
        Formula: ΔP = (PV × L × V) / (18750 × D²) + (YP × L) / (225 × D)
        where V = 24.51 × Q / D²
        """
        d = pipe_id_in
        if d <= 0:
            raise ExtendedEngineeringError("Pipe ID must be > 0")
        
        v_pipe = 24.51 * flow_rate_gpm / d**2
        
        p_viscous = (pv_cp * length_ft * v_pipe) / (18750 * d**2)
        p_yield = (yp_lbf100ft2 * length_ft) / (225 * d)
        total_psi = p_viscous + p_yield
        
        return {
            "pressure_loss_psi": round(total_psi, 1),
            "pipe_velocity_ftmin": round(v_pipe, 1),
            "formula": "ΔP = PV×L×V/(18750×D²) + YP×L/(225×D)",
        }

    @staticmethod
    def bit_nozzle_pressure_drop(flow_rate_gpm: float, mw_ppg: float,
                                  tfa_in2: float) -> Dict:
        """Calculate pressure drop across bit nozzles.
        
        Formula: ΔP_bit = (MW × Q²) / (10858 × TFA²)
        """
        if tfa_in2 <= 0:
            raise ExtendedEngineeringError("TFA must be > 0")
        
        delta_p = (mw_ppg * flow_rate_gpm**2) / (10858 * tfa_in2**2)
        
        return {
            "nozzle_pressure_drop_psi": round(delta_p, 1),
            "formula": "ΔP_bit = MW × Q² / (10858 × TFA²)",
        }

    @staticmethod
    def jet_velocity(flow_rate_gpm: float, tfa_in2: float) -> Dict:
        """Calculate jet velocity at bit nozzles.
        
        Formula: V_jet = Q × 0.3208 / TFA (ft/s)
        """
        if tfa_in2 <= 0:
            raise ExtendedEngineeringError("TFA must be > 0")
        
        v_jet = flow_rate_gpm * 0.3208 / tfa_in2
        
        return {
            "jet_velocity_fps": round(v_jet, 1),
            "jet_velocity_ftmin": round(v_jet * 60, 1),
            "formula": "V_jet = Q × 0.3208 / TFA",
        }

    @staticmethod
    def impact_force(flow_rate_gpm: float, mw_ppg: float,
                     nozzle_pressure_drop_psi: float) -> Dict:
        """Calculate hydraulic impact force at bit.
        
        Formula: F = 0.000516 × MW × Q × V_jet (lbf)
        Or: F = Q × √(MW × ΔP / 10858) (simplified)
        """
        v_jet = flow_rate_gpm * math.sqrt(mw_ppg * nozzle_pressure_drop_psi / 10858)
        force = 0.000516 * mw_ppg * flow_rate_gpm * v_jet
        
        return {
            "impact_force_lbf": round(force, 1),
            "formula": "F = 0.000516 × MW × Q × V_jet",
        }


# ==================== Well Control Extended ====================

class WellControlExtended:
    """Extended well control calculations.
    
    References:
    - Well Control Manual (IWCF/IADC)
    - Applied Drilling Engineering (Bourgoyne)
    """

    @staticmethod
    def kick_tolerance(mw_ppg: float, tvd_ft: float, shoe_tvd_ft: float,
                       lot_pressure_psi: float, influx_gradient_ppg: float = 0.1) -> Dict:
        """Calculate kick tolerance.
        
        Formula: KT = (FPP - Current_P_bottom) / (0.052 × TVD)
        where FPP = LOT / (0.052 × Shoe_TVD) + MW
        """
        fpp_ppg = lot_pressure_psi / (0.052 * shoe_tvd_ft) + mw_ppg
        current_bottom_psi = 0.052 * mw_ppg * tvd_ft
        max_bottom_psi = 0.052 * fpp_ppg * shoe_tvd_ft
        
        # Kick tolerance in equivalent mud weight
        kt_ppg = fpp_ppg - mw_ppg
        
        # Maximum kick height
        max_kick_height_ft = kt_ppg * tvd_ft / (mw_ppg - influx_gradient_ppg) if (mw_ppg - influx_gradient_ppg) > 0 else 0
        
        return {
            "kick_tolerance_ppg": round(kt_ppg, 2),
            "fracture_pressure_ppg": round(fpp_ppg, 2),
            "max_kick_height_ft": round(max_kick_height_ft, 0),
            "formula": "KT = FPP - MW, FPP = LOT/(0.052×Shoe_TVD) + MW",
        }

    @staticmethod
    def wait_weight_method(original_mw_ppg: float, sidpp_psi: float,
                           tvd_ft: float, circ_pressure_psi: float) -> Dict:
        """Wait & Weight method calculations.
        
        Returns: Kill MW, ICP (Initial Circulating Pressure), FCP (Final Circulating Pressure)
        
        Kill MW = Original MW + SIDPP / (0.052 × TVD)
        ICP = SIDPP + Circ Pressure (slow pump rate)
        FCP = Circ Pressure × (Kill MW / Original MW)
        """
        kill_mw = original_mw_ppg + sidpp_psi / (0.052 * tvd_ft)
        icp = sidpp_psi + circ_pressure_psi
        fcp = circ_pressure_psi * (kill_mw / original_mw_ppg)
        
        return {
            "kill_mud_weight_ppg": round(kill_mw, 2),
            "initial_circulating_pressure_psi": round(icp, 1),
            "final_circulating_pressure_psi": round(fcp, 1),
            "formula": "Kill MW = MW + SIDPP/(0.052×TVD), ICP = SIDPP + SPR, FCP = SPR × KillMW/MW",
        }

    @staticmethod
    def formation_pressure(mw_ppg: float, sidpp_psi: float, tvd_ft: float) -> Dict:
        """Calculate formation pressure from shut-in data.
        
        Formula: P_formation = SIDPP + 0.052 × MW × TVD
        """
        p_form = sidpp_psi + 0.052 * mw_ppg * tvd_ft
        
        return {
            "formation_pressure_psi": round(p_form, 1),
            "formation_pressure_ppg_equivalent": round(p_form / (0.052 * tvd_ft), 2) if tvd_ft > 0 else 0,
            "formula": "P_form = SIDPP + 0.052 × MW × TVD",
        }


# ==================== Casing Design ====================

class CasingDesign:
    """Basic casing design calculations.
    
    References:
    - API TR 5C3 (Casing, Tubing, and Drill Pipe)
    - Bourgoyne et al.
    """

    @staticmethod
    def burst_pressure(internal_pressure_psi: float, safety_factor: float = 1.1) -> Dict:
        """Required burst pressure rating.
        
        Formula: Burst_rating ≥ P_internal × SF
        """
        required = internal_pressure_psi * safety_factor
        
        return {
            "required_burst_rating_psi": round(required, 0),
            "internal_pressure_psi": internal_pressure_psi,
            "safety_factor": safety_factor,
            "formula": "Burst_rating ≥ P_internal × SF",
        }

    @staticmethod
    def collapse_pressure(external_pressure_psi: float, safety_factor: float = 1.125) -> Dict:
        """Required collapse pressure rating.
        
        Formula: Collapse_rating ≥ P_external × SF
        """
        required = external_pressure_psi * safety_factor
        
        return {
            "required_collapse_rating_psi": round(required, 0),
            "external_pressure_psi": external_pressure_psi,
            "safety_factor": safety_factor,
            "formula": "Collapse_rating ≥ P_external × SF",
        }

    @staticmethod
    def hydrostatic_pressure(mw_ppg: float, tvd_ft: float) -> Dict:
        """Calculate hydrostatic pressure.
        
        Formula: P_hydro = 0.052 × MW × TVD
        """
        p_hydro = 0.052 * mw_ppg * tvd_ft
        
        return {
            "hydrostatic_pressure_psi": round(p_hydro, 1),
            "formula": "P_hydro = 0.052 × MW × TVD",
        }


# ==================== Directional Drilling Extended ====================

class DirectionalExtended:
    """Extended directional drilling calculations.
    
    References:
    - welleng (jonnymaserati)
    - 3D-directional-drilling-engine (ejbo2001)
    - dasvan/engineering-calculations
    """

    @staticmethod
    def deviation_from_vertical(north_m: float, east_m: float) -> Dict:
        """Calculate total deviation from vertical.
        
        Formula: Deviation = √(North² + East²)
        """
        dev = math.sqrt(north_m**2 + east_m**2)
        
        return {
            "deviation_m": round(dev, 2),
            "north_m": north_m,
            "east_m": east_m,
            "formula": "Deviation = √(N² + E²)",
        }

    @staticmethod
    def slide_rotor_ratio(meters_slide: float, meters_rotor: float) -> Dict:
        """Calculate slide/rotor ratio for directional drilling.
        
        Formula: Ratio = Slide / (Slide + Rotor) × 100
        """
        total = meters_slide + meters_rotor
        if total <= 0:
            raise ExtendedEngineeringError("Total meters must be > 0")
        
        ratio = meters_slide / total * 100
        
        return {
            "slide_percent": round(ratio, 1),
            "rotor_percent": round(100 - ratio, 1),
            "total_m": round(total, 1),
            "formula": "Slide% = Slide/(Slide+Rotor) × 100",
        }

    @staticmethod
    def tool_face_offset(motor_mark_mm: float, toolface_mark_mm: float,
                         motor_circumference_mm: float) -> Dict:
        """Calculate tool face offset angle.
        
        Formula: Offset = (T/S_mark - Motor_mark) / Circumference × 360
        """
        if motor_circumference_mm <= 0:
            raise ExtendedEngineeringError("Motor circumference must be > 0")
        
        offset_deg = (toolface_mark_mm - motor_mark_mm) / motor_circumference_mm * 360
        
        # Normalize to 0-360
        offset_deg = offset_deg % 360
        
        return {
            "offset_degrees": round(offset_deg, 1),
            "formula": "Offset = (T/S_mark - Motor_mark) / Circumference × 360",
        }

    @staticmethod
    def inclination_from_accelerometers(gx: float, gy: float, gz: float) -> Dict:
        """Calculate inclination from accelerometer readings.
        
        Formula: Inc = atan2(√(Gx² + Gy²), Gz) × 180/π
        """
        inc_rad = math.atan2(math.sqrt(gx**2 + gy**2), gz)
        inc_deg = math.degrees(inc_rad)
        
        return {
            "inclination_deg": round(inc_deg, 2),
            "formula": "Inc = atan2(√(Gx² + Gy²), Gz)",
        }

    @staticmethod
    def azimuth_from_magnetometers(gx: float, gy: float, gz: float,
                                    bx: float, by: float, bz: float) -> Dict:
        """Calculate magnetic azimuth from accelerometer and magnetometer readings.
        
        Formula:
        Hx = Bx×Gz - Bz×Gx
        Hy = By×Gz - Bz×Gy (corrected for dip)
        Azimuth = atan2(-Hy, Hx) × 180/π
        """
        hx = bx * gz - bz * gx
        hy = by * gz - bz * gy
        
        azi_rad = math.atan2(-hy, hx)
        azi_deg = math.degrees(azi_rad) % 360
        
        return {
            "azimuth_deg": round(azi_deg, 2),
            "formula": "Azi = atan2(-(By×Gz-Bz×Gy), Bx×Gz-Bz×Gx)",
        }


# ==================== Cementing ====================

class CementingEngine:
    """Basic cementing calculations.
    
    References:
    - API RP 10B-2 (Testing Well Cements)
    - Halliburton Cementing Tables
    """

    @staticmethod
    def cement_volume_annular(outer_diameter_in: float, inner_diameter_in: float,
                               length_ft: float) -> Dict:
        """Calculate cement volume needed for annular space.
        
        Formula: V = (OD² - ID²) / 1029.4 × Length (bbl/ft)
        """
        if outer_diameter_in <= inner_diameter_in:
            raise ExtendedEngineeringError("OD must be > ID")
        
        volume_bbl = (outer_diameter_in**2 - inner_diameter_in**2) / 1029.4 * length_ft
        volume_m3 = volume_bbl * 0.159
        
        return {
            "volume_bbl": round(volume_bbl, 2),
            "volume_m3": round(volume_m3, 3),
            "formula": "V = (OD² - ID²) / 1029.4 × L",
        }

    @staticmethod
    def cement_volume_pipe(inner_diameter_in: float, length_ft: float) -> Dict:
        """Calculate cement volume inside pipe.
        
        Formula: V = ID² / 1029.4 × Length (bbl)
        """
        volume_bbl = inner_diameter_in**2 / 1029.4 * length_ft
        
        return {
            "volume_bbl": round(volume_bbl, 2),
            "formula": "V = ID² / 1029.4 × L",
        }

    @staticmethod
    def displacement_volume(pipe_id_in: float, length_ft: float) -> Dict:
        """Calculate displacement volume to bump plug.
        
        Formula: V_disp = ID² / 1029.4 × Length (bbl)
        """
        volume_bbl = pipe_id_in**2 / 1029.4 * length_ft
        
        return {
            "displacement_bbl": round(volume_bbl, 2),
            "formula": "V_disp = ID² / 1029.4 × L",
        }

    @staticmethod
    def slurry_density(cement_weight_kg: float, water_volume_l: float,
                       cement_sg: float = 3.15) -> Dict:
        """Calculate slurry density from cement and water.
        
        Formula: ρ_slurry = (Cement_weight + Water_weight) / (Cement_vol + Water_vol)
        """
        cement_vol_m3 = cement_weight_kg / (cement_sg * 1000)
        water_vol_m3 = water_volume_l / 1000
        total_weight = cement_weight_kg + water_volume_l  # water density ≈ 1 kg/L
        total_vol = cement_vol_m3 + water_vol_m3
        
        if total_vol <= 0:
            raise ExtendedEngineeringError("Total volume must be > 0")
        
        density_sg = total_weight / (total_vol * 1000)
        density_ppg = density_sg * 8.345
        
        return {
            "slurry_density_sg": round(density_sg, 3),
            "slurry_density_ppg": round(density_ppg, 2),
            "slurry_volume_m3": round(total_vol, 3),
            "yield_m3_per_ton": round(total_vol / (cement_weight_kg / 1000), 3) if cement_weight_kg > 0 else 0,
            "formula": "ρ = (W_cement + W_water) / (V_cement + V_water)",
        }


# ==================== ROP Models ====================

class ROPModels:
    """Rate of Penetration prediction models.
    
    References:
    - Bourgoyne & Young (1974)
    - Tanaka (1968)
    - Warren (1987)
    """

    @staticmethod
    def bourgoyne_young_rop(depth_ft: float, wob_klbf: float, rpm: float,
                            mw_ppg: float, porosity_pct: float = 20,
                            strength_factor: float = 1.0) -> Dict:
        """Simplified Bourgoyne & Young ROP model.
        
        ROP = K × (WOB/D)^a × RPM^b × e^(-c×D)
        where K = formation drillability, a,b,c = exponents
        
        NOTE: This is a simplified model for relative comparison.
        Actual ROP prediction requires calibrated constants from offset wells.
        K is calibrated here to produce realistic field-order results
        (typically 5-50 m/hr for conventional drilling).
        """
        if depth_ft <= 0 or wob_klbf <= 0 or rpm <= 0:
            raise ExtendedEngineeringError("Depth, WOB, and RPM must be > 0")
        
        # Typical exponents from Bourgoyne & Young (1974)
        a = 1.0  # WOB exponent
        b = 0.6  # RPM exponent
        c = 0.00005  # depth exponent (calibrated for realistic output)
        
        # Formation drillability (calibrated for realistic output)
        # K ≈ 0.5-2.0 for soft-moderate formations
        k = 0.5 * strength_factor * (1 + porosity_pct / 100)
        
        rop = k * (wob_klbf) ** a * rpm ** b * math.exp(-c * depth_ft)
        
        return {
            "predicted_rop_ft_hr": round(rop, 1),
            "predicted_rop_m_hr": round(rop * 0.3048, 1),
            "parameters": {"K": k, "a": a, "b": b, "c": c},
            "formula": "ROP = K × WOB^a × RPM^b × e^(-c×D)",
            "note": "Simplified model. Calibrate K, a, b, c with offset well data.",
        }
