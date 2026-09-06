"""Structured diagnostics shared by import and persistence boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


class ImportStatus(str, Enum):
    ACCEPT = "ACCEPT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
import traceback as traceback_module


@dataclass
class PersistenceIssue:
    """One actionable persistence or validation failure.

    Values are intentionally source-oriented.  Callers may omit sensitive
    database details while retaining the source value and its provenance.
    """

    stage: str
    entity: str
    field: str = ""
    source: Any = None
    row: Optional[int] = None
    original_value: Any = None
    normalized_value: Any = None
    expected_type: str = ""
    operation: str = ""
    exception_type: str = ""
    message: str = ""
    traceback: str = ""
    status: str = "PERSISTENCE_ERROR"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        stage: str,
        entity: str,
        field: str = "",
        source: Any = None,
        row: Optional[int] = None,
        original_value: Any = None,
        normalized_value: Any = None,
        expected_type: str = "",
        operation: str = "",
        status: str = "PERSISTENCE_ERROR",
    ) -> "PersistenceIssue":
        return cls(
            stage=stage,
            entity=entity,
            field=field,
            source=source,
            row=row,
            original_value=original_value,
            normalized_value=normalized_value,
            expected_type=expected_type,
            operation=operation,
            exception_type=type(exc).__name__,
            message=str(exc),
            traceback="".join(traceback_module.format_exception(exc)),
            status=status,
        )


class PersistenceError(RuntimeError):
    """Raised after an import transaction has captured its first issue."""

    def __init__(self, issue: PersistenceIssue, *, result: Optional[dict] = None):
        super().__init__(issue.message)
        self.issue = issue
        self.result = result or {}

    def to_dict(self) -> dict[str, Any]:
        return self.issue.to_dict()
