"""M54: versioned, editable DDR report profiles.

A report profile describes how one operator's report format maps onto the
canonical schema: header aliases, source units, date formats, table rules,
multi-page continuation and the confidence threshold below which a mapped
value must be reviewed.

Contract
* Every save inserts a NEW immutable version (``profile_key``, ``version``);
  versions are never updated or deleted (data-layer policy: insert only).
* Aliases may only target existing canonical fields (``FIELD_SPECS``); units
  must be known source units. Validation errors block the save.
* A profile is mapping *context*: it never invents values. Profile hits are
  recorded with key and version so the review shows which rule mapped a column.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

PROFILE_SCHEMA_VERSION = "M54 report profile v1"
FORMATS = ("pdf", "xlsx", "any")
KNOWN_SOURCE_UNITS = (
    "m", "ft", "in", "mm", "psi", "bar", "kpa", "mpa", "ppg", "pcf", "sg", "kg/m3", "g/cm3", "lb/ft3",
    "deg", "rpm", "gpm", "lpm", "bbl", "m3", "hr", "klbf", "kn", "m/h", "ft/h", "c", "f", "%",
)
DEFAULT_DATE_FORMATS = ("%Y-%m-%d",)


def _norm_label(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().rstrip(":").split())


@dataclass(frozen=True)
class ReportProfile:
    key: str
    version: int
    name: str
    operator: str = ""
    report_format: str = "any"
    aliases: Dict[str, str] = field(default_factory=dict)       # source label -> canonical path
    units: Dict[str, str] = field(default_factory=dict)         # canonical path -> source unit
    date_formats: Tuple[str, ...] = DEFAULT_DATE_FORMATS
    table_rules: Dict[str, Any] = field(default_factory=dict)   # e.g. {"stop_markers": [...], "skip_rows_containing": [...]}
    continuation: bool = True
    confidence_threshold: float = 0.8
    note: str = ""

    # -- application ------------------------------------------------------
    def resolve(self, label: Any) -> Optional[str]:
        """Canonical path for a source label from this profile's aliases, else ``None``."""
        wanted = _norm_label(label)
        if not wanted:
            return None
        for source, target in self.aliases.items():
            if _norm_label(source) == wanted:
                return target
        return None

    def source_unit(self, field_path: str) -> Optional[str]:
        return self.units.get(field_path)

    def parse_date(self, text: Any) -> Optional[date]:
        """First matching profile date format, else ``None`` (never guessed)."""
        raw = str(text or "").strip()
        for fmt in self.date_formats:
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:  # silent-ok: try the next declared format; no match returns None (never guessed)
                continue
        return None

    def needs_review(self, confidence: Optional[float]) -> bool:
        return confidence is None or confidence < self.confidence_threshold

    def label(self) -> str:
        return f"{self.name} (v{self.version})"

    def payload(self) -> Dict[str, Any]:
        return {
            "schema": PROFILE_SCHEMA_VERSION,
            "aliases": dict(self.aliases),
            "units": dict(self.units),
            "date_formats": list(self.date_formats),
            "table_rules": dict(self.table_rules),
            "continuation": bool(self.continuation),
            "confidence_threshold": float(self.confidence_threshold),
        }


def profile_from_dict(data: Dict[str, Any], *, key: str = "", version: int = 0) -> ReportProfile:
    payload = data.get("payload", data)
    return ReportProfile(
        key=str(data.get("profile_key") or data.get("key") or key),
        version=int(data.get("version") or version),
        name=str(data.get("name") or ""),
        operator=str(data.get("operator") or ""),
        report_format=str(data.get("report_format") or "any"),
        aliases={str(k): str(v) for k, v in (payload.get("aliases") or {}).items()},
        units={str(k): str(v) for k, v in (payload.get("units") or {}).items()},
        date_formats=tuple(payload.get("date_formats") or DEFAULT_DATE_FORMATS),
        table_rules=dict(payload.get("table_rules") or {}),
        continuation=bool(payload.get("continuation", True)),
        confidence_threshold=float(payload.get("confidence_threshold", 0.8)),
        note=str(data.get("note") or ""),
    )


def validate_profile(profile: ReportProfile) -> List[str]:
    """Human-readable errors; an empty list means the profile may be saved."""
    from core.canonical_schema import FIELD_SPECS

    errors: List[str] = []
    if not profile.key.strip():
        errors.append("Profile key is required.")
    if not profile.name.strip():
        errors.append("Profile name is required.")
    if profile.report_format not in FORMATS:
        errors.append(f"Report format must be one of {', '.join(FORMATS)}.")
    seen: Dict[str, str] = {}
    for source, target in profile.aliases.items():
        label = _norm_label(source)
        if not label:
            errors.append("An alias has an empty source label.")
            continue
        if target not in FIELD_SPECS:
            errors.append(f"Alias '{source}' targets unknown canonical field '{target}'.")
        if label in seen and seen[label] != target:
            errors.append(f"Alias '{source}' is mapped to two different fields.")
        seen[label] = target
    for target, unit in profile.units.items():
        if target not in FIELD_SPECS:
            errors.append(f"Unit rule targets unknown canonical field '{target}'.")
        if str(unit).strip().lower() not in KNOWN_SOURCE_UNITS:
            errors.append(f"Unit '{unit}' for '{target}' is not a known source unit.")
    for fmt in profile.date_formats:
        try:
            datetime(2026, 1, 15).strftime(fmt)
            if "%" not in fmt:
                raise ValueError
        except ValueError:
            errors.append(f"Date format '{fmt}' is not a valid strftime pattern.")
    if not 0.0 <= float(profile.confidence_threshold) <= 1.0:
        errors.append("Confidence threshold must be between 0 and 1.")
    for name in ("stop_markers", "skip_rows_containing", "skip_tables_containing"):
        value = profile.table_rules.get(name, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            errors.append(f"Table rule '{name}' must be a list of text values.")
    return errors


def map_headers(profile: Optional[ReportProfile], headers: List[str]) -> List[Dict[str, Any]]:
    """Preview how headers map: profile alias first, then the canonical alias index."""
    from core.canonical_mapper import resolve_canonical_field

    rows = []
    for header in headers:
        hit = profile.resolve(header) if profile is not None else None
        if hit:
            rows.append({"header": header, "field": hit, "method": f"profile {profile.key} v{profile.version}",
                         "unit": profile.source_unit(hit) or ""})
            continue
        canonical = resolve_canonical_field(header)
        rows.append({"header": header, "field": canonical or "",
                     "method": "canonical alias" if canonical else "unmapped — review",
                     "unit": (profile.source_unit(canonical) if profile and canonical else "") or ""})
    return rows


# ---------------------------------------------------------------------------
# Persistence (immutable versions)
# ---------------------------------------------------------------------------
def save_profile_version(db, profile: ReportProfile, *, user_id: Optional[int] = None, note: str = "") -> ReportProfile:
    """Insert ``profile`` as the next version of its key; returns the stored version.

    Raises ``ValueError`` with all validation errors; nothing is written then.
    """
    from core.database import DDRReportProfile

    errors = validate_profile(profile)
    if errors:
        raise ValueError("; ".join(errors))
    with db.session_scope() as session:
        latest = (
            session.query(DDRReportProfile.version)
            .filter(DDRReportProfile.profile_key == profile.key)
            .order_by(DDRReportProfile.version.desc())
            .first()
        )
        version = (latest[0] if latest else 0) + 1
        row = DDRReportProfile(
            profile_key=profile.key, version=version, name=profile.name, operator=profile.operator,
            report_format=profile.report_format, payload=json.loads(json.dumps(profile.payload())),
            note=note or profile.note, created_by=user_id,
        )
        session.add(row)
    return get_profile(db, profile.key, version)


def _row_to_profile(row) -> ReportProfile:
    return profile_from_dict({
        "profile_key": row.profile_key, "version": row.version, "name": row.name, "operator": row.operator,
        "report_format": row.report_format, "payload": row.payload or {}, "note": row.note,
    })


def get_profile(db, key: str, version: Optional[int] = None) -> Optional[ReportProfile]:
    from core.database import DDRReportProfile

    with db.session_scope() as session:
        query = session.query(DDRReportProfile).filter(DDRReportProfile.profile_key == key)
        row = (query.filter(DDRReportProfile.version == version).first() if version is not None
               else query.order_by(DDRReportProfile.version.desc()).first())
        return _row_to_profile(row) if row is not None else None


def list_latest_profiles(db) -> List[ReportProfile]:
    from core.database import DDRReportProfile

    with db.session_scope() as session:
        rows = session.query(DDRReportProfile).order_by(DDRReportProfile.profile_key, DDRReportProfile.version).all()
        latest: Dict[str, Any] = {}
        for row in rows:
            latest[row.profile_key] = row
        return [_row_to_profile(r) for r in sorted(latest.values(), key=lambda r: r.name.lower())]


def profile_history(db, key: str) -> List[Dict[str, Any]]:
    from core.database import DDRReportProfile

    with db.session_scope() as session:
        rows = (session.query(DDRReportProfile).filter(DDRReportProfile.profile_key == key)
                .order_by(DDRReportProfile.version).all())
        return [{"version": r.version, "name": r.name, "created_at": r.created_at, "note": r.note or "",
                 "aliases": len((r.payload or {}).get("aliases") or {})} for r in rows]
