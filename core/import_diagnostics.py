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


STATUS_PRECEDENCE = (
    ImportStatus.PERSISTENCE_ERROR.value,
    ImportStatus.VALIDATION_ERROR.value,
    ImportStatus.REVIEW_REQUIRED.value,
    ImportStatus.ACCEPT.value,
)


import traceback as traceback_module


def determine_import_status(*, persistence_error: bool = False,
                            validation_error: bool = False,
                            review_required: bool = False) -> str:
    """Return the deterministic final status for an import result."""
    flags = {
        ImportStatus.PERSISTENCE_ERROR.value: persistence_error,
        ImportStatus.VALIDATION_ERROR.value: validation_error,
        ImportStatus.REVIEW_REQUIRED.value: review_required,
    }
    for status in STATUS_PRECEDENCE:
        if flags.get(status):
            return status
    return ImportStatus.ACCEPT.value


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
        from core.save_outcome import public_status
        return {**asdict(self), "outcome_status": public_status(self.status)}

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


class OwnershipIntegrityError(ValueError):
    """Raised when a persisted ownership chain would become internally
    contradictory.

    The Well → Wellbore → Section → DailyReport hierarchy must stay coherent:
    a foreign key alone only proves the referenced row exists, not that it
    belongs to the same Well/Wellbore. This error is raised at the persistence
    boundary (a ``before_flush`` hook) so it fires on every save path — ORM
    helpers, the import service, and direct session use alike — rather than
    relying on UI selection guards.
    """


class SchemaMigrationError(RuntimeError):
    """Structured fatal error raised when a SQLite migration cannot complete."""

    def __init__(self, issue: PersistenceIssue, *, result: Optional[dict] = None):
        super().__init__(issue.message)
        self.issue = issue
        self.result = result or {"diagnostics": [issue.to_dict()]}

    def to_dict(self) -> dict[str, Any]:
        return self.issue.to_dict()
