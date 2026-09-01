"""Single canonical field registry shared by import, units, review, AI and DB.

This is the ONE canonical schema of the application:

* Every import path (ExcelIntelligence, profile engine, smart template,
  universal import, AI mapper) resolves fields through this registry.
* Field metadata (quantity, unit, criticality, engineering bounds, aliases)
  lives here — never duplicated in UI or import code.
* No company-specific parsing branches: company behaviour belongs in
  templates/company mapping, not in this registry.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, FrozenSet


@dataclass(frozen=True)
class FieldSpec:
    path: str
    quantity: str = "text"          # text, date, time, code, integer, number,
                                    # length, density, pressure, force, rpm,
                                    # torque, rate, flow_rate, volume,
                                    # viscosity, temperature, angle, dls, area,
                                    # stress, currency
    unit: str = ""
    critical: bool = False
    aliases: Tuple[str, ...] = ()
    min_val: Optional[float] = None
    max_val: Optional[float] = None

    def __post_init__(self) -> None:
        # Default engineering bounds per quantity when not given explicitly.
        if self.min_val is None and self.max_val is None:
            bounds = _DEFAULT_BOUNDS.get(self.quantity)
            if bounds:
                object.__setattr__(self, "min_val", bounds[0])
                object.__setattr__(self, "max_val", bounds[1])


# Default engineering bounds per quantity type (min, max).
_DEFAULT_BOUNDS: Dict[str, Tuple[Optional[float], Optional[float]]] = {
    "length": (0.0, None),
    "density": (0.0, 25.0),
    "pressure": (0.0, 20000.0),
    "force": (0.0, 500.0),
    "rpm": (0.0, 500.0),
    "torque": (0.0, 500.0),
    "rate": (0.0, None),
    "flow_rate": (0.0, None),
    "volume": (0.0, None),
    "viscosity": (0.0, None),
    "temperature": (-50.0, 500.0),
    "angle": (0.0, 360.0),
    "dls": (0.0, None),
    "area": (0.0, None),
    "stress": (0.0, None),
    "currency": (0.0, None),
}


def _F(path, quantity="text", unit="", critical=False, aliases=(), bounds=None):
    """Compact FieldSpec constructor."""
    min_val = max_val = None
    if bounds:
        min_val, max_val = bounds
    return FieldSpec(path, quantity, unit, critical, tuple(aliases), min_val, max_val)


FIELD_SPECS: Dict[str, FieldSpec] = {
    spec.path: spec for spec in [
        # ---------------- Well Info ----------------
        _F("well_info.name", "text", "", True, ["well name", "well", "well number", "well id", "well designation", "well_name"]),
        _F("well_info.field_name", "text", "", False, ["field", "field name"]),
        _F("well_info.project_name", "text", "", False, ["project"]),
        _F("well_info.rig_name", "text", "", False, ["rig name", "rig"]),
        _F("well_info.well_type", "text", "", False, ["well type"]),
        _F("well_info.well_shape", "text", "", False, ["well shape"]),
        _F("well_info.client", "text", "", False, ["client"]),
        _F("well_info.operator", "text", "", False, ["operator"]),
        _F("well_info.drilling_contractor", "text", "", False, ["drilling contractor"]),
        _F("well_info.report_no", "integer", "", False, ["report no", "report no."]),
        _F("well_info.client_rep", "text", "", False, ["client rep"]),
        _F("well_info.section_name", "text", "", False, ["hole section", "section name"]),
        _F("well_info.target_depth", "length", "m", False, ["estimated final depth", "target depth"]),
        _F("well_info.water_depth", "length", "m", False, ["offshore water depth", "water depth"]),
        _F("well_info.gle_msl", "length", "m", False, ["gle-msl", "gle msl"]),
        _F("well_info.rte_msl", "length", "m", False, ["rte-msl", "rte msl"]),
        _F("well_info.gle_rte", "length", "m", False, ["gle-rte", "rt - wh", "gle rte"]),
        _F("well_info.rig_heading", "text", "", False, ["rig heading"]),
        _F("well_info.easting", "length", "m", False, ["easting"]),
        _F("well_info.northing", "length", "m", False, ["northing"]),
        _F("well_info.latitude", "number", "", False, ["latitude", "lat"]),
        _F("well_info.longitude", "number", "", False, ["longitude", "long"]),
        _F("well_info.formation", "text", "", False, ["formation"]),
        _F("well_info.kop1", "length", "m", False, ["kop1", "kop 1"]),
        _F("well_info.kop2", "length", "m", False, ["kop2", "kop 2"]),
        _F("well_info.geologist1", "text", "", False, ["site geologist", "geologist"]),
        _F("well_info.operation_manager", "text", "", False, ["operation manager"]),
        _F("well_info.superintendent", "text", "", False, ["superintendent"]),
        _F("well_info.supervisor_day", "text", "", False, ["supervisor (day)", "supervisor day"]),
        _F("well_info.supervisor_night", "text", "", False, ["supervisor (night)", "supervisor night"]),
        _F("well_info.tool_pusher_day", "text", "", False, ["tool pusher"]),
        _F("well_info.drilling_engineer", "text", "", False, ["well site drilling engineering", "drilling engineer"]),
        _F("well_info.report_date", "date", "", True, ["report date", "date"]),
        _F("well_info.spud_date", "date", "", False, ["spud", "spud date"]),
        _F("well_info.start_hole_date", "date", "", False, ["hole section strat", "start hole date"]),
        _F("well_info.lta_day", "integer", "day", False, ["lta (day)", "lta day", "lta"]),
        _F("well_info.actual_rig_days", "number", "day", False, ["actual rig days"]),

        # ---------------- Daily Report ----------------
        _F("daily_report.report_date", "date", "", True, ["report date"]),
        _F("daily_report.report_number", "integer", "", False, ["report no", "report number"]),
        _F("daily_report.lta_day", "integer", "day", False, ["lta (day)", "lta day", "lta"]),
        _F("daily_report.actual_rig_days", "number", "day", False, ["actual rig days"]),
        _F("daily_report.report_year", "integer", "", False, ["report year", "year"]),
        _F("daily_report.report_month", "text", "", False, ["report month", "month"]),
        _F("daily_report.report_day", "integer", "", False, ["report day", "day"]),
        _F("daily_report.report_time", "time", "", False, ["report time"]),
        _F("daily_report.depth_0000", "length", "m", False, ["md (m)@ 0:00", "depth @ 0:00", "depth_0000"]),
        _F("daily_report.depth_0600", "length", "m", False, ["md (m)@ 6:00", "depth @ 6:00", "depth_0600"]),
        _F("daily_report.depth_2400", "length", "m", True, ["md (m)@ 24:00", "depth @ 24:00", "depth_2400", "measured depth", "bit depth", "current depth", "depth", "td"]),
        _F("daily_report.drilled_24hrs", "length", "m", False, ["24 hrs drilled", "drilled 24hrs"]),
        _F("daily_report.avg_rop", "rate", "m/hr", False, ["avg rop", "average rop", "rop"]),
        _F("daily_report.avg_rop_remark", "rate", "m/hr", False, ["avg. rop", "avg rop remark"]),
        _F("daily_report.rt_wh", "length", "m", False, ["rt - wh", "rt wh"]),
        _F("daily_report.mw_pcf", "density", "pcf", False, ["mw (pcf)", "mw pcf"]),
        _F("daily_report.section_start_depth", "length", "m", False, ["section start depth"]),
        _F("daily_report.vol_in_hole", "volume", "bbl", False, ["vol. in hole", "vol in hole"]),
        _F("daily_report.total_circ_vol", "volume", "bbl", False, ["total cir. volume", "total circ volume"]),
        _F("daily_report.mud_lost_downhole", "volume", "bbl", False, ["mud lost down hole", "mud lost downhole"]),
        _F("daily_report.mud_lost_surface", "volume", "bbl", False, ["mud lost at surface", "mud lost surface"]),
        _F("daily_report.suction1_vol", "volume", "bbl", False, ["suction 1 vol", "suction1 vol"]),
        _F("daily_report.suction1_mw", "density", "pcf", False, ["suction 1 mw", "suction1 mw"]),
        _F("daily_report.suction2_vol", "volume", "bbl", False, ["suction 2 vol"]),
        _F("daily_report.suction2_mw", "density", "pcf", False, ["suction 2 mw"]),
        _F("daily_report.reserve1_vol", "volume", "bbl", False, ["reserve 1 vol"]),
        _F("daily_report.reserve1_mw", "density", "pcf", False, ["reserve 1 mw"]),
        _F("daily_report.reserve2_vol", "volume", "bbl", False, ["reserve 2 vol"]),
        _F("daily_report.reserve2_mw", "density", "pcf", False, ["reserve 2 mw"]),
        _F("daily_report.reserve3_vol", "volume", "bbl", False, ["reserve 3 vol"]),
        _F("daily_report.reserve3_mw", "density", "pcf", False, ["reserve 3 mw"]),
        _F("daily_report.reserve4_vol", "volume", "bbl", False, ["reserve 4 vol"]),
        _F("daily_report.middle_vol", "volume", "bbl", False, ["middle vol"]),
        _F("daily_report.middle_mw", "density", "pcf", False, ["middle mw"]),
        _F("daily_report.desilter_vol", "volume", "bbl", False, ["desilter vol"]),
        _F("daily_report.desander_vol", "volume", "bbl", False, ["desander vol"]),
        _F("daily_report.desander_mw", "density", "pcf", False, ["desander mw"]),
        _F("daily_report.degasser_vol", "volume", "bbl", False, ["degasser vol"]),
        _F("daily_report.degasser_mw", "density", "pcf", False, ["degasser mw"]),
        _F("daily_report.sand_trap_vol", "volume", "bbl", False, ["sand trap vol"]),
        _F("daily_report.sand_trap_mw", "density", "pcf", False, ["sand trap mw"]),
        _F("daily_report.summary", "text", "", False, ["summary", "summary of activities", "summary text block"]),
        _F("daily_report.forecast", "text", "", False, ["operation forecast", "forecast"]),
        _F("daily_report.note_01", "text", "", False, ["note#01", "note 1"]),
        _F("daily_report.note_02", "text", "", False, ["note#02", "note 2"]),
        _F("daily_report.note_03", "text", "", False, ["note#03", "note 3"]),
        _F("daily_report.note_04", "text", "", False, ["note#04", "note 4"]),
        _F("daily_report.note_05", "text", "", False, ["note#05", "note 5"]),
        _F("daily_report.note_06", "text", "", False, ["note#06", "note 6"]),
        _F("daily_report.note_07", "text", "", False, ["note#07", "note 7"]),
        _F("daily_report.material_request", "text", "", False, ["material request"]),
        _F("daily_report.material_request_detail", "text", "", False, ["request detail"]),
        _F("daily_report.outstanding", "text", "", False, ["outstanding"]),
        _F("daily_report.received_items", "text", "", False, ["received"]),
        _F("daily_report.backload_items", "text", "", False, ["back load", "backload"]),

        # ---------------- Mud Report ----------------
        _F("mud_report.mud_type", "text", "", False, ["mud type"]),
        _F("mud_report.mw", "density", "ppg", True, ["mud weight", "mw", "mud wt", "mudweight", "density", "1.50 sg", "sg"], bounds=(0.0, 25.0)),
        _F("mud_report.mw_unit", "text", "", False, ["mw unit", "unit"]),
        _F("mud_report.mw_original", "number", "", False, ["mw original"]),
        _F("mud_report.funnel_vis", "viscosity", "sec/qt", False, ["funnel vis", "funnel viscosity"]),
        _F("mud_report.pv", "viscosity", "cp", False, ["pv", "plastic viscosity", "pv (cp)"]),
        _F("mud_report.yp", "stress", "lb/100ft2", False, ["yp", "yield point", "yp (lb/100ft2)"]),
        _F("mud_report.gel_10s", "stress", "lb/100ft2", False, ["gel 10 s", "gel 10s", "gel 10 sec"]),
        _F("mud_report.gel_10m", "stress", "lb/100ft2", False, ["gel 10 min", "gel 10m"]),
        _F("mud_report.fl", "volume", "cc/30min", False, ["fluid loss", "api fluid loss", "api fl", "fl", "filtrate"]),
        _F("mud_report.total_hardness", "number", "mg/lit", False, ["total hardness"]),
        _F("mud_report.cake_thickness", "length", "1/32in", False, ["filter cake", "cake thickness"]),
        _F("mud_report.solid_percent", "number", "%", False, ["solid", "solid (% vol)"]),
        _F("mud_report.chloride", "number", "mg/lit", False, ["chloride"]),
        _F("mud_report.oil_percent", "number", "%", False, ["oil / water", "oil percent"]),
        _F("mud_report.water_percent", "number", "%", False, ["water percent"]),
        _F("mud_report.kcl", "number", "%", False, ["kcl", "kcl (% wt)"]),
        _F("mud_report.ph", "number", "", False, ["ph"]),
        _F("mud_report.temperature", "temperature", "C", False, ["flow line temp", "temperature"]),
        _F("mud_report.flowline_temp", "temperature", "F", False, ["flowline temp"]),
        _F("mud_report.calcium", "number", "mg/lit", False, ["ca++", "calcium"]),
        _F("mud_report.pf_mf", "text", "", False, ["pf / mf", "pf/mf"]),
        _F("mud_report.mbt", "number", "lb/bbl", False, ["mbt"]),
        _F("mud_report.volume_hole", "volume", "bbl", False, ["vol. in hole (bbls)"]),
        _F("mud_report.loss_surface", "volume", "bbl", False, ["lost at surface"]),
        _F("mud_report.loss_downhole", "volume", "bbl", False, ["lost down hole"]),

        # ---------------- Drilling Parameters ----------------
        _F("drilling_params.bit_no", "text", "", False, ["bit no", "bit no.", "bit number"]),
        _F("drilling_params.bit_rerun", "integer", "", False, ["bit rerun", "bit rerun no"]),
        _F("drilling_params.bit_size", "length", "in", True, ["bit size", "bit size (inch)"], bounds=(0.0, 50.0)),
        _F("drilling_params.bit_type", "text", "", False, ["bit type"]),
        _F("drilling_params.manufacturer", "text", "", False, ["bit manufacture", "bit manufacturer"]),
        _F("drilling_params.bit_serial", "text", "", False, ["bit serial no", "bit serial"]),
        _F("drilling_params.iadc_code", "text", "", False, ["iadc code", "iadc"]),
        _F("drilling_params.nozzle1_no", "integer", "", False, ["nozzle 1 no", "nozzle no 1"]),
        _F("drilling_params.nozzle1_size", "text", "", False, ["nozzle 1 size"]),
        _F("drilling_params.nozzle2_no", "integer", "", False, ["nozzle 2 no", "nozzle no 2"]),
        _F("drilling_params.nozzle2_size", "text", "", False, ["nozzle 2 size"]),
        _F("drilling_params.tfa", "area", "in2", False, ["tfa", "tfa (in^2)"]),
        _F("drilling_params.bit_drilled", "length", "m", False, ["bit drilled"]),
        _F("drilling_params.bit_cum_drilled", "length", "m", False, ["bit cum. drilled"]),
        _F("drilling_params.bit_hours_on_bottom", "number", "hr", False, ["bit hours on bottom"]),
        _F("drilling_params.bit_cum_hrs_on_bottom", "number", "hr", False, ["bit cum. hrs on bottom"]),
        _F("drilling_params.cum_bit_avg_rop", "rate", "m/hr", False, ["cum.bit ave rop"]),
        _F("drilling_params.bit_dull_condition", "text", "", False, ["bit dull condition", "bit dull grading"]),
        _F("drilling_params.bit_revolution", "number", "k.rev", False, ["bit revolution", "bit spin"]),
        _F("drilling_params.pump_liner_size", "text", "", False, ["pump liner size", "liner size"]),
        _F("drilling_params.pump_output_min", "flow_rate", "gpm", False, ["pump output min", "flow rate min"]),
        _F("drilling_params.pump_output_max", "flow_rate", "gpm", False, ["pump output max", "flow rate max"]),
        _F("drilling_params.wob_min", "force", "klb", False, ["wob min", "weight on bit min"]),
        _F("drilling_params.wob_max", "force", "klb", False, ["wob", "wob max", "wt. on bit", "bit load", "weight on bit", "w.o.b"]),
        _F("drilling_params.rpm_min", "rpm", "", False, ["rpm min", "rotary min"]),
        _F("drilling_params.rpm_max", "rpm", "", False, ["rpm", "rpm max", "rotary", "rotary speed", "surface rpm"]),
        _F("drilling_params.torque_min", "torque", "kft-lbs", False, ["torque min"]),
        _F("drilling_params.torque_max", "torque", "kft-lbs", False, ["torque", "torque max"]),
        _F("drilling_params.pump_pressure_min", "pressure", "psi", False, ["pump pressure min", "spp min"]),
        _F("drilling_params.pump_pressure_max", "pressure", "psi", False, ["pump pressure", "spp", "pump pressure max"]),
        _F("drilling_params.depth_in", "length", "m", False, ["depth in"]),
        _F("drilling_params.depth_out", "length", "m", False, ["depth out"]),
        _F("drilling_params.avg_rop", "rate", "m/hr", False, ["avg rop"]),
        _F("drilling_params.hours_on_bottom", "number", "hr", False, ["hours on bottom"]),
        _F("drilling_params.motor_rpm", "rpm", "", False, ["motor rpm"]),

        # ---------------- Drilling Parameter table (row-oriented) ----------------
        _F("drilling_param.name", "text", "", False, ["parameter"]),
        _F("drilling_param.min", "number", "", False, ["min"]),
        _F("drilling_param.max", "number", "", False, ["max"]),

        # ---------------- Time Log ----------------
        _F("time_log.time_from", "time", "", False, ["from", "time from"]),
        _F("time_log.time_to", "time", "", False, ["to", "time to"]),
        _F("time_log.duration", "number", "hr", False, ["hrs", "duration", "hours"]),
        _F("time_log.main_phase", "text", "", False, ["main phase"]),
        _F("time_log.main_code", "code", "", True, ["code"]),
        _F("time_log.sub_code", "code", "", True, ["sub code"]),
        _F("time_log.status", "text", "", False, ["status"]),
        _F("time_log.npt_category", "text", "", False, ["npt/ unplan attributed", "npt category", "npt"]),
        _F("time_log.activity_description", "text", "", False, ["rig activity", "activity description"]),
        _F("time_log.contractor", "text", "", False, ["contractor"]),

        _F("time_log_morning.time_from", "time", "", False, ["morning from"]),
        _F("time_log_morning.time_to", "time", "", False, ["morning to"]),
        _F("time_log_morning.duration", "number", "hr", False, ["morning hrs"]),
        _F("time_log_morning.main_phase", "text", "", False, ["morning main phase"]),
        _F("time_log_morning.main_code", "code", "", True, ["morning code"]),
        _F("time_log_morning.sub_code", "code", "", True, ["morning sub code"]),
        _F("time_log_morning.status", "text", "", False, ["morning status"]),
        _F("time_log_morning.npt_category", "text", "", False, ["morning npt"]),
        _F("time_log_morning.activity_description", "text", "", False, ["morning rig activity"]),
        _F("time_log_morning.contractor", "text", "", False, ["morning contractor"]),

        # ---------------- Survey ----------------
        _F("survey.md", "length", "m", True, ["md", "m.d", "measured depth"], bounds=(0.0, None)),
        _F("survey.inc", "angle", "deg", False, ["inc", "inclination", "incl."], bounds=(0.0, 180.0)),
        _F("survey.azi", "angle", "deg", False, ["azi", "azimuth"], bounds=(0.0, 360.0)),
        _F("survey.tvd", "length", "m", False, ["tvd"]),
        _F("survey.north", "length", "m", False, ["north"]),
        _F("survey.east", "length", "m", False, ["east"]),
        _F("survey.vs_hd", "length", "m", False, ["vs / hd", "vs/hd", "vs", "hd"]),
        _F("survey.dls", "dls", "", False, ["dls"]),
        _F("survey.tool", "text", "", False, ["tool"]),

        # ---------------- BHA ----------------
        _F("bha.component_name", "text", "", False, ["item", "component name"]),
        _F("bha.od", "length", "in", False, ["od (in)", "od"]),
        _F("bha.length", "length", "m", False, ["length (m)", "length"]),
        _F("bha.cum_length", "length", "m", False, ["cum. len", "cum length"]),
        _F("bha.total_length", "length", "m", False, ["total"]),

        # ---------------- Downhole ----------------
        _F("downhole.equipment_name", "text", "", False, ["equipment", "equipment name"]),
        _F("downhole.od", "text", "", False, ["od (inch)", "od"]),
        _F("downhole.serial_number", "text", "", False, ["serial number", "serial no"]),
        _F("downhole.rot_hrs", "number", "hr", False, ["rot. hrs", "rot hrs"]),
        _F("downhole.cum_hrs", "number", "hr", False, ["cum. hrs", "cum hrs"]),

        # ---------------- Mud Chemical ----------------
        _F("mud_chemical.product_type", "text", "", False, ["product type", "product"]),
        _F("mud_chemical.used", "volume", "", False, ["used"]),
        _F("mud_chemical.received", "volume", "", False, ["received"]),
        _F("mud_chemical.on_hand", "volume", "", False, ["on hand"]),
        _F("mud_chemical.unit", "text", "", False, ["unit"]),

        # ---------------- Bulk Material ----------------
        _F("bulk_material.material_name", "text", "", False, ["material name", "mat. type", "material"]),
        _F("bulk_material.unit", "text", "", False, ["unit"]),
        _F("bulk_material.initial_stock", "volume", "", False, ["initial stock", "on hand"]),
        _F("bulk_material.received", "volume", "", False, ["received"]),
        _F("bulk_material.used", "volume", "", False, ["used"]),
        _F("bulk_material.current_stock", "volume", "", False, ["current stock"]),
        _F("bulk_material.blend_cmt", "volume", "MT", False, ["blend cmt"]),
        _F("bulk_material.cmt_g", "volume", "MT", False, ["cmt g", "cmt g delijan"]),

        # ---------------- SCR ----------------
        _F("scr.pump", "text", "", False, ["pump"]),
        _F("scr.spm", "rpm", "", False, ["spm"]),
        _F("scr.fr_gpm", "flow_rate", "gpm", False, ["fr (gpm)", "fr gpm"]),
        _F("scr.spp", "pressure", "psi", False, ["spp"]),

        # ---------------- BOP ----------------
        _F("bop.name", "text", "", False, ["name"]),
        _F("bop.type", "text", "", False, ["type", "bop type"]),
        _F("bop.working_pressure", "pressure", "psi", True, ["w.p (psi)", "wp", "working pressure", "w.p"]),
        _F("bop.size", "text", "", False, ["size"]),
        _F("bop.rams", "text", "", False, ["rams"]),
        _F("bop.last_test", "date", "", False, ["last test"]),

        # ---------------- Service ----------------
        _F("service.company_name", "text", "", False, ["company name", "company"]),
        _F("service.service_type", "text", "", False, ["service type", "service"]),
        _F("service.personnel_count", "integer", "", False, ["personnel", "personnel count", "pax"]),
        _F("service.contact", "text", "", False, ["contact"]),
        _F("service.phone", "text", "", False, ["phone"]),
        _F("service.npt_hours", "number", "hr", False, ["total npt (hrs)", "total npt", "npt hours"]),
        _F("service.hole_section", "text", "", False, ["hole section"]),
        _F("service.date_in", "text", "", False, ["date in"]),
        _F("service.date_out", "text", "", False, ["date out"]),
        _F("service.duration_day", "number", "day", False, ["duration (day)", "duration day"]),
        _F("service.description", "text", "", False, ["job description", "description"]),
        _F("service.condition", "text", "", False, ["condition"]),
        _F("service.issue", "text", "", False, ["problem/issue", "problem", "issue"]),

        # ---------------- Lookahead ----------------
        _F("lookahead.day", "date", "", False, ["days", "day"]),
        _F("lookahead.date", "date", "", False, ["date"]),
        _F("lookahead.hours", "number", "hr", False, ["hrs"]),
        _F("lookahead.date_start", "date", "", False, ["date start"]),
        _F("lookahead.date_end", "date", "", False, ["date end"]),
        _F("lookahead.activity", "text", "", False, ["activity"]),
        _F("lookahead.tools", "text", "", False, ["tools"]),
        _F("lookahead.responsible", "text", "", False, ["responsible"]),
        _F("lookahead.remarks", "text", "", False, ["remarks", "comments"]),

        # ---------------- Cement ----------------
        _F("cement.material_type", "text", "", False, ["material type", "material"]),
        _F("cement.used", "volume", "", False, ["used"]),
        _F("cement.received", "volume", "", False, ["received"]),
        _F("cement.on_hand", "volume", "", False, ["on hand"]),
        _F("cement.unit", "text", "", False, ["unit"]),
        _F("cement.slurry_density", "density", "ppg", False, ["slurry density"]),

        # ---------------- Casing ----------------
        _F("casing.size", "length", "in", False, ["size (in)", "size"]),
        _F("casing.depth_from", "length", "m", False, ["from (m)", "depth from"]),
        _F("casing.depth_to", "length", "m", False, ["to (m)", "depth to"]),
        _F("casing.grade", "text", "", False, ["grade"]),
        _F("casing.weight", "number", "#", False, ["weight (#)", "weight"]),
        _F("casing.thread", "text", "", False, ["thread"]),
        _F("casing.shoe_tvd", "length", "m", False, ["shoe tvd"]),
        _F("casing.burst_pressure", "pressure", "psi", False, ["burst pressure"]),
        _F("casing.collapse_pressure", "pressure", "psi", False, ["collapse pressure"]),

        # ---------------- Fuel / Water ----------------
        _F("fuel_water.fw_on_hand", "volume", "Lit", False, ["f.w on hand"]),
        _F("fuel_water.fw_used", "volume", "Lit", False, ["f.w used"]),
        _F("fuel_water.fw_received", "volume", "Lit", False, ["f.w received"]),
        _F("fuel_water.dw_on_hand", "volume", "BBL", False, ["d.w on hand"]),
        _F("fuel_water.dw_used", "volume", "BBL", False, ["d.w used"]),
        _F("fuel_water.dw_received", "volume", "BBL", False, ["d.w received"]),
        _F("fuel_water.fuel_rig_on_hand", "volume", "Lit", False, ["fuel rig on hand"]),
        _F("fuel_water.fuel_rig_used", "volume", "Lit", False, ["fuel rig used"]),
        _F("fuel_water.fuel_rig_received", "volume", "Lit", False, ["fuel rig received"]),
        _F("fuel_water.fuel_camp_on_hand", "volume", "Lit", False, ["fuel camp on hand"]),
        _F("fuel_water.fuel_camp_used", "volume", "Lit", False, ["fuel camp used"]),
        _F("fuel_water.fuel_camp_received", "volume", "Lit", False, ["fuel camp received"]),

        # ---------------- Logistics / POB ----------------
        _F("logistics.company_name", "text", "", False, ["company name"]),
        _F("logistics.pob_rig", "integer", "", False, ["oeoc rig"]),
        _F("logistics.pob_client", "integer", "", False, ["client (kpe)", "client"]),
        _F("logistics.pob_msa", "integer", "", False, ["msa"]),
        _F("logistics.pob_service", "integer", "", False, ["service company"]),
        _F("logistics.pob_catering", "integer", "", False, ["catering + guard", "catering"]),
        _F("logistics.pob_labour", "integer", "", False, ["labour"]),
        _F("logistics.pob_other", "integer", "", False, ["other"]),
        _F("logistics.pob_total", "integer", "", False, ["total pob", "pob total"]),

        # ---------------- Safety ----------------
        _F("safety.days_without_lti", "integer", "day", False, ["days without lta", "days without lti", "lta"]),
        _F("safety.last_bop_test", "date", "", False, ["last bop test"]),
        _F("safety.last_fire_drill", "date", "", False, ["last fire drill"]),
        _F("safety.last_h2s_drill", "date", "", False, ["last h2s drill"]),
        _F("safety.last_bop_drill", "date", "", False, ["last bop drill"]),
        _F("safety.wind_speed", "rate", "km/h", False, ["wind speed"]),
        _F("safety.wind_direction", "text", "", False, ["wind direction"]),
        _F("safety.temperature", "temperature", "C", False, ["temp", "temperature"]),
        _F("safety.visibility", "number", "km", False, ["visibility"]),

        # ---------------- Formation ----------------
        _F("formation.name", "text", "", False, ["name", "formation name"]),
        _F("formation.md_top", "length", "m", False, ["m md", "md top"]),
        _F("formation.tvd", "length", "m", False, ["m tvd", "tvd"]),
        _F("formation.lithology", "text", "", False, ["lithology"]),

        # ---------------- Solid Control ----------------
        _F("solid_control.equipment", "text", "", False, ["equipment"]),
        _F("solid_control.size_cones", "text", "", False, ["size/# cones", "size cones"]),
        _F("solid_control.uf", "text", "", False, ["u.f", "uf"]),
        _F("solid_control.of", "text", "", False, ["o.f", "of"]),
        _F("solid_control.daily_hrs", "number", "hr", False, ["daily hrs", "daily hrs/ cum hrs"]),
        _F("solid_control.cum_hrs", "number", "hr", False, ["cum hrs"]),

        # ---------------- Transport / Boats ----------------
        _F("transport.name", "text", "", False, ["name", "boat name"]),
        _F("transport.arrival_time", "time", "", False, ["arrival rig time", "arrival time"]),
        _F("transport.arrival_date", "date", "", False, ["arrival rig date", "arrival date"]),
        _F("transport.departure_time", "time", "", False, ["departure time"]),
        _F("transport.departure_date", "date", "", False, ["departure date"]),
        _F("transport.pax_in", "integer", "", False, ["no. of pax in", "pax in"]),
        _F("transport.status", "text", "", False, ["status"]),

        # ---------------- Time Breakdown ----------------
        _F("time_breakdown.code", "code", "", False, ["no", "code"]),
        _F("time_breakdown.activity", "text", "", False, ["activity"]),
        _F("time_breakdown.hours", "number", "hr", False, ["hrs", "hours"]),

        # ---------------- NPT ----------------
        _F("npt.npt_category", "text", "", False, ["npt category"]),
        _F("npt.duration_hours", "number", "hr", False, ["npt duration", "duration hours"]),
        _F("npt.npt_code", "code", "", False, ["npt code"]),
        _F("npt.responsible_party", "text", "", False, ["responsible party", "npt service company"]),
        _F("npt.description", "text", "", False, ["npt description"]),
        _F("npt.start_time", "time", "", False, ["start time"]),
        _F("npt.end_time", "time", "", False, ["end time"]),

        # ---------------- Cost ----------------
        _F("cost.description", "text", "", False, ["description"]),
        _F("cost.amount", "currency", "", False, ["amount"]),
        _F("cost.planned_cost", "currency", "", False, ["planned cost"]),
        _F("cost.actual_cost", "currency", "", False, ["actual cost"]),
        _F("cost.category", "text", "", False, ["category", "cost category"]),

        # ---------------- Equipment ----------------
        _F("equipment.equipment_name", "text", "", False, ["equipment name"]),
        _F("equipment.equipment_type", "text", "", False, ["equipment type"]),
        _F("equipment.equipment_id", "text", "", False, ["equipment id"]),
        _F("equipment.serial_number", "text", "", False, ["serial number"]),
        _F("equipment.manufacturer", "text", "", False, ["manufacturer"]),
        _F("equipment.hours_worked", "number", "hr", False, ["hours worked", "rot. hrs"]),
        _F("equipment.status", "text", "", False, ["status"]),
        _F("equipment.notes", "text", "", False, ["notes"]),
    ]
}

CANONICAL_FIELDS: FrozenSet[str] = frozenset(FIELD_SPECS.keys())

# Centralized alias index — built once from FieldSpec.aliases.
_ALIAS_INDEX: Dict[str, str] = {}
for _path, _spec in FIELD_SPECS.items():
    for _alias in _spec.aliases:
        _key = _alias.strip().lower().rstrip(":").strip()
        if _key and _key not in _ALIAS_INDEX:
            _ALIAS_INDEX[_key] = _path

# Aliases that are also valid canonical paths themselves (e.g. "md").
_ALIAS_INDEX.update({p: p for p in FIELD_SPECS})


def _normalize(text: str) -> str:
    return str(text or "").strip().lower().rstrip(":").strip()


def lookup_alias(text: str) -> Optional[str]:
    """Resolve a free-text label/alias to a canonical field path.

    Resolution order:
      1. exact canonical path (e.g. "mud_report.mw")
      2. exact alias match (e.g. "mud weight", "mw")
      3. alias with trailing spaces/colons normalized
      4. canonical key match (e.g. "md" -> survey.md)
    Returns None when unresolvable.
    """
    if not text:
        return None
    key = _normalize(text)
    if not key:
        return None
    if key in _ALIAS_INDEX:
        return _ALIAS_INDEX[key]
    # Fall back to matching the tail of a canonical path (e.g. "bit size").
    for path in FIELD_SPECS:
        if path.split(".")[-1] == key:
            return path
        if path.split(".")[-1].replace("_", " ") == key:
            return path
    return None


def get_field_spec(path: str) -> Optional[FieldSpec]:
    """Return the FieldSpec for a canonical path, or None."""
    return FIELD_SPECS.get(path)


def get_engineering_bounds(path: str) -> Tuple[Optional[float], Optional[float]]:
    """Return (min, max) engineering bounds for a canonical field."""
    spec = FIELD_SPECS.get(path)
    if spec is None:
        return (None, None)
    return (spec.min_val, spec.max_val)


def get_quantity_unit(path: str) -> Tuple[Optional[str], str]:
    """Return (quantity, unit) for a canonical field."""
    spec = FIELD_SPECS.get(path)
    if spec is None:
        return (None, "")
    return (spec.quantity, spec.unit)


def get_critical_fields() -> List[str]:
    """Return all canonical paths marked critical."""
    return [p for p, s in FIELD_SPECS.items() if s.critical]


def get_fields_by_quantity(quantity: str) -> List[str]:
    """Return all canonical paths with the given quantity type."""
    return [p for p, s in FIELD_SPECS.items() if s.quantity == quantity]


# Deterministic mapping methods that may be trusted at high confidence.
DETERMINISTIC_MAPPING_METHODS = frozenset({
    "preferred_cell", "merge_cell", "label_match", "alias_match",
    "learned", "exact", "template", "deterministic",
})


def mapping_certainty(confidence: float, method: str = "") -> str:
    """Map a confidence score + mapping method to a certainty tier.

    Policy:
      * Deterministic template/preferred/label mappings with solid
        confidence (>= 0.70) -> HIGH
      * Deterministic mappings with moderate confidence (>= 0.50) -> MEDIUM
      * Fuzzy/ambiguous/spatial mappings -> never HIGH; >= 0.85 -> MEDIUM,
        otherwise LOW.

    Confidence is never inflated: a fuzzy match can never reach HIGH merely
    by raising its score — its confidence is capped by the mapping itself,
    and the method keeps the tier honest.
    """
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return "LOW"
    deterministic = method in DETERMINISTIC_MAPPING_METHODS
    if deterministic:
        if confidence >= 0.70:
            return "HIGH"
        if confidence >= 0.50:
            return "MEDIUM"
        return "LOW"
    if confidence >= 0.85:
        return "MEDIUM"
    return "LOW"
