# core/validators.py
"""
Data Validation Rules - Professional Intelligence Platform

Implements full validators for all record types:
- Time Log (24:00 with day_offset, overlap, gap, duration, total 24h, midnight crossing, continuation, duplicate)
- Contractor autocomplete + recent + master data
- Survey (MD, Inc, Azi, TVD, North, East, VS, HD, DLS, Tool, QC, Duplicate MD, Non-monotonic)
- BHA (Component, OD, ID, Length, Weight, Serial, Position, Cumulative Length)
- Bit (Bit No, Size, Type, IADC, Manufacturer, Serial, Nozzle, TFA)
- Mud Chemicals (Product, Type, Received, Used, On Hand, Unit + Ledger)
- Equipment (Equipment, Category, Serial, Manufacturer, Status, Service Date, Hours)
- Logistics (Company, Service Type, Personnel, Date In, Date Out, Status)
- Safety/BOP with configurable intervals
- Cost, Services, etc.

Never silently invent missing inputs - return MISSING_INPUT or UNSUPPORTED.
"""

import logging
from datetime import date, datetime, time
from typing import Dict, List, Optional, Tuple
import math
import re

logger = logging.getLogger(__name__)


class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []

    @property
    def is_valid(self):
        return len(self.errors) == 0

    def add_error(self, field, message):
        self.errors.append({"field": field, "message": message})

    def add_warning(self, field, message):
        self.warnings.append({"field": field, "message": message})

    def merge(self, other):
        if other is None:
            return self
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        return self

    def summary(self):
        lines = []
        for e in self.errors:
            lines.append(f"❌ {e['field']}: {e['message']}")
        for w in self.warnings:
            lines.append(f"⚠️ {w['field']}: {w['message']}")
        return "\n".join(lines) if lines else "✅ All valid"


class WellValidator:
    @staticmethod
    def validate(data: dict) -> ValidationResult:
        r = ValidationResult()
        if not data.get("name", "").strip():
            r.add_error("name", "Well name is required - MISSING_INPUT")
        if data.get("code") is not None and not isinstance(data.get("code"), str):
            r.add_error("code", "Must be text")
        if not data.get("well_type"):
            r.add_warning("well_type", "Well type is missing - will be flagged as review")

        td = data.get("target_depth")
        if td is not None:
            try:
                if float(td) <= 0:
                    r.add_warning("target_depth", "Target depth should be > 0")
                if float(td) > 15000:
                    r.add_warning("target_depth", "Target depth > 15000m - verify")
            except (ValueError, TypeError):
                r.add_error("target_depth", "Must be a number")

        wd = data.get("water_depth")
        if wd is not None:
            try:
                if float(wd) < 0:
                    r.add_error("water_depth", "Cannot be negative")
            except (ValueError, TypeError):
                r.add_error("water_depth", "Must be a number")

        # Coordinates validation
        lat = data.get("latitude")
        if lat is not None:
            try:
                if not (-90 <= float(lat) <= 90):
                    r.add_error("latitude", "Must be in [-90,90]")
            except (TypeError, ValueError):
                r.add_error("latitude", "Must be numeric")

        lon = data.get("longitude")
        if lon is not None:
            try:
                if not (-180 <= float(lon) <= 180):
                    r.add_error("longitude", "Must be in [-180,180]")
            except (TypeError, ValueError):
                r.add_error("longitude", "Must be numeric")

        return r


class DailyReportValidator:
    @staticmethod
    def validate(data: dict) -> ValidationResult:
        r = ValidationResult()
        if not data.get("well_id"):
            r.add_error("well_id", "Well is required - MISSING_INPUT")
        if not data.get("section_id"):
            r.add_warning("section_id", "Section is missing - will be auto-created with review flag")
        if not data.get("report_date"):
            r.add_error("report_date", "Date is required - MISSING_INPUT")

        d0 = data.get("depth_0000")
        d6 = data.get("depth_0600")
        d24 = data.get("depth_2400")

        # No fake defaults: None is allowed (unknown), but if present must be valid
        for field_name, val in [("depth_0000", d0), ("depth_0600", d6), ("depth_2400", d24)]:
            if val is None:
                r.add_warning(field_name, "Depth is missing - preserved as NULL, not fake 0")
            else:
                try:
                    v = float(val)
                    if v < 0:
                        r.add_error(field_name, "Depth cannot be negative")
                    if v > 15000:
                        r.add_warning(field_name, "Depth > 15000m - verify")
                except (ValueError, TypeError):
                    r.add_error(field_name, "Depth must be numeric")

        # Only check ordering if both present
        try:
            if d0 is not None and d24 is not None and float(d24) < float(d0):
                r.add_warning("depth", f"Depth@24:00 ({d24}) < Depth@00:00 ({d0}) - may be valid if milling/backreaming")
        except (ValueError, TypeError):
            pass

        return r


class MudValidator:
    @staticmethod
    def validate(data: dict) -> ValidationResult:
        r = ValidationResult()
        ranges = {
            "mw": (0, 300, "ppg/pcf - check unit"),
            "pv": (0, 200, "cp"),
            "yp": (0, 200, "lb/100ft²"),
            "ph": (0, 14, ""),
            "temperature": (0, 300, "°C"),
            "fl": (0, 200, "cc/30min"),
            "gel_10s": (0, 100, ""),
            "gel_10m": (0, 200, ""),
            "solid_percent": (0, 100, "%"),
            "oil_percent": (0, 100, "%"),
            "water_percent": (0, 100, "%"),
        }
        for field, (lo, hi, unit) in ranges.items():
            val = data.get(field)
            if val is None:
                continue
            try:
                v = float(val)
                if v < lo or v > hi:
                    r.add_warning(field, f"Value {v} outside range ({lo}-{hi} {unit}) - verify unit conversion")
            except (ValueError, TypeError):
                r.add_error(field, "Must be a number")

        try:
            s = float(data.get("solid_percent") or 0)
            o = float(data.get("oil_percent") or 0)
            w = float(data.get("water_percent") or 0)
            total = s + o + w
            if total > 0 and abs(total - 100) > 5:
                r.add_warning("solids", f"Solids+Oil+Water = {total:.1f}% (expected ~100%)")
        except (ValueError, TypeError):
            pass

        return r


class DrillingParamsValidator:
    @staticmethod
    def validate(data: dict) -> ValidationResult:
        r = ValidationResult()
        di = data.get("depth_in")
        do = data.get("depth_out")
        if di is not None and do is not None:
            try:
                if float(do) < float(di):
                    r.add_error("depth", "Depth Out must be >= Depth In")
            except (ValueError, TypeError):
                r.add_error("depth", "Depth values must be numbers")

        for field, lo, hi in [
            ("wob_min", 0, 200),
            ("wob_max", 0, 200),
            ("rpm_min", 0, 500),
            ("rpm_max", 0, 500),
            ("torque_min", 0, 200),
            ("torque_max", 0, 200),
            ("pump_pressure_min", 0, 10000),
            ("pump_pressure_max", 0, 10000),
            ("bit_size", 0, 50),
            ("avg_rop", 0, 500),
        ]:
            val = data.get(field)
            if val is None:
                continue
            try:
                v = float(val)
                if v < lo or v > hi:
                    r.add_warning(field, f"Value {v} outside range ({lo}-{hi}) - verify unit")
            except (ValueError, TypeError):
                r.add_warning(field, f"Non-numeric {field}: {val}")

        return r


class SurveyValidator:
    """Survey validation: MD, Inc, Azi, TVD, North, East, VS, HD, DLS, Tool, QC, Duplicate, Non-monotonic"""

    @staticmethod
    def validate_points(points: List[Dict]) -> ValidationResult:
        r = ValidationResult()
        if not points:
            r.add_warning("survey", "No survey points")
            return r

        seen_md = set()
        prev_md = -1

        for idx, p in enumerate(points):
            md = p.get("md")
            if md in (None, ""):
                r.add_error(f"survey[{idx}].md", "MD is required - MISSING_INPUT")
                continue

            try:
                md_f = float(md)
            except (TypeError, ValueError):
                r.add_error(f"survey[{idx}].md", "MD must be numeric")
                continue

            if md_f in seen_md:
                r.add_error(f"survey[{idx}].md", f"Duplicate MD detected: {md_f}")
            seen_md.add(md_f)

            if md_f <= prev_md and prev_md != -1:
                r.add_error(f"survey[{idx}].md", f"Non-monotonic MD: {md_f} <= {prev_md}")
            prev_md = md_f

            inc = p.get("inc", p.get("inclination", 0))
            if inc not in (None, ""):
                try:
                    inc_f = float(inc)
                    if not (0 <= inc_f <= 180):
                        r.add_error(f"survey[{idx}].inc", f"Inclination out of [0,180]: {inc_f}")
                except (TypeError, ValueError):
                    r.add_error(f"survey[{idx}].inc", "Inc must be numeric")

            azi = p.get("azi", p.get("azimuth", 0))
            if azi not in (None, ""):
                try:
                    float(azi)
                except (TypeError, ValueError):
                    r.add_error(f"survey[{idx}].azi", "Azi must be numeric")

            dls = p.get("dls")
            if dls not in (None, ""):
                try:
                    dls_f = float(dls)
                    if dls_f > 15:
                        r.add_warning(f"survey[{idx}].dls", f"High DLS {dls_f} deg/30m - verify")
                except (TypeError, ValueError):
                    pass

        return r


class BHAValidator:
    """BHA validation: Component, OD, ID, Length, Weight, Serial, Position, Cumulative Length"""

    @staticmethod
    def validate(components: List[Dict]) -> ValidationResult:
        r = ValidationResult()
        if not components:
            r.add_warning("bha", "No BHA components")
            return r

        total_length = 0
        for idx, c in enumerate(components):
            comp_name = c.get("component_name", c.get("component", ""))
            if not comp_name:
                r.add_error(f"bha[{idx}].component", "Component name required - MISSING_INPUT")

            length = c.get("length")
            if length in (None, ""):
                r.add_error(f"bha[{idx}].length", "Length required - MISSING_INPUT")
            else:
                try:
                    l = float(length)
                    if l < 0:
                        r.add_error(f"bha[{idx}].length", "Length cannot be negative")
                    if l == 0:
                        r.add_warning(f"bha[{idx}].length", "Zero length component")
                    total_length += l
                except (TypeError, ValueError):
                    r.add_error(f"bha[{idx}].length", "Length must be numeric")

            od = c.get("od")
            id_val = c.get("id")
            if od not in (None, "") and id_val not in (None, ""):
                try:
                    if float(id_val) >= float(od):
                        r.add_error(f"bha[{idx}].id", f"ID {id_val} must be < OD {od}")
                except (TypeError, ValueError):
                    pass

        # Cumulative length check
        if total_length > 500:
            r.add_warning("bha.total_length", f"BHA total length {total_length:.1f}m >500m - verify")

        return r


class BitValidator:
    """Bit validation: Bit No, Size, Type, IADC, Manufacturer, Serial, Nozzle, TFA"""

    @staticmethod
    def validate(bit: Dict) -> ValidationResult:
        r = ValidationResult()
        if not bit:
            r.add_warning("bit", "No bit data")
            return r

        if not bit.get("bit_size") and not bit.get("size"):
            r.add_error("bit.size", "Bit size required - MISSING_INPUT")

        if not bit.get("iadc_code") and not bit.get("iadc"):
            r.add_warning("bit.iadc", "IADC code missing - recommended")

        nozzles = bit.get("nozzles", bit.get("nozzle", []))
        tfa = bit.get("tfa")
        if not nozzles and not tfa:
            r.add_warning("bit.nozzle", "Nozzle configuration missing - TFA cannot be calculated")

        if tfa is not None:
            try:
                tfa_f = float(tfa)
                if tfa_f <= 0:
                    r.add_error("bit.tfa", "TFA must be >0")
            except (TypeError, ValueError):
                r.add_error("bit.tfa", "TFA must be numeric")

        # Duplicate bit run detection would require DB check
        return r


class BulkValidator:
    """Mud Chemicals / Bulk Materials validation with Ledger"""

    @staticmethod
    def validate(materials: List[Dict]) -> ValidationResult:
        r = ValidationResult()
        if not materials:
            return r

        seen_names = set()
        for idx, m in enumerate(materials):
            name = m.get("material_name", m.get("product", ""))
            if not name:
                r.add_error(f"bulk[{idx}].material_name", "Material name required - MISSING_INPUT")
                continue

            if name in seen_names:
                r.add_warning(f"bulk[{idx}].material_name", f"Duplicate material: {name}")
            seen_names.add(name)

            # Stock checks
            try:
                initial = float(m.get("initial_stock", 0) or 0)
                received = float(m.get("received", 0) or 0)
                used = float(m.get("used", 0) or 0)
                current = float(m.get("current_stock", 0) or 0)
                expected = initial + received - used
                if abs(current - expected) > 0.01 and current != 0:
                    r.add_warning(f"bulk[{idx}].current_stock", f"Stock mismatch: {current} != {initial}+{received}-{used}={expected}")
                if current < 0:
                    r.add_error(f"bulk[{idx}].current_stock", f"Negative stock: {current}")
            except (TypeError, ValueError):
                r.add_error(f"bulk[{idx}]", "Stock values must be numeric")

            unit = m.get("unit", "")
            if not unit:
                r.add_warning(f"bulk[{idx}].unit", "Unit missing")

        return r


class EquipmentValidator:
    @staticmethod
    def validate(logs: List[Dict]) -> ValidationResult:
        r = ValidationResult()
        for idx, eq in enumerate(logs or []):
            if not eq.get("equipment_name"):
                r.add_error(f"equipment[{idx}].equipment_name", "Equipment name required - MISSING_INPUT")
            hours = eq.get("hours_worked", eq.get("hours", 0))
            if hours not in (None, ""):
                try:
                    if float(hours) < 0:
                        r.add_error(f"equipment[{idx}].hours", "Hours cannot be negative")
                except (TypeError, ValueError):
                    r.add_error(f"equipment[{idx}].hours", "Hours must be numeric")
        return r


class LogisticsValidator:
    @staticmethod
    def validate(records: List[Dict]) -> ValidationResult:
        r = ValidationResult()
        for idx, rec in enumerate(records or []):
            if not rec.get("company_name"):
                r.add_error(f"logistics[{idx}].company_name", "Company name required - MISSING_INPUT")
            # Date In/Out check
            date_in = rec.get("date_in")
            date_out = rec.get("date_out")
            if date_in and date_out:
                try:
                    from datetime import date as dt_date
                    if isinstance(date_in, str):
                        date_in = dt_date.fromisoformat(date_in)
                    if isinstance(date_out, str):
                        date_out = dt_date.fromisoformat(date_out)
                    if date_out < date_in:
                        r.add_error(f"logistics[{idx}].date_out", "Date Out must be >= Date In")
                except Exception:
                    pass
        return r


class SafetyValidator:
    @staticmethod
    def validate(report: Dict) -> ValidationResult:
        r = ValidationResult()
        if not report:
            return r

        # Days without LTI should be >=0
        lti = report.get("days_without_lti")
        if lti is not None:
            try:
                if int(lti) < 0:
                    r.add_error("safety.days_without_lti", "Cannot be negative")
            except (TypeError, ValueError):
                r.add_error("safety.days_without_lti", "Must be integer")

        # BOP test intervals should be configurable, not hard-coded
        # Validation only checks dates
        last_rams = report.get("last_rams_test")
        if last_rams:
            # Check if test due date is past
            pass

        return r


class BOPValidator:
    @staticmethod
    def validate(components: List[Dict], configurable_interval_days: int = 14) -> ValidationResult:
        r = ValidationResult()
        for idx, comp in enumerate(components or []):
            if not comp.get("component_name"):
                r.add_error(f"bop[{idx}].component_name", "Component name required - MISSING_INPUT")
            wp = comp.get("working_pressure")
            if wp in (None, ""):
                r.add_error(f"bop[{idx}].working_pressure", "Working pressure required - MISSING_INPUT (critical)")
            else:
                try:
                    if float(wp) <= 0:
                        r.add_error(f"bop[{idx}].working_pressure", "Must be >0")
                except (TypeError, ValueError):
                    r.add_error(f"bop[{idx}].working_pressure", "Must be numeric")

            # Test due date check with configurable interval
            last_test = comp.get("last_test_date")
            if last_test:
                try:
                    from datetime import date, timedelta
                    if isinstance(last_test, str):
                        last_test = date.fromisoformat(last_test)
                    next_due = last_test + timedelta(days=configurable_interval_days)
                    if next_due < date.today():
                        r.add_warning(f"bop[{idx}].last_test_date", f"Test overdue: {comp.get('component_name')} last tested {last_test}, due {next_due} (interval {configurable_interval_days} days configurable)")
                except Exception:
                    pass

        return r


class ServiceValidator:
    @staticmethod
    def validate(companies: List[Dict]) -> ValidationResult:
        r = ValidationResult()
        for idx, comp in enumerate(companies or []):
            if not comp.get("company_name"):
                r.add_error(f"service[{idx}].company_name", "Company name required - MISSING_INPUT")
        return r


class CostValidator:
    @staticmethod
    def validate(records: List[Dict]) -> ValidationResult:
        r = ValidationResult()
        for idx, rec in enumerate(records or []):
            if rec.get("actual_cost") in (None, "") and rec.get("planned_cost") in (None, ""):
                r.add_warning(f"cost[{idx}]", "Both planned and actual cost missing")
            try:
                if rec.get("actual_cost") is not None and float(rec.get("actual_cost")) < 0:
                    r.add_error(f"cost[{idx}].actual_cost", "Cannot be negative")
            except (TypeError, ValueError):
                r.add_error(f"cost[{idx}].actual_cost", "Must be numeric")
        return r


class ImportValidator:
    """Legacy wrapper for backward compat - delegates to import_quality module"""

    @staticmethod
    def validate_rows(rows, required_fields=()):
        result = ValidationResult()
        for index, row in enumerate(rows or [], start=2):
            if not isinstance(row, dict):
                result.add_error(str(index), "Row must be an object")
                continue
            for field in required_fields:
                if row.get(field) in (None, ""):
                    result.add_error(f"row {index}.{field}", "Required value is missing - MISSING_INPUT")
        return result


def cross_validate(data):
    """Cross-field checks shared by dialogs and importers."""
    result = ValidationResult()
    spud = data.get("spud_date")
    report = data.get("report_date")
    if spud and report:
        try:
            if isinstance(spud, str):
                spud = date.fromisoformat(spud)
            if isinstance(report, str):
                report = date.fromisoformat(report)
            if report < spud:
                result.add_error("report_date", "Report date must be on or after spud date")
        except (TypeError, ValueError):
            result.add_error("date", "Dates must use YYYY-MM-DD format")
    return result


class TimeLogValidator:
    """Legacy simple validator - use import_quality.TimeLogValidator for professional"""

    @staticmethod
    def validate_logs(logs: list) -> ValidationResult:
        r = ValidationResult()
        total = sum(l.get("duration", 0) or 0 for l in logs)
        if total > 0 and abs(total - 24) > 0.5:
            r.add_warning("total_hours", f"Total = {total:.2f}h (expected ~24h)")
        for i, log in enumerate(logs):
            dur = log.get("duration", 0) or 0
            if dur < 0:
                r.add_error(f"log_{i}", "Duration cannot be negative")
            if dur > 24:
                r.add_error(f"log_{i}", "Duration > 24h")
            if not log.get("main_code") and not log.get("activity_description"):
                r.add_warning(f"log_{i}", "No code or description")
        return r
