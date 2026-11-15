"""M206 / M221 / M224: truthful provenance of every value a tubular / casing input can carry.

Field-level origins (M221) - one of :data:`FIELD_ORIGINS`, never inferred:

* ``MANUFACTURER`` / ``USER`` / ``DERIVED`` - the ``origin`` a PUBLISHED tubular library item declares for itself
  (``core.engineering.tubular_reference``), only while the bound value is unchanged;
* ``DERIVED`` - computed here from other values (the caller lists which, e.g. wall from OD and ID);
* ``LEGACY_PRESET_UNVERIFIED`` - a value copied from one of the built-in preset tables listed in :data:`INVENTORY`,
  only while it is unchanged. Nobody has verified where those numbers came from; they are NEVER manufacturer data;
* ``USER`` - typed (or edited) by the operator;
* ``UNKNOWN`` - no value (None). A rating is never inferred from a grade and a missing value is never 0.

The registry is versioned (:data:`REGISTRY_VERSION`): a record stored with a case keeps the version it was made
with, so changing a table later never rewrites history (M224). No preset value or formula is changed by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

REGISTRY_VERSION = "legacy-preset-provenance-v1"

MANUFACTURER, USER, DERIVED, LEGACY_PRESET, UNKNOWN = (
    "MANUFACTURER", "USER", "DERIVED", "LEGACY_PRESET_UNVERIFIED", "UNKNOWN")
FIELD_ORIGINS = (MANUFACTURER, USER, DERIVED, LEGACY_PRESET, UNKNOWN)

#: What the operator sees next to a preset value, verbatim.
PRESET_LABEL = "LEGACY_PRESET — SOURCE UNVERIFIED"
#: What the operator sees for a hard-coded default whose origin nobody knows.
UNKNOWN_DEFAULT_LABEL = "LEGACY — SOURCE UNKNOWN"
_SUFFIX = f"  [{PRESET_LABEL}]"


@dataclass(frozen=True)
class PresetTable:
    """One built-in table or default found in the product (M206 inventory)."""
    table_id: str
    location: str
    content: str
    label: str
    replaceable_by: str
    note: str = ""


INVENTORY: Tuple[PresetTable, ...] = (
    PresetTable("pipe_db", "dialogs/engineering_dialogs.py AddPipeDialog.PIPE_DB",
                "drill pipe / HWDP / drill collar OD, ID, weight, grade, connection",
                PRESET_LABEL, "📚 Library… (published tubular reference item)"),
    PresetTable("casing_db", "dialogs/engineering_dialogs.py AddCasingDialog.CASING_DB",
                "casing OD, ID, weight, grade and burst / collapse figures",
                PRESET_LABEL, "📚 Library… in W3b / W13 Casing Strength",
                "the burst / collapse figures are shown as 'preset ref' only and never enter the strength engine"),
    PresetTable("w3b_casing_templates", "tabs/w3b_wellbore_schematic_tab.py _create_casing_tab add_types",
                "conductor / surface / intermediate / production / liner OD and ID templates",
                PRESET_LABEL, "📚 Library… on the selected casing row"),
    PresetTable("w13_casing_strength_preset", "tabs/w13_Engineering_Calculator.py _csg_select_from_db",
                "W13 Casing Strength inputs filled through AddCasingDialog.CASING_DB",
                PRESET_LABEL, "📚 Library… / From architecture"),
    PresetTable("pipe_joint_lengths", "dialogs/engineering_dialogs.py AddPipeDialog._joints_to_length",
                "average joint lengths 9.14 m (pipe), 1.5 m (stabilizer), 0.6 m (sub) used by the joints helper",
                UNKNOWN_DEFAULT_LABEL, "type the measured length"),
    PresetTable("hydraulics_pipe_weight_default", "core/hydraulics_engine.py dataclass weight_ppf = 0.0",
                "pipe weight placeholder 0.0 lb/ft of the hydraulics pipe dataclass (weight is not used by the "
                "hydraulics formulas)", UNKNOWN_DEFAULT_LABEL, "not an input; kept for compatibility"),
)
TABLES = {t.table_id: t for t in INVENTORY}


def display_name(name: str) -> str:
    """The combo text of a preset entry: the operator sees that it is unverified before choosing it."""
    return f"{name}{_SUFFIX}"


def entry_name(text: str) -> str:
    """The table key behind :func:`display_name` (a plain name is returned unchanged)."""
    return text[:-len(_SUFFIX)] if text.endswith(_SUFFIX) else text


def preset_record(table_id: str, entry: str, values: Mapping[str, Any],
                  table_values: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """What a case / component stores about a preset it was filled from.

    ``values`` are the values as they landed in the inputs (a spin box may round them); ``table_values`` the table
    entry itself when it differs, so the rounding is visible rather than hidden.
    """
    if table_id not in TABLES:
        raise KeyError(f"unknown preset table {table_id!r}")
    out = {"origin": LEGACY_PRESET, "label": TABLES[table_id].label, "table": table_id, "entry": entry,
           "registry": REGISTRY_VERSION, "values": {k: v for k, v in values.items() if v is not None}}
    if table_values is not None:
        raw = {k: v for k, v in table_values.items() if v is not None}
        if any(not _same(raw.get(k), v) for k, v in out["values"].items() if k in raw):
            out["table_values"] = raw
    return out


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= 1e-9
    return (str(a).strip() if a is not None else None) == (str(b).strip() if b is not None else None)


def preset_holds(record: Optional[Mapping[str, Any]], values: Mapping[str, Any]) -> bool:
    """True while every value copied from the preset is still the current value (an edit detaches it)."""
    if not isinstance(record, Mapping) or record.get("origin") != LEGACY_PRESET:
        return False
    copied = record.get("values") or {}
    return bool(copied) and all(k in values and _same(values[k], v) for k, v in copied.items())


def field_origins(values: Mapping[str, Any], *, binding: Optional[Mapping[str, Any]] = None,
                  preset: Optional[Mapping[str, Any]] = None, derived: Iterable[str] = (),
                  preset_keys: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """The origin of each field of ``values`` (see the module docstring).

    ``binding`` is a ``tubular-binding-v1`` binding (``reference_binding.make_binding``); ``preset`` a
    :func:`preset_record`; ``preset_keys`` maps a field of ``values`` to its key in the preset record when they
    differ (e.g. ``weight_ppf`` -> ``wt``).
    """
    from core.engineering import reference_binding as rb

    derived = set(derived)
    bound: Dict[str, str] = {}
    if binding and rb.binding_holds(binding, values):
        spec = (binding.get("snapshot") or {}).get("spec") or {}
        declared = str(((spec.get("provenance") or {}).get("origin")) or "").upper()
        library_origin = declared if declared in (MANUFACTURER, USER, DERIVED) else UNKNOWN
        bound = {key: library_origin for key in (binding.get("fields") or {})}
    copied = (preset or {}).get("values") or {}
    mapping = dict(preset_keys or {})
    out: Dict[str, str] = {}
    for key, value in values.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            out[key] = UNKNOWN
        elif key in bound:
            out[key] = bound[key]
        elif key in derived:
            out[key] = DERIVED
        elif preset and mapping.get(key, key) in copied and _same(copied[mapping.get(key, key)], value):
            out[key] = LEGACY_PRESET
        else:
            out[key] = USER
    return out


def describe(origin: str) -> str:
    """Operator-facing wording of a field origin."""
    return {MANUFACTURER: "manufacturer document (library)", USER: "user-entered", DERIVED: "derived",
            LEGACY_PRESET: PRESET_LABEL, UNKNOWN: "unknown (not recorded)"}.get(origin, UNKNOWN)
