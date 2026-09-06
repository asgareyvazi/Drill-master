"""Common raw/intermediate representation for all document imports.

Excel and external document engines may differ in extraction mechanics, but
canonical mapping consumes the same lossless primitives: source cells, tables,
text blocks, and source coordinates.  This layer intentionally performs no
canonical-field guessing and no type coercion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SourceLocation:
    file: str = ""
    sheet: Optional[str] = None
    page: Optional[int] = None
    row: Optional[int] = None
    column: Optional[int | str] = None
    cell: Optional[str] = None
    coordinates: Optional[tuple[float, ...]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "sheet": self.sheet,
            "page": self.page,
            "row": self.row,
            "column": self.column,
            "cell": self.cell,
            "coordinates": list(self.coordinates) if self.coordinates else None,
        }


@dataclass
class RawCell:
    value: Any
    location: SourceLocation
    formula: Optional[str] = None
    hidden: bool = False
    merged: bool = False
    style: Optional[str] = None


@dataclass
class RawTable:
    headers: list[RawCell] = field(default_factory=list)
    rows: list[list[RawCell]] = field(default_factory=list)
    name: str = ""
    location: Optional[SourceLocation] = None
    classification: str = "unknown"


@dataclass
class RawDocument:
    source_file: str
    tables: list[RawTable] = field(default_factory=list)
    cells: list[RawCell] = field(default_factory=list)
    text_blocks: list[tuple[str, SourceLocation]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len({cell.location.page for cell in self.cells if cell.location.page is not None})

    @property
    def sheet_count(self) -> int:
        return len({cell.location.sheet for cell in self.cells if cell.location.sheet})

    def to_dict(self, *, include_cells: bool = False) -> dict[str, Any]:
        payload = {
            "source_file": self.source_file,
            "tables": len(self.tables),
            "cells": len(self.cells),
            "text_blocks": len(self.text_blocks),
            "metadata": dict(self.metadata),
        }
        if include_cells:
            payload["cell_values"] = [
                {"value": cell.value, "formula": cell.formula, "location": cell.location.to_dict()}
                for cell in self.cells
            ]
        return payload


def raw_document_from_mineru(document: Any) -> RawDocument:
    """Adapt the MinerU document IR without importing MinerU itself."""
    raw = RawDocument(
        source_file=str(getattr(document, "source_file", "")),
        metadata={
            "backend": getattr(document, "backend", ""),
            "method": getattr(document, "method", ""),
            "engine": "MinerU",
        },
    )
    for block in getattr(document, "text_blocks", []) or []:
        provenance = getattr(block, "provenance", None)
        location = SourceLocation(
            file=raw.source_file,
            sheet=getattr(provenance, "source_sheet", None),
            page=getattr(provenance, "source_page", None),
            row=getattr(provenance, "source_row", None),
            column=getattr(provenance, "source_column", None),
            coordinates=getattr(provenance, "bounding_box", None),
        )
        raw.text_blocks.append((str(getattr(block, "text", "")), location))

    for table in getattr(document, "tables", []) or []:
        provenance = getattr(table, "provenance", None)
        base = SourceLocation(
            file=raw.source_file,
            sheet=getattr(provenance, "source_sheet", None),
            page=getattr(provenance, "source_page", None),
            coordinates=getattr(provenance, "bounding_box", None),
        )
        headers = [
            RawCell(value=header, location=SourceLocation(**{**base.to_dict(), "column": index + 1}))
            for index, header in enumerate(getattr(table, "headers", []) or [])
        ]
        rows: list[list[RawCell]] = []
        for row_number, row in enumerate(getattr(table, "rows", []) or [], 1):
            rows.append([
                RawCell(
                    value=value,
                    location=SourceLocation(**{**base.to_dict(), "row": row_number, "column": index + 1}),
                )
                for index, value in enumerate(row)
            ])
        raw.tables.append(
            RawTable(
                headers=headers,
                rows=rows,
                name=str(getattr(table, "name", "") or ""),
                location=base,
                classification="table",
            )
        )
    return raw


def raw_document_from_workbook(workbook: Any, *, max_cells: int = 250_000) -> RawDocument:
    """Losslessly adapt populated Excel cells, including formulas and hidden state.

    ``data_only=False`` is not forced here; the caller's workbook determines
    whether formula text or cached values are available.  The existing Excel
    extraction path continues to decide how formulas are evaluated; this IR
    merely prevents provenance and layout information from being discarded.
    """
    source_file = str(getattr(workbook, "filename", ""))
    raw = RawDocument(source_file=source_file, metadata={"engine": "Excel"})
    for worksheet in getattr(workbook, "worksheets", []) or []:
        hidden_rows = getattr(worksheet, "row_dimensions", {})
        hidden_columns = getattr(worksheet, "column_dimensions", {})
        merged_ranges = getattr(worksheet, "merged_cells", None)
        merged_cells = set()
        if merged_ranges is not None:
            for merged_range in merged_ranges.ranges:
                for row in range(merged_range.min_row, merged_range.max_row + 1):
                    for col in range(merged_range.min_col, merged_range.max_col + 1):
                        merged_cells.add((row, col))
        for row in worksheet.iter_rows():
            for cell in row:
                if len(raw.cells) >= max_cells:
                    raw.metadata["truncated"] = True
                    return raw
                if cell.value is None:
                    continue
                coordinate = getattr(cell, "coordinate", None)
                location = SourceLocation(
                    file=source_file,
                    sheet=worksheet.title,
                    row=cell.row,
                    column=cell.column,
                    cell=coordinate,
                )
                row_dimension = hidden_rows.get(cell.row)
                column_dimension = hidden_columns.get(getattr(cell, "column_letter", ""))
                raw.cells.append(
                    RawCell(
                        value=cell.value,
                        formula=cell.value if isinstance(cell.value, str) and cell.value.startswith("=") else None,
                        location=location,
                        hidden=bool(getattr(row_dimension, "hidden", False) or getattr(column_dimension, "hidden", False)),
                        merged=(cell.row, cell.column) in merged_cells,
                        style=getattr(cell, "style_id", None),
                    )
                )
    return raw


__all__ = [
    "SourceLocation", "RawCell", "RawTable", "RawDocument",
    "raw_document_from_mineru", "raw_document_from_workbook",
]
