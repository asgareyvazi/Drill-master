"""Vendor drill-pipe workbook reader → canonical :class:`DrillPipeSpec`.

This is the single authoritative ingestion seam for vendor DrillPipe reference
data. Its ONLY job is to turn the presentation quirks of a real vendor
spreadsheet (title rows, blank rows, unit-suffixed headers, stray columns) into
clean per-row header→value mappings, then hand each row to the already-proven
canonical normalizer :meth:`DrillPipeSpec.from_vendor_row`.

It deliberately does NOT:

* re-implement numeric coercion, unit handling, conflict/invalid detection or
  identity — that all lives in ``drill_pipe.py`` and must not be duplicated;
* persist anything — persistence is
  ``DrillPipeReferenceRepository.import_specs``;
* depend on Qt — so it is testable without a display.

openpyxl and the canonical normalizer are the only dependencies (both already
present in the project); no new third-party library is introduced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.engineering.drill_pipe import (
    DrillPipeSpec,
    Provenance,
    _is_missing,
    _norm_header,
)

# Canonical field aliases the normalizer understands. A header row is only
# accepted when it contains at least this many recognizable engineering columns,
# which lets us skip vendor title/legend rows without hard-coding a layout.
_RECOGNIZED_HEADER_TOKENS = {
    # od / id / weight / grade / connection / manufacturer / model families
    "nominal_od", "nominal od", "od", "od (in)", "od_in", "outer diameter",
    "nominal_id", "nominal id", "id", "id (in)", "id_in", "inner diameter",
    "nominal_weight", "nominal weight", "weight", "weight (ppf)", "weight ppf",
    "ppf", "lb/ft", "grade", "material grade", "steel grade", "pipe grade",
    "connection", "conn", "tool joint connection", "tj connection",
    "manufacturer", "maker", "mfg", "vendor", "supplier",
    "model", "product", "product line", "type", "designation",
    "tool_joint_od", "tool joint od", "tj od", "tj_od",
    "tool_joint_id", "tool joint id", "tj id", "tj_id",
    "drift", "drift diameter", "drift_diameter", "drift (in)",
    "tensile", "tensile rating", "tensile_rating", "pipe body yield",
    "body yield", "yield tension",
}

# How many recognizable columns a candidate row needs to be treated as headers.
_MIN_HEADER_HITS = 2


class DrillPipeImportError(Exception):
    """Raised only for structural failures (unreadable file / no header row).

    Row-level problems are NOT exceptions — they are reported per row so one bad
    row never aborts the batch.
    """


@dataclass
class ParsedRow:
    """One data row lifted from the workbook, mapped to a canonical spec."""

    source_row: int                 # 1-based worksheet row number (audit trail)
    raw: Dict[str, Any]             # header -> cell value, as read
    spec: Optional[DrillPipeSpec]   # None when the row carried no usable data
    note: str = ""                  # why spec is None, when applicable


@dataclass
class ParsedWorkbook:
    """Result of reading one worksheet: the specs plus a full parse audit."""

    source: str
    sheet: str
    header_row: int
    headers: List[str]
    rows: List[ParsedRow] = field(default_factory=list)

    @property
    def specs(self) -> List[DrillPipeSpec]:
        return [r.spec for r in self.rows if r.spec is not None]

    @property
    def skipped(self) -> List[ParsedRow]:
        return [r for r in self.rows if r.spec is None]

    def as_summary(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "sheet": self.sheet,
            "header_row": self.header_row,
            "headers": list(self.headers),
            "data_rows": len(self.rows),
            "specs": len(self.specs),
            "skipped": len(self.skipped),
        }


@dataclass
class WorkbookImportResult:
    """Combined parse + persistence outcome for one imported workbook."""

    parsed: ParsedWorkbook
    persistence: Any  # repositories...ImportSummary (kept loose to avoid import cycle)
    blank_rows: int = 0

    def as_dict(self) -> Dict[str, Any]:
        p = self.persistence
        return {
            "parse": self.parsed.as_summary(),
            "blank_rows": self.blank_rows,
            "inserted": getattr(p, "inserted", 0),
            "unchanged": getattr(p, "unchanged", 0),
            "enriched": getattr(p, "enriched", 0),
            "conflicting": getattr(p, "conflicting", 0),
            "invalid": getattr(p, "invalid", 0),
            "rows_persisted": getattr(p, "rows_seen", 0),
        }


def import_workbook(
    repository,
    path: str,
    *,
    sheet: Optional[str] = None,
    source_label: Optional[str] = None,
    status: str = "unverified",
    created_by: Optional[int] = None,
) -> WorkbookImportResult:
    """Full vertical slice: vendor workbook → canonical specs → persisted catalog.

    Parses the workbook (canonical normalization + provenance), then persists
    every row that produced a spec through ``repository.import_specs`` — the
    established, transaction-safe, conflict-aware path. Truly blank rows are not
    sent to persistence (they are counted separately); every non-blank row,
    including ones the normalizer could not validate, is sent so the repository's
    own NEW / UNCHANGED / ENRICHED / CONFLICT / INVALID accounting stays
    authoritative.
    """
    parsed = parse_workbook(
        path, sheet=sheet, source_label=source_label, status=status
    )
    specs = [r.spec for r in parsed.rows if r.spec is not None]
    blank = sum(1 for r in parsed.rows if r.spec is None)
    persistence = repository.import_specs(specs, created_by=created_by)
    return WorkbookImportResult(parsed=parsed, persistence=persistence, blank_rows=blank)


def _header_hits(values: Tuple[Any, ...]) -> int:
    """Count cells in a candidate row that look like recognizable headers."""
    hits = 0
    for v in values:
        if v is None:
            continue
        if _norm_header(v) in _RECOGNIZED_HEADER_TOKENS:
            hits += 1
    return hits


def _detect_header_row(rows: List[Tuple[Any, ...]], scan_limit: int = 25) -> int:
    """Return the 0-based index of the best header row, or raise.

    Scans the first ``scan_limit`` rows and picks the one with the most
    recognizable engineering-column names (ties → earliest). This tolerates
    title banners, blank rows and legends above the real header without
    hard-coding any single vendor layout.
    """
    best_idx = -1
    best_hits = 0
    for idx, values in enumerate(rows[:scan_limit]):
        hits = _header_hits(values)
        if hits > best_hits:
            best_hits, best_idx = hits, idx
    if best_idx < 0 or best_hits < _MIN_HEADER_HITS:
        raise DrillPipeImportError(
            "No recognizable drill-pipe header row found "
            f"(need \u2265{_MIN_HEADER_HITS} known columns such as OD, weight, grade). "
            "Check the sheet name and that the vendor sheet has a header row."
        )
    return best_idx


def _dedupe_headers(cells: Tuple[Any, ...]) -> List[str]:
    """Build clean, unique header strings for a header row.

    Blank header cells become positional placeholders (``column_N``) so they are
    never confused with a real field; duplicate headers get a numeric suffix so
    two columns cannot silently overwrite each other in the row dict.
    """
    headers: List[str] = []
    seen: Dict[str, int] = {}
    for i, cell in enumerate(cells):
        name = "" if cell is None else str(cell).strip()
        if not name:
            name = f"column_{i + 1}"
        key = name.lower()
        if key in seen:
            seen[key] += 1
            name = f"{name} ({seen[key]})"
        else:
            seen[key] = 1
        headers.append(name)
    return headers


def read_workbook_rows(
    path: str, *, sheet: Optional[str] = None
) -> Tuple[str, List[Tuple[Any, ...]]]:
    """Read every cell row from one worksheet using openpyxl (values only).

    Returns ``(sheet_name, rows)``. Raises :class:`DrillPipeImportError` for
    structural problems (missing file, unreadable workbook, missing sheet).
    """
    p = Path(path)
    if not p.exists():
        raise DrillPipeImportError(f"Workbook not found: {path}")
    try:
        from openpyxl import load_workbook
    except Exception as exc:  # pragma: no cover - openpyxl is a hard dependency
        raise DrillPipeImportError(f"openpyxl unavailable: {exc}") from exc
    try:
        wb = load_workbook(p, data_only=True, read_only=True)
    except Exception as exc:
        raise DrillPipeImportError(f"Could not open workbook: {exc}") from exc
    try:
        if sheet is not None:
            if sheet not in wb.sheetnames:
                raise DrillPipeImportError(
                    f"Sheet {sheet!r} not found; available: {wb.sheetnames}"
                )
            ws = wb[sheet]
        else:
            ws = wb.active
        rows = [tuple(r) for r in ws.iter_rows(values_only=True)]
        return ws.title, rows
    finally:
        wb.close()


def parse_workbook(
    path: str,
    *,
    sheet: Optional[str] = None,
    source_label: Optional[str] = None,
    status: str = "unverified",
) -> ParsedWorkbook:
    """Read a vendor workbook and normalize every data row to a canonical spec.

    Each data row is passed through :meth:`DrillPipeSpec.from_vendor_row`, so all
    numeric/unit/conflict/identity rules and the ``issues`` audit trail are the
    canonical ones — this function adds no parallel normalization. Provenance
    records the workbook, sheet and 1-based source row so an imported spec can be
    traced back to its origin. Rows with no usable engineering data are recorded
    (with a note) rather than silently dropped.
    """
    sheet_name, raw_rows = read_workbook_rows(path, sheet=sheet)
    if not raw_rows:
        raise DrillPipeImportError(f"Worksheet {sheet_name!r} is empty")

    header_idx = _detect_header_row(raw_rows)
    headers = _dedupe_headers(raw_rows[header_idx])
    label = source_label or Path(path).name

    parsed = ParsedWorkbook(
        source=label, sheet=sheet_name, header_row=header_idx + 1, headers=headers
    )

    for offset, values in enumerate(raw_rows[header_idx + 1:]):
        source_row = header_idx + 1 + offset + 1  # 1-based worksheet row
        row = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}

        # A completely empty row (all cells missing) is structural filler, not a
        # rejected spec — record it as skipped with a clear note.
        if all(_is_missing(v) for v in row.values()):
            parsed.rows.append(ParsedRow(source_row, row, None, "blank row"))
            continue

        provenance = Provenance(
            source=f"{label} [{sheet_name}]",
            source_revision="",
            status=status,
            notes=f"row {source_row}",
        )
        spec = DrillPipeSpec.from_vendor_row(row, provenance=provenance)

        # Without a nominal OD and weight the row has no engineering identity and
        # cannot be a catalog entry; surface it as skipped (the repository would
        # reject it as INVALID anyway, but this keeps parse-time auditing clear).
        if not spec.has_identity:
            parsed.rows.append(
                ParsedRow(source_row, row, spec, "no engineering identity (needs OD and weight)")
            )
            continue

        parsed.rows.append(ParsedRow(source_row, row, spec))

    return parsed
