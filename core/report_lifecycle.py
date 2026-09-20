"""Daily Drilling Report lifecycle rules — Qt-free, domain-specific.

This is NOT a generic workflow engine. It encodes the concrete Daily Report
state machine (Draft/Submitted/Under Review/Rejected/Approved/Final) and the
transition/permission/comment rules that the backend enforces authoritatively.

The database layer calls :func:`decide_transition` to validate a requested
action before it mutates state, revision, and approval history atomically. The
UI is a consumer of the same rules; UI buttons are never the security boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


class LifecycleOutcome:
    """Explicit outcome codes reusing the project's established vocabulary."""

    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    CONTEXT_ERROR = "CONTEXT_ERROR"
    NOT_FOUND = "NOT_FOUND"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"


# Canonical status vocabulary. "Under Review" and "Final" are legacy-real
# states: they can exist in stored data and are handled honestly, even though
# the default UI drives Draft -> Submitted -> Approved.
ALL_STATUSES = ("Draft", "Submitted", "Under Review", "Rejected", "Approved", "Final")

# States whose report body may be edited. Draft is the working state; Rejected
# is editable so the author can correct and resubmit. Everything else is locked.
EDITABLE_STATES = frozenset({"Draft", "Rejected"})

# Final is terminal and immutable.
TERMINAL_STATES = frozenset({"Final"})

# Workflow actions and the permission each one requires.
ACTION_PERMISSION = {
    "submit": "can_edit_reports",
    "approve": "can_approve_reports",
    "reject": "can_approve_reports",
    "finalize": "can_approve_reports",
}

# Actions that require a non-blank comment/reason.
COMMENT_REQUIRED = frozenset({"reject"})

# The concrete transition table: {current_status: {action: next_status}}.
# Any (status, action) pair absent here is an invalid transition.
TRANSITIONS = {
    "Draft": {"submit": "Submitted"},
    "Rejected": {"submit": "Submitted"},
    "Submitted": {"approve": "Approved", "reject": "Rejected"},
    "Under Review": {"approve": "Approved", "reject": "Rejected"},
    "Approved": {"finalize": "Final"},
    "Final": {},
}

# Workflow actions produce a revision snapshot (audit + immutable history).
ACTION_CREATES_REVISION = frozenset({"submit", "approve", "reject", "finalize"})

# Actions that assert the report's operational content is sound before an
# irreversible workflow event. Rejection deliberately does NOT re-validate
# content — you are rejecting it precisely because something is wrong, and the
# mandatory comment carries the reason (mission §18/§19/§26).
ACTION_REQUIRES_VALIDATION = frozenset({"submit", "approve", "finalize"})


def is_editable(status: Optional[str]) -> bool:
    """True when a report in ``status`` may have its body edited/saved."""
    return (status or "Draft") in EDITABLE_STATES


def is_terminal(status: Optional[str]) -> bool:
    return (status or "") in TERMINAL_STATES


def resolve_transition(current_status: Optional[str], action: str) -> Optional[str]:
    """Return the next status for a (current_status, action) pair, or None."""
    return TRANSITIONS.get(current_status or "Draft", {}).get(action)


def allowed_actions(current_status: Optional[str]) -> tuple:
    """Actions that are structurally valid from ``current_status``."""
    return tuple(TRANSITIONS.get(current_status or "Draft", {}).keys())


@dataclass
class LifecycleDecision:
    """Pure decision about whether a transition may proceed."""

    ok: bool
    outcome: str
    message: str
    next_status: Optional[str] = None

    def __bool__(self) -> bool:
        return self.ok


def decide_transition(
    current_status: Optional[str],
    action: str,
    has_permission: Callable[[str], bool],
    comment: str = "",
) -> LifecycleDecision:
    """Validate a requested transition against the state machine.

    Order of checks is deliberate: structural validity first (is this action
    even meaningful from this state?), then authorization, then required input.
    Nothing is silently coerced — every rejection carries an explicit outcome.
    """
    action = (action or "").strip()
    if action not in ACTION_PERMISSION:
        return LifecycleDecision(False, LifecycleOutcome.INVALID_TRANSITION,
                                 f"Unknown workflow action: {action!r}.")

    next_status = resolve_transition(current_status, action)
    if next_status is None:
        return LifecycleDecision(
            False, LifecycleOutcome.INVALID_TRANSITION,
            f"Cannot '{action}' a report in status '{current_status or 'Draft'}'.")

    permission = ACTION_PERMISSION[action]
    if not has_permission(permission):
        return LifecycleDecision(
            False, LifecycleOutcome.PERMISSION_DENIED,
            f"You do not have permission to {action} reports.")

    if action in COMMENT_REQUIRED and not (comment or "").strip():
        return LifecycleDecision(
            False, LifecycleOutcome.VALIDATION_ERROR,
            f"A comment is required to {action} a report.")

    return LifecycleDecision(True, LifecycleOutcome.SUCCESS, "", next_status)


@dataclass
class LifecycleResult:
    """Result of an executed transition attempt (persistence-aware)."""

    ok: bool
    outcome: str
    message: str = ""
    report_id: Optional[int] = None
    new_status: Optional[str] = None
    revision_id: Optional[int] = None
    action_id: Optional[int] = None

    def __bool__(self) -> bool:
        return self.ok
