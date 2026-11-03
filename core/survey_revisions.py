"""M72: immutable survey revisions.

A survey revision is a numbered, insert-only snapshot of a well's stations
(``survey_revisions``).  Stations are previewed and validated before saving:

* units: MD is converted to metres from the declared source unit (``m`` or
  ``ft``; 1 ft = 0.3048 m exactly).  Angles are degrees.  An unknown unit is
  refused, never assumed.
* azimuth reference (``true``/``grid``/``magnetic``) and depth datum must be
  declared (no default reference since M85) and are stored. Revisions with
  different references are not compared. A reference is converted only by
  ``transform_revision`` with a user-supplied declination/convergence, its
  source and date; the result is a new revision (mode ``azimuth_transform``).
  Depth-datum shifts are not implemented (no TVD-offset field in the model).
* integrity: every read recomputes the SHA-256 of the canonical stations
  (``integrity``: VERIFIED / HASH MISMATCH). It covers the stations, not the
  computed positions; ``verify_results`` recomputes those explicitly.
* ordering: rows are sorted by MD with a warning; duplicate MDs with the same
  angles are kept once with a warning; duplicate MDs with different angles are
  an error (the user must resolve the conflict).
* values: non-finite MD/angles, a negative MD and an inclination outside
  0..180 are errors; an azimuth outside 0..360 is normalised with a warning.

Positions come from the canonical minimum-curvature engine
(``core.well_trajectory.compose_well_trajectory``) and are stored with the
stations' SHA-256.  Modes: ``initial`` (first revision), ``replace`` (a full
new set; parent = the revision it supersedes), ``append`` (parent stations
plus deeper new stations), ``branch`` (parent stations down to a tie-in MD
plus new stations, normally on another wellbore).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

SURVEY_METHOD = "minimum curvature (core.well_trajectory)"
SURVEY_REVISION_VERSION = "M72 survey revision v1"
UNITS = {"m": 1.0, "ft": 0.3048}
AZIMUTH_REFERENCES = ("true", "grid", "magnetic")
MODES = ("initial", "replace", "append", "branch")
TRANSFORM_MODE = "azimuth_transform"
DATUM_TRANSFORM_MODE = "datum_transform"
DATUM_TRANSFORM_VERSION = "M105 vertical depth-datum shift v1"
DATUM_TRANSFORM_CONVENTION = (
    "Elevations are in metres, positive upwards, relative to the stated elevation reference. "
    "offset = source datum elevation - target datum elevation; every station MD and TVD becomes depth - offset; "
    "inclination, azimuth, north and east are unchanged. Both datums are assumed to lie on the vertical "
    "through the well's surface location, so the first station must be vertical (inclination 0).")
TRANSFORM_VERSION = "M85 azimuth reference transform v1"
# true = magnetic + declination (east positive); true = grid + convergence
# (positive when grid north lies east of true north).
TRANSFORM_CONVENTION = ("true = magnetic + declination (east positive); "
                        "true = grid + convergence (grid north east of true north positive)")
MD_TOLERANCE = 1e-6          # m: two stations closer than this are the same MD
ANGLE_TOLERANCE = 1e-9       # deg: identical angles for a duplicate station


class SurveyRevisionError(ValueError):
    """The survey rows or the requested revision are not acceptable."""


@dataclass
class SurveyPreview:
    stations: List[Dict[str, float]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    source_unit: str = "m"
    azimuth_reference: str = ""
    depth_datum: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors and len(self.stations) >= 2


def _finite(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):  # silent-ok: not a number; preview() reports the row as an error
        return None
    return number if math.isfinite(number) else None


def preview(rows, *, source_unit: str = "m", azimuth_reference: str = "", depth_datum: str = "") -> SurveyPreview:
    """Validate and normalise survey rows (``md``, ``inc``, ``azi``) without saving."""
    out = SurveyPreview(source_unit=str(source_unit or "").strip().lower(),
                        azimuth_reference=str(azimuth_reference or "").strip().lower(),
                        depth_datum=str(depth_datum or "").strip())
    if out.source_unit not in UNITS:
        out.errors.append(f"Unknown depth unit {source_unit!r}; declare 'm' or 'ft'.")
    if out.azimuth_reference not in AZIMUTH_REFERENCES:
        out.errors.append("Declare the azimuth reference (true, grid or magnetic)." if not out.azimuth_reference else
                          f"Unknown azimuth reference {azimuth_reference!r}; declare true, grid or magnetic.")
    if not out.depth_datum:
        out.errors.append("Declare the depth datum (for example RKB or MSL).")
    if out.errors:
        return out
    factor = UNITS[out.source_unit]
    clean = []
    for number, row in enumerate(rows or [], 1):
        md, inc, azi = (_finite((row or {}).get(key)) for key in ("md", "inc", "azi"))
        if md is None or inc is None or azi is None:
            out.errors.append(f"Row {number}: MD, inclination and azimuth must all be finite numbers.")
            continue
        if md < 0:
            out.errors.append(f"Row {number}: negative MD {md:g}.")
            continue
        if not 0.0 <= inc <= 180.0:
            out.errors.append(f"Row {number}: inclination {inc:g} is outside 0..180 degrees.")
            continue
        if not 0.0 <= azi < 360.0:
            normalised = azi % 360.0
            out.warnings.append(f"Row {number}: azimuth {azi:g} normalised to {normalised:g} degrees.")
            azi = normalised
        clean.append((md * factor, inc, azi, number))
    if [c[0] for c in clean] != sorted(c[0] for c in clean):
        out.warnings.append("Rows were not in MD order; they were sorted by MD.")
    clean.sort(key=lambda c: (c[0], c[3]))
    for md, inc, azi, number in clean:
        if out.stations and abs(md - out.stations[-1]["md"]) <= MD_TOLERANCE:
            last = out.stations[-1]
            if abs(inc - last["inc"]) <= ANGLE_TOLERANCE and abs(azi - last["azi"]) <= ANGLE_TOLERANCE:
                out.warnings.append(f"Row {number}: duplicate station at MD {md:g} m kept once.")
            else:
                out.errors.append(f"Row {number}: MD {md:g} m appears twice with different angles; resolve it first.")
            continue
        out.stations.append({"md": md, "inc": inc, "azi": azi})
    if len(out.stations) < 2 and not out.errors:
        out.errors.append("At least two valid stations are needed.")
    return out


def stations_sha256(stations) -> str:
    payload = json.dumps([[round(s["md"], 9), round(s["inc"], 9), round(s["azi"], 9)] for s in stations])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# M105: every stored result field with its unit and verification tolerance. Results of every
# revision since M72 carry exactly these keys.  Azimuth differences wrap at 360 degrees.
RESULT_FIELDS: Dict[str, Tuple[str, float]] = {
    "md": ("m", 1e-6), "inc": ("deg", 1e-7), "azi": ("deg", 1e-7), "tvd": ("m", 1e-6),
    "north": ("m", 1e-6), "east": ("m", 1e-6), "vs": ("m", 1e-6), "hd": ("m", 1e-6),
    "dls": ("deg/30m", 1e-6),
}
RESULTS_HASH_VERSION = "M105 survey results hash v1"


def _canonical_result_value(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value if value is None else str(value)
    return round(float(value), 9) if math.isfinite(value) else str(value)


def results_sha256(results) -> str:
    """Deterministic SHA-256 of the stored results (every field, station order kept)."""
    payload = json.dumps([[_canonical_result_value((row or {}).get(key)) for key in RESULT_FIELDS]
                          + [[key, _canonical_result_value(row[key])] for key in sorted(set(row or {}) - set(RESULT_FIELDS))]
                          for row in results])
    return hashlib.sha256((RESULTS_HASH_VERSION + "\n" + payload).encode("utf-8")).hexdigest()


def compute(stations) -> List[Dict[str, float]]:
    """Positions from the canonical minimum-curvature engine."""
    from core.well_trajectory import compose_well_trajectory

    trajectory = compose_well_trajectory([dict(s) for s in stations])
    if len(trajectory.stations) != len(stations):
        problems = "; ".join(i.message for i in trajectory.issues_at_least("warning")) or trajectory.status
        raise SurveyRevisionError(f"The trajectory engine did not accept every station: {problems}")
    return [{"md": s.md, "inc": s.inc, "azi": s.azi, "tvd": s.tvd, "north": s.north, "east": s.east,
             "vs": s.vs, "hd": s.hd, "dls": s.dls} for s in trajectory.stations]


def _record(row) -> Dict[str, Any]:
    return {
        "id": row.id, "well_id": row.well_id, "wellbore_id": row.wellbore_id, "revision": row.revision,
        "parent_id": row.parent_id, "mode": row.mode, "source_type": row.source_type, "source_ref": row.source_ref,
        "source_unit": row.source_unit, "azimuth_reference": row.azimuth_reference, "depth_datum": row.depth_datum,
        "stations": json.loads(row.stations_json), "station_count": row.station_count,
        "stations_sha256": row.stations_sha256, "results": json.loads(row.results_json),
        "warnings": json.loads(row.warnings_json or "[]"), "method": row.method,
        "method_version": row.method_version, "note": row.note or "",
        "created_at": row.created_at, "created_by": row.created_by,
        "integrity": "VERIFIED" if stations_sha256(json.loads(row.stations_json)) == row.stations_sha256
        else "HASH MISMATCH",
        "results_sha256": getattr(row, "results_sha256", None),
        "results_integrity": _results_integrity(row),
    }


def _results_integrity(row) -> str:
    """VERIFIED / HASH MISMATCH, or NOT RECORDED for revisions saved before M105 (never backfilled)."""
    recorded = getattr(row, "results_sha256", None)
    if not recorded:
        return "NOT RECORDED"
    try:
        return "VERIFIED" if results_sha256(json.loads(row.results_json)) == recorded else "HASH MISMATCH"
    except (TypeError, ValueError):  # silent-ok: unreadable results are reported as HASH MISMATCH, never trusted
        return "HASH MISMATCH"


def get_revision(db, revision_id) -> Optional[Dict[str, Any]]:
    from core.database import SurveyRevision

    if not revision_id:
        return None
    with db.session_scope() as session:
        row = session.get(SurveyRevision, int(revision_id))
        return _record(row) if row is not None else None


def list_revisions(db, well_id) -> List[Dict[str, Any]]:
    from core.database import SurveyRevision

    if not well_id:
        return []
    with db.session_scope() as session:
        rows = (session.query(SurveyRevision).filter(SurveyRevision.well_id == int(well_id))
                .order_by(SurveyRevision.revision.desc()).all())
        return [_record(r) for r in rows]


def save_revision(db, well_id: int, rows, *, mode: str = "initial", parent_id: Optional[int] = None,
                  wellbore_id: Optional[int] = None, source_unit: str = "m", azimuth_reference: str = "",
                  depth_datum: str = "", source_type: str = "manual", source_ref: str = "",
                  tie_in_md: Optional[float] = None, note: str = "", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Validate, compute and insert a new revision; nothing existing is changed."""
    from core.database import SurveyRevision, Wellbore

    if mode not in MODES:
        raise SurveyRevisionError(f"Unknown mode {mode!r}.")
    checked = preview(rows, source_unit=source_unit, azimuth_reference=azimuth_reference, depth_datum=depth_datum)
    new_rows = checked.stations
    if mode != "append" and not checked.ok:
        raise SurveyRevisionError("; ".join(checked.errors) or "Not enough stations.")
    if mode == "append" and checked.errors and not (len(new_rows) == 1 and checked.errors == ["At least two valid stations are needed."]):
        raise SurveyRevisionError("; ".join(checked.errors))
    with db.session_scope() as session:
        if wellbore_id is not None:
            bore = session.get(Wellbore, int(wellbore_id))
            if bore is None or bore.well_id != int(well_id):
                raise SurveyRevisionError("The wellbore does not belong to this well.")
        parent = session.get(SurveyRevision, int(parent_id)) if parent_id else None
        if mode == "initial":
            if parent is not None:
                raise SurveyRevisionError("An initial revision has no parent.")
            stations = new_rows
        else:
            if parent is None or parent.well_id != int(well_id):
                raise SurveyRevisionError("A replace, append or branch revision needs a parent revision of this well.")
            if parent.azimuth_reference != checked.azimuth_reference or parent.depth_datum != checked.depth_datum:
                raise SurveyRevisionError(
                    f"The parent uses azimuth reference {parent.azimuth_reference!r} and datum "
                    f"{parent.depth_datum!r}; mixing references is refused; use 'Convert azimuths' (a separate revision) first.")
            base = json.loads(parent.stations_json)
            if mode == "replace":
                stations = new_rows
            elif mode == "append":
                if not new_rows or new_rows[0]["md"] <= base[-1]["md"] + MD_TOLERANCE:
                    raise SurveyRevisionError(
                        f"Appended stations must be deeper than the parent's last MD {base[-1]['md']:g} m.")
                stations = base + new_rows
            else:
                if tie_in_md is None or not math.isfinite(float(tie_in_md)):
                    raise SurveyRevisionError("A branch needs the tie-in MD on the parent.")
                kept = [s for s in base if s["md"] <= float(tie_in_md) + MD_TOLERANCE]
                if not kept or abs(kept[-1]["md"] - float(tie_in_md)) > MD_TOLERANCE:
                    raise SurveyRevisionError(f"The tie-in MD {float(tie_in_md):g} m is not a station of the parent.")
                if not new_rows or new_rows[0]["md"] <= kept[-1]["md"] + MD_TOLERANCE:
                    raise SurveyRevisionError("Branch stations must start below the tie-in MD.")
                stations = kept + new_rows
        results = compute(stations)
        number = (session.query(func.max(SurveyRevision.revision))
                  .filter(SurveyRevision.well_id == int(well_id)).scalar() or 0) + 1
        row = SurveyRevision(
            well_id=int(well_id), wellbore_id=wellbore_id, revision=number, parent_id=parent.id if parent else None,
            mode=mode, source_type=str(source_type), source_ref=str(source_ref or ""),
            source_unit=checked.source_unit, azimuth_reference=checked.azimuth_reference,
            depth_datum=checked.depth_datum, stations_json=json.dumps(stations), station_count=len(stations),
            stations_sha256=stations_sha256(stations), results_json=json.dumps(results),
            results_sha256=results_sha256(results),
            warnings_json=json.dumps(checked.warnings), method=SURVEY_METHOD,
            method_version=SURVEY_REVISION_VERSION, note=str(note or ""), created_by=user_id,
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise SurveyRevisionError("Another revision was saved at the same time; reload and try again.") from exc
        return _record(row)


def snapshot_survey_points(db, well_id: int, *, depth_datum: str, azimuth_reference: str,
                           wellbore_id: Optional[int] = None, user_id: Optional[int] = None,
                           note: str = "") -> Dict[str, Any]:
    """Freeze the well's current ``survey_points`` (stored in metres) as a new revision."""
    points = db.load_survey_points(well_id=int(well_id)) or []
    rows = [{"md": p["md"] if isinstance(p, dict) else p.md,
             "inc": p["inc"] if isinstance(p, dict) else p.inc,
             "azi": p["azi"] if isinstance(p, dict) else p.azi} for p in points]
    ids = sorted({(p.get("id") if isinstance(p, dict) else p.id) for p in points} - {None})
    latest = list_revisions(db, well_id)
    mode, parent = ("replace", latest[0]["id"]) if latest else ("initial", None)
    return save_revision(db, well_id, rows, mode=mode, parent_id=parent, wellbore_id=wellbore_id,
                         source_unit="m", azimuth_reference=azimuth_reference, depth_datum=depth_datum,
                         source_type="survey_points", source_ref=f"survey_points ids {ids[:1] + ids[-1:]} ({len(ids)} rows)",
                         note=note, user_id=user_id)


def _correction_to_true(reference: str, declination, convergence) -> float:
    if reference == "true":
        return 0.0
    if reference == "magnetic":
        return declination
    return convergence


def azimuth_correction(from_ref: str, to_ref: str, *, declination_deg: Optional[float] = None,
                       convergence_deg: Optional[float] = None) -> float:
    """Degrees to add to an azimuth in ``from_ref`` to express it in ``to_ref``.

    Uses only explicit values (no lookup): true = magnetic + declination (east
    positive) and true = grid + convergence (positive when grid north is east
    of true north). A needed value that is missing or not finite is refused.
    """
    for ref in (from_ref, to_ref):
        if ref not in AZIMUTH_REFERENCES:
            raise SurveyRevisionError(f"Unknown azimuth reference {ref!r}.")
    if from_ref == to_ref:
        raise SurveyRevisionError("The revision already uses that azimuth reference.")
    needed = {from_ref, to_ref}
    values = {}
    for name, ref, value, limit in (("declination", "magnetic", declination_deg, 180.0),
                                    ("grid convergence", "grid", convergence_deg, 90.0)):
        if ref not in needed:
            continue
        number = _finite(value)
        if number is None:
            raise SurveyRevisionError(f"Converting {from_ref} to {to_ref} needs the {name} (degrees); "
                                      "it is not looked up or assumed.")
        if abs(number) >= limit:
            raise SurveyRevisionError(f"The {name} {number:g} deg is outside the accepted range (|value| < {limit:g}).")
        values[ref] = number
    return (_correction_to_true(from_ref, values.get("magnetic"), values.get("grid"))
            - _correction_to_true(to_ref, values.get("magnetic"), values.get("grid")))


def transform_revision(db, revision_id: int, to_reference: str, *, declination_deg: Optional[float] = None,
                       convergence_deg: Optional[float] = None, parameter_source: str = "",
                       reference_date: str = "", note: str = "", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Save a new revision with every azimuth converted to ``to_reference``.

    The source revision is unchanged; the new one has mode ``azimuth_transform``,
    the source as parent, and the exact parameters, convention, their source
    and date in ``source_ref`` (canonical JSON). A declination needs its date.
    """
    from core.database import SurveyRevision

    source = get_revision(db, revision_id)
    if source is None:
        raise SurveyRevisionError(f"Survey revision {revision_id} does not exist.")
    verify_for_use(source, "an azimuth conversion")
    shift = azimuth_correction(source["azimuth_reference"], to_reference, declination_deg=declination_deg,
                               convergence_deg=convergence_deg)
    if not str(parameter_source or "").strip():
        raise SurveyRevisionError("State where the declination/convergence value comes from.")
    uses_declination = "magnetic" in (source["azimuth_reference"], to_reference)
    if uses_declination and not str(reference_date or "").strip():
        raise SurveyRevisionError("A declination changes with time; give the date it applies to.")
    stations = [{"md": st["md"], "inc": st["inc"], "azi": round((st["azi"] + shift) % 360.0, 10)}
                for st in source["stations"]]
    provenance = json.dumps({
        "method_version": TRANSFORM_VERSION, "from": source["azimuth_reference"], "to": to_reference,
        "declination_deg": _finite(declination_deg) if uses_declination else None,
        "convergence_deg": _finite(convergence_deg) if "grid" in (source["azimuth_reference"], to_reference) else None,
        "correction_deg": shift, "convention": TRANSFORM_CONVENTION,
        "parameter_source": str(parameter_source).strip(), "reference_date": str(reference_date or "").strip(),
        "source_revision_id": source["id"], "source_stations_sha256": source["stations_sha256"],
    }, sort_keys=True)
    results = compute(stations)
    with db.session_scope() as session:
        number = (session.query(func.max(SurveyRevision.revision))
                  .filter(SurveyRevision.well_id == int(source["well_id"])).scalar() or 0) + 1
        row = SurveyRevision(
            well_id=source["well_id"], wellbore_id=source["wellbore_id"], revision=number, parent_id=source["id"],
            mode=TRANSFORM_MODE, source_type=TRANSFORM_MODE, source_ref=provenance,
            source_unit=source["source_unit"], azimuth_reference=to_reference, depth_datum=source["depth_datum"],
            stations_json=json.dumps(stations), station_count=len(stations),
            stations_sha256=stations_sha256(stations), results_json=json.dumps(results),
            results_sha256=results_sha256(results),
            warnings_json=json.dumps([f"Azimuths converted {source['azimuth_reference']} -> {to_reference} by "
                                      f"{shift:+.6f} deg ({str(parameter_source).strip()})."]),
            method=SURVEY_METHOD, method_version=SURVEY_REVISION_VERSION, note=str(note or ""), created_by=user_id,
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise SurveyRevisionError("Another revision was saved at the same time; reload and try again.") from exc
        return _record(row)


def verify_results(revision: Dict[str, Any], *, tolerance_m: Optional[float] = None) -> Dict[str, Any]:
    """Recompute from the stored stations and compare EVERY stored result field.

    Checks the station count, the exact field set of every station (missing or
    extra fields), finiteness, and each field against its own tolerance and
    unit (``RESULT_FIELDS``; azimuth wraps at 360 degrees).  Reordered or
    missing stations show up as MD differences.  Separate from the station
    hash: the hash proves the stations are unchanged, this proves the derived
    results belong to them.  Nothing is repaired.
    """
    tolerances = {key: (unit, tolerance_m if tolerance_m is not None and unit == "m" else tol)
                  for key, (unit, tol) in RESULT_FIELDS.items()}
    stored = revision.get("results")
    if not isinstance(stored, list) or not all(isinstance(row, dict) for row in stored):
        return {"status": "DIFFERENT", "detail": "stored results are not a list of stations", "issue_count": 1}
    try:
        fresh = compute(revision["stations"])
    except SurveyRevisionError as exc:
        return {"status": "DIFFERENT", "detail": f"stations could not be recomputed: {exc}", "issue_count": 1}
    if len(fresh) != len(stored):
        return {"status": "DIFFERENT", "detail": f"{len(stored)} stored vs {len(fresh)} recomputed stations",
                "issue_count": 1}
    issues: List[str] = []
    worst = {key: 0.0 for key in RESULT_FIELDS}
    for index, (a, b) in enumerate(zip(stored, fresh)):
        missing, extra = sorted(set(RESULT_FIELDS) - set(a)), sorted(set(a) - set(RESULT_FIELDS))
        if missing or extra:
            issues.append(f"station {index}: missing {missing} extra {extra}")
        for key, (unit, tol) in tolerances.items():
            if key not in a:
                continue
            x, y = a[key], b.get(key)
            if x is None or y is None:
                if (x is None) != (y is None):
                    issues.append(f"station {index}: {key} stored {x!r}, recomputed {y!r}")
                continue
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
                issues.append(f"station {index}: {key} is not a finite number ({x!r})")
                continue
            delta = float(x) - float(y)
            if key == "azi":
                delta = (delta + 180.0) % 360.0 - 180.0
            worst[key] = max(worst[key], abs(delta))
            if abs(delta) > tol:
                issues.append(f"station {index}: {key} differs by {delta:.3g} {unit}")
    return {"status": "DIFFERENT" if issues else "MATCH", "issue_count": len(issues), "issues": issues[:20],
            "fields_checked": list(RESULT_FIELDS), "tolerances": {k: {"unit": u, "tolerance": t}
                                                                   for k, (u, t) in tolerances.items()},
            "max_difference": worst,
            "max_position_difference_m": max(worst[k] for k in ("tvd", "north", "east"))}


def verify_for_use(revision: Optional[Dict[str, Any]], purpose: str) -> Dict[str, Any]:
    """Fail closed before stored results feed an engineering calculation.

    Requires: station hash VERIFIED (a missing state is not VERIFIED), no
    results-hash mismatch (NOT RECORDED is allowed for pre-M105 revisions) and
    a full ``verify_results`` MATCH.  Raises ``SurveyRevisionError`` otherwise.
    """
    if not revision:
        raise SurveyRevisionError(f"No survey revision for {purpose}.")
    label = f"Survey revision {revision.get('revision', '?')}"
    if revision.get("integrity") != "VERIFIED":
        raise SurveyRevisionError(f"{label} failed its station hash check; it cannot be used for {purpose}.")
    if revision.get("results_integrity") == "HASH MISMATCH":
        raise SurveyRevisionError(f"{label}: the stored results fail their SHA-256 check; "
                                  f"it cannot be used for {purpose}.")
    check = verify_results(revision)
    if check["status"] != "MATCH":
        first = (check.get("issues") or [check.get("detail", "")])[0]
        raise SurveyRevisionError(f"{label}: the stored results do not match its stations "
                                  f"({check['issue_count']} issue(s); first: {first}); "
                                  f"it cannot be used for {purpose}.")
    return check


def transform_depth_datum(db, revision_id: int, to_datum: str, *, source_datum_elevation_m, target_datum_elevation_m,
                          elevation_reference: str, parameter_source: str, effective_date: str = "",
                          note: str = "", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Save a NEW revision whose depths are referred to ``to_datum`` (M105).

    Only an explicit vertical shift is supported: both datum elevations must be given against one stated
    reference with the source of the values.  The source revision must pass the full integrity check; it is
    never modified.  No geodetic, CRS or map-projection transform is attempted.
    """
    from core.database import SurveyRevision

    source = get_revision(db, revision_id)
    if source is None:
        raise SurveyRevisionError("That survey revision does not exist.")
    verify_for_use(source, "a depth-datum transform")
    from_datum = str(source.get("depth_datum") or "").strip()
    target = str(to_datum or "").strip()
    if not from_datum:
        raise SurveyRevisionError("The revision has no declared depth datum; an unknown datum cannot be shifted.")
    if not target:
        raise SurveyRevisionError("Declare the target depth datum (for example GL or MSL).")
    if target.lower() == from_datum.lower():
        raise SurveyRevisionError(f"The revision is already referred to {from_datum!r}.")
    reference = str(elevation_reference or "").strip()
    if not reference:
        raise SurveyRevisionError("State what both datum elevations are measured from (for example MSL).")
    if not str(parameter_source or "").strip():
        raise SurveyRevisionError("State where the datum elevations come from (rig survey, well file ...).")
    source_elev, target_elev = _finite(source_datum_elevation_m), _finite(target_datum_elevation_m)
    if source_elev is None or target_elev is None:
        raise SurveyRevisionError("Both datum elevations are required as finite numbers in metres; "
                                  "a missing elevation is never assumed to be zero.")
    stations_in = source["stations"]
    if not stations_in:
        raise SurveyRevisionError("The revision has no stations.")
    if abs(float(stations_in[0]["inc"])) > 1e-9:
        raise SurveyRevisionError(
            f"The first station (MD {stations_in[0]['md']:.2f} m) is inclined {stations_in[0]['inc']:.4f} deg; "
            "a vertical datum shift is only exact when the hole above the first station is vertical.")
    offset = round(source_elev - target_elev, 10)
    if offset == 0:
        raise SurveyRevisionError("The two elevations are equal; the shift would be zero.")
    stations = [{"md": round(float(st["md"]) - offset, 10), "inc": st["inc"], "azi": st["azi"]} for st in stations_in]
    above = [st["md"] for st in stations if st["md"] < 0]
    if above:
        raise SurveyRevisionError(
            f"{len(above)} station(s) would lie above the {target} datum (MD {above[0]:.2f} m); "
            "stations are never dropped or clamped automatically.")
    provenance = json.dumps({
        "method_version": DATUM_TRANSFORM_VERSION, "from_datum": from_datum, "to_datum": target,
        "source_datum_elevation_m": source_elev, "target_datum_elevation_m": target_elev,
        "elevation_reference": reference, "offset_m": offset, "convention": DATUM_TRANSFORM_CONVENTION,
        "parameter_source": str(parameter_source).strip(), "effective_date": str(effective_date or "").strip(),
        "source_revision_id": source["id"], "source_stations_sha256": source["stations_sha256"],
    }, sort_keys=True)
    results = compute(stations)
    with db.session_scope() as session:
        number = (session.query(func.max(SurveyRevision.revision))
                  .filter(SurveyRevision.well_id == int(source["well_id"])).scalar() or 0) + 1
        row = SurveyRevision(
            well_id=source["well_id"], wellbore_id=source["wellbore_id"], revision=number, parent_id=source["id"],
            mode=DATUM_TRANSFORM_MODE, source_type=DATUM_TRANSFORM_MODE, source_ref=provenance,
            source_unit=source["source_unit"], azimuth_reference=source["azimuth_reference"], depth_datum=target,
            stations_json=json.dumps(stations), station_count=len(stations),
            stations_sha256=stations_sha256(stations), results_json=json.dumps(results),
            results_sha256=results_sha256(results),
            warnings_json=json.dumps([f"Depths shifted {from_datum} -> {target} by {-offset:+.4f} m "
                                      f"(elevations vs {reference}; {str(parameter_source).strip()})."]),
            method=SURVEY_METHOD, method_version=SURVEY_REVISION_VERSION, note=str(note or ""), created_by=user_id,
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise SurveyRevisionError("Another revision was saved at the same time; reload and try again.") from exc
        return _record(row)


def compare_revisions(older: Dict[str, Any], newer: Dict[str, Any], *, tolerance_m: float = 1e-6,
                      tolerance_deg: float = 1e-7) -> Dict[str, Any]:
    """Station-by-station difference at common MDs plus added/removed stations."""
    for revision in (older, newer):
        try:
            verify_for_use(revision, "comparison")
        except SurveyRevisionError as exc:
            return {"comparable": False, "reason": str(exc)}
    if older["azimuth_reference"] != newer["azimuth_reference"] or older["depth_datum"] != newer["depth_datum"]:
        return {"comparable": False,
                "reason": ("Different azimuth reference or depth datum; not compared. Convert the azimuth "
                           "reference or shift the depth datum with explicit elevations first (each a new revision).")}
    a = {round(s["md"], 6): s for s in older["results"]}
    b = {round(s["md"], 6): s for s in newer["results"]}
    changed = []
    for md in sorted(set(a) & set(b)):
        diffs = {}
        for key in ("inc", "azi"):
            delta = b[md][key] - a[md][key]
            if key == "azi":
                delta = (delta + 180.0) % 360.0 - 180.0
            if abs(delta) > tolerance_deg:
                diffs[key] = delta
        for key in ("tvd", "north", "east"):
            delta = b[md][key] - a[md][key]
            if abs(delta) > tolerance_m:
                diffs[key] = delta
        if diffs:
            changed.append({"md": md, **diffs})
    return {"comparable": True, "common": len(set(a) & set(b)), "changed": changed,
            "added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
            "units": {"md": "m", "angles": "deg", "positions": "m"}}


def tie_in_from_revision(revision: Dict[str, Any], md: Optional[float] = None) -> Dict[str, Any]:
    """A plan tie-in at a station of the revision (default: its last station), pinned by id and hash."""
    verify_for_use(revision, "a plan tie-in")
    stations = revision["results"]
    station = stations[-1] if md is None else next(
        (s for s in stations if abs(s["md"] - float(md)) <= MD_TOLERANCE), None)
    if station is None:
        raise SurveyRevisionError(f"MD {md} is not a station of survey revision {revision['revision']}.")
    return {"md": station["md"], "inc": station["inc"], "azi": station["azi"], "tvd": station["tvd"],
            "north": station["north"], "east": station["east"],
            "survey_revision_id": revision["id"], "survey_sha256": revision["stations_sha256"]}
