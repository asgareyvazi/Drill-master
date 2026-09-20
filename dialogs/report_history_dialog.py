"""Read-only Daily Report revision & approval history browser.

Surfaces the two distinct audit streams the backend already persists for a
Daily Report:

* Revision history — immutable snapshots created at each workflow transition
  (``get_report_revisions``). Each row is a frozen copy of the report body at
  that point, with its status, author, timestamp and comment.
* Approval history — the workflow action log (``get_approval_history``):
  submit / approve / reject / finalize, who did it, when, and any comment.

The dialog never edits or deletes history; it is observational only. Empty
states are honest ("No revision history available"). It is intentionally
specific to the Daily Report — no generic diff/audit engine (mission §16/§32).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _fmt_dt(value) -> str:
    if value is None:
        return "—"
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except (AttributeError, ValueError):
        return str(value)


class ReportHistoryDialog(QDialog):
    def __init__(self, db_manager, report_id: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.report_id = report_id
        self.setWindowTitle(f"Report History — Report #{report_id}")
        self.resize(880, 560)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        revisions = self.db_manager.get_report_revisions(report_id)
        actions = self.db_manager.get_approval_history(report_id)
        user_ids = {r.get("created_by") for r in revisions}
        user_ids |= {a.get("user_id") for a in actions}
        self._names = self.db_manager.get_usernames_by_id(user_ids)

        tabs.addTab(self._build_revision_tab(revisions), "📄 Revision History")
        tabs.addTab(self._build_approval_tab(actions), "🕑 Approval History")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _name(self, uid):
        if uid is None:
            return "—"
        return self._names.get(uid, f"user #{uid}")

    def _build_revision_tab(self, revisions):
        container = QWidget()
        vbox = QVBoxLayout(container)
        if not revisions:
            vbox.addWidget(QLabel("No revision history available."))
            return container

        table = QTableWidget(len(revisions), 5)
        table.setHorizontalHeaderLabels(["Revision #", "Status", "Date", "User", "Comment"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)
        for row, rev in enumerate(revisions):
            table.setItem(row, 0, QTableWidgetItem(str(rev.get("revision_no", ""))))
            table.setItem(row, 1, QTableWidgetItem(str(rev.get("status", ""))))
            table.setItem(row, 2, QTableWidgetItem(_fmt_dt(rev.get("created_at"))))
            table.setItem(row, 3, QTableWidgetItem(self._name(rev.get("created_by"))))
            table.setItem(row, 4, QTableWidgetItem(str(rev.get("comment") or "")))
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        table.resizeColumnsToContents()
        vbox.addWidget(table)

        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        detail.setPlaceholderText("Select a revision to view its snapshot.")
        vbox.addWidget(detail)

        def show_detail():
            row = table.currentRow()
            if 0 <= row < len(revisions):
                snap = revisions[row].get("snapshot") or {}
                lines = [f"{k}: {v}" for k, v in sorted(snap.items())]
                detail.setPlainText("\n".join(lines) if lines else "(empty snapshot)")

        table.itemSelectionChanged.connect(show_detail)
        return container

    def _build_approval_tab(self, actions):
        container = QWidget()
        vbox = QVBoxLayout(container)
        if not actions:
            vbox.addWidget(QLabel("No approval history available."))
            return container

        table = QTableWidget(len(actions), 5)
        table.setHorizontalHeaderLabels(["Action", "Resulting Status", "Date", "User", "Comment"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)
        for row, act in enumerate(actions):
            table.setItem(row, 0, QTableWidgetItem(str(act.get("action", ""))))
            table.setItem(row, 1, QTableWidgetItem(str(act.get("status", ""))))
            table.setItem(row, 2, QTableWidgetItem(_fmt_dt(act.get("created_at"))))
            table.setItem(row, 3, QTableWidgetItem(self._name(act.get("user_id"))))
            table.setItem(row, 4, QTableWidgetItem(str(act.get("comment") or "")))
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        table.resizeColumnsToContents()
        vbox.addWidget(table)
        return container
