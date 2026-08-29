"""Single canonical field registry shared by import, units, review and AI.

Every field in this registry is the Single Source of Truth for:
- Import mapping (AI and deterministic)
- Unit conversion (UnitManager)
- Validation (validators)
- Database storage (ORM models)
- UI display (tabs)
- Export (reports)

If a field exists here, other modules MUST reference it rather than redefine it.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class FieldSpec:
    path: str
    quantity: str = "text"
    unit: str = ""
    critical: bool = False

# fmt: off
_FIELD_TUPLES = [
    # ── Well Info ──────────────────────────────────────────────
    ("well_info.name",              "text",       "",      True),
    ("well_info.report_date",       "date",       "",      True),
    ("well_info.well_type",         "text",       "",      False),
    ("well_info.rig_name",          "text",       "",      False),
    ("well_info.field_name",        "text",       "",      False),
    ("well_info.operator",          "text",       "",      False),
    ("well_info.client",            "text",       "",      False),
    ("well_info.location",          "text",       "",      False),
    ("well_info.spud_date",         "date",       "",      False),
    ("well_info.target_depth",      "length",     "m",     False),

    # ── Daily Report ──────────────────────────────────────────
    ("daily_report.report_date",    "date",       "",      True),
    ("daily_report.report_number",  "integer",    "",      False),
    ("daily_report.rig_day",        "integer",    "",      False),
    ("daily_report.depth_0000",     "length",     "m",     False),
    ("daily_report.depth_0600",     "length",     "m",     False),
    ("daily_report.depth_2400",     "length",     "m",     True),
    ("daily_report.summary",        "text",       "",      False),
    ("daily_report.status",         "text",       "",      False),

    # ── Mud Report ────────────────────────────────────────────
    ("mud_report.mw",               "density",    "ppg",   True),
    ("mud_report.pv",               "viscosity",  "cp",    False),
    ("mud_report.yp",               "stress",     "lb/100ft2", False),
    ("mud_report.funnel_vis",       "viscosity",  "sec",   False),
    ("mud_report.gel_10s",          "stress",     "lb/100ft2", False),
    ("mud_report.gel_10m",          "stress",     "lb/100ft2", False),
    ("mud_report.fl",               "volume",     "ml",    False),
    ("mud_report.cake_thickness",   "length",     "mm",    False),
    ("mud_report.ph",               "number",     "",      False),
    ("mud_report.temperature",      "temperature","C",     False),
    ("mud_report.solid_percent",    "number",     "%",     False),
    ("mud_report.oil_percent",      "number",     "%",     False),
    ("mud_report.water_percent",    "number",     "%",     False),
    ("mud_report.chloride",         "number",     "mg/L",  False),
    ("mud_report.mud_type",         "text",       "",      False),

    # ── Drilling Parameters ───────────────────────────────────
    ("drilling_params.bit_no",      "text",       "",      False),
    ("drilling_params.bit_size",    "length",     "in",    True),
    ("drilling_params.bit_type",    "text",       "",      False),
    ("drilling_params.iadc_code",   "text",       "",      False),
    ("drilling_params.manufacturer","text",       "",      False),
    ("drilling_params.depth_in",    "length",     "m",     False),
    ("drilling_params.depth_out",   "length",     "m",     False),
    ("drilling_params.hours_on_bottom","number",  "hr",    False),
    ("drilling_params.avg_rop",     "rate",       "m/hr",  False),
    ("drilling_params.wob_min",     "force",      "klbf",  False),
    ("drilling_params.wob_max",     "force",      "klbf",  False),
    ("drilling_params.rpm_min",     "rpm",        "rpm",   False),
    ("drilling_params.rpm_max",     "rpm",        "rpm",   False),
    ("drilling_params.torque_min",  "torque",     "ft_lbf",False),
    ("drilling_params.torque_max",  "torque",     "ft_lbf",False),
    ("drilling_params.pump_pressure_min","pressure","psi",  False),
    ("drilling_params.pump_pressure_max","pressure","psi",  False),
    ("drilling_params.pump_output_min","flow_rate","gpm",   False),
    ("drilling_params.pump_output_max","flow_rate","gpm",   False),
    ("drilling_params.tfa",         "area",       "in2",   False),
    ("drilling_params.hsi",         "number",     "",      False),
    ("drilling_params.annular_velocity","rate",   "ft/min",False),

    # ── Time Log ──────────────────────────────────────────────
    ("time_log.main_code",          "code",       "",      True),
    ("time_log.sub_code",           "code",       "",      True),
    ("time_log.contractor",         "text",       "",      False),
    ("time_log.activity_description","text",      "",      False),
    ("time_log.duration",           "number",     "hr",    False),

    # ── Survey / Trajectory ───────────────────────────────────
    ("survey.md",                   "length",     "m",     True),
    ("survey.inc",                  "angle",      "deg",   False),
    ("survey.azi",                  "angle",      "deg",   False),
    ("survey.tvd",                  "length",     "m",     False),
    ("survey.north",                "length",     "m",     False),
    ("survey.east",                 "length",     "m",     False),
    ("survey.dls",                  "dls",        "deg/30m",False),
    ("survey.tool",                 "text",       "",      False),

    # ── Bulk Materials ────────────────────────────────────────
    ("bulk_material.material_name", "text",       "",      False),
    ("bulk_material.unit",          "text",       "",      False),
    ("bulk_material.initial_stock", "volume",     "",      False),
    ("bulk_material.received",      "volume",     "",      False),
    ("bulk_material.used",          "volume",     "",      False),
    ("bulk_material.current_stock", "volume",     "",      False),

    # ── BHA ───────────────────────────────────────────────────
    ("bha.component_name",          "text",       "",      False),
    ("bha.od",                      "length",     "in",    False),
    ("bha.id",                      "length",     "in",    False),
    ("bha.length",                  "length",     "m",     False),
    ("bha.weight",                  "weight",     "ppf",   False),

    # ── Downhole Equipment ────────────────────────────────────
    ("downhole.equipment_name",     "text",       "",      False),
    ("downhole.serial_number",      "text",       "",      False),

    # ── Formation ─────────────────────────────────────────────
    ("formation.name",              "text",       "",      False),
    ("formation.md_top",            "length",     "m",     False),
    ("formation.md_bottom",         "length",     "m",     False),

    # ── Casing ────────────────────────────────────────────────
    ("casing.size",                 "length",     "in",    False),
    ("casing.weight",               "weight",     "ppf",   False),
    ("casing.depth_from",           "length",     "m",     False),
    ("casing.depth_to",             "length",     "m",     False),
    ("casing.grade",                "text",       "",      False),

    # ── Cement ────────────────────────────────────────────────
    ("cement.material",             "text",       "",      False),
    ("cement.used",                 "volume",     "",      False),
    ("cement.slurry_density",       "density",    "ppg",   False),

    # ── BOP ───────────────────────────────────────────────────
    ("bop.component_name",          "text",       "",      False),
    ("bop.component_type",          "text",       "",      False),
    ("bop.working_pressure",        "pressure",   "psi",   True),
    ("bop.size",                    "text",       "",      False),
    ("bop.test_pressure",           "pressure",   "psi",   False),

    # ── Safety ────────────────────────────────────────────────
    ("safety.days_without_lti",     "integer",    "day",   False),
    ("safety.lti_count",            "integer",    "",      False),
    ("safety.near_miss_count",      "integer",    "",      False),
    ("safety.report_type",          "text",       "",      False),

    # ── Equipment ─────────────────────────────────────────────
    ("equipment.equipment_name",    "text",       "",      False),
    ("equipment.equipment_type",    "text",       "",      False),
    ("equipment.serial_number",     "text",       "",      False),
    ("equipment.hours_worked",      "number",     "hr",    False),
    ("equipment.status",            "text",       "",      False),

    # ── Logistics ─────────────────────────────────────────────
    ("logistics.company_name",      "text",       "",      False),
    ("logistics.position",          "text",       "",      False),
    ("logistics.personnel_count",   "integer",    "",      False),
    ("fuel_water.fuel_consumed",    "volume",     "bbl",   False),
    ("fuel_water.fuel_stock",       "volume",     "bbl",   False),
    ("fuel_water.water_consumed",   "volume",     "bbl",   False),
    ("fuel_water.water_stock",      "volume",     "bbl",   False),

    # ── Services ──────────────────────────────────────────────
    ("service.company_name",        "text",       "",      False),
    ("service.service_type",        "text",       "",      False),
    ("service.personnel_count",     "integer",    "",      False),

    # ── Cost ──────────────────────────────────────────────────
    ("cost.description",            "text",       "",      False),
    ("cost.amount",                 "currency",   "",      False),
    ("cost.category",               "text",       "",      False),
    ("cost.planned_cost",           "currency",   "",      False),
    ("cost.actual_cost",            "currency",   "",      False),

    # ── NPT ───────────────────────────────────────────────────
    ("npt.npt_category",            "text",       "",      False),
    ("npt.npt_code",                "text",       "",      False),
    ("npt.duration_hours",          "number",     "hr",    False),
    ("npt.responsible_party",       "text",       "",      False),
    ("npt.cost_impact",             "currency",   "",      False),
]
# fmt: on

FIELD_SPECS = {
    path: FieldSpec(path, quantity, unit, critical)
    for path, quantity, unit, critical in _FIELD_TUPLES
}
CANONICAL_FIELDS = frozenset(FIELD_SPECS)


def get_critical_fields() -> frozenset:
    """Return the set of field paths that are marked critical."""
    return frozenset(path for path, spec in FIELD_SPECS.items() if spec.critical)


def get_fields_by_quantity(quantity: str) -> list:
    """Return field paths matching a given quantity type."""
    return [path for path, spec in FIELD_SPECS.items() if spec.quantity == quantity]


def get_field_spec(path: str) -> FieldSpec:
    """Get the FieldSpec for a canonical field path, or None if not found."""
    return FIELD_SPECS.get(path)
