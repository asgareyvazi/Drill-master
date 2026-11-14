"""M182: controlled import of tubular reference rows from an XLSX, CSV or JSON file into a DRAFT library set.

Contract ``tubular-import-v1``. The importer never decides what a value means:

* **Canonical headers only.** A column maps to a :class:`~core.engineering.tubular_reference.TubularSpec`
  field by its exact field name (``nominal_od_in``) or its label with the canonical unit
  (``Nominal OD (in)``). A recognised label without a unit, or with another unit (``Nominal OD (mm)``),
  blocks the file: nothing is converted or guessed. Other columns are listed as ignored, never read.
* **Missing stays missing.** A blank cell is ``None`` (shown as unavailable), never 0. A cell that is not a plain
  finite number, a boolean, or an Excel formula (a computed - derived - value) makes its row INVALID.
* **Provenance is the operator's statement about the file**, entered once (origin, manufacturer, document,
  URL, revision, licence); every row also carries the file SHA-256 and its source row / page. Only
  ``manufacturer`` (licence required) and ``user`` origins can be imported - a derived row needs its own
  derivation. Files that cite standards tables (API 5DP / 5CT / RP 7G / TR 5C3, ISO 11960 / 11961 / 10400)
  are refused: those tables are owner-gated and are not redistributable data.
* **Preview first, then an explicit confirmation.** :func:`preview_file` classifies each row as NEW,
  ALREADY_PRESENT (identical item already in the set), DUPLICATE_IN_FILE (identical earlier row), CONFLICT
  (same identity - type, designation, grade, connection - with different values, in the file or in the set)
  or INVALID. :func:`apply_import` writes only NEW rows, in one transaction with a mandatory audit record,
  after checking that the file is byte-identical to the previewed one and that the set is still a DRAFT.
  INVALID or CONFLICT rows block the import unless the operator explicitly accepts a partial import.
* **The raw file is not stored** - only the values, the file name and its SHA-256.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.engineering import tubular_reference as tr

CONTRACT_VERSION = "tubular-import-v1"
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 5000
FORMATS = {".csv": "csv", ".xlsx": "xlsx", ".xlsm": "xlsx", ".json": "json"}
IMPORT_ORIGINS = ("manufacturer", "user")

NEW, ALREADY_PRESENT, DUPLICATE_IN_FILE, CONFLICT, INVALID = (
    "NEW", "ALREADY_PRESENT", "DUPLICATE_IN_FILE", "CONFLICT", "INVALID")
BLOCKING_ROW_STATES = (INVALID, CONFLICT)

TEXT_FIELDS = ("component_type", "designation", "grade", "connection", "page")
TEXT_HEADERS = {
    "component_type": ("component_type", "component type", "type"),
    "designation": ("designation",),
    "grade": ("grade",),
    "connection": ("connection",),
    "page": ("page", "source page"),
}
# Standards tables are owner-gated (M181): a file that cites one is refused, whatever licence is stated.
_SEP = r"[\s\-_.]*"
STANDARD_TABLE_PATTERNS = tuple(p.replace("~", _SEP) for p in (
    r"\bapi~(spec~)?5~dp\b", r"\bapi~(spec~)?5~ct\b", r"\bapi~(rp~)?7~g\b", r"\bapi~(tr~)?5~c~3\b",
    r"\biso~1196[01]\b", r"\biso~10400\b", r"\bapi~(spec~)?7~-?~2\b",
))


class TubularImportError(ValueError):
    """The import (not a single row) is refused; nothing was written."""


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _header_table() -> Tuple[Dict[str, str], Dict[str, str]]:
    """(accepted header -> field, bare label -> canonical unit) for the engineering fields."""
    accepted: Dict[str, str] = {}
    bare: Dict[str, str] = {}
    for name, (label, unit) in tr.ENGINEERING_FIELDS.items():
        accepted[_norm(name)] = name
        accepted[_norm(f"{label} ({unit})")] = name
        bare[_norm(label)] = name
    for name, headers in TEXT_HEADERS.items():
        for header in headers:
            accepted[_norm(header)] = name
    return accepted, bare


ACCEPTED_HEADERS, BARE_LABELS = _header_table()


@dataclass
class RowResult:
    row_number: int                  # 1-based row in the source (header = row 1 for CSV/XLSX; item index for JSON)
    status: str
    spec: Optional[tr.TubularSpec] = None
    issues: List[str] = field(default_factory=list)
    fingerprint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"row": self.row_number, "status": self.status, "issues": list(self.issues),
                "designation": self.spec.designation if self.spec else None, "fingerprint": self.fingerprint}


@dataclass
class ImportPreview:
    contract: str
    file_name: str
    file_path: str
    sha256: str
    file_format: str
    sheet: Optional[str]
    set_id: int
    set_label: str
    provenance: tr.Provenance
    columns: Dict[str, str]                     # source header -> field
    ignored_columns: List[str]
    blocking: List[str]
    rows: List[RowResult]

    def counts(self) -> Dict[str, int]:
        out = {state: 0 for state in (NEW, ALREADY_PRESENT, DUPLICATE_IN_FILE, CONFLICT, INVALID)}
        for row in self.rows:
            out[row.status] += 1
        return out

    @property
    def importable(self) -> bool:
        return not self.blocking and any(row.status == NEW for row in self.rows)

    def summary(self) -> str:
        if self.blocking:
            return "BLOCKED - nothing can be imported: " + "; ".join(self.blocking)
        c = self.counts()
        return (f"{self.file_name}: {c[NEW]} new, {c[ALREADY_PRESENT]} already in the set, "
                f"{c[DUPLICATE_IN_FILE]} duplicate(s) in the file, {c[CONFLICT]} conflict(s), {c[INVALID]} invalid")


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------------------------- readers

def _read_csv(path: str) -> Tuple[List[Any], List[Tuple[int, List[Any]]]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        lines = list(csv.reader(handle))
    numbered = [(i + 1, row) for i, row in enumerate(lines) if any(str(c).strip() for c in row)]
    if not numbered:
        return [], []
    return numbered[0][1], numbered[1:]


def _read_xlsx(path: str, sheet: Optional[str]) -> Tuple[List[Any], List[Tuple[int, List[Any]]], str]:
    from core.workbook_io import load_workbook_readonly_safe

    # data_only=False: a formula is seen as a formula (its cached result would be a derived value).
    workbook = load_workbook_readonly_safe(path, read_only=True, data_only=False)
    try:
        names = list(workbook.sheetnames)
        if sheet is None:
            if len(names) != 1:
                raise TubularImportError(f"The workbook has {len(names)} sheets ({', '.join(names)}); choose one")
            sheet = names[0]
        if sheet not in names:
            raise TubularImportError(f"Sheet {sheet!r} is not in the workbook ({', '.join(names)})")
        rows = [(i + 1, list(r)) for i, r in enumerate(workbook[sheet].iter_rows(values_only=True))]
    finally:
        workbook.close()
    rows = [(n, r) for n, r in rows if any(c is not None and str(c).strip() for c in r)]
    if not rows:
        return [], [], sheet
    return rows[0][1], rows[1:], sheet


def _read_json(path: str) -> Tuple[List[Any], List[Tuple[int, List[Any]]], List[str]]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    notes: List[str] = []
    if isinstance(data, Mapping):
        notes = [f"top-level key {k!r} ignored" for k in data if k != "items"]
        data = data.get("items")
    if not isinstance(data, list) or not all(isinstance(item, Mapping) for item in data):
        raise TubularImportError("A JSON file must be a list of objects or {\"items\": [objects]}")
    header: List[str] = []
    for item in data:
        for key in item:
            if key not in header:
                header.append(key)
    return header, [(i + 1, [item.get(k) for k in header]) for i, item in enumerate(data)], notes


# ------------------------------------------------------------------------------------------- mapping

def map_columns(header: Sequence[Any]) -> Tuple[Dict[int, str], Dict[str, str], List[str], List[str]]:
    """(column index -> field, header -> field, ignored headers, blocking problems)."""
    by_index: Dict[int, str] = {}
    shown: Dict[str, str] = {}
    ignored: List[str] = []
    blocking: List[str] = []
    for index, raw in enumerate(header):
        text = str(raw).strip() if raw is not None else ""
        if not text:
            continue
        key = _norm(text)
        name = ACCEPTED_HEADERS.get(key)
        if name is None:
            label = re.sub(r"\s*\(.*\)\s*$", "", key)
            if label in BARE_LABELS:
                unit = tr.ENGINEERING_FIELDS[BARE_LABELS[label]][1]
                blocking.append(f"column {text!r} must state the canonical unit as \"({unit})\"; values are never "
                                f"converted or assumed")
            else:
                ignored.append(text)
            continue
        if name in by_index.values():
            blocking.append(f"column {text!r} maps to {name}, which another column already provides")
            continue
        by_index[index] = name
        shown[text] = name
    for required in ("component_type", "designation"):
        if required not in by_index.values():
            blocking.append(f"no {required} column")
    return by_index, shown, ignored, blocking


def _component(value: Any) -> Optional[str]:
    text = _norm(value)
    for code, label in tr.COMPONENT_LABELS.items():
        if text in (code.casefold(), label.casefold()):
            return code
    return None


def _number(value: Any) -> Tuple[Optional[float], Optional[str]]:
    """(value, problem). Blank -> (None, None): unavailable, never 0."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if isinstance(value, bool):
        return None, "a boolean is not a number"
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("="):
            return None, "an Excel formula is a computed (derived) value; enter the documented value"
        try:
            number = float(text)
        except ValueError:
            return None, f"{text!r} is not a plain number"
    elif isinstance(value, (int, float)):
        number = float(value)
    else:
        return None, f"{type(value).__name__} is not a number"
    if not math.isfinite(number):
        return None, f"{value!r} is not finite"
    return number, None


def _text(value: Any) -> Tuple[Optional[str], Optional[str]]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "a boolean is not text"
    text = str(value).strip()
    if text.startswith("="):
        return None, "an Excel formula is a computed value"
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    return (text or None), None


def identity_key(spec: tr.TubularSpec) -> Tuple[str, str, str, str]:
    return (spec.component_type, _norm(spec.designation), _norm(spec.grade), _norm(spec.connection))


# Provenance fields that locate a row (not what it says): two rows that differ only here carry the same data.
LOCATION_FIELDS = ("page", "notes", "file_fingerprint", "entered_by", "units")


def content_fingerprint(spec: tr.TubularSpec) -> str:
    """SHA-256 of the values and the source statement, without the row location (duplicate detection)."""
    payload = spec.to_payload()
    payload["provenance"] = {k: v for k, v in payload["provenance"].items() if k not in LOCATION_FIELDS}
    return tr._sha(payload)


def _standard_citation(prov: tr.Provenance) -> Optional[str]:
    text = " ".join(str(v) for v in (prov.manufacturer, prov.document, prov.url, prov.revision, prov.notes) if v)
    for pattern in STANDARD_TABLE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def check_provenance(prov: tr.Provenance) -> List[str]:
    issues: List[str] = []
    if prov.origin not in IMPORT_ORIGINS:
        issues.append(f"origin {prov.origin!r} cannot be imported from a file (manufacturer or user); a derived "
                      f"value needs its own stated derivation")
    elif prov.origin == "manufacturer":
        for name in ("manufacturer", "document", "licence"):
            if tr._blank(getattr(prov, name)):
                issues.append(f"a manufacturer file needs provenance.{name}"
                              + (" (a public PDF is not a redistribution right)" if name == "licence" else ""))
    cited = _standard_citation(prov)
    if cited:
        issues.append(f"the provenance cites {cited!r}: standards tables are owner-gated and are not imported")
    return issues


# ------------------------------------------------------------------------------------------- preview

def _existing(db, set_id: int) -> Tuple[Dict[str, str], Dict[Tuple[str, str, str, str], str], str, str]:
    """(content fingerprints, identity -> item fingerprint, status, label) of the target set."""
    from core.database import TubularReferenceSet

    with db.session_scope() as session:
        ref = session.get(TubularReferenceSet, set_id)
        if ref is None:
            raise TubularImportError(f"Reference set {set_id} does not exist")
        fingerprints: Dict[str, str] = {}
        identities: Dict[Tuple[str, str, str, str], str] = {}
        for item in ref.items:
            spec = tr.TubularSpec.from_payload(json.loads(item.payload_json))
            fingerprints[content_fingerprint(spec)] = spec.designation
            identities[identity_key(spec)] = item.fingerprint
        return fingerprints, identities, ref.status, f"{ref.name} v{ref.version}"


def _classify(rows: List[RowResult], fingerprints, identities) -> None:
    seen_fp: Dict[str, int] = {}
    seen_id: Dict[Tuple[str, str, str, str], Tuple[int, str]] = {}
    for row in rows:
        if row.status == INVALID or row.spec is None:
            continue
        fp, key = content_fingerprint(row.spec), identity_key(row.spec)
        if fp in fingerprints:
            row.status = ALREADY_PRESENT
        elif key in identities:
            row.status = CONFLICT
            row.issues.append("the set already holds this type / designation / grade / connection with other "
                              "values; it is never overwritten (publish a revision instead)")
        elif fp in seen_fp:
            row.status = DUPLICATE_IN_FILE
            row.issues.append(f"identical to row {seen_fp[fp]}")
        elif key in seen_id:
            row.status = CONFLICT
            row.issues.append(f"same identity as row {seen_id[key][0]} with different values")
            first = next(r for r in rows if r.row_number == seen_id[key][0])
            if first.status == NEW:
                first.status = CONFLICT
                first.issues.append(f"same identity as row {row.row_number} with different values")
        else:
            row.status = NEW
            seen_fp[fp] = row.row_number
            seen_id[key] = (row.row_number, fp)


def preview_file(db, set_id: int, path: str, provenance: tr.Provenance, *,
                 sheet: Optional[str] = None) -> ImportPreview:
    """Read ``path`` and classify every row against the DRAFT set ``set_id``. Nothing is written."""
    source = Path(path)
    file_format = FORMATS.get(source.suffix.lower())
    if file_format is None:
        raise TubularImportError(f"{source.suffix or 'this file'} is not supported (XLSX, CSV or JSON)")
    size = os.path.getsize(source)
    if size > MAX_FILE_BYTES:
        raise TubularImportError(f"The file is {size} bytes; the limit is {MAX_FILE_BYTES}")
    sha = file_sha256(str(source))
    fingerprints, identities, status, label = _existing(db, set_id)
    blocking = check_provenance(provenance)
    if status != tr.DRAFT:
        blocking.append(f"{label} is {status} and immutable; create a revision (a new draft) first")
    notes: List[str] = []
    if file_format == "csv":
        header, body = _read_csv(str(source))
    elif file_format == "xlsx":
        header, body, sheet = _read_xlsx(str(source), sheet)
    else:
        header, body, notes = _read_json(str(source))
    if len(body) > MAX_ROWS:
        raise TubularImportError(f"The file has {len(body)} rows; the limit is {MAX_ROWS}")
    by_index, shown, ignored, problems = map_columns(header)
    blocking += problems
    if not body:
        blocking.append("the file has no data rows")
    row_prov = replace(provenance, file_fingerprint=sha,
                       units=provenance.units or "canonical: in, lb/ft, psi, klbf, ft-lbf (per column header)")
    rows: List[RowResult] = []
    for number, cells in body:
        values: Dict[str, Any] = {}
        issues: List[str] = []
        for index, name in by_index.items():
            cell = cells[index] if index < len(cells) else None
            if name in TEXT_FIELDS:
                value, problem = _text(cell)
            else:
                value, problem = _number(cell)
            if problem:
                issues.append(f"{name}: {problem}")
            values[name] = value
        code = _component(values.get("component_type"))
        if values.get("component_type") is not None and code is None:
            issues.append(f"component_type {values['component_type']!r} is not one of {', '.join(tr.COMPONENT_TYPES)}")
        page = values.pop("page", None)
        values["component_type"] = code or ""
        values.setdefault("designation", "")
        prov = replace(row_prov, page=page or row_prov.page,
                       notes="; ".join(x for x in (row_prov.notes, f"source row {number}") if x))
        spec = tr.TubularSpec(provenance=prov, **{k: v for k, v in values.items()
                                                  if k in tr.ENGINEERING_FIELDS or k in TEXT_FIELDS})
        if not issues:
            issues = tr.validate_spec(spec)
        if issues:
            rows.append(RowResult(number, INVALID, spec, issues))
        else:
            rows.append(RowResult(number, NEW, spec, [], spec.fingerprint()))
    _classify(rows, fingerprints, identities)
    return ImportPreview(CONTRACT_VERSION, source.name, str(source), sha, file_format, sheet, set_id, label,
                         provenance, shown, ignored + notes, blocking, rows)


# ---------------------------------------------------------------------------------------------- apply

def apply_import(db, preview: ImportPreview, *, confirmed: bool, reason: str,
                 accept_partial: bool = False) -> Dict[str, Any]:
    """Write the NEW rows of ``preview`` atomically with an audit record; refuse anything stale or unconfirmed."""
    from core.database import TubularReferenceSet

    if confirmed is not True:
        raise TubularImportError("The import was not confirmed; nothing was written")
    if tr._blank(reason):
        raise TubularImportError("A reason is required; nothing was written")
    if preview.blocking:
        raise TubularImportError("The preview is blocked: " + "; ".join(preview.blocking))
    counts = preview.counts()
    if not accept_partial and (counts[INVALID] or counts[CONFLICT]):
        raise TubularImportError(f"{counts[INVALID]} invalid and {counts[CONFLICT]} conflicting row(s): accept a "
                                 f"partial import explicitly or fix the file; nothing was written")
    new_rows = [row for row in preview.rows if row.status == NEW]
    if not new_rows:
        raise TubularImportError("No new rows to import; nothing was written")
    try:
        current = file_sha256(preview.file_path)
    except OSError as exc:
        raise TubularImportError(f"The file can no longer be read ({type(exc).__name__}); nothing was written") from exc
    if current != preview.sha256:
        raise TubularImportError("The file changed after the preview; preview it again. Nothing was written")
    with db.session_scope() as session:
        ref = session.get(TubularReferenceSet, preview.set_id)
        if ref is None or ref.status != tr.DRAFT:
            raise TubularImportError("The target set is no longer a draft; nothing was written")
        specs = [tr.TubularSpec.from_payload(json.loads(item.payload_json)) for item in ref.items]
        present = {content_fingerprint(spec) for spec in specs}
        identities = {identity_key(spec) for spec in specs}
        stale = [row.row_number for row in new_rows
                 if content_fingerprint(row.spec) in present or identity_key(row.spec) in identities]
        if stale:
            raise TubularImportError(f"The set changed after the preview (rows {stale[:10]}); preview it again. "
                                     f"Nothing was written")
        for row in new_rows:
            session.add(tr.item_row(ref.id, row.spec))
        session.flush()
        details = json.dumps({"contract": CONTRACT_VERSION, "file": preview.file_name, "sha256": preview.sha256,
                              "imported": len(new_rows), "skipped": {k: v for k, v in counts.items() if k != NEW and v},
                              "origin": preview.provenance.origin, "reason": reason.strip()},
                             sort_keys=True, ensure_ascii=False)
        db._add_mandatory_audit(session, "tubular_reference_import", "tubular_reference_set", ref.id,
                                f"{ref.name} v{ref.version}", details)
        return {"set_id": ref.id, "set": f"{ref.name} v{ref.version}", "imported": len(new_rows),
                "fingerprints": [row.fingerprint for row in new_rows], "sha256": preview.sha256,
                "skipped": {k: v for k, v in counts.items() if k != NEW}}
