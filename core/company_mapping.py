"""Multi-company source → canonical mapping.

Architecture (do NOT add per-company application logic):

    Company-specific source
        → Template / Mapping (JSON)
        → Canonical activity / field
        → Database
        → Existing DrillMaster tabs

New companies are added by dropping a JSON template in
config/company_templates/ — core code does not change.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "config" / "company_templates"


@dataclass
class ActivityMappingRecord:
    original_code: str = ""
    original_description: str = ""
    canonical_code: str = ""
    canonical_description: str = ""
    source_company: str = ""
    source_sheet: str = ""
    source_cell: str = ""
    original_value: Any = None
    normalized_value: Any = None
    unit: str = ""
    mapping_confidence: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyTemplate:
    company: str
    version: str = "1"
    activity_map: Dict[str, Dict[str, str]] = field(default_factory=dict)
    field_map: Dict[str, str] = field(default_factory=dict)
    sheet_map: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompanyTemplate":
        return cls(
            company=data.get("company") or data.get("name") or "",
            version=str(data.get("version", "1")),
            activity_map=data.get("activity_map") or {},
            field_map=data.get("field_map") or {},
            sheet_map=data.get("sheet_map") or {},
        )


class CompanyMappingService:
    """Load templates and map source rows to canonical records."""

    def __init__(self, templates_dir: Optional[Path] = None):
        self.dir = Path(templates_dir or TEMPLATES_DIR)
        self._templates: Dict[str, CompanyTemplate] = {}
        self.reload()

    def reload(self) -> None:
        self._templates = {}
        if not self.dir.exists():
            return
        for path in self.dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tmpl = CompanyTemplate.from_dict(data)
                key = (tmpl.company or path.stem).strip().lower()
                self._templates[key] = tmpl
            except (OSError, ValueError):
                continue

    def list_companies(self) -> List[str]:
        return sorted(self._templates.keys())

    def get_template(self, company: str) -> Optional[CompanyTemplate]:
        if not company:
            return None
        return self._templates.get(company.strip().lower())

    def map_activity(
        self,
        *,
        original_code: str,
        original_description: str = "",
        source_company: str,
        source_sheet: str = "",
        source_cell: str = "",
        original_value: Any = None,
        normalized_value: Any = None,
        unit: str = "",
    ) -> ActivityMappingRecord:
        tmpl = self.get_template(source_company)
        rec = ActivityMappingRecord(
            original_code=original_code or "",
            original_description=original_description or "",
            source_company=source_company or "",
            source_sheet=source_sheet or "",
            source_cell=source_cell or "",
            original_value=original_value,
            normalized_value=normalized_value if normalized_value is not None else original_value,
            unit=unit or "",
        )
        if tmpl is None:
            rec.canonical_code = original_code or ""
            rec.canonical_description = original_description or ""
            rec.mapping_confidence = 0.0
            return rec

        key = (original_code or "").strip()
        entry = tmpl.activity_map.get(key) or tmpl.activity_map.get(key.upper()) or tmpl.activity_map.get(key.lower())
        if entry:
            rec.canonical_code = entry.get("canonical_code") or key
            rec.canonical_description = entry.get("canonical_description") or original_description
            rec.mapping_confidence = float(entry.get("confidence", 1.0))
        else:
            rec.canonical_code = key
            rec.canonical_description = original_description
            rec.mapping_confidence = 0.4  # passthrough, unknown code
        return rec

    def map_field(self, source_company: str, source_field: str) -> Optional[str]:
        tmpl = self.get_template(source_company)
        if not tmpl:
            return None
        return tmpl.field_map.get(source_field) or tmpl.field_map.get(source_field.lower())
