"""Import quality, row-level validation and duplicate detection.

This module is intentionally UI/database agnostic so the same rules can be
used by Excel preview, batch import and automated tests.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Iterable


@dataclass
class ImportIssue:
    sheet: str
    row: int
    level: str  # error / warning
    message: str
    field: str = ""
    value: Any = None


@dataclass
class ImportReport:
    total: int = 0
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def errors(self):
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.level == "warning"]

    @property
    def success(self):
        return self.failed == 0 and not self.errors

    def error(self, sheet, row, message, field="", value=None):
        self.issues.append(ImportIssue(sheet, row, "error", message, field, value))
        self.failed += 1

    def warning(self, sheet, row, message, field="", value=None):
        self.issues.append(ImportIssue(sheet, row, "warning", message, field, value))

    def as_dict(self):
        return {
            "total": self.total, "imported": self.imported,
            "updated": self.updated, "skipped": self.skipped,
            "failed": self.failed, "errors": len(self.errors),
            "warnings": len(self.warnings),
            "issues": [i.__dict__ for i in self.issues],
        }

    def summary(self):
        return (f"Total: {self.total} | Imported: {self.imported} | "
                f"Updated: {self.updated} | Skipped: {self.skipped} | "
                f"Failed: {self.failed} | Warnings: {len(self.warnings)}")


class ImportValidator:
    """Conservative validation for normalized import rows."""
    NUMERIC_FIELDS = {
        "depth_0000", "depth_0600", "depth_2400", "depth_in", "depth_out",
        "md", "inc", "azi", "tvd", "mw", "pv", "yp", "ph",
        "duration", "wob", "rpm", "torque", "pressure", "solid_percent",
    }
    REQUIRED_BY_TYPE = {
        "daily_report": ("report_date",),
        "survey": ("md",),
        "time_log": ("time_from", "time_to"),
        "well": ("name",),
    }

    @classmethod
    def validate_rows(cls, rows: Iterable[dict], record_type="", sheet="Import"):
        report = ImportReport()
        required = cls.REQUIRED_BY_TYPE.get(record_type, ())
        for row_number, row in enumerate(rows or (), start=2):
            report.total += 1
            if not isinstance(row, dict):
                report.error(sheet, row_number, "Row must be an object")
                continue
            for field in required:
                if row.get(field) in (None, ""):
                    report.error(sheet, row_number, "Required value is missing", field)
            for field in cls.NUMERIC_FIELDS:
                value = row.get(field)
                if value in (None, ""):
                    continue
                try:
                    float(value)
                except (TypeError, ValueError):
                    report.error(sheet, row_number, "Must be numeric", field, value)
            if "depth_in" in row and "depth_out" in row:
                try:
                    if float(row["depth_out"]) < float(row["depth_in"]):
                        report.error(sheet, row_number, "Depth out must be >= depth in", "depth_out")
                except (TypeError, ValueError):
                    pass
        return report


def row_key(record_type: str, row: dict):
    """Stable natural key used to make repeated imports idempotent."""
    keys = {
        "survey": ("well_id", "report_id", "md"),
        "time_log": ("report_id", "time_from", "time_to"),
        "daily_report": ("well_id", "section_id", "report_date"),
        "equipment": ("well_id", "report_id", "equipment_type", "equipment_id", "equipment_name"),
        "service": ("well_id", "report_id", "company_name", "service_type"),
    }.get(record_type, ("id",))
    values = tuple(row.get(k) for k in keys)
    return (record_type,) + values if any(v not in (None, "") for v in values) else None


def find_duplicates(rows: Iterable[dict], record_type: str):
    """Return duplicate row indexes (zero-based) within an import batch."""
    seen, duplicates = set(), []
    for index, row in enumerate(rows or ()):
        key = row_key(record_type, row)
        if key is not None and key in seen:
            duplicates.append(index)
        elif key is not None:
            seen.add(key)
    return duplicates
