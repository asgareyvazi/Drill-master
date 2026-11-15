"""M207: the versioned JSON document of a W3b wellbore schematic (``elements_json`` and the JSON export).

``drillmaster-schematic-v2`` stores, per casing string, every value with None for "not recorded" (M205: a missing
weight is ``null``, never 0.0), the tubular library binding (set name, version, set / item fingerprints and the
immutable snapshot), the built-in preset it was filled from (M206: ``LEGACY_PRESET — SOURCE UNVERIFIED``), the
origin of every field (M221) and a list of the missing values. The document names the well it belongs to.

Reading:

* a v2 document of ANOTHER well is refused (:class:`SchematicOwnershipError`) - nothing is imported silently into the
  wrong well; the caller may only override with an explicit operator confirmation, and the import is then recorded
  as foreign in the report (bindings are kept: they are global library citations, not well data);
* a legacy document (the pre-M207 format without ``schema``: od / id / top / bottom / cement) stays readable - its
  weight / grade are UNKNOWN (None / "") and its rows are labelled ``LEGACY — SOURCE UNKNOWN``;
* a binding whose snapshot no longer matches its fingerprint is dropped and reported, never trusted.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

SCHEMA = "drillmaster-schematic-v2"
_CASING_VALUES = ("od", "id", "weight_ppf", "top", "bottom")


class SchematicDocumentError(ValueError):
    """The document cannot be read."""


class SchematicOwnershipError(SchematicDocumentError):
    """The document belongs to another well."""


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _binding_summary(binding: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(binding, Mapping):
        return None
    snap = binding.get("snapshot") or {}
    return {"set_name": snap.get("set_name"), "set_version": snap.get("set_version"),
            "set_fingerprint": snap.get("set_fingerprint"), "item_fingerprint": snap.get("item_fingerprint"),
            "designation": (snap.get("spec") or {}).get("designation")}


def casing_values(casing) -> Dict[str, Any]:
    """The values of one ``CasingData`` under the names the architecture / binding contracts use."""
    return {"od_in": casing.od_inch, "id_in": casing.id_inch, "weight_ppf": casing.weight_ppf,
            "grade": casing.grade or None}


def casing_origins(casing) -> Dict[str, str]:
    """M221: field origin of one casing string (library / legacy preset / user / unknown)."""
    from core.engineering import value_provenance as vp

    return vp.field_origins(casing_values(casing), binding=casing.tubular_reference, preset=casing.legacy_preset,
                            preset_keys={"od_in": "od", "id_in": "id"})


def to_document(schematic, *, well_id: Optional[int], wellbore_id: Optional[int] = None) -> Dict[str, Any]:
    from core.engineering import reference_binding as rb
    from core.engineering import value_provenance as vp
    from core.wellbore_schematic_engine import completion_od_status

    casings: List[Dict[str, Any]] = []
    missing: List[str] = []
    for c in schematic.casings:
        values = casing_values(c)
        binding = c.tubular_reference if rb.binding_holds(c.tubular_reference, values) else None
        preset = c.legacy_preset if vp.preset_holds(c.legacy_preset, {"od": c.od_inch, "id": c.id_inch}) else None
        row = {"name": c.name, "type": c.element_type.value, "od": c.od_inch, "id": c.id_inch,
               "weight_ppf": c.weight_ppf, "grade": c.grade or None, "connection": c.connection or None,
               "top": c.top_depth_m, "bottom": c.bottom_depth_m, "cement_top": c.cement_top_m,
               "cement_bottom": c.cement_bottom_m, "show_cement": bool(c.show_cement),
               "value_source": c.value_source or None, "field_origins": casing_origins(c),
               "tubular_reference": binding, "library": _binding_summary(binding), "legacy_preset": preset}
        for key in ("od", "id", "weight_ppf", "grade", "connection"):
            if row[key] is None:
                missing.append(f"casing '{c.name}': {key}")
        casings.append(row)
    return {
        "schema": SCHEMA, "well_id": well_id, "wellbore_id": wellbore_id,
        "casings": casings,
        "formations": [{"name": f.name, "top": f.top_depth_m, "bottom": f.bottom_depth_m, "lithology": f.lithology,
                        "color": f.color} for f in schematic.formations],
        "completion": [{"type": i.element_type.value, "depth": i.depth_m, "label": i.label,
                        "od_inch": i.od_inch if completion_od_status(i.od_inch, i.od_source_status) == "RECORDED"
                        else None, "od_status": completion_od_status(i.od_inch, i.od_source_status),
                        "length": i.length_m} for i in schematic.completion],
        "config": {"total_depth": schematic.total_depth_m, "well_name": schematic.well_name,
                   "wellbore_name": schematic.wellbore_name, "show_tubing": schematic.show_tubing,
                   "show_xmas_tree": schematic.show_xmas_tree, "tubing_od_inch": schematic.tubing_od_inch,
                   "tubing_bottom_m": schematic.tubing_bottom_m},
        "missing": missing,
        "provenance": {"registry": vp.REGISTRY_VERSION, "binding_contract": rb.CONTRACT_VERSION},
    }


def dumps(schematic, *, well_id: Optional[int], wellbore_id: Optional[int] = None) -> str:
    return json.dumps(to_document(schematic, well_id=well_id, wellbore_id=wellbore_id), sort_keys=True,
                      allow_nan=False)


def loads(text_or_data: Any, *, expected_well_id: Optional[int], stored_well_id: Optional[int] = None,
          accept_foreign: bool = False) -> Tuple[Any, Dict[str, Any]]:
    """``(WellboreSchematic, report)`` from a stored or exported document.

    ``stored_well_id`` is the owner recorded OUTSIDE the document (the ``wellbore_schematics`` row) - the only owner
    a legacy document has. ``report``: schema, legacy, foreign, dropped bindings, missing values.
    """
    from core.engineering import tubular_reference as tr
    from core.wellbore_schematic_engine import (CasingData, CompletionItem, ElementType, FormationLayer,
                                                WellboreSchematic)
    from core.engineering import value_provenance as vp

    try:
        data = json.loads(text_or_data) if isinstance(text_or_data, (str, bytes)) else dict(text_or_data)
    except (TypeError, ValueError) as exc:
        raise SchematicDocumentError(f"Not a schematic document: {exc}") from exc
    if not isinstance(data, dict):
        raise SchematicDocumentError("Not a schematic document: a JSON object is required")
    schema = data.get("schema")
    if schema not in (None, SCHEMA):
        raise SchematicDocumentError(f"Unsupported schematic schema {schema!r} (this version reads {SCHEMA})")
    legacy = schema is None
    owner = data.get("well_id") if not legacy else stored_well_id
    if owner is None and stored_well_id is not None:
        owner = stored_well_id
    foreign = owner is not None and expected_well_id is not None and int(owner) != int(expected_well_id)
    if foreign and not accept_foreign:
        raise SchematicOwnershipError(f"This schematic belongs to well id {owner}, not to the selected well id "
                                      f"{expected_well_id}; nothing was imported.")
    if owner is None and not accept_foreign:
        raise SchematicOwnershipError("This schematic names no well; confirm the target well to import it.")

    report: Dict[str, Any] = {"schema": schema or "legacy (no schema)", "legacy": legacy, "owner_well_id": owner,
                              "foreign": bool(foreign or owner is None), "dropped_bindings": [], "missing": []}
    schematic = WellboreSchematic()
    config = data.get("config") or {}
    schematic.well_name = str(config.get("well_name") or "")
    schematic.wellbore_name = str(config.get("wellbore_name") or "")
    schematic.total_depth_m = _num(config.get("total_depth"))
    schematic.show_tubing = bool(config.get("show_tubing", True))
    schematic.show_xmas_tree = bool(config.get("show_xmas_tree", True))
    schematic.tubing_od_inch = _num(config.get("tubing_od_inch"))
    schematic.tubing_bottom_m = _num(config.get("tubing_bottom_m"))
    for row in data.get("casings") or []:
        values = {key: _num(row.get(key)) for key in _CASING_VALUES}
        if values["od"] is None or values["top"] is None or values["bottom"] is None:
            report["missing"].append(f"casing '{row.get('name')}': skipped - OD or depth missing")
            continue
        try:
            etype = ElementType(row.get("type"))
        except ValueError:
            etype = ElementType.CASING
        binding = row.get("tubular_reference") if not legacy else None
        if binding is not None and tr.verify_snapshot((binding or {}).get("snapshot") or {}):
            report["dropped_bindings"].append(str(row.get("name")))
            binding = None
        preset = row.get("legacy_preset") if not legacy else None
        casing = CasingData(name=str(row.get("name") or ""), element_type=etype, od_inch=values["od"],
                            id_inch=values["id"], top_depth_m=values["top"], bottom_depth_m=values["bottom"],
                            grade=str(row.get("grade") or ""), connection=str(row.get("connection") or ""),
                            weight_ppf=values["weight_ppf"] if not legacy else None,
                            cement_top_m=_num(row.get("cement_top")) or 0.0,
                            cement_bottom_m=_num(row.get("cement_bottom")) or 0.0,
                            show_cement=bool(row.get("show_cement", bool(_num(row.get("cement_bottom"))))),
                            tubular_reference=binding, legacy_preset=preset,
                            value_source=vp.UNKNOWN_DEFAULT_LABEL if legacy else str(row.get("value_source") or ""))
        for key in ("id", "weight_ppf"):
            if getattr(casing, {"id": "id_inch", "weight_ppf": "weight_ppf"}[key]) is None:
                report["missing"].append(f"casing '{casing.name}': {key}")
        schematic.casings.append(casing)
    for row in data.get("formations") or []:
        top, bottom = _num(row.get("top")), _num(row.get("bottom"))
        if top is None or bottom is None:
            continue
        schematic.formations.append(FormationLayer(name=str(row.get("name") or ""), top_depth_m=top,
                                                   bottom_depth_m=bottom, lithology=str(row.get("lithology") or ""),
                                                   color=str(row.get("color") or "#808080")))
    for row in data.get("completion") or []:
        depth = _num(row.get("depth"))
        try:
            etype = ElementType(row.get("type"))
        except ValueError:
            continue
        if depth is None:
            continue
        schematic.completion.append(CompletionItem(element_type=etype, depth_m=depth, od_inch=_num(row.get("od_inch")),
                                                   length_m=_num(row.get("length")) or 1.0,
                                                   label=str(row.get("label") or ""),
                                                   od_source_status="INVALID_SOURCE"
                                                   if row.get("od_status") == "INVALID" else ""))
    return schematic, report
