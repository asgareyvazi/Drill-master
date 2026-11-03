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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.database import MSECalculationRecord
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

LINEAGE_VERSION = 1          # M104: wellbore / report / input source recorded at save
MANUAL_ENTRY = "manual entry (W13 Bit Hydraulics)"


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
    ) -> int:
        """Persist ONE MSE run as an immutable historical record; returns id.

        Builds the canonical snapshot from the *exact* inputs used (already in
        canonical engine units), stores it with the derived result and promoted
        summary columns, all in a single ``session_scope`` unit of work so a
        failure leaves no partial row. Each call is a distinct run — never
        deduplicated.
        """
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
            )
            session.add(record)
            session.flush()
            return record.id

    def get(self, calc_id: int) -> Optional[SavedMSECalculation]:
        with self.db.session_scope() as session:
            row = session.get(MSECalculationRecord, calc_id)
            return self._to_saved(row) if row else None

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
            return [self._to_saved(r) for r in rows]

    def count(self) -> int:
        with self.db.session_scope() as session:
            return session.query(MSECalculationRecord).count()

    @staticmethod
    def _to_saved(row: MSECalculationRecord) -> SavedMSECalculation:
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
        )
