"""Data Lineage — field-level provenance tracking for imported values.

Every imported value should be traceable back to its source:
    field → source_file → source_sheet → source_cell → original_label → 
    mapping_method → confidence → validation_status → imported_at

This is critical for professional engineering software where an engineer
may ask: "Where did this MW value come from?"
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Any, Dict, List
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class LineageRecord:
    """Complete provenance record for one imported field value."""
    
    # Target
    canonical_field: str          # e.g., "mud_report.mw"
    value: Any                    # The stored value (normalized)
    
    # Source
    source_file: str = ""         # e.g., "DDR_2026_08_20.xlsx"
    source_sheet: str = ""        # e.g., "Daily Report"
    source_cell: str = ""         # e.g., "H17"
    source_row: Optional[int] = None
    source_column: Optional[int] = None
    original_label: str = ""      # e.g., "Mud Wt."
    original_value: Any = None    # Value as found in source
    original_unit: str = ""       # e.g., "SG"
    
    # Normalization
    normalized_value: Any = None  # After unit conversion
    normalized_unit: str = ""     # e.g., "ppg"
    conversion_rule: str = ""     # e.g., "1.50 SG * 8.3454 = 12.52 ppg"
    
    # Mapping
    mapping_method: str = ""      # "deterministic", "ai", "manual"
    confidence: float = 0.0       # 0.0 to 1.0
    
    # Validation
    validation_status: str = ""   # "valid", "warning", "error", "review"
    validation_message: str = ""
    
    # Metadata
    imported_at: str = ""
    imported_by: str = ""
    report_id: Optional[int] = None
    well_id: Optional[int] = None
    
    def as_dict(self) -> dict:
        return asdict(self)
    
    def summary(self) -> str:
        """Human-readable summary for UI display."""
        parts = [f"Field: {self.canonical_field}"]
        if self.value is not None:
            parts.append(f"Value: {self.value}")
        if self.normalized_unit:
            parts.append(f"Unit: {self.normalized_unit}")
        if self.source_file:
            parts.append(f"Source: {self.source_file}")
        if self.source_sheet:
            parts.append(f"Sheet: {self.source_sheet}")
        if self.source_cell:
            parts.append(f"Cell: {self.source_cell}")
        if self.original_label:
            parts.append(f"Label: {self.original_label}")
        if self.mapping_method:
            parts.append(f"Method: {self.mapping_method}")
        if self.confidence > 0:
            parts.append(f"Confidence: {self.confidence:.0%}")
        return " | ".join(parts)


class LineageTracker:
    """Collects and manages lineage records during an import session."""
    
    def __init__(self):
        self._records: List[LineageRecord] = []
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    
    def track(self, record: LineageRecord):
        """Add a lineage record."""
        if not record.imported_at:
            record.imported_at = datetime.now(timezone.utc).isoformat()
        self._records.append(record)
    
    def track_value(self, canonical_field: str, value: Any, *,
                    source_file: str = "", source_sheet: str = "",
                    source_cell: str = "", source_row: int = None,
                    source_column: int = None, original_label: str = "",
                    original_value: Any = None, original_unit: str = "",
                    normalized_value: Any = None, normalized_unit: str = "",
                    conversion_rule: str = "", mapping_method: str = "",
                    confidence: float = 0.0, validation_status: str = "",
                    validation_message: str = "", report_id: int = None,
                    well_id: int = None, imported_by: str = ""):
        """Convenience method to track a value with keyword arguments."""
        self.track(LineageRecord(
            canonical_field=canonical_field,
            value=value,
            source_file=source_file,
            source_sheet=source_sheet,
            source_cell=source_cell,
            source_row=source_row,
            source_column=source_column,
            original_label=original_label,
            original_value=original_value,
            original_unit=original_unit,
            normalized_value=normalized_value,
            normalized_unit=normalized_unit,
            conversion_rule=conversion_rule,
            mapping_method=mapping_method,
            confidence=confidence,
            validation_status=validation_status,
            validation_message=validation_message,
            report_id=report_id,
            well_id=well_id,
            imported_by=imported_by,
        ))
    
    @property
    def records(self) -> List[LineageRecord]:
        return list(self._records)
    
    @property
    def count(self) -> int:
        return len(self._records)
    
    def get_by_field(self, canonical_field: str) -> List[LineageRecord]:
        """Get all lineage records for a specific canonical field."""
        return [r for r in self._records if r.canonical_field == canonical_field]
    
    def get_by_source(self, source_file: str, source_sheet: str = "") -> List[LineageRecord]:
        """Get all lineage records from a specific source."""
        results = [r for r in self._records if r.source_file == source_file]
        if source_sheet:
            results = [r for r in results if r.source_sheet == source_sheet]
        return results
    
    def get_low_confidence(self, threshold: float = 0.7) -> List[LineageRecord]:
        """Get records with confidence below threshold (need review)."""
        return [r for r in self._records if 0 < r.confidence < threshold]
    
    def get_errors(self) -> List[LineageRecord]:
        """Get records with validation errors."""
        return [r for r in self._records if r.validation_status == "error"]
    
    def get_warnings(self) -> List[LineageRecord]:
        """Get records with validation warnings."""
        return [r for r in self._records if r.validation_status == "warning"]
    
    def to_json(self) -> str:
        """Export all records as JSON."""
        return json.dumps([r.as_dict() for r in self._records], 
                         default=str, ensure_ascii=False, indent=2)
    
    def summary_table(self) -> List[dict]:
        """Return a summary suitable for display in the import review UI."""
        return [
            {
                "field": r.canonical_field,
                "value": r.value,
                "unit": r.normalized_unit,
                "source": f"{r.source_sheet}!{r.source_cell}" if r.source_sheet else r.source_file,
                "label": r.original_label,
                "method": r.mapping_method,
                "confidence": f"{r.confidence:.0%}" if r.confidence > 0 else "",
                "status": r.validation_status or "ok",
            }
            for r in self._records
        ]
    
    def clear(self):
        """Clear all records (for new import session)."""
        self._records.clear()
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


# Global tracker instance for the current import session
_import_lineage = LineageTracker()


def get_import_lineage() -> LineageTracker:
    """Get the global import lineage tracker."""
    return _import_lineage


def reset_import_lineage():
    """Reset the global tracker for a new import session."""
    _import_lineage.clear()
