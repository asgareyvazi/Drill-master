"""Shared canonical mapping and normalization for document imports.

Extractors are allowed to be source-specific, but the field registry, value
normalization, contextual label resolution, and review representation are not.
This module deliberately contains no database or UI code.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Optional

from core.canonical_schema import FIELD_SPECS, lookup_alias, mapping_certainty
from core.import_quality import ReviewItem
from core.import_ir import SourceLocation
from core.value_normalizer import normalize_for_field


@dataclass(frozen=True)
class CanonicalValue:
    field: str
    original_value: Any
    normalized_value: Any
    expected_type: str = ""
    unit: str = ""
    validation_state: str = "valid"
    review_reason: str = ""

    @property
    def needs_review(self) -> bool:
        return self.validation_state not in {"valid", "missing"}

    # Compatibility view for source adapters that historically consumed the
    # ValueNormalization result directly.
    @property
    def ok(self) -> bool:
        return self.validation_state in {"valid", "missing"}

    @property
    def missing(self) -> bool:
        return self.validation_state == "missing"

    @property
    def value(self) -> Any:
        return self.normalized_value

    @property
    def error(self) -> str:
        return self.review_reason


def normalize_canonical_value(value: Any, field_path: str) -> CanonicalValue:
    """Normalize one value using the authoritative shared field registry."""
    spec = FIELD_SPECS.get(field_path)
    if spec is None:
        return CanonicalValue(field_path, value, value)
    result = normalize_for_field(value, spec)
    if result.missing:
        state = "missing"
    elif result.ok:
        state = "valid"
    else:
        state = "needs_review"
    reason = "" if result.ok or result.missing else (result.error or "Invalid source value")
    return CanonicalValue(
        field=field_path,
        original_value=value,
        normalized_value=result.value if result.ok else None,
        expected_type=result.expected_type,
        unit=spec.unit,
        validation_state=state,
        review_reason=reason,
    )


_SECTION_ALIASES = {
    "well_info": ("well info", "well information", "well header"),
    "daily_report": ("daily report", "daily reporting", "ddr", "report header"),
    "time_log": ("time log", "24h log", "24 hour log", "24-hour log", "time breakdown"),
    "time_log_morning": ("time log morning", "time logs morning", "morning log", "morning time log", "morning time logs", "morning activities"),
}


def _context_text(context: Any = "", *, section: Any = "", headings: Iterable[str] = ()) -> str:
    parts = [str(context or ""), str(section or "")]
    parts.extend(str(item or "") for item in headings)
    return " ".join(" ".join(parts).lower().split())


def resolve_canonical_field(label: str, context: Any = "", *, section: Any = "", headings: Iterable[str] = ()) -> Optional[str]:
    """Resolve an alias without guessing when the canonical field is ambiguous."""
    normalized = " ".join(str(label or "").strip().lower().split())
    if not normalized:
        return None
    context_text = _context_text(context, section=section, headings=headings)
    exact = [path for path in FIELD_SPECS if path.lower() == normalized]
    if len(exact) == 1:
        return exact[0]

    candidates = [
        path for path, spec in FIELD_SPECS.items()
        if normalized in {" ".join(alias.lower().split()) for alias in spec.aliases}
    ]
    # Hrs/hours is intentionally resolved only from the surrounding section.
    if normalized in {"hrs", "hours"} and any(
        phrase in context_text for phrase in _SECTION_ALIASES["time_log_morning"]
    ):
        if "time_log_morning.duration" not in candidates:
            candidates.append("time_log_morning.duration")

    if len(candidates) == 1:
        return candidates[0]

    for section_name, aliases in sorted(
        _SECTION_ALIASES.items(),
        key=lambda item: max((len(alias) for alias in item[1]), default=0),
        reverse=True,
    ):
        if not any(re.search(rf"\b{re.escape(alias)}\b", context_text) for alias in aliases):
            continue
        scoped = [path for path in candidates if path.startswith(section_name + ".")]
        if len(scoped) == 1:
            return scoped[0]

    mapped = lookup_alias(label)
    return mapped if mapped in candidates and len(candidates) == 1 else None


def review_item(
    *,
    field: str = "",
    original_value: Any = None,
    normalized_value: Any = None,
    location: Optional[SourceLocation | dict] = None,
    reason: str = "Review required",
    status: str = "REVIEW_REQUIRED",
    confidence: Optional[float] = None,
    mapping_method: str = "shared-canonical-mapper",
    entity: str = "",
    detected_table: str = "",
    expected_type: str = "",
    unit: str = "",
    decision: str = "REVIEW",
    message: str = "",
) -> ReviewItem:
    """Create the one review object used by Excel, PDF, and persistence."""
    if isinstance(location, SourceLocation):
        source = location.to_dict()
    else:
        source = dict(location or {})
    source_file = source.get("file") or source.get("source_file", "")
    source_sheet = source.get("sheet") or source.get("source_sheet", "") or ""
    source_page = source.get("page", source.get("source_page"))
    source_row = source.get("row", source.get("source_row")) or 0
    source_column = source.get("column", source.get("source_column")) or ""
    source_cell = source.get("cell") or source.get("source_cell") or ""
    if not source_cell and source_row:
        source_cell = f"row {source_row}, column {source_column}".strip(", ")
    return ReviewItem(
        file=str(source_file or ""),
        sheet=str(source_sheet),
        page=source_page,
        row=source_row,
        column=source_column,
        source_cell=str(source_cell),
        source_location=source,
        source_document=str(source_file or ""),
        source_table=str(source.get("table") or source.get("source_table") or detected_table or ""),
        detected_table=detected_table or str(source.get("table") or source.get("source_table") or ""),
        section_title=str(source.get("section_title") or ""),
        coordinates=source.get("coordinates") or source.get("bounding_box"),
        extraction_method=str(source.get("extraction_method") or ""),
        original_value=original_value,
        normalized_value=normalized_value,
        target_field=field,
        canonical_field=field,
        expected_type=expected_type,
        unit=unit,
        normalized_unit=unit,
        confidence=confidence,
        certainty=mapping_certainty(confidence or 0, mapping_method),
        decision=decision,
        status=status,
        validation_state=status,
        mapping_method=mapping_method,
        reason=reason,
        validation_message=message or reason,
        entity=entity,
        field=field,
        review_state="unreviewed",
    )


__all__ = [
    "CanonicalValue",
    "normalize_canonical_value",
    "resolve_canonical_field",
    "review_item",
]
