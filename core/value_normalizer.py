"""Single deterministic value-normalization boundary for imports.

The importers deliberately keep the source token separate from the normalized
value.  A failed conversion is not converted to zero and is not silently
coerced by a database driver: callers receive ``ok=False`` and can retain the
original token with its source location in the review/lineage record.

This module has no Qt, database, pandas, or MinerU dependency so every import
route can use the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any, Optional


_MISSING = frozenset({"", "--", "---", "n/a", "na", "none", "null", "nil", "nan", "tbd", "tba", "n.c", "nc"})
_NUMERIC_TYPES = frozenset({
    "integer", "number", "float", "decimal", "length", "density", "pressure",
    "force", "rpm", "torque", "rate", "flow_rate", "volume", "viscosity",
    "temperature", "angle", "dls", "area", "stress", "currency",
})
_UNIT_SUFFIXES = frozenset({
    "m", "ft", "in", "inch", "inches", "mm", "cm", "km", "mi",
    "ppg", "sg", "pcf", "lb/ft3", "kg/m3", "kg/m^3", "psi", "bar", "kpa", "mpa", "kpsi",
    "klb", "klbf", "lbf", "n", "kn", "rpm", "gpm", "lpm", "l/min", "m3/hr", "m3/h",
    "bbl/hr", "bbl/min", "spm", "bbl", "m3", "gal", "cc", "cp", "cps", "sec", "s",
    "hr", "hrs", "h", "min", "day", "days", "deg", "°", "rad", "sqm", "m2", "m²",
    "in2", "in²", "ftlb", "ft-lb", "n-m", "nm", "kn-m", "klbf-ft", "%", "c", "f", "°c", "°f",
})

# Numeric literals accepted after an optional engineering unit suffix.  The
# suffix is only accepted from the explicit set above; arbitrary text such as
# "Drilling Data" therefore cannot reach a Float column.
_NUMBER = r"[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_NUMERIC_WITH_SUFFIX = re.compile(
    rf"^({_NUMBER})\s*([A-Za-z°²%/_-]+)?\s*$",
    re.IGNORECASE,
)
_MIXED_FRACTION = re.compile(r"^(\d+)\s*-\s*(\d+)\s*/\s*(\d+)\s*(?:in(?:ch(?:es)?)?|\")?$", re.IGNORECASE)
_FRACTION = re.compile(r"^(\d+)\s*/\s*(\d+)\s*(?:in(?:ch(?:es)?)?|\")?$", re.IGNORECASE)


@dataclass(frozen=True)
class NormalizationResult:
    original_value: Any
    value: Any = None
    expected_type: str = ""
    source_unit: Optional[str] = None
    normalized_unit: Optional[str] = None
    ok: bool = False
    missing: bool = False
    error: Optional[str] = None

    @property
    def needs_review(self) -> bool:
        return not self.ok and not self.missing


class ValueNormalizer:
    """Typed, loss-averse normalization shared by Excel and document imports."""

    EMPTY_MARKERS = _MISSING

    @classmethod
    def is_missing(cls, value: Any) -> bool:
        if value is None:
            return True
        return str(value).strip().lower() in cls.EMPTY_MARKERS

    # Backward-compatible spelling used by the legacy Smart Template dialog.
    is_empty = is_missing

    @classmethod
    def normalize(
        cls,
        value: Any,
        expected_type: str = "string",
        *,
        unit: Optional[str] = None,
        normalized_unit: Optional[str] = None,
        valid_range: Optional[tuple[float, float]] = None,
    ) -> NormalizationResult:
        expected = (expected_type or "string").strip().lower()
        if cls.is_missing(value):
            return NormalizationResult(value, None, expected, unit, normalized_unit, ok=True, missing=True)

        try:
            if expected in _NUMERIC_TYPES:
                parsed = cls._number(value, expected)
                if parsed is None:
                    return NormalizationResult(value, None, expected, unit, normalized_unit, error="not a safe numeric literal")
                if valid_range and not (valid_range[0] <= float(parsed) <= valid_range[1]):
                    return NormalizationResult(value, None, expected, unit, normalized_unit, error="outside allowed range")
                if isinstance(parsed, float) and (math.isnan(parsed) or math.isinf(parsed)):
                    return NormalizationResult(value, None, expected, unit, normalized_unit, error="non-finite number")
                return NormalizationResult(value, parsed, expected, unit, normalized_unit, ok=True)

            if expected in {"date"}:
                parsed = cls.to_date(value)
            elif expected in {"time"}:
                parsed = cls.to_time(value)
            elif expected in {"datetime", "timestamp"}:
                parsed = cls.to_datetime(value)
            elif expected in {"duration", "timedelta"}:
                parsed = cls.to_duration(value)
            elif expected in {"boolean", "bool"}:
                parsed = cls.to_bool(value)
            elif expected in {"string", "text", "code", "enum", "quantity"}:
                parsed = cls.to_str(value)
            else:
                parsed = cls.to_str(value)

            if parsed is None:
                return NormalizationResult(value, None, expected, unit, normalized_unit, error=f"invalid {expected}")
            return NormalizationResult(value, parsed, expected, unit, normalized_unit, ok=True)
        except (TypeError, ValueError, OverflowError, InvalidOperation) as exc:
            return NormalizationResult(value, None, expected, unit, normalized_unit, error=str(exc))

    @classmethod
    def _number(cls, value: Any, expected: str) -> Optional[int | float | Decimal]:
        if isinstance(value, bool):
            return None
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, int):
            result = value
        elif isinstance(value, float):
            return value if math.isfinite(value) else None
        else:
            text = str(value).strip().replace("−", "-").replace("–", "-")
            mixed = _MIXED_FRACTION.fullmatch(text)
            if mixed:
                numerator, whole, denominator = int(mixed.group(2)), int(mixed.group(1)), int(mixed.group(3))
                if denominator == 0:
                    return None
                result = whole + numerator / denominator
            else:
                fraction = _FRACTION.fullmatch(text)
                if fraction:
                    denominator = int(fraction.group(2))
                    if denominator == 0:
                        return None
                    result = int(fraction.group(1)) / denominator
                else:
                    match = _NUMERIC_WITH_SUFFIX.fullmatch(text)
                    if not match:
                        return None
                    suffix = (match.group(2) or "").strip().lower()
                    if suffix and suffix not in _UNIT_SUFFIXES and not (suffix.endswith("k") and suffix[:-1] == ""):
                        # K is handled below; every other suffix must be
                        # explicitly known.  Do not strip arbitrary words.
                        if suffix != "k":
                            return None
                    result = float(match.group(1).replace(",", ""))
                    if suffix == "k":
                        result *= 1000.0

        if expected == "integer":
            number = float(result)
            return int(number) if math.isfinite(number) and number.is_integer() else None
        if expected == "decimal":
            return Decimal(str(result))
        return float(result)

    @classmethod
    def to_float(cls, value: Any, valid_range=None) -> Optional[float]:
        result = cls.normalize(value, "number", valid_range=valid_range)
        # Missing values are represented as ok=True/missing=True so callers
        # can distinguish NULL from malformed input.  They still have no
        # numeric payload and must never reach float(None).
        return float(result.value) if result.ok and result.value is not None else None

    @classmethod
    def to_int(cls, value: Any) -> Optional[int]:
        result = cls.normalize(value, "integer")
        # Do not turn a missing nozzle/count into zero and never call
        # int(None).  The database boundary will persist this as NULL.
        return int(result.value) if result.ok and result.value is not None else None

    @classmethod
    def to_decimal(cls, value: Any) -> Optional[Decimal]:
        result = cls.normalize(value, "decimal")
        return result.value if result.ok else None

    @classmethod
    def to_str(cls, value: Any) -> Optional[str]:
        if cls.is_missing(value):
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def to_date(cls, value: Any) -> Optional[date]:
        if cls.is_missing(value):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        for fmt in (
            "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
            "%d-%b-%Y", "%d-%B-%Y", "%d.%m.%Y", "%Y.%m.%d", "%d %b %Y", "%d %B %Y",
            "%b %d %Y", "%B %d %Y",
            "%b %d, %Y", "%B %d, %Y",
        ):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def to_time(cls, value: Any) -> Optional[time]:
        if cls.is_missing(value):
            return None
        if isinstance(value, datetime):
            return value.time()
        if isinstance(value, time):
            return value
        if isinstance(value, timedelta):
            if value.total_seconds() < 0 or value.total_seconds() > 86400:
                return None
            total = int(value.total_seconds()) % 86400
            return time(total // 3600, (total % 3600) // 60, total % 60)
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            number = float(value)
            if 0 <= number < 1:
                total = int(number * 86400)
                return time(total // 3600, (total % 3600) // 60)
            if 0 <= number <= 24 and number.is_integer():
                hour = int(number)
                return time(0, 0) if hour == 24 else time(hour, 0)
        text = str(value).strip()
        match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
        if match:
            hour, minute, second = map(int, (match.group(1), match.group(2), match.group(3) or 0))
            if hour == 24 and minute == 0 and second == 0:
                return time(0, 0)
            if 0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60:
                return time(hour, minute, second)
            return None
        return None

    @classmethod
    def to_datetime(cls, value: Any) -> Optional[datetime]:
        if cls.is_missing(value):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time())
        text = str(value).strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    @classmethod
    def to_duration(cls, value: Any) -> Optional[timedelta]:
        if cls.is_missing(value):
            return None
        if isinstance(value, timedelta):
            return value if value.total_seconds() >= 0 else None
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            return timedelta(hours=float(value)) if math.isfinite(float(value)) and float(value) >= 0 else None
        text = str(value).strip()
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours?)", text, re.IGNORECASE)
        if match:
            return timedelta(hours=float(match.group(1)))
        match = re.fullmatch(r"(\d{1,3}):(\d{2})(?::(\d{2}))?", text)
        if match:
            hours, minutes, seconds = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
            if minutes < 60 and seconds < 60:
                return timedelta(hours=hours, minutes=minutes, seconds=seconds)
        return None

    @classmethod
    def to_bool(cls, value: Any) -> Optional[bool]:
        if cls.is_missing(value):
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "yes", "y", "1", "on"}:
            return True
        if text in {"false", "no", "n", "0", "off"}:
            return False
        return None

    @classmethod
    def convert(cls, value: Any, data_type: str, valid_range=None):
        mapping = {"float": "number", "int": "integer", "text": "text"}
        expected = mapping.get(data_type, data_type)
        result = cls.normalize(value, expected, valid_range=valid_range)
        return result.value if result.ok else None

    @classmethod
    def combine_date_parts(cls, parts: list[Any]) -> Optional[date]:
        """Combine explicit year/month/day tokens without inventing a day."""
        values = [str(part).strip() for part in parts if part is not None and str(part).strip()]
        if len(values) == 1:
            return cls.to_date(values[0])
        month_map = {name.lower(): number for number, name in enumerate(
            ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
        ) if name}
        year = month = day = None
        for token in values:
            lowered = token.lower().strip(".")
            if lowered in month_map:
                month = month_map[lowered]
            elif lowered[:3] in {name[:3] for name in month_map}:
                month = next(number for name, number in month_map.items() if name[:3] == lowered[:3])
            elif re.fullmatch(r"\d{4}", token):
                year = int(token)
            elif re.fullmatch(r"\d{1,2}", token):
                number = int(token)
                if month is None and 1 <= number <= 12:
                    month = number
                elif day is None and 1 <= number <= 31:
                    day = number
        if year is None or month is None or day is None:
            return None
        try:
            return date(year, month, day)
        except ValueError:
            return None


def normalize_for_field(value: Any, field_spec: Any) -> NormalizationResult:
    """Normalize using a canonical ``FieldSpec`` without importing its module."""
    expected = getattr(field_spec, "quantity", None) or "string"
    return ValueNormalizer.normalize(
        value,
        expected,
        unit=getattr(field_spec, "unit", None),
        normalized_unit=getattr(field_spec, "unit", None),
        # Engineering bounds are validated after source-unit context is
        # resolved.  Applying a ppg bound to a raw PCF token would discard a
        # valid source value before UnitManager can perform the explicit
        # conversion.
        valid_range=None,
    )


__all__ = ["NormalizationResult", "ValueNormalizer", "normalize_for_field"]
