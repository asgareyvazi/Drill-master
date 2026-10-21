"""Unmapped populated content diagnostic for Excel imports.

The extractor keeps every populated source cell in the lossless IR
(``metadata.raw_ir``) but only some cells become canonical values. Before this
diagnostic, a table whose headers matched no canonical signature produced no
``table_results`` and was not mentioned anywhere: the import under-reported
silently.

``unmapped_content_diagnostic`` lists populated cells that no extraction step
accounted for, grouped into connected regions with their sheet and A1 range.

Contract:
* informational only - it proposes no mapping and never changes the status or
  the persisted values of an import;
* it carries locations and counts only, never cell values (DDR content is
  private);
* deterministic for a given workbook and extraction (sheet order of the IR,
  regions ordered by position);
* bounded output (``max_regions_per_sheet``) so it can live in import lineage.

"Accounted for" means: the value cell of a field result, the label cell of the
candidate that produced it, any cell referenced by a table record, and the
owned span of a detected table (its header row through its last data row over
its mapped column range). Everything else that is populated - labels the
extractor did not use, notes, and unrecognised tables - is reported. Text-only
regions are usually labels; regions with numeric cells deserve a look first.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any, Iterable

DIAGNOSTIC_VERSION = 1
_R1C1 = re.compile(r"^R(\d+)C(\d+)$")


def _column_letter(col: int) -> str:
    letters = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _a1(row: int, col: int) -> str:
    return f"{_column_letter(col)}{row}"


def _populated(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, datetime, date, time)):
        return True
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        try:
            float(text)
        except ValueError:  # silent-ok: not a number is an expected answer for a text cell
            return False
        return True
    return False


def _accounted_cells(report: Any) -> set[tuple[str, int, int]]:
    accounted: set[tuple[str, int, int]] = set()
    for result in getattr(report, "field_results", None) or ():
        sheet, row, col = getattr(result, "sheet", "") or "", getattr(result, "row", 0), getattr(result, "col", 0)
        if row and col:
            accounted.add((sheet, int(row), int(col)))
            for candidate in getattr(result, "candidates", None) or ():
                if not isinstance(candidate, dict):
                    continue
                if candidate.get("row") == row and candidate.get("col") == col:
                    label_row, label_col = candidate.get("label_row") or 0, candidate.get("label_col") or 0
                    if label_row and label_col:
                        accounted.add((candidate.get("sheet") or sheet, int(label_row), int(label_col)))
                    break
    for table in getattr(report, "table_results", None) or ():
        sheet = getattr(table, "sheet", "") or ""
        columns = [c.get("col") for c in (getattr(table, "columns", None) or ()) if isinstance(c, dict)]
        columns = [int(c) for c in columns if isinstance(c, int) and c > 0]
        start, end = int(getattr(table, "start_row", 0) or 0), int(getattr(table, "end_row", 0) or 0)
        header = int(getattr(table, "header_row", 0) or 0) or (start - 1 if start > 1 else start)
        if columns and start and end >= start:
            for row in range(max(1, header), end + 1):
                for col in range(min(columns), max(columns) + 1):
                    accounted.add((sheet, row, col))
        for record in getattr(table, "records", None) or ():
            if not isinstance(record, dict):
                continue
            for ref in (record.get("_source_cells") or {}).values():
                match = _R1C1.match(str(ref or ""))
                if match:
                    accounted.add((sheet, int(match.group(1)), int(match.group(2))))
    return accounted


def _regions(cells: dict[tuple[int, int], Any]) -> list[dict]:
    """8-connected components of the given (row, col) cells, ordered by position."""
    remaining = set(cells)
    regions = []
    for start in sorted(cells):
        if start not in remaining:
            continue
        remaining.discard(start)
        stack, members = [start], []
        while stack:
            row, col = stack.pop()
            members.append((row, col))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    neighbour = (row + dr, col + dc)
                    if neighbour in remaining:
                        remaining.discard(neighbour)
                        stack.append(neighbour)
        rows = [r for r, _ in members]
        cols = [c for _, c in members]
        numeric = sum(1 for key in members if _numeric(cells[key]))
        height, width = max(rows) - min(rows) + 1, max(cols) - min(cols) + 1
        regions.append({
            "range": f"{_a1(min(rows), min(cols))}:{_a1(max(rows), max(cols))}",
            "cells": len(members),
            "numeric_cells": numeric,
            "text_cells": len(members) - numeric,
            "rows": height,
            "columns": width,
            "kind": "table-like" if height >= 2 and width >= 2 and len(members) >= 4 else "isolated",
        })
    regions.sort(key=lambda item: (-item["numeric_cells"], -item["cells"], item["range"]))
    return regions


def unmapped_content_diagnostic(report: Any, *, max_regions_per_sheet: int = 25) -> dict:
    """Locations and counts of populated source cells no extraction step used."""
    raw = getattr(report, "raw_document", None)
    raw_cells: Iterable[Any] = getattr(raw, "cells", None) or ()
    accounted = _accounted_cells(report)
    sheets: dict[str, dict[tuple[int, int], Any]] = {}
    populated: dict[str, int] = {}
    for cell in raw_cells:
        location = getattr(cell, "location", None)
        if location is None or not isinstance(location.column, int) or not location.row:
            continue
        value = getattr(cell, "value", None)
        if not _populated(value):
            continue
        sheet = location.sheet or ""
        populated[sheet] = populated.get(sheet, 0) + 1
        bucket = sheets.setdefault(sheet, {})
        if (sheet, location.row, location.column) not in accounted:
            bucket[(location.row, location.column)] = value
    out_sheets = []
    for sheet, cells in sheets.items():  # IR order = workbook sheet order
        regions = _regions(cells) if cells else []
        out_sheets.append({
            "sheet": sheet,
            "populated_cells": populated.get(sheet, 0),
            "unmapped_cells": len(cells),
            "unmapped_numeric_cells": sum(region["numeric_cells"] for region in regions),
            "regions": regions[:max_regions_per_sheet],
            "regions_total": len(regions),
            "regions_truncated": max(0, len(regions) - max_regions_per_sheet),
        })
    return {
        "version": DIAGNOSTIC_VERSION,
        "informational": True,
        "populated_cells": sum(populated.values()),
        "unmapped_cells": sum(item["unmapped_cells"] for item in out_sheets),
        "unmapped_numeric_cells": sum(item["unmapped_numeric_cells"] for item in out_sheets),
        "table_like_regions": sum(
            1 for item in out_sheets for region in item["regions"] if region["kind"] == "table-like"),
        "sheets": out_sheets,
    }


def summary_line(diagnostic: dict | None) -> str:
    """One user-facing line (no values) or '' when nothing is unmapped."""
    if not diagnostic or not diagnostic.get("unmapped_cells"):
        return ""
    return (f"ℹ️ {diagnostic['unmapped_cells']} populated source cell(s) were not mapped "
            f"({diagnostic['unmapped_numeric_cells']} numeric, "
            f"{diagnostic['table_like_regions']} table-like region(s)); "
            "they are kept in the source record and were not imported")
