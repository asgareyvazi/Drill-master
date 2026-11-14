"""M175: ask the operator which well a DDR belongs to when the source names another well than the selected one.

The dialog shows both identities, the source evidence (which field / cell stated the well), the matching database
well and the consequence of every choice. Nothing is preselected; OK stays disabled until a choice is made and a
reason is entered. Cancelling saves nothing. The returned decision is re-validated at the persistence boundary
(``core.ddr_well_identity.validate_decision``), so a stale selection cannot be applied.
"""
from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QRadioButton, QVBoxLayout,
)

from core.ddr_well_identity import (
    CHOOSE_CREATE, CHOOSE_SELECTED, CHOOSE_SOURCE_WELL, Assessment, make_decision,
)

CHOICE_LABELS = {
    CHOOSE_SELECTED: "Import into the selected well",
    CHOOSE_SOURCE_WELL: "Import into the well named by the source",
    CHOOSE_CREATE: "Create the source well and import there",
}


class WellIdentityDialog(QDialog):
    def __init__(self, assessment: Assessment, parent=None, *, decided_by: str = ""):
        super().__init__(parent)
        self.assessment = assessment
        self.decided_by = decided_by
        self.decision: Optional[Dict] = None
        self.setWindowTitle("DDR well identity - decision required")
        layout = QVBoxLayout(self)

        intro = QLabel(assessment.message + "\nNothing is saved until you choose the target well.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        facts = QGroupBox("Identities")
        form = QFormLayout(facts)
        form.addRow("Selected well:", QLabel(assessment.selected.label() if assessment.selected else "(none)"))
        form.addRow("Source states:", QLabel(assessment.source_label()))
        evidence = "; ".join(f"{e['role']} from field '{e['field']}'" + (f" (cell {e['cell']})" if e.get("cell")
                                                                         else "")
                             for e in assessment.evidence) or "(none)"
        self.evidence_label = QLabel(evidence)
        self.evidence_label.setWordWrap(True)
        form.addRow("Evidence:", self.evidence_label)
        form.addRow("Matching well:", QLabel(", ".join(m.label() for m in assessment.matches) or
                                             "(no existing well matches the source)"))
        layout.addWidget(facts)

        choices = QGroupBox("Choose the target well")
        box = QVBoxLayout(choices)
        self.group = QButtonGroup(self)
        self.buttons: Dict[str, QRadioButton] = {}
        for index, option in enumerate(assessment.options):
            button = QRadioButton(CHOICE_LABELS.get(option, option))
            consequence = (assessment.consequences[index] if index < len(assessment.consequences) else "")
            hint = QLabel(consequence)
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #555; margin-left: 22px;")
            self.group.addButton(button)
            self.buttons[option] = button
            box.addWidget(button)
            box.addWidget(hint)
            button.toggled.connect(self._refresh)
        layout.addWidget(choices)

        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Reason (required, stored in the import audit)")
        self.reason.textChanged.connect(self._refresh)
        layout.addWidget(self.reason)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self._refresh()

    def chosen(self) -> Optional[str]:
        return next((option for option, button in self.buttons.items() if button.isChecked()), None)

    def _refresh(self, *_args) -> None:
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(bool(self.chosen() and self.reason.text().strip()))

    def _accept(self) -> None:
        choice = self.chosen()
        if not choice or not self.reason.text().strip():
            return
        self.decision = make_decision(self.assessment, choice, self.reason.text(), decided_by=self.decided_by)
        self.accept()
