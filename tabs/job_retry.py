"""M138: the Retry button that the background-job messages refer to.

``ContextJobRunner`` tells the user "Press Retry" when a job fails (and, for the panels below, also when a result
was discarded as stale or the job was cancelled). A panel that shows those messages must offer that button. It is
hidden unless the panel's last job ended in one of those states, and the panels connect it to a re-read of their
*current* scope - never to a replay of the failed job's parameters.
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from core.context_jobs import CANCELLED, ERROR, STALE

RETRY_STATES = (ERROR, STALE, CANCELLED)
#: STALE hint for panels whose Retry re-reads the current scope (the runner's default names a Refresh button)
REFRESH_HINT = "Press Retry to read the current scope."


def retry_button(slot, tooltip: str = "Read the current scope again") -> QPushButton:
    button = QPushButton("Retry")
    button.setToolTip(tooltip)
    button.setVisible(False)
    button.clicked.connect(slot)
    return button


def scope_row(label: QLabel, button: QPushButton) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(label, 1)
    row.addWidget(button)
    return row


def show_retry(button: QPushButton, state: str) -> None:
    button.setVisible(state in RETRY_STATES)
