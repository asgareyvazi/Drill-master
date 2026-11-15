"""M217: the operator chooses what may be carried from the previous day, and confirms it.

Nothing is preselected. A section with nothing to carry, or one that already has rows today, cannot be chosen.
The sections that are never carried are listed with the reason. OK stays disabled until at least one item is
chosen and the confirmation box is ticked.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QLabel, QVBoxLayout)


class CarryForwardDialog(QDialog):
    def __init__(self, plan: dict, parent=None):
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Carry forward from the previous day")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"From report of {plan['source_date']} to the report of {plan['target_date']}. "
                                "Carried sections stay marked CARRIED until you confirm them for the new day."))
        carry_box = QGroupBox("May be carried (choose explicitly)")
        carry_layout = QVBoxLayout(carry_box)
        self.section_boxes = {}
        for item in plan["carryable"]:
            text = f"{item['label']} - {item['rows']} row(s)"
            if item["blocked"]:
                text += f"  ({item['blocked']})"
            box = QCheckBox(text)
            box.setObjectName(f"carry_{item['key']}")
            box.setEnabled(not item["blocked"])
            box.toggled.connect(self._update)
            carry_layout.addWidget(box)
            self.section_boxes[item["key"]] = box
        layout.addWidget(carry_box)
        self.header_boxes = {}
        derived = {k: v for k, v in (plan.get("derived_header") or {}).items() if v is not None}
        if derived:
            header_box = QGroupBox("Report header derived from the previous report")
            header_layout = QVBoxLayout(header_box)
            labels = {"depth_0000": "Depth at 00:00 = previous depth at 24:00",
                      "rig_day": "Rig day = previous rig day + 1"}
            for field, value in derived.items():
                box = QCheckBox(f"{labels.get(field, field)} ({value})")
                box.setObjectName(f"derive_{field}")
                box.toggled.connect(self._update)
                header_layout.addWidget(box)
                self.header_boxes[field] = box
            layout.addWidget(header_box)
        never = [n for n in plan["never_carried"] if n["rows"]] or plan["never_carried"]
        never_label = QLabel("Never carried (measured or happening on its own day):\n" + "\n".join(
            f"• {n['label']}: {n['reason']}" for n in never))
        never_label.setObjectName("never_carried_label")
        never_label.setWordWrap(True)
        layout.addWidget(never_label)
        self.confirm_box = QCheckBox(f"I confirm the chosen values are still valid on {plan['target_date']}")
        self.confirm_box.setObjectName("carry_confirm")
        self.confirm_box.toggled.connect(self._update)
        layout.addWidget(self.confirm_box)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update()

    def selected_sections(self):
        return [key for key, box in self.section_boxes.items() if box.isEnabled() and box.isChecked()]

    def selected_header(self):
        return [key for key, box in self.header_boxes.items() if box.isChecked()]

    def confirmed(self) -> bool:
        return self.confirm_box.isChecked()

    def _update(self, *_):
        ready = self.confirm_box.isChecked() and bool(self.selected_sections() or self.selected_header())
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(ready)


class DayStatesDialog(QDialog):
    """Read-only states of a report's sections, with the confirmation of carried sections."""

    def __init__(self, states: dict, parent=None):
        from PySide6.QtWidgets import QPushButton, QTableWidget, QTableWidgetItem
        super().__init__(parent)
        self.setWindowTitle("Day states")
        self.confirm_requested = False
        layout = QVBoxLayout(self)
        table = QTableWidget(len(states), 4, self)
        table.setObjectName("day_states_table")
        table.setHorizontalHeaderLabels(["Section", "State", "Rows", "Carried from report"])
        for row, (key, entry) in enumerate(states.items()):
            for col, value in enumerate((entry["label"], entry["state"], entry["rows"],
                                         entry.get("source_report_id", ""))):
                table.setItem(row, col, QTableWidgetItem(str(value)))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(table)
        self.table = table
        carried = [e["label"] for e in states.values() if e["state"] == "CARRIED"]
        self.confirm_button = QPushButton(f"Confirm {len(carried)} carried section(s) for this day")
        self.confirm_button.setObjectName("confirm_carried")
        self.confirm_button.setEnabled(bool(carried))
        self.confirm_button.clicked.connect(self._confirm)
        layout.addWidget(self.confirm_button)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def _confirm(self):
        self.confirm_requested = True
        self.accept()
