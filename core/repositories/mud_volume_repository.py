"""Persistence + historical reconstruction for Mud Volume balance runs.

DrillMaster's SIXTH calculation-history repository. Like the Casing / Cement /
MSE repositories, it is an INDEPENDENT concrete implementation that follows the
same principles as the Torque & Drag repository (single ``session_scope`` unit
of work; a detached, reload-safe ``SavedMudVolumeCalculation``; whole-result
verification via the shared engine-agnostic core) but does not share code with
any of them beyond the verification core, because the mud volume
snapshot/reconstruction are engine-specific.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.database import MudVolumeCalculationRecord
from core.engineering.calculation_verification import (
    VERIFY_UNREADABLE,
    VerificationOutcome,
    classify_verification,
)
from core.engineering.mud_volume_persistence import (
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    result_summary,
)
from core.repositories.base import BaseRepository


@dataclass
class SavedMudVolumeCalculation:
    """A detached, reload-safe view of one persisted mud volume balance run.

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


class MudVolumeCalculationRepository(BaseRepository):
    """Save / load / reconstruct Mud Volume balance calculation history."""

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
        """Persist ONE balance run as an immutable historical record; returns id.

        Builds the canonical snapshot from the *exact* inputs used, stores it
        with the derived result and promoted summary columns, all in a single
        ``session_scope`` unit of work so a failure leaves no partial row. Each
        call is a distinct run — never deduplicated.
        """
        snapshot = build_snapshot(inputs=inputs, method=method)
        summary = result_summary(result_values or {})

        with self.db.session_scope() as session:
            record = MudVolumeCalculationRecord(
                well_id=well_id,
                label=label or "",
                method=method,
                snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
                input_snapshot_json=snapshot,
                result_json=dict(result_values or {}),
                active_volume_bbl=summary.get("active_volume_bbl"),
                final_volume_bbl=summary.get("final_volume_bbl"),
                net_change_bbl=summary.get("net_change_bbl"),
                created_by=created_by,
            )
            session.add(record)
            session.flush()
            return record.id

    def get(self, calc_id: int) -> Optional[SavedMudVolumeCalculation]:
        with self.db.session_scope() as session:
            row = session.get(MudVolumeCalculationRecord, calc_id)
            return self._to_saved(row) if row else None

    def all(self) -> List[SavedMudVolumeCalculation]:
        """All persisted runs, newest first (deterministic: created_at, id)."""
        with self.db.session_scope() as session:
            rows = (
                session.query(MudVolumeCalculationRecord)
                .order_by(
                    MudVolumeCalculationRecord.created_at.desc(),
                    MudVolumeCalculationRecord.id.desc(),
                )
                .all()
            )
            return [self._to_saved(r) for r in rows]

    def count(self) -> int:
        with self.db.session_scope() as session:
            return session.query(MudVolumeCalculationRecord).count()

    @staticmethod
    def _to_saved(row: MudVolumeCalculationRecord) -> SavedMudVolumeCalculation:
        return SavedMudVolumeCalculation(
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
