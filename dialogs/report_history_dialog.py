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
    QGroupBox,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
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
        vbox.addWidget(QLabel("Revisions:"))
        vbox.addWidget(table)

        # Structured, human-readable view of the selected revision's frozen
        # operational content — NOT a raw JSON dump as the primary UI (§29).
        vbox.addWidget(QLabel("Historical content of selected revision:"))
        detail = QTreeWidget()
        detail.setColumnCount(2)
        detail.setHeaderLabels(["Section", "Detail"])
        detail.setRootIsDecorated(True)
        detail.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        detail.header().setSectionResizeMode(1, QHeaderView.Stretch)
        vbox.addWidget(detail, 1)

        # Raw JSON remains available as a secondary/debug representation.
        raw = QPlainTextEdit()
        raw.setReadOnly(True)
        raw.setMaximumHeight(140)
        raw_box = QGroupBox("Raw snapshot (debug)")
        raw_box.setCheckable(True)
        raw_box.setChecked(False)
        raw_layout = QVBoxLayout(raw_box)
        raw_layout.addWidget(raw)
        raw.setVisible(False)
        raw_box.toggled.connect(raw.setVisible)
        vbox.addWidget(raw_box)

        def show_detail():
            row = table.currentRow()
            detail.clear()
            if not (0 <= row < len(revisions)):
                return
            snap = revisions[row].get("snapshot") or {}
            self._populate_revision_tree(detail, snap)
            import json
            try:
                raw.setPlainText(json.dumps(snap, indent=2, default=str, ensure_ascii=False))
            except Exception:
                raw.setPlainText(str(snap))

        table.itemSelectionChanged.connect(show_detail)
        if revisions:
            table.selectRow(0)
        return container

    # Friendly labels for the report-owned child collections.
    _CHILD_LABELS = {
        "time_logs_24h": "Time Log (24h)",
        "time_logs_morning": "Time Log (Morning)",
        "drilling_parameters": "Drilling Parameters",
        "mud_report": "Mud Report",
        "cement_report": "Cement Report",
        "casing_report": "Casing Report",
        "bit_report": "Bit Report",
        "bha_report": "BHA Report",
        "downhole_equipment": "Downhole Equipment",
        "formation_report": "Formation Report",
        "safety_report": "Safety Report",
        "wellbore_schematic": "Wellbore Schematic",
        "trip_sheet": "Trip Sheet",
        "survey": "Survey",
        "logistics_personnel": "Logistics / Personnel",
        "service_company_pob": "Service Company POB",
        "fuel_water_inventory": "Fuel / Water Inventory",
        "bulk_materials": "Bulk Materials",
        "transport_log": "Transport Log",
        "transport_notes": "Transport Notes",
        "service_company": "Service Company",
        "service_note": "Service Notes",
        "material_request": "Material Requests",
        "equipment_log": "Equipment Log",
        "seven_days_lookahead": "7-Day Lookahead",
        "npt_report": "NPT Report",
    }

    def _populate_revision_tree(self, tree, snap):
        """Render a complete revision snapshot as readable sections.

        Falls back gracefully for legacy header-only snapshots (mission §29/§52).
        """
        if not isinstance(snap, dict):
            QTreeWidgetItem(tree, ["(unreadable snapshot)", ""])
            return

        # Header section — legacy snapshots stored fields at top level; the
        # complete v1 snapshot nests them under "report".
        report = snap.get("report") if isinstance(snap.get("report"), dict) else snap
        header = QTreeWidgetItem(tree, ["Report Header", ""])
        for key in ("report_number", "report_date", "status", "well_id",
                    "section_id", "depth_0000", "depth_2400", "summary"):
            if key in report:
                QTreeWidgetItem(header, [key, str(report.get(key))])
        header.setExpanded(True)

        children = snap.get("children")
        if not isinstance(children, dict):
            note = QTreeWidgetItem(tree, ["Operational content", "legacy header-only revision"])
            note.setExpanded(True)
            return

        any_child = False
        for key, rows in children.items():
            if not rows:
                continue
            any_child = True
            label = self._CHILD_LABELS.get(key, key)
            section = QTreeWidgetItem(tree, [label, f"{len(rows)} row(s)"])
            for idx, entry in enumerate(rows, 1):
                row_node = QTreeWidgetItem(section, [f"#{idx}", self._row_summary(entry)])
                for fk, fv in entry.items():
                    if fv is None or fv == "" or fk in ("id", "report_id", "created_at", "updated_at"):
                        continue
                    QTreeWidgetItem(row_node, [fk, str(fv)])
        if not any_child:
            QTreeWidgetItem(tree, ["Operational content", "No child records captured"])

    @staticmethod
    def _row_summary(entry):
        """A short one-line summary for a child row."""
        for key in ("activity_description", "main_phase", "mud_type", "bha_name",
                    "bit_no", "md", "npt_category", "description", "name"):
            if entry.get(key):
                return str(entry[key])
        return ""

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
