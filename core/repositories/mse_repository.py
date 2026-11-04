"""Persistence + historical reconstruction for MSE (Teale) runs.

DrillMaster's FIFTH calculation-history repository. Like the Casing / Cement
repositories, it is an INDEPENDENT concrete implementation that follows the same
principles as the Torque & Drag repository (single ``session_scope`` unit of
work; a detached, reload-safe ``SavedMSECalculation``; whole-result verification
via the shared engine-agnostic core) but does not share code with any of them
beyond the verification core, because MSE's snapshot/reconstruction are
engine-specific.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.database import MSECalculationRecord, MSELineageRepair
from core.engineering.calculation_verification import (
    VERIFY_UNREADABLE,
    VerificationOutcome,
    classify_verification,
)
from core.engineering.mse_persistence import (
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    result_summary,
)
from core.repositories.base import BaseRepository

# Lineage versions: 1 (M104) wellbore / report / input source recorded at save; 2 (M123, D6) also the measured
# depth when (and only when) the user entered it, and the units of the frozen inputs.  NULL = legacy run.
LINEAGE_VERSION = 2
MANUAL_ENTRY = "manual entry (W13 Bit Hydraulics)"
#: The one label for a run saved before any lineage was recorded (shown in OA, History and exports).
LEGACY_LABEL = "LEGACY — LINEAGE UNKNOWN — NOT DEPTH-REPRODUCIBLE"
REPAIR_METHOD_VERSION = "M123 MSE lineage repair v1"
#: Units of the frozen snapshot parameters (the keys already carry them; recorded explicitly from v2).
INPUT_UNITS = {"wob_lbf": "lbf", "rpm": "rpm", "torque_ft_lbf": "ft·lbf", "rop_ft_hr": "ft/h",
               "bit_diameter_in": "in"}
MD_UNITS = ("m", "ft")
REPAIRABLE_FIELDS = ("wellbore_id", "report_id", "md_m")
# Lineage classes (OA separates them; only "depth" runs carry a depth that can be reproduced).
CLASS_DEPTH = "depth (wellbore + entered MD)"
CLASS_WELLBORE = "wellbore"
CLASS_WELL = "whole-well"
CLASS_LEGACY = "unscoped legacy"
CLASS_NO_WELL = "no well (standalone)"


def md_in_metres(value, unit) -> float:
    """The entered MD in canonical metres (``core.unit_manager``); raises on an unusable entry."""
    from core.unit_manager import UnitManager

    if unit not in MD_UNITS:
        raise ValueError(f"Measured depth unit must be one of {', '.join(MD_UNITS)}.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Measured depth must be a number.") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Measured depth must be a positive, finite number.")
    return float(UnitManager.convert(number, "length", unit, "m"))


@dataclass(frozen=True)
class LineageRepair:
    """A detached view of one audited lineage repair (M123)."""

    id: int
    field: str
    wellbore_id: Optional[int]
    report_id: Optional[int]
    md_m: Optional[float]
    md_entered_value: Optional[float]
    md_entered_unit: Optional[str]
    value_label: str
    before_value: str
    evidence: str
    reason: str
    confirmed_by: int
    confirmer: str
    confirmed_at: Any
    method_version: str

    @property
    def value(self):
        return {"wellbore_id": self.wellbore_id, "report_id": self.report_id, "md_m": self.md_m}[self.field]

    @property
    def unlinked(self) -> bool:
        """The repaired reference was deleted later (report/wellbore delete): the value is unknown again."""
        return self.value is None


@dataclass
class SavedMSECalculation:
    """A detached, reload-safe view of one persisted MSE run.

    Plain data (no ORM instance, no live session) so callers/tests hold
    historical state that cannot be mutated by later activity. ``id`` is a
    storage handle, never an engineering identity.
    """

    id: int
    label: str
    method: str
    snapshot_schema_version: int
    input_snapshot: Dict[str, Any]
    result: Dict[str, Any]
    well_id: Optional[int]
    created_at: Any
    summary: Dict[str, Optional[float]] = field(default_factory=dict)
    # M104 lineage; all None for runs saved before lineage was recorded (``lineage_version`` None).
    wellbore_id: Optional[int] = None
    report_id: Optional[int] = None
    input_source: Optional[str] = None
    lineage_version: Optional[int] = None
    # M123 lineage v2 (None on older runs) and the audited repairs, oldest first.
    md_m: Optional[float] = None
    md_entered_value: Optional[float] = None
    md_entered_unit: Optional[str] = None
    input_units: Optional[Dict[str, str]] = None
    repairs: tuple = ()
    stored_mse_psi: Optional[float] = None        # the promoted ``mse_psi`` column, as stored

    @property
    def is_legacy(self) -> bool:
        return self.lineage_version is None

    def repair_for(self, name: str) -> Optional[LineageRepair]:
        """The latest repair of ``name`` whose value still exists (an unlinked repair no longer counts)."""
        live = [r for r in self.repairs if r.field == name and not r.unlinked]
        return live[-1] if live else None

    def _effective(self, name: str):
        recorded = getattr(self, name)
        if recorded is not None:
            return recorded
        repair = self.repair_for(name)
        return repair.value if repair is not None else None

    @property
    def effective_wellbore_id(self) -> Optional[int]:
        return self._effective("wellbore_id")

    @property
    def effective_report_id(self) -> Optional[int]:
        return self._effective("report_id")

    @property
    def effective_md_m(self) -> Optional[float]:
        return self._effective("md_m")

    @property
    def repaired_fields(self) -> List[str]:
        return [name for name in REPAIRABLE_FIELDS if getattr(self, name) is None and self.repair_for(name)]

    @property
    def lineage_class(self) -> str:
        return lineage_class(self.well_id, self.lineage_version, self.effective_wellbore_id, self.effective_md_m,
                             self.repaired_fields)

    def recalculate(self):
        """Re-run the real engine from this run's frozen snapshot."""
        return recalculate_from_snapshot(self.input_snapshot)

    def verify(self, current_method: Optional[str] = None) -> VerificationOutcome:
        """Compare the stored result against a fresh recalculation.

        Observational only — returns a ``VerificationOutcome`` and never mutates
        this record or the stored result. Compares the ENTIRE result via the
        shared deep numeric diff.
        """
        snap_method = (self.input_snapshot or {}).get("method")
        try:
            recalc = recalculate_from_snapshot(self.input_snapshot)
        except Exception as exc:
            method_matches = (current_method is None) or (snap_method == current_method)
            return VerificationOutcome(
                status=VERIFY_UNREADABLE,
                stored=dict(self.summary),
                method_matches=method_matches,
                detail=f"snapshot could not be reconstructed: {exc}",
            )
        outcome = classify_verification(
            self.result or {}, recalc,
            snapshot_method=snap_method, current_method=current_method)
        outcome.stored = dict(self.summary)
        if getattr(recalc, "success", False):
            outcome.recalculated = result_summary(recalc.values)
        return outcome

    @property
    def input_parameters(self) -> Dict[str, Any]:
        return dict(self.input_snapshot.get("parameters", {}) or {})


def lineage_class(well_id, lineage_version, wellbore_id, md_m, repaired=()) -> str:
    """Whole-well / wellbore / depth / unscoped legacy, from the EFFECTIVE (recorded or repaired) lineage."""
    if well_id is None:
        return CLASS_NO_WELL
    if lineage_version is None and not repaired:
        return CLASS_LEGACY
    if wellbore_id is not None and md_m is not None:
        base = CLASS_DEPTH
    elif wellbore_id is not None:
        base = CLASS_WELLBORE
    else:
        base = CLASS_WELL
    return f"{base} (repaired: {', '.join(repaired)})" if repaired else base


def _check_lineage(session, well_id, wellbore_id, report_id) -> None:
    """A recorded wellbore or report must exist and belong to the run's well (no invented relation)."""
    from core.database import DailyReport, Wellbore

    if (wellbore_id is not None or report_id is not None) and well_id is None:
        raise ValueError("A wellbore or report can only be recorded for an MSE run saved to a well.")
    if wellbore_id is not None:
        bore = session.get(Wellbore, wellbore_id)
        if bore is None or bore.well_id != well_id:
            raise ValueError(f"Wellbore {wellbore_id} is not a wellbore of well {well_id}.")
    if report_id is not None:
        report = session.get(DailyReport, report_id)
        if report is None or report.well_id != well_id:
            raise ValueError(f"Daily report {report_id} is not a report of well {well_id}.")
        if wellbore_id is not None and report.wellbore_id not in (None, wellbore_id):
            raise ValueError(f"Daily report {report_id} belongs to another wellbore.")


class MSECalculationRepository(BaseRepository):
    """Save / load / reconstruct MSE (Teale) calculation history."""

    def save_run(
        self,
        *,
        inputs: Mapping[str, Any],
        result_values: Mapping[str, Any],
        method: str,
        label: str = "",
        well_id: Optional[int] = None,
        created_by: Optional[int] = None,
        wellbore_id: Optional[int] = None,
        report_id: Optional[int] = None,
        input_source: str = MANUAL_ENTRY,
        md_value: Optional[float] = None,
        md_unit: Optional[str] = None,
    ) -> int:
        """Persist ONE MSE run as an immutable historical record; returns id.

        Builds the canonical snapshot from the *exact* inputs used (already in
        canonical engine units), stores it with the derived result and promoted
        summary columns, all in a single ``session_scope`` unit of work so a
        failure leaves no partial row. Each call is a distinct run — never
        deduplicated.

        M123: ``md_value``/``md_unit`` are recorded only when the user entered them, and only together with
        the wellbore the depth was measured in; nothing derives a depth.
        """
        md_m = None
        if md_value is not None or md_unit is not None:
            if wellbore_id is None:
                raise ValueError("A measured depth can only be recorded with the wellbore it was measured in.")
            md_m = md_in_metres(md_value, md_unit)
        snapshot = build_snapshot(inputs=inputs, method=method)
        summary = result_summary(result_values or {})

        with self.db.session_scope() as session:
            _check_lineage(session, well_id, wellbore_id, report_id)
            record = MSECalculationRecord(
                well_id=well_id,
                label=label or "",
                method=method,
                snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
                input_snapshot_json=snapshot,
                result_json=dict(result_values or {}),
                mse_psi=summary.get("mse_psi"),
                axial_term_psi=summary.get("axial_term_psi"),
                rotary_term_psi=summary.get("rotary_term_psi"),
                bit_area_in2=summary.get("bit_area_in2"),
                created_by=created_by,
                wellbore_id=wellbore_id,
                report_id=report_id,
                input_source=(input_source or MANUAL_ENTRY)[:80],
                lineage_version=LINEAGE_VERSION,
                md_m=md_m,
                md_entered_value=float(md_value) if md_m is not None else None,
                md_entered_unit=md_unit if md_m is not None else None,
                input_units_json=dict(INPUT_UNITS),
            )
            session.add(record)
            session.flush()
            return record.id

    def get(self, calc_id: int) -> Optional[SavedMSECalculation]:
        with self.db.session_scope() as session:
            row = session.get(MSECalculationRecord, calc_id)
            return self._to_saved(row, _repairs_by_run(session, [row.id]).get(row.id, ())) if row else None

    def all(self) -> List[SavedMSECalculation]:
        """All persisted runs, newest first (deterministic: created_at, id)."""
        with self.db.session_scope() as session:
            rows = (
                session.query(MSECalculationRecord)
                .order_by(
                    MSECalculationRecord.created_at.desc(),
                    MSECalculationRecord.id.desc(),
                )
                .all()
            )
            repairs = _repairs_by_run(session, [r.id for r in rows])
            return [self._to_saved(r, repairs.get(r.id, ())) for r in rows]

    def count(self) -> int:
        with self.db.session_scope() as session:
            return session.query(MSECalculationRecord).count()

    def repair_choices(self, calc_id: int) -> Dict[str, Any]:
        """Plain choices for a repair of run ``calc_id``: the wellbores and reports of ITS well only (M123)."""
        from core.database import DailyReport, Wellbore

        with self.db.session_scope() as session:
            row = session.get(MSECalculationRecord, calc_id)
            if row is None or row.well_id is None:
                return {"wellbores": [], "reports": []}
            bores = [(b.id, b.name or f"wellbore #{b.id}") for b in session.query(Wellbore)
                     .filter(Wellbore.well_id == row.well_id).order_by(Wellbore.id)]
            reports = [(r.id, f"Report #{r.report_number} ({r.report_date})", r.wellbore_id)
                       for r in session.query(DailyReport).filter(DailyReport.well_id == row.well_id)
                       .order_by(DailyReport.report_date, DailyReport.id)]
            return {"wellbores": bores, "reports": reports}

    def confirmer_label(self) -> Optional[str]:
        """The identified user who would confirm a repair now, or None (repairs are then refused)."""
        user_id, username = self.db._audit_actor()
        return (username or f"user #{user_id}") if user_id is not None else None

    def repair_lineage(self, calc_id: int, field_name: str, *, evidence: str, reason: str,
                       wellbore_id: Optional[int] = None, report_id: Optional[int] = None,
                       md_value: Optional[float] = None, md_unit: Optional[str] = None) -> int:
        """Record ONE audited repair of an unknown lineage field of a stored run (M123, D6); returns its id.

        Never infers: the caller supplies the value, the evidence it rests on and the reason; the confirming
        user is the identified actor of this session.  Only a field that is unknown on the record (and has no
        live repair) can be repaired, the value must belong to the run's well, and the run record is never
        written.  A mandatory audit record is added in the same transaction.
        """
        from core.database import DailyReport, User, Wellbore

        if field_name not in REPAIRABLE_FIELDS:
            raise ValueError(f"Only {', '.join(REPAIRABLE_FIELDS)} can be repaired.")
        evidence, reason = (evidence or "").strip(), (reason or "").strip()
        if not evidence:
            raise ValueError("A lineage repair needs the evidence it rests on (document, report, log).")
        if not reason:
            raise ValueError("A lineage repair needs a reason.")
        given = {"wellbore_id": wellbore_id is not None, "report_id": report_id is not None,
                 "md_m": md_value is not None or md_unit is not None}
        if [name for name, present in given.items() if present] != [field_name]:
            raise ValueError(f"Give exactly the value of {field_name} and nothing else.")
        user_id, username = self.db._audit_actor()
        with self.db.session_scope() as session:
            if user_id is None or session.get(User, user_id) is None:
                raise ValueError("A lineage repair must be confirmed by an identified user of this database.")
            row = session.get(MSECalculationRecord, calc_id)
            if row is None:
                raise ValueError(f"MSE run {calc_id} does not exist.")
            if row.well_id is None:
                raise ValueError("A run saved without a well cannot be repaired: assigning a well would be inference.")
            saved = self._to_saved(row, _repairs_by_run(session, [row.id]).get(row.id, ()))
            if getattr(saved, field_name) is not None:
                raise ValueError(f"{field_name} is recorded on this run; recorded lineage is never overwritten.")
            if saved.repair_for(field_name) is not None:
                raise ValueError(f"{field_name} was already repaired; a repair is never overwritten.")
            values: Dict[str, Any] = {}
            if field_name == "wellbore_id":
                bore = session.get(Wellbore, wellbore_id)
                if bore is None or bore.well_id != row.well_id:
                    raise ValueError(f"Wellbore {wellbore_id} is not a wellbore of well {row.well_id}.")
                bore_report = session.get(DailyReport, saved.effective_report_id) if saved.effective_report_id \
                    else None
                if bore_report is not None and bore_report.wellbore_id not in (None, wellbore_id):
                    raise ValueError("The run's report belongs to another wellbore.")
                values["wellbore_id"] = wellbore_id
                label = f"{bore.name or 'wellbore'} (wellbore #{bore.id})"
            elif field_name == "report_id":
                report = session.get(DailyReport, report_id)
                if report is None or report.well_id != row.well_id:
                    raise ValueError(f"Daily report {report_id} is not a report of well {row.well_id}.")
                bore = saved.effective_wellbore_id
                if bore is not None and report.wellbore_id not in (None, bore):
                    raise ValueError(f"Daily report {report_id} belongs to another wellbore.")
                values["report_id"] = report_id
                label = f"Report #{report.report_number} ({report.report_date})"
            else:
                if saved.effective_wellbore_id is None:
                    raise ValueError("A measured depth can only be recorded with the wellbore it was measured in "
                                     "(record or repair the wellbore first).")
                values.update(md_m=md_in_metres(md_value, md_unit), md_entered_value=float(md_value),
                              md_entered_unit=md_unit)
                label = f"{float(md_value):g} {md_unit}"
            before = ("unknown (legacy run: no lineage recorded)" if saved.is_legacy
                      else "unknown (not recorded at save)")
            repair = MSELineageRepair(mse_calculation_id=row.id, well_id=row.well_id, field=field_name,
                                      value_label=label[:200], before_value=before, evidence=evidence,
                                      reason=reason, confirmed_by=user_id, method_version=REPAIR_METHOD_VERSION,
                                      **values)
            session.add(repair)
            session.flush()
            self.db._add_mandatory_audit(
                session, "lineage_repair", "mse_calculation", row.id, row.label or f"MSE run #{row.id}",
                json.dumps({"repair_id": repair.id, "field": field_name, "before": before, "after": label[:120]},
                           sort_keys=True, ensure_ascii=False))
            return repair.id

    @staticmethod
    def _to_saved(row: MSECalculationRecord, repairs=()) -> SavedMSECalculation:
        return SavedMSECalculation(
            id=row.id,
            label=row.label or "",
            method=row.method,
            snapshot_schema_version=(row.snapshot_schema_version
                                     or SNAPSHOT_SCHEMA_VERSION),
            input_snapshot=dict(row.input_snapshot_json or {}),
            result=dict(row.result_json or {}),
            well_id=row.well_id,
            created_at=row.created_at,
            summary=result_summary(row.result_json or {}),
            wellbore_id=row.wellbore_id,
            report_id=row.report_id,
            input_source=row.input_source,
            lineage_version=row.lineage_version,
            md_m=row.md_m,
            md_entered_value=row.md_entered_value,
            md_entered_unit=row.md_entered_unit,
            input_units=dict(row.input_units_json) if isinstance(row.input_units_json, dict) else None,
            repairs=tuple(repairs),
            stored_mse_psi=row.mse_psi,
        )


def _repairs_by_run(session, run_ids) -> Dict[int, tuple]:
    """Detached repairs per run id, oldest first (confirmer name resolved here; plain data only)."""
    from core.database import User

    if not run_ids:
        return {}
    out: Dict[int, list] = {}
    rows = (session.query(MSELineageRepair, User.username)
            .outerjoin(User, User.id == MSELineageRepair.confirmed_by)
            .filter(MSELineageRepair.mse_calculation_id.in_(list(run_ids)))
            .order_by(MSELineageRepair.confirmed_at, MSELineageRepair.id))
    for repair, username in rows:
        out.setdefault(repair.mse_calculation_id, []).append(LineageRepair(
            id=repair.id, field=repair.field, wellbore_id=repair.wellbore_id, report_id=repair.report_id,
            md_m=repair.md_m, md_entered_value=repair.md_entered_value, md_entered_unit=repair.md_entered_unit,
            value_label=repair.value_label, before_value=repair.before_value, evidence=repair.evidence,
            reason=repair.reason, confirmed_by=repair.confirmed_by, confirmer=username or f"user #{repair.confirmed_by}",
            confirmed_at=repair.confirmed_at, method_version=repair.method_version))
    return {key: tuple(value) for key, value in out.items()}


def runs_for_well(session, well_id: int) -> List[SavedMSECalculation]:
    """Every stored run of ``well_id`` with its repairs, oldest first (OA reads through this, M123)."""
    rows = (session.query(MSECalculationRecord).filter(MSECalculationRecord.well_id == well_id)
            .order_by(MSECalculationRecord.created_at, MSECalculationRecord.id).all())
    repairs = _repairs_by_run(session, [r.id for r in rows])
    return [MSECalculationRepository._to_saved(r, repairs.get(r.id, ())) for r in rows]
