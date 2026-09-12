"""Deterministic Well → Wellbore → Section scope attribution.

Legacy / ambiguous Daily Reports may carry a canonical ``well_id`` but leave
``wellbore_id`` / ``section_id`` NULL ("unknown"). The schema explicitly defers
these to "a deterministic attribution" (see the v3 upgrade note in
``core.database``). This service IS that attribution — and nothing more.

Core principle: **prefer preserving uncertainty over fabricating certainty.**
Scope is assigned ONLY when ownership is objectively provable from canonical
data, never from rig names, display-name similarity, or date proximity.

Resolution outcomes are a four-state classification, never a boolean:

* ``RESOLVED``   — a unique, provable owner was found (and, in ``resolve``,
  assigned).
* ``AMBIGUOUS``  — more than one candidate owner exists and no canonical
  discriminator distinguishes them; left NULL.
* ``UNRESOLVED`` — no candidate owner exists at all; left NULL.
* ``INVALID``    — an existing scope contradicts the ownership chain (detected
  defensively; never "resolved", never silently repaired).

Safe resolution rules
---------------------
Wellbore for a report whose ``wellbore_id`` is NULL:
  1. via section — the report's Section already has a non-NULL ``wellbore_id``
     (the section itself proves the bore). This is the strongest evidence.
  2. via unique wellbore — the report's Well has exactly ONE wellbore, so any
     report under that well unambiguously belongs to it.
  otherwise AMBIGUOUS (≥2 bores, no discriminator) or UNRESOLVED (0 bores).

Section for a report whose ``section_id`` is NULL:
  1. via unique section in bore — the (resolved or existing) wellbore has
     exactly ONE section.
  2. via unique section in well — the well has exactly ONE section.
  otherwise AMBIGUOUS / UNRESOLVED.

``resolve`` writes through the ORM, so the ``before_flush`` ownership-integrity
invariants remain the ultimate safety net: any assignment that would cross a
well boundary raises rather than committing. Existing non-NULL scope is never
overwritten, so the operation is idempotent.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"
INVALID = "invalid"
ALREADY = "already"  # scope already present (nothing to do)


@dataclass
class ReportOutcome:
    """Per-report attribution outcome for one dimension (wellbore or section)."""

    report_id: int
    dimension: str  # "wellbore" | "section"
    status: str  # ALREADY | RESOLVED | AMBIGUOUS | UNRESOLVED | INVALID
    target_id: Optional[int] = None  # the id assigned/assignable when RESOLVED
    method: str = ""  # provenance of a RESOLVED decision
    detail: str = ""


@dataclass
class AttributionReport:
    """Aggregate result of an analyze()/resolve() run."""

    total_reports: int = 0
    wellbore: Counter = field(default_factory=Counter)
    section: Counter = field(default_factory=Counter)
    outcomes: List[ReportOutcome] = field(default_factory=list)
    applied: int = 0  # number of FK assignments actually written (resolve only)

    def as_dict(self) -> Dict:
        return {
            "total_reports": self.total_reports,
            "wellbore": dict(self.wellbore),
            "section": dict(self.section),
            "applied": self.applied,
            "outcomes": [vars(o) for o in self.outcomes],
        }


class ScopeAttributionService:
    """Analyze and (optionally) apply deterministic scope attribution."""

    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # Read-only analysis
    # ------------------------------------------------------------------
    def analyze(self, well_id: Optional[int] = None) -> AttributionReport:
        """Classify every report's wellbore/section attribution WITHOUT writing.

        ``well_id`` limits the scan to one well; ``None`` scans all wells.
        """
        session = self.db.create_session()
        try:
            return self._compute(session, well_id, apply=False)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Deterministic backfill
    # ------------------------------------------------------------------
    def resolve(self, well_id: Optional[int] = None) -> AttributionReport:
        """Assign only provably-unique wellbore/section owners; commit once.

        Idempotent: a second call finds the same rows ``ALREADY`` attributed.
        Never overwrites existing scope and never crosses a well boundary (the
        persistence invariants enforce the latter regardless).
        """
        session = self.db.create_session()
        try:
            report = self._compute(session, well_id, apply=True)
            if report.applied:
                session.commit()
            return report
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Shared engine
    # ------------------------------------------------------------------
    def _compute(self, session, well_id, apply: bool) -> AttributionReport:
        from core.database import DailyReport, Section, Wellbore

        result = AttributionReport()

        # Wellbores and sections grouped by well, loaded once (no N+1).
        wb_q = session.query(Wellbore)
        sec_q = session.query(Section)
        rep_q = session.query(DailyReport)
        if well_id is not None:
            wb_q = wb_q.filter(Wellbore.well_id == well_id)
            sec_q = sec_q.filter(Section.well_id == well_id)
            rep_q = rep_q.filter(DailyReport.well_id == well_id)

        wellbores_by_well: Dict[int, List[int]] = defaultdict(list)
        for wb in wb_q.all():
            wellbores_by_well[wb.well_id].append(wb.id)

        sections_by_well: Dict[int, List] = defaultdict(list)
        section_by_id: Dict[int, object] = {}
        sections_by_wellbore: Dict[int, List[int]] = defaultdict(list)
        for sec in sec_q.all():
            sections_by_well[sec.well_id].append(sec)
            section_by_id[sec.id] = sec
            if sec.wellbore_id is not None:
                sections_by_wellbore[sec.wellbore_id].append(sec.id)

        reports = rep_q.order_by(DailyReport.report_date).all()
        result.total_reports = len(reports)

        for rep in reports:
            wb_outcome = self._classify_wellbore(
                rep, wellbores_by_well, section_by_id
            )
            result.wellbore[wb_outcome.status] += 1
            result.outcomes.append(wb_outcome)
            if apply and wb_outcome.status == RESOLVED:
                # Only write onto a currently-NULL column.
                if rep.wellbore_id is None:
                    rep.wellbore_id = wb_outcome.target_id
                    result.applied += 1

            # Section resolution can use a wellbore that is now known (either
            # pre-existing or just resolved above).
            effective_wb = rep.wellbore_id
            sec_outcome = self._classify_section(
                rep,
                effective_wb,
                sections_by_well,
                sections_by_wellbore,
                section_by_id,
            )
            result.section[sec_outcome.status] += 1
            result.outcomes.append(sec_outcome)
            if apply and sec_outcome.status == RESOLVED:
                if rep.section_id is None:
                    rep.section_id = sec_outcome.target_id
                    result.applied += 1

        return result

    # ------------------------------------------------------------------
    def _classify_wellbore(
        self, rep, wellbores_by_well, section_by_id
    ) -> ReportOutcome:
        # Existing scope: trust it (invariants guarantee it is coherent) but
        # defensively flag a contradiction with the section's own bore.
        if rep.wellbore_id is not None:
            sec = section_by_id.get(rep.section_id)
            if (
                sec is not None
                and sec.wellbore_id is not None
                and sec.wellbore_id != rep.wellbore_id
            ):
                return ReportOutcome(
                    rep.id, "wellbore", INVALID,
                    detail=(
                        f"report wellbore_id={rep.wellbore_id} contradicts "
                        f"section {sec.id} wellbore_id={sec.wellbore_id}"
                    ),
                )
            return ReportOutcome(
                rep.id, "wellbore", ALREADY, target_id=rep.wellbore_id
            )

        # Rule 1: the report's section already proves a bore.
        sec = section_by_id.get(rep.section_id)
        if sec is not None and sec.wellbore_id is not None:
            return ReportOutcome(
                rep.id, "wellbore", RESOLVED,
                target_id=sec.wellbore_id,
                method="via_section",
                detail=f"section {sec.id} owns wellbore {sec.wellbore_id}",
            )

        # Rule 2: the well has exactly one wellbore.
        bores = wellbores_by_well.get(rep.well_id, [])
        if len(bores) == 1:
            return ReportOutcome(
                rep.id, "wellbore", RESOLVED,
                target_id=bores[0],
                method="via_unique_wellbore",
                detail=f"well {rep.well_id} has exactly one wellbore",
            )
        if len(bores) >= 2:
            return ReportOutcome(
                rep.id, "wellbore", AMBIGUOUS,
                detail=(
                    f"well {rep.well_id} has {len(bores)} wellbores and no "
                    "canonical discriminator"
                ),
            )
        return ReportOutcome(
            rep.id, "wellbore", UNRESOLVED,
            detail=f"well {rep.well_id} has no wellbore to attribute",
        )

    def _classify_section(
        self,
        rep,
        effective_wb,
        sections_by_well,
        sections_by_wellbore,
        section_by_id,
    ) -> ReportOutcome:
        if rep.section_id is not None:
            return ReportOutcome(
                rep.id, "section", ALREADY, target_id=rep.section_id
            )

        # Rule 1: the (known) wellbore has exactly one section.
        if effective_wb is not None:
            bore_sections = sections_by_wellbore.get(effective_wb, [])
            if len(bore_sections) == 1:
                return ReportOutcome(
                    rep.id, "section", RESOLVED,
                    target_id=bore_sections[0],
                    method="via_unique_section_in_wellbore",
                    detail=f"wellbore {effective_wb} has exactly one section",
                )
            if len(bore_sections) >= 2:
                return ReportOutcome(
                    rep.id, "section", AMBIGUOUS,
                    detail=(
                        f"wellbore {effective_wb} has {len(bore_sections)} "
                        "sections and no canonical discriminator"
                    ),
                )

        # Rule 2: the well has exactly one section.
        well_sections = sections_by_well.get(rep.well_id, [])
        if len(well_sections) == 1:
            return ReportOutcome(
                rep.id, "section", RESOLVED,
                target_id=well_sections[0].id,
                method="via_unique_section_in_well",
                detail=f"well {rep.well_id} has exactly one section",
            )
        if len(well_sections) >= 2:
            return ReportOutcome(
                rep.id, "section", AMBIGUOUS,
                detail=(
                    f"well {rep.well_id} has {len(well_sections)} sections and "
                    "no canonical discriminator"
                ),
            )
        return ReportOutcome(
            rep.id, "section", UNRESOLVED,
            detail=f"well {rep.well_id} has no section to attribute",
        )

    # ------------------------------------------------------------------
    # Coverage metrics (read-only)
    # ------------------------------------------------------------------
    def coverage(self, well_id: Optional[int] = None) -> Dict:
        """Return scope-attribution coverage percentages for a well (or all).

        Coverage counts ONLY genuinely-attributed reports (ALREADY + the
        provably RESOLVED ones); NULL/ambiguous/unresolved rows are never
        treated as covered. Percentages are ``None`` when there are no reports
        (unknown, never a fabricated 0/100).
        """
        report = self.analyze(well_id)
        total = report.total_reports

        def _pct(counter: Counter) -> Optional[float]:
            if not total:
                return None
            covered = counter.get(ALREADY, 0) + counter.get(RESOLVED, 0)
            return round(covered / total * 100, 1)

        return {
            "well_id": well_id,
            "total_reports": total,
            "wellbore_coverage_pct": _pct(report.wellbore),
            "section_coverage_pct": _pct(report.section),
            "wellbore": dict(report.wellbore),
            "section": dict(report.section),
        }
