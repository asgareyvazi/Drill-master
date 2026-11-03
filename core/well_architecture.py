"""Immutable well architecture revisions (M74).

A revision freezes the well's architecture: sections, casing strings,
liners, tubing, shoes, formations, packers, cement (TOC) and accessories.
Values are canonical (MD in metres, sizes in inches); an unknown value is
``None`` and is never replaced by zero. Validation rules are listed in
``validate``; a revision with errors is refused. The schematic is generated
from the stored records through the existing ``wellbore_schematic_engine``,
and ``cement_annulus`` derives annular intervals for the cement worksheet
from the same records (WORKSHEET: nominal sizes unless an average caliper
is declared; excess only when declared, open hole only - M89).
``casing_inputs`` (M89) hands a string's geometry to the casing-strength
calculator with the origin of every value; material properties are never
inferred.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

ARCHITECTURE_VERSION = "M74 well architecture v1"
KINDS = ("section", "casing", "liner", "tubing", "shoe", "formation", "packer", "cement", "accessory")
STRINGS = ("casing", "liner", "tubing")
INTERVAL_KINDS = ("section", "casing", "liner", "tubing", "formation", "cement")
POINT_KINDS = ("shoe", "packer", "accessory")
NUMERIC = ("top_md", "bottom_md", "od_in", "id_in", "hole_in", "weight_ppf")
TEXT = ("kind", "name", "grade", "note")
DEPTH_TOLERANCE = 0.01   # m: a shoe "at" a string bottom
CEMENT_WORKSHEET_VERSION = "M89 cement annulus worksheet v1"
CEMENT_WORKSHEET_METHOD = "m89.cement_annulus"
CASING_SOURCE_VERSION = "M89 casing inputs from architecture v1"
MAX_EXCESS_PCT = 500.0


class ArchitectureError(ValueError):
    """A revision that cannot be stored (validation errors, wrong well, ...)."""


def _number(value: Any, label: str, errors: List[str]) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label}: {value!r} is not a number")
        return None
    if not math.isfinite(number):
        errors.append(f"{label}: must be finite")
        return None
    return number


def normalize(components: Iterable[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
    """Canonical component dicts plus parse errors (blank -> None, never 0)."""
    out, errors = [], []
    for index, raw in enumerate(components, start=1):
        item = {key: (str(raw.get(key) or "").strip()) for key in TEXT}
        item["kind"] = item["kind"].lower()
        label = f"#{index} {item['name'] or item['kind'] or '?'}"
        for key in NUMERIC:
            item[key] = _number(raw.get(key), f"{label} {key}", errors)
        out.append(item)
    return out, errors


def validate(components: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Errors block saving; warnings are stored with the revision.

    Rules: known kind and a name; interval kinds need top < bottom, point kinds
    a depth (top_md); depths >= 0; ID < OD; a string's OD below its hole size;
    a liner hangs inside a larger string; unique string names; a shoe sits at
    the bottom of the string it names; cement names a string and lies within
    it; formation intervals do not overlap; a packer lies within tubing. A
    rule whose inputs are unknown is not judged (listed as a warning).
    """
    items, errors = normalize(components)
    warnings: List[str] = []
    strings: Dict[str, Dict[str, Any]] = {}
    for item in items:
        label = f"{item['kind'] or '?'} '{item['name'] or '?'}'"
        if item["kind"] not in KINDS:
            errors.append(f"{label}: unknown kind (use one of {', '.join(KINDS)})")
            continue
        if not item["name"]:
            errors.append(f"{label}: a name is required")
        top, bottom = item["top_md"], item["bottom_md"]
        if item["kind"] in INTERVAL_KINDS:
            if top is None or bottom is None:
                errors.append(f"{label}: top and bottom MD are required")
            elif bottom <= top:
                errors.append(f"{label}: bottom MD must be below top MD")
        elif top is None:
            errors.append(f"{label}: a depth (top MD) is required")
        if any(v is not None and v < 0 for v in (top, bottom)):
            errors.append(f"{label}: depths must not be negative")
        od, inner, hole = item["od_in"], item["id_in"], item["hole_in"]
        if any(v is not None and v <= 0 for v in (od, inner, hole)):
            errors.append(f"{label}: sizes must be positive")
        if od is not None and inner is not None and inner >= od:
            errors.append(f"{label}: ID must be smaller than OD")
        if item["kind"] in STRINGS:
            if item["name"] in strings:
                errors.append(f"{label}: duplicate string name")
            strings[item["name"]] = item
            if od is None:
                warnings.append(f"{label}: OD unknown - clearance and nesting not checked")
            elif hole is not None and od >= hole:
                errors.append(f"{label}: OD {od:g} in does not fit the {hole:g} in hole")
            if item["kind"] == "casing" and top not in (None, 0.0):
                warnings.append(f"{label}: casing not run from surface - should it be a liner?")
    for item in items:
        label = f"{item['kind']} '{item['name']}'"
        if item["kind"] == "liner" and item["od_in"] is not None and item["top_md"] is not None:
            hosts = [s for s in strings.values() if s is not item and s["kind"] in ("casing", "liner")
                     and s["id_in"] is not None and s["top_md"] is not None and s["bottom_md"] is not None
                     and s["top_md"] <= item["top_md"] <= s["bottom_md"]]
            if not hosts:
                errors.append(f"{label}: liner top is not inside a casing or liner with a known ID")
            elif all(item["od_in"] >= h["id_in"] for h in hosts):
                errors.append(f"{label}: liner OD does not fit inside the host string ID")
        if item["kind"] in ("shoe", "cement"):
            host = strings.get(item["name"])
            if host is None:
                errors.append(f"{label}: names no casing/liner/tubing string in this architecture")
                continue
            if None in (host["top_md"], host["bottom_md"]):
                continue
            if item["kind"] == "shoe" and item["top_md"] is not None and \
                    abs(item["top_md"] - host["bottom_md"]) > DEPTH_TOLERANCE:
                errors.append(f"{label}: shoe depth {item['top_md']:g} m is not the string bottom "
                              f"{host['bottom_md']:g} m")
            if item["kind"] == "cement" and None not in (item["top_md"], item["bottom_md"]) and (
                    item["top_md"] < host["top_md"] - DEPTH_TOLERANCE
                    or item["bottom_md"] > host["bottom_md"] + DEPTH_TOLERANCE):
                errors.append(f"{label}: cement interval lies outside the string")
        if item["kind"] == "packer" and item["top_md"] is not None:
            tubing = [s for s in strings.values() if s["kind"] == "tubing"]
            if not tubing:
                warnings.append(f"{label}: no tubing string - packer setting depth not checked")
            elif not any(t["top_md"] is not None and t["bottom_md"] is not None
                         and t["top_md"] <= item["top_md"] <= t["bottom_md"] for t in tubing):
                errors.append(f"{label}: packer depth is outside every tubing string")
    formations = sorted((i for i in items if i["kind"] == "formation" and i["top_md"] is not None
                         and i["bottom_md"] is not None), key=lambda i: i["top_md"])
    for upper, lower in zip(formations, formations[1:]):
        if lower["top_md"] < upper["bottom_md"] - DEPTH_TOLERANCE:
            errors.append(f"formation '{lower['name']}' overlaps '{upper['name']}'")
    return {"errors": errors, "warnings": warnings}


def components_sha256(components: List[Dict[str, Any]]) -> str:
    blob = json.dumps(components, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _dto(row) -> Dict[str, Any]:
    return {"id": row.id, "well_id": row.well_id, "wellbore_id": row.wellbore_id,
            "survey_revision_id": row.survey_revision_id, "revision": row.revision, "parent_id": row.parent_id,
            "components": json.loads(row.components_json), "component_count": row.component_count,
            "components_sha256": row.components_sha256, "validation": json.loads(row.validation_json),
            "schema_version": row.schema_version, "note": row.note or "",
            "created_at": row.created_at.isoformat() if row.created_at else None, "created_by": row.created_by}


def save_revision(db, well_id: int, components: Iterable[Dict[str, Any]], *, wellbore_id: Optional[int] = None,
                  survey_revision_id: Optional[int] = None, parent_id: Optional[int] = None, note: str = "",
                  user_id: Optional[int] = None) -> Dict[str, Any]:
    """Validate and insert the next revision for ``well_id``; errors refuse the save."""
    from core.database import SurveyRevision, WellArchitectureRevision, Wellbore

    items, _parse = normalize(components)
    if not items:
        raise ArchitectureError("The architecture has no components.")
    result = validate(items)
    if result["errors"]:
        raise ArchitectureError("Not saved - fix: " + "; ".join(result["errors"]))
    with db.session_scope() as session:
        if wellbore_id is not None:
            bore = session.get(Wellbore, int(wellbore_id))
            if bore is None or bore.well_id != well_id:
                raise ArchitectureError("The wellbore does not belong to this well.")
        if survey_revision_id is not None:
            survey = session.get(SurveyRevision, int(survey_revision_id))
            if survey is None or survey.well_id != well_id:
                raise ArchitectureError("The survey revision does not belong to this well.")
        if parent_id is not None:
            parent = session.get(WellArchitectureRevision, int(parent_id))
            if parent is None or parent.well_id != well_id:
                raise ArchitectureError("The parent revision does not belong to this well.")
        number = (session.query(func.max(WellArchitectureRevision.revision))
                  .filter(WellArchitectureRevision.well_id == well_id).scalar() or 0) + 1
        row = WellArchitectureRevision(
            well_id=well_id, wellbore_id=wellbore_id, survey_revision_id=survey_revision_id, revision=number,
            parent_id=parent_id, components_json=json.dumps(items, sort_keys=True), component_count=len(items),
            components_sha256=components_sha256(items), validation_json=json.dumps(result),
            schema_version=ARCHITECTURE_VERSION, note=note or None, created_by=user_id)
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:      # a concurrent save took this number
            raise ArchitectureError("Another revision was saved at the same time; reload and save again.") from exc
        return _dto(row)


def list_revisions(db, well_id: int) -> List[Dict[str, Any]]:
    from core.database import WellArchitectureRevision

    with db.session_scope() as session:
        rows = (session.query(WellArchitectureRevision).filter(WellArchitectureRevision.well_id == well_id)
                .order_by(WellArchitectureRevision.revision.desc()).all())
        return [_dto(r) for r in rows]


def get_revision(db, revision_id: int) -> Dict[str, Any]:
    from core.database import WellArchitectureRevision

    with db.session_scope() as session:
        row = session.get(WellArchitectureRevision, int(revision_id))
        if row is None:
            raise LookupError(f"Architecture revision {revision_id} not found.")
        stored = _dto(row)
    if components_sha256(stored["components"]) != stored["components_sha256"]:
        raise ArchitectureError(f"Architecture revision {revision_id} fails its SHA-256 check.")
    return stored


# ---- schematic -------------------------------------------------------------------------------------
def from_schematic(schematic) -> List[Dict[str, Any]]:
    """Components from the W3b schematic tables (cement only where it is shown)."""
    from core.wellbore_schematic_engine import ElementType

    out: List[Dict[str, Any]] = []
    for casing in schematic.casings:
        kind = "liner" if casing.element_type == ElementType.LINER else "casing"
        out.append({"kind": kind, "name": casing.name, "top_md": casing.top_depth_m,
                    "bottom_md": casing.bottom_depth_m, "od_in": casing.od_inch, "id_in": casing.id_inch,
                    "grade": casing.grade, "weight_ppf": casing.weight_ppf or None})
        out.append({"kind": "shoe", "name": casing.name, "top_md": casing.bottom_depth_m})
        if casing.show_cement:
            out.append({"kind": "cement", "name": casing.name, "top_md": casing.cement_top_m,
                        "bottom_md": casing.cement_bottom_m or casing.bottom_depth_m})
    for layer in schematic.formations:
        out.append({"kind": "formation", "name": layer.name, "top_md": layer.top_depth_m,
                    "bottom_md": layer.bottom_depth_m, "note": layer.lithology})
    if schematic.tubing_od_inch is not None and schematic.tubing_bottom_m is not None:
        out.append({"kind": "tubing", "name": "Tubing", "top_md": 0.0, "bottom_md": schematic.tubing_bottom_m,
                    "od_in": schematic.tubing_od_inch})
    for item in schematic.completion:
        kind = "packer" if item.element_type == ElementType.PACKER else "accessory"
        out.append({"kind": kind, "name": item.label or item.element_type.value, "top_md": item.depth_m,
                    "od_in": item.od_inch, "note": item.element_type.value})
    return normalize(out)[0]


def to_schematic(components: Iterable[Dict[str, Any]], *, well_name: str = "", wellbore_name: str = ""):
    """A ``WellboreSchematic`` generated from stored records only (nothing invented)."""
    from core.wellbore_schematic_engine import (CasingData, CompletionItem, ElementType, FormationLayer,
                                                WellboreSchematic)

    items = normalize(components)[0]
    cement = {i["name"]: i for i in items if i["kind"] == "cement"}
    schematic = WellboreSchematic()
    schematic.well_name, schematic.wellbore_name = well_name, wellbore_name
    for item in items:
        if item["kind"] in ("casing", "liner") and item["od_in"] is not None:
            toc = cement.get(item["name"])
            schematic.casings.append(CasingData(
                name=item["name"], element_type=ElementType.LINER if item["kind"] == "liner" else ElementType.CASING,
                od_inch=item["od_in"], id_inch=item["id_in"], top_depth_m=item["top_md"],
                bottom_depth_m=item["bottom_md"], grade=item["grade"], weight_ppf=item["weight_ppf"] or 0.0,
                cement_top_m=toc["top_md"] if toc else 0.0, cement_bottom_m=toc["bottom_md"] if toc else 0.0,
                show_cement=toc is not None))
        elif item["kind"] == "formation":
            schematic.formations.append(FormationLayer(name=item["name"], top_depth_m=item["top_md"],
                                                       bottom_depth_m=item["bottom_md"], lithology=item["note"]))
        elif item["kind"] == "tubing":
            schematic.tubing_od_inch, schematic.tubing_bottom_m = item["od_in"], item["bottom_md"]
        elif item["kind"] in ("packer", "accessory"):
            etype = ElementType.PACKER if item["kind"] == "packer" else ElementType.ANNOTATION
            schematic.completion.append(CompletionItem(element_type=etype, depth_m=item["top_md"],
                                                       od_inch=item["od_in"], label=item["name"]))
    depths = [i["bottom_md"] for i in items if i["bottom_md"] is not None]
    schematic.total_depth_m = max(depths) if depths else None
    return schematic


# ---- cement worksheet geometry -----------------------------------------------------------------
def _declared(value: Optional[float], label: str, low: float, high: float) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not low <= value <= high:
        raise ArchitectureError(f"{label} must be between {low:g} and {high:g}.")
    return float(value)


def cement_annulus(components: Iterable[Dict[str, Any]], string_name: str, *,
                   open_hole_in: Optional[float] = None, caliper_in: Optional[float] = None,
                   excess_pct: Optional[float] = None) -> Dict[str, Any]:
    """Annular intervals between ``string_name`` and its outer boundary, TOC to cement bottom.

    Cased sections use the ID of the larger string covering the depth. The open
    hole uses, in this order, a declared average ``caliper_in``, the
    ``open_hole_in`` override or the string's recorded hole size; each interval
    records which (``outer_source``). An unknown size leaves that interval's
    volume ``None`` (never zero). M89: ``excess_pct`` is applied to open-hole
    intervals only and only when declared (``None`` = no excess, stated in the
    label). Capacity reuses ``AdvancedHydraulicsEngine.calc_annular_capacity_bbl_ft``.
    The result remains a WORKSHEET.
    """
    from core.hydraulics_engine import AdvancedHydraulicsEngine as engine

    caliper_in = _declared(caliper_in, "The average caliper", 0.0, 60.0)
    excess_pct = _declared(excess_pct, "The excess", 0.0, MAX_EXCESS_PCT)
    items = normalize(components)[0]
    string = next((i for i in items if i["kind"] in STRINGS and i["name"] == string_name), None)
    cement = next((i for i in items if i["kind"] == "cement" and i["name"] == string_name), None)
    if string is None or cement is None:
        raise ArchitectureError(f"'{string_name}' has no string and cement record in this architecture.")
    if string["od_in"] is None:
        raise ArchitectureError(f"'{string_name}' has no OD; the annulus cannot be derived.")
    if caliper_in is not None and caliper_in <= string["od_in"]:
        raise ArchitectureError(f"The average caliper ({caliper_in:g} in) is not larger than the string OD "
                                f"({string['od_in']:g} in).")
    if caliper_in is not None:
        hole, hole_source = caliper_in, "declared average caliper"
    elif open_hole_in is not None:
        hole, hole_source = open_hole_in, "open-hole size entered"
    elif string["hole_in"] is not None:
        hole, hole_source = string["hole_in"], "recorded hole size"
    else:
        hole, hole_source = None, "unknown"
    outers = sorted((i for i in items if i["kind"] in ("casing", "liner") and i is not string
                     and i["id_in"] is not None and i["id_in"] > string["od_in"]
                     and i["top_md"] is not None and i["bottom_md"] is not None), key=lambda i: i["bottom_md"])
    cuts = sorted({cement["top_md"], cement["bottom_md"],
                   *[o[k] for o in outers for k in ("top_md", "bottom_md")
                     if cement["top_md"] < o[k] < cement["bottom_md"]]})
    intervals: List[Dict[str, Any]] = []
    total: Optional[float] = 0.0
    base_total: Optional[float] = 0.0
    for top, bottom in zip(cuts, cuts[1:]):
        middle = (top + bottom) / 2
        host = next((o for o in outers if o["top_md"] <= middle <= o["bottom_md"]), None)
        outer = host["id_in"] if host else hole
        capacity = (engine.calc_annular_capacity_bbl_ft(outer, string["od_in"]) * 3.28084
                    if outer is not None and outer > string["od_in"] else None)
        base = capacity * (bottom - top) if capacity is not None else None
        excess = base * excess_pct / 100.0 if base is not None and host is None and excess_pct is not None else None
        volume = base + (excess or 0.0) if base is not None else None
        intervals.append({"top_md": top, "bottom_md": bottom, "outer": host["name"] if host else "open hole",
                          "outer_id_in": outer, "outer_source": f"{host['name']} ID" if host else hole_source,
                          "capacity_bbl_m": capacity, "base_volume_bbl": base, "excess_bbl": excess,
                          "volume_bbl": volume})
        total = total + volume if volume is not None and total is not None else None
        base_total = base_total + base if base is not None and base_total is not None else None
    sizes = "declared average caliper" if caliper_in is not None else "nominal sizes"
    extra = f"excess {excess_pct:g} % on open hole (declared)" if excess_pct is not None else "no excess"
    return {"string": string_name, "string_od_in": string["od_in"], "intervals": intervals,
            "base_total_bbl": base_total, "total_bbl": total, "caliper_in": caliper_in, "excess_pct": excess_pct,
            "open_hole_source": hole_source, "method": CEMENT_WORKSHEET_METHOD, "version": CEMENT_WORKSHEET_VERSION,
            "label": f"WORKSHEET ({sizes}; {extra})"}


def casing_inputs(components: Iterable[Dict[str, Any]], string_name: str) -> Dict[str, Any]:
    """M89: casing-strength inputs of one string with the origin of every value.

    ``provenance`` per field: ``architecture`` (stored on the revision),
    ``derived`` (wall = (OD - ID) / 2) or ``unknown``. The yield strength is
    never inferred from the grade text: it is always ``unknown`` here and must
    be entered by the user (recorded as ``user`` by the calculator).
    """
    items = normalize(components)[0]
    string = next((i for i in items if i["kind"] in STRINGS and i["name"] == string_name), None)
    if string is None:
        raise ArchitectureError(f"'{string_name}' is not a casing, liner or tubing string in this architecture.")
    values: Dict[str, Any] = {}
    provenance: Dict[str, str] = {}
    for key in ("od_in", "id_in", "weight_ppf"):
        values[key] = string[key]
        provenance[key] = "architecture" if string[key] is not None else "unknown"
    values["grade"] = string["grade"] or None
    provenance["grade"] = "architecture" if string["grade"] else "unknown"
    od, inner = string["od_in"], string["id_in"]
    if od is not None and inner is not None and od > inner:
        values["wall_in"], provenance["wall_in"] = (od - inner) / 2.0, "derived"
    else:
        values["wall_in"], provenance["wall_in"] = None, "unknown"
    values["yield_psi"], provenance["yield_psi"] = None, "unknown"
    return {"string": string_name, "kind": string["kind"], "top_md": string["top_md"],
            "bottom_md": string["bottom_md"], "values": values, "provenance": provenance,
            "version": CASING_SOURCE_VERSION}


# ---- M109: cement worksheet contract, re-run and verification ---------------------------------------
CEMENT_WORKSHEET_LABEL = "WORKSHEET — NOT A CEMENT DESIGN APPROVAL"
CEMENT_CALCULATOR = "Architecture › Cement annulus"
CEMENT_VERIFY_TOLERANCE_BBL = 1e-9
CEMENT_INPUTS = (("architecture_revision_id", "Architecture revision id", ""),
                 ("architecture_revision", "Architecture rev", ""),
                 ("components_sha256", "Components SHA-256", ""), ("string", "String", ""),
                 ("open_hole_in", "Open hole (in)", "in"), ("caliper_in", "Average caliper (in)", "in"),
                 ("excess_pct", "Excess on open hole (%)", "%"))
CEMENT_CONTRACT = {
    "id": "architecture.cement_annulus", "method": CEMENT_WORKSHEET_METHOD, "version": CEMENT_WORKSHEET_VERSION,
    "label": CEMENT_WORKSHEET_LABEL,
    "inputs": tuple({"id": key, "label": label, "unit": unit} for key, label, unit in CEMENT_INPUTS),
    "results": ({"id": "total_bbl", "unit": "bbl"}, {"id": "base_total_bbl", "unit": "bbl"},
                {"id": "interval_<n>", "unit": "bbl"}, {"id": "interval_<n>_excess", "unit": "bbl"}),
    "source": "the frozen well architecture revision named by architecture_revision_id (SHA-256 checked)",
    "not_inferred": ("cement yield (ft³/sk) or sacks — never inferred from a grade, class or name",
                     "slurry design, thickening time, compressive strength, gas migration — not modelled",
                     "casing yield strength — never inferred from the grade text (see casing_inputs)"),
}


def cement_case_payload(work: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(inputs, results) of a calculation case for a cement worksheet (one builder for save and re-run)."""
    inputs = {key: {"label": label, "value": work[key], **({"unit": unit} if unit else {})}
              for key, label, unit in CEMENT_INPUTS}
    results: Dict[str, Any] = {
        "total_bbl": {"label": "Total annular volume", "value": work["total_bbl"], "unit": "bbl"},
        "base_total_bbl": {"label": "Annular volume without excess", "value": work["base_total_bbl"], "unit": "bbl"}}
    for index, part in enumerate(work["intervals"], start=1):
        results[f"interval_{index}"] = {"label": f"{part['top_md']:g}-{part['bottom_md']:g} m in {part['outer']}"
                                                 f" ({part['outer_source']})",
                                        "value": part["volume_bbl"], "unit": "bbl"}
        if part["excess_bbl"] is not None:
            results[f"interval_{index}_excess"] = {"label": f"Excess in interval {index}",
                                                   "value": part["excess_bbl"], "unit": "bbl"}
    return inputs, results


def _input(inputs: Dict[str, Any], key: str):
    entry = (inputs or {}).get(key)
    return entry.get("value") if isinstance(entry, dict) else None


def cement_reproducibility(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    if version != CEMENT_WORKSHEET_VERSION:
        return "NOT REPRODUCIBLE", f"cement worksheet version {version!r} is not available in this build"
    missing = [key for key in ("architecture_revision_id", "components_sha256", "string")
               if _input(inputs, key) in (None, "")]
    if missing:
        return "NOT REPRODUCIBLE", f"the case does not record {', '.join(missing)}"
    return "REPRODUCIBLE", "re-derived from the frozen architecture revision after its SHA-256 check"


def rerun_cement_worksheet(db_manager, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """The worksheet again from the stored inputs and the frozen revision (raises on any integrity failure)."""
    revision_id = _input(inputs, "architecture_revision_id")
    stored = get_revision(db_manager, int(revision_id))          # LookupError / ArchitectureError (SHA-256)
    if stored["components_sha256"] != _input(inputs, "components_sha256"):
        raise ArchitectureError(f"Architecture revision {revision_id} no longer holds the components the case "
                                "used (SHA-256 differs).")
    work = cement_annulus(stored["components"], _input(inputs, "string"), open_hole_in=_input(inputs, "open_hole_in"),
                          caliper_in=_input(inputs, "caliper_in"), excess_pct=_input(inputs, "excess_pct"))
    return {**work, "architecture_revision_id": stored["id"], "architecture_revision": stored["revision"],
            "components_sha256": stored["components_sha256"], "open_hole_in": _input(inputs, "open_hole_in"),
            "wellbore_id": stored.get("wellbore_id")}


def verify_cement_case(db_manager, inputs: Dict[str, Any], results: Dict[str, Any], version: str) -> Dict[str, Any]:
    """Re-run a stored cement worksheet case: NOT_REPRODUCIBLE / UNREADABLE / MATCH / DIFFERENT.

    Every stored result field is compared (value within ``CEMENT_VERIFY_TOLERANCE_BBL``, label text exactly,
    fields present on one side only). ``results`` of the outcome is the fresh case payload, so a re-run can be
    stored as a NEW linked case; nothing is written here.
    """
    blank = {"method_matches": None, "current_method": "", "values": {}, "differences": [], "not_compared": []}
    status, why = cement_reproducibility(inputs, version)
    if status != "REPRODUCIBLE":
        return {**blank, "status": "NOT_REPRODUCIBLE", "detail": why}
    if db_manager is None:
        return {**blank, "status": "NOT_REPRODUCIBLE", "detail": "the architecture revision cannot be read here"}
    try:
        work = rerun_cement_worksheet(db_manager, inputs)
    except LookupError as exc:
        return {**blank, "status": "UNREADABLE", "detail": f"{exc} The stored result is shown as saved."}
    except (ArchitectureError, TypeError, ValueError) as exc:
        return {**blank, "status": "UNREADABLE", "detail": f"not re-derived: {exc}"}
    _inputs, fresh = cement_case_payload(work)
    differences = []
    for key in sorted(set(results or {}) | set(fresh)):
        old, new = (results or {}).get(key), fresh.get(key)
        if old is None or new is None:
            differences.append({"field_id": key, "stored": None if old is None else old.get("value"),
                                "current": None if new is None else new.get("value")})
            continue
        a, b = old.get("value"), new.get("value")
        numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (a, b))
        if (numeric and abs(a - b) > CEMENT_VERIFY_TOLERANCE_BBL) or (not numeric and a != b) \
                or old.get("label") != new.get("label"):
            differences.append({"field_id": key, "stored": a, "current": b,
                                **({"label": [old.get("label"), new.get("label")]}
                                   if old.get("label") != new.get("label") else {})})
    return {"status": "DIFFERENT" if differences else "MATCH", "method_matches": True,
            "current_method": f"{CEMENT_WORKSHEET_METHOD} {CEMENT_WORKSHEET_VERSION}",
            "detail": (f"{len(differences)} field(s) differ" if differences else
                       f"every stored field repeated from architecture rev {work['architecture_revision']}")
            + f". {CEMENT_WORKSHEET_LABEL}.",
            "values": {k: v["value"] for k, v in fresh.items() if v.get("value") is not None},
            "results": fresh, "work": {"label": work["label"], "wellbore_id": work.get("wellbore_id")},
            "differences": differences, "not_compared": []}


def save_cement_rerun(db_manager, source_case_id: int, inputs: Dict[str, Any], outcome: Dict[str, Any], *,
                      well_id: Optional[int], wellbore_id: Optional[int], name: str,
                      user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store a verified re-run as a NEW cement worksheet case linked ``rerun_of`` the original."""
    from core import calculation_cases as cc

    if outcome.get("status") not in ("MATCH", "DIFFERENT") or not outcome.get("results"):
        raise ValueError(f"Nothing to store: re-run status {outcome.get('status')}.")
    return cc.save_case(
        db_manager, calculator=CEMENT_CALCULATOR, name=f"{name} (re-run)", inputs=inputs, results=outcome["results"],
        method=CEMENT_WORKSHEET_METHOD, method_version=CEMENT_WORKSHEET_VERSION, well_id=well_id,
        wellbore_id=wellbore_id, user_id=user_id,
        note=f"{CEMENT_WORKSHEET_LABEL} — {outcome['work']['label']}; re-run of case #{source_case_id}: "
             f"{outcome['status']}",
        source_link={"link_type": "rerun_of", "source_table": "calculation_cases", "source_id": source_case_id,
                     "source_method": CEMENT_WORKSHEET_METHOD, "source_method_version": CEMENT_WORKSHEET_VERSION,
                     "recalc_method": CEMENT_WORKSHEET_METHOD, "recalc_method_version": CEMENT_WORKSHEET_VERSION,
                     "verification_status": outcome["status"], "method_changed": False})
