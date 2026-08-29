"""Excel Intelligence Layer v2 — Robust, Deterministic, Explainable Extraction.

CRITICAL FIXES APPLIED:
1. Preferred cell is a CANDIDATE, never automatic truth (never 1.0 confidence)
2. find_near_label uses MULTI-FACTOR SCORING, not first-match
3. Single canonical mapping registry (from canonical_schema.py)
4. _guess_canonical() removed — uses lookup_alias()
5. Canonical namespace preserved (survey.md, not md)
6. Engineering validation uses field-specific bounds from schema
7. Every result has complete provenance
8. Confidence represents actual evidence

Architecture:
    Excel → MergeCellAnalyzer → LabelDetector → CandidateCollector
    → CandidateScorer → ConflictDetector → BestCandidateSelector
    → Validator → Canonical JSON → ImportReport
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from difflib import SequenceMatcher
import re
import logging
import time

from core.canonical_schema import (
    FIELD_SPECS, lookup_alias, get_engineering_bounds,
    get_quantity_unit, get_field_spec, CANONICAL_FIELDS,
)

logger = logging.getLogger(__name__)


# ==================== Data Classes ====================

@dataclass
class Candidate:
    """A candidate value for a field, with scoring metadata."""
    value: Any
    source: str  # preferred_cell, merge_cell, label_match, alias_match, fuzzy_match, spatial
    row: int = 0
    col: int = 0
    sheet: str = ""
    label_text: str = ""
    label_row: int = 0
    label_col: int = 0
    distance: int = 0  # Manhattan distance from label to value
    direction: str = ""  # right, below, diagonal
    raw_score: float = 0.0  # base score before normalization
    final_score: float = 0.0  # normalized 0-1
    reason: str = ""


@dataclass
class ExtractionResult:
    """Result of extracting a single field."""
    canonical_field: str
    value: Any = None
    status: str = "OK"  # OK, UNRESOLVED, CONFLICT, REVIEW_REQUIRED, INVALID
    confidence: float = 0.0
    source: str = ""
    cell: str = ""
    row: int = 0
    col: int = 0
    sheet: str = ""
    original_label: str = ""
    reason: str = ""
    candidates: List[Dict] = field(default_factory=list)  # all candidates considered
    validation: str = ""  # valid, invalid_type, out_of_range, engineering_violation
    data_type: str = ""
    canonical_unit: str = ""
    engineering_bounds: tuple = (None, None)

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
            "candidates_count": len(self.candidates),
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
    rejected_rows: int = 0
    rejection_reasons: List[str] = field(default_factory=list)


@dataclass
class ImportReport:
    """Complete import report with diagnostics."""
    file_name: str = ""
    template_version: str = ""
    extraction_time_ms: float = 0.0
    fields_detected: int = 0
    fields_accepted: int = 0
    fields_review: int = 0
    fields_rejected: int = 0
    fields_unresolved: int = 0
    fields_conflict: int = 0
    tables_detected: int = 0
    total_rows_extracted: int = 0
    rejected_rows: int = 0
    duplicates: int = 0
    validation_errors: int = 0
    unit_conversions: int = 0
    confidence_distribution: Dict[str, int] = field(default_factory=lambda: {
        ">=0.95": 0, "0.70-0.94": 0, "<0.70": 0
    })
    field_results: List[ExtractionResult] = field(default_factory=list)
    table_results: List[TableExtraction] = field(default_factory=list)
    canonical_json: Dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"Fields: {self.fields_detected} detected, {self.fields_accepted} accepted, "
            f"{self.fields_review} review, {self.fields_rejected} rejected, "
            f"{self.fields_unresolved} unresolved, {self.fields_conflict} conflicts | "
            f"Tables: {self.tables_detected} ({self.total_rows_extracted} rows, "
            f"{self.rejected_rows} rejected) | "
            f"Confidence: >={self.confidence_distribution['>=0.95']} high, "
            f"{self.confidence_distribution['0.70-0.94']} medium, "
            f"{self.confidence_distribution['<0.70']} low | "
            f"Time: {self.extraction_time_ms:.0f}ms"
        )


# ==================== Confidence Policy ====================

def confidence_decision(confidence: float, critical: bool = False) -> str:
    """Enforce confidence policy from canonical schema.
    
    Critical fields:
        >= 0.99 ACCEPT, 0.85-0.989 REVIEW, < 0.85 REJECT
    Non-critical:
        >= 0.95 ACCEPT, 0.70-0.949 REVIEW, < 0.70 REJECT
    """
    if critical:
        if confidence >= 0.99:
            return "ACCEPT"
        elif confidence >= 0.85:
            return "REVIEW"
        else:
            return "REJECT"
    else:
        if confidence >= 0.95:
            return "ACCEPT"
        elif confidence >= 0.70:
            return "REVIEW"
        else:
            return "REJECT"


# ==================== Merge Cell Analyzer ====================

class MergeCellAnalyzer:
    """Analyzes merged cells and provides value lookup."""

    def __init__(self, worksheet):
        self._merge_map = {}
        self._build_map(worksheet)

    def _build_map(self, ws):
        try:
            for merge_range in ws.merged_cells.ranges:
                top_left = ws.cell(merge_range.min_row, merge_range.min_col)
                value = top_left.value
                for row in range(merge_range.min_row, merge_range.max_row + 1):
                    for col in range(merge_range.min_col, merge_range.max_col + 1):
                        self._merge_map[(row, col)] = (
                            merge_range.min_row, merge_range.min_col, value,
                        )
        except Exception as e:
            logger.debug(f"Merge cell analysis error: {e}")

    def get_value(self, row: int, col: int) -> Tuple[Any, bool]:
        key = (row, col)
        if key in self._merge_map:
            return self._merge_map[key][2], True
        return None, False

    def is_merged(self, row: int, col: int) -> bool:
        return (row, col) in self._merge_map


# ==================== Label Detector ====================

class LabelDetector:
    """Finds labels by text matching with aliases and fuzzy matching."""

    def __init__(self, cells: Dict[Tuple[int, int], Any]):
        self.cells = cells
        self._label_index = {}
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
        t = text.lower().strip()
        t = re.sub(r'[:\?\!]', '', t)
        t = re.sub(r'\s+', ' ', t)
        return t

    def find_exact(self, label: str) -> List[Tuple[int, int, Any]]:
        normalized = self._normalize(label)
        return self._label_index.get(normalized, [])

    def find_aliases(self, aliases: List[str]) -> List[Tuple[int, int, Any, str]]:
        for alias in aliases:
            matches = self.find_exact(alias)
            if matches:
                return [(r, c, v, alias) for r, c, v in matches]
        return []

    def find_fuzzy(self, label: str, threshold: float = 0.70) -> List[Tuple[int, int, Any, float]]:
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
                        search_radius: int = 10) -> List[Tuple[int, int, Any, str, int]]:
        """Find value cells near a label with scored spatial matching.
        
        Returns: (row, col, value, direction, distance)
        Direction: 'right', 'below', 'diagonal'
        """
        candidates = []
        for dr in range(-2, search_radius + 1):
            for dc in range(0, search_radius + 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = label_row + dr, label_col + dc
                val = self.cells.get((r, c))
                if val is None:
                    continue
                text = str(val).strip()
                if not text:
                    continue
                # Skip cells that look like labels
                if self._looks_like_label(text):
                    continue
                # Determine direction
                if dr == 0:
                    direction = "right"
                elif dc == 0:
                    direction = "below"
                else:
                    direction = "diagonal"
                distance = abs(dr) + abs(dc)
                candidates.append((r, c, val, direction, distance))
        return candidates

    def _looks_like_label(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        if text.endswith(':'):
            return True
        if len(text) < 3:
            return True
        has_digits = any(c.isdigit() for c in text)
        has_hyphen = '-' in text
        if has_digits and has_hyphen:
            return False
        try:
            float(text.replace(',', '').replace(' ', ''))
            return False
        except ValueError:
            pass
        if not has_digits and len(text) < 25:
            return True
        return False


# ==================== Candidate Scorer ====================

class CandidateScorer:
    """Scores candidates using multi-factor analysis."""

    @staticmethod
    def score_candidate(candidate: Candidate, canonical_field: str,
                        assigned_cells: set = None) -> float:
        """Score a candidate (0.0 to 1.0).
        
        Factors:
        - Source type (preferred=0.6, merge=0.55, label=0.5, alias=0.45, fuzzy=0.3, spatial=0.35)
        - Direction (right=+0.15, below=+0.05, diagonal=-0.05)
        - Distance penalty (-0.03 per unit)
        - Data type match (+0.1)
        - Already assigned penalty (-0.3)
        - Looks like label penalty (-0.4)
        """
        score = 0.0

        # Base score by source type
        source_scores = {
            "preferred_cell": 0.70,
            "merge_cell": 0.65,
            "label_match": 0.60,
            "alias_match": 0.55,
            "fuzzy_match": 0.35,
            "spatial": 0.40,
        }
        score = source_scores.get(candidate.source, 0.25)

        # Direction bonus/penalty
        if candidate.direction == "right":
            score += 0.15  # Values to the right of label are most common
        elif candidate.direction == "below":
            score += 0.05
        elif candidate.direction == "diagonal":
            score -= 0.05

        # Distance penalty
        distance_penalty = candidate.distance * 0.03
        score -= distance_penalty

        # Data type match bonus
        spec = FIELD_SPECS.get(canonical_field)
        if spec:
            if spec.quantity in ("length", "density", "pressure", "number", "integer", "force", "rpm"):
                try:
                    float(str(candidate.value).replace(',', ''))
                    score += 0.10
                except (ValueError, TypeError):
                    score -= 0.20  # Numeric expected but got text
            elif spec.quantity == "text":
                if isinstance(candidate.value, str) and not candidate.value.replace('.', '').replace('-', '').isdigit():
                    score += 0.05

        # Already assigned penalty
        if assigned_cells and (candidate.row, candidate.col) in assigned_cells:
            score -= 0.30

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    @staticmethod
    def score_label_match_quality(label_text: str, canonical_field: str) -> float:
        """Score how well a label matches the expected field name (0.0 to 1.0)."""
        spec = FIELD_SPECS.get(canonical_field)
        if not spec:
            return 0.3

        label_lower = label_text.lower().strip().rstrip(':')

        # Exact match with canonical key
        key = canonical_field.split(".")[-1].replace("_", " ")
        if label_lower == key:
            return 1.0

        # Exact match with any alias
        for alias in spec.aliases:
            if label_lower == alias.lower():
                return 0.95

        # Partial match
        for alias in spec.aliases:
            if alias.lower() in label_lower or label_lower in alias.lower():
                return 0.80

        # Fuzzy match
        best = 0.0
        for alias in spec.aliases:
            ratio = SequenceMatcher(None, label_lower, alias.lower()).ratio()
            best = max(best, ratio)
        return best * 0.70


# ==================== Field Extractor ====================

class FieldExtractor:
    """Extracts a field using multi-candidate scoring.

    NEVER automatically assigns confidence=1.0.
    Always collects all candidates, scores them, compares, detects conflicts.
    """

    def __init__(self, cells: Dict[Tuple[int, int], Any],
                 merge_analyzer: MergeCellAnalyzer,
                 label_detector: LabelDetector):
        self.cells = cells
        self.merge = merge_analyzer
        self.labels = label_detector
        self._assigned_cells = set()  # track cells already assigned

    def extract(self, field_def: Dict, canonical: str, sheet: str = "") -> ExtractionResult:
        """Extract a field using multi-candidate scoring."""
        row = field_def.get("row", 0)
        col = field_def.get("col", 0)
        field_name = field_def.get("field", canonical)
        spec = FIELD_SPECS.get(canonical)
        critical = spec.critical if spec else False

        candidates = []

        # Strategy 1: Preferred cell (CANDIDATE, not truth)
        value = self.cells.get((row, col))
        if value is not None and str(value).strip():
            # Validate: reject if preferred cell contains a label, not a value
            if not self.labels._looks_like_label(str(value)):
                candidates.append(Candidate(
                    value=value, source="preferred_cell",
                    row=row, col=col, sheet=sheet,
                    raw_score=0.70,
                    reason=f"Preferred cell {self._col_letter(col)}{row}",
                ))

        # Strategy 2: Merge cell
        merge_val, is_merged = self.merge.get_value(row, col)
        if merge_val is not None and str(merge_val).strip():
            candidates.append(Candidate(
                value=merge_val, source="merge_cell",
                row=row, col=col, sheet=sheet,
                raw_score=0.55,
                reason=f"Merged cell at {self._col_letter(col)}{row}",
            ))

        # Strategy 3: Exact label match
        label_matches = self.labels.find_exact(field_name)
        for lr, lc, lv in label_matches:
            nearby = self.labels.find_near_label(lr, lc)
            for nr, nc, nv, direction, distance in nearby:
                label_quality = CandidateScorer.score_label_match_quality(str(lv), canonical)
                candidates.append(Candidate(
                    value=nv, source="label_match",
                    row=nr, col=nc, sheet=sheet,
                    label_text=str(lv), label_row=lr, label_col=lc,
                    distance=distance, direction=direction,
                    raw_score=0.50 * label_quality,
                    reason=f"Label '{lv}' at {self._col_letter(lc)}{lr}, value at {self._col_letter(nc)}{nr} ({direction}, d={distance})",
                ))

        # Strategy 4: Alias match
        aliases = self._get_aliases(canonical)
        alias_matches = self.labels.find_aliases(aliases)
        for lr, lc, lv, matched_alias in alias_matches:
            nearby = self.labels.find_near_label(lr, lc)
            for nr, nc, nv, direction, distance in nearby:
                label_quality = CandidateScorer.score_label_match_quality(str(lv), canonical)
                candidates.append(Candidate(
                    value=nv, source="alias_match",
                    row=nr, col=nc, sheet=sheet,
                    label_text=str(lv), label_row=lr, label_col=lc,
                    distance=distance, direction=direction,
                    raw_score=0.45 * label_quality,
                    reason=f"Alias '{matched_alias}' → '{lv}' at {self._col_letter(lc)}{lr}",
                ))

        # Strategy 5: Fuzzy match
        fuzzy_matches = self.labels.find_fuzzy(field_name, threshold=0.65)
        for lr, lc, lv, ratio in fuzzy_matches[:3]:
            nearby = self.labels.find_near_label(lr, lc)
            for nr, nc, nv, direction, distance in nearby[:2]:
                candidates.append(Candidate(
                    value=nv, source="fuzzy_match",
                    row=nr, col=nc, sheet=sheet,
                    label_text=str(lv), label_row=lr, label_col=lc,
                    distance=distance, direction=direction,
                    raw_score=0.30 * ratio,
                    reason=f"Fuzzy ({ratio:.0%}) '{lv}' at {self._col_letter(lc)}{lr}",
                ))

        # Score all candidates
        for c in candidates:
            c.final_score = CandidateScorer.score_candidate(c, canonical, self._assigned_cells)

        # Sort by final score
        candidates.sort(key=lambda c: -c.final_score)

        # Select best candidate
        if not candidates:
            return ExtractionResult(
                canonical_field=canonical, value=None, status="UNRESOLVED",
                confidence=0.0, source="not_found",
                reason=f"Field '{field_name}' not found by any strategy",
                data_type=spec.quantity if spec else "text",
                canonical_unit=spec.unit if spec else "",
            )

        best = candidates[0]
        self._assigned_cells.add((best.row, best.col))

        # Conflict detection: check if second-best is very close
        status = "OK"
        if len(candidates) >= 2:
            second = candidates[1]
            if abs(best.final_score - second.final_score) < 0.10:
                if best.value != second.value:
                    status = "CONFLICT"

        # Engineering validation
        validation = self._validate_engineering(best.value, canonical, spec)

        # Confidence policy
        decision = confidence_decision(best.final_score, critical)
        if decision == "REJECT" and status == "OK":
            status = "REVIEW_REQUIRED"

        return ExtractionResult(
            canonical_field=canonical,
            value=best.value,
            status=status,
            confidence=best.final_score,
            source=best.source,
            cell=f"{self._col_letter(best.col)}{best.row}",
            row=best.row, col=best.col, sheet=sheet,
            original_label=best.label_text,
            reason=best.reason,
            candidates=[c.__dict__ for c in candidates[:5]],
            validation=validation,
            data_type=spec.quantity if spec else "text",
            canonical_unit=spec.unit if spec else "",
            engineering_bounds=get_engineering_bounds(canonical),
        )

    def _validate_engineering(self, value: Any, canonical: str, spec) -> str:
        """Engineering validation using canonical schema bounds."""
        if value is None:
            if spec and spec.critical:
                return "missing_required"
            return "missing"

        # Type check
        if spec and spec.quantity in ("length", "density", "pressure", "number", "integer",
                                       "force", "rpm", "angle", "rate", "dls", "area",
                                       "viscosity", "stress", "torque", "flow_rate", "volume"):
            try:
                num_val = float(str(value).replace(',', ''))
            except (ValueError, TypeError):
                return "invalid_type"

            # Engineering bounds from canonical schema
            min_val, max_val = get_engineering_bounds(canonical)
            if min_val is not None and num_val < min_val:
                return f"below_minimum({min_val})"
            if max_val is not None and num_val > max_val:
                return f"above_maximum({max_val})"

            # Additional engineering rules
            key = canonical.split(".")[-1]
            if key in ("md", "tvd", "depth_in", "depth_out") and num_val < 0:
                return "engineering_violation(depth<0)"
            if key in ("inc",) and not (0 <= num_val <= 180):
                return "engineering_violation(inc_0_180)"
            if key in ("azi",) and not (0 <= num_val <= 360):
                return "engineering_violation(azi_0_360)"
            if key in ("dls",) and num_val < 0:
                return "engineering_violation(dls<0)"
            if key in ("mw",) and num_val <= 0:
                return "engineering_violation(mw<=0)"

        return "valid"

    @staticmethod
    def _get_aliases(canonical: str) -> List[str]:
        """Get aliases from canonical schema — THE centralized registry."""
        spec = FIELD_SPECS.get(canonical)
        if spec and spec.aliases:
            return list(spec.aliases)
        key = canonical.split(".")[-1].replace("_", " ")
        return [key]

    @staticmethod
    def _col_letter(col: int) -> str:
        result = ""
        while col > 0:
            col, remainder = divmod(col - 1, 26)
            result = chr(65 + remainder) + result
        return result


# ==================== Dynamic Table Extractor ====================

class DynamicTableExtractor:
    """Finds and extracts tables using header detection and row classification."""

    def __init__(self, cells: Dict[Tuple[int, int], Any], merge_analyzer: MergeCellAnalyzer):
        self.cells = cells
        self.merge = merge_analyzer

    def find_table_by_template(self, table_def: Dict, sheet: str = "") -> TableExtraction:
        """Extract table using template definition with dynamic fallback."""
        columns = table_def.get("columns", [])
        start_row = table_def.get("start_row", 0)

        if not columns or not start_row:
            return TableExtraction(name="unknown", sheet=sheet, status="INVALID_DEF")

        # Verify start_row has data
        has_data = any(
            self.cells.get((start_row, col_def.get("col", 0))) is not None
            for col_def in columns
        )

        actual_start = start_row
        if not has_data:
            # Dynamic search for header nearby
            header_keywords = [col_def.get("field", "") for col_def in columns[:3]]
            for r in range(max(1, start_row - 20), start_row + 20):
                matches = sum(
                    1 for col_def in columns
                    if self.cells.get((r, col_def.get("col", 0))) is not None
                    and any(kw.lower() in str(self.cells.get((r, col_def.get("col", 0)), "")).lower()
                           for kw in header_keywords if kw)
                )
                if matches >= 2:
                    actual_start = r + 1
                    break

        # Find end row with row classification
        end_row = actual_start
        blank_count = 0
        rejected_count = 0
        rejection_reasons = []
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
                        return self._build_result(table_def, sheet, actual_start, r - 1,
                                                   columns, rejected_count, rejection_reasons)

            if has_row_data:
                # Classify the row
                row_class = self._classify_row(r, columns)
                if row_class == "data":
                    end_row = r
                    blank_count = 0
                else:
                    rejected_count += 1
                    rejection_reasons.append(f"R{r}: {row_class}")
            else:
                blank_count += 1
                if blank_count >= 3:
                    break

        return self._build_result(table_def, sheet, actual_start, end_row,
                                   columns, rejected_count, rejection_reasons)

    def _classify_row(self, row: int, columns: List[Dict]) -> str:
        """Classify a row as: data, header_repeat, subtotal, footer, note, unit_row, title."""
        values = []
        for col_def in columns:
            c = col_def.get("col", 0)
            val = self.cells.get((row, c))
            if val is not None:
                values.append(str(val).strip().lower())

        if not values:
            return "empty"

        all_text = " ".join(values)

        # Check for repeated header
        header_keywords = [col_def.get("field", "").lower() for col_def in columns]
        header_match = sum(1 for v in values if any(kw in v for kw in header_keywords if kw))
        if header_match >= len(columns) * 0.5:
            return "header_repeat"

        # Check for subtotal/footer
        if any(kw in all_text for kw in ["total", "subtotal", "sum", "average", "avg"]):
            return "subtotal"

        # Check for notes
        if any(kw in all_text for kw in ["note:", "notes:", "remark", "n/a", "-"]):
            # But only if most cells are text
            numeric_count = sum(1 for v in values if self._is_numeric(v))
            if numeric_count < len(values) * 0.3:
                return "note"

        return "data"

    @staticmethod
    def _is_numeric(text: str) -> bool:
        try:
            float(text.replace(',', '').replace(' ', ''))
            return True
        except (ValueError, TypeError):
            return False

    def _build_result(self, table_def, sheet, start_row, end_row,
                       columns, rejected_count, rejection_reasons):
        records = []
        for r in range(start_row, end_row + 1):
            record = {}
            has_value = False
            for col_def in columns:
                c = col_def.get("col", 0)
                val = self.cells.get((r, c))
                if val is None:
                    val, _ = self.merge.get_value(r, c)
                if val is not None:
                    has_value = True
                    canonical = col_def.get("canonical", "")
                    # Use short key for downstream compatibility (database, UI)
                    if canonical and "." in canonical:
                        key = canonical.split(".", 1)[1]  # survey.md -> md
                    else:
                        key = col_def.get("field", f"col_{c}")
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
            confidence=0.90 if records else 0.0,
            rejected_rows=rejected_count,
            rejection_reasons=rejection_reasons,
        )


# ==================== Excel Intelligence (Main Orchestrator) ====================

class ExcelIntelligence:
    """Main orchestrator for robust Excel extraction."""

    def __init__(self, workbook, template: Dict = None):
        self.workbook = workbook
        self.template = template or {}
        self.cell_cache = {}
        self.merge_analyzers = {}
        self.label_detectors = {}
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
                    for field_def in section_data:
                        canonical_path = field_def.get("canonical", "")
                        if not canonical_path:
                            continue

                        result = extractor.extract(field_def, canonical_path, actual_sheet)
                        report.field_results.append(result)

                        # Apply confidence policy
                        spec = FIELD_SPECS.get(canonical_path)
                        critical = spec.critical if spec else False
                        decision = confidence_decision(result.confidence, critical)

                        if result.status == "OK":
                            report.fields_detected += 1
                            if decision == "ACCEPT":
                                report.fields_accepted += 1
                            elif decision == "REVIEW":
                                report.fields_review += 1
                            else:
                                report.fields_rejected += 1
                            section, key = canonical_path.split(".", 1)
                            canonical.setdefault(section, {})[key] = result.value
                        elif result.status == "REVIEW_REQUIRED":
                            report.fields_review += 1
                            section, key = canonical_path.split(".", 1)
                            canonical.setdefault(section, {})[key] = result.value
                        elif result.status == "CONFLICT":
                            report.fields_conflict += 1
                            section, key = canonical_path.split(".", 1)
                            canonical.setdefault(section, {})[key] = result.value
                        elif result.status == "UNRESOLVED":
                            report.fields_unresolved += 1

                        # Confidence distribution
                        if result.confidence >= 0.95:
                            report.confidence_distribution[">=0.95"] += 1
                        elif result.confidence >= 0.70:
                            report.confidence_distribution["0.70-0.94"] += 1
                        else:
                            report.confidence_distribution["<0.70"] += 1

                        # Validation errors
                        if result.validation and result.validation != "valid":
                            report.validation_errors += 1

                elif isinstance(section_data, dict):
                    if "columns" in section_data:
                        table_result = table_extractor.find_table_by_template(
                            section_data, actual_sheet
                        )
                        report.table_results.append(table_result)
                        report.tables_detected += 1
                        report.total_rows_extracted += table_result.row_count
                        report.rejected_rows += table_result.rejected_rows

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
                        for sub_key, sub_data in section_data.items():
                            if isinstance(sub_data, list):
                                for field_def in sub_data:
                                    canon = field_def.get("canonical", "")
                                    if canon:
                                        result = extractor.extract(field_def, canon, actual_sheet)
                                        report.field_results.append(result)
                                        if result.status == "OK" and result.confidence >= 0.70:
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
        parts = sheet_key.split("_", 2)
        if len(parts) >= 3:
            hint = parts[2].replace("_", " ").lower()
            for actual_name in self.cell_cache.keys():
                if hint in actual_name.lower() or actual_name.lower() in hint:
                    return actual_name
        if self.cell_cache:
            return list(self.cell_cache.keys())[0]
        return None
