"""Named, revisioned Well Trajectory Viewer views (M178) and their export (M179).

Why this exists
---------------
The legacy W6 "Trajectory Plot" tab saved an unnamed ``trajectory_plots`` row bound to a daily report only
(no well, wellbore or survey revision), never reopened it (``load_plots`` replotted the current surveys) and
exported a CSV whose ``Z`` column was the constant 0 and that had no units.  This module is the canonical
replacement used by the Well Trajectory Viewer (``tabs/trajectory_viewer.py``):

* a *view* is named and bound to its well, optionally to a wellbore of that well and to the immutable survey
  revision it shows; every save inserts an immutable revision (``trajectory_view_revisions``, storage guard and
  insert-only policy).  Revise / clone / archive / restore add a revision; nothing is updated or deleted;
* the revision stores the viewer settings, a snapshot of the composed stations (canonical metres, degrees,
  deg/30 m - exactly what ``core.well_trajectory`` returned, no extra calculation) with its SHA-256, and the
  SHA-256 of the input stations; reopening shows the snapshot and states whether the current data still produce
  it (``MATCH`` / ``DIFFERENT`` / ``NOT_REPRODUCIBLE`` / ``UNREADABLE``) - it is never silently redrawn from
  changed surveys;
* revise and archive use optimistic concurrency: the caller states the head revision it saw;
* the comparison of two revisions pairs stations by MD only; a station missing on one side is listed, never
  interpolated;
* the export writes only stored stations, in the chosen display unit with the unit in every header; a value the
  snapshot does not hold is an empty cell, never 0.

Legacy rows of ``trajectory_plots`` stay in the database and are listed read-only (``legacy_plots``).

Not claimed: survey uncertainty, grid convergence / map projection, a datum or tie-on other than the one the
source stations carry.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from core.survey_revisions import SURVEY_METHOD
from core.well_trajectory import DLS_30M_TO_100FT, FT_PER_M, NO_DATA, compose_well_trajectory

VIEW_CONTRACT = "trajectory-view-v1"
EXPORT_CONTRACT = "trajectory-view-export-v1"
VIEW_METHOD_VERSION = "M178 trajectory view snapshot v1"

ACTIVE, ARCHIVED = "ACTIVE", "ARCHIVED"
CREATE, REVISE, CLONE, ARCHIVE, RESTORE = "CREATE", "REVISE", "CLONE", "ARCHIVE", "RESTORE"
SOURCE_POINTS, SOURCE_REVISION = "survey_points", "survey_revision"

MATCH, DIFFERENT, NOT_REPRODUCIBLE, UNREADABLE = "MATCH", "DIFFERENT", "NOT_REPRODUCIBLE", "UNREADABLE"

DEFAULT_SETTINGS = {"scope": "well", "unit": "m", "vs_mode": "closure", "vs_azimuth": None,
                    "show_stations": True, "equal_scale": True}
STATION_FIELDS = ("md", "inc", "azi", "tvd", "north", "east", "vs", "hd", "dls")
MD_TOLERANCE = 1e-6
NAME_MAX = 200


class TrajectoryViewError(ValueError):
    """The view, its source or the requested change is not acceptable; nothing was saved."""


class StaleViewError(TrajectoryViewError):
    """Another revision was saved since the caller read the view (optimistic concurrency)."""


# ---- settings and snapshot ---------------------------------------------------------------------------------------
def _finite(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):  # silent-ok: an unparsable value is missing; callers refuse it
        return None
    return number if math.isfinite(number) else None


def normalise_settings(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validated viewer settings; unknown keys and invalid values are refused, never coerced."""
    raw = dict(settings or {})
    unknown = sorted(set(raw) - set(DEFAULT_SETTINGS))
    if unknown:
        raise TrajectoryViewError(f"Unknown view setting(s): {', '.join(unknown)}.")
    out = dict(DEFAULT_SETTINGS, **raw)
    if out["scope"] not in ("well", "report"):
        raise TrajectoryViewError("The scope must be 'well' or 'report'.")
    if out["unit"] not in ("m", "ft"):
        raise TrajectoryViewError("The display unit must be 'm' or 'ft'.")
    if out["vs_mode"] not in ("closure", "user"):
        raise TrajectoryViewError("The VS azimuth mode must be 'closure' or 'user'.")
    if out["vs_mode"] == "user":
        azimuth = _finite(out["vs_azimuth"])
        if azimuth is None or not 0.0 <= azimuth < 360.0:
            raise TrajectoryViewError("A custom VS azimuth must be a finite number in 0..360 degrees.")
        out["vs_azimuth"] = azimuth
    else:
        out["vs_azimuth"] = None
    for key in ("show_stations", "equal_scale"):
        if not isinstance(out[key], bool):
            raise TrajectoryViewError(f"The setting {key!r} must be true or false.")
    return out


def _round(value):
    return None if value is None else round(float(value), 9)


def snapshot_sha256(stations: Sequence[Dict[str, Any]]) -> str:
    payload = json.dumps([[_round(s.get(k)) for k in STATION_FIELDS] + [list(s.get("report_ids") or [])]
                          for s in stations])
    return hashlib.sha256((VIEW_METHOD_VERSION + "\n" + payload).encode("utf-8")).hexdigest()


def source_sha256(rows: Sequence[Dict[str, Any]]) -> str:
    """SHA-256 of the measured inputs (id, report, MD, Inc, Azi) in MD order - what the snapshot was built from."""
    payload = json.dumps(sorted([[r.get("id"), r.get("report_id"), _round(_finite(r.get("md"))),
                                  _round(_finite(r.get("inc"))), _round(_finite(r.get("azi")))] for r in rows],
                                key=lambda x: (x[2] is None, x[2] or 0.0, str(x[0]))))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ViewCapture:
    """The source rows and the composed trajectory of one view, before it is saved."""

    settings: Dict[str, Any]
    source_kind: str
    source_report_id: Optional[int]
    survey_revision_id: Optional[int]
    source_rows: List[Dict[str, Any]]
    trajectory: Any
    stations: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def source_sha256(self) -> str:
        return source_sha256(self.source_rows)

    @property
    def stations_sha256(self) -> str:
        return snapshot_sha256(self.stations)

    def trajectory_summary(self) -> Dict[str, Any]:
        t = self.trajectory
        return {"status": t.status, "vs_azimuth": t.vs_azimuth, "vs_azimuth_source": t.vs_azimuth_source,
                "closure_distance": t.closure_distance, "closure_azimuth": t.closure_azimuth,
                "input_rows": t.input_rows, "excluded_rows": t.excluded_rows,
                "issues": [{"code": i.code, "severity": i.severity, "message": i.message, "md": i.md}
                           for i in t.issues]}


def _source_rows(db, well_id: int, settings, *, report_id=None, survey_revision_id=None):
    from core import survey_revisions as sr

    if survey_revision_id:
        revision = sr.get_revision(db, survey_revision_id)
        if revision is None or revision["well_id"] != int(well_id):
            raise TrajectoryViewError("The survey revision does not belong to this well.")
        if revision["integrity"] != "VERIFIED":
            raise TrajectoryViewError(f"Survey revision {revision['revision']} failed its integrity check "
                                      f"({revision['integrity']}); it is not used for a saved view.")
        if settings["scope"] != "well":
            raise TrajectoryViewError("A survey revision is a whole-well source; the report scope does not apply.")
        rows = [{"id": None, "report_id": None, "md": s["md"], "inc": s["inc"], "azi": s["azi"]}
                for s in revision["stations"]]
        return SOURCE_REVISION, None, int(survey_revision_id), rows
    scope_report = None
    if settings["scope"] == "report":
        if not report_id:
            raise TrajectoryViewError("The report scope needs a selected daily report.")
        scope_report = int(report_id)
    stored = db.load_survey_points(well_id=int(well_id), report_id=scope_report)
    foreign = [r for r in stored if r.get("well_id") not in (None, int(well_id))]
    if foreign:
        raise TrajectoryViewError("The selected report holds survey stations of another well; nothing was saved.")
    rows = [{"id": r.get("id"), "report_id": r.get("report_id"), "md": r.get("md"), "inc": r.get("inc"),
             "azi": r.get("azi"), "tool": r.get("tool")} for r in stored]
    return SOURCE_POINTS, scope_report, None, rows


def capture(db, well_id: int, settings: Optional[Dict[str, Any]] = None, *, report_id: Optional[int] = None,
            survey_revision_id: Optional[int] = None) -> ViewCapture:
    """Read the source stations and compose the trajectory exactly as the viewer does (no new formula)."""
    if not well_id:
        raise TrajectoryViewError("Select a well first.")
    settings = normalise_settings(settings)
    kind, scope_report, revision_id, rows = _source_rows(db, well_id, settings, report_id=report_id,
                                                         survey_revision_id=survey_revision_id)
    trajectory = compose_well_trajectory(rows, vs_azimuth=settings["vs_azimuth"])
    stations = [{**{k: getattr(s, k) for k in STATION_FIELDS}, "report_ids": list(s.report_ids)}
                for s in trajectory.stations]
    return ViewCapture(settings, kind, scope_report, revision_id, rows, trajectory, stations)


# ---- records ----------------------------------------------------------------------------------------------------
def _record(row) -> Dict[str, Any]:
    out = {"id": row.id, "well_id": row.well_id, "wellbore_id": row.wellbore_id, "view_key": row.view_key,
           "revision": row.revision, "parent_id": row.parent_id, "action": row.action, "status": row.status,
           "name": row.name, "source_kind": row.source_kind, "source_report_id": row.source_report_id,
           "survey_revision_id": row.survey_revision_id, "source_sha256": row.source_sha256,
           "station_count": row.station_count, "stations_sha256": row.stations_sha256, "method": row.method,
           "method_version": row.method_version, "note": row.note or "", "created_at": row.created_at,
           "created_by": row.created_by}
    try:
        out["settings"] = json.loads(row.settings_json)
        out["stations"] = json.loads(row.stations_json)
        out["trajectory"] = json.loads(row.trajectory_json)
        readable = isinstance(out["stations"], list) and isinstance(out["settings"], dict)
    except (TypeError, ValueError):  # silent-ok: an unreadable snapshot is reported as UNREADABLE, never drawn
        readable = False
    if not readable:
        out.update(settings={}, stations=[], trajectory={}, integrity=UNREADABLE)
    elif len(out["stations"]) != row.station_count or snapshot_sha256(out["stations"]) != row.stations_sha256:
        out["integrity"] = "HASH MISMATCH"
    else:
        out["integrity"] = "VERIFIED"
    return out


def get_view(db, revision_id) -> Optional[Dict[str, Any]]:
    from core.database import TrajectoryViewRevision

    if not revision_id:
        return None
    with db.session_scope() as session:
        row = session.get(TrajectoryViewRevision, int(revision_id))
        return _record(row) if row is not None else None


def history(db, view_key: str) -> List[Dict[str, Any]]:
    from core.database import TrajectoryViewRevision

    with db.session_scope() as session:
        rows = (session.query(TrajectoryViewRevision).filter(TrajectoryViewRevision.view_key == str(view_key))
                .order_by(TrajectoryViewRevision.revision.desc()).all())
        return [_record(r) for r in rows]


def list_views(db, well_id, *, include_archived: bool = False) -> List[Dict[str, Any]]:
    """The head (latest revision) of every view of the well, newest first."""
    from core.database import TrajectoryViewRevision

    if not well_id:
        return []
    with db.session_scope() as session:
        rows = (session.query(TrajectoryViewRevision).filter(TrajectoryViewRevision.well_id == int(well_id))
                .order_by(TrajectoryViewRevision.view_key, TrajectoryViewRevision.revision.desc()).all())
        heads: Dict[str, Any] = {}
        for row in rows:
            heads.setdefault(row.view_key, row)
        records = [_record(r) for r in heads.values() if include_archived or r.status == ACTIVE]
    return sorted(records, key=lambda r: (r["created_at"], r["id"]), reverse=True)


# ---- writes (insert-only) ---------------------------------------------------------------------------------------
def _clean_name(name) -> str:
    text = " ".join(str(name or "").split())
    if not text:
        raise TrajectoryViewError("A saved view needs a name.")
    if len(text) > NAME_MAX:
        raise TrajectoryViewError(f"The view name is longer than {NAME_MAX} characters.")
    return text


def _check_unique_name(session, well_id: int, name: str, *, except_key: Optional[str] = None) -> None:
    from core.database import TrajectoryViewRevision

    rows = (session.query(TrajectoryViewRevision).filter(TrajectoryViewRevision.well_id == int(well_id))
            .order_by(TrajectoryViewRevision.view_key, TrajectoryViewRevision.revision.desc()).all())
    heads: Dict[str, Any] = {}
    for row in rows:
        heads.setdefault(row.view_key, row)
    folded = name.casefold()
    for key, head in heads.items():
        if key != except_key and head.status == ACTIVE and head.name.casefold() == folded:
            raise TrajectoryViewError(f"The well already has an active view named {head.name!r}.")


def _check_wellbore(session, well_id: int, wellbore_id) -> Optional[int]:
    from core.database import Wellbore

    if wellbore_id is None:
        return None
    bore = session.get(Wellbore, int(wellbore_id))
    if bore is None or bore.well_id != int(well_id):
        raise TrajectoryViewError("The wellbore does not belong to this well.")
    return int(wellbore_id)


def _insert(db, session, *, well_id, wellbore_id, view_key, revision, parent_id, action, status, name,
            capture_or_record, note, user_id) -> Dict[str, Any]:
    from core.database import TrajectoryViewRevision

    if isinstance(capture_or_record, ViewCapture):
        c = capture_or_record
        fields = dict(source_kind=c.source_kind, source_report_id=c.source_report_id,
                      survey_revision_id=c.survey_revision_id, source_sha256=c.source_sha256,
                      settings_json=json.dumps(c.settings, sort_keys=True), stations_json=json.dumps(c.stations),
                      station_count=len(c.stations), stations_sha256=c.stations_sha256,
                      trajectory_json=json.dumps(c.trajectory_summary(), sort_keys=True))
    else:
        r = capture_or_record           # archive / restore / clone copy the stored snapshot unchanged
        if r["integrity"] != "VERIFIED":
            raise TrajectoryViewError(f"The stored snapshot is {r['integrity']}; it is not copied.")
        fields = dict(source_kind=r["source_kind"], source_report_id=r["source_report_id"],
                      survey_revision_id=r["survey_revision_id"], source_sha256=r["source_sha256"],
                      settings_json=json.dumps(r["settings"], sort_keys=True),
                      stations_json=json.dumps(r["stations"]), station_count=r["station_count"],
                      stations_sha256=r["stations_sha256"], trajectory_json=json.dumps(r["trajectory"], sort_keys=True))
    row = TrajectoryViewRevision(well_id=int(well_id), wellbore_id=wellbore_id, view_key=view_key, revision=revision,
                                 parent_id=parent_id, action=action, status=status, name=name, method=SURVEY_METHOD,
                                 method_version=VIEW_METHOD_VERSION, note=str(note or ""), created_by=user_id,
                                 **fields)
    session.add(row)
    try:
        session.flush()
    except Exception as exc:
        if "UNIQUE" in str(exc) or "cannot be replaced" in str(exc):
            raise StaleViewError("Another revision of this view was saved at the same time; reload it.") from exc
        raise
    db._add_mandatory_audit(session, "trajectory_view_" + action.lower(), "well", int(well_id), name,
                            json.dumps({"view_revision_id": row.id, "view_key": view_key, "revision": revision,
                                        "parent_id": parent_id, "status": status,
                                        "stations_sha256": row.stations_sha256}, sort_keys=True))
    return _record(row)


def _actor(db) -> Optional[int]:
    user_id, _name = db._audit_actor()
    return user_id


def _head(session, view_key: str):
    from core.database import TrajectoryViewRevision

    return (session.query(TrajectoryViewRevision).filter(TrajectoryViewRevision.view_key == str(view_key))
            .order_by(TrajectoryViewRevision.revision.desc()).first())


def _require_head(session, view_key: str, expected_revision) -> Any:
    head = _head(session, view_key)
    if head is None:
        raise TrajectoryViewError("The saved view no longer exists.")
    if expected_revision is None or int(expected_revision) != head.revision:
        raise StaleViewError(f"The view is now at revision {head.revision} (you opened revision "
                             f"{expected_revision}); reopen it before changing it. Nothing was saved.")
    return head


def _drawable(c: ViewCapture) -> None:
    if not c.trajectory.drawable:
        raise TrajectoryViewError("The current scope has no drawable trajectory (at least two valid stations are "
                                  "needed); nothing was saved.")


def save_view(db, well_id: int, name: str, settings: Optional[Dict[str, Any]] = None, *,
              wellbore_id: Optional[int] = None, report_id: Optional[int] = None,
              survey_revision_id: Optional[int] = None, note: str = "") -> Dict[str, Any]:
    """Create a new named view (revision 1) from the current data."""
    name = _clean_name(name)
    c = capture(db, well_id, settings, report_id=report_id, survey_revision_id=survey_revision_id)
    _drawable(c)
    with db.session_scope() as session:
        bore = _check_wellbore(session, well_id, wellbore_id)
        _check_unique_name(session, well_id, name)
        return _insert(db, session, well_id=well_id, wellbore_id=bore, view_key=str(uuid.uuid4()), revision=1,
                       parent_id=None, action=CREATE, status=ACTIVE, name=name, capture_or_record=c, note=note,
                       user_id=_actor(db))


def revise_view(db, view_key: str, *, expected_revision: int, settings: Optional[Dict[str, Any]] = None,
                name: Optional[str] = None, report_id: Optional[int] = None,
                survey_revision_id: Optional[int] = None, note: str = "") -> Dict[str, Any]:
    """A new revision of an ACTIVE view from the current data (and optionally new settings or name)."""
    with db.session_scope() as session:
        head = _require_head(session, view_key, expected_revision)
        if head.status != ACTIVE:
            raise TrajectoryViewError("An archived view is read-only; restore it before revising it.")
        well_id, wellbore_id, current_name = head.well_id, head.wellbore_id, head.name
        base_settings = json.loads(head.settings_json)
        base_report, base_revision = head.source_report_id, head.survey_revision_id
    new_name = _clean_name(name) if name is not None else current_name
    c = capture(db, well_id, settings if settings is not None else base_settings,
                report_id=report_id if report_id is not None else base_report,
                survey_revision_id=survey_revision_id if survey_revision_id is not None else base_revision)
    _drawable(c)
    with db.session_scope() as session:
        head = _require_head(session, view_key, expected_revision)   # re-checked inside the writing transaction
        _check_unique_name(session, well_id, new_name, except_key=view_key)
        return _insert(db, session, well_id=well_id, wellbore_id=wellbore_id, view_key=view_key,
                       revision=head.revision + 1, parent_id=head.id, action=REVISE, status=ACTIVE, name=new_name,
                       capture_or_record=c, note=note, user_id=_actor(db))


def clone_view(db, revision_id: int, name: str, *, note: str = "") -> Dict[str, Any]:
    """A new view whose revision 1 is an exact copy of the stored snapshot of ``revision_id``."""
    name = _clean_name(name)
    source = get_view(db, revision_id)
    if source is None:
        raise TrajectoryViewError("The view revision to clone does not exist.")
    with db.session_scope() as session:
        _check_unique_name(session, source["well_id"], name)
        return _insert(db, session, well_id=source["well_id"], wellbore_id=source["wellbore_id"],
                       view_key=str(uuid.uuid4()), revision=1, parent_id=source["id"], action=CLONE, status=ACTIVE,
                       name=name, capture_or_record=source, note=note, user_id=_actor(db))


def _status_change(db, view_key: str, expected_revision: int, reason: str, *, to_status: str, action: str):
    reason = (reason or "").strip()
    if not reason:
        raise TrajectoryViewError(f"{action.title()} needs a reason.")
    with db.session_scope() as session:
        head = _require_head(session, view_key, expected_revision)
        if head.status == to_status:
            raise TrajectoryViewError(f"The view is already {to_status}.")
        if to_status == ACTIVE:
            _check_unique_name(session, head.well_id, head.name, except_key=view_key)
        record = _record(head)
        return _insert(db, session, well_id=head.well_id, wellbore_id=head.wellbore_id, view_key=view_key,
                       revision=head.revision + 1, parent_id=head.id, action=action, status=to_status,
                       name=head.name, capture_or_record=record, note=reason, user_id=_actor(db))


def archive_view(db, view_key: str, *, expected_revision: int, reason: str) -> Dict[str, Any]:
    return _status_change(db, view_key, expected_revision, reason, to_status=ARCHIVED, action=ARCHIVE)


def restore_view(db, view_key: str, *, expected_revision: int, reason: str) -> Dict[str, Any]:
    return _status_change(db, view_key, expected_revision, reason, to_status=ACTIVE, action=RESTORE)


# ---- reopen: drift against the current data ----------------------------------------------------------------------
@dataclass(frozen=True)
class Drift:
    state: str
    reason: str
    current_stations_sha256: Optional[str] = None
    current_source_sha256: Optional[str] = None


def drift(db, record: Optional[Dict[str, Any]]) -> Drift:
    """Does the current data still produce the stored snapshot?  Never repairs or redraws the record."""
    if record is None:
        return Drift(UNREADABLE, "The view revision does not exist.")
    if record.get("integrity") != "VERIFIED":
        return Drift(UNREADABLE, f"The stored snapshot is {record.get('integrity')}; it is not trusted.")
    if record["source_kind"] == SOURCE_REVISION and record.get("survey_revision_id") is None:
        return Drift(NOT_REPRODUCIBLE, "The survey revision this view was built from no longer exists.")
    try:
        current = capture(db, record["well_id"], record["settings"], report_id=record["source_report_id"],
                          survey_revision_id=record["survey_revision_id"])
    except TrajectoryViewError as exc:
        return Drift(NOT_REPRODUCIBLE, str(exc))
    if current.trajectory.status == NO_DATA:
        return Drift(NOT_REPRODUCIBLE, "No survey stations are stored for this scope any more.",
                     current.stations_sha256, current.source_sha256)
    if current.stations_sha256 == record["stations_sha256"]:
        return Drift(MATCH, "The current data reproduce the saved snapshot.", current.stations_sha256,
                     current.source_sha256)
    return Drift(DIFFERENT, "The survey data changed since this view was saved; the saved snapshot is shown, "
                 "not the current trajectory.", current.stations_sha256, current.source_sha256)


# ---- comparison (no interpolation) -------------------------------------------------------------------------------
COMPARE_FIELDS = ("inc", "azi", "tvd", "north", "east", "vs", "dls")


def compare(older: Dict[str, Any], newer: Dict[str, Any]) -> Dict[str, Any]:
    """Pair stations of two saved revisions by MD; unmatched stations are listed, never interpolated."""
    for record in (older, newer):
        if record.get("integrity") != "VERIFIED":
            raise TrajectoryViewError(f"View revision {record.get('id')} is {record.get('integrity')}; "
                                      "it is not compared.")
    if older["well_id"] != newer["well_id"]:
        raise TrajectoryViewError("Only views of the same well are compared.")
    remaining = list(newer["stations"])
    pairs, only_old = [], []
    for station in older["stations"]:
        match = next((s for s in remaining if abs(s["md"] - station["md"]) <= MD_TOLERANCE), None)
        if match is None:
            only_old.append(station["md"])
            continue
        remaining.remove(match)
        delta = {}
        for key in COMPARE_FIELDS:
            a, b = _finite(station.get(key)), _finite(match.get(key))
            delta[key] = None if a is None or b is None else b - a
        pairs.append({"md": station["md"], "delta": delta})
    settings_changed = sorted(k for k in set(older["settings"]) | set(newer["settings"])
                              if older["settings"].get(k) != newer["settings"].get(k))
    worst = {key: max((abs(p["delta"][key]) for p in pairs if p["delta"][key] is not None), default=None)
             for key in COMPARE_FIELDS}
    return {"older_id": older["id"], "newer_id": newer["id"], "paired": pairs, "only_in_older": only_old,
            "only_in_newer": [s["md"] for s in remaining], "settings_changed": settings_changed,
            "max_abs_delta": worst, "identical": older["stations_sha256"] == newer["stations_sha256"],
            "method": "pairs stations by MD within 1e-6 m; no interpolation"}


# ---- export (M179) -----------------------------------------------------------------------------------------------
def _length(value, unit: str):
    number = _finite(value)
    if number is None:
        return None
    return number * FT_PER_M if unit == "ft" else number


def _dls(value, unit: str):
    number = _finite(value)
    if number is None:
        return None
    return number * DLS_30M_TO_100FT if unit == "ft" else number


def export_columns(unit: str) -> List[str]:
    dls = "DLS (deg/30m)" if unit == "m" else "DLS (deg/100ft)"
    return [f"MD ({unit})", "Inc (deg)", "Azi (deg)", f"TVD ({unit})", f"North ({unit})", f"East ({unit})",
            f"VS ({unit})", dls, "Reports"]


def export_rows(record: Dict[str, Any], unit: str) -> List[List[Any]]:
    """One row per stored station in ``unit``; a value the snapshot does not hold stays None (never 0)."""
    if unit not in ("m", "ft"):
        raise TrajectoryViewError("The export unit must be 'm' or 'ft'.")
    if record.get("integrity") != "VERIFIED":
        raise TrajectoryViewError(f"The stored snapshot is {record.get('integrity')}; it is not exported.")
    rows = []
    for s in record["stations"]:
        rows.append([_length(s.get("md"), unit), _finite(s.get("inc")), _finite(s.get("azi")),
                     _length(s.get("tvd"), unit), _length(s.get("north"), unit), _length(s.get("east"), unit),
                     _length(s.get("vs"), unit), _dls(s.get("dls"), unit),
                     ";".join(str(r) for r in s.get("report_ids") or [])])
    return rows


def export_header(record: Dict[str, Any], unit: str, *, well_label: str = "") -> List[List[str]]:
    t = record.get("trajectory") or {}
    vs = t.get("vs_azimuth")
    return [
        ["DrillMaster saved trajectory view", EXPORT_CONTRACT],
        ["View", record["name"]],
        ["Revision", str(record["revision"]), record["status"]],
        ["Well", well_label or f"well #{record['well_id']}"],
        ["Wellbore", "" if record["wellbore_id"] is None else f"wellbore #{record['wellbore_id']}"],
        ["Source", record["source_kind"], "" if record["survey_revision_id"] is None
         else f"survey revision id {record['survey_revision_id']}",
         "" if record["source_report_id"] is None else f"report id {record['source_report_id']}"],
        ["Units", f"lengths {unit}; angles deg; DLS {'deg/30m' if unit == 'm' else 'deg/100ft'}"],
        ["VS azimuth (deg)", "" if vs is None else f"{vs:.6f}", str(t.get("vs_azimuth_source") or "")],
        ["Method", record["method"], record["method_version"]],
        ["Snapshot SHA-256", record["stations_sha256"]],
        ["Note", "Stored stations only; no interpolation. An empty cell is a value the snapshot does not hold."],
    ]


def export_csv(path: str, record: Dict[str, Any], unit: str, *, well_label: str = "") -> int:
    rows = export_rows(record, unit)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        out = csv.writer(handle)
        for line in export_header(record, unit, well_label=well_label):
            out.writerow(line)
        out.writerow([])
        out.writerow(export_columns(unit))
        for row in rows:
            out.writerow(["" if v is None else (f"{v:.6f}" if isinstance(v, float) else v) for v in row])
    return len(rows)


def export_json(path: str, record: Dict[str, Any], unit: str, *, well_label: str = "") -> int:
    rows = export_rows(record, unit)
    columns = export_columns(unit)
    payload = {"contract": EXPORT_CONTRACT, "header": export_header(record, unit, well_label=well_label),
               "columns": columns, "stations": [dict(zip(columns, row)) for row in rows]}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
    return len(rows)


# ---- legacy read-compat adapter (M180) ---------------------------------------------------------------------------
LEGACY_LABEL = ("LEGACY 'Trajectory Plot' snapshot - read-only; bound to a daily report only (no well, wellbore "
                "or survey revision); its CSV export wrote Z = 0 and no units")


def legacy_plots(db, well_id) -> List[Dict[str, Any]]:
    """Read-only list of legacy ``trajectory_plots`` rows of the well's reports (the data is kept, never edited)."""
    from core.database import DailyReport, TrajectoryPlot

    if not well_id:
        return []
    out = []
    with db.session_scope() as session:
        rows = (session.query(TrajectoryPlot, DailyReport.report_date)
                .join(DailyReport, TrajectoryPlot.report_id == DailyReport.id)
                .filter(DailyReport.well_id == int(well_id)).order_by(TrajectoryPlot.id).all())
        for plot, report_date in rows:
            data = plot.plot_data_json
            try:
                parsed = json.loads(data) if isinstance(data, str) else data
                readable = isinstance(parsed, dict)
            except (TypeError, ValueError):  # silent-ok: an unreadable legacy payload is listed as UNREADABLE
                parsed, readable = None, False
            points = len((parsed or {}).get("2d_plan", {}).get("east", []) or []) if readable else None
            out.append({"id": plot.id, "report_id": plot.report_id, "report_date": report_date,
                        "title": plot.title or "", "plot_type": plot.plot_type or "", "created_at": plot.created_at,
                        "readable": readable, "points": points, "plot_data": parsed if readable else None,
                        "label": LEGACY_LABEL})
    return out
