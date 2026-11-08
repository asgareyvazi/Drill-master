"""M134: NPT event reconciliation — the NPT register (``npt_reports``) against the DDR time-log NPT rows.

The two sources describe the same downtime in two places. Until M134 they were listed side by side and never
added (M91). Reconciliation pairs them so that one NPT event is counted ONCE:

* ``MATCHED``         – one register event, linked to the same daily report, whose interval is exactly the
                        union of the overlapping time-log NPT rows (no other register event touches them);
* ``REGISTER ONLY``   – a register event that no time-log NPT row overlaps;
* ``TIME-LOG ONLY``   – a time-log NPT row that no register event overlaps;
* ``UNCERTAIN``       – anything else that overlaps: different intervals, a row shared by two register events,
                        a register event linked by date only (no report) — never counted in the total;
* ``CONFIRMED SAME`` / ``CONFIRMED DIFFERENT`` – an UNCERTAIN group a user decided, with evidence and a reason
                        (append-only ``npt_event_decisions``; stale when any of its rows changed since).

Counting basis: a MATCHED or CONFIRMED SAME event counts the time-log hours (the DDR's own 24 h log) once; a
single-source event counts its own hours; CONFIRMED DIFFERENT counts both. UNCERTAIN hours are reported as a
range (once … both) beside the certain total, never inside it. Overlap is decided from the recorded clock
times only (an end at or before the start is read as crossing midnight); nothing is interpolated.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

RECON_METHOD = "M134 NPT event reconciliation v1"
DECISION_VERSION = "M134 NPT event decision v1"
MATCHED, REGISTER_ONLY, LOG_ONLY, UNCERTAIN = "MATCHED", "REGISTER ONLY", "TIME-LOG ONLY", "UNCERTAIN"
CONFIRMED_SAME, CONFIRMED_DIFFERENT = "CONFIRMED SAME", "CONFIRMED DIFFERENT"
SAME_EVENT, DIFFERENT_EVENTS = "SAME_EVENT", "DIFFERENT_EVENTS"
DECISIONS = (SAME_EVENT, DIFFERENT_EVENTS)
MINUTES_PER_DAY = 24 * 60
COLUMNS = ("Status", "Date", "Report", "Register event", "Register h", "Time-log rows", "Time-log h", "Counted h",
           "Basis", "Note")


class ReconciliationError(ValueError):
    """A decision that cannot be recorded (the message says why)."""


@dataclass(frozen=True)
class RegisterEvent:
    id: int
    report_id: Optional[int]
    date: str
    start: str
    end: str
    hours: Optional[float]
    category: str
    code: str
    description: str

    def interval(self) -> Optional[Tuple[int, int]]:
        return _interval(self.start, self.end)

    def label(self) -> str:
        return f"NPT #{self.id} {self.date} {self.start}–{self.end} {self.code or self.category}".strip()


@dataclass(frozen=True)
class LogRow:
    id: int
    report_id: int
    date: str
    start: str
    end: str
    hours: Optional[float]
    code: str
    category: str

    def interval(self) -> Optional[Tuple[int, int]]:
        return _interval(self.start, self.end)


@dataclass(frozen=True)
class Decision:
    id: int
    register_ids: Tuple[int, ...]
    log_ids: Tuple[int, ...]
    rows_sha256: str
    decision: str
    evidence: str
    reason: str
    confirmer: str
    confirmed_at: str


@dataclass
class Group:
    status: str
    register: List[RegisterEvent]
    logs: List[LogRow]
    counted_hours: Optional[float]
    basis: str
    notes: List[str] = field(default_factory=list)
    decision: Optional[Decision] = None
    once_hours: Optional[float] = None       # UNCERTAIN range, low end (the rows are one event)
    both_hours: Optional[float] = None       # UNCERTAIN range, high end (they are different events)

    @property
    def register_ids(self) -> Tuple[int, ...]:
        return tuple(sorted(r.id for r in self.register))

    @property
    def log_ids(self) -> Tuple[int, ...]:
        return tuple(sorted(r.id for r in self.logs))

    @property
    def report_id(self) -> Optional[int]:
        ids = {r.report_id for r in self.logs} | {r.report_id for r in self.register if r.report_id}
        return ids.pop() if len(ids) == 1 else None

    @property
    def date(self) -> str:
        dates = sorted({r.date for r in self.register} | {r.date for r in self.logs})
        return ", ".join(dates)

    def table_row(self) -> Tuple[Any, ...]:
        return (self.status, self.date, self.report_id,
                "; ".join(r.label() for r in self.register) or None, _sum(r.hours for r in self.register),
                "; ".join(f"#{r.id} {r.start}–{r.end} {r.code}".strip() for r in self.logs) or None,
                _sum(r.hours for r in self.logs), self.counted_hours, self.basis, " ".join(self.notes))


@dataclass
class Reconciliation:
    groups: List[Group]
    excluded: List[str]

    def totals(self) -> Dict[str, Any]:
        certain = sum(g.counted_hours for g in self.groups if g.counted_hours is not None)
        uncertain = [g for g in self.groups if g.status == UNCERTAIN]
        unknown = [g for g in self.groups if g.status != UNCERTAIN and g.counted_hours is None]
        low = sum(g.once_hours or 0.0 for g in uncertain)
        high = sum(g.both_hours or 0.0 for g in uncertain)
        by_status: Dict[str, int] = {}
        for g in self.groups:
            by_status[g.status] = by_status.get(g.status, 0) + 1
        return {"certain_hours": certain, "uncertain_groups": len(uncertain), "uncertain_low": low,
                "uncertain_high": high, "unknown_duration_groups": len(unknown), "by_status": by_status}

    def summary(self) -> str:
        t = self.totals()
        text = f"Reconciled NPT {t['certain_hours']:.2f} h (each event once)."
        if t["uncertain_groups"]:
            text += (f" {t['uncertain_groups']} UNCERTAIN group(s) not added: "
                     f"{t['uncertain_low']:.2f}–{t['uncertain_high']:.2f} h more (one event … different events).")
        if t["unknown_duration_groups"]:
            text += f" {t['unknown_duration_groups']} event(s) without a valid duration are not added."
        return text + f" {RECON_METHOD}."


def _minutes(text: str) -> Optional[int]:
    try:
        hours, minutes = (int(part) for part in text.split(":")[:2])
    except (AttributeError, ValueError):  # silent-ok: an unreadable time has no interval (reported as such)
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):     # M140: "25:00" or "10:75" is not a time of day
        return None
    return hours * 60 + minutes


def _interval(start: str, end: str) -> Optional[Tuple[int, int]]:
    a, b = _minutes(start), _minutes(end)
    if a is None or b is None:
        return None
    if b <= a:
        b += MINUTES_PER_DAY            # recorded end at or before the start: the row crosses midnight
    return a, b


def _overlap(x: Optional[Tuple[int, int]], y: Optional[Tuple[int, int]]) -> int:
    if x is None or y is None:
        return 0
    return max(0, min(x[1], y[1]) - max(x[0], y[0]))


def _sum(values) -> Optional[float]:
    values = list(values)
    if not values or any(v is None or v < 0 for v in values):
        return None
    return float(sum(values))


def _hhmm(value) -> str:
    return value.strftime("%H:%M") if value is not None else ""


def _finite(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):  # silent-ok: an unreadable duration is unknown, never zero
        return None
    return number if number == number and abs(number) != float("inf") else None


# ---- loading (worker side: plain values only) ---------------------------------------------------------------
def load(db, well_id: int, wellbore_id: Optional[int] = None) -> Tuple[List[RegisterEvent], List[LogRow],
                                                                      List[Decision], List[str]]:
    """Register events, time-log NPT rows and decisions of the scope. With an explicit wellbore only rows of
    that wellbore's reports; register events without a report are then excluded (never attributed)."""
    from core.database import DailyReport, NPTEventDecision, NPTReport, TimeLog24H, User

    excluded: List[str] = []
    with db.session_scope() as session:
        reports = {r.id: (r.report_date.isoformat() if r.report_date else "", r.wellbore_id)
                   for r in session.query(DailyReport).filter(DailyReport.well_id == well_id)}
        in_scope = {rid for rid, (_d, bore) in reports.items() if not wellbore_id or bore == wellbore_id}
        register = []
        for row in session.query(NPTReport).filter(NPTReport.well_id == well_id).order_by(NPTReport.npt_date,
                                                                                            NPTReport.start_time):
            if wellbore_id and row.report_id not in in_scope:
                excluded.append(f"NPT #{row.id}: " + ("no daily report link — not attributed to the wellbore"
                                                      if not row.report_id else "another wellbore's report"))
                continue
            register.append(RegisterEvent(row.id, row.report_id, row.npt_date.isoformat() if row.npt_date else "",
                                          _hhmm(row.start_time), _hhmm(row.end_time), _finite(row.duration_hours),
                                          row.npt_category or "", row.npt_code or "", row.npt_description or ""))
        logs = []
        if in_scope:
            for row in (session.query(TimeLog24H).filter(TimeLog24H.report_id.in_(in_scope),
                                                         TimeLog24H.is_npt.is_(True))
                        .order_by(TimeLog24H.report_id, TimeLog24H.time_from, TimeLog24H.id)):
                logs.append(LogRow(row.id, row.report_id, reports[row.report_id][0], _hhmm(row.time_from),
                                   _hhmm(row.time_to), _finite(row.duration), row.main_code or "",
                                   row.npt_category or ""))
        decisions = []
        names = dict(session.query(User.id, User.username).all())
        for row in (session.query(NPTEventDecision).filter(NPTEventDecision.well_id == well_id)
                    .order_by(NPTEventDecision.id)):
            decisions.append(Decision(row.id, tuple(json.loads(row.register_ids_json)),
                                      tuple(json.loads(row.time_log_ids_json)), row.rows_sha256, row.decision,
                                      row.evidence, row.reason, names.get(row.confirmed_by) or
                                      f"user #{row.confirmed_by}",
                                      row.confirmed_at.isoformat(sep=" ", timespec="seconds")
                                      if row.confirmed_at else ""))
    return register, logs, decisions, excluded


def rows_sha256(register: Sequence[RegisterEvent], logs: Sequence[LogRow]) -> str:
    payload = {"register": sorted((r.id, r.report_id, r.date, r.start, r.end, r.hours) for r in register),
               "logs": sorted((r.id, r.report_id, r.start, r.end, r.hours) for r in logs)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ---- reconciliation ---------------------------------------------------------------------------------------------
def _components(register: Sequence[RegisterEvent], logs: Sequence[LogRow]):
    """Register events and time-log rows connected by a time overlap (same report, or same date when the
    register event has no report)."""
    edges: Dict[int, List[int]] = {r.id: [] for r in register}
    by_report: Dict[int, List[LogRow]] = {}
    for log in logs:
        by_report.setdefault(log.report_id, []).append(log)
    for reg in register:
        if reg.report_id:
            candidates = by_report.get(reg.report_id, [])
        else:
            candidates = [log for log in logs if log.date == reg.date]
        edges[reg.id] = [log.id for log in candidates if _overlap(reg.interval(), log.interval()) > 0]
    reg_of: Dict[int, List[int]] = {}
    for rid, ids in edges.items():
        for lid in ids:
            reg_of.setdefault(lid, []).append(rid)
    seen_reg, seen_log, groups = set(), set(), []
    reg_by_id, log_by_id = {r.id: r for r in register}, {r.id: r for r in logs}
    for start in register:
        if start.id in seen_reg:
            continue
        regs, lgs, stack = set(), set(), [("r", start.id)]
        while stack:
            kind, ident = stack.pop()
            if kind == "r" and ident not in regs:
                regs.add(ident)
                stack.extend(("l", lid) for lid in edges[ident])
            elif kind == "l" and ident not in lgs:
                lgs.add(ident)
                stack.extend(("r", rid) for rid in reg_of.get(ident, []))
        seen_reg |= regs
        seen_log |= lgs
        groups.append(([reg_by_id[i] for i in sorted(regs)], [log_by_id[i] for i in sorted(lgs)]))
    for log in logs:
        if log.id not in seen_log:
            groups.append(([], [log]))
    return groups


def _exact(reg: RegisterEvent, logs: Sequence[LogRow]) -> bool:
    """The register interval is exactly the union of the rows: contiguous, same start and end."""
    spans = sorted(log.interval() for log in logs if log.interval() is not None)
    if len(spans) != len(logs) or reg.interval() is None:
        return False
    for (_a, b), (c, _d) in zip(spans, spans[1:]):
        if b != c:
            return False
    return (spans[0][0], spans[-1][1]) == reg.interval()


def reconcile(register: Sequence[RegisterEvent], logs: Sequence[LogRow], decisions: Sequence[Decision] = (),
              excluded: Sequence[str] = ()) -> Reconciliation:
    latest: Dict[Tuple[Tuple[int, ...], Tuple[int, ...]], Decision] = {}
    for d in decisions:                                    # the latest decision of a group governs
        latest[(tuple(sorted(d.register_ids)), tuple(sorted(d.log_ids)))] = d
    groups: List[Group] = []
    for regs, lgs in _components(register, logs):
        reg_hours, log_hours = _sum(r.hours for r in regs), _sum(r.hours for r in lgs)
        if not lgs:
            groups.append(Group(REGISTER_ONLY, regs, [], reg_hours, "register hours",
                                [] if reg_hours is not None else ["duration not recorded validly"]))
            continue
        if not regs:
            groups.append(Group(LOG_ONLY, [], lgs, log_hours, "time-log hours",
                                [] if log_hours is not None else ["duration not recorded validly"]))
            continue
        notes = []
        if len(regs) == 1 and regs[0].report_id and _exact(regs[0], lgs):
            if reg_hours is not None and log_hours is not None and abs(reg_hours - log_hours) > 1e-9:
                notes.append(f"recorded durations differ (register {reg_hours:g} h, time log {log_hours:g} h); "
                             "the time-log hours are counted")
            codes = {r.code for r in lgs if r.code}
            if regs[0].code and codes and codes != {regs[0].code}:
                notes.append(f"codes differ (register {regs[0].code}, time log {', '.join(sorted(codes))})")
            groups.append(Group(MATCHED, regs, lgs, log_hours, "time-log hours (counted once)", notes))
            continue
        if len(regs) > 1:
            notes.append(f"{len(regs)} register events overlap the same time-log row(s)")
        if any(not r.report_id for r in regs):
            notes.append("a register event has no daily report link (matched by date only)")
        if not notes:
            notes.append("intervals overlap but differ")
        group = Group(UNCERTAIN, regs, lgs, None, "not counted (needs a decision)", notes)
        if reg_hours is not None and log_hours is not None:
            group.once_hours, group.both_hours = max(reg_hours, log_hours), reg_hours + log_hours
        decision = latest.get((group.register_ids, group.log_ids))
        if decision is not None:
            if decision.rows_sha256 != rows_sha256(regs, lgs):
                group.notes.append(f"decision #{decision.id} is STALE: the rows changed since it was confirmed")
            elif decision.decision == SAME_EVENT:
                group.status, group.decision = CONFIRMED_SAME, decision
                group.counted_hours, group.basis = log_hours, "time-log hours (confirmed one event)"
            else:
                group.status, group.decision = CONFIRMED_DIFFERENT, decision
                group.counted_hours = None if reg_hours is None or log_hours is None else reg_hours + log_hours
                group.basis = "register + time-log hours (confirmed different events)"
            if group.decision is not None:
                group.notes.append(f"decision #{decision.id} by {decision.confirmer} {decision.confirmed_at}: "
                                   f"{decision.reason}")
        groups.append(group)
    groups.sort(key=lambda g: (g.date, g.register_ids, g.log_ids))
    return Reconciliation(groups, list(excluded))


def reconcile_scope(db, well_id: int, wellbore_id: Optional[int] = None) -> Reconciliation:
    register, logs, decisions, excluded = load(db, well_id, wellbore_id)
    return reconcile(register, logs, decisions, excluded)


# ---- audited decision (append-only) -------------------------------------------------------------------------------
def record_decision(db, well_id: int, register_ids: Sequence[int], log_ids: Sequence[int], *, decision: str,
                    evidence: str, reason: str, wellbore_id: Optional[int] = None) -> int:
    """Record a user decision for one UNCERTAIN group; returns its id. The rows are re-read and must still form
    exactly that UNCERTAIN group; the confirming user is the identified actor of this session; a mandatory audit
    record is added in the same transaction. Earlier decisions are never changed."""
    from core.database import NPTEventDecision, User

    if decision not in DECISIONS:
        raise ReconciliationError(f"The decision must be one of {', '.join(DECISIONS)}.")
    evidence, reason = (evidence or "").strip(), (reason or "").strip()
    if not evidence:
        raise ReconciliationError("A decision needs the evidence it rests on (report, log, document).")
    if not reason:
        raise ReconciliationError("A decision needs a reason.")
    key = (tuple(sorted(register_ids)), tuple(sorted(log_ids)))
    register, logs, _decisions, _excluded = load(db, well_id, wellbore_id)   # the group as the user saw it
    current = reconcile(register, logs, ())
    group = next((g for g in current.groups if (g.register_ids, g.log_ids) == key), None)
    if group is None or group.status != UNCERTAIN:
        raise ReconciliationError("These rows are not an UNCERTAIN group of this well now (they changed, or the "
                                  "match is already certain); nothing was recorded.")
    user_id, username = db._audit_actor()
    with db.session_scope() as session:
        if user_id is None or session.get(User, user_id) is None:
            raise ReconciliationError("A decision must be confirmed by an identified user of this database.")
        row = NPTEventDecision(well_id=well_id, register_ids_json=json.dumps(list(key[0])),
                               time_log_ids_json=json.dumps(list(key[1])),
                               rows_sha256=rows_sha256(group.register, group.logs), decision=decision,
                               group_label="; ".join(r.label() for r in group.register)[:300],
                               evidence=evidence, reason=reason, confirmed_by=user_id,
                               method_version=DECISION_VERSION)
        session.add(row)
        session.flush()
        db._add_mandatory_audit(session, "npt_event_decision", "well", well_id, f"well #{well_id}",
                                json.dumps({"decision_id": row.id, "decision": decision, "register": list(key[0]),
                                            "time_logs": list(key[1])}, sort_keys=True))
        return row.id


# ---- export ------------------------------------------------------------------------------------------------------
def export_csv(path: str, recon: Reconciliation, *, well_label: str, scope_label: str) -> int:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        out = csv.writer(handle)
        out.writerow(["NPT event reconciliation", RECON_METHOD])
        out.writerow(["Well", well_label])
        out.writerow(["Scope", scope_label])
        out.writerow(["Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")])
        out.writerow(["Sources", "npt_reports (register) and time_logs_24h rows marked NPT; empty = unknown"])
        out.writerow(["Totals", recon.summary()])
        out.writerow([])
        out.writerow(COLUMNS)
        for group in recon.groups:
            out.writerow(["" if v is None else v for v in group.table_row()])
        if recon.excluded:
            out.writerow([])
            out.writerow(["Excluded from this scope"])
            for line in recon.excluded:
                out.writerow([line])
    return len(recon.groups)
