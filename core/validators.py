# core/validators.py
"""
Data Validation Rules
"""
import logging
from datetime import date, datetime
from typing import Dict, List

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
        """Merge another validation result without losing field context."""
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
            r.add_error("name", "Well name is required")
        # Code is optional in both the ORM and the import format.
        if data.get("code") is not None and not isinstance(data.get("code"), str):
            r.add_error("code", "Must be text")
        if not data.get("well_type"):
            r.add_error("well_type", "Well type is required")

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
        return r


class DailyReportValidator:
    @staticmethod
    def validate(data: dict) -> ValidationResult:
        r = ValidationResult()
        if not data.get("well_id"):
            r.add_error("well_id", "Well is required")
        if not data.get("section_id"):
            r.add_error("section_id", "Section is required")
        if not data.get("report_date"):
            r.add_error("report_date", "Date is required")

        d0 = data.get("depth_0000") or 0
        d6 = data.get("depth_0600") or 0
        d24 = data.get("depth_2400") or 0

        try:
            d0, d6, d24 = float(d0), float(d6), float(d24)
        except (ValueError, TypeError):
            r.add_error("depth", "Depth values must be numbers")
            return r

        if d24 < d0:
            r.add_warning("depth", f"Depth@24:00 ({d24}) < Depth@00:00 ({d0})")
        if d0 < 0 or d6 < 0 or d24 < 0:
            r.add_error("depth", "Depth cannot be negative")
        if d24 > 15000:
            r.add_warning("depth", "Depth > 15000m - verify")
        return r


class MudValidator:
    @staticmethod
    def validate(data: dict) -> ValidationResult:
        r = ValidationResult()
        ranges = {
            "mw": (30, 200, "pcf"),
            "pv": (0, 150, "cp"),
            "yp": (0, 150, "lb/100ft²"),
            "ph": (0, 14, ""),
            "temperature": (0, 250, "°C"),
            "fl": (0, 100, "cc/30min"),
        }
        for field, (lo, hi, unit) in ranges.items():
            val = data.get(field)
            if val is not None:
                try:
                    v = float(val)
                    if v < lo or v > hi:
                        r.add_warning(field, f"Value {v} outside range ({lo}-{hi} {unit})")
                except (ValueError, TypeError):
                    r.add_error(field, "Must be a number")

        try:
            s = float(data.get("solid_percent") or 0)
            o = float(data.get("oil_percent") or 0)
            w = float(data.get("water_percent") or 0)
        except (ValueError, TypeError):
            r.add_error("composition", "Solid, oil and water percentages must be numbers")
            return r
        total = s + o + w
        if total > 0 and abs(total - 100) > 5:
            r.add_warning("solids", f"Solids+Oil+Water = {total:.1f}% (expected ~100%)")
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
            ("wob_max", 0, 100), ("rpm_max", 0, 300),
            ("torque_max", 0, 100), ("pump_pressure_max", 0, 8000),
        ]:
            val = data.get(field)
            if val is not None:
                try:
                    v = float(val)
                    if v < lo or v > hi:
                        r.add_warning(field, f"Value {v} outside range ({lo}-{hi})")
                except (ValueError, TypeError):
                    pass
        return r


class ImportValidator:
    """Validate tabular import rows before they reach the database."""
    @staticmethod
    def validate_rows(rows, required_fields=()):
        result = ValidationResult()
        for index, row in enumerate(rows or [], start=2):
            if not isinstance(row, dict):
                result.add_error(str(index), "Row must be an object")
                continue
            for field in required_fields:
                if row.get(field) in (None, ""):
                    result.add_error(f"row {index}.{field}", "Required value is missing")
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