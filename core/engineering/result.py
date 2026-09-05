"""Canonical engineering result contract.

Every engine returns the same shape so UI, AI tools, export and tests
can consume results without per-engine adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import math


class EngineeringError(Exception):
    pass


class MissingInputError(EngineeringError):
    def __init__(self, field: str):
        super().__init__(f"MISSING_INPUT: {field}")
        self.field = field


class UnsupportedCalculationError(EngineeringError):
    def __init__(self, reason: str):
        super().__init__(f"UNSUPPORTED_CALCULATION: {reason}")
        self.reason = reason


@dataclass
class EngineeringResult:
    """ONE result contract for all engineering engines."""

    success: bool
    value: Any = None
    values: Dict[str, Any] = field(default_factory=dict)
    unit: str = ""
    formula: str = ""
    method: str = ""
    assumptions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validation_status: str = "ok"  # ok | warning | missing_input | unsupported | error
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    scope: str = "COMPLETE"  # COMPLETE | PARTIAL | SCREENING | NOT_IMPLEMENTED

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def ok(
    value: Any = None,
    *,
    values: Optional[Dict[str, Any]] = None,
    unit: str = "",
    formula: str = "",
    method: str = "",
    assumptions: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    scope: str = "COMPLETE",
) -> EngineeringResult:
    status = "warning" if warnings else "ok"
    return EngineeringResult(
        success=True,
        value=value,
        values=values or {},
        unit=unit,
        formula=formula,
        method=method,
        assumptions=list(assumptions or []),
        warnings=list(warnings or []),
        validation_status=status,
        metadata=metadata or {},
        scope=scope,
    )


def missing(field: str) -> EngineeringResult:
    return EngineeringResult(
        success=False,
        error=f"MISSING_INPUT: {field}",
        validation_status="missing_input",
        scope="PARTIAL",
    )


def unsupported(reason: str, *, scope: str = "NOT_IMPLEMENTED") -> EngineeringResult:
    return EngineeringResult(
        success=False,
        error=f"UNSUPPORTED_CALCULATION: {reason}",
        validation_status="unsupported",
        scope=scope,
    )


def failed(message: str) -> EngineeringResult:
    return EngineeringResult(
        success=False,
        error=message,
        validation_status="error",
    )


def require_number(value: Any, field: str) -> float:
    """Reject None/blank. Never invent 0 for a missing engineering input."""
    if value is None or value == "":
        raise MissingInputError(field)
    if isinstance(value, bool):
        raise EngineeringError(f"Invalid numeric value for {field}: {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EngineeringError(f"Invalid numeric value for {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise EngineeringError(f"Invalid numeric value for {field}: {value!r}")
    return number


def optional_number(value: Any, field: str) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise EngineeringError(f"Invalid numeric value for {field}: {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EngineeringError(f"Invalid numeric value for {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise EngineeringError(f"Invalid numeric value for {field}: {value!r}")
    return number
