"""M175: the selected well versus the well a DDR source names - never resolved silently.

Before M175 the import resolved the workbook's well name / code against the database and *switched* the target
to whatever it found, or created a new well in the selected project, without telling the operator. A report could
therefore land under another well than the one selected in the application.

Contract ``ddr-well-identity-v1``:

* :func:`assess` compares the selected well with every identity the source states (name and code are resolved
  separately; each keeps the source key that produced it as evidence).  It never mutates anything.
* ``SAME`` / ``NO_SOURCE_IDENTITY`` import into the selected well.  Without a selected well an unambiguous source
  identity still resolves (``NO_SELECTION_MATCH``) or - only when exactly one project exists - creates the well
  (``NO_SELECTION_NEW``); an ambiguous one is refused.
* ``CONFLICT_EXISTING`` (the source names another existing well), ``UNKNOWN_SOURCE_WELL`` (the source names a well
  that does not exist) and ``OTHER_PROJECT`` require an explicit :func:`make_decision` taken by the operator; the
  decision carries the selected well and the source identity it was taken for and is re-validated by
  :func:`validate_decision` at the persistence boundary (a stale selection or a changed source refuses it).
* ``AMBIGUOUS`` (several wells match) and ``MULTIPLE_IDENTITIES`` (name and code point at different wells) are
  always refused: no routing, no creation.

The module is free of Qt and of the ORM so the rules are regression-tested directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

WELL_IDENTITY_CONTRACT = "ddr-well-identity-v1"

SAME = "SAME"
NO_SOURCE_IDENTITY = "NO_SOURCE_IDENTITY"
NO_SELECTION_MATCH = "NO_SELECTION_MATCH"
NO_SELECTION_NEW = "NO_SELECTION_NEW"
CONFLICT_EXISTING = "CONFLICT_EXISTING"
UNKNOWN_SOURCE_WELL = "UNKNOWN_SOURCE_WELL"
OTHER_PROJECT = "OTHER_PROJECT"
AMBIGUOUS = "AMBIGUOUS"
MULTIPLE_IDENTITIES = "MULTIPLE_IDENTITIES"
NO_SELECTION_AMBIGUOUS = "NO_SELECTION_AMBIGUOUS"

# Operator choices.
CHOOSE_SELECTED = "IMPORT_INTO_SELECTED_WELL"
CHOOSE_SOURCE_WELL = "IMPORT_INTO_SOURCE_WELL"
CHOOSE_CREATE = "CREATE_SOURCE_WELL"

DECISION_REQUIRED = (CONFLICT_EXISTING, UNKNOWN_SOURCE_WELL, OTHER_PROJECT)
REFUSED = (AMBIGUOUS, MULTIPLE_IDENTITIES, NO_SELECTION_AMBIGUOUS)

# Source keys that state a well name (first non-empty wins, the key is evidence) and a well code.
NAME_KEYS = ("name", "well_name", "well", "well_number", "well_id", "well_number_text", "نام چاه",
             "well designation", "wellname")
CODE_KEYS = ("code", "well_code")


@dataclass(frozen=True)
class WellRef:
    id: int
    name: str = ""
    code: str = ""
    project_id: Optional[int] = None
    project_name: str = ""

    def label(self) -> str:
        code = f" [{self.code}]" if self.code else ""
        project = f" - project {self.project_name or self.project_id}" if self.project_id is not None else ""
        return f"{self.name or '(unnamed)'}{code} (id {self.id}){project}"

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "code": self.code, "project_id": self.project_id,
                "project_name": self.project_name}


class WellIdentityRefused(ValueError):
    """The import is refused before anything is written; ``assessment`` says why."""

    def __init__(self, message: str, assessment: "Assessment"):
        super().__init__(message)
        self.assessment = assessment


@dataclass
class Assessment:
    status: str
    selected: Optional[WellRef]
    source_name: str = ""
    source_code: str = ""
    evidence: List[Dict[str, str]] = field(default_factory=list)
    matches: List[WellRef] = field(default_factory=list)
    message: str = ""
    consequences: List[str] = field(default_factory=list)
    options: Tuple[str, ...] = ()

    @property
    def requires_decision(self) -> bool:
        return self.status in DECISION_REQUIRED

    @property
    def refused(self) -> bool:
        return self.status in REFUSED

    def source_label(self) -> str:
        parts = [self.source_name and f"name {self.source_name!r}", self.source_code and f"code {self.source_code!r}"]
        return ", ".join(p for p in parts if p) or "(no well identity in the source)"

    def to_dict(self) -> Dict[str, Any]:
        return {"contract": WELL_IDENTITY_CONTRACT, "status": self.status,
                "selected": self.selected.to_dict() if self.selected else None,
                "source": {"name": self.source_name, "code": self.source_code},
                "evidence": list(self.evidence), "matches": [m.to_dict() for m in self.matches],
                "message": self.message, "consequences": list(self.consequences), "options": list(self.options)}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def source_identity(well_info: Optional[Mapping[str, Any]]) -> Tuple[str, str, List[Dict[str, str]]]:
    """The well name and code a source states, with the key that stated each one (evidence)."""
    info = well_info if isinstance(well_info, Mapping) else {}
    evidence: List[Dict[str, str]] = []
    name = code = ""
    for key in NAME_KEYS:
        value = _text(info.get(key))
        if value:
            name = value
            evidence.append({"field": key, "value": value, "role": "name"})
            break
    for key in CODE_KEYS:
        value = _text(info.get(key))
        if value:
            code = value
            evidence.append({"field": key, "value": value, "role": "code"})
            break
    provenance = info.get("_source_cells") if isinstance(info.get("_source_cells"), Mapping) else {}
    for item in evidence:
        cell = provenance.get(f"well_info.{item['field']}") or provenance.get(item["field"])
        if cell:
            item["cell"] = str(cell)
    return name, code, evidence


def _norm(text: str) -> str:
    """The established label equivalence of the well catalogue (case, spacing and punctuation insensitive)."""
    from core.combo_identity import normalize_label
    return normalize_label(text)


def _matching(value: str, wells: Sequence[WellRef], attribute: str) -> List[WellRef]:
    """All catalogue-equivalent matches of one identity (never fuzzy, never partial).

    An exact match does not hide an equivalent twin: "AZNS-207" and "AZNS 207" are the same catalogue label,
    so two such wells make the identity ambiguous (M175 finding; it was routed to the exact spelling before).
    """
    if not value:
        return []
    return [w for w in wells if getattr(w, attribute) and _norm(getattr(w, attribute)) == _norm(value)]


def _exactly_named(well: WellRef, name: str, code: str) -> bool:
    return bool((name and well.name == name) or (code and well.code == code))


def _resolve(name: str, code: str, wells: Sequence[WellRef]) -> Tuple[List[WellRef], bool]:
    """Wells the source identity points at, and whether name and code disagree."""
    by_code = _matching(code, wells, "code") or _matching(code, wells, "name")
    by_name = _matching(name, wells, "name") or _matching(name, wells, "code")
    if by_code and by_name and not ({w.id for w in by_code} & {w.id for w in by_name}):
        return sorted({w.id: w for w in by_code + by_name}.values(), key=lambda w: w.id), True
    if by_code and by_name:
        common = [w for w in by_code if w.id in {n.id for n in by_name}]
        return common, False
    return by_code or by_name, False


def assess(selected: Optional[WellRef], well_info: Optional[Mapping[str, Any]], wells: Iterable[WellRef],
           *, project_count: int = 1) -> Assessment:
    """Compare the selected well with the source identity; ``wells`` are all wells of the database."""
    wells = list(wells)
    name, code, evidence = source_identity(well_info)
    base = dict(selected=selected, source_name=name, source_code=code, evidence=evidence)
    if not name and not code:
        if selected is None:
            return Assessment(NO_SELECTION_AMBIGUOUS, message="No well is selected and the source names no well: "
                              "select the target well before importing.", **base)
        return Assessment(NO_SOURCE_IDENTITY, message="The source names no well; the selected well is the target.",
                          **base)

    scope = [w for w in wells if selected is None or w.project_id == selected.project_id]
    matches, contradictory = _resolve(name, code, scope)
    if not matches and selected is not None:
        outside, contradictory_outside = _resolve(name, code, wells)
        if outside:
            matches, contradictory = outside, contradictory_outside
    if (not contradictory and selected is not None and len(matches) > 1
            and any(m.id == selected.id for m in matches) and _exactly_named(selected, name, code)):
        # The operator's selection is itself an exact spelling of the source identity: that is the target.
        # The equivalent twins stay visible as evidence.
        evidence = list(evidence) + [{"field": "equivalent_wells", "role": "twin",
                                      "value": ", ".join(m.label() for m in matches if m.id != selected.id)}]
        return Assessment(SAME, matches=[selected], message="The source names the selected well (an equivalent "
                          "spelling exists on another well).", **dict(base, evidence=evidence))
    if contradictory:
        return Assessment(MULTIPLE_IDENTITIES, matches=matches,
                          message=f"The source's well name and code point at different wells "
                                  f"({', '.join(m.label() for m in matches)}); the import is refused.", **base)
    if len(matches) > 1:
        status = AMBIGUOUS if selected is not None else NO_SELECTION_AMBIGUOUS
        return Assessment(status, matches=matches,
                          message=f"The source identity {', '.join(filter(None, [name, code]))!r} matches "
                                  f"{len(matches)} wells (ambiguous); select a unique well/code before importing.", **base)

    if selected is None:
        if matches:
            return Assessment(NO_SELECTION_MATCH, matches=matches,
                              message=f"No well is selected; the source identifies {matches[0].label()}.", **base)
        if project_count == 1:
            return Assessment(NO_SELECTION_NEW, message="No well is selected; the source well does not exist and "
                              "will be created in the only project.", **base)
        return Assessment(NO_SELECTION_AMBIGUOUS, message="Select a well/project context before importing: project "
                          "identity is ambiguous.", **base)

    if matches and matches[0].id == selected.id:
        return Assessment(SAME, matches=matches, message="The source names the selected well.", **base)

    if matches:
        other = matches[0]
        status = OTHER_PROJECT if other.project_id != selected.project_id else CONFLICT_EXISTING
        consequences = [
            f"Import into the selected well {selected.label()}: the report is stored there and the source's well "
            f"identity ({name or code}) is kept only as evidence; header values of the source well are not "
            f"applied to the selected well's master data.",
            f"Import into the source well {other.label()}: the report is stored under that well, not under the "
            f"well you selected.",
        ]
        options = (CHOOSE_SELECTED,) if status == OTHER_PROJECT else (CHOOSE_SELECTED, CHOOSE_SOURCE_WELL)
        if status == OTHER_PROJECT:
            consequences[1] = (f"The source well {other.label()} belongs to another project; select that well "
                               f"in its project to import there.")
        return Assessment(status, matches=matches, consequences=consequences, options=options,
                          message=f"The selected well is {selected.label()}, but the source names "
                                  f"{other.label()}.", **base)

    return Assessment(UNKNOWN_SOURCE_WELL, consequences=[
        f"Import into the selected well {selected.label()}: the source's well identity ({name or code}) is kept "
        f"only as evidence; header values of the source well are not applied to the selected well's master data.",
        f"Create a new well {name or code!r} in project {selected.project_name or selected.project_id} and import "
        f"the report there.",
    ], options=(CHOOSE_SELECTED, CHOOSE_CREATE),
        message=f"The selected well is {selected.label()}, but the source names a well that does not exist "
                f"({', '.join(filter(None, [name, code]))}).", **base)


def make_decision(assessment: Assessment, choice: str, reason: str, *, decided_by: str = "") -> Dict[str, Any]:
    """The operator's explicit decision for an assessment that requires one."""
    if not assessment.requires_decision:
        raise ValueError(f"No decision is needed for {assessment.status}")
    if choice not in assessment.options:
        raise ValueError(f"{choice} is not an option for {assessment.status}")
    if not _text(reason):
        raise ValueError("A reason is required for a well identity decision")
    target = (assessment.selected.id if choice == CHOOSE_SELECTED
              else assessment.matches[0].id if choice == CHOOSE_SOURCE_WELL else None)
    return {"contract": WELL_IDENTITY_CONTRACT, "status": assessment.status, "choice": choice,
            "target_well_id": target, "selected_well_id": assessment.selected.id,
            "source": {"name": assessment.source_name, "code": assessment.source_code},
            "reason": _text(reason), "decided_by": decided_by,
            "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def validate_decision(assessment: Assessment, decision: Optional[Mapping[str, Any]]) -> Tuple[Optional[int], bool]:
    """Re-validate at persistence: returns ``(target_well_id, create)`` or raises :class:`WellIdentityRefused`."""
    if assessment.refused:
        raise WellIdentityRefused(assessment.message, assessment)
    if assessment.status in (SAME, NO_SOURCE_IDENTITY):
        return assessment.selected.id, False
    if assessment.status == NO_SELECTION_MATCH:
        return assessment.matches[0].id, False
    if assessment.status == NO_SELECTION_NEW:
        return None, True
    if not isinstance(decision, Mapping):
        raise WellIdentityRefused(f"NOT SAVED: {assessment.message} Choose the target well explicitly.", assessment)
    stale = []
    if decision.get("contract") != WELL_IDENTITY_CONTRACT:
        stale.append("unknown decision contract")
    if decision.get("selected_well_id") != assessment.selected.id:
        stale.append("the selected well changed after the decision")
    source = decision.get("source") if isinstance(decision.get("source"), Mapping) else {}
    if (_text(source.get("name")), _text(source.get("code"))) != (assessment.source_name, assessment.source_code):
        stale.append("the source identity differs from the one decided")
    if decision.get("status") != assessment.status:
        stale.append("the database identity changed after the decision")
    choice = decision.get("choice")
    if choice not in assessment.options:
        stale.append(f"{choice!r} is not an option for {assessment.status}")
    if not _text(decision.get("reason")):
        stale.append("no reason was recorded")
    expected = (assessment.selected.id if choice == CHOOSE_SELECTED
                else assessment.matches[0].id if choice == CHOOSE_SOURCE_WELL and assessment.matches else None)
    if decision.get("target_well_id") != expected:
        stale.append("the decided target is not the well the choice names")
    if stale:
        raise WellIdentityRefused("NOT SAVED: the well identity decision is no longer valid (" + "; ".join(stale)
                                  + "). Decide again.", assessment)
    return expected, choice == CHOOSE_CREATE
