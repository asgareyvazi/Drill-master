"""M55: survey file import (CSV / TXT / XLSX) with explicit units and validation.

Contract
* Columns are detected from header aliases (MD / Inc / Azi); a file without a
  recognisable MD, inclination and azimuth header is refused, never guessed.
* The depth unit must be explicit: from the header (``MD (ft)``) or chosen by
  the user. A file whose unit is neither stated nor chosen is refused, so ft and
  m can never be mixed silently. Feet are converted with the exact 0.3048 m/ft.
* Stations are validated by the canonical ``core.survey_records.prepare_surveys``
  (finite numbers, non-negative unique MD, 0-180 deg inclination); azimuths are
  additionally checked to lie in [0, 360). Rejected rows are listed with their
  source row; nothing is persisted here.
* The azimuth reference (true / grid / magnetic) is recorded as stated by the
  user; it is never inferred or converted.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

IMPORT_VERSION = "M55 survey file import v1"
FT_TO_M = 0.3048
AZIMUTH_REFERENCES = ("true north", "grid north", "magnetic north", "not stated")

_ALIASES = {
    "md": ("md", "measured depth", "depth", "meas depth", "mdepth", "md depth"),
    "inc": ("inc", "incl", "inclination", "incl.", "inc."),
    "azi": ("azi", "az", "azimuth", "azim", "azi.", "azimuth (true)", "azimuth (grid)"),
}
_UNIT_IN_HEADER = re.compile(r"[\[(]\s*(m|ft|feet|meter|meters|metre|metres)\s*[\])]", re.IGNORECASE)


@dataclass
class SurveyImportResult:
    stations: List[Dict[str, Any]] = field(default_factory=list)     # md (m), inc, azi + source row
    issues: List[Dict[str, Any]] = field(default_factory=list)       # {row, field, reason}
    unit: Optional[str] = None                                        # source depth unit
    unit_source: str = ""                                             # "header" | "user"
    columns: Dict[str, str] = field(default_factory=dict)            # canonical -> source header
    sheet: Optional[str] = None
    azimuth_reference: str = "not stated"
    error: Optional[str] = None
    version: str = IMPORT_VERSION

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.stations)


def _norm(text: Any) -> str:
    base = _UNIT_IN_HEADER.sub("", str(text or ""))
    return " ".join(base.strip().lower().replace("_", " ").split())


def _header_unit(text: Any) -> Optional[str]:
    match = _UNIT_IN_HEADER.search(str(text or ""))
    if not match:
        return None
    return "ft" if match.group(1).lower() in ("ft", "feet") else "m"


def detect_columns(header: Sequence[Any]) -> Dict[str, int]:
    found: Dict[str, int] = {}
    for index, cell in enumerate(header):
        key = _norm(cell)
        for canonical, aliases in _ALIASES.items():
            if canonical not in found and key in aliases:
                found[canonical] = index
    return found


def _rows_from_text(text: str) -> List[List[str]]:
    """Split delimited or whitespace-aligned text; '#' lines are comments."""
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        return []
    for delimiter in (",", ";", "\t", "|"):
        if all(delimiter in line for line in lines[: min(5, len(lines))]):
            return [[c.strip() for c in row] for row in csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)]
    # Whitespace-aligned: two or more spaces separate cells (headers may contain one space).
    return [re.split(r"\s{2,}", line.strip()) if re.search(r"\s{2,}", line.strip()) else line.split()
            for line in lines]


def read_table(path: str | Path, sheet: Optional[str] = None) -> tuple[List[List[Any]], Optional[str], List[str]]:
    """Rows of the file, chosen sheet name, and all sheet names (XLSX)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            names = list(workbook.sheetnames)
            chosen = sheet if sheet in names else names[0]
            rows = [list(row) for row in workbook[chosen].iter_rows(values_only=True)]
        finally:
            workbook.close()
        return rows, chosen, names
    if suffix in (".csv", ".txt", ".dat", ".tsv"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return _rows_from_text(text), None, []
    raise ValueError(f"Unsupported survey file type '{suffix}'. Use CSV, TXT or XLSX.")


def import_survey_rows(rows: Sequence[Sequence[Any]], *, unit: Optional[str] = None,
                       azimuth_reference: str = "not stated", sheet: Optional[str] = None) -> SurveyImportResult:
    from core.survey_records import prepare_surveys

    result = SurveyImportResult(sheet=sheet, azimuth_reference=azimuth_reference
                                if azimuth_reference in AZIMUTH_REFERENCES else "not stated")
    header_index, columns = None, {}
    for index, row in enumerate(rows[:30]):
        found = detect_columns(row)
        if {"md", "inc", "azi"} <= set(found):
            header_index, columns = index, found
            break
    if header_index is None:
        result.error = "No header row with MD, inclination and azimuth columns was found."
        return result
    header = rows[header_index]
    result.columns = {k: str(header[v]) for k, v in columns.items()}
    header_unit = _header_unit(header[columns["md"]])
    if header_unit and unit and header_unit != unit:
        result.error = (f"The MD header states '{header_unit}' but '{unit}' was chosen; "
                        "resolve the conflict before importing.")
        return result
    result.unit = header_unit or unit
    result.unit_source = "header" if header_unit else ("user" if unit else "")
    if result.unit not in ("m", "ft"):
        result.error = "The depth unit is not stated in the file; choose metres or feet explicitly."
        return result
    factor = FT_TO_M if result.unit == "ft" else 1.0

    records = []
    for offset, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        cells = list(row) + [None] * (max(columns.values()) + 1 - len(row))
        if all(c in (None, "") for c in cells):
            continue
        records.append({"md": cells[columns["md"]], "inc": cells[columns["inc"]], "azi": cells[columns["azi"]],
                        "_source_location": {"row": offset, "sheet": sheet}})
    accepted, issues, _rejected = prepare_surveys(records)
    for issue in issues:
        row_no = issue.get("row")
        if row_no in (None, "") and isinstance(issue.get("source_location"), dict):
            row_no = issue["source_location"].get("row")
        result.issues.append({"row": row_no, "field": issue.get("field", ""), "reason": issue.get("reason")
                              or issue.get("review_reason") or issue.get("message", "")})
    for record in accepted:
        azi = record.get("azi")
        if azi is not None and not 0.0 <= float(azi) < 360.0:
            result.issues.append({"row": record["_source_location"]["row"], "field": "survey.azi",
                                  "reason": "Azimuth must be in [0, 360) degrees"})
            continue
        if record.get("inc") is None or azi is None:
            continue                       # retained by prepare_surveys with a NULL angle; not importable
        result.stations.append({"md": float(record["md"]) * factor, "inc": float(record["inc"]), "azi": float(azi),
                                "source_row": record["_source_location"]["row"],
                                "source_md": record["md"], "source_unit": result.unit})
    result.stations.sort(key=lambda s: s["md"])
    if not result.stations:
        result.error = "No valid survey stations were found."
    return result


def import_survey_file(path: str | Path, *, unit: Optional[str] = None, sheet: Optional[str] = None,
                       azimuth_reference: str = "not stated") -> SurveyImportResult:
    try:
        rows, chosen, _names = read_table(path, sheet)
    except (OSError, ValueError) as exc:
        return SurveyImportResult(error=str(exc))
    return import_survey_rows(rows, unit=unit, azimuth_reference=azimuth_reference, sheet=chosen)
