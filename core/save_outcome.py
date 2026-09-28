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
    NO_CHANGES = "NO_CHANGES"
    SAVED = "SAVED"
    CONTEXT_BLOCKED = "CONTEXT_BLOCKED"


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
    code: str = ""


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

    @property
    def disposition(self):
        if self.status == "SUCCESS":
            return "SAVED" if self.saved else "NO_CHANGES"
        if self.status == "REVIEW_REQUIRED" and any(i.code == "CONTEXT_BLOCKED" for i in self.issues):
            return "CONTEXT_BLOCKED"
        return "VALIDATION_ERROR" if self.status == "INVALID_SOURCE" else self.status

    @property
    def counts(self):
        counts = {}
        def visit(value):
            if value.get("sections"):
                for child in value["sections"].values():
                    visit(child)
            else:
                key = value["disposition"]
                counts[key] = counts.get(key, 0) + 1
                if value["saved"] and key != "SAVED":
                    counts["SAVED"] = counts.get("SAVED", 0) + 1
        visit(self.to_dict())
        return counts

    def __bool__(self):
        return self.status == "SUCCESS"

    def to_dict(self):
        return {**asdict(self), "status": self.status, "disposition": self.disposition}

    def summary(self):
        lines = ["NO_CHANGES: Nothing to save." if self.disposition == "NO_CHANGES" else
                 f"{self.disposition}: {self.saved} save operation(s) completed; section counts: {self.counts}."]
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
            if getattr(owner, "_edit_sections", None) == {}:
                outcome = SaveOutcome()
            elif callable(ready) and not ready():
                outcome = SaveOutcome(issues=[SaveIssue(section,
                    "The selected context has not been loaded successfully; stale editor data was not saved.",
                    status="REVIEW_REQUIRED", code="CONTEXT_BLOCKED", corrective_action="Open/reload this tab, resolve any load error, and save again.")])
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
