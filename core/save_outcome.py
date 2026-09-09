"""Qt-free save outcome contract shared by record services and Save All.

Legacy booleans remain compatible, but a false/None result is never success.
A legacy callback without diagnostics is explicitly a contract/system error.
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
import traceback


class OutcomeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INVALID_SOURCE = "INVALID_SOURCE"
    UNSUPPORTED = "UNSUPPORTED"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass
class SaveIssue:
    section: str
    reason: str
    status: str = "SYSTEM_ERROR"
    row: int | None = None
    field: str = ""
    corrective_action: str = "Inspect the section diagnostics before retrying; do not assume it saved."
    exception_type: str = ""
    traceback: str = ""


@dataclass
class SaveOutcome:
    saved: int = 0
    issues: list[SaveIssue] = field(default_factory=list)
    sections: dict = field(default_factory=dict)

    @property
    def status(self):
        for status in ("SYSTEM_ERROR", "INVALID_SOURCE", "UNSUPPORTED", "REVIEW_REQUIRED"):
            if any(issue.status == status for issue in self.issues):
                return status
        return "SUCCESS"

    def __bool__(self):
        return self.status == "SUCCESS"

    def to_dict(self):
        return {**asdict(self), "status": self.status}

    def summary(self):
        lines = [f"{self.status}: {self.saved} save operation(s) completed."]
        for issue in self.issues:
            location = issue.section + (f" row {issue.row}" if issue.row is not None else "")
            if issue.field:
                location += f" [{issue.field}]"
            lines.append(f"{location}: {issue.reason} — {issue.corrective_action}")
        return "\n".join(lines)


def save_all(steps):
    """Execute independent section saves; report partial success honestly.

    Atomicity belongs to the supplied domain service. This coordinator does
    not promise rollback across callbacks which commit independent records.
    """
    result = SaveOutcome()
    for section, callback in steps:
        try:
            owner = getattr(callback, "__self__", None)
            if owner is not None and hasattr(owner, "last_save_outcome"):
                owner.last_save_outcome = None
            ready = getattr(owner, "save_context_ready", None)
            if callable(ready) and not ready():
                outcome = SaveOutcome(issues=[SaveIssue(section,
                    "The selected context has not been loaded successfully; stale editor data was not saved.",
                    status="REVIEW_REQUIRED", corrective_action="Open/reload this tab, resolve any load error, and save again.")])
                owner.last_save_outcome = outcome
            else:
                value = callback()
                detailed = getattr(owner, "last_save_outcome", None)
                if isinstance(value, SaveOutcome):
                    outcome = value
                elif isinstance(detailed, SaveOutcome):
                    outcome = detailed
                elif value is True or (type(value) is int and value > 0):
                    outcome = SaveOutcome(saved=1)
                else:
                    outcome = SaveOutcome(issues=[SaveIssue(section, f"Save returned {value!r} without a structured result")])
        except Exception as exc:
            invalid = isinstance(exc, ValueError)
            unsupported = isinstance(exc, NotImplementedError)
            outcome = SaveOutcome(issues=[SaveIssue(section, str(exc),
                status="INVALID_SOURCE" if invalid else "UNSUPPORTED" if unsupported else "SYSTEM_ERROR",
                corrective_action="Correct the supplied value/context and retry." if invalid else "Inspect the exception and retry after correcting the fault.",
                exception_type=type(exc).__name__, traceback=traceback.format_exc())])
        result.saved += outcome.saved
        result.issues.extend(outcome.issues)
        result.sections[section] = outcome.to_dict()
    return result


def public_status(status):
    """Explicit presentation mapping without breaking legacy serialized APIs."""
    normalized = {"ACCEPT": "SUCCESS", "OK": "SUCCESS", "VALIDATION_ERROR": "INVALID_SOURCE",
                  "PERSISTENCE_ERROR": "SYSTEM_ERROR", "UNRESOLVED": "REVIEW_REQUIRED",
                  "CONFLICT": "REVIEW_REQUIRED", "REVIEW": "REVIEW_REQUIRED"}.get(status, status)
    return normalized if normalized in {item.value for item in OutcomeStatus} else "SYSTEM_ERROR"


def validation_outcome(section, validation, saved=0):
    """Translate the established validators' dict issue contract, losslessly."""
    outcome = SaveOutcome(saved=saved)
    for status, issues in (("INVALID_SOURCE", validation.errors), ("REVIEW_REQUIRED", validation.warnings)):
        for issue in issues:
            outcome.issues.append(SaveIssue(section, issue["message"], field=issue["field"], status=status,
                                           corrective_action="Correct invalid input or review the retained missing source value."))
    return outcome
