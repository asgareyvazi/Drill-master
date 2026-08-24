"""Workbook-first import analysis shared by Excel and AI mapping.

No values are imported here. The scanner produces an auditable structural
snapshot which is later passed to mapping, review and validation stages.

Professional Features (P0/P1):
- Workbook Scanner: File Name, Size, Type, Version, Sheet Count, Hidden Sheets, Merged Ranges, Hidden Rows/Columns, Used Range, Formula Count, Empty Cell Ratio, Table Count
- Sheet Classifier: Daily Report, Mud, Drilling, BHA, Bit, Survey, Trajectory, Safety, BOP, Logistics, Services, Cost, Planning, Reference, Unknown based on Name/Headers/Content/Data Types/Nearby Titles/Table Shape/AI Semantic
- Table Detector: Row Density, Column Density, Blank Row/Column, Border, Style, Merged Cells, Header Pattern, Data Type Consistency, Title, Repeated Header, handles vertical/horizontal/nested/2-3 row headers/merge/no border/continuation
"""

from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import re
import math
from collections import Counter


@dataclass
class ColumnProfile:
    column: int
    header: str
    samples: List[str]
    data_type: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    blank_ratio: float = 0.0
    density: float = 0.0
    confidence: float = 0.0


@dataclass
class TableRegion:
    sheet: str
    min_row: int
    max_row: int
    min_col: int
    max_col: int
    title: str = ""
    headers: List[str] = field(default_factory=list)
    columns: List[Dict] = field(default_factory=list)
    row_density: float = 0.0
    col_density: float = 0.0
    table_type: str = "unknown"  # vertical, horizontal, nested, continuation
    header_rows: int = 1
    has_merged: bool = False
    has_border: bool = False
    data_type_consistency: float = 0.0
    detected_class: str = "Unknown"


# Sheet classification taxonomy
SHEET_CLASSES = [
    "Daily Report",
    "Mud",
    "Drilling",
    "BHA",
    "Bit",
    "Survey",
    "Trajectory",
    "Safety",
    "BOP",
    "Logistics",
    "Services",
    "Cost",
    "Planning",
    "Reference",
    "Unknown",
]

SHEET_KEYWORDS = {
    "Daily Report": ["daily", "ddr", "report", "remark", "operation", "activities", "24h", "24 hour", "rig activity"],
    "Mud": ["mud", "fluid", "rheology", "pv", "yp", "gel", "chemical", "funnel", "filtrate"],
    "Drilling": ["drilling", "parameter", "wob", "rpm", "torque", "rop", "spp", "pump"],
    "BHA": ["bha", "bottom hole assembly", "component", "stabilizer", "drill collar", "dc", "hwdp"],
    "Bit": ["bit", "iadc", "nozzle", "tfa", "bit run", "bit record"],
    "Survey": ["survey", "md", "inclination", "azimuth", "tvd", "north", "east", "dls", "deviation", "directional"],
    "Trajectory": ["trajectory", "wellbore", "plan", "vs", "hd", "section view", "plan view"],
    "Safety": ["safety", "hse", "lti", "incident", "near miss", "drill", "h2s", "fire", "bop drill"],
    "BOP": ["bop", "blow out preventer", "wellhead", "ram", "annular", "koomey", "pressure test"],
    "Logistics": ["logistics", "pob", "personnel", "fuel", "water", "bulk", "inventory", "transport", "boat", "helicopter", "crew"],
    "Services": ["service", "company", "contractor", "third party", "service company"],
    "Cost": ["cost", "afe", "expense", "budget", "invoice", "daily cost"],
    "Planning": ["plan", "lookahead", "forecast", "7 days", "schedule"],
    "Reference": ["reference", "lookup", "master", "config", "template", "code", "activity code"],
}


class WorkbookScanner:
    """Professional workbook scanner."""

    def scan(self, workbook, file_path: str = "") -> Dict[str, Any]:
        """Full workbook scan with professional metadata."""
        result = {
            "file_name": Path(file_path).name if file_path else "",
            "file_size": 0,
            "file_type": Path(file_path).suffix if file_path else ".xlsx",
            "workbook_version": getattr(workbook, "excel_base_date", "1900"),
            "sheet_count": len(workbook.worksheets),
            "hidden_sheets": 0,
            "sheets": [],
            "tables": [],
            "total_merged_ranges": 0,
            "total_formula_count": 0,
            "overall_density": 0.0,
        }

        if file_path:
            try:
                result["file_size"] = Path(file_path).stat().st_size
            except Exception:
                pass

        total_cells = 0
        total_non_empty = 0
        total_formulas = 0

        for sheet in workbook.worksheets:
            sheet_info = self._scan_sheet(sheet)
            result["sheets"].append(sheet_info)
            if sheet_info.get("hidden"):
                result["hidden_sheets"] += 1
            result["total_merged_ranges"] += sheet_info.get("merged_ranges", 0)
            result["total_formula_count"] += sheet_info.get("formula_count", 0)
            total_cells += sheet_info.get("total_cells", 0)
            total_non_empty += sheet_info.get("non_empty", 0)

            # Detect tables for this sheet
            cells = sheet_info.get("_cells_cache")
            if cells is None:
                cells = {(cell.row, cell.column): cell.value for row in sheet.iter_rows() for cell in row if cell.value not in (None, "")}
            tables = self.detect_tables(sheet, cells, sheet_info)
            result["tables"].extend([asdict(t) for t in tables])
            # Remove internal cache
            sheet_info.pop("_cells_cache", None)

        if total_cells > 0:
            result["overall_density"] = round(total_non_empty / total_cells, 4)
            result["empty_cell_ratio"] = round(1 - total_non_empty / total_cells, 4)
        else:
            result["empty_cell_ratio"] = 1.0

        result["table_count"] = len(result["tables"])
        return result

    def _scan_sheet(self, sheet) -> Dict[str, Any]:
        """Scan single sheet with all professional metrics."""
        cells = {}
        formula_count = 0
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value not in (None, ""):
                    cells[(cell.row, cell.column)] = cell.value
                # Formula detection
                if cell.data_type == "f":
                    formula_count += 1

        # Hidden rows/columns detection
        hidden_rows = 0
        hidden_cols = 0
        try:
            # openpyxl stores hidden in row_dimensions and column_dimensions
            hidden_rows = sum(1 for dim in sheet.row_dimensions.values() if getattr(dim, "hidden", False))
            hidden_cols = sum(1 for dim in sheet.column_dimensions.values() if getattr(dim, "hidden", False))
        except Exception:
            pass

        if cells:
            rows = [r for r, _ in cells]
            cols = [c for _, c in cells]
            min_row, max_row, min_col, max_col = min(rows), max(rows), min(cols), max(cols)
            used_rows = max_row - min_row + 1
            used_cols = max_col - min_col + 1
            area = max(1, used_rows * used_cols)
            density = len(cells) / area
            total_cells = sheet.max_row * sheet.max_column if sheet.max_row and sheet.max_column else area
            empty_ratio = 1 - len(cells) / max(1, total_cells)
        else:
            min_row = max_row = min_col = max_col = 0
            density = 0.0
            total_cells = 0
            empty_ratio = 1.0
            used_rows = 0
            used_cols = 0

        sheet_info = {
            "name": sheet.title,
            "rows": sheet.max_row,
            "columns": sheet.max_column,
            "hidden": sheet.sheet_state != "visible",
            "merged_ranges": len(sheet.merged_cells.ranges),
            "hidden_rows": hidden_rows,
            "hidden_columns": hidden_cols,
            "used_range": f"{min_col}:{min_row}-{max_col}:{max_row}" if cells else "",
            "used_range_rows": used_rows,
            "used_range_cols": used_cols,
            "non_empty": len(cells),
            "total_cells": total_cells,
            "density": round(density, 4),
            "empty_cell_ratio": round(empty_ratio, 4),
            "formula_count": formula_count,
            "table_count": 0,  # will be updated after table detection
            "_cells_cache": cells,  # internal, removed later
        }
        return sheet_info

    def detect_tables(self, sheet, cells=None, sheet_info=None) -> List[TableRegion]:
        """Advanced table detector.

        Handles:
        - Multiple vertical tables (separated by blank rows)
        - Multiple horizontal tables (side by side)
        - Nested tables
        - 2-row / 3-row headers
        - Merged cells
        - No border tables
        - Continuation tables
        """
        cells = cells or {(cell.row, cell.column): cell.value for row in sheet.iter_rows() for cell in row if cell.value not in (None, "")}
        if not cells:
            return []

        # Check for merged cells
        has_merged = False
        try:
            has_merged = len(sheet.merged_cells.ranges) > 0
        except Exception:
            pass

        # Build row population map
        populated: Dict[int, List[int]] = {}
        for row, col in cells:
            populated.setdefault(row, []).append(col)

        # Detect bands with at least 2 populated cells, split on >=2 consecutive empty rows
        bands: List[List[int]] = []
        current: List[int] = []
        empty_streak = 0

        if populated:
            min_r = min(populated)
            max_r = max(populated)
            for r in range(min_r, max_r + 1):
                count = len(populated.get(r, []))
                if count >= 2:
                    current.append(r)
                    empty_streak = 0
                else:
                    empty_streak += 1
                    if current and empty_streak >= 2:
                        # End of band
                        bands.append(current)
                        current = []
                        empty_streak = 0
            if current:
                bands.append(current)

        regions: List[TableRegion] = []

        for band in bands:
            if len(band) < 2:
                continue

            # For each band, check if there are horizontal splits (side-by-side tables)
            # by analyzing column gaps
            all_cols = sorted({col for row in band for col in populated.get(row, [])})
            if len(all_cols) < 2:
                continue

            # Detect column gaps >=2 empty columns as table separators
            col_bands = []
            curr_cols = []
            col_empty = 0
            for idx, col in enumerate(all_cols):
                if not curr_cols:
                    curr_cols.append(col)
                    continue
                gap = col - curr_cols[-1]
                if gap >= 3:  # gap of 2+ empty columns
                    if len(curr_cols) >= 2:
                        col_bands.append(curr_cols)
                    curr_cols = [col]
                else:
                    curr_cols.append(col)
            if len(curr_cols) >= 2:
                col_bands.append(curr_cols)

            # If no column split, use all columns as one table
            if not col_bands:
                col_bands = [all_cols]

            for cols in col_bands:
                if len(cols) < 2 or len(band) < 2:
                    continue

                # Detect header rows: could be 1, 2, or 3 rows
                header_rows = self._detect_header_rows(band, cols, cells)
                header_row_count = len(header_rows)

                if header_row_count == 0:
                    header_row = band[0]
                    headers = [str(cells.get((header_row, col), "")).strip() for col in cols]
                    header_rows = [header_row]
                else:
                    # Combine multi-row headers
                    headers = []
                    for col in cols:
                        parts = []
                        for hr in header_rows:
                            v = cells.get((hr, col))
                            if v not in (None, ""):
                                parts.append(str(v).strip())
                        # Join with space, avoid duplicates
                        combined = " ".join(parts).strip()
                        # If last part already contains previous, use last
                        headers.append(combined)

                # Title: row before first header
                title = ""
                first_header = header_rows[0]
                if first_header > 1:
                    # Look 1-2 rows above for title
                    for offset in (1, 2):
                        tr = first_header - offset
                        title_parts = []
                        for col in cols:
                            v = cells.get((tr, col))
                            if v not in (None, ""):
                                title_parts.append(str(v).strip())
                        if title_parts:
                            # If single cell spans multiple columns (merged title), take it
                            if len(title_parts) == 1 and len(cols) > 2:
                                title = title_parts[0]
                                break
                            # If title row has fewer populated cells, it's likely a title
                            if len(title_parts) < len(cols) * 0.6:
                                title = " ".join(title_parts)
                                break
                    if not title:
                        # Join first row above if it looks like title (not header-like)
                        title = " ".join(
                            str(cells.get((first_header - 1, col), "")).strip()
                            for col in cols
                            if cells.get((first_header - 1, col)) not in (None, "")
                        )

                # Calculate densities
                data_rows = [r for r in band if r not in header_rows]
                if not data_rows:
                    continue

                total_possible = len(data_rows) * len(cols)
                actual_data = sum(1 for r in data_rows for c in cols if (r, c) in cells)
                row_density = actual_data / max(1, total_possible)

                # Column density: how many rows have data per column
                col_density = sum(1 for c in cols if any((r, c) in cells for r in data_rows)) / max(1, len(cols))

                # Data type consistency
                consistency = self._calculate_type_consistency(data_rows, cols, cells)

                # Detect table type
                table_type = self._detect_table_type(band, cols, cells, title, headers)

                # Classify sheet/table
                detected_class = self.classify_table(title, headers, cells, band, cols)

                # Build column profiles
                profiles = []
                for col, header in zip(cols, headers):
                    values = [cells[(row, col)] for row in data_rows if (row, col) in cells]
                    profile = self.profile_column(col, header, values, len(data_rows))
                    profiles.append(asdict(profile))

                region = TableRegion(
                    sheet=sheet.title,
                    min_row=band[0],
                    max_row=band[-1],
                    min_col=min(cols),
                    max_col=max(cols),
                    title=title,
                    headers=headers,
                    columns=profiles,
                    row_density=round(row_density, 4),
                    col_density=round(col_density, 4),
                    table_type=table_type,
                    header_rows=header_row_count,
                    has_merged=has_merged,
                    has_border=False,  # Border detection would require style inspection
                    data_type_consistency=round(consistency, 4),
                    detected_class=detected_class,
                )
                regions.append(region)

        # Update sheet_info table count
        if sheet_info is not None:
            sheet_info["table_count"] = len(regions)

        return regions

    def _detect_header_rows(self, band: List[int], cols: List[int], cells: Dict) -> List[int]:
        """Detect if header is 1, 2, or 3 rows.

        Heuristic:
        - Header rows typically have more text, less numeric
        - First row(s) with high text ratio
        - Repeated header pattern detection
        """
        if len(band) < 2:
            return [band[0]] if band else []

        # Analyze first 3 rows for header characteristics
        header_candidates = []
        for idx in range(min(3, len(band))):
            row = band[idx]
            text_count = 0
            numeric_count = 0
            for col in cols:
                v = cells.get((row, col))
                if v in (None, ""):
                    continue
                try:
                    float(str(v).replace(",", ""))
                    numeric_count += 1
                except (ValueError, TypeError):
                    text_count += 1

            total = text_count + numeric_count
            if total == 0:
                continue
            text_ratio = text_count / max(1, total)
            # Header if text_ratio > 0.6
            if text_ratio >= 0.6:
                header_candidates.append(row)
            else:
                # If we already found headers and now numeric dominates, stop
                if header_candidates:
                    break

        # At least one header row
        if not header_candidates:
            return [band[0]]

        # Check for repeated header pattern in band
        # If same header text appears again later, it's likely a new table, not multi-row header
        # So we limit to consecutive rows at start
        return header_candidates[:3]  # max 3-row header

    def _calculate_type_consistency(self, data_rows: List[int], cols: List[int], cells: Dict) -> float:
        """Calculate data type consistency per column, averaged."""
        consistencies = []
        for col in cols:
            values = [cells.get((r, col)) for r in data_rows if (r, col) in cells]
            if not values:
                continue
            # Determine dominant type
            numeric = 0
            date_count = 0
            text = 0
            for v in values:
                try:
                    float(str(v).replace(",", ""))
                    numeric += 1
                except (ValueError, TypeError):
                    if hasattr(v, "year") and hasattr(v, "month"):
                        date_count += 1
                    else:
                        text += 1
            dominant = max(numeric, date_count, text)
            consistency = dominant / len(values) if values else 0
            consistencies.append(consistency)

        return sum(consistencies) / len(consistencies) if consistencies else 0.0

    def _detect_table_type(self, band: List[int], cols: List[int], cells: Dict, title: str, headers: List[str]) -> str:
        """Detect table type: vertical, horizontal, nested, continuation."""
        title_lower = title.lower() if title else ""
        headers_lower = " ".join(h.lower() for h in headers).lower()

        # Check for nested indicators
        if any(x in title_lower for x in ["bha", "bit", "assembly"]):
            # BHA often has nested structure
            return "nested"

        # Continuation: if title contains "continued" or band is very long
        if "continu" in title_lower or len(band) > 100:
            return "continuation"

        # Vertical: most tables are vertical (headers in row, data in rows below)
        # Horizontal would have headers in column
        # For now, default vertical, but detect horizontal by shape
        if len(band) < len(cols) * 0.5:
            # More columns than rows - could be horizontal
            return "horizontal"

        return "vertical"

    @staticmethod
    def classify_table(title: str, headers: List[str], cells: Dict, band: List[int], cols: List[int]) -> str:
        """Classify table into one of the known classes."""
        text = f"{title} {' '.join(headers)}".lower()

        best_class = "Unknown"
        best_score = 0

        for cls, keywords in SHEET_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw.lower() in text:
                    # Weight by keyword length (more specific = higher)
                    score += len(kw) * 0.5
            if score > best_score:
                best_score = score
                best_class = cls

        # Additional heuristics based on data shape
        if best_score == 0:
            # Check column headers patterns
            if any("from" in h.lower() and "to" in " ".join(headers).lower() for h in headers):
                if any("hrs" in h.lower() or "hour" in h.lower() or "duration" in h.lower() for h in headers):
                    best_class = "Daily Report"
            elif any("md" in h.lower() or "measured depth" in h.lower() for h in headers):
                if any("inc" in h.lower() or "incl" in h.lower() for h in headers):
                    best_class = "Survey"
            elif any("material" in h.lower() or "chemical" in h.lower() for h in headers):
                best_class = "Mud"

        return best_class

    @staticmethod
    def profile_column(column: int, header: str, values: List[Any], total_rows: int) -> ColumnProfile:
        """Profile a column with samples, type, min/max, blank ratio, density."""
        numeric = []
        dates = 0
        blanks = total_rows - len(values)

        for value in values:
            try:
                numeric.append(float(str(value).replace(",", "")))
            except (ValueError, TypeError):
                pass
            if hasattr(value, "year") and hasattr(value, "month"):
                dates += 1

        if numeric and len(numeric) >= max(1, len(values) * 0.6):
            data_type = "numeric"
            min_val = min(numeric) if numeric else None
            max_val = max(numeric) if numeric else None
            confidence = len(numeric) / max(1, len(values))
        elif dates >= max(1, len(values) * 0.6):
            data_type = "date"
            min_val = None
            max_val = None
            confidence = dates / max(1, len(values))
        else:
            data_type = "text"
            min_val = None
            max_val = None
            confidence = 0.7 if values else 0.0

        blank_ratio = blanks / max(1, total_rows)
        density = len(values) / max(1, total_rows)

        return ColumnProfile(
            column=column,
            header=header,
            samples=[str(v)[:80] for v in values[:5]],
            data_type=data_type,
            minimum=min_val,
            maximum=max_val,
            blank_ratio=round(blank_ratio, 4),
            density=round(density, 4),
            confidence=round(confidence, 4),
        )

    @staticmethod
    def compact_context(snapshot: Dict[str, Any], limit=80) -> Dict[str, Any]:
        """Compact context for AI - only Table Title, Header Row, Sample Values, etc."""
        tables = []
        for table in snapshot.get("tables", [])[:limit]:
            # Only send limited, precise context: Title, Headers, Samples, Coordinates, Unit Candidates, Canonical Fields
            columns_compact = []
            for col in table.get("columns", [])[:10]:  # limit columns
                columns_compact.append(
                    {
                        "header": col.get("header", ""),
                        "samples": col.get("samples", [])[:3],
                        "data_type": col.get("data_type", ""),
                        "min": col.get("minimum"),
                        "max": col.get("maximum"),
                    }
                )

            tables.append(
                {
                    "sheet": table.get("sheet", ""),
                    "region": [table.get("min_row"), table.get("max_row"), table.get("min_col"), table.get("max_col")],
                    "title": table.get("title", ""),
                    "headers": table.get("headers", [])[:15],
                    "columns": columns_compact,
                    "row_density": table.get("row_density"),
                    "col_density": table.get("col_density"),
                    "table_type": table.get("table_type"),
                    "header_rows": table.get("header_rows"),
                    "detected_class": table.get("detected_class"),
                    "data_type_consistency": table.get("data_type_consistency"),
                }
            )
        return {"sheets": snapshot.get("sheets", []), "tables": tables, "file_meta": {k: v for k, v in snapshot.items() if k not in ("sheets", "tables")}}


class SheetClassifier:
    """Professional sheet classifier based on multiple signals."""

    def classify(self, sheet_name: str, tables: List[Dict], cell_samples: List[str] = None) -> str:
        """Classify a sheet.

        Signals:
        - Sheet Name
        - Headers
        - Content
        - Data Types
        - Nearby Titles
        - Table Shape
        - AI Semantic Mapping (via keywords for now, AI escalation for ambiguous)
        """
        text = sheet_name.lower()
        all_headers = []
        all_titles = []
        for t in tables:
            all_headers.extend([h.lower() for h in t.get("headers", [])])
            if t.get("title"):
                all_titles.append(t["title"].lower())

        combined = f"{text} {' '.join(all_headers)} {' '.join(all_titles)}"
        if cell_samples:
            combined += f" {' '.join(s.lower() for s in cell_samples[:20])}"

        best_class = "Unknown"
        best_score = 0

        for cls, keywords in SHEET_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw.lower() in combined:
                    score += 1
            # Bonus for sheet name exact match
            for kw in keywords:
                if kw.lower() in text:
                    score += 2

            if score > best_score:
                best_score = score
                best_class = cls

        # If ambiguous (score 0 or tie), return Unknown for AI escalation
        if best_score == 0:
            return "Unknown"

        return best_class

    def classify_all(self, workbook_snapshot: Dict) -> Dict[str, str]:
        """Classify all sheets in workbook."""
        result = {}
        tables_by_sheet: Dict[str, List[Dict]] = {}
        for t in workbook_snapshot.get("tables", []):
            tables_by_sheet.setdefault(t.get("sheet", ""), []).append(t)

        for sheet in workbook_snapshot.get("sheets", []):
            name = sheet.get("name", "")
            tables = tables_by_sheet.get(name, [])
            result[name] = self.classify(name, tables)

        return result
