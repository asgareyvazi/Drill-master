"""Persistence + historical reconstruction for Well Control kill-sheet runs.

DrillMaster's FOURTH calculation-history repository — and the first for a
*composite* calculation. Like the Casing / Cement repositories it is an
INDEPENDENT concrete implementation that follows the proven principles (single
``session_scope`` unit of work; a detached, reload-safe saved view;
whole-result verification via the shared engine-agnostic core), but it shares no
code beyond that verification core because the kill sheet's snapshot and
reconstruction are composite-specific.

The composite owns the historical claim: verification reconstructs the frozen
canonical inputs and re-runs the whole ``compute_kill_sheet`` (all three
sub-engines + derived arithmetic + schedule), then compares the ENTIRE stored
result against the recalculation. Sub-engine results are never stored or
verified independently (mission §51).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.database import WellControlKillSheetCalculationRecord
from core.engineering.calculation_verification import (
    VERIFY_UNREADABLE,
    VerificationOutcome,
    classify_verification,
)
from core.engineering.well_control_kill_sheet_persistence import (
    SNAPSHOT_SCHEMA_VERSION,
    recalculate_from_snapshot,
    result_summary,
)
from core.repositories.base import BaseRepository


@dataclass
class SavedKillSheetCalculation:
    """A detached, reload-safe view of one persisted kill-sheet run.

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
        """Re-run the real composite from this run's frozen snapshot."""
        return recalculate_from_snapshot(self.input_snapshot)

    def verify(self, current_method: Optional[str] = None) -> VerificationOutcome:
        """Compare the stored result against a fresh recalculation.

        Observational only — returns a ``VerificationOutcome`` and never mutates
        this record or the stored result. Compares the ENTIRE composite result,
        including the nested string/annular detail lists and the full choke
        schedule (via the shared deep numeric diff). A reconstruction/compute
        exception maps to UNREADABLE; a composite that runs but whose result
        differs maps to DIFFERENT; a composite that cannot run maps to
        NOT_REPRODUCIBLE.
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
    def canonical_inputs(self) -> Dict[str, Any]:
        return dict(self.input_snapshot.get("canonical_inputs", {}) or {})

    @property
    def display_inputs(self) -> Dict[str, Any]:
        return dict(self.input_snapshot.get("display", {}) or {})


class WellControlKillSheetRepository(BaseRepository):
    """Save / load / reconstruct Well Control kill-sheet calculation history."""

    def save_run(
        self,
        *,
        snapshot: Mapping[str, Any],
        result: Mapping[str, Any],
        method: str,
        label: str = "",
        well_id: Optional[int] = None,
        created_by: Optional[int] = None,
    ) -> int:
        """Persist ONE kill-sheet run as an immutable historical record; id.

        Stores the frozen composite snapshot with the whole derived result and
        promoted summary columns, all in a single ``session_scope`` unit of work
        so a failure leaves no partial row (mission §53 — no partial saved
        calculation). Each call is a distinct run — never deduplicated (mission
        §43: two saves of the same sheet are two executions).

        The caller passes the snapshot already built from the exact
        ``WellControlKillSheetInputs`` the composite consumed (via
        ``well_control_kill_sheet_persistence.build_snapshot``) and the whole
        ``KillSheetResult.as_dict()`` result, so this repository performs no
        engineering and no unit conversion.
        """
        summary = result_summary(result or {})

        with self.db.session_scope() as session:
            record = WellControlKillSheetCalculationRecord(
                well_id=well_id,
                label=label or "",
                method=method,
                snapshot_schema_version=snapshot.get(
                    "schema_version", SNAPSHOT_SCHEMA_VERSION),
                input_snapshot_json=dict(snapshot),
                result_json=dict(result or {}),
                kill_mw_ppg=summary.get("kill_mw_ppg"),
                icp_psi=summary.get("icp_psi"),
                fcp_psi=summary.get("fcp_psi"),
                maasp_psi=summary.get("maasp_psi"),
                total_well_vol_bbl=summary.get("total_well_vol_bbl"),
                stk_total=summary.get("stk_total"),
                kick_height_ft=summary.get("kick_height_ft"),
                created_by=created_by,
            )
            session.add(record)
            session.flush()
            return record.id

    def get(self, calc_id: int) -> Optional[SavedKillSheetCalculation]:
        with self.db.session_scope() as session:
            row = session.get(WellControlKillSheetCalculationRecord, calc_id)
            return self._to_saved(row) if row else None

    def all(self) -> List[SavedKillSheetCalculation]:
        """All persisted runs, newest first (deterministic: created_at, id)."""
        with self.db.session_scope() as session:
            rows = (
                session.query(WellControlKillSheetCalculationRecord)
                .order_by(
                    WellControlKillSheetCalculationRecord.created_at.desc(),
                    WellControlKillSheetCalculationRecord.id.desc(),
                )
                .all()
            )
            return [self._to_saved(r) for r in rows]

    def count(self) -> int:
        with self.db.session_scope() as session:
            return session.query(WellControlKillSheetCalculationRecord).count()

    @staticmethod
    def _to_saved(row: WellControlKillSheetCalculationRecord) -> SavedKillSheetCalculation:
        return SavedKillSheetCalculation(
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
