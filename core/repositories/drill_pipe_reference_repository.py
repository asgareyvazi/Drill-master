"""Drill-pipe reference-catalog repository (global engineering master data).

This is the controlled persistence seam between the canonical
:class:`core.engineering.drill_pipe.DrillPipeSpec` and the database. It exists so
that a future real vendor-import path and a future reference selector both go
through ONE place that enforces the mission's safety contract:

* deterministic identity (``DrillPipeSpec.identity_fingerprint`` — a UNIQUE
  natural key, never a row index);
* **no silent overwrite** of a stored engineering spec;
* **no silent conflict resolution** — a conflicting incoming spec is rejected
  with evidence, never merged over the stored one;
* **no fabrication** — a spec that cannot establish identity, or that carries a
  hard normalization issue, is rejected;
* transactional integrity via the existing ``session_scope`` unit of work.

It reuses the existing ``BaseRepository`` / ``session_scope`` infrastructure and
the existing custom auto-migration (the ``drill_pipe_specs`` table is created by
``DatabaseManager`` on initialize). No new persistence framework is introduced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.database import DrillPipeSpecRecord
from core.engineering.drill_pipe import (
    CONFLICTING,
    DUPLICATE,
    IDENTICAL,
    DrillPipeSpec,
    classify_duplicate,
)
from core.repositories.base import BaseRepository


# Per-row import outcomes (mission §17/§20 taxonomy).
NEW = "NEW"
UNCHANGED = "UNCHANGED"          # IDENTICAL to stored
ENRICHED = "ENRICHED"            # DUPLICATE that filled gaps, non-destructively
CONFLICT = "CONFLICT"            # same identity, contradictory values -> rejected
INVALID = "INVALID"             # unusable spec (no identity / hard issue) -> rejected


@dataclass
class RowResult:
    outcome: str
    identity_fingerprint: Optional[str] = None
    detail: str = ""


@dataclass
class ImportSummary:
    rows_seen: int = 0
    inserted: int = 0
    unchanged: int = 0
    enriched: int = 0
    conflicting: int = 0
    invalid: int = 0
    rows: List[RowResult] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "rows_seen": self.rows_seen,
            "inserted": self.inserted,
            "unchanged": self.unchanged,
            "enriched": self.enriched,
            "conflicting": self.conflicting,
            "invalid": self.invalid,
            "rows": [{"outcome": r.outcome, "identity": r.identity_fingerprint,
                      "detail": r.detail} for r in self.rows],
        }


class DrillPipeReferenceRepository(BaseRepository):
    """Controlled CRUD + duplicate/conflict-aware upsert for drill-pipe specs."""

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get_by_identity(self, fingerprint: str) -> Optional[DrillPipeSpec]:
        with self.db.session_scope() as session:
            row = (
                session.query(DrillPipeSpecRecord)
                .filter(DrillPipeSpecRecord.identity_fingerprint == fingerprint)
                .one_or_none()
            )
            return self._to_spec(row) if row else None

    def get_spec(self, spec: DrillPipeSpec) -> Optional[DrillPipeSpec]:
        return self.get_by_identity(spec.identity_fingerprint())

    def all(self) -> List[DrillPipeSpec]:
        with self.db.session_scope() as session:
            return [self._to_spec(r) for r in session.query(DrillPipeSpecRecord).all()]

    def count(self) -> int:
        with self.db.session_scope() as session:
            return session.query(DrillPipeSpecRecord).count()

    # ------------------------------------------------------------------
    # Controlled upsert
    # ------------------------------------------------------------------
    def upsert(self, spec: DrillPipeSpec, *, created_by: Optional[int] = None) -> RowResult:
        """Insert or safely reconcile ONE spec. Never silently overwrites.

        * no identity, or any INVALID/CONFLICT normalization issue -> INVALID.
        * not present -> NEW (insert).
        * present and IDENTICAL -> UNCHANGED.
        * present and DUPLICATE (incoming only *adds* missing fields) -> ENRICHED
          (non-destructive: existing values are never changed).
        * present and CONFLICTING -> CONFLICT (rejected; stored row untouched).
        """
        if not spec.has_identity:
            return RowResult(INVALID, None, "no engineering identity (needs OD and weight)")
        # A spec whose identity-forming fields are themselves in conflict/invalid
        # must not enter the catalog.
        blocking = [i for i in spec.issues if i.field in _IDENTITY_FIELDS]
        if blocking:
            kinds = ", ".join(sorted({i.kind for i in blocking}))
            return RowResult(INVALID, spec.identity_fingerprint(),
                             f"identity field issue: {kinds}")

        fp = spec.identity_fingerprint()
        with self.db.session_scope() as session:
            existing = (
                session.query(DrillPipeSpecRecord)
                .filter(DrillPipeSpecRecord.identity_fingerprint == fp)
                .one_or_none()
            )
            if existing is None:
                values = spec.to_record_values()
                if created_by is not None:
                    values["created_by"] = created_by
                session.add(DrillPipeSpecRecord(**values))
                return RowResult(NEW, fp, "inserted")

            stored = self._to_spec(existing)
            verdict = classify_duplicate(stored, spec)
            if verdict == IDENTICAL:
                return RowResult(UNCHANGED, fp, "identical to stored record")
            if verdict == CONFLICTING:
                return RowResult(CONFLICT, fp,
                                 "incoming values contradict stored record; not overwritten")
            if verdict == DUPLICATE:
                merged = _merge_fill_gaps(stored, spec)
                if merged is None:
                    return RowResult(UNCHANGED, fp, "no new fields to add")
                for k, v in merged.to_record_values().items():
                    setattr(existing, k, v)
                return RowResult(ENRICHED, fp, "filled previously-missing fields")
            # AMBIGUOUS should be unreachable here (identities match by fp), but
            # be safe: never guess.
            return RowResult(CONFLICT, fp, f"unresolved classification: {verdict}")

    def import_specs(self, specs, *, created_by: Optional[int] = None) -> ImportSummary:
        """Import many specs, one controlled upsert each, with a full summary.

        Each spec is committed in its own unit of work, so a bad row cannot
        corrupt already-accepted rows and no half-written record survives.
        """
        summary = ImportSummary()
        for spec in specs:
            summary.rows_seen += 1
            result = self.upsert(spec, created_by=created_by)
            summary.rows.append(result)
            if result.outcome == NEW:
                summary.inserted += 1
            elif result.outcome == UNCHANGED:
                summary.unchanged += 1
            elif result.outcome == ENRICHED:
                summary.enriched += 1
            elif result.outcome == CONFLICT:
                summary.conflicting += 1
            elif result.outcome == INVALID:
                summary.invalid += 1
        return summary

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_spec(row: DrillPipeSpecRecord) -> DrillPipeSpec:
        return DrillPipeSpec.from_record_values({"payload_json": row.payload_json})


_IDENTITY_FIELDS = {
    "manufacturer", "model", "nominal_od_in", "nominal_weight_ppf",
    "grade", "connection",
}

# Descriptive fields eligible for non-destructive gap-filling.
_DESCRIPTIVE_FIELDS = (
    "nominal_id_in", "tool_joint_od_in", "tool_joint_id_in",
    "drift_in", "tensile_rating_klbf",
)


def _merge_fill_gaps(stored: DrillPipeSpec, incoming: DrillPipeSpec) -> Optional[DrillPipeSpec]:
    """Return a spec that adds only the descriptive fields missing on ``stored``.

    Existing stored values are NEVER changed (that would be a silent overwrite);
    only ``None`` fields are filled from the incoming spec. Returns ``None`` when
    nothing can be added.
    """
    from dataclasses import replace

    updates = {}
    for name in _DESCRIPTIVE_FIELDS:
        if getattr(stored, name) is None and getattr(incoming, name) is not None:
            updates[name] = getattr(incoming, name)
    if not updates:
        return None
    return replace(stored, **updates)
