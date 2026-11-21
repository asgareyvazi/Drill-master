"""M272: explicit value states for the numeric DDR header fields - contract ``ddr-value-states-v1``.

A blank number on a daily report can mean several different things: the value was 0, it was not known, the
field did not apply that day, or nobody reported it. A value can also be calculated rather than reported.
Before M272 all of these looked the same on a report. This module lets the operator record **which** one it is,
per field and per report, without ever putting a number into a missing value:

* ``REPORTED``: a non-zero number was reported.
* ``ZERO``: the reported value is 0 (a real zero, not a missing value).
* ``CALCULATED``: the stored number was calculated; the method must be stated.
* ``UNKNOWN``: the value existed but was not known. The stored value stays None.
* ``NOT_APPLICABLE``: the field did not apply that day (e.g. no rotation). The stored value stays None.
* ``NOT_REPORTED``: nobody reported it. The stored value stays None. This is also the implicit state of an
  empty field.

Carrying a value forward is not a value state. It stays the M217 section contract (``ddr_carry_forward``):
only with explicit confirmation, and a carried section stays CARRIED until it is confirmed.

Recorded states are append-only events (``ddr_value_states``, insert-only storage guard), and the latest event of
a field wins. Each event writes a mandatory audit record in the same transaction. A state that contradicts the
stored value is refused: a missing state with a stored number, ZERO with a non-zero number, REPORTED or
CALCULATED without a number, or CALCULATED without a method. If the value is edited after its state was recorded,
the contradiction is reported as INCONSISTENT; it is never repaired silently.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

CONTRACT = "ddr-value-states-v1"
REPORTED, ZERO, CALCULATED = "REPORTED", "ZERO", "CALCULATED"
UNKNOWN, NOT_APPLICABLE, NOT_REPORTED = "UNKNOWN", "NOT_APPLICABLE", "NOT_REPORTED"
STATES = (REPORTED, ZERO, CALCULATED, UNKNOWN, NOT_APPLICABLE, NOT_REPORTED)
MISSING_STATES = (UNKNOWN, NOT_APPLICABLE, NOT_REPORTED)        # the stored value must be None
INCONSISTENT = "INCONSISTENT"
AUDIT_ACTION = "ddr_value_state"

# The numeric header fields of ``daily_reports`` (column -> label as shown on the DDR form). No unit is
# claimed here; the DDR form owns the units.
FIELDS: Dict[str, str] = {
    "depth_0000": "Depth 00:00", "depth_0600": "Depth 06:00", "depth_2400": "Depth 24:00",
    "rop_meter": "ROP", "wob": "WOB", "rpm": "RPM", "torque": "Torque", "pressure": "Pressure",
    "mud_weight_in": "Mud weight in", "mud_weight_out": "Mud weight out", "mw_pcf": "MW (PCF) remark",
}

# What an operator may type for a value with no number (case-insensitive, stripped).
_TEXT_STATES = {
    "": NOT_REPORTED, "nr": NOT_REPORTED, "n.r.": NOT_REPORTED, "not reported": NOT_REPORTED,
    "?": UNKNOWN, "unk": UNKNOWN, "unknown": UNKNOWN,
    "n/a": NOT_APPLICABLE, "na": NOT_APPLICABLE, "not applicable": NOT_APPLICABLE,
}


class ValueStateError(ValueError):
    """A value state was refused; the message says why. Nothing was written."""


def _number(value: Any) -> Optional[float]:
    """A stored or typed number as a finite float; None for empty, booleans, text, NaN and infinity."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None                                       # numeric DDR columns: anything else is not a number
    number = float(value)
    return number if math.isfinite(number) else None


def parse_authored(text: Any) -> Tuple[Optional[float], str]:
    """``(value, state)`` for what an operator typed into a numeric DDR field.

    A number gives REPORTED, or ZERO for 0. The words above give a missing state with the value None. Anything
    else, including NaN and infinity, is refused rather than guessed.
    """
    if text is None:
        return None, NOT_REPORTED
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        number = _number(text)
        if number is None:
            raise ValueStateError(f"{text!r} is not a finite number")
        return number, (ZERO if number == 0 else REPORTED)
    raw = str(text).strip()
    key = raw.lower()
    if key in _TEXT_STATES:
        return None, _TEXT_STATES[key]
    if "," in raw:                                        # "1,5" (decimal comma) vs "1,500" (thousands): refuse
        raise ValueStateError(f"{raw!r}: commas are refused (decimal or thousands separator?) - type 1500 or 1.5")
    try:
        number = float(raw)
    except ValueError:
        raise ValueStateError(f"{raw!r} is neither a number nor one of: blank, NR, ?, unknown, N/A") from None
    if not math.isfinite(number):
        raise ValueStateError(f"{raw!r} is not a finite number")
    return number, (ZERO if number == 0 else REPORTED)


def implicit_state(value: Any) -> str:
    """The state of a field with no recorded state: NOT_REPORTED when empty, ZERO for 0, else REPORTED.

    A stored value that is not a finite number (legacy text, NaN) is not empty: it is INCONSISTENT.
    """
    if value is None:
        return NOT_REPORTED
    number = _number(value)
    if number is None:
        return INCONSISTENT
    return ZERO if number == 0 else REPORTED


def contradiction(state: str, value: Any, method: str = "") -> Optional[str]:
    """Why ``state`` cannot describe the stored ``value`` (None when it can)."""
    number = _number(value)
    if state not in STATES:
        return f"unknown value state {state!r}"
    if state in MISSING_STATES and value is not None:
        return f"{state} needs an empty value (a missing value stays None); the field holds {value!r}"
    if state == ZERO and number != 0:
        return f"ZERO needs a stored 0; the field holds {value!r}"
    if state == REPORTED and (number is None or number == 0):
        return "REPORTED needs a stored non-zero number" + (" (use ZERO for 0)" if number == 0 else "")
    if state == CALCULATED:
        if number is None:
            return "CALCULATED needs the calculated number in the field"
        if not str(method or "").strip():
            return "CALCULATED needs the calculation method"
    return None


def _report(session, report_id: int):
    from core.database import DailyReport

    report = session.get(DailyReport, report_id)
    if report is None:
        raise ValueStateError(f"daily report {report_id} does not exist")
    return report


def _latest(session, report_id: int) -> Dict[str, Any]:
    from core.database import DdrValueState

    rows = (session.query(DdrValueState).filter(DdrValueState.report_id == report_id)
            .order_by(DdrValueState.id.asc()).all())
    latest: Dict[str, Any] = {}
    for row in rows:
        latest[row.field] = row                            # ordered by id: the last event wins
    return latest


def record(db, report_id: int, field: str, state: str, *, method: str = "", note: str = "",
           user_id: Optional[int] = None) -> Dict[str, Any]:
    """Record the state of one field of one report (append-only, audited). Refused on any contradiction."""
    from core.database import DdrValueState

    if field not in FIELDS:
        raise ValueStateError(f"{field!r} is not a numeric DDR header field")
    with db.session_scope() as session:
        report = _report(session, report_id)
        value = getattr(report, field)
        why = contradiction(state, value, method)
        if why:
            raise ValueStateError(f"{FIELDS[field]}: {why}")
        row = DdrValueState(report_id=report_id, field=field, state=state, method=str(method or "").strip() or None,
                            note=str(note or "").strip() or None, created_by=user_id)
        session.add(row)
        session.flush()
        db._add_mandatory_audit(session, AUDIT_ACTION, "daily_reports", report_id, FIELDS[field],
                                f"{CONTRACT}: {field} = {state}" + (f" ({row.method})" if row.method else ""))
        return {"id": row.id, "report_id": report_id, "field": field, "state": state, "method": row.method}


def states(db, report_id: int) -> Dict[str, Dict[str, Any]]:
    """Per numeric header field: stored value, state, whether it was recorded, method, note, consistency."""
    with db.session_scope() as session:
        return states_in(session, report_id)


def states_in(session, report_id: int) -> Dict[str, Dict[str, Any]]:
    """:func:`states` inside the caller's session (read-only; used by the data-quality workspace)."""
    report = _report(session, report_id)
    latest = _latest(session, report_id)
    out: Dict[str, Dict[str, Any]] = {}
    for field, label in FIELDS.items():
        value = getattr(report, field)
        row = latest.get(field)
        if row is None:
            state = implicit_state(value)
            unreadable = state == INCONSISTENT
            out[field] = {"label": label, "value": value, "state": state, "recorded": False,
                          "method": None, "note": None, "consistent": not unreadable,
                          "reason": f"the stored value {value!r} is not a finite number" if unreadable else ""}
            continue
        why = contradiction(row.state, value, row.method or "")
        out[field] = {"label": label, "value": value, "state": INCONSISTENT if why else row.state,
                      "recorded_state": row.state, "recorded": True, "method": row.method, "note": row.note,
                      "consistent": why is None, "reason": why or ""}
    return out
