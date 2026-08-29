"""Import quality, review decisions and duplicate detection.

This module is UI/database agnostic so Smart Import, Profile Import and batch
imports use exactly the same acceptance rules.

P0 Requirements Implemented:
- 24:00 with day_offset
- Time overlap detection
- Gap detection
- Duration validation
- Total must equal 24 hours
- Midnight crossing
- Continuation rows
- Duplicate time range
- Professional Review Matrix: File, Sheet/Page, Detected Table, Source Cell, Original Value, Normalized Value, Unit, Target Field, Confidence, Decision
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Dict, Tuple, Optional
from datetime import time, datetime, date
import re


def _safe_float(value) -> Optional[float]:
    """Convert value to float safely. Returns None for non-numeric strings like 'hrs', 'month'."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ImportIssue:
    sheet: str
    row: int
    level: str
    message: str
    field: str = ""
    value: Any = None


@dataclass
class ReviewItem:
    """Professional Review Matrix item as per spec."""
    file: str = ""  # File Name
    sheet: str = ""  # Sheet/Page
    detected_table: str = ""  # Detected Table
    source_cell: str = ""  # Source Cell (e.g. B12)
    original_value: Any = None  # Original Value
    normalized_value: Any = None  # Normalized Value
    unit: str = ""  # Unit
    target_field: str = ""  # Target Field
    canonical_field: str = ""  # alias for backward compat
    confidence: float = 0.0  # Confidence
    decision: str = "REVIEW"  # Decision: ACCEPT / REVIEW / REJECT / CONFIRMED
    transform: str = ""  # Edit Mapping / Edit Value / Edit Unit etc.
    # backward compat fields
    row: int = 0
    column: str = ""
    source_value: Any = None

    def __post_init__(self):
        # Sync legacy fields
        if self.canonical_field and not self.target_field:
            self.target_field = self.canonical_field
        if not self.canonical_field and self.target_field:
            self.canonical_field = self.target_field
        if self.source_value is None and self.original_value is not None:
            self.source_value = self.original_value
        if self.original_value is None and self.source_value is not None:
            self.original_value = self.source_value


class ImportReviewMatrix:
    """Complete Review Matrix before DB save."""

    def __init__(self):
        self.items: List[ReviewItem] = []

    def add(self, **kwargs):
        # Handle legacy calls: canonical_field, source_value, etc.
        if "canonical_field" in kwargs and "target_field" not in kwargs:
            kwargs["target_field"] = kwargs["canonical_field"]
        if "source_value" in kwargs and "original_value" not in kwargs:
            kwargs["original_value"] = kwargs["source_value"]
        # Build source_cell from row/column if not provided
        if not kwargs.get("source_cell") and kwargs.get("row"):
            col = kwargs.get("column", "")
            if isinstance(col, int):
                # Convert to letter
                try:
                    from openpyxl.utils import get_column_letter
                    col_letter = get_column_letter(col)
                except Exception:
                    col_letter = str(col)
            else:
                col_letter = str(col) if col else ""
            kwargs["source_cell"] = f"{col_letter}{kwargs.get('row','')}"
        item = ReviewItem(**kwargs)
        self.items.append(item)
        return item

    def as_rows(self):
        return [item.__dict__.copy() for item in self.items]

    def filter_by_decision(self, decision: str):
        return [i for i in self.items if i.decision == decision]

    def high_confidence(self):
        return [i for i in self.items if i.confidence >= 0.95]

    def medium_confidence(self):
        return [i for i in self.items if 0.70 <= i.confidence < 0.95]

    def low_confidence(self):
        return [i for i in self.items if i.confidence < 0.70]

    def accept_all_high(self):
        for item in self.high_confidence():
            item.decision = "ACCEPT"

    def reject_low(self):
        for item in self.low_confidence():
            item.decision = "REJECT"


@dataclass
class ImportReport:
    total: int = 0
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    issues: List[ImportIssue] = field(default_factory=list)
    review: ImportReviewMatrix = field(default_factory=ImportReviewMatrix)
    _failed_rows: set = field(default_factory=set, repr=False)

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
        key = (sheet, row)
        if key not in self._failed_rows:
            self._failed_rows.add(key)
            self.failed += 1

    def warning(self, sheet, row, message, field="", value=None):
        self.issues.append(ImportIssue(sheet, row, "warning", message, field, value))

    def add_review(self, **kwargs):
        return self.review.add(**kwargs)

    def as_dict(self):
        return {
            "total": self.total,
            "imported": self.imported,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "issues": [i.__dict__ for i in self.issues],
            "review": self.review.as_rows(),
        }

    def summary(self):
        return (
            f"Total: {self.total} | Imported: {self.imported} | "
            f"Updated: {self.updated} | Skipped: {self.skipped} | "
            f"Failed: {self.failed} | Warnings: {len(self.warnings)}"
        )


class TimeLogValidator:
    """Professional 24h Time Log validation as per spec.

    Checks:
    - 24:00 with day_offset
    - Time overlap detection
    - Gap detection
    - Duration validation (duration must match From/To)
    - Total must equal 24 hours
    - Midnight crossing
    - Continuation rows
    - Duplicate time range
    """

    @staticmethod
    def _to_minutes(t) -> Optional[int]:
        """Convert time to minutes from 00:00, handling 24:00 as 1440."""
        if t is None:
            return None
        if isinstance(t, str):
            s = t.strip()
            if s == "24:00":
                return 24 * 60
            m = re.match(r"^(\d{1,2}):(\d{2})", s)
            if m:
                h, mi = int(m.group(1)), int(m.group(2))
                if h == 24:
                    return 24 * 60
                return h * 60 + mi
            return None
        if isinstance(t, time):
            # Python time cannot be 24:00, treat 00:00 as potential 24:00 if needed via flag
            return t.hour * 60 + t.minute
        if hasattr(t, "hour") and hasattr(t, "minute"):
            # DrillTime or similar
            h = getattr(t, "hour", 0)
            m = getattr(t, "minute", 0)
            is_24 = getattr(t, "is_midnight_24", False) or getattr(t, "_is_2400", False)
            if is_24 or h == 24:
                return 24 * 60
            return h * 60 + m
        return None

    @staticmethod
    def _duration_from_times(from_m, to_m) -> Optional[float]:
        """Calculate duration in hours handling midnight crossing."""
        if from_m is None or to_m is None:
            return None
        diff = to_m - from_m
        if diff < 0:
            diff += 24 * 60  # midnight crossing
        return diff / 60.0

    @classmethod
    def validate_logs(cls, logs: List[Dict], sheet="TimeLog", tolerance_hours=0.5) -> ImportReport:
        """Validate a list of time logs (dicts with time_from, time_to, duration).

        Returns ImportReport with errors/warnings.
        """
        report = ImportReport()
        report.total = len(logs)

        if not logs:
            report.warning(sheet, 0, "No time logs provided", "time_log")
            return report

        # Normalize to minutes
        parsed = []
        for idx, log in enumerate(logs):
            if not isinstance(log, dict):
                report.error(sheet, idx + 2, "Log must be dict", "time_log")
                continue

            tf = log.get("time_from")
            tt = log.get("time_to")
            dur = log.get("duration")

            from_m = cls._to_minutes(tf)
            to_m = cls._to_minutes(tt)

            # Special handling for 24:00 as string
            if isinstance(tf, str) and tf.strip() == "24:00":
                from_m = 24 * 60
            if isinstance(tt, str) and tt.strip() == "24:00":
                to_m = 24 * 60

            # If duration missing, try to compute
            computed_dur = None
            if from_m is not None and to_m is not None:
                computed_dur = cls._duration_from_times(from_m, to_m)

            # Duration validation
            if dur is not None:
                try:
                    dur_f = float(dur)
                    if dur_f < 0:
                        report.error(sheet, idx + 2, "Duration cannot be negative", "duration", dur)
                    if dur_f > 24:
                        report.error(sheet, idx + 2, "Duration > 24h invalid", "duration", dur)
                    # Check if duration matches From/To within tolerance
                    if computed_dur is not None and abs(dur_f - computed_dur) > 0.25:  # 15 min tolerance
                        report.warning(
                            sheet,
                            idx + 2,
                            f"Duration {dur_f:.2f}h doesn't match From/To ({computed_dur:.2f}h)",
                            "duration",
                            dur,
                        )
                except (TypeError, ValueError):
                    report.error(sheet, idx + 2, "Duration must be numeric", "duration", dur)

            # Code validation
            if not log.get("main_code") and not log.get("activity_description"):
                report.warning(sheet, idx + 2, "No code or description", "main_code")

            # NPT contractor validation
            if log.get("is_npt") and not log.get("contractor") and not log.get("npt_category"):
                report.warning(sheet, idx + 2, "NPT without contractor/category", "contractor")

            parsed.append(
                {
                    "index": idx,
                    "from_m": from_m,
                    "to_m": to_m,
                    "duration": _safe_float(dur) if dur not in (None, "") else computed_dur,
                    "computed_duration": computed_dur,
                    "log": log,
                }
            )

        # Sort by from time for overlap/gap detection
        valid_parsed = [p for p in parsed if p["from_m"] is not None and p["to_m"] is not None]
        valid_parsed.sort(key=lambda x: x["from_m"])

        # Overlap detection
        for i in range(1, len(valid_parsed)):
            prev = valid_parsed[i - 1]
            curr = valid_parsed[i]
            # If prev ends after curr starts -> overlap
            # Handle midnight crossing: if prev to_m < from_m, it crossed midnight
            prev_to = prev["to_m"]
            curr_from = curr["from_m"]

            # Simple overlap check (without crossing)
            if prev_to > curr_from and not (prev["from_m"] > prev["to_m"]):
                report.error(
                    sheet,
                    curr["index"] + 2,
                    f"Time overlap with previous: {prev['log'].get('time_from')}–{prev['log'].get('time_to')} overlaps {curr['log'].get('time_from')}–{curr['log'].get('time_to')}",
                    "time_range",
                )

        # Gap detection
        for i in range(1, len(valid_parsed)):
            prev = valid_parsed[i - 1]
            curr = valid_parsed[i]
            gap_minutes = curr["from_m"] - prev["to_m"]
            if gap_minutes > 5:  # more than 5 minutes gap
                report.warning(
                    sheet,
                    curr["index"] + 2,
                    f"Gap detected: {gap_minutes} minutes between {prev['log'].get('time_to')} and {curr['log'].get('time_from')}",
                    "time_range",
                )
            if gap_minutes < -5 and gap_minutes > -24 * 60 + 5:
                # Negative gap already reported as overlap
                pass

        # Total must equal 24 hours
        total_hours = sum(p["duration"] or 0 for p in parsed if p["duration"] is not None)
        if total_hours > 0:
            if abs(total_hours - 24.0) > tolerance_hours:
                report.warning(
                    sheet,
                    0,
                    f"Total time {total_hours:.2f}h != 24h (tolerance {tolerance_hours}h). Gap or overlap likely.",
                    "total_hours",
                    total_hours,
                )
                # Add review item for total
                report.add_review(
                    file="",
                    sheet=sheet,
                    detected_table="Time Log 24H",
                    source_cell="Total",
                    original_value=total_hours,
                    normalized_value=24.0,
                    unit="h",
                    target_field="time_log.total",
                    confidence=0.6,
                    decision="REVIEW",
                    transform="Total must equal 24h",
                )

        # Midnight crossing and 24:00 handling
        has_midnight_start = any(p["from_m"] == 0 for p in parsed)
        has_midnight_end = any(p["to_m"] == 24 * 60 or p["to_m"] == 0 for p in parsed)
        if not has_midnight_start:
            report.warning(sheet, 0, "No entry starting at 00:00 - daily coverage may be incomplete", "time_from")
        if not has_midnight_end:
            report.warning(sheet, 0, "No entry ending at 24:00 - daily coverage may be incomplete", "time_to")

        # Duplicate time range detection
        seen_ranges = set()
        for p in valid_parsed:
            key = (p["from_m"], p["to_m"])
            if key in seen_ranges:
                report.error(sheet, p["index"] + 2, f"Duplicate time range {p['log'].get('time_from')}–{p['log'].get('time_to')}", "time_range")
            else:
                seen_ranges.add(key)

        # Continuation rows: if description continues but no time, it's okay if previous exists
        # This is handled in import - here we just warn if time missing
        for p in parsed:
            if p["from_m"] is None or p["to_m"] is None:
                # Could be continuation row - check if log has only description
                log = p["log"]
                if log.get("activity_description") and not log.get("time_from"):
                    report.add_review(
                        sheet=sheet,
                        row=p["index"] + 2,
                        original_value=log.get("activity_description", "")[:50],
                        target_field="time_log.continuation",
                        confidence=0.8,
                        decision="REVIEW",
                        transform="Continuation row - will be merged",
                    )
                else:
                    report.warning(sheet, p["index"] + 2, "Missing time_from or time_to", "time_range")

        return report

    @classmethod
    def validate_and_sort(cls, logs: List[Dict]) -> Tuple[List[Dict], ImportReport]:
        """Sort logs by time and validate, returning sorted logs and report."""
        report = cls.validate_logs(logs)
        # Sort by from_m
        def sort_key(log):
            m = cls._to_minutes(log.get("time_from"))
            return m if m is not None else 9999

        sorted_logs = sorted(logs, key=sort_key)
        return sorted_logs, report


class ImportValidator:
    NUMERIC_FIELDS = {
        "depth_0000",
        "depth_0600",
        "depth_2400",
        "depth_in",
        "depth_out",
        "md",
        "inc",
        "azi",
        "tvd",
        "mw",
        "pv",
        "yp",
        "ph",
        "duration",
        "wob",
        "rpm",
        "torque",
        "pressure",
        "solid_percent",
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
                    report.add_review(
                        file="",
                        sheet=sheet,
                        detected_table=record_type,
                        source_cell=f"{field}:{row_number}",
                        original_value=row.get(field),
                        normalized_value=None,
                        target_field=f"{record_type}.{field}",
                        confidence=0.0,
                        decision="REJECT",
                        transform="Missing required",
                    )
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

        # For time_log type, run professional 24h validation
        if record_type == "time_log":
            time_report = TimeLogValidator.validate_logs(list(rows or []), sheet=sheet)
            # Merge issues
            report.issues.extend(time_report.issues)
            report.failed = max(report.failed, time_report.failed)
            # Merge review items
            for item in time_report.review.items:
                report.review.items.append(item)

        return report


def row_key(record_type: str, row: dict):
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
    seen, duplicates = set(), []
    for index, row in enumerate(rows or ()):
        key = row_key(record_type, row)
        if key is not None and key in seen:
            duplicates.append(index)
        elif key is not None:
            seen.add(key)
    return duplicates


def decision_for_confidence(confidence, critical=False):
    """Conservative decision policy for automatic import.

    Critical fields need 0.99 for ACCEPT, else 0.95.
    """
    confidence = float(confidence or 0)
    if critical:
        return "ACCEPT" if confidence >= 0.99 else "REVIEW" if confidence >= 0.85 else "REJECT"
    return "ACCEPT" if confidence >= 0.95 else "REVIEW" if confidence >= 0.70 else "REJECT"
