"""M135: End-of-well package (W11 Export Center › End-of-well package).

The user picks the well (W11 well selector) and, explicitly, a wellbore or the whole well, optionally the Qt
PDF, and a parent folder. ``core.well_package.build_package`` writes the package in the background (read-only
database view); the GUI thread then adds the mandatory audit record with the manifest SHA-256 and renames the
``.partial`` folder to its final name (``finalize_package``). The parts table shows each file's status,
rows, scope, method and SHA-256; "Verify package…" re-hashes a package folder and looks up its audit record.

Residual R2 (D59): a rename that fails after the audit record keeps the folder (it is an audited package) and
offers to complete the rename; "Stale folders…" lists the ``.partial`` folders of a parent folder, classified
by the audit log (``core.well_package.inspect_stale_folder``): an UNAUDITED one can be removed, an AUDITED one
given its final name once every file still matches; anything else is refused and left alone.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core import well_package as wp
from core.authorization import AuthorizationError
from core.context_jobs import CANCELLED, ERROR, LOADING, STALE, ContextJobRunner, check_cancel
from tabs.job_retry import REFRESH_HINT, retry_button, scope_row, show_retry

logger = logging.getLogger(__name__)

PART_COLUMNS = ("Part", "File", "Status", "Rows", "Scope", "Method", "SHA-256", "Note")
STATUS_COLOUR = {wp.INCLUDED: "#1e7d32", wp.EMPTY: "#5d6d7e", wp.NOT_INCLUDED: "#5d6d7e", wp.FAILED: "#b00020"}


class _FixedScope:
    """The package scope is the explicit request, not the global selection: navigating elsewhere while a
    package is written must not discard the finished folder (a discarded result would leave it unaudited)."""

    @staticmethod
    def context_token():
        return "end-of-well package (explicit scope)"

    @staticmethod
    def is_current(token) -> bool:
        return token == _FixedScope.context_token()


def _bores_job(db, params, cancel_event) -> List[Tuple[int, str]]:
    check_cancel(cancel_event)
    return [(b["id"], b.get("name") or f"wellbore #{b['id']}") for b in db.get_wellbores_by_well(params["well"])]


def _build_job(db, params, cancel_event) -> wp.PackageResult:
    return wp.build_package(db, params["request"], cancel_event)


def _verify_job(db, params, cancel_event) -> wp.Verification:
    check_cancel(cancel_event)
    return wp.verify_package(params["folder"], db)


class WellPackagePanel(QWidget):
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.well_id: Optional[int] = None
        self.well_name = ""
        self.result: Optional[wp.PackageResult] = None
        self.final_dir: Optional[str] = None
        self.verification: Optional[wp.Verification] = None
        self.stale: List[wp.StaleFolder] = []
        self.bore_jobs = ContextJobRunner(None, "wellbores", parent=self)
        self.bore_jobs.result_ready.connect(self._show_bores)
        self.bore_jobs.state_changed.connect(self._bores_state)
        self.bore_jobs.refresh_hint = REFRESH_HINT
        # M138: a failed build or verification is repeated with the same button, so the message names that button
        self.jobs = ContextJobRunner(None, "end-of-well package", selection=_FixedScope(),
                                     retry_hint="Build the package again to retry.", parent=self)
        self.jobs.result_ready.connect(self._built)
        self.jobs.state_changed.connect(self._job_state)
        self.verify_jobs = ContextJobRunner(None, "package verification", selection=_FixedScope(),
                                            retry_hint="Verify the folder again to retry.", parent=self)
        self.verify_jobs.result_ready.connect(self._verified)
        self.verify_jobs.state_changed.connect(self._verify_state)

        box = QGroupBox("End-of-well package — every file with its scope, sources, method and SHA-256")
        layout = QVBoxLayout(box)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        banner = QLabel(f"<b>{wp.LABEL}</b><br>{wp.APPROVAL_NOTE}")
        banner.setWordWrap(True)
        banner.setStyleSheet("border:2px solid #b00; padding:4px;")
        layout.addWidget(banner)
        row = QHBoxLayout()
        row.addWidget(QLabel("Scope:"))
        self.bore_combo = QComboBox()
        self.bore_combo.setMinimumWidth(240)
        row.addWidget(self.bore_combo)
        self.pdf_check = QCheckBox("Also the EOWR as PDF (Qt writer)")
        row.addWidget(self.pdf_check)
        row.addStretch()
        layout.addLayout(row)
        self.scope_label = QLabel("NOT ASSESSED: select a well")
        self.scope_label.setWordWrap(True)
        self.retry_btn = retry_button(self._retry, "Read the wellbores of this well again")
        layout.addLayout(scope_row(self.scope_label, self.retry_btn))
        buttons = QHBoxLayout()
        self.build_btn = QPushButton("Build package…")
        self.build_btn.clicked.connect(self._build_dialog)
        self.verify_btn = QPushButton("Verify package…")
        self.verify_btn.clicked.connect(self._verify_dialog)
        self.stale_btn = QPushButton("Stale folders…")
        self.stale_btn.setToolTip("List the '.partial' folders of a folder, classified by the audit log")
        self.stale_btn.clicked.connect(self._stale_dialog)
        self.remove_stale_btn = QPushButton("Remove unaudited")
        self.remove_stale_btn.clicked.connect(self._remove_stale_clicked)
        self.recover_stale_btn = QPushButton("Complete rename")
        self.recover_stale_btn.clicked.connect(self._recover_stale_clicked)
        buttons.addWidget(self.build_btn)
        buttons.addWidget(self.verify_btn)
        buttons.addWidget(self.stale_btn)
        buttons.addWidget(self.remove_stale_btn)
        buttons.addWidget(self.recover_stale_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.table = QTableWidget(0, len(PART_COLUMNS))
        self.table.setHorizontalHeaderLabels(PART_COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(200)
        layout.addWidget(self.table)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._set_bores([])

    # -- scope ------------------------------------------------------------------------------------------------
    def set_well(self, well_id: Optional[int], well_name: str = "") -> None:
        if well_id != self.well_id:
            self.result, self.final_dir = None, None
            self._fill([])
            self.status.setText("")
        self.well_id, self.well_name = well_id, well_name or (f"well #{well_id}" if well_id else "")
        self._set_bores([])
        self.retry_btn.setVisible(False)
        if well_id is None or self.db is None:
            self.bore_jobs.invalidate()
        else:
            self.bore_jobs.db_manager = self.db
            self.bore_jobs.start(_bores_job, {"well": well_id})
        self._update()

    def _set_bores(self, bores) -> None:
        self.bore_combo.clear()
        self.bore_combo.addItem("Whole well (all wellbores)", None)
        for bore_id, name in bores:
            self.bore_combo.addItem(f"Wellbore {name} only", bore_id)

    def _show_bores(self, _job_id, bores) -> None:
        self._set_bores(bores)

    def _bores_state(self, state: str, message: str) -> None:
        """M138: a failed wellbore list is said, not hidden behind a combo that offers only the whole well."""
        show_retry(self.retry_btn, state)
        problem = getattr(self, "_bores_problem", "")
        if state in (ERROR, STALE, CANCELLED):
            self._bores_problem = message + " Only the whole-well scope can be chosen until the wellbores are read."
            self.status.setText(self._bores_problem)
        elif problem and self.status.text() == problem:      # read again successfully: the warning goes away
            self._bores_problem = ""
            self.status.setText("")

    def _retry(self, _checked: bool = False) -> None:
        if self.well_id is not None:
            self.set_well(self.well_id, self.well_name)

    def scope_text(self) -> str:
        if self.well_id is None:
            return "NOT ASSESSED: select a well"
        bore = self.bore_combo.currentData()
        return f"{self.well_name}: " + (f"wellbore #{bore} only" if bore else "whole well (all wellbores)")

    def _update(self) -> None:
        self.scope_label.setText(self.scope_text())
        self.build_btn.setEnabled(self.well_id is not None and self.db is not None and self.jobs.state != LOADING)
        self.stale_btn.setEnabled(self.db is not None)
        self.remove_stale_btn.setEnabled(any(f.state == wp.STALE_UNAUDITED for f in self.stale))
        self.recover_stale_btn.setEnabled(any(f.state == wp.STALE_AUDITED for f in self.stale))

    # -- build ------------------------------------------------------------------------------------------------
    def build_into(self, parent_folder: str, *, wellbore_id: Optional[int] = None,
                   include_pdf: Optional[bool] = None, direction: str = "ltr") -> Optional[int]:
        if self.well_id is None or self.db is None or self.jobs.state == LOADING:
            return None
        if wellbore_id is not None:
            index = self.bore_combo.findData(wellbore_id)
            if index < 0:
                self.status.setText(f"Wellbore #{wellbore_id} is not a wellbore of this well; nothing was built.")
                return None
            self.bore_combo.setCurrentIndex(index)
        _uid, username = self.db._audit_actor()
        request = wp.PackageRequest(
            well_id=self.well_id, wellbore_id=self.bore_combo.currentData(),
            target_dir=os.path.join(parent_folder, wp.default_folder_name(self.well_name)),
            include_pdf=self.pdf_check.isChecked() if include_pdf is None else include_pdf,
            direction=direction, generated_by=username or "")
        self.result, self.final_dir = None, None
        self._fill([])
        self.status.setText(f"Writing {request.target_dir}{wp.PARTIAL_SUFFIX} …")
        self.jobs.db_manager = self.db
        job = self.jobs.start(_build_job, {"request": request})
        self._update()
        return job

    def _job_state(self, state: str, message: str) -> None:
        if state in (ERROR, STALE, CANCELLED):
            # D59: a build stopped by an error or a cancel removes its own '.partial' folder; only a killed process
            # leaves one, and it may be audited (killed after the audit record) - the audit log decides.
            self.status.setText(message + " No package was finalized. A '.partial' folder left by a process that "
                                          "was killed is classified by the audit log under 'Stale folders…'.")
        self._update()

    def _built(self, _job_id, result: wp.PackageResult) -> None:
        self.result = result
        self._fill(result.parts)
        try:
            self.final_dir = wp.finalize_package(self.db, result)
        except wp.PackageAuditedNotRenamed as exc:          # D59: audited - kept, never discarded
            self.final_dir = None
            self.stale = [wp.inspect_stale_folder(exc.partial_dir, self.db)]
            self.status.setText(f"AUDITED — NOT RENAMED: {exc}")
            self._update()
            return
        except (wp.PackageError, AuthorizationError, OSError) as exc:
            self.final_dir = None
            try:
                wp.discard_package(result, self.db)
            except (wp.PackageError, OSError) as kept:
                self.status.setText(f"Not finalized: {exc}. The folder was kept: {kept}")
            else:
                self.status.setText(f"Not finalized: {exc}. The unaudited folder was removed.")
            self._update()
            return
        failed = [p.key for p in result.parts if p.status == wp.FAILED]
        self.status.setText(f"{result.status}: {self.final_dir} — manifest SHA-256 {result.manifest_sha256[:16]}…, "
                            "audit record written." + (f" FAILED part(s): {', '.join(failed)}." if failed else ""))
        self._update()

    def _fill(self, parts) -> None:
        self.table.setRowCount(len(parts))
        for i, part in enumerate(parts):
            values = (part.title, part.file or "—", part.status, "—" if part.rows is None else str(part.rows),
                      part.scope, part.method, (part.sha256[:16] + "…") if part.sha256 else "—", part.note)
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                if j == 2:
                    from PySide6.QtGui import QColor
                    item.setForeground(QColor(STATUS_COLOUR.get(part.status, "#000000")))
                self.table.setItem(i, j, item)

    def _build_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder for the end-of-well package")
        if folder:
            self.build_into(folder, direction=self.document_direction())

    def document_direction(self) -> str:
        """The Export Center's document direction (LTR/RTL) - found through the parent chain, no reference
        back to the host is kept (no widget cycle)."""
        widget = self.parentWidget()
        while widget is not None and not hasattr(widget, "direction_combo"):
            widget = widget.parentWidget()
        return widget.direction() if widget is not None else "ltr"

    # -- verify -----------------------------------------------------------------------------------------------
    def verify(self, folder: str) -> Optional[int]:
        if self.db is None:
            return None
        self.verification = None
        self.verify_jobs.db_manager = self.db
        return self.verify_jobs.start(_verify_job, {"folder": folder})

    def _verified(self, _job_id, verification: wp.Verification) -> None:
        self.verification = verification
        if verification.ok:
            self.status.setText(f"VERIFIED: {verification.checked} file(s) match the manifest; {verification.audit}.")
        else:
            self.status.setText("NOT VERIFIED: " + "; ".join(verification.problems) + f". {verification.audit}.")

    def _verify_state(self, state: str, message: str) -> None:
        if state in (ERROR, STALE, CANCELLED):
            self.status.setText(message)

    def _verify_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "End-of-well package folder to verify")
        if folder:
            self.verify(folder)

    # -- stale '.partial' folders (D59) ---------------------------------------------------------------------
    def scan_stale(self, parent_folder: str) -> List[wp.StaleFolder]:
        """Classify every '.partial' folder of ``parent_folder`` (one manifest hash and audit lookup each)."""
        self.stale = [] if self.db is None else wp.find_stale_folders(parent_folder, self.db)
        if not self.stale:
            self.status.setText(f"No '.partial' folder in {parent_folder}.")
        else:
            self.status.setText("Stale folders: " + "; ".join(
                f"{os.path.basename(f.path)} — {f.state}: {f.reason}" for f in self.stale) + ".")
        self._update()
        return self.stale

    def remove_unaudited_stale(self) -> List[str]:
        """Remove every UNAUDITED folder of the last scan (each is classified again first)."""
        done, refused = self._apply_stale(wp.STALE_UNAUDITED, wp.remove_stale_folder)
        self.status.setText(f"Removed {len(done)} unaudited folder(s)" + (f"; refused: {'; '.join(refused)}"
                                                                         if refused else "") + ".")
        return done

    def recover_audited_stale(self) -> List[str]:
        """Give every AUDITED folder of the last scan its final name once its files still match."""
        done, refused = self._apply_stale(wp.STALE_AUDITED, wp.recover_stale_folder)
        self.status.setText(f"Renamed {len(done)} audited package(s)" + (f": {', '.join(done)}" if done else "")
                            + (f"; refused: {'; '.join(refused)}" if refused else "") + ".")
        if done:
            self.final_dir = done[-1]
        return done

    def _apply_stale(self, state: str, action) -> Tuple[List[str], List[str]]:
        done, refused, keep = [], [], []
        for folder in self.stale:
            if folder.state != state:
                keep.append(folder)
                continue
            try:
                outcome = action(folder.path, self.db)
            except (wp.PackageError, OSError) as exc:
                refused.append(str(exc))
                keep.append(wp.inspect_stale_folder(folder.path, self.db) if os.path.lexists(folder.path)
                            else folder)
            else:
                done.append(outcome if isinstance(outcome, str) else folder.path)
        self.stale = keep
        self._update()
        return done, refused

    def _stale_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder to search for '.partial' folders")
        if folder:
            self.scan_stale(folder)

    def _remove_stale_clicked(self, _checked: bool = False) -> None:
        names = [os.path.basename(f.path) for f in self.stale if f.state == wp.STALE_UNAUDITED]
        if names and QMessageBox.question(
                self, "Remove unaudited folders",
                "Delete these interrupted builds (no audit record matches them)?\n" + "\n".join(names)) \
                == QMessageBox.StandardButton.Yes:
            self.remove_unaudited_stale()

    def _recover_stale_clicked(self, _checked: bool = False) -> None:
        if any(f.state == wp.STALE_AUDITED for f in self.stale):
            self.recover_audited_stale()

    # -- lifecycle --------------------------------------------------------------------------------------------
    def wait(self, timeout_ms: int = 30000) -> bool:
        return all(r.wait(timeout_ms) for r in (self.bore_jobs, self.jobs, self.verify_jobs))

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        return all([r.shutdown(timeout_ms) for r in (self.bore_jobs, self.jobs, self.verify_jobs)])
