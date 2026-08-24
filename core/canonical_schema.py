"""Single canonical field registry shared by import, units, review and AI."""
from dataclasses import dataclass

@dataclass(frozen=True)
class FieldSpec:
    path: str
    quantity: str = "text"
    unit: str = ""
    critical: bool = False

FIELD_SPECS = {
    path: FieldSpec(path, quantity, unit, critical)
    for path, quantity, unit, critical in [
        ("well_info.name", "text", "", True), ("well_info.report_date", "date", "", True),
        ("daily_report.report_date", "date", "", True), ("daily_report.report_number", "integer", "", False),
        ("daily_report.depth_0000", "length", "m", False), ("daily_report.depth_0600", "length", "m", False),
        ("daily_report.depth_2400", "length", "m", True), ("mud_report.mw", "density", "ppg", True),
        ("mud_report.pv", "viscosity", "cp", False), ("mud_report.yp", "stress", "lb/100ft2", False),
        ("mud_report.ph", "number", "", False), ("mud_report.temperature", "temperature", "C", False),
        ("drilling_params.bit_no", "text", "", False), ("drilling_params.bit_size", "length", "in", True),
        ("drilling_params.bit_type", "text", "", False), ("drilling_params.depth_in", "length", "m", False),
        ("drilling_params.depth_out", "length", "m", False), ("drilling_params.avg_rop", "rate", "m/hr", False),
        ("time_log.main_code", "code", "", True), ("time_log.sub_code", "code", "", True),
        ("time_log.contractor", "text", "", False), ("survey.md", "length", "m", True),
        ("survey.inc", "angle", "deg", False), ("survey.azi", "angle", "deg", False),
        ("survey.tvd", "length", "m", False), ("bulk_material.material_name", "text", "", False),
        ("bulk_material.received", "volume", "", False), ("bulk_material.used", "volume", "", False),
        ("bulk_material.current_stock", "volume", "", False), ("bha.component_name", "text", "", False),
        ("bha.od", "length", "in", False), ("bha.length", "length", "m", False),
        ("downhole.equipment_name", "text", "", False), ("downhole.serial_number", "text", "", False),
        ("formation.name", "text", "", False), ("formation.md_top", "length", "m", False),
        ("casing.size", "length", "in", False), ("casing.depth_from", "length", "m", False),
        ("casing.depth_to", "length", "m", False), ("casing.grade", "text", "", False),
        ("cement.material", "text", "", False), ("cement.used", "volume", "", False),
        ("bop.component_name", "text", "", False), ("bop.working_pressure", "pressure", "psi", True),
        ("safety.days_without_lti", "integer", "day", False), ("equipment.equipment_name", "text", "", False),
        ("logistics.company_name", "text", "", False), ("service.company_name", "text", "", False),
        ("service.service_type", "text", "", False), ("cost.description", "text", "", False),
        ("cost.amount", "currency", "", False),
    ]
}
CANONICAL_FIELDS = frozenset(FIELD_SPECS)
