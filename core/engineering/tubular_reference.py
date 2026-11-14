"""M157-M159: versioned, typed tubular reference data with full provenance and immutable snapshots.

Scope: drill pipe (DP), heavy-weight drill pipe (HWDP), drill collars (DC), tool joints, casing, tubing and
liners. This module is the *library* layer; the older ``drill_pipe_specs`` table (one canonical DP spec per
identity) stays readable and unchanged.

Rules (mission M157/M158):

* **No invented values.** Every engineering field is optional and ``None`` means *unavailable*; it is shown
  as "unavailable", never as 0 and never filled from another row.
* **Provenance is mandatory and typed.** ``origin`` is ``manufacturer`` (a published manufacturer document),
  ``user`` (entered or imported by the user) or ``derived`` (computed from other values - the derivation
  must be stated). A manufacturer entry needs the manufacturer, the document and the licence/terms under
  which it may be stored; a public web page alone is not a redistribution licence, so ``licence`` must be
  stated explicitly. Origins are never mixed inside one item.
* **Versioned and immutable.** Items live in a reference *set version*. A PUBLISHED version cannot change;
  a revision is a new version. A calculation stores a :func:`reference_snapshot` - the full item plus set
  name, version and fingerprints - so a later library revision can never change the meaning of an old result.
* **No bundled third-party tables.** The application ships no pipe rows: no traceable source with a
  redistribution licence was found (see the M141-M170 report, section E). Libraries are built by the user.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

CONTRACT_VERSION = "tubular-reference-v1"

COMPONENT_TYPES = ("DP", "HWDP", "DC", "TOOL_JOINT", "CASING", "TUBING", "LINER")
COMPONENT_LABELS = {
    "DP": "Drill pipe", "HWDP": "Heavy-weight drill pipe", "DC": "Drill collar", "TOOL_JOINT": "Tool joint",
    "CASING": "Casing", "TUBING": "Tubing", "LINER": "Liner",
}
ORIGINS = ("manufacturer", "user", "derived")
DRAFT, PUBLISHED = "DRAFT", "PUBLISHED"
UNAVAILABLE = "unavailable"

# field -> (label, canonical unit). Canonical units only; conversion happens at the boundary.
ENGINEERING_FIELDS: Dict[str, tuple] = {
    "nominal_od_in": ("Nominal OD", "in"),
    "id_in": ("ID", "in"),
    "wall_in": ("Wall thickness", "in"),
    "drift_in": ("Drift", "in"),
    "weight_ppf": ("Nominal weight", "lb/ft"),
    "tool_joint_od_in": ("Tool joint OD", "in"),
    "tool_joint_id_in": ("Tool joint ID", "in"),
    "burst_psi": ("Burst (internal yield)", "psi"),
    "collapse_psi": ("Collapse", "psi"),
    "tensile_klbf": ("Tensile", "klbf"),
    "torsional_ftlbf": ("Torsional yield", "ft-lbf"),
    "makeup_torque_ftlbf": ("Make-up torque", "ft-lbf"),
}


class TubularReferenceError(ValueError):
    """A spec, a provenance record or a set operation that the contract refuses."""


@dataclass(frozen=True)
class Provenance:
    origin: str
    manufacturer: Optional[str] = None
    document: Optional[str] = None
    url: Optional[str] = None
    revision: Optional[str] = None
    page: Optional[str] = None
    units: Optional[str] = None
    licence: Optional[str] = None
    file_fingerprint: Optional[str] = None
    derived_from: Optional[str] = None
    entered_by: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class TubularSpec:
    component_type: str
    designation: str
    provenance: Provenance
    grade: Optional[str] = None
    connection: Optional[str] = None
    nominal_od_in: Optional[float] = None
    id_in: Optional[float] = None
    wall_in: Optional[float] = None
    drift_in: Optional[float] = None
    weight_ppf: Optional[float] = None
    tool_joint_od_in: Optional[float] = None
    tool_joint_id_in: Optional[float] = None
    burst_psi: Optional[float] = None
    collapse_psi: Optional[float] = None
    tensile_klbf: Optional[float] = None
    torsional_ftlbf: Optional[float] = None
    makeup_torque_ftlbf: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["contract"] = CONTRACT_VERSION
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "TubularSpec":
        data = {k: v for k, v in dict(payload).items() if k != "contract"}
        prov = data.pop("provenance", None) or {}
        known = {f.name for f in fields(Provenance)}
        data["provenance"] = Provenance(**{k: v for k, v in dict(prov).items() if k in known})
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def fingerprint(self) -> str:
        return _sha(self.to_payload())

    def unavailable_fields(self) -> List[str]:
        return [name for name in ENGINEERING_FIELDS if getattr(self, name) is None]

    def display_value(self, name: str) -> str:
        value = getattr(self, name)
        if value is None:
            return UNAVAILABLE
        return f"{value:g}" if isinstance(value, float) else str(value)


def _sha(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_spec(spec: TubularSpec) -> List[str]:
    """Hard issues that refuse the spec. An empty list means it may be stored (unknowns stay unknown)."""
    issues: List[str] = []
    if spec.component_type not in COMPONENT_TYPES:
        issues.append(f"Unknown component type {spec.component_type!r}")
    if _blank(spec.designation):
        issues.append("A designation is required")
    prov = spec.provenance
    if prov.origin not in ORIGINS:
        issues.append(f"Unknown origin {prov.origin!r} (manufacturer, user or derived)")
    elif prov.origin == "manufacturer":
        for name in ("manufacturer", "document", "licence"):
            if _blank(getattr(prov, name)):
                issues.append(f"A manufacturer entry needs provenance.{name}"
                              + (" (a public page is not a redistribution licence)" if name == "licence" else ""))
    elif prov.origin == "derived" and _blank(prov.derived_from):
        issues.append("A derived entry must state what it was derived from (provenance.derived_from)")
    for name in ENGINEERING_FIELDS:
        value = getattr(spec, name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            issues.append(f"{name} must be a positive number or unavailable (got {value!r})")
    if issues:
        return issues
    od, inner, wall, drift = spec.nominal_od_in, spec.id_in, spec.wall_in, spec.drift_in
    if od is not None and inner is not None and inner >= od:
        issues.append("ID must be smaller than the nominal OD")
    if inner is not None and drift is not None and drift > inner:
        issues.append("Drift cannot exceed the ID")
    if od is not None and inner is not None and wall is not None and abs((od - inner) / 2.0 - wall) > 0.001:
        issues.append("Wall thickness contradicts (OD - ID) / 2; the values cannot all be right")
    tj_od, tj_id = spec.tool_joint_od_in, spec.tool_joint_id_in
    if tj_od is not None and tj_id is not None and tj_id >= tj_od:
        issues.append("Tool joint ID must be smaller than the tool joint OD")
    return issues


def derive_wall(spec: TubularSpec) -> Optional[TubularSpec]:
    """A *derived* copy with the wall thickness computed from OD and ID - only when both are known."""
    if spec.nominal_od_in is None or spec.id_in is None or spec.wall_in is not None:
        return None
    return replace(spec, wall_in=round((spec.nominal_od_in - spec.id_in) / 2.0, 6),
                   provenance=replace(spec.provenance, origin="derived",
                                      derived_from=f"wall = (OD - ID) / 2 from item {spec.fingerprint()[:12]}"))


# ----------------------------------------------------------------------------------------- persistence

def _set_fingerprint(name: str, version: int, item_fingerprints) -> str:
    return _sha([CONTRACT_VERSION, name, int(version), sorted(item_fingerprints)])


def create_set(db, name: str, *, notes: str = "", created_by: Optional[int] = None) -> Dict[str, Any]:
    """A new DRAFT set: version 1 for a new name, otherwise latest version + 1 (a revision copies its items)."""
    from core.database import TubularReferenceItem, TubularReferenceSet

    if _blank(name):
        raise TubularReferenceError("A reference set needs a name")
    with db.session_scope() as session:
        latest = (session.query(TubularReferenceSet).filter_by(name=name)
                  .order_by(TubularReferenceSet.version.desc()).first())
        if latest is not None and latest.status == DRAFT:
            raise TubularReferenceError(f"{name} v{latest.version} is still a draft; publish or edit it first")
        row = TubularReferenceSet(name=name, version=(latest.version + 1) if latest else 1, status=DRAFT,
                                  notes=notes or None, created_by=created_by)
        session.add(row)
        session.flush()
        if latest is not None:
            for item in latest.items:
                session.add(TubularReferenceItem(
                    set_id=row.id, component_type=item.component_type, designation=item.designation,
                    nominal_od_in=item.nominal_od_in, weight_ppf=item.weight_ppf, grade=item.grade,
                    connection=item.connection, origin=item.origin, payload_json=item.payload_json,
                    fingerprint=item.fingerprint))
        return {"id": row.id, "name": row.name, "version": row.version, "status": row.status}


def add_item(db, set_id: int, spec: TubularSpec) -> Dict[str, Any]:
    from core.database import TubularReferenceItem, TubularReferenceSet

    issues = validate_spec(spec)
    if issues:
        raise TubularReferenceError("; ".join(issues))
    fingerprint = spec.fingerprint()
    with db.session_scope() as session:
        ref = session.get(TubularReferenceSet, set_id)
        if ref is None:
            raise TubularReferenceError(f"Reference set {set_id} does not exist")
        if ref.status != DRAFT:
            raise TubularReferenceError(f"{ref.name} v{ref.version} is published and immutable; create a revision")
        if session.query(TubularReferenceItem).filter_by(set_id=set_id, fingerprint=fingerprint).first():
            return {"fingerprint": fingerprint, "status": "UNCHANGED"}
        session.add(item_row(set_id, spec))
        return {"fingerprint": fingerprint, "status": "NEW"}


def item_row(set_id: int, spec: TubularSpec):
    """The ORM row for a validated ``spec`` (M182: shared by ``add_item`` and the file importer)."""
    from core.database import TubularReferenceItem

    return TubularReferenceItem(
        set_id=set_id, component_type=spec.component_type, designation=spec.designation,
        nominal_od_in=spec.nominal_od_in, weight_ppf=spec.weight_ppf, grade=spec.grade,
        connection=spec.connection, origin=spec.provenance.origin,
        payload_json=json.dumps(spec.to_payload(), sort_keys=True, default=str), fingerprint=spec.fingerprint())


def remove_item(db, set_id: int, fingerprint: str) -> bool:
    from core.database import TubularReferenceItem, TubularReferenceSet

    with db.session_scope() as session:
        ref = session.get(TubularReferenceSet, set_id)
        if ref is None or ref.status != DRAFT:
            raise TubularReferenceError("Only an existing draft set can change; a published set is immutable")
        item = session.query(TubularReferenceItem).filter_by(set_id=set_id, fingerprint=fingerprint).first()
        if item is None:
            return False
        session.delete(item)
        return True


def publish_set(db, set_id: int) -> Dict[str, Any]:
    from core.database import TubularReferenceSet

    with db.session_scope() as session:
        ref = session.get(TubularReferenceSet, set_id)
        if ref is None:
            raise TubularReferenceError(f"Reference set {set_id} does not exist")
        if ref.status != DRAFT:
            raise TubularReferenceError(f"{ref.name} v{ref.version} is already published")
        if not ref.items:
            raise TubularReferenceError("An empty set cannot be published")
        ref.content_fingerprint = _set_fingerprint(ref.name, ref.version, [i.fingerprint for i in ref.items])
        ref.status = PUBLISHED
        ref.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return {"id": ref.id, "name": ref.name, "version": ref.version, "fingerprint": ref.content_fingerprint}


def list_sets(db) -> List[Dict[str, Any]]:
    from core.database import TubularReferenceSet

    with db.session_scope() as session:
        rows = session.query(TubularReferenceSet).order_by(TubularReferenceSet.name, TubularReferenceSet.version)
        return [{"id": r.id, "name": r.name, "version": r.version, "status": r.status,
                 "fingerprint": r.content_fingerprint, "items": len(r.items)} for r in rows]


def search(db, *, component_type: Optional[str] = None, text: str = "", od_in: Optional[float] = None,
           od_tolerance_in: float = 0.0005, origin: Optional[str] = None, set_id: Optional[int] = None,
           published_only: bool = True) -> List[Dict[str, Any]]:
    """Filter the library. Returns rows with the spec, its set version and its fingerprint."""
    from core.database import TubularReferenceItem, TubularReferenceSet

    with db.session_scope() as session:
        query = session.query(TubularReferenceItem, TubularReferenceSet).join(
            TubularReferenceSet, TubularReferenceItem.set_id == TubularReferenceSet.id)
        if published_only:
            query = query.filter(TubularReferenceSet.status == PUBLISHED)
        if set_id is not None:
            query = query.filter(TubularReferenceSet.id == set_id)
        if component_type:
            query = query.filter(TubularReferenceItem.component_type == component_type)
        if origin:
            query = query.filter(TubularReferenceItem.origin == origin)
        if od_in is not None:
            query = query.filter(TubularReferenceItem.nominal_od_in.between(od_in - od_tolerance_in,
                                                                            od_in + od_tolerance_in))
        needle = (text or "").strip().lower()
        out = []
        for item, ref in query.order_by(TubularReferenceItem.component_type, TubularReferenceItem.nominal_od_in,
                                        TubularReferenceItem.designation):
            spec = TubularSpec.from_payload(json.loads(item.payload_json))
            haystack = " ".join(str(v) for v in (spec.designation, spec.grade, spec.connection,
                                                 spec.provenance.manufacturer, spec.provenance.document) if v)
            if needle and needle not in haystack.lower():
                continue
            out.append({"spec": spec, "fingerprint": item.fingerprint, "set_id": ref.id, "set_name": ref.name,
                        "set_version": ref.version, "set_status": ref.status,
                        "set_fingerprint": ref.content_fingerprint})
        return out


# ------------------------------------------------------------------------------------------ snapshots

def reference_snapshot(row: Mapping[str, Any]) -> Dict[str, Any]:
    """The immutable value a calculation stores: the full spec plus the exact library version it came from.

    Only items of a PUBLISHED set can be cited - a draft can still change under the calculation.
    """
    if row.get("set_status") != PUBLISHED or not row.get("set_fingerprint"):
        raise TubularReferenceError("Only an item of a published reference set can be used in a calculation")
    spec = row["spec"]
    snapshot = {"contract": CONTRACT_VERSION, "set_name": row["set_name"], "set_version": int(row["set_version"]),
                "set_fingerprint": row["set_fingerprint"], "item_fingerprint": spec.fingerprint(),
                "spec": spec.to_payload()}
    snapshot["snapshot_fingerprint"] = _sha({k: v for k, v in snapshot.items()})
    return snapshot


def verify_snapshot(snapshot: Mapping[str, Any]) -> List[str]:
    """Problems with a stored snapshot (empty = intact). The library is NOT consulted: the snapshot stands alone."""
    problems: List[str] = []
    body = {k: v for k, v in dict(snapshot).items() if k != "snapshot_fingerprint"}
    if _sha(body) != snapshot.get("snapshot_fingerprint"):
        problems.append("Snapshot content does not match its fingerprint (modified after it was stored)")
    try:
        spec = TubularSpec.from_payload(snapshot.get("spec") or {})
    except TypeError as exc:
        return problems + [f"Snapshot spec is unreadable: {exc}"]
    if spec.fingerprint() != snapshot.get("item_fingerprint"):
        problems.append("Snapshot spec does not match its item fingerprint")
    return problems


def snapshot_drift(db, snapshot: Mapping[str, Any]) -> Optional[str]:
    """Explain how the library differs from a stored snapshot today (None = the cited version is unchanged)."""
    from core.database import TubularReferenceItem, TubularReferenceSet

    with db.session_scope() as session:
        ref = session.query(TubularReferenceSet).filter_by(name=snapshot.get("set_name"),
                                                           version=snapshot.get("set_version")).first()
        if ref is None:
            return "The cited reference set version is no longer in this database; the snapshot is still valid"
        if ref.content_fingerprint != snapshot.get("set_fingerprint"):
            return "The cited set version has a different fingerprint than when the snapshot was taken"
        found = session.query(TubularReferenceItem).filter_by(
            set_id=ref.id, fingerprint=snapshot.get("item_fingerprint")).first()
        if found is None:
            return "The cited item is not in the cited set version"
        newer = (session.query(TubularReferenceSet).filter(TubularReferenceSet.name == ref.name,
                                                           TubularReferenceSet.version > ref.version,
                                                           TubularReferenceSet.status == PUBLISHED).count())
        return f"{newer} newer published version(s) exist; this calculation keeps citing v{ref.version}" if newer else None
