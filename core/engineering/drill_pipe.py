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

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Dict, Mapping, Optional

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


def _first_present(row: Mapping[str, Any], aliases) -> Optional[Any]:
    """Return the first vendor value whose header matches an alias, else None.

    A blank/NaN vendor cell is treated as *absent*, never as 0.
    """
    normalized = { _norm_header(k): v for k, v in row.items() }
    for alias in aliases:
        key = _norm_header(alias)
        if key in normalized:
            value = normalized[key]
            if _is_missing(value):
                return None
            return value
    return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        # NaN never equals itself.
        return value != value
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() in {"nan", "none", "n/a", "-"}
    return False


def _to_float(value: Any) -> Optional[float]:
    if _is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN guard
        return None
    return number


def _to_inches(value: Any, source_unit: Optional[str]) -> Optional[float]:
    """Diameter to canonical inches. Only converts when the source unit is
    explicitly non-inch; otherwise the number is assumed already canonical."""
    number = _to_float(value)
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

        Unmapped columns are preserved verbatim in ``extra`` (audit trail).
        Missing/blank cells stay ``None``. No value is inferred from another.
        """
        mapped_headers = set()

        def take(aliases):
            value = _first_present(row, aliases)
            for alias in aliases:
                mapped_headers.add(_norm_header(alias))
            return value

        manufacturer = take(_MANUFACTURER_ALIASES)
        model = take(_MODEL_ALIASES)
        grade = take(_GRADE_ALIASES)
        connection = take(_CONNECTION_ALIASES)
        od_raw = take(_OD_ALIASES)
        id_raw = take(_ID_ALIASES)
        weight_raw = take(_WEIGHT_ALIASES)
        tj_od_raw = take(_TJ_OD_ALIASES)
        tj_id_raw = take(_TJ_ID_ALIASES)
        drift_raw = take(_DRIFT_ALIASES)
        tensile_raw = take(_TENSILE_ALIASES)

        # Preserve every unmapped column so nothing is silently lost.
        extra = {
            str(k): v
            for k, v in row.items()
            if _norm_header(k) not in mapped_headers and not _is_missing(v)
        }

        return cls(
            manufacturer=(str(manufacturer).strip() if not _is_missing(manufacturer) else None),
            model=(str(model).strip() if not _is_missing(model) else None),
            grade=(str(grade).strip() if not _is_missing(grade) else None),
            connection=(str(connection).strip() if not _is_missing(connection) else None),
            nominal_od_in=_to_inches(od_raw, od_unit),
            nominal_id_in=_to_inches(id_raw, id_unit),
            nominal_weight_ppf=_to_float(weight_raw),  # ppf kept numeric (see docstring)
            tool_joint_od_in=_to_inches(tj_od_raw, od_unit),
            tool_joint_id_in=_to_inches(tj_id_raw, id_unit),
            drift_in=_to_inches(drift_raw, od_unit),
            tensile_rating_klbf=_to_float(tensile_raw),
            provenance=provenance or Provenance(),
            extra=extra,
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
        return d


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
