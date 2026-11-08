"""M135: end-of-well package — one folder per well (or explicit wellbore) with full provenance.

``build_package`` (worker side, read-only database view) writes, into a NEW folder that never overwrites an
existing one:

* ``eowr.html`` (and ``eowr.pdf`` on request) — the W11 End-of-Well report with its M93 provenance block;
  the PDF is Qt's rich-text writer (``QTextDocument`` + ``QPrinter``), the documented PDF boundary of this
  build (no PyMuPDF);
* ``bit_runs.csv`` (M130), ``npt_reconciliation.csv`` (M134), ``mud_evaluation.csv`` (M133),
  ``calculation_history.csv`` (M67 history of the well);
* ``approvals.csv`` — every daily report in scope with its workflow approval record (or "none"), latest
  revision, and the typed "Approved By" names of the well's procedures listed SEPARATELY as typed text;
* ``manifest.json`` — scope, generation time and user, every part with status (INCLUDED / EMPTY /
  NOT INCLUDED with the reason / FAILED with the exception type), rows, sources, method version, SHA-256 and
  size; the label UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED and the approval note.

The folder is written as ``<name>.partial``; ``finalize_package`` (GUI thread) adds the mandatory audit record
with the manifest SHA-256 and only then renames it to its final name — a package without its audit record is
discarded (``discard_package``). ``verify_package`` re-hashes every file, reports changed, missing and
unlisted files, and looks the manifest hash up in the audit log.

Nothing here approves anything: a typed name is not an approval, a workflow "approve" action is a status in
DrillMaster (not a signature), and the package itself is not an approval.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core import report_provenance

PACKAGE_VERSION = "M135 end-of-well package v1"
LABEL = report_provenance.LABEL
APPROVAL_NOTE = ("A typed 'Approved By' name (operational procedures, report signature blocks) is text a user "
                 "entered; it is not an approval. The only approval records are the daily-report workflow's "
                 "'approve' actions, listed as such; none of them is a signature, and this package is not an "
                 "approval.")
AUDIT_ACTION = "end_of_well_package"
MANIFEST = "manifest.json"
PARTIAL_SUFFIX = ".partial"
INCLUDED, EMPTY, NOT_INCLUDED, FAILED = "INCLUDED", "EMPTY", "NOT INCLUDED", "FAILED"
COMPLETE, INCOMPLETE = "COMPLETE", "INCOMPLETE"
_CHUNK = 1 << 16


class PackageError(ValueError):
    """The package cannot be built or finalized as requested (nothing is overwritten)."""


@dataclass(frozen=True)
class PackageRequest:
    """Plain data captured on the GUI thread (ids, a path, flags, the user label)."""
    well_id: int
    target_dir: str                       # the final folder; must not exist yet
    wellbore_id: Optional[int] = None
    include_pdf: bool = False
    direction: str = "ltr"
    generated_by: str = ""


@dataclass
class Part:
    key: str
    file: str
    title: str
    status: str = NOT_INCLUDED
    rows: Optional[int] = None
    scope: str = ""
    sources: Tuple[str, ...] = ()
    method: str = ""
    note: str = ""
    sha256: str = ""
    bytes: Optional[int] = None


@dataclass
class PackageResult:
    partial_dir: str
    final_dir: str
    manifest: Dict[str, Any]
    manifest_sha256: str
    parts: List[Part] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.manifest["status"]


@dataclass
class Verification:
    ok: bool
    problems: List[str]
    audit: str
    manifest_sha256: str = ""
    checked: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text or "").strip("_")[:40] or "well"


def default_folder_name(well_name: str, when: Optional[datetime] = None) -> str:
    return f"EOW_{safe_name(well_name)}_{(when or _now()).strftime('%Y%m%dT%H%M%SZ')}"


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(cancel_event) -> None:
    if cancel_event is not None:
        from core.context_jobs import check_cancel
        check_cancel(cancel_event)


# ---- scope ----------------------------------------------------------------------------------------------------
def _scope(db, well_id: int, wellbore_id: Optional[int]) -> Dict[str, Any]:
    from core.database import Well, Wellbore
    with db.session_scope() as session:
        well = session.get(Well, well_id)
        if well is None:
            raise PackageError(f"Well #{well_id} does not exist in this database.")
        bore = session.get(Wellbore, wellbore_id) if wellbore_id else None
        if wellbore_id and (bore is None or bore.well_id != well_id):
            raise PackageError(f"Wellbore #{wellbore_id} is not a wellbore of well #{well_id}.")
        return {"well_id": well.id, "well": well.name or f"well #{well.id}",
                "wellbore_id": bore.id if bore is not None else None,
                "wellbore": f"{bore.name} (id {bore.id})" if bore is not None else "whole well (all wellbores)"}


def _bore_scope(scope: Dict[str, Any]) -> str:
    return (f"wellbore {scope['wellbore']} only" if scope["wellbore_id"]
            else "whole well (all wellbores)")


# ---- parts ----------------------------------------------------------------------------------------------------
def _eowr(db, request: PackageRequest, scope, folder: str, fmt: str) -> Part:
    from core.report_engine import EOWRReportEngine
    name = f"eowr.{fmt}"
    part = Part(f"eowr_{fmt}", name, f"End-of-well report ({fmt.upper()})",
                scope="whole well (the EOWR engine reads every wellbore of the well"
                      + (f"; the package scope {scope['wellbore']} does not narrow it)" if scope["wellbore_id"]
                         else ")"),
                sources=report_provenance.SOURCES["eowr"],
                method=f"{report_provenance.PROVENANCE_VERSION}; report template core/report_engine.py (eowr)")
    if fmt == "pdf" and not request.include_pdf:
        part.note = "not requested"
        return part
    engine = EOWRReportEngine(db)
    engine.direction = request.direction
    if not engine.generate(request.well_id, os.path.join(folder, name), fmt):
        part.status = FAILED
        part.note = "the EOWR engine produced no file (see the application log)"
        return part
    part.status = INCLUDED
    part.note = ("Qt rich-text PDF writer (QTextDocument + QPrinter); not byte-reproducible (embedded time)"
                 if fmt == "pdf" else "M93 provenance block and label inside")
    return part


def _bit_runs(db, request, scope, folder) -> Part:
    from core import bit_runs
    part = Part("bit_runs", "bit_runs.csv", "Bit runs (M130 workbench, no cost scenario)", scope=_bore_scope(scope),
                sources=("drilling_parameters",), method=bit_runs.RUN_METHOD,
                note="cost per metre NOT ASSESSED in the package: costs are user scenarios, not records")
    runs = bit_runs.load_runs(db, request.well_id, request.wellbore_id)
    part.rows = bit_runs.export_csv(os.path.join(folder, part.file), runs, bit_runs.compare(runs, {}),
                                    well_label=scope["well"], scope_label=part.scope)
    part.status = INCLUDED if part.rows else EMPTY
    return part


def _npt(db, request, scope, folder) -> Part:
    from core import npt_reconciliation as nr
    part = Part("npt", "npt_reconciliation.csv", "NPT events reconciled (M134)", scope=_bore_scope(scope),
                sources=("npt_reports", "time_logs_24h", "npt_event_decisions"), method=nr.RECON_METHOD)
    recon = nr.reconcile_scope(db, request.well_id, request.wellbore_id)
    part.rows = nr.export_csv(os.path.join(folder, part.file), recon, well_label=scope["well"],
                              scope_label=part.scope)
    part.status = INCLUDED if part.rows else EMPTY
    part.note = recon.summary()
    return part


MUD_COLUMNS = ("Mud report", "Date", "Sample time", "DDR", "Wellbore", "Mud type", "Property", "Value", "Unit",
               "Class", "Source / formula")


def _mud(db, request, scope, folder) -> Part:
    from core import mud_engineering as me
    part = Part("mud", "mud_evaluation.csv", "Mud evaluation of the DDR mud reports (M133)", scope=_bore_scope(scope),
                sources=("mud_reports", "daily_reports"), method=me.MUD_VERSION,
                note="recorded values only (no Fann readings are stored with DDR mud reports); "
                     "Herschel-Bulkley NOT ASSESSED")
    samples = me.load_samples(db, request.well_id, request.wellbore_id)
    not_evaluated = 0
    with open(os.path.join(folder, part.file), "w", newline="", encoding="utf-8") as handle:
        out = csv.writer(handle)
        out.writerow(["Mud evaluation", me.MUD_VERSION])
        out.writerow(["Label", me.MUD_LABEL])
        out.writerow(["Herschel-Bulkley", me.HB_STATUS])
        out.writerow(["Scope", part.scope])
        out.writerow([])
        out.writerow(MUD_COLUMNS)
        for sample in samples:
            head = [sample.id, sample.report_date, sample.sample_time, sample.report_id or "", sample.wellbore_id or "",
                    sample.mud_type]
            try:
                evaluation = me.evaluate(sample.frozen(), None)
            except (me.MudEvaluationError, ValueError) as exc:   # recorded per sample, never dropped
                not_evaluated += 1
                out.writerow(head + ["NOT EVALUATED", "", "", me.UNKNOWN, type(exc).__name__ + ": " + str(exc)])
                continue
            for row in evaluation.rows:
                out.writerow(head + [row.label, "" if row.value is None else row.value, row.unit, row.cls, row.source])
    part.rows = len(samples)
    part.status = INCLUDED if samples else EMPTY
    if not_evaluated:
        part.note += f"; {not_evaluated} sample(s) NOT EVALUATED (reason in the file)"
    return part


def _history(db, request, scope, folder) -> Part:
    from core import calculation_history as ch
    part = Part("history", "calculation_history.csv", "Calculation history of the well (M67)",
                scope="whole well (history entries are recorded per well; each row keeps its own scope column)",
                sources=("calculation history tables",), method="core/calculation_history.py export")
    entries = ch.load_history(db, well_id=request.well_id)
    part.rows = ch.export_history_csv(entries, os.path.join(folder, part.file))
    part.status = INCLUDED if part.rows else EMPTY
    return part


APPROVAL_COLUMNS = ("Record", "Id", "Date", "Wellbore", "Workflow status", "Approval record (workflow action)",
                    "Latest revision", "Typed names (NOT approvals)")


def _approvals(db, request, scope, folder) -> Part:
    from core.database import ApprovalAction, DailyReport, OperationalProcedure, ReportRevision, User
    part = Part("approvals", "approvals.csv", "Approval records and typed names", scope=_bore_scope(scope),
                sources=("daily_reports", "approval_actions", "report_revisions", "operational_procedures"),
                method=PACKAGE_VERSION, note=APPROVAL_NOTE)
    rows: List[List[Any]] = []
    with db.session_scope() as session:
        reports = session.query(DailyReport).filter(DailyReport.well_id == request.well_id)
        if request.wellbore_id:
            reports = reports.filter(DailyReport.wellbore_id == request.wellbore_id)
        for report in reports.order_by(DailyReport.report_date, DailyReport.id).all():
            action = (session.query(ApprovalAction)
                      .filter(ApprovalAction.report_id == report.id, ApprovalAction.action == "approve")
                      .order_by(ApprovalAction.created_at.desc(), ApprovalAction.id.desc()).first())
            if action is None:
                approval = "No approval recorded in DrillMaster"
            else:
                user = session.get(User, action.user_id) if action.user_id else None
                who = getattr(user, "username", None) or (f"user #{action.user_id}" if action.user_id
                                                          else "unknown user")
                approval = (f"workflow 'approve' by {who} at {action.created_at.isoformat(timespec='seconds')} "
                            "(a DrillMaster status, not a signature)")
            revision = (session.query(ReportRevision).filter(ReportRevision.report_id == report.id)
                        .order_by(ReportRevision.revision_no.desc(), ReportRevision.id.desc()).first())
            rows.append([f"Daily report #{report.report_number or '—'}", report.id,
                         report.report_date.isoformat() if report.report_date else "",
                         report.wellbore_id or "not recorded", report.status or "", approval,
                         f"revision {revision.revision_no} ({revision.status})" if revision is not None
                         else "No report revision recorded", ""])
        for proc in (session.query(OperationalProcedure).filter(OperationalProcedure.well_id == request.well_id)
                     .order_by(OperationalProcedure.id).all()):
            typed = "; ".join(f"{label}: {value}" for label, value in
                              (("Prepared by", proc.prepared_by), ("Checked by", proc.checked_by),
                               ("Approved by", proc.approved_by)) if value)
            rows.append([f"Procedure '{proc.title}'", proc.id,
                         proc.revision_date.isoformat() if proc.revision_date else "", "well level",
                         proc.status or "", "none (procedures have no approval workflow in DrillMaster)",
                         proc.revision or "", typed or "none typed"])
    with open(os.path.join(folder, part.file), "w", newline="", encoding="utf-8") as handle:
        out = csv.writer(handle)
        out.writerow(["Approval records", PACKAGE_VERSION])
        out.writerow(["Note", APPROVAL_NOTE])
        out.writerow(["Scope", part.scope])
        out.writerow([])
        out.writerow(APPROVAL_COLUMNS)
        out.writerows(rows)
    part.rows = len(rows)
    part.status = INCLUDED if rows else EMPTY
    return part


_STEPS = (("eowr_html", lambda db, r, s, f: _eowr(db, r, s, f, "html")),
          ("eowr_pdf", lambda db, r, s, f: _eowr(db, r, s, f, "pdf")),
          ("bit_runs", _bit_runs), ("npt", _npt), ("mud", _mud), ("history", _history), ("approvals", _approvals))


def _manifest(request: PackageRequest, scope: Dict[str, Any], parts: List[Part], when: datetime) -> Dict[str, Any]:
    return {
        "package": PACKAGE_VERSION, "label": LABEL, "approval_note": APPROVAL_NOTE,
        "generated_at_utc": when.isoformat(timespec="seconds"),
        "generated_by": request.generated_by or "unidentified (no signed-in user)",
        "scope": scope, "direction": request.direction,
        "status": INCOMPLETE if any(p.status == FAILED for p in parts) else COMPLETE,
        "parts": [dict(asdict(p), sources=list(p.sources)) for p in parts],
        "pdf_boundary": "Qt rich-text PDF writer (QTextDocument + QPrinter); no PyMuPDF",
    }


def build_package(db, request: PackageRequest, cancel_event=None) -> PackageResult:
    """Write every part into ``<target_dir>.partial`` and return the result (worker side: plain data only)."""
    final_dir = os.path.abspath(request.target_dir)
    partial = final_dir + PARTIAL_SUFFIX
    if os.path.exists(final_dir) or os.path.exists(partial):
        raise PackageError(f"{final_dir} already exists; a package never overwrites an existing folder.")
    if request.direction not in report_provenance.DIRECTIONS:
        raise PackageError(f"unknown text direction {request.direction!r}")
    scope = _scope(db, request.well_id, request.wellbore_id)
    os.makedirs(partial, mode=0o700)       # M136: owner-only folder on POSIX (ignored on Windows)
    parts: List[Part] = []
    written = False
    try:
        for key, step in _STEPS:
            _check(cancel_event)
            try:
                part = step(db, request, scope, partial)
            except (OSError, ValueError, LookupError, TypeError, AttributeError) as exc:
                # Recorded in the manifest as FAILED with the type only (a message may quote report data).
                part = Part(key, "", key, status=FAILED, note=f"{type(exc).__name__} while writing this part")
            if part.status in (INCLUDED, EMPTY):
                path = os.path.join(partial, part.file)
                part.sha256, part.bytes = file_sha256(path), os.path.getsize(path)
            parts.append(part)
        _check(cancel_event)
        manifest = _manifest(request, scope, parts, _now())
        data = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        with open(os.path.join(partial, MANIFEST), "wb") as handle:
            handle.write(data)
        written = True
    finally:
        if not written:                       # cancelled or failed: no half-written folder is left behind
            shutil.rmtree(partial, ignore_errors=True)
    return PackageResult(partial, final_dir, manifest, hashlib.sha256(data).hexdigest(), parts)


def finalize_package(db, result: PackageResult) -> str:
    """GUI side: mandatory audit record with the manifest hash, then the rename to the final name."""
    if not os.path.isdir(result.partial_dir) or not result.partial_dir.endswith(PARTIAL_SUFFIX):
        raise PackageError("The package folder is gone; nothing was recorded.")
    if os.path.exists(result.final_dir):
        raise PackageError(f"{result.final_dir} appeared meanwhile; it is not overwritten.")
    if file_sha256(os.path.join(result.partial_dir, MANIFEST)) != result.manifest_sha256:
        raise PackageError("The manifest changed after it was written; nothing was recorded.")
    scope = result.manifest["scope"]
    details = json.dumps({"package": os.path.basename(result.final_dir), "manifest_sha256": result.manifest_sha256,
                          "wellbore_id": scope["wellbore_id"], "status": result.status,
                          "files": sum(1 for p in result.parts if p.sha256)}, sort_keys=True)
    with db.session_scope() as session:
        db._add_mandatory_audit(session, AUDIT_ACTION, "well", scope["well_id"], scope["well"], details)
    os.rename(result.partial_dir, result.final_dir)
    return result.final_dir


def discard_package(result: PackageResult) -> None:
    """Remove an unfinalized ``.partial`` folder (never a finalized package)."""
    if result.partial_dir.endswith(PARTIAL_SUFFIX) and os.path.isdir(result.partial_dir):
        shutil.rmtree(result.partial_dir)


def find_audit(db, manifest_sha256: str) -> Optional[Dict[str, Any]]:
    from core.database import AuditLog
    with db.session_scope() as session:
        rows = (session.query(AuditLog).filter(AuditLog.action == AUDIT_ACTION,
                                               AuditLog.details.like(f"%{manifest_sha256}%"))
                .order_by(AuditLog.id).all())
        for row in rows:
            if json.loads(row.details or "{}").get("manifest_sha256") == manifest_sha256:
                return {"id": row.id, "username": row.username, "timestamp": row.timestamp,
                        "well_id": row.entity_id}
    return None


def _plain_name(name: Any) -> bool:
    """A manifest entry names one file directly inside the package folder: no directory part, no absolute path."""
    return (isinstance(name, str) and name not in ("", ".", "..") and os.path.basename(name) == name
            and "/" not in name and "\\" not in name and not os.path.isabs(name))


def verify_package(folder: str, db=None) -> Verification:
    """Re-hash every listed file; report changed, missing and unlisted files; find the audit record."""
    manifest_path = os.path.join(folder, MANIFEST)
    if not os.path.isfile(manifest_path):
        return Verification(False, [f"no {MANIFEST} in {folder}"], "not checked")
    manifest_sha = file_sha256(manifest_path)
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        parts = manifest["parts"]
    except (ValueError, KeyError, TypeError) as exc:
        return Verification(False, [f"{MANIFEST} is unreadable ({type(exc).__name__})"], "not checked", manifest_sha)
    if not isinstance(parts, list) or not all(isinstance(part, dict) for part in parts):
        return Verification(False, [f"{MANIFEST} is unreadable (its parts are not a list of entries)"], "not checked",
                            manifest_sha)
    problems, listed, checked = [], {MANIFEST}, 0
    for part in parts:
        if not part.get("sha256"):
            continue
        name = part.get("file")
        if not _plain_name(name):              # M140 (D54): never read a file outside the package folder
            problems.append(f"refused: manifest entry {name!r} is not a file name inside the package folder")
            continue
        listed.add(name)
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            problems.append(f"missing: {name}")
            continue
        checked += 1
        if file_sha256(path) != part["sha256"]:
            problems.append(f"changed: {name} (SHA-256 differs from the manifest)")
    for name in sorted(os.listdir(folder)):
        if name not in listed:
            problems.append(f"unlisted: {name}")
    if checked == 0 and not problems:            # M140 (D54): a package always carries at least its hashed EOWR
        problems.append("nothing verified: the manifest lists no file with a SHA-256")
    if db is None:
        audit = "not checked (no database)"
    else:
        record = find_audit(db, manifest_sha)
        audit = (f"audit record #{record['id']} by {record['username'] or 'unidentified'} at {record['timestamp']}"
                 if record else "NO audit record for this manifest in this database (a different database, or the "
                                "manifest was changed)")
        if record is None:
            problems.append("no matching audit record")
    return Verification(not problems, problems, audit, manifest_sha, checked)
