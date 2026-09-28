"""Qt-free presentation logic for the persisted DrillPipe reference catalog.

This module holds the *logic* for browsing, searching and inspecting the
authoritative persisted catalog (``DrillPipeReferenceRepository``) so the UI
layer (``tabs/w15_Reference_Tables.py``) can stay a thin view. Keeping it
Qt-free means it is unit-testable without constructing a widget (the project's
headless test contract), and it prevents engineering/normalization logic from
leaking into the UI (mission §22).

It introduces NO new normalization: identity, labels and canonical fields all
come from the existing canonical helpers
(:mod:`core.engineering.drill_pipe`, :mod:`dialogs.engineering_dialogs`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from core.engineering.drill_pipe import DrillPipeSpec, _norm_header

# The columns shown in the catalog browse grid, in order. Each is (key, header).
CATALOG_COLUMNS = (
    ("manufacturer", "Manufacturer"),
    ("model", "Model"),
    ("nominal_od_in", "OD (in)"),
    ("nominal_id_in", "ID (in)"),
    ("nominal_weight_ppf", "Weight (ppf)"),
    ("grade", "Grade"),
    ("connection", "Connection"),
    ("source", "Source"),
    ("status", "Status"),
)


def _fmt(value: Any) -> str:
    """Human cell text: blank for unknown, ``:g`` for floats (5.0 -> '5')."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


@dataclass(frozen=True)
class CatalogRow:
    """One browse-grid row derived from a persisted :class:`DrillPipeSpec`.

    ``spec`` is retained so a selection can open the full detail/provenance view
    without a second DB round-trip. ``fingerprint`` is the stable engineering
    identity (never a DB primary key) used for lookups and selection.
    """

    fingerprint: str
    spec: DrillPipeSpec
    cells: Dict[str, str]
    search_blob: str

    def cell(self, key: str) -> str:
        return self.cells.get(key, "")


def _row_for(spec: DrillPipeSpec) -> CatalogRow:
    prov = spec.provenance
    values = {
        "manufacturer": spec.manufacturer,
        "model": spec.model,
        "nominal_od_in": spec.nominal_od_in,
        "nominal_id_in": spec.nominal_id_in,
        "nominal_weight_ppf": spec.nominal_weight_ppf,
        "grade": spec.grade,
        "connection": spec.connection,
        "source": prov.source,
        "status": prov.status,
    }
    cells = {k: _fmt(values.get(k)) for k, _ in CATALOG_COLUMNS}
    # Search blob is the normalized concatenation of every visible cell plus the
    # fingerprint, so search reuses the canonical normalizer (no second impl).
    blob = _norm_header(" ".join(v for v in cells.values() if v))
    fp = spec.identity_fingerprint()
    return CatalogRow(fp, spec, cells, f"{blob} {fp.lower()}")


def build_catalog_rows(specs: Sequence[DrillPipeSpec]) -> List[CatalogRow]:
    """Build browse-grid rows for every offerable persisted spec.

    Only specs with an engineering identity (OD and weight) are shown — a row
    without identity cannot be a usable catalog entry and would only be
    misleading. Ordering is preserved from the repository, which already returns
    a deterministic engineering order.
    """
    rows: List[CatalogRow] = []
    for spec in specs:
        if spec.nominal_od_in is None or spec.nominal_weight_ppf is None:
            continue
        rows.append(_row_for(spec))
    return rows


def filter_catalog_rows(rows: Sequence[CatalogRow], query: str) -> List[CatalogRow]:
    """Case/space-insensitive substring filter across all visible fields.

    Reuses the canonical header normalizer for both the stored blob and the
    query so search matches the same way identity does: case is folded and
    runs of whitespace are collapsed (e.g. ' NC50 ' and '5-1/2  FH' match), but
    a single internal space is significant ('nc 50' != 'nc50'). An empty query
    returns all rows unchanged.
    """
    q = _norm_header(query)
    if not q:
        return list(rows)
    return [r for r in rows if q in r.search_blob]


# --------------------------------------------------------------------------
# Detail / provenance view
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DetailField:
    label: str
    value: str
    group: str  # "Identity" | "Engineering" | "Provenance" | "Issues"


def build_detail_fields(spec: DrillPipeSpec) -> List[DetailField]:
    """Full, human-auditable detail for one catalog record.

    Answers "exactly what engineering specification is this, and where did it
    come from?" — engineering identity, canonical values, provenance (source
    file/sheet/row), any unmapped vendor columns, and any normalization issues.
    It deliberately exposes the engineering ``fingerprint`` as the identity and
    NEVER a raw database primary key (mission §8).
    """
    prov = spec.provenance
    fields: List[DetailField] = [
        DetailField("Manufacturer", _fmt(spec.manufacturer), "Identity"),
        DetailField("Model", _fmt(spec.model), "Identity"),
        DetailField("Grade", _fmt(spec.grade), "Identity"),
        DetailField("Connection", _fmt(spec.connection), "Identity"),
        DetailField("Identity fingerprint", spec.identity_fingerprint(), "Identity"),

        DetailField("Nominal OD (in)", _fmt(spec.nominal_od_in), "Engineering"),
        DetailField("Nominal ID (in)", _fmt(spec.nominal_id_in), "Engineering"),
        DetailField("Nominal weight (ppf)", _fmt(spec.nominal_weight_ppf), "Engineering"),
        DetailField("Tool-joint OD (in)", _fmt(spec.tool_joint_od_in), "Engineering"),
        DetailField("Tool-joint ID (in)", _fmt(spec.tool_joint_id_in), "Engineering"),
        DetailField("Drift (in)", _fmt(spec.drift_in), "Engineering"),
        DetailField("Tensile rating (klbf)", _fmt(spec.tensile_rating_klbf), "Engineering"),

        DetailField("Source", _fmt(prov.source), "Provenance"),
        DetailField("Source revision", _fmt(prov.source_revision), "Provenance"),
        DetailField("Status", _fmt(prov.status), "Provenance"),
        DetailField("Import note", _fmt(prov.notes), "Provenance"),
    ]
    if prov.effective_date is not None:
        fields.append(DetailField("Effective date", prov.effective_date.isoformat(),
                                  "Provenance"))
    for key, val in (spec.extra or {}).items():
        fields.append(DetailField(f"Vendor column: {key}", _fmt(val), "Provenance"))

    for issue in spec.issues:
        fields.append(DetailField(f"{issue.field} ({issue.kind})", issue.detail, "Issues"))

    return fields


def detail_text(spec: DrillPipeSpec) -> str:
    """Flat, grouped plain-text rendering of :func:`build_detail_fields`.

    Suitable for a read-only detail panel; grouped by section with the group
    header shown once. Empty values are kept (blank) so the absence of a value
    is itself visible and auditable.
    """
    lines: List[str] = []
    current: Optional[str] = None
    for f in build_detail_fields(spec):
        if f.group != current:
            if lines:
                lines.append("")
            lines.append(f"[{f.group}]")
            current = f.group
        lines.append(f"  {f.label}: {f.value}")
    return "\n".join(lines)
