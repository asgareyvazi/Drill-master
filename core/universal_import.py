"""Workbook-first import analysis shared by Excel and AI mapping.

No values are imported here. The scanner produces an auditable structural
snapshot which is later passed to mapping, review and validation stages.
"""
from dataclasses import dataclass, asdict
from collections import Counter
import math


@dataclass
class ColumnProfile:
    column: int
    header: str
    samples: list
    data_type: str
    minimum: float = None
    maximum: float = None


@dataclass
class TableRegion:
    sheet: str
    min_row: int
    max_row: int
    min_col: int
    max_col: int
    title: str = ""
    headers: list = None
    columns: list = None


class WorkbookScanner:
    def scan(self, workbook):
        result = {"sheets": [], "tables": []}
        for sheet in workbook.worksheets:
            cells = {(cell.row, cell.column): cell.value for row in sheet.iter_rows() for cell in row if cell.value not in (None, "")}
            if cells:
                rows = [r for r, _ in cells]
                cols = [c for _, c in cells]
                min_row, max_row, min_col, max_col = min(rows), max(rows), min(cols), max(cols)
                area = max(1, (max_row - min_row + 1) * (max_col - min_col + 1))
                density = len(cells) / area
            else:
                min_row = max_row = min_col = max_col = 0
                density = 0.0
            sheet_info = {
                "name": sheet.title, "rows": sheet.max_row, "columns": sheet.max_column,
                "hidden": sheet.sheet_state != "visible", "merged_ranges": len(sheet.merged_cells.ranges),
                "used_range": f"{min_col}:{min_row}-{max_col}:{max_row}" if cells else "",
                "non_empty": len(cells), "density": round(density, 4),
            }
            result["sheets"].append(sheet_info)
            result["tables"].extend(asdict(region) for region in self.detect_tables(sheet, cells))
        return result

    def detect_tables(self, sheet, cells=None):
        cells = cells or {(cell.row, cell.column): cell.value for row in sheet.iter_rows() for cell in row if cell.value not in (None, "")}
        if not cells:
            return []
        # Detect row bands with at least two populated cells; split on two
        # consecutive empty rows. This handles several tables on one sheet.
        populated = {}
        for row, col in cells:
            populated.setdefault(row, []).append(col)
        bands, current, empty = [], [], 0
        for row in range(min(populated), max(populated) + 1):
            if len(populated.get(row, [])) >= 2:
                current.append(row); empty = 0
            else:
                empty += 1
                if current and empty >= 2:
                    bands.append(current); current = []; empty = 0
        if current: bands.append(current)
        regions = []
        for band in bands:
            cols = sorted({col for row in band for col in populated[row]})
            if len(cols) < 2 or len(band) < 2:
                continue
            header_row = band[0]
            headers = [str(cells.get((header_row, col), "")).strip() for col in cols]
            title = ""
            if header_row > 1:
                title = " ".join(str(cells.get((header_row - 1, col), "")).strip() for col in cols if cells.get((header_row - 1, col)) not in (None, ""))
            profiles = []
            for col, header in zip(cols, headers):
                values = [cells[(row, col)] for row in band[1:] if (row, col) in cells]
                profiles.append(asdict(self.profile_column(col, header, values)))
            regions.append(TableRegion(sheet.title, band[0], band[-1], min(cols), max(cols), title, headers, profiles))
        return regions

    @staticmethod
    def profile_column(column, header, values):
        numeric = []
        for value in values:
            try: numeric.append(float(str(value).replace(",", "")))
            except (ValueError, TypeError): pass
        if numeric and len(numeric) >= max(1, len(values) * 0.6):
            return ColumnProfile(column, header, [str(v)[:80] for v in values[:5]], "numeric", min(numeric), max(numeric))
        dates = sum(1 for value in values if hasattr(value, "year") and hasattr(value, "month"))
        kind = "date" if dates >= max(1, len(values) * 0.6) else "text"
        return ColumnProfile(column, header, [str(v)[:80] for v in values[:5]], kind)

    @staticmethod
    def compact_context(snapshot, limit=80):
        tables = []
        for table in snapshot.get("tables", [])[:limit]:
            tables.append({"sheet": table["sheet"], "region": [table["min_row"], table["max_row"], table["min_col"], table["max_col"]], "title": table.get("title", ""), "columns": table.get("columns", [])})
        return {"sheets": snapshot.get("sheets", []), "tables": tables}
