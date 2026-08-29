"""Excel Intelligence Layer — Robust, Deterministic, Explainable Extraction.

Architecture:
    Excel File → Workbook Analyzer → Sheet Detector → Merge Cell Analyzer
    → Label/Header Detector → Field Extractor → Dynamic Table Extractor
    → Validator → Conflict Detector → Confidence Scorer → Canonical JSON

Design Principles:
- Static preferred locations + dynamic fallback detection
- No AI/LLM in main extraction path (deterministic first)
- Every extraction has confidence score + source reason
- Existing template mappings preserved as Preferred Locations
- Unknown fields marked UNRESOLVED, never crash
- Conflict detection when preferred ≠ detected values
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Set
from difflib import SequenceMatcher
import re
import logging
import time

logger = logging.getLogger(__name__)


# ==================== Data Classes ====================

@dataclass
class ExtractionResult:
    """Result of extracting a single field."""
    canonical_field: str
    value: Any = None
    status: str = "OK"  # OK, UNRESOLVED, CONFLICT, INVALID
    confidence: float = 0.0
    source: str = ""  # preferred_cell, label_match, alias_match, nearby_search, merge_cell, context_inference
    cell: str = ""  # e.g., "W3"
    row: int = 0
    col: int = 0
    sheet: str = ""
    original_label: str = ""
    label_distance: int = 0  # how far label was from value
    reason: str = ""  # human-readable explanation
    preferred_value: Any = None  # value at preferred cell (if different)
    detected_value: Any = None  # value found by detection
    validation: str = ""  # valid, invalid_type, out_of_range, missing_required
    data_type: str = ""  # numeric, text, date, time

    def to_dict(self) -> dict:
        return {
            "field": self.canonical_field,
            "value": self.value,
            "status": self.status,
            "confidence": round(self.confidence, 2),
            "source": self.source,
            "cell": self.cell,
            "row": self.row,
            "col": self.col,
            "sheet": self.sheet,
            "original_label": self.original_label,
            "reason": self.reason,
            "validation": self.validation,
        }


@dataclass
class TableExtraction:
    """Result of extracting a dynamic table."""
    name: str
    sheet: str
    header_row: int = 0
    start_row: int = 0
    end_row: int = 0
    columns: List[Dict] = field(default_factory=list)
    records: List[Dict] = field(default_factory=list)
    row_count: int = 0
    status: str = "OK"
    confidence: float = 0.0
    reason: str = ""


@dataclass
class ImportReport:
    """Complete import report."""
    file_name: str = ""
    template_version: str = ""
    extraction_time_ms: float = 0.0
    fields_detected: int = 0
    fields_unresolved: int = 0
    fields_conflict: int = 0
    fields_low_confidence: int = 0
    tables_detected: int = 0
    total_rows_extracted: int = 0
    field_results: List[ExtractionResult] = field(default_factory=list)
    table_results: List[TableExtraction] = field(default_factory=list)
    canonical_json: Dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"Fields: {self.fields_detected} detected, "
            f"{self.fields_unresolved} unresolved, "
            f"{self.fields_conflict} conflicts, "
            f"{self.fields_low_confidence} low-confidence | "
            f"Tables: {self.tables_detected} ({self.total_rows_extracted} rows) | "
            f"Time: {self.extraction_time_ms:.0f}ms"
        )


# ==================== Merge Cell Analyzer ====================

class MergeCellAnalyzer:
    """Analyzes merged cells and provides value lookup."""

    def __init__(self, worksheet):
        self._merge_map = {}  # (row, col) → (top_row, top_col, value)
        self._merge_ranges = []
        self._build_map(worksheet)

    def _build_map(self, ws):
        try:
            for merge_range in ws.merged_cells.ranges:
                self._merge_ranges.append(merge_range)
                top_left = ws.cell(merge_range.min_row, merge_range.min_col)
                value = top_left.value
                for row in range(merge_range.min_row, merge_range.max_row + 1):
                    for col in range(merge_range.min_col, merge_range.max_col + 1):
                        self._merge_map[(row, col)] = (
                            merge_range.min_row,
                            merge_range.min_col,
                            value,
                        )
        except Exception as e:
            logger.debug(f"Merge cell analysis error: {e}")

    def get_value(self, row: int, col: int) -> Tuple[Any, bool]:
        """Get value at cell, checking merged cells. Returns (value, is_merged)."""
        key = (row, col)
        if key in self._merge_map:
            top_row, top_col, value = self._merge_map[key]
            return value, True
        return None, False

    def get_top_left(self, row: int, col: int) -> Tuple[int, int]:
        """Get the top-left cell of a merged range containing (row, col)."""
        key = (row, col)
        if key in self._merge_map:
            return self._merge_map[key][0], self._merge_map[key][1]
        return row, col

    def is_merged(self, row: int, col: int) -> bool:
        return (row, col) in self._merge_map

    def find_label_in_merges(self, label: str) -> List[Tuple[int, int, Any]]:
        """Find merged cells whose value matches label."""
        results = []
        seen = set()
        for (row, col), (top_row, top_col, value) in self._merge_map.items():
            if (top_row, top_col) in seen:
                continue
            seen.add((top_row, top_col))
            if value and label.lower() in str(value).lower():
                results.append((top_row, top_col, value))
        return results


# ==================== Label Detector ====================

class LabelDetector:
    """Finds fields by label text matching with aliases and fuzzy matching."""

    def __init__(self, cells: Dict[Tuple[int, int], Any]):
        self.cells = cells
        self._label_index = {}  # normalized_text → [(row, col, value)]
        self._build_index()

    def _build_index(self):
        for (row, col), value in self.cells.items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            normalized = self._normalize(text)
            self._label_index.setdefault(normalized, []).append((row, col, value))

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for matching: lowercase, remove extra spaces, punctuation."""
        t = text.lower().strip()
        t = re.sub(r'[:\?\!]', '', t)
        t = re.sub(r'\s+', ' ', t)
        return t

    def find_exact(self, label: str) -> List[Tuple[int, int, Any]]:
        normalized = self._normalize(label)
        return self._label_index.get(normalized, [])

    def find_aliases(self, aliases: List[str]) -> List[Tuple[int, int, Any, str]]:
        """Find label using list of aliases. Returns (row, col, value, matched_alias)."""
        for alias in aliases:
            matches = self.find_exact(alias)
            if matches:
                return [(r, c, v, alias) for r, c, v in matches]
        return []

    def find_fuzzy(self, label: str, threshold: float = 0.75) -> List[Tuple[int, int, Any, float]]:
        """Find labels similar to given text."""
        normalized = self._normalize(label)
        results = []
        for key, entries in self._label_index.items():
            ratio = SequenceMatcher(None, normalized, key).ratio()
            if ratio >= threshold:
                for row, col, value in entries:
                    results.append((row, col, value, ratio))
        results.sort(key=lambda x: -x[3])
        return results[:5]

    def find_near_label(self, label_row: int, label_col: int,
                        search_radius: int = 5) -> List[Tuple[int, int, Any]]:
        """Find value cells near a label cell (right, below, diagonal)."""
        candidates = []
        for dr in range(-1, search_radius + 1):
            for dc in range(0, search_radius + 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = label_row + dr, label_col + dc
                val = self.cells.get((r, c))
                if val is not None and str(val).strip():
                    # Skip if this cell is also a label
                    if not self._looks_like_label(str(val)):
                        candidates.append((r, c, val))
        return candidates

    def _looks_like_label(self, text: str) -> bool:
        """Heuristic: labels tend to end with :, have no digits, or be short."""
        text = text.strip()
        if not text:
            return False
        if text.endswith(':'):
            return True
        if len(text) < 3:
            return True
        # Values with digits and hyphens (like "AZNS-207") are values, not labels
        has_digits = any(c.isdigit() for c in text)
        has_hyphen = '-' in text
        if has_digits and has_hyphen:
            return False
        # Pure numeric values are not labels
        try:
            float(text.replace(',', '').replace(' ', ''))
            return False
        except ValueError:
            pass
        # Short all-text strings without colon are likely labels
        if not has_digits and len(text) < 20:
            return True
        return False


# ==================== Dynamic Table Extractor ====================

class DynamicTableExtractor:
    """Finds and extracts tables by header detection, not fixed positions."""

    def __init__(self, cells: Dict[Tuple[int, int], Any], merge_analyzer: MergeCellAnalyzer):
        self.cells = cells
        self.merge_analyzer = merge_analyzer

    def find_table_by_header(self, header_keywords: List[str],
                              sheet: str = "") -> Optional[TableExtraction]:
        """Find a table by searching for header row containing keywords."""
        # Group cells by row
        row_texts = {}
        for (row, col), value in self.cells.items():
            if value is None:
                continue
            text = str(value).strip().lower()
            if text:
                row_texts.setdefault(row, {})[col] = text

        # Find row that matches most keywords
        best_row = None
        best_score = 0
        for row, col_texts in row_texts.items():
            all_text = ' '.join(col_texts.values())
            score = sum(1 for kw in header_keywords if kw.lower() in all_text)
            if score > best_score:
                best_score = score
                best_row = row

        if best_row is None or best_score < 2:
            return None

        # Found header row — extract column mapping
        header_cells = row_texts[best_row]
        columns = []
        for col in sorted(header_cells.keys()):
            header_text = header_cells[col]
            columns.append({
                "col": col,
                "header": header_text,
                "canonical": self._guess_canonical(header_text),
            })

        # Find data rows (below header, until blank or next header)
        start_row = best_row + 1
        end_row = start_row
        blank_count = 0
        for r in range(start_row, start_row + 500):
            has_data = any((r, c) in self.cells and self.cells[(r, c)] is not None
                          for c in [col_info["col"] for col_info in columns])
            if has_data:
                end_row = r
                blank_count = 0
            else:
                blank_count += 1
                if blank_count >= 3:
                    break

        # Extract records
        records = []
        for r in range(start_row, end_row + 1):
            record = {}
            has_value = False
            for col_info in columns:
                c = col_info["col"]
                val = self.cells.get((r, c))
                if val is not None:
                    has_value = True
                    key = col_info.get("canonical", "").split(".")[-1] if col_info.get("canonical") else col_info["header"]
                    record[key] = val
            if has_value and record:
                records.append(record)

        return TableExtraction(
            name=header_keywords[0],
            sheet=sheet,
            header_row=best_row,
            start_row=start_row,
            end_row=end_row,
            columns=columns,
            records=records,
            row_count=len(records),
            confidence=min(1.0, best_score / len(header_keywords)) if header_keywords else 0.5,
        )

    def find_table_by_template(self, table_def: Dict, sheet: str = "") -> TableExtraction:
        """Extract table using template definition with dynamic fallback."""
        columns = table_def.get("columns", [])
        start_row = table_def.get("start_row", 0)

        if not columns or not start_row:
            return TableExtraction(name="unknown", sheet=sheet, status="INVALID_DEF")

        # Step 1: Try preferred start_row
        # Step 2: If no data, search for header keywords
        header_keywords = [col.get("field", "") for col in columns[:3]]

        # Verify start_row has data
        has_data = False
        for col_def in columns:
            c = col_def.get("col", 0)
            if self.cells.get((start_row, c)) is not None:
                has_data = True
                break

        actual_start = start_row
        if not has_data:
            # Dynamic search for header
            for r in range(max(1, start_row - 20), start_row + 20):
                matches = sum(1 for col_def in columns
                             if self.cells.get((r, col_def.get("col", 0))) is not None
                             and any(kw.lower() in str(self.cells.get((r, col_def.get("col", 0)), "")).lower()
                                    for kw in header_keywords if kw))
                if matches >= 2:
                    actual_start = r + 1  # data starts after header
                    break

        # Find end row
        end_row = actual_start
        blank_count = 0
        end_marker = table_def.get("end_marker", "").lower()
        for r in range(actual_start, actual_start + 500):
            has_row_data = any(
                self.cells.get((r, col_def.get("col", 0))) is not None
                for col_def in columns
            )
            # Check end marker
            if end_marker:
                for c in range(1, 60):
                    val = self.cells.get((r, c))
                    if val and str(val).strip().lower() == end_marker:
                        return self._build_table_result(
                            table_def, sheet, actual_start, r - 1, columns
                        )

            if has_row_data:
                end_row = r
                blank_count = 0
            else:
                blank_count += 1
                if blank_count >= 3:
                    break

        return self._build_table_result(table_def, sheet, actual_start, end_row, columns)

    def _build_table_result(self, table_def, sheet, start_row, end_row, columns):
        records = []
        for r in range(start_row, end_row + 1):
            record = {}
            has_value = False
            for col_def in columns:
                c = col_def.get("col", 0)
                val = self.cells.get((r, c))
                # Also check merged cells
                if val is None:
                    val, _ = self.merge_analyzer.get_value(r, c)
                if val is not None:
                    has_value = True
                    canonical = col_def.get("canonical", "")
                    key = canonical.split(".")[-1] if "." in canonical else col_def.get("field", f"col_{c}")
                    record[key] = val
            if has_value and record:
                records.append(record)

        return TableExtraction(
            name=table_def.get("columns", [{}])[0].get("field", "table") if table_def.get("columns") else "table",
            sheet=sheet,
            start_row=start_row,
            end_row=end_row,
            columns=columns,
            records=records,
            row_count=len(records),
            confidence=0.95 if records else 0.0,
        )

    @staticmethod
    def _guess_canonical(header_text: str) -> str:
        """Guess canonical field from header text."""
        h = header_text.lower().strip()
        mappings = {
            "well name": "well_info.name", "well": "well_info.name",
            "rig name": "well_info.rig_name", "rig": "well_info.rig_name",
            "client": "well_info.client", "operator": "well_info.operator",
            "mud weight": "mud_report.mw", "mw": "mud_report.mw",
            "bit size": "drilling_params.bit_size",
            "md": "survey.md", "inc": "survey.inc", "azi": "survey.azi",
            "tvd": "survey.tvd", "north": "survey.north", "east": "survey.east",
            "dls": "survey.dls",
            "from": "time_log.time_from", "to": "time_log.time_to",
            "duration": "time_log.duration", "hrs": "time_log.duration",
            "main code": "time_log.main_code", "sub code": "time_log.sub_code",
            "activity": "time_log.activity_description",
            "description": "time_log.activity_description",
        }
        for key, canonical in mappings.items():
            if key in h:
                return canonical
        return ""


# ==================== Field Extractor ====================

class FieldExtractor:
    """Extracts a single field using multi-strategy approach."""

    def __init__(self, cells: Dict[Tuple[int, int], Any],
                 merge_analyzer: MergeCellAnalyzer,
                 label_detector: LabelDetector):
        self.cells = cells
        self.merge = merge_analyzer
        self.labels = label_detector

    def extract(self, field_def: Dict, canonical: str, sheet: str = "") -> ExtractionResult:
        """Extract a field using priority chain:
        1. Preferred cell (from template)
        2. Merge cell check
        3. Label exact match
        4. Label alias match
        5. Label fuzzy match
        6. Near-label search
        7. Mark UNRESOLVED
        """
        row = field_def.get("row", 0)
        col = field_def.get("col", 0)
        field_name = field_def.get("field", canonical)
        expected_type = self._guess_type(canonical)

        # Strategy 1: Preferred cell
        value = self.cells.get((row, col))
        if value is not None and str(value).strip():
            return ExtractionResult(
                canonical_field=canonical,
                value=value,
                status="OK",
                confidence=1.0,
                source="preferred_cell",
                cell=f"{self._col_letter(col)}{row}",
                row=row, col=col, sheet=sheet,
                reason=f"Value at preferred cell {self._col_letter(col)}{row}",
                data_type=expected_type,
                validation=self._validate(value, expected_type),
            )

        # Strategy 2: Merge cell
        merge_val, is_merged = self.merge.get_value(row, col)
        if merge_val is not None and str(merge_val).strip():
            return ExtractionResult(
                canonical_field=canonical,
                value=merge_val,
                status="OK",
                confidence=0.95,
                source="merge_cell",
                cell=f"{self._col_letter(col)}{row}",
                row=row, col=col, sheet=sheet,
                reason=f"Value from merged cell at {self._col_letter(col)}{row}",
                data_type=expected_type,
                validation=self._validate(merge_val, expected_type),
            )

        # Strategy 3: Label exact match
        label_matches = self.labels.find_exact(field_name)
        if label_matches:
            for lr, lc, lv in label_matches:
                nearby = self.labels.find_near_label(lr, lc)
                if nearby:
                    nr, nc, nv = nearby[0]
                    return ExtractionResult(
                        canonical_field=canonical,
                        value=nv,
                        status="OK",
                        confidence=0.95,
                        source="label_match",
                        cell=f"{self._col_letter(nc)}{nr}",
                        row=nr, col=nc, sheet=sheet,
                        original_label=lv,
                        label_distance=abs(nr - lr) + abs(nc - lc),
                        reason=f"Label '{lv}' found at {self._col_letter(lc)}{lr}, value at {self._col_letter(nc)}{nr}",
                        data_type=expected_type,
                        validation=self._validate(nv, expected_type),
                    )

        # Strategy 4: Alias match
        aliases = self._get_aliases(canonical)
        alias_matches = self.labels.find_aliases(aliases)
        if alias_matches:
            for lr, lc, lv, matched_alias in alias_matches:
                nearby = self.labels.find_near_label(lr, lc)
                if nearby:
                    nr, nc, nv = nearby[0]
                    return ExtractionResult(
                        canonical_field=canonical,
                        value=nv,
                        status="OK",
                        confidence=0.85,
                        source="alias_match",
                        cell=f"{self._col_letter(nc)}{nr}",
                        row=nr, col=nc, sheet=sheet,
                        original_label=lv,
                        reason=f"Alias '{matched_alias}' matched '{lv}' at {self._col_letter(lc)}{lr}",
                        data_type=expected_type,
                        validation=self._validate(nv, expected_type),
                    )

        # Strategy 5: Fuzzy match
        fuzzy_matches = self.labels.find_fuzzy(field_name, threshold=0.70)
        if fuzzy_matches:
            for lr, lc, lv, ratio in fuzzy_matches:
                nearby = self.labels.find_near_label(lr, lc)
                if nearby:
                    nr, nc, nv = nearby[0]
                    return ExtractionResult(
                        canonical_field=canonical,
                        value=nv,
                        status="OK",
                        confidence=0.50 + ratio * 0.3,
                        source="fuzzy_match",
                        cell=f"{self._col_letter(nc)}{nr}",
                        row=nr, col=nc, sheet=sheet,
                        original_label=lv,
                        reason=f"Fuzzy match ({ratio:.0%}) '{lv}' at {self._col_letter(lc)}{lr}",
                        data_type=expected_type,
                        validation=self._validate(nv, expected_type),
                    )

        # Strategy 6: UNRESOLVED
        return ExtractionResult(
            canonical_field=canonical,
            value=None,
            status="UNRESOLVED",
            confidence=0.0,
            source="not_found",
            reason=f"Field '{field_name}' not found by any strategy",
            data_type=expected_type,
        )

    @staticmethod
    def _validate(value: Any, expected_type: str) -> str:
        if value is None:
            return "missing"
        if expected_type == "numeric":
            try:
                float(str(value).replace(',', ''))
                return "valid"
            except (ValueError, TypeError):
                return "invalid_type"
        if expected_type == "date":
            if hasattr(value, 'year'):
                return "valid"
            try:
                str(value)  # string dates are OK
                return "valid"
            except:
                return "invalid_type"
        return "valid"

    @staticmethod
    def _guess_type(canonical: str) -> str:
        c = canonical.lower()
        if any(x in c for x in ["depth", "md", "tvd", "weight", "pressure", "rop", "rpm",
                                  "torque", "wob", "pv", "yp", "ph", "temp", "length",
                                  "od", "size", "hours", "vol", "amount", "count",
                                  "latitude", "longitude", "northing", "easting",
                                  "mw", "density", "funnel", "gel", "loss", "chloride",
                                  "hardness", "cake", "solid", "water", "oil", "kcl",
                                  "dls", "inc", "azi", "tfa", "hsi", "velocity",
                                  "fuel", "duration", "days", "impact", "elevation",
                                  "target", "heading", "rig_day", "lta"]):
            return "numeric"
        if any(x in c for x in ["date", "time"]):
            return "date"
        return "text"

    @staticmethod
    def _get_aliases(canonical: str) -> List[str]:
        """Get label aliases for a canonical field."""
        alias_map = {
            "well_info.name": ["well name", "well", "well name:", "wellname", "well_name"],
            "well_info.rig_name": ["rig name", "rig", "rig name:", "rigname"],
            "well_info.client": ["client", "client:"],
            "well_info.operator": ["operator", "operator:"],
            "well_info.drilling_contractor": ["drilling contractor", "contractor"],
            "well_info.field_name": ["field", "field:", "field name"],
            "well_info.section_name": ["hole section", "section", "hole section (inch)"],
            "well_info.target_depth": ["estimated final depth", "target depth", "efd"],
            "mud_report.mw": ["mud weight", "mw", "mud wt", "density"],
            "drilling_params.bit_size": ["bit size", "bit size (inch)"],
            "daily_report.depth_2400": ["md (m)@ 24:00", "md @ 24:00", "depth 24:00"],
            "daily_report.depth_0000": ["md (m)@ 0:00", "md @ 0:00", "depth 0:00"],
            "daily_report.depth_0600": ["md (m)@ 6:00 am", "md @ 6:00", "depth 6:00"],
        }
        return alias_map.get(canonical, [canonical.split(".")[-1].replace("_", " ")])

    @staticmethod
    def _col_letter(col: int) -> str:
        result = ""
        while col > 0:
            col, remainder = divmod(col - 1, 26)
            result = chr(65 + remainder) + result
        return result


# ==================== Excel Intelligence (Main Orchestrator) ====================

class ExcelIntelligence:
    """Main orchestrator for robust Excel extraction.

    Usage:
        ei = ExcelIntelligence(workbook, template_v3)
        report = ei.extract()
        canonical_json = report.canonical_json
    """

    def __init__(self, workbook, template: Dict = None):
        self.workbook = workbook
        self.template = template or {}
        self.cell_cache = {}  # sheet_name → {(row, col): value}
        self.merge_analyzers = {}  # sheet_name → MergeCellAnalyzer
        self.label_detectors = {}  # sheet_name → LabelDetector
        self._build_cache()

    def _build_cache(self):
        for ws in self.workbook.worksheets:
            if ws.sheet_state != 'visible' and ws.title.lower() == 'setting':
                continue
            cells = {}
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None and str(cell.value).strip():
                        cells[(cell.row, cell.column)] = cell.value
            self.cell_cache[ws.title] = cells
            self.merge_analyzers[ws.title] = MergeCellAnalyzer(ws)
            self.label_detectors[ws.title] = LabelDetector(cells)

    def extract(self) -> ImportReport:
        """Run full extraction pipeline."""
        start_time = time.time()
        report = ImportReport(
            file_name=getattr(self.workbook, 'filename', ''),
            template_version=self.template.get("version", "none"),
        )

        canonical = {}

        # Process each sheet in template
        for sheet_key, sheet_data in self.template.items():
            if not sheet_key.startswith("sheet_"):
                continue

            actual_sheet = self._resolve_sheet(sheet_key)
            if not actual_sheet:
                continue

            cells = self.cell_cache.get(actual_sheet, {})
            merge = self.merge_analyzers.get(actual_sheet)
            labels = self.label_detectors.get(actual_sheet)
            extractor = FieldExtractor(cells, merge, labels)
            table_extractor = DynamicTableExtractor(cells, merge)

            for section_name, section_data in sheet_data.items():
                if isinstance(section_data, list):
                    # Single fields
                    for field_def in section_data:
                        canonical_path = field_def.get("canonical", "")
                        if not canonical_path:
                            continue

                        result = extractor.extract(field_def, canonical_path, actual_sheet)
                        report.field_results.append(result)

                        if result.status == "OK":
                            report.fields_detected += 1
                            section, key = canonical_path.split(".", 1)
                            canonical.setdefault(section, {})[key] = result.value
                        elif result.status == "UNRESOLVED":
                            report.fields_unresolved += 1
                        if result.confidence < 0.70 and result.confidence > 0:
                            report.fields_low_confidence += 1

                elif isinstance(section_data, dict):
                    if "columns" in section_data:
                        # Table
                        table_result = table_extractor.find_table_by_template(
                            section_data, actual_sheet
                        )
                        report.table_results.append(table_result)
                        report.tables_detected += 1
                        report.total_rows_extracted += table_result.row_count

                        # Map table records to canonical
                        if table_result.records:
                            first_canon = section_data["columns"][0].get("canonical", "")
                            if "." in first_canon:
                                section = first_canon.split(".")[0]
                            else:
                                section = section_name.lower().replace(" ", "_")
                            key_map = {
                                "time_log": "time_logs_24h",
                                "time_log_morning": "time_logs_morning",
                                "survey": "surveys",
                                "mud_chemical": "bulk_materials",
                                "bha": "bha_components",
                                "downhole": "downhole_equipment",
                                "drilling_param": "drilling_params_table",
                                "scr": "scr_data",
                                "bop": "bop_components",
                                "formation": "formation_data",
                                "solid_control": "solid_control",
                                "transport": "boats",
                                "lookahead": "lookahead",
                                "service": "service_companies",
                                "cement": "cement_additives",
                                "fuel_water": "fuel_water_data",
                                "casing": "casing_data",
                                "pob": "pob_data",
                                "time_breakdown": "time_breakdown",
                            }
                            storage_key = key_map.get(section, section)
                            canonical.setdefault(storage_key, []).extend(table_result.records)
                    else:
                        # Nested dict (like Previous Casing Info)
                        for sub_key, sub_data in section_data.items():
                            if isinstance(sub_data, list):
                                for field_def in sub_data:
                                    canon = field_def.get("canonical", "")
                                    if canon:
                                        result = extractor.extract(field_def, canon, actual_sheet)
                                        report.field_results.append(result)
                                        if result.status == "OK":
                                            report.fields_detected += 1
                                            s, k = canon.split(".", 1)
                                            canonical.setdefault(s, {})[k] = result.value
                            elif isinstance(sub_data, dict) and "columns" in sub_data:
                                table_result = table_extractor.find_table_by_template(sub_data, actual_sheet)
                                report.table_results.append(table_result)
                                report.tables_detected += 1
                                report.total_rows_extracted += table_result.row_count

        report.canonical_json = canonical
        report.extraction_time_ms = (time.time() - start_time) * 1000
        return report

    def _resolve_sheet(self, sheet_key: str) -> Optional[str]:
        """Resolve sheet_key to actual sheet name."""
        parts = sheet_key.split("_", 2)
        if len(parts) >= 3:
            hint = parts[2].replace("_", " ").lower()
            for actual_name in self.cell_cache.keys():
                if hint in actual_name.lower() or actual_name.lower() in hint:
                    return actual_name
        # Fallback: first sheet
        if self.cell_cache:
            return list(self.cell_cache.keys())[0]
        return None
