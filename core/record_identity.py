"""M365 (D87): content fingerprints that pin an archive mark or a lineage link to one exact source record.

Background. Archive marks (``calculation_archive_marks``) and lineage links (``calculation_source_links``) address
their source by table name and integer id. SQLite without AUTOINCREMENT reuses the highest deleted id, so a later
record can take the id of a deleted one. Before M365 the only identity evidence was ``created_at``:

* a mark applied only while the row kept the ``created_at`` snapshotted at marking time, and
* a clone was SOURCE_REPLACED when its source was created after the link.

Two holes remained (M292 register, D87 PARTIAL):

* **equal timestamps.** A replacement row with the same ``created_at`` (same clock tick, a restored copy, or an
  import that carries timestamps) was indistinguishable;
* **NULL timestamps.** Seven of the eleven history tables allow ``created_at`` NULL. Archiving such rows had to be
  refused, and clones of them were only IDENTITY_WEAK.

M365 snapshots a SHA-256 **content fingerprint** of the source row's identity columns with each new mark and link.
The fingerprint covers the frozen engineering content: method, version, input snapshot and stored results. It
excludes presentation or lifecycle columns that may legitimately change: labels, notes, ``updated_at``, the
author reference (SET NULL when a user is deleted) and nullable parent references. A mark or link with a
fingerprint applies only while the current row has the same fingerprint.

Residual, stated rather than hidden: a replacement row in the same table, with the same id and byte-identical
engineering content, is indistinguishable by construction. It is the same calculation, but not the same row.
Marks and links written before M365 carry no fingerprint and keep the timestamp rule (reported as
``TIMESTAMP_ONLY``).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any, Dict, Optional, Tuple

FINGERPRINT_VERSION = "D87fp1"

_ENGINE_SNAPSHOT = ("well_id", "method", "snapshot_schema_version", "input_snapshot_json", "result_json")
IDENTITY_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "torque_drag_calculations": _ENGINE_SNAPSHOT,
    "casing_calculations": _ENGINE_SNAPSHOT,
    "cement_calculations": _ENGINE_SNAPSHOT,
    "mse_calculations": _ENGINE_SNAPSHOT,
    "mud_volume_calculations": _ENGINE_SNAPSHOT,
    "well_control_kill_sheet_calculations": _ENGINE_SNAPSHOT,
    "trajectory_calculations": ("well_id", "method", "method_version", "calculation_date", "parameters_json",
                                "results_json"),
    "calculation_cases": ("well_id", "calculator", "method", "method_version", "inputs", "results"),
    "directional_plan_revisions": ("well_id", "plan_key", "revision", "method", "method_version", "inputs",
                                   "results"),
    "survey_revisions": ("well_id", "revision", "stations_sha256", "results_sha256", "method", "method_version"),
    "well_architecture_revisions": ("well_id", "revision", "components_sha256", "schema_version"),
}

# identity outcomes
MATCH, DIFFERENT, NOT_PINNED, NOT_SUPPORTED = "MATCH", "DIFFERENT", "NOT_PINNED", "NOT_SUPPORTED"
CONTENT_PINNED, TIMESTAMP_ONLY = "CONTENT_PINNED", "TIMESTAMP_ONLY"


def _canonical(value: Any) -> Any:
    if isinstance(value, (_dt.datetime, _dt.date)):
        if isinstance(value, _dt.datetime) and value.tzinfo is not None:
            value = value.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return hashlib.sha256(bytes(value)).hexdigest()
    if isinstance(value, str):
        # JSON stored as text and JSON stored natively must give the same fingerprint
        stripped = value.strip()
        if stripped[:1] in ("{", "["):
            try:
                return _canonical(json.loads(stripped))
            except ValueError:            # silent-ok: plain text that only looks like JSON is fingerprinted as text
                return value
        return value
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def supported(table: str) -> bool:
    return table in IDENTITY_COLUMNS


def fingerprint(table: str, row: Any) -> Optional[str]:
    """``"D87fp1:<sha256>"`` of the identity columns of ``row``; None for a table without an identity contract."""
    columns = IDENTITY_COLUMNS.get(table)
    if columns is None or row is None:
        return None
    payload = {"table": table, "version": FINGERPRINT_VERSION,
               "columns": {name: _canonical(getattr(row, name, None)) for name in columns}}
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=True)
    return f"{FINGERPRINT_VERSION}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def compare(table: str, stored: Optional[str], row: Any) -> str:
    """MATCH / DIFFERENT for a pinned mark or link; NOT_PINNED for a pre-M365 record; NOT_SUPPORTED otherwise."""
    if not stored:
        return NOT_PINNED
    if not supported(table) or not str(stored).startswith(f"{FINGERPRINT_VERSION}:"):
        return NOT_SUPPORTED
    return MATCH if fingerprint(table, row) == stored else DIFFERENT
