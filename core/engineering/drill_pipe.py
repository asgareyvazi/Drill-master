"""Canonical Drill Pipe engineering specification.

This is the first **canonical Engineering Master Data** representation in the
application. It exists to give the scattered, schema-less vendor drill-pipe
reference (today an optional read-only Excel viewer in
``tabs/w13_Engineering_Calculator.py`` that no calculation consumes) a single,
explicit, unit-aware, provenance-carrying shape that the canonical calculation
engines can consume safely.

Design contract (see ``docs/audits/2026-09-13_ENGINEERING_DATABASE_FORENSIC_AUDIT.md``):

* **Master data, not operational data.** A ``DrillPipeSpec`` is a *reference
  specification* (5" 19.5 ppf S-135 NC50 …). It is NOT a string segment run in a
  particular BHA — that is operational data keyed by Well/Wellbore/Run and lives
  elsewhere. The two must never be conflated.
* **No fabrication.** Every field except the ones that form identity is optional
  and defaults to ``None`` ("unknown"). Missing vendor values stay unknown; we
  never invent a grade, connection, rating, or manufacturer.
* **Explicit units.** Diameters are canonical **inches**; nominal weight is
  canonical **ppf (lb/ft)**; ratings are **psi**; tensile is **klbf**. Vendor
  values in other units are converted at the boundary via the existing
  :class:`core.unit_manager.UnitManager` — except ``ppf`` (a *linear* weight),
  which ``UnitManager`` treats numerically only, so it is never routed through a
  unit conversion here.
* **Stable domain identity.** Identity is a domain key
  (manufacturer + model + nominal OD + nominal weight + grade + connection),
  never a spreadsheet/UI row index.
* **Provenance + revision.** Where each value came from and which revision it
  belongs to is preserved so a later reference change cannot silently rewrite the
  meaning of an older calculation.

The canonical calculation consumer proven by the accompanying tests is the
soft-string Torque & Drag / weight-card engine
(``core.engineering.engines.torque_drag``), whose per-component contract is
exactly ``{length, weight (ppf), od (in), id (in)}``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.unit_manager import UnitManager


# Vendor column header -> canonical field. Deliberately conservative: only
# headers whose engineering meaning is unambiguous are mapped. Anything else is
# preserved verbatim in ``extra`` rather than guessed.
_OD_ALIASES = ("nominal_od", "nominal od", "od", "od (in)", "od_in", "outer diameter",
               "body od", "pipe od")
_ID_ALIASES = ("nominal_id", "nominal id", "id", "id (in)", "id_in", "inner diameter",
               "body id", "pipe id")
_WEIGHT_ALIASES = ("nominal_weight", "nominal weight", "weight", "weight (ppf)",
                   "wt", "wt (ppf)", "ppf", "adjusted weight", "nominal_weight_ppf")
_GRADE_ALIASES = ("grade", "material grade", "steel grade", "pipe grade")
_CONNECTION_ALIASES = ("connection", "conn", "tool joint connection", "tj connection")
_MANUFACTURER_ALIASES = ("manufacturer", "maker", "mfg", "vendor", "supplier")
_MODEL_ALIASES = ("model", "product", "product line", "type", "designation")
_TJ_OD_ALIASES = ("tool_joint_od", "tool joint od", "tj od", "tj_od")
_TJ_ID_ALIASES = ("tool_joint_id", "tool joint id", "tj id", "tj_id")
_DRIFT_ALIASES = ("drift", "drift diameter", "drift_diameter", "drift (in)")
_TENSILE_ALIASES = ("tensile", "tensile rating", "tensile_rating", "pipe body yield",
                    "body yield", "yield tension")


def _norm_header(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


# Sentinel textual values that explicitly encode *unknown*, distinct from a
# genuine string that merely fails to parse as a number.
_UNKNOWN_TOKENS = {"", "nan", "none", "null", "n/a", "na", "-", "--", "?", "tbd", "unknown"}


def _is_missing(value: Any) -> bool:
    """True when a vendor cell means *unknown / not supplied*.

    Blank, NaN and explicit unknown sentinels ("n/a", "unknown", …) are missing.
    A concrete value (including 0, negatives, or an unparseable string) is NOT
    missing — those are separate states handled downstream (invalid vs conflict).
    """
    if value is None:
        return True
    if isinstance(value, float):
        # NaN never equals itself.
        return value != value
    if isinstance(value, str):
        return value.strip().lower() in _UNKNOWN_TOKENS
    return False


def _present_matches(row: Mapping[str, Any], aliases):
    """Return ``[(header, value), …]`` for every non-missing column whose header
    matches one of ``aliases``. Unlike a first-wins lookup this surfaces *all*
    candidates so conflicting source columns can be detected, never silently
    resolved."""
    matched = []
    alias_set = {_norm_header(a) for a in aliases}
    for header, value in row.items():
        if _norm_header(header) in alias_set and not _is_missing(value):
            matched.append((str(header), value))
    return matched


def _to_number(value: Any) -> Optional[float]:
    """Parse a finite float, or None when the value is not a clean number.

    Note: this does NOT judge the engineering domain (0/negative pass here);
    domain validity (OD>0 etc.) is enforced separately so we can distinguish
    'not a number' from 'a number outside the physical domain'."""
    if _is_missing(value):
        return None
    if isinstance(value, bool):  # bool is an int subclass — never a measurement
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):  # NaN / inf / 1e400 overflow
        return None
    return number


def _to_inches(value: Any, source_unit: Optional[str]) -> Optional[float]:
    """Diameter to canonical inches. Only converts when the source unit is
    explicitly non-inch; otherwise the number is assumed already canonical."""
    number = _to_number(value)
    if number is None:
        return None
    unit = _norm_header(source_unit)
    if unit in ("", "in", "inch", "inches", '"'):
        return number
    converted = UnitManager.convert(number, "diameter", unit, "in")
    return converted if converted is not None else None


@dataclass(frozen=True)
class Provenance:
    """Where a reference value came from — never invented."""

    source: str = ""                       # e.g. "vendor Excel", "API 5DP", "company std"
    source_revision: str = ""              # vendor/standard revision if known
    effective_date: Optional[date] = None  # when this revision took effect
    status: str = "unverified"             # unverified | verified | deprecated
    notes: str = ""

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.effective_date is not None:
            d["effective_date"] = self.effective_date.isoformat()
        return d


# Duplicate classification vocabulary (import/migration safety, §15).
IDENTICAL = "IDENTICAL"        # same identity, same engineering values
DUPLICATE = "DUPLICATE"        # same identity, one is an empty/subset copy
CONFLICTING = "CONFLICTING"    # same identity, contradictory engineering values
AMBIGUOUS = "AMBIGUOUS"        # identity cannot be established for one/both


# Per-field normalization issue kinds. These make the states the mission
# requires explicit and distinct — a value is never quietly downgraded from one
# to another (unknown != invalid != conflicting != zero).
ISSUE_CONFLICT = "CONFLICTING_SOURCE"   # >1 mapped source column, materially different
ISSUE_INVALID = "INVALID_VALUE"         # a value outside the physical domain / unparseable
ISSUE_UNIT = "UNIT_UNCONVERTIBLE"       # a declared source unit could not be converted


@dataclass(frozen=True)
class SpecIssue:
    """A single, human-actionable normalization problem for one field.

    Issues are *surfaced*, never silently resolved. A field that carries a
    conflict or invalid value is left ``None`` (unknown) on the canonical spec so
    it can never masquerade as a trusted engineering value, while the raw
    evidence is preserved here for audit / manual resolution.
    """

    field: str
    kind: str
    detail: str
    raw: Tuple[Any, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "kind": self.kind, "detail": self.detail,
                "raw": list(self.raw)}


@dataclass(frozen=True)
class DrillPipeSpec:
    """Canonical drill-pipe reference specification (master data).

    All measured fields carry an explicit canonical unit (see module docstring).
    Optional fields default to ``None`` = unknown, never a fabricated default.
    """

    # --- identity-forming fields (domain key, not row index) ---
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    nominal_od_in: Optional[float] = None      # inches
    nominal_weight_ppf: Optional[float] = None  # lb/ft (NOT unit-converted)
    grade: Optional[str] = None
    connection: Optional[str] = None

    # --- descriptive engineering fields ---
    nominal_id_in: Optional[float] = None       # inches
    tool_joint_od_in: Optional[float] = None    # inches
    tool_joint_id_in: Optional[float] = None    # inches
    drift_in: Optional[float] = None            # inches
    tensile_rating_klbf: Optional[float] = None  # klbf

    # --- provenance + unmapped vendor columns (preserved, never dropped) ---
    provenance: Provenance = field(default_factory=Provenance)
    extra: Dict[str, Any] = field(default_factory=dict)

    # --- normalization issues surfaced for audit / manual resolution ---
    # Conflicts and invalid values leave their field None (unknown) but are
    # recorded here rather than silently discarded.
    issues: Tuple[SpecIssue, ...] = ()

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    @property
    def identity_key(self) -> tuple:
        """Stable domain identity. Case/space-insensitive for text parts."""
        def _n(text: Optional[str]) -> str:
            return _norm_header(text) if text is not None else ""

        return (
            _n(self.manufacturer),
            _n(self.model),
            self.nominal_od_in,
            self.nominal_weight_ppf,
            _n(self.grade),
            _n(self.connection),
        )

    @property
    def has_identity(self) -> bool:
        """A spec is identifiable when it carries the minimal engineering key:
        a nominal OD and a nominal weight (the two fields every calculation and
        every vendor row needs). Manufacturer/model/grade refine but do not
        gate identity, because vendor sheets frequently omit them."""
        return self.nominal_od_in is not None and self.nominal_weight_ppf is not None

    def identity_fingerprint(self) -> str:
        """Deterministic, storage-safe string form of :attr:`identity_key`.

        Used as the UNIQUE natural key at the persistence boundary. It is stable
        across float spelling (5.0 == 5.000) and text case/spacing because it is
        built from the already-normalized ``identity_key`` tuple.
        """
        import json

        def _canon(part: Any) -> Any:
            if isinstance(part, float):
                # Collapse 5.0 / 5.000 / 5.000000 to one representation.
                return format(round(part, 6), ".6f")
            return part

        return json.dumps([_canon(p) for p in self.identity_key], ensure_ascii=False)

    # ------------------------------------------------------------------
    # Vendor row -> canonical spec (safe normalization, no fabrication)
    # ------------------------------------------------------------------
    @classmethod
    def from_vendor_row(
        cls,
        row: Mapping[str, Any],
        *,
        provenance: Optional[Provenance] = None,
        od_unit: Optional[str] = None,
        id_unit: Optional[str] = None,
    ) -> "DrillPipeSpec":
        """Normalize one arbitrary vendor row into a canonical spec.

        Safety contract (never silently wrong):

        * **Conflicting source columns** — if two mapped headers for the same
          canonical field carry materially different values (e.g. ``OD=5.000``
          and ``OD (in)=5.125``), the field is left ``None`` and a
          ``CONFLICTING_SOURCE`` issue records both raw values. The conflict is
          never silently resolved to one of them.
        * **Invalid values** — a number outside the physical domain (a
          non-positive or non-finite diameter/weight/tensile) is rejected to
          ``None`` with an ``INVALID_VALUE`` issue. Invalid is a distinct state
          from unknown.
        * **Unknown** — blank/NaN/explicit sentinels stay ``None`` with no
          issue.
        * Unmapped columns are preserved verbatim in ``extra``. Nothing is
          inferred from another field.
        """
        issues: List[SpecIssue] = []
        mapped_headers = set()

        def resolve_text(aliases, field_name):
            for alias in aliases:
                mapped_headers.add(_norm_header(alias))
            matches = _present_matches(row, aliases)
            if not matches:
                return None
            values = [str(v).strip() for _, v in matches]
            if len({v.lower() for v in values}) > 1:
                issues.append(SpecIssue(
                    field_name, ISSUE_CONFLICT,
                    "multiple source columns disagree",
                    tuple((h, v) for h, v in matches),
                ))
                return None
            return values[0] or None

        def resolve_number(aliases, field_name, *, unit=None, positive=True):
            for alias in aliases:
                mapped_headers.add(_norm_header(alias))
            matches = _present_matches(row, aliases)
            if not matches:
                return None

            parsed = []  # (header, raw, canonical_number|None, invalid_reason|None)
            for header, raw in matches:
                if unit is not None:
                    number = _to_inches(raw, unit)
                else:
                    number = _to_number(raw)
                if number is None:
                    parsed.append((header, raw, None, "unparseable/non-finite"))
                elif positive and number <= 0:
                    parsed.append((header, raw, None, "non-positive"))
                else:
                    parsed.append((header, raw, number, None))

            valid = [(h, r, n) for (h, r, n, bad) in parsed if bad is None]
            invalid = [(h, r, bad) for (h, r, n, bad) in parsed if bad is not None]

            # Conflict among the *valid* candidates → refuse to pick one.
            distinct = {round(n, 9) for _, _, n in valid}
            if len(distinct) > 1:
                issues.append(SpecIssue(
                    field_name, ISSUE_CONFLICT,
                    "multiple source columns disagree",
                    tuple((h, r) for h, r, _ in valid),
                ))
                return None
            if valid:
                return valid[0][2]
            # No valid value but at least one present-and-invalid value.
            if invalid:
                issues.append(SpecIssue(
                    field_name, ISSUE_INVALID,
                    "; ".join(f"{h}={r!r} ({why})" for h, r, why in invalid),
                    tuple((h, r) for h, r, _ in invalid),
                ))
            return None

        manufacturer = resolve_text(_MANUFACTURER_ALIASES, "manufacturer")
        model = resolve_text(_MODEL_ALIASES, "model")
        grade = resolve_text(_GRADE_ALIASES, "grade")
        connection = resolve_text(_CONNECTION_ALIASES, "connection")
        nominal_od = resolve_number(_OD_ALIASES, "nominal_od_in", unit=od_unit)
        nominal_id = resolve_number(_ID_ALIASES, "nominal_id_in", unit=id_unit)
        nominal_weight = resolve_number(_WEIGHT_ALIASES, "nominal_weight_ppf")
        tj_od = resolve_number(_TJ_OD_ALIASES, "tool_joint_od_in", unit=od_unit)
        tj_id = resolve_number(_TJ_ID_ALIASES, "tool_joint_id_in", unit=id_unit)
        drift = resolve_number(_DRIFT_ALIASES, "drift_in", unit=od_unit)
        tensile = resolve_number(_TENSILE_ALIASES, "tensile_rating_klbf")

        # Preserve every unmapped column so nothing is silently lost.
        extra = {
            str(k): v
            for k, v in row.items()
            if _norm_header(k) not in mapped_headers and not _is_missing(v)
        }

        return cls(
            manufacturer=manufacturer,
            model=model,
            grade=grade,
            connection=connection,
            nominal_od_in=nominal_od,
            nominal_id_in=nominal_id,
            nominal_weight_ppf=nominal_weight,  # ppf kept numeric (see docstring)
            tool_joint_od_in=tj_od,
            tool_joint_id_in=tj_id,
            drift_in=drift,
            tensile_rating_klbf=tensile,
            provenance=provenance or Provenance(),
            extra=extra,
            issues=tuple(issues),
        )

    # ------------------------------------------------------------------
    # Canonical calculation handoff
    # ------------------------------------------------------------------
    def to_component(self, length_m: float) -> Dict[str, Any]:
        """Build a drill-string component for the canonical T&D / weight engine.

        ``length_m`` is *operational* (how much of this pipe is run) and must be
        supplied by the caller — it is never part of the master spec. The
        returned dict matches ``TorqueDragEngine`` component contract exactly:
        ``{length, weight (ppf), od (in), id (in)}``. Fields the spec does not
        carry are omitted (not defaulted), so the engine's own MISSING_INPUT
        handling stays authoritative.
        """
        component: Dict[str, Any] = {"length": length_m}
        if self.nominal_weight_ppf is not None:
            component["weight"] = self.nominal_weight_ppf
        if self.nominal_od_in is not None:
            component["od"] = self.nominal_od_in
        if self.nominal_id_in is not None:
            component["id"] = self.nominal_id_in
        return component

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["provenance"] = self.provenance.as_dict()
        d["identity_key"] = self.identity_key
        d["issues"] = [i.as_dict() for i in self.issues]
        return d

    # ------------------------------------------------------------------
    # Persistence bridge (kept out of the ORM so the domain model stays
    # storage-agnostic; the repository owns the actual DB row).
    # ------------------------------------------------------------------
    def to_record_values(self) -> Dict[str, Any]:
        """Flat, DB-friendly column values for a reference-catalog row.

        The full spec (including provenance, issues and unmapped ``extra``) is
        also serialized into ``payload_json`` so a stored record round-trips back
        to an identical :class:`DrillPipeSpec` without lossy column mapping.
        """
        import json

        return {
            "identity_fingerprint": self.identity_fingerprint(),
            "manufacturer": self.manufacturer,
            "model": self.model,
            "nominal_od_in": self.nominal_od_in,
            "nominal_weight_ppf": self.nominal_weight_ppf,
            "grade": self.grade,
            "connection": self.connection,
            "nominal_id_in": self.nominal_id_in,
            "tool_joint_od_in": self.tool_joint_od_in,
            "tool_joint_id_in": self.tool_joint_id_in,
            "drift_in": self.drift_in,
            "tensile_rating_klbf": self.tensile_rating_klbf,
            "source": self.provenance.source,
            "source_revision": self.provenance.source_revision,
            "status": self.provenance.status,
            "payload_json": json.dumps(self.as_dict(), ensure_ascii=False, default=str),
        }

    @classmethod
    def from_record_values(cls, values: Mapping[str, Any]) -> "DrillPipeSpec":
        """Reconstruct a spec from a stored row's ``payload_json`` (lossless)."""
        import json

        payload = values.get("payload_json")
        data = json.loads(payload) if isinstance(payload, str) and payload else dict(values)
        prov = data.get("provenance") or {}
        eff = prov.get("effective_date")
        provenance = Provenance(
            source=prov.get("source", "") or "",
            source_revision=prov.get("source_revision", "") or "",
            effective_date=date.fromisoformat(eff) if eff else None,
            status=prov.get("status", "unverified") or "unverified",
            notes=prov.get("notes", "") or "",
        )
        issues = tuple(
            SpecIssue(i.get("field", ""), i.get("kind", ""), i.get("detail", ""),
                      tuple(tuple(x) if isinstance(x, list) else x for x in i.get("raw", [])))
            for i in (data.get("issues") or [])
        )
        return cls(
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            nominal_od_in=data.get("nominal_od_in"),
            nominal_weight_ppf=data.get("nominal_weight_ppf"),
            grade=data.get("grade"),
            connection=data.get("connection"),
            nominal_id_in=data.get("nominal_id_in"),
            tool_joint_od_in=data.get("tool_joint_od_in"),
            tool_joint_id_in=data.get("tool_joint_id_in"),
            drift_in=data.get("drift_in"),
            tensile_rating_klbf=data.get("tensile_rating_klbf"),
            provenance=provenance,
            extra=dict(data.get("extra") or {}),
            issues=issues,
        )


def classify_duplicate(a: DrillPipeSpec, b: DrillPipeSpec) -> str:
    """Classify two specs sharing (or not) an identity — never silently merge.

    Returns one of ``IDENTICAL`` / ``DUPLICATE`` / ``CONFLICTING`` / ``AMBIGUOUS``.
    Conflicting engineering specs must be surfaced for a human decision, not
    auto-merged.
    """
    if not a.has_identity or not b.has_identity or a.identity_key != b.identity_key:
        return AMBIGUOUS

    # Compare the descriptive engineering fields that are present in both.
    compared = ("nominal_id_in", "tool_joint_od_in", "tool_joint_id_in",
                "drift_in", "tensile_rating_klbf")
    conflict = False
    one_sided = False
    for name in compared:
        va = getattr(a, name)
        vb = getattr(b, name)
        if va is None and vb is None:
            continue
        if va is None or vb is None:
            one_sided = True
            continue
        if isinstance(va, float) and isinstance(vb, float):
            if abs(va - vb) > 1e-9:
                conflict = True
        elif va != vb:
            conflict = True

    if conflict:
        return CONFLICTING
    if one_sided:
        return DUPLICATE
    return IDENTICAL
