"""M54: review dialog for duplicating a daily report.

The dialog only collects the user's choices and shows exactly what will be
prepared. Nothing is written to the database here: the caller turns the choices
into an UNSAVED draft in the Daily Report form, which the user must review and
save explicitly (no silent persistence).
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


def default_duplicate_options(source: dict) -> dict:
    """Return the default duplicate plan for ``source`` (a report dict)."""
    src_date = source.get("report_date")
    target = src_date + timedelta(days=1) if isinstance(src_date, date) else None
    number = source.get("report_number")
    return {
        "target_date": target,
        "report_number": (int(number) + 1) if isinstance(number, int) else None,
        "copy_time_log": False,
        "copy_morning_log": False,
        "copy_summary": False,
        "carry_depth": True,
    }


def describe_duplicate_plan(source: dict, options: dict, existing_dates=()) -> list[str]:
    """Plain-English lines describing what the draft will contain."""
    lines = [
        f"Source: report #{source.get('report_number', '?')} dated {source.get('report_date', '?')}.",
        f"Draft date: {options.get('target_date') or 'not set'}; report number: {options.get('report_number') or 'not set'}.",
    ]
    lines.append(
        "00:00 depth: taken from the source 24:00 depth."
        if options.get("carry_depth")
        else "00:00 depth: left empty (unknown)."
    )
    lines.append("06:00 and 24:00 depths: left empty (unknown) — enter the new day's values.")
    lines.append("24-hour time log: " + ("copied for editing." if options.get("copy_time_log") else "starts empty."))
    lines.append("Morning log: " + ("copied for editing." if options.get("copy_morning_log") else "starts empty."))
    lines.append("Summary text: " + ("copied for editing." if options.get("copy_summary") else "starts empty."))
    lines.append("Status: Draft. Nothing is saved until you review the form and press Save Report.")
    lines.append("Mud, bit, cost and other tab records are NOT duplicated.")
    target = options.get("target_date")
    if target is not None and target in set(existing_dates):
        lines.append(f"WARNING: this well already has a report dated {target}.")
    return lines


class DuplicateReportDialog(QDialog):
    """Collects duplicate options with a live, explicit review of the plan."""

    def __init__(self, source: dict, existing_dates=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate report — review")
        self.setMinimumWidth(460)
        self._source = dict(source)
        self._existing = set(existing_dates)
        defaults = default_duplicate_options(source)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        if defaults["target_date"] is not None:
            self.date_edit.setDate(QDate(defaults["target_date"]))
        form.addRow("Draft date", self.date_edit)
        self.number_spin = QSpinBox()
        self.number_spin.setRange(1, 100000)
        self.number_spin.setValue(defaults["report_number"] or 1)
        form.addRow("Report number", self.number_spin)
        layout.addLayout(form)

        self.carry_depth = QCheckBox("Carry the source 24:00 depth into the 00:00 depth")
        self.carry_depth.setChecked(defaults["carry_depth"])
        self.copy_time_log = QCheckBox("Copy the 24-hour time log for editing")
        self.copy_morning = QCheckBox("Copy the morning (00:00–06:00) log for editing")
        self.copy_summary = QCheckBox("Copy the summary text for editing")
        for box in (self.carry_depth, self.copy_time_log, self.copy_morning, self.copy_summary):
            layout.addWidget(box)
            box.toggled.connect(self._update_review)
        self.date_edit.dateChanged.connect(self._update_review)
        self.number_spin.valueChanged.connect(self._update_review)

        self.review_label = QLabel()
        self.review_label.setWordWrap(True)
        self.review_label.setObjectName("duplicateReview")
        layout.addWidget(self.review_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Prepare draft for review")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_review()

    def options(self) -> dict:
        return {
            "target_date": self.date_edit.date().toPython(),
            "report_number": self.number_spin.value(),
            "copy_time_log": self.copy_time_log.isChecked(),
            "copy_morning_log": self.copy_morning.isChecked(),
            "copy_summary": self.copy_summary.isChecked(),
            "carry_depth": self.carry_depth.isChecked(),
        }

    def review_lines(self) -> list[str]:
        return describe_duplicate_plan(self._source, self.options(), self._existing)

    def _update_review(self, *_args):
        self.review_label.setText("\n".join(self.review_lines()))
