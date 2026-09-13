"""Persistence + historical reconstruction for Torque & Drag calculation runs.

This is the controlled seam between a live ``TorqueDragEngine`` execution and
the database. It saves a *complete self-contained historical snapshot* of a run
and reconstructs it later so the calculation can be re-executed and checked,
independently of the mutable DrillPipe master catalog.

It reuses the existing ``BaseRepository`` / ``session_scope`` unit-of-work — no
new transaction abstraction — and the Qt-free snapshot domain in
``core.engineering.torque_drag_persistence``. No engine physics is reimplemented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from core.database import TorqueDragCalculationRecord
from core.engineering.torque_drag_persistence import (
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    recalculate_from_snapshot,
    reference_fingerprints,
    result_summary,
)
from core.repositories.base import BaseRepository


@dataclass
class SavedCalculation:
    """A detached, reload-safe view of one persisted T&D run.

    Deliberately plain data (no ORM instance, no live session) so callers and
    tests hold historical state that cannot be mutated by later catalog or
    session activity. ``id`` is a storage handle, never an engineering identity.
    """

    id: int
    label: str
    method: str
    snapshot_schema_version: int
    input_snapshot: Dict[str, Any]
    result: Dict[str, Any]
    reference_fingerprints: List[str]
    well_id: Optional[int]
    created_at: Any
    summary: Dict[str, Optional[float]]

    def recalculate(self):
        """Re-run the real engine from this run's frozen snapshot."""
        return recalculate_from_snapshot(self.input_snapshot)


class TorqueDragCalculationRepository(BaseRepository):
    """Save / load / reconstruct Torque & Drag calculation history."""

    def save_run(
        self,
        *,
        survey: List[Mapping[str, Any]],
        components: List[Mapping[str, Any]],
        mud_density_ppg: Any,
        friction_factor: Any,
        result_values: Mapping[str, Any],
        method: str,
        wob_klbf: Any = 0.0,
        wellbore_id_in: Any = None,
        label: str = "",
        well_id: Optional[int] = None,
        created_by: Optional[int] = None,
    ) -> int:
        """Persist ONE T&D run as an immutable historical record; returns its id.

        Builds the canonical snapshot from the *exact* inputs used, stores it
        together with the derived result and promoted summary columns, all in a
        single ``session_scope`` unit of work so a failure leaves no partial
        row (mission §15). Each call is a distinct run — never deduplicated.
        """
        snapshot = build_snapshot(
            survey=survey,
            components=components,
            mud_density_ppg=mud_density_ppg,
            friction_factor=friction_factor,
            wob_klbf=wob_klbf,
            wellbore_id_in=wellbore_id_in,
            method=method,
        )
        summary = result_summary(result_values or {})
        fps = reference_fingerprints(snapshot)

        with self.db.session_scope() as session:
            record = TorqueDragCalculationRecord(
                well_id=well_id,
                label=label or "",
                method=method,
                snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
                input_snapshot_json=snapshot,
                result_json=dict(result_values or {}),
                reference_fingerprints_json=fps,
                hookload_pickup_klbf=summary.get("hookload_pickup"),
                hookload_slackoff_klbf=summary.get("hookload_slackoff"),
                hookload_rotating_klbf=summary.get("hookload_rotating"),
                surface_torque_rotating_ft_lbf=summary.get(
                    "surface_torque_rotating_ft_lbf"),
                total_buoyed_weight_klbf=summary.get("total_buoyed_weight"),
                created_by=created_by,
            )
            session.add(record)
            session.flush()
            return record.id

    def get(self, calc_id: int) -> Optional[SavedCalculation]:
        with self.db.session_scope() as session:
            row = session.get(TorqueDragCalculationRecord, calc_id)
            return self._to_saved(row) if row else None

    def all(self) -> List[SavedCalculation]:
        """All persisted runs, newest first (deterministic: created_at, id)."""
        with self.db.session_scope() as session:
            rows = (
                session.query(TorqueDragCalculationRecord)
                .order_by(
                    TorqueDragCalculationRecord.created_at.desc(),
                    TorqueDragCalculationRecord.id.desc(),
                )
                .all()
            )
            return [self._to_saved(r) for r in rows]

    def count(self) -> int:
        with self.db.session_scope() as session:
            return session.query(TorqueDragCalculationRecord).count()

    @staticmethod
    def _to_saved(row: TorqueDragCalculationRecord) -> SavedCalculation:
        snapshot = dict(row.input_snapshot_json or {})
        return SavedCalculation(
            id=row.id,
            label=row.label or "",
            method=row.method,
            snapshot_schema_version=row.snapshot_schema_version or SNAPSHOT_SCHEMA_VERSION,
            input_snapshot=snapshot,
            result=dict(row.result_json or {}),
            reference_fingerprints=list(row.reference_fingerprints_json or []),
            well_id=row.well_id,
            created_at=row.created_at,
            summary=result_summary(row.result_json or {}),
        )
