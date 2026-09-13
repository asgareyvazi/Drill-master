"""Persistence + historical reconstruction for Casing-strength calculation runs.

DrillMaster's SECOND calculation-history repository. It is an INDEPENDENT
concrete implementation that follows the same principles as the Torque & Drag
repository (single ``session_scope`` unit of work; a detached, reload-safe
``SavedCasingCalculation``; whole-result verification via the shared
engine-agnostic core) but does not share code with it beyond the verification
core, because casing's snapshot/reconstruction are engine-specific.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.database import CasingCalculationRecord
from core.engineering.calculation_verification import (
    VERIFY_UNREADABLE,
    VerificationOutcome,
    classify_verification,
)
from core.engineering.casing_persistence import (
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    result_summary,
)
from core.repositories.base import BaseRepository


@dataclass
class SavedCasingCalculation:
    """A detached, reload-safe view of one persisted casing-strength run.

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

    def recalculate(self):
        """Re-run the real engine from this run's frozen snapshot."""
        return recalculate_from_snapshot(self.input_snapshot)

    def verify(self, current_method: Optional[str] = None) -> VerificationOutcome:
        """Compare the stored result against a fresh recalculation.

        Observational only — returns a ``VerificationOutcome`` and never mutates
        this record or the stored result. Compares the ENTIRE numeric result.
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


class CasingCalculationRepository(BaseRepository):
    """Save / load / reconstruct Casing-strength calculation history."""

    def save_run(
        self,
        *,
        inputs: Mapping[str, Any],
        result_values: Mapping[str, Any],
        method: str,
        label: str = "",
        well_id: Optional[int] = None,
        created_by: Optional[int] = None,
    ) -> int:
        """Persist ONE casing run as an immutable historical record; returns id.

        Builds the canonical snapshot from the *exact* inputs used, stores it
        with the derived result and promoted summary columns, all in a single
        ``session_scope`` unit of work so a failure leaves no partial row. Each
        call is a distinct run — never deduplicated.
        """
        snapshot = build_snapshot(inputs=inputs, method=method)
        summary = result_summary(result_values or {})

        with self.db.session_scope() as session:
            record = CasingCalculationRecord(
                well_id=well_id,
                label=label or "",
                method=method,
                snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
                input_snapshot_json=snapshot,
                result_json=dict(result_values or {}),
                burst_rating_psi=summary.get("burst_rating_psi"),
                collapse_rating_psi=summary.get("collapse_rating_psi"),
                pipe_body_yield_lbf=summary.get("pipe_body_yield_lbf"),
                governing_burst_psi=summary.get("governing_burst_psi"),
                governing_collapse_psi=summary.get("governing_collapse_psi"),
                governing_tension_lbf=summary.get("governing_tension_lbf"),
                created_by=created_by,
            )
            session.add(record)
            session.flush()
            return record.id

    def get(self, calc_id: int) -> Optional[SavedCasingCalculation]:
        with self.db.session_scope() as session:
            row = session.get(CasingCalculationRecord, calc_id)
            return self._to_saved(row) if row else None

    def all(self) -> List[SavedCasingCalculation]:
        """All persisted runs, newest first (deterministic: created_at, id)."""
        with self.db.session_scope() as session:
            rows = (
                session.query(CasingCalculationRecord)
                .order_by(
                    CasingCalculationRecord.created_at.desc(),
                    CasingCalculationRecord.id.desc(),
                )
                .all()
            )
            return [self._to_saved(r) for r in rows]

    def count(self) -> int:
        with self.db.session_scope() as session:
            return session.query(CasingCalculationRecord).count()

    @staticmethod
    def _to_saved(row: CasingCalculationRecord) -> SavedCasingCalculation:
        return SavedCasingCalculation(
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
        )
